#!/usr/bin/env python3
"""Focused fail-closed contract for the blocked B3 TikTok media audit."""
from pathlib import Path
import hashlib
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
VIDEO_REPORTS = ROOT / "automation-log" / "video-production"
RECEIPTS = ROOT / "automation-log" / "media-qa"
EVIDENCE = ROOT / "_vidout" / "media-evidence-b3"
EXPECTED = tuple(f"b3-{number:02d}" for number in range(1, 7))

sys.path.insert(0, str(ROOT / "tools"))
import media_publish_guard  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    audio_hashes = set()
    for content_id in EXPECTED:
        report_path = VIDEO_REPORTS / f"{content_id}_qa.json"
        require(report_path.is_file(), f"missing report: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        require(report.get("content_id") == content_id, f"wrong content_id in {report_path}")
        require(report.get("verdict") == "BLOCKED", f"{content_id} must remain BLOCKED")
        require(report.get("receipt_created") is False, f"{content_id} must not claim a receipt")

        target = report.get("target_contract") or {}
        require(target.get("outbound_url_allowed") is False, f"{content_id} URL contract drift")
        require(target.get("affiliate_claim_expected") is False, f"{content_id} affiliate contract drift")
        require(target.get("provider_license_claim_allowed") is False, f"{content_id} license contract drift")

        asset = (ROOT / report["asset"]).resolve()
        staging = (ROOT / report["source_binding"]["staging_asset"]).resolve()
        require(asset.is_file() and staging.is_file(), f"{content_id} media source missing")
        actual = sha256(asset)
        require(actual == report.get("sha256"), f"{content_id} canonical hash drift")
        require(actual == sha256(staging), f"{content_id} staging is no longer byte-identical")
        require(report["source_binding"].get("byte_identical") is True, f"{content_id} source binding not recorded")
        require(report["source_binding"].get("voiceover_source_match") == "PASS", f"{content_id} source voice mismatch")

        technical = report.get("technical") or {}
        require(15.0 <= float(technical.get("duration_seconds", 0)) <= 25.0, f"{content_id} duration out of contract")
        require(technical.get("full_decode") == "PASS", f"{content_id} video decode not PASS")
        require(technical.get("audio_decode") == "PASS", f"{content_id} audio decode not PASS")
        require(technical.get("non_silent") == "PASS", f"{content_id} audio is silent or unverified")
        require((technical.get("video") or {}).get("width") == 1080, f"{content_id} width drift")
        require((technical.get("video") or {}).get("height") == 1920, f"{content_id} height drift")
        audio_hash = technical.get("decoded_pcm_sha256")
        require(isinstance(audio_hash, str) and len(audio_hash) == 64, f"{content_id} missing decoded audio hash")
        require(audio_hash not in audio_hashes, f"{content_id} decoded audio duplicates another B3 piece")
        audio_hashes.add(audio_hash)

        watermark = report.get("watermark") or {}
        automated = watermark.get("automated_scan") or {}
        require(automated.get("status") == "PASS", f"{content_id} recorded mark scan not PASS")
        require(automated.get("track_frames") == 0, f"{content_id} recorded mark track is nonzero")
        visual = watermark.get("full_frame_visual_review") or {}
        require(visual.get("status") == "PASS_NO_THIRD_PARTY_WATERMARK", f"{content_id} visual mark review missing")
        require(visual.get("intentional_brand") == "@ngernduangold", f"{content_id} intentional brand drift")

        semantic = report.get("semantic_review") or {}
        require(semantic.get("status") == "FAIL", f"{content_id} semantic failure must stay explicit")
        blockers = "\n".join(semantic.get("blockers") or [])
        require("AFFILIATE_MISMATCH" in blockers, f"{content_id} affiliate blocker missing")
        require("UNSUBSTANTIATED_LICENSE_CLAIM" in blockers, f"{content_id} license blocker missing")
        require("NO_LINK_MISMATCH" in blockers or "OUTBOUND_URL_MISMATCH" in blockers, f"{content_id} no-link blocker missing")

        evidence = (report.get("visual_evidence") or {}).get("files") or []
        require(len(evidence) == 9, f"{content_id} must retain a contact sheet plus eight full frames")
        for raw in evidence:
            path = (ROOT / raw).resolve()
            require(path.is_relative_to(ROOT) and path.is_file(), f"{content_id} evidence missing/outside repo: {raw}")

        receipt = RECEIPTS / f"{content_id}-video.json"
        require(not receipt.exists(), f"receipt must not exist for blocked media: {receipt}")
        guard_result = media_publish_guard.evaluate(asset, receipt, repo=ROOT)
        require(guard_result.get("verdict") == "FAIL", f"media guard must fail closed for {content_id}")
        require(any("receipt is missing or unreadable" in item for item in guard_result.get("findings", [])),
                f"media guard did not report the missing {content_id} receipt")

    require(not (VIDEO_REPORTS / "b3-07_qa.json").exists(), "b3-07 must stay outside this evidence set")
    require(not (EVIDENCE / "b3-07").exists(), "b3-07 evidence must not be generated")
    require(not list(RECEIPTS.glob("b3-*-video.json")), "blocked B3 receipts must remain absent")
    print("B3 TikTok media evidence: 6/6 BLOCKED contract PASS; 0 receipts; b3-07 excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
