#!/usr/bin/env python3
"""Fail-closed authority gate for direct publishers and manual Threads text.

Repository data is validation evidence, never proof of owner approval. A live
action additionally needs an exact, private, one-time receipt provisioned outside
the tracked tree at::

    .local-private/runtime/publication-receipts/pending/<nonce>.json

This module deliberately contains no receipt-minting command and does not claim
that an ``actor`` string authenticates a person. Schema v2 binds immutable
SHA-256 values for the policy, role matrix, content calendar, exact content plus
validation bundle, and media-QA evidence. It also enforces the calendar's
Asia/Bangkok execution window. The private receipt must be created through a
separate owner-controlled interaction. On success it is atomically reserved
under ``consumed`` before the caller can touch a browser, OAuth endpoint, upload
API, or other external service. A crash may therefore burn a receipt, but can
never make it reusable.

Threads support is an authority primitive, not a browser publisher. Its caller
must still verify authenticated page identity/live history, reserve an atomic
dedup claim, submit once, and reconcile the public receipt before any retry.
No transport or owner-approval provisioning is provided by this module.

Threads uses a separate fixed private owner-controlled manual calendar, never
the editorial-only planning calendar. Its schema-v3 receipt binds that selected
path and exact bytes. Missing/empty/manual-unapproved input remains blocked;
these primitives never provision a calendar, promote a plan, or publish.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping
from zoneinfo import ZoneInfo

try:
    from tools import content_source_gate, generative_media_origin_gate, media_publish_guard
except ImportError:  # Direct import when ``tools`` itself is on sys.path.
    import content_source_gate
    import generative_media_origin_gate
    import media_publish_guard


PASS_VALUES = {"pass", "approved"}
REQUIRED_VALIDATIONS = (
    "publication",
    "privacy_gate",
    "public_identity",
    "source_gate",
    "dedup",
    "qa",
)
ALLOWED_STATES = {"active", "manual", "testing"}
SOURCE_FRESHNESS_HOURS = 24
RECEIPT_SCHEMA_VERSION = 2
THREADS_RECEIPT_SCHEMA_VERSION = 3
BANGKOK = ZoneInfo("Asia/Bangkok")
IMMEDIATE_LATE_WINDOW = timedelta(minutes=10)
SCHEDULED_MAX_LEAD = timedelta(hours=24)
SCHEDULED_MIN_LEAD = timedelta(minutes=15)
POLICY_PATH = Path(".system_control/policy.json")
ROLE_CAPABILITIES_PATH = Path(".system_control/role_capabilities.json")
CONTENT_CALENDAR_PATH = Path(".system_control/content_calendar.json")
THREADS_MANUAL_CALENDAR_PATH = Path(".local-private/runtime/manual-publication-calendar.json")
MEDIA_QA_ROOT = Path("automation-log/media-qa")
GENERATIVE_MEDIA_POLICY_PATH = Path(".system_control/generative_media_policy.json")
EVIDENCE_HASH_FIELDS = {
    "policy_sha256",
    "role_capabilities_sha256",
    "content_calendar_sha256",
    "content_source_sha256",
    "media_qa_sha256",
}
RECEIPT_FIELDS = {
    "schema_version",
    "content_id",
    "placement_id",
    "channel",
    "target_identity",
    "caption_sha256",
    "asset_sha256",
    "scheduled_slot",
    "expires_at",
    "nonce",
} | EVIDENCE_HASH_FIELDS
NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
THREADS_MANUAL_GATES = {
    "publication_authority": "PASS", "source_review": "NOT_REQUIRED",
    "media": "NOT_REQUIRED", "dedup": "PASS", "page_identity": "PASS",
}


class PublicationBlocked(RuntimeError):
    pass


def _strict_json_loads(value: str | bytes) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    parsed = json.loads(
        value,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def require_finite(item: object) -> None:
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


def _object_evidence(path: Path, label: str) -> tuple[dict, bytes]:
    if path.is_symlink():
        raise PublicationBlocked(f"{label} must not be a symlink")
    try:
        raw = path.read_bytes()
        value = _strict_json_loads(raw.decode("utf-8"))
    except Exception as exc:
        raise PublicationBlocked(f"{label} is missing or unreadable") from exc
    if not isinstance(value, dict):
        raise PublicationBlocked(f"{label} must be a JSON object")
    return value, raw


def _object(path: Path, label: str) -> dict:
    value, _raw = _object_evidence(path, label)
    return value


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_evidence_sha256(value: object) -> str:
    """Hash one exact JSON evidence value with deterministic UTF-8 encoding."""
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except Exception as exc:
        raise PublicationBlocked("publication evidence is not canonical JSON") from exc
    return _bytes_sha256(raw)


def content_source_sha256(content_source_evidence: object, approval: object) -> str:
    """Bind the exact content input and validation object used by the gate."""
    if not isinstance(content_source_evidence, dict) or not content_source_evidence:
        raise PublicationBlocked("exact content source evidence is missing")
    return canonical_evidence_sha256(
        {"content_source": content_source_evidence, "validation": approval}
    )


def _bound_content_source_files(
    repo: Path, content_source_evidence: object
) -> tuple[dict[str, str], list[tuple[Path, bytes]]]:
    """Validate optional canonical source-file hashes and retain exact bytes.

    The private receipt already binds the surrounding content-source object.
    These path/hash bindings additionally let authorization and the immediate
    pre-mutation verifier detect a snapshot or registry replacement on disk.
    """
    if not isinstance(content_source_evidence, dict):
        raise PublicationBlocked("exact content source evidence is missing")
    bindings = content_source_evidence.get("source_file_sha256")
    if bindings is None:
        return {}, []
    if not isinstance(bindings, dict) or not bindings:
        raise PublicationBlocked("content-source file SHA-256 bindings are malformed")
    normalized: dict[str, str] = {}
    evidence: list[tuple[Path, bytes]] = []
    for relative, expected in bindings.items():
        if not isinstance(relative, str) or not relative.strip():
            raise PublicationBlocked("content-source file path binding is malformed")
        relative_path = Path(relative.strip())
        if relative_path.is_absolute() or relative_path.as_posix() != relative.strip():
            raise PublicationBlocked("content-source file path must be canonical and relative")
        candidate = repo / relative_path
        if candidate.is_symlink():
            raise PublicationBlocked("content-source evidence file must not be a symlink")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(repo)
        except ValueError as exc:
            raise PublicationBlocked("content-source evidence file escapes repository") from exc
        expected_hash = _sha256(expected, "content-source file SHA-256")
        try:
            raw = resolved.read_bytes()
        except OSError as exc:
            raise PublicationBlocked("content-source evidence file is missing or unreadable") from exc
        if _bytes_sha256(raw) != expected_hash:
            raise PublicationBlocked("content-source evidence file hash does not match")
        normalized[relative_path.as_posix()] = expected_hash
        evidence.append((resolved, raw))
    return normalized, evidence


def no_media_qa_sha256(content_id: str, placement_id: str) -> str:
    """Bind an explicit text-only decision instead of accepting a missing hash."""
    return canonical_evidence_sha256(
        {
            "asset_sha256": None,
            "content_id": content_id,
            "kind": "NO_MEDIA_REQUIRED",
            "placement_id": placement_id,
        }
    )


def media_qa_evidence_sha256(media_qa_raw: bytes, origin_policy_raw: bytes) -> str:
    """Bind the exact receipt and policy used to accept its origin declaration."""
    return canonical_evidence_sha256({
        "generative_media_policy_sha256": _bytes_sha256(origin_policy_raw),
        "kind": "MEDIA_QA_WITH_ORIGIN_POLICY",
        "media_qa_receipt_sha256": _bytes_sha256(media_qa_raw),
    })


def _approved(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold() in PASS_VALUES


def _checked_at(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PublicationBlocked(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationBlocked(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PublicationBlocked(f"{label} must include a timezone")
    return parsed


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PublicationBlocked(f"{label} is missing")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    normalized = _required_string(value, label).casefold()
    if SHA256_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked(f"{label} must be an exact SHA-256")
    return normalized


def caption_sha256(caption: str) -> str:
    """Hash the exact UTF-8 text that the caller will transmit."""
    if not isinstance(caption, str):
        raise PublicationBlocked("publication caption must be text")
    return hashlib.sha256(caption.encode("utf-8")).hexdigest()


def file_sha256(path: str | os.PathLike[str]) -> str:
    """Hash an exact local publication asset without following a missing path."""
    selected = Path(path)
    if not selected.is_file():
        raise PublicationBlocked(f"publication asset is missing: {selected}")
    digest = hashlib.sha256()
    try:
        with selected.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PublicationBlocked("publication asset is unreadable") from exc
    return digest.hexdigest()


def _repo_evidence_file(
    repo: Path,
    value: object,
    label: str,
    *,
    required_root: Path | None = None,
) -> tuple[Path, bytes, str]:
    relative = _required_string(value, label)
    selected_relative = Path(relative)
    if selected_relative.is_absolute():
        raise PublicationBlocked(f"{label} must be repository-relative")
    unresolved = repo / selected_relative
    if unresolved.is_symlink():
        raise PublicationBlocked(f"{label} must not be a symlink")
    selected = unresolved.resolve()
    try:
        selected.relative_to(repo)
    except ValueError as exc:
        raise PublicationBlocked(f"{label} escapes the repository") from exc
    if required_root is not None:
        root = (repo / required_root).resolve()
        try:
            selected.relative_to(root)
        except ValueError as exc:
            raise PublicationBlocked(f"{label} is outside {required_root.as_posix()}") from exc
    if not selected.is_file():
        raise PublicationBlocked(f"{label} is missing, not regular, or a symlink")
    try:
        raw = selected.read_bytes()
    except OSError as exc:
        raise PublicationBlocked(f"{label} is unreadable") from exc
    return selected, raw, _bytes_sha256(raw)


def _calendar_slot(
    calendar: dict,
    *,
    channel: str,
    content_id: str,
    placement_id: str,
) -> datetime:
    if calendar.get("timezone") != "Asia/Bangkok":
        raise PublicationBlocked("content calendar timezone must be exactly Asia/Bangkok")
    placements = calendar.get("placements")
    if not isinstance(placements, list):
        raise PublicationBlocked("content calendar placements are missing")
    matches = [
        item
        for item in placements
        if isinstance(item, dict) and item.get("placement_id") == placement_id
    ]
    if len(matches) != 1:
        raise PublicationBlocked("content calendar placement must exist exactly once")
    placement = matches[0]
    if placement.get("content_id") != content_id:
        raise PublicationBlocked("content calendar content_id binding does not match")
    if placement.get("publication_authorized") is not True:
        raise PublicationBlocked(
            "content calendar placement publication_authorized is not explicitly true"
        )
    account_id = _required_string(placement.get("account"), "calendar placement account")
    accounts = calendar.get("accounts")
    account = accounts.get(account_id) if isinstance(accounts, dict) else None
    if not isinstance(account, dict):
        raise PublicationBlocked("content calendar placement account is unknown")
    account_channel = str(
        account.get("policy_channel") or account.get("channel") or ""
    ).strip().casefold()
    if account_channel != channel:
        raise PublicationBlocked("content calendar channel binding does not match")
    raw_date = _required_string(placement.get("date"), "calendar placement date")
    raw_time = _required_string(placement.get("time"), "calendar placement time")
    try:
        day = datetime.strptime(raw_date, "%Y-%m-%d").date()
        clock = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError as exc:
        raise PublicationBlocked("content calendar Bangkok slot is invalid") from exc
    return datetime.combine(day, clock, tzinfo=BANGKOK)


def _calendar_relative_path(channel: str) -> Path:
    """Internal fixed-path selection; callers cannot supply calendar paths."""
    return THREADS_MANUAL_CALENDAR_PATH if channel == "threads" else CONTENT_CALENDAR_PATH


def _validate_threads_manual_calendar(calendar: dict) -> None:
    """Strict independent schema for owner-provisioned text-only Threads rows."""
    if (set(calendar) != {"schema_version", "purpose", "timezone", "accounts", "placements"}
            or type(calendar.get("schema_version")) is not int
            or calendar["schema_version"] != 1
            or calendar.get("purpose") != "owner_controlled_manual_publication"
            or calendar.get("timezone") != "Asia/Bangkok"):
        raise PublicationBlocked("Threads manual calendar schema/purpose/timezone is invalid; not an editorial-only plan")
    accounts = calendar.get("accounts")
    if not isinstance(accounts, dict) or set(accounts) != {"threads_main"}:
        raise PublicationBlocked("Threads manual calendar accounts are missing")
    for key, account in accounts.items():
        if (not isinstance(key, str) or not key or key != key.strip()
                or not isinstance(account, dict)
                or account != {"channel": "threads", "policy_channel": "threads"}):
            raise PublicationBlocked("Threads manual calendar cannot mix channels or unknown account fields")
    rows = calendar.get("placements")
    if not isinstance(rows, list) or not rows:
        raise PublicationBlocked("Threads manual calendar placements are missing or empty")
    required = {
        "placement_id", "content_id", "account", "date", "time",
        "publication_authorized", "format", "status", "slot_state",
        "blockers", "gates", "media", "media_receipt",
    }
    seen_ids, seen_content, seen_slots = set(), set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise PublicationBlocked("Threads manual calendar placement fields are not exact")
        placement_id = _required_string(row.get("placement_id"), "manual placement_id")
        content_id = _required_string(row.get("content_id"), "manual content_id")
        account = _required_string(row.get("account"), "manual account")
        identity = (account, content_id)
        if placement_id in seen_ids or identity in seen_content:
            raise PublicationBlocked("Threads manual calendar contains duplicate placement/content identity")
        seen_ids.add(placement_id)
        seen_content.add(identity)
        slot = _calendar_slot(calendar, channel="threads", content_id=content_id, placement_id=placement_id)
        slot_key = (account, slot)
        if slot_key in seen_slots:
            raise PublicationBlocked("Threads manual calendar contains a duplicate account slot")
        seen_slots.add(slot_key)
        if (row.get("status") != "OWNER_APPROVED"
                or row.get("slot_state") != "APPROVED_IMMEDIATE"
                or row.get("blockers") != []):
            raise PublicationBlocked("Threads calendar placement is not owner-approved or retains unresolved blockers")
        if row.get("format") != "text" or row.get("media") is not None or row.get("media_receipt") is not None:
            raise PublicationBlocked("Threads calendar placement must be text-only without media")
        if row.get("gates") != THREADS_MANUAL_GATES:
            raise PublicationBlocked("Threads calendar gates must be exact, with text media NOT_REQUIRED")


def _load_publication_calendar(repo: Path, channel: str) -> tuple[dict, bytes, Path]:
    relative = _calendar_relative_path(channel)
    unresolved = repo / relative
    if channel == "threads":
        cursor = repo
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
                raise PublicationBlocked("Threads manual calendar path must not contain links or junctions")
        try:
            unresolved.resolve().relative_to(repo)
        except ValueError as exc:
            raise PublicationBlocked("Threads manual calendar path escapes repository") from exc
    document, raw = _object_evidence(unresolved, "publication content calendar")
    if channel == "threads":
        _validate_threads_manual_calendar(document)
    return document, raw, unresolved


def _enforce_slot_window(channel: str, slot: datetime, current: datetime) -> str:
    slot_utc = slot.astimezone(timezone.utc)
    current_utc = current.astimezone(timezone.utc)
    if channel == "youtube":
        if current_utc >= slot_utc:
            raise PublicationBlocked("Bangkok scheduled slot has passed")
        lead = slot_utc - current_utc
        if lead <= SCHEDULED_MIN_LEAD:
            raise PublicationBlocked(
                "Bangkok scheduled slot is too close for a safe scheduled upload"
            )
        if lead > SCHEDULED_MAX_LEAD:
            raise PublicationBlocked(
                "Bangkok scheduled slot is too early for this authorization window"
            )
        return "scheduled_24h_to_15m_before"
    if current_utc < slot_utc:
        raise PublicationBlocked("Bangkok immediate-publication slot is early")
    if current_utc > slot_utc + IMMEDIATE_LATE_WINDOW:
        raise PublicationBlocked("Bangkok immediate-publication slot has passed")
    return "immediate_slot_to_plus_10m"


def _media_qa_evidence(
    repo: Path,
    *,
    content_id: str,
    placement_id: str,
    asset_sha256: str | None,
    media_qa_path: object,
) -> tuple[str, tuple[tuple[Path, bytes], ...] | None, str | None]:
    if asset_sha256 is None:
        if media_qa_path not in (None, ""):
            raise PublicationBlocked("text-only publication must not claim media QA evidence")
        return no_media_qa_sha256(content_id, placement_id), None, None
    path, raw, digest = _repo_evidence_file(
        repo,
        media_qa_path,
        "media QA evidence path",
        required_root=MEDIA_QA_ROOT,
    )
    try:
        payload = _strict_json_loads(raw.decode("utf-8"))
    except Exception as exc:
        raise PublicationBlocked("media QA evidence is not readable JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PublicationBlocked("media QA evidence schema_version is unsupported")
    if str(payload.get("sha256") or "").strip().casefold() != asset_sha256:
        raise PublicationBlocked("media QA evidence asset SHA-256 does not match")
    novelty = payload.get("novelty_review")
    if not isinstance(novelty, dict) or novelty.get("content_id") != content_id:
        raise PublicationBlocked("media QA evidence content_id does not match")
    if novelty.get("status") != "PASS":
        raise PublicationBlocked("media QA evidence novelty review is not PASS")
    watermark = payload.get("watermark")
    visual = watermark.get("visual_review") if isinstance(watermark, dict) else None
    if not isinstance(visual, dict) or visual.get("status") != "PASS":
        raise PublicationBlocked("media QA evidence visual watermark review is not PASS")

    origin_policy_path = (repo / GENERATIVE_MEDIA_POLICY_PATH).resolve()
    origin_policy, origin_policy_raw = _object_evidence(
        origin_policy_path, "generative media policy"
    )
    policy_findings = generative_media_origin_gate.policy_problems(origin_policy)
    if policy_findings:
        raise PublicationBlocked(
            "generative media policy is invalid: " + "; ".join(policy_findings)
        )
    origin_findings = generative_media_origin_gate.origin_problems(
        origin_policy, payload.get("media_origin"), label="media QA declared origin"
    )
    if origin_findings:
        raise PublicationBlocked("; ".join(origin_findings))
    asset_relative = payload.get("asset")
    if not isinstance(asset_relative, str) or not asset_relative.strip():
        raise PublicationBlocked("media QA evidence asset path is missing")
    asset_path = (repo / asset_relative).resolve()
    final_review_findings = media_publish_guard.final_review_findings(
        asset_path,
        payload,
        repo=repo,
        actual_hash=asset_sha256,
        media_type=payload.get("media_type"),
        origin_policy=origin_policy,
    )
    if final_review_findings:
        raise PublicationBlocked(
            "media QA final review is blocked: " + "; ".join(final_review_findings)
        )
    combined_digest = media_qa_evidence_sha256(raw, origin_policy_raw)
    return (
        combined_digest,
        ((path, raw), (origin_policy_path, origin_policy_raw)),
        path.relative_to(repo).as_posix(),
    )


def _assert_file_evidence_unchanged(evidence: tuple[Path, bytes], label: str) -> None:
    path, expected = evidence
    try:
        if path.is_symlink() or path.read_bytes() != expected:
            raise PublicationBlocked(f"{label} changed during authorization")
    except PublicationBlocked:
        raise
    except OSError as exc:
        raise PublicationBlocked(f"{label} disappeared during authorization") from exc


def canonical_text_payload(parts: Mapping[str, str]) -> str:
    """Serialize every transmitted text part for one unambiguous caption hash.

    Facebook publishes a body and then a first comment. Binding only the body
    would leave the comment replayable, so that caller hashes this canonical JSON
    payload. Single-caption publishers hash their caption directly.
    """
    if not isinstance(parts, Mapping) or not parts:
        raise PublicationBlocked("publication text parts are missing")
    normalized: dict[str, str] = {}
    for key, value in parts.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            raise PublicationBlocked("publication text parts must be named text values")
        normalized[key] = value
    return json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _run_local_guard(repo: Path, relative: str) -> int:
    result = subprocess.run(
        [sys.executable, str(repo / relative)],
        cwd=str(repo),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return int(result.returncode)


def _normalize_target(channel: str, value: object, label: str) -> str:
    target = _required_string(value, label)
    if channel == "threads":
        # Accept one bare handle or one @handle, never a URL/display name.
        if re.fullmatch(r"@?[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*", target) is None:
            raise PublicationBlocked(f"{label} must be a single Threads account handle")
        return target.removeprefix("@").casefold()
    if channel == "tiktok":
        return target.casefold().lstrip("@")
    return target


def _threads_text_evidence(
    repo: Path,
    calendar: dict,
    *,
    policy: dict,
    content_id: str,
    placement_id: str,
    caption: str,
    asset_sha256: str | None,
    media_qa_path: object,
    content_source_evidence: object,
    bound_source_hashes: dict[str, str],
    now: datetime,
) -> None:
    """Require an explicitly text-only placement and the exact bound text file.

    The regular calendar/owner/source gates remain required. In particular this
    does not classify a draft as source-neutral or turn a blocked slot into READY.
    """
    if asset_sha256 is not None or media_qa_path is not None:
        raise PublicationBlocked("Threads authority supports text-only publication")
    if not isinstance(caption, str) or not caption.strip():
        raise PublicationBlocked("Threads publication caption must be non-empty text")
    if calendar.get("purpose") != "owner_controlled_manual_publication":
        raise PublicationBlocked("Threads requires an owner-controlled manual calendar, not an editorial-only plan")
    placements = calendar.get("placements")
    matches = [
        row for row in placements if isinstance(row, dict)
        and row.get("placement_id") == placement_id
    ] if isinstance(placements, list) else []
    if len(matches) != 1:
        raise PublicationBlocked("Threads text placement must exist exactly once")
    placement = matches[0]
    if (placement.get("status") != "OWNER_APPROVED"
            or placement.get("slot_state") != "APPROVED_IMMEDIATE"
            or placement.get("blockers") != []):
        raise PublicationBlocked("Threads calendar placement is not owner-approved or retains unresolved blockers")
    if placement.get("format") != "text" or any(
        placement.get(field) is not None
        for field in ("media", "media_receipt", "media_content_id", "media_qa_report")
    ):
        raise PublicationBlocked("Threads calendar placement must be text-only without media")
    if placement.get("gates") != THREADS_MANUAL_GATES:
        raise PublicationBlocked(
            "Threads calendar gates must exactly authorize publication, source-neutral "
            "text, identity and dedup with media NOT_REQUIRED"
        )
    if not isinstance(content_source_evidence, dict):
        raise PublicationBlocked("Threads exact text-file evidence is missing")
    relative = _required_string(
        content_source_evidence.get("publication_text_file"),
        "Threads publication_text_file",
    )
    if relative not in bound_source_hashes:
        raise PublicationBlocked("Threads publication text file must have a bound SHA-256")
    _path, raw, digest = _repo_evidence_file(repo, relative, "Threads publication text file")
    if digest != bound_source_hashes[relative] or raw != caption.encode("utf-8"):
        raise PublicationBlocked("Threads publication text file does not match the exact caption")
    _threads_source_neutral_review(
        repo, policy=policy, content_id=content_id, caption=caption,
        content_source_evidence=content_source_evidence,
        bound_source_hashes=bound_source_hashes, now=now,
    )


def _threads_source_neutral_review(
    repo: Path, *, policy: dict, content_id: str, caption: str,
    content_source_evidence: dict, bound_source_hashes: dict[str, str],
    now: datetime,
) -> None:
    """Validate exact review evidence, never mint or substitute owner authority.

    This narrow manual lane cannot reclassify a factual registry namespace. The
    reviewed caption and source decision are bound by the separate private owner
    receipt. A clean risk scan alone is not review proof or publication approval.
    """
    if content_source_gate.repo_content_source_contract(content_id, repo)[0] is not None:
        raise PublicationBlocked("Threads source-neutral lane cannot override a factual source namespace")
    if "official_source_snapshot" in content_source_evidence:
        raise PublicationBlocked("Threads source-neutral lane cannot carry official-source claims")
    relative = _required_string(
        content_source_evidence.get("source_neutral_review_file"),
        "Threads source_neutral_review_file",
    )
    if relative not in bound_source_hashes:
        raise PublicationBlocked("Threads source-neutral review must have a bound SHA-256")
    _path, raw, digest = _repo_evidence_file(repo, relative, "Threads source-neutral review")
    if digest != bound_source_hashes[relative]:
        raise PublicationBlocked("Threads source-neutral review file hash does not match")
    try:
        review = _strict_json_loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PublicationBlocked("Threads source-neutral review is malformed") from exc
    if not isinstance(review, dict) or set(review) != {
        "schema_version", "content_id", "caption_sha256", "decision",
        "source_ids", "checked_at", "expires_at",
    }:
        raise PublicationBlocked("Threads source-neutral review fields are not exact")
    if (type(review.get("schema_version")) is not int or review["schema_version"] != 1
            or review.get("content_id") != content_id
            or review.get("decision") != "SOURCE_NEUTRAL_EXACT_TEXT"
            or review.get("source_ids") != []
            or _sha256(review.get("caption_sha256"), "source-neutral review caption hash")
            != caption_sha256(caption)):
        raise PublicationBlocked("Threads source-neutral review caption/content/decision binding is invalid")
    checked = _checked_at(review.get("checked_at"), "source-neutral review checked_at")
    expires = _checked_at(review.get("expires_at"), "source-neutral review expires_at")
    if not checked <= now < expires or not timedelta(0) < expires - checked <= timedelta(hours=24):
        raise PublicationBlocked("Threads source-neutral review is stale, future, or exceeds 24 hours")
    try:
        from tools.editorial_draft_gate import check_source_neutral_text
    except ImportError:
        try:
            from editorial_draft_gate import check_source_neutral_text
        except ImportError as exc:
            raise PublicationBlocked("Threads source-neutral text validator is unavailable") from exc
    result = check_source_neutral_text(caption, policy=policy)
    if not isinstance(result, dict) or result.get("allowed") is not True:
        raise PublicationBlocked("Threads source-neutral text validation is blocked")


def _receipt_paths(repo: Path, nonce: object) -> tuple[str, Path, Path]:
    normalized = _required_string(nonce, "private publication receipt nonce")
    if NONCE_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked(
            "private publication receipt nonce must be 32-128 URL-safe characters"
        )
    root = (repo / ".local-private" / "runtime" / "publication-receipts").resolve()
    pending_root = (root / "pending").resolve()
    consumed_root = (root / "consumed").resolve()
    pending = (pending_root / f"{normalized}.json").resolve()
    consumed = (consumed_root / f"{normalized}.json").resolve()
    if pending.parent != pending_root or consumed.parent != consumed_root:
        raise PublicationBlocked("private publication receipt path escaped its private root")
    return normalized, pending, consumed


def _load_private_receipt(repo: Path, nonce: object) -> tuple[dict, bytes, Path, Path]:
    normalized, pending, consumed = _receipt_paths(repo, nonce)
    if consumed.exists():
        raise PublicationBlocked(
            f"private publication receipt {normalized!r} was already consumed (replay blocked)"
        )
    if not pending.is_file() or pending.is_symlink():
        relative = (
            Path(".local-private/runtime/publication-receipts/pending")
            / f"{normalized}.json"
        )
        raise PublicationBlocked(
            "private one-time publication receipt is required at "
            f"{relative}; actor labels and repository approval JSON are not authorization"
        )
    try:
        raw = pending.read_bytes()
        value = _strict_json_loads(raw.decode("utf-8"))
    except Exception as exc:
        raise PublicationBlocked("private publication receipt is unreadable") from exc
    if not isinstance(value, dict):
        raise PublicationBlocked("private publication receipt must be a JSON object")
    expected_fields = _receipt_fields(value.get("schema_version"))
    if set(value) != expected_fields:
        missing = sorted(expected_fields - set(value))
        extra = sorted(set(value) - expected_fields)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise PublicationBlocked(
            "private publication receipt fields are not exact (" + "; ".join(detail) + ")"
        )
    return value, raw, pending, consumed


def _receipt_fields(version: object) -> set[str]:
    return RECEIPT_FIELDS | ({"content_calendar_path"} if version == THREADS_RECEIPT_SCHEMA_VERSION else set())


def _load_consumed_receipt(repo: Path, nonce: object) -> tuple[dict, datetime]:
    """Load the durable receipt and its exact consumption chronology."""
    normalized, _pending, consumed = _receipt_paths(repo, nonce)
    if not consumed.is_file() or consumed.is_symlink():
        raise PublicationBlocked("consumed publication receipt is missing or unreadable")
    try:
        record = _strict_json_loads(consumed.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PublicationBlocked("consumed publication receipt is unreadable") from exc
    if (
        not isinstance(record, dict)
        or set(record) != {"schema_version", "consumed_at", "receipt"}
        or type(record.get("schema_version")) is not int
        or record.get("schema_version") not in {RECEIPT_SCHEMA_VERSION, THREADS_RECEIPT_SCHEMA_VERSION}
        or not isinstance(record.get("receipt"), dict)
        or record["receipt"].get("schema_version") != record.get("schema_version")
        or set(record["receipt"]) != _receipt_fields(record.get("schema_version"))
        or record["receipt"].get("nonce") != normalized
    ):
        raise PublicationBlocked("consumed publication receipt contract is invalid")
    consumed_at = _checked_at(
        record.get("consumed_at"), "consumed publication receipt consumed_at"
    )
    return record["receipt"], consumed_at


def _consume_private_receipt(
    *, receipt: dict, raw: bytes, pending: Path, consumed: Path, current: datetime
) -> None:
    """Reserve a nonce exactly once using exclusive file creation.

    ``O_EXCL`` is the atomic winner election. The pending file is removed only
    after the durable consumed record exists. If cleanup fails, the operation is
    denied while the consumed marker still prevents retry/replay.
    """
    try:
        if pending.read_bytes() != raw:
            raise PublicationBlocked("private publication receipt changed during validation")
    except PublicationBlocked:
        raise
    except OSError as exc:
        raise PublicationBlocked("private publication receipt disappeared during validation") from exc

    consumed.parent.mkdir(parents=True, exist_ok=True)
    record = json.dumps(
        {
            "schema_version": receipt["schema_version"],
            "consumed_at": current.isoformat(),
            "receipt": receipt,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(consumed, flags, 0o600)
    except FileExistsError as exc:
        raise PublicationBlocked("private publication receipt replay was blocked atomically") from exc
    except OSError as exc:
        raise PublicationBlocked("private publication receipt cannot be consumed atomically") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(record)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        try:
            consumed.unlink(missing_ok=True)
        except OSError:
            pass
        raise PublicationBlocked("private publication receipt consumption was not durable") from exc
    try:
        pending.unlink()
    except OSError as exc:
        raise PublicationBlocked(
            "private publication receipt was reserved but pending cleanup failed; action denied"
        ) from exc


def authorize_live_publication(
    *,
    repo: Path,
    channel: str,
    actor: str | None,
    target_identity: str | None,
    approval: object,
    content_id: object,
    placement_id: object,
    caption: str,
    asset_sha256: str | None,
    content_source_evidence: object,
    media_qa_path: object,
    scheduled_slot: object,
    receipt_nonce: object,
    now: datetime | None = None,
    guard_runner=None,
) -> dict:
    """Consume an exact private receipt or raise ``PublicationBlocked``.

    ``actor`` is only a role/capability label. It is intentionally insufficient
    for action authorization, even when its value is ``"owner"``.
    """
    repo = Path(repo).resolve()
    normalized_channel = _required_string(channel, "publication channel").casefold()
    if normalized_channel not in {"facebook", "instagram", "tiktok", "youtube", "threads"}:
        raise PublicationBlocked("direct publication channel is unsupported")
    normalized_actor = _required_string(actor, "live publication actor label")

    policy_path = repo / POLICY_PATH
    role_path = repo / ROLE_CAPABILITIES_PATH
    policy, policy_raw = _object_evidence(policy_path, "policy")
    roles, role_raw = _object_evidence(role_path, "role capabilities")
    calendar, calendar_raw, calendar_path = _load_publication_calendar(repo, normalized_channel)
    if roles.get("default") != "deny":
        raise PublicationBlocked("role capabilities must explicitly set default to deny")

    channels = policy.get("channels")
    channel_policy = (
        channels.get(normalized_channel) if isinstance(channels, dict) else None
    )
    if not isinstance(channel_policy, dict):
        raise PublicationBlocked(f"policy is missing channels.{normalized_channel}")
    state = str(channel_policy.get("state", "")).strip().casefold()
    if state not in ALLOWED_STATES:
        raise PublicationBlocked(
            f"channels.{normalized_channel}.state is not live-eligible"
        )
    if channel_policy.get("publication_authorized") is not True:
        raise PublicationBlocked(
            f"channels.{normalized_channel}.publication_authorized is not explicitly true"
        )

    actors = roles.get("actors")
    capabilities = (
        actors.get(normalized_actor) if isinstance(actors, dict) else None
    )
    if not isinstance(capabilities, dict) or capabilities.get("social_publish") is not True:
        raise PublicationBlocked(
            f"actor label {normalized_actor!r} has no social_publish capability"
        )

    target_fields = {
        "facebook": ("page_id",),
        "instagram": ("account_id", "ig_user_id"),
        "tiktok": ("account_handle",),
        "threads": ("account_handle",),
        "youtube": ("channel_id",),
    }
    expected_target = ""
    for field in target_fields.get(normalized_channel, ("publication_target",)):
        value = channel_policy.get(field)
        if isinstance(value, str) and value.strip():
            expected_target = value
            break
    if not expected_target:
        raise PublicationBlocked(
            f"channels.{normalized_channel} has no configured publication target"
        )
    expected_target = _normalize_target(
        normalized_channel, expected_target, "policy publication target"
    )
    actual_target = _normalize_target(
        normalized_channel, target_identity, "live publication target identity"
    )
    if actual_target != expected_target:
        raise PublicationBlocked("live publication target does not match policy")

    normalized_content_id = _required_string(content_id, "publication content_id")
    normalized_placement_id = _required_string(
        placement_id, "publication placement_id"
    )
    requested_slot = _checked_at(scheduled_slot, "publication scheduled_slot")
    requested_caption_hash = caption_sha256(caption)
    requested_asset_hash = (
        None if asset_sha256 is None else _sha256(asset_sha256, "publication asset_sha256")
    )
    if normalized_channel in {"instagram", "tiktok", "youtube"} and requested_asset_hash is None:
        raise PublicationBlocked(f"{normalized_channel} publication requires an asset SHA-256")

    calendar_slot = _calendar_slot(
        calendar,
        channel=normalized_channel,
        content_id=normalized_content_id,
        placement_id=normalized_placement_id,
    )
    if calendar_slot.astimezone(timezone.utc) != requested_slot.astimezone(timezone.utc):
        raise PublicationBlocked("publication scheduled slot does not match content calendar")

    current = now or datetime.now(timezone.utc)
    if (
        not isinstance(current, datetime)
        or current.tzinfo is None
        or current.utcoffset() is None
    ):
        raise PublicationBlocked("authorization time must include a timezone")
    slot_window = _enforce_slot_window(normalized_channel, calendar_slot, current)

    source_file_hashes, source_file_evidence = _bound_content_source_files(
        repo, content_source_evidence
    )
    if normalized_channel == "threads":
        _threads_text_evidence(
            repo, calendar, policy=policy, content_id=normalized_content_id,
            placement_id=normalized_placement_id,
            caption=caption, asset_sha256=requested_asset_hash,
            media_qa_path=media_qa_path,
            content_source_evidence=content_source_evidence,
            bound_source_hashes=source_file_hashes,
            now=current,
        )
    content_hash = content_source_sha256(content_source_evidence, approval)
    try:
        source_authorization_bundle = _strict_json_loads(
            json.dumps(
                {"evidence": content_source_evidence, "approval": approval},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    except Exception as exc:
        raise PublicationBlocked("content-source authorization bundle is not serializable") from exc
    media_hash, media_file_evidence, normalized_media_qa_path = _media_qa_evidence(
        repo,
        content_id=normalized_content_id,
        placement_id=normalized_placement_id,
        asset_sha256=requested_asset_hash,
        media_qa_path=media_qa_path,
    )
    evidence_hashes = {
        "policy_sha256": _bytes_sha256(policy_raw),
        "role_capabilities_sha256": _bytes_sha256(role_raw),
        "content_calendar_sha256": _bytes_sha256(calendar_raw),
        "content_source_sha256": content_hash,
        "media_qa_sha256": media_hash,
    }

    # Repo-editable evidence can satisfy validation conditions, but the private
    # receipt must independently bind its exact hashes. Actor='owner' plus an
    # approval object therefore remains insufficient.
    receipt, raw_receipt, pending_path, consumed_path = _load_private_receipt(
        repo, receipt_nonce
    )

    expected_version = THREADS_RECEIPT_SCHEMA_VERSION if normalized_channel == "threads" else RECEIPT_SCHEMA_VERSION
    if type(receipt.get("schema_version")) is not int or receipt.get("schema_version") != expected_version:
        raise PublicationBlocked("private publication receipt schema_version is unsupported")
    if normalized_channel == "threads" and receipt.get("content_calendar_path") != THREADS_MANUAL_CALENDAR_PATH.as_posix():
        raise PublicationBlocked("private publication receipt selected calendar path does not match")
    if receipt.get("nonce") != _required_string(receipt_nonce, "receipt nonce"):
        raise PublicationBlocked("private publication receipt nonce binding does not match")
    if receipt.get("content_id") != normalized_content_id:
        raise PublicationBlocked("private publication receipt content_id binding does not match")
    if receipt.get("placement_id") != normalized_placement_id:
        raise PublicationBlocked("private publication receipt placement_id binding does not match")
    receipt_channel = _required_string(
        receipt.get("channel"), "receipt.channel"
    ).casefold()
    if receipt_channel != normalized_channel:
        raise PublicationBlocked("private publication receipt channel binding does not match")
    receipt_target = _normalize_target(
        normalized_channel, receipt.get("target_identity"), "receipt.target_identity"
    )
    if receipt_target != actual_target:
        raise PublicationBlocked("private publication receipt target binding does not match")
    if _sha256(receipt.get("caption_sha256"), "receipt.caption_sha256") != requested_caption_hash:
        raise PublicationBlocked("private publication receipt caption binding does not match")
    receipt_asset = receipt.get("asset_sha256")
    if requested_asset_hash is None:
        if receipt_asset is not None:
            raise PublicationBlocked("text-only receipt.asset_sha256 must be null")
    elif _sha256(receipt_asset, "receipt.asset_sha256") != requested_asset_hash:
        raise PublicationBlocked("private publication receipt asset binding does not match")
    receipt_slot = _checked_at(receipt.get("scheduled_slot"), "receipt.scheduled_slot")
    if receipt_slot.astimezone(timezone.utc) != requested_slot.astimezone(timezone.utc):
        raise PublicationBlocked("private publication receipt scheduled slot does not match")
    for field, expected_hash in evidence_hashes.items():
        if _sha256(receipt.get(field), f"receipt.{field}") != expected_hash:
            raise PublicationBlocked(
                f"private publication receipt {field} evidence binding does not match"
            )
    expires_at = _checked_at(receipt.get("expires_at"), "receipt.expires_at")
    if expires_at.astimezone(timezone.utc) <= current.astimezone(timezone.utc):
        raise PublicationBlocked("private publication receipt is expired")

    # Repo-editable validation evidence remains a necessary gate, but it is never
    # identity or action authorization and cannot substitute for the receipt.
    if not isinstance(approval, dict):
        raise PublicationBlocked("structured per-item validation evidence is missing")
    for field in REQUIRED_VALIDATIONS:
        if not _approved(approval.get(field)):
            raise PublicationBlocked(f"per-item validation.{field} is not approved")
    checked_at = _checked_at(approval.get("approved_at"), "validation.approved_at")
    source_checked_at = _checked_at(
        approval.get("source_checked_at"), "validation.source_checked_at"
    )
    if checked_at.astimezone(timezone.utc) > current.astimezone(timezone.utc):
        raise PublicationBlocked("validation.approved_at is in the future")
    source_age = (
        current.astimezone(timezone.utc) - source_checked_at.astimezone(timezone.utc)
    ).total_seconds() / 3600
    if source_age < 0 or source_age > SOURCE_FRESHNESS_HOURS:
        raise PublicationBlocked("validation.source_checked_at is stale or in the future")

    runner = guard_runner or (lambda rel: _run_local_guard(repo, rel))
    for relative, label in (
        ("tools/privacy_guard.py", "privacy"),
        ("tools/public_identity_guard.py", "public identity"),
    ):
        try:
            result = int(runner(relative))
        except Exception as exc:
            raise PublicationBlocked(f"{label} guard is unavailable") from exc
        if result != 0:
            raise PublicationBlocked(f"{label} guard is blocked (exit {result})")

    # Close TOCTOU gaps: the receipt authorizes the exact bytes/objects evaluated
    # above, not later replacements with the same path or caller reference.
    for evidence, label in (
        ((policy_path, policy_raw), "policy evidence"),
        ((role_path, role_raw), "role-capability evidence"),
        ((calendar_path, calendar_raw), "content-calendar evidence"),
    ):
        _assert_file_evidence_unchanged(evidence, label)
    if normalized_channel == "threads":
        _fresh_calendar, fresh_raw, fresh_path = _load_publication_calendar(repo, normalized_channel)
        if fresh_path != calendar_path or fresh_raw != calendar_raw:
            raise PublicationBlocked("selected manual calendar changed during authorization")
    if media_file_evidence is not None:
        for position, evidence in enumerate(media_file_evidence):
            label = (
                "media-QA evidence" if position == 0
                else "generative-media policy evidence"
            )
            _assert_file_evidence_unchanged(evidence, label)
    for source_file in source_file_evidence:
        _assert_file_evidence_unchanged(source_file, "content-source file evidence")
    if content_source_sha256(content_source_evidence, approval) != content_hash:
        raise PublicationBlocked("content-source evidence changed during authorization")

    _consume_private_receipt(
        receipt=receipt,
        raw=raw_receipt,
        pending=pending_path,
        consumed=consumed_path,
        current=current,
    )
    return {
        **({"content_calendar_path": THREADS_MANUAL_CALENDAR_PATH.as_posix()} if normalized_channel == "threads" else {}),
        "content_id": normalized_content_id,
        "placement_id": normalized_placement_id,
        "channel": normalized_channel,
        "actor": normalized_actor,
        "target_identity": actual_target,
        "caption_sha256": requested_caption_hash,
        "asset_sha256": requested_asset_hash,
        "scheduled_slot": calendar_slot.isoformat(),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "slot_window": slot_window,
        "media_qa_path": normalized_media_qa_path,
        "evidence_sha256": evidence_hashes,
        "content_source_file_sha256": source_file_hashes,
        "content_source_authorization": source_authorization_bundle,
        "nonce": receipt["nonce"],
        "consumed": True,
    }


def verify_execution_authorization(
    *,
    repo: Path,
    action: object,
    caption: str,
    asset_sha256: str | None,
    media_qa_path: object,
    now: datetime | None = None,
) -> dict:
    """Re-check mutable evidence and the Bangkok window at mutation time.

    The one-time receipt has already been consumed by
    :func:`authorize_live_publication`; this verifier never creates, moves, or
    consumes a receipt. It exists because OAuth, hosted-file checks, and browser
    preparation can outlive the authorization window or race policy evidence.
    """
    if not isinstance(action, dict) or action.get("consumed") is not True:
        raise PublicationBlocked("execution has no consumed publication action")
    current = now or datetime.now(timezone.utc)
    if (
        not isinstance(current, datetime)
        or current.tzinfo is None
        or current.utcoffset() is None
    ):
        raise PublicationBlocked("execution time must include a timezone")
    current_utc = current.astimezone(timezone.utc)
    repo = Path(repo).resolve()
    channel = _required_string(action.get("channel"), "execution channel").casefold()
    if channel not in {"facebook", "instagram", "tiktok", "youtube", "threads"}:
        raise PublicationBlocked("execution channel is unsupported")
    actor = _required_string(action.get("actor"), "execution actor")
    content_id = _required_string(action.get("content_id"), "execution content_id")
    placement_id = _required_string(
        action.get("placement_id"), "execution placement_id"
    )
    target = _normalize_target(
        channel, action.get("target_identity"), "execution target identity"
    )
    if caption_sha256(caption) != _sha256(
        action.get("caption_sha256"), "execution caption_sha256"
    ):
        raise PublicationBlocked("publication caption changed after authorization")
    requested_asset_hash = (
        None if asset_sha256 is None else _sha256(asset_sha256, "execution asset_sha256")
    )
    action_asset = action.get("asset_sha256")
    if requested_asset_hash is None:
        if action_asset is not None:
            raise PublicationBlocked("publication asset changed after authorization")
    elif _sha256(action_asset, "authorized asset_sha256") != requested_asset_hash:
        raise PublicationBlocked("publication asset changed after authorization")

    evidence = action.get("evidence_sha256")
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_HASH_FIELDS:
        raise PublicationBlocked("execution evidence hash contract is missing or not exact")
    normalized_evidence = {
        field: _sha256(evidence.get(field), f"execution evidence.{field}")
        for field in EVIDENCE_HASH_FIELDS
    }
    action_expires_at = _checked_at(
        action.get("expires_at"), "execution expires_at"
    )
    consumed_receipt, consumed_at = _load_consumed_receipt(
        repo, action.get("nonce")
    )
    expected_version = THREADS_RECEIPT_SCHEMA_VERSION if channel == "threads" else RECEIPT_SCHEMA_VERSION
    if consumed_receipt.get("schema_version") != expected_version:
        raise PublicationBlocked("execution receipt schema does not match the selected channel")
    if channel == "threads" and (
        action.get("content_calendar_path") != THREADS_MANUAL_CALENDAR_PATH.as_posix()
        or consumed_receipt.get("content_calendar_path") != THREADS_MANUAL_CALENDAR_PATH.as_posix()
    ):
        raise PublicationBlocked("execution selected calendar path no longer matches the fixed receipt binding")
    receipt_expires_at = _checked_at(
        consumed_receipt.get("expires_at"), "consumed receipt expires_at"
    )
    if (
        action_expires_at.astimezone(timezone.utc)
        != receipt_expires_at.astimezone(timezone.utc)
    ):
        raise PublicationBlocked(
            "execution expires_at no longer matches consumed receipt"
        )
    consumed_utc = consumed_at.astimezone(timezone.utc)
    expires_utc = receipt_expires_at.astimezone(timezone.utc)
    if consumed_utc > current_utc:
        raise PublicationBlocked(
            "consumed publication receipt chronology is in the future"
        )
    if expires_utc <= consumed_utc:
        raise PublicationBlocked(
            "consumed publication receipt expiry does not follow consumption"
        )
    if current_utc >= expires_utc:
        raise PublicationBlocked("consumed publication receipt is expired")
    if consumed_receipt.get("content_id") != content_id:
        raise PublicationBlocked("execution content_id no longer matches consumed receipt")
    if consumed_receipt.get("placement_id") != placement_id:
        raise PublicationBlocked("execution placement_id no longer matches consumed receipt")
    if _required_string(consumed_receipt.get("channel"), "consumed receipt channel").casefold() != channel:
        raise PublicationBlocked("execution channel no longer matches consumed receipt")
    if _normalize_target(
        channel, consumed_receipt.get("target_identity"), "consumed receipt target"
    ) != target:
        raise PublicationBlocked("execution target no longer matches consumed receipt")
    if _sha256(
        consumed_receipt.get("caption_sha256"), "consumed receipt caption_sha256"
    ) != _sha256(action.get("caption_sha256"), "authorized caption_sha256"):
        raise PublicationBlocked("execution caption binding no longer matches consumed receipt")
    receipt_asset = consumed_receipt.get("asset_sha256")
    if requested_asset_hash is None:
        if receipt_asset is not None:
            raise PublicationBlocked("execution asset no longer matches consumed receipt")
    elif _sha256(receipt_asset, "consumed receipt asset_sha256") != requested_asset_hash:
        raise PublicationBlocked("execution asset no longer matches consumed receipt")
    receipt_slot = _checked_at(
        consumed_receipt.get("scheduled_slot"), "consumed receipt scheduled_slot"
    )
    action_slot = _checked_at(action.get("scheduled_slot"), "execution scheduled_slot")
    if receipt_slot.astimezone(timezone.utc) != action_slot.astimezone(timezone.utc):
        raise PublicationBlocked("execution slot no longer matches consumed receipt")
    for field, expected_hash in normalized_evidence.items():
        if _sha256(consumed_receipt.get(field), f"consumed receipt {field}") != expected_hash:
            raise PublicationBlocked(f"execution {field} no longer matches consumed receipt")

    source_authorization = action.get("content_source_authorization")
    if (
        not isinstance(source_authorization, dict)
        or set(source_authorization) != {"evidence", "approval"}
    ):
        raise PublicationBlocked("execution content-source authorization bundle is missing")
    if content_source_sha256(
        source_authorization.get("evidence"), source_authorization.get("approval")
    ) != normalized_evidence["content_source_sha256"]:
        raise PublicationBlocked("execution content-source bundle no longer matches consumed receipt")

    policy, policy_raw = _object_evidence(repo / POLICY_PATH, "execution policy")
    roles, role_raw = _object_evidence(
        repo / ROLE_CAPABILITIES_PATH, "execution role capabilities"
    )
    calendar, calendar_raw, _calendar_path = _load_publication_calendar(repo, channel)
    current_hashes = {
        "policy_sha256": _bytes_sha256(policy_raw),
        "role_capabilities_sha256": _bytes_sha256(role_raw),
        "content_calendar_sha256": _bytes_sha256(calendar_raw),
    }
    for field, current_hash in current_hashes.items():
        if normalized_evidence[field] != current_hash:
            raise PublicationBlocked(f"{field} drifted after receipt consumption")

    if roles.get("default") != "deny":
        raise PublicationBlocked("execution role capabilities no longer default deny")
    actors = roles.get("actors")
    capabilities = actors.get(actor) if isinstance(actors, dict) else None
    if not isinstance(capabilities, dict) or capabilities.get("social_publish") is not True:
        raise PublicationBlocked("execution actor no longer has social_publish capability")
    channels = policy.get("channels")
    channel_policy = channels.get(channel) if isinstance(channels, dict) else None
    if not isinstance(channel_policy, dict):
        raise PublicationBlocked("execution policy channel is missing")
    if channel_policy.get("publication_authorized") is not True:
        raise PublicationBlocked("execution policy no longer authorizes publication")
    target_fields = {
        "facebook": ("page_id",),
        "instagram": ("account_id", "ig_user_id"),
        "tiktok": ("account_handle",),
        "threads": ("account_handle",),
        "youtube": ("channel_id",),
    }
    expected_target = ""
    for field in target_fields[channel]:
        value = channel_policy.get(field)
        if isinstance(value, str) and value.strip():
            expected_target = _normalize_target(channel, value, "execution policy target")
            break
    if not expected_target or target != expected_target:
        raise PublicationBlocked("execution target drifted from policy")

    calendar_slot = _calendar_slot(
        calendar,
        channel=channel,
        content_id=content_id,
        placement_id=placement_id,
    )
    authorized_slot = _checked_at(action.get("scheduled_slot"), "execution scheduled_slot")
    if calendar_slot.astimezone(timezone.utc) != authorized_slot.astimezone(timezone.utc):
        raise PublicationBlocked("execution calendar slot drifted after authorization")
    execution_source_checked_at = _checked_at(
        source_authorization["approval"].get("source_checked_at")
        if isinstance(source_authorization.get("approval"), dict)
        else None,
        "execution validation.source_checked_at",
    )
    execution_source_age = (
        current.astimezone(timezone.utc)
        - execution_source_checked_at.astimezone(timezone.utc)
    ).total_seconds() / 3600
    if execution_source_age < 0 or execution_source_age > SOURCE_FRESHNESS_HOURS:
        raise PublicationBlocked(
            "execution validation.source_checked_at is stale or in the future"
        )
    slot_window = _enforce_slot_window(channel, calendar_slot, current)

    media_hash, _media_file, normalized_media_path = _media_qa_evidence(
        repo,
        content_id=content_id,
        placement_id=placement_id,
        asset_sha256=requested_asset_hash,
        media_qa_path=media_qa_path,
    )
    if normalized_evidence["media_qa_sha256"] != media_hash:
        raise PublicationBlocked("media_qa_sha256 drifted after receipt consumption")
    if action.get("media_qa_path") != normalized_media_path:
        raise PublicationBlocked("media-QA path changed after authorization")
    action_source_files = action.get("content_source_file_sha256")
    if not isinstance(action_source_files, dict) or not action_source_files:
        raise PublicationBlocked("execution content-source file bindings are missing")
    bundled_source_files, _source_evidence = _bound_content_source_files(
        repo, source_authorization["evidence"]
    )
    if bundled_source_files != action_source_files:
        raise PublicationBlocked(
            "content-source file bindings no longer match consumed authorization"
        )
    if channel == "threads":
        _threads_text_evidence(
            repo, calendar, policy=policy, content_id=content_id,
            placement_id=placement_id, caption=caption,
            asset_sha256=requested_asset_hash, media_qa_path=media_qa_path,
            content_source_evidence=source_authorization["evidence"],
            bound_source_hashes=bundled_source_files,
            now=current,
        )
    exact_source_evidence = source_authorization["evidence"]
    if "official_source_snapshot" in exact_source_evidence:
        canonical_snapshot = (
            repo / "automation-log/knowledge-base/official-news-snapshot.json"
        ).resolve()
        canonical_registry, library = content_source_gate.repo_content_source_contract(
            content_id, repo
        )
        if canonical_registry is None:
            raise PublicationBlocked(
                "execution content has no canonical content-source registry"
            )
        canonical_registry = canonical_registry.resolve()
        expected_paths = {
            canonical_snapshot.relative_to(repo).as_posix(),
            canonical_registry.relative_to(repo).as_posix(),
        }
        if set(action_source_files) != expected_paths:
            raise PublicationBlocked(
                "execution source-file bindings are not the exact canonical pair"
            )
        try:
            snapshot_document = _strict_json_loads(
                canonical_snapshot.read_text(encoding="utf-8")
            )
            registry_raw = canonical_registry.read_bytes()
            registry_document = _strict_json_loads(registry_raw.decode("utf-8"))
        except Exception as exc:
            raise PublicationBlocked(
                "execution canonical source evidence is unreadable"
            ) from exc
        if snapshot_document != exact_source_evidence.get("official_source_snapshot"):
            raise PublicationBlocked(
                "execution canonical snapshot no longer matches consumed authorization"
            )
        registry_hash = _bytes_sha256(registry_raw)
        if registry_hash != exact_source_evidence.get("source_registry_sha256"):
            raise PublicationBlocked(
                "execution canonical registry no longer matches consumed authorization"
            )
        declared_source_ids = exact_source_evidence.get("source_ids")
        if (
            not isinstance(declared_source_ids, list)
            or not declared_source_ids
            or any(not isinstance(item, str) or not item.strip()
                   for item in declared_source_ids)
            or len(declared_source_ids) != len(set(declared_source_ids))
        ):
            raise PublicationBlocked("execution canonical source IDs are malformed")
        canonical_decision = content_source_gate.evaluate_content_source_gate(
            content_id,
            canonical_registry,
            canonical_snapshot,
            library_name=library,
            now=current.astimezone(timezone.utc),
            _registry_document=registry_document,
            _snapshot_document=snapshot_document,
        )
        if set(declared_source_ids) != set(canonical_decision.source_ids):
            raise PublicationBlocked(
                "execution canonical source IDs no longer match the registry"
            )
        if canonical_decision.allowed is not True:
            detail = "; ".join(str(value) for value in canonical_decision.failures[:3])
            raise PublicationBlocked(
                "execution canonical content-source gate is blocked"
                + ((": " + detail) if detail else "")
            )
    if channel == "threads":
        _latest_calendar, latest_raw, latest_path = _load_publication_calendar(repo, channel)
        if latest_path != _calendar_path or latest_raw != calendar_raw:
            raise PublicationBlocked("selected manual calendar changed during execution verification")
        for source_file in _source_evidence:
            _assert_file_evidence_unchanged(source_file, "execution content-source file evidence")
    return {"slot_window": slot_window, "verified": True}
