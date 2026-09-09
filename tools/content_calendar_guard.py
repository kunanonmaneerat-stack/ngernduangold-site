#!/usr/bin/env python3
"""Fail-closed validator for the local editorial content calendar.

The calendar is deliberately not a publisher.  PASS means the plan is complete,
future-only, internally consistent, and blocked at every external-mutation
boundary.  COMPLETED_BLOCKED means historical PLANNED_BLOCKED rows were observed
and reported without being promoted or backfilled.  Neither verdict authorizes
publication; structural or safety drift is always FAIL.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_LOG = ROOT / "automation-log"
if str(AUTOMATION_LOG) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_LOG))

import content_compliance_gate
import content_source_gate
import media_publish_guard
import post_ledger


CALENDAR_PATH = Path(".system_control/content_calendar.json")
POLICY_PATH = Path(".system_control/policy.json")
LEDGER_PATH = Path("automation-log/post-ledger.jsonl")
TIMEZONE_NAME = "Asia/Bangkok"
BANGKOK = ZoneInfo(TIMEZONE_NAME)
BLOCKED_STATUS = "PLANNED_BLOCKED"
BLOCKED_SLOT = "BLOCKED"
RESERVED_SLOT = "RESERVED_BLOCKED"
REPORT_ONLY = "REPORT_ONLY"
PUBLICATION_BLOCKER = "PUBLICATION_BLOCKER"
VERDICT_PASS = "PASS"
VERDICT_COMPLETED_BLOCKED = "COMPLETED_BLOCKED"
VERDICT_FAIL = "FAIL"
PROCESS_PASS = "PASS"
PROCESS_COMPLETED_BLOCKED = "COMPLETED_BLOCKED"
PROCESS_BLOCKED = "BLOCKED"
PROCESS_RUNNER_FAILED = "RUNNER_FAILED"
EXIT_CODES = {
    PROCESS_PASS: 0,
    PROCESS_COMPLETED_BLOCKED: 1,
    PROCESS_BLOCKED: 2,
    PROCESS_RUNNER_FAILED: 3,
}


class _FailClosedArgumentParser(argparse.ArgumentParser):
    """Raise so malformed invocation uses the runner-failure exit contract."""

    def error(self, message):
        raise ValueError(message)
SUCCESS_TYPES = {
    "text", "comment", "story", "broadcast-scheduled",
    "video", "image", "post", "now", "schedule", "manual",
}
# Only publication-shaped ledger rows consume the anti-blast quota.  Comments,
# replies, stories and operational events have separate policies and must not
# silently consume (or evade) the post cap.
RATE_LIMIT_LEDGER_TYPES = {"text", "video", "image", "post", "now", "schedule", "manual"}
NON_SUCCESS_STATUSES = {
    "aborted", "cancelled", "canceled", "failed", "failure", "rejected", "skipped",
}
SUCCESS_STATUSES = {
    "completed", "confirmed", "delivered_confirmed", "live", "posted", "published",
    "published_confirmed", "scheduled", "success", "succeeded",
}
EXPECTED_PAGE2_NAME = "สินเชื่อธนาคารถูกกฎหมาย"
HELD_IDS = {"qt-12", "qt-13", "qt-14", "b4-p01"}
QUOTE_PACK_CAPTION_FIELDS = {
    "qt-12__facebook_main": "facebook_text",
    "qt-12__instagram_main": "threads_text",
    "qt-12__pinterest_main": "threads_text",
    "qt-13__facebook_main": "facebook_text",
    "qt-13__instagram_main": "threads_text",
    "qt-13__pinterest_main": "threads_text",
}
QUOTE_PACK_ADAPTATIONS = {
    "facebook_main": "platform_native_image_exact_pack_caption",
    "instagram_main": "platform_native_image_exact_pack_caption",
    "pinterest_main": "two_by_three_pin_exact_pack_caption_profile_link_only",
}
TIKTOK_ACCOUNT = "tiktok_main"
TIKTOK_STATE = "testing_blocked"
TIKTOK_PLAN_FILENAME = "TIKTOK-REACTIVATION-PLAN_20260817-30.md"
WEEKLY_REPLACEMENT_PACK = "WEEK-CONTENT-PACK_20260824-30.json"
TIKTOK_LINK_POLICY = "NO_LINK_UNTIL_LIVE_LANDING_PARITY"
TIKTOK_REQUIRED_BLOCKERS = {
    "publication_authority",
    "channel_review",
    "per_piece_owner_confirmation",
    "official_source_review",
    "live_tiktok_history_dedup",
    "live_landing_parity",
    "bio_route_parity",
}
TIKTOK_WEEK_REPLACEMENT_MAP = {
    "tt-r14-08": "wk36-sf01",
    "tt-r14-09": "wk36-sf02",
    "tt-r14-10": "qt-12",
    "tt-r14-11": "wk36-sf03",
    "tt-r14-12": "wk36-sf04",
    "tt-r14-13": "qt-13",
    "tt-r14-14": "wk36-sf05",
}
TIKTOK_WEEK_REPLACEMENT_IDS = set(TIKTOK_WEEK_REPLACEMENT_MAP.values())
TIKTOK_WEEK_SOURCE_FIELD = "threads_text"
TIKTOK_WEEK_ADAPTATION = "tiktok_exact_week_pack_video_no_link"
HUMAN_LISTENING_BLOCKER = "human_listening_not_run"
NEXT_WINDOW_HOURS = 48
ROLLING_RUNWAY_DAYS = 7


def _finding(code: str, message: str, placement_id: str | None = None) -> dict:
    value = {"code": code, "message": message}
    if placement_id:
        value["placement_id"] = placement_id
    return value


def _report_finding(code: str, message: str, placement_id: str | None = None) -> dict:
    """Return a visible lifecycle finding that does not invalidate the plan."""
    value = _finding(code, message, placement_id)
    value["classification"] = REPORT_ONLY
    return value


def _publication_finding(
    code: str, message: str, placement_id: str | None = None
) -> dict:
    """Return a validly-detected business blocker, not a runner/shape failure."""
    value = _finding(code, message, placement_id)
    value["classification"] = PUBLICATION_BLOCKER
    return value


def _closed_result(process_state: str, findings: list[dict], counts: dict | None = None) -> dict:
    """Build a result that never implies publication authority."""
    safe_counts = dict(counts or {})
    safe_counts["publishable"] = 0
    if process_state == PROCESS_PASS:
        verdict = VERDICT_PASS
    elif process_state == PROCESS_COMPLETED_BLOCKED:
        verdict = VERDICT_COMPLETED_BLOCKED
    else:
        verdict = VERDICT_FAIL
    return {
        "verdict": verdict,
        "process_state": process_state,
        "findings": findings,
        "counts": safe_counts,
    }


def _strict_json_loads(raw: str) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key: " + key)
            value[key] = item
        return value

    value = json.loads(
        raw,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
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

    require_finite(value)
    return value


def _stable_text(path: Path, label: str) -> str:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise ValueError(f"{label} changed while being read")
    return raw.decode("utf-8")


def _load_object(path: Path, label: str) -> dict:
    try:
        value = _strict_json_loads(_stable_text(path, label))
    except Exception as exc:
        raise ValueError(f"{label} missing/unreadable: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _safe_repo_path(repo: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = (repo / raw).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError:
        return None
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _blocked_media_report_error(placement: dict, repo: Path) -> str | None:
    """Verify that a semantic media block is backed by exact local evidence."""
    report_path = _safe_repo_path(repo, placement.get("media_qa_report"))
    asset_path = _safe_repo_path(repo, placement.get("media"))
    if report_path is None or not report_path.is_file():
        return "blocked semantic media QA report is missing or outside the repository"
    if asset_path is None or not asset_path.is_file():
        return "blocked semantic media asset is missing or outside the repository"
    try:
        report = _load_object(report_path, "blocked semantic media QA report")
        actual_hash = _sha256(asset_path)
    except (OSError, ValueError) as exc:
        return str(exc)
    if report.get("content_id") != placement.get("content_id"):
        return "blocked semantic media QA report is bound to another content_id"
    if report.get("verdict") != "BLOCKED" or report.get("receipt_created") is not False:
        return "blocked semantic media QA report must record BLOCKED and receipt_created=false"
    if str(report.get("sha256", "")).upper() != actual_hash:
        return "blocked semantic media QA report hash does not match the current asset"
    semantic = report.get("semantic_review")
    if not isinstance(semantic, dict) or semantic.get("status") != "FAIL":
        return "blocked semantic media QA report does not preserve the semantic failure"
    return None


def _media_binding_receipt_errors(
    placement: dict,
    repo: Path,
    *,
    calendar_file_sha256: str | None,
) -> list[str]:
    """Validate an optional cross-artifact media binding receipt.

    A normal media-QA receipt proves the asset bytes.  A declared binding
    receipt additionally promises that those bytes, the QA receipt, the source
    row and the exact calendar placement were reviewed together.  Treating its
    mere path as proof would let a later calendar/source edit retain stale QA.
    """
    raw_binding = placement.get("media_binding_receipt")
    if raw_binding is None:
        return []
    binding_path = _safe_repo_path(repo, raw_binding)
    if binding_path is None or not binding_path.is_file():
        return ["declared media binding receipt is missing or outside the repository"]
    try:
        binding = _load_object(binding_path, "media binding receipt")
    except ValueError as exc:
        return [str(exc)]

    errors: list[str] = []
    if binding.get("schema_version") != 1:
        errors.append("media binding receipt schema_version must be 1")

    calendar_binding = (
        binding.get("calendar")
        if isinstance(binding.get("calendar"), dict)
        else {}
    )
    if calendar_binding.get("path") != CALENDAR_PATH.as_posix():
        errors.append("media binding receipt calendar path differs from the canonical calendar")
    if calendar_file_sha256 is not None and (
        str(calendar_binding.get("file_sha256") or "").upper()
        != str(calendar_file_sha256).upper()
    ):
        errors.append("media binding receipt calendar SHA-256 differs from the current calendar")

    placement_source = (
        placement.get("source")
        if isinstance(placement.get("source"), dict)
        else {}
    )
    source_binding = (
        binding.get("source")
        if isinstance(binding.get("source"), dict)
        else {}
    )
    placement_source_path = _safe_repo_path(repo, placement_source.get("file"))
    bound_source_path = _safe_repo_path(repo, source_binding.get("path"))
    if (
        placement_source_path is None
        or bound_source_path is None
        or placement_source_path != bound_source_path
    ):
        errors.append("media binding receipt source path differs from the placement source")
    elif not placement_source_path.is_file():
        errors.append("media binding receipt source file is missing")
    elif (
        str(source_binding.get("sha256") or "").upper()
        != _sha256(placement_source_path)
    ):
        errors.append("media binding receipt source SHA-256 differs from the current source")
    if source_binding.get("row_id") != placement_source.get("row_id"):
        errors.append("media binding receipt source row differs from the placement source")
    if source_binding.get("field") != placement_source.get("field"):
        errors.append("media binding receipt source field differs from the placement source")

    assets = binding.get("assets") if isinstance(binding.get("assets"), dict) else {}
    matching_assets = [
        (key, value)
        for key, value in assets.items()
        if isinstance(value, dict) and value.get("path") == placement.get("media")
    ]
    if len(matching_assets) != 1:
        errors.append("media binding receipt must contain exactly one matching asset")
        asset_key, asset_binding = None, {}
    else:
        asset_key, asset_binding = matching_assets[0]
        asset_path = _safe_repo_path(repo, placement.get("media"))
        qa_path = _safe_repo_path(repo, placement.get("media_receipt"))
        if asset_path is None or not asset_path.is_file():
            errors.append("media binding receipt asset is missing")
        elif str(asset_binding.get("sha256") or "").upper() != _sha256(asset_path):
            errors.append("media binding receipt asset SHA-256 differs from the current media")
        if asset_binding.get("qa_receipt") != placement.get("media_receipt"):
            errors.append("media binding receipt QA path differs from the placement receipt")
        if qa_path is None or not qa_path.is_file():
            errors.append("media binding receipt QA file is missing")
        elif (
            str(asset_binding.get("qa_receipt_sha256") or "").upper()
            != _sha256(qa_path)
        ):
            errors.append("media binding receipt QA SHA-256 differs from the current receipt")

    placement_id = str(placement.get("placement_id") or "")
    placement_bindings = (
        binding.get("placement_bindings")
        if isinstance(binding.get("placement_bindings"), dict)
        else {}
    )
    placement_binding = placement_bindings.get(placement_id)
    if not isinstance(placement_binding, dict):
        errors.append("media binding receipt has no exact placement binding")
    else:
        if placement_binding.get("asset_key") != asset_key:
            errors.append("media binding receipt placement points to another asset")
        if (
            str(placement_binding.get("placement_canonical_sha256") or "").upper()
            != _canonical_sha256(placement)
        ):
            errors.append("media binding receipt placement SHA-256 differs from the current placement")
        if placement_binding.get("remaining_blockers") != placement.get("blockers"):
            errors.append("media binding receipt remaining blockers differ from the placement")
    return errors


def _parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_clock(value: object) -> time | None:
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError):
        return None


def _evaluation_clock(
    *, now: datetime | None, today: date | None, findings: list[dict]
) -> datetime:
    """Return one timezone-aware Asia/Bangkok evaluation instant.

    ``today`` remains as a deterministic compatibility override and means the
    start of that Bangkok day.  Runtime callers should use ``now`` (or omit both)
    so a missed slot on the current day cannot hide behind a date-only audit.
    Invalid/ambiguous caller time is recorded as a hard finding before a
    deterministic Bangkok interpretation is used for the remaining checks.
    """
    if now is not None and today is not None:
        findings.append(_finding("NOW_CONFLICT", "provide now or today, not both"))
    if now is not None:
        if now.tzinfo is None or now.utcoffset() is None:
            findings.append(_finding("NOW_TIMEZONE", "evaluation now must include a timezone"))
            return now.replace(tzinfo=BANGKOK)
        return now.astimezone(BANGKOK)
    if today is not None:
        return datetime.combine(today, time.min, tzinfo=BANGKOK)
    return datetime.now(BANGKOK)


def _table_rows(path: Path) -> dict[str, dict[str, str]]:
    """Parse the simple Markdown tables used by all three editorial libraries."""
    rows: dict[str, dict[str, str]] = {}
    header: list[str] | None = None
    for raw_line in _stable_text(path, "editorial library").splitlines():
        if not raw_line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        lowered = [cell.casefold() for cell in cells]
        if "date" in lowered and "id" in lowered:
            if len(lowered) != len(set(lowered)):
                raise ValueError("duplicate editorial library table header")
            header = lowered
            continue
        if header is None or len(cells) != len(header):
            continue
        if all(re.fullmatch(r"[-: ]+", cell or "-") for cell in cells):
            continue
        row = dict(zip(header, cells))
        content_id = row.get("id", "").strip()
        if content_id:
            if content_id in rows:
                raise ValueError(f"duplicate library content id: {content_id}")
            rows[content_id] = row
    return rows


def _section(path: Path, marker: str, expected_content_id: str) -> str:
    text = _stable_text(path, "editorial package")
    if not isinstance(expected_content_id, str) or not expected_content_id.strip():
        raise ValueError("editorial package expected content_id is missing")
    if text.count("**Asset ID:**") != 1:
        raise ValueError("editorial package must contain exactly one Asset ID marker")
    asset_matches = list(re.finditer(
        r"(?m)^\s*-\s+\*\*Asset ID:\*\*\s*`([^`\r\n]+)`\s*\r?$",
        text,
    ))
    if len(asset_matches) != 1:
        raise ValueError("editorial package Asset ID marker is malformed")
    if asset_matches[0].group(1).strip() != expected_content_id.strip():
        raise ValueError("editorial package Asset ID does not match content_id")

    heading_text = {
        "youtube_package": "YouTube package",
        "social_caption": "Social caption",
    }.get(marker)
    if not heading_text:
        raise ValueError("editorial package section marker is unsupported")
    heading_matches = list(re.finditer(
        rf"(?m)^## {re.escape(heading_text)}[ \t]*\r?$",
        text,
    ))
    if len(heading_matches) != 1:
        raise ValueError("editorial package target heading must occur exactly once")
    tail = text[heading_matches[0].end():]
    next_heading = re.search(r"(?m)^##[ \t]+[^\r\n]+[ \t]*\r?$", tail)
    section = tail[:next_heading.start() if next_heading else None].strip()
    if not section:
        raise ValueError("editorial package target section is empty")
    return section


def _copy_text(row: dict[str, str], field: str) -> str:
    return re.sub(r"<br\s*/?>", "\n", row.get(field, ""), flags=re.I)


def _weekly_pack_rows(path: Path) -> dict[str, dict]:
    document = _load_object(path, "weekly replacement pack")
    if (
        document.get("schema_version") != 1
        or document.get("state") != "DRAFT_ONLY"
        or document.get("calendar_action")
        != "REPLACEMENT_CANDIDATES_ONLY_DO_NOT_ADD_OR_REPLACE_AUTOMATICALLY"
    ):
        raise ValueError("weekly replacement pack contract is invalid")
    days = document.get("days")
    if not isinstance(days, list):
        raise ValueError("weekly replacement pack days are malformed")
    rows: dict[str, dict] = {}
    for day in days:
        if not isinstance(day, dict):
            raise ValueError("weekly replacement candidate is malformed")
        candidate_id = str(day.get("candidate_id") or "").strip()
        if not candidate_id or candidate_id in rows:
            raise ValueError("weekly replacement candidate identity is invalid")
        rows[candidate_id] = day
    return rows


def _weekly_public_copy(day: dict) -> dict:
    image = day.get("image_spec") if isinstance(day.get("image_spec"), dict) else {}
    tiktok = day.get("tiktok_draft") if isinstance(day.get("tiktok_draft"), dict) else {}
    return {
        "threads_text": day.get("threads_text"),
        "facebook_text": day.get("facebook_text"),
        "quote_text": day.get("quote_text"),
        "image_overlay_text": image.get("exact_overlay_text"),
        "tiktok": {
            "hook": tiktok.get("hook"),
            "voiceover": tiktok.get("voiceover"),
            "onscreen_text": tiktok.get("onscreen_text"),
            "end_card": tiktok.get("end_card"),
        },
    }


def _replacement_evidence_errors(
    calendar: dict,
    spec: dict,
    rows: dict[str, dict],
    repo: Path,
    *,
    calendar_file_sha256: str | None,
) -> list[str]:
    errors: list[str] = []
    selected_ids = {
        str(value) for value in spec.get("ids", [])
        if isinstance(value, str) and value.strip()
    }
    if not selected_ids:
        return ["replacement selection is empty"]

    receipt_path = _safe_repo_path(repo, spec.get("change_receipt"))
    freshness_spec = spec.get("freshness_receipt")
    freshness_spec = freshness_spec if isinstance(freshness_spec, dict) else {}
    novelty_spec = spec.get("novelty_receipt")
    novelty_spec = novelty_spec if isinstance(novelty_spec, dict) else {}
    freshness_path = _safe_repo_path(repo, freshness_spec.get("path"))
    novelty_path = _safe_repo_path(repo, novelty_spec.get("path"))
    pack_path = _safe_repo_path(repo, spec.get("source_file"))
    if receipt_path is None or freshness_path is None or novelty_path is None:
        return ["replacement evidence path is missing or outside the repository"]
    try:
        change = _load_object(receipt_path, "replacement change receipt")
        freshness = _load_object(freshness_path, "replacement freshness receipt")
        novelty = _load_object(novelty_path, "replacement novelty receipt")
    except ValueError as exc:
        return [str(exc)]
    if pack_path is None or not pack_path.is_file():
        return ["replacement pack is missing"]
    pack_hash = _sha256(pack_path)

    if change.get("schema_version") != 1:
        errors.append("change receipt schema is invalid")
    if change.get("change_kind") != "OWNER_AUTHORIZED_LOCAL_PLAN_REPLACEMENT":
        errors.append("change receipt kind is invalid")
    if change.get("scope") != "LOCAL_EDITORIAL_PLAN_ONLY":
        errors.append("change receipt scope is invalid")
    authority = change.get("authority_changes")
    authority = authority if isinstance(authority, dict) else {}
    if any(authority.get(key) is not False for key in (
        "policy_mutated", "role_capabilities_mutated",
        "publication_authority_mutated", "owner_receipt_minted",
    )):
        errors.append("change receipt claims a forbidden authority mutation")
    external = change.get("external_actions")
    external = external if isinstance(external, dict) else {}
    if not external or any(value is not False for value in external.values()):
        errors.append("change receipt does not preserve the local-only boundary")
    calendar_binding = change.get("calendar")
    calendar_binding = calendar_binding if isinstance(calendar_binding, dict) else {}
    if calendar_file_sha256 is not None:
        if str(calendar_binding.get("after_file_sha256") or "").upper() != calendar_file_sha256:
            errors.append("change receipt file SHA-256 does not match the calendar")
        if str(calendar_binding.get("after_canonical_sha256") or "").upper() != _canonical_sha256(calendar):
            errors.append("change receipt canonical SHA-256 does not match the calendar")

    change_evidence = change.get("evidence")
    change_evidence = change_evidence if isinstance(change_evidence, dict) else {}
    pack_evidence = change_evidence.get("pack")
    pack_evidence = pack_evidence if isinstance(pack_evidence, dict) else {}
    if (
        str(spec.get("pack_sha256") or "").upper() != pack_hash
        or str(pack_evidence.get("sha256") or "").upper() != pack_hash
    ):
        errors.append("change receipt pack SHA-256 does not match the exact pack")
    if str(freshness_spec.get("sha256") or "").upper() != _sha256(freshness_path):
        errors.append("freshness receipt SHA-256 does not match")
    if str(novelty_spec.get("sha256") or "").upper() != _sha256(novelty_path):
        errors.append("novelty receipt SHA-256 does not match")
    freshness_pack = freshness.get("pack")
    freshness_pack = freshness_pack if isinstance(freshness_pack, dict) else {}
    novelty_pack = novelty.get("pack")
    novelty_pack = novelty_pack if isinstance(novelty_pack, dict) else {}
    if str(freshness_pack.get("sha256") or "").upper() != pack_hash:
        errors.append("freshness receipt is not bound to the exact pack")
    if str(novelty_pack.get("sha256") or "").upper() != pack_hash:
        errors.append("novelty receipt is not bound to the exact pack")

    freshness_rows = {
        str(item.get("candidate_id") or ""): item
        for item in freshness.get("candidates", [])
        if isinstance(item, dict)
    }
    candidate_ids = {
        str(value) for value in novelty_pack.get("candidate_ids", [])
        if isinstance(value, str)
    }
    text_novelty = novelty.get("text_novelty")
    text_novelty = text_novelty if isinstance(text_novelty, dict) else {}
    collision_fields = (
        "historical_exact_collisions", "historical_near_collisions",
        "cross_candidate_exact_collisions", "cross_candidate_near_collisions",
    )
    collisions = []
    for field in collision_fields:
        value = text_novelty.get(field)
        if not isinstance(value, list):
            errors.append("novelty receipt collision inventory is malformed")
            continue
        collisions.extend(value)

    placements_by_id = {
        str(item.get("placement_id") or ""): item
        for item in calendar.get("placements", [])
        if isinstance(item, dict)
    }
    caption_bindings = change.get("caption_bindings")
    caption_bindings = caption_bindings if isinstance(caption_bindings, dict) else {}
    for candidate_id in sorted(selected_ids):
        day = rows.get(candidate_id)
        fresh_row = freshness_rows.get(candidate_id)
        if not isinstance(day, dict) or not isinstance(fresh_row, dict):
            errors.append(f"{candidate_id}: candidate or freshness row is missing")
            continue
        if (
            day.get("source_review")
            != "NOT_REQUIRED_IF_TEXT_REMAINS_EXACT"
            or
            day.get("source_ids") != []
            or fresh_row.get("source_ids") != []
            or fresh_row.get("high_risk_findings") != []
            or fresh_row.get("source_decision")
            != "NOT_REQUIRED_ONLY_WHILE_EXACT_COPY_HASH_MATCHES"
            or fresh_row.get("public_copy_sha256")
            != _canonical_sha256(_weekly_public_copy(day))
        ):
            errors.append(f"{candidate_id}: evergreen exact-copy evidence is invalid")
        if candidate_id not in candidate_ids or any(
            isinstance(item, dict) and candidate_id in {
                str(item.get("candidate_id") or ""),
                str(item.get("left_candidate_id") or ""),
                str(item.get("right_candidate_id") or ""),
            }
            for item in collisions
        ):
            errors.append(f"{candidate_id}: per-item novelty evidence is invalid")
        for account, field in (
            ("threads_main", "threads_text"),
            ("facebook_main", "facebook_text"),
        ):
            placement_id = f"{candidate_id}__{account}"
            placement = placements_by_id.get(placement_id)
            binding = caption_bindings.get(placement_id)
            binding = binding if isinstance(binding, dict) else {}
            if not isinstance(placement, dict):
                errors.append(f"{placement_id}: replacement placement is missing")
                continue
            caption = day.get(field)
            caption_hash = (
                hashlib.sha256(caption.encode("utf-8")).hexdigest().upper()
                if isinstance(caption, str)
                else ""
            )
            expected_adaptation = (
                "short_text_no_body_url_profile_link_only"
                if account == "threads_main"
                else "long_text_no_body_url_profile_link_only"
            )
            gates = placement.get("gates")
            gates = gates if isinstance(gates, dict) else {}
            blockers = placement.get("blockers")
            blockers = blockers if isinstance(blockers, list) else []
            if (
                binding.get("source_field") != field
                or str(binding.get("caption_sha256") or "").upper() != caption_hash
                or str(binding.get("placement_canonical_sha256") or "").upper()
                != _canonical_sha256(placement)
                or placement.get("status") != BLOCKED_STATUS
                or placement.get("slot_state") != BLOCKED_SLOT
                or placement.get("media") is not None
                or placement.get("media_receipt") is not None
                or placement.get("source_ids") != []
                or placement.get("cta_id") != "quote-profile"
                or placement.get("adaptation") != expected_adaptation
                or set(blockers)
                != {"publication_authority", "permanent_dedup_coverage"}
                or gates.get("publication_authority") != "BLOCKED"
                or gates.get("source_review") != "NOT_REQUIRED"
                or gates.get("media") != "NOT_REQUIRED"
                or gates.get("dedup") != "REQUIRED"
                or gates.get("page_identity") != "PASS"
                or gates.get("evergreen_exact_copy") != "PASS"
                or gates.get("candidate_novelty") != "PASS_PER_ITEM"
                or gates.get("global_permanent_dedup") != "BLOCKED"
            ):
                errors.append(
                    f"{placement_id}: exact caption, CTA, page-only, or text-only binding is invalid"
                )

    quote_caption_bindings = change.get("quote_caption_bindings")
    quote_caption_bindings = (
        quote_caption_bindings if isinstance(quote_caption_bindings, dict) else {}
    )
    if set(quote_caption_bindings) != set(QUOTE_PACK_CAPTION_FIELDS):
        errors.append("quote caption binding inventory is incomplete or contains extra rows")
    for placement_id, field in sorted(QUOTE_PACK_CAPTION_FIELDS.items()):
        placement = placements_by_id.get(placement_id)
        binding = quote_caption_bindings.get(placement_id)
        binding = binding if isinstance(binding, dict) else {}
        content_id, account = placement_id.split("__", 1)
        day = rows.get(content_id)
        source = placement.get("source") if isinstance(placement, dict) else {}
        source = source if isinstance(source, dict) else {}
        gates = placement.get("gates") if isinstance(placement, dict) else {}
        gates = gates if isinstance(gates, dict) else {}
        blockers = placement.get("blockers") if isinstance(placement, dict) else []
        blockers = blockers if isinstance(blockers, list) else []
        caption = day.get(field) if isinstance(day, dict) else None
        caption_hash = (
            hashlib.sha256(caption.encode("utf-8")).hexdigest().upper()
            if isinstance(caption, str) and caption.strip()
            else ""
        )
        expected_blockers = {"publication_authority"}
        if account in {"instagram_main", "pinterest_main"}:
            expected_blockers.add("channel_review")
        if (
            not isinstance(placement, dict)
            or not isinstance(day, dict)
            or day.get("source_review") != "NOT_REQUIRED"
            or day.get("source_ids") != []
            or placement.get("topic") != day.get("quote_text")
            or source.get("file") != spec.get("source_file")
            or source.get("row_id") != content_id
            or source.get("field") != field
            or placement.get("adaptation") != QUOTE_PACK_ADAPTATIONS.get(account)
            or placement.get("status") != BLOCKED_STATUS
            or placement.get("slot_state") != RESERVED_SLOT
            or set(blockers) != expected_blockers
            or placement.get("cta_id") != "quote-profile"
            or gates.get("publication_authority") != "BLOCKED"
            or gates.get("source_review") != "NOT_REQUIRED"
            or gates.get("media") != "PASS"
            or gates.get("dedup") != "REQUIRED"
            or gates.get("page_identity") != "PASS"
            or binding.get("source_field") != field
            or str(binding.get("caption_sha256") or "").upper() != caption_hash
            or str(binding.get("placement_canonical_sha256") or "").upper()
            != _canonical_sha256(placement)
            or set(binding.get("remaining_blockers") or []) != expected_blockers
        ):
            errors.append(
                f"{placement_id}: exact quote caption or fail-closed channel binding is invalid"
            )
    superseded_rows = change.get("superseded_placements")
    superseded_rows = superseded_rows if isinstance(superseded_rows, list) else []
    superseded_by_id = {
        str(item.get("placement_id") or ""): item
        for item in superseded_rows
        if isinstance(item, dict) and item.get("placement_id")
    }
    superseded_bindings = change.get("superseded_bindings")
    superseded_bindings = (
        superseded_bindings if isinstance(superseded_bindings, dict) else {}
    )
    supersedes = spec.get("supersedes")
    supersedes = supersedes if isinstance(supersedes, dict) else {}
    for original, candidate_id in sorted(supersedes.items()):
        day = rows.get(str(candidate_id))
        for account in ("threads_main", "facebook_main"):
            old_id = f"{original}__{account}"
            old = superseded_by_id.get(old_id)
            binding = superseded_bindings.get(old_id)
            binding = binding if isinstance(binding, dict) else {}
            if (
                not isinstance(day, dict)
                or not isinstance(old, dict)
                or old.get("content_id") != original
                or old.get("date") != day.get("date")
                or old.get("account") != account
                or old.get("status") != BLOCKED_STATUS
                or old.get("slot_state") != BLOCKED_SLOT
                or binding.get("candidate_id") != candidate_id
                or str(binding.get("placement_canonical_sha256") or "").upper()
                != _canonical_sha256(old)
            ):
                errors.append(f"{old_id}: superseded placement hash binding is invalid")
    expected_old_ids = {
        f"{original}__{account}"
        for original in supersedes
        for account in ("threads_main", "facebook_main")
    }
    if set(superseded_by_id) != expected_old_ids or set(superseded_bindings) != expected_old_ids:
        errors.append("superseded placement inventory does not exactly match the replacement map")
    required_remaining = {
        "PUBLICATION_AUTHORITY_FALSE",
        "PRIVATE_ONE_TIME_OWNER_RECEIPT_MISSING",
        "GLOBAL_PERMANENT_DEDUP_IDENTITY_COVERAGE_INCOMPLETE",
    }
    if not required_remaining.issubset(set(change.get("remaining_blockers") or [])):
        errors.append("change receipt hides a mandatory publication blocker")
    return errors


def _tiktok_week_replacement_evidence_errors(
    calendar: dict,
    spec: dict,
    rows: dict[str, dict],
    repo: Path,
    *,
    calendar_file_sha256: str | None,
) -> list[str]:
    """Validate the reversible local-only substitution of seven produced videos.

    The original TikTok briefs remain in the immutable runway and policy.  This
    contract only substitutes their seven future calendar placements with exact
    weekly-pack candidates whose final assets and QA receipts already exist.
    Human listening and every publication/source/live/owner gate remain blocked.
    """

    errors: list[str] = []
    selected = {
        str(value) for value in spec.get("ids", [])
        if isinstance(value, str) and value.strip()
    }
    supersedes = spec.get("supersedes")
    supersedes = supersedes if isinstance(supersedes, dict) else {}
    if selected != TIKTOK_WEEK_REPLACEMENT_IDS:
        errors.append("TikTok week replacement selection is not the exact seven-item set")
    if supersedes != TIKTOK_WEEK_REPLACEMENT_MAP:
        errors.append("TikTok week replacement map drifted")
    if (
        spec.get("selection_mode") != "OWNER_AUTHORIZED_LOCAL_PLAN_REPLACEMENT"
        or spec.get("reservation_only") is not True
        or spec.get("link_policy") != TIKTOK_LINK_POLICY
    ):
        errors.append("TikTok week replacement mode is not local-only and fail-closed")

    pack_path = _safe_repo_path(repo, spec.get("source_file"))
    receipt_path = _safe_repo_path(repo, spec.get("change_receipt"))
    if pack_path is None or not pack_path.is_file() or receipt_path is None:
        return errors + ["TikTok week replacement pack or receipt path is invalid"]
    try:
        receipt = _load_object(receipt_path, "TikTok week replacement receipt")
    except ValueError as exc:
        return errors + [str(exc)]

    if (
        receipt.get("schema_version") != 1
        or receipt.get("change_kind") != "OWNER_AUTHORIZED_LOCAL_PLAN_REPLACEMENT"
        or receipt.get("scope") != "LOCAL_EDITORIAL_PLAN_ONLY"
    ):
        errors.append("TikTok week replacement receipt contract is invalid")
    authority = receipt.get("authority_changes")
    authority = authority if isinstance(authority, dict) else {}
    if any(authority.get(key) is not False for key in (
        "policy_mutated", "role_capabilities_mutated",
        "publication_authority_mutated", "owner_receipt_minted",
    )):
        errors.append("TikTok week replacement receipt claims a forbidden authority mutation")
    external = receipt.get("external_actions")
    external = external if isinstance(external, dict) else {}
    if not external or any(value is not False for value in external.values()):
        errors.append("TikTok week replacement receipt does not preserve local-only execution")

    calendar_binding = receipt.get("calendar")
    calendar_binding = calendar_binding if isinstance(calendar_binding, dict) else {}
    if calendar_file_sha256 is not None and (
        str(calendar_binding.get("after_file_sha256") or "").upper()
        != calendar_file_sha256
    ):
        errors.append("TikTok week receipt file SHA-256 does not match the calendar")
    if (
        str(calendar_binding.get("after_canonical_sha256") or "").upper()
        != _canonical_sha256(calendar)
    ):
        errors.append("TikTok week receipt canonical SHA-256 does not match the calendar")

    evidence = receipt.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    pack_evidence = evidence.get("pack")
    pack_evidence = pack_evidence if isinstance(pack_evidence, dict) else {}
    if (
        pack_evidence.get("path") != spec.get("source_file")
        or str(pack_evidence.get("sha256") or "").upper() != _sha256(pack_path)
        or str(spec.get("pack_sha256") or "").upper() != _sha256(pack_path)
    ):
        errors.append("TikTok week receipt is not bound to the exact weekly pack")
    plan_evidence = evidence.get("superseded_plan")
    plan_evidence = plan_evidence if isinstance(plan_evidence, dict) else {}
    plan_path = _safe_repo_path(repo, plan_evidence.get("path"))
    if plan_path is None or plan_path.name != TIKTOK_PLAN_FILENAME or not plan_path.is_file():
        errors.append("TikTok superseded runway evidence is missing")
        plan_rows = {}
    else:
        if str(plan_evidence.get("sha256") or "").upper() != _sha256(plan_path):
            errors.append("TikTok superseded runway hash drifted")
        try:
            plan_rows = _table_rows(plan_path)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"TikTok superseded runway is unreadable: {exc}")
            plan_rows = {}

    placements_by_id = {
        str(item.get("placement_id") or ""): item
        for item in calendar.get("placements", [])
        if isinstance(item, dict)
    }
    replacement_bindings = receipt.get("replacement_bindings")
    replacement_bindings = (
        replacement_bindings if isinstance(replacement_bindings, dict) else {}
    )
    superseded_bindings = receipt.get("superseded_plan_bindings")
    superseded_bindings = (
        superseded_bindings if isinstance(superseded_bindings, dict) else {}
    )
    expected_new_ids = {
        f"{candidate_id}__{TIKTOK_ACCOUNT}"
        for candidate_id in TIKTOK_WEEK_REPLACEMENT_MAP.values()
    }
    if set(replacement_bindings) != expected_new_ids:
        errors.append("TikTok replacement binding inventory is incomplete or contains extra rows")
    if set(superseded_bindings) != set(TIKTOK_WEEK_REPLACEMENT_MAP):
        errors.append("TikTok superseded plan binding inventory is incomplete or contains extra rows")

    required_blockers = set(TIKTOK_REQUIRED_BLOCKERS) | {HUMAN_LISTENING_BLOCKER}
    for old_id, candidate_id in TIKTOK_WEEK_REPLACEMENT_MAP.items():
        placement_id = f"{candidate_id}__{TIKTOK_ACCOUNT}"
        placement = placements_by_id.get(placement_id)
        binding = replacement_bindings.get(placement_id)
        binding = binding if isinstance(binding, dict) else {}
        day = rows.get(candidate_id)
        day = day if isinstance(day, dict) else {}
        draft = day.get("tiktok_draft")
        draft = draft if isinstance(draft, dict) else {}
        asset = draft.get("candidate_asset")
        asset = asset if isinstance(asset, dict) else {}
        source = placement.get("source") if isinstance(placement, dict) else {}
        source = source if isinstance(source, dict) else {}
        gates = placement.get("gates") if isinstance(placement, dict) else {}
        gates = gates if isinstance(gates, dict) else {}
        blockers = placement.get("blockers") if isinstance(placement, dict) else []
        blockers = blockers if isinstance(blockers, list) else []
        provenance = (
            placement.get("replacement_provenance")
            if isinstance(placement, dict) else {}
        )
        provenance = provenance if isinstance(provenance, dict) else {}
        caption = day.get(TIKTOK_WEEK_SOURCE_FIELD)
        caption_hash = (
            hashlib.sha256(caption.encode("utf-8")).hexdigest().upper()
            if isinstance(caption, str) and caption.strip()
            else ""
        )
        media_path = _safe_repo_path(repo, asset.get("path"))
        media_receipt_path = _safe_repo_path(repo, asset.get("qa_receipt"))
        if (
            not isinstance(placement, dict)
            or not day
            or day.get("date") != placement.get("date")
            or placement.get("time") != "19:00"
            or placement.get("topic") != day.get("theme")
            or placement.get("account") != TIKTOK_ACCOUNT
            or source.get("file") != spec.get("source_file")
            or source.get("row_id") != candidate_id
            or source.get("field") != TIKTOK_WEEK_SOURCE_FIELD
            or placement.get("source_ids") != []
            or placement.get("adaptation") != TIKTOK_WEEK_ADAPTATION
            or placement.get("format") != "video"
            or placement.get("media") != asset.get("path")
            or placement.get("media_receipt") != asset.get("qa_receipt")
            or placement.get("media_content_id") != candidate_id
            or placement.get("cta_id") != "tiktok-no-link"
            or placement.get("link_policy") != TIKTOK_LINK_POLICY
            or placement.get("status") != BLOCKED_STATUS
            or placement.get("slot_state") != RESERVED_SLOT
            or set(blockers) != required_blockers
            or gates.get("publication_authority") != "BLOCKED"
            or gates.get("source_review") != "BLOCKED"
            or gates.get("media") != "BLOCKED"
            or gates.get("dedup") != "REQUIRED"
            or gates.get("page_identity") != "PASS"
            or gates.get("owner_confirmation") != "BLOCKED"
            or gates.get("live_history_dedup") != "BLOCKED"
            or gates.get("landing_parity") != "BLOCKED"
            or provenance.get("supersedes_placement_id")
            != f"{old_id}__{TIKTOK_ACCOUNT}"
            or provenance.get("supersedes_content_id") != old_id
            or provenance.get("candidate_id") != candidate_id
            or provenance.get("change_receipt") != spec.get("change_receipt")
            or media_path is None
            or not media_path.is_file()
            or media_receipt_path is None
            or not media_receipt_path.is_file()
            or str(asset.get("sha256") or "").upper() != _sha256(media_path)
            or binding.get("source_field") != TIKTOK_WEEK_SOURCE_FIELD
            or str(binding.get("caption_sha256") or "").upper() != caption_hash
            or binding.get("asset") != asset.get("path")
            or str(binding.get("asset_sha256") or "").upper() != _sha256(media_path)
            or binding.get("media_receipt") != asset.get("qa_receipt")
            or str(binding.get("media_receipt_sha256") or "").upper()
            != _sha256(media_receipt_path)
            or str(binding.get("placement_canonical_sha256") or "").upper()
            != _canonical_sha256(placement)
            or set(binding.get("remaining_blockers") or []) != required_blockers
            or binding.get("limitation") != "HUMAN_LISTENING_NOT_RUN"
        ):
            errors.append(
                f"{placement_id}: exact TikTok replacement, media, or fail-closed binding is invalid"
            )

        old_row = plan_rows.get(old_id)
        old_row = old_row if isinstance(old_row, dict) else {}
        old_binding = superseded_bindings.get(old_id)
        old_binding = old_binding if isinstance(old_binding, dict) else {}
        if (
            old_row.get("phase") != "creative_brief"
            or old_row.get("asset") != "TBD"
            or old_row.get("qa_receipt") != "MISSING"
            or old_row.get("date") != day.get("date")
            or old_row.get("time") != "19:00"
            or old_binding.get("candidate_id") != candidate_id
            or str(old_binding.get("plan_row_canonical_sha256") or "").upper()
            != _canonical_sha256(old_row)
        ):
            errors.append(f"{old_id}: superseded TikTok brief binding is invalid")

    required_remaining = {
        "PUBLICATION_AUTHORITY_FALSE",
        "PRIVATE_ONE_TIME_OWNER_RECEIPT_MISSING",
        "OFFICIAL_SOURCE_REVIEW_BLOCKED",
        "LIVE_TIKTOK_HISTORY_DEDUP_BLOCKED",
        "LIVE_LANDING_AND_BIO_PARITY_BLOCKED",
        "HUMAN_LISTENING_NOT_RUN",
        "GLOBAL_PERMANENT_DEDUP_IDENTITY_COVERAGE_INCOMPLETE",
    }
    if not required_remaining.issubset(set(receipt.get("remaining_blockers") or [])):
        errors.append("TikTok week receipt hides a mandatory publication blocker")
    return errors


def _ledger_rows(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    failures: list[str] = []
    if not path.is_file():
        return rows, ["post ledger is missing"]
    try:
        document = _stable_text(path, "post ledger")
        if document and not document.endswith("\n"):
            failures.append("post ledger final record is not newline committed")
        for line_no, raw in enumerate(document.splitlines(), 1):
            if not raw.strip():
                continue
            try:
                row = _strict_json_loads(raw)
            except (json.JSONDecodeError, ValueError):
                failures.append(f"post ledger line {line_no} is malformed")
                continue
            if not isinstance(row, dict):
                failures.append(f"post ledger line {line_no} is not an object")
                continue
            rows.append(row)
    except (OSError, UnicodeError) as exc:
        failures.append(f"post ledger is unreadable: {type(exc).__name__}")
    return rows, failures


def _ledger_account(channel: object) -> str | None:
    normalized = str(channel or "").strip().casefold().replace("_", "-")
    mapping = {
        "facebook-page2": "facebook_page2",
        "fb-page2": "facebook_page2",
        "facebook": "facebook_main",
        "fb": "facebook_main",
        "threads": "threads_main",
        "youtube": "youtube_main",
        "yt": "youtube_main",
        "instagram": "instagram_main",
        "ig": "instagram_main",
        "pinterest": "pinterest_main",
        "tiktok": "tiktok_main",
        "tt": "tiktok_main",
    }
    return mapping.get(normalized)


def _account_rate_identity(accounts: dict, account_id: object) -> str | None:
    """Return the policy channel used by the live ledger's cap/gap contract.

    Multiple page accounts on one platform intentionally share one rate identity
    unless a future policy introduces and validates an explicit override.  The live
    writers currently claim ``facebook`` rather than a page-specific channel, so the
    calendar must not treat Facebook Page 1 and Page 2 as independent gap buckets.
    """
    account = accounts.get(str(account_id or "").strip())
    if not isinstance(account, dict):
        return None
    value = account.get("policy_channel")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().casefold()


def _account_dedup_identity(accounts: dict, account_id: object) -> str | None:
    """Return the permanent-dedup identity space for one public account.

    Quota/gap intentionally shares Facebook's policy channel across both pages,
    but permanent dedup is explicitly same-account.  The append-only ledger uses
    ``facebook-page2`` for the second page, so collapsing it into ``fb`` would let
    an unresolved Page 1 Story deadlock otherwise independent Page 2 content.
    """
    selected_account = str(account_id or "").strip()
    account = accounts.get(selected_account)
    if not isinstance(account, dict):
        return None
    if selected_account == "facebook_page2":
        return "facebook-page2"
    channel = account.get("channel")
    if not isinstance(channel, str) or not channel.strip():
        return None
    normalized = post_ledger.norm_channel(channel)
    return normalized or None


def _ledger_content_id(row: dict) -> str:
    for field in ("content_id", "kn_id", "p2_id", "clip_id", "clip_key", "slug"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().casefold()
    return ""


def _aware_ledger_timestamp(value: object) -> datetime | None:
    """Parse exact ledger time without inventing a timezone for legacy data."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return None
    return stamp.astimezone(BANGKOK)


