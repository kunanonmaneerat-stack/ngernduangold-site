#!/usr/bin/env python3
"""Synthetic-only tests for private AccessTrade CSV evidence import."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import import_accesstrade_csv as AT


class AccessTradeCsvImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / "private"
        self.private.mkdir()
        self.source = self.private / "synthetic.csv"
        self.output = self.private / "evidence.json"
        self.browser = self.private / "browser-evidence.json"

    def row(self, **overrides: str) -> list[str]:
        values = {name: "" for name in AT.CSV_HEADERS}
        values.update({
            AT.CLICK_AT: "2026-07-28 20:30:00",
            AT.CONVERSION_AT: "2026-07-28 20:33:33",
            AT.CAMPAIGN_ID: "588",
            "Conversion ID": "provider-secret-conversion",
            "Transaction ID": "provider-secret-transaction",
            AT.REWARD: "35.00",
            AT.STATUS: "PENDING",
        })
        values.update(overrides)
        return [values[name] for name in AT.CSV_HEADERS]

    def write(self, *rows: list[str], headers=None) -> str:
        with self.source.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\r\n")
            writer.writerow(list(headers or AT.CSV_HEADERS))
            writer.writerows(rows)
        return hashlib.sha256(self.source.read_bytes()).hexdigest()

    def write_browser(
        self,
        *,
        path=None,
        coverage_start="2026-07-19",
        coverage_end="2026-08-17",
        extracted_at="2026-08-17T12:00:00+07:00",
        status_filter="ALL",
        asserted_conversion_count=1,
        asserted_reward_thb="35.00",
        sale_id="at-20260728-ktcproud-01",
        event_id="at-20260728-ktcproud-01-pending",
        ledger_status="pending",
        ledger_bindings=None,
    ):
        selected = Path(path or self.browser)
        browser_status = {
            "ALL": "all", "PENDING": "pending_approval", "APPROVED": "approved",
            "PAID": "paid", "REJECTED": "rejected", "REFUNDED": "refunded",
            "CANCELLED": "cancelled",
        }[status_filter]
        if ledger_bindings is None:
            bindings = [] if asserted_conversion_count == 0 else [{
                "event_id": event_id,
                "sale_id": sale_id,
                "status": ledger_status,
                "amount_thb": float(asserted_reward_thb),
            }]
        else:
            bindings = ledger_bindings
        payload = {
            "schema_version": AT.BROWSER_EVIDENCE_SCHEMA_VERSION,
            "provider": "AccessTrade",
            "verified_at": extracted_at,
            "verification_mode": AT.VERIFICATION_MODE,
            "report_url": AT.REPORT_URL,
            "filters": {
                "period_start": coverage_start,
                "period_end": coverage_end,
                "date_basis": AT.DATE_BASIS,
                "status": browser_status,
                "campaign": "all",
            },
            "observed": {
                "campaign": "synthetic-campaign",
                "conversion_count": asserted_conversion_count,
                "total_reward_thb": float(asserted_reward_thb),
                "currency": "THB",
                # Browser visibility is independent from IDs present in the CSV.
                "provider_conversion_id_available": False,
                "transaction_id_available": False,
                "sub_id_available": False,
            },
            "ledger_bindings": bindings,
            "external_mutation": False,
            "financial_action": False,
            "note": "synthetic test evidence only",
        }
        selected.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return selected, hashlib.sha256(selected.read_bytes()).hexdigest()

    def import_one(self, *, status_filter="ALL", replace=False, **kwargs):
        raw_hash = kwargs.pop("raw_hash", hashlib.sha256(self.source.read_bytes()).hexdigest())
        expected_row_count = kwargs.pop("expected_row_count", 1)
        coverage_start = kwargs.pop("coverage_start", "2026-07-19")
        coverage_end = kwargs.pop("coverage_end", "2026-08-17")
        extracted_at = kwargs.pop("extracted_at", "2026-08-17T12:00:00+07:00")
        row_bindings = kwargs.pop("row_bindings", None)
        sale_id = kwargs.pop(
            "sale_id", None if row_bindings is not None else "at-20260728-ktcproud-01"
        )
        event_id = kwargs.pop(
            "event_id",
            None if row_bindings is not None else "at-20260728-ktcproud-01-pending",
        )
        asserted_count = kwargs.pop("asserted_conversion_count", 1)
        asserted_reward = kwargs.pop("asserted_reward_thb", "35.00")
        browser_path = kwargs.pop("browser_evidence_path", self.browser)
        browser_mutator = kwargs.pop("browser_mutator", None)
        browser_ledger_bindings = kwargs.pop("browser_ledger_bindings", None)
        _, default_browser_hash = self.write_browser(
            path=browser_path,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            extracted_at=extracted_at,
            status_filter=status_filter,
            asserted_conversion_count=asserted_count,
            asserted_reward_thb=asserted_reward,
            sale_id=sale_id,
            event_id=event_id,
            ledger_bindings=browser_ledger_bindings,
        )
        if browser_mutator is not None:
            browser_payload = json.loads(Path(browser_path).read_text(encoding="utf-8"))
            browser_mutator(browser_payload)
            Path(browser_path).write_text(
                json.dumps(browser_payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            default_browser_hash = hashlib.sha256(Path(browser_path).read_bytes()).hexdigest()
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            return AT.import_csv(
                self.source, self.output,
                expected_raw_sha256=raw_hash,
                expected_row_count=expected_row_count,
                browser_evidence_path=browser_path,
                browser_evidence_sha256=kwargs.pop(
                    "browser_evidence_sha256", default_browser_hash
                ),
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                extracted_at=extracted_at,
                verification_mode=kwargs.pop("verification_mode", AT.VERIFICATION_MODE),
                date_basis=kwargs.pop("date_basis", AT.DATE_BASIS),
                status_filter=status_filter,
                campaign_filter=kwargs.pop("campaign_filter", "ALL"),
                asserted_conversion_count=asserted_count,
                asserted_reward_thb=asserted_reward,
                sale_id=sale_id,
                event_id=event_id,
                row_bindings=row_bindings,
                ledger_ref=kwargs.pop(
                    "ledger_ref",
                    "" if row_bindings is not None else "accesstrade-dashboard-jul2026",
                ),
                channel_source=kwargs.pop("channel_source", "atth"),
                fee=kwargs.pop("fee", "0.00"),
                replace=replace,
                **kwargs,
            )

    @staticmethod
    def exact_row_binding(
        row: list[str], *, sale_id: str, event_id: str,
        ledger_ref: str = "accesstrade-dashboard-jul2026", fee: str = "0.00",
    ) -> dict[str, str]:
        return {
            "source_row_sha256": AT.canonical_sha256(row),
            "event_id": event_id,
            "sale_id": sale_id,
            "ledger_ref": ledger_ref,
            "fee": fee,
        }

    def test_exact_export_creates_private_hash_only_receipt(self) -> None:
        raw_hash = self.write(self.row())
        result = self.import_one(raw_hash=raw_hash)
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        evidence = AT.validate_receipt(receipt, require_complete=True)

        self.assertTrue(result["trusted"])
        self.assertEqual(evidence["raw_file_sha256"], raw_hash)
        self.assertEqual(evidence["raw_file_row_count"], 1)
        self.assertEqual(evidence["filter_assertion"]["coverage_start"], "2026-07-19")
        self.assertEqual(evidence["filter_assertion"]["coverage_end"], "2026-08-17")
        self.assertEqual(evidence["verification_mode"], AT.VERIFICATION_MODE)
        self.assertEqual(evidence["filter_assertion"]["campaign_filter"], "ALL")
        self.assertEqual(evidence["filter_assertion"]["asserted_conversion_count"], 1)
        self.assertEqual(evidence["filter_assertion"]["asserted_reward_thb"], "35.00")
        self.assertEqual(evidence["filter_assertion"]["currency"], "THB")
        self.assertEqual(evidence["filter_assertion"]["date_basis"], "effect_date")
        self.assertFalse(evidence["sub_id_available"])
        self.assertEqual(evidence["attribution_state"], "UNATTRIBUTED")
        binding = evidence["bindings"][0]
        self.assertEqual(binding["sale_id"], "at-20260728-ktcproud-01")
        self.assertEqual(binding["event_id"], "at-20260728-ktcproud-01-pending")
        self.assertEqual(binding["channel_source"], "atth")
        self.assertEqual(binding["gross_amount_thb"], 35)
        rendered = self.output.read_text(encoding="utf-8")
        self.assertNotIn("provider-secret-conversion", rendered)
        self.assertNotIn("provider-secret-transaction", rendered)
        self.assertNotIn('"588"', rendered)

    def test_same_raw_bytes_can_carry_distinct_authenticated_filter_assertions(self) -> None:
        raw_hash = self.write(self.row())
        first = self.import_one(raw_hash=raw_hash)
        first_receipt = json.loads(self.output.read_text(encoding="utf-8"))
        second_output = self.private / "evidence-second.json"
        second_browser, second_browser_hash = self.write_browser(
            path=self.private / "browser-second.json",
            coverage_start="2026-07-01",
            coverage_end="2026-07-31",
        )
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            second = AT.import_csv(
                self.source, second_output,
                expected_raw_sha256=raw_hash, expected_row_count=1,
                browser_evidence_path=second_browser,
                browser_evidence_sha256=second_browser_hash,
                coverage_start="2026-07-01", coverage_end="2026-07-31",
                extracted_at="2026-08-17T12:00:00+07:00",
                verification_mode=AT.VERIFICATION_MODE,
                date_basis=AT.DATE_BASIS, status_filter="ALL",
                campaign_filter="ALL", asserted_conversion_count=1,
                asserted_reward_thb="35.00",
                sale_id="at-20260728-ktcproud-01",
                event_id="at-20260728-ktcproud-01-pending",
                ledger_ref="accesstrade-dashboard-jul2026",
            )
        second_receipt = json.loads(second_output.read_text(encoding="utf-8"))
        self.assertEqual(first["raw_file_sha256"], second["raw_file_sha256"])
        self.assertNotEqual(first_receipt["evidence_sha256"], second_receipt["evidence_sha256"])

    def test_partial_status_filter_is_recorded_but_not_decision_complete(self) -> None:
        self.write(self.row())
        result = self.import_one(status_filter="PENDING")
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertFalse(result["complete_status_coverage"])
        AT.validate_receipt(receipt, require_complete=False)
        with self.assertRaisesRegex(AT.AccessTradeImportError, "partial"):
            AT.validate_receipt(receipt, require_complete=True)

    def test_header_hash_count_and_multirow_drift_fail_closed(self) -> None:
        changed = list(AT.CSV_HEADERS)
        changed[0], changed[1] = changed[1], changed[0]
        self.write(self.row(), headers=changed)
        with self.assertRaisesRegex(AT.AccessTradeImportError, "header/order"):
            self.import_one()

        raw_hash = self.write(self.row())
        with self.assertRaisesRegex(AT.AccessTradeImportError, "hash"):
            self.import_one(raw_hash="0" * 64)
        with self.assertRaisesRegex(AT.AccessTradeImportError, "row count"):
            self.import_one(raw_hash=raw_hash, expected_row_count=0)

        self.write(self.row(), self.row(**{"Conversion ID": "second"}))
        with self.assertRaisesRegex(AT.AccessTradeImportError, "row-binding"):
            self.import_one(expected_row_count=2)

    def test_multirow_exact_hash_bindings_are_supported_and_canonically_ordered(self) -> None:
        first = self.row(
            **{
                AT.CONVERSION_AT: "2026-07-28 20:33:33",
                "Conversion ID": "provider-secret-first",
                "Transaction ID": "provider-transaction-first",
                AT.REWARD: "17.50",
                AT.STATUS: "PENDING",
            }
        )
        second = self.row(
            **{
                AT.CONVERSION_AT: "2026-07-29 09:15:00",
                "Conversion ID": "provider-secret-second",
                "Transaction ID": "provider-transaction-second",
                AT.REWARD: "17.50",
                AT.STATUS: "PENDING",
            }
        )
        raw_hash = self.write(second, first)
        first_binding = self.exact_row_binding(
            first, sale_id="at-multi-first", event_id="at-multi-first-pending"
        )
        second_binding = self.exact_row_binding(
            second, sale_id="at-multi-second", event_id="at-multi-second-pending"
        )
        browser_bindings = [
            {
                "event_id": second_binding["event_id"],
                "sale_id": second_binding["sale_id"],
                "status": "pending",
                "amount_thb": 17.5,
            },
            {
                "event_id": first_binding["event_id"],
                "sale_id": first_binding["sale_id"],
                "status": "pending",
                "amount_thb": 17.5,
            },
        ]

        result = self.import_one(
            raw_hash=raw_hash,
            expected_row_count=2,
            asserted_conversion_count=2,
            asserted_reward_thb="35.00",
            # Specification order is deliberately independent of raw CSV order.
            row_bindings=[first_binding, second_binding],
            browser_ledger_bindings=browser_bindings,
        )
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        evidence = AT.validate_receipt(receipt, require_complete=True)
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            AT.verify_receipt_sources(
                receipt, self.source, self.browser, require_complete=True
            )

        self.assertTrue(result["trusted"])
        self.assertEqual(result["raw_file_row_count"], 2)
        self.assertEqual(
            [binding["source_row_sha256"] for binding in evidence["bindings"]],
            sorted((first_binding["source_row_sha256"], second_binding["source_row_sha256"])),
        )
        bound_sales = {
            binding["source_row_sha256"]: binding["sale_id"]
            for binding in evidence["bindings"]
        }
        self.assertEqual(
            bound_sales,
            {
                first_binding["source_row_sha256"]: "at-multi-first",
                second_binding["source_row_sha256"]: "at-multi-second",
            },
        )
        rendered = self.output.read_text(encoding="utf-8")
        self.assertNotIn("provider-secret-first", rendered)
        self.assertNotIn("provider-secret-second", rendered)

    def test_multirow_mapping_drift_and_ambiguity_fail_closed(self) -> None:
        first = self.row(
            **{"Conversion ID": "first", "Transaction ID": "tx-first", AT.REWARD: "10.00"}
        )
        second = self.row(
            **{
                AT.CONVERSION_AT: "2026-07-29 09:15:00",
                "Conversion ID": "second",
                "Transaction ID": "tx-second",
                AT.REWARD: "25.00",
            }
        )
        self.write(first, second)
        first_binding = self.exact_row_binding(
            first, sale_id="at-first", event_id="at-first-pending"
        )
        second_binding = self.exact_row_binding(
            second, sale_id="at-second", event_id="at-second-pending"
        )
        common = {
            "expected_row_count": 2,
            "asserted_conversion_count": 2,
            "asserted_reward_thb": "35.00",
        }
        with self.assertRaisesRegex(AT.AccessTradeImportError, "exactly cover"):
            self.import_one(row_bindings=[first_binding], **common)
        wrong = {**second_binding, "source_row_sha256": "0" * 64}
        with self.assertRaisesRegex(AT.AccessTradeImportError, "row hashes"):
            self.import_one(row_bindings=[first_binding, wrong], **common)
        duplicate_event = {**second_binding, "event_id": first_binding["event_id"]}
        with self.assertRaisesRegex(AT.AccessTradeImportError, "duplicate identities"):
            self.import_one(row_bindings=[first_binding, duplicate_event], **common)
        with self.assertRaisesRegex(AT.AccessTradeImportError, "cannot be mixed"):
            self.import_one(
                row_bindings=[first_binding, second_binding],
                sale_id="legacy-sale",
                event_id="legacy-event",
                **common,
            )

        self.write(first, first)
        duplicate_rows = [
            first_binding,
            {**first_binding, "sale_id": "at-copy", "event_id": "at-copy-pending"},
        ]
        with self.assertRaisesRegex(AT.AccessTradeImportError, "duplicate source rows"):
            self.import_one(row_bindings=duplicate_rows, **common)

    def test_private_row_binding_spec_is_hash_and_raw_csv_bound(self) -> None:
        row = self.row()
        raw_hash = self.write(row)
        binding = self.exact_row_binding(
            row, sale_id="at-spec", event_id="at-spec-pending"
        )
        spec_path = self.private / "row-bindings.json"
        spec = {
            "schema_version": AT.ROW_BINDING_SPEC_SCHEMA_VERSION,
            "raw_file_sha256": raw_hash,
            "bindings": [binding],
        }
        spec_path.write_text(
            json.dumps(spec, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        spec_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest()
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            loaded = AT._read_row_binding_spec(
                spec_path,
                expected_sha256=spec_hash,
                expected_raw_sha256=raw_hash,
            )
            self.assertEqual(loaded, [binding])
            with self.assertRaisesRegex(AT.AccessTradeImportError, "specification hash"):
                AT._read_row_binding_spec(
                    spec_path,
                    expected_sha256="0" * 64,
                    expected_raw_sha256=raw_hash,
                )
            with self.assertRaisesRegex(AT.AccessTradeImportError, "exact raw CSV"):
                AT._read_row_binding_spec(
                    spec_path,
                    expected_sha256=spec_hash,
                    expected_raw_sha256="1" * 64,
                )

    def test_status_money_time_and_identity_must_be_exact(self) -> None:
        cases = [
            ({AT.STATUS: "pending"}, "status"),
            ({AT.REWARD: "35"}, "two decimals"),
            ({AT.REWARD: "NaN"}, "two decimals"),
            ({AT.CONVERSION_AT: "28/07/2026 20:33:33"}, "YYYY-MM-DD"),
            ({AT.CONVERSION_AT: "2026-06-30 20:33:33"}, "outside"),
            ({"Conversion ID": "", "Transaction ID": ""}, "identity is missing"),
        ]
        for overrides, pattern in cases:
            with self.subTest(overrides=overrides):
                self.write(self.row(**overrides))
                with self.assertRaisesRegex(AT.AccessTradeImportError, pattern):
                    self.import_one()

    def test_unattributed_source_and_private_artifacts_are_mandatory(self) -> None:
        self.write(self.row())
        with self.assertRaisesRegex(AT.AccessTradeImportError, "source atth"):
            self.import_one(channel_source="fb")
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(AT.AccessTradeImportError, "private runtime"):
                AT.import_csv(
                    self.source, self.root / "public.json",
                    expected_raw_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
                    expected_row_count=1, coverage_start="2026-07-19",
                    browser_evidence_path=self.browser,
                    browser_evidence_sha256=hashlib.sha256(self.browser.read_bytes()).hexdigest(),
                    coverage_end="2026-08-17",
                    extracted_at="2026-08-17T12:00:00+07:00",
                    verification_mode=AT.VERIFICATION_MODE,
                    date_basis=AT.DATE_BASIS, status_filter="ALL",
                    campaign_filter="ALL", asserted_conversion_count=1,
                    asserted_reward_thb="35.00",
                    sale_id="at-20260728-ktcproud-01",
                    event_id="at-20260728-ktcproud-01-pending",
                    ledger_ref="accesstrade-dashboard-jul2026",
                )
        outside = self.root / "outside.csv"
        outside.write_bytes(self.source.read_bytes())
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(AT.AccessTradeImportError, "private runtime"):
                AT.import_csv(
                    outside, self.output,
                    expected_raw_sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
                    expected_row_count=1, coverage_start="2026-07-19",
                    browser_evidence_path=self.browser,
                    browser_evidence_sha256=hashlib.sha256(self.browser.read_bytes()).hexdigest(),
                    coverage_end="2026-08-17",
                    extracted_at="2026-08-17T12:00:00+07:00",
                    verification_mode=AT.VERIFICATION_MODE,
                    date_basis=AT.DATE_BASIS, status_filter="ALL",
                    campaign_filter="ALL", asserted_conversion_count=1,
                    asserted_reward_thb="35.00",
                    sale_id="at-20260728-ktcproud-01",
                    event_id="at-20260728-ktcproud-01-pending",
                    ledger_ref="accesstrade-dashboard-jul2026",
                )

    def test_receipt_tampering_is_detected(self) -> None:
        self.write(self.row())
        self.import_one()
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        receipt["evidence"]["bindings"][0]["status"] = "paid"
        with self.assertRaisesRegex(AT.AccessTradeImportError, "canonical hash"):
            AT.validate_receipt(receipt, require_complete=True)

    def test_schema_versions_require_exact_json_integers(self) -> None:
        self.write(self.row())
        self.import_one()
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        receipt["evidence"]["schema_version"] = 1.0
        receipt["evidence_sha256"] = AT.canonical_sha256(receipt["evidence"])
        with self.assertRaisesRegex(AT.AccessTradeImportError, "contract"):
            AT.validate_receipt(receipt, require_complete=True)

        with self.assertRaisesRegex(AT.AccessTradeImportError, "safety contract"):
            self.import_one(
                replace=True,
                browser_mutator=lambda payload: payload.update(
                    {"schema_version": 2.0}
                ),
            )

        raw_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        binding = self.exact_row_binding(
            self.row(), sale_id="at-schema", event_id="at-schema-pending"
        )
        spec_path = self.private / "row-bindings-schema-float.json"
        spec_path.write_text(
            json.dumps(
                {
                    "schema_version": 1.0,
                    "raw_file_sha256": raw_hash,
                    "bindings": [binding],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        spec_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest()
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(AT.AccessTradeImportError, "exact raw CSV"):
                AT._read_row_binding_spec(
                    spec_path,
                    expected_sha256=spec_hash,
                    expected_raw_sha256=raw_hash,
                )

    def test_browser_summary_and_campaign_scope_are_independent_fail_closed_assertions(self) -> None:
        self.write(self.row())
        with self.assertRaisesRegex(AT.AccessTradeImportError, "conversion count"):
            self.import_one(asserted_conversion_count=0)
        with self.assertRaisesRegex(AT.AccessTradeImportError, "reward summary"):
            self.import_one(asserted_reward_thb="34.99")
        with self.assertRaisesRegex(AT.AccessTradeImportError, "all campaigns"):
            self.import_one(campaign_filter="588")

    def test_browser_and_raw_source_artifacts_are_reopened_and_semantically_verified(self) -> None:
        self.write(self.row())
        with self.assertRaisesRegex(AT.AccessTradeImportError, "browser evidence hash"):
            self.import_one(browser_evidence_sha256="0" * 64)
        with self.assertRaisesRegex(AT.AccessTradeImportError, "filters do not match"):
            self.import_one(
                browser_mutator=lambda payload: payload["filters"].update({"campaign": "588"})
            )
        with self.assertRaisesRegex(AT.AccessTradeImportError, "ledger binding"):
            self.import_one(
                browser_mutator=lambda payload: payload["ledger_bindings"][0].update(
                    {"amount_thb": 34}
                )
            )
        with self.assertRaisesRegex(AT.AccessTradeImportError, "safety contract"):
            self.import_one(
                browser_mutator=lambda payload: payload.update(
                    {"report_url": "https://example.test/fake-report"}
                )
            )
        invalid_refs = (
            "page-or-cta-winner",
            "accesstrade-dashboard-bureau-blacklist-loan",
            "accesstrade-dashboard-jul2026-page",
            "accesstrade-dashboard-jul2026-cta",
            "accesstrade-dashboard-jul-2026",
            "accesstrade-dashboard-Jul2026",
            "accesstrade-dashboard-jul2026-extra-token",
        )
        for invalid_ref in invalid_refs:
            with self.subTest(ledger_ref=invalid_ref), self.assertRaisesRegex(
                AT.AccessTradeImportError, "provider-dashboard"
            ):
                self.import_one(ledger_ref=invalid_ref)

        self.import_one(replace=True)
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        self.source.write_bytes(self.source.read_bytes() + b"\r\n")
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(AT.AccessTradeImportError, "CSV hash"):
                AT.verify_receipt_sources(
                    receipt, self.source, self.browser, require_complete=True
                )

    def test_unreadable_private_sources_never_leak_paths_or_provider_ids(self) -> None:
        self.write(self.row())
        leaked = "denied " + str(self.source) + " provider-secret-conversion"
        with mock.patch.object(AT, "file_sha256", side_effect=OSError(leaked)):
            with self.assertRaises(AT.AccessTradeImportError) as caught:
                self.import_one()
        rendered = str(caught.exception)
        self.assertNotIn(str(self.source), rendered)
        self.assertNotIn("provider-secret-conversion", rendered)
        self.assertIn("readable", rendered)

        self.write_browser()
        browser_hash = hashlib.sha256(self.browser.read_bytes()).hexdigest()
        with mock.patch.object(AT, "PRIVATE_ROOT", self.private), mock.patch.object(
            AT, "file_sha256", side_effect=OSError(leaked)
        ):
            with self.assertRaises(AT.AccessTradeImportError) as browser_caught:
                AT._read_browser_evidence(
                    self.browser, expected_sha256=browser_hash
                )
        browser_rendered = str(browser_caught.exception)
        self.assertNotIn(str(self.browser), browser_rendered)
        self.assertNotIn("provider-secret-conversion", browser_rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
