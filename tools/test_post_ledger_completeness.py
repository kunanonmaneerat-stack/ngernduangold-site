#!/usr/bin/env python3
"""Focused tests for measurable fail-closed permanent-dedup completeness."""

import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation-log"))
import post_ledger as ledger  # noqa: E402


def write_rows(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def write_collision_tombstone(path, rows, *, lines):
    occurrences = []
    for line in lines:
        row = rows[line - 1]
        raw = json.dumps(row, ensure_ascii=False).encode("utf-8")
        occurrences.append({
            "line": line,
            "row_sha256": hashlib.sha256(raw).hexdigest().upper(),
            "ledger_status": row["status"],
            "ledger_date": row["ts"][:10],
        })
    payload = {
        "schema_version": 1,
        "created_at": "2026-08-23T22:00:00+07:00",
        "purpose": "Regression fixture for exact collision occurrence binding.",
        "tombstones": [{
            "tombstone_id": "collision-v1-fb-b3-02",
            "channel": "facebook",
            "identity_type": "clip",
            "identity": "b3-02",
            "reuse_policy": "HISTORICAL_CANONICAL_COLLISION_NON_REUSABLE",
            "external_delivery_resolution": "UNKNOWN_NO_INFERENCE",
            "occurrences": occurrences,
        }],
        "self_sha256": "",
    }
    payload["self_sha256"] = ledger.post_ledger_collision.payload_sha256(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory(prefix="ledger_completeness_") as raw:
        path = Path(raw) / "ledger.jsonl"
        complete_text = {
            "type": "text",
            "channel": "threads",
            "text_hash": ledger.text_hash("ข้อความหนึ่ง"),
            "text_norm": ledger.normalize_text("ข้อความหนึ่ง"),
            "ts": "2026-08-01T12:00:00+07:00",
        }
        complete_clip = {
            "type": "video",
            "channel": "facebook",
            "clip_id": "b3-02",
            "ts": "2026-08-02T12:00:00+07:00",
        }
        write_rows(path, [complete_text, complete_clip])
        allowed, reason, metric = ledger.permanent_dedup_gate(path)
        check(
            "complete permanent identities pass with a 100 percent metric",
            allowed and reason and metric["coverage_percent"] == 100.0,
        )

        duplicate_clip = dict(complete_clip)
        duplicate_clip["ts"] = "2026-08-04T12:00:00+07:00"
        write_rows(path, [complete_clip, duplicate_clip])
        allowed, reason, metric = ledger.permanent_dedup_gate(path)
        check(
            "complete duplicate clip identities still block permanently",
            not allowed
            and metric["coverage_percent"] == 100.0
            and metric["duplicate_identity_groups"] == 1
            and "duplicate canonical identity" in reason,
        )

        cancelled_clip = dict(duplicate_clip)
        cancelled_clip["status"] = "cancelled"
        write_rows(path, [complete_clip, cancelled_clip])
        allowed, reason, metric = ledger.permanent_dedup_gate(path)
        check(
            "explicitly cancelled duplicate does not create a false collision",
            allowed and metric["duplicate_identity_groups"] == 0,
        )

        shared_key = ledger.make_dedup_key("facebook", "b3-02", "2026-08-02")
        first_shared = dict(complete_clip, dedup_key=shared_key, status="posted")
        second_shared = dict(first_shared, ts="2026-08-02T18:00:00+07:00")
        shared_cancel = {
            "type": "status", "dedup_key": shared_key, "status": "cancelled",
            "ts": "2026-08-02T19:00:00+07:00",
        }
        write_rows(path, [first_shared, second_shared, shared_cancel])
        shared_allowed, shared_reason, shared_metric = ledger.permanent_dedup_gate(path)
        check(
            "one status row cannot mask multiple base rows sharing a dedup key",
            not shared_allowed
            and shared_metric["state"] == "BLOCKED"
            and shared_metric["integrity_state"] == "UNKNOWN"
            and "multiple base identity rows" in shared_reason,
        )

        original_snapshot = ledger._read_ledger_snapshot
        ledger._read_ledger_snapshot = lambda _path=None: (
            [complete_clip, duplicate_clip],
            {
                "state": "OK",
                "identity_coverage": {
                    "state": "COMPLETE", "complete_rows": 2,
                    "incomplete_rows": 0,
                },
                "identity_bindings": {},
                "identity_binding_report": {"state": "NOT_PRESENT"},
                "collision_tombstone_report": {
                    "state": "PASS", "tombstone_count": 1,
                    "non_reusable_identities": [
                        {
                            "identity_type": "clip",
                            "channel": "fb",
                            "identity": "b3-02",
                        }
                    ],
                },
                "collision_tombstones": {("clip", "fb", "b3-02")},
            },
        )
        try:
            tombstoned = ledger.permanent_dedup_completeness(path)
        finally:
            ledger._read_ledger_snapshot = original_snapshot
        check(
            "valid collision tombstone resolves history health but preserves evidence",
            tombstoned["state"] == "PASS"
            and tombstoned["duplicate_identity_groups"] == 0
            and tombstoned["tombstoned_duplicate_identity_groups"] == 1,
        )
        duplicate, reason, codes = ledger.is_twin({
            "integrity": {"state": "OK"},
            "collision_tombstone_report": {"state": "PASS"},
            "collision_tombstoned_clip_identities": {("fb", "b3-02")},
            "identity_coverage": {"state": "COMPLETE"},
        }, "facebook", "b3-02", ledger.now_local().date())
        check(
            "tombstoned historical collision remains permanently non-reusable",
            duplicate
            and "HISTORICAL_CANONICAL_COLLISION_NON_REUSABLE" in codes
            and "permanently non-reusable" in reason,
        )

        duplicate_text = dict(complete_text)
        duplicate_text["ts"] = "2026-08-05T12:00:00+07:00"
        write_rows(path, [complete_text, duplicate_text])
        allowed, reason, metric = ledger.permanent_dedup_gate(path)
        check(
            "complete duplicate text identities also block permanently",
            not allowed
            and metric["duplicate_identity_groups"] == 1
            and metric["duplicate_identities"][0]["identity_type"] == "text_hash",
        )

        incomplete = {
            "type": "text",
            "channel": "threads",
            "text_first80": "legacy prefix only",
            "ts": "2026-08-03T12:00:00+07:00",
        }
        write_rows(path, [complete_text, incomplete])
        allowed, reason, metric = ledger.permanent_dedup_gate(path)
        check(
            "legacy prefix-only identity blocks at 50 percent completeness",
            not allowed
            and metric["coverage_percent"] == 50.0
            and "1 incomplete" in reason,
        )
        duplicate, reason, finding = ledger.is_duplicate_text(
            "facebook", "ข้อความใหม่", path=path
        )
        check(
            "unrelated incomplete channel does not deadlock Facebook text dedup",
            not duplicate and reason == "" and finding is None,
        )
        duplicate, reason, finding = ledger.is_duplicate_text(
            "threads", "ข้อความใหม่", path=path
        )
        check(
            "text duplicate decision fails closed on its own incomplete channel",
            duplicate
            and finding.get("type") == "dedup_completeness"
            and "fail-closed" in reason,
        )

        original = ledger.LEDGER
        ledger.LEDGER = str(path)
        try:
            result = ledger.record_post("threads", "save", "2026-08-24")
        finally:
            ledger.LEDGER = original
        check(
            "clip writer refuses incomplete permanent history without changing it",
            not result["appended"]
            and result["reason"].startswith("DEDUP_COMPLETENESS_BLOCK:"),
        )
        check("completeness test leaves no lock", not os.path.exists(ledger._lock_path(path)))

    with tempfile.TemporaryDirectory(prefix="ledger_tombstone_occurrences_") as raw:
        path = Path(raw) / "ledger.jsonl"
        tombstone_path = path.with_name("post-ledger-collision-tombstones.json")
        rows = [
            {
                "type": "video", "channel": "facebook", "clip_key": "b3-02",
                "ts": "2026-08-02T12:00:00+07:00", "status": "posted",
            },
            {
                "type": "video", "channel": "facebook", "clip_key": "b3-02",
                "ts": "2026-08-04T12:00:00+07:00", "status": "posted",
            },
        ]
        write_rows(path, rows)
        write_collision_tombstone(tombstone_path, rows, lines=[1, 2])
        exact = ledger.permanent_dedup_completeness(path)
        check(
            "tombstone resolves only the exact complete two-occurrence collision set",
            exact["state"] == "PASS"
            and exact["collision_tombstone_state"] == "PASS"
            and exact["duplicate_identity_groups"] == 0
            and exact["tombstoned_duplicate_identity_rows"] == 2,
        )

        rows.append({
            "type": "video", "channel": "facebook", "clip_key": "b3-02",
            "ts": "2026-08-06T12:00:00+07:00", "status": "posted",
        })
        write_rows(path, rows)
        stale = ledger.permanent_dedup_completeness(path)
        check(
            "new third occurrence invalidates the old tombstone and hard-blocks",
            stale["state"] == "BLOCKED"
            and stale["collision_tombstone_state"] == "INVALID"
            and stale["duplicate_identity_groups"] == 1
            and stale["duplicate_identity_rows"] == 3
            and any("occurrence set mismatch" in item for item in stale["failures"]),
        )

    current = ledger.permanent_dedup_completeness(
        ROOT / "automation-log" / "post-ledger.jsonl"
    )
    check(
        "current ledger reports its incomplete history instead of passing",
        current["state"] == "BLOCKED"
        and current["complete_rows"] == 124
        and current["incomplete_rows"] == 1
        and current["coverage_percent"] == 99.2
        and current["duplicate_identity_groups"] == 0
        and current["tombstoned_duplicate_identity_groups"] == 3,
    )
    print("post ledger completeness: 14/14 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