def _ledger_rate_time(row: dict) -> tuple[datetime | None, date | None]:
    """Return exact publication time and, when knowable, its quota day.

    A schedule date without a time is useful for the daily cap but cannot prove
    the minimum gap.  ``posted_at`` on a scheduled row is commonly the time the
    scheduler UI was used, so it must not be substituted for the future slot.
    """
    kind = str(row.get("type") or "").strip().casefold()
    if kind == "schedule" and row.get("scheduled_for"):
        exact = _aware_ledger_timestamp(row.get("scheduled_for"))
        if exact is not None:
            return exact, exact.date()
        return None, _parse_iso_date(row.get("scheduled_for"))

    for field in ("published_at", "posted_at", "ts"):
        if row.get(field):
            exact = _aware_ledger_timestamp(row.get(field))
            if exact is not None:
                return exact, exact.date()
            return None, _parse_iso_date(row.get(field))

    exact = _aware_ledger_timestamp(row.get("scheduled_for"))
    if exact is not None:
        return exact, exact.date()
    return None, _parse_iso_date(row.get("scheduled_for"))


def _default_source_result(content_id: str, repo: Path, now: datetime):
    return content_source_gate.evaluate_repo_content_source_gate(
        content_id,
        repo,
        now=now,
    )


def _default_media_result(asset: str, receipt: str, repo: Path):
    return media_publish_guard.evaluate(asset, receipt, repo=repo)


