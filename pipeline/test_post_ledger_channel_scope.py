"""Action-scoped permanent dedup must stay strict without cross-channel deadlock."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation-log"))
import post_ledger as ledger  # noqa: E402


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            for row in rows
        ) + "\n",
        encoding="utf-8",
    )


def exact_text_row(channel: str, text: str, stamp: str) -> dict:
    normalized = ledger.normalize_text(text)
    return {
        "type": "text",
        "channel": channel,
        "text_hash": ledger.text_hash(text),
        "text_norm": normalized,
        "text_first80": text[:80],
        "ts": stamp,
        "source": "test",
    }


class ChannelScopedPermanentDedupTests(unittest.TestCase):
    def test_unrelated_incomplete_channel_does_not_block_threads(self):
        with tempfile.TemporaryDirectory(prefix="channel-dedup-") as raw:
            path = Path(raw) / "post-ledger.jsonl"
            old_text = "ข้อความ Threads เดิมที่มีหลักฐานครบถ้วน"
            write_rows(path, [
                exact_text_row(
                    "threads", old_text, "2026-07-20T12:40:00+07:00"
                ),
                {
                    "type": "comment", "channel": "youtube",
                    "note": "legacy comment without exact text",
                    "ts": "2026-07-20T21:30:00+07:00", "source": "test",
                },
            ])
            global_allowed, _, global_metric = ledger.permanent_dedup_gate(path)
            self.assertFalse(global_allowed)
            self.assertEqual("INCOMPLETE", global_metric["identity_coverage_state"])

            allowed, reason, metric = ledger.permanent_dedup_channel_gate(
                "threads", path
            )
            self.assertTrue(allowed, reason)
            self.assertEqual((1, 0, 100.0), (
                metric["complete_rows"], metric["incomplete_rows"],
                metric["coverage_percent"],
            ))
            youtube_allowed, _, youtube_metric = ledger.permanent_dedup_channel_gate(
                "youtube", path
            )
            self.assertFalse(youtube_allowed)
            self.assertEqual(1, youtube_metric["incomplete_rows"])

            duplicate, _, _ = ledger.is_duplicate_text("threads", old_text, path=path)
            self.assertTrue(duplicate)
            duplicate, reason, finding = ledger.is_duplicate_text(
                "threads", "ข้อความใหม่ไม่ซ้ำและไม่มีตัวเลข", path=path
            )
            self.assertFalse(duplicate, (reason, finding))

            index = ledger.load_index(path)
            self.assertGreater(
                ledger.day_capacity(index, "threads", "2026-08-25"), 0
            )
            gap_allowed, gap_reason = ledger.minimum_gap(
                index, "threads", "2026-08-25T12:40:00+07:00"
            )
            self.assertTrue(gap_allowed, gap_reason)
            twin, twin_reason, _ = ledger.is_twin(
                index, "threads", "save", "2026-08-25"
            )
            self.assertFalse(twin, twin_reason)

    def test_invalid_overlay_still_blocks_every_channel(self):
        with tempfile.TemporaryDirectory(prefix="channel-dedup-invalid-") as raw:
            root = Path(raw)
            path = root / "post-ledger.jsonl"
            write_rows(path, [
                exact_text_row(
                    "threads", "หลักฐานครบแต่ overlay เสีย",
                    "2026-07-20T12:40:00+07:00",
                )
            ])
            path.with_name("post-ledger-identity-bindings.jsonl").write_text(
                "{}\n", encoding="utf-8"
            )
            allowed, reason, metric = ledger.permanent_dedup_channel_gate(
                "threads", path
            )
            self.assertFalse(allowed)
            self.assertEqual("UNKNOWN", metric["identity_coverage_state"])
            self.assertIn("INVALID", reason)

    def test_channel_aliases_share_one_identity_space(self):
        with tempfile.TemporaryDirectory(prefix="channel-dedup-alias-") as raw:
            path = Path(raw) / "post-ledger.jsonl"
            write_rows(path, [
                exact_text_row(
                    "fb", "โพสต์เฟซบุ๊กที่บันทึกครบ",
                    "2026-07-20T12:50:00+07:00",
                ),
                {
                    "type": "comment", "channel": "instagram",
                    "text_first80": "ข้อความเก่าไม่ครบ",
                    "ts": "2026-07-20T21:50:00+07:00", "source": "test",
                },
            ])
            allowed, reason, metric = ledger.permanent_dedup_channel_gate(
                "facebook", path
            )
            self.assertTrue(allowed, reason)
            self.assertEqual("fb", metric["channel"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
