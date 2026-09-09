#!/usr/bin/env python3
"""Regression tests for the exact-copy evergreen weekly-pack guard."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import week_content_freshness_guard as guard


NOW = datetime.fromisoformat("2026-08-23T20:20:00+07:00")


class WeekContentFreshnessGuardTests(unittest.TestCase):
    def _evaluate_fresh_fixture(self, mutate_binding=None):
        """Build a self-contained receipt so dated workspace state cannot flake."""
        pack = json.loads(guard.DEFAULT_PACK.read_text(encoding="utf-8"))
        snapshot = json.loads(guard.DEFAULT_SNAPSHOT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot_path = root / "official-news-snapshot.json"
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            binding_paths = {
                "content_calendar_sha256": root / "content-calendar.json",
                "policy_sha256": root / "policy.json",
                "post_ledger_sha256": root / "post-ledger.jsonl",
                "official_news_snapshot_sha256": snapshot_path,
            }
            for field, path in binding_paths.items():
                if field != "official_news_snapshot_sha256":
                    path.write_text(field + "\n", encoding="utf-8")
                    pack["source_binding"][field] = guard._file_sha256(path)
            # The evergreen lane deliberately preserves the historical global
            # news binding as stale; it does not claim that news was reviewed.
            pack["source_binding"]["official_news_snapshot_sha256"] = "0" * 64
            pack_path = root / "pack.json"
            pack_path.write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            receipt_path = root / "receipt.json"
            with patch.dict(guard.BINDING_PATHS, binding_paths, clear=True):
                receipt = guard.build_receipt_document(
                    pack_path,
                    snapshot_path,
                    checked_at="2026-08-23T20:14:30+07:00",
                )
                receipt_path.write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                if mutate_binding is not None:
                    mutate_binding(binding_paths)
                with patch(
                    "tools.content_source_gate.validate_official_snapshot_contract",
                    return_value=SimpleNamespace(allowed=True, failures=()),
                ):
                    return guard.evaluate(
                        pack_path,
                        receipt_path,
                        snapshot_path,
                        now=NOW,
                    )

    def test_fresh_exact_copy_receipt_proves_authoring_but_never_publication(self):
        result = self._evaluate_fresh_fixture()
        self.assertEqual(result["freshness_verdict"], "PASS_EVERGREEN_EXACT_COPY")
        self.assertEqual(result["process_state"], "COMPLETED_BLOCKED")
        self.assertFalse(result["publication_ready"])
        self.assertEqual(result["official_news_scope"], [])
        self.assertEqual(result["candidate_count"], 7)
        self.assertTrue(all(row["status"].startswith("PASS_") for row in result["candidates"]))
        news = result["binding_check"]["official_news_snapshot_sha256"]
        self.assertFalse(news["match"])
        self.assertTrue(any("not auto-refreshed" in item for item in result["global_findings"]))

    def test_receipt_fails_closed_when_a_bound_input_changes(self):
        result = self._evaluate_fresh_fixture(
            lambda paths: paths["content_calendar_sha256"].write_text(
                "changed after receipt\n", encoding="utf-8"
            )
        )
        self.assertEqual(result["freshness_verdict"], "BLOCKED")
        self.assertFalse(result["publication_ready"])
        self.assertTrue(any(
            "content_calendar_sha256: dated binding evidence changed"
            in item for item in result["findings"]
        ))

    def _evaluate_mutation(self, mutate):
        pack = json.loads(guard.DEFAULT_PACK.read_text(encoding="utf-8"))
        mutate(pack)
        with tempfile.TemporaryDirectory() as temp:
            pack_path = Path(temp) / "pack.json"
            pack_path.write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return guard.evaluate(
                pack_path,
                guard.DEFAULT_RECEIPT,
                guard.DEFAULT_SNAPSHOT,
                now=NOW,
            )

    def test_any_copy_edit_breaks_the_frozen_pack_and_piece_hash(self):
        result = self._evaluate_mutation(
            lambda pack: pack["days"][0].__setitem__(
                "threads_text", pack["days"][0]["threads_text"] + " เพิ่มอีกหนึ่งบรรทัด"
            )
        )
        self.assertEqual(result["freshness_verdict"], "BLOCKED")
        self.assertTrue(any("frozen weekly pack SHA-256" in item for item in result["findings"]))
        self.assertTrue(any("public-copy SHA-256" in item for item in result["findings"]))

    def test_promo_rate_or_current_claim_fails_even_if_receipt_were_rebuilt(self):
        pack = json.loads(guard.DEFAULT_PACK.read_text(encoding="utf-8"))
        pack["days"][0]["threads_text"] += " โปรล่าสุด ดอกเบี้ย 9.99% สมัครวันนี้"
        risks = guard._risk_findings(pack["days"][0])
        codes = {item["code"] for item in risks}
        self.assertIn("rate_price_fee_or_return_claim", codes)
        self.assertIn("promotion_or_currentness_claim", codes)
        self.assertIn("affiliate_or_conversion_cta", codes)

    def test_source_required_candidate_cannot_enter_evergreen_lane(self):
        def mutate(pack):
            pack["days"][0]["source_ids"] = ["bot-credit-card-guidance"]
            pack["days"][0]["source_review"] = "PASS"

        result = self._evaluate_mutation(mutate)
        self.assertEqual(result["freshness_verdict"], "BLOCKED")
        self.assertTrue(any(
            "source-required/factual candidate" in item for item in result["findings"]
        ))

        pack = json.loads(guard.DEFAULT_PACK.read_text(encoding="utf-8"))
        mutate(pack)
        with tempfile.TemporaryDirectory() as temp:
            pack_path = Path(temp) / "pack.json"
            pack_path.write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            generated = guard.build_receipt_document(
                pack_path,
                guard.DEFAULT_SNAPSHOT,
                checked_at="2026-08-23T20:14:30+07:00",
            )
        self.assertEqual(
            generated["assessment"]["freshness_verdict"],
            "BLOCKED_FACTUAL_OR_PROMOTIONAL_COPY",
        )
        self.assertTrue(any(
            "source-required/factual candidate" in item
            for item in generated["assessment"]["authoring_findings"]
        ))

    def test_receipt_cannot_claim_publication_authority(self):
        receipt = json.loads(guard.DEFAULT_RECEIPT.read_text(encoding="utf-8"))
        receipt["assessment"]["publication_ready"] = True
        with tempfile.TemporaryDirectory() as temp:
            receipt_path = Path(temp) / "receipt.json"
            receipt_path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            result = guard.evaluate(
                guard.DEFAULT_PACK,
                receipt_path,
                guard.DEFAULT_SNAPSHOT,
                now=NOW,
            )
        self.assertEqual(result["freshness_verdict"], "BLOCKED")
        self.assertFalse(result["publication_ready"])
        self.assertTrue(any("never claim publication readiness" in item for item in result["findings"]))

    def test_receipt_expires_after_the_scheduled_week(self):
        result = guard.evaluate(
            now=datetime.fromisoformat("2026-08-31T00:00:00+07:00")
        )
        self.assertEqual(result["freshness_verdict"], "BLOCKED")
        self.assertTrue(any("expired after its scheduled week" in item for item in result["findings"]))

    def test_receipt_builder_does_not_refresh_pack_snapshot_binding(self):
        generated = guard.build_receipt_document(
            checked_at="2026-08-23T20:14:30+07:00"
        )
        news = generated["official_news_snapshot"]
        pack = json.loads(guard.DEFAULT_PACK.read_text(encoding="utf-8"))
        self.assertEqual(
            news["pack_recorded_sha256"],
            pack["source_binding"]["official_news_snapshot_sha256"],
        )
        self.assertNotEqual(news["pack_recorded_sha256"], news["observed_sha256"])
        self.assertEqual(news["binding_status"], "STALE_NOT_AUTO_REFRESHED")
        self.assertEqual(generated["scope"]["official_source_ids"], [])
        self.assertFalse(generated["assessment"]["publication_ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
