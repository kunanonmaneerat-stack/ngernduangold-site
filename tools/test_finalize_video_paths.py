#!/usr/bin/env python3
"""Destructive-path regression checks for the video finalizer."""
import importlib.util
import pathlib
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tiktok-pipeline" / "src" / "09_finalize_video.py"
SPEC = importlib.util.spec_from_file_location("finalize_video", MODULE_PATH)
FINALIZE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FINALIZE)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def rejected(video, voice, out, report):
    before = {p: p.read_bytes() for p in (video, voice) if p.exists()}
    try:
        FINALIZE.validate_paths(video, voice, out, report)
        result = False
    except ValueError:
        result = True
    return result and all(path.read_bytes() == data for path, data in before.items())


def main():
    staging = ROOT / "_vidout"
    staging.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="path_guard_", dir=staging) as raw:
        temp = pathlib.Path(raw)
        video = temp / "video.mp4"
        voice = temp / "voice.wav"
        out = temp / "final.mp4"
        report = temp / "qa.json"
        video.write_bytes(b"VIDEO-SENTINEL")
        voice.write_bytes(b"VOICE-SENTINEL")
        check("report cannot alias video", rejected(video, voice, out, video))
        check("report cannot alias voice", rejected(video, voice, out, voice))
        check("report cannot alias output", rejected(video, voice, out, out))
        check("output cannot alias video", rejected(video, voice, video, report))
        outside = pathlib.Path(tempfile.gettempdir()) / "ngernduangold-outside-final.mp4"
        check("outside-repository output is rejected before writes",
              rejected(video, voice, outside, report) and not outside.exists())
        got = FINALIZE.validate_paths(video, voice, out, report)
        check("distinct approved paths pass", got[2] == out.resolve() and got[3] == report.resolve())
    print("finalize video path guard: all checks passed")


if __name__ == "__main__":
    main()
