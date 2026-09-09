#!/usr/bin/env python3
"""Fail-closed provenance gate for final social media candidates.

Google Flow remains useful for written ideation and storyboards, but its output
cannot enter final pixels or audio while the page requires no watermark of any
kind.  The gate intentionally does not attempt to detect SynthID; it requires a
source attestation and rejects unknown lineage instead.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / ".system_control" / "generative_media_policy.json"
DEFAULT_PACK = ROOT / "automation-log" / "WEEK-CONTENT-PACK_20260824-30.json"


def _strict_json_loads(value: str) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    document = json.loads(
        value,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for nested in item.values():
                require_finite(nested)
        elif isinstance(item, list):
            for nested in item:
                require_finite(nested)

    require_finite(document)
    return document


def load_json(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"{path}: symlink evidence is not accepted")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if ((before.st_size, before.st_mtime_ns) !=
            (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size):
        raise ValueError(f"{path}: file changed while being read")
    value = _strict_json_loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def iter_assets(pack: dict):
    for day in pack.get("days", []):
        candidate_id = day.get("candidate_id", "UNKNOWN")
        video = day.get("tiktok_draft", {}).get("candidate_asset")
        if isinstance(video, dict):
            yield candidate_id, "video", video
        images = day.get("image_spec", {}).get("candidate_assets", {})
        if isinstance(images, dict):
            for placement, asset in images.items():
                if isinstance(asset, dict):
                    yield candidate_id, f"image:{placement}", asset


def policy_problems(policy: dict) -> list[str]:
    problems: list[str] = []
    flow = policy.get("google_flow", {})
    if policy.get("schema_version") != 1:
        problems.append("policy.schema_version must be 1")
    if policy.get("strict_no_watermark") is not True:
        problems.append("policy.strict_no_watermark must be true")
    if not isinstance(flow, dict):
        problems.append("policy.google_flow must be an object")
        return problems
    if flow.get("role") != "IDEATION_STORYBOARD_ONLY":
        problems.append("policy.google_flow.role must be IDEATION_STORYBOARD_ONLY")
    if flow.get("final_pixels_allowed") is not False or flow.get("final_audio_allowed") is not False:
        problems.append("Google Flow pixels/audio must be forbidden in final assets")
    required = policy.get("final_asset_required_fields")
    if not isinstance(required, list) or not required or any(
        not isinstance(field, str) or not field for field in required
    ):
        problems.append("policy.final_asset_required_fields must be a non-empty string list")
    allowed = policy.get("allowed_final_origins")
    if not isinstance(allowed, list) or not allowed or any(
        not isinstance(origin, str) or not origin for origin in allowed
    ):
        problems.append("policy.allowed_final_origins must be a non-empty string list")
    else:
        forbidden = re.compile(r"(?:GOOGLE|FLOW|VEO|GEMINI|REMOTE|CLOUD)", re.I)
        for origin in allowed:
            if not origin.startswith("LOCAL_") or forbidden.search(origin):
                problems.append(
                    "policy.allowed_final_origins contains a non-local or "
                    f"forbidden origin: {origin}"
                )
    return problems


def origin_problems(policy: dict, origin, *, label="asset") -> list[str]:
    """Validate one final-asset provenance attestation fail closed."""
    if not isinstance(origin, dict):
        return [f"{label}: missing media_origin; unknown origin is BLOCKED"]
    required = policy.get("final_asset_required_fields", [])
    if not isinstance(required, list):
        required = []
    missing = [field for field in required if field not in origin]
    if missing:
        return [f"{label}: missing provenance fields {', '.join(missing)}"]
    problems: list[str] = []
    allowed = set(policy.get("allowed_final_origins", []))
    if origin.get("generator_origin") not in allowed:
        problems.append(
            f"{label}: unapproved generator_origin {origin.get('generator_origin')!r}"
        )
    if origin.get("contains_flow_pixels") is not False:
        problems.append(f"{label}: Flow pixels present or unknown")
    if origin.get("contains_flow_audio") is not False:
        problems.append(f"{label}: Flow audio present or unknown")
    if origin.get("synthid_expected") is not False:
        problems.append(f"{label}: SynthID present or expected/unknown")
    return problems


def check(policy: dict, pack: dict) -> list[str]:
    problems = policy_problems(policy)
    count = 0
    for candidate_id, media_type, asset in iter_assets(pack):
        count += 1
        label = f"{candidate_id}/{media_type}/{asset.get('path', 'UNKNOWN')}"
        problems.extend(origin_problems(policy, asset.get("media_origin"), label=label))
    if count == 0:
        problems.append("weekly pack contains no candidate assets")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    args = parser.parse_args()
    try:
        problems = check(load_json(args.policy), load_json(args.pack))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"GENERATIVE_MEDIA_ORIGIN_GATE: BLOCKED: {exc}")
        return 2
    if problems:
        print("GENERATIVE_MEDIA_ORIGIN_GATE: BLOCKED")
        for problem in problems:
            print(f"- {problem}")
        return 1
    asset_count = sum(1 for _ in iter_assets(load_json(args.pack)))
    print(
        "GENERATIVE_MEDIA_ORIGIN_GATE: PASS "
        f"({asset_count} assets; allow-list declarations accepted; origin not independently verified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
