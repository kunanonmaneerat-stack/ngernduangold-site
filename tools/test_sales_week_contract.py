#!/usr/bin/env python3
"""Focused decision-safety tests for the weekly revenue command."""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

import sales_week


class SalesWeekContractTests(unittest.TestCase):
    def test_unreconciled_is_unavailable_and_exit_two(self) -> None:
        blocked = {
            "trusted": False,
            "reconciliation_state": "UNRECONCILED",
            "error": "invalid metadata contract at line 1",
            "net_revenue_thb": None,
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sales_week.revenue_ledger,
                "read_affiliate_revenue",
                return_value=blocked,
            ) as reader,
            contextlib.redirect_stdout(stdout),
        ):
            code = sales_week.main(["2026-08-13"])
        reader.assert_called_once_with(sales_week.LOG, today=mock.ANY, days=4)
        report = stdout.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("WEEK 2026-08-10..2026-08-13", report)
        self.assertIn("revenue=UNRECONCILED", report)
        self.assertIn("unavailable, not zero", report)
        self.assertNotIn("net_revenue=0", report)

    def test_trusted_lifecycle_is_reported_without_confirmed_fallback(self) -> None:
        trusted = {
            "trusted": True,
            "reconciliation_state": "RECONCILED",
            "source_row_count": 4,
            "ledger_event_rows": 4,
            "ledger_transaction_rows": 3,
            "source_snapshot_sha256": "a" * 64,
            "paid_transactions": 2,
            "refund_transactions": 1,
            "net_revenue_thb": 150,
            "pending_transactions": 3,
            "pending_amount_thb": 120,
            "approved_transactions": 1,
            "approved_amount_thb": 40,
            "lifecycle_counts": {
                "approved": 1,
                "cancelled": 0,
                "paid": 2,
                "pending": 3,
                "refunded": 1,
                "rejected": 0,
            },
            "by_source": {"fb": 100, "threads": 50},
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sales_week.revenue_ledger,
                "read_affiliate_revenue",
                return_value=trusted,
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = sales_week.main(["2026-08-16"])
        report = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("paid=2 refunds=1 net_revenue=150.00 THB", report)
        self.assertIn("pending=3 (120.00 THB)", report)
        self.assertNotIn("confirmed", report)
        self.assertNotIn("UNRECONCILED", report)
        self.assertIn("reconciled events=4 transactions=3", report)

    def test_incomplete_trusted_payload_fails_closed(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sales_week.revenue_ledger,
                "read_affiliate_revenue",
                return_value={"trusted": True, "paid_transactions": 1},
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = sales_week.main(["2026-08-16"])
        self.assertEqual(code, 2)
        self.assertIn("revenue=UNRECONCILED", stdout.getvalue())
        self.assertIn("trusted payload is incomplete", stdout.getvalue())

    def test_mismatched_event_provenance_fails_closed(self) -> None:
        payload = {
            "trusted": True,
            "reconciliation_state": "RECONCILED",
            "source_row_count": 2,
            "ledger_event_rows": 1,
            "ledger_transaction_rows": 1,
            "source_snapshot_sha256": "b" * 64,
            "paid_transactions": 1,
            "refund_transactions": 0,
            "net_revenue_thb": 90,
            "pending_transactions": 0,
            "pending_amount_thb": 0,
            "approved_transactions": 0,
            "approved_amount_thb": 0,
            "lifecycle_counts": {status: int(status == "paid") for status in sales_week.revenue_ledger.ALLOWED_STATUS},
            "by_source": {"direct": 90},
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sales_week.revenue_ledger, "read_affiliate_revenue",
                return_value=payload,
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = sales_week.main(["2026-08-16"])
        self.assertEqual(code, 2)
        self.assertIn("trusted payload is incomplete", stdout.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
