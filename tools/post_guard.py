#!/usr/bin/env python3
"""Nightly verification for the ngernduangold posting plan.

The guard deliberately uses local evidence when a channel has no safe read API.
Its default mode never sends a social post.  YouTube repair is a separate,
explicit operation that requires ``--repair-youtube``, ``--date``, and ``--actor``.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import content_source_gate
import manifest_contract


ROOT = Path(__file__).resolve().parent.parent
AUTOMATION_LOG = ROOT / "automation-log"
MANIFEST_PATH = ROOT / ".system_control" / "content_manifest.json"
YT_UPLOAD_LOG_PATH = ROOT / ".system_control" / "yt_upload_log.json"
POLICY_PATH = ROOT / ".system_control" / "policy.json"
ROLE_CAPABILITIES_PATH = ROOT / ".system_control" / "role_capabilities.json"
PRIVACY_GUARD_PATH = ROOT / "tools" / "privacy_guard.py"
OFFICIAL_SOURCE_SNAPSHOT_PATH = (
    AUTOMATION_LOG / "knowledge-base" / "official-news-snapshot.json"
)
REELS_DIR = ROOT / "reels"
REEL_SCHEDULE_PATH = REELS_DIR / "schedule.json"
POST_GUARD_DIR = AUTOMATION_LOG / "post-guard"
HISTORY_PATH = POST_GUARD_DIR / "history.jsonl"
POST_LEDGER_PATH = AUTOMATION_LOG / "post-ledger.jsonl"
BANGKOK = ZoneInfo("Asia/Bangkok")
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_TOKEN_PATH = ROOT / "secrets" / "yt_token.json"
AUTO_YT_FROM = date(2026, 7, 26)
UI_SCHEDULED_IG_DATES = {
    date(2026, 7, day) for day in range(13, 20)
}
# Paused/retired channel state is evaluated from policy at run time. A review
# date is not an automatic reactivation date; only an explicit policy change is.
FB_MANUAL_DATE = date(2026, 7, 20)
# Facebook publishing is manual via Business Suite from 21 Jul 2026 ONWARDS -- this is a
# standing decision (Meta token revoked 18 Jul 2026), not a temporary window.  It was
# previously a hardcoded set covering only 21-26 Jul, which silently expired on 27 Jul and
# made the guard fall through to UNKNOWN every day.  Use an open-ended start date instead.
FB_MANUAL_FROM = date(2026, 7, 21)
TIKTOK_MANUAL_DATES = {
    date(2026, 7, day) for day in range(23, 27)
}
TIKTOK_UI_SCHEDULED_DATES = {
    date(2026, 7, day) for day in range(13, 27)
}


class GuardSetupError(RuntimeError):
    """A required local planning artifact is missing or malformed."""


class YouTubeUnavailable(RuntimeError):
    """The read-only YouTube API check could not be run safely."""


class YouTubeRepairError(RuntimeError):
    """An explicitly requested YouTube repair could not be completed safely."""


KNOWN_CHANNEL_STATES = {"active", "manual", "paused", "retired", "testing", "testing_blocked"}
PUBLICATION_BLOCKED_ACTION = (
    "Report the delivery gap only; do not schedule, repost, or publish."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the daily ngernduangold posting plan (Asia/Bangkok)."
    )
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="Date to check (default: today in Asia/Bangkok).")
    parser.add_argument(
        "--check-tomorrow",
        action="store_true",
        help="Add a local readiness preview for the day after the target date.",
    )
    parser.add_argument("--json", action="store_true", help="Emit only machine-readable JSON on stdout.")
    parser.add_argument(
        "--repair-youtube",
        action="store_true",
        help=(
            "Explicitly run the live YouTube repair for exactly --date. "
            "Without this flag the guard is read-only."
        ),
    )
    parser.add_argument(
        "--actor",
        help="Actor key from role_capabilities.json; required for explicit YouTube repair.",
    )
    parser.add_argument(
        "--receipt-nonce",
        help=(
            "Private one-time publication receipt nonce for the exact YouTube repair; "
            "required with --repair-youtube and never printed."
        ),
    )
    args = parser.parse_args()
    if args.repair_youtube and not args.date:
        parser.error("--repair-youtube requires an explicit --date YYYY-MM-DD")
    if args.repair_youtube and (not isinstance(args.actor, str) or not args.actor.strip()):
        parser.error("--repair-youtube requires an explicit --actor")
    if args.repair_youtube and (
        not isinstance(args.receipt_nonce, str) or not args.receipt_nonce.strip()
    ):
        parser.error("--repair-youtube requires an explicit --receipt-nonce")
    if not args.repair_youtube and args.receipt_nonce:
        parser.error("--receipt-nonce is accepted only with --repair-youtube")
    if args.date:
        try:
            args.target_date = date.fromisoformat(args.date)
        except ValueError:
            parser.error("--date must use YYYY-MM-DD and name a real calendar date")
    else:
        args.target_date = datetime.now(BANGKOK).date()
    return args


def now_bangkok() -> datetime:
    return datetime.now(BANGKOK)


def iso_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _reject_json_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _require_finite_json(item: Any) -> Any:
    if isinstance(item, float) and not math.isfinite(item):
        raise ValueError("non-finite JSON number")
    if isinstance(item, dict):
        for nested in item.values():
            _require_finite_json(nested)
    elif isinstance(item, list):
        for nested in item:
            _require_finite_json(nested)
    return item


def _strict_json_loads(value: str) -> Any:
    return _require_finite_json(json.loads(
        value,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_json_duplicates,
    ))


def _stable_bytes(path: Path) -> bytes:
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if ((before.st_size, before.st_mtime_ns) !=
            (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size):
        raise ValueError("file changed while being read")
    return raw


def _read_strict_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = _stable_bytes(path)
    if raw and not raw.endswith(b"\n"):
        raise ValueError("final JSONL row lacks newline commit boundary")
    rows: list[dict[str, Any]] = []
    for line_number, source in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not source.strip():
            raise ValueError(f"blank JSONL row at line {line_number}")
        row = _strict_json_loads(source)
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row {line_number} is not an object")
        rows.append(row)
    return rows


def read_json(path: Path, label: str) -> Any:
    try:
        return _strict_json_loads(_stable_bytes(path).decode("utf-8-sig"))
    except FileNotFoundError as exc:
        raise GuardSetupError(f"{label} not found: {path.relative_to(ROOT)}") from exc
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "msg", str(exc))
        raise GuardSetupError(
            f"{label} is not valid stable strict JSON: {path.relative_to(ROOT)} ({detail})"
        ) from exc


def load_manifest() -> list[dict[str, Any]]:
    document = read_json(MANIFEST_PATH, "Content manifest")
    errors = manifest_contract.validate_document(document, now_bangkok().date())
    if errors:
        detail = "; ".join(errors[:3])
        raise GuardSetupError(f"Content manifest contract failed: {detail}")
    return document["items"]


def load_upload_log() -> dict[str, str]:
    if not YT_UPLOAD_LOG_PATH.exists():
        return {}
    document = read_json(YT_UPLOAD_LOG_PATH, "YouTube upload log")
    if not isinstance(document, dict):
        raise GuardSetupError("YouTube upload log must be an object mapping dates to video IDs.")
    return {
        key: value
        for key, value in document.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }


def load_channel_policy(channel: str) -> dict[str, Any]:
    """Load one channel policy and reject missing or unknown state.

    A policy failure is an unsafe state, not permission to fall back to a stale
    hard-coded default.  Callers must stop before any external check or action.
    """
    document = read_json(POLICY_PATH, "Policy")
    if not isinstance(document, dict):
        raise GuardSetupError("Policy must be a JSON object.")
    channels = document.get("channels")
    if not isinstance(channels, dict):
        raise GuardSetupError("Policy must contain a 'channels' object.")
    policy = channels.get(channel)
    if not isinstance(policy, dict):
        raise GuardSetupError(f"Policy channel is missing or invalid: {channel}")
    state = policy.get("state")
    if not isinstance(state, str) or state.strip().casefold() not in KNOWN_CHANNEL_STATES:
        shown = state if isinstance(state, str) and state.strip() else "missing"
        raise GuardSetupError(f"Policy channel {channel} has unknown state: {shown}")
    normalized = dict(policy)
    normalized["state"] = state.strip().casefold()
    return normalized


def load_reel_schedule() -> dict[str, dict[str, Any]]:
    document = read_json(REEL_SCHEDULE_PATH, "Reel schedule")
    if not isinstance(document, dict):
        raise GuardSetupError("Reel schedule must be an object keyed by YYYY-MM-DD.")
    invalid = [key for key, value in document.items() if not isinstance(key, str) or not isinstance(value, dict)]
    if invalid:
        raise GuardSetupError("Reel schedule contains a non-object entry.")
    return document


def evaluate_publication_authority(
    checked_at: datetime,
    actor: str = "cowork",
    *,
    channel: str,
    content_id: str | None = None,
    channel_policy: dict[str, Any] | None = None,
    role_path: Path = ROLE_CAPABILITIES_PATH,
    source_path: Path = OFFICIAL_SOURCE_SNAPSHOT_PATH,
    privacy_check: Any = None,
    content_source_check: Any = None,
) -> tuple[bool, str]:
    """Return whether an actor may recommend a social mutation right now.

    Delivery verification and publication authority are separate concerns. This
    gate is deliberately fail-closed: an unreadable role matrix, privacy scanner,
    or exact content-source decision can never turn a missing post into a
    recommendation to schedule/repost/publish.  The global official-news queue is
    diagnostic only; an unrelated source may not block or authorize this piece.
    """
    if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
        return False, "publication decision time must include a timezone"
    try:
        roles = json.loads(role_path.read_text(encoding="utf-8"))
        capabilities = (roles.get("actors") or {}).get(actor)
    except Exception:
        return False, "role capability matrix is missing or unreadable"
    if not isinstance(capabilities, dict) or capabilities.get("social_publish") is not True:
        return False, f"actor {actor} has no current social_publish authority"

    if not isinstance(channel, str) or not channel.strip():
        return False, "publication channel is missing or invalid"
    normalized_channel = channel.strip().casefold()
    if channel_policy is None:
        try:
            channel_policy = load_channel_policy(normalized_channel)
        except GuardSetupError:
            return False, f"policy channel {normalized_channel} is missing or unreadable"
    if not isinstance(channel_policy, dict):
        return False, f"policy channel {normalized_channel} is missing or invalid"
    state = channel_policy.get("state")
    normalized_state = state.strip().casefold() if isinstance(state, str) else ""
    if normalized_state not in KNOWN_CHANNEL_STATES:
        return False, f"policy channel {normalized_channel} has unknown state"
    if normalized_state in {"paused", "retired", "testing_blocked"}:
        return False, f"policy channel {normalized_channel} is {normalized_state}"
    if channel_policy.get("publication_authorized") is not True:
        return False, (
            f"policy channel {normalized_channel} publication_authorized is not explicitly true"
        )

    if privacy_check is None:
        def privacy_check() -> int:
            try:
                return subprocess.run(
                    [sys.executable, str(PRIVACY_GUARD_PATH)],
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=45,
                    check=False,
                ).returncode
            except Exception:
                return 2
    try:
        privacy_rc = int(privacy_check())
    except Exception:
        privacy_rc = 2
    if privacy_rc != 0:
        return False, f"privacy gate is blocked (exit {privacy_rc})"

    normalized_content_id = content_id.strip() if isinstance(content_id, str) else ""
    if not normalized_content_id:
        return False, "exact content_id is missing from the publication decision"
    try:
        canonical = content_source_gate.evaluate_repo_content_source_gate(
            normalized_content_id,
            ROOT,
            now=checked_at.astimezone(timezone.utc),
            snapshot_path=OFFICIAL_SOURCE_SNAPSHOT_PATH,
        )
    except Exception:
        return False, "canonical content-scoped official-source gate is unavailable"
    if canonical.allowed is not True:
        detail = "; ".join(str(value) for value in canonical.failures[:3])
        return False, detail or "canonical content-scoped official-source gate is blocked"
    if content_source_check is None:
        return True, (
            "channel, actor, privacy, and canonical content-scoped source gates passed"
        )
    try:
        source_allowed, source_reason = content_source_check(
            normalized_content_id, OFFICIAL_SOURCE_SNAPSHOT_PATH, checked_at
        )
    except Exception:
        return False, "additional content-scoped official-source check is unavailable"
    if source_allowed is not True:
        return False, str(source_reason or "additional content-scoped source check is blocked")
    return True, "channel, actor, privacy, and canonical content-scoped source gates passed"


def publication_blocked(channel: str, evidence: str, reason: str) -> dict[str, str]:
    return result(
        channel,
        "PUBLICATION-BLOCKED",
        f"{evidence} · publication authority blocked: {reason}",
        PUBLICATION_BLOCKED_ACTION,
    )


def item_for(items: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    wanted = target.isoformat()
    return next((item for item in items if item.get("date") == wanted), None)


def channel_caption(item: dict[str, Any] | None, channel: str) -> str:
    if not item:
        return ""
    captions = item.get("captions")
    if not isinstance(captions, dict):
        return ""
    aliases = {
        "instagram": ("instagram", "ig"),
        "facebook": ("facebook", "fb"),
        "youtube": ("youtube", "yt"),
        "tiktok": ("tiktok", "tik_tok"),
        "threads": ("threads",),
    }
    for key in aliases[channel]:
        value = captions.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


# Which statuses mean "a human has to do something". Module-level on purpose (7 Aug 2026):
# it used to be a local inside the summary function, so the one rule that decides whether
# the guard exits 2 could not be imported, could not be tested, and could drift away from
# the status strings the check_* functions actually return. That drift has already bitten
# once - the note below records a verdict rename that stopped matching the literal "FAIL".
# SKIPPED is deliberately absent: "the task ran and correctly did nothing" is a healthy
# day and must not page anyone. FAILED is present: the ledger saying an attempt failed is
# exactly the case that needs a person.
ACTION_REQUIRED = {"FAIL", "FAILED", "NOT-POSTED", "EVIDENCE-ERROR"}


def result(channel: str, status: str, evidence: str, action: str = "-") -> dict[str, str]:
    return {"channel": channel, "status": status, "evidence": evidence, "action": action}


def manifest_posted_status(
    item: dict[str, Any] | None, channel: str, manifest_key: str
) -> dict[str, str] | None:
    """Return a local manifest status when its posted field is explicit."""
    if not item:
        return None
    posted = item.get("posted")
    if not isinstance(posted, dict):
        return None
    value = posted.get(manifest_key)
    if not isinstance(value, str) or not value.strip():
        return None
    kind = manifest_contract.evidence_kind(value)
    if kind == "scheduled":
        return result(channel, "SCHEDULED-UI", f"(จาก manifest: {value})")
    # "published" is what yt_upload_batch2 writes when the slot had already passed and
    # the video went out immediately. It is a STRONGER claim than "posted", but this
    # function used to understand only "posted"/"scheduled", so a genuinely published
    # item returned None and read as no-signal-at-all. Found 31 Jul 2026.
    if kind == "posted":
        return result(channel, "POSTED", "(จาก manifest)")
    return None


LEDGER_POST_TYPES = ("video", "image")  # rows that assert a real post happened


LEDGER_DATE_FIELDS = ("publish_at", "scheduled_for", "schedule_date", "slot", "ts")


def _ledger_dates(entry: dict[str, Any]) -> set[str]:
    dates: set[str] = set()
    for key in LEDGER_DATE_FIELDS:
        value = entry.get(key)
        if not isinstance(value, str):
            continue
        match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:$|T|\s)", value.strip())
        if match:
            try:
                dates.add(date.fromisoformat(match.group(1)).isoformat())
            except ValueError:
                continue
    return dates


def _ledger_content_id(entry: dict[str, Any]) -> str | None:
    for key in ("content_id", "clip_id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def ledger_evidence(
    channel: str,
    target: date,
    expected_content_id: str | None = None,
    *,
    require_content_id: bool = False,
) -> tuple[str, dict[str, Any] | None]:
    """Read post-ledger.jsonl once and say what it knows about `channel` on `target`.

    Returns ("posted"|"failed"|"none"|"evidence_error", entry).  Precedence: a real post row wins over a
    failure row for the same day (a retry that finally succeeded must not read as failed).

    Rows of type "text" are ignored on purpose: the noon knowledge-post writes to the same
    channel but is not the daily clip, and counting it green hid a missing clip on 20 Jul.
    Rows of type "failure" are the ledger stating the post did NOT happen -- treating them
    as evidence of success is the false-green bug fixed in e85fa55 (30 Jul).
    """
    ledger = AUTOMATION_LOG / "post-ledger.jsonl"
    if not ledger.is_file():
        return "none", None
    wanted = target.isoformat()
    failure: dict[str, Any] | None = None
    evidence_error: dict[str, Any] | None = None
    try:
        rows = _read_strict_jsonl(ledger)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return "evidence_error", {
            "note": f"post ledger is not stable strict evidence: {type(exc).__name__}"
        }
    try:
        for entry in rows:
            if str(entry.get("channel", "")).casefold() != channel.casefold():
                continue
            if wanted not in _ledger_dates(entry):
                continue
            kind = str(entry.get("type", "")).casefold()
            if kind in LEDGER_POST_TYPES:
                row_content_id = _ledger_content_id(entry)
                if expected_content_id and row_content_id != expected_content_id:
                    if require_content_id:
                        evidence_error = {
                            "note": (
                                "post row content identity is missing or mismatched: "
                                f"expected {expected_content_id}, got {row_content_id or 'missing'}"
                            )
                        }
                    continue
                return "posted", entry
            if kind == "failure" and failure is None:
                failure = entry
    except (TypeError, ValueError, OverflowError) as exc:
        return "evidence_error", {"note": f"post ledger row invalid: {type(exc).__name__}"}
    if failure is not None:
        return "failed", failure
    if evidence_error is not None:
        return "evidence_error", evidence_error
    return "none", None


def ledger_note(entry: dict[str, Any] | None) -> str:
    if not entry:
        return ""
    for key in ("text_first80", "note"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return clean_text(value)[:90]
    return ""


def source_side_or_not_posted(
    target: date,
    item: dict[str, Any] | None,
    channel: str,
    manifest_key: str,
    evidence: str,
) -> dict[str, str]:
    """Downstream verification failed. Fall back to what WE control (ledger + manifest).

    Never returns UNKNOWN: every outcome must translate into an action.
      SOURCE-SIDE = we recorded/scheduled it but cannot confirm on the platform.
      FAILED      = the ledger says the attempt failed -> fix the pipeline.
      NOT-POSTED  = no evidence anywhere -> it did not go out; post it.
    (order 30 Jul: "UNKNOWN ทำให้คนมองข้าม NOT-POSTED ทำให้คนแก้")
    """
    expected_content_id = item.get("id") if isinstance(item, dict) else None
    kind, entry = ledger_evidence(
        manifest_key,
        target,
        expected_content_id if isinstance(expected_content_id, str) else None,
        require_content_id=target >= now_bangkok().date(),
    )
    if kind == "posted":
        return result(channel, "SOURCE-SIDE", f"{evidence} · ledger บันทึกว่าโพสต์แล้ว", "ยืนยันปลายทางด้วยตาเมื่อสะดวก")
    manifest_status = manifest_posted_status(item, channel, manifest_key)
    if kind == "evidence_error":
        note = ledger_note(entry)
        return result(
            channel,
            "EVIDENCE-ERROR",
            f"{evidence} · หลักฐาน ledger ใช้ยืนยันไม่ได้: {note}",
            "ซ่อมหลักฐานและตรวจ content_id ก่อนตัดสินใจเผยแพร่",
        )
    if kind == "failed" and not (
        manifest_status is not None and manifest_status.get("status") == "POSTED"
    ):
        note = ledger_note(entry)
        return result(channel, "FAILED", f"{evidence} · ledger บันทึกความล้มเหลว: {note}", "ซ่อม pipeline แล้วโพสต์ซ้ำ")
    if manifest_status is not None:
        detail = manifest_status["evidence"]
        return result(channel, "SOURCE-SIDE", f"{evidence} · ต้นทางตั้งค่าไว้แล้ว {detail}",
                      "ยืนยันปลายทางด้วยตาเมื่อสะดวก")
    return result(channel, "NOT-POSTED", f"{evidence} · ไม่มีหลักฐานทั้งใน ledger และ manifest", "โพสต์ให้เรียบร้อย")


def manifest_or_unknown(
    item: dict[str, Any] | None,
    channel: str,
    manifest_key: str,
    evidence: str,
    action: str = "-",
) -> dict[str, str]:
    manifest_status = manifest_posted_status(item, channel, manifest_key)
    if manifest_status is not None:
        return manifest_status
    return result(channel, "UNKNOWN", evidence, action)


def http_error_detail(error: Exception) -> str:
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    content = getattr(error, "content", b"")
    reason = "unknown"
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        payload = _strict_json_loads(content)
        errors = payload.get("error", {}).get("errors", [])
        if errors and isinstance(errors[0], dict):
            reason = str(errors[0].get("reason", reason))
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return f"HTTP {status if isinstance(status, int) else 'unknown'} ({reason})"


def youtube_service() -> Any:
    """Create a YouTube client without refreshing or writing the token cache."""
    if not YOUTUBE_TOKEN_PATH.is_file():
        raise YouTubeUnavailable("yt_token.json is unavailable")
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise YouTubeUnavailable("Google API libraries are unavailable") from exc
    try:
        credentials = Credentials.from_authorized_user_file(YOUTUBE_TOKEN_PATH, [YOUTUBE_SCOPE])
    except Exception as exc:
        raise YouTubeUnavailable("yt_token.json could not be loaded") from exc
    # Refreshing through the helper would write the cache; the guard is read-only.
    if not credentials.valid:
        # Wording matters: this token is upload-scope only and may simply be stale but
        # refreshable. Do not imply the credential is dead -- that misreading is why
        # uploads were done by hand for days when the script would have worked.
        raise YouTubeUnavailable(
            "cached YouTube token needs refresh (upload-scope only); guard is read-only and will not rewrite it"
        )
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def expected_youtube_time(target: date) -> datetime:
    return datetime.combine(target, time(19, 0), tzinfo=BANGKOK)


def check_logged_youtube(target: date, video_id: str, checked_at: datetime) -> dict[str, str]:
    try:
        service = youtube_service()
        response = service.videos().list(part="status,snippet", id=video_id).execute()
    except Exception as exc:
        detail = http_error_detail(exc) if hasattr(exc, "resp") else str(exc)
        # EVIDENCE FIX 30 Jul 2026: yt_upload_log is written ONLY after YouTube returns a
        # video ID for a completed upload, so its presence already proves the clip shipped.
        # Reporting UNKNOWN here made a delivered day look undelivered, and the accompanying
        # "token invalid" wording caused a standing (wrong) belief that YouTube auth was dead
        # -- the cached token is upload-scope only, so read calls legitimately return 403.
        return result(
            "YOUTUBE",
            "OK",
            f"upload confirmed by yt_upload_log ({video_id}); live visibility not re-checked ({detail})",
            "No action. To verify visibility, open the video in YouTube Studio.",
        )

    videos = response.get("items", [])
    if not videos:
        return result("YOUTUBE", "FAIL", "yt_upload_log video ID was not returned by videos.list", "Investigate the upload log/video ID.")
    status = videos[0].get("status", {})
    privacy = str(status.get("privacyStatus", "unknown"))
    publish_at = str(status.get("publishAt", "-") or "-")
    due = checked_at >= expected_youtube_time(target) + timedelta(minutes=5)
    if due:
        if privacy == "public":
            return result("YOUTUBE", "OK", f"API: privacyStatus=public; publishAt={publish_at}")
        return result(
            "YOUTUBE",
            "FAIL",
            f"API after 19:05 Asia/Bangkok: privacyStatus={privacy}; publishAt={publish_at}",
            "Check YouTube Studio visibility/publish time.",
        )
    if privacy == "public":
        return result("YOUTUBE", "OK", f"API: already public; publishAt={publish_at}")
    if privacy == "private" and publish_at != "-":
        return result("YOUTUBE", "OK", f"API: scheduled private video; publishAt={publish_at}")
    return result("YOUTUBE", "UNKNOWN", f"API: privacyStatus={privacy}; publishAt={publish_at}")


def check_ui_youtube(item: dict[str, Any] | None) -> dict[str, str]:
    title_line = first_line(channel_caption(item, "youtube"))
    if not title_line:
        return result(
            "YOUTUBE",
            "UNKNOWN",
            "No yt_upload_log entry and manifest captions.youtube has no first-line title to match.",
            "Check YouTube Studio's UI-scheduled Short.",
        )
    # A YouTube title is capped at 100 characters.  Eighty keeps the match
    # specific while still working when a source caption includes #Shorts.
    title_prefix = clean_text(title_line)[:80]
    try:
        service = youtube_service()
        channels = service.channels().list(part="contentDetails", mine=True).execute().get("items", [])
        if not channels:
            return result("YOUTUBE", "UNKNOWN", "channels.list(mine=True) returned no channel")
        uploads_id = channels[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not isinstance(uploads_id, str) or not uploads_id:
            return result("YOUTUBE", "UNKNOWN", "The YouTube uploads playlist was unavailable")
        playlist = service.playlistItems().list(
            part="snippet", playlistId=uploads_id, maxResults=10
        ).execute()
    except Exception as exc:
        detail = http_error_detail(exc) if hasattr(exc, "resp") else str(exc)
        return result("YOUTUBE", "UNKNOWN", f"Uploads-playlist check unavailable: {detail}")
    titles = [
        str(entry.get("snippet", {}).get("title", ""))
        for entry in playlist.get("items", [])
        if isinstance(entry, dict)
    ]
    if any(clean_text(title).startswith(title_prefix) for title in titles):
        return result("YOUTUBE", "OK", "Recent uploads playlist contains the manifest title prefix.")
    return result(
        "YOUTUBE",
        "UNKNOWN",
        "Recent 10 uploads do not contain the manifest title prefix (UI schedules are best-effort).",
        "Check YouTube Studio's UI-scheduled Short.",
    )


def quota_likely_available(checked_at: datetime) -> bool:
    """Avoid repeating an upload after a quota block recorded earlier today."""
    if not HISTORY_PATH.exists():
        return True
    today = checked_at.date().isoformat()
    try:
        rows = _read_strict_jsonl(HISTORY_PATH)[-100:]
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False
    for entry in rows:
        if not str(entry.get("checked_at", "")).startswith(today):
            continue
        if "quotaexceeded" in json.dumps(entry, ensure_ascii=False).casefold():
            return False
    return True


def upload_token_is_safe_to_use() -> bool:
    """Do not invoke the upload helper if it would need to rewrite its token."""
    if not YOUTUBE_TOKEN_PATH.is_file():
        return False
    try:
        from google.oauth2.credentials import Credentials

        credentials = Credentials.from_authorized_user_file(YOUTUBE_TOKEN_PATH, [YOUTUBE_SCOPE])
        return bool(credentials.valid)
    except Exception:
        return False


def _safe_reel_asset(base: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise YouTubeRepairError(f"{label} is missing")
    relative = Path(raw_path)
    if relative.is_absolute():
        raise YouTubeRepairError(f"{label} must be a repository-relative reel path")
    candidate = (base / relative).resolve()
    reels_root = REELS_DIR.resolve()
    if candidate != reels_root and reels_root not in candidate.parents:
        raise YouTubeRepairError(f"{label} escapes the reels directory")
    if not candidate.is_file():
        raise YouTubeRepairError(f"{label} does not exist: {raw_path}")
    try:
        if candidate.stat().st_size <= 0:
            raise YouTubeRepairError(f"{label} is empty: {raw_path}")
    except OSError as exc:
        raise YouTubeRepairError(f"{label} cannot be read: {raw_path}") from exc
    return candidate


def validate_youtube_repair_authorization(
    target: date,
    checked_at: datetime,
    item: dict[str, Any] | None,
    youtube_policy: dict[str, Any],
    schedule: dict[str, dict[str, Any]],
) -> None:
    """Require an exact, approved current/future publication record.

    Canonical approval schema lives on the exact ``reels/schedule.json`` row::

        "approval": {
          "qa": "PASS", "publication": "APPROVED",
          "privacy_gate": "PASS", "publication_gate": "PASS",
          "approved_by": "...", "approved_at": "ISO-8601"
        }

    Existing prose QA is evidence, but it is not publication authorization.
    """
    if not isinstance(youtube_policy, dict):
        raise YouTubeRepairError("YouTube policy is missing or invalid")
    if not isinstance(schedule, dict):
        raise YouTubeRepairError("reel schedule is missing or invalid")
    state = str(youtube_policy.get("state", "")).strip().casefold()
    if state != "active":
        raise YouTubeRepairError(
            f"policy channels.youtube.state must be active; found {state or 'missing'}"
        )
    if youtube_policy.get("publication_authorized") is not True:
        raise YouTubeRepairError(
            "policy channels.youtube.publication_authorized must be explicitly true"
        )
    if target < checked_at.astimezone(BANGKOK).date():
        raise YouTubeRepairError(
            f"repair target {target.isoformat()} is historical; only current/future schedules are allowed"
        )
    if not isinstance(item, dict) or item.get("date") != target.isoformat():
        raise YouTubeRepairError(
            f"content manifest has no exact item for {target.isoformat()}"
        )
    manifest_content_id = item.get("id")
    if not isinstance(manifest_content_id, str) or not manifest_content_id.strip():
        raise YouTubeRepairError("exact manifest item is missing id/content_id")

    scheduled = schedule.get(target.isoformat())
    if not isinstance(scheduled, dict):
        raise YouTubeRepairError(
            f"reels/schedule.json has no exact current/future row for {target.isoformat()}"
        )
    scheduled_content_id = scheduled.get("content_id")
    if not isinstance(scheduled_content_id, str) or not scheduled_content_id.strip():
        raise YouTubeRepairError(
            f"reels/schedule.json[{target.isoformat()}] is missing explicit content_id"
        )
    if scheduled_content_id.strip() != manifest_content_id.strip():
        raise YouTubeRepairError(
            "schedule content_id does not match the exact manifest item: "
            f"{scheduled_content_id!r} != {manifest_content_id!r}"
        )

    manifest_asset = _safe_reel_asset(ROOT, item.get("reel"), "manifest reel asset")
    scheduled_asset = _safe_reel_asset(REELS_DIR, scheduled.get("file"), "scheduled reel asset")
    if manifest_asset != scheduled_asset:
        raise YouTubeRepairError(
            "scheduled reel asset does not exactly match the manifest reel asset"
        )

    approval = scheduled.get("approval")
    if not isinstance(approval, dict):
        raise YouTubeRepairError(
            "no structured publication approval record; add approval with qa=PASS, "
            "publication=APPROVED, privacy_gate=PASS, publication_gate=PASS, "
            "approved_by and approved_at to the exact reels/schedule.json row"
        )
    required_statuses = {
        "qa": {"pass", "approved"},
        "publication": {"approved"},
        "privacy_gate": {"pass", "approved"},
        "publication_gate": {"pass", "approved"},
    }
    for field, accepted in required_statuses.items():
        value = approval.get(field)
        normalized = value.strip().casefold() if isinstance(value, str) else ""
        if normalized not in accepted:
            wanted = " or ".join(sorted(status.upper() for status in accepted))
            raise YouTubeRepairError(
                f"publication approval field {field} must explicitly be {wanted}; "
                f"found {value if value is not None else 'missing'}"
            )
    approved_by = approval.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise YouTubeRepairError("publication approval is missing approved_by")
    approved_at_value = approval.get("approved_at")
    if not isinstance(approved_at_value, str) or not approved_at_value.strip():
        raise YouTubeRepairError("publication approval is missing approved_at")
    try:
        approved_at = datetime.fromisoformat(approved_at_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise YouTubeRepairError("publication approval approved_at must be ISO-8601") from exc
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=BANGKOK)
    if approved_at > checked_at.astimezone(approved_at.tzinfo):
        raise YouTubeRepairError("publication approval approved_at cannot be in the future")


def run_youtube_recovery(
    target: date,
    checked_at: datetime,
    *,
    item: dict[str, Any] | None,
    youtube_policy: dict[str, Any],
    schedule: dict[str, dict[str, Any]],
    actor: str,
    receipt_nonce: str,
) -> str:
    """Run the explicit live repair for one exact manifest date or fail closed."""
    validate_youtube_repair_authorization(
        target, checked_at, item, youtube_policy, schedule
    )
    if not isinstance(actor, str) or not actor.strip():
        raise YouTubeRepairError("repair requires an explicit actor")
    if not isinstance(receipt_nonce, str) or not receipt_nonce.strip():
        raise YouTubeRepairError("repair requires an explicit private receipt nonce")
    target_channel_id = youtube_policy.get("channel_id")
    if not isinstance(target_channel_id, str) or not target_channel_id.strip():
        raise YouTubeRepairError("YouTube policy is missing the exact target channel id")
    allowed, authority_reason = evaluate_publication_authority(
        checked_at,
        actor.strip(),
        channel="youtube",
        content_id=item.get("id") if isinstance(item, dict) else None,
        channel_policy=youtube_policy,
    )
    if not allowed:
        raise YouTubeRepairError(f"publication authority blocked: {authority_reason}")
    if target < AUTO_YT_FROM:
        raise YouTubeRepairError(
            f"repair target {target.isoformat()} is before the supported window {AUTO_YT_FROM.isoformat()}"
        )
    if not quota_likely_available(checked_at):
        raise YouTubeRepairError("a quotaExceeded result is already recorded for today")
    if not upload_token_is_safe_to_use():
        raise YouTubeRepairError(
            "the cached YouTube token is unavailable/expired; repair will not rewrite secrets"
        )
    launcher = shutil.which("py") or sys.executable
    command = [
        launcher,
        str(ROOT / "tools" / "yt_upload_batch2.py"),
        "--live",
        "--limit",
        "1",
        "--dates",
        target.isoformat(),
        "--actor",
        actor.strip(),
        "--target-channel-id",
        target_channel_id.strip(),
        "--receipt-nonce",
        f"{target.isoformat()}={receipt_nonce.strip()}",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20 * 60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise YouTubeRepairError(
            f"repair command could not complete: {type(exc).__name__}"
        ) from exc
    # Do not copy subprocess output into a report: it is unnecessary for the
    # guard result and may expose future helper diagnostics.
    output = (completed.stdout + "\n" + completed.stderr).casefold()
    if "quotaexceeded" in output:
        raise YouTubeRepairError("repair stopped on quotaExceeded")
    if completed.returncode != 0:
        raise YouTubeRepairError(f"repair command exited {completed.returncode}")
    return f"Ran explicit YouTube repair for exactly {target.isoformat()} (exit 0); re-verified afterward."


def check_youtube(
    target: date, item: dict[str, Any] | None, upload_log: dict[str, str], checked_at: datetime
) -> dict[str, str]:
    video_id = upload_log.get(target.isoformat())
    if video_id:
        return check_logged_youtube(target, video_id, checked_at)
    return check_ui_youtube(item)


def ig_artifact_matches(target: date) -> list[Path]:
    directory = AUTOMATION_LOG / "ig-reels"
    if not directory.is_dir():
        return []
    wanted = target.isoformat()
    matches: list[Path] = []
    candidates = [directory / "published.json"]
    candidates.extend(directory.glob(f"log-{wanted}.*"))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            if wanted in candidate.read_text(encoding="utf-8", errors="replace"):
                matches.append(candidate)
        except OSError:
            continue
    return matches


def ig_workflow_configured() -> bool:
    # A bare generic Meta file is intentionally not inspected or used.  A
    # runnable IG workflow requires the explicit runtime token and account ID.
    return bool(os.environ.get("IG_ACCESS_TOKEN") and os.environ.get("IG_USER_ID"))


def check_instagram(
    target: date,
    item: dict[str, Any] | None,
    channel_policy: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Check Instagram only when its authoritative policy explicitly permits it."""
    if channel_policy is None:
        try:
            channel_policy = load_channel_policy("instagram")
        except GuardSetupError as exc:
            return result(
                "INSTAGRAM",
                "FAIL",
                f"Instagram policy unavailable: {exc}",
                "Repair .system_control/policy.json before any Instagram check or action.",
            )
    state_value = channel_policy.get("state")
    state = state_value.strip().casefold() if isinstance(state_value, str) else ""
    if state not in KNOWN_CHANNEL_STATES:
        return result(
            "INSTAGRAM",
            "FAIL",
            f"Instagram policy has unknown state: {state_value or 'missing'}",
            "Set a known Instagram state before any check or action.",
        )
    if state == "retired":
        return result(
            "INSTAGRAM",
            "RETIRED",
            "Instagram is retired by policy.",
            "-",
        )
    if state == "paused":
        until_value = channel_policy.get("until")
        try:
            review_date = date.fromisoformat(until_value) if isinstance(until_value, str) else None
        except ValueError:
            review_date = None
        if review_date is None:
            return result(
                "INSTAGRAM",
                "FAIL",
                "Instagram policy state is paused but review date 'until' is missing or invalid.",
                "Repair the Instagram policy; do not publish while state is unresolved.",
            )
        review_due = target > review_date
        evidence = (
            f"Instagram remains paused after its {review_date.isoformat()} review date; "
            "a review date never reactivates a channel."
            if review_due
            else f"Instagram is paused by policy; review date is {review_date.isoformat()}."
        )
        action = (
            "Review the evidence and record an explicit policy state; no publishing until then."
            if review_due
            else "No action until the recorded review date."
        )
        return result(
            "INSTAGRAM",
            "PAUSED",
            evidence,
            action,
        )
    matches = ig_artifact_matches(target)
    if matches:
        files = ", ".join(path.relative_to(ROOT).as_posix() for path in matches)
        return result("INSTAGRAM", "OK", f"IG automation artifact mentions {target.isoformat()}: {files}")
    if target in UI_SCHEDULED_IG_DATES:
        return result(
            "INSTAGRAM",
            "SCHEDULED-UI",
            "UI-scheduled date (13-19 Jul); no local IG publish artifact yet.",
            "Verify the scheduled Reel in Instagram UI.",
        )
    if not ig_workflow_configured():
        return result(
            "INSTAGRAM",
            "MANUAL-ONLY",
            "IG publishing is manual via Business Suite by design (Meta token revoked 18 Jul 2026).",
            "Verify in Instagram UI. Do NOT request tokens or credentials.",
        )
    return manifest_or_unknown(
        item,
        "INSTAGRAM",
        "ig",
        "IG workflow credentials exist, but this guard is read-only and found no artifact.",
    )


