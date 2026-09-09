#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused regression tests for permanent exact dedup and atomic ledger claims."""
import concurrent.futures
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "automation-log"))
import post_ledger as PL


def append_row(path, row):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    original_ledger = PL.LEDGER
    PL.LEDGER = tmp
    lock_path = PL._lock_path(tmp)
    try:
        base = "เก็บเงินสำรองก่อนใช้จ่าย และตรวจเงื่อนไขจากแหล่งทางการทุกครั้ง"
        old_ts = (PL.now_local() - datetime.timedelta(days=365)).isoformat(timespec="seconds")
        append_row(tmp, {
            "type": "text", "channel": "threads", "text_hash": PL.text_hash(base),
            "text_norm": PL.normalize_text(base), "text_first80": base[:80],
            "ts": old_ts, "source": "permanent-dedup-test",
        })

        # 1) Exact normalized text is blocked forever on the same channel.
        dup, reason, _ = PL.is_duplicate_text("threads", base + " 🙏 https://example.com")
        assert dup and "permanent" in reason, reason

        # 2) Cross-channel reuse remains allowed.
        dup, _, _ = PL.is_duplicate_text("facebook", base)
        assert not dup, "same text on a different channel must remain allowed"

        # 3) Old near-duplicate text remains outside the 30-day near window.
        near = base.replace("ทุกครั้ง", "เสมอ")
        dup, _, _ = PL.is_duplicate_text("threads", near)
        assert not dup, "old near duplicate must remain outside the rolling window"

        # 4) Concurrent check+append calls admit exactly one same-channel text row.
        concurrent_text = "ข้อความใหม่สำหรับทดสอบ atomic claim ของโพสต์เดียวกัน"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _: PL.record_text_post("facebook", concurrent_text,
                                              source="atomic-dedup-test"),
                range(8),
            ))
        assert sum(bool(result.get("appended")) for result in results) == 1, results

        # 5) Canonical clip identity is permanent per channel, even beyond 16 days.
        first = PL.record_post("threads", "save", "2025-01-01", source="permanent-dedup-test")
        assert first["appended"], first
        repeat = PL.record_post("threads", "save", "2026-08-16", source="permanent-dedup-test")
        assert not repeat["appended"] and "DUPLICATE:" in repeat["reason"], repeat

        # 6) The same canonical clip may still be adapted to another channel.
        cross_channel = PL.record_post("facebook", "save", "2026-08-16",
                                       source="permanent-dedup-test")
        assert cross_channel["appended"], cross_channel

        # 7) Concurrent clip records also admit exactly one identity claim.
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            clip_results = list(pool.map(
                lambda _: PL.record_post("threads", "debt", "2026-08-16",
                                         source="atomic-dedup-test"),
                range(8),
            ))
        assert sum(bool(result.get("appended")) for result in clip_results) == 1, clip_results

        # 8) Dated B3/B4 reel filenames resolve to stable batch content IDs.
        assert PL.resolve_clip_key("reels/2026-08-16_b4-p01.mp4") == "b4-p01"
        assert PL.resolve_clip_key("reels/2026-07-30_b3-04.mp4") == "b3-04"

        # 9) Batch identities receive the same permanent no-repost protection.
        batch_first = PL.record_post("threads", "reels/2026-08-16_b4-p01.mp4",
                                     "2026-08-16", source="batch-id-test")
        batch_repeat = PL.record_post("threads", "b4-p01", "2027-08-16",
                                      source="batch-id-test")
        assert batch_first["appended"] and not batch_repeat["appended"], (batch_first, batch_repeat)

        # 10) A rolling index still carries all-time exact identities for claim().
        index = PL.load_index(since_days=16)
        twin, reason, _ = PL.is_twin(index, "threads", "save", "2027-01-01", 16)
        assert twin and "exact content identity" in reason, reason

        assert not os.path.exists(lock_path), "ledger lock must be released after every path"
        print("test_post_ledger_permanent_dedup: 10/10 PASS")
        return 0
    finally:
        PL.LEDGER = original_ledger
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        try:
            os.unlink(lock_path)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
