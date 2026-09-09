"""Offline adversarial checks for non-executable weekly draft QA."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import editorial_draft_gate as gate


class EditorialDraftGateTests(unittest.TestCase):
    def setUp(self):
        # Tests own their fixtures; missing ignored operational files never turns
        # a clean clone test run into a setup error or an assumed approval.
        self.document = {
            "schema_version": 2,
            "artifact_type": "NON_EXECUTABLE_PRIVATE_EDITORIAL_PROPOSALS",
            "state": "DRAFT_ONLY_BLOCKED", "source_classification": gate.CLASSIFICATION,
            "authority": {key: False for key in gate.AUTHORITY_KEYS},
            "public_speaker": "เงินเดือนสมองทอง", "drafts": [],
        }
        subjects = [
            "จดรายการรายจ่ายที่ต้องดูแลก่อนเริ่มสัปดาห์",
            "ก่อนซื้อของลองทบทวนว่ามีสิ่งทดแทนอยู่แล้วหรือไม่",
            "แยกภาระประจำออกจากเหตุการณ์ที่เกิดขึ้นเพียงครั้งเดียว",
            "เงินสำรองควรแยกจากงบใช้จ่ายทั่วไปให้ชัดเจน",
            "ตรวจสมาชิกที่ไม่ค่อยได้ใช้ก่อนต่ออายุบริการ",
            "ดูวันครบกำหนดและเอกสารภาระต่าง ๆ ให้ครบ",
            "บันทึกสิ่งที่ได้เรียนรู้แล้วค่อยปรับแผนรอบหน้า",
        ]
        for index, subject in enumerate(subjects, 7):
            text = subject + "\n\n" + gate.DISCLAIMER + " · ผลิตด้วย AI"
            self.document["drafts"].append({
                "draft_id": f"nsw-202609{index:02d}-example-v2",
                "editorial_day": f"2026-09-{index:02d}", "text": text,
                "caption_sha256": gate._hash(text.encode()), "ai_assisted": True,
                "media": None, "links": [], "source_ids": [],
            })
        self.policy = {"public_identity": {"canonical_name": "เงินเดือนสมองทอง", "page_only": True,
                       "forbidden_personal_claim_patterns": [r"ผม"], "forbidden_public_speakers": ["codex"]}}

    def evaluate(self, duplicate_check=lambda text: (False, "", None)):
        return gate.evaluate_document(self.document, policy=self.policy, duplicate_check=duplicate_check)

    def assertBlocked(self, result):
        self.assertNotEqual(result["state"], "DRAFT_QA_PASSED_PUBLICATION_BLOCKED")
        self.assertIs(result["publication_authorized"], False)
        self.assertEqual(result["source_review"], "NOT_GRANTED")

    def replace_text(self, text):
        row = self.document["drafts"][0]
        row["text"] = text
        row["caption_sha256"] = gate._hash(text.encode())

    def test_valid_drafts_never_become_publication_ready(self):
        result = self.evaluate()
        self.assertEqual(result["state"], "DRAFT_QA_PASSED_PUBLICATION_BLOCKED")
        self.assertFalse(result["publication_authorized"])

    def test_each_authority_flag_fails_closed(self):
        for key in gate.AUTHORITY_KEYS:
            with self.subTest(key=key):
                self.document["authority"][key] = True
                self.assertBlocked(self.evaluate())
                self.document["authority"][key] = False

    def test_caption_hash_drift_is_blocked(self):
        self.document["drafts"][0]["text"] += " แก้ใหม่"
        self.assertBlocked(self.evaluate())

    def test_missing_full_disclaimer_is_blocked(self):
        self.replace_text("ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI")
        self.assertBlocked(self.evaluate())

    def test_missing_ai_disclosure_is_blocked(self):
        self.replace_text(gate.DISCLAIMER)
        self.assertBlocked(self.evaluate())

    def test_lending_claim_or_url_requires_separate_review(self):
        for prefix in ("ดอกเบี้ย 3% ", "https://example.com ", "สินเชื่อ "):
            with self.subTest(prefix=prefix):
                self.replace_text(prefix + gate.DISCLAIMER + " · ผลิตด้วย AI")
                self.assertBlocked(self.evaluate())

    def test_personal_or_agent_public_voice_is_blocked(self):
        for prefix in ("ผม ", "Codex "):
            self.replace_text(prefix + gate.DISCLAIMER + " · ผลิตด้วย AI")
            self.assertBlocked(self.evaluate())

    def test_pack_duplicates_are_blocked(self):
        self.replace_text(self.document["drafts"][1]["text"])
        self.assertBlocked(self.evaluate())

    def test_missing_days_or_reordered_week_is_blocked(self):
        self.document["drafts"].reverse()
        self.assertBlocked(self.evaluate())

    def test_missing_dedup_is_not_pass(self):
        self.assertBlocked(self.evaluate(None))

    def test_dedup_unavailable_or_collision_is_not_pass(self):
        self.assertBlocked(self.evaluate(lambda text: (True, "coverage incomplete", None)))
        def unavailable(text):
            raise OSError("unavailable")
        self.assertBlocked(self.evaluate(unavailable))

    def test_unknown_source_classification_is_blocked(self):
        self.document["source_classification"] = "NOT_REQUIRED"
        self.assertBlocked(self.evaluate())

    def test_strict_json_rejects_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pack.json"
            for raw in ('{"state":1,"state":2}', '{"x":NaN}', '{"x":1e999}'):
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    gate._read(path)
            path.write_text('{"ratio":0.9}', encoding="utf-8")
            self.assertEqual(gate._read(path)[0]["ratio"], 0.9)

    def test_missing_ledger_never_means_no_prior_posts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "pack.json"
            path.write_text(json.dumps(self.document), encoding="utf-8")
            (root / ".system_control").mkdir()
            (root / ".system_control/policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
            with patch.object(gate.post_ledger, "is_duplicate_text") as duplicate:
                result = gate.evaluate(path, repo=root)
            self.assertEqual(result["state"], "UNKNOWN")
            duplicate.assert_not_called()

    def test_literal_newline_and_overlong_caption_are_blocked(self):
        for text in ("test\\n" + gate.DISCLAIMER + " · ผลิตด้วย AI", "ก" * 501 + gate.DISCLAIMER + " · ผลิตด้วย AI"):
            self.replace_text(text)
            self.assertBlocked(self.evaluate())

    def test_pure_lint_missing_or_malformed_identity_fails_closed(self):
        caption = self.document["drafts"][0]["text"]
        for policy in (None, {}, {"public_identity": {"canonical_name": "page", "page_only": True}}):
            with self.subTest(policy=policy):
                result = gate.check_source_neutral_text(caption, policy=policy)
                self.assertFalse(result["allowed"])
                self.assertFalse(result["publication_authorized"])

    def test_pure_lint_rejects_named_bank_and_english_claim(self):
        for prefix in ("กสิกรอนุมัติ ", "Guaranteed income ", "กฎหมายล่าสุด "):
            result = gate.check_source_neutral_text(prefix + self.document["drafts"][0]["text"], policy=self.policy)
            self.assertFalse(result["allowed"])

    def test_invisible_characters_cannot_hide_prohibited_claims(self):
        for character in ("\u200b", "\u202e", "\ufeff", "\ufffd", "\x00"):
            result = gate.check_source_neutral_text("กา" + character + "รันตี " + self.document["drafts"][0]["text"], policy=self.policy)
            self.assertFalse(result["allowed"])

    def test_editorial_day_requires_canonical_iso_date(self):
        self.document["drafts"][0]["editorial_day"] = "20260907"
        self.assertBlocked(self.evaluate())

    def test_guaranteed_returns_and_easy_approval_are_not_source_neutral(self):
        for prefix in ("รับประกันกำไรแน่นอน", "ผ่านง่าย", "อนุมัติไว", "ได้เงินชัวร์", "ไม่มีความเสี่ยง"):
            result = gate.check_source_neutral_text(prefix + "\n\n" + self.document["drafts"][0]["text"], policy=self.policy)
            self.assertFalse(result["allowed"], prefix)

    def test_foreign_combining_mark_cannot_hide_guarantee(self):
        result = gate.check_source_neutral_text("กา\u034fรันตี " + self.document["drafts"][0]["text"], policy=self.policy)
        self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main()
