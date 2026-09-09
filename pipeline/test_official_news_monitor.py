#!/usr/bin/env python3
"""Regression checks for the durable official-source change detector."""
import os
import hashlib
import json
import tempfile
from unittest import mock
from urllib.parse import urlparse

import official_news_monitor as monitor


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def blocked(label, call):
    try:
        call()
    except monitor.ActionBlocked:
        print("PASS", label)
        return
    raise AssertionError(label)


def rejected(label, call):
    try:
        call()
    except ValueError:
        print("PASS", label)
        return
    raise AssertionError(label)


def fetched_body(source, body, content_type="", final_url=None, attest=True):
    method, digest = monitor.fingerprint_body(source, body)
    raw_digest = hashlib.sha256(body).hexdigest()
    fetched = {
        "http_status": 200,
        "final_url": final_url if final_url is not None else source["url"],
        "content_type": content_type,
        "etag": "",
        "last_modified": "",
        "bytes": len(body),
        "raw_sha256": raw_digest,
        "sha256": digest,
        "fingerprint_method": method,
    }
    if attest:
        fetched.update(monitor.build_rss_content_type_fallback_evidence(body))
    return fetched


def fake_fetch(source, _timeout):
    if source["kind"] == "html":
        body = (
            "<html><main>Official reviewable fixture content for "
            + source["id"]
            + "</main></html>"
        ).encode("utf-8")
    else:
        body = ("official fixture bytes for " + source["id"]).encode("utf-8")
    method, digest = monitor.fingerprint_body(source, body)
    raw_digest = hashlib.sha256(body).hexdigest()
    content_type = {
        "html": "text/html",
        "pdf": "application/pdf",
        "json": "application/json",
        "rss": "application/rss+xml",
    }[source["kind"]]
    return {
        "http_status": 200,
        "final_url": source["url"],
        "content_type": content_type,
        "etag": "",
        "last_modified": "",
        "bytes": len(body),
        "raw_sha256": raw_digest,
        "sha256": digest,
        "fingerprint_method": method,
    }


