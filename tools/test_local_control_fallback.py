from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import local_control_fallback as fallback


NOW = dt.datetime(2026, 8, 24, 22, 45, tzinfo=fallback.LOCAL_TZ)


def bound_snapshot(task_count: int = 1) -> dict:
    tasks = []
    for index in range(task_count):
        tasks.append({
            "source": "cowork",
            "task_id": "ngernduangold-control-%d" % index,
            "due_at": "2026-08-24T%02d:00:00+07:00" % (8 + index),
            "scheduler_state": "MISSED_OR_STUCK",
            "last_attempt_state": "RUNNER_FAILED",
            "task_record_sha256": ("%064x" % (index + 1)),
        })
    payload = {
        "status": "BOUND",
        "reason_code": None,
        "record_count": task_count,
        "blocking_task_count": task_count,
        "blocking_tasks": tasks,
    }
    payload["snapshot_sha256"] = fallback._sha_bytes(fallback._canonical(payload))
    return payload


def completed(returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["python"], returncode=returncode, stdout=b"ok\n", stderr=b""
    )


class LocalControlFallbackTests(unittest.TestCase):
    def test_allowlist_contains_no_external_action_entrypoint(self):
        specs = fallback._check_specs(NOW)
        rendered = " ".join(
            " ".join([item["entrypoint"], *item["args"]]) for item in specs
        ).lower()
        for forbidden in (
            "publish_fb", "publish_tiktok", "post_agent", "ga4_pull",
            "gsc_pull", "deploy", "notify", "clicktest", "--live", " pack",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertEqual(
            [
                "daily_media_2026-08-24",
                "daily_media_2026-08-25",
                "daily_media_2026-08-26",
            ],
            [item["id"] for item in specs if item["id"].startswith("daily_media_")],
        )

    def test_blocking_due_task_keeps_terminal_blocked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document, receipt = fallback.run_fallback(
                now=NOW,
                receipt_root=Path(temp_dir),
                scheduler_snapshot=bound_snapshot(1),
                command_runner=lambda *args, **kwargs: completed(0),
            )
            self.assertTrue(receipt.is_file())
            self.assertEqual(
                "LOCAL_CHECKS_COMPLETED_BLOCKED", document["terminal"]["state"]
            )
            self.assertIn("SCHEDULER_DUE_GAPS_REMAIN_1", document["terminal"]["blockers"])
            self.assertEqual({
                "scheduler_dispatch_proven": False,
                "scheduler_task_completion_claimed": False,
                "due_slots_repaired_or_backfilled": False,
                "compatible_with_scheduler_task_receipt": False,
            }, document["scheduler_claims"])
            validated = fallback.validate_receipt(
                receipt, verify_current_scheduler=False
            )
            self.assertEqual(document["run_id"], validated["run_id"])

    def test_no_due_gap_and_all_pass_is_local_complete_only(self):
        snapshot = bound_snapshot(0)
        with tempfile.TemporaryDirectory() as temp_dir:
            document, _receipt = fallback.run_fallback(
                now=NOW,
                receipt_root=Path(temp_dir),
                scheduler_snapshot=snapshot,
                command_runner=lambda *args, **kwargs: completed(0),
            )
        self.assertEqual("LOCAL_CHECKS_COMPLETED", document["terminal"]["state"])
        self.assertFalse(document["scheduler_claims"]["scheduler_task_completion_claimed"])

    def test_check_nonzero_uses_exact_exit_contract(self):
        calls = 0

        def runner(*args, **kwargs):
            nonlocal calls
            calls += 1
            # content_calendar is the fifth check; exit 1 is COMPLETED_BLOCKED.
            return completed(1 if calls == 5 else 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            document, receipt = fallback.run_fallback(
                now=NOW,
                receipt_root=Path(temp_dir),
                scheduler_snapshot=bound_snapshot(0),
                command_runner=runner,
            )
            self.assertEqual(
                "COMPLETED_BLOCKED", document["checks"][4]["state"]
            )
            self.assertEqual(
                "LOCAL_CHECKS_COMPLETED_BLOCKED", document["terminal"]["state"]
            )
            fallback.validate_receipt(receipt, verify_current_scheduler=False)

    def test_unknown_exit_is_runner_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document, _receipt = fallback.run_fallback(
                now=NOW,
                receipt_root=Path(temp_dir),
                scheduler_snapshot=bound_snapshot(0),
                command_runner=lambda *args, **kwargs: completed(77),
            )
        self.assertEqual("RUNNER_FAILED", document["terminal"]["state"])
        self.assertTrue(all(row["state"] == "RUNNER_FAILED" for row in document["checks"]))

    def test_tampered_task_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _document, receipt = fallback.run_fallback(
                now=NOW,
                receipt_root=Path(temp_dir),
                scheduler_snapshot=bound_snapshot(1),
                command_runner=lambda *args, **kwargs: completed(0),
            )
            tampered = json.loads(receipt.read_text(encoding="utf-8"))
            tampered["scheduler_snapshot"]["blocking_tasks"][0][
                "task_record_sha256"
            ] = "f" * 64
            receipt.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(
                fallback.FallbackEvidenceError, "integrity hash mismatch"
            ):
                fallback.validate_receipt(
                    receipt, verify_current_scheduler=False
                )

    def test_false_pass_with_recomputed_integrity_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _document, receipt = fallback.run_fallback(
                now=NOW,
                receipt_root=Path(temp_dir),
                scheduler_snapshot=bound_snapshot(1),
                command_runner=lambda *args, **kwargs: completed(0),
            )
            tampered = json.loads(receipt.read_text(encoding="utf-8"))
            tampered["terminal"]["state"] = "LOCAL_CHECKS_COMPLETED"
            tampered["terminal"]["blockers"] = []
            tampered["terminal"]["result_sha256"] = fallback._sha_bytes(
                fallback._canonical({
                    "scheduler_snapshot": tampered["scheduler_snapshot"],
                    "checks": tampered["checks"],
                    "terminal_state": tampered["terminal"]["state"],
                    "blockers": [],
                })
            )
            tampered["receipt_integrity_sha256"] = fallback._receipt_integrity(tampered)
            receipt.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(
                fallback.FallbackEvidenceError, "terminal state is not fail-closed"
            ):
                fallback.validate_receipt(
                    receipt, verify_current_scheduler=False
                )

    def test_receipt_root_cannot_overlap_scheduler_receipts(self):
        with self.assertRaisesRegex(
            fallback.FallbackEvidenceError, "cannot enter scheduler-task-receipts"
        ):
            fallback._safe_receipt_root(
                fallback.FORBIDDEN_RECEIPT_ROOT / "cowork" / "fake-task"
            )

    def test_snapshot_hash_covers_due_and_task_record_hash(self):
        snapshot = bound_snapshot(2)
        fallback._validate_snapshot(snapshot)
        changed = copy.deepcopy(snapshot)
        changed["blocking_tasks"][0]["due_at"] = "2026-08-24T09:00:00+07:00"
        with self.assertRaisesRegex(
            fallback.FallbackEvidenceError, "snapshot hash mismatch"
        ):
            fallback._validate_snapshot(changed)


if __name__ == "__main__":
    unittest.main()
