#!/usr/bin/env python3
"""Regression tests for fail-closed weekly-report evidence prose."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import decision_readiness
    import report_trust_guard
    import weekly_growth_review
except ImportError:  # package import path
    from pipeline import decision_readiness, report_trust_guard, weekly_growth_review


def source(state: str, ready: bool) -> SimpleNamespace:
    return SimpleNamespace(
        trusted=ready,
        label="CURRENT" if ready else "UNTRUSTED",
        reason="fixture",
        schema="fixture",
        state=state,
        expires_at="2099-01-01T00:00:00+00:00" if ready else None,
    )


def blocked_readiness() -> SimpleNamespace:
    return SimpleNamespace(
        ga4=source("INVALID_METADATA", False),
        gsc=source("STALE_WINDOW", False),
        revenue=source("STALE_COVERAGE", False),
        observation=None,
    )


class ReportTrustGuardTests(unittest.TestCase):
    def test_stale_sources_cannot_be_promoted_in_prose(self) -> None:
        readiness = blocked_readiness()
        report = "\n".join(
            report_trust_guard.canonical_block(readiness)
            + [
                "ตัวหลักที่เชื่อได้รอบนี้ = GSC (CURRENT)",
                "verified affiliate revenue: 0",
            ]
        )
        errors = report_trust_guard.validate_report(report, readiness)
        self.assertTrue(any("promotes GSC" in error for error in errors))
        self.assertTrue(any("revenue into zero" in error for error in errors))

    def test_blocked_source_cannot_hide_behind_unlabelled_action(self) -> None:
        readiness = blocked_readiness()
        report = "\n".join(
            report_trust_guard.canonical_block(readiness)
            + ["winner สัปดาห์นี้คือหน้าสินเชื่อ ให้ดันซ้ำทันที"]
        )
        errors = report_trust_guard.validate_report(report, readiness)
        self.assertTrue(any("without an explicit evidence basis" in error for error in errors))

    def test_blocked_source_cannot_be_an_explicit_action_basis(self) -> None:
        readiness = blocked_readiness()
        report = "\n".join(
            report_trust_guard.canonical_block(readiness)
            + ["ACTION [basis=GSC]: ปรับ title ของหน้าที่อันดับตก"]
        )
        errors = report_trust_guard.validate_report(report, readiness)
        self.assertTrue(any("uses blocked GSC" in error for error in errors))

    def test_local_policy_repair_action_remains_allowed(self) -> None:
        readiness = blocked_readiness()
        report = "\n".join(
            report_trust_guard.canonical_block(readiness)
            + ["ACTION [basis=LOCAL_POLICY]: แก้โครงสร้างหลักฐานก่อนวิเคราะห์"]
        )
        self.assertEqual(report_trust_guard.validate_report(report, readiness), [])

    def test_own_product_sales_need_separate_paid_and_fulfilled_evidence(self) -> None:
        readiness = blocked_readiness()
        readiness.revenue = source("CURRENT", True)
        report = "\n".join(
            report_trust_guard.canonical_block(readiness)
            + ["ยอดขายชุดจดหมาย 199฿ จริง = 1 รายการ"]
        )
        errors = report_trust_guard.validate_report(report, readiness)
        self.assertTrue(any("paid-and-fulfilled ledger" in error for error in errors))

    def test_matching_blocked_prose_passes(self) -> None:
        readiness = blocked_readiness()
        report = "\n".join(
            report_trust_guard.canonical_block(readiness)
            + [
                "GSC = STALE_WINDOW / BLOCKED — ห้ามใช้เลือกคีย์",
                "ยอดขายจริง — UNRECONCILED (ไม่ใช่ 0)",
            ]
        )
        self.assertEqual(report_trust_guard.validate_report(report, readiness), [])

    def test_marker_must_match_current_canonical_states(self) -> None:
        stale = blocked_readiness()
        current = SimpleNamespace(
            ga4=stale.ga4,
            gsc=source("CURRENT", True),
            revenue=stale.revenue,
            observation=None,
        )
        old_report = "\n".join(report_trust_guard.canonical_block(stale))
        errors = report_trust_guard.validate_report(old_report, current)
        self.assertIn("canonical evidence marker is missing or mismatched", errors)

    def test_source_marker_is_revalidated_against_current_canonical_state(self) -> None:
        readiness = blocked_readiness()
        source_report = "\n".join(report_trust_guard.canonical_block(readiness))
        recovered = report_trust_guard.readiness_from_marker(source_report)
        self.assertEqual(recovered.gsc.state, "STALE_WINDOW")
        self.assertFalse(recovered.gsc.trusted)
        promoted = source_report + "\nตัวหลักที่เชื่อได้ = GSC (CURRENT)\n"
        with tempfile.TemporaryDirectory(prefix="report_guard_cli_") as temp:
            root = Path(temp)
            source_path = root / "source.md"
            report_path = root / "report.md"
            source_path.write_text(source_report, encoding="utf-8")
            report_path.write_text(promoted, encoding="utf-8")
            with mock.patch.object(
                report_trust_guard.decision_readiness,
                "read",
                return_value=readiness,
            ):
                result = report_trust_guard.main([
                    "--source-report", str(source_path),
                    "--report", str(report_path),
                ])
        self.assertEqual(result, 2)

    def test_forged_ready_source_marker_cannot_override_current_block(self) -> None:
        current = blocked_readiness()
        forged = SimpleNamespace(
            ga4=source("CURRENT", True),
            gsc=source("CURRENT", True),
            revenue=source("CURRENT", True),
            observation=None,
        )
        source_report = "\n".join(report_trust_guard.canonical_block(forged))
        with tempfile.TemporaryDirectory(prefix="report_guard_forged_") as temp:
            root = Path(temp)
            source_path = root / "source.md"
            report_path = root / "report.md"
            source_path.write_text(source_report, encoding="utf-8")
            report_path.write_text(source_report, encoding="utf-8")
            with mock.patch.object(
                report_trust_guard.decision_readiness,
                "read",
                return_value=current,
            ):
                result = report_trust_guard.main([
                    "--source-report", str(source_path),
                    "--report", str(report_path),
                ])
        self.assertEqual(result, 2)


class DecisionReadinessRevenueTests(unittest.TestCase):
    def test_stale_revenue_is_exposed_as_untrusted(self) -> None:
        now = dt.datetime(2026, 8, 30, 0, 0, tzinfo=dt.timezone.utc)
        observed = {
            "observed_at": now.isoformat(),
            "sources": {
                "ga4": {"bundle": {
                    "decisionable": True, "state": "CURRENT",
                    "capture_trust": "TRUSTED", "current_trust": "TRUSTED",
                    "expires_at": "2026-08-31T00:00:00+00:00",
                }},
                "gsc": {"bundle": {
                    "decisionable": True, "state": "CURRENT",
                    "expires_at": "2026-08-31T00:00:00+00:00",
                }},
                "revenue_ledger": {
                    "trusted": False, "learning_ready": False,
                    "quality_state": "STALE_COVERAGE",
                    "reconcile_required": True,
                },
            },
            "learning_readiness": {"sources": {"revenue": {
                "ready": False, "state": "STALE_COVERAGE",
            }}},
        }
        with mock.patch.object(
            decision_readiness.observation_snapshot, "collect", return_value=observed
        ):
            readiness = decision_readiness.read(now=now)
        self.assertFalse(readiness.revenue.trusted)
        self.assertEqual(readiness.revenue.state, "STALE_COVERAGE")
        self.assertEqual(readiness.revenue.label, "UNTRUSTED")


class WeeklyGrowthReportTests(unittest.TestCase):
    def test_stale_gsc_is_bound_and_cannot_emit_seo_actions(self) -> None:
        readiness = blocked_readiness()
        with tempfile.TemporaryDirectory(prefix="weekly_report_trust_") as temp:
            root = Path(temp)
            inbox = root / "inbox"
            ga4 = root / "ga4.csv"
            pages = root / "ga4-pages.csv"
            gsc = root / "gsc.csv"
            gsc_pages = root / "gsc-pages.csv"
            ga4.write_text(
                "source,sessions,quiz_start,affiliate_click\nfb,10,0,1\n",
                encoding="utf-8",
            )
            pages.write_text(
                "page,views,affiliate_click\n/offer,10,1\n", encoding="utf-8"
            )
            gsc.write_text(
                "query,clicks,impressions,ctr,position\nloan,0,10,0,9\n",
                encoding="utf-8",
            )
            gsc_pages.write_text(
                "page,clicks,impressions,ctr,position\n/offer,0,10,0,30\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(weekly_growth_review, "LOG", str(root)),
                mock.patch.object(weekly_growth_review, "INBOX", str(inbox)),
                mock.patch.object(weekly_growth_review, "GA4", str(ga4)),
                mock.patch.object(weekly_growth_review, "PAGES", str(pages)),
                mock.patch.object(weekly_growth_review, "GSC", str(gsc)),
                mock.patch.object(weekly_growth_review, "GSCP", str(gsc_pages)),
                mock.patch.object(
                    weekly_growth_review, "_decision_readiness",
                    return_value=readiness,
                ),
            ):
                output = Path(weekly_growth_review.main())
            report = output.read_text(encoding="utf-8")
        self.assertIn("GSC=STALE_WINDOW|BLOCKED", report)
        self.assertIn("REVENUE=STALE_COVERAGE|BLOCKED", report)
        self.assertIn("DECISION BLOCK", report)
        self.assertNotIn("Striking distance —", report)
        self.assertNotIn("หน้าได้ impression สูงสุด", report)
        self.assertNotIn("ทำต่อ: ปรับ title", report)
        self.assertEqual(
            report_trust_guard.validate_report(report, readiness), []
        )

    def test_producer_refuses_to_write_report_when_guard_fails(self) -> None:
        readiness = blocked_readiness()
        with tempfile.TemporaryDirectory(prefix="weekly_report_fail_closed_") as temp:
            root = Path(temp)
            inbox = root / "inbox"
            with (
                mock.patch.object(weekly_growth_review, "LOG", str(root)),
                mock.patch.object(weekly_growth_review, "INBOX", str(inbox)),
                mock.patch.object(
                    weekly_growth_review, "_decision_readiness",
                    return_value=readiness,
                ),
                mock.patch.object(
                    weekly_growth_review.report_trust_guard,
                    "validate_report",
                    return_value=["fixture contradiction"],
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "fixture contradiction"):
                    weekly_growth_review.main()
            self.assertEqual(list(root.glob("weekly-growth-*.md")), [])
            self.assertFalse(inbox.exists())

    def test_task_producer_requires_guard_and_verbatim_states(self) -> None:
        task = (
            Path(__file__).resolve().parents[1]
            / "automation-log" / "_task_weekly-review_SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("canonical-evidence-state:v1", task)
        self.assertIn("report_trust_guard.py --source-report", task)
        self.assertIn("--report automation-log\\WEEKLY-REVIEW_", task)
        self.assertIn("ห้ามเขียนยกระดับ", task)
        self.assertIn("LOCAL-ONLY EVIDENCE REVIEW", task)
        self.assertIn("[basis=LOCAL_POLICY]", task)
        self.assertNotIn("AUTO FAST-PATH", task)
        self.assertNotIn("git commit", task)
        self.assertNotIn("git push", task)


if __name__ == "__main__":
    unittest.main(verbosity=2)
