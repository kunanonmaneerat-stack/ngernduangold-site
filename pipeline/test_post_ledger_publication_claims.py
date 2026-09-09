#!/usr/bin/env python3
"""Regression tests for atomic publication quota/gap/text claim boundaries."""
from contextlib import contextmanager
import concurrent.futures
import datetime
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation-log"))
import post_ledger as PL  # noqa: E402


POLICY = {
    "limits": {
        "posts_per_day": {"default": 2, "pinterest": 5},
        "min_gap_hours": 3,
    }
}


@contextmanager
def isolated_ledger():
    with tempfile.TemporaryDirectory(prefix="post-ledger-publication-") as raw:
        directory = Path(raw)
        ledger_path = directory / "post-ledger.jsonl"
        policy_path = directory / "policy.json"
        ledger_path.write_bytes(b"")
        policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
        prior_ledger, prior_policy = PL.LEDGER, PL.POLICY
        PL.LEDGER, PL.POLICY = str(ledger_path), str(policy_path)
        try:
            yield ledger_path
        finally:
            PL.LEDGER, PL.POLICY = prior_ledger, prior_policy
            lock = Path(PL._lock_path(str(ledger_path)))
            if lock.exists():
                lock.unlink()


def append_row(path, row):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def text_identity_row(kind, channel, text, stamp):
    normalized = PL.normalize_text(text)
    return {
        "type": kind,
        "channel": channel,
        "text_hash": PL.text_hash(text),
        "text_norm": normalized,
        "text_first80": text[:80],
        "ts": stamp,
        "source": "publication-claim-test",
    }


