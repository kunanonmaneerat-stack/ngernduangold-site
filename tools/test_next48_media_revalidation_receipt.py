#!/usr/bin/env python3
"""Fail-closed checks for the exact next-48-hour media revalidation bundle."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "automation-log"
    / "media-qa"
    / "NEXT48-MEDIA-REVALIDATION-RECEIPT_20260824.json"
)
HISTORICAL_WINDOW_FIXTURE = (
    ROOT / "tools" / "fixtures" / "next48-media-revalidation-20260824-window.json"
)
RECEIPT_SHA256 = "31E9D7EC82F3F01C595996592E818457410055C8784B77CD1B0DD957D53A0E2A"
HISTORICAL_WINDOW_FIXTURE_SHA256 = (
    "E9AEEA59CF4321D0E731884B9C8DC6A2DF042D9309292F78867BB05D50579848"
)


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON object required: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _repo_path(raw: str) -> Path:
    path = (ROOT / raw).resolve()
    path.relative_to(ROOT)
    return path


def _audio_packet_hash(path: Path) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg is required for packet-binding verification")
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-c:a",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    match = re.search(r"SHA256=([0-9a-fA-F]{64})", result.stdout)
    if not match:
        raise AssertionError("ffmpeg returned no audio packet hash")
    return match.group(1).upper()


class Next48MediaRevalidationReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = _json(RECEIPT)
        cls.fixture = _json(HISTORICAL_WINDOW_FIXTURE)

    def test_window_selects_every_and_only_media_placement(self):
        self.assertEqual(_sha256(RECEIPT), RECEIPT_SHA256)
        self.assertEqual(
            _sha256(HISTORICAL_WINDOW_FIXTURE),
            HISTORICAL_WINDOW_FIXTURE_SHA256,
        )
        window = self.receipt["window"]
        start = datetime.fromisoformat(window["start_inclusive"])
        end = datetime.fromisoformat(window["end_inclusive"])
        self.assertEqual(end - start, timedelta(hours=48))
        self.assertEqual(
            self.fixture["source_calendar_sha256"], window["calendar_sha256"]
        )
        self.assertEqual(self.fixture["window"], {
            "start_inclusive": window["start_inclusive"],
            "end_inclusive": window["end_inclusive"],
            "hours": window["hours"],
        })
        selected = set()
        for placement in self.fixture["placements"]:
            if not placement.get("media"):
                continue
            scheduled = datetime.fromisoformat(
                f'{placement["date"]}T{placement["time"]}:00+07:00'
            )
            if start <= scheduled <= end:
                selected.add(placement["placement_id"])
        recorded = {item["placement_id"] for item in self.receipt["placements"]}
        self.assertEqual(
            selected,
            {
                "wk36-sf02__tiktok_main",
                "qt-12__facebook_main",
                "qt-12__tiktok_main",
            },
        )
        self.assertEqual(recorded, selected)

    def test_all_input_and_asset_hashes_are_exact(self):
        source = self.receipt["source_binding"]
        self.assertEqual(
            _sha256(_repo_path(source["weekly_pack"])),
            source["weekly_pack_sha256"],
        )
        for guard in self.receipt["guard_implementation"].values():
            self.assertRegex(guard["sha256"], r"^[0-9A-F]{64}$")
        for item in self.receipt["placements"]:
            asset = _repo_path(item["asset"])
            canonical = _repo_path(item["canonical_receipt"])
            self.assertEqual(_sha256(asset), item["asset_sha256"])
            self.assertEqual(asset.stat().st_size, item["asset_size_bytes"])
            self.assertEqual(
                _sha256(canonical), item["canonical_receipt_sha256"]
            )
            canonical_data = _json(canonical)
            self.assertEqual(canonical_data["asset"], item["asset"])
            self.assertEqual(canonical_data["sha256"], item["asset_sha256"])
            if "content_payload_sha256" in item:
                self.assertEqual(
                    canonical_data["source_binding"]["content_payload_sha256"],
                    item["content_payload_sha256"],
                )
            if "source_markup_sha256" in item:
                self.assertEqual(
                    canonical_data["source_binding"]["source_markup_sha256"],
                    item["source_markup_sha256"],
                )

    def test_audio_review_artifacts_copy_the_final_video_packets(self):
        videos = [
            item for item in self.receipt["placements"] if "review_artifact" in item
        ]
        self.assertEqual(len(videos), 2)
        for item in videos:
            review = item["review_artifact"]
            review_path = _repo_path(review["path"])
            final_path = _repo_path(item["asset"])
            self.assertEqual(_sha256(review_path), review["sha256"])
            self.assertEqual(review_path.stat().st_size, review["size_bytes"])
            self.assertEqual(_audio_packet_hash(review_path), review["audio_packet_sha256"])
            self.assertEqual(_audio_packet_hash(final_path), review["audio_packet_sha256"])
            self.assertEqual(review["packet_match_to_final_video"], "PASS")

    def test_receipt_does_not_overstate_human_review_or_authority(self):
        summary = self.receipt["summary"]
        self.assertEqual(
            summary["verdict"], "COMPLETED_WITH_HUMAN_LISTENING_BLOCKERS"
        )
        self.assertEqual(summary["human_audio_reviews_outstanding"], 2)
        self.assertFalse(summary["publication_authority_granted"])
        self.assertFalse(summary["calendar_or_authority_mutated"])
        for item in self.receipt["placements"]:
            self.assertFalse(
                item["media_publish_guard"]["publication_authority_granted"]
            )
        blocked = [
            item
            for item in self.receipt["placements"]
            if item["media_publish_guard"]["verdict"] == "FAIL"
        ]
        self.assertEqual(len(blocked), 2)
        self.assertTrue(
            all(
                item["media_publish_guard"]["finding"]
                == "human audio review is missing"
                for item in blocked
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