def main():
    with tempfile.TemporaryDirectory() as raw:
        strict_path = os.path.join(raw, "strict.json")
        for label, document in (
            ("duplicate official-source JSON is rejected", '{"schema":999,"schema":3}'),
            ("overflow official-source JSON is rejected", '{"schema":3,"probe":1e999}'),
        ):
            with open(strict_path, "w", encoding="utf-8") as handle:
                handle.write(document)
            try:
                monitor._strict_json_file(strict_path)
            except ValueError:
                print("PASS", label)
            else:
                raise AssertionError(label)
    ids = [source["id"] for source in monitor.SOURCES]
    check("source ids are unique", len(ids) == len(set(ids)))
    check("source id aliases point to current sources",
          set(monitor.SOURCE_ID_ALIASES.values()).issubset(ids))
    check("all sources use HTTPS", all(source["url"].startswith("https://") for source in monitor.SOURCES))
    official_hosts = {
        "status.search.google.com",
        "developers.google.com",
        "www.bot.or.th",
        "app.bot.or.th",
        "market.sec.or.th",
        "www.sec.or.th",
        "gppc.pdpc.or.th",
    }
    check("all sources use an approved first-party official host",
          all(urlparse(source["url"]).hostname in official_hosts
              for source in monitor.SOURCES))
    required = {
        "bot-auto-loan-restructuring",
        "bot-before-loan",
        "bot-happy-debtor",
        "bot-hire-purchase-leasing",
        "bot-ltv-2026-extension",
        "bot-secured-loan",
        "bot-youth-transfer-controls",
        "bot-your-data-criteria",
        "bot-responsible-lending",
    }
    check("time-sensitive content sources are monitored", required.issubset(ids))
    explicit_limits = [source["max_bytes"] for source in monitor.SOURCES
                       if "max_bytes" in source]
    check("large official files use bounded per-source byte limits",
          explicit_limits and
          all(monitor.MAX_BYTES < limit <= 20 * 1024 * 1024
              for limit in explicit_limits))
    visible_claim = b"Official claim with enough stable reviewable page text"
    dynamic_a = (b'<input type="hidden" value="token-a">'
                 b'<main>' + visible_claim + b'</main><script nonce="a">x</script>')
    dynamic_b = (b'<input type="hidden" value="token-b">'
                 b'<main>' + visible_claim + b'</main><script nonce="b">y</script>')
    visible_source = {"fingerprint": "visible-text-v1"}
    check("visible-text fingerprint ignores volatile HTML tokens",
          monitor.fingerprint_body(visible_source, dynamic_a)[1] ==
          monitor.fingerprint_body(visible_source, dynamic_b)[1])
    check("visible-text fingerprint detects claim changes",
          monitor.fingerprint_body(visible_source, dynamic_a)[1] !=
          monitor.fingerprint_body(
              visible_source,
              dynamic_b.replace(visible_claim, b"Changed claim with enough stable reviewable page text"),
          )[1])
    script_only_a = b"<html><script>claim A</script></html>"
    script_only_b = b"<html><script>claim B</script></html>"
    script_a = monitor.fingerprint_body(visible_source, script_only_a)
    script_b = monitor.fingerprint_body(visible_source, script_only_b)
    check("empty visible-text extraction falls back to raw evidence",
          script_a[0] == "raw-v1" and script_b[0] == "raw-v1" and
          script_a[1] != script_b[1])
    check("HTML defaults to visible-text fingerprint",
          monitor.fingerprint_body({"kind": "html"}, dynamic_a)[0] ==
          "visible-text-v1")
    boilerplate = b"Loading your official content, please wait..."
    embedded_a = b"<html><main>" + boilerplate + b"</main><script>claim A</script></html>"
    embedded_b = b"<html><main>" + boilerplate + b"</main><script>claim B</script></html>"
    embedded_visible_a = monitor.fingerprint_body(visible_source, embedded_a)
    embedded_visible_b = monitor.fingerprint_body(visible_source, embedded_b)
    check("embedded claim drift is reviewable despite stable boilerplate",
          embedded_visible_a[1] == embedded_visible_b[1] and
          monitor.classify_change(
              {"sha256": embedded_visible_a[1],
               "raw_sha256": hashlib.sha256(embedded_a).hexdigest(),
               "fingerprint_method": embedded_visible_a[0]},
              {"sha256": embedded_visible_b[1],
               "raw_sha256": hashlib.sha256(embedded_b).hexdigest(),
               "fingerprint_method": embedded_visible_b[0]}) == "changed")
    check("raw-to-visible migration preserves unchanged state",
          monitor.classify_change(
              {"sha256": "raw-hash"},
              {"sha256": "text-hash", "raw_sha256": "raw-hash",
               "fingerprint_method": "visible-text-v1"}) == "unchanged")
    check("configured URL identity drift is always reviewable",
          monitor.classify_change(
              {"url": "https://www.bot.or.th/a", "sha256": "same",
               "fingerprint_method": "raw-v1"},
              {"url": "https://www.bot.or.th/b", "sha256": "same",
               "fingerprint_method": "raw-v1"}) == "changed")
    check("final URL query identity drift is always reviewable",
          monitor.classify_change(
              {"final_url": "https://app.bot.or.th/report?packId=one",
               "sha256": "same", "raw_sha256": "same",
               "fingerprint_method": "raw-v1"},
              {"final_url": "https://app.bot.or.th/report?packId=two",
               "sha256": "same", "raw_sha256": "same",
               "fingerprint_method": "raw-v1"}) == "changed")
    redirected = fake_fetch({"id": "redirect", "kind": "html",
                             "url": "https://www.bot.or.th/a"}, 1)
    redirected["final_url"] = "https://evil.example/a"
    try:
        monitor.validate_fetched_metadata(
            {"id": "redirect", "kind": "html",
             "url": "https://www.bot.or.th/a"}, redirected)
    except ValueError:
        print("PASS cross-host final redirects fail closed")
    else:
        raise AssertionError("cross-host final redirects fail closed")
    rss_source = {
        "id": "rss-fixture", "kind": "rss",
        "url": "https://developers.google.com/search/updates/feed.rss",
    }
    rss_body = b"<?xml version='1.0'?><rss version='2.0'><channel /></rss>"
    rss_fetched = fetched_body(rss_source, rss_body)
    monitor.validate_fetched_metadata(rss_source, rss_fetched, body=rss_body)
    check("missing RSS Content-Type accepts hash-bound parsed rss root",
          rss_fetched["rss_xml_root"] == "rss" and
          rss_fetched["rss_xml_raw_sha256"] == rss_fetched["raw_sha256"])
    rss_none_fetched = fetched_body(
        rss_source, rss_body, content_type="None")
    monitor.validate_fetched_metadata(
        rss_source, rss_none_fetched, body=rss_body)
    check("literal None RSS Content-Type accepts the same hash-bound proof",
          rss_none_fetched["rss_xml_root"] == "rss" and
          rss_none_fetched["rss_xml_raw_sha256"] ==
          rss_none_fetched["raw_sha256"])
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = rss_body
    response.getcode.return_value = 200
    response.geturl.return_value = rss_source["url"]
    response.headers = {}
    with mock.patch.object(monitor.urllib.request, "urlopen", return_value=response):
        fetched_without_header = monitor.fetch(rss_source, 1)
    check("fetch records parsed RSS proof without making a real network call",
          fetched_without_header["content_type"] == "" and
          fetched_without_header["rss_xml_root"] == "rss" and
          fetched_without_header["rss_xml_raw_sha256"] ==
          fetched_without_header["raw_sha256"])
    response.headers = {"Content-Type": "None"}
    with mock.patch.object(monitor.urllib.request, "urlopen", return_value=response):
        fetched_none_header = monitor.fetch(rss_source, 1)
    check("producer records hash-bound proof for literal None media type",
          fetched_none_header["content_type"] == "None" and
          fetched_none_header["rss_xml_root"] == "rss" and
          fetched_none_header["rss_xml_raw_sha256"] ==
          fetched_none_header["raw_sha256"])
    atom_body = (
        b"<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>"
        b"<title>fixture</title></feed>"
    )
    atom_fetched = fetched_body(rss_source, atom_body)
    monitor.validate_fetched_metadata(rss_source, atom_fetched, body=atom_body)
    check("missing RSS Content-Type accepts namespaced Atom feed root",
          atom_fetched["rss_xml_root"] == "feed")
    rejected("malformed XML cannot create RSS fallback evidence", lambda:
             monitor.build_rss_content_type_fallback_evidence(b"<rss><channel>"))
    rejected("well-formed non-feed XML cannot create RSS fallback evidence", lambda:
             monitor.build_rss_content_type_fallback_evidence(b"<html><body /></html>"))
    rejected("DTD or entity declarations fail closed", lambda:
             monitor.build_rss_content_type_fallback_evidence(
                 b"<!DOCTYPE rss [<!ENTITY x 'y'>]><rss>&x;</rss>"))
    wrong_type = fetched_body(rss_source, rss_body, content_type="text/html")
    rejected("explicit wrong media type cannot use the RSS fallback", lambda:
             monitor.validate_fetched_metadata(rss_source, wrong_type, body=rss_body))
    for invalid_placeholder in (
            "none", "null", "unknown", "application/octet-stream"):
        invalid_type = fetched_body(
            rss_source, rss_body, content_type=invalid_placeholder)
        rejected(
            "non-exact RSS media-type placeholder fails closed: " +
            invalid_placeholder,
            lambda invalid_type=invalid_type: monitor.validate_fetched_metadata(
                rss_source, invalid_type, body=rss_body),
        )
    same_host_redirect = fetched_body(
        rss_source, rss_body,
        final_url="https://developers.google.com/search/updates/spoof.rss")
    rejected("same-host different-path RSS fallback fails exact URL binding", lambda:
             monitor.validate_fetched_metadata(
                 rss_source, same_host_redirect, body=rss_body))
    altered_body = rss_body.replace(b"channel", b"changed", 1)
    rejected("RSS fallback proof cannot be replayed for altered body bytes", lambda:
             monitor.validate_fetched_metadata(
                 rss_source, rss_fetched, body=altered_body))
    html_source = {
        "id": "html-fixture", "kind": "html",
        "url": "https://developers.google.com/search/updates/page",
    }
    html_without_type = fetched_body(html_source, rss_body, attest=False)
    rejected("missing Content-Type never falls back for non-RSS kinds", lambda:
             monitor.validate_fetched_metadata(
                 html_source, html_without_type, body=rss_body))
    for kind, body in (
            ("html", b"<html><body>official</body></html>"),
            ("json", b"{}"),
            ("pdf", b"%PDF-1.7 fixture")):
        non_rss_source = {
            "id": kind + "-fixture", "kind": kind,
            "url": "https://developers.google.com/fixture." + kind,
        }
        non_rss_none = fetched_body(
            non_rss_source, body, content_type="None", attest=False)
        rejected(
            "literal None fallback never applies to " + kind,
            lambda source=non_rss_source, fetched=non_rss_none, body=body:
                monitor.validate_fetched_metadata(source, fetched, body=body),
        )
    response.read.return_value = b"<html><body /></html>"
    response.headers = {"Content-Type": "None"}
    with mock.patch.object(monitor.urllib.request, "urlopen", return_value=response):
        rejected(
            "literal None media type cannot admit a non-feed RSS body",
            lambda: monitor.fetch(rss_source, 1),
        )
    registry_path = os.path.join(
        monitor.ROOT, "automation-log", "knowledge-base", "content-source-registry.json")
    with open(registry_path, encoding="utf-8") as handle:
        registry = json.load(handle)
    registries = [registry]
    for name in ("page2-source-registry.json", "social-source-registry.json"):
        with open(os.path.join(
            monitor.ROOT, "automation-log", "knowledge-base", name
        ), encoding="utf-8") as handle:
            registries.append(json.load(handle))
    referenced = {
        url for registry_payload in registries
        for item in registry_payload["items"].values()
        for url in item["official_urls"]
    }
    monitored = {source["url"] for source in monitor.SOURCES}
    check("every knowledge-post official URL is monitored", referenced.issubset(monitored))
    unbound = {
        source["id"] for source in monitor.SOURCES
        if source["url"] not in referenced
    }
    check("every non-content watch source is explicitly global-monitor-only",
          unbound == set(monitor.GLOBAL_MONITOR_SOURCE_IDS) and
          all(source.get("scope") == monitor.GLOBAL_MONITOR_SCOPE
              for source in monitor.SOURCES
              if source["id"] in monitor.GLOBAL_MONITOR_SOURCE_IDS))
    impacts = monitor.load_review_impacts(registry_path)
    criteria_url = next(
        source["url"] for source in monitor.SOURCES
        if source["id"] == "bot-your-data-criteria"
    )
    check("Your Data criteria source is mapped to the affected knowledge claim",
          any(item["content_id"] == "kn-39" for item in impacts.get(criteria_url, [])))
    all_impacts = monitor.load_review_impacts()
    social_url = next(
        source["url"] for source in monitor.SOURCES
        if source["id"] == "bot-hire-purchase-leasing"
    )
    check("owner impact mapping covers the social and Page2 registries",
          any(item["content_id"] == "b3-01"
              for item in all_impacts.get(social_url, [])))

    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot = os.path.join(temp_dir, "snapshot.json")
        alert = os.path.join(temp_dir, "review.md")
        role_path = os.path.join(temp_dir, "roles.json")
        with open(role_path, "w", encoding="utf-8") as handle:
            json.dump({
                "default": "deny",
                "actors": {
                    "owner": {"source_acknowledge": True},
                    "codex": {"source_acknowledge": False},
                },
            }, handle)
        with mock.patch.object(monitor, "fetch", side_effect=fake_fetch):
            first = monitor.run(snapshot, 1)
            monitor.write_review_alert(alert, first)
            check("new sources become durable review items",
                  set(first["review_required"]) == set(ids) and os.path.exists(alert))
            check("snapshot exposes complete current-run freshness counts",
                  first["schema"] == 3 and
                  first["summary"]["network_probe"] == "COMPLETE" and
                  first["summary"]["successful_sources"] == len(ids) and
                  first["summary"]["current_errors"] == 0 and
                  first["summary"]["pending_owner_reviews"] == len(ids))
            check("first attestation bootstraps every source fail closed",
                  first["queue_integrity"]["state"] == "BOOTSTRAPPED_FAIL_CLOSED" and
                  first["queue_attestation"]["history"][-1]["pending_ids"] == sorted(ids) and
                  not monitor.validate_queue_attestation(first)[1])
            check("review queue records trigger without acknowledging it",
                  len(first["review_queue"]) == len(ids) and
                  all(item["trigger"] == "new" for item in first["review_queue"]) and
                  all(item["acknowledgement_status"] == "PENDING_OWNER_REVIEW"
                      for item in first["review_queue"]))
            with open(alert, encoding="utf-8") as handle:
                packet = handle.read()
            check("owner packet contains verdict, impact, evidence, and no-authority language",
                  "Owner verdict" in packet and "Impact:" in packet and
                  "Evidence/date" in packet and "ไม่ให้อำนาจ" in packet and
                  "acknowledged_this_run: `0`" in packet)
            check("owner packet distinguishes global monitoring from content impact",
                  "GLOBAL_MONITOR_ONLY" in packet and "UNMAPPED" not in packet)
            check("strict mode blocks pending source review",
                  monitor.strict_exit_code(first) == 1)

            second = monitor.run(snapshot, 1)
            monitor.write_review_alert(alert, second)
            check("unchanged run does not erase pending review",
                  set(second["review_required"]) == set(ids) and os.path.exists(alert))
            first_queue = {item["source_id"]: item for item in first["review_queue"]}
            second_queue = {item["source_id"]: item for item in second["review_queue"]}
            check("unchanged refresh preserves each pending trigger and pending_since",
                  all(second_queue[source_id]["trigger"] == "new" and
                      second_queue[source_id]["pending_since"] ==
                      first_queue[source_id]["pending_since"]
                      for source_id in ids))
            check("valid queue attestation advances without self-acknowledgement",
                  second["queue_integrity"]["state"] == "VALID" and
                  len(second["queue_attestation"]["history"]) == 2 and
                  not monitor.validate_queue_attestation(second)[1])

            # Removing a durable review item directly from the co-located JSON is
            # not owner proof.  The next run must distrust the artifact and
            # bootstrap every configured source back into the queue.
            edited = json.loads(json.dumps(second))
            removed_id = ids[0]
            edited["review_required"].remove(removed_id)
            edited["review_queue"] = [
                item for item in edited["review_queue"]
                if item["source_id"] != removed_id
            ]
            edited["summary"]["pending_owner_reviews"] -= 1
            with open(snapshot, "w", encoding="utf-8") as handle:
                json.dump(edited, handle)
            restored = monitor.run(snapshot, 1)
            check("direct queue deletion fails closed without owner proof",
                  removed_id in restored["review_required"] and
                  restored["queue_integrity"]["state"] == "BOOTSTRAPPED_FAIL_CLOSED" and
                  restored["acknowledgement_log"] == [])
            try:
                monitor.build_queue_attestation(
                    restored["queue_attestation"],
                    configured_source_ids=ids,
                    pending_ids=[],
                    acknowledged_ids=ids,
                    checked_at=restored["checked_at"],
                    sources=restored["sources"],
                )
            except ValueError:
                print("PASS local hash chain cannot manufacture owner acknowledgement")
            else:
                raise AssertionError(
                    "local hash chain cannot manufacture owner acknowledgement"
                )

            blocked("acknowledgement requires an owner-controlled process", lambda: monitor.run(
                snapshot, 1, acknowledged=[ids[0]], role_path=role_path
            ))
            blocked("Codex cannot acknowledge source review", lambda: monitor.run(
                snapshot, 1, acknowledged=[ids[0]], acknowledged_by="codex",
                role_path=role_path
            ))
            blocked("owner CLI string is not identity proof", lambda: monitor.run(
                snapshot, 1, acknowledged=ids, acknowledged_by="owner",
                role_path=role_path
            ))
            third = monitor.run(snapshot, 1)
            monitor.write_review_alert(alert, third)
            check("pending review cannot be cleared by a CLI actor string",
                  set(third["review_required"]) == set(ids) and os.path.exists(alert))
            check("strict mode rejects a schema-less synthetic clean payload",
                  monitor.strict_exit_code({"errors": [], "review_required": []}) == 3)

        def one_error(source, timeout):
            if source["id"] == ids[0]:
                raise TimeoutError("test timeout")
            return fake_fetch(source, timeout)

        with mock.patch.object(monitor, "fetch", side_effect=one_error):
            failed = monitor.run(snapshot, 1)
            monitor.write_review_alert(alert, failed)
            check("fetch errors fail closed into review queue",
                  ids[0] in failed["errors"] and ids[0] in failed["review_required"])
            check("current error summary is explicit and fail-closed",
                  failed["summary"]["network_probe"] == "PARTIAL" and
                  failed["summary"]["current_errors"] == 1 and
                  failed["summary"]["freshness_state"] == "ERROR" and
                  any(item.get("current_error") for item in failed["review_queue"]
                      if item["source_id"] == ids[0]))
            check("strict mode distinguishes source errors",
                  monitor.strict_exit_code(failed) == 2)

        approved_output_root = monitor.ROOT_PATH / "automation-log" / "knowledge-base"
        approved_alert_root = monitor.ROOT_PATH / "automation-log" / "cowork-inbox"
        check("default monitor paths are confined",
              monitor.confined_cli_path(monitor.DEFAULT_OUT, approved_output_root, ".json") and
              monitor.confined_cli_path(monitor.DEFAULT_ALERT, approved_alert_root, ".md"))
        blocked("snapshot path cannot escape approved root", lambda:
                monitor.confined_cli_path(snapshot, approved_output_root, ".json"))
        blocked("alert path cannot escape approved root", lambda:
                monitor.confined_cli_path(alert, approved_alert_root, ".md"))

    print("official news monitor: all checks passed")


if __name__ == "__main__":
    main()
