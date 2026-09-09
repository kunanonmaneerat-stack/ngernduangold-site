#!/usr/bin/env python3
"""Fail-closed tests for the deterministic weekly TikTok candidate renderer."""

from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "render_week_tiktok_candidates.py"
SPEC = importlib.util.spec_from_file_location("week_tiktok_renderer", MODULE_PATH)
renderer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(renderer)


class WeeklyTikTokRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack, cls.days = renderer.load_candidates()

    def test_exact_candidate_set_and_draft_only_state(self):
        self.assertEqual(self.pack["state"], "DRAFT_ONLY")
        self.assertEqual(
            tuple(day["candidate_id"] for day in self.days), renderer.EXPECTED_IDS
        )

    def test_visible_copy_is_exact_pack_copy(self):
        for day in self.days:
            draft = day["tiktok_draft"]
            self.assertEqual(
                renderer.scene_texts(day),
                [draft["hook"], *draft["onscreen_text"], draft["end_card"]],
            )
            self.assertEqual(draft["end_card"], "ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI")

    def test_scene_frame_allocation_is_exact(self):
        for day in self.days:
            scene_count = len(renderer.scene_texts(day))
            minimum_frames = (
                (scene_count - 1)
                * int(renderer.MIN_SCENE_DWELL_SECONDS * renderer.FPS)
                + int(renderer.MIN_END_CARD_DWELL_SECONDS * renderer.FPS)
            )
            duration = minimum_frames / renderer.FPS
            counts = renderer.scene_frame_counts(duration, scene_count)
            self.assertEqual(sum(counts), minimum_frames)
            self.assertGreaterEqual(
                min(counts[:-1]), renderer.MIN_SCENE_DWELL_SECONDS * renderer.FPS
            )
            self.assertGreaterEqual(
                counts[-1], renderer.MIN_END_CARD_DWELL_SECONDS * renderer.FPS
            )

    def test_documents_are_vertical_and_contain_no_outward_identity(self):
        for day in self.days:
            texts = renderer.scene_texts(day)
            for index, text in enumerate(texts):
                document = renderer.scene_document(day, text, index, len(texts))
                self.assertIn("width:1080px", document)
                self.assertIn("height:1920px", document)
                self.assertIn(text, document)
                for forbidden in renderer.FORBIDDEN_VISIBLE:
                    self.assertNotIn(forbidden.casefold(), document.casefold())
                self.assertNotIn("@", document)

    def test_content_payload_excludes_mutable_media_fields(self):
        for day in self.days:
            payload = renderer._content_payload(day["tiktok_draft"])
            self.assertNotIn("media_status", payload)
            self.assertNotIn("watermark_qa", payload)
            self.assertEqual(payload["voiceover"], day["tiktok_draft"]["voiceover"])

    def test_bound_candidate_assets_and_receipts_match_exact_bytes(self):
        live_pack = json.loads(renderer.PACK_PATH.read_text(encoding="utf-8"))
        blockers = live_pack["global_blockers"]
        if "tiktok_audio_rework_in_progress_no_partial_binding" in blockers:
            self.assertTrue(live_pack["pack_id"].endswith("-r4"))
            self.assertTrue(
                all(
                    day["tiktok_draft"]["audio_qa"] == "BLOCKED_REWORK_IN_PROGRESS"
                    for day in live_pack["days"]
                )
            )
            return

        self.assertTrue(live_pack["pack_id"].endswith("-r5"))
        for day in self.days:
            draft = day["tiktok_draft"]
            self.assertEqual(draft["media_status"], "CANDIDATE_PRODUCED_LOCAL_ONLY")
            self.assertEqual(draft["visual_qa"], "PASS")
            self.assertEqual(draft["watermark_qa"], "PASS")
            self.assertEqual(
                draft["audio_qa"],
                "SOURCE_TEXT_BOUND_TECHNICAL_PASS_VOICE_ONLY_SHORT_TAIL_"
                "HUMAN_LISTENING_NOT_RUN",
            )
            binding = draft["candidate_asset"]
            self.assertIn("week-20260824-30-r5/", binding["path"])
            self.assertTrue(binding["qa_receipt"].endswith("-r5.json"))
            asset = ROOT / binding["path"]
            receipt_path = ROOT / binding["qa_receipt"]
            self.assertTrue(asset.is_file())
            self.assertTrue(receipt_path.is_file())
            actual = hashlib.sha256(asset.read_bytes()).hexdigest().upper()
            self.assertEqual(actual, binding["sha256"])
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["asset"], binding["path"])
            self.assertEqual(receipt["sha256"], actual)
            self.assertEqual(receipt["watermark"]["visual_review"]["status"], "PASS")
            self.assertEqual(receipt["watermark"]["automated_scan"]["status"], "PASS")
            lineage = receipt["technical_qa"]["audio_lineage"]
            self.assertEqual(
                lineage["status"], "PASS_SINGLE_LOCAL_TTS_SOURCE_NO_MIX"
            )
            self.assertEqual(lineage["audio_input_count"], 1)
            self.assertEqual(lineage["ambient_or_music_sources"], [])
            self.assertEqual(lineage["foreign_audio_sources"], [])
            self.assertEqual(lineage["packet_binding"], "PASS_EXACT_PACKET_COPY")
            silence = receipt["technical_qa"]["continuous_silence_audit"]
            self.assertEqual(silence["status"], "PASS")
            self.assertLessEqual(
                silence["longest_exact_zero_run_seconds"],
                renderer.MAX_DIGITAL_SILENCE_SECONDS,
            )
            self.assertLessEqual(
                silence["post_narration_tail"]["duration_seconds"],
                renderer.TAIL_SILENCE_MAX_SECONDS,
            )
            self.assertEqual(
                receipt["manual_check_resolution"]["landing_page_qa"],
                "NOT_APPLICABLE_NO_OUTBOUND_URL_OR_LINK_CTA",
            )
            self.assertEqual(
                receipt["source_binding"]["content_payload_sha256"],
                renderer.stable_json_sha256(renderer._content_payload(draft)),
            )

    def test_receipts_are_not_the_default_action(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("if args.write_receipts:", source)
        self.assertIn("else:\n        render_all()", source)

    def test_media_blocker_is_replaced_but_calendar_blocker_remains(self):
        live_pack = json.loads(renderer.PACK_PATH.read_text(encoding="utf-8"))
        blockers = live_pack["global_blockers"]
        self.assertNotIn("tiktok_media_missing_and_watermark_qa_not_run", blockers)
        self.assertIn(
            "tiktok_media_candidates_not_yet_bound_to_calendar_placements", blockers
        )
        self.assertIn("publication_authority_false_for_all_channels", blockers)
        if live_pack["pack_id"].endswith("-r4"):
            self.assertIn("tiktok_audio_rework_in_progress_no_partial_binding", blockers)
        else:
            self.assertNotIn("tiktok_audio_rework_in_progress_no_partial_binding", blockers)

    def test_final_copy_projection_removes_superseded_wording(self):
        by_id = {day["candidate_id"]: day for day in self.days}
        combined = json.dumps(self.pack, ensure_ascii=False)
        for superseded in ("หนี้ของเขา", "ภาระทั้งหมด", "รดน้ำมัน"):
            self.assertNotIn(superseded, combined)
        self.assertEqual(
            by_id["qt-12"]["quote_text"],
            "อย่าเอาสถานะการเงินของเราไปเทียบกับภาพชีวิตของคนอื่น เพราะเราไม่เห็นภาพการเงินทั้งหมดของเขา",
        )
        self.assertEqual(
            by_id["qt-13"]["quote_text"],
            "ต้นไม้ใหญ่ไม่ได้โตในวันเดียว เงินก้อนแรกก็เช่นกัน แค่ดูแลมันทุกเดือน",
        )
        self.assertEqual(
            by_id["wk36-sf05"]["tiktok_draft"]["onscreen_text"],
            ["เก็บ 1 พฤติกรรม", "ลด 1 รายจ่าย", "ทดลอง 1 วิธีใช้เงิน"],
        )

    def test_silence_audit_accepts_short_tail_and_rejects_two_seconds(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            short_tail = folder / "short-tail.wav"
            long_tail = folder / "long-tail.wav"
            renderer._run(
                [
                    renderer._binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:sample_rate=48000:duration=0.5",
                    "-af", "apad,atrim=duration=1.25", "-c:a", "pcm_s16le",
                    str(short_tail),
                ]
            )
            result = renderer._digital_silence_audit(
                short_tail, expected_narration_end_seconds=0.5
            )
            self.assertEqual(result["status"], "PASS")
            self.assertLessEqual(result["post_narration_tail"]["duration_seconds"], 1.0)
            renderer._run(
                [
                    renderer._binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:sample_rate=48000:duration=0.5",
                    "-af", "apad,atrim=duration=2.5", "-c:a", "pcm_s16le",
                    str(long_tail),
                ]
            )
            with self.assertRaisesRegex(RuntimeError, "continuous digital silence|post-narration silence"):
                renderer._digital_silence_audit(long_tail)

    def test_voice_only_contract_and_r5_roots(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in ("aevalsrc=", "sidechaincompress", "amix=inputs"):
            self.assertNotIn(forbidden, source)
        for token in ("PASS_SINGLE_LOCAL_TTS_SOURCE_NO_MIX", "audio_input_count"):
            self.assertIn(token, source)
        self.assertEqual(renderer.OUTPUT_ROOT.name, "week-20260824-30-r5")
        self.assertEqual(renderer.EVIDENCE_ROOT.name, "week-20260824-30-r5")

    def test_timing_plan_binds_short_tail_and_disclosure_overlap(self):
        narration = {
            "last_active_sample_seconds": 7.2,
            "audio_duration_seconds": 7.3,
        }
        timing = renderer._plan_timing(narration, 5)
        self.assertLessEqual(timing["planned_tail_after_narration_seconds"], 1.0)
        self.assertLessEqual(
            timing["end_card_start_seconds"], timing["narration_last_active_seconds"]
        )
        self.assertGreaterEqual(timing["end_card_dwell_seconds"], 2.0)


if __name__ == "__main__":
    unittest.main()
