#!/usr/bin/env python3
"""Mux narration into a rendered vertical video and fail closed on delivery specs."""

import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
from fractions import Fraction


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
APPROVED_OUTPUT_ROOTS = (REPO_ROOT / "reels", REPO_ROOT / "_vidout")
APPROVED_REPORT_ROOTS = (
    REPO_ROOT / "automation-log" / "video-production",
    REPO_ROOT / "_vidout",
    REPO_ROOT / "reports",
)
EXPECTED_FPS = Fraction(24, 1)
EXPECTED_SAMPLE_RATE = 48000
LOUDNESS_MIN_LUFS = -18.0
LOUDNESS_MAX_LUFS = -14.0
TRUE_PEAK_MAX_DBFS = -1.0


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed")[-1200:])
    return result


def probe(path):
    raw = run([
        FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ]).stdout
    return json.loads(raw)


def repo_relative(path):
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("final video must stay inside the repository for auditable reporting") from exc


def _under(path, roots):
    for root in roots:
        try:
            path.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def validate_paths(video, voice, out, report_path=None):
    """Validate every path before mkdir, unlink, mux or report writes."""
    video, voice, out = (pathlib.Path(p).resolve() for p in (video, voice, out))
    report_path = pathlib.Path(report_path).resolve() if report_path else None
    if out in (video, voice):
        raise ValueError("output must not overwrite an input")
    if out.suffix.lower() != ".mp4" or not _under(out, APPROVED_OUTPUT_ROOTS):
        raise ValueError("output must be an MP4 under reels/ or _vidout/")
    if report_path:
        if report_path in (video, voice, out):
            raise ValueError("report must be distinct from video, voice and output")
        if report_path.suffix.lower() != ".json" or not _under(report_path, APPROVED_REPORT_ROOTS):
            raise ValueError("report must be JSON under automation-log/video-production, _vidout or reports")
    return video, voice, out, report_path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def mp4_faststart(path):
    """Return top-level MP4 atom offsets and require moov before media data."""
    positions = {}
    total = path.stat().st_size
    offset = 0
    with path.open("rb") as handle:
        while offset + 8 <= total:
            handle.seek(offset)
            header = handle.read(8)
            atom_size = int.from_bytes(header[:4], "big")
            atom_type = header[4:8].decode("ascii", errors="replace")
            header_size = 8
            if atom_size == 1:
                extended = handle.read(8)
                if len(extended) != 8:
                    raise ValueError("truncated extended MP4 atom")
                atom_size = int.from_bytes(extended, "big")
                header_size = 16
            elif atom_size == 0:
                atom_size = total - offset
            if atom_size < header_size or offset + atom_size > total:
                raise ValueError(f"invalid MP4 atom {atom_type!r} at offset {offset}")
            positions.setdefault(atom_type, offset)
            offset += atom_size
    if "moov" not in positions or "mdat" not in positions:
        raise ValueError("final MP4 must contain moov and mdat atoms")
    if positions["moov"] > positions["mdat"]:
        raise ValueError("final MP4 is not faststart: moov atom follows mdat")
    return {"status": "PASS", "moov_offset": positions["moov"], "mdat_offset": positions["mdat"]}