def fb_log_candidates() -> list[Path]:
    if not AUTOMATION_LOG.is_dir():
        return []
    paths: list[Path] = []
    for path in AUTOMATION_LOG.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.casefold()
        # Do not treat generic FB link-health notes as posting proof.  These are
        # the explicit scheduling/feed-run naming conventions used by the plan.
        if re.search(r"(?:schedule[_-]?(?:fb|facebook)|(?:fb|facebook)[_-]?schedule|(?:fb|facebook)[_-]?feed|feed[_-]?(?:fb|facebook)|(?:fb|facebook)[_-]?publish)", name):
            paths.append(path)
    return paths


def check_facebook(
    target: date,
    item: dict[str, Any] | None,
    publication_gate: tuple[bool, str] | None = None,
) -> dict[str, str]:
    wanted = target.isoformat()
    candidates = fb_log_candidates()
    matching: list[Path] = []
    for candidate in candidates:
        try:
            if wanted in candidate.read_text(encoding="utf-8", errors="replace"):
                matching.append(candidate)
        except OSError:
            continue
    if matching:
        files = ", ".join(path.relative_to(ROOT).as_posix() for path in matching[:3])
        return result("FACEBOOK", "OK", f"FB/feed automation log mentions {wanted}: {files}")
    note = "no FB/feed run logs found" if not candidates else f"scanned {len(candidates)} FB/feed-named log(s); none mention {wanted}"
    if target == FB_MANUAL_DATE:
        return result("FACEBOOK", "OK", f"Manual-scheduled date (20 Jul); {note}")
    allowed, authority_reason = publication_gate or evaluate_publication_authority(
        now_bangkok(),
        channel="facebook",
        content_id=item.get("id") if isinstance(item, dict) else None,
    )
    if not allowed:
        return publication_blocked("FACEBOOK", note, authority_reason)
    # The owner permanently revoked the Meta token on 18 Jul 2026; FB publishing is manual via
    # Business Suite by design.  This branch used to report BLOCKED and ask for FB_PAGE_ID /
    # FB_PAGE_TOKEN every single day, which contradicts a settled decision and trains the
    # operator to ignore the guard.  Report the real state instead and never prompt for tokens.
    if target >= FB_MANUAL_FROM:
        return result(
            "FACEBOOK",
            "MANUAL-ONLY",
            f"{note}; FB publishing is manual via Business Suite by design (Meta token revoked 18 Jul 2026).",
            "Verify/schedule in Business Suite. Do NOT request tokens or credentials.",
        )
    return manifest_or_unknown(
        item,
        "FACEBOOK",
        "fb",
        note,
        "Check Facebook/Business Suite or add a run artifact.",
    )


