import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import week_content_r5_novelty_guard as guard


class WeekContentR5NoveltyGuardTests(unittest.TestCase):
    def test_normalization_removes_disclosure_url_and_has_deterministic_near_rule(self):
        left = (
            "เก็บ 1 พฤติกรรม ลด 1 รายจ่าย และทดลองเปลี่ยน 1 วิธีใช้เงิน "
            "ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI https://example.test/x"
        )
        right = "เก็บ 1 พฤติกรรม ลด 1 รายจ่าย แล้วทดลองเปลี่ยน 1 วิธีใช้เงิน"
        unrelated = "ตรวจเอกสารและอ่านสัญญาจากผู้ให้บริการทางการก่อนตัดสินใจ"
        self.assertNotIn("ผลตดวยai", guard.normalize_text(left))
        self.assertTrue(guard.text_similarity(left, right)["near"])
        self.assertFalse(guard.text_similarity(left, unrelated)["near"])

    def test_live_pack_has_exact_candidate_and_public_variant_shape(self):
        pack = guard._load_json(guard.PACK)
        self.assertEqual(guard.EXPECTED_PACK_ID, pack["pack_id"])
        self.assertEqual("DRAFT_ONLY", pack["state"])
        self.assertEqual(guard.EXPECTED_IDS, tuple(
            day["candidate_id"] for day in pack["days"]
        ))
        variants = guard._public_variants(pack)
        self.assertEqual(23, len(variants))
        self.assertEqual(
            {"threads", "facebook", "tiktok", "quote_image"},
            {record.channel for record in variants},
        )

    def test_page_only_identity_overlay_passes_current_pack(self):
        pack = guard._load_json(guard.PACK)
        policy = guard._load_json(guard.POLICY)
        result = guard._identity_audit(pack, guard._public_variants(pack), policy)
        self.assertEqual("PASS", result["status"])
        self.assertEqual([], result["findings"])

    def test_cross_candidate_collision_blocks_but_same_candidate_adaptation_is_expected(self):
        base = "จดรายการรายจ่ายทุกครั้งที่เงินออกเพื่อกลับมาดูภาพรวมปลายเดือน"
        variants = [
            guard.TextRecord("pack", "a.threads", "candidate", base,
                             guard.normalize_text(base), "a", "threads"),
            guard.TextRecord("pack", "a.facebook", "candidate", base,
                             guard.normalize_text(base), "a", "facebook"),
            guard.TextRecord("pack", "b.threads", "candidate", base,
                             guard.normalize_text(base), "b", "threads"),
        ]
        result = guard.audit_text(variants, [])
        self.assertEqual(1, len(result["expected_same_candidate_adaptations"]))
        self.assertEqual(2, len(result["cross_candidate_exact_collisions"]))

    def test_perceptual_near_rule_requires_hash_and_pixel_agreement(self):
        first = np.tile(np.arange(32, dtype=np.uint8), (32, 1)) * 8
        same = first.copy()
        opposite = 255 - first
        left = [{"hash": guard._phash(first), "frame": first}]
        equal = [{"hash": guard._phash(same), "frame": same}]
        different = [{"hash": guard._phash(opposite), "frame": opposite}]
        self.assertTrue(guard.perceptual_similarity(
            left, equal, "image", "image"
        )["near"])
        self.assertFalse(guard.perceptual_similarity(
            left, different, "image", "image"
        )["near"])

    def test_live_media_bindings_match_exact_bytes(self):
        pack = guard._load_json(guard.PACK)
        records = guard._current_media(pack)
        self.assertEqual(11, len(records))
        for record in records:
            path = guard.ROOT / record.path
            self.assertTrue(path.is_file(), record.path)
            self.assertEqual(record.sha256, guard._sha256(path), record.path)

    def test_all_historical_collisions_are_non_reusable_without_mutating_history(self):
        before_ledger = guard._sha256(guard.LEDGER)
        before_bindings = guard._sha256(guard.BINDINGS)
        module = guard._import_post_ledger()
        result = module.permanent_dedup_completeness(guard.LEDGER)
        self.assertEqual(0, result["duplicate_identity_groups"])
        self.assertEqual([], result["duplicate_identities"])
        self.assertEqual(
            [
                ("clip", "tiktok", "titleloan", [1, 19]),
                ("text_hash", "ig", "aed0406157eb7257c3bf86c7906a6822f8b86e79", [63, 89]),
                ("text_hash", "yt", "90e43a4ddc4d3da3f72e17d10fd38f153e0741bc", [31, 47, 55, 62, 70, 78, 87, 94, 103, 113, 120, 129, 137, 155]),
            ],
            [
                (
                    item["identity_type"],
                    item["channel"],
                    item["identity"],
                    [occurrence["line"] for occurrence in item["occurrences"]],
                )
                for item in result["tombstoned_duplicate_identities"]
            ],
        )
        self.assertEqual(before_ledger, guard._sha256(guard.LEDGER))
        self.assertEqual(before_bindings, guard._sha256(guard.BINDINGS))

    def test_atomic_receipt_writer_replaces_only_the_named_json(self):
        before_ledger = guard._sha256(guard.LEDGER)
        before_bindings = guard._sha256(guard.BINDINGS)
        with tempfile.TemporaryDirectory(dir=guard.ROOT) as directory:
            output = Path(directory) / "receipt.json"
            output.write_text("stale", encoding="utf-8")
            expected = {"verdict": "BLOCKED", "rows": [123, 2]}
            guard._write_receipt_atomic(output, expected)
            self.assertEqual(expected, json.loads(output.read_text(encoding="utf-8")))
            self.assertTrue(output.read_bytes().endswith(b"\n"))
            self.assertEqual([], list(output.parent.glob(f".{output.name}.*.tmp")))
        self.assertEqual(before_ledger, guard._sha256(guard.LEDGER))
        self.assertEqual(before_bindings, guard._sha256(guard.BINDINGS))

    def test_receipt_output_path_is_fail_closed_and_workspace_scoped(self):
        expected = (
            guard.NOVELTY_RECEIPT_DIR
            / "WEEK-CONTENT-R5-NOVELTY-RECEIPT_20260823.json"
        ).resolve()
        self.assertEqual(
            expected,
            guard._resolve_receipt_output(
                "automation-log/dedup-evidence/"
                "WEEK-CONTENT-R5-NOVELTY-RECEIPT_20260823.json"
            ),
        )
        with self.assertRaises(ValueError):
            guard._resolve_receipt_output("../outside.json")
        with self.assertRaises(ValueError):
            guard._resolve_receipt_output(
                "automation-log/dedup-evidence/not-a-novelty-receipt.json"
            )

    def test_guard_has_no_publication_mutation_path(self):
        source = Path(guard.__file__).read_text(encoding="utf-8")
        self.assertNotIn("record_post(", source)
        self.assertNotIn("record_text_post(", source)
        self.assertIn("os.replace(temporary, path)", source)
        self.assertIn("append_only_history_mutated\": False", source)


if __name__ == "__main__":
    unittest.main()
