#!/usr/bin/env python3
"""Regression checks for the hash-bound image/video publication guard."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import media_publish_guard as guard


ORIGIN = {
    "generator_origin": "LOCAL_HTML_CSS_BROWSER_RENDER",
    "contains_flow_pixels": False,
    "contains_flow_audio": False,
    "synthid_expected": False,
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def receipt(repo, asset, media_type, *, visual="PASS", automated="PASS",
            human="PASS", outside=False, include_origin=True, origin=None):
    payload = {
        "schema_version": 1,
        "asset": asset.relative_to(repo).as_posix(),
        "sha256": digest(asset),
        "media_type": media_type,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "novelty_review": {
            "status": "PASS",
            "content_id": asset.stem,
            "reviewer": "unit-test-reviewer",
            "corpus_fingerprint": guard.publication_corpus_fingerprint(repo),
        },
        "watermark": {
            "visual_review": {
                "status": visual,
                "reviewer": "unit-test-reviewer",
                "evidence": [asset.relative_to(repo).as_posix()],
                "evidence_sha256": {
                    asset.relative_to(repo).as_posix(): digest(asset),
                },
            },
        },
    }
    if include_origin:
        payload["media_origin"] = dict(origin or ORIGIN)
    if media_type == "video":
        payload["watermark"]["automated_scan"] = {"status": automated, "fps": 3.0}
        payload["human_audio_review"] = {
            "status": human,
            "reviewer_is_human": True,
            "reviewer_type": "HUMAN",
            "reviewer": "unit-test-human",
            "asset_sha256": digest(asset),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
    base = repo / ("outside" if outside else "automation-log/media-qa")
    base.mkdir(parents=True, exist_ok=True)
    path = base / (asset.stem + ".json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def main():
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        (repo / ".system_control").mkdir(parents=True)
        (repo / ".system_control/content_manifest.json").write_text(
            json.dumps({"items": []}), encoding="utf-8")
        (repo / ".system_control/generative_media_policy.json").write_text(
            json.dumps({
                "schema_version": 1,
                "strict_no_watermark": True,
                "google_flow": {
                    "role": "IDEATION_STORYBOARD_ONLY",
                    "final_pixels_allowed": False,
                    "final_audio_allowed": False,
                },
                "final_asset_required_fields": [
                    "generator_origin", "contains_flow_pixels",
                    "contains_flow_audio", "synthid_expected",
                ],
                "allowed_final_origins": [
                    "LOCAL_HTML_CSS_BROWSER_RENDER",
                    "LOCAL_HTML_SVG_FFMPEG_WINDOWS_TTS",
                ],
            }), encoding="utf-8")
        (repo / "automation-log/media-qa").mkdir(parents=True)
        (repo / "automation-log/media-qa/published-media.json").write_text(
            json.dumps({"schema_version": 1, "items": []}), encoding="utf-8")
        image = repo / "media/pins/clean.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"clean-image-fixture")
        image_report = receipt(repo, image, "image")
        assert guard.evaluate(image, image_report, repo=repo)["verdict"] == "PASS"

        manifest_path = repo / ".system_control/content_manifest.json"
        registry_path = repo / "automation-log/media-qa/published-media.json"
        empty_manifest = {"items": []}
        empty_registry = {"schema_version": 1, "items": []}

        def write_corpus(*, manifest=empty_manifest, registry=empty_registry):
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

        def assert_invalid_corpus(*, manifest=empty_manifest, registry=empty_registry):
            write_corpus(manifest=manifest, registry=registry)
            invalid_report = receipt(repo, image, "image")
            invalid = guard.evaluate(image, invalid_report, repo=repo)
            assert invalid["verdict"] == "FAIL" and any(
                item == "publication comparison corpus is missing or unreadable"
                for item in invalid["findings"]
            )

        # A raw-byte fingerprint must never bless a corpus whose logical items
        # cannot be exhaustively compared for permanent novelty.
        assert_invalid_corpus(registry={
            "schema_version": 1,
            "items": {"content_id": "prior", "asset": "media/quotes/prior.jpg"},
        })
        assert_invalid_corpus(manifest={"items": {}})
        assert_invalid_corpus(registry={
            "schema_version": 1,
            "items": [{"content_id": "missing-asset"}],
        })
        assert_invalid_corpus(registry={
            "schema_version": 1,
            "items": [{
                "content_id": "escape",
                "asset": "../outside.jpg",
                "sha256": "0" * 64,
                "status": "published",
            }],
        })
        assert_invalid_corpus(manifest={
            "items": [{"id": "escape-manifest", "reel": "../outside.mp4"}],
        })

        prior_registry_asset = repo / "media/quotes/registry-prior.jpg"
        prior_registry_asset.parent.mkdir(parents=True, exist_ok=True)
        prior_registry_asset.write_bytes(b"registry-prior")
        prior_registry_item = {
            "content_id": "registry-prior",
            "asset": prior_registry_asset.relative_to(repo).as_posix(),
            "sha256": digest(prior_registry_asset),
            "status": "published",
        }
        assert_invalid_corpus(registry={
            "schema_version": 1,
            "items": [prior_registry_item, dict(prior_registry_item)],
        })

        write_corpus(registry={
            "schema_version": 1,
            "items": [prior_registry_item],
        })
        original_link_check = guard._path_is_linklike

        def synthetic_symlink(path):
            return (
                Path(path) == prior_registry_asset
                or original_link_check(path)
            )

        with mock.patch.object(
            guard, "_path_is_linklike", side_effect=synthetic_symlink
        ):
            symlink_report = receipt(repo, image, "image")
            symlink_result = guard.evaluate(
                image, symlink_report, repo=repo
            )
        assert symlink_result["verdict"] == "FAIL" and any(
            "publication comparison corpus is missing or unreadable" == item
            for item in symlink_result["findings"]
        )

        readable_report = receipt(repo, image, "image")
        original_hash = guard._sha256

        def synthetic_unreadable(path):
            if Path(path) == prior_registry_asset:
                raise PermissionError("synthetic unreadable corpus asset")
            return original_hash(path)

        with mock.patch.object(
            guard, "_sha256", side_effect=synthetic_unreadable
        ):
            unreadable_result = guard.evaluate(
                image, readable_report, repo=repo
            )
        assert unreadable_result["verdict"] == "FAIL" and any(
            "publication comparison corpus is missing or unreadable" == item
            for item in unreadable_result["findings"]
        )

        write_corpus()
        restored_report = receipt(repo, image, "image")
        assert guard.publication_corpus_fingerprint(repo) is not None
        assert guard.evaluate(image, restored_report, repo=repo)["verdict"] == "PASS"

        # The claim is a lease across the caller's mutation body, not a check
        # that is released before the remote boundary executes.
        nested_claim_entered = False
        with guard.publication_corpus_claim(
            image,
            restored_report,
            expected_asset_sha256=digest(image),
            expected_content_id=image.stem,
            repo=repo,
        ):
            try:
                with guard.publication_corpus_claim(
                    image,
                    restored_report,
                    expected_asset_sha256=digest(image),
                    expected_content_id=image.stem,
                    repo=repo,
                ):
                    nested_claim_entered = True
            except guard.MediaPublicationBlocked as exc:
                assert "another media publication corpus claim is active" in str(exc)
        assert not nested_claim_entered

        # Deterministically reproduce the original TOCTOU: the corpus advances
        # after evaluate() has retained its records but before it returns.  A
        # stale standalone verdict may exist, but the mutation-boundary claim
        # must re-read under the shared lock and deny entry before remote code.
        race_report = receipt(repo, image, "image")
        original_fingerprint = guard._corpus_fingerprint
        race_calls = {"count": 0}

        def advance_registry_after_snapshot(documents):
            fingerprint = original_fingerprint(documents)
            race_calls["count"] += 1
            if race_calls["count"] == 1:
                registry_path.write_text(json.dumps({
                    "schema_version": 1,
                    "items": [{
                        "content_id": "already-published",
                        "asset": image.relative_to(repo).as_posix(),
                        "sha256": digest(image),
                        "status": "published",
                    }],
                }), encoding="utf-8")
            return fingerprint

        crossed_mutation_boundary = False
        with mock.patch.object(
            guard,
            "_corpus_fingerprint",
            side_effect=advance_registry_after_snapshot,
        ):
            try:
                with guard.publication_corpus_claim(
                    image,
                    race_report,
                    expected_asset_sha256=digest(image),
                    expected_content_id=image.stem,
                    repo=repo,
                ):
                    crossed_mutation_boundary = True
            except guard.MediaPublicationBlocked as exc:
                assert "generation changed at the mutation boundary" in str(exc)
        assert not crossed_mutation_boundary
        assert json.loads(registry_path.read_text(encoding="utf-8"))["items"]
        write_corpus()

        # A valid historical registry row is history even when its identity/path
        # exactly match the candidate; it cannot be mistaken for manifest self.
        published_image_item = {
            "content_id": image.stem,
            "asset": image.relative_to(repo).as_posix(),
            "sha256": digest(image),
            "status": "published",
        }
        write_corpus(registry={
            "schema_version": 1,
            "items": [published_image_item],
        })
        published_duplicate_report = receipt(repo, image, "image")
        published_duplicate = guard.evaluate(
            image, published_duplicate_report, repo=repo
        )
        assert published_duplicate["verdict"] == "FAIL" and any(
            "exact media duplicate" in item
            for item in published_duplicate["findings"]
        )
        write_corpus()

        unknown_origin = receipt(repo, image, "image", include_origin=False)
        unknown = guard.evaluate(image, unknown_origin, repo=repo)
        assert unknown["verdict"] == "FAIL" and any(
            "unknown origin" in item for item in unknown["findings"])

        flow_origin = dict(ORIGIN)
        flow_origin["contains_flow_pixels"] = True
        flow_report = receipt(repo, image, "image", origin=flow_origin)
        flow = guard.evaluate(image, flow_report, repo=repo)
        assert flow["verdict"] == "FAIL" and any(
            "Flow pixels" in item for item in flow["findings"])

        image.write_bytes(b"changed-after-review")
        result = guard.evaluate(image, image_report, repo=repo)
        assert result["verdict"] == "FAIL" and any("SHA-256" in x for x in result["findings"])
        image.write_bytes(b"clean-image-fixture")

        failed_visual = receipt(repo, image, "image", visual="FAIL")
        assert guard.evaluate(image, failed_visual, repo=repo)["verdict"] == "FAIL"

        raw_asset = repo / "media/clips/raw.png"
        raw_asset.parent.mkdir(parents=True)
        raw_asset.write_bytes(b"raw")
        raw_report = receipt(repo, raw_asset, "image")
        assert guard.evaluate(raw_asset, raw_report, repo=repo)["verdict"] == "FAIL"

        video = repo / "reels/clean.mp4"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"video-fixture")
        video_report = receipt(repo, video, "video")
        pass_scan = lambda _path, _fps: {"verdict": "PASS", "frames": 10}
        fail_scan = lambda _path, _fps: {"verdict": "FAIL", "frames": 10}
        assert guard.evaluate(video, video_report, repo=repo, scanner=pass_scan)["verdict"] == "PASS"
        assert guard.evaluate(video, video_report, repo=repo, scanner=fail_scan)["verdict"] == "FAIL"

        review_now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
        boundary_report = receipt(repo, video, "video")
        boundary_payload = json.loads(boundary_report.read_text(encoding="utf-8"))
        boundary = review_now + guard.MAX_REVIEW_FUTURE_SKEW
        boundary_payload["reviewed_at"] = boundary.isoformat()
        boundary_payload["human_audio_review"]["reviewed_at"] = boundary.isoformat()
        boundary_report.write_text(json.dumps(boundary_payload), encoding="utf-8")
        assert guard.evaluate(
            video, boundary_report, repo=repo, scanner=pass_scan, now=review_now
        )["verdict"] == "PASS"

        historical_report = receipt(repo, video, "video")
        historical_payload = json.loads(historical_report.read_text(encoding="utf-8"))
        historical = review_now - timedelta(days=30)
        historical_payload["reviewed_at"] = historical.isoformat()
        historical_payload["human_audio_review"]["reviewed_at"] = historical.isoformat()
        historical_report.write_text(json.dumps(historical_payload), encoding="utf-8")
        assert guard.evaluate(
            video, historical_report, repo=repo, scanner=pass_scan, now=review_now
        )["verdict"] == "PASS"

        future_report = receipt(repo, video, "video")
        future_payload = json.loads(future_report.read_text(encoding="utf-8"))
        future = review_now + guard.MAX_REVIEW_FUTURE_SKEW + timedelta(seconds=1)
        future_payload["reviewed_at"] = future.isoformat()
        future_payload["human_audio_review"]["reviewed_at"] = review_now.isoformat()
        future_report.write_text(json.dumps(future_payload), encoding="utf-8")
        future_result = guard.evaluate(
            video, future_report, repo=repo, scanner=pass_scan, now=review_now
        )
        assert future_result["verdict"] == "FAIL" and any(
            item == "reviewed_at is in the future beyond allowed clock skew"
            for item in future_result["findings"]
        )

        future_human_report = receipt(repo, video, "video")
        future_human_payload = json.loads(
            future_human_report.read_text(encoding="utf-8")
        )
        future_human_payload["reviewed_at"] = review_now.isoformat()
        future_human_payload["human_audio_review"]["reviewed_at"] = future.isoformat()
        future_human_report.write_text(
            json.dumps(future_human_payload), encoding="utf-8"
        )
        future_human_result = guard.evaluate(
            video, future_human_report, repo=repo, scanner=pass_scan, now=review_now
        )
        assert future_human_result["verdict"] == "FAIL" and any(
            item == (
                "human audio reviewed_at is in the future beyond allowed clock skew"
            )
            for item in future_human_result["findings"]
        )

        missing_human = receipt(repo, video, "video", human="NOT_PERFORMED")
        diagnostic_scan_calls = []

        def diagnostic_fail_scan(path, fps):
            diagnostic_scan_calls.append((Path(path), fps))
            return {"verdict": "FAIL", "frames": 10}

        human_result = guard.evaluate(
            video, missing_human, repo=repo, scanner=diagnostic_fail_scan
        )
        assert (
            human_result["verdict"] == "FAIL"
            and diagnostic_scan_calls == [(video.resolve(), 3.0)]
            and any("human audio review" in item for item in human_result["findings"])
            and any(
                "fresh automated watermark scan did not PASS" in item
                for item in human_result["diagnostic_findings"]
            )
        )

        mutation_report = receipt(repo, video, "video")

        def mutating_pass_scan(path, _fps):
            Path(path).write_bytes(b"mutated-during-scan")
            return {"verdict": "PASS", "frames": 10}

        mutated = guard.evaluate(
            video, mutation_report, repo=repo, scanner=mutating_pass_scan
        )
        assert mutated["verdict"] == "FAIL" and any(
            "changed during fresh watermark scan" in item
            for item in mutated["findings"]
        )
        video.write_bytes(b"video-fixture")

        wrong_human_hash = receipt(repo, video, "video")
        wrong_human_payload = json.loads(wrong_human_hash.read_text(encoding="utf-8"))
        wrong_human_payload["human_audio_review"]["asset_sha256"] = "0" * 64
        wrong_human_hash.write_text(json.dumps(wrong_human_payload), encoding="utf-8")
        human_hash_result = guard.evaluate(
            video, wrong_human_hash, repo=repo, scanner=pass_scan
        )
        assert human_hash_result["verdict"] == "FAIL" and any(
            "exact asset SHA-256" in item for item in human_hash_result["findings"])

        wrong_visual_hash = receipt(repo, video, "video")
        wrong_visual_payload = json.loads(wrong_visual_hash.read_text(encoding="utf-8"))
        key = video.relative_to(repo).as_posix()
        wrong_visual_payload["watermark"]["visual_review"]["evidence_sha256"][key] = "0" * 64
        wrong_visual_hash.write_text(json.dumps(wrong_visual_payload), encoding="utf-8")
        visual_hash_result = guard.evaluate(
            video, wrong_visual_hash, repo=repo, scanner=pass_scan
        )
        assert visual_hash_result["verdict"] == "FAIL" and any(
            "visual evidence SHA-256 does not match" in item
            for item in visual_hash_result["findings"]
        )

        wrong_visual_set = receipt(repo, video, "video")
        wrong_set_payload = json.loads(wrong_visual_set.read_text(encoding="utf-8"))
        wrong_set_payload["watermark"]["visual_review"]["evidence_sha256"][
            "reels/not-reviewed.png"
        ] = "0" * 64
        wrong_visual_set.write_text(json.dumps(wrong_set_payload), encoding="utf-8")
        visual_set_result = guard.evaluate(
            video, wrong_visual_set, repo=repo, scanner=pass_scan
        )
        assert visual_set_result["verdict"] == "FAIL" and any(
            "path set does not exactly match" in item
            for item in visual_set_result["findings"]
        )

        missing_auto = receipt(repo, video, "video", automated="FAIL")
        assert guard.evaluate(video, missing_auto, repo=repo, scanner=pass_scan)["verdict"] == "FAIL"

        outside_report = receipt(repo, image, "image", outside=True)
        assert guard.evaluate(image, outside_report, repo=repo)["verdict"] == "FAIL"

        prior = repo / "media/quotes/prior.jpg"
        prior.parent.mkdir(parents=True, exist_ok=True)
        prior.write_bytes(b"same-media-bytes")
        candidate = repo / "media/pins/candidate.jpg"
        candidate.write_bytes(b"same-media-bytes")
        (repo / ".system_control/content_manifest.json").write_text(json.dumps({
            "items": [{"id": "prior-content", "reel": "media/quotes/prior.jpg"}]
        }), encoding="utf-8")
        duplicate_report = receipt(repo, candidate, "image")
        duplicate = guard.evaluate(candidate, duplicate_report, repo=repo)
        assert duplicate["verdict"] == "FAIL" and any(
            "exact media duplicate" in item for item in duplicate["findings"])

        stale_report = receipt(repo, image, "image")
        (repo / ".system_control/content_manifest.json").write_text(
            json.dumps({"items": []}), encoding="utf-8")
        stale = guard.evaluate(image, stale_report, repo=repo)
        assert stale["verdict"] == "FAIL" and any(
            "novelty review is stale" in item for item in stale["findings"])

    print("media publish guard: 34/34 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
