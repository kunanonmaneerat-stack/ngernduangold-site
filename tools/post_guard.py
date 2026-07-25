#!/usr/bin/env python3
"""Nightly, read-mostly verification for the ngernduangold posting plan.

The guard deliberately uses local evidence when a channel has no safe read API.
It never sends a social post.  The only permitted write-side channel action is
the narrowly scoped YouTube batch-2 recovery for 2026-07-26 and later.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
AUTOMATION_LOG = ROOT / "automation-log"
MANIFEST_PATH = ROOT / ".system_control" / "content_manifest.json"
YT_UPLOAD_LOG_PATH = ROOT / ".system_control" / "yt_upload_log.json"
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
# Channel paused by decision 25 Jul 2026 (see automation-log/CHANNEL-DECISION_20260725.md).
IG_PAUSED_FROM = date(2026, 7, 26)
IG_PAUSED_UNTIL = date(2026, 8, 25)
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
    args = parser.parse_args()
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


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GuardSetupError(f"{label} not found: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise GuardSetupError(f"{label} is not valid JSON: {path.relative_to(ROOT)} ({exc.msg})") from exc


def load_manifest() -> list[dict[str, Any]]:
    document = read_json(MANIFEST_PATH, "Content manifest")
    items = document.get("items") if isinstance(document, dict) else document
    if not isinstance(items, list):
        raise GuardSetupError("Content manifest must be a list or contain an 'items' list.")
    return [item for item in items if isinstance(item, dict)]


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
    normalized = value.casefold()
    if "scheduled" in normalized:
        return result(channel, "SCHEDULED-UI", f"(จาก manifest: {value})")
    if "posted" in normalized:
        return result(channel, "POSTED", "(จาก manifest)")
    return None


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
        payload = json.loads(content)
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
        raise YouTubeUnavailable("cached YouTube token is invalid or expired; guard will not rewrite it")
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def expected_youtube_time(target: date) -> datetime:
    return datetime.combine(target, time(19, 0), tzinfo=BANGKOK)


def check_logged_youtube(target: date, video_id: str, checked_at: datetime) -> dict[str, str]:
    try:
        service = youtube_service()
        response = service.videos().list(part="status,snippet", id=video_id).execute()
    except Exception as exc:
        detail = http_error_detail(exc) if hasattr(exc, "resp") else str(exc)
        return result("YOUTUBE", "UNKNOWN", f"yt_upload_log has a video ID, but API check is unavailable: {detail}")

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
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()[-100:]
    except OSError:
        return True
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
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


def run_youtube_recovery(target: date, checked_at: datetime) -> str:
    if not quota_likely_available(checked_at):
        return "Not attempted: a quotaExceeded result is already recorded for today."
    if not upload_token_is_safe_to_use():
        return "Not attempted: the cached YouTube token is unavailable/expired; guard will not rewrite secrets."
    launcher = shutil.which("py") or sys.executable
    command = [launcher, str(ROOT / "tools" / "yt_upload_batch2.py"), "--live", "--limit", "1"]
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
        return f"Recovery command could not complete: {type(exc).__name__}."
    # Do not copy subprocess output into a report: it is unnecessary for the
    # guard result and may expose future helper diagnostics.
    output = (completed.stdout + "\n" + completed.stderr).casefold()
    if "quotaexceeded" in output:
        return "YouTube recovery stopped on quotaExceeded; re-verified afterward."
    if completed.returncode == 0:
        return f"Ran YouTube recovery for {target.isoformat()} (exit 0); re-verified afterward."
    return f"YouTube recovery ran (exit {completed.returncode}); re-verified afterward."


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


def check_instagram(target: date, item: dict[str, Any] | None) -> dict[str, str]:
    # IG paused on purpose 26 Jul - 25 Aug 2026.  Evidence (GA4, 28d): ig = 1 session,
    # 0 conversions from 5 posts, vs pantip 29 sessions from 2 items.  See
    # automation-log/CHANNEL-DECISION_20260725.md.  A silent IG channel in this window is
    # the plan working, not a failure -- reporting BLOCKED here produced a daily false alarm
    # that also asked the owner to supply Meta credentials, which they permanently revoked
    # on 18 Jul 2026.  Never surface a token prompt for IG again.
    if IG_PAUSED_FROM <= target <= IG_PAUSED_UNTIL:
        return result(
            "INSTAGRAM",
            "PAUSED",
            f"IG paused by decision until {IG_PAUSED_UNTIL.isoformat()} (GA4: 1 session / 0 conv).",
            "No action -- revisit on 25 Aug 2026.",
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


def check_facebook(target: date, item: dict[str, Any] | None) -> dict[str, str]:
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
    if POST_LEDGER_PATH.is_file():
        try:
            for raw_line in POST_LEDGER_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                if entry.get("channel") != "facebook" or entry.get("type") != "comment":
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
                if parsed.astimezone(BANGKOK).date() == target:
                    return result("FACEBOOK-COMMENT", "OK", f"comment-link in ledger {timestamp}")
        except OSError:
            pass
    return result(
        "FACEBOOK-COMMENT",
        "NONE",
        "no comment-link ledger entry today",
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
                return json.loads(script.group("body").strip())
            except json.JSONDecodeError:
                return None
    match = re.search(r"window\s*\[\s*['\"]SIGI_STATE['\"]\s*\]\s*=", page)
    if not match:
        return None
    start = match.end()
    while start < len(page) and page[start].isspace():
        start += 1
    try:
        return json.JSONDecoder().raw_decode(page[start:])[0]
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


def check_tiktok(target: date, item: dict[str, Any] | None, checked_at: datetime) -> dict[str, str]:
    if target in TIKTOK_UI_SCHEDULED_DATES and checked_at.time() < time(19, 5):
        return result("TIKTOK", "SCHEDULED-UI", "UI-scheduled through 26 Jul; public verification begins after 19:05 Asia/Bangkok.")
    prefix = clean_text(channel_caption(item, "tiktok"))[:25]
    if not prefix:
        return manifest_or_unknown(
            item,
            "TIKTOK",
            "tiktok",
            "Manifest captions.tiktok is missing; no public profile match is possible.",
        )
    page, error_name = public_profile_page("https://www.tiktok.com/@ngernduangold")
    if page is None:
        return manifest_or_unknown(
            item,
            "TIKTOK",
            "tiktok",
            f"Public profile GET was unavailable/unparseable: {error_name}",
        )
    document = tiktok_embedded_json(page)
    if document is None:
        return manifest_or_unknown(
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
    return manifest_or_unknown(
        item,
        "TIKTOK",
        "tiktok",
        "No public TikTok item matched the manifest caption prefix or target date.",
    )


def check_threads(target: date, item: dict[str, Any] | None) -> dict[str, str]:
    ledger = AUTOMATION_LOG / "post-ledger.jsonl"
    if not ledger.is_file():
        return result("THREADS", "UNKNOWN", "post-ledger.jsonl is absent.", "Ask Cowork/Threads profile.")
    wanted = target.isoformat()
    try:
        for raw_line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if str(entry.get("channel", "")).casefold() != "threads":
                continue
            # กันสับสน: knowledge-post เที่ยงเป็น type=text ช่อง threads เหมือนกัน
            # แต่ไม่ใช่คลิปรายวัน 19:00 — อย่านับ text เป็นหลักฐานว่าคลิปขึ้นแล้ว (บั๊ก 20 ก.ค.)
            if str(entry.get("type", "")).casefold() == "text":
                continue
            if wanted in json.dumps(entry, ensure_ascii=False):
                return result("THREADS", "OK", f"Threads clip entry dated {wanted} found in post-ledger.jsonl.")
    except OSError as exc:
        return result("THREADS", "UNKNOWN", f"Could not read post-ledger.jsonl: {type(exc).__name__}", "Ask Cowork/Threads profile.")
    prefix = clean_text(channel_caption(item, "threads"))[:30]
    if not prefix:
        return result("THREADS", "UNKNOWN", f"No Threads ledger entry dated {wanted}; manifest captions.threads is missing.", "Ask Cowork/Threads profile.")
    page, error_name = public_profile_page("https://www.threads.com/@ngernduangold")
    if page is None:
        return result("THREADS", "UNKNOWN", f"Public Threads profile GET was unavailable: {error_name}", "Ask Cowork/Threads profile.")
    page_text = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", page)))
    if prefix in page_text:
        return result("THREADS", "OK", "caption prefix found on public profile")
    return result("THREADS", "UNKNOWN", "Caption prefix was not found on the public Threads profile.", "Ask Cowork/Threads profile.")


def readiness_preview(target: date, items: list[dict[str, Any]], upload_log: dict[str, str], checked_at: datetime) -> dict[str, Any]:
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
    if planned_days:
        tiktok_note = (
            "TikTok manual scheduling window is open for: "
            + ", ".join(day.isoformat() for day in planned_days)
            + ". Schedule once if not already set."
        )
    else:
        last_planned = max(planned_all, default=None)
        tiktok_note = (
            f"No planned clip inside the next 10 days; manifest ends {last_planned.isoformat()} -- produce the next batch."
            if last_planned
            else "Manifest has no dated clips -- produce the next batch."
        )
    return {"date": tomorrow.isoformat(), "checks": checks, "tiktok_schedule_note": tiktok_note}


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
        items = load_manifest()
        upload_log = load_upload_log()
    except GuardSetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        return 2

    item = item_for(items, target)
    youtube_action = "-"
    if target >= AUTO_YT_FROM and target.isoformat() not in upload_log:
        youtube_action = run_youtube_recovery(target, checked_at)
        upload_log = load_upload_log()

    channels = [
        check_youtube(target, item, upload_log, checked_at),
        check_instagram(target, item),
        check_facebook(target, item),
        check_facebook_comment(target),
        check_tiktok(target, item, checked_at),
        check_threads(target, item),
    ]
    if youtube_action != "-":
        channels[0]["action"] = youtube_action
    has_fail = any(channel["status"] == "FAIL" for channel in channels)
    payload: dict[str, Any] = {
        "checked_date": target.isoformat(),
        "checked_at": iso_timestamp(checked_at),
        "timezone": "Asia/Bangkok",
        "channels": channels,
        "has_fail": has_fail,
        "exit_code": 2 if has_fail else 0,
    }
    if args.check_tomorrow:
        payload["tomorrow"] = readiness_preview(target, items, upload_log, checked_at)
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
