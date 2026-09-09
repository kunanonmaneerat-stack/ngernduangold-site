#!/usr/bin/env python3
"""Adversarial mutation-boundary tests for agent_gap_check.

All production CLI shapes are evaluated against temporary alert paths.  The
tests never query or mutate an actual scheduler and never touch the repository
alert.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import agent_gap_check as gap  # noqa: E402
import automation_policy_guard as policy_guard  # noqa: E402


class AgentGapReadOnlyTests(unittest.TestCase):
    def _run_main(self, alert: Path, argv: list[str], *, blocking: bool) -> int:
        now = datetime.datetime(2026, 8, 24, 10, 0)
        if blocking:
            scheduler_result = (
                "missed-or-stuck",
                "1 missed-or-stuck, 0 current runner-failed",
                [{
                    "source": "cowork",
                    "id": "ngernduangold-test",
                    "status": "MISSED_OR_STUCK",
                    "reason": "cron slot has no exact dispatch within SLA",
                    "due_at": "2026-08-24T08:00:00+07:00",
                    "last_scheduled_for": "2026-08-23T08:00:00+07:00",
                    "last_run_at": "2026-08-23T08:01:00+07:00",
                }],
            )
        else:
            scheduler_result = ("ok", "1 due slot has a receipt", [{
                "source": "cowork",
                "id": "ngernduangold-test",
                "status": "COMPLETED",
            }])
        with (
            mock.patch.object(gap, "ALERT", str(alert)),
            mock.patch.object(gap, "_traces", return_value=[("trace", "unused")]),
            mock.patch.object(gap, "last_seen", return_value=(now, 1)),
            mock.patch.object(gap, "judge", return_value=("ok", 1.0, "fresh")),
            mock.patch.object(gap, "newest_report", return_value=(now, "report")),
            mock.patch.object(gap, "judge_reporting", return_value=("ok", "fresh")),
            mock.patch.object(gap, "scheduler_records", return_value=([{}], None)),
            mock.patch.object(gap, "judge_scheduler", return_value=scheduler_result),
            mock.patch.object(sys, "argv", ["agent_gap_check.py", *argv]),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            return gap.main()

    def test_default_json_and_quiet_modes_never_create_or_modify_alert(self) -> None:
        for argv in ([], ["--json"], ["--quiet"]):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as tmp:
                alert = Path(tmp) / "AGENT-SILENT-ALERT.md"
                self.assertEqual(self._run_main(alert, argv, blocking=True), 2)
                self.assertFalse(alert.exists(), "read-only audit created an alert")

                sentinel = b"existing-alert-must-remain-byte-exact\n"
                alert.write_bytes(sentinel)
                before = alert.stat().st_mtime_ns
                self.assertEqual(self._run_main(alert, argv, blocking=True), 2)
                self.assertEqual(alert.read_bytes(), sentinel)
                self.assertEqual(alert.stat().st_mtime_ns, before)

    def test_default_json_and_quiet_modes_never_delete_alert_on_pass(self) -> None:
        for argv in ([], ["--json"], ["--quiet"]):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as tmp:
                alert = Path(tmp) / "AGENT-SILENT-ALERT.md"
                sentinel = b"do-not-delete-from-read-only-audit\n"
                alert.write_bytes(sentinel)
                before = alert.stat().st_mtime_ns
                self.assertEqual(self._run_main(alert, argv, blocking=False), 0)
                self.assertEqual(alert.read_bytes(), sentinel)
                self.assertEqual(alert.stat().st_mtime_ns, before)

    def test_explicit_cli_writer_is_required_and_privacy_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alert = Path(tmp) / "AGENT-SILENT-ALERT.md"
            malicious_detail = (
                "missed private.person@example.invalid at "
                r"C:\Users\Private\account.json via https://example.invalid/?token=secret"
            )
            scheduler_result = (
                "runner-failed",
                malicious_detail,
                [{
                    "source": "cowork",
                    "id": "ngernduangold-safe-id",
                    "status": "RUNNER_FAILED",
                    "reason": malicious_detail,
                    "due_at": "2026-08-24T08:00:00+07:00",
                    "last_scheduled_for": "2026-08-24T08:00:00+07:00",
                    "last_run_at": "2026-08-24T08:01:00+07:00",
                    "session_evidence": {
                        "session_id": "private-session-id",
                        "session_sha256": "a" * 64,
                        "error_sha256": "b" * 64,
                        "error_class": "WEEKLY_LIMIT",
                    },
                }],
            )
            now = datetime.datetime(2026, 8, 24, 10, 0)
            with (
                mock.patch.object(gap, "ALERT", str(alert)),
                mock.patch.object(gap, "_traces", return_value=[("trace", "unused")]),
                mock.patch.object(gap, "last_seen", return_value=(now, 1)),
                mock.patch.object(gap, "judge", return_value=("ok", 1.0, "fresh")),
                mock.patch.object(gap, "newest_report", return_value=(now, "report")),
                mock.patch.object(gap, "judge_reporting", return_value=("ok", "fresh")),
                mock.patch.object(gap, "scheduler_records", return_value=([{}], None)),
                mock.patch.object(gap, "judge_scheduler", return_value=scheduler_result),
                mock.patch.object(
                    sys, "argv", ["agent_gap_check.py", gap.ALERT_MUTATION_FLAG]
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(gap.main(), 2)

            body = alert.read_text(encoding="utf-8")
            self.assertIn("ngernduangold-safe-id", body)
            self.assertIn("WEEKLY_LIMIT", body)
            for secret in (
                "private.person@example.invalid", r"C:\Users\Private",
                "https://example.invalid", "token=secret", "private-session-id",
                "a" * 64, "b" * 64,
            ):
                self.assertNotIn(secret, body)
            self.assertEqual(list(alert.parent.glob(".*.tmp")), [])

    def test_atomic_failure_preserves_old_alert_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alert = Path(tmp) / "AGENT-SILENT-ALERT.md"
            original = b"previous-good-alert\n"
            alert.write_bytes(original)
            with (
                mock.patch.object(gap, "ALERT", str(alert)),
                mock.patch.object(gap.os, "replace", side_effect=OSError("disk failure")),
                self.assertRaises(OSError),
            ):
                gap.write_alert(30.0, "safe detail", [("trace", None, 0)])
            self.assertEqual(alert.read_bytes(), original)
            self.assertEqual(list(alert.parent.glob(".*.tmp")), [])

    def test_explicit_writer_can_clear_but_read_only_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alert = Path(tmp) / "AGENT-SILENT-ALERT.md"
            alert.write_text("obsolete\n", encoding="utf-8")
            self.assertEqual(
                self._run_main(
                    alert, [gap.ALERT_MUTATION_FLAG], blocking=False
                ),
                0,
            )
            self.assertFalse(alert.exists())

    def test_explicit_writer_failure_is_sanitised_runner_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alert = Path(tmp) / "AGENT-SILENT-ALERT.md"
            private_error = r"disk failed for C:\Users\Private\account.json"
            now = datetime.datetime(2026, 8, 24, 10, 0)
            scheduler_result = (
                "missed-or-stuck", "one missed", [{
                    "source": "cowork",
                    "id": "ngernduangold-test",
                    "status": "MISSED_OR_STUCK",
                }],
            )
            stderr = io.StringIO()
            with (
                mock.patch.object(gap, "ALERT", str(alert)),
                mock.patch.object(gap, "_traces", return_value=[("trace", "unused")]),
                mock.patch.object(gap, "last_seen", return_value=(now, 1)),
                mock.patch.object(gap, "judge", return_value=("ok", 1.0, "fresh")),
                mock.patch.object(gap, "newest_report", return_value=(now, "report")),
                mock.patch.object(gap, "judge_reporting", return_value=("ok", "fresh")),
                mock.patch.object(gap, "scheduler_records", return_value=([{}], None)),
                mock.patch.object(gap, "judge_scheduler", return_value=scheduler_result),
                mock.patch.object(
                    gap, "write_scheduler_alert", side_effect=OSError(private_error)
                ),
                mock.patch.object(
                    sys, "argv", ["agent_gap_check.py", gap.ALERT_MUTATION_FLAG]
                ),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(gap._guarded_entrypoint(), 3)
            self.assertIn("OSError", stderr.getvalue())
            self.assertNotIn(private_error, stderr.getvalue())
            self.assertFalse(alert.exists())


class SchedulerLifecycleTests(unittest.TestCase):
    NOW = datetime.datetime(2026, 8, 24, 12, 0, tzinfo=gap.LOCAL_TZ)

    @staticmethod
    def _disabled_row(**overrides):
        row = {
            "source": "cowork",
            "id": "ngernduangold-disabled-history",
            "enabled": False,
            "cronExpression": "0 8 * * *",
            "lastScheduledFor": "2026-08-24T01:00:00Z",
            "lastRunAt": "2026-08-24T01:01:00Z",
            "session_evidence": {
                "error_class": "WEEKLY_LIMIT",
                "created_at": "2026-08-24T08:01:00+07:00",
                "last_activity_at": "2026-08-24T08:02:00+07:00",
            },
        }
        row.update(overrides)
        return row

    def test_disabled_runner_failure_remains_unresolved_not_recovered(self):
        verdict, detail, rows = gap.judge_scheduler(
            self.NOW, [self._disabled_row()]
        )
        self.assertEqual("disabled-unresolved", verdict)
        self.assertIn("1 disabled-unresolved", detail)
        self.assertEqual("UNKNOWN", rows[0]["status"])
        self.assertEqual("DISABLED", rows[0]["lifecycle_state"])
        self.assertEqual("RUNNER_FAILED", rows[0]["historical_status"])
        self.assertTrue(rows[0]["disabled_unresolved"])
        counts = gap._scheduler_state_counts(rows)
        self.assertEqual(1, counts["disabled_unresolved"])
        self.assertEqual(1, counts["disabled_historical_runner_failed"])

    def test_disabled_late_run_preserves_missed_slot_and_late_attempt(self):
        row = self._disabled_row(
            lastRunAt="2026-08-24T04:00:00Z",
            session_evidence={
                "error_class": "WEEKLY_LIMIT",
                "created_at": "2026-08-24T11:00:00+07:00",
                "last_activity_at": "2026-08-24T11:01:00+07:00",
            },
        )
        verdict, _detail, rows = gap.judge_scheduler(self.NOW, [row])
        self.assertEqual("disabled-unresolved", verdict)
        self.assertEqual("UNKNOWN", rows[0]["status"])
        self.assertEqual("MISSED_OR_STUCK", rows[0]["historical_status"])
        self.assertEqual("RUNNER_FAILED", rows[0]["last_attempt_status"])
        self.assertEqual(
            "MISSING_OR_STALE", rows[0]["evidence_chain"]["dispatch"]
        )

    def test_disabled_missing_receipt_stays_unknown_after_sla(self):
        row = self._disabled_row(session_evidence={
            "error_class": None,
            "created_at": "2026-08-24T08:01:00+07:00",
            "last_activity_at": "2026-08-24T08:02:00+07:00",
        })
        verdict, _detail, rows = gap.judge_scheduler(self.NOW, [row])
        self.assertEqual("disabled-unresolved", verdict)
        self.assertEqual("UNKNOWN", rows[0]["status"])
        self.assertEqual("UNKNOWN", rows[0]["historical_status"])
        self.assertEqual("MISSING", rows[0]["receipt_evidence"]["state"])
        self.assertTrue(rows[0]["disabled_unresolved"])

    def test_only_valid_completed_receipt_resolves_disabled_history(self):
        row = self._disabled_row(session_evidence={
            "error_class": None,
            "created_at": "2026-08-24T08:01:00+07:00",
            "last_activity_at": "2026-08-24T08:02:00+07:00",
        })
        receipt = {
            "state": "VALID",
            "terminal_status": "COMPLETED",
            "deliverable_count": 1,
            "errors": [],
        }
        with mock.patch.object(
            gap, "_scheduler_receipt_evidence", return_value=receipt
        ):
            verdict, _detail, rows = gap.judge_scheduler(self.NOW, [row])
        self.assertEqual("ok", verdict)
        self.assertEqual("SKIP", rows[0]["status"])
        self.assertEqual("COMPLETED", rows[0]["historical_status"])
        self.assertFalse(rows[0]["disabled_unresolved"])

    def test_registry_discovery_retains_disabled_project_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scheduled-tasks.json"
            rows = [{
                "id": "ngernduangold-disabled-history",
                "enabled": False,
                "filePath": "X",
                "cronExpression": "0 8 * * *",
                "lastScheduledFor": "2026-08-24T01:00:00Z",
                "lastRunAt": "2026-08-24T01:01:00Z",
            }, {
                "id": "unrelated-personal-job",
                "enabled": False,
                "filePath": "Y",
                "cronExpression": "0 8 * * *",
            }]
            raw = json.dumps({"scheduledTasks": rows}).encode("utf-8")
            path.write_bytes(raw)
            discovered, error = gap._stable_raw_registry({
                "name": "cowork",
                "registry_path": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "records": [{
                    "id": row["id"], "enabled": row["enabled"],
                    "file_path": row["filePath"],
                } for row in rows],
            })
        self.assertIsNone(error)
        self.assertEqual(
            ["ngernduangold-disabled-history"],
            [row["id"] for row in discovered],
        )
        self.assertFalse(discovered[0]["enabled"])

    def test_live_owner_suppresses_its_disabled_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = []
            for name, enabled in (("cowork", False), ("ccd", True)):
                folder = Path(tmp) / name
                folder.mkdir()
                path = folder / "scheduled-tasks.json"
                row = {
                    "id": "ngernduangold-owner-move",
                    "enabled": enabled,
                    "filePath": name.upper(),
                    "cronExpression": "0 8 * * *",
                    "lastScheduledFor": "2026-09-05T01:00:00Z",
                    "lastRunAt": "2026-09-05T01:01:00Z",
                }
                raw = json.dumps({"scheduledTasks": [row]}).encode("utf-8")
                path.write_bytes(raw)
                sources.append({
                    "name": name,
                    "registry_path": str(path),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "records": [{
                        "id": row["id"], "enabled": enabled,
                        "file_path": row["filePath"],
                    }],
                })
            with mock.patch.object(
                policy_guard, "query_claude_scheduler_registries",
                return_value={"status": "OK", "sources": sources},
            ):
                records, error = gap.scheduler_records()
        self.assertIsNone(error)
        self.assertEqual(1, len(records))
        self.assertEqual("ccd", records[0]["source"])
        self.assertTrue(records[0]["enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
