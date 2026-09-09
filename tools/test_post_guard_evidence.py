#!/usr/bin/env python3
"""Adversarial checks for post_guard manifest and ledger evidence."""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

import post_guard as guard


TARGET = date(2026, 8, 16)
checks = 0


def check(label: str, condition: bool) -> None:
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def row(*, ts: str = "2026-08-16T19:00:00+07:00", clip_id=None, note="") -> dict:
    value = {"type": "video", "channel": "threads", "ts": ts, "note": note}
    if clip_id is not None:
        value["clip_id"] = clip_id
    return value


def main() -> int:
    for negative in ("not posted", "failed: not published", "unscheduled draft"):
        item = {"posted": {"threads": negative}}
        check(
            f"negative manifest evidence is ignored: {negative}",
            guard.manifest_posted_status(item, "THREADS", "threads") is None,
        )

    posted = {"posted": {"threads": "posted-offset (verified)"}}
    check(
        "canonical positive manifest evidence is accepted",
        guard.manifest_posted_status(posted, "THREADS", "threads")["status"] == "POSTED",
    )

    with tempfile.TemporaryDirectory(prefix="post_guard_evidence_") as raw:
        base = Path(raw)
        original_log = guard.AUTOMATION_LOG
        original_manifest = guard.MANIFEST_PATH
        guard.AUTOMATION_LOG = base
        guard.MANIFEST_PATH = base / "manifest.json"
        ledger = base / "post-ledger.jsonl"
        try:
            ledger.write_text(
                json.dumps(row(ts="2026-08-15T19:00:00+07:00", clip_id="right", note="2026-08-16")) + "\n",
                encoding="utf-8",
            )
            check(
                "date mentioned only in a note is not evidence",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0] == "none",
            )

            ledger.write_text(json.dumps(row(clip_id="wrong")) + "\n", encoding="utf-8")
            check(
                "wrong content id fails closed",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0]
                == "evidence_error",
            )

            ledger.write_text(json.dumps(row()) + "\n", encoding="utf-8")
            check(
                "missing content id fails closed",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0]
                == "evidence_error",
            )

            ledger.write_text(json.dumps(row(clip_id="right")) + "\n", encoding="utf-8")
            check(
                "exact date and content id is accepted",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0] == "posted",
            )

            ledger.write_text(
                json.dumps(row(clip_id="right")) + "\n{broken-tail\n",
                encoding="utf-8",
            )
            check(
                "later corrupt row invalidates an earlier apparent match",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0]
                == "evidence_error",
            )

            ledger.write_text(
                '{"type":"failure","type":"video","channel":"threads",'
                '"clip_id":"right","ts":"2026-08-16T19:00:00+07:00"}\n',
                encoding="utf-8",
            )
            check(
                "duplicate ledger keys fail closed",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0]
                == "evidence_error",
            )

            ledger.write_text(
                '{"type":"video","channel":"threads","clip_id":"right",'
                '"ts":"2026-08-16T19:00:00+07:00","unused":1e999}\n',
                encoding="utf-8",
            )
            check(
                "overflowed JSON number fails closed",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0]
                == "evidence_error",
            )

            ledger.write_text("{bad-json\n", encoding="utf-8")
            check(
                "malformed ledger fails closed",
                guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0]
                == "evidence_error",
            )

            ledger.write_text(json.dumps(row(clip_id="right")) + "\n", encoding="utf-8")
            with mock.patch.object(Path, "read_bytes", side_effect=OSError("locked")):
                check(
                    "unreadable ledger fails closed",
                    guard.ledger_evidence("threads", TARGET, "right", require_content_id=True)[0]
                    == "evidence_error",
                )

            invalid_manifest = {
                "items": [{"id": "bad", "date": "2026-08-16", "status": "Posted", "posted": {}}]
            }
            guard.MANIFEST_PATH.write_text(json.dumps(invalid_manifest), encoding="utf-8")
            try:
                guard.load_manifest()
            except guard.GuardSetupError:
                contract_failed = True
            else:
                contract_failed = False
            check("post_guard validates the complete manifest contract", contract_failed)
        finally:
            guard.AUTOMATION_LOG = original_log
            guard.MANIFEST_PATH = original_manifest

    print(f"post_guard evidence: {checks} checks, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
