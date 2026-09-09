#!/usr/bin/env python3
"""Focused regression tests for daily canonical/future media coverage."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import daily_media_gate as gate


TODAY = dt.date(2026, 8, 16)


class DailyMediaGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / ".system_control").mkdir(parents=True)
        (self.repo / "reels").mkdir(parents=True)
        (self.repo / "automation-log/media-qa").mkdir(parents=True)
        self.write_manifest([])
        self.write_schedule({})
        self.write_calendar([])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_manifest(self, items) -> None:
        (self.repo / ".system_control/content_manifest.json").write_text(
            json.dumps({"items": items}), encoding="utf-8")

    def write_schedule(self, rows) -> None:
        (self.repo / "reels/schedule.json").write_text(
            json.dumps(rows), encoding="utf-8")

    def write_calendar(self, placements) -> None:
        (self.repo / ".system_control/content_calendar.json").write_text(
            json.dumps({"placements": placements}), encoding="utf-8")

    def asset(self, relative: str, content: bytes = b"media") -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def report(self, relative: str = "automation-log/media-qa/test.json") -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    def indexed_report(self, asset: Path, relative: str = "automation-log/media-qa/indexed.json") -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "asset": asset.relative_to(self.repo).as_posix(),
        }), encoding="utf-8")
        return path

    @staticmethod
    def pass_scan(path, fps):
        return {"file": str(path), "verdict": "PASS", "frames": 12, "track_frames": 0}

    def test_scans_manifest_and_extra_canonical_reel_but_never_quarantine(self) -> None:
        first = self.asset("reels/manifest.mp4")
        extra = self.asset("reels/unlisted-b4.mp4")
        quarantined = self.asset("media/quarantine/watermarked/raw-veo/bad.mp4")
        self.write_manifest([{"id": "manifest", "reel": "reels/manifest.mp4"}])
        scanned = []

        def scanner(path, fps):
            scanned.append(Path(path))
            return self.pass_scan(path, fps)

        result = gate.evaluate(repo=self.repo, today=TODAY, scanner=scanner)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(set(scanned), {first.resolve(), extra.resolve()})
        self.assertNotIn(quarantined.resolve(), scanned)
        self.assertEqual(result["coverage"]["canonical_video_files"], 2)
        self.assertEqual(result["coverage"]["quarantine_files_scanned"], 0)

    def test_future_video_requires_guard_and_is_not_weakened_to_bare_scan(self) -> None:
        video = self.asset("reels/future.mp4")
        receipt = self.report()
        self.write_manifest([{"id": "future", "reel": "reels/future.mp4"}])
        self.write_schedule({
            "2026-08-17": {
                "file": "future.mp4",
                "qa_report": "automation-log/media-qa/test.json",
            }
        })
        guarded = []

        def no_bare_scan(path, fps):
            self.fail("future video must be scanned through the hash-bound guard")

        def guard_runner(path, report, **kwargs):
            guarded.append((Path(path), Path(report)))
            return {"verdict": "PASS", "findings": []}

        result = gate.evaluate(
            repo=self.repo, today=TODAY, scanner=no_bare_scan, guard_runner=guard_runner)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(guarded, [(video.resolve(), receipt.resolve())])
        self.assertEqual(result["coverage"]["future_video_guards"], 1)
        self.assertEqual(result["coverage"]["canonical_videos_guarded_as_future"], 1)

    def test_future_video_without_receipt_fails_even_when_frame_scan_would_pass(self) -> None:
        video = self.asset("reels/future.mp4")
        self.write_manifest([{"id": "future", "reel": "reels/future.mp4"}])
        self.write_schedule({"2026-08-17": {"file": "future.mp4"}})
        scans = []

        def scanner(path, fps):
            scans.append(path)
            return self.pass_scan(path, fps)

        result = gate.evaluate(repo=self.repo, today=TODAY, scanner=scanner)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(scans, [video.resolve()])
        self.assertTrue(any("hash-bound qa_report" in item for item in result["findings"]))
        self.assertEqual(result["coverage"]["future_video_diagnostic_scans"], 1)

    def test_future_video_without_receipt_still_records_failing_watermark_scan(self) -> None:
        video = self.asset("reels/future.mp4")
        self.write_manifest([{"id": "future", "reel": "reels/future.mp4"}])
        self.write_schedule({"2026-08-17": {"file": "future.mp4"}})

        result = gate.evaluate(
            repo=self.repo,
            today=TODAY,
            scanner=lambda path, fps: {"verdict": "FAIL", "frames": 12},
        )

        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("hash-bound qa_report" in item for item in result["findings"]))
        self.assertTrue(any(
            video.relative_to(self.repo).as_posix() in item and "frame scan FAIL" in item
            for item in result["findings"]
        ))

    def test_future_image_requires_hash_bound_guard_and_never_video_scanner(self) -> None:
        image = self.asset("media/pins/future.png")
        receipt = self.report()
        self.write_schedule({
            "2026-08-17": {
                "asset": "media/pins/future.png",
                "qa_report": "automation-log/media-qa/test.json",
            }
        })
        guarded = []

        def no_video_scan(path, fps):
            self.fail("still image was sent to the Veo video detector")

        def guard_runner(path, report, **kwargs):
            guarded.append((Path(path), Path(report)))
            return {"verdict": "PASS", "findings": []}

        result = gate.evaluate(
            repo=self.repo, today=TODAY, scanner=no_video_scan, guard_runner=guard_runner)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(guarded, [(image.resolve(), receipt.resolve())])
        self.assertEqual(result["coverage"]["future_image_guards"], 1)

    def test_future_image_without_receipt_fails_closed(self) -> None:
        self.asset("media/quotes/future.jpg")
        self.write_schedule({"2026-08-17": {"asset": "media/quotes/future.jpg"}})
        result = gate.evaluate(repo=self.repo, today=TODAY, scanner=self.pass_scan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("hash-bound qa_report" in item for item in result["findings"]))
        self.assertEqual(result["coverage"]["future_image_guards"], 0)

    def test_content_calendar_future_image_is_hash_guarded(self) -> None:
        image = self.asset("media/quotes/future.jpg")
        receipt = self.report()
        self.write_calendar([{
            "placement_id": "quote__instagram_main",
            "date": "2026-08-17",
            "time": "19:00",
            "format": "image",
            "media": "media/quotes/future.jpg",
            "media_receipt": "automation-log/media-qa/test.json",
        }])
        guarded = []

        def guard_runner(path, report, **kwargs):
            guarded.append((Path(path), Path(report)))
            return {"verdict": "PASS", "findings": []}

        result = gate.evaluate(
            repo=self.repo,
            today=TODAY,
            scanner=self.pass_scan,
            guard_runner=guard_runner,
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(guarded, [(image.resolve(), receipt.resolve())])
        self.assertEqual(result["coverage"]["content_calendar_routes"], 1)
        self.assertEqual(result["coverage"]["future_image_guards"], 1)

    def test_content_calendar_future_media_without_receipt_fails_closed(self) -> None:
        self.asset("media/quotes/future.jpg")
        self.write_calendar([{
            "placement_id": "quote__instagram_main",
            "date": "2026-08-17",
            "time": "19:00",
            "format": "image",
            "media": "media/quotes/future.jpg",
            "media_receipt": None,
        }])
        result = gate.evaluate(repo=self.repo, today=TODAY, scanner=self.pass_scan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any(
            "content calendar quote__instagram_main" in item
            and "hash-bound qa_report" in item
            for item in result["findings"]
        ))

    def test_same_day_calendar_slot_uses_exact_bangkok_time_boundary(self) -> None:
        image = self.asset("media/quotes/boundary.jpg")
        receipt = self.report()
        self.write_calendar([{
            "placement_id": "boundary__instagram_main",
            "date": TODAY.isoformat(),
            "time": "19:00",
            "format": "image",
            "media": "media/quotes/boundary.jpg",
            "media_receipt": "automation-log/media-qa/test.json",
        }])

        for label, evaluation_now, expected_routes in (
            ("before", dt.datetime(2026, 8, 16, 18, 59, tzinfo=gate.BANGKOK), 1),
            ("equal", dt.datetime(2026, 8, 16, 19, 0, tzinfo=gate.BANGKOK), 1),
            ("after", dt.datetime(2026, 8, 16, 19, 1, tzinfo=gate.BANGKOK), 0),
        ):
            with self.subTest(label=label):
                guarded = []

                def guard_runner(path, report, **kwargs):
                    guarded.append((Path(path), Path(report)))
                    return {"verdict": "PASS", "findings": []}

                result = gate.evaluate(
                    repo=self.repo,
                    now=evaluation_now,
                    scanner=self.pass_scan,
                    guard_runner=guard_runner,
                )
                self.assertEqual(result["verdict"], "PASS")
                self.assertEqual(
                    result["coverage"]["content_calendar_routes"], expected_routes)
                self.assertEqual(len(guarded), expected_routes)
                if expected_routes:
                    self.assertEqual(guarded, [(image.resolve(), receipt.resolve())])

    def test_calendar_boundary_converts_aware_now_to_bangkok(self) -> None:
        image = self.asset("media/quotes/timezone.jpg")
        receipt = self.report()
        self.write_calendar([{
            "placement_id": "timezone__instagram_main",
            "date": TODAY.isoformat(),
            "time": "19:00",
            "format": "image",
            "media": "media/quotes/timezone.jpg",
            "media_receipt": "automation-log/media-qa/test.json",
        }])
        guarded = []

        def guard_runner(path, report, **kwargs):
            guarded.append((Path(path), Path(report)))
            return {"verdict": "PASS", "findings": []}

        # 12:00 UTC is the exact 19:00 Bangkok boundary and remains eligible.
        result = gate.evaluate(
            repo=self.repo,
            now=dt.datetime(2026, 8, 16, 12, 0, tzinfo=dt.timezone.utc),
            scanner=self.pass_scan,
            guard_runner=guard_runner,
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(len(guarded), 1)
        self.assertEqual(result["evaluated_at"], "2026-08-16T19:00:00+07:00")

    def test_naive_evaluation_now_fails_closed(self) -> None:
        result = gate.evaluate(
            repo=self.repo,
            now=dt.datetime(2026, 8, 16, 19, 1),
            scanner=self.pass_scan,
        )
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("must include a timezone" in item for item in result["findings"]))

    def test_legacy_same_day_route_remains_in_scope_without_exact_time(self) -> None:
        image = self.asset("media/quotes/legacy.jpg")
        receipt = self.report()
        self.write_schedule({
            TODAY.isoformat(): {
                "asset": "media/quotes/legacy.jpg",
                "qa_report": "automation-log/media-qa/test.json",
            }
        })
        guarded = []

        def guard_runner(path, report, **kwargs):
            guarded.append((Path(path), Path(report)))
            return {"verdict": "PASS", "findings": []}

        result = gate.evaluate(
            repo=self.repo,
            now=dt.datetime(2026, 8, 16, 23, 59, tzinfo=gate.BANGKOK),
            scanner=self.pass_scan,
            guard_runner=guard_runner,
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["coverage"]["legacy_schedule_routes"], 1)
        self.assertEqual(guarded, [(image.resolve(), receipt.resolve())])

    def test_past_content_calendar_media_is_not_a_future_route(self) -> None:
        self.write_calendar([{
            "placement_id": "past__instagram_main",
            "date": "2026-08-15",
            "format": "image",
            "media": "media/quotes/missing.jpg",
            "media_receipt": None,
        }])
        result = gate.evaluate(repo=self.repo, today=TODAY, scanner=self.pass_scan)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["coverage"]["content_calendar_routes"], 0)

    def test_same_asset_receipt_in_legacy_and_calendar_is_guarded_once(self) -> None:
        image = self.asset("media/quotes/future.jpg")
        receipt = self.report()
        self.write_schedule({
            "2026-08-17": {
                "asset": "media/quotes/future.jpg",
                "qa_report": "automation-log/media-qa/test.json",
            }
        })
        self.write_calendar([{
            "placement_id": "quote__instagram_main",
            "date": "2026-08-17",
            "time": "19:00",
            "format": "image",
            "media": "media/quotes/future.jpg",
            "media_receipt": "automation-log/media-qa/test.json",
        }])
        guarded = []

        def guard_runner(path, report, **kwargs):
            guarded.append((Path(path), Path(report)))
            return {"verdict": "PASS", "findings": []}

        result = gate.evaluate(
            repo=self.repo,
            today=TODAY,
            scanner=self.pass_scan,
            guard_runner=guard_runner,
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(guarded, [(image.resolve(), receipt.resolve())])
        self.assertEqual(result["coverage"]["future_routes"], 2)
        self.assertEqual(result["coverage"]["deduplicated_guard_bindings"], 1)

    def test_canonical_reel_poster_requires_discoverable_hash_bound_receipt(self) -> None:
        poster = self.asset("reels/poster.png")
        without = gate.evaluate(repo=self.repo, today=TODAY, scanner=self.pass_scan)
        self.assertEqual(without["verdict"], "FAIL")
        self.assertTrue(any("hash-bound QA receipt is missing" in item for item in without["findings"]))

        receipt = self.indexed_report(poster)
        guarded = []

        def no_video_scan(path, fps):
            self.fail("canonical still was sent to the Veo video detector")

        def guard_runner(path, report, **kwargs):
            guarded.append((Path(path), Path(report)))
            return {"verdict": "PASS", "findings": []}

        with_receipt = gate.evaluate(
            repo=self.repo, today=TODAY, scanner=no_video_scan, guard_runner=guard_runner)
        self.assertEqual(with_receipt["verdict"], "PASS")
        self.assertEqual(guarded, [(poster.resolve(), receipt.resolve())])
        self.assertEqual(with_receipt["coverage"]["canonical_image_guards"], 1)

    def test_quarantine_route_is_rejected_without_scanning_or_guarding(self) -> None:
        self.asset("media/quarantine/watermarked/stills/bad.png")
        self.report()
        self.write_schedule({
            "2026-08-17": {
                "asset": "media/quarantine/watermarked/stills/bad.png",
                "qa_report": "automation-log/media-qa/test.json",
            }
        })
        guard_calls = []

        def guard_runner(*args, **kwargs):
            guard_calls.append(args)
            return {"verdict": "PASS", "findings": []}

        result = gate.evaluate(
            repo=self.repo, today=TODAY, scanner=self.pass_scan, guard_runner=guard_runner)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(guard_calls, [])
        self.assertTrue(any("outside approved" in item for item in result["findings"]))

    def test_mixed_valid_and_invalid_media_list_fails_closed(self) -> None:
        self.asset("reels/future.mp4")
        self.report()
        self.write_schedule({
            "2026-08-17": {
                "media": [
                    {"file": "future.mp4", "qa_report": "automation-log/media-qa/test.json"},
                    "silently-invalid-route",
                ]
            }
        })
        result = gate.evaluate(repo=self.repo, today=TODAY, scanner=self.pass_scan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("media routes are missing or invalid" in item for item in result["findings"]))

    def test_scanner_fail_and_error_both_block(self) -> None:
        self.asset("reels/current.mp4")
        self.write_manifest([{"id": "current", "reel": "reels/current.mp4"}])
        for verdict in ("FAIL", "ERROR"):
            with self.subTest(verdict=verdict):
                result = gate.evaluate(
                    repo=self.repo,
                    today=TODAY,
                    scanner=lambda path, fps, value=verdict: {"verdict": value, "frames": 12},
                )
                self.assertEqual(result["verdict"], "FAIL")
                self.assertTrue(any(f"frame scan {verdict}" in item for item in result["findings"]))

    def test_unreadable_control_files_fail_closed(self) -> None:
        (self.repo / ".system_control/content_manifest.json").write_text("{", encoding="utf-8")
        (self.repo / "reels/schedule.json").unlink()
        result = gate.evaluate(repo=self.repo, today=TODAY, scanner=self.pass_scan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertGreaterEqual(len(result["findings"]), 2)

    def test_ambiguous_or_overflow_control_json_fails_closed(self) -> None:
        manifest = self.repo / ".system_control/content_manifest.json"
        for malformed in (
            '{"items":[],"items":[]}',
            '{"items":[],"probe":1e999}',
        ):
            with self.subTest(malformed=malformed):
                manifest.write_text(malformed, encoding="utf-8")
                result = gate.evaluate(repo=self.repo, today=TODAY, scanner=self.pass_scan)
                self.assertEqual(result["verdict"], "FAIL")
                self.assertTrue(any("manifest" in item for item in result["findings"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