def analyze_loudness(path):
    null_target = "NUL" if sys.platform.startswith("win") else "/dev/null"
    result = run([
        FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", null_target,
    ])
    matches = re.findall(r'\{\s*"input_i".*?\}', result.stderr, flags=re.DOTALL)
    if not matches:
        raise ValueError("ffmpeg did not return a loudness measurement")
    measured = json.loads(matches[-1])
    try:
        integrated = float(measured["input_i"])
        true_peak = float(measured["input_tp"])
        loudness_range = float(measured["input_lra"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid loudness measurement") from exc
    if not math.isfinite(integrated) or not math.isfinite(true_peak):
        raise ValueError("final audio is silent or has non-finite loudness")
    if not LOUDNESS_MIN_LUFS <= integrated <= LOUDNESS_MAX_LUFS:
        raise ValueError(
            f"integrated loudness {integrated:.2f} LUFS outside "
            f"{LOUDNESS_MIN_LUFS:.1f} to {LOUDNESS_MAX_LUFS:.1f} LUFS"
        )
    if true_peak > TRUE_PEAK_MAX_DBFS:
        raise ValueError(f"true peak {true_peak:.2f} dBFS exceeds {TRUE_PEAK_MAX_DBFS:.1f} dBFS")
    return {
        "status": "PASS",
        "non_silent": "PASS",
        "integrated_lufs": integrated,
        "true_peak_dbfs": true_peak,
        "loudness_range_lu": loudness_range,
        "guard": {
            "integrated_lufs_min": LOUDNESS_MIN_LUFS,
            "integrated_lufs_max": LOUDNESS_MAX_LUFS,
            "true_peak_dbfs_max": TRUE_PEAK_MAX_DBFS,
        },
    }


def scan_watermark(path, fps=3.0):
    scanner = pathlib.Path(__file__).with_name("qa_watermark.py")
    if not scanner.is_file():
        raise ValueError("watermark scanner is missing")
    result = run([sys.executable, str(scanner), str(path), "--fps", str(fps), "--json"])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("watermark scanner returned no result")
    measured = json.loads(lines[-1])
    if measured.get("verdict") != "PASS":
        raise ValueError("watermark scan did not pass")
    measured.pop("file", None)
    measured["fps"] = fps
    return measured


def validate_final(path, minimum_duration, maximum_duration):
    path = path.resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("final video is missing or empty")
    data = probe(path)
    streams = data.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise ValueError("final file must contain exactly one video and one audio stream")
    video, audio = videos[0], audios[0]
    if (video.get("width"), video.get("height")) != (1080, 1920):
        raise ValueError("final video must be 1080x1920")
    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        raise ValueError("final video must be H.264 yuv420p")
    try:
        fps = Fraction(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError("final video has an unreadable frame rate") from exc
    if fps != EXPECTED_FPS:
        raise ValueError(f"final video must be exactly 24 fps, got {fps}")
    if audio.get("codec_name") != "aac" or int(audio.get("channels", 0)) != 1:
        raise ValueError("final audio must be mono AAC")
    if int(audio.get("sample_rate", 0)) != EXPECTED_SAMPLE_RATE:
        raise ValueError("final audio must be exactly 48000 Hz")
    duration = float(data.get("format", {}).get("duration", 0))
    if not minimum_duration <= duration <= maximum_duration:
        raise ValueError(
            f"duration {duration:.2f}s outside allowed {minimum_duration:.2f}-{maximum_duration:.2f}s"
        )

    faststart = mp4_faststart(path)
    # Decode every frame and every audio packet. A probe-only pass can miss truncation.
    null_target = "NUL" if sys.platform.startswith("win") else "/dev/null"
    run([FFMPEG, "-v", "error", "-xerror", "-i", str(path), "-f", "null", null_target])
    loudness = analyze_loudness(path)
    watermark = scan_watermark(path)
    return {
        "file": repo_relative(path),
        "sha256": sha256_file(path),
        "qa_scope": "automated_media_only",
        "manual_checks_required": ["semantic_frame_review", "landing_page_qa"],
        "duration_seconds": round(duration, 3),
        "size_bytes": path.stat().st_size,
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": video.get("r_frame_rate"),
            "pixel_format": video.get("pix_fmt"),
        },
        "audio": {
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
        },
        "full_decode": "PASS",
        "faststart": faststart,
        "loudness": loudness,
        "watermark": watermark,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="silent H.264 video")
    parser.add_argument("--voice", required=True, help="narration audio")
    parser.add_argument("--out", required=True, help="final MP4")
    parser.add_argument("--report", default=None, help="optional JSON QA report")
    parser.add_argument("--min-duration", type=float, default=15.0)
    parser.add_argument("--max-duration", type=float, default=25.0)
    args = parser.parse_args()

    try:
        video, voice, out, report_path = validate_paths(
            args.video, args.voice, args.out, args.report)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    for source in (video, voice):
        if not source.is_file() or source.stat().st_size == 0:
            raise SystemExit(f"missing or empty input: {source}")
    if not FFMPEG or not FFPROBE:
        raise SystemExit("ffmpeg and ffprobe must be available on PATH")
    out.parent.mkdir(parents=True, exist_ok=True)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    temp_out = out.with_name(out.stem + f".tmp-{os.getpid()}" + out.suffix)
    temp_out.unlink(missing_ok=True)
    try:
        run([
            FFMPEG, "-y", "-v", "error", "-i", str(video), "-i", str(voice),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-af", "apad,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1",
            "-shortest", "-movflags", "+faststart", str(temp_out),
        ])
        report = validate_final(temp_out, args.min_duration, args.max_duration)
        report["file"] = repo_relative(out)
        os.replace(temp_out, out)
    except Exception:
        temp_out.unlink(missing_ok=True)
        raise
    if report_path:
        temp_report = report_path.with_name(report_path.name + f".tmp-{os.getpid()}")
        temp_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_report, report_path)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
