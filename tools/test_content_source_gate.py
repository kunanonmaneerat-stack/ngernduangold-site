#!/usr/bin/env python3
"""Adversarial regression tests for strict content-scoped source evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import content_source_gate as gate
import source_review_receipt


COUNT = 0


def check(label, condition):
    global COUNT
    if not condition:
        raise AssertionError(label)
    COUNT += 1
    print("PASS", label)


def source_row(source_id, url, checked_at, change="unchanged"):
    digest = hashlib.sha256(source_id.encode()).hexdigest()
    return {
        "id": source_id, "url": url, "kind": "html", "http_status": 200,
        "final_url": url, "content_type": "text/html", "etag": "",
        "last_modified": "", "bytes": 10, "raw_sha256": digest,
        "sha256": digest, "fingerprint_method": "visible-text-v1",
        "checked_at": checked_at, "change": change,
    }


def rss_source_row(source_id, url, checked_at, body, content_type=""):
    digest = hashlib.sha256(body).hexdigest()
    row = {
        "id": source_id, "url": url, "kind": "rss", "http_status": 200,
        "final_url": url, "content_type": content_type, "etag": "",
        "last_modified": "", "bytes": len(body), "raw_sha256": digest,
        "sha256": digest, "fingerprint_method": "raw-v1",
        "checked_at": checked_at, "change": "unchanged",
    }
    row.update(gate.build_rss_content_type_fallback_evidence(body))
    return row


def snapshot(rows):
    checked_at = rows[0]["checked_at"]
    pending = sorted(row["id"] for row in rows)
    payload = {
        "schema": 3, "checked_at": checked_at,
        "purpose": "change detection only; review official source before publishing",
        "summary": {
            "configured_sources": len(rows), "checked_sources": len(rows),
            "successful_sources": len(rows), "changed_this_run": 0,
            "current_errors": 0, "pending_owner_reviews": len(pending),
            "acknowledged_this_run": 0, "network_probe": "COMPLETE",
            "freshness_state": "FRESH_REVIEW_REQUIRED",
        },
        "changed": [], "errors": [], "review_required": pending,
        "review_queue": [{
            "source_id": item, "trigger": "queue_integrity_fail_closed",
            "pending_since": checked_at, "last_checked_at": checked_at,
            "current_state": "unchanged",
            "acknowledgement_status": "PENDING_OWNER_REVIEW",
        } for item in pending],
        "acknowledged_this_run": [], "acknowledgement_log": [], "sources": rows,
    }
    payload["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=pending, pending_ids=pending,
        acknowledged_ids=[], checked_at=checked_at, sources=rows, bootstrap=True,
    )
    return payload


def registry(url):
    payload = {
        "schema_version": 1, "library": "KNOWLEDGE-POSTS-X.md",
        "binding_state": "HUMAN_REVIEWED", "last_human_review": "2026-08-23",
        "freshness_hours": 24,
        "items": {"kn-1": {"claim_scope": "fixture", "source_ids": ["source-a"],
                             "official_urls": [url]}},
    }
    payload["reviewed_binding_sha256"] = gate.source_registry_binding_sha256(payload)
    return payload


def write_test_source_review_receipt(root, content_id, registry_document,
                                     snapshot_document, private_key, now):
    """Create ephemeral signed evidence only inside a test temp directory."""
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    source_ids = sorted(
        registry_document["items"][content_id]["source_ids"]
    )
    registry_hash = gate.source_registry_binding_sha256(registry_document)
    source_hash = source_review_receipt.source_state_sha256(
        snapshot_document["sources"], source_ids
    )
    unsigned = {
        "schema_version": 1,
        "receipt_kind": "OWNER_CONTENT_SOURCE_REVIEW",
        "content_id": content_id,
        "verdict": "UNCHANGED",
        "reviewed_at": (now - timedelta(minutes=1)).isoformat(),
        "registry_binding_sha256": registry_hash,
        "source_ids": source_ids,
        "source_state_sha256": source_hash,
        "nonce": "T" * 32,
        "owner_key_sha256": hashlib.sha256(public_raw).hexdigest(),
        "signature_algorithm": "ed25519",
    }
    signed = dict(unsigned)
    signed["signature_b64"] = base64.b64encode(
        private_key.sign(source_review_receipt.canonical_signed_payload(unsigned))
    ).decode("ascii")
    path = source_review_receipt.expected_receipt_path(
        root, content_id, registry_hash, source_hash
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(signed, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return base64.b64encode(public_raw).decode("ascii")


def main():
    now = datetime.now(timezone.utc)
    checked_at = now.isoformat(timespec="seconds")
    url_a, url_b = "https://official.example/a", "https://other.example/b"
    clean = snapshot([source_row("source-a", url_a, checked_at),
                      source_row("source-b", url_b, checked_at)])

    check("valid schema-3 bootstrap envelope passes integrity",
          gate.validate_official_snapshot_contract(clean, now=now).allowed)
    scoped = gate.validate_official_snapshot_contract(
        clean, required_source_ids=["source-a"],
        expected_urls={"source-a": url_a}, now=now)
    check("exact relevant pending source blocks", not scoped.allowed and
          any("pending" in issue for issue in scoped.failures))

    bad_unrelated = deepcopy(clean)
    bad_unrelated["sources"][1]["change"] = "skipped"
    bad_unrelated["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-a", "source-b"],
        pending_ids=["source-a", "source-b"], acknowledged_ids=[],
        checked_at=checked_at, sources=bad_unrelated["sources"], bootstrap=True)
    scoped_bad = gate.validate_official_snapshot_contract(
        bad_unrelated, required_source_ids=["source-a"], now=now)
    check("unrelated malformed row does not become a scoped row blocker",
          not any("source-b" in issue and "change" in issue
                  for issue in scoped_bad.failures))
    check("global validator rejects unrelated malformed row",
          any("source-b" in issue for issue in
              gate.validate_official_snapshot_contract(
                  bad_unrelated, now=now, strict_all_rows=True).failures))

    downgraded = deepcopy(clean)
    downgraded["schema"] = 2
    check("schema downgrade fails closed",
          not gate.validate_official_snapshot_contract(downgraded, now=now).allowed)

    stale_row = deepcopy(clean)
    stale_row["sources"][0]["checked_at"] = "2020-01-01T00:00:00+00:00"
    stale_row["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-a", "source-b"],
        pending_ids=["source-a", "source-b"], acknowledged_ids=[],
        checked_at=checked_at, sources=stale_row["sources"], bootstrap=True)
    check("relevant row cannot borrow top-level freshness",
          any("checked_at" in issue for issue in
              gate.validate_official_snapshot_contract(
                  stale_row, required_source_ids=["source-a"], now=now).failures))

    redirect = deepcopy(clean)
    redirect["sources"][0]["final_url"] = "https://evil.example/a"
    redirect["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-a", "source-b"],
        pending_ids=["source-a", "source-b"], acknowledged_ids=[],
        checked_at=checked_at, sources=redirect["sources"], bootstrap=True)
    check("cross-host final URL fails provenance",
          any("final URL" in issue for issue in
              gate.validate_official_snapshot_contract(
                  redirect, required_source_ids=["source-a"], now=now).failures))

    rss_url = "https://official.example/feed.rss"
    rss_body = b"<?xml version='1.0'?><rss><channel /></rss>"
    rss_snapshot = snapshot([
        rss_source_row("source-rss", rss_url, checked_at, rss_body)
    ])
    rss_result = gate.validate_official_snapshot_contract(
        rss_snapshot, now=now, strict_all_rows=True)
    check("persisted RSS XML proof permits an absent Content-Type",
          not any("content type" in issue for issue in rss_result.failures))
    rss_none_snapshot = snapshot([
        rss_source_row(
            "source-rss", rss_url, checked_at, rss_body,
            content_type="None")
    ])
    rss_none_result = gate.validate_official_snapshot_contract(
        rss_none_snapshot, now=now, strict_all_rows=True)
    check("persisted RSS proof permits the exact None placeholder",
          not any("content type" in issue
                  for issue in rss_none_result.failures))
    rss_lower_none = deepcopy(rss_none_snapshot)
    rss_lower_none["sources"][0]["content_type"] = "none"
    rss_lower_none["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-rss"],
        pending_ids=["source-rss"], acknowledged_ids=[],
        checked_at=checked_at, sources=rss_lower_none["sources"], bootstrap=True)
    check("persisted RSS proof rejects non-exact None placeholders",
          any("content type" in issue for issue in
              gate.validate_official_snapshot_contract(
                  rss_lower_none, now=now, strict_all_rows=True).failures))
    non_rss_none = deepcopy(rss_none_snapshot)
    non_rss_none["sources"][0]["kind"] = "html"
    non_rss_none["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-rss"],
        pending_ids=["source-rss"], acknowledged_ids=[],
        checked_at=checked_at, sources=non_rss_none["sources"], bootstrap=True)
    check("persisted None fallback never applies to non-RSS kinds",
          any("content type" in issue for issue in
              gate.validate_official_snapshot_contract(
                  non_rss_none, now=now, strict_all_rows=True).failures))
    rss_spoof = deepcopy(rss_snapshot)
    rss_spoof["sources"][0]["final_url"] = "https://official.example/spoof.rss"
    rss_spoof["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-rss"], pending_ids=["source-rss"],
        acknowledged_ids=[], checked_at=checked_at,
        sources=rss_spoof["sources"], bootstrap=True)
    check("persisted RSS proof cannot bypass exact URL binding",
          any("content type" in issue for issue in
              gate.validate_official_snapshot_contract(
                  rss_spoof, now=now, strict_all_rows=True).failures))
    rss_hash_spoof = deepcopy(rss_snapshot)
    rss_hash_spoof["sources"][0]["rss_xml_raw_sha256"] = "0" * 64
    rss_hash_spoof["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-rss"], pending_ids=["source-rss"],
        acknowledged_ids=[], checked_at=checked_at,
        sources=rss_hash_spoof["sources"], bootstrap=True)
    check("persisted RSS proof is bound to the fetched raw hash",
          any("content type" in issue for issue in
              gate.validate_official_snapshot_contract(
                  rss_hash_spoof, now=now, strict_all_rows=True).failures))

    mismatch = deepcopy(clean)
    mismatch["sources"][0]["change"] = "changed"
    mismatch["queue_attestation"] = gate.build_queue_attestation(
        None, configured_source_ids=["source-a", "source-b"],
        pending_ids=["source-a", "source-b"], acknowledged_ids=[],
        checked_at=checked_at, sources=mismatch["sources"], bootstrap=True)
    check("row state and changed list are bidirectional",
          any("contradicts changed" in issue for issue in
              gate.validate_official_snapshot_contract(
                  mismatch, required_source_ids=["source-a"], now=now).failures))

    tampered = deepcopy(clean)
    tampered["review_required"].remove("source-a")
    tampered["review_queue"] = [item for item in tampered["review_queue"]
                                if item["source_id"] != "source-a"]
    tampered["summary"]["pending_owner_reviews"] -= 1
    check("direct pending deletion breaks attestation",
          any("attestation" in issue for issue in
              gate.validate_official_snapshot_contract(tampered, now=now).failures))
    try:
        gate.build_queue_attestation(
            clean["queue_attestation"],
            configured_source_ids=["source-a", "source-b"], pending_ids=[],
            acknowledged_ids=["source-a", "source-b"], checked_at=checked_at,
            sources=clean["sources"])
    except ValueError:
        check("local checksum cannot manufacture owner acknowledgement", True)
    else:
        raise AssertionError("local checksum cannot manufacture owner acknowledgement")

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        registry_path, snapshot_path = root / "registry.json", root / "snapshot.json"
        reg = registry(url_a)
        registry_path.write_text(json.dumps(reg), encoding="utf-8")
        snapshot_path.write_text(json.dumps(clean), encoding="utf-8")
        result = gate.evaluate_content_source_gate(
            "kn-1", registry_path, snapshot_path,
            library_name="KNOWLEDGE-POSTS-X.md", now=now)
        check("local registry checksum is not owner authority", not result.allowed and
              any("checksum is not authority" in issue for issue in result.failures))

        invalid_receipt_path = source_review_receipt.expected_receipt_path(
            root,
            "kn-1",
            gate.source_registry_binding_sha256(reg),
            source_review_receipt.source_state_sha256(
                clean["sources"], ["source-a"]
            ),
        )
        invalid_receipt_path.parent.mkdir(parents=True, exist_ok=True)
        invalid_receipt_path.write_text("{}", encoding="utf-8")
        invalid_receipt_result = gate.evaluate_content_source_gate(
            "kn-1", registry_path, snapshot_path,
            library_name="KNOWLEDGE-POSTS-X.md", now=now,
            _review_receipt_repo=root)
        check("malformed local receipt retains old blockers and adds a diagnosis",
              not invalid_receipt_result.allowed and
              any("checksum is not authority" in issue
                  for issue in invalid_receipt_result.failures) and
              any("source-review receipt invalid" in issue
                  for issue in invalid_receipt_result.failures))

        private_key = Ed25519PrivateKey.generate()
        public_key_b64 = write_test_source_review_receipt(
            root, "kn-1", reg, clean, private_key, now
        )
        original_pending = deepcopy(clean["review_required"])
        with mock.patch.dict(
            os.environ,
            {source_review_receipt.PUBLIC_KEY_ENV: public_key_b64},
        ):
            positive = gate.evaluate_content_source_gate(
                "kn-1", registry_path, snapshot_path,
                library_name="KNOWLEDGE-POSTS-X.md", now=now,
                _review_receipt_repo=root)
            check("valid exact owner receipt opens the content-scoped positive path",
                  positive.allowed)
            check("positive path never mutates the official global review queue",
                  clean["review_required"] == original_pending and
                  "source-a" in clean["review_required"])

            stale_checked = (now - timedelta(hours=25)).isoformat(timespec="seconds")
            stale = snapshot([
                source_row("source-a", url_a, stale_checked),
                source_row("source-b", url_b, stale_checked),
            ])
            stale_result = gate.evaluate_content_source_gate(
                "kn-1", registry_path, snapshot_path,
                library_name="KNOWLEDGE-POSTS-X.md", now=now,
                _registry_document=reg, _snapshot_document=stale,
                _review_receipt_repo=root)
            check("signed local review never clears source freshness failures",
                  not stale_result.allowed and
                  any("stale" in issue for issue in stale_result.failures))

            changed = deepcopy(clean)
            changed["changed"] = ["source-a"]
            changed["sources"][0]["change"] = "changed"
            changed["review_queue"][0]["current_state"] = "changed"
            changed["summary"]["changed_this_run"] = 1
            changed["queue_attestation"] = gate.build_queue_attestation(
                None, configured_source_ids=["source-a", "source-b"],
                pending_ids=["source-a", "source-b"], acknowledged_ids=[],
                checked_at=checked_at, sources=changed["sources"], bootstrap=True)
            changed_result = gate.evaluate_content_source_gate(
                "kn-1", registry_path, snapshot_path,
                library_name="KNOWLEDGE-POSTS-X.md", now=now,
                _registry_document=reg, _snapshot_document=changed,
                _review_receipt_repo=root)
            check("signed local review never clears a relevant changed-source state",
                  not changed_result.allowed and any(
                      "relevant official source changed" in issue
                      for issue in changed_result.failures))

            errored = deepcopy(clean)
            errored["errors"] = ["source-a"]
            errored["sources"][0]["change"] = "error"
            errored["sources"][0]["error"] = "test-network-error"
            errored["review_queue"][0]["current_state"] = "error"
            errored["summary"].update({
                "successful_sources": 1,
                "current_errors": 1,
                "network_probe": "PARTIAL",
                "freshness_state": "ERROR",
            })
            errored["queue_attestation"] = gate.build_queue_attestation(
                None, configured_source_ids=["source-a", "source-b"],
                pending_ids=["source-a", "source-b"], acknowledged_ids=[],
                checked_at=checked_at, sources=errored["sources"], bootstrap=True)
            error_result = gate.evaluate_content_source_gate(
                "kn-1", registry_path, snapshot_path,
                library_name="KNOWLEDGE-POSTS-X.md", now=now,
                _registry_document=reg, _snapshot_document=errored,
                _review_receipt_repo=root)
            check("signed local review never clears a relevant source error",
                  not error_result.allowed and any(
                      "relevant official source error" in issue
                      for issue in error_result.failures))

            drifted = deepcopy(clean)
            drifted["sources"][0]["raw_sha256"] = "f" * 64
            drifted["sources"][0]["sha256"] = "f" * 64
            drifted["queue_attestation"] = gate.build_queue_attestation(
                None, configured_source_ids=["source-a", "source-b"],
                pending_ids=["source-a", "source-b"], acknowledged_ids=[],
                checked_at=checked_at, sources=drifted["sources"], bootstrap=True)
            drift_result = gate.evaluate_content_source_gate(
                "kn-1", registry_path, snapshot_path,
                library_name="KNOWLEDGE-POSTS-X.md", now=now,
                _registry_document=reg, _snapshot_document=drifted,
                _review_receipt_repo=root)
            check("source fingerprint drift cannot reuse an older owner receipt",
                  not drift_result.allowed and any(
                      "checksum is not authority" in issue
                      for issue in drift_result.failures))

            manual = deepcopy(reg)
            manual["items"]["kn-1"]["manual_evidence_required"] = "owner document"
            manual["reviewed_binding_sha256"] = gate.source_registry_binding_sha256(manual)
            write_test_source_review_receipt(
                root, "kn-1", manual, clean, private_key, now
            )
            manual_result = gate.evaluate_content_source_gate(
                "kn-1", registry_path, snapshot_path,
                library_name="KNOWLEDGE-POSTS-X.md", now=now,
                _registry_document=manual, _snapshot_document=clean,
                _review_receipt_repo=root)
            check("signed local review never clears required manual evidence",
                  not manual_result.allowed and any(
                      "manual source evidence" in issue
                      for issue in manual_result.failures))

        missing_state = deepcopy(reg)
        missing_state.pop("binding_state")
        missing_state["reviewed_binding_sha256"] = gate.source_registry_binding_sha256(
            missing_state)
        registry_path.write_text(json.dumps(missing_state), encoding="utf-8")
        check("registry binding_state is mandatory",
              any("explicit human review" in issue for issue in
                  gate.evaluate_content_source_gate(
                      "kn-1", registry_path, snapshot_path,
                      library_name="KNOWLEDGE-POSTS-X.md", now=now).failures))

        invalid_date = deepcopy(reg)
        invalid_date["last_human_review"] = "not-a-date"
        registry_path.write_text(json.dumps(invalid_date), encoding="utf-8")
        check("registry review date is strict",
              any("last_human_review" in issue for issue in
                  gate.evaluate_content_source_gate(
                      "kn-1", registry_path, snapshot_path,
                      library_name="KNOWLEDGE-POSTS-X.md", now=now).failures))

        nonfinite = deepcopy(reg)
        nonfinite["freshness_hours"] = float("nan")
        registry_path.write_text(json.dumps(nonfinite), encoding="utf-8")
        result = gate.evaluate_content_source_gate(
            "kn-1", registry_path, snapshot_path,
            library_name="KNOWLEDGE-POSTS-X.md", now=now)
        check("non-finite registry freshness fails closed at decoding",
              not result.allowed and
              any("missing/unreadable" in issue for issue in result.failures))

        for label, malformed in (
            ("duplicate registry keys fail closed",
             '{"schema_version":999,"schema_version":1}'),
            ("overflow registry numbers fail closed",
             '{"schema_version":1,"probe":1e999}'),
        ):
            registry_path.write_text(malformed, encoding="utf-8")
            result = gate.evaluate_content_source_gate(
                "kn-1", registry_path, snapshot_path,
                library_name="KNOWLEDGE-POSTS-X.md", now=now)
            check(label, not result.allowed and
                  any("missing/unreadable" in issue for issue in result.failures))

        semantic_nonfinite = deepcopy(reg)
        semantic_nonfinite["freshness_hours"] = float("nan")
        result = gate.evaluate_content_source_gate(
            "kn-1", registry_path, snapshot_path,
            library_name="KNOWLEDGE-POSTS-X.md", now=now,
            _registry_document=semantic_nonfinite,
            _snapshot_document=clean)
        check("bound-object non-finite freshness retains semantic diagnosis",
              not result.allowed and
              any("positive finite" in issue for issue in result.failures))

        registry_path.write_text(json.dumps(reg), encoding="utf-8")
        wrong = gate.evaluate_content_source_claim(
            "kn-1", ["source-b"], registry_path, snapshot_path,
            library_name="KNOWLEDGE-POSTS-X.md", now=now)
        check("declared IDs require exact registry equality",
              any("exactly equal" in issue for issue in wrong.failures))

    path, library = gate.repo_content_source_contract("b3-01", Path("C:/repo"))
    check("repo resolver selects canonical social registry",
          path.name == "social-source-registry.json" and
          library == "SOCIAL-CONTENT-BINDINGS_20260823")
    check("unknown repo content ID fails closed",
          not gate.evaluate_repo_content_source_claim(
              "unknown-1", ["source-a"], Path("C:/repo"), now=now).allowed)
    check("shared source-truth resolver fails closed for unknown content",
          not gate.evaluate_repo_content_source_gate(
              "unknown-1", Path("C:/repo"), now=now).allowed)
    print("content source gate: %d/%d PASS" % (COUNT, COUNT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