class PublicationClaimTests(unittest.TestCase):
    def test_policy_reader_rejects_duplicate_keys_and_unstable_snapshots(self):
        with isolated_ledger():
            policy_path = Path(PL.POLICY)
            policy_path.write_text(
                '{"limits":{"posts_per_day":{"default":2,"default":999},'
                '"min_gap_hours":3}}',
                encoding="utf-8",
            )
            self.assertEqual((None, None), PL._policy_posting_limits())
            self.assertEqual(
                0,
                PL.day_capacity(
                    PL.load_index(), "facebook", "2026-08-25T10:00:00+07:00"
                ),
            )

            policy_path.write_text(
                '{"limits":{"posts_per_day":{"default":2},'
                '"min_gap_hours":1e999}}',
                encoding="utf-8",
            )
            self.assertEqual((None, None), PL._policy_posting_limits())

            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
            before = policy_path.stat()
            changed = SimpleNamespace(
                st_dev=before.st_dev,
                st_ino=before.st_ino,
                st_size=before.st_size,
                st_mtime_ns=before.st_mtime_ns + 1,
            )
            with mock.patch.object(PL.os, "stat", side_effect=[before, changed]):
                self.assertEqual((None, None), PL._policy_posting_limits())

    def test_comment_and_story_are_permanent_text_identities(self):
        with isolated_ledger() as path:
            comment = "ความคิดเห็นเฉพาะนี้ต้องไม่ถูกเผยแพร่ซ้ำ"
            story = "สตอรีเฉพาะนี้ต้องไม่ถูกเผยแพร่ซ้ำ"
            append_row(path, text_identity_row(
                "comment", "facebook", comment, "2025-01-01T10:00:00+07:00"
            ))
            append_row(path, text_identity_row(
                "story", "facebook", story, "2025-01-02T10:00:00+07:00"
            ))
            for value in (comment, story):
                duplicate, reason, _finding = PL.is_duplicate_text(
                    "facebook", value + " https://example.invalid"
                )
                self.assertTrue(duplicate, value)
                self.assertIn("permanent", reason)

    def test_policy_default_and_text_rows_enforce_daily_capacity(self):
        with isolated_ledger() as path:
            when = "2026-08-25T10:00:00+07:00"
            empty = PL.load_index()
            self.assertEqual(PL.day_capacity(empty, "unknown-platform", when), 2)
            self.assertEqual(PL.day_capacity(empty, "tiktok", when), 2)
            append_row(path, text_identity_row(
                "comment", "facebook", "ข้อความที่หนึ่ง", when
            ))
            append_row(path, text_identity_row(
                "story", "facebook", "ข้อความที่สอง", "2026-08-25T14:00:00+07:00"
            ))
            index = PL.load_index()
            self.assertEqual(index["by_day"][("fb", datetime.date(2026, 8, 25))], 2)
            self.assertEqual(PL.day_capacity(index, "facebook", when), 0)

        with isolated_ledger() as path:
            append_row(path, {
                "type": "text", "channel": "facebook",
                "text_first80": "legacy prefix without exact identity",
                "ts": "2026-08-25T09:00:00+07:00",
                "source": "legacy",
            })
            incomplete = PL.load_index()
            self.assertEqual(PL.day_capacity(incomplete, "facebook", when), 0)
            allowed, reason = PL.minimum_gap(incomplete, "facebook", when)
            self.assertFalse(allowed)
            self.assertIn("coverage", reason)

    def test_text_claim_is_atomic_pending_and_requires_success_evidence(self):
        with isolated_ledger() as path:
            text = "ข้อความเดียวสำหรับทดสอบ claim แบบ atomic"
            when = "2026-08-25T10:00:00+07:00"

            def reserve(_index):
                return PL.claim_text_publication(
                    "facebook", text, when,
                    content_id="content-001",
                    placement_id="content-001__facebook-feed",
                    source="publication-claim-test",
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(reserve, range(8)))
            successes = [result for result in results if result[0]]
            self.assertEqual(len(successes), 1, results)
            claim_key = successes[0][1]
            claimed_day = datetime.date(2026, 8, 25)
            self.assertEqual(
                PL.load_index()["by_day"][("fb", claimed_day)], 1
            )
            self.assertEqual(
                [item["dedup_key"] for item in PL.inspect_ledger(path)["pending_claims"]],
                [claim_key],
            )

            with self.assertRaisesRegex(RuntimeError, "UNKNOWN platform post_id"):
                PL.confirm(claim_key, post_id="", status="POSTED")
            with self.assertRaisesRegex(RuntimeError, "non-success status"):
                PL.confirm(claim_key, post_id="platform-1", status="UNKNOWN")
            self.assertEqual(len(PL.inspect_ledger(path)["pending_claims"]), 1)

            PL.confirm(claim_key, post_id="platform-1", status="POSTED")
            PL.confirm(claim_key, post_id="platform-1", status="POSTED")
            self.assertFalse(PL.inspect_ledger(path)["pending_claims"])
            with self.assertRaisesRegex(RuntimeError, "terminal evidence"):
                PL.confirm(claim_key, post_id="platform-2", status="POSTED")

            repeat = PL.claim_text_publication(
                "facebook", text, "2027-08-25T10:00:00+07:00",
                content_id="content-002",
                placement_id="content-002__facebook-feed",
            )
            self.assertFalse(repeat[0], repeat)
            self.assertIn("DUPLICATE_OR_UNKNOWN", repeat[2])

    def test_minimum_gap_is_part_of_the_same_atomic_claim(self):
        with isolated_ledger():
            when = "2026-08-25T10:00:00+07:00"
            texts = (
                "แนวทางวางแผนภาษีสำหรับผู้เริ่มต้น",
                "วิธีจัดห้องทำงานให้รับแสงธรรมชาติพอดี",
            )

            def reserve(index):
                content_id = "gap-content-%d" % index
                return PL.claim_text_publication(
                    "threads", texts[index], when,
                    content_id=content_id,
                    placement_id=content_id + "__threads",
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(reserve, range(2)))
            self.assertEqual(sum(result[0] for result in results), 1, results)
            self.assertTrue(any("GAP:" in result[2] for result in results if not result[0]))

        with isolated_ledger():
            claimed = PL.claim_text_publication(
                "threads", "เทคนิคจัดงบอาหารรายสัปดาห์", "2026-08-25T10:00:00+07:00",
                content_id="gap-base",
                placement_id="gap-base__threads",
            )
            self.assertTrue(claimed[0], claimed)
            PL.confirm(claimed[1], post_id="platform-gap", status="POSTED")
            too_soon = PL.claim_text_publication(
                "threads", "หลักเลือกประกันเดินทางต่างประเทศ", "2026-08-25T11:00:00+07:00",
                content_id="gap-soon",
                placement_id="gap-soon__threads",
            )
            self.assertFalse(too_soon[0], too_soon)
            self.assertIn("GAP:", too_soon[2])
            exact_boundary = PL.claim_text_publication(
                "threads", "วิธีดูแลแบตเตอรี่โทรศัพท์ให้อยู่ได้นาน", "2026-08-25T13:00:00+07:00",
                content_id="gap-boundary",
                placement_id="gap-boundary__threads",
            )
            self.assertTrue(exact_boundary[0], exact_boundary)

        with isolated_ledger():
            date_only = PL.claim(
                "tiktok", "b4-p01", "2026-08-25", enforce_gap=True
            )
            self.assertFalse(date_only[0], date_only)
            self.assertIn("GAP:", date_only[2])

            disabled = PL.claim(
                "tiktok", "b4-p01", "2026-08-25T10:00:00+07:00",
                enforce_gap=False,
            )
            self.assertFalse(disabled[0], disabled)
            self.assertIn("cannot be disabled", disabled[2])

    def test_hash_addressed_media_identity_is_permanent(self):
        with isolated_ledger():
            identity = "sha256:" + ("a" * 64)
            first = PL.claim(
                "youtube", identity, "2026-08-25T10:00:00+07:00"
            )
            self.assertTrue(first[0], first)
            PL.confirm(first[1], post_id="AbCdEf12345", status="POSTED")
            repeat = PL.claim(
                "youtube", identity, "2027-08-25T10:00:00+07:00"
            )
            self.assertFalse(repeat[0], repeat)
            self.assertIn("TWIN:", repeat[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
