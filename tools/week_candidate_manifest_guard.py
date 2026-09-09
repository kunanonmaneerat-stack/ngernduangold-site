#!/usr/bin/env python3
"""Fail-closed binding guard for the 24-30 August r5 media manifest.

The manifest is a compact release-fence index, not publication authority.  It
must bind the frozen draft pack, QA summary, exact asset bytes, exact receipt
bytes, and the same media-origin attestation carried by each pack asset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from tools import generative_media_origin_gate, media_publish_guard
except ImportError:  # Direct ``py tools/week_candidate_manifest_guard.py``.
    import generative_media_origin_gate
    import media_publish_guard


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT / "automation-log" / "media-qa"
    / "WEEK-TIKTOK-QUOTE-CANDIDATES_MANIFEST_R5_20260823.json"
)
EXPECTED_STATUS = "TECHNICAL_QA_PASS_HUMAN_LISTENING_NOT_RUN_DRAFT_ONLY"
EXPECTED_FENCES = {
    "DRAFT_ONLY",
    "HUMAN_LISTENING_NOT_RUN",
    "PUBLICATION_AUTHORITY_FALSE",
    "EXACT_OWNER_APPROVAL_MISSING",
    "CALENDAR_AND_DEDUP_BLOCKERS_RETAINED",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _repo_path(root: Path, raw) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("repository-relative path is missing")
    relative = Path(raw.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe repository path: {raw}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path leaves repository: {raw}") from exc
    return path


def _pack_assets(pack: dict) -> dict[str, dict]:
    assets = {}
    for day in pack.get("days", []):
        if not isinstance(day, dict):
            continue
        video = day.get("tiktok_draft", {}).get("candidate_asset")
        candidates = [video] if isinstance(video, dict) else []
        images = day.get("image_spec", {}).get("candidate_assets", {})
        if isinstance(images, dict):
            candidates.extend(asset for asset in images.values() if isinstance(asset, dict))
        for asset in candidates:
            path = asset.get("path")
            if isinstance(path, str) and path:
                if path in assets:
                    raise ValueError(f"duplicate pack asset path: {path}")
                assets[path] = asset
    return assets


def evaluate_document(
    manifest: dict,
    *,
    root: Path = ROOT,
    manifest_path: Path | None = None,
) -> dict:
    root = Path(root).resolve()
    findings = []
    publication_blockers = []
    media_results = []
    checked = 0
    if manifest.get("schema_version") != 1:
        findings.append("manifest schema_version must be 1")
    if manifest.get("status") != EXPECTED_STATUS:
        findings.append("manifest status is not the frozen draft-only QA state")
    if set(manifest.get("release_fences") or []) != EXPECTED_FENCES:
        findings.append("manifest release fences are incomplete or changed")

    pack_binding = manifest.get("pack") if isinstance(manifest.get("pack"), dict) else {}
    try:
        pack_path = _repo_path(root, pack_binding.get("path"))
        pack = _load(pack_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        findings.append(f"pack is missing or unreadable: {exc}")
        pack = {}
        pack_path = None
    if pack:
        if pack_binding.get("id") != pack.get("pack_id"):
            findings.append("manifest pack id differs from the frozen pack")
        if pack_path and str(pack_binding.get("sha256") or "").upper() != _sha256(pack_path):
            findings.append("manifest pack SHA-256 is stale")
        findings.extend(generative_media_origin_gate.check(
            _load(root / ".system_control/generative_media_policy.json"), pack
        ))

    qa = manifest.get("qa_summary") if isinstance(manifest.get("qa_summary"), dict) else {}
    try:
        qa_path = _repo_path(root, qa.get("path"))
        if not qa_path.is_file() or str(qa.get("sha256") or "").upper() != _sha256(qa_path):
            findings.append("QA summary SHA-256 is stale or missing")
    except (OSError, ValueError) as exc:
        findings.append(f"QA summary binding is invalid: {exc}")

    try:
        expected_assets = _pack_assets(pack)
    except ValueError as exc:
        findings.append(str(exc))
        expected_assets = {}
    rows = manifest.get("assets")
    if not isinstance(rows, list):
        rows = []
        findings.append("manifest assets must be a list")
    row_paths = [row.get("asset") for row in rows if isinstance(row, dict)]
    if len(row_paths) != len(set(row_paths)):
        findings.append("manifest asset paths are duplicated")
    if set(row_paths) != set(expected_assets):
        findings.append("manifest asset coverage differs from the frozen pack")

    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            findings.append(f"manifest asset row {index} is malformed")
            continue
        raw_asset = row.get("asset")
        expected = expected_assets.get(raw_asset)
        if expected is None:
            continue
        checked += 1
        try:
            asset = _repo_path(root, raw_asset)
            receipt = _repo_path(root, row.get("receipt"))
            if not asset.is_file() or row.get("sha256") != _sha256(asset):
                findings.append(f"asset hash is stale: {raw_asset}")
            if row.get("sha256") != expected.get("sha256"):
                findings.append(f"manifest asset hash differs from pack: {raw_asset}")
            if row.get("receipt") != expected.get("qa_receipt"):
                findings.append(f"manifest receipt path differs from pack: {raw_asset}")
            if not receipt.is_file() or row.get("receipt_sha256") != _sha256(receipt):
                findings.append(f"receipt hash is stale: {row.get('receipt')}")
            receipt_payload = _load(receipt)
            if receipt_payload.get("asset") != raw_asset:
                findings.append(f"receipt asset binding differs: {raw_asset}")
            if receipt_payload.get("sha256") != expected.get("sha256"):
                findings.append(f"receipt asset hash differs from pack: {raw_asset}")
            if receipt_payload.get("media_origin") != expected.get("media_origin"):
                findings.append(f"receipt media origin differs from pack: {raw_asset}")
            guard_result = media_publish_guard.evaluate(asset, receipt, repo=root)
            guard_findings = list(guard_result.get("findings") or [])
            human_only = bool(guard_findings) and all(
                str(item).startswith("human audio") for item in guard_findings
            )
            media_results.append({
                "asset": raw_asset,
                "media_type": guard_result.get("media_type"),
                "guard_verdict": guard_result.get("verdict"),
                "state": (
                    "BLOCKED_HUMAN_AUDIO_REVIEW"
                    if human_only else
                    "PASS" if guard_result.get("verdict") == "PASS" else
                    "FAIL"
                ),
                "findings": guard_findings,
                "origin_attestation": guard_result.get("origin_attestation"),
            })
            if human_only:
                publication_blockers.extend(
                    f"{raw_asset}: {item}" for item in guard_findings
                )
            elif guard_result.get("verdict") != "PASS":
                findings.extend(
                    f"media guard {raw_asset}: {item}" for item in guard_findings
                )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            findings.append(f"asset binding {raw_asset!r} is unreadable: {exc}")

    technical_state = "PASS" if not findings else "FAIL"
    final_media_state = (
        "FAIL" if findings else "BLOCKED" if publication_blockers else "PASS"
    )
    verdict = "FAIL" if findings else "BLOCKED" if publication_blockers else "PASS"
    selected_manifest = Path(manifest_path or MANIFEST)
    if not selected_manifest.is_absolute():
        selected_manifest = (root / selected_manifest).resolve()
    return {
        "verdict": verdict,
        "manifest": str(selected_manifest),
        "manifest_integrity_state": "PASS" if not findings else "FAIL",
        "technical_qa_state": technical_state,
        "final_media_guard_state": final_media_state,
        "publishable": False,
        "expected_assets": len(expected_assets),
        "checked_assets": checked,
        "findings": findings,
        "publication_blockers": publication_blockers,
        "media_guard_results": media_results,
        "origin_attestation_state": "DECLARED_ALLOWLIST_ONLY_NOT_PROVEN",
        "publication_authority_granted": False,
    }


def evaluate(path: Path = MANIFEST, *, root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    selected = Path(path)
    if not selected.is_absolute():
        selected = (root / selected).resolve()
    try:
        return evaluate_document(
            _load(selected), root=root, manifest_path=selected
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "verdict": "FAIL", "manifest": str(selected),
            "manifest_integrity_state": "FAIL",
            "technical_qa_state": "FAIL",
            "final_media_guard_state": "FAIL",
            "publishable": False,
            "expected_assets": 0, "checked_assets": 0,
            "findings": [f"manifest is missing or unreadable: {exc}"],
            "publication_blockers": [],
            "media_guard_results": [],
            "origin_attestation_state": "BLOCKED_OR_UNKNOWN",
            "publication_authority_granted": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.manifest)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "WEEK_CANDIDATE_MANIFEST_GUARD: %s (%d/%d assets; technical=%s; final=%s)"
            % (
                result["verdict"], result["checked_assets"], result["expected_assets"],
                result["technical_qa_state"], result["final_media_guard_state"],
            )
        )
        for finding in result["findings"]:
            print("- " + finding)
        for blocker in result["publication_blockers"]:
            print("- " + blocker)
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