def check_facebook_comment(target: date) -> dict[str, str]:
    """OK / SKIPPED / FAILED / NONE for today's page comment-link.

    SKIPPED and FAILED were added 7 Aug 2026. Before that this function knew only
    "found a comment row" or "found nothing", so three genuinely different days looked
    identical from here:

      - the task ran and commented                      -> correct
      - the task ran and correctly did nothing, because the page had already been
        commented on, or there was no new page post to comment under
      - the task never ran, or ran and failed

    All three reported "no comment-link ledger entry today", i.e. a day that worked
    perfectly and a day that silently failed produced the same line. The task's own
    prompt admitted this - it said to skip the ledger append when idempotent and then
    noted, in the same sentence, that the guard would therefore report the day as not
    done. The prompt now writes an explicit row every run; this reads it.

    Precedence matches ledger_evidence: a real comment wins over skipped, and skipped
    wins over failure, because a retry that eventually succeeded must not read as failed.
    """
    found: dict[str, dict[str, str]] = {}
    if POST_LEDGER_PATH.is_file():
        try:
            rows = _read_strict_jsonl(POST_LEDGER_PATH)
            for entry in rows:
                if entry.get("channel") != "facebook":
                    continue
                kind = str(entry.get("type", "")).casefold()
                if kind not in ("comment", "skipped", "failure"):
                    continue
                timestamp = entry.get("ts")
                if not isinstance(timestamp, str):
                    continue
                try:
                    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=BANGKOK)
                if parsed.astimezone(BANGKOK).date() != target:
                    continue
                # a skipped/failure row from the noon text post is not about the comment
                # layer; only rows written by the comment task itself count here
                if kind != "comment" and "comment" not in str(entry.get("source", "")).casefold():
                    continue
                found.setdefault(kind, {"ts": timestamp, "note": str(entry.get("note", ""))})
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            return result(
                "FACEBOOK-COMMENT", "FAILED",
                "post-ledger evidence is invalid: %s" % type(exc).__name__,
                "repair/reconcile the local ledger before trusting comment state",
            )

    if "comment" in found:
        return result("FACEBOOK-COMMENT", "OK",
                      f"comment-link in ledger {found['comment']['ts']}")
    if "skipped" in found:
        note = found["skipped"]["note"] or "no reason recorded"
        return result("FACEBOOK-COMMENT", "SKIPPED",
                      f"task ran and correctly did nothing: {note}")
    if "failure" in found:
        note = found["failure"]["note"] or "no reason recorded"
        return result("FACEBOOK-COMMENT", "FAILED",
                      f"task ran and failed: {note}",
                      "read the note, then check the 21:30 task / extension bridge")
    return result(
        "FACEBOOK-COMMENT",
        "NONE",
        "no comment-link row of any kind today - the task did not run, or died before writing",
        "check 21:30 task / extension bridge",
    )


