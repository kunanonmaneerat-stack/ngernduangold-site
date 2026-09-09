#!/usr/bin/env python3
"""Regression checks for the post-id to official-source freshness contract."""
import datetime
import hashlib
import json
import pathlib
import tempfile

import content_source_gate as gate
import validate_knowledge_posts as validator


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def source_row(source_id, url, checked_at):
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    return {
        "id": source_id,
        "url": url,
        "kind": "html",
        "http_status": 200,
        "final_url": url,
        "content_type": "text/html",
        "etag": "",
        "last_modified": "",
        "bytes": 10,
        "raw_sha256": digest,
        "sha256": digest,
        "fingerprint_method": "visible-text-v1",
        "checked_at": checked_at,
        "change": "unchanged",
    }


def strict_snapshot(rows):
    checked_at = rows[0]["checked_at"]
    pending = sorted(row["id"] for row in rows)
    payload = {
        "schema": 3,
        "checked_at": checked_at,
        "purpose": "change detection only; review official source before publishing",
        "summary": {
            "configured_sources": len(rows),
            "checked_sources": len(rows),
            "successful_sources": len(rows),
            "changed_this_run": 0,
            "current_errors": 0,
            "pending_owner_reviews": len(pending),
            "acknowledged_this_run": 0,
            "network_probe": "COMPLETE",
            "freshness_state": "FRESH_REVIEW_REQUIRED",
        },
        "changed": [],
        "errors": [],
        "review_required": pending,
        "review_queue": [{
            "source_id": source_id,
            "trigger": "queue_integrity_fail_closed",
            "pending_since": checked_at,
            "last_checked_at": checked_at,
            "current_state": "unchanged",
            "acknowledgement_status": "PENDING_OWNER_REVIEW",
        } for source_id in pending],
        "acknowledged_this_run": [],
        "acknowledgement_log": [],
        "sources": rows,
    }
    payload["queue_attestation"] = gate.build_queue_attestation(
        None,
        configured_source_ids=pending,
        pending_ids=pending,
        acknowledged_ids=[],
        checked_at=checked_at,
        sources=rows,
        bootstrap=True,
    )
    return payload


def main():
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        library = root / "KNOWLEDGE-POSTS-X.md"
        library.write_text("fixture", encoding="utf-8")
        rows = [{"id": "kn-1"}]
        url = "https://example.test/official"
        decision_time = datetime.datetime.now(datetime.timezone.utc)
        registry = {
            "schema_version": 1,
            "library": library.name,
            "binding_state": "HUMAN_REVIEWED",
            "last_human_review": decision_time.date().isoformat(),
            "freshness_hours": 24,
            "items": {"kn-1": {
                "claim_scope": "fixture",
                "source_ids": ["source-a"],
                "official_urls": [url],
            }},
        }
        registry["reviewed_binding_sha256"] = gate.source_registry_binding_sha256(
            registry
        )
        checked_at = decision_time.isoformat()
        snapshot = strict_snapshot([source_row("source-a", url, checked_at)])
        write_json(root / "knowledge-base" / validator.REGISTRY_FILE, registry)
        write_json(root / "knowledge-base" / validator.SNAPSHOT_FILE, snapshot)
        issues = validator.validate_source_contract(library, rows, "kn-1")
        check("fresh reviewed local metadata cannot replace owner authority",
              any("checksum is not authority" in issue for issue in issues))
        check("bootstrap review queue fails closed",
              any("review is pending" in issue for issue in issues))
        check("otherwise-current strict evidence has no structural failure",
              not any(marker in issue for issue in issues for marker in (
                  "malformed", "not monitored", "stale", "different library",
                  "does not match",
              )))

        other_url = "https://example.test/other"
        unmonitored = strict_snapshot([
            source_row("source-b", other_url, checked_at)
        ])
        write_json(root / "knowledge-base" / validator.SNAPSHOT_FILE, unmonitored)
        check("unmonitored mapped URL fails closed", any("not monitored" in issue for issue in
              validator.validate_source_contract(library, rows, "kn-1")))

        stale_at = (datetime.datetime.now(datetime.timezone.utc)
                    - datetime.timedelta(days=2)).isoformat()
        stale = strict_snapshot([source_row("source-a", url, stale_at)])
        write_json(root / "knowledge-base" / validator.SNAPSHOT_FILE, stale)
        check("stale source snapshot fails closed", any("stale" in issue for issue in
              validator.validate_source_contract(library, rows, "kn-1")))
        check("missing content id fails closed", any("content_id missing" in issue for issue in
              validator.validate_source_contract(library, rows)))
    print("knowledge source contract: all checks passed")


if __name__ == "__main__":
    main()
