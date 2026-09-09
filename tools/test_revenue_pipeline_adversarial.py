#!/usr/bin/env python3
"""Adversarial tests for frozen-source reconciliation and atomic install."""
from __future__ import annotations

import datetime as dt
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import log_sale
import import_accesstrade_csv as accesstrade_csv
import reconcile_sales
import revenue_ledger


class RevenuePipelineAdversarialTests(unittest.TestCase):
    END = dt.date(2026, 8, 16)
    NOW = dt.datetime(2026, 8, 16, 13, 0, tzinfo=log_sale.BANGKOK)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / "frozen-source.jsonl"
        self.output = root / "sales-log.jsonl"

    def row(
        self,
        sale_id: str = "affiliate-A1",
        *,
        event_id: str | None = None,
        status: str = "paid",
        source: str = "atth",
        gross: int | None = None,
        fee: int | None = None,
        second: int = 0,
    ) -> dict:
        if gross is None:
            gross = 0 if status in log_sale.ZERO_STATUSES else 100
        if fee is None:
            fee = 0 if status in log_sale.ZERO_STATUSES else 10
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

    def write_rows(self, *rows: object) -> None:
        self.source.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def reconcile(
        self,
        *,
        replace: bool = False,
        expected_sha256: str | None = None,
        expected_row_count: int | None = None,
    ) -> dict:
        if expected_sha256 is None:
            expected_sha256 = hashlib.sha256(self.source.read_bytes()).hexdigest()
        if expected_row_count is None:
            expected_row_count = sum(
                1 for line in self.source.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        evidence_paths, evidence_hashes, raw_paths, browser_paths = self.evidence_receipts()
        with mock.patch.object(accesstrade_csv, "PRIVATE_ROOT", self.output.parent):
            return reconcile_sales.reconcile(
                self.source,
                self.output,
                source_system="owner-frozen-export",
                coverage_start="2026-07-20",
                coverage_end=self.END,
                extracted_at="2026-08-16T12:30:00+07:00",
                expected_sha256=expected_sha256,
                expected_row_count=expected_row_count,
                upstream_evidence_path=evidence_paths,
                expected_upstream_evidence_sha256=evidence_hashes,
                upstream_raw_csv_path=raw_paths,
                upstream_browser_evidence_path=browser_paths,
                replace=replace,
                now=self.NOW,
            )

    def evidence_receipts(
        self,
    ) -> tuple[list[Path], list[str], list[Path], list[Path]]:
        try:
            rows = [json.loads(line) for line in self.source.read_text(encoding="utf-8").splitlines()
                    if line.strip()]
            latest = log_sale.validate_event_sequence(rows, now=self.NOW)
        except Exception:
            rows = []
            latest = {}
        current_ids = {row["event_id"] for row in latest.values()
                       if row.get("product") == "affiliate-commission"}
        current = [
            row for row in rows
            if row.get("event_id") in current_ids
            and str(row.get("date", "")) >= "2026-07-20"
        ]
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

    def assert_no_install_artifacts(self) -> None:
        root = self.output.parent
        self.assertFalse(Path(str(self.output) + ".reconcile.lock").exists())
        self.assertEqual(list(root.glob("sales-log-candidate-*.jsonl")), [])
        self.assertEqual(list(root.glob("sales-log-rollback-*.jsonl")), [])

    def test_live_mutable_intake_is_refused(self) -> None:
        self.write_rows(self.row())
        with mock.patch.object(reconcile_sales, "SALES_INTAKE_FILE", self.source):
            with self.assertRaisesRegex(reconcile_sales.ReconcileError, "live intake is mutable"):
                self.reconcile()
        self.assertFalse(self.output.exists())

    def test_invalid_sources_fail_closed_without_touching_existing_output(self) -> None:
        valid = self.row()
        malformed_money = {**valid, "sale_id": "nan-A1", "gross_amount_thb": "NaN"}
        legacy_status = {**valid, "sale_id": "legacy-A1", "status": "confirmed"}
        pii = {**valid, "sale_id": "pii-A1", "note": "buyer@example.com"}
        ip_address = {**valid, "sale_id": "ip-A1", "note": "127.0.0.1"}
        outside = {**valid, "sale_id": "old-A1", "date": "2026-07-19"}
        after_export = {**valid, "sale_id": "late-A1", "ts": "2026-08-16T12:31:00+07:00"}
        fixed_mismatch = {**valid, "sale_id": "fixed-A1", "product": "ebook-59"}
        extra_field = {**valid, "sale_id": "drift-A1", "unexpected": "field"}
        cases = {
            "metadata schema2 source": [{"_meta": "legacy", "schema_version": 2}],
            "duplicate id": [valid, valid],
            "legacy confirmed": [legacy_status],
            "PII": [pii],
            "IP address": [ip_address],
            "outside coverage": [outside],
            "transaction after export": [after_export],
            "fixed price mismatch": [fixed_mismatch],
            "field drift": [extra_field],
            "non-finite money": [malformed_money],
        }
        sentinel = b"do-not-replace-on-failure\n"
        for label, rows in cases.items():
            with self.subTest(case=label):
                self.output.write_bytes(sentinel)
                self.write_rows(*rows)
                with self.assertRaises(reconcile_sales.ReconcileError):
                    self.reconcile(replace=True)
                self.assertEqual(self.output.read_bytes(), sentinel)
                self.assert_no_install_artifacts()

        self.source.write_text("{not-json}\n", encoding="utf-8")
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "invalid JSON"):
            self.reconcile(replace=True)
        self.assertEqual(self.output.read_bytes(), sentinel)

        for raw, pattern in (("\n", "blank JSONL row"),
                             (json.dumps(valid, ensure_ascii=False), "newline commit boundary")):
            self.source.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(reconcile_sales.ReconcileError, pattern):
                self.reconcile(replace=True)
            self.assertEqual(self.output.read_bytes(), sentinel)

    def test_source_hash_change_before_install_preserves_old_output(self) -> None:
        self.write_rows(self.row())
        sentinel = b"old-output-remains\n"
        self.output.write_bytes(sentinel)
        actual = hashlib.sha256(self.source.read_bytes()).hexdigest()
        original_sha256 = reconcile_sales._sha256
        source_reads = 0

        def changed_on_final_source_check(path: Path) -> str:
            nonlocal source_reads
            if Path(path).resolve() == self.source.resolve():
                source_reads += 1
                if source_reads == 3:
                    return "0" * 64
            return original_sha256(path)

        with mock.patch.object(
            reconcile_sales,
            "_sha256",
            side_effect=changed_on_final_source_check,
        ):
            with self.assertRaisesRegex(reconcile_sales.ReconcileError, "changed before atomic install"):
                self.reconcile(replace=True)
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assert_no_install_artifacts()

    def test_candidate_mutation_by_reader_preserves_old_output(self) -> None:
        self.write_rows(self.row())
        sentinel = b"old-output-remains\n"
        self.output.write_bytes(sentinel)
        original_reader = revenue_ledger.read_affiliate_revenue

        def mutate_after_read(path, *args, **kwargs):
            result = original_reader(path, *args, **kwargs)
            selected = Path(path)
            selected.write_bytes(selected.read_bytes() + b" ")
            return result

        with mock.patch.object(
            reconcile_sales.revenue_ledger,
            "read_affiliate_revenue",
            side_effect=mutate_after_read,
        ):
            with self.assertRaisesRegex(
                reconcile_sales.ReconcileError,
                "candidate changed during strict validation",
            ):
                self.reconcile(replace=True)
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assert_no_install_artifacts()

    def test_installed_mutation_rolls_back_old_output(self) -> None:
        self.write_rows(self.row())
        sentinel = b"old-output-remains\n"
        self.output.write_bytes(sentinel)
        original_reader = revenue_ledger.read_affiliate_revenue
        reader_calls = 0

        def mutate_installed_after_read(path, *args, **kwargs):
            nonlocal reader_calls
            result = original_reader(path, *args, **kwargs)
            reader_calls += 1
            if reader_calls == 2:
                selected = Path(path)
                selected.write_bytes(selected.read_bytes() + b" ")
            return result

        with mock.patch.object(
            reconcile_sales.revenue_ledger,
            "read_affiliate_revenue",
            side_effect=mutate_installed_after_read,
        ):
            with self.assertRaisesRegex(
                reconcile_sales.ReconcileError,
                "installed output changed during strict validation",
            ):
                self.reconcile(replace=True)
        self.assertEqual(reader_calls, 2)
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assert_no_install_artifacts()

    def test_upstream_artifact_alignment_order_and_duplicates_fail_closed(self) -> None:
        rows = [
            self.row("pair-A1", status="pending"),
            self.row(
                "pair-A1", event_id="pair-approved", status="approved", second=1
            ),
        ]
        self.write_rows(*rows)
        receipts, hashes, raw_paths, browser_paths = self.evidence_receipts()
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()

        def call(receipt_values, hash_values, raw_values, browser_values):
            with mock.patch.object(accesstrade_csv, "PRIVATE_ROOT", self.output.parent):
                return reconcile_sales.reconcile(
                    self.source,
                    self.output,
                    source_system="owner-frozen-export",
                    coverage_start="2026-07-20",
                    coverage_end=self.END,
                    extracted_at="2026-08-16T12:30:00+07:00",
                    expected_sha256=source_hash,
                    expected_row_count=2,
                    upstream_evidence_path=receipt_values,
                    expected_upstream_evidence_sha256=hash_values,
                    upstream_raw_csv_path=raw_values,
                    upstream_browser_evidence_path=browser_values,
                    replace=True,
                    now=self.NOW,
                )

        sentinel = b"old-output-remains\n"
        self.output.write_bytes(sentinel)
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "non-empty and aligned"):
            call(receipts, hashes, raw_paths[:-1], browser_paths)
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "paths must be distinct"):
            call(
                [receipts[0], receipts[0]],
                [hashes[0], hashes[0]],
                [raw_paths[0], raw_paths[0]],
                [browser_paths[0], browser_paths[0]],
            )
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "source artifacts are invalid"):
            call(receipts, hashes, list(reversed(raw_paths)), browser_paths)
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assert_no_install_artifacts()

    def test_upstream_files_changed_before_install_preserve_old_output(self) -> None:
        targets = (
            ("receipt", "evidence-0.json", 3),
            ("raw", "raw-0.csv", 1),
            ("browser", "browser-0.json", 1),
        )
        sentinel = b"old-output-remains\n"
        for label, filename, fail_on_read in targets:
            with self.subTest(artifact=label):
                self.write_rows(self.row())
                self.output.write_bytes(sentinel)
                target = (self.output.parent / filename).resolve()
                original_sha256 = reconcile_sales._sha256
                target_reads = 0

                def changed_on_final_check(path: Path) -> str:
                    nonlocal target_reads
                    if Path(path).resolve() == target:
                        target_reads += 1
                        if target_reads == fail_on_read:
                            return "0" * 64
                    return original_sha256(path)

                with mock.patch.object(
                    reconcile_sales, "_sha256", side_effect=changed_on_final_check
                ):
                    with self.assertRaisesRegex(
                        reconcile_sales.ReconcileError,
                        "upstream evidence changed before atomic install",
                    ):
                        self.reconcile(replace=True)
                self.assertEqual(self.output.read_bytes(), sentinel)
                self.assert_no_install_artifacts()

    def test_private_upstream_boundary_and_first_hash_errors_are_sanitized(self) -> None:
        self.write_rows(self.row())
        receipts, hashes, raw_paths, browser_paths = self.evidence_receipts()
        outside_root = Path(self.tmp.name).parent / (
            Path(self.tmp.name).name + "-outside"
        )
        outside_root.mkdir(exist_ok=True)
        self.addCleanup(lambda: outside_root.rmdir())
        outside_raw = outside_root / "provider-secret.csv"
        outside_raw.write_bytes(raw_paths[0].read_bytes())
        self.addCleanup(lambda: outside_raw.unlink(missing_ok=True))
        with mock.patch.object(accesstrade_csv, "PRIVATE_ROOT", self.output.parent):
            with self.assertRaisesRegex(
                accesstrade_csv.AccessTradeImportError, "private runtime"
            ):
                accesstrade_csv.verify_receipt_sources(
                    json.loads(receipts[0].read_text(encoding="utf-8")),
                    outside_raw,
                    browser_paths[0],
                    require_complete=True,
                )

            leaked = "denied " + str(receipts[0]) + " conversion-provider-secret"
            with mock.patch.object(
                reconcile_sales, "_sha256", side_effect=OSError(leaked)
            ):
                with self.assertRaises(reconcile_sales.ReconcileError) as caught:
                    reconcile_sales._read_upstream_receipt(
                        receipts[0], hashes[0]
                    )
        rendered = str(caught.exception)
        self.assertNotIn(str(receipts[0]), rendered)
        self.assertNotIn("conversion-provider-secret", rendered)
        self.assertIn("unreadable", rendered)

    def test_public_or_outside_output_is_rejected_before_any_write(self) -> None:
        self.write_rows(self.row())
        receipts, hashes, raw_paths, browser_paths = self.evidence_receipts()
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        outside_root = Path(self.tmp.name).parent / (
            Path(self.tmp.name).name + "-public-output"
        )
        outside_root.mkdir(exist_ok=True)
        self.addCleanup(lambda: outside_root.rmdir())
        existing = outside_root / "tracked-sales.jsonl"
        missing = outside_root / "new-sales.jsonl"
        sentinel = b"public-file-must-not-change\n"
        existing.write_bytes(sentinel)
        self.addCleanup(lambda: existing.unlink(missing_ok=True))

        def attempt(target: Path) -> None:
            with mock.patch.object(accesstrade_csv, "PRIVATE_ROOT", self.output.parent):
                reconcile_sales.reconcile(
                    self.source,
                    target,
                    source_system="owner-frozen-export",
                    coverage_start="2026-07-20",
                    coverage_end=self.END,
                    extracted_at="2026-08-16T12:30:00+07:00",
                    expected_sha256=source_hash,
                    expected_row_count=1,
                    upstream_evidence_path=receipts,
                    expected_upstream_evidence_sha256=hashes,
                    upstream_raw_csv_path=raw_paths,
                    upstream_browser_evidence_path=browser_paths,
                    replace=True,
                    now=self.NOW,
                )

        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "private runtime"):
            attempt(existing)
        self.assertEqual(existing.read_bytes(), sentinel)
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "private runtime"):
            attempt(missing)
        self.assertFalse(missing.exists())
        self.assertFalse(Path(str(existing) + ".reconcile.lock").exists())
        self.assertFalse(Path(str(missing) + ".reconcile.lock").exists())
        self.assertEqual(list(outside_root.glob("*-candidate-*.jsonl")), [])

    def test_invalid_lifecycle_sequences_never_install(self) -> None:
        cases = {
            "initial refund": [self.row("refund-first", status="refunded")],
            "backward": [
                self.row("back-A1", status="paid"),
                self.row("back-A1", event_id="back-approved", status="approved", second=1),
            ],
            "duplicate state": [
                self.row("repeat-A1", status="pending"),
                self.row("repeat-A1", event_id="repeat-pending-2", status="pending", second=1),
            ],
            "terminal reuse": [
                self.row("terminal-A1", status="cancelled"),
                self.row("terminal-A1", event_id="terminal-paid", status="paid", second=1),
            ],
            "timestamp reversal": [
                self.row("time-A1", status="pending", second=1),
                self.row("time-A1", event_id="time-approved", status="approved", second=0),
            ],
            "identity mutation": [
                self.row("identity-A1", status="pending"),
                self.row(
                    "identity-A1", event_id="identity-paid", status="paid",
                    source="fb", second=1,
                ),
            ],
            "event id collision": [
                self.row("collision-A1", event_id="shared-event"),
                self.row("collision-A2", event_id="shared-event"),
            ],
        }
        sentinel = b"preserve-existing-output\n"
        for label, rows in cases.items():
            with self.subTest(case=label):
                self.output.write_bytes(sentinel)
                self.write_rows(*rows)
                with self.assertRaises(reconcile_sales.ReconcileError):
                    self.reconcile(replace=True)
                self.assertEqual(self.output.read_bytes(), sentinel)
                self.assert_no_install_artifacts()

    def test_recorded_hash_and_row_count_must_match_before_install(self) -> None:
        self.write_rows(self.row())
        sentinel = b"old-output-remains\n"
        self.output.write_bytes(sentinel)
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "checksum does not match"):
            self.reconcile(replace=True, expected_sha256="0" * 64)
        self.assertEqual(self.output.read_bytes(), sentinel)
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "row count does not match"):
            self.reconcile(replace=True, expected_row_count=0)
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assert_no_install_artifacts()

    def test_strict_reader_rejection_preserves_old_output(self) -> None:
        self.write_rows(self.row())
        sentinel = b"old-output-remains\n"
        self.output.write_bytes(sentinel)
        with mock.patch.object(
            reconcile_sales.revenue_ledger,
            "read_affiliate_revenue",
            return_value={"trusted": False, "error": "fixture strict rejection"},
        ):
            with self.assertRaisesRegex(reconcile_sales.ReconcileError, "strict reader rejected"):
                self.reconcile(replace=True)
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assert_no_install_artifacts()

    def test_strict_reader_provenance_mismatch_preserves_old_output(self) -> None:
        self.write_rows(self.row())
        sentinel = b"old-output-remains\n"
        self.output.write_bytes(sentinel)
        with mock.patch.object(
            reconcile_sales.revenue_ledger,
            "read_affiliate_revenue",
            return_value={
                "trusted": True,
                "source_snapshot_sha256": "0" * 64,
                "source_row_count": 1,
                "ledger_event_rows": 1,
                "ledger_transaction_rows": 1,
            },
        ):
            with self.assertRaisesRegex(reconcile_sales.ReconcileError, "provenance"):
                self.reconcile(replace=True)
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assert_no_install_artifacts()

    def test_schema2_output_is_not_auto_trusted_or_overwritten(self) -> None:
        legacy = b'{"_meta":"legacy","schema_version":4}\n'
        self.output.write_bytes(legacy)
        blocked = revenue_ledger.read_affiliate_revenue(
            self.output,
            today=self.END,
            days=28,
        )
        self.assertFalse(blocked["trusted"])
        self.write_rows(self.row())
        with self.assertRaisesRegex(reconcile_sales.ReconcileError, "output exists"):
            self.reconcile(replace=False)
        self.assertEqual(self.output.read_bytes(), legacy)

        installed = self.reconcile(replace=True)
        self.assertTrue(installed["trusted"])
        metadata = json.loads(self.output.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(metadata["schema_version"], 5)
        strict = revenue_ledger.read_affiliate_revenue(
            self.output,
            today=self.END,
            days=28,
        )
        self.assertTrue(strict["trusted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
