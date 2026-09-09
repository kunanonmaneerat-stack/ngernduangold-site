#!/usr/bin/env python3
"""Contract tests for the private raw revenue intake writer."""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import log_sale


class LogSaleContractTests(unittest.TestCase):
    NOW = dt.datetime(2026, 8, 15, 12, 0, tzinfo=log_sale.BANGKOK)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sales-intake.jsonl"

    def invoke(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(log_sale, "LOG", str(self.path)),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                code = log_sale.main(list(args))
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 2
        return code, stdout.getvalue(), stderr.getvalue()

    def args(self, sale_id: str = "gumroad-A1", event_id: str | None = None) -> tuple[str, ...]:
        return (
            "--event-id", event_id or ("event-" + sale_id),
            "--sale-id", sale_id,
            "--product", "ebook-59",
            "--amount", "59",
            "--status", "paid",
            "--source", "gumroad",
            "--date", "2026-08-15",
        )

    def record(self, sale_id: str, **overrides: object) -> dict:
        values = {
            "event_id": "event-" + sale_id,
            "sale_id": sale_id,
            "product": "affiliate-commission",
            "amount": 100,
            "fee": 10,
            "status": "paid",
            "source": "direct",
            "date": "2026-08-15",
            "now": self.NOW,
        }
        values.update(overrides)
        return log_sale.make_record(**values)

    def test_cli_requires_explicit_lifecycle_and_writes_intake_only(self) -> None:
        original = self.args()
        without_status = tuple(
            item for pair in zip(original[::2], original[1::2])
            if pair[0] != "--status" for item in pair
        )
        code, _, _ = self.invoke(*without_status)
        self.assertEqual(code, 2)
        self.assertFalse(self.path.exists())

        code, stdout, _ = self.invoke(*self.args())
        self.assertEqual(code, 0)
        row = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["gross_amount_thb"], 59)
        self.assertEqual(row["net_amount_thb"], 59)
        self.assertIn("UNRECONCILED", stdout)
        self.assertNotIn("confirmed", stdout)

    def test_legacy_confirmed_and_idempotency_conflicts_are_handled(self) -> None:
        legacy = list(self.args())
        legacy[legacy.index("paid")] = "confirmed"
        self.assertEqual(self.invoke(*legacy)[0], 2)
        self.assertEqual(self.invoke(*self.args())[0], 0)
        self.assertEqual(self.invoke(*self.args())[0], 0)
        self.assertEqual(
            self.invoke(*self.args(), "--note", "different retry payload")[0], 2
        )
        self.assertEqual(
            self.invoke(*self.args(event_id="event-gumroad-A1-second"))[0], 2
        )
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)

    def test_fixed_price_blocked_product_and_pii_are_rejected(self) -> None:
        mismatch = list(self.args("gumroad-A2"))
        mismatch[mismatch.index("59")] = "199"
        self.assertEqual(self.invoke(*mismatch)[0], 2)
        blocked = list(self.args("line-A3"))
        blocked[blocked.index("ebook-59")] = "letter-kit-199"
        self.assertEqual(self.invoke(*blocked)[0], 2)
        self.assertEqual(self.invoke(*self.args("safe-A4"), "--note", "buyer@example.com")[0], 2)
        self.assertEqual(self.invoke(*self.args("safe-A5"), "--note", "+66 81 234 5678")[0], 2)
        self.assertEqual(self.invoke(*self.args("safe-A6"), "--note", "127.0.0.1")[0], 2)
        self.assertEqual(self.invoke(*self.args("safe-A7"), "--note", "2001:db8::1")[0], 2)
        self.assertEqual(self.invoke(*self.args("safe-A8"), "--note", "x" * 501)[0], 2)
        self.assertEqual(self.invoke(*self.args("safe-A9"), "--note", "line1\nline2")[0], 2)
        self.assertFalse(self.path.exists())

    def test_non_finite_precision_future_and_invalid_zero_status_money_fail(self) -> None:
        for index, amount in enumerate(("NaN", "Infinity", "1.001"), 1):
            args = list(self.args(f"bad-money-{index}"))
            args[args.index("59")] = amount
            with self.subTest(amount=amount):
                self.assertEqual(self.invoke(*args)[0], 2)
        future = list(self.args("future-A1"))
        future[future.index("2026-08-15")] = "2999-01-01"
        self.assertEqual(self.invoke(*future)[0], 2)
        with self.assertRaises(log_sale.IntakeError):
            self.record("cancelled-bad", status="cancelled", amount=1, fee=0)
        with self.assertRaises(log_sale.IntakeError):
            self.record("rejected-bad", status="rejected", amount=0, fee=1)

    def test_each_lifecycle_has_exact_canonical_money(self) -> None:
        expected = {
            "pending": 90,
            "approved": 90,
            "paid": 90,
            "refunded": -90,
            "rejected": 0,
            "cancelled": 0,
        }
        for status, net in expected.items():
            amount = 0 if status in log_sale.ZERO_STATUSES else 100
            fee = 0 if status in log_sale.ZERO_STATUSES else 10
            row = self.record(status + "-A1", status=status, amount=amount, fee=fee)
            with self.subTest(status=status):
                self.assertEqual(row["net_amount_thb"], net)
                self.assertEqual(log_sale.validate_record(row, now=self.NOW), row)

    def test_append_fsyncs_lock_and_row_and_rejects_forged_record(self) -> None:
        row = self.record("durable-A1")
        real_fsync = log_sale.os.fsync
        with mock.patch.object(log_sale.os, "fsync", wraps=real_fsync) as fsync:
            log_sale.append_record(row, self.path)
        self.assertGreaterEqual(fsync.call_count, 2)
        forged = self.record("forged-A1")
        forged["net_amount_thb"] = 999
        with self.assertRaises(log_sale.IntakeError):
            log_sale.append_record(forged, self.path)
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)

    def test_same_event_retry_is_idempotent_even_when_local_timestamp_changes(self) -> None:
        first = self.record("retry-A1", event_id="retry-event")
        retry = self.record(
            "retry-A1", event_id="retry-event",
            now=self.NOW + dt.timedelta(minutes=1),
        )
        log_sale.append_record(first, self.path)
        log_sale.append_record(retry, self.path)
        rows = self.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0])["ts"], first["ts"])

    def test_monotonic_lifecycle_reduces_to_latest_and_rejects_backward_events(self) -> None:
        events = [
            self.record("life-A1", event_id="life-pending", status="pending"),
            self.record(
                "life-A1", event_id="life-approved", status="approved",
                now=self.NOW + dt.timedelta(seconds=1),
            ),
            self.record(
                "life-A1", event_id="life-paid", status="paid",
                now=self.NOW + dt.timedelta(seconds=2),
            ),
            self.record(
                "life-A1", event_id="life-refunded", status="refunded",
                now=self.NOW + dt.timedelta(seconds=3),
            ),
        ]
        for row in events:
            log_sale.append_record(row, self.path)
        latest = log_sale.validate_event_sequence(events, now=self.NOW + dt.timedelta(seconds=4))
        self.assertEqual(latest["life-A1"]["status"], "refunded")
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 4)

        backward = self.record(
            "life-A1", event_id="life-backward", status="approved",
            now=self.NOW + dt.timedelta(seconds=4),
        )
        with self.assertRaisesRegex(log_sale.IntakeError, "invalid lifecycle transition"):
            log_sale.append_record(backward, self.path)

    def test_event_sequence_rejects_initial_refund_terminal_reuse_and_mutation(self) -> None:
        initial_refund = self.record("refund-first", status="refunded")
        with self.assertRaisesRegex(log_sale.IntakeError, "cannot start"):
            log_sale.validate_event_sequence([initial_refund], now=self.NOW)

        cancelled = self.record(
            "terminal-A1", status="cancelled", amount=0, fee=0,
        )
        after_terminal = self.record(
            "terminal-A1", event_id="terminal-after", status="paid",
            now=self.NOW + dt.timedelta(seconds=1),
        )
        with self.assertRaisesRegex(log_sale.IntakeError, "invalid lifecycle transition"):
            log_sale.validate_event_sequence(
                [cancelled, after_terminal], now=self.NOW + dt.timedelta(seconds=2)
            )

        pending = self.record("mutate-A1", status="pending")
        mutation = self.record(
            "mutate-A1", event_id="mutate-paid", status="paid", source="fb",
            now=self.NOW + dt.timedelta(seconds=1),
        )
        with self.assertRaisesRegex(log_sale.IntakeError, "channel_source cannot change"):
            log_sale.validate_event_sequence(
                [pending, mutation], now=self.NOW + dt.timedelta(seconds=2)
            )

    def test_corrupt_existing_intake_blocks_new_append(self) -> None:
        self.path.write_text("{not-json}\n", encoding="utf-8")
        with self.assertRaisesRegex(log_sale.IntakeError, "invalid JSON"):
            log_sale.append_record(self.record("after-corrupt-A1"), self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{not-json}\n")

        self.path.write_text("\n", encoding="utf-8")
        with self.assertRaisesRegex(log_sale.IntakeError, "blank JSONL row"):
            log_sale.append_record(self.record("after-blank-A1"), self.path)

        self.path.write_text(
            json.dumps(self.record("no-boundary-A1"), ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(log_sale.IntakeError, "newline commit boundary"):
            log_sale.append_record(self.record("after-no-boundary-A1"), self.path)

    def test_concurrent_duplicate_is_serialized(self) -> None:
        row = self.record("race-A1")
        barrier = threading.Barrier(2)
        results: list[str] = []
        result_lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            try:
                log_sale.append_record(row, self.path, lock_timeout=2)
                result = "completed"
            except log_sale.IntakeError:
                result = "rejected"
            with result_lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(results, ["completed", "completed"])
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)
        self.assertFalse(Path(str(self.path) + ".lock").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
