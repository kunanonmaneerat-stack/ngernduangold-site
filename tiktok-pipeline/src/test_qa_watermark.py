#!/usr/bin/env python3
# ASCII-ONLY. Unit-proof for qa_watermark.py (order 2026-07-09 T3).
# Fixtures with KNOWN ground truth:
#   FAIL: media/quarantine/watermarked/raw-veo/title-loan-2026.mp4
#         (raw Veo footage, sparkle visible ~30/30 frames)
#   PASS: _vidout/clean/reel_title-loan-2026_clean.mp4 (07_render kinetic text, no footage)
# Run:  python tiktok-pipeline/src/test_qa_watermark.py   -> exit 0 = 2/2 pass, 1 = broken gate.
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import qa_watermark as QW

DIRTY = os.path.join(
    REPO, "media", "quarantine", "watermarked", "raw-veo",
    "title-loan-2026.mp4",
)
CLEAN = os.path.join(REPO, "_vidout", "clean", "reel_title-loan-2026_clean.mp4")


class WatermarkQATests(unittest.TestCase):
    def test_known_watermarked_clip_fails(self):
        result = QW.scan(DIRTY, fps=3)
        self.assertEqual(result.get("verdict"), "FAIL", result)

    def test_known_clean_render_passes(self):
        result = QW.scan(CLEAN, fps=3)
        self.assertEqual(result.get("verdict"), "PASS", result)

    def test_unsafe_low_sample_scan_fails_closed(self):
        result = QW.scan(DIRTY, fps=0.1)
        self.assertEqual(result.get("verdict"), "ERROR", result)

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
