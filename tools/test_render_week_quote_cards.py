#!/usr/bin/env python3
"""Offline contract checks for the current weekly quote-card candidates."""

from pathlib import Path
import unittest

from PIL import Image

from tools import render_week_quote_cards as renderer


ROOT = Path(__file__).resolve().parents[1]


class QuoteCardRenderTests(unittest.TestCase):
    def test_copy_and_markup_have_no_outward_identity_or_link(self):
        expected = {
            "qt-12": "อย่าเอาสถานะการเงินของเราไปเทียบกับภาพชีวิตของคนอื่น เพราะเราไม่เห็นภาพการเงินทั้งหมดของเขา",
            "qt-13": "ต้นไม้ใหญ่ไม่ได้โตในวันเดียว เงินก้อนแรกก็เช่นกัน แค่ดูแลมันทุกเดือน",
            "qt-14": "อิสรภาพทางการเงินไม่ใช่การมีเงินไม่จำกัด แต่คือการไม่ต้องกังวลทุกครั้งที่สิ้นเดือนมาถึง",
        }
        forbidden = (
            "@ngernduangold", "http://", "https://", "/links", "facebook",
            "instagram", "pinterest", "tiktok", "watermark", "logo",
        )
        for card_id, quote in expected.items():
            with self.subTest(card_id=card_id):
                self.assertEqual(renderer.CARDS[card_id]["text"], quote)
                for variant, width, height in (("4x5", 1080, 1350),
                                               ("2x3", 1000, 1500)):
                    document = renderer._document(card_id, width, height, variant)
                    self.assertIn(quote, document)
                    lowered = document.casefold().replace(
                        "http://www.w3.org/2000/svg", ""
                    )
                    self.assertTrue(all(term not in lowered for term in forbidden))
                    self.assertNotIn("หนี้ของเขา", document)
                    self.assertNotIn("รดน้ำมัน", document)

    def test_rendered_candidates_exist_at_exact_channel_dimensions(self):
        expected = {
            "qt-12_fb-ig_4x5.jpg": (1080, 1350),
            "qt-12_pinterest_2x3.jpg": (1000, 1500),
            "qt-13_fb-ig_4x5.jpg": (1080, 1350),
            "qt-13_pinterest_2x3.jpg": (1000, 1500),
            "qt-14_fb-ig_4x5.jpg": (1080, 1350),
            "qt-14_pinterest_2x3.jpg": (1000, 1500),
        }
        for name, dimensions in expected.items():
            with self.subTest(asset=name):
                path = ROOT / "media" / "quotes" / "week-20260824-30-r5" / name
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    self.assertEqual(image.size, dimensions)
                    self.assertEqual(image.mode, "RGB")

    def test_single_card_selection_is_exact_and_rejects_unknown_ids(self):
        self.assertEqual(renderer._selected_cards(["qt-14"]), ("qt-14",))
        with self.assertRaises(ValueError):
            renderer._selected_cards(["qt-14", "qt-14"])
        with self.assertRaises(ValueError):
            renderer._selected_cards(["qt-99"])

    def test_every_card_is_bound_to_an_exact_local_editorial_field(self):
        for card_id, card in renderer.CARDS.items():
            with self.subTest(card_id=card_id):
                self.assertIn(card["text"], renderer._bound_source_value(card_id))


if __name__ == "__main__":
    unittest.main(verbosity=2)
