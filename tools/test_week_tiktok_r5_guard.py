#!/usr/bin/env python3
"""Contract tests for the independent weekly TikTok r5 technical guard."""

from pathlib import Path
import json
import unittest

from tools import week_tiktok_r5_guard as guard


ROOT = Path(__file__).resolve().parents[1]


class WeekTikTokR5GuardTests(unittest.TestCase):
    def test_guard_source_has_fail_closed_audio_and_timing_checks(self):
        source = (ROOT / "tools" / "week_tiktok_r5_guard.py").read_text(
            encoding="utf-8"
        )
        for required in (
            "audio_input_count",
            "ambient_or_music_sources",
            "foreign_audio_sources",
            "final audio packets are not copied",
            "post-narration tail exceeds one second",
            "fresh decoded frame count",
            "exact visible copy",
            "fresh watermark scan",
            "fresh loudness/true-peak guard",
        ):
            self.assertIn(required, source)

    def test_live_pack_is_fail_closed_or_all_r5_bindings_pass(self):
        live = json.loads(guard.PACK_PATH.read_text(encoding="utf-8"))
        blockers = live["global_blockers"]
        if "tiktok_audio_rework_in_progress_no_partial_binding" in blockers:
            self.assertEqual(live["pack_id"], "week-content-20260824-30-r4")
            self.assertTrue(
                all(
                    day["tiktok_draft"]["audio_qa"]
                    == "BLOCKED_REWORK_IN_PROGRESS"
                    for day in live["days"]
                )
            )
            return
        self.assertEqual(live["pack_id"], guard.renderer.TARGET_PACK_ID)
        for day in live["days"]:
            binding = day["tiktok_draft"]["candidate_asset"]
            result = guard.evaluate(binding["path"], binding["qa_receipt"])
            self.assertEqual(result["verdict"], "PASS", result["findings"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
