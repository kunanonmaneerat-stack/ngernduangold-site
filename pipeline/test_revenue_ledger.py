#!/usr/bin/env python3
"""Contract tests for the fail-closed affiliate revenue reader."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for support_dir in (ROOT / "pipeline", ROOT / "tools"):
    if str(support_dir) not in sys.path:
        sys.path.insert(0, str(support_dir))

import revenue_ledger as ledger
import import_accesstrade_csv as accesstrade_csv


class RevenueLedgerTests(unittest.TestCase):
    TODAY = dt.date(2026, 8, 16)
    AUTO_EVIDENCE = "__AUTO_SYNTHETIC_UPSTREAM_EVIDENCE__"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sales-log.jsonl"

    def write(self, *rows):
        rows = list(rows)
        if (
            rows and isinstance(rows[0], dict)
            and rows[0].get("upstream_evidence") == self.AUTO_EVIDENCE
        ):
            metadata = dict(rows[0])
            metadata["upstream_evidence"] = self.evidence(metadata, rows[1:])
            rows[0] = metadata
        self.path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def metadata(self, source_row_count, **overrides):
        row = {
            "_meta": "reconciled-source-export",
            "schema_version": 5,
            "fields": sorted(ledger.REQUIRED_SALE_FIELDS),
            "products": {
                "affiliate-commission": None,
                "ebook-59": 59,
            },
            "blocked_products": [],
            "channel_source_values": ["atth", "gumroad"],
            "created": "2026-07-20",
            "updated": "2026-08-16",
            "source_system": "fixture-export",
            "coverage_start": "2026-07-20",
            "coverage_end": "2026-08-16",
            "extracted_at": "2026-08-16T08:00:00+07:00",
            "reconciled_at": "2026-08-16T09:00:00+07:00",
            "source_snapshot_sha256": hashlib.sha256(b"fixture-export").hexdigest(),
            "source_row_count": source_row_count,
            "upstream_evidence": self.AUTO_EVIDENCE,
            "complete": True,
        }
        row.update(overrides)
        return row

    def evidence(self, metadata, events):
        try:
            latest = ledger.log_sale.validate_event_sequence(
                events,
                now=dt.datetime.fromisoformat(metadata["extracted_at"]),
            )
        except Exception:
            latest = {}
        latest_ids = {
            row["event_id"] for row in latest.values()
            if row.get("product") == "affiliate-commission"
        }
        current = [row for row in events if row.get("event_id") in latest_ids]
        historical = [
            row for row in events
            if row.get("product") == "affiliate-commission"
            and row.get("event_id") not in latest_ids
        ]
        coverage_start = metadata["coverage_start"]
        groups = [(current, metadata["coverage_end"])]
        groups.extend(([row], row["date"]) for row in historical)
        bundles = []
        for index, (group, coverage_end) in enumerate(groups):
            bindings = []
            for row in group:
                token = hashlib.sha256(
                    ("provider:" + str(row["sale_id"])).encode("utf-8")
                ).hexdigest()
                bindings.append({
                    "provider_identity_sha256": token,
                    "provider_conversion_id_hash": token,
                    "transaction_id_hash": None,
                    "campaign_id_hash": hashlib.sha256(
                        ("campaign:" + str(row["sale_id"])).encode("utf-8")
                    ).hexdigest(),
                    "source_row_sha256": hashlib.sha256(
                        ("row:" + str(row["event_id"])).encode("utf-8")
                    ).hexdigest(),
                    "event_id": row["event_id"],
                    "sale_id": row["sale_id"],
                    "date": row["date"],
                    "status": row["status"],
                    "gross_amount_thb": row["gross_amount_thb"],
                    "fee_thb": row["fee_thb"],
                    "net_amount_thb": row["net_amount_thb"],
                    "channel_source": row["channel_source"],
                    "ref": row["ref"],
                })
            try:
                reward = sum(
                    (Decimal(str(binding["gross_amount_thb"])) for binding in bindings),
                    Decimal("0.00"),
                )
                reward_text = format(reward, ".2f")
            except Exception:
                # Malformed-money cases must reach the production reader, not fail
                # while this synthetic-only evidence fixture is being assembled.
                bindings = []
                reward_text = "0.00"
            evidence = {
                "schema_version": 1,
                "provider": "accesstrade",
                "format": accesstrade_csv.FORMAT_ID,
                "verification_mode": accesstrade_csv.VERIFICATION_MODE,
                "raw_file_sha256": hashlib.sha256(
                    ("raw:%d" % index).encode("utf-8")
                ).hexdigest(),
                "raw_file_row_count": len(bindings),
                "header_sha256": accesstrade_csv._header_sha256(),
                "browser_evidence_sha256": hashlib.sha256(
                    ("browser:%d" % index).encode("utf-8")
                ).hexdigest(),
                "filter_assertion": {
                    "coverage_start": coverage_start,
                    "coverage_end": coverage_end,
                    "date_basis": accesstrade_csv.DATE_BASIS,
                    "status_filter": "ALL",
                    "campaign_filter": "ALL",
                    "asserted_conversion_count": len(bindings),
                    "asserted_reward_thb": reward_text,
                    "currency": "THB",
                    "timezone": "Asia/Bangkok",
                    "asserted_from": "authenticated_browser_filter_not_csv",
                },
                "extracted_at": metadata["extracted_at"],
                "importer_sha256": accesstrade_csv._importer_sha256(),
                "sub_id_available": False,
                "attribution_state": "UNATTRIBUTED",
                "bindings": bindings,
            }
            receipt = {
                "_meta": "private AccessTrade CSV evidence receipt",
                "evidence": evidence,
                "evidence_sha256": accesstrade_csv.canonical_sha256(evidence),
            }
            canonical_receipt_hash = accesstrade_csv.canonical_sha256(receipt)
            bundles.append({
                "receipt_file_sha256": hashlib.sha256(
                    (canonical_receipt_hash + "\n").encode("ascii")
                ).hexdigest(),
                "receipt_sha256": canonical_receipt_hash,
                "receipt": receipt,
                "canonical_source_sha256": metadata["source_snapshot_sha256"],
                "canonical_source_row_count": metadata["source_row_count"],
            })
        return bundles

    def sale(
        self,
        sale_id,
        *,
        status="paid",
        date="2026-08-15",
        product="affiliate-commission",
        source="atth",
        gross=None,
        fee=None,
        net=None,
        **overrides,
    ):
        if gross is None:
            gross = 0 if status in {"rejected", "cancelled"} else 100
        if fee is None:
            fee = 0 if status in {"rejected", "cancelled"} else 10
        if net is None:
            if status in {"rejected", "cancelled"}:
                net = 0
            elif status == "refunded":
                net = -(gross - fee)
            else:
                net = gross - fee
        row = {
            "event_id": "event-%s-%s" % (sale_id, status),
            "sale_id": sale_id,
            "date": date,
            "product": product,
            "status": status,
            "gross_amount_thb": gross,
            "fee_thb": fee,
            "net_amount_thb": net,
            "channel_source": source,
            "ref": "",
            "note": "",
            "ts": date + "T12:00:00+07:00",
        }
        row.update(overrides)
        return row

    def read(self, *, days=28, now=None):
        options = {"today": self.TODAY, "days": days}
        if now is not None:
            options["now"] = now
        return ledger.read_affiliate_revenue(self.path, **options)

    def test_mixed_lifecycle_keeps_paid_north_star_separate(self):
        rows = [
            self.sale("pending-1", status="pending", source="atth"),
            self.sale("approved-1", status="approved", source="atth", gross=80, fee=5),
            self.sale("paid-1", status="paid", source="atth", gross=120, fee=20),
            self.sale("rejected-1", status="rejected", source="atth"),
            self.sale("refunded-1", status="paid", source="atth", gross=50, fee=5),
            self.sale(
                "refunded-1", status="refunded", source="atth", gross=50, fee=5,
                ts="2026-08-15T12:00:01+07:00",
            ),
            self.sale("cancelled-1", status="cancelled", source="atth"),
        ]
        self.write(self.metadata(len(rows)), *rows)

        result = self.read()

        self.assertTrue(result["trusted"])
        self.assertTrue(result["learning_ready"])
        self.assertFalse(result["reconcile_required"])
        self.assertEqual(result["quality_state"], "CURRENT")
        self.assertEqual(result["next_action"], "NONE")
        self.assertEqual(
            ledger.learning_contract_errors(result, expected_end=self.TODAY), []
        )
        self.assertEqual(result["reconciliation_state"], "RECONCILED")
        self.assertEqual(result["source_row_count"], 7)
        self.assertEqual(
            result["source_snapshot_sha256"],
            self.metadata(0)["source_snapshot_sha256"],
        )
        self.assertEqual(result["ledger_event_rows"], 7)
        self.assertEqual(result["ledger_transaction_rows"], 6)
        self.assertEqual(result["affiliate_window_transactions"], 6)
        self.assertEqual(result["lifecycle_counts"], {
            "approved": 1,
            "cancelled": 1,
            "paid": 1,
            "pending": 1,
            "refunded": 1,
            "rejected": 1,
        })
        self.assertEqual(result["paid_transactions"], 1)
        self.assertEqual(result["verified_transactions"], 1)
        self.assertEqual(result["confirmed_transactions"], 1)
        self.assertEqual(result["pending_transactions"], 1)
        self.assertEqual(result["approved_transactions"], 1)
        self.assertEqual(result["rejected_transactions"], 1)
        self.assertEqual(result["refund_transactions"], 1)
        self.assertEqual(result["cancelled_transactions"], 1)
        self.assertEqual(result["paid_revenue_thb"], 100.0)
        self.assertEqual(result["verified_revenue_thb"], 100.0)
        self.assertEqual(result["pending_amount_thb"], 90.0)
        self.assertEqual(result["approved_amount_thb"], 75.0)
        self.assertEqual(result["refund_amount_thb"], 45.0)
        self.assertEqual(result["net_revenue_thb"], 100.0)
        self.assertEqual(result["by_source"], {"atth": 100.0})
        self.assertEqual(result["pending_by_source"], {"atth": 90.0})
        self.assertEqual(result["approved_by_source"], {"atth": 75.0})
        self.assertEqual(result["attribution_state"], "UNATTRIBUTED")
        self.assertEqual(result["attribution_scope"], "MERCHANT_TOTAL_ONLY")
        self.assertFalse(result["sub_id_available"])
        self.assertFalse(result["page_cta_attribution_ready"])
        self.assertEqual(result["verified_revenue_statuses"], ["paid"])
        self.assertFalse(result["pending_is_verified_revenue"])
        self.assertEqual(result["trust_expires_at"], "2026-08-17T00:00:00+07:00")
        self.assertEqual(result["latest_paid_date"], "2026-08-15")
        facts = result["affiliate_window_transaction_facts"]
        self.assertEqual(len(facts), 6)
        self.assertEqual(
            set(facts[0]), set(ledger.AFFILIATE_TRANSACTION_FACT_FIELDS)
        )
        self.assertTrue(all(
            "sale_id" not in fact and "event_id" not in fact
            and "ref" not in fact and "note" not in fact and "ts" not in fact
            for fact in facts
        ))
        self.assertEqual(facts, sorted(facts, key=ledger._fact_sort_key))
        json.dumps(result)  # Decimal values must not leak across the API boundary.

    def test_non_affiliate_row_reconciles_but_does_not_enter_metrics(self):
        self.write(
            self.metadata(1),
            self.sale("ebook-1", product="ebook-59", source="gumroad",
                      gross=59, fee=0, net=59),
        )

        result = self.read()

        self.assertTrue(result["trusted"])
        self.assertEqual(result["source_row_count"], 1)
        self.assertEqual(result["ledger_transaction_rows"], 1)
        self.assertEqual(result["paid_transactions"], 0)
        self.assertEqual(result["net_revenue_thb"], 0.0)
        self.assertEqual(result["lifecycle_counts"], {
            "approved": 0,
            "cancelled": 0,
            "paid": 0,
            "pending": 0,
            "refunded": 0,
            "rejected": 0,
        })

    def test_row_outside_requested_window_still_reconciles_source_count(self):
        self.write(
            self.metadata(1, coverage_start="2026-07-01", created="2026-07-01"),
            self.sale("old-1", date="2026-07-05"),
        )

        result = self.read()

        self.assertTrue(result["trusted"])
        self.assertEqual(result["source_row_count"], 1)
        self.assertEqual(result["paid_transactions"], 0)
        self.assertEqual(result["net_revenue_thb"], 0.0)

    def test_reconciled_zero_export_is_trusted_zero(self):
        self.write(self.metadata(0))

        result = self.read()

        self.assertTrue(result["trusted"])
        self.assertEqual(result["reconciliation_state"], "RECONCILED")
        self.assertEqual(result["source_row_count"], 0)
        self.assertEqual(result["ledger_event_rows"], 0)
        self.assertEqual(result["ledger_transaction_rows"], 0)
        self.assertEqual(result["affiliate_window_transactions"], 0)
        self.assertEqual(result["paid_transactions"], 0)
        self.assertEqual(result["confirmed_transactions"], 0)
        self.assertEqual(result["pending_transactions"], 0)
        self.assertEqual(result["approved_transactions"], 0)
        self.assertEqual(result["net_revenue_thb"], 0.0)
        self.assertTrue(all(value == 0 for value in result["lifecycle_counts"].values()))

    def test_source_row_count_mismatch_fails_closed(self):
        cases = [
            (1, []),
            (0, [self.sale("unexpected-1")]),
            (2, [self.sale("missing-1")]),
        ]
        for source_count, rows in cases:
            with self.subTest(source_count=source_count, actual=len(rows)):
                self.write(self.metadata(source_count), *rows)
                result = self.read()
                self.assertFalse(result["trusted"])
                self.assertEqual(result["reconciliation_state"], "UNRECONCILED")
                self.assertEqual(result["source_row_count"], source_count)
                self.assertEqual(result["ledger_event_rows"], len(rows))
                self.assertEqual(result["ledger_transaction_rows"], len(rows))
                self.assertIsNone(result["net_revenue_thb"])
                self.assertIn("source_row_count", result["error"])
                self.assertEqual(result["quality_state"], "ROW_COUNT_MISMATCH")
                self.assertTrue(result["reconcile_required"])

    def test_schema_four_metadata_remains_unreconciled(self):
        old = self.metadata(0)
        old["schema_version"] = 4
        self.write(old)

        result = self.read()

        self.assertFalse(result["trusted"])
        self.assertEqual(result["reconciliation_state"], "UNRECONCILED")
        self.assertIsNone(result["paid_transactions"])
        self.assertIsNone(result["net_revenue_thb"])
        self.assertIn("invalid metadata contract", result["error"])

    def test_legacy_confirmed_status_is_not_silently_treated_as_paid(self):
        self.write(self.metadata(1), self.sale("legacy-1", status="confirmed"))

        result = self.read()

        self.assertFalse(result["trusted"])
        self.assertIsNone(result["confirmed_transactions"])
        self.assertIn("invalid status", result["error"])

    def test_invalid_lifecycle_money_contracts_fail_closed(self):
        invalid_rows = [
            self.sale("pending-negative", status="pending", gross=-1, fee=0, net=-1),
            self.sale("approved-mismatch", status="approved", gross=100, fee=10, net=100),
            self.sale("paid-negative", status="paid", gross=100, fee=10, net=-90),
            self.sale("refund-positive", status="refunded", gross=100, fee=10, net=90),
            self.sale("rejected-nonzero", status="rejected", gross=100, fee=0, net=0),
            self.sale("cancelled-nonzero", status="cancelled", gross=0, fee=0, net=1),
            self.sale("fee-over-gross", gross=10, fee=11, net=-1),
            self.sale("too-precise", gross="10.001", fee=0, net="10.001"),
            self.sale("bool-money", gross=True, fee=0, net=1),
            self.sale("nan-money", gross="NaN", fee=0, net=0),
            self.sale("infinite-money", gross="Infinity", fee=0, net=0),
            self.sale("huge-exponent", gross="1e1000000", fee=0, net="1e1000000"),
        ]
        for row in invalid_rows:
            with self.subTest(sale_id=row["sale_id"]):
                self.write(self.metadata(1), row)
                result = self.read()
                self.assertFalse(result["trusted"])
                self.assertEqual(result["reconciliation_state"], "UNRECONCILED")
                self.assertIsNone(result["net_revenue_thb"])
                self.assertIsNotNone(result["error"])

    def test_append_only_lifecycle_is_reduced_to_one_latest_state(self):
        events = [
            self.sale("life-1", status="pending"),
            self.sale(
                "life-1", status="approved",
                ts="2026-08-15T12:00:01+07:00",
            ),
            self.sale(
                "life-1", status="paid",
                ts="2026-08-15T12:00:02+07:00",
            ),
        ]
        self.write(self.metadata(3), *events)
        result = self.read()
        self.assertTrue(result["trusted"])
        self.assertEqual(result["ledger_event_rows"], 3)
        self.assertEqual(result["ledger_transaction_rows"], 1)
        self.assertEqual(result["lifecycle_counts"]["paid"], 1)
        self.assertEqual(result["lifecycle_counts"]["pending"], 0)
        self.assertEqual(result["paid_revenue_thb"], 90.0)

    def test_backward_duplicate_terminal_and_nonmonotonic_events_fail_closed(self):
        cases = [
            [
                self.sale("back-1", status="paid"),
                self.sale("back-1", status="approved", ts="2026-08-15T12:00:01+07:00"),
            ],
            [
                self.sale("repeat-1", status="pending"),
                self.sale(
                    "repeat-1", status="pending", event_id="repeat-second",
                    ts="2026-08-15T12:00:01+07:00",
                ),
            ],
            [
                self.sale("terminal-1", status="rejected"),
                self.sale("terminal-1", status="paid", ts="2026-08-15T12:00:01+07:00"),
            ],
            [
                self.sale("time-1", status="pending"),
                self.sale("time-1", status="approved"),
            ],
        ]
        for events in cases:
            with self.subTest(sale_id=events[0]["sale_id"]):
                self.write(self.metadata(len(events)), *events)
                result = self.read()
                self.assertFalse(result["trusted"])
                self.assertIn("lifecycle", result["error"])

    def test_missing_malformed_duplicate_and_field_drift_fail_closed(self):
        missing = ledger.read_affiliate_revenue(
            Path(self.tmp.name) / "missing.jsonl", today=self.TODAY
        )
        self.assertFalse(missing["trusted"])
        self.assertIn("missing", missing["error"])

        self.path.write_text("{not-json}\n", encoding="utf-8")
        self.assertIn("invalid JSON", self.read()["error"])

        duplicate = self.sale("duplicate-1")
        self.write(self.metadata(2), duplicate, duplicate)
        self.assertIn("duplicate event_id", self.read()["error"])

        drift = self.sale("drift-1")
        drift["unexpected"] = "field"
        self.write(self.metadata(1), drift)
        self.assertIn("fields do not match", self.read()["error"])

    def test_blank_row_and_missing_commit_newline_fail_closed(self):
        metadata_row = self.metadata(0)
        metadata_row["upstream_evidence"] = self.evidence(metadata_row, [])
        metadata = json.dumps(metadata_row, ensure_ascii=False)
        self.path.write_text(metadata + "\n\n", encoding="utf-8")
        blank = self.read()
        self.assertFalse(blank["trusted"])
        self.assertIn("blank JSONL row", blank["error"])

        self.path.write_text(metadata, encoding="utf-8")
        incomplete = self.read()
        self.assertFalse(incomplete["trusted"])
        self.assertIn("newline commit boundary", incomplete["error"])

    def test_noncanonical_identity_timestamp_and_fixed_price_fail_closed(self):
        cases = [
            self.sale("bad ts", ts="not-a-time"),
            self.sale("pii-1", note="buyer@example.com"),
            self.sale("ebook-wrong", product="ebook-59", source="gumroad",
                      gross=100, fee=0, net=100),
            self.sale("after-export", ts="2026-08-16T08:01:00+07:00"),
        ]
        for row in cases:
            with self.subTest(sale_id=row["sale_id"]):
                self.write(self.metadata(1), row)
                result = self.read()
                self.assertFalse(result["trusted"])
                self.assertIsNone(result["net_revenue_thb"])
                self.assertIsNotNone(result["error"])

    def test_invalid_metadata_contracts_fail_closed(self):
        cases = []
        incomplete = self.metadata(0, complete=False)
        cases.append(incomplete)
        bad_hash = self.metadata(0, source_snapshot_sha256="not-a-hash")
        cases.append(bad_hash)
        duplicate_source = self.metadata(
            0, channel_source_values=["fb", "fb"]
        )
        cases.append(duplicate_source)
        bool_count = self.metadata(True)
        cases.append(bool_count)
        naive_time = self.metadata(0, reconciled_at="2026-08-16T09:00:00")
        cases.append(naive_time)
        for index, metadata in enumerate(cases):
            with self.subTest(index=index):
                self.write(metadata)
                result = self.read()
                self.assertFalse(result["trusted"])
                self.assertEqual(result["reconciliation_state"], "UNRECONCILED")
                self.assertIsNone(result["net_revenue_thb"])

    def test_jsonl_rejects_duplicate_keys_and_nonfinite_numbers(self):
        event = self.sale("strict-json")
        self.write(self.metadata(1), event)
        baseline = self.path.read_text(encoding="utf-8")
        self.assertTrue(self.read()["trusted"])

        duplicate = baseline.replace(
            '"schema_version": 5',
            '"schema_version": 999, "schema_version": 5',
            1,
        )
        self.path.write_text(duplicate, encoding="utf-8")
        result = self.read()
        self.assertFalse(result["trusted"])
        self.assertEqual(result["quality_state"], "INVALID_LEDGER")
        self.assertEqual(result["error"], "invalid JSON at line 1")

        metadata = self.metadata(1)
        metadata["products"]["affiliate-commission"] = float("nan")
        self.write(metadata, event)
        result = self.read()
        self.assertFalse(result["trusted"])
        self.assertEqual(result["quality_state"], "INVALID_LEDGER")
        self.assertEqual(result["error"], "invalid JSON at line 1")

        self.path.write_text(
            baseline.replace('"ebook-59": 59', '"ebook-59": Infinity', 1),
            encoding="utf-8",
        )
        result = self.read()
        self.assertFalse(result["trusted"])
        self.assertEqual(result["quality_state"], "INVALID_LEDGER")
        self.assertEqual(result["error"], "invalid JSON at line 1")

        self.path.write_text(
            baseline.replace('"ebook-59": 59', '"ebook-59": 1e999', 1),
            encoding="utf-8",
        )
        result = self.read()
        self.assertFalse(result["trusted"])
        self.assertEqual(result["quality_state"], "INVALID_LEDGER")
        self.assertEqual(result["error"], "invalid JSON at line 1")

    def test_boolean_days_is_not_a_valid_revenue_window(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            self.read(days=True)

    def test_short_coverage_unknown_domains_and_out_of_coverage_rows_fail(self):
        self.write(self.metadata(0, coverage_start="2026-07-21"))
        result = self.read()
        self.assertFalse(result["trusted"])
        self.assertEqual(result["quality_state"], "INCOMPLETE_COVERAGE")
        self.assertIn("starts after", result["error"])

        self.write(self.metadata(1), self.sale("unknown-source", source="email"))
        self.assertIn("unknown channel_source", self.read()["error"])

        self.write(self.metadata(1), self.sale("unknown-product", product="course"))
        self.assertIn("unknown product", self.read()["error"])

        self.write(
            self.metadata(1),
            self.sale("outside-coverage", date="2026-07-19"),
        )
        self.assertIn("outside reconciled coverage", self.read()["error"])

    def test_stale_future_and_future_timestamp_snapshots_require_reconciliation(self):
        self.write(
            self.metadata(1, coverage_end="2026-08-15"),
            self.sale("stale-1"),
        )
        stale = self.read()
        self.assertFalse(stale["trusted"])
        self.assertEqual(stale["quality_state"], "STALE_COVERAGE")
        self.assertEqual(stale["next_action"], "RECONCILE_REVENUE")

        self.write(self.metadata(
            0,
            coverage_end="2026-08-17",
            updated="2026-08-17",
            extracted_at="2026-08-17T08:00:00+07:00",
            reconciled_at="2026-08-17T09:00:00+07:00",
        ))
        future_coverage = self.read(
            now=dt.datetime(2026, 8, 18, 12, tzinfo=ledger.BANGKOK)
        )
        self.assertEqual(future_coverage["quality_state"], "FUTURE_COVERAGE")

        self.write(self.metadata(
            0,
            extracted_at="2026-08-16T20:00:00+07:00",
            reconciled_at="2026-08-16T20:01:00+07:00",
        ))
        future_time = self.read(
            now=dt.datetime(2026, 8, 16, 19, tzinfo=ledger.BANGKOK)
        )
        self.assertEqual(future_time["quality_state"], "FUTURE_RECONCILIATION")

    def test_learning_contract_rejects_trusted_flag_nan_and_incomplete_provenance(self):
        self.write(self.metadata(0))
        valid = self.read()
        self.assertEqual(ledger.learning_contract_errors(valid, expected_end=self.TODAY), [])

        before_expiry = dt.datetime(2026, 8, 16, 23, 59, 59,
                                    tzinfo=ledger.BANGKOK)
        self.assertEqual(
            ledger.learning_contract_errors(
                valid, expected_end=self.TODAY, observed_at=before_expiry
            ),
            [],
        )
        at_expiry = dt.datetime(2026, 8, 17, 0, 0,
                                tzinfo=ledger.BANGKOK)
        expired_errors = ledger.learning_contract_errors(
            valid, expected_end=self.TODAY, observed_at=at_expiry
        )
        self.assertIn(
            "revenue trust has expired at the observation time", expired_errors
        )

        nan_payload = {**valid, "net_revenue_thb": float("nan")}
        errors = ledger.learning_contract_errors(nan_payload, expected_end=self.TODAY)
        self.assertTrue(any("net_revenue_thb" in error for error in errors))

        forged = {
            "trusted": True,
            "reconciliation_state": "RECONCILED",
            "quality_state": "CURRENT",
            "learning_ready": True,
            "reconcile_required": False,
            "next_action": "NONE",
            "error": None,
        }
        self.assertTrue(ledger.learning_contract_errors(forged, expected_end=self.TODAY))

        forged_attribution = {
            **valid,
            "attribution_state": "ATTRIBUTED",
            "attribution_scope": "PAGE_CTA",
            "sub_id_available": True,
            "page_cta_attribution_ready": True,
            "by_source": {"facebook-page-post": 0.0},
        }
        errors = ledger.learning_contract_errors(
            forged_attribution, expected_end=self.TODAY
        )
        self.assertTrue(any("merchant-total-only" in error for error in errors))
        self.assertTrue(any("by source" in error for error in errors))

        forged_pending_revenue = {
            **valid,
            "verified_revenue_statuses": ["paid", "pending"],
            "pending_is_verified_revenue": True,
            "verified_transactions": valid["paid_transactions"] + 1,
            "verified_revenue_thb": valid["paid_revenue_thb"] + 35,
        }
        errors = ledger.learning_contract_errors(
            forged_pending_revenue, expected_end=self.TODAY
        )
        self.assertTrue(any("pending is excluded" in error for error in errors))
        self.assertTrue(any("verified transactions" in error for error in errors))
        self.assertTrue(any("verified revenue" in error for error in errors))

    def test_learning_contract_rejects_zeroed_paid_window_payload(self):
        self.write(
            self.metadata(1),
            self.sale("paid-window-1", status="paid", gross=100, fee=10, net=90),
        )
        valid = self.read()
        self.assertEqual(valid["affiliate_window_transactions"], 1)
        self.assertEqual(
            ledger.learning_contract_errors(valid, expected_end=self.TODAY), []
        )

        zeroed = {
            **valid,
            "verified_transactions": 0,
            "paid_transactions": 0,
            "confirmed_transactions": 0,
            "paid_revenue_thb": 0.0,
            "verified_revenue_thb": 0.0,
            "net_revenue_thb": 0.0,
            "by_source": {},
            "lifecycle_counts": {
                status: 0 for status in ledger.ALLOWED_STATUS
            },
        }
        errors = ledger.learning_contract_errors(
            zeroed, expected_end=self.TODAY
        )
        self.assertIn(
            "affiliate window transactions do not reconcile to lifecycle counts",
            errors,
        )

        self_consistent_zero = {
            **zeroed,
            "affiliate_window_transactions": 0,
            "latest_transaction_date": None,
            "latest_paid_date": None,
        }
        errors = ledger.learning_contract_errors(
            self_consistent_zero, expected_end=self.TODAY
        )
        self.assertTrue(any(
            "does not reconcile to transaction facts" in error
            for error in errors
        ))

        date_tamper = {
            **valid,
            "latest_transaction_date": None,
            "latest_paid_date": None,
        }
        errors = ledger.learning_contract_errors(
            date_tamper, expected_end=self.TODAY
        )
        self.assertIn(
            "latest_transaction_date does not reconcile to transaction facts",
            errors,
        )
        self.assertIn(
            "latest_paid_date does not reconcile to transaction facts", errors
        )

    def test_learning_contract_reconciles_provenance_counts_and_timestamps(self):
        self.write(
            self.metadata(1),
            self.sale("provenance-window-1", status="paid", gross=100, fee=10, net=90),
        )
        valid = self.read()
        self.assertEqual(
            ledger.learning_contract_errors(valid, expected_end=self.TODAY), []
        )

        bound_tamper = {**valid, "upstream_bound_event_rows": 0}
        self.assertIn(
            "upstream bound event rows do not equal ledger event rows",
            ledger.learning_contract_errors(bound_tamper, expected_end=self.TODAY),
        )

        impossible_window = {
            **valid,
            "affiliate_window_transactions": valid["ledger_transaction_rows"] + 1,
        }
        self.assertIn(
            "affiliate window transactions exceed ledger transaction rows",
            ledger.learning_contract_errors(impossible_window, expected_end=self.TODAY),
        )

        naive = {**valid, "extracted_at": "2026-08-16T08:00:00"}
        self.assertIn(
            "revenue extraction or reconciliation timestamp is invalid",
            ledger.learning_contract_errors(naive, expected_end=self.TODAY),
        )

        reversed_times = {
            **valid,
            "extracted_at": "2026-08-16T10:00:00+07:00",
            "reconciled_at": "2026-08-16T09:00:00+07:00",
        }
        self.assertIn(
            "revenue reconciliation timestamp precedes extraction",
            ledger.learning_contract_errors(reversed_times, expected_end=self.TODAY),
        )

        before_coverage = {
            **valid,
            "extracted_at": "2026-08-15T08:00:00+07:00",
            "reconciled_at": "2026-08-15T09:00:00+07:00",
        }
        self.assertIn(
            "revenue reconciliation timestamp precedes coverage end",
            ledger.learning_contract_errors(before_coverage, expected_end=self.TODAY),
        )

    def test_learning_contract_rejects_future_provenance_after_observation(self):
        self.write(self.metadata(0))
        valid = self.read()
        decision_time = dt.datetime(2026, 8, 16, 19, tzinfo=ledger.BANGKOK)
        self.assertEqual(
            ledger.learning_contract_errors(
                valid, expected_end=self.TODAY, observed_at=decision_time
            ),
            [],
        )

        after_observation = {
            **valid,
            "extracted_at": "2026-08-16T19:30:00+07:00",
            "reconciled_at": "2026-08-16T19:31:00+07:00",
        }
        errors = ledger.learning_contract_errors(
            after_observation, expected_end=self.TODAY,
            observed_at=decision_time,
        )
        self.assertIn("revenue extraction timestamp is after the observation", errors)
        self.assertIn("revenue reconciliation timestamp is after the observation", errors)

        far_future = {
            **valid,
            "extracted_at": "2099-01-01T00:00:00+07:00",
            "reconciled_at": "2099-01-01T00:00:01+07:00",
        }
        errors = ledger.learning_contract_errors(
            far_future, expected_end=self.TODAY
        )
        self.assertIn("revenue extraction timestamp is outside the trust window", errors)
        self.assertIn("revenue reconciliation timestamp is outside the trust window", errors)

    def test_upstream_receipt_hash_scope_summary_and_attribution_tampering_fail_closed(self):
        event = self.sale("evidence-1", status="pending")
        metadata = self.metadata(1)
        metadata["upstream_evidence"] = self.evidence(metadata, [event])

        def recompute_receipt(bundle):
            receipt = bundle["receipt"]
            receipt["evidence_sha256"] = accesstrade_csv.canonical_sha256(
                receipt["evidence"]
            )
            bundle["receipt_sha256"] = accesstrade_csv.canonical_sha256(receipt)

        cases = []

        stale_outer_hash = copy.deepcopy(metadata)
        stale_outer_hash["upstream_evidence"][0]["receipt"]["evidence"][
            "filter_assertion"
        ]["asserted_reward_thb"] = "99.00"
        stale_outer_hash["upstream_evidence"][0]["receipt"]["evidence_sha256"] = (
            accesstrade_csv.canonical_sha256(
                stale_outer_hash["upstream_evidence"][0]["receipt"]["evidence"]
            )
        )
        cases.append((stale_outer_hash, "embedded receipt hash"))

        partial = copy.deepcopy(metadata)
        partial_bundle = partial["upstream_evidence"][0]
        partial_bundle["receipt"]["evidence"]["filter_assertion"][
            "status_filter"
        ] = "PENDING"
        recompute_receipt(partial_bundle)
        cases.append((partial, "partial AccessTrade status filter"))

        wrong_summary = copy.deepcopy(metadata)
        summary_bundle = wrong_summary["upstream_evidence"][0]
        summary_bundle["receipt"]["evidence"]["filter_assertion"][
            "asserted_reward_thb"
        ] = "99.00"
        recompute_receipt(summary_bundle)
        cases.append((wrong_summary, "reward summary"))

        inferred_source = copy.deepcopy(metadata)
        source_bundle = inferred_source["upstream_evidence"][0]
        source_bundle["receipt"]["evidence"]["bindings"][0][
            "channel_source"
        ] = "fb"
        recompute_receipt(source_bundle)
        cases.append((inferred_source, "source atth"))

        source_hash_drift = copy.deepcopy(metadata)
        source_hash_drift["upstream_evidence"][0]["canonical_source_sha256"] = "0" * 64
        cases.append((source_hash_drift, "canonical source"))

        for broken_metadata, expected in cases:
            with self.subTest(expected=expected):
                self.write(broken_metadata, event)
                result = self.read()
                self.assertFalse(result["trusted"])
                self.assertEqual(result["quality_state"], "INVALID_LEDGER")
                self.assertIn(expected, result["error"])

    def test_provider_identity_cannot_change_across_sale_lifecycle_receipts(self):
        events = [
            self.sale("provider-life", status="pending"),
            self.sale(
                "provider-life", status="approved",
                ts="2026-08-15T12:00:01+07:00",
            ),
        ]
        metadata = self.metadata(2)
        metadata["upstream_evidence"] = self.evidence(metadata, events)
        historical_bundle = metadata["upstream_evidence"][1]
        binding = historical_bundle["receipt"]["evidence"]["bindings"][0]
        binding["provider_identity_sha256"] = "1" * 64
        binding["provider_conversion_id_hash"] = "2" * 64
        binding["transaction_id_hash"] = "3" * 64
        binding["campaign_id_hash"] = "4" * 64
        receipt = historical_bundle["receipt"]
        receipt["evidence_sha256"] = accesstrade_csv.canonical_sha256(receipt["evidence"])
        historical_bundle["receipt_sha256"] = accesstrade_csv.canonical_sha256(receipt)

        self.write(metadata, *events)
        result = self.read()
        self.assertFalse(result["trusted"])
        self.assertIn("provider identity changed across lifecycle", result["error"])


if __name__ == "__main__":
    unittest.main()