def _source_allowed(result: object) -> bool:
    allowed = (
        result.get("allowed")
        if isinstance(result, dict)
        else getattr(result, "allowed", False)
    )
    # A contradictory or incomplete evaluator response is never publication
    # evidence.  ``allowed=True`` must be backed by at least one exact source
    # identity and by an empty failure set.
    return (
        allowed is True
        and bool(_source_ids(result))
        and not _source_failures(result)
    )


def _source_ids(result: object) -> set[str]:
    if isinstance(result, dict):
        value = result.get("source_ids")
    else:
        value = getattr(result, "source_ids", ())
    return {str(item) for item in (value or ()) if str(item).strip()}


def _source_failures(result: object) -> list[str]:
    if isinstance(result, dict):
        value = result.get("failures")
    else:
        value = getattr(result, "failures", ())
    return [str(item) for item in (value or ())]


def evaluate_document(
    calendar: dict,
    *,
    repo: Path = ROOT,
    today: date | None = None,
    now: datetime | None = None,
    policy: dict | None = None,
    ledger_rows: list[dict] | None = None,
    source_evaluator=None,
    media_evaluator=None,
    calendar_file_sha256: str | None = None,
) -> dict:
    """Validate one in-memory calendar without performing an external mutation."""
    repo = Path(repo).resolve()
    findings: list[dict] = []
    if not isinstance(calendar, dict):
        return _closed_result(
            PROCESS_BLOCKED,
            [_finding("CALENDAR_SHAPE", "calendar must be an object")],
        )

    if calendar.get("schema_version") != 1:
        findings.append(_finding("SCHEMA", "schema_version must be 1"))
    if calendar.get("purpose") != "editorial_plan_only_no_publication":
        findings.append(_finding("PURPOSE", "calendar purpose must remain editorial-only"))
    if calendar.get("timezone") != TIMEZONE_NAME:
        findings.append(_finding("TIMEZONE", f"timezone must be {TIMEZONE_NAME}"))

    plan_as_of = _parse_iso_date(calendar.get("plan_as_of"))
    not_before = _parse_iso_date(calendar.get("not_before"))
    if plan_as_of is None or not_before is None or not_before <= plan_as_of:
        findings.append(_finding("DATE_CONTRACT", "plan_as_of/not_before are invalid or not future-only"))
    evaluation_now_bangkok = _evaluation_clock(now=now, today=today, findings=findings)
    current_day = evaluation_now_bangkok.date()

    try:
        policy = policy or _load_object(repo / POLICY_PATH, "policy")
    except ValueError as exc:
        policy = {}
        findings.append(_finding("POLICY", str(exc)))
    identity_policy = policy.get("public_identity") if isinstance(policy.get("public_identity"), dict) else {}
    canonical = identity_policy.get("canonical_name")
    root_identity = calendar.get("public_identity") if isinstance(calendar.get("public_identity"), dict) else {}
    if not isinstance(canonical, str) or not canonical.strip():
        findings.append(_finding("IDENTITY_POLICY", "policy canonical page identity is missing"))
        canonical = ""
    if root_identity.get("canonical_brand") != canonical:
        findings.append(_finding("IDENTITY_CANONICAL", "calendar canonical brand does not match policy"))
    if root_identity.get("entity_type") != "Organization" or root_identity.get("page_only") is not True:
        findings.append(_finding("IDENTITY_PAGE_ONLY", "calendar identity must be a page-only Organization"))

    accounts = calendar.get("accounts") if isinstance(calendar.get("accounts"), dict) else {}
    sets = calendar.get("content_sets") if isinstance(calendar.get("content_sets"), dict) else {}
    tiktok_set = sets.get("tiktok_reactivation") if isinstance(sets.get("tiktok_reactivation"), dict) else {}
    tiktok_ids = {
        str(value) for value in tiktok_set.get("ids", [])
        if isinstance(value, str) and value.strip()
    }
    tiktok_week_set = (
        sets.get("tiktok_week_replacements")
        if isinstance(sets.get("tiktok_week_replacements"), dict)
        else {}
    )
    tiktok_week_ids = {
        str(value) for value in tiktok_week_set.get("ids", [])
        if isinstance(value, str) and value.strip()
    }
    reservation_ids = set(HELD_IDS) | tiktok_ids | tiktok_week_ids
    channels_policy = policy.get("channels") if isinstance(policy.get("channels"), dict) else {}
    account_policies: dict[str, dict] = {}
    forbidden_speakers = {
        str(value).strip().casefold()
        for value in identity_policy.get("forbidden_public_speakers", [])
        if isinstance(value, str) and value.strip()
    }
    personal_patterns: list[re.Pattern] = []
    for raw in identity_policy.get("forbidden_personal_claim_patterns", []):
        try:
            personal_patterns.append(re.compile(str(raw), re.I))
        except re.error:
            findings.append(_finding("IDENTITY_PATTERN", "policy has an invalid personal-voice pattern"))

    for account_id, account in accounts.items():
        if not isinstance(account, dict):
            findings.append(_finding("ACCOUNT_SHAPE", f"account {account_id} is malformed"))
            continue
        speaker = str(account.get("public_speaker", "")).strip()
        if account.get("page_only") is not True or account.get("entity_type") != "Organization":
            findings.append(_finding("ACCOUNT_PAGE_ONLY", f"account {account_id} must be page-only Organization"))
        if not speaker or speaker.casefold() in forbidden_speakers:
            findings.append(_finding("ACCOUNT_SPEAKER", f"account {account_id} has a forbidden public speaker"))
        if account_id == "facebook_page2":
            if speaker != EXPECTED_PAGE2_NAME or account.get("brand_owner") != canonical:
                findings.append(_finding("PAGE2_IDENTITY", "facebook_page2 identity or brand owner is incorrect"))
        elif speaker != canonical:
            findings.append(_finding("ACCOUNT_IDENTITY", f"account {account_id} does not speak as the canonical page"))
        channel = account.get("channel")
        policy_channel = account.get("policy_channel")
        if channel != policy_channel:
            findings.append(_finding("ACCOUNT_CHANNEL", f"account {account_id} channel/policy_channel mismatch"))
        channel_policy = channels_policy.get(policy_channel) if isinstance(policy_channel, str) else None
        if not isinstance(channel_policy, dict):
            findings.append(_finding("CHANNEL_POLICY", f"policy is missing channel {policy_channel!r}"))
            continue
        if account_id == TIKTOK_ACCOUNT:
            expected_handle = str(channel_policy.get("account_handle", "")).strip().casefold()
            actual_handle = str(account.get("account_handle", "")).strip().casefold()
            if not expected_handle or not actual_handle or expected_handle.lstrip("@") != actual_handle.lstrip("@"):
                findings.append(_finding("TIKTOK_TARGET", "TikTok account handle does not match policy"))
            if channel_policy.get("profile_url") != account.get("profile_url"):
                findings.append(_finding("TIKTOK_TARGET", "TikTok profile URL does not match policy"))
            if not account.get("target_verified_on"):
                findings.append(_finding("TIKTOK_TARGET", "TikTok target verification date is missing"))
        account_policies[account_id] = channel_policy

    placements = calendar.get("placements")
    if not isinstance(placements, list):
        placements = []
        findings.append(_finding("PLACEMENTS", "placements must be a list"))
    compliance = content_compliance_gate.evaluate_calendar_compliance_document(
        calendar, repo=repo
    )
    for item in compliance.get("findings", []):
        placement_ids = item.get("placement_ids") if isinstance(item, dict) else None
        issues = item.get("issues") if isinstance(item, dict) else None
        message = "; ".join(str(issue) for issue in (issues or ["unknown compliance failure"]))
        if placement_ids:
            message += " [placements: %s]" % ", ".join(str(value) for value in placement_ids)
        findings.append(_publication_finding("CONTENT_COMPLIANCE", message))
    for item in compliance.get("warnings", []):
        placement_ids = item.get("placement_ids") if isinstance(item, dict) else None
        issues = item.get("issues") if isinstance(item, dict) else None
        message = "; ".join(str(issue) for issue in (issues or ["unknown compliance warning"]))
        if placement_ids:
            message += " [placements: %s]" % ", ".join(str(value) for value in placement_ids)
        findings.append(_report_finding("CONTENT_COMPLIANCE_WARNING", message))
    cta_catalog = calendar.get("cta_catalog") if isinstance(calendar.get("cta_catalog"), dict) else {}
    seen_placement_ids: set[str] = set()
    seen_content_accounts: set[tuple[str, str]] = set()
    by_rate_day: dict[tuple[str, date], list[tuple[str, str]]] = defaultdict(list)
    rate_events: dict[str, list[tuple[datetime, str, str]]] = defaultdict(list)
    calendar_days_by_rate: dict[str, set[date]] = defaultdict(set)
    placements_by_content: dict[str, set[str]] = defaultdict(set)
    source_tables: dict[str, dict[str, dict[str, str]]] = {}
    source_weekly_packs: dict[str, dict[str, dict]] = {}
    copy_by_placement: dict[str, str] = {}
    media_cache: dict[tuple[str, str], dict] = {}
    source_cache: dict[str, object] = {}
    unregistered_source_reported: set[str] = set()
    source_reference_time: dict[str, datetime] = {}
    for item in placements:
        if not isinstance(item, dict):
            continue
        item_content_id = str(item.get("content_id") or "").strip()
        item_day = _parse_iso_date(item.get("date"))
        item_clock = _parse_clock(item.get("time"))
        if not item_content_id or item_day is None or item_clock is None:
            continue
        item_slot = datetime.combine(item_day, item_clock, tzinfo=BANGKOK)
        previous = source_reference_time.get(item_content_id)
        if previous is None or item_slot > previous:
            source_reference_time[item_content_id] = item_slot
    media_fn = media_evaluator or _default_media_result

    for index, placement in enumerate(placements):
        if not isinstance(placement, dict):
            findings.append(_finding("PLACEMENT_SHAPE", f"placement index {index} is malformed"))
            continue
        placement_id = str(placement.get("placement_id", "")).strip()
        content_id = str(placement.get("content_id", "")).strip()
        account_id = str(placement.get("account", "")).strip()
        if not placement_id:
            findings.append(_finding("PLACEMENT_ID", f"placement index {index} has no placement_id"))
            placement_id = f"index-{index}"
        elif placement_id in seen_placement_ids:
            findings.append(_finding("PLACEMENT_DUPLICATE", "placement_id is duplicated", placement_id))
        seen_placement_ids.add(placement_id)
        if not content_id or not account_id:
            findings.append(_finding("PLACEMENT_IDENTITY", "content_id/account is missing", placement_id))
        elif placement_id != f"{content_id}__{account_id}":
            findings.append(_finding(
                "PLACEMENT_NAMESPACE",
                "placement_id must exactly equal <content_id>__<account>",
                placement_id,
            ))
        if account_id not in accounts:
            findings.append(_finding("PLACEMENT_ACCOUNT", f"unknown account {account_id!r}", placement_id))
        placements_by_content[content_id].add(account_id)

        placement_status = placement.get("status")
        if placement_status != BLOCKED_STATUS:
            findings.append(_finding("STATUS_NOT_BLOCKED", f"every placement must be {BLOCKED_STATUS}", placement_id))
        slot_state = placement.get("slot_state")
        if slot_state not in {BLOCKED_SLOT, RESERVED_SLOT}:
            findings.append(_finding("SLOT_STATE", "slot_state must be BLOCKED or RESERVED_BLOCKED", placement_id))
        is_reserved_content = (
            content_id in (set(HELD_IDS) | tiktok_ids)
            or (account_id == TIKTOK_ACCOUNT and content_id in tiktok_week_ids)
        )
        if is_reserved_content and slot_state != RESERVED_SLOT:
            findings.append(_finding("HELD_NOT_RESERVED", "held content must remain RESERVED_BLOCKED", placement_id))
        if not is_reserved_content and slot_state != BLOCKED_SLOT:
            findings.append(_finding("CORE_RESERVED", "core library content must use BLOCKED, not a reservation", placement_id))

        day = _parse_iso_date(placement.get("date"))
        clock = _parse_clock(placement.get("time"))
        slot_at: datetime | None = None
        if day is None or clock is None:
            findings.append(_finding("PLACEMENT_DATETIME", "placement date/time is invalid", placement_id))
        else:
            slot_at = datetime.combine(day, clock, tzinfo=BANGKOK)
            if not_before and day < not_before:
                findings.append(_finding("BACKFILL", "placement predates not_before", placement_id))
            if plan_as_of and day <= plan_as_of:
                findings.append(_finding("BACKFILL", "placement is not after plan_as_of", placement_id))
            if day < current_day:
                finding = (
                    _report_finding
                    if placement_status == BLOCKED_STATUS
                    else _finding
                )
                findings.append(finding(
                    "PAST_PLACEMENT",
                    "placement is stale/past in Asia/Bangkok; historical blocked row retained",
                    placement_id,
                ))
            if slot_at < evaluation_now_bangkok:
                finding = (
                    _report_finding
                    if placement_status == BLOCKED_STATUS
                    else _finding
                )
                findings.append(finding(
                    "STALE_SLOT",
                    f"missed slot {slot_at.isoformat()} remains {BLOCKED_STATUS}; do not backfill or promote",
                    placement_id,
                ))
            rate_identity = _account_rate_identity(accounts, account_id)
            if rate_identity is None:
                findings.append(_finding(
                    "ACCOUNT_RATE_IDENTITY",
                    "placement account has no policy-backed quota/gap identity",
                    placement_id,
                ))
            else:
                by_rate_day[(rate_identity, day)].append((placement_id, "calendar"))
                rate_events[rate_identity].append((slot_at, placement_id, "calendar"))
                calendar_days_by_rate[rate_identity].add(day)

        duplicate_key = (account_id, content_id)
        if content_id and account_id:
            if duplicate_key in seen_content_accounts:
                findings.append(_finding("PERMANENT_CALENDAR_DUPLICATE", "content_id repeats on the same account", placement_id))
            seen_content_accounts.add(duplicate_key)

        blockers = placement.get("blockers") if isinstance(placement.get("blockers"), list) else []
        blockers = [str(value) for value in blockers]
        if not blockers:
            findings.append(_finding("BLOCKERS_MISSING", "blocked placement must declare blockers", placement_id))
        gates = placement.get("gates") if isinstance(placement.get("gates"), dict) else {}
        required_gates = {"publication_authority", "source_review", "media", "dedup", "page_identity"}
        if not required_gates.issubset(gates):
            findings.append(_finding("GATES_MISSING", "placement gate record is incomplete", placement_id))
        if gates.get("dedup") != "REQUIRED":
            findings.append(_finding("DEDUP_NOT_REQUIRED", "permanent dedup must remain REQUIRED", placement_id))
        if gates.get("page_identity") != "PASS":
            findings.append(_finding("PAGE_IDENTITY_GATE", "page identity gate must be recorded PASS", placement_id))
        if account_id == TIKTOK_ACCOUNT:
            if not TIKTOK_REQUIRED_BLOCKERS.issubset(blockers):
                findings.append(_finding("TIKTOK_BLOCKERS", "TikTok reservation is missing a mandatory reactivation blocker", placement_id))
            for gate_name in ("owner_confirmation", "live_history_dedup", "landing_parity"):
                if gates.get(gate_name) != "BLOCKED":
                    findings.append(_finding("TIKTOK_GATE", f"TikTok {gate_name} must remain BLOCKED", placement_id))
            if placement.get("link_policy") != TIKTOK_LINK_POLICY:
                findings.append(_finding("TIKTOK_LINK_POLICY", "TikTok no-link policy is missing or changed", placement_id))
            if placement.get("cta_id") != "tiktok-no-link":
                findings.append(_finding("TIKTOK_CTA", "TikTok reactivation must use the disabled no-link CTA", placement_id))

        channel_policy = account_policies.get(account_id)
        if isinstance(channel_policy, dict):
            state = str(channel_policy.get("state", "")).strip().casefold()
            if state not in {"active", "manual", "testing", TIKTOK_STATE, "paused", "retired"}:
                findings.append(_finding("CHANNEL_STATE", "channel state is missing or unknown", placement_id))
            if state == "retired":
                findings.append(_finding("RETIRED_PLACEMENT", "retired channels may not have placements", placement_id))
            if state == "paused" and (slot_state != RESERVED_SLOT or "channel_review" not in blockers):
                findings.append(_finding("PAUSED_ACTIVE_SLOT", "paused channel may only have review-gated reservations", placement_id))
            if state == TIKTOK_STATE:
                if account_id != TIKTOK_ACCOUNT:
                    findings.append(_finding("TESTING_BLOCKED_CHANNEL", "testing_blocked is reserved for the TikTok plan", placement_id))
                if slot_state != RESERVED_SLOT or "channel_review" not in blockers:
                    findings.append(_finding("TESTING_BLOCKED_SLOT", "testing_blocked TikTok may only hold review-gated reservations", placement_id))
                if any(channel_policy.get(field) is not False for field in ("auto", "automation_capable", "publication_authorized")):
                    findings.append(_finding("TESTING_BLOCKED_CAPABILITY", "testing_blocked TikTok must keep auto, automation, and publication false", placement_id))
            authorized = channel_policy.get("publication_authorized") is True
            if not authorized:
                if gates.get("publication_authority") != "BLOCKED" or "publication_authority" not in blockers:
                    findings.append(_finding("AUTHORITY_FAIL_OPEN", "unauthorized channel is not explicitly blocked", placement_id))
            elif gates.get("publication_authority") == "BLOCKED" and "publication_authority" in blockers:
                findings.append(_finding("AUTHORITY_STATE_CHANGED", "channel authorization changed; calendar needs owner review", placement_id))

        cta_id = placement.get("cta_id")
        cta = cta_catalog.get(cta_id) if isinstance(cta_id, str) else None
        if not isinstance(cta, dict):
            findings.append(_finding("CTA", "placement CTA is missing from cta_catalog", placement_id))
        else:
            landing = cta.get("landing")
            if cta.get("kind") == "no_link":
                if landing is not None or cta.get("body_url_allowed") is not False or cta.get("enabled") is not False:
                    findings.append(_finding("CTA_NO_LINK", "no-link CTA must stay disabled with no landing", placement_id))
            elif not isinstance(landing, str) or not (landing.startswith("/") or landing.startswith("https://")):
                findings.append(_finding("CTA_LANDING", "CTA landing must be an internal path or HTTPS URL", placement_id))

        source = placement.get("source") if isinstance(placement.get("source"), dict) else {}
        source_path = _safe_repo_path(repo, source.get("file"))
        source_row_id = source.get("row_id")
        source_field = str(source.get("field", ""))
        if account_id == TIKTOK_ACCOUNT:
            expected_tiktok_field = (
                TIKTOK_WEEK_SOURCE_FIELD
                if content_id in tiktok_week_ids
                else "caption_no_link"
            )
            if source_field != expected_tiktok_field:
                findings.append(_finding(
                    "TIKTOK_SOURCE_FIELD",
                    f"TikTok placement must use {expected_tiktok_field}",
                    placement_id,
                ))
        if source_path is None or not source_path.is_file():
            findings.append(_finding("SOURCE_FILE", "source file is missing or outside the repository", placement_id))
        elif source_path.name == WEEKLY_REPLACEMENT_PACK:
            key = source_path.relative_to(repo).as_posix()
            if key not in source_weekly_packs:
                try:
                    source_weekly_packs[key] = _weekly_pack_rows(source_path)
                except (OSError, UnicodeError, ValueError) as exc:
                    source_weekly_packs[key] = {}
                    findings.append(_finding("SOURCE_PACK", str(exc), placement_id))
            row = source_weekly_packs[key].get(str(source_row_id))
            if not isinstance(row, dict) or source_row_id != content_id:
                findings.append(_finding("SOURCE_ROW", "source row does not match content_id", placement_id))
            elif not source_field or not isinstance(row.get(source_field), str) or not row.get(source_field).strip():
                findings.append(_finding("SOURCE_FIELD", "source field is missing", placement_id))
            else:
                copy_by_placement[placement_id] = str(row[source_field])
                quote_field = QUOTE_PACK_CAPTION_FIELDS.get(placement_id)
                if account_id == TIKTOK_ACCOUNT and content_id in tiktok_week_ids:
                    if (
                        source_field != TIKTOK_WEEK_SOURCE_FIELD
                        or row.get("source_ids") != []
                        or row.get("source_review") not in {
                            "NOT_REQUIRED", "NOT_REQUIRED_IF_TEXT_REMAINS_EXACT",
                        }
                        or row.get("date") != placement.get("date")
                        or placement.get("topic") != row.get("theme")
                    ):
                        findings.append(_finding(
                            "TIKTOK_WEEK_SOURCE_SCOPE",
                            "TikTok week replacement must use its exact no-link pack copy and dated theme",
                            placement_id,
                        ))
                elif quote_field is not None:
                    if (
                        source_field != quote_field
                        or row.get("source_ids") != []
                        or row.get("source_review") != "NOT_REQUIRED"
                        or placement.get("topic") != row.get("quote_text")
                    ):
                        findings.append(_finding(
                            "QUOTE_PACK_SOURCE_SCOPE",
                            "quote placement must use its exact channel field and quote text from the bound weekly pack",
                            placement_id,
                        ))
                else:
                    if row.get("date") != placement.get("date"):
                        findings.append(_finding(
                            "REPLACEMENT_SLOT_DRIFT",
                            "weekly replacement placement date differs from its candidate row",
                            placement_id,
                        ))
                    if (
                        row.get("source_ids") != []
                        or row.get("source_review")
                        != "NOT_REQUIRED_IF_TEXT_REMAINS_EXACT"
                    ):
                        findings.append(_finding(
                            "REPLACEMENT_SOURCE_SCOPE",
                            "weekly replacement must remain exact-copy evergreen with no source IDs",
                            placement_id,
                        ))
        elif source_path.suffix.casefold() == ".md" and source_path.name != "BATCH4-PILOT_20260816.md":
            key = source_path.relative_to(repo).as_posix()
            if key not in source_tables:
                try:
                    source_tables[key] = _table_rows(source_path)
                except (OSError, UnicodeError, ValueError) as exc:
                    source_tables[key] = {}
                    findings.append(_finding("SOURCE_TABLE", str(exc), placement_id))
            row = source_tables[key].get(str(source_row_id))
            if not isinstance(row, dict) or source_row_id != content_id:
                findings.append(_finding("SOURCE_ROW", "source row does not match content_id", placement_id))
            elif not source_field or not row.get(source_field):
                findings.append(_finding("SOURCE_FIELD", "source field is missing", placement_id))
            else:
                copy_by_placement[placement_id] = _copy_text(row, source_field)
                if account_id == TIKTOK_ACCOUNT:
                    if row.get("date") != placement.get("date") or row.get("time") != placement.get("time"):
                        findings.append(_finding("TIKTOK_SLOT_DRIFT", "TikTok placement date/time differs from the runway row", placement_id))
                    if row.get("link_policy") != TIKTOK_LINK_POLICY:
                        findings.append(_finding("TIKTOK_LINK_POLICY", "TikTok runway row no-link policy changed", placement_id))
                    phase = row.get("phase")
                    if phase == "candidate_existing":
                        if row.get("asset") != placement.get("media"):
                            findings.append(_finding("TIKTOK_ASSET", "existing TikTok candidate asset differs from its runway row", placement_id))
                        declared_receipt = row.get("qa_receipt")
                        if declared_receipt == "MISSING_PER_PIECE_RECEIPT":
                            if placement.get("media_receipt") is not None or gates.get("media") != "MISSING" or "missing_media" not in blockers:
                                findings.append(_finding("TIKTOK_RECEIPT", "missing per-piece receipt must remain explicitly blocked", placement_id))
                        elif declared_receipt == "BLOCKED_SEMANTIC_PARITY":
                            if (
                                placement.get("media_receipt") is not None
                                or gates.get("media") != "BLOCKED"
                                or "semantic_parity_failed" not in blockers
                            ):
                                findings.append(_finding("TIKTOK_RECEIPT", "semantic-failed TikTok media must remain explicitly blocked", placement_id))
                        elif declared_receipt != placement.get("media_receipt"):
                            findings.append(_finding("TIKTOK_RECEIPT", "TikTok receipt differs from its runway row", placement_id))
                    elif phase == "creative_brief":
                        if row.get("asset") != "TBD" or placement.get("media") is not None or not row.get("creative_brief"):
                            findings.append(_finding("TIKTOK_BRIEF", "new TikTok brief must remain unproduced with a concrete brief", placement_id))
                    else:
                        findings.append(_finding("TIKTOK_PHASE", "TikTok runway row phase is invalid", placement_id))
        elif content_id == "b4-p01" and source_path is not None and source_path.is_file():
            if source_row_id != content_id:
                findings.append(_finding("SOURCE_SECTION", "b4 source section is missing or mismatched", placement_id))
            else:
                try:
                    copy_by_placement[placement_id] = _section(
                        source_path, source_field, content_id
                    )
                except ValueError as exc:
                    findings.append(_finding("SOURCE_SECTION", str(exc), placement_id))

        for pattern in personal_patterns:
            if pattern.search(copy_by_placement.get(placement_id, "")):
                findings.append(_finding("PERSONAL_PUBLIC_VOICE", "source copy contains a forbidden personal claim", placement_id))
                break
        folded_copy = copy_by_placement.get(placement_id, "").casefold()
        if any(re.search(r"(?<![a-z])" + re.escape(speaker) + r"(?![a-z])", folded_copy) for speaker in forbidden_speakers):
            findings.append(_finding("AGENT_PUBLIC_SPEAKER", "source copy exposes an internal agent as speaker", placement_id))
        if account_id == TIKTOK_ACCOUNT:
            forbidden_link_markers = (
                r"https?://", r"www\.", r"ngernduangold\.com", r"/links\b",
                r"utm_", r"ลิงก์", r"link\s+in\s+bio",
            )
            if any(re.search(pattern, folded_copy, re.I) for pattern in forbidden_link_markers):
                findings.append(_finding("TIKTOK_BODY_LINK", "TikTok testing caption must contain no link or link direction", placement_id))

        source_gate = gates.get("source_review")
        if (
            account_id == TIKTOK_ACCOUNT
            and (source_gate != "BLOCKED" or "official_source_review" not in blockers)
        ):
            findings.append(_finding(
                "TIKTOK_SOURCE",
                "TikTok reactivation source review must remain fail-closed BLOCKED",
                placement_id,
            ))
        # Source applicability belongs to the factual content namespace, never
        # to the placement-controlled gate value. Validate the carried claim on
        # every platform even though the live decision is cached per content_id.
        source_required = (
            content_source_gate.repo_content_source_contract(content_id, repo)[0]
            is not None
        )
        raw_declared_ids = placement.get("source_ids")
        declared_ids: set[str] = set()
        declared_ids_valid = False
        if source_required:
            if (
                not isinstance(raw_declared_ids, list)
                or not raw_declared_ids
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in raw_declared_ids
                )
            ):
                findings.append(_finding(
                    "SOURCE_IDS_SHAPE",
                    "source-required placement must carry a non-empty list of source ID strings",
                    placement_id,
                ))
            else:
                normalized_declared_ids = [item.strip() for item in raw_declared_ids]
                if len(normalized_declared_ids) != len(set(normalized_declared_ids)):
                    findings.append(_finding(
                        "SOURCE_IDS_DUPLICATE",
                        "source-required placement source_ids must be unique",
                        placement_id,
                    ))
                else:
                    declared_ids_valid = True
                    declared_ids = set(normalized_declared_ids)
        if source_required:
            source_key = content_id
            if source_key not in source_cache:
                source_now = source_reference_time.get(content_id)
                if source_now is None:
                    source_cache[source_key] = {
                        "allowed": False,
                        "source_ids": [],
                        "failures": ["invalid placement slot"],
                    }
                else:
                    try:
                        if source_evaluator is None:
                            source_cache[source_key] = _default_source_result(
                                content_id,
                                repo,
                                source_now.astimezone(timezone.utc),
                            )
                        else:
                            source_cache[source_key] = source_evaluator(
                                content_id, repo, source_now.astimezone(timezone.utc)
                            )
                    except Exception as exc:
                        source_cache[source_key] = {
                            "allowed": False,
                            "source_ids": [],
                            "failures": [type(exc).__name__],
                        }
            live_source = source_cache[source_key]
            expected_gate = "PASS" if _source_allowed(live_source) else "BLOCKED"
            if source_gate != expected_gate:
                findings.append(_finding("SOURCE_GATE_DRIFT", f"source gate must be {expected_gate}", placement_id))
            live_ids = _source_ids(live_source)
            if (
                not live_ids
                and source_evaluator is None
                and content_id not in unregistered_source_reported
            ):
                unregistered_source_reported.add(content_id)
                findings.append(_publication_finding(
                    "SOURCE_UNREGISTERED",
                    "; ".join(_source_failures(live_source)) or
                    "factual content has no source-registry mapping",
                ))
            elif declared_ids_valid and declared_ids != live_ids:
                findings.append(_finding(
                    "SOURCE_IDS",
                    "declared source_ids must exactly equal the content-scoped registry mapping",
                    placement_id,
                ))
            if expected_gate == "BLOCKED" and "official_source_review" not in blockers:
                findings.append(_finding("SOURCE_FAIL_OPEN", "blocked official source is not a placement blocker", placement_id))
        elif (
            account_id == TIKTOK_ACCOUNT
            and content_id in tiktok_week_ids
            and source_gate == "BLOCKED"
            and "official_source_review" in blockers
        ):
            # The exact evergreen replacement has no factual source namespace,
            # but TikTok's stricter launch lane intentionally keeps source review
            # blocked until the owner clears the per-piece publication decision.
            pass
        elif source_gate not in {"NOT_REQUIRED", "MISSING"}:
            findings.append(_finding("SOURCE_GATE", "non-knowledge reservation must record NOT_REQUIRED", placement_id))
        elif placement.get("source_ids") not in (None, []):
            findings.append(_finding(
                "SOURCE_IDS_ORPHAN",
                "non-source placement must not carry source_ids",
                placement_id,
            ))

        media = placement.get("media")
        receipt = placement.get("media_receipt")
        media_gate = gates.get("media")
        media_format = placement.get("format")
        if media_format == "text":
            if (media is not None or receipt is not None
                    or placement.get("media_content_id") is not None
                    or placement.get("media_qa_report") is not None
                    or media_gate != "NOT_REQUIRED"):
                findings.append(_finding("TEXT_MEDIA", "text placement must not claim media", placement_id))
        elif media and not receipt and "semantic_parity_failed" in blockers:
            if media_gate != "BLOCKED":
                findings.append(_finding("MEDIA_FAIL_OPEN", "semantic-failed media must remain BLOCKED", placement_id))
            report_error = _blocked_media_report_error(placement, repo)
            if report_error:
                findings.append(_finding("BLOCKED_MEDIA_QA_REPORT", report_error, placement_id))
        elif bool(media) != bool(receipt):
            findings.append(_finding(
                "MEDIA_ORPHAN",
                "media and its hash-bound receipt must be present together",
                placement_id,
            ))
            if media_gate != "MISSING" or "missing_media" not in blockers:
                findings.append(_finding("MEDIA_FAIL_OPEN", "missing media/receipt is not explicitly blocked", placement_id))
        elif not media or not receipt:
            if placement.get("media_content_id") is not None:
                findings.append(_finding(
                    "MEDIA_CONTENT_ID_ORPHAN",
                    "media content identity is present without a media asset",
                    placement_id,
                ))
            if placement.get("media_qa_report") is not None:
                findings.append(_finding(
                    "MEDIA_QA_ORPHAN",
                    "media QA report is present without a media asset",
                    placement_id,
                ))
            if media_gate != "MISSING" or "missing_media" not in blockers:
                findings.append(_finding("MEDIA_FAIL_OPEN", "missing media/receipt is not explicitly blocked", placement_id))
        else:
            cache_key = (str(media), str(receipt))
            if cache_key not in media_cache:
                try:
                    media_cache[cache_key] = media_fn(str(media), str(receipt), repo)
                except Exception as exc:
                    media_cache[cache_key] = {"verdict": "FAIL", "findings": [type(exc).__name__]}
            live_media = media_cache[cache_key]
            live_media_type = live_media.get("media_type")
            if media_format not in {"image", "video"}:
                findings.append(_finding(
                    "MEDIA_FORMAT",
                    "non-text media placement format must be image or video",
                    placement_id,
                ))
            elif live_media_type not in {"image", "video"}:
                findings.append(_finding(
                    "MEDIA_TYPE_UNKNOWN",
                    "media receipt did not prove an image or video media_type",
                    placement_id,
                ))
            elif media_format != live_media_type:
                findings.append(_finding(
                    "MEDIA_TYPE_MISMATCH",
                    f"placement format {media_format} does not match receipt media_type {live_media_type}",
                    placement_id,
                ))
            expected_media = "PASS" if live_media.get("verdict") == "PASS" else "BLOCKED"
            live_media_findings = live_media.get("findings")
            declared_human_audio_blocked = HUMAN_LISTENING_BLOCKER in blockers
            human_audio_blocked = (
                live_media.get("media_type") == "video"
                and isinstance(live_media_findings, list)
                and bool(live_media_findings)
                and all(
                    isinstance(item, str) and item.startswith("human audio")
                    for item in live_media_findings
                )
            )
            if declared_human_audio_blocked:
                if media_gate != "BLOCKED":
                    findings.append(_finding(
                        "MEDIA_FAIL_OPEN",
                        "video awaiting exact human listening must remain media BLOCKED",
                        placement_id,
                    ))
                if human_audio_blocked:
                    findings.append(_publication_finding(
                        "MEDIA_HUMAN_AUDIO_REVIEW_REQUIRED",
                        "final video media gate is blocked until exact hash-bound human listening passes",
                        placement_id,
                    ))
                elif live_media.get("verdict") != "PASS":
                    findings.append(_publication_finding(
                        "MEDIA_BLOCKED",
                        "video media receipt has failures beyond the declared human-listening limitation",
                        placement_id,
                    ))
            elif human_audio_blocked:
                findings.append(_publication_finding(
                    "MEDIA_HUMAN_AUDIO_REVIEW_REQUIRED",
                    "final video media gate is blocked until exact hash-bound human listening passes",
                    placement_id,
                ))
            elif media_gate != expected_media:
                findings.append(_finding("MEDIA_GATE_DRIFT", f"media gate must be {expected_media}", placement_id))
            receipt_path = _safe_repo_path(repo, receipt)
            try:
                receipt_payload = _load_object(receipt_path, "media receipt") if receipt_path else {}
                novelty = receipt_payload.get("novelty_review") if isinstance(receipt_payload.get("novelty_review"), dict) else {}
                source_binding = (
                    receipt_payload.get("source_binding")
                    if isinstance(receipt_payload.get("source_binding"), dict)
                    else {}
                )
                declared_media_content_id = placement.get("media_content_id")
                expected_media_content_id = (
                    declared_media_content_id
                    if isinstance(declared_media_content_id, str)
                    and declared_media_content_id.strip()
                    else content_id
                )
                if novelty.get("content_id") != expected_media_content_id:
                    findings.append(_finding("MEDIA_CONTENT_ID", "media receipt is bound to another content_id", placement_id))
                if source_binding and source_binding.get("candidate_id") != content_id:
                    findings.append(_finding(
                        "MEDIA_SOURCE_CONTENT_ID",
                        "media receipt source binding is not bound to the placement content_id",
                        placement_id,
                    ))
                bound_source_raw = (
                    source_binding.get("source_file")
                    if source_binding.get("source_file") is not None
                    else source_binding.get("weekly_pack")
                )
                if bound_source_raw is not None:
                    bound_source_path = _safe_repo_path(repo, bound_source_raw)
                    if (
                        source_path is None
                        or bound_source_path is None
                        or bound_source_path != source_path
                    ):
                        findings.append(_finding(
                            "MEDIA_SOURCE_FILE",
                            "media receipt source path differs from the placement source",
                            placement_id,
                        ))
                if source_binding.get("source_file_sha256") is not None:
                    if (
                        source_path is None
                        or not source_path.is_file()
                        or str(source_binding.get("source_file_sha256") or "").upper()
                        != _sha256(source_path)
                    ):
                        findings.append(_finding(
                            "MEDIA_SOURCE_HASH",
                            "media receipt source SHA-256 differs from the current source",
                            placement_id,
                        ))
                if (
                    source_binding.get("source_row_id") is not None
                    and source_binding.get("source_row_id") != source_row_id
                ):
                    findings.append(_finding(
                        "MEDIA_SOURCE_ROW",
                        "media receipt source row differs from the placement source",
                        placement_id,
                    ))
                if (
                    source_binding.get("source_field") is not None
                    and source_binding.get("source_field") != source_field
                ):
                    findings.append(_finding(
                        "MEDIA_SOURCE_FIELD",
                        "media receipt source field differs from the placement source",
                        placement_id,
                    ))
                if source_binding.get("source_value_sha256") is not None:
                    source_copy = copy_by_placement.get(placement_id)
                    actual_source_value_hash = (
                        hashlib.sha256(source_copy.encode("utf-8")).hexdigest().upper()
                        if isinstance(source_copy, str)
                        else None
                    )
                    if (
                        actual_source_value_hash is None
                        or str(source_binding.get("source_value_sha256") or "").upper()
                        != actual_source_value_hash
                    ):
                        findings.append(_finding(
                            "MEDIA_SOURCE_VALUE",
                            "media receipt source-value SHA-256 differs from the exact placement copy",
                            placement_id,
                        ))
            except ValueError as exc:
                findings.append(_finding("MEDIA_RECEIPT", str(exc), placement_id))
            for error in _media_binding_receipt_errors(
                placement,
                repo,
                calendar_file_sha256=calendar_file_sha256,
            ):
                findings.append(_finding(
                    "MEDIA_BINDING_RECEIPT",
                    error,
                    placement_id,
                ))

    if ledger_rows is None:
        try:
            dedup_allowed, dedup_reason, dedup_metric = post_ledger.permanent_dedup_gate(
                repo / LEDGER_PATH
            )
        except Exception as exc:
            dedup_allowed = False
            dedup_reason = "permanent dedup gate failed: %s" % type(exc).__name__
            dedup_metric = {}
        if not dedup_allowed:
            # Preserve the global metric for audit visibility, but never use an
            # unrelated account's incomplete legacy row as an action gate.  The
            # actual publication blockers are derived per account identity below.
            findings.append(_report_finding(
                "PERMANENT_DEDUP_GLOBAL_AUDIT",
                "%s; coverage=%s%% (%s/%s complete)" % (
                    dedup_reason,
                    dedup_metric.get("coverage_percent", "unknown"),
                    dedup_metric.get("complete_rows", "unknown"),
                    dedup_metric.get("identity_rows", "unknown"),
                ),
            ))

        accounts_by_dedup_channel: dict[str, set[str]] = defaultdict(set)
        for placement in placements:
            if not isinstance(placement, dict):
                continue
            account_id = str(placement.get("account") or "").strip()
            channel = _account_dedup_identity(accounts, account_id)
            if channel:
                accounts_by_dedup_channel[channel].add(account_id)
        for channel, affected_accounts in sorted(accounts_by_dedup_channel.items()):
            try:
                channel_allowed, channel_reason, channel_metric = (
                    post_ledger.permanent_dedup_channel_gate(
                        channel, repo / LEDGER_PATH
                    )
                )
            except Exception as exc:
                channel_allowed = False
                channel_reason = (
                    "permanent dedup channel gate failed: %s" % type(exc).__name__
                )
                channel_metric = {}
            if not channel_allowed:
                findings.append(_publication_finding(
                    "PERMANENT_DEDUP_INCOMPLETE",
                    "channel %s is blocked: %s; coverage=%s%% (%s/%s complete); "
                    "affected accounts=%s" % (
                        channel,
                        channel_reason,
                        channel_metric.get("coverage_percent", "unknown"),
                        channel_metric.get("complete_rows", "unknown"),
                        channel_metric.get("identity_rows", "unknown"),
                        ",".join(sorted(affected_accounts)),
                    ),
                ))
        ledger_rows, ledger_failures = _ledger_rows(repo / LEDGER_PATH)
        findings.extend(_finding("LEDGER", failure) for failure in ledger_failures)

    # Resolve append-only status transitions before quota accounting.  A status
    # row shared by multiple bases is ambiguous and is never allowed to cancel
    # all of them; the permanent-ledger reader also rejects this shape.
    latest_ledger_status: dict[str, tuple[int, str]] = {}
    base_count_by_key: dict[str, int] = defaultdict(int)
    base_line_by_key: dict[str, int] = {}
    for row_number, row in enumerate(ledger_rows or [], 1):
        if not isinstance(row, dict):
            continue
        dedup_key = str(row.get("dedup_key") or "").strip()
        if str(row.get("type") or "").strip().casefold() == "status":
            if dedup_key:
                latest_ledger_status[dedup_key] = (
                    row_number, str(row.get("status") or "").strip().casefold()
                )
        elif dedup_key:
            base_count_by_key[dedup_key] += 1
            base_line_by_key.setdefault(dedup_key, row_number)

    ledger_unknown_times: list[tuple[str, date | None, str]] = []
    for row_number, row in enumerate(ledger_rows or [], 1):
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type", "")).strip().casefold()
        if kind not in SUCCESS_TYPES:
            continue
        account_id = _ledger_account(row.get("channel"))
        content_id = _ledger_content_id(row)
        dedup_key = str(row.get("dedup_key") or "").strip()
        direct_status = str(row.get("status") or "").strip().casefold()
        transition = latest_ledger_status.get(dedup_key)
        if (
            dedup_key
            and base_count_by_key.get(dedup_key) == 1
            and (
                transition is None
                or transition[0] > base_line_by_key.get(dedup_key, row_number)
            )
        ):
            effective_status = transition[1] if transition is not None else direct_status
        else:
            effective_status = direct_status
            if dedup_key and base_count_by_key.get(dedup_key, 0) > 1:
                findings.append(_publication_finding(
                    "LEDGER_RATE_STATUS_AMBIGUOUS",
                    "one dedup_key belongs to multiple ledger base rows; shared status was not applied",
                ))
            elif transition is not None:
                findings.append(_publication_finding(
                    "LEDGER_RATE_STATUS_AMBIGUOUS",
                    "ledger status precedes its base row and was not applied",
                ))
        if effective_status in NON_SUCCESS_STATUSES:
            continue
        if effective_status and effective_status not in SUCCESS_STATUSES:
            findings.append(_publication_finding(
                "LEDGER_RATE_STATUS_UNKNOWN",
                f"ledger row {row_number} has an unrecognized publication status",
            ))

        if account_id and content_id and (account_id, content_id) in seen_content_accounts:
            findings.append(_finding("PERMANENT_LEDGER_DUPLICATE", f"{content_id} already succeeded on {account_id}"))

        if kind not in RATE_LIMIT_LEDGER_TYPES or account_id not in accounts:
            continue
        rate_identity = _account_rate_identity(accounts, account_id)
        if rate_identity is None:
            findings.append(_publication_finding(
                "LEDGER_RATE_IDENTITY_UNKNOWN",
                f"ledger row {row_number} has no policy-backed quota/gap identity",
            ))
            continue
        exact_time, quota_day = _ledger_rate_time(row)
        label = f"ledger-row-{row_number}"
        if quota_day is None:
            findings.append(_publication_finding(
                "LEDGER_RATE_TIMESTAMP_UNKNOWN",
                f"ledger row {row_number} has no trustworthy publication date/time",
            ))
            continue
        by_rate_day[(rate_identity, quota_day)].append((label, "ledger"))
        if exact_time is not None:
            rate_events[rate_identity].append((exact_time, label, "ledger"))
        else:
            ledger_unknown_times.append((rate_identity, quota_day, label))

    limits = policy.get("limits") if isinstance(policy.get("limits"), dict) else {}
    posts_per_day = limits.get("posts_per_day") if isinstance(limits.get("posts_per_day"), dict) else {}
    default_cap = posts_per_day.get("default")
    min_gap_hours = limits.get("min_gap_hours")
    if isinstance(default_cap, bool) or not isinstance(default_cap, int) or default_cap < 1:
        findings.append(_finding("CAP_POLICY", "policy default post cap is missing/invalid"))
        default_cap = 0
    if (
        isinstance(min_gap_hours, bool)
        or not isinstance(min_gap_hours, (int, float))
        or not math.isfinite(float(min_gap_hours))
        or min_gap_hours <= 0
    ):
        findings.append(_finding("GAP_POLICY", "policy minimum gap is missing/invalid"))
        min_gap_hours = 24
    calendar_days = {
        (rate_identity, day)
        for rate_identity, days in calendar_days_by_rate.items()
        for day in days
    }
    for rate_identity, day in sorted(calendar_days):
        slots = by_rate_day[(rate_identity, day)]
        cap = posts_per_day.get(rate_identity, default_cap)
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            findings.append(_finding("CAP_POLICY", f"cap for {rate_identity!r} is invalid"))
            continue
        if len(slots) > cap:
            findings.append(_finding(
                "ACCOUNT_CAP",
                f"policy channel {rate_identity} has {len(slots)}/{cap} placements on {day}",
            ))
    maximum_gap_seconds = float(min_gap_hours) * 3600
    for rate_identity, events in rate_events.items():
        ordered = sorted(events, key=lambda event: (event[0], event[1], event[2]))
        for (left, left_id, left_source), (right, right_id, right_source) in zip(ordered, ordered[1:]):
            if "calendar" not in {left_source, right_source}:
                continue
            if (right - left).total_seconds() < maximum_gap_seconds:
                findings.append(_finding(
                    "ACCOUNT_GAP",
                    f"policy channel {rate_identity} events {left_id}/{right_id} "
                    f"are under {min_gap_hours}h apart",
                ))

    relevant_day_span = max(1, math.ceil(float(min_gap_hours) / 24))
    for rate_identity, quota_day, label in ledger_unknown_times:
        if any(
            abs((quota_day - planned_day).days) <= relevant_day_span
            for planned_day in calendar_days_by_rate.get(rate_identity, set())
        ):
            findings.append(_publication_finding(
                "LEDGER_RATE_TIMESTAMP_UNKNOWN",
                f"{label} has only a date; minimum-gap safety cannot be proven",
            ))

    expected_specs = {
        "knowledge": ("KNOWLEDGE-POSTS-C_20260816-0831.md", {"threads_main", "facebook_main"}),
        "weekly_replacements": (WEEKLY_REPLACEMENT_PACK, {"threads_main", "facebook_main"}),
        "facebook_page2": ("PAGE2-POSTS-B_20260818-0915.md", {"facebook_page2"}),
        "held_quotes": ("QUOTE-CARDS_20260723-0822.md", {"facebook_main", "instagram_main", "pinterest_main"}),
        "held_video": ("BATCH4-PILOT_20260816.md", {"youtube_main", "threads_main", "facebook_main", "instagram_main"}),
        "tiktok_reactivation": (TIKTOK_PLAN_FILENAME, {TIKTOK_ACCOUNT}),
        "tiktok_week_replacements": (WEEKLY_REPLACEMENT_PACK, {TIKTOK_ACCOUNT}),
    }
    allowed_ids: set[str] = set()
    expected_accounts_by_content: dict[str, set[str]] = defaultdict(set)
    for set_name, (filename, required_accounts) in expected_specs.items():
        rows: dict[str, dict[str, str]] = {}
        spec = sets.get(set_name) if isinstance(sets.get(set_name), dict) else None
        if not isinstance(spec, dict):
            findings.append(_finding("CONTENT_SET", f"content set {set_name} is missing"))
            continue
        source_file = _safe_repo_path(repo, spec.get("source_file"))
        if source_file is None or source_file.name != filename or not source_file.is_file():
            findings.append(_finding("CONTENT_SET_SOURCE", f"content set {set_name} source is incorrect"))
            continue
        declared_ids = {str(value) for value in spec.get("ids", [])}
        declared_accounts = {str(value) for value in spec.get("required_accounts", [])}
        if declared_accounts != required_accounts:
            findings.append(_finding("CONTENT_SET_ACCOUNTS", f"content set {set_name} required accounts drifted"))
        if set_name == "weekly_replacements":
            try:
                rows = _weekly_pack_rows(source_file)
            except (OSError, UnicodeError, ValueError) as exc:
                rows = {}
                findings.append(_finding("CONTENT_SET_PARSE", f"{set_name}: {exc}"))
            if (
                not isinstance(spec.get("ids"), list)
                or not declared_ids
                or len(declared_ids) != len(spec.get("ids", []))
                or not declared_ids.issubset(rows)
            ):
                findings.append(_finding(
                    "REPLACEMENT_SELECTION",
                    "weekly replacement selection must be a non-empty unique subset of the pack",
                ))
            library_ids = declared_ids & set(rows)
            if spec.get("selection_mode") != "OWNER_AUTHORIZED_LOCAL_PLAN_REPLACEMENT":
                findings.append(_finding(
                    "REPLACEMENT_SELECTION_MODE",
                    "weekly replacement selection lacks the local owner-authorized plan-change mode",
                ))
            if str(spec.get("pack_sha256") or "").upper() != _sha256(source_file):
                findings.append(_finding(
                    "REPLACEMENT_PACK_HASH",
                    "weekly replacement pack SHA-256 drifted",
                ))
            receipt_path = _safe_repo_path(repo, spec.get("change_receipt"))
            if receipt_path is None or not receipt_path.is_file():
                findings.append(_finding(
                    "REPLACEMENT_CHANGE_RECEIPT",
                    "weekly replacement change receipt is missing",
                ))
            for evidence_name in ("freshness_receipt", "novelty_receipt"):
                evidence = spec.get(evidence_name)
                evidence = evidence if isinstance(evidence, dict) else {}
                evidence_path = _safe_repo_path(repo, evidence.get("path"))
                if evidence_path is None or not evidence_path.is_file():
                    findings.append(_finding(
                        "REPLACEMENT_EVIDENCE",
                        f"weekly replacement {evidence_name} is missing",
                    ))
                elif str(evidence.get("sha256") or "").upper() != _sha256(evidence_path):
                    findings.append(_finding(
                        "REPLACEMENT_EVIDENCE_HASH",
                        f"weekly replacement {evidence_name} SHA-256 drifted",
                    ))
            for content_id in library_ids:
                row = rows.get(content_id, {})
                if (
                    _parse_iso_date(row.get("date")) is None
                    or not_before is None
                    or _parse_iso_date(row.get("date")) < not_before
                ):
                    findings.append(_finding(
                        "REPLACEMENT_DATE",
                        f"weekly replacement {content_id} is not a valid future candidate",
                    ))
            for error in _replacement_evidence_errors(
                calendar,
                spec,
                rows,
                repo,
                calendar_file_sha256=calendar_file_sha256,
            ):
                findings.append(_finding("REPLACEMENT_EVIDENCE", error))
        elif set_name == "tiktok_week_replacements":
            try:
                rows = _weekly_pack_rows(source_file)
            except (OSError, UnicodeError, ValueError) as exc:
                rows = {}
                findings.append(_finding("CONTENT_SET_PARSE", f"{set_name}: {exc}"))
            library_ids = declared_ids & set(rows)
            if (
                not isinstance(spec.get("ids"), list)
                or len(declared_ids) != 7
                or len(declared_ids) != len(spec.get("ids", []))
                or declared_ids != TIKTOK_WEEK_REPLACEMENT_IDS
                or spec.get("selection_mode")
                != "OWNER_AUTHORIZED_LOCAL_PLAN_REPLACEMENT"
                or spec.get("reservation_only") is not True
                or spec.get("link_policy") != TIKTOK_LINK_POLICY
                or str(spec.get("pack_sha256") or "").upper() != _sha256(source_file)
            ):
                findings.append(_finding(
                    "TIKTOK_WEEK_REPLACEMENT_SELECTION",
                    "TikTok week replacement must remain the exact seven-item local-only selection",
                ))
            dated_rows = sorted(
                (_parse_iso_date(rows.get(content_id, {}).get("date")), content_id)
                for content_id in library_ids
            )
            if (
                len(dated_rows) != 7
                or any(day is None for day, _ in dated_rows)
                or any(
                    (right[0] - left[0]).days != 1
                    for left, right in zip(dated_rows, dated_rows[1:])
                )
            ):
                findings.append(_finding(
                    "TIKTOK_WEEK_REPLACEMENT_CADENCE",
                    "TikTok week replacement must cover seven consecutive dated candidates",
                ))
            for error in _tiktok_week_replacement_evidence_errors(
                calendar,
                spec,
                rows,
                repo,
                calendar_file_sha256=calendar_file_sha256,
            ):
                findings.append(_finding("TIKTOK_WEEK_REPLACEMENT_EVIDENCE", error))
        elif set_name == "held_video":
            try:
                source_text = _stable_text(source_file, "held-video editorial package")
            except (OSError, UnicodeError, ValueError) as exc:
                source_text = ""
                findings.append(_finding("CONTENT_SET_PARSE", f"{set_name}: {exc}"))
            library_ids = {"b4-p01"} if "b4-p01" in source_text else set()
        else:
            try:
                rows = _table_rows(source_file)
            except (OSError, UnicodeError, ValueError) as exc:
                rows = {}
                findings.append(_finding("CONTENT_SET_PARSE", f"{set_name}: {exc}"))
            library_ids = {
                content_id for content_id, row in rows.items()
                if (_parse_iso_date(row.get("date")) is not None and
                    not_before is not None and _parse_iso_date(row.get("date")) >= not_before)
            }
        if set_name not in {"weekly_replacements", "tiktok_week_replacements"} and declared_ids != library_ids:
            findings.append(_finding("CONTENT_SET_COVERAGE", f"content set {set_name} does not exactly cover future library rows"))
        for content_id in library_ids:
            expected_accounts_by_content[content_id].update(required_accounts)
        if set_name == "tiktok_reactivation":
            candidate_ids = {content_id for content_id, row in rows.items() if row.get("phase") == "candidate_existing"}
            brief_ids = {content_id for content_id, row in rows.items() if row.get("phase") == "creative_brief"}
            if len(library_ids) != 14 or len(candidate_ids) != 7 or len(brief_ids) != 7:
                findings.append(_finding("TIKTOK_RUNWAY", "TikTok plan must contain exactly 7 existing candidates and 7 new briefs"))
            excluded = spec.get("excluded_ids") if isinstance(spec.get("excluded_ids"), dict) else {}
            if "b3-07" not in excluded or "b3-07" in library_ids or "b3-07" in declared_ids:
                findings.append(_finding("TIKTOK_EXCLUSION", "b3-07 must stay explicitly excluded from the runway"))
            if spec.get("reservation_only") is not True or spec.get("link_policy") != TIKTOK_LINK_POLICY:
                findings.append(_finding("TIKTOK_SET_POLICY", "TikTok set must remain reservation-only and no-link"))
            dated_rows = sorted(
                (_parse_iso_date(row.get("date")), content_id)
                for content_id, row in rows.items()
                if content_id in library_ids and _parse_iso_date(row.get("date")) is not None
            )
            if len(dated_rows) != 14 or any(
                (right[0] - left[0]).days != 1 for left, right in zip(dated_rows, dated_rows[1:])
            ):
                findings.append(_finding("TIKTOK_CADENCE", "TikTok runway must cover 14 consecutive calendar days"))
            channel_policy = channels_policy.get("tiktok") if isinstance(channels_policy.get("tiktok"), dict) else {}
            test_policy = channel_policy.get("reactivation_test") if isinstance(channel_policy.get("reactivation_test"), dict) else {}
            if set(candidate_ids) != {str(value) for value in test_policy.get("source_side_candidate_ids", [])}:
                findings.append(_finding("TIKTOK_POLICY_IDS", "TikTok candidate IDs drifted from policy"))
            if set(brief_ids) != {str(value) for value in test_policy.get("new_brief_ids", [])}:
                findings.append(_finding("TIKTOK_POLICY_IDS", "TikTok brief IDs drifted from policy"))
            if dated_rows:
                if test_policy.get("start_not_before") != dated_rows[0][0].isoformat() or test_policy.get("end_not_after") != dated_rows[-1][0].isoformat():
                    findings.append(_finding("TIKTOK_POLICY_DATES", "TikTok runway dates drifted from policy"))
            if test_policy.get("duration_days") != 14 or test_policy.get("link_policy") != TIKTOK_LINK_POLICY:
                findings.append(_finding("TIKTOK_POLICY", "TikTok duration or no-link policy drifted"))
        allowed_ids.update(library_ids)

    replacement_spec = (
        sets.get("weekly_replacements")
        if isinstance(sets.get("weekly_replacements"), dict)
        else {}
    )
    supersedes = replacement_spec.get("supersedes")
    if not isinstance(supersedes, dict) or not supersedes:
        findings.append(_finding(
            "REPLACEMENT_SUPERSEDES",
            "weekly replacement must declare the superseded content mapping",
        ))
        supersedes = {}
    replacement_ids = {
        str(value) for value in replacement_spec.get("ids", [])
        if isinstance(value, str) and value.strip()
    }
    seen_replacement_targets: set[str] = set()
    for original_raw, replacement_raw in supersedes.items():
        original = str(original_raw or "").strip()
        replacement = str(replacement_raw or "").strip()
        original_accounts = expected_accounts_by_content.get(original)
        replacement_accounts = expected_accounts_by_content.get(replacement)
        replacement_core_accounts = (
            set(replacement_accounts or set())
            - ({TIKTOK_ACCOUNT} if replacement in tiktok_week_ids else set())
        )
        if (
            not original
            or not replacement
            or replacement not in replacement_ids
            or original not in allowed_ids
            or replacement not in allowed_ids
            or replacement in seen_replacement_targets
            or original_accounts != replacement_core_accounts
        ):
            findings.append(_finding(
                "REPLACEMENT_SUPERSEDES",
                f"invalid supersedes mapping {original!r} -> {replacement!r}",
            ))
            continue
        seen_replacement_targets.add(replacement)
        expected_accounts_by_content.pop(original, None)
        change_receipt = replacement_spec.get("change_receipt")
        for placement in placements:
            if (
                not isinstance(placement, dict)
                or placement.get("content_id") != replacement
                or placement.get("account") not in (original_accounts or set())
            ):
                continue
            provenance = placement.get("replacement_provenance")
            provenance = provenance if isinstance(provenance, dict) else {}
            expected_old_placement = f"{original}__{placement.get('account')}"
            if (
                provenance.get("supersedes_placement_id") != expected_old_placement
                or provenance.get("supersedes_content_id") != original
                or provenance.get("candidate_id") != replacement
                or provenance.get("change_receipt") != change_receipt
            ):
                findings.append(_finding(
                    "REPLACEMENT_PROVENANCE",
                    "replacement placement provenance is incomplete or mismatched",
                    str(placement.get("placement_id") or ""),
                ))
    tiktok_replacement_spec = (
        sets.get("tiktok_week_replacements")
        if isinstance(sets.get("tiktok_week_replacements"), dict)
        else {}
    )
    tiktok_supersedes = tiktok_replacement_spec.get("supersedes")
    if tiktok_supersedes != TIKTOK_WEEK_REPLACEMENT_MAP:
        findings.append(_finding(
            "TIKTOK_WEEK_REPLACEMENT_SUPERSEDES",
            "TikTok week replacement must retain the exact reversible supersedes map",
        ))
        tiktok_supersedes = {}
    tiktok_change_receipt = tiktok_replacement_spec.get("change_receipt")
    for original, replacement in tiktok_supersedes.items():
        if (
            original not in allowed_ids
            or replacement not in allowed_ids
            or expected_accounts_by_content.get(original) != {TIKTOK_ACCOUNT}
            or TIKTOK_ACCOUNT not in expected_accounts_by_content.get(replacement, set())
        ):
            findings.append(_finding(
                "TIKTOK_WEEK_REPLACEMENT_SUPERSEDES",
                f"invalid TikTok supersedes mapping {original!r} -> {replacement!r}",
            ))
            continue
        expected_accounts_by_content.pop(original, None)
        placement_id = f"{replacement}__{TIKTOK_ACCOUNT}"
        placement = next(
            (
                item for item in placements
                if isinstance(item, dict) and item.get("placement_id") == placement_id
            ),
            None,
        )
        provenance = (
            placement.get("replacement_provenance")
            if isinstance(placement, dict) else {}
        )
        provenance = provenance if isinstance(provenance, dict) else {}
        if (
            provenance.get("supersedes_placement_id")
            != f"{original}__{TIKTOK_ACCOUNT}"
            or provenance.get("supersedes_content_id") != original
            or provenance.get("candidate_id") != replacement
            or provenance.get("change_receipt") != tiktok_change_receipt
        ):
            findings.append(_finding(
                "TIKTOK_WEEK_REPLACEMENT_PROVENANCE",
                "TikTok week replacement provenance is incomplete or mismatched",
                placement_id,
            ))
    for content_id, required_accounts in expected_accounts_by_content.items():
        if placements_by_content.get(content_id, set()) != required_accounts:
            findings.append(_finding("PLACEMENT_COVERAGE", f"{content_id} does not cover its required accounts"))
    unknown_ids = set(placements_by_content) - allowed_ids
    if unknown_ids:
        findings.append(_finding("UNKNOWN_CONTENT", "calendar contains non-future or unregistered content: " + ", ".join(sorted(unknown_ids))))

    unique_findings = []
    seen_findings = set()
    for item in findings:
        key = (item.get("code"), item.get("placement_id"), item.get("message"))
        if key not in seen_findings:
            seen_findings.add(key)
            unique_findings.append(item)
    report_findings = [
        item for item in unique_findings
        if item.get("classification") == REPORT_ONLY
    ]
    publication_findings = [
        item for item in unique_findings
        if item.get("classification") == PUBLICATION_BLOCKER
    ]
    structural_findings = [
        item for item in unique_findings
        if item.get("classification") not in {REPORT_ONLY, PUBLICATION_BLOCKER}
    ]
    blocking_findings = publication_findings + structural_findings
    blocked_slots: list[tuple[datetime, dict]] = []
    for item in placements:
        if not isinstance(item, dict) or item.get("status") != BLOCKED_STATUS:
            continue
        item_day = _parse_iso_date(item.get("date"))
        item_clock = _parse_clock(item.get("time"))
        if item_day is None or item_clock is None:
            continue
        blocked_slots.append((
            datetime.combine(item_day, item_clock, tzinfo=BANGKOK),
            item,
        ))
    active_blocked_slots = [
        pair for pair in blocked_slots if pair[0] >= evaluation_now_bangkok
    ]
    stale_blocked_slots = [
        pair for pair in blocked_slots if pair[0] < evaluation_now_bangkok
    ]
    next_window_end = evaluation_now_bangkok + timedelta(hours=NEXT_WINDOW_HOURS)
    rolling_runway_end = evaluation_now_bangkok + timedelta(days=ROLLING_RUNWAY_DAYS)
    next_window_slots = [
        pair for pair in active_blocked_slots if pair[0] <= next_window_end
    ]
    rolling_runway_slots = [
        pair for pair in active_blocked_slots if pair[0] <= rolling_runway_end
    ]
    beyond_runway_slots = [
        pair for pair in active_blocked_slots if pair[0] > rolling_runway_end
    ]

    counts = {
        "placements": len(placements),
        "content_ids": len(placements_by_content),
        # Prove that official-source freshness was evaluated at content_id grain.
        # A blocked result is still a successful fail-closed control outcome; it
        # must not be confused with a global queue blocking unrelated content.
        "source_content_evaluated": len(source_cache),
        "source_content_allowed": sum(
            1 for result in source_cache.values() if _source_allowed(result)
        ),
        "source_content_blocked": sum(
            1 for result in source_cache.values() if not _source_allowed(result)
        ),
        "source_failure_reasons": sum(
            len(_source_failures(result)) for result in source_cache.values()
        ),
        # Preserve ``planned_blocked`` as the lifecycle/status total for older
        # consumers.  Operational backlog readers must use the explicit active
        # metric so historical held rows cannot inflate current runway.
        "planned_blocked": len(blocked_slots),
        "active_planned_blocked": len(active_blocked_slots),
        "planned_blocked_total": len(blocked_slots),
        "planned_blocked_stale": len(stale_blocked_slots),
        "next_48h_planned_blocked": len(next_window_slots),
        "rolling_7d_planned_blocked": len(rolling_runway_slots),
        "rolling_7d_days_covered": len({pair[0].date() for pair in rolling_runway_slots}),
        "beyond_7d_planned_blocked": len(beyond_runway_slots),
        "reserved_blocked": sum(1 for item in placements if isinstance(item, dict) and item.get("slot_state") == RESERVED_SLOT),
        "publishable": 0,
        "stale_slots": sum(1 for item in unique_findings if item.get("code") == "STALE_SLOT"),
        "findings": len(unique_findings),
        "blocking_findings": len(blocking_findings),
        "publication_blocking_findings": len(publication_findings),
        "structural_findings": len(structural_findings),
        "report_only_findings": len(report_findings),
    }
    if structural_findings:
        process_state = PROCESS_RUNNER_FAILED
    elif publication_findings:
        process_state = PROCESS_BLOCKED
    elif report_findings:
        process_state = PROCESS_COMPLETED_BLOCKED
    else:
        process_state = PROCESS_PASS
    return _closed_result(process_state, unique_findings, counts)


