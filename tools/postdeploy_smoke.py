#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""postdeploy_smoke — auto-verify affiliate buttons / sub_id / rel / GA4 / og / no-linktr
across every page. กัน flow คลิกทำเงินพังเงียบเวลาแก้เว็บ. stdlib only.

MODES
  --src DIR    ตรวจ HTML ที่ build แล้วในเครื่อง (เช่น --src site) = BUILD-TIME GATE.
               exit code != 0 ถ้ามี fail → Netlify deploy ล้ม → เวอร์ชันพังไม่ขึ้น live.
  --live       fetch หน้า live จริงจาก sitemap.xml = DAILY RE-CHECK.
OPTIONS
  --compare-src DIR   ใช้ร่วมกับ --live เท่านั้น; เทียบ canonical HTML และ aggregate
                      SHA-256 release manifest เพื่อจับ deploy drift ทั้งหน้าและ asset.
  --report [PATH]      เขียนรายงาน markdown (default automation-log/smoke-latest.md)
  --telegram-on-fail   ยิง Telegram เฉพาะตอน fail (ผ่านเงียบ)

ASSERT ต่อปุ่ม a[href*=atth.me]: rel มี sponsored+nofollow+noopener · data-provider อยู่ใน canon ·
  href มี campaign code · utm_content = channel_page_provider (lowercase, provider in canon)
ASSERT per page: GA4 G-17PPE0M1B8 + scoped event taxonomy
  (affiliate / own product / LINE lead / internal CTA) + og:image + og:title + 0 linktr.ee
(หมายเหตุ: การ build sub_id ตอน ?utm_source=test เป็น runtime JS — ตรวจระดับ runtime ด้วย Playwright แยก
 ดู postdeploy_click_test.py; สคริปต์นี้ตรวจ static ingredients ครบ)