def public_profile_page(url: str) -> tuple[str | None, str | None]:
    """Fetch a public social profile with browser-like, bounded requests."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip",
        },
    )
    last_error: Exception | None = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = response.read(2_500_000)
                if response.headers.get("Content-Encoding", "").casefold() == "gzip":
                    payload = gzip.decompress(payload)
                return payload.decode("utf-8", errors="replace"), None
        except Exception as exc:  # Public profiles may fail in provider-specific ways.
            last_error = exc
    return None, type(last_error).__name__ if last_error else "UnknownError"


def tiktok_embedded_json(page: str) -> Any | None:
    """Return TikTok's rehydration data, with its legacy SIGI state as fallback."""
    for script in re.finditer(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", page, re.IGNORECASE | re.DOTALL):
        attrs = script.group("attrs")
        if re.search(r"\bid\s*=\s*(['\"])__UNIVERSAL_DATA_FOR_REHYDRATION__\1", attrs, re.IGNORECASE):
            try:
                return _strict_json_loads(script.group("body").strip())
            except (json.JSONDecodeError, ValueError):
                return None
    match = re.search(r"window\s*\[\s*['\"]SIGI_STATE['\"]\s*\]\s*=", page)
    if not match:
        return None
    start = match.end()
    while start < len(page) and page[start].isspace():
        start += 1
    try:
        decoder = json.JSONDecoder(
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_json_duplicates,
        )
        return _require_finite_json(decoder.raw_decode(page[start:])[0])
    except (json.JSONDecodeError, ValueError):
        return None


def tiktok_items(document: Any) -> list[tuple[str, Any]]:
    """Find item dictionaries regardless of TikTok's surrounding JSON shape."""
    found: list[tuple[str, Any]] = []
    pending = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if "desc" in value and "createTime" in value:
                description = value.get("desc")
                if isinstance(description, str):
                    found.append((description, value.get("createTime")))
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return found


def tiktok_created_on(value: Any, target: date) -> bool:
    try:
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, BANGKOK).date() == target
    except (TypeError, ValueError, OverflowError, OSError):
        return False


