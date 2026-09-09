#!/usr/bin/env python3
"""Deterministic public release provenance shared by build and live verification."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "release-manifest.json"
PILOT_PATH = Path("release/funnel_pilot.json")
SOURCE_INPUTS = (
    Path("build_site.py"),
    Path("netlify.toml"),
    Path(".system_control/policy.json"),
    Path(".system_control/merchant_offers.json"),
    Path(".system_control/content_manifest.json"),
    Path("tools/comply_gate_stitch.py"),
    Path("tools/merchant_offer_gate.py"),
    Path("tools/postdeploy_smoke.py"),
    Path("tools/release_contract.py"),
    Path("tools/release_funnel_readiness.py"),
    Path("tools/write_release_manifest.py"),
    Path("pipeline/ga4_pull.py"),
    Path("pipeline/ga4_schema.py"),
    PILOT_PATH,
)
CONTRACT_VERSIONS = {
    "release_parity": 2,
    "affiliate_attribution": 1,
    "offer_safety": 1,
    "bounded_pilot": 2,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json_loads(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON constant: " + value)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    parsed = json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def require_finite(item: Any) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    require_finite(parsed)
    return parsed


def _relative_path_without_symlinks(root: Path, relative: Path, label: str) -> Path:
    selected = root
    for part in relative.parts:
        selected = selected / part
        if selected.is_symlink():
            raise ValueError(label + " must not contain a symlink")
    return selected


def _stable_file_bytes(path: Path, label: str) -> bytes:
    """Read one exact regular-file snapshot and reject path/handle replacement."""
    if path.is_symlink():
        raise ValueError(label + " must not be a symlink")
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            raw = handle.read()
            after = os.fstat(handle.fileno())
        current = path.stat()
    except OSError as exc:
        raise ValueError(label + " is unreadable") from exc
    identity_before = (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
    )
    identity_current = (
        current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns,
    )
    if (
        identity_before != identity_after
        or identity_after != identity_current
        or len(raw) != after.st_size
    ):
        raise ValueError(label + " changed while being read")
    return raw


def file_hashes(src: Path | str) -> dict[str, str]:
    requested = Path(src)
    if requested.is_symlink():
        raise ValueError("release artifact root must not be a symlink")
    selected = requested.resolve()
    if not selected.is_dir():
        raise ValueError("release artifact root is missing or not a directory")
    files: dict[str, str] = {}
    for path in sorted(selected.rglob("*")):
        if path.is_symlink():
            raise ValueError("release artifact contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(selected).as_posix()
        if relative == MANIFEST_NAME:
            continue
        files[relative] = sha256_bytes(_stable_file_bytes(path, "release artifact"))
    return files


def tree_hash(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative, value in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def source_hashes(
    repo: Path | str = ROOT, *, captured: dict[Path, bytes] | None = None,
) -> dict[str, str]:
    selected = Path(repo).resolve()
    hashes: dict[str, str] = {}
    for relative in SOURCE_INPUTS:
        path = _relative_path_without_symlinks(
            selected, relative, "required release input"
        )
        if not path.is_file():
            raise ValueError("required release input is missing: " + relative.as_posix())
        raw = (captured or {}).get(relative)
        if raw is None:
            raw = _stable_file_bytes(path, "required release input")
        hashes[relative.as_posix()] = sha256_bytes(raw)
    return hashes


def _parse_pilot(raw: bytes) -> dict[str, Any]:
    try:
        payload = _strict_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("bounded pilot contract is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError("bounded pilot contract must be an object")
    return payload


def load_pilot(repo: Path | str = ROOT) -> dict[str, Any]:
    selected = Path(repo).resolve()
    path = _relative_path_without_symlinks(
        selected, PILOT_PATH, "bounded pilot contract"
    )
    return _parse_pilot(_stable_file_bytes(path, "bounded pilot contract"))


def manifest_for(src: Path | str, repo: Path | str = ROOT) -> dict[str, Any]:
    files = file_hashes(src)
    tree = tree_hash(files)
    selected_repo = Path(repo).resolve()
    pilot_path = _relative_path_without_symlinks(
        selected_repo, PILOT_PATH, "bounded pilot contract"
    )
    pilot_raw = _stable_file_bytes(pilot_path, "bounded pilot contract")
    pilot = _parse_pilot(pilot_raw)
    pilot_id = pilot.get("pilot_id")
    pilot_state = pilot.get("state")
    external = pilot.get("external_action_authorized")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise ValueError("bounded pilot id is missing")
    if pilot_state != "planned_blocked" or external is not False:
        raise ValueError("bounded pilot must remain planned_blocked and non-authorizing")
    return {
        "schema_version": 2,
        "algorithm": "sha256-tree-v1",
        "file_count": len(files),
        "tree_sha256": tree,
        "release_id": "sha256:" + tree,
        "contracts": dict(CONTRACT_VERSIONS),
        "source_sha256": source_hashes(repo, captured={PILOT_PATH: pilot_raw}),
        "pilot": {
            "pilot_id": pilot_id,
            "state": pilot_state,
            "external_action_authorized": False,
            "contract_sha256": sha256_bytes(pilot_raw),
        },
    }


def manifest_findings(
    payload: object, src: Path | str, repo: Path | str = ROOT
) -> list[str]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        return ["release manifest: missing or unsupported schema"]
    try:
        expected = manifest_for(src, repo)
    except (OSError, ValueError) as exc:
        return ["release manifest: local provenance unavailable: " + str(exc)]
    if payload.get("algorithm") != expected["algorithm"]:
        return ["release manifest: malformed hash contract"]
    if (
        payload.get("file_count") != expected["file_count"]
        or payload.get("tree_sha256") != expected["tree_sha256"]
        or payload.get("release_id") != expected["release_id"]
    ):
        return ["release drift: production artifact hashes differ from the audited local build"]
    if payload.get("contracts") != expected["contracts"]:
        return ["release drift: production release-contract versions differ"]
    if payload.get("source_sha256") != expected["source_sha256"]:
        return ["release drift: production source/gate provenance differs"]
    if payload.get("pilot") != expected["pilot"]:
        return ["release drift: production bounded-pilot provenance differs"]
    if set(payload) != set(expected):
        return ["release manifest: unexpected or missing metadata fields"]
    return []
