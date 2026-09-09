#!/usr/bin/env python3
"""Fail-closed reader for hash-bound historical canonical-collision tombstones."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re


ZERO_SHA256 = "0" * 64
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
TOP_KEYS = {"schema_version", "created_at", "purpose", "tombstones", "self_sha256"}
ITEM_KEYS = {
    "tombstone_id", "channel", "identity_type", "identity", "reuse_policy",
    "external_delivery_resolution", "occurrences",
}
OCCURRENCE_KEYS = {"line", "row_sha256", "ledger_status", "ledger_date"}


class CollisionTombstoneError(ValueError):
    pass


def _strict_json_loads(value: str):
    def reject_constant(token: str):
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicate_keys(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    document = json.loads(
        value,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    require_finite(document)
    return document


def _canonical_json(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def payload_sha256(payload: dict) -> str:
    value = dict(payload)
    value.pop("self_sha256", None)
    return hashlib.sha256(_canonical_json(value)).hexdigest().upper()


def _require_sha(value, label: str) -> str:
    text = str(value or "")
    if not SHA256_RE.fullmatch(text):
        raise CollisionTombstoneError(f"{label} must be uppercase SHA-256")
    return text


def _stable_bytes(path: Path) -> bytes:
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise CollisionTombstoneError(f"cannot read {path}: {exc}") from exc
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise CollisionTombstoneError(f"file changed while reading: {path}")
    return raw


def _norm_channel(value) -> str:
    aliases = {"youtube": "yt", "instagram": "ig", "facebook": "fb", "tt": "tiktok"}
    channel = str(value or "").strip().casefold()
    return aliases.get(channel, channel)


def _row_date(row: dict) -> str:
    for field in ("scheduled_for", "published_at", "posted_at", "ts"):
        value = str(row.get(field) or "")
        if len(value) >= 10:
            try:
                import datetime
                return datetime.date.fromisoformat(value[:10]).isoformat()
            except ValueError:
                pass
    raise CollisionTombstoneError("tombstoned row has no valid ledger date")


def load_collision_tombstones(
    *, ledger_path, rows: list[dict], row_sha256: dict[int, str], bindings=None,
    collision_groups=None, tombstone_path=None,
) -> tuple[set[tuple[str, str]], dict]:
    ledger = Path(ledger_path).resolve()
    path = (
        Path(tombstone_path).resolve() if tombstone_path
        else ledger.with_name("post-ledger-collision-tombstones.json")
    )
    report = {
        "state": "NOT_PRESENT", "path": str(path), "tombstone_count": 0,
        "non_reusable_identities": [], "bound_occurrence_sets": [], "errors": [],
    }
    if not path.exists():
        return set(), report
    try:
        raw = _stable_bytes(path)
        try:
            payload = _strict_json_loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise CollisionTombstoneError("collision tombstone is not valid UTF-8 JSON") from exc
        if not isinstance(payload, dict) or set(payload) != TOP_KEYS:
            raise CollisionTombstoneError("collision tombstone top-level keys are not exact")
        if payload["schema_version"] != 1:
            raise CollisionTombstoneError("collision tombstone schema_version must be 1")
        stored = _require_sha(payload["self_sha256"], "collision tombstone self_sha256")
        if stored != payload_sha256(payload):
            raise CollisionTombstoneError("collision tombstone payload hash mismatch")
        if not isinstance(payload["created_at"], str) or not payload["created_at"]:
            raise CollisionTombstoneError("collision tombstone created_at is missing")
        if not isinstance(payload["purpose"], str) or not payload["purpose"]:
            raise CollisionTombstoneError("collision tombstone purpose is missing")
        items = payload["tombstones"]
        if not isinstance(items, list) or not items:
            raise CollisionTombstoneError("collision tombstones must be non-empty")
        if not isinstance(collision_groups, list):
            raise CollisionTombstoneError(
                "current collision groups are required to prove complete occurrence binding"
            )
        current_occurrences = {}
        for group in collision_groups:
            if not isinstance(group, dict):
                raise CollisionTombstoneError("current collision group is invalid")
            group_key = (
                str(group.get("identity_type") or ""),
                _norm_channel(group.get("channel")),
                str(group.get("identity") or ""),
            )
            group_rows = group.get("occurrences")
            if not all(group_key) or not isinstance(group_rows, list):
                raise CollisionTombstoneError("current collision group identity is incomplete")
            try:
                group_lines = tuple(sorted(int(row["line"]) for row in group_rows))
            except (KeyError, TypeError, ValueError) as exc:
                raise CollisionTombstoneError(
                    "current collision group occurrence lines are invalid"
                ) from exc
            if len(group_lines) < 2 or len(group_lines) != len(set(group_lines)):
                raise CollisionTombstoneError(
                    "current collision group occurrence set is invalid"
                )
            if group_key in current_occurrences:
                raise CollisionTombstoneError("duplicate current collision group identity")
            current_occurrences[group_key] = group_lines
        bindings = bindings or {}
        tombstone_ids = set()
        identities = set()
        bound_occurrence_sets = []
        for number, item in enumerate(items, 1):
            if not isinstance(item, dict) or set(item) != ITEM_KEYS:
                raise CollisionTombstoneError(f"tombstone {number} keys are not exact")
            tombstone_id = str(item["tombstone_id"] or "")
            if not re.fullmatch(r"collision-v1-[a-z0-9-]+", tombstone_id):
                raise CollisionTombstoneError("collision tombstone_id is invalid")
            if tombstone_id in tombstone_ids:
                raise CollisionTombstoneError("duplicate collision tombstone_id")
            tombstone_ids.add(tombstone_id)
            identity_type = str(item["identity_type"] or "")
            if identity_type not in {"clip", "text_hash"}:
                raise CollisionTombstoneError(
                    "only canonical clip or exact text-hash collisions are supported"
                )
            if item["reuse_policy"] != "HISTORICAL_CANONICAL_COLLISION_NON_REUSABLE":
                raise CollisionTombstoneError("collision reuse policy is invalid")
            if item["external_delivery_resolution"] != "UNKNOWN_NO_INFERENCE":
                raise CollisionTombstoneError("external delivery resolution must remain unknown")
            channel = _norm_channel(item["channel"])
            canonical = str(item["identity"] or "")
            key = (identity_type, channel, canonical)
            if not channel or not canonical or key in identities:
                raise CollisionTombstoneError("collision identity is empty or duplicated")
            occurrences = item["occurrences"]
            if not isinstance(occurrences, list) or len(occurrences) < 2:
                raise CollisionTombstoneError("collision tombstone needs at least two occurrences")
            lines = []
            for occurrence in occurrences:
                if not isinstance(occurrence, dict) or set(occurrence) != OCCURRENCE_KEYS:
                    raise CollisionTombstoneError("collision occurrence keys are not exact")
                line = occurrence["line"]
                if not isinstance(line, int) or isinstance(line, bool) or not 1 <= line <= len(rows):
                    raise CollisionTombstoneError("collision occurrence line is invalid")
                if line in lines:
                    raise CollisionTombstoneError("collision occurrence line is duplicated")
                lines.append(line)
                if _require_sha(occurrence["row_sha256"], "collision row_sha256") != row_sha256.get(line):
                    raise CollisionTombstoneError("collision occurrence row hash mismatch")
                row = rows[line - 1]
                native_field = "clip_key" if identity_type == "clip" else "text_hash"
                row_identity = str(
                    row.get(native_field)
                    or (bindings.get(line) or {}).get("value")
                    or ""
                )
                if _norm_channel(row.get("channel")) != channel or row_identity != canonical:
                    raise CollisionTombstoneError("collision occurrence canonical identity mismatch")
                if str(row.get("status") or "") != occurrence["ledger_status"]:
                    raise CollisionTombstoneError("collision occurrence ledger status mismatch")
                if _row_date(row) != occurrence["ledger_date"]:
                    raise CollisionTombstoneError("collision occurrence ledger date mismatch")
            if lines != sorted(lines):
                raise CollisionTombstoneError("collision occurrence lines must be sorted")
            group_key = (identity_type, channel, canonical)
            current_lines = current_occurrences.get(group_key)
            if current_lines is None:
                raise CollisionTombstoneError(
                    "collision tombstone does not bind a current duplicate identity group"
                )
            if tuple(lines) != current_lines:
                raise CollisionTombstoneError(
                    "collision tombstone occurrence set mismatch: expected current lines %s, got %s"
                    % (list(current_lines), lines)
                )
            bound_occurrence_sets.append({
                "channel": channel,
                "identity_type": identity_type,
                "identity": canonical,
                "lines": lines,
            })
            identities.add(key)
        report.update({
            "state": "PASS", "tombstone_count": len(items),
            "non_reusable_identities": [
                {
                    "identity_type": identity_type,
                    "channel": channel,
                    "identity": identity,
                }
                for identity_type, channel, identity in sorted(identities)
            ],
            "bound_occurrence_sets": bound_occurrence_sets,
        })
        return identities, report
    except (CollisionTombstoneError, OSError, TypeError, ValueError) as exc:
        report.update({"state": "INVALID", "errors": [str(exc)]})
        return set(), report
