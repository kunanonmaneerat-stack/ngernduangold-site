from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import next48_media_revalidation as revalidation
import next48_owner_decision_packet as packet


AS_OF = datetime.fromisoformat("2026-08-30T22:49:00+07:00")


class Next48MediaRevalidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / ".system_control").mkdir(parents=True)
        (self.repo / "automation-log/media-qa").mkdir(parents=True)
        for name, relative in packet.MEDIA_REVALIDATION_IMPLEMENTATIONS.items():
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# immutable test implementation: {name}\n", encoding="utf-8")
        (self.repo / "source.json").write_text("{}\n", encoding="utf-8")
        for name in ("image.jpg", "video.mp4", "outside.jpg"):
            (self.repo / name).write_bytes(name.encode("ascii"))
            (self.repo / f"{name}.receipt.json").write_text("{}\n", encoding="utf-8")
        placements = [
            self.placement("text__threads_main", "2026-08-31", "12:40", "text"),
            self.placement("image__instagram_main", "2026-08-31", "19:00", "image", "image.jpg"),
            self.placement("video__facebook_main", "2026-09-01", "19:00", "video", "video.mp4"),
            self.placement("outside__instagram_main", "2026-09-02", "23:00", "image", "outside.jpg"),
        ]
        (self.repo / ".system_control/content_calendar.json").write_text(
            json.dumps({"placements": placements}), encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def placement(placement_id, day, clock, media_type, asset=None):
        return {
            "placement_id": placement_id,
            "date": day,
            "time": clock,
            "format": media_type,
            "media": asset,
            "media_receipt": f"{asset}.receipt.json" if asset else None,
            "source": {"file": "source.json", "row_id": "row", "field": "copy"},
        }

    @staticmethod
    def guard(asset, receipt, *, repo, now=None, scanner=None):
        media_type = "video" if Path(asset).suffix == ".mp4" else "image"
        findings = ["human audio review is missing"] if media_type == "video" else []
        return {
            "verdict": "FAIL" if findings else "PASS",
            "media_type": media_type,
            "findings": findings,
            "fresh_scan": {
                "file": str(Path(asset).resolve()),
                "verdict": "PASS",
                "frames": 12,
                "track_frames": 0,
            } if media_type == "video" else None,
            "publication_authority_granted": False,
        }

    def selector_inputs(self):
        calendar_path = self.repo / ".system_control/content_calendar.json"
        calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
        end = AS_OF + timedelta(hours=48)
        selected = packet._select_window_placements(
            calendar["placements"], AS_OF, end
        )
        return calendar_path, end, selected

    def write_resigned_receipt(self, payload: dict, name: str = "tampered") -> Path:
        unsigned = dict(payload)
        unsigned.pop("receipt_payload_sha256", None)
        payload["receipt_payload_sha256"] = packet._canonical_sha256(unsigned)
        output = (
            self.repo
            / f"automation-log/media-qa/NEXT48-MEDIA-REVALIDATION-RECEIPT_{name}.json"
        )
        output.write_text(json.dumps(payload), encoding="utf-8")
        return output

    def select_receipt(self, calendar_path: Path, end: datetime, selected: list[dict]):
        return packet._media_index(
            self.repo,
            packet._sha256(calendar_path),
            AS_OF,
            end,
            selected,
            guard_runner=self.guard,
        )

    def test_exact_window_is_deterministic_and_preserves_human_blocker(self):
        first = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        second = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [row["placement_id"] for row in first["placements"]],
            ["image__instagram_main", "video__facebook_main"],
        )
        self.assertEqual(first["summary"]["calendar_placements_in_window"], 3)
        self.assertEqual(first["summary"]["media_placements_in_window"], 2)
        self.assertEqual(first["summary"]["human_audio_reviews_outstanding"], 1)
        self.assertFalse(first["summary"]["publication_authority_granted"])
        self.assertEqual(
            set(first["guard_implementation"]),
            set(packet.MEDIA_REVALIDATION_IMPLEMENTATIONS),
        )
        video = first["placements"][1]
        self.assertEqual(
            video["media_publish_guard"]["finding"],
            "human audio review is missing",
        )
        scan = video["fresh_automated_qa"]
        self.assertNotIn("file", scan)
        self.assertEqual(scan["asset"], "video.mp4")
        rendered = json.dumps(first)
        self.assertNotIn(str(self.repo), rendered)
        self.assertNotIn("\\\\", rendered)
        unsigned = dict(first)
        unsigned.pop("receipt_payload_sha256")
        self.assertEqual(
            first["receipt_payload_sha256"], packet._canonical_sha256(unsigned)
        )

    def test_guard_evaluation_is_bound_to_exact_window_anchor(self):
        observed = []

        def tracking_guard(asset, receipt, *, repo, now=None):
            observed.append(now)
            return self.guard(asset, receipt, repo=repo, now=now)

        revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=tracking_guard
        )
        self.assertEqual(observed, [AS_OF, AS_OF])

    def test_guard_cannot_grant_authority(self):
        def bad_guard(asset, receipt, *, repo, now=None):
            result = self.guard(asset, receipt, repo=repo, now=now)
            result["publication_authority_granted"] = True
            return result

        with self.assertRaisesRegex(
            revalidation.RevalidationError, "attempted to grant"
        ):
            revalidation.build_receipt(
                self.repo, AS_OF, guard_runner=bad_guard
            )

    def test_calendar_media_type_mismatch_fails_closed(self):
        calendar = json.loads(
            (self.repo / ".system_control/content_calendar.json").read_text()
        )
        calendar["placements"][1]["format"] = "video"
        (self.repo / ".system_control/content_calendar.json").write_text(
            json.dumps(calendar), encoding="utf-8"
        )
        with self.assertRaisesRegex(
            revalidation.RevalidationError, "calendar/media type mismatch"
        ):
            revalidation.build_receipt(
                self.repo, AS_OF, guard_runner=self.guard
            )

    def test_selector_rejects_transitive_dependency_drift(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        output = (
            self.repo
            / "automation-log/media-qa/NEXT48-MEDIA-REVALIDATION-RECEIPT_test.json"
        )
        revalidation.write_receipt(output, receipt, self.repo)
        calendar_path, end, selected = self.selector_inputs()
        index, _binding = self.select_receipt(calendar_path, end, selected)
        self.assertEqual(set(index), {"image__instagram_main", "video__facebook_main"})

        scanner = self.repo / packet.MEDIA_REVALIDATION_IMPLEMENTATIONS["watermark_scanner"]
        scanner.write_text("# changed scanner\n", encoding="utf-8")
        with self.assertRaisesRegex(
            packet.PacketError, "implementation has changed: watermark_scanner"
        ):
            self.select_receipt(calendar_path, end, selected)

    def test_selector_rejects_resigned_implementation_tamper(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        receipt["guard_implementation"]["generative_media_origin_gate"]["sha256"] = "0" * 64
        self.write_resigned_receipt(receipt)
        calendar_path, end, selected = self.selector_inputs()
        with self.assertRaisesRegex(
            packet.PacketError,
            "implementation has changed: generative_media_origin_gate",
        ):
            self.select_receipt(calendar_path, end, selected)

    def test_selector_rejects_resigned_evaluation_time_drift(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        receipt["evaluated_at"] = (AS_OF + timedelta(seconds=1)).isoformat()
        self.write_resigned_receipt(receipt)
        calendar_path, end, selected = self.selector_inputs()
        with self.assertRaisesRegex(
            packet.PacketError, "evaluation time differs from the window"
        ):
            self.select_receipt(calendar_path, end, selected)

    def test_selector_rejects_resigned_gate_finding_mismatch(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        video = next(
            row for row in receipt["placements"]
            if row["placement_id"] == "video__facebook_main"
        )
        video["media_publish_guard"]["finding"] = "different finding"
        self.write_resigned_receipt(receipt)
        calendar_path, end, selected = self.selector_inputs()
        with self.assertRaisesRegex(
            packet.PacketError, "gate evidence is inconsistent"
        ):
            self.select_receipt(calendar_path, end, selected)

    def test_selector_rejects_resigned_private_scan_field(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        video = next(
            row for row in receipt["placements"]
            if row["placement_id"] == "video__facebook_main"
        )
        video["fresh_automated_qa"]["file"] = str(
            (self.repo / "video.mp4").resolve()
        )
        self.write_resigned_receipt(receipt)
        calendar_path, end, selected = self.selector_inputs()
        with self.assertRaisesRegex(
            packet.PacketError, "fresh video scan differs"
        ):
            self.select_receipt(calendar_path, end, selected)

    def test_selector_rejects_resigned_summary_count_drift(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        receipt["summary"]["human_audio_reviews_outstanding"] = 0
        self.write_resigned_receipt(receipt)
        calendar_path, end, selected = self.selector_inputs()
        with self.assertRaisesRegex(
            packet.PacketError, "summary is inconsistent"
        ):
            self.select_receipt(calendar_path, end, selected)

    def test_selector_rejects_resigned_source_binding_drift(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        receipt["placements"][0]["source_binding"]["row_id"] = "other-row"
        self.write_resigned_receipt(receipt)
        calendar_path, end, selected = self.selector_inputs()
        with self.assertRaisesRegex(
            packet.PacketError, "source binding differs"
        ):
            self.select_receipt(calendar_path, end, selected)

    def test_selector_rejects_coordinated_resigned_verdict_promotion(self):
        receipt = revalidation.build_receipt(
            self.repo, AS_OF, guard_runner=self.guard
        )
        video = next(
            row for row in receipt["placements"]
            if row["placement_id"] == "video__facebook_main"
        )
        video["media_publish_guard"] = {
            "verdict": "PASS",
            "findings": [],
            "finding": None,
            "publication_authority_granted": False,
        }
        video["state"] = "MEDIA_GATE_PASS_AUTHORITY_STILL_BLOCKED"
        receipt["summary"].update({
            "media_publish_guard_pass": 2,
            "media_publish_guard_blocked": 0,
            "human_audio_reviews_outstanding": 0,
            "verdict": "COMPLETED_MEDIA_PASS_AUTHORITY_BLOCKED",
        })
        self.write_resigned_receipt(receipt)
        calendar_path, end, selected = self.selector_inputs()
        with self.assertRaisesRegex(
            packet.PacketError, "guard replay differs"
        ):
            self.select_receipt(calendar_path, end, selected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