"""
import os, re, sys, argparse, datetime, urllib.request, json
from html import unescape
from urllib.parse import parse_qs, urlsplit

try:
    from release_contract import (
        SOURCE_INPUTS,
        _strict_json_loads as strict_release_manifest_loads,
        file_hashes as _contract_file_hashes,
        manifest_findings,
        tree_hash as _contract_tree_hash,
    )
except ModuleNotFoundError:  # package import used by focused tests
    from tools.release_contract import (
        SOURCE_INPUTS,
        _strict_json_loads as strict_release_manifest_loads,
        file_hashes as _contract_file_hashes,
        manifest_findings,
        tree_hash as _contract_tree_hash,
    )

# Windows console may be cp874 (Thai) and crash on emoji — force UTF-8, never raise.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GA_ID = "G-17PPE0M1B8"
CANON = {"krungsri", "kept", "srisawad", "carforcash", "ktcphboom", "ngernturbo", "kashjoy",
         "happycash", "ktcproud", "ktccard", "ladytitanium", "refinance", "loan",
         "scbprotect", "scb", "axapa", "axamotor", "gettgo", "klook", "anc", "tuneprotect", "msig", "thanachart", "fwd", "viriyah"}
BASE = "https://ngernduangold.com"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MAX_SITEMAP_BYTES = 2 * 1024 * 1024
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_RELEASE_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_SITEMAP_URLS = 500

EVENT_TAXONOMY_MARKERS = {
    "scoped affiliate classifier": 'var aff=/sponsored/.test(rel)||',
    "affiliate_click": 'if(aff){gtag("event","affiliate_click"',
    "buy_intent_click": 'else if(product){gtag("event","buy_intent_click"',
    "line_lead_click": 'else if(u.hostname==="line.me"){gtag("event","line_lead_click"',
    "internal_cta_click": 'else if(u.origin===location.origin&&cta){gtag("event","internal_cta_click"',
}

def _attrs(tag):
    attrs = {}
    for match in re.finditer(
            r'''([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')''', tag):
        attrs[match.group(1).lower()] = (
            match.group(2) if match.group(2) is not None else match.group(3))
    return attrs


def load_merchant_products(path=None):
    path = path or os.path.join(REPO, ".system_control", "merchant_offers.json")
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    products = payload.get("products") if isinstance(payload, dict) else None
    if (not isinstance(payload, dict) or payload.get("schema_version") != 2 or
            not isinstance(products, dict) or not products):
        raise ValueError("merchant registry is missing or unsupported")
    return products


def _affiliate_traits(href, rel_tokens):
    """Classify a literal non-inert affiliate href without following it."""
    if not href or href.startswith(("#", "javascript:")):
        return False, False, False
    try:
        parsed = urlsplit(href)
    except ValueError:
        return False, False, False
    host = (parsed.hostname or "").lower()
    atth = host == "atth.me" or host.endswith(".atth.me")
    own_host = not host or host in {"ngernduangold.com", "www.ngernduangold.com"}
    internal_go = own_host and re.match(r"^/go(?:/|$)", parsed.path, re.I) is not None
    tracked = "sponsored" in rel_tokens or atth or internal_go
    return tracked, atth, internal_go

def _canonical(html):
    for tag in re.findall(r"<link\b[^>]*>", html, re.I):
        attrs = _attrs(tag)
        if "canonical" in attrs.get("rel", "").lower().split():
            return unescape(attrs.get("href", ""))
    return None

def _release_text(html):
    """Normalize transport-only newline differences, not content differences."""
    return html.replace("\r\n", "\n").replace("\r", "\n").strip()

def _release_hashes(src):
    return _contract_file_hashes(src)

def _tree_hash(files):
    return _contract_tree_hash(files)

def compare_release_manifest(payload, src, repo=REPO):
    return manifest_findings(payload, src, repo)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never let a production attestation follow traffic to another resource."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _exact_base_url(value):
    """Accept only query-free HTTPS resources on the exact configured origin."""
    try:
        parsed = urlsplit(str(value).strip())
        base = urlsplit(BASE)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return bool(
        parsed.scheme.casefold() == base.scheme.casefold() == "https"
        and (parsed.hostname or "").casefold() == (base.hostname or "").casefold()
        and parsed.username is None
        and parsed.password is None
        and port is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path.startswith("/")
    )


def _same_resource(left, right):
    try:
        a, b = urlsplit(left), urlsplit(right)
    except (TypeError, ValueError):
        return False
    return (
        a.scheme.casefold(), (a.hostname or "").casefold(), a.port, a.path
    ) == (
        b.scheme.casefold(), (b.hostname or "").casefold(), b.port, b.path
    ) and not any((a.query, a.fragment, b.query, b.fragment))


def _read_live_resource(url, *, user_agent, max_bytes, open_fn=None):
    """Read one bounded exact-origin resource without following redirects."""
    if not _exact_base_url(url):
        raise ValueError("live resource is outside the exact BASE origin")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    opener = open_fn
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirectHandler()).open
    with opener(req, timeout=25) as response:
        final_url = response.geturl() if hasattr(response, "geturl") else url
        if not _exact_base_url(final_url) or not _same_resource(url, final_url):
            raise ValueError("live resource redirected away from the exact requested URL")
        status = response.getcode() if hasattr(response, "getcode") else None
        if (
            not isinstance(status, int)
            or isinstance(status, bool)
            or not 200 <= status < 300
        ):
            raise ValueError("live resource returned a non-success HTTP status")
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("live resource exceeds the bounded evidence size")
    return payload


def fetch_release_manifest_evidence(open_fn=None):
    """Return the live manifest plus a bounded transport/parse diagnostic."""
    try:
        payload = _read_live_resource(
            BASE + "/release-manifest.json",
            user_agent="ngernduangold-release-audit",
            max_bytes=MAX_RELEASE_MANIFEST_BYTES,
            open_fn=open_fn,
        )
    except Exception as exc:
        return None, "release manifest fetch failed: %s" % type(exc).__name__
    try:
        return strict_release_manifest_loads(payload.decode("utf-8")), None
    except Exception as exc:
        return None, "release manifest parse failed: %s" % type(exc).__name__


def fetch_release_manifest(open_fn=None):
    payload, _diagnostic = fetch_release_manifest_evidence(open_fn=open_fn)
    return payload

def local_build_freshness(src, repo=REPO):
    """Fail when the generated comparison tree predates its canonical sources."""
    src = os.path.abspath(src)
    index = os.path.join(src, "index.html")
    if not os.path.isfile(index):
        return ["release drift: audited local build has no index.html"]
    generated_at = os.path.getmtime(index)
    build_inputs = [os.path.join(repo, *str(path).split("/"))
                    for path in SOURCE_INPUTS]
    missing_inputs = [path for path in build_inputs if not os.path.isfile(path)]
    if missing_inputs:
        return ["release drift: required build input is missing: " +
                os.path.relpath(missing_inputs[0], repo)]
    stale = any(os.path.getmtime(path) > generated_at for path in build_inputs)
    if not stale:
        for name in os.listdir(repo):
            source = os.path.join(repo, name)
            target = os.path.join(src, name)
            if (name.endswith(".html") and os.path.isfile(source)
                    and os.path.isfile(target)
                    and os.path.getmtime(source) > os.path.getmtime(target)):
                stale = True
                break
    return (["release drift: audited local site is older than its canonical source"]
            if stale else [])

def compare_release_pages(live_pages, local_pages):
    """Return {page: [fail]} when production is not the exact local release.

    Both inputs contain HTML strings.  Local pages are keyed by filename while
    live pages are keyed by URL.  Canonicals are the join key, so extensionless
    routes and index.html are handled without guessing from filenames.

    A failed sitemap fetch makes production membership UNKNOWN.  In that state
    the caller keeps the fetch failure as a blocking finding, but this function
    must not manufacture "absent from production sitemap" drift for every local
    page.  A failed page fetch is different: its exact URL came from a sitemap
    that was read successfully, so membership is known even though HTML parity
    remains blocked by the fetch failure.
    """
    fails = {}
    local_by_canonical = {}
    for filename, html in local_pages.items():
        canonical = _canonical(html)
        if not canonical:
            fails.setdefault("LOCAL:" + filename, []).append(
                "release drift: local page has no canonical")
            continue
        if canonical in local_by_canonical:
            fails.setdefault("LOCAL:" + filename, []).append(
                "release drift: duplicate local canonical " + canonical)
            continue
        local_by_canonical[canonical] = html

    sitemap_membership_known = not any(
        name == "SITEMAP" and html.startswith("__FETCH_FAIL__")
        for name, html in live_pages.items()
    )
    live_canonicals = set()
    live_owner = {}
    for url, html in live_pages.items():
        if html.startswith("__FETCH_FAIL__"):
            if _exact_base_url(url):
                # The URL was parsed from a successfully fetched sitemap.  Do
                # not turn an unreadable page body into a false absence claim.
                live_canonicals.add(url)
            continue
        canonical = _canonical(html) or url
        live_canonicals.add(canonical)
        if canonical in live_owner:
            fails.setdefault(url, []).append(
                "release drift: duplicate production canonical also used by " +
                live_owner[canonical])
        else:
            live_owner[canonical] = url
        local_html = local_by_canonical.get(canonical)
        if local_html is None:
            fails.setdefault(url, []).append(
                "release drift: production page has no matching local canonical")
        elif _release_text(html) != _release_text(local_html):
            fails.setdefault(url, []).append(
                "release drift: production HTML differs from the audited local build")

    if sitemap_membership_known:
        for canonical in sorted(set(local_by_canonical) - live_canonicals):
            fails.setdefault(canonical, []).append(
                "release drift: audited local page is absent from production sitemap")
    return fails

def check_page(html, products=None, expected_url=None):
    """return (button_count, [fail strings])"""
    fails, btn = [], 0
    if html.startswith("__FETCH_FAIL__"):
        return 0, ["fetch ล้ม: " + html[:80]]
    # HTML-looking strings inside JavaScript are runtime templates, not literal
    # anchors. Treating them as DOM nodes creates false passes and false fails;
    # runtime behavior belongs to postdeploy_click_test.py.
    markup = re.sub(r"<script\b[^>]*>.*?</script>", "", html,
                    flags=re.I | re.S)
    if re.search(r"linktr", html, re.I):
        fails.append("พบ linktr.ee/Linktree")
    if GA_ID not in html:
        fails.append("ไม่พบ GA4 " + GA_ID)
    for label, marker in EVENT_TAXONOMY_MARKERS.items():
        if marker not in html:
            fails.append("event taxonomy missing: " + label)
    if "og:image" not in html:
        fails.append("ไม่มี og:image")
    if "og:title" not in html:
        fails.append("ไม่มี og:title")
    canonical = _canonical(html)
    if not canonical:
        fails.append("ไม่มี canonical")
    else:
        if not _exact_base_url(canonical):
            fails.append("canonical host/shape ผิด: " + canonical[:80])
        elif expected_url and canonical.rstrip("/") != expected_url.rstrip("/"):
            fails.append("canonical ไม่ใช่ self URL: " + canonical[:80])

    anchor_rows = []
    for match in re.finditer(r"<a\b[^>]*>", markup, re.I):
        tag = match.group(0)
        attrs = _attrs(tag)
        href = unescape(attrs.get("href", ""))
        rel_tokens = set(attrs.get("rel", "").lower().split())
        tracked, atth, internal_go = _affiliate_traits(href, rel_tokens)
        if tracked:
            anchor_rows.append((match.start(), tag, attrs, href, rel_tokens,
                                atth, internal_go))

    # FTC clear-and-conspicuous: disclosure precedes every first literal
    # affiliate path, including future /go links, without following the target.
    if anchor_rows:
        # negative lookbehind: "ไม่มีลิงก์พันธมิตร" (หน้าที่ไม่มี affiliate) ต้องไม่นับเป็น disclosure
        _dp = [m.start() for ph in ("มีลิงก์พันธมิตร", "ได้รับค่าตอบแทน")
               for m in re.finditer("(?<!ไม่)" + ph, markup)]
        if not _dp or min(_dp) > anchor_rows[0][0]:
            fails.append("affiliate disclosure ไม่อยู่เหนือ CTA แรก (FTC clear & conspicuous)")

    for _, tag, a, href, rel_tokens, atth, internal_go in anchor_rows:
        own_product = "data-buy" in a or "data-note" in a
        if own_product:
            fails.append("own-product CTA is classified as affiliate: " + href[:60])
        btn += 1
        code = "go"
        if atth:
            m = re.search(r"https://(?:[^/]+\.)?atth\.me/((?:go/)?[0-9A-Za-z]+)",
                          href, re.I)
            code = m.group(1) if m else "?"
            if not m:
                fails.append("ปุ่ม atth.me href ว่าง/ไม่มี code: " + href[:40])
        for need in ("sponsored", "nofollow", "noopener"):
            if need not in rel_tokens:
                fails.append("ปุ่ม %s ขาด rel '%s'" % (code, need))
        prov = a.get("data-provider", "")
        if not prov:
            fails.append("ปุ่ม %s ไม่มี data-provider" % code)
        elif products is not None:
            product = products.get(prov)
            if not isinstance(product, dict):
                fails.append("ปุ่ม %s data-provider '%s' ไม่อยู่ใน registry" % (code, prov))
            elif product.get("availability") != "active":
                fails.append("ปุ่ม %s provider '%s' ไม่ active" % (code, prov))
        elif prov not in CANON:
            fails.append("ปุ่ม %s data-provider '%s' ไม่อยู่ใน canon" % (code, prov))

        content_id = a.get("data-content-id", "")
        if not content_id:
            fails.append("ปุ่ม %s ไม่มี data-content-id" % code)
        elif products is not None and isinstance(products.get(prov), dict):
            if content_id not in products[prov].get("allowed_content_ids", []):
                fails.append("ปุ่ม %s provider '%s' ไม่ผ่าน content fit '%s'"
                             % (code, prov, content_id))

        if atth:
            try:
                query = parse_qs(urlsplit(href).query, keep_blank_values=True)
            except ValueError:
                query = {}
            sub = (query.get("utm_content") or [""])[0]
            if not sub:
                fails.append("ปุ่ม %s ไม่มี utm_content (sub_id)" % code)
            else:
                parts = sub.split("_")
                if sub != sub.lower():
                    fails.append("sub_id ไม่ lowercase: " + sub)
                expected_providers = set(products) if products is not None else CANON
                if len(parts) < 3 or parts[-1] not in expected_providers:
                    fails.append(
                        "sub_id format ผิด (channel_page_provider, provider in registry): " + sub)
                elif prov and parts[-1] != prov:
                    fails.append("sub_id provider ไม่ตรง data-provider: %s != %s"
                                 % (parts[-1], prov))
    return btn, fails

def pages_local(src):
    out = {}
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".html"):
            continue
        content = open(os.path.join(src, fn), encoding="utf-8", errors="replace").read()
        if content.startswith("google-site-verification:"):
            continue  # GSC ownership token, not a content page (sitemap/--live exclude it too)
        if 'content="noindex"' in content or '<!--smoke-skip-->' in content:
            continue  # utility/visual page (e.g. infographic), not a content article
        out[fn] = content
    return out

def pages_live(open_fn=None):
    try:
        sm = _read_live_resource(
            BASE + "/sitemap.xml",
            user_agent="ngernduangold-smoke",
            max_bytes=MAX_SITEMAP_BYTES,
            open_fn=open_fn,
        ).decode("utf-8", "strict")
    except Exception as exc:
        return {"SITEMAP": "__FETCH_FAIL__ %s" % type(exc).__name__}
    out = {}
    locations = [unescape(value).strip() for value in re.findall(r"<loc>([^<]+)</loc>", sm)]
    if not locations:
        return {"SITEMAP": "__FETCH_FAIL__ sitemap has no page locations"}
    if len(locations) > MAX_SITEMAP_URLS:
        return {"SITEMAP": "__FETCH_FAIL__ sitemap page limit exceeded"}
    seen = set()
    for index, u in enumerate(locations, 1):
        if not _exact_base_url(u):
            out["SITEMAP-LOC-%d" % index] = "__FETCH_FAIL__ off-origin or unsafe sitemap location"
            continue
        if u in seen:
            out["SITEMAP-LOC-%d" % index] = "__FETCH_FAIL__ duplicate sitemap location"
            continue
        seen.add(u)
        try:
            out[u] = _read_live_resource(
                u,
                user_agent="ngernduangold-smoke",
                max_bytes=MAX_PAGE_BYTES,
                open_fn=open_fn,
            ).decode("utf-8", "strict")
        except Exception as e:
            out[u] = "__FETCH_FAIL__ %s" % type(e).__name__
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--compare-src", metavar="DIR",
                    help="with --live, fail when production differs from this audited local build")
    ap.add_argument("--report", nargs="?", const=os.path.join(REPO, "automation-log", "smoke-latest.md"))
    ap.add_argument("--telegram-on-fail", action="store_true")
    a = ap.parse_args()

    if a.compare_src and not a.live:
        print("--compare-src requires --live"); sys.exit(2)
    if a.live:
        pages, mode = pages_live(), "LIVE"
    elif a.src:
        pages, mode = pages_local(a.src), "BUILD(%s)" % a.src
    else:
        print("usage: --src DIR | --live"); sys.exit(2)

    try:
        products = load_merchant_products()
    except Exception as exc:
        print("merchant registry unavailable: %s" % exc)
        sys.exit(2)

    drift = {}
    if a.live and a.compare_src:
        drift = compare_release_pages(pages, pages_local(a.compare_src))
        local_fails = local_build_freshness(a.compare_src)
        if local_fails:
            drift.setdefault("LOCAL-BUILD", []).extend(local_fails)
        manifest_payload, manifest_error = fetch_release_manifest_evidence()
        manifest_fails = ([manifest_error] if manifest_error else
                          compare_release_manifest(manifest_payload, a.compare_src))
        if manifest_fails:
            drift.setdefault("RELEASE-MANIFEST", []).extend(manifest_fails)
        mode += "+RELEASE(%s)" % a.compare_src

    total_btn, passed, results = 0, 0, []
    for name, html in pages.items():
        if a.live:
            expected_url = name
        else:
            expected_url = (BASE + "/" if name == "index.html"
                            else BASE + "/" + name[:-5])
        btn, fails = check_page(html, products=products, expected_url=expected_url)
        fails.extend(drift.pop(name, []))
        total_btn += btn
        if not fails:
            passed += 1
        results.append((name, btn, fails))
    for name, fails in sorted(drift.items()):
        results.append((name, 0, fails))

    n = len(results)
    ok = (passed == n)
    head = "%s/%d หน้าผ่าน · ปุ่ม atth.me รวม %d ตัว · %s" % (
        passed, n, total_btn, "✅ PASS" if ok else "❌ FAIL")
    print("🧪 smoke check [%s] — %s" % (mode, head))
    for name, btn, fails in results:
        if fails:
            print("  ❌ %s (%d ปุ่ม): %s" % (name, btn, " | ".join(fails)))

    if a.report:
        ts = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
        lines = ["# 🧪 smoke check ล่าสุด", "", "_%s · %s · %s_" % (ts, mode, head), ""]
        for name, btn, fails in results:
            lines.append("- %s **%s** (%d ปุ่ม)%s" % (
                "✅" if not fails else "❌", name, btn,
                "" if not fails else " — " + "; ".join(fails)))
        os.makedirs(os.path.dirname(a.report), exist_ok=True)
        open(a.report, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("report ->", a.report)

    if not ok and a.telegram_on_fail:
        try:
            sys.path.insert(0, os.path.join(REPO, "automation-log"))
            import telegram_notify
            bad = [n for n, _, f in results if f]
            telegram_notify.notify("🧪 SMOKE FAIL [%s] %s\nหน้าที่พัง: %s" % (mode, head, ", ".join(bad)[:300]))
        except Exception as e:
            sys.stderr.write("telegram skip: %s\n" % e)

    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
