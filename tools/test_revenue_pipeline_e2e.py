#!/usr/bin/env python3
"""End-to-end tests for intake -> frozen export -> schema-5 revenue."""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import log_sale
import import_accesstrade_csv as accesstrade_csv
import reconcile_sales
import revenue_ledger
import sales_week


class RevenuePipelineEndToEndTests(unittest.TestCase):
    END = dt.date(2026, 8, 16)
    NOW = dt.datetime(2026, 8, 16, 13, 0, tzinfo=log_sale.BANGKOK)
    EXTRACTED = dt.datetime(2026, 8, 16, 12, 30, tzinfo=log_sale.BANGKOK)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.intake = root / "sales-intake.jsonl"
        self.frozen = root / "owner-export-frozen.jsonl"
        self.output = root / "sales-log.jsonl"

    def row(
        self, sale_id: str, status: str, gross: int, fee: int, source: str,
        *, event_id: str | None = None, second: int = 0,
    ) -> dict:
        return log_sale.make_record(
            event_id=event_id or ("event-%s-%s" % (sale_id, status)),
            sale_id=sale_id,
            product="affiliate-commission",
            amount=gross,
            fee=fee,
            status=status,
            source=source,
            date="2026-08-15",
            now=dt.datetime(2026, 8, 15, 12, 0, second, tzinfo=log_sale.BANGKOK),
        )

    def reconcile(self, source: Path | None = None, output: Path | None = None, **kwargs: object) -> dict:
        selected_source = source or self.frozen
        rows = [json.loads(line) for line in selected_source.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        evidence_paths, evidence_hashes, raw_paths, browser_paths = self.evidence_receipts(rows)
        options = {
            "source_system": "owner-frozen-export",
            "coverage_start": "2026-07-20",
            "coverage_end": self.END,
            "extracted_at": self.EXTRACTED,
            "expected_sha256": hashlib.sha256(selected_source.read_bytes()).hexdigest(),
            "expected_row_count": sum(
                1 for line in selected_source.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ),
            "upstream_evidence_path": evidence_paths,
            "expected_upstream_evidence_sha256": evidence_hashes,
            "upstream_raw_csv_path": raw_paths,
            "upstream_browser_evidence_path": browser_paths,
            "now": self.NOW,
        }
        options.update(kwargs)
        with mock.patch.object(accesstrade_csv, "PRIVATE_ROOT", self.output.parent):
            return reconcile_sales.reconcile(
                selected_source,
                output or self.output,
                **options,
            )

    def evidence_receipts(
        self, rows: list[dict]
    ) -> tuple[list[Path], list[str], list[Path], list[Path]]:
        latest = log_sale.validate_event_sequence(rows, now=self.EXTRACTED)
        current_ids = {row["event_id"] for row in latest.values()
                       if row["product"] == "affiliate-commission"}
        current = [row for row in rows if row.get("event_id") in current_ids]
        historical = [row for row in rows
                      if row.get("product") == "affiliate-commission"
                      and row.get("event_id") not in current_ids]
        groups = [(current, self.END)]
        groups.extend(([row], dt.date.fromisoformat(row["date"])) for row in historical)
        paths: list[Path] = []
        hashes: list[str] = []
        raw_paths: list[Path] = []
        browser_paths: list[Path] = []
        for index, (group, coverage_end) in enumerate(groups):
            raw_path = self.output.parent / ("raw-%d.csv" % index)
            raw_values = []
            bindings = []
            for row in group:
                values = {name: "" for name in accesstrade_csv.CSV_HEADERS}
                values.update({
                    accesstrade_csv.CLICK_AT: row["date"] + " 11:59:00",
                    accesstrade_csv.CONVERSION_AT: row["date"] + " 12:00:00",
                    accesstrade_csv.CAMPAIGN_ID: "campaign-" + row["sale_id"],
                    "Conversion ID": "conversion-" + row["sale_id"],
                    "Transaction ID": "transaction-" + row["sale_id"],
                    accesstrade_csv.REWARD: "%.2f" % float(row["gross_amount_thb"]),
                    accesstrade_csv.STATUS: row["status"].upper(),
                })
                raw_values.append([values[name] for name in accesstrade_csv.CSV_HEADERS])
                bindings.append(accesstrade_csv._binding_for_row(
                    values,
                    sale_id=row["sale_id"], event_id=row["event_id"],
                    channel_source=row["channel_source"], ledger_ref=row["ref"],
                    fee=str(row["fee_thb"]),
                    coverage_start=dt.date(2026, 7, 20), coverage_end=coverage_end,
                    extracted_at=dt.datetime.combine(
                        coverage_end, dt.time(12, 30), tzinfo=log_sale.BANGKOK
                    ),
                ))
            with raw_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\r\n")
                writer.writerow(accesstrade_csv.CSV_HEADERS)
                writer.writerows(raw_values)
            extracted = dt.datetime.combine(
                coverage_end, dt.time(12, 30), tzinfo=log_sale.BANGKOK
            )
            browser_path = self.output.parent / ("browser-%d.json" % index)
            reward = sum(float(binding["gross_amount_thb"]) for binding in bindings)
            browser_payload = {
                "schema_version": accesstrade_csv.BROWSER_EVIDENCE_SCHEMA_VERSION,
                "provider": "AccessTrade",
                "verified_at": extracted.isoformat(timespec="seconds"),
                "verification_mode": accesstrade_csv.VERIFICATION_MODE,
                "report_url": accesstrade_csv.REPORT_URL,
                "filters": {
                    "period_start": "2026-07-20",
                    "period_end": coverage_end.isoformat(),
                    "date_basis": accesstrade_csv.DATE_BASIS,
                    "status": "all",
                    "campaign": "all",
                },
                "observed": {
                    "campaign": "synthetic-all-campaigns",
                    "conversion_count": len(bindings),
                    "total_reward_thb": reward,
                    "currency": "THB",
                    "provider_conversion_id_available": bool(bindings),
                    "transaction_id_available": bool(bindings),
                    "sub_id_available": False,
                },
                "ledger_bindings": [
                    {
                        "event_id": binding["event_id"],
                        "sale_id": binding["sale_id"],
                        "status": binding["status"],
                        "amount_thb": binding["gross_amount_thb"],
                    }
                    for binding in bindings
                ],
                "external_mutation": False,
                "financial_action": False,
                "note": "synthetic test evidence only",
            }
            browser_path.write_text(
                json.dumps(browser_payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            evidence = {
                "schema_version": 1, "provider": "accesstrade",
                "format": accesstrade_csv.FORMAT_ID,
                "verification_mode": accesstrade_csv.VERIFICATION_MODE,
                "raw_file_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "raw_file_row_count": len(bindings),
                "header_sha256": accesstrade_csv._header_sha256(),
                "browser_evidence_sha256": hashlib.sha256(browser_path.read_bytes()).hexdigest(),
                "filter_assertion": {
                    "coverage_start": "2026-07-20",
                    "coverage_end": coverage_end.isoformat(),
                    "date_basis": accesstrade_csv.DATE_BASIS,
                    "status_filter": "ALL",
                    "campaign_filter": "ALL",
                    "asserted_conversion_count": len(bindings),
                    "asserted_reward_thb": "%.2f" % sum(
                        float(binding["gross_amount_thb"]) for binding in bindings
                    ),
                    "currency": "THB",
                    "timezone": "Asia/Bangkok",
                    "asserted_from": "authenticated_browser_filter_not_csv",
                },
                "extracted_at": extracted.isoformat(timespec="seconds"),
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
            path = self.output.parent / ("evidence-%d.json" % index)
            path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
                            encoding="utf-8")
            paths.append(path)
            hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
            raw_paths.append(raw_path)
            browser_paths.append(browser_path)
        return paths, hashes, raw_paths, browser_paths

    def test_intake_reconcile_strict_reader_and_weekly_report_agree(self) -> None:
        rows = [
            self.row("paid-A1", "paid", 100, 10, "atth"),
            self.row("refund-A1", "paid", 20, 0, "atth"),
            self.row("refund-A1", "refunded", 20, 0, "atth", second=1),
            self.row("pending-A1", "pending", 50, 5, "atth"),
            self.row("approved-A1", "approved", 70, 7, "atth"),
            self.row("rejected-A1", "rejected", 0, 0, "atth"),
            self.row("cancelled-A1", "cancelled", 0, 0, "atth"),
        ]
        for row in rows:
            log_sale.append_record(row, self.intake)
        shutil.copyfile(self.intake, self.frozen)
        source_hash = hashlib.sha256(self.frozen.read_bytes()).hexdigest()

        installed = self.reconcile()

        self.assertTrue(installed["trusted"])
        self.assertEqual(installed["schema_version"], 5)
        self.assertEqual(installed["source_snapshot_sha256"], source_hash)
        self.assertEqual(installed["source_row_count"], len(rows))
        metadata = json.loads(self.output.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(metadata["source_snapshot_sha256"], source_hash)
        self.assertEqual(metadata["source_row_count"], len(rows))
        self.assertTrue(metadata["complete"])
        self.assertTrue(metadata["upstream_evidence"])

        strict = revenue_ledger.read_affiliate_revenue(
            self.output,
            today=self.END,
            days=28,
        )
        self.assertTrue(strict["trusted"])
        self.assertEqual(strict["paid_transactions"], 1)
        self.assertEqual(strict["refund_transactions"], 1)
        self.assertEqual(strict["pending_transactions"], 1)
        self.assertEqual(strict["approved_transactions"], 1)
        self.assertEqual(strict["paid_revenue_thb"], 90)
        self.assertEqual(strict["net_revenue_thb"], 90)
        self.assertEqual(strict["pending_amount_thb"], 45)
        self.assertEqual(strict["approved_amount_thb"], 63)
        self.assertEqual(strict["by_source"], {"atth": 90.0})
        self.assertEqual(strict["attribution_state"], "UNATTRIBUTED")
        self.assertEqual(strict["attribution_scope"], "MERCHANT_TOTAL_ONLY")
        self.assertFalse(strict["sub_id_available"])
        self.assertFalse(strict["page_cta_attribution_ready"])
        self.assertEqual(strict["ledger_event_rows"], 7)
        self.assertEqual(strict["ledger_transaction_rows"], 6)
        self.assertTrue(strict["upstream_evidence_bound"])
        self.assertEqual(strict["upstream_bound_event_rows"], 7)
        self.assertEqual(
            len(strict["upstream_browser_evidence_sha256"]),
            strict["upstream_evidence_count"],
        )
        self.assertEqual(
            len(strict["upstream_receipt_file_sha256"]),
            strict["upstream_evidence_count"],
        )

        stdout = io.StringIO()
        with (
            mock.patch.object(sales_week, "LOG", str(self.output)),
            contextlib.redirect_stdout(stdout),
        ):
            code = sales_week.main([self.END.isoformat()])
        report = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("paid=1 refunds=1 net_revenue=90.00 THB", report)
        self.assertIn("reconciled events=7 transactions=6", report)
        self.assertIn("pending=1 (45.00 THB)", report)
        self.assertIn("approved=1 (63.00 THB)", report)
        self.assertNotIn("UNRECONCILED", report)

    def test_empty_frozen_export_is_a_trusted_zero_only_after_reconciliation(self) -> None:
        self.frozen.write_bytes(b"")
        self.reconcile()
        strict = revenue_ledger.read_affiliate_revenue(
            self.output,
            today=self.END,
            days=28,
        )
        self.assertTrue(strict["trusted"])
        self.assertEqual(strict["source_row_count"], 0)
        self.assertEqual(strict["ledger_event_rows"], 0)
        self.assertEqual(strict["ledger_transaction_rows"], 0)
        self.assertEqual(strict["paid_transactions"], 0)
        self.assertEqual(strict["net_revenue_thb"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
