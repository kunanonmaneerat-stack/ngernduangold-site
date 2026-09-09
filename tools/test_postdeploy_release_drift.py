#!/usr/bin/env python3
"""Focused release-drift contract tests; no network or workspace writes."""
import importlib.util
import json
import os
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))
import release_contract
spec = importlib.util.spec_from_file_location("postdeploy_smoke", HERE / "postdeploy_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class FakeResponse:
    def __init__(self, body, *, final_url, status=200):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.final_url = final_url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.final_url

    def getcode(self):
        return self.status

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


def page(canonical, body="same", newline="\n"):
    return newline.join([
        "<!doctype html><html><head>",
        f'<link rel="canonical" href="{canonical}">',
        "</head><body>", body, "</body></html>",
    ])


def run():
    base = "https://ngernduangold.com/a"
    local = {"a.html": page(base)}
    assert smoke.compare_release_pages({base: page(base)}, local) == {}

    # Transport newline changes alone are not a release mismatch.
    assert smoke.compare_release_pages(
        {base: page(base, newline="\r\n")}, local) == {}

    stale = smoke.compare_release_pages({base: page(base, "old")}, local)
    assert "differs" in stale[base][0]

    missing_live = smoke.compare_release_pages({}, local)
    assert "absent" in missing_live[base][0]

    # A top-level sitemap failure blocks parity, but cannot prove that every
    # audited local page is absent from production.
    sitemap_unknown = smoke.compare_release_pages(
        {"SITEMAP": "__FETCH_FAIL__ URLError"}, local)
    assert sitemap_unknown == {}, sitemap_unknown

    # A page-body failure also remains blocking through check_page(), while the
    # exact URL still proves that the page was present in the fetched sitemap.
    page_unknown = smoke.compare_release_pages(
        {base: "__FETCH_FAIL__ TimeoutError"}, local)
    assert page_unknown == {}, page_unknown
    _count, page_fetch_fails = smoke.check_page("__FETCH_FAIL__ TimeoutError")
    assert page_fetch_fails and "fetch" in page_fetch_fails[0]

    extra_live = smoke.compare_release_pages(
        {base: page(base), base + "-extra": page(base + "-extra")}, local)
    assert "no matching" in extra_live[base + "-extra"][0]

    no_canonical = smoke.compare_release_pages(
        {}, {"bad.html": "<html><body>bad</body></html>"})
    assert "no canonical" in no_canonical["LOCAL:bad.html"][0]

    duplicate = smoke.compare_release_pages(
        {base: page(base)}, {"a.html": page(base), "b.html": page(base)})
    assert "duplicate" in duplicate["LOCAL:b.html"][0]

    duplicate_live = smoke.compare_release_pages(
        {base: page(base), base + "?copy=1": page(base)}, local)
    assert "duplicate production canonical" in duplicate_live[base + "?copy=1"][0]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "index.html").write_text("one", encoding="utf-8")
        good = release_contract.manifest_for(root, HERE.parent)
        assert smoke.compare_release_manifest(good, root, HERE.parent) == []
        bad = dict(good)
        bad["tree_sha256"] = "0" * 64
        mismatch = smoke.compare_release_manifest(bad, root, HERE.parent)
        assert mismatch and "differ" in mismatch[0], mismatch
        assert "schema" in smoke.compare_release_manifest(None, root, HERE.parent)[0]
        provenance = dict(good)
        provenance["source_sha256"] = {}
        assert "provenance" in smoke.compare_release_manifest(
            provenance, root, HERE.parent
        )[0]

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        src = repo / "site"
        src.mkdir(parents=True)
        for relative in release_contract.SOURCE_INPUTS:
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source", encoding="utf-8")
            os.utime(path, (100, 100))
        index = src / "index.html"
        index.write_text("built", encoding="utf-8")
        os.utime(index, (200, 200))
        assert smoke.local_build_freshness(src, repo) == []
        policy = repo / ".system_control" / "policy.json"
        os.utime(policy, (300, 300))
        assert "older" in smoke.local_build_freshness(src, repo)[0]

    calls = []
    sitemap_url = smoke.BASE + "/sitemap.xml"
    page_url = smoke.BASE + "/a"

    def valid_open(request, timeout):
        calls.append(request.full_url)
        if request.full_url == sitemap_url:
            return FakeResponse("<urlset><loc>%s</loc></urlset>" % page_url,
                                final_url=sitemap_url)
        if request.full_url == page_url:
            return FakeResponse(page(page_url), final_url=page_url)
        raise AssertionError("unexpected outbound URL")

    assert smoke.pages_live(open_fn=valid_open) == {page_url: page(page_url)}
    assert calls == [sitemap_url, page_url]

    calls.clear()
    external = "https://example.invalid/tracker"

    def external_loc_open(request, timeout):
        calls.append(request.full_url)
        return FakeResponse("<urlset><loc>%s</loc></urlset>" % external,
                            final_url=sitemap_url)

    external_result = smoke.pages_live(open_fn=external_loc_open)
    assert calls == [sitemap_url]
    assert "off-origin" in external_result["SITEMAP-LOC-1"]

    calls.clear()

    def redirect_open(request, timeout):
        calls.append(request.full_url)
        if request.full_url == sitemap_url:
            return FakeResponse("<urlset><loc>%s</loc></urlset>" % page_url,
                                final_url=sitemap_url)
        return FakeResponse("external", final_url=external)

    redirected = smoke.pages_live(open_fn=redirect_open)
    assert calls == [sitemap_url, page_url]
    assert redirected[page_url].startswith("__FETCH_FAIL__")

    def error_status_open(request, timeout):
        return FakeResponse(
            "<urlset><loc>%s</loc></urlset>" % page_url,
            final_url=sitemap_url,
            status=404,
        )

    status_failed = smoke.pages_live(open_fn=error_status_open)
    assert status_failed["SITEMAP"].startswith("__FETCH_FAIL__")

    assert not smoke._exact_base_url("https://ngernduangold.com.evil.invalid/a")
    assert not smoke._exact_base_url("https://user@ngernduangold.com/a")
    assert not smoke._exact_base_url(smoke.BASE + "/a?tracking=1")
    _count, unsafe_canonical = smoke.check_page(
        '<link rel="canonical" href="https://user@ngernduangold.com/a">'
    )
    assert any("canonical host/shape" in item for item in unsafe_canonical)

    manifest_url = smoke.BASE + "/release-manifest.json"

    def manifest_redirect(request, timeout):
        assert request.full_url == manifest_url
        return FakeResponse("{}", final_url=external)

    assert smoke.fetch_release_manifest(open_fn=manifest_redirect) is None
    redirected_payload, redirected_error = smoke.fetch_release_manifest_evidence(
        open_fn=manifest_redirect
    )
    assert redirected_payload is None
    assert redirected_error == "release manifest fetch failed: ValueError"

    canonical_manifest = {
        "schema_version": 2,
        "algorithm": "sha256-tree-v1",
        "file_count": 0,
    }
    canonical_body = json.dumps(canonical_manifest, separators=(",", ":"))

    def manifest_body_open(body):
        def open_manifest(request, timeout):
            assert request.full_url == manifest_url
            return FakeResponse(body, final_url=manifest_url)
        return open_manifest

    assert smoke.fetch_release_manifest(
        open_fn=manifest_body_open(canonical_body)
    ) == canonical_manifest
    canonical_payload, canonical_error = smoke.fetch_release_manifest_evidence(
        open_fn=manifest_body_open(canonical_body)
    )
    assert canonical_payload == canonical_manifest
    assert canonical_error is None

    malformed_manifests = (
        '{"schema_version":999,"schema_version":2}',
        '{"schema_version":2,"contracts":{"offer_safety":1,"offer_safety":2}}',
        '{"schema_version":NaN}',
        '{"schema_version":Infinity}',
        '{"schema_version":-Infinity}',
        '{"schema_version":1e999}',
    )
    for body in malformed_manifests:
        assert smoke.fetch_release_manifest(
            open_fn=manifest_body_open(body)
        ) is None, body
        malformed_payload, malformed_error = smoke.fetch_release_manifest_evidence(
            open_fn=manifest_body_open(body)
        )
        assert malformed_payload is None, body
        assert malformed_error.startswith("release manifest parse failed: "), body
    print("postdeploy release drift: exact-origin and redirect regressions PASS")


if __name__ == "__main__":
    run()
