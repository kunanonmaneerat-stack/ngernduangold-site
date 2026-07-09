#!/usr/bin/env python3
# ASCII-ONLY. Unit-proof for qa_watermark.py (order 2026-07-09 T3).
# Fixtures with KNOWN ground truth:
#   FAIL: media/clips/title-loan-2026.mp4      (raw Veo footage, sparkle visible ~30/30 frames)
#   PASS: _vidout/clean/reel_title-loan-2026_clean.mp4 (07_render kinetic text, no footage)
# Run:  python tiktok-pipeline/src/test_qa_watermark.py   -> exit 0 = 2/2 pass, 1 = broken gate.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import qa_watermark as QW

def main():
    dirty = os.path.join(REPO, "media", "clips", "title-loan-2026.mp4")
    clean = os.path.join(REPO, "_vidout", "clean", "reel_title-loan-2026_clean.mp4")
    ok = True
    r1 = QW.scan(dirty, fps=3)
    if r1.get("verdict") != "FAIL":
        print("BROKEN: known-watermarked clip did not FAIL ->", r1); ok = False
    else:
        print("ok: dirty fixture FAIL (%s/%s frames)" % (r1["track_frames"], r1["frames"]))
    r2 = QW.scan(clean, fps=3)
    if r2.get("verdict") != "PASS":
        print("BROKEN: known-clean 07_render clip did not PASS ->", r2); ok = False
    else:
        print("ok: clean fixture PASS (%s/%s frames)" % (r2["track_frames"], r2["frames"]))
    print("test_qa_watermark:", "2/2 PASS" if ok else "FAILED")
    return 0 if ok else 1

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
