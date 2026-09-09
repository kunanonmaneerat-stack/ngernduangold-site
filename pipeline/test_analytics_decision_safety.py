#!/usr/bin/env python3
"""Focused regression tests for analytics trust and metric semantics."""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import dashboard_agent as DASHBOARD  # noqa: E402
import metrics_loop as METRICS  # noqa: E402
import post_timing as TIMING  # noqa: E402
import traffic_analyst as ANALYST  # noqa: E402
import traffic_monitor as MONITOR  # noqa: E402
import import_accesstrade_csv as AT  # noqa: E402
import log_sale  # noqa: E402


class PackageImportTests(unittest.TestCase):
    def test_analytics_consumers_support_package_imports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        modules = (
            "pipeline.observation_snapshot",
            "pipeline.decision_readiness",
            "pipeline.dashboard_agent",
            "pipeline.traffic_monitor",
            "pipeline.weekly_growth_review",
        )
        source = "import sys; sys.path.insert(0, %r); " % str(root)
        source += "; ".join("import %s" % name for name in modules)
        result = subprocess.run(
            [sys.executable, "-I", "-c", source],
            cwd=str(root), capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


def trust(value: bool):
    return types.SimpleNamespace(
        trusted=value,
        label="TRUSTED" if value else "UNTRUSTED",
        reason="fixture trusted" if value else "fixture mismatch",
        schema="fixture",
        state="CURRENT" if value else "INVALID_METADATA",
        expires_at="2099-01-01T00:00:00+00:00" if value else None,
    )


def write(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def reconciled_sales(rows: list[dict]) -> list[dict]:
    """Wrap source-snapshot events in the schema-5 reconciliation contract."""
    metadata = {
        "_meta": "reconciled-source-export",
        "schema_version": 5,
        "fields": [
            "channel_source", "date", "fee_thb", "gross_amount_thb", "net_amount_thb",
            "event_id", "note", "product", "ref", "sale_id", "status", "ts",
        ],
        "products": {"affiliate-commission": None, "ebook-59": 59},
        "blocked_products": [],
        "channel_source_values": ["atth", "gumroad"],
        "created": "2026-07-20",
        "updated": "2026-08-16",
        "source_system": "analytics-test-export",
        "coverage_start": "2026-07-20",
        "coverage_end": "2026-08-16",
        "extracted_at": "2026-08-16T13:00:00+07:00",
        "reconciled_at": "2026-08-16T14:00:00+07:00",
        "source_snapshot_sha256": hashlib.sha256(b"analytics-test-export").hexdigest(),
        "source_row_count": len(rows),
        "upstream_evidence": [],
        "complete": True,
    }
    latest = log_sale.validate_event_sequence(
        rows, now=datetime.datetime.fromisoformat(metadata["extracted_at"])
    )
    latest_ids = {
        row["event_id"] for row in latest.values()
        if row.get("product") == "affiliate-commission"
    }
    current = [row for row in rows if row.get("event_id") in latest_ids]
    historical = [
        row for row in rows
        if row.get("product") == "affiliate-commission"
        and row.get("event_id") not in latest_ids
    ]
    groups = [(current, metadata["coverage_end"])]
    groups.extend(([row], row["date"]) for row in historical)
    for index, (group, coverage_end) in enumerate(groups):
        bindings = []
        for row in group:
            token = hashlib.sha256(("provider:" + row["sale_id"]).encode()).hexdigest()
            bindings.append({
                "provider_identity_sha256": token,
                "provider_conversion_id_hash": token,
                "transaction_id_hash": None,
                "campaign_id_hash": hashlib.sha256(
                    ("campaign:" + row["sale_id"]).encode()
                ).hexdigest(),
                "source_row_sha256": hashlib.sha256(
                    ("row:" + row["event_id"]).encode()
                ).hexdigest(),
                "event_id": row["event_id"], "sale_id": row["sale_id"],
                "date": row["date"], "status": row["status"],
                "gross_amount_thb": row["gross_amount_thb"],
                "fee_thb": row["fee_thb"], "net_amount_thb": row["net_amount_thb"],
                "channel_source": row["channel_source"], "ref": row["ref"],
            })
        reward = sum(
            (Decimal(str(binding["gross_amount_thb"])) for binding in bindings),
            Decimal("0.00"),
        )
        evidence = {
            "schema_version": 1, "provider": "accesstrade", "format": AT.FORMAT_ID,
            "verification_mode": AT.VERIFICATION_MODE,
            "raw_file_sha256": hashlib.sha256(("raw:%d" % index).encode()).hexdigest(),
            "raw_file_row_count": len(bindings),
            "header_sha256": AT._header_sha256(),
            "browser_evidence_sha256": hashlib.sha256(
                ("browser:%d" % index).encode()
            ).hexdigest(),
            "filter_assertion": {
                "coverage_start": metadata["coverage_start"],
                "coverage_end": coverage_end,
                "date_basis": AT.DATE_BASIS, "status_filter": "ALL",
                "campaign_filter": "ALL", "asserted_conversion_count": len(bindings),
                "asserted_reward_thb": format(reward, ".2f"), "currency": "THB",
                "timezone": "Asia/Bangkok",
                "asserted_from": "authenticated_browser_filter_not_csv",
            },
            "extracted_at": metadata["extracted_at"],
            "importer_sha256": AT._importer_sha256(),
            "sub_id_available": False, "attribution_state": "UNATTRIBUTED",
            "bindings": bindings,
        }
        receipt = {
            "_meta": "private AccessTrade CSV evidence receipt",
            "evidence": evidence,
            "evidence_sha256": AT.canonical_sha256(evidence),
        }
        receipt_hash = AT.canonical_sha256(receipt)
        metadata["upstream_evidence"].append({
            "receipt_file_sha256": hashlib.sha256(
                (receipt_hash + "\n").encode("ascii")
            ).hexdigest(),
            "receipt_sha256": receipt_hash,
            "receipt": receipt,
            "canonical_source_sha256": metadata["source_snapshot_sha256"],
            "canonical_source_row_count": len(rows),
        })
    return [metadata, *rows]


def sale(sale_id: str, product: str, status: str, gross: float, net: float,
         source: str, *, second: int = 0) -> dict:
    return {
        "event_id": "event-%s-%s" % (sale_id, status),
        "sale_id": sale_id,
        "product": product,
        "status": status,
        "date": "2026-08-16",
        "gross_amount_thb": gross,
        "fee_thb": 0,
        "net_amount_thb": net,
        "channel_source": source,
        "ref": "",
        "note": "",
        "ts": "2026-08-16T12:00:%02d+07:00" % second,
    }


class TrafficAnalystSafetyTests(unittest.TestCase):
    def _run(self, root: Path, trusted: bool, sales_rows: list[dict] | None = None):
        ga4 = root / "ga4.csv"
        sales = root / "sales.jsonl"
        inbox = root / "inbox"
        write(
            ga4,
            "source,sessions,quiz_start,affiliate_click,buy_intent_click\n"
            "facebook,20,2,7,1\n",
        )
        rows = sales_rows or []
        write(
            sales,
            "".join(json.dumps(row) + "\n" for row in reconciled_sales(rows)),
        )
        monitor_result = {
            "agg": {"facebook": {"views": 40}},
            "total": {"views": 40, "clicks": 3, "quiz_start": 0, "conversion": 0},
            "rows": 1,
            "ts": "20260816-1200",
            "file": str(root / "monitor.md"),
        }
        with (
            mock.patch.object(ANALYST, "GA4_FILE", str(ga4)),
            mock.patch.object(ANALYST, "SALES_LOG", str(sales)),
            mock.patch.object(ANALYST, "INBOX", str(inbox)),
            mock.patch.object(ANALYST, "_ga4_trust", return_value=trust(trusted)),
            mock.patch.object(ANALYST.tm, "run", return_value=monitor_result),
        ):
            result = ANALYST.analyze(today=datetime.date(2026, 8, 16))
        report = Path(result["file"]).read_text(encoding="utf-8")
        return result, report

    def test_untrusted_ga4_never_selects_a_winner_or_changes_timing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_untrusted_") as temp:
            result, report = self._run(Path(temp), False)
        self.assertFalse(result["ga4_trusted"])
        self.assertIn("UNTRUSTED", result["verdict"])
        self.assertIn("ห้ามเลือกช่องชนะ", result["decision"])
        self.assertIn("เปลี่ยนเวลาโพสต์", result["decision"])
        self.assertNotIn("ช่อง EV", report)
        self.assertNotIn("ทุ่ม reach", report)
        self.assertNotIn("observed affiliate_click distribution", report)
        self.assertIn("event density: suppressed", report)

    def test_unreconciled_revenue_is_unavailable_not_zero(self) -> None:
        blocked = {
            "trusted": False,
            "reconciliation_state": "UNRECONCILED",
            "error": "fixture metadata mismatch",
        }
        with tempfile.TemporaryDirectory(prefix="analytics_unreconciled_") as temp:
            with mock.patch.object(
                ANALYST.revenue_ledger, "read_affiliate_revenue", return_value=blocked
            ):
                result, report = self._run(Path(temp), True)
        self.assertIn("BLOCKED", result["verdict"])
        self.assertIn("verified affiliate revenue**: unavailable", report)
        self.assertIn("do not interpret as zero", report)
        self.assertNotIn("verified affiliate revenue (paid net of refunds)**: 0", report)

    def test_trusted_clicks_without_commission_are_intent_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_intent_") as temp:
            result, report = self._run(Path(temp), True)
        self.assertEqual(result["paid_affiliate_commission"], 0)
        self.assertIn("INTENT ONLY", result["verdict"])
        self.assertIn("ห้าม scale", result["decision"])
        self.assertIn("paid affiliate commission 0", report)
        self.assertNotIn("PROVEN:", report)

    def test_sales_schema_counts_confirmed_refunds_and_cancelled_correctly(self) -> None:
        rows = [
            sale("a01", "affiliate-commission", "paid", 100, 100, "atth"),
            sale("a02", "affiliate-commission", "paid", 20, 20, "atth"),
            sale(
                "a02", "affiliate-commission", "refunded", 20, -20, "atth",
                second=1,
            ),
            sale("a03", "affiliate-commission", "cancelled", 0, 0, "atth"),
            sale("e01", "ebook-59", "paid", 59, 59, "gumroad"),
        ]
        with tempfile.TemporaryDirectory(prefix="analytics_sales_") as temp:
            path = Path(temp) / "sales.jsonl"
            write(
                path,
                "".join(json.dumps(row) + "\n" for row in reconciled_sales(rows)),
            )
            with mock.patch.object(ANALYST, "SALES_LOG", str(path)):
                sales = ANALYST.read_sales(today=datetime.date(2026, 8, 16))
        self.assertTrue(sales["trusted"])
        self.assertEqual(sales["count"], 1)
        self.assertEqual(sales["baht"], 100)
        self.assertEqual(sales["affiliate_commission_count"], 1)
        self.assertEqual(sales["affiliate_commission_baht"], 100)


class PostTimingSafetyTests(unittest.TestCase):
    def test_untrusted_state_short_circuits_before_credentials_or_network(self) -> None:
        with mock.patch.object(TIMING.ga4_pull, "_get", side_effect=AssertionError("must not run")):
            by_hour, by_day, ok = TIMING.ga4_peaks(trust(False))
        self.assertEqual((by_hour, by_day, ok), ({}, {}, False))

    def test_trusted_query_uses_exact_28_day_window_and_host_filter(self) -> None:
        requests = []
        host_filter = object()

        class DateRange:
            def __init__(self, start_date, end_date):
                self.start_date = start_date
                self.end_date = end_date

        class Field:
            def __init__(self, name):
                self.name = name

        class Request:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                requests.append(self)

        class Client:
            def run_report(self, request):
                return types.SimpleNamespace(rows=[])

        data_module = types.ModuleType("google.analytics.data_v1beta")
        data_module.BetaAnalyticsDataClient = lambda credentials=None: Client()
        type_module = types.ModuleType("google.analytics.data_v1beta.types")
        type_module.RunReportRequest = Request
        type_module.DateRange = DateRange
        type_module.Dimension = Field
        type_module.Metric = Field
        with (
            mock.patch.dict(sys.modules, {
                "google.analytics.data_v1beta": data_module,
                "google.analytics.data_v1beta.types": type_module,
            }),
            mock.patch.object(TIMING.ga4_pull, "_get", return_value="123"),
            mock.patch.object(TIMING.ga4_pull, "_credentials", return_value=object()),
            mock.patch.object(TIMING.ga4_pull, "_api_window", return_value=("27daysAgo", "today")),
            mock.patch.object(TIMING.ga4_pull, "_host_exclude", return_value=host_filter),
        ):
            TIMING.ga4_peaks(trust(True))
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(request.date_ranges[0].start_date, "27daysAgo")
            self.assertEqual(request.date_ranges[0].end_date, "today")
            self.assertIs(request.dimension_filter, host_filter)


class PublicMetricSemanticsTests(unittest.TestCase):
    @staticmethod
    def _unavailable_sales():
        return {
            "trusted": False,
            "net_28d": None,
            "n_28d": None,
            "pending_28d": None,
            "pending_n_28d": None,
            "by_src": {},
            "pending_by_src": {},
            "state": "UNRECONCILED",
            "quality_state": "UNAVAILABLE",
            "expires_at": None,
            "error": "fixture unavailable",
        }

    def test_manual_gumroad_csv_is_never_treated_as_verified_revenue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_legacy_sales_") as temp:
            sales = Path(temp) / "gumroad-sales.csv"
            write(sales, "date,units,amount_thb\n2026-08-16,2,118\n")
            with mock.patch.object(MONITOR, "SALES", str(sales)):
                line, has_data = MONITOR.sales_summary()
        self.assertFalse(has_data)
        self.assertIn("UNRECONCILED", line)
        self.assertIn("excluded from verified revenue", line)
        self.assertIn("2 ชิ้น", line)
        self.assertNotIn("sales (Gumroad", line)

    def test_monitor_and_manual_feedback_label_clicks_as_intent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_labels_") as temp:
            root = Path(temp)
            metrics = root / "metrics.csv"
            ga4 = root / "ga4.csv"
            pages = root / "pages.csv"
            funnel = root / "funnel.csv"
            write(metrics, "source,topic,views,clicks,quiz_start,conversion\nfb,x,10,2,1,1\n")
            write(ga4, "source,sessions,quiz_start,affiliate_click\nfb,5,1,2\n")
            write(pages, "page,views,affiliate_click\n/x,5,2\n")
            write(funnel, "stage,count\nquiz_start,1\naffiliate_click,2\n")
            with (
                mock.patch.object(MONITOR, "METRICS", str(metrics)),
                mock.patch.object(MONITOR, "GA4_METRICS", str(ga4)),
                mock.patch.object(MONITOR, "GA4_PAGES", str(pages)),
                mock.patch.object(MONITOR, "GA4_FUNNEL", str(funnel)),
                mock.patch.object(MONITOR, "SALES", str(root / "missing-sales.csv")),
                mock.patch.object(MONITOR, "OUTDIR", str(root)),
                mock.patch.object(MONITOR, "ga4_trust", return_value=trust(True)),
            ):
                monitor_path = Path(MONITOR.run()["file"])
            monitor_text = monitor_path.read_text(encoding="utf-8")
            self.assertIn("legacy_intent", monitor_text)
            self.assertIn("affiliate_click (intent)", monitor_text)
            self.assertNotIn("| conversion |", monitor_text)

            messages = []
            with (
                mock.patch.object(METRICS, "SRC", str(metrics)),
                mock.patch.object(METRICS, "LOG", str(root)),
                mock.patch.object(METRICS.cc_bridge, "ping", side_effect=messages.append),
            ):
                feedback = Path(METRICS.main())
            feedback_text = feedback.read_text(encoding="utf-8")
            self.assertIn("legacy_intent", feedback_text)
            self.assertIn("not revenue / not scale", feedback_text)
            self.assertNotIn("หัวข้อที่ควรดันต่อ", feedback_text)
            self.assertIn("not revenue / not scale", messages[0])

    def test_dashboard_labels_ga4_clicks_as_observed_intent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_dashboard_") as temp:
            root = Path(temp)
            inbox = root / "cowork-inbox"
            inbox.mkdir()
            write(root / "ga4-metrics.csv",
                  "source,sessions,quiz_start,affiliate_click\nfb,5,1,2\n")
            write(
                root / "post-queue-20260816.md",
                "| เวลา | งาน |\n|---|---|\n| 19:00 | must-not-leak-untrusted-timing |\n",
            )
            sales = root / "sales.jsonl"
            write(sales, "")
            output = root / "dashboard.html"
            blocked_readiness = types.SimpleNamespace(
                ga4=trust(False), gsc=trust(False), observation=None,
            )
            with (
                mock.patch.object(DASHBOARD, "AL", str(root)),
                mock.patch.object(DASHBOARD, "INBOX", str(inbox)),
                mock.patch.object(DASHBOARD, "OUT", str(output)),
                mock.patch.object(DASHBOARD, "SALES_LOG_FILE", sales),
                mock.patch.object(
                    DASHBOARD.decision_readiness, "read",
                    return_value=blocked_readiness,
                ),
            ):
                DASHBOARD.build(
                    now=datetime.datetime(2026, 8, 16, 8, tzinfo=datetime.timezone.utc)
                )
            text = output.read_text(encoding="utf-8")
            self.assertIn("affiliate_click รายช่อง", text)
            self.assertIn("intent only", text)
            self.assertIn("UNTRUSTED", text)
            self.assertIn('name="ngernduangold-revenue-trusted" content="false"', text)
            self.assertIn('name="ngernduangold-revenue-state" content="UNRECONCILED"', text)
            self.assertIn(
                'name="ngernduangold-revenue-pending-amount-thb" content="UNAVAILABLE"',
                text,
            )
            self.assertIn('name="ngernduangold-dashboard-producer-sha256"', text)
            self.assertIn('name="ngernduangold-analytics-input-sha256"', text)
            self.assertIn('name="ngernduangold-analytics-reader-sha256"', text)
            self.assertIn('name="ngernduangold-ga4-trusted" content="false"', text)
            self.assertIn('name="ngernduangold-ga4-state" content="INVALID_METADATA"', text)
            self.assertIn('name="ngernduangold-gsc-trusted" content="false"', text)
            self.assertIn('name="ngernduangold-gsc-state" content="INVALID_METADATA"', text)
            self.assertIn(
                'data-dashboard-metric="revenue-28d" style="color:#3ddc97">UNAVAILABLE',
                text,
            )
            self.assertIn(
                'data-dashboard-metric="revenue-pending-amount">UNAVAILABLE', text,
            )
            self.assertIn(
                'data-dashboard-metric="gsc-impressions">UNAVAILABLE', text,
            )
            self.assertIn('data-dashboard-metric="gsc-clicks">UNAVAILABLE', text)
            self.assertIn('data-dashboard-metric="ga4-sessions">UNAVAILABLE', text)
            self.assertNotIn('data-dashboard-metric="ga4-sessions">5', text)
            self.assertIn("ห้ามตีความเป็นศูนย์", text)
            self.assertNotIn("0฿ สุทธิใน 28 วัน", text)
            self.assertNotIn("reconciled source export ยืนยัน 0 paid", text)
            self.assertNotIn("conversion รายช่อง", text)
            self.assertIn("timing/cadence UNAVAILABLE", text)
            self.assertNotIn("must-not-leak-untrusted-timing", text)
            self.assertNotIn("เวลาดีสุดจาก GA4", text)

    def test_dashboard_rejects_sales_input_changed_during_semantic_read(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dashboard_sales_race_") as temp:
            root = Path(temp)
            inbox = root / "cowork-inbox"
            inbox.mkdir()
            sales_path = root / "sales.jsonl"
            write(sales_path, "before\n")
            blocked = types.SimpleNamespace(
                ga4=trust(False), gsc=trust(False), observation=None,
            )

            def mutate_sales(**_kwargs):
                write(sales_path, "after\n")
                return self._unavailable_sales()

            with (
                mock.patch.object(DASHBOARD, "AL", str(root)),
                mock.patch.object(DASHBOARD, "INBOX", str(inbox)),
                mock.patch.object(DASHBOARD, "OUT", str(root / "dashboard.html")),
                mock.patch.object(DASHBOARD, "SALES_LOG_FILE", sales_path),
                mock.patch.object(DASHBOARD.decision_readiness, "read", return_value=blocked),
                mock.patch.object(DASHBOARD, "_sales", side_effect=mutate_sales),
            ):
                with self.assertRaisesRegex(RuntimeError, "sales input changed"):
                    DASHBOARD.build(
                        now=datetime.datetime(
                            2026, 8, 16, 8, tzinfo=datetime.timezone.utc
                        )
                    )

    def test_dashboard_rejects_transitive_reader_changed_during_build(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dashboard_reader_race_") as temp:
            root = Path(temp)
            inbox = root / "cowork-inbox"
            inbox.mkdir()
            sales_path = root / "sales.jsonl"
            reader = root / "content_source_gate.py"
            write(sales_path, "")
            write(reader, "before\n")
            blocked = types.SimpleNamespace(
                ga4=trust(False), gsc=trust(False), observation=None,
            )

            def mutate_reader(**_kwargs):
                write(reader, "after\n")
                return blocked

            with (
                mock.patch.object(DASHBOARD, "AL", str(root)),
                mock.patch.object(DASHBOARD, "INBOX", str(inbox)),
                mock.patch.object(DASHBOARD, "OUT", str(root / "dashboard.html")),
                mock.patch.object(DASHBOARD, "SALES_LOG_FILE", sales_path),
                mock.patch.object(DASHBOARD, "ANALYTICS_READER_FILES", (reader,)),
                mock.patch.object(DASHBOARD.decision_readiness, "read", side_effect=mutate_reader),
                mock.patch.object(
                    DASHBOARD, "_sales", return_value=self._unavailable_sales()
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "analytics readers changed"):
                    DASHBOARD.build(
                        now=datetime.datetime(
                            2026, 8, 16, 8, tzinfo=datetime.timezone.utc
                        )
                    )

    def test_dashboard_hides_stale_operational_claims(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_stale_ops_") as temp:
            root = Path(temp)
            write(
                root / "launch-status.json",
                json.dumps({
                    "updated": "2026-07-01 — old status",
                    "product": "old product",
                    "channels": [{
                        "name": "external endpoint",
                        "st": "ok",
                        "note": "STALE-LIVE-CLAIM-MUST-NOT-RENDER",
                    }],
                    "pending": ["STALE-PENDING-MUST-NOT-RENDER"],
                }),
            )
            write(
                root / "LINE-FUNNEL-FIX_20260701.md",
                "แชท | 🔴 ปิด | ✅ เปิด\n",
            )
            with mock.patch.object(DASHBOARD, "AL", str(root)):
                launch = DASHBOARD._launch(today=datetime.date(2026, 8, 16))
                funnel = DASHBOARD._funnel(today=datetime.date(2026, 8, 16))
        self.assertIn("UNVERIFIED", launch)
        self.assertNotIn("STALE-LIVE-CLAIM-MUST-NOT-RENDER", launch)
        self.assertNotIn("STALE-PENDING-MUST-NOT-RENDER", launch)
        self.assertIsNone(funnel["ok"])
        self.assertIn("UNVERIFIED", funnel["state"])
        self.assertNotIn("แชทเปิด + auto-reply 24 ชม.", funnel["state"])

    def test_dashboard_keeps_pending_commission_out_of_paid_revenue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_pending_dashboard_") as temp:
            root = Path(temp)
            inbox = root / "cowork-inbox"
            inbox.mkdir()
            write(root / "ga4-metrics.csv",
                  "source,sessions,quiz_start,affiliate_click\nfb,5,1,2\n")
            output = root / "dashboard.html"
            blocked_readiness = types.SimpleNamespace(
                ga4=trust(False), gsc=trust(False), observation=None,
            )
            sales = {
                "trusted": True,
                "net_28d": 0.0,
                "n_28d": 0,
                "pending_28d": 35.0,
                "pending_n_28d": 1,
                "by_src": {},
                "pending_by_src": {"atth": 35.0},
                "state": "RECONCILED",
                "quality_state": "CURRENT",
                "expires_at": "2026-08-17T00:00:00+07:00",
                "error": "",
            }
            with (
                mock.patch.object(DASHBOARD, "AL", str(root)),
                mock.patch.object(DASHBOARD, "INBOX", str(inbox)),
                mock.patch.object(DASHBOARD, "OUT", str(output)),
                mock.patch.object(
                    DASHBOARD.decision_readiness, "read",
                    return_value=blocked_readiness,
                ),
                mock.patch.object(DASHBOARD, "_sales", return_value=sales),
            ):
                DASHBOARD.build(
                    now=datetime.datetime(2026, 8, 16, 8, tzinfo=datetime.timezone.utc)
                )
            text = output.read_text(encoding="utf-8")
            self.assertIn(
                'name="ngernduangold-revenue-paid-net-thb" content="0.00"', text,
            )
            self.assertIn(
                'name="ngernduangold-revenue-pending-amount-thb" content="35.00"',
                text,
            )
            self.assertIn('data-dashboard-metric="revenue-28d" style="color:#3ddc97">0.00฿', text)
            self.assertIn('data-dashboard-metric="revenue-paid-count">0', text)
            self.assertIn('data-dashboard-metric="revenue-pending-count">1', text)
            self.assertIn('data-dashboard-metric="revenue-pending-amount">35.00฿', text)
            self.assertIn("Pending commission — not paid revenue", text)
            self.assertNotIn('data-dashboard-metric="revenue-28d" style="color:#3ddc97">35.00฿', text)
            self.assertIn(
                'name="ngernduangold-revenue-expires-at" '
                'content="2026-08-16T17:00:00+00:00"',
                text,
            )
            self.assertIn("Date.now() >= deadline", text)
            self.assertIn("STALE_AT_VIEW", text)

    def test_dashboard_headlines_use_strict_observation_metric_grain(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics_grain_dashboard_") as temp:
            root = Path(temp)
            inbox = root / "cowork-inbox"
            inbox.mkdir()
            write(
                root / "ga4-metrics.csv",
                "source,sessions,quiz_start,affiliate_click\nfb,5,1,2\n",
            )
            # Query totals can be lower because anonymized queries are omitted.
            write(
                root / "gsc-queries.csv",
                "query,clicks,impressions,ctr,position\nloan,1,10,10,2\n",
            )
            write(
                root / "gsc-pages.csv",
                "page,clicks,impressions,ctr,position\n/x,3,30,10,2\n",
            )
            output = root / "dashboard.html"
            ready = types.SimpleNamespace(
                ga4=trust(True),
                gsc=trust(True),
                observation={"metrics": {
                    "ga4_observed_not_decisionable_unless_trusted": {
                        "sessions": 5,
                    },
                    "gsc_observed_not_decisionable_unless_current": {
                        "clicks": 3,
                        "impressions": 30,
                    },
                }},
            )
            unavailable_sales = {
                "trusted": False,
                "net_28d": None,
                "n_28d": None,
                "pending_28d": None,
                "pending_n_28d": None,
                "by_src": {},
                "pending_by_src": {},
                "state": "UNRECONCILED",
                "quality_state": "UNAVAILABLE",
                "expires_at": None,
                "error": "fixture unavailable",
            }
            with (
                mock.patch.object(DASHBOARD, "AL", str(root)),
                mock.patch.object(DASHBOARD, "INBOX", str(inbox)),
                mock.patch.object(DASHBOARD, "OUT", str(output)),
                mock.patch.object(DASHBOARD.decision_readiness, "read", return_value=ready),
                mock.patch.object(DASHBOARD, "_sales", return_value=unavailable_sales),
            ):
                DASHBOARD.build(
                    now=datetime.datetime(2026, 8, 16, 8, tzinfo=datetime.timezone.utc)
                )
            text = output.read_text(encoding="utf-8")
            self.assertIn(
                'name="ngernduangold-ga4-metric-grain" '
                'content="ga4-metrics-source-session-total"',
                text,
            )
            self.assertIn(
                'name="ngernduangold-gsc-metric-grain" '
                'content="gsc-pages-url-total"',
                text,
            )
            self.assertIn('data-dashboard-metric="ga4-sessions">5', text)
            self.assertIn('data-dashboard-metric="gsc-impressions">30', text)
            self.assertIn('data-dashboard-metric="gsc-clicks">3', text)
            self.assertNotIn('data-dashboard-metric="gsc-impressions">10', text)

    def test_dashboard_downgrades_trust_when_strict_metric_is_malformed(self) -> None:
        ready = types.SimpleNamespace(
            ga4=trust(True),
            gsc=trust(True),
            observation={"metrics": {
                "ga4_observed_not_decisionable_unless_trusted": {
                    "sessions": "5",
                },
                "gsc_observed_not_decisionable_unless_current": {
                    "clicks": 3,
                    "impressions": 30,
                },
            }},
        )
        metrics = DASHBOARD._canonical_analytics_metrics(ready)
        ga4 = DASHBOARD._bind_metric_trust(ready.ga4, metrics["ga4"], "GA4")
        self.assertFalse(ga4.trusted)
        self.assertEqual(ga4.state, "INVALID_METRIC")
        self.assertIsNone(metrics["ga4"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