def check_tiktok(
    target: date,
    item: dict[str, Any] | None,
    checked_at: datetime,
    channel_policy: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Check TikTok only when the authoritative policy permits it.

    Retired and testing_blocked return before the public-profile request. Missing,
    malformed, expired-paused, or unknown policy also stops before the network.
    """
    if channel_policy is None:
        try:
            channel_policy = load_channel_policy("tiktok")
        except GuardSetupError as exc:
            return result(
                "TIKTOK",
                "FAIL",
                f"TikTok policy unavailable: {exc}",
                "Repair .system_control/policy.json before any TikTok check or action.",
            )
    state_value = channel_policy.get("state")
    state = state_value.strip().casefold() if isinstance(state_value, str) else ""
    if state not in KNOWN_CHANNEL_STATES:
        return result(
            "TIKTOK",
            "FAIL",
            f"TikTok policy has unknown state: {state_value or 'missing'}",
            "Set a known TikTok state in .system_control/policy.json before any check or action.",
        )
    if state == "retired":
        return result(
            "TIKTOK",
            "RETIRED",
            "TikTok is retired by policy; an old 'until' date cannot reactivate it.",
            "-",
        )
    if state == "testing_blocked":
        return result(
            "TIKTOK",
            "TESTING-BLOCKED",
            "TikTok has a local reactivation plan, but every placement remains blocked by policy.",
            "Resolve the per-piece source, dedup, media, landing, identity, and owner-confirmation gates; do not schedule or publish.",
        )
    if state == "paused":
        until_value = channel_policy.get("until")
        try:
            paused_until = date.fromisoformat(until_value) if isinstance(until_value, str) else None
        except ValueError:
            paused_until = None
        if paused_until is None:
            return result(
                "TIKTOK",
                "FAIL",
                "TikTok policy state is paused but 'until' is missing or invalid.",
                "Repair the TikTok policy before any check or action.",
            )
        if target > paused_until:
            return result(
                "TIKTOK",
                "FAIL",
                f"TikTok pause expired on {paused_until.isoformat()} but policy still says paused.",
                "Record an explicit active, testing, or retired decision before any check or action.",
            )
        return result(
            "TIKTOK",
            "PAUSED",
            f"TikTok is paused by policy until {paused_until.isoformat()}.",
            "No action until the recorded review date.",
        )
    # Logged-out profile scraping stopped working (interest modal / no rehydration JSON).
    # When downstream verification is impossible we report from the source side instead of
    # UNKNOWN, which never told anyone what to do (order 30 Jul, task 2.1a).
    if target in TIKTOK_UI_SCHEDULED_DATES and checked_at.time() < time(19, 5):
        return result("TIKTOK", "SCHEDULED-UI", "UI-scheduled through 26 Jul; public verification begins after 19:05 Asia/Bangkok.")
    prefix = clean_text(channel_caption(item, "tiktok"))[:25]
    if not prefix:
        return source_side_or_not_posted(
            target,
            item,
            "TIKTOK",
            "tiktok",
            "Manifest captions.tiktok is missing; no public profile match is possible.",
        )
    page, error_name = public_profile_page("https://www.tiktok.com/@ngernduangold")
    if page is None:
        return source_side_or_not_posted(
            target,
            item,
            "TIKTOK",
            "tiktok",
            f"Public profile GET was unavailable/unparseable: {error_name}",
        )
    document = tiktok_embedded_json(page)
    if document is None:
        return source_side_or_not_posted(
            target,
            item,
            "TIKTOK",
            "tiktok",
            "Public profile did not contain parseable TikTok rehydration data.",
        )
    items = tiktok_items(document)
    if any(prefix in clean_text(description) for description, _ in items):
        return result("TIKTOK", "OK", "Manifest caption prefix appears in a public TikTok item description.")
    if any(tiktok_created_on(created_at, target) for _, created_at in items):
        return result("TIKTOK", "OK", "an item was published on the target date (caption mismatch)")
    return source_side_or_not_posted(
        target,
        item,
        "TIKTOK",
        "tiktok",
        "No public TikTok item matched the manifest caption prefix or target date.",
    )


def check_threads(
    target: date,
    item: dict[str, Any] | None,
    publication_gate: tuple[bool, str] | None = None,
) -> dict[str, str]:
    """Threads is a channel WE post to ourselves, so the ledger is the source of truth.

    No ledger row does not mean "unknown" -- it means nobody posted (order 30 Jul, task 2.2).
    The public-profile scrape stays only as a free upside: Threads renders client-side so the
    HTML almost never contains the caption, and a miss there must not downgrade the verdict.
    """
    wanted = target.isoformat()
    expected_content_id = item.get("id") if isinstance(item, dict) else None
    kind, entry = ledger_evidence(
        "threads",
        target,
        expected_content_id if isinstance(expected_content_id, str) else None,
        require_content_id=target >= now_bangkok().date(),
    )
    if kind == "posted":
        return result("THREADS", "OK", f"Threads clip entry dated {wanted} found in post-ledger.jsonl.")

    if kind == "evidence_error":
        note = ledger_note(entry)
        return result(
            "THREADS",
            "EVIDENCE-ERROR",
            f"หลักฐาน ledger ของ {wanted} ใช้ยืนยันไม่ได้: {note}",
            "ซ่อม ledger และยืนยัน content_id ก่อนตัดสินใจเผยแพร่",
        )

    allowed, authority_reason = publication_gate or evaluate_publication_authority(
        now_bangkok(),
        channel="threads",
        content_id=item.get("id") if isinstance(item, dict) else None,
    )
    if not allowed:
        evidence = (
            f"ledger records a failed Threads attempt for {wanted}"
            if kind == "failed"
            else f"no Threads video ledger row exists for {wanted}"
        )
        return publication_blocked("THREADS", evidence, authority_reason)

    prefix = clean_text(channel_caption(item, "threads"))[:30]
    if prefix:
        page, _error_name = public_profile_page("https://www.threads.com/@ngernduangold")
        if page is not None:
            page_text = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", page)))
            if prefix in page_text:
                return result("THREADS", "OK", "caption prefix found on public profile")

    if kind == "failed":
        note = ledger_note(entry)
        return result("THREADS", "FAILED", f"ledger บันทึกว่าโพสต์ไม่สำเร็จ ({wanted}): {note}",
                      "ซ่อมเส้นทางแนบไฟล์แล้วโพสต์ซ้ำวันนี้")
    return result("THREADS", "NOT-POSTED", f"ไม่มีแถวคลิป Threads ลงวันที่ {wanted} ใน post-ledger.jsonl",
                  "โพสต์คลิปวันนี้ลง Threads แล้วบันทึก ledger")


def readiness_preview(
    target: date,
    items: list[dict[str, Any]],
    upload_log: dict[str, str],
    checked_at: datetime,
    tiktok_policy: dict[str, Any],
) -> dict[str, Any]:
    tomorrow = target + timedelta(days=1)
    item = item_for(items, tomorrow)
    checks: list[dict[str, str]] = []
    if not item:
        checks.append({"name": "Manifest", "status": "MISSING", "detail": f"No manifest item for {tomorrow.isoformat()}."})
    else:
        reel = item.get("reel")
        reel_path = (ROOT / reel).resolve() if isinstance(reel, str) else None
        reel_exists = bool(reel_path and reel_path.is_file() and ROOT in reel_path.parents)
        checks.append({
            "name": "Reel file",
            "status": "OK" if reel_exists else "MISSING",
            "detail": reel if reel_exists else f"Missing or unsafe reel path: {reel or '-'}",
        })
        missing_captions = [
            channel for channel in ("tiktok", "instagram", "facebook", "youtube", "threads")
            if not channel_caption(item, channel)
        ]
        checks.append({
            "name": "Captions",
            "status": "OK" if not missing_captions else "MISSING",
            "detail": "All channel captions present." if not missing_captions else "Missing: " + ", ".join(missing_captions),
        })
        if date(2026, 7, 20) <= tomorrow <= date(2026, 7, 26):
            if tomorrow.isoformat() in upload_log:
                detail = "yt_upload_log has an API-scheduled video."
                status = "OK"
            elif channel_caption(item, "youtube") and isinstance(item.get("reel"), str):
                detail = "Manifest contains a YouTube upload plan (not yet in yt_upload_log)."
                status = "PLAN"
            else:
                detail = "Neither yt_upload_log nor a complete YouTube plan is present."
                status = "MISSING"
            checks.append({"name": "YouTube plan", "status": status, "detail": detail})

    # TikTok lets you schedule ~10 days ahead, and every clip is uploaded by hand (no-bot-post
    # policy).  Derive the open window from the manifest instead of a hardcoded July date set:
    # the old set covered only 23-26 Jul and silently stopped being useful on 27 Jul, leaving a
    # note that could never fire again.  Manifest-derived means this keeps working for batch 4, 5...
    horizon_end = checked_at.date() + timedelta(days=10)
    planned_all: list[date] = []
    for entry in items:
        raw = entry.get("date")
        if not isinstance(raw, str):
            continue
        try:
            planned_all.append(date.fromisoformat(raw))
        except ValueError:
            continue
    planned_days = sorted({d for d in planned_all if checked_at.date() <= d <= horizon_end})
    last_planned = max(planned_all, default=None)
    if tiktok_policy["state"] == "retired":
        tiktok_note = "TikTok is RETIRED by policy -- no scheduling or verification action."
    elif tiktok_policy["state"] == "testing_blocked":
        tiktok_note = (
            "TikTok is TESTING_BLOCKED -- the 14-day runway is a local reservation only; "
            "do not upload, schedule, or publish."
        )
    elif tiktok_policy["state"] == "paused":
        tiktok_note = (
            f"TikTok is PAUSED by policy until {tiktok_policy.get('until', 'invalid')} -- "
            "no scheduling action."
        )
    elif planned_days:
        tiktok_note = (
            "TikTok manual scheduling window is open for: "
            + ", ".join(day.isoformat() for day in planned_days)
            + ". Schedule once if not already set."
        )
    else:
        tiktok_note = (
            f"No planned clip inside the next 10 days; manifest ends {last_planned.isoformat()} -- produce the next batch."
            if last_planned
            else "Manifest has no dated clips -- produce the next batch."
        )

    # EARLY WARNING for the content cliff.  One manifest feeds four channels at once (Threads
    # daily, TikTok nudge, YouTube Shorts, FB Reel), so when it runs out they all go quiet on the
    # same day.  Producing a batch takes days, so warning only after the clip queue is empty is
    # too late -- surface it while there is still runway.  Escalates as the deadline approaches.
    runway_note = None
    if last_planned is not None:
        days_left = (last_planned - checked_at.date()).days
        if days_left < 0:
            runway_note = f"CONTENT CLIFF: manifest ended {last_planned.isoformat()} -- Threads/TikTok/YouTube/FB Reel have no clips."
        elif days_left <= 3:
            runway_note = f"CONTENT CLIFF in {days_left} day(s) (manifest ends {last_planned.isoformat()}) -- 4 channels go quiet together. Produce the next batch now."
        elif days_left <= 10:
            runway_note = f"Clip runway: {days_left} days left (manifest ends {last_planned.isoformat()}). Start the next batch."
    payload = {"date": tomorrow.isoformat(), "checks": checks, "tiktok_schedule_note": tiktok_note}
    if runway_note:
        payload["content_runway_note"] = runway_note
    return payload


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Post guard — {payload['checked_date']}",
        "",
        f"ตรวจเมื่อ: {payload['checked_at']} (Asia/Bangkok)",
        "",
        "| ช่อง | สถานะ | หลักฐาน | การแก้ไขที่ทำไป |",
        "|---|---|---|---|",
    ]
    for channel in payload["channels"]:
        lines.append(
            "| {channel} | {status} | {evidence} | {action} |".format(
                channel=markdown_cell(channel["channel"]),
                status=markdown_cell(channel["status"]),
                evidence=markdown_cell(channel["evidence"]),
                action=markdown_cell(channel["action"]),
            )
        )
    lines.extend(["", f"ผลรวม: {'FAIL พบ' if payload['has_fail'] else 'ไม่พบ FAIL'} (exit {payload['exit_code']})"])
    readiness = payload.get("tomorrow")
    if readiness:
        lines.extend(["", f"## ความพร้อมวันถัดไป ({readiness['date']})", ""])
        for check in readiness["checks"]:
            lines.append(f"- {check['name']}: {check['status']} — {check['detail']}")
        lines.extend(["", f"- TikTok: {readiness['tiktok_schedule_note']}"])
        runway = readiness.get("content_runway_note")
        if runway:
            lines.append(f"- ⚠️ คลังคลิป: {runway}")
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any]) -> Path:
    POST_GUARD_DIR.mkdir(parents=True, exist_ok=True)
    status_path = POST_GUARD_DIR / f"status-{payload['checked_date']}.md"
    status_path.write_text(render_markdown(payload), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8", newline="\n") as history:
        history.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return status_path


def main() -> int:
    args = parse_args()
    checked_at = now_bangkok()
    target = args.target_date
    try:
        tiktok_policy = load_channel_policy("tiktok")
        instagram_policy = load_channel_policy("instagram")
        items = load_manifest()
        upload_log = load_upload_log()
    except GuardSetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        return 2

    item = item_for(items, target)
    content_id = item.get("id") if isinstance(item, dict) else None
    facebook_publication_gate = evaluate_publication_authority(
        checked_at, channel="facebook", content_id=content_id
    )
    threads_publication_gate = evaluate_publication_authority(
        checked_at, channel="threads", content_id=content_id
    )
    youtube_action = "-"
    if args.repair_youtube:
        if item is None:
            print(
                f"REPAIR ERROR: manifest has no item for exact target {target.isoformat()}",
                file=sys.stderr,
            )
            return 2
        if target.isoformat() in upload_log:
            youtube_action = (
                f"No repair needed: yt_upload_log already contains exact target {target.isoformat()}."
            )
        else:
            try:
                youtube_policy = load_channel_policy("youtube")
                schedule = load_reel_schedule()
                youtube_action = run_youtube_recovery(
                    target,
                    checked_at,
                    item=item,
                    youtube_policy=youtube_policy,
                    schedule=schedule,
                    actor=args.actor,
                    receipt_nonce=args.receipt_nonce,
                )
                upload_log = load_upload_log()
            except (GuardSetupError, YouTubeRepairError) as exc:
                print(f"REPAIR ERROR: {exc}", file=sys.stderr)
                return 2
            if target.isoformat() not in upload_log:
                print(
                    "REPAIR ERROR: live helper exited successfully but the exact target "
                    f"{target.isoformat()} is still absent from yt_upload_log",
                    file=sys.stderr,
                )
                return 2

    channels = [
        check_youtube(target, item, upload_log, checked_at),
        check_instagram(target, item, instagram_policy),
        check_facebook(target, item, facebook_publication_gate),
        check_facebook_comment(target),
        check_tiktok(target, item, checked_at, tiktok_policy),
        check_threads(target, item, threads_publication_gate),
    ]
    if youtube_action != "-":
        channels[0]["action"] = youtube_action
    # Statuses that mean "a human must do something today".  Before 30 Jul this only
    # matched the literal "FAIL", so the new actionable verdicts would have been
    # reported in the body while the summary line said "ไม่พบ FAIL" -- a guard
    # contradicting itself is how a dead channel stays dead for five days.
    # SOURCE-SIDE is deliberately NOT here: it means we did our part and only the
    # platform-side confirmation is unavailable.
    has_fail = any(channel["status"] in ACTION_REQUIRED for channel in channels)
    payload: dict[str, Any] = {
        "checked_date": target.isoformat(),
        "checked_at": iso_timestamp(checked_at),
        "timezone": "Asia/Bangkok",
        "channels": channels,
        "has_fail": has_fail,
        "exit_code": 2 if has_fail else 0,
    }
    if args.check_tomorrow:
        payload["tomorrow"] = readiness_preview(
            target, items, upload_log, checked_at, tiktok_policy
        )
    status_path = write_outputs(payload)
    payload["status_report"] = status_path.relative_to(ROOT).as_posix()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(f"Post guard {target.isoformat()} ({payload['timezone']}):")
        for channel in channels:
            print(f"- {channel['channel']}: {channel['status']} — {channel['evidence']}")
        print(f"Report: {payload['status_report']}")
    return payload["exit_code"]


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