def evaluate(
    path: Path = ROOT / CALENDAR_PATH,
    *,
    repo: Path = ROOT,
    today: date | None = None,
    now: datetime | None = None,
) -> dict:
    try:
        calendar = _load_object(Path(path), "content calendar")
    except ValueError as exc:
        return _closed_result(
            PROCESS_RUNNER_FAILED,
            [_finding("CALENDAR_LOAD", str(exc))],
        )
    try:
        calendar_file_sha256 = _sha256(Path(path))
    except OSError as exc:
        return _closed_result(
            PROCESS_RUNNER_FAILED,
            [_finding("CALENDAR_LOAD", "content calendar hash failed: " + type(exc).__name__)],
        )
    return evaluate_document(
        calendar,
        repo=repo,
        today=today,
        now=now,
        calendar_file_sha256=calendar_file_sha256,
    )


def exit_code_for_result(result: dict) -> int:
    """Map the four-state process classification to the runner exit contract."""
    return EXIT_CODES.get(
        result.get("process_state"),
        EXIT_CODES[PROCESS_RUNNER_FAILED],
    )


def main(argv=None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    json_requested = "--json" in raw_argv
    parser = _FailClosedArgumentParser(description="validate the blocked, future-only editorial calendar")
    parser.add_argument("--calendar", default=str(CALENDAR_PATH))
    clock_group = parser.add_mutually_exclusive_group()
    clock_group.add_argument(
        "--now",
        help="timezone-aware ISO-8601 evaluation instant; converted to Asia/Bangkok",
    )
    clock_group.add_argument(
        "--today",
        help="Asia/Bangkok date override at 00:00 for deterministic compatibility tests",
    )
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(raw_argv)
        today = _parse_iso_date(args.today) if args.today else None
        if args.today and today is None:
            parser.error("--today must be YYYY-MM-DD")
        evaluation_now = None
        if args.now:
            try:
                evaluation_now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            except ValueError:
                parser.error("--now must be an ISO-8601 timestamp")
            if evaluation_now.tzinfo is None or evaluation_now.utcoffset() is None:
                parser.error("--now must include a UTC offset or Z")
    except ValueError as exc:
        result = _closed_result(
            PROCESS_RUNNER_FAILED,
            [_finding("INVALID_CLI", str(exc))],
        )
        if json_requested:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"content-calendar-guard: RUNNER_FAILED: {exc}", file=sys.stderr)
        return EXIT_CODES[PROCESS_RUNNER_FAILED]
    path = Path(args.calendar)
    if not path.is_absolute():
        path = ROOT / path
    try:
        result = evaluate(path, repo=ROOT, today=today, now=evaluation_now)
    except Exception as exc:
        result = _closed_result(
            PROCESS_RUNNER_FAILED,
            [_finding("GUARD_RUNTIME", f"{type(exc).__name__}: {exc}")],
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["process_state"] == PROCESS_PASS:
        counts = result["counts"]
        print(
            "content-calendar-guard: PASS "
            f"({counts['placements']} placements; all PLANNED_BLOCKED; publishable=0)"
        )
    elif result["process_state"] == PROCESS_COMPLETED_BLOCKED:
        counts = result["counts"]
        print(
            "content-calendar-guard: COMPLETED_BLOCKED "
            f"({counts['stale_slots']} stale slot(s) retained as {BLOCKED_STATUS}; "
            "publishable=0; no backfill or promotion)"
        )
        for item in result["findings"]:
            suffix = f" [{item['placement_id']}]" if item.get("placement_id") else ""
            print(f"- {item['code']}{suffix}: {item['message']}")
    elif result["process_state"] == PROCESS_BLOCKED:
        print(f"content-calendar-guard: BLOCKED ({len(result['findings'])} safety finding(s))")
        for item in result["findings"]:
            suffix = f" [{item['placement_id']}]" if item.get("placement_id") else ""
            print(f"- {item['code']}{suffix}: {item['message']}")
    else:
        print(f"content-calendar-guard: RUNNER_FAILED ({len(result['findings'])} finding(s))")
        for item in result["findings"]:
            print(f"- {item['code']}: {item['message']}")
    return exit_code_for_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
