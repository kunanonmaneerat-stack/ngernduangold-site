#!/usr/bin/env python3
"""Fail-closed technical guard for the voice-only weekly TikTok r5 candidates."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "automation-log" / "WEEK-CONTENT-PACK_20260824-30.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = _load_module(
    "week_tiktok_r5_renderer", ROOT / "tools" / "render_week_tiktok_candidates.py"
)
finalizer = _load_module(
    "week_tiktok_r5_finalizer", ROOT / "tiktok-pipeline" / "src" / "09_finalize_video.py"
)


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _repo_path(raw: object) -> Path:
    path = Path(str(raw))
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"path leaves repository: {raw}") from exc
    return path


def evaluate(asset_raw: str | Path, receipt_raw: str | Path) -> dict:
    findings: list[str] = []
    asset = _repo_path(asset_raw)
    receipt_path = _repo_path(receipt_raw)
    try:
        receipt = _json(receipt_path)
    except Exception as exc:
        return {
            "verdict": "FAIL",
            "asset": str(asset),
            "findings": [f"receipt unreadable: {exc}"],
        }

    try:
        pack, days = renderer.load_candidates(PACK_PATH)
        if pack.get("state") != "DRAFT_ONLY":
            findings.append("weekly pack is not DRAFT_ONLY")
        if pack.get("pack_id") != renderer.TARGET_PACK_ID:
            findings.append("projected weekly pack is not r5")
        binding = receipt.get("source_binding") or {}
        candidate_id = str(binding.get("candidate_id") or "")
        day = next((item for item in days if item["candidate_id"] == candidate_id), None)
        if day is None:
            findings.append("receipt candidate is not in the projected r5 pack")
        if not asset.is_file() or asset.stat().st_size == 0:
            findings.append("asset is missing or empty")
        else:
            expected_root = (ROOT / "reels" / "week-20260824-30-r5").resolve()
            try:
                asset.relative_to(expected_root)
            except ValueError:
                findings.append("asset is outside the canonical r5 video root")
        if receipt.get("schema_version") != 1 or receipt.get("media_type") != "video":
            findings.append("receipt schema/media type mismatch")
        rel_asset = asset.relative_to(ROOT).as_posix()
        if receipt.get("asset") != rel_asset:
            findings.append("receipt asset path mismatch")
        actual_hash = renderer.sha256_file(asset) if asset.is_file() else None
        if not actual_hash or receipt.get("sha256") != actual_hash:
            findings.append("asset SHA-256 mismatch")

        technical = receipt.get("technical_qa") or {}
        if "ambient_bed" in technical or "ambient_bed" in binding:
            findings.append("ambient-bed evidence is forbidden in r5")
        lineage = technical.get("audio_lineage") or {}
        if lineage.get("status") != "PASS_SINGLE_LOCAL_TTS_SOURCE_NO_MIX":
            findings.append("single-source audio lineage is not PASS")
        if lineage.get("audio_input_count") != 1:
            findings.append("audio lineage does not have exactly one input")
        if lineage.get("source_kind") != "LOCAL_WINDOWS_TTS_EXACT_TEXT":
            findings.append("audio source is not the exact local Windows TTS source")
        if lineage.get("ambient_or_music_sources") != []:
            findings.append("ambient or music source is present")
        if lineage.get("foreign_audio_sources") != []:
            findings.append("foreign audio source is present")
        if lineage.get("human_listening_status") != "NOT_PERFORMED":
            findings.append("human listening status is overstated")

        source_audio = _repo_path(lineage.get("source_audio", ""))
        voice_track = _repo_path(lineage.get("voice_track", ""))
        private_root = (
            ROOT / ".local-private" / "runtime" / "week-tiktok-render-r5"
        ).resolve()
        for label, path in (("source TTS", source_audio), ("voice-only track", voice_track)):
            try:
                path.relative_to(private_root)
            except ValueError:
                findings.append(f"{label} is outside the r5 private render root")
            if not path.is_file():
                findings.append(f"{label} is missing")
        if source_audio.is_file() and renderer.sha256_file(source_audio) != lineage.get(
            "source_audio_sha256"
        ):
            findings.append("source TTS hash mismatch")
        if voice_track.is_file() and renderer.sha256_file(voice_track) != lineage.get(
            "voice_track_sha256"
        ):
            findings.append("voice-only track hash mismatch")
        if asset.is_file() and voice_track.is_file():
            final_packets = renderer._audio_packet_hash(asset)
            voice_packets = renderer._audio_packet_hash(voice_track)
            if final_packets != voice_packets:
                findings.append("final audio packets are not copied from the voice-only track")
            if final_packets != lineage.get("final_audio_packet_sha256"):
                findings.append("recorded final audio packet hash mismatch")
            if voice_packets != lineage.get("voice_track_audio_packet_sha256"):
                findings.append("recorded voice-track packet hash mismatch")
        if lineage.get("packet_binding") != "PASS_EXACT_PACKET_COPY":
            findings.append("exact audio packet binding is not PASS")

        if day is not None:
            expected_text = renderer.scene_texts(day)
            if binding.get("weekly_pack_id") != renderer.TARGET_PACK_ID:
                findings.append("receipt weekly pack ID is not r5")
            if binding.get("exact_visible_copy") != expected_text:
                findings.append("exact visible copy differs from the projected r5 pack")
            expected_payload = renderer.stable_json_sha256(
                renderer._content_payload(day["tiktok_draft"])
            )
            if binding.get("content_payload_sha256") != expected_payload:
                findings.append("content payload hash differs from projected r5 copy")
            combined = "\n".join(expected_text + [day["tiktok_draft"]["voiceover"]])
            for forbidden in ("หนี้ของเขา", "ภาระทั้งหมด", "รดน้ำมัน"):
                if forbidden in combined:
                    findings.append(f"superseded wording remains: {forbidden}")

        timing = technical.get("timing") or {}
        frame_counts = timing.get("scene_frame_counts") or []
        if frame_counts != binding.get("scene_frame_counts"):
            findings.append("receipt scene frame binding mismatch")
        if not frame_counts or sum(frame_counts) != timing.get("total_frames"):
            findings.append("scene frames do not sum to the planned total")
        else:
            if any(
                count < renderer.MIN_SCENE_DWELL_SECONDS * renderer.FPS
                for count in frame_counts[:-1]
            ):
                findings.append("a non-final scene dwell is too short")
            if frame_counts[-1] < renderer.MIN_END_CARD_DWELL_SECONDS * renderer.FPS:
                findings.append("AI disclosure dwell is too short")
        if float(timing.get("end_card_start_seconds", 1e9)) > float(
            timing.get("narration_last_active_seconds", -1)
        ):
            findings.append("AI disclosure begins after narration ends")
        if float(timing.get("planned_tail_after_narration_seconds", 1e9)) > 1.0:
            findings.append("planned post-narration tail exceeds one second")
        if asset.is_file() and timing.get("total_frames") is not None:
            if renderer._count_video_frames(asset) != int(timing["total_frames"]):
                findings.append("fresh decoded frame count differs from timing receipt")

        evidence_hashes = binding.get("scene_evidence_sha256") or {}
        if len(evidence_hashes) < len(binding.get("exact_visible_copy") or []) + 2:
            findings.append("source/encoded visual evidence set is incomplete")
        for raw, expected_hash in evidence_hashes.items():
            evidence = _repo_path(raw)
            if not evidence.is_file() or renderer.sha256_file(evidence) != expected_hash:
                findings.append(f"visual evidence hash mismatch: {raw}")

        if asset.is_file() and timing.get("duration_seconds") is not None:
            fresh = finalizer.validate_final(
                asset,
                float(timing["duration_seconds"]) - 0.12,
                float(timing["duration_seconds"]) + 0.12,
            )
            if fresh.get("full_decode") != "PASS":
                findings.append("fresh full decode is not PASS")
            if (fresh.get("watermark") or {}).get("verdict") != "PASS":
                findings.append("fresh watermark scan is not PASS")
            if (fresh.get("loudness") or {}).get("status") != "PASS":
                findings.append("fresh loudness/true-peak guard is not PASS")
            silence = renderer._digital_silence_audit(
                asset,
                expected_narration_end_seconds=timing.get(
                    "narration_last_active_seconds"
                ),
            )
            if silence.get("threshold_silence_events_at_or_above_limit") != 0:
                findings.append("fresh silence detector found a prohibited interval")
            if float((silence.get("post_narration_tail") or {}).get("duration_seconds", 9)) > 1.0:
                findings.append("fresh post-narration tail exceeds one second")
        else:
            fresh = None
            silence = None
    except Exception as exc:
        findings.append(f"guard execution failed closed: {type(exc).__name__}: {exc}")
        fresh = None
        silence = None
        actual_hash = renderer.sha256_file(asset) if asset.is_file() else None

    return {
        "verdict": "PASS" if not findings else "FAIL",
        "asset": str(asset),
        "sha256": actual_hash,
        "findings": findings,
        "fresh_media_qa": fresh,
        "fresh_silence_qa": silence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(args.asset, args.receipt)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["verdict"], result["asset"])
        for finding in result["findings"]:
            print("- " + finding)
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
