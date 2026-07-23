#!/usr/bin/env python3
# Requirements: py -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2
"""Schedule the seven batch-2 Shorts from the content manifest.

Dry-run is deliberately the default and performs no Google authentication.
Use --live only when the channel owner is ready to complete the OAuth consent
screen.  The YouTube token is intentionally separate from the GA4/GSC token:
it needs the YouTube upload scope and is cached in an ignored location.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".system_control" / "content_manifest.json"
UPLOAD_LOG_PATH = ROOT / ".system_control" / "yt_upload_log.json"
SECRETS_DIR = ROOT / "secrets"
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
CHANNEL_ID = "UCVuqb7l5rJ4Q7PUKSIgsL4w"
TARGET_DATES = tuple(f"2026-07-{day:02d}" for day in range(20, 27))
MAX_UPLOADS_PER_RUN = 6
TITLE_SUFFIX = " #Shorts"


class SetupError(RuntimeError):
    """The owner must make a safe, external setup change before continuing."""


class AuthUnavailable(RuntimeError):
    """A non-interactive command cannot authenticate safely."""


class QuotaExceeded(RuntimeError):
    """The Google API reported that today's quota is exhausted."""


class UploadLimitExceeded(RuntimeError):
    """The channel reported its upload limit was reached."""


@dataclass(frozen=True)
class UploadPlan:
    date: str
    item: dict[str, Any]
    video_path: Path
    relative_video_path: str
    title: str
    description: str
    publish_at: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Schedule ngernduangold batch-2 YouTube Shorts. Dry-run is the default."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the upload plan only (default; no OAuth or network calls).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Authenticate if needed and create scheduled private uploads.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Best-effort check for existing channel titles; does not upload.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_UPLOADS_PER_RUN,
        help=f"Maximum uploads in a live run (1-{MAX_UPLOADS_PER_RUN}; default %(default)s).",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= MAX_UPLOADS_PER_RUN:
        parser.error(f"--limit must be between 1 and {MAX_UPLOADS_PER_RUN}")
    return args


def load_manifest() -> tuple[dict[str, Any] | list[Any], list[dict[str, Any]]]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SetupError(f"Manifest not found: {MANIFEST_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise SetupError(f"Manifest is not valid JSON: {MANIFEST_PATH} ({exc})") from exc

    if isinstance(manifest, dict) and isinstance(manifest.get("items"), list):
        return manifest, manifest["items"]
    if isinstance(manifest, list):
        return manifest, manifest
    raise SetupError("Manifest must be a list or an object with an 'items' list.")


def make_title(caption: str) -> str:
    first_line = caption.splitlines()[0].strip() if caption.splitlines() else ""
    if not first_line:
        raise SetupError("captions.youtube has no usable first line for a YouTube title.")

    # Rebuild the suffix even when the source already has it, so truncation can
    # never remove #Shorts or exceed YouTube's 100-character title limit.
    stem = first_line
    if stem.endswith("#Shorts"):
        stem = stem[: -len("#Shorts")].rstrip()
    room_for_stem = 100 - len(TITLE_SUFFIX)
    stem = stem[:room_for_stem].rstrip()
    if not stem:
        raise SetupError("The YouTube title cannot be reduced to a non-empty title plus #Shorts.")
    return f"{stem}{TITLE_SUFFIX}"


def utc_publish_at(date: str) -> str:
    local_time = datetime.fromisoformat(f"{date}T19:00:00+07:00")
    utc_time = local_time.astimezone(timezone.utc)
    return utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_plans(items: list[dict[str, Any]]) -> list[UploadPlan]:
    by_date: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        date = item.get("date")
        if date in TARGET_DATES:
            if date in by_date:
                raise SetupError(f"Manifest has more than one item dated {date}.")
            by_date[date] = item

    missing_dates = [date for date in TARGET_DATES if date not in by_date]
    if missing_dates:
        raise SetupError("Manifest is missing batch-2 date(s): " + ", ".join(missing_dates))

    plans: list[UploadPlan] = []
    for date in TARGET_DATES:
        item = by_date[date]
        caption_data = item.get("captions")
        caption = caption_data.get("youtube") if isinstance(caption_data, dict) else None
        reel = item.get("reel")
        if not isinstance(caption, str) or not caption.strip():
            raise SetupError(f"{date}: captions.youtube is missing or empty.")
        if not isinstance(reel, str) or not reel.strip():
            raise SetupError(f"{date}: reel path is missing or empty.")

        candidate = Path(reel)
        if candidate.is_absolute():
            raise SetupError(f"{date}: reel must be repository-relative, not absolute: {reel}")
        video_path = (ROOT / candidate).resolve()
        try:
            relative_video_path = video_path.relative_to(ROOT).as_posix()
        except ValueError as exc:
            raise SetupError(f"{date}: reel resolves outside the repository: {reel}") from exc
        if not video_path.is_file():
            raise SetupError(f"{date}: video file does not exist: {relative_video_path}")

        plans.append(
            UploadPlan(
                date=date,
                item=item,
                video_path=video_path,
                relative_video_path=relative_video_path,
                title=make_title(caption),
                description=caption,
                publish_at=utc_publish_at(date),
            )
        )
    return plans


def description_preview(description: str) -> str:
    return description.replace("\r\n", "\n").replace("\n", " ")[:80]


def print_plan(plans: list[UploadPlan]) -> None:
    print(f"Planned batch-2 Shorts: {len(plans)}")
    for plan in plans:
        print(
            f"PLAN {plan.date} | file={plan.relative_video_path} | "
            f"title={plan.title} | publishAt={plan.publish_at} | "
            f"description_first_80={description_preview(plan.description)}"
        )


def load_upload_log() -> dict[str, str]:
    if not UPLOAD_LOG_PATH.exists():
        return {}
    try:
        data = json.loads(UPLOAD_LOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SetupError(f"Upload log is not valid JSON: {UPLOAD_LOG_PATH} ({exc})") from exc
    if not isinstance(data, dict) or not all(
        isinstance(date, str) and isinstance(video_id, str) for date, video_id in data.items()
    ):
        raise SetupError("Upload log must be an object in the form {date: videoId}.")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(path)


def save_manifest(manifest: dict[str, Any] | list[Any]) -> None:
    # The manifest currently uses UTF-8 and two-space JSON indentation; keep it
    # in that format whenever a successful upload changes posted.youtube.
    write_json(MANIFEST_PATH, manifest)


def git_ignores(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(path.relative_to(ROOT))],
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, ValueError):
        return False
    return result.returncode == 0


def token_cache_path() -> Path:
    repo_cache = SECRETS_DIR / "yt_token.json"
    if git_ignores(repo_cache):
        return repo_cache
    profile = Path(os.environ.get("USERPROFILE", Path.home()))
    return profile / ".ngernduangold" / "yt_token.json"


def is_installed_app_client(path: Path) -> bool:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(document, dict) and isinstance(document.get("installed"), dict)


def find_oauth_client() -> Path | None:
    preferred = (
        SECRETS_DIR / "yt-client.json",
        SECRETS_DIR / "yt_client.json",
        SECRETS_DIR / "youtube-client.json",
        SECRETS_DIR / "youtube_client.json",
        # Recon found this existing Desktop client. It is a safe reusable OAuth
        # client only after YouTube Data API v3 is enabled in its Cloud project.
        SECRETS_DIR / "ga4-client.json",
    )
    candidates = list(preferred)
    if SECRETS_DIR.exists():
        candidates.extend(sorted(SECRETS_DIR.glob("*client*.json")))
        candidates.extend(sorted(SECRETS_DIR.glob("client_secret*.json")))

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file() and is_installed_app_client(candidate):
            return candidate
    return None


def client_setup_message() -> str:
    return (
        "No OAuth Desktop client JSON was found. Create a Desktop app OAuth client in "
        "Google Cloud Console with YouTube Data API v3 enabled, then save its downloaded "
        "JSON as secrets/yt-client.json (or secrets/youtube-client.json)."
    )


def require_google_libraries() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise SetupError(
            "Missing Google API libraries. Install: py -m pip install --user "
            "google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload


def get_credentials(interactive: bool) -> tuple[Any, tuple[Any, Any, Any, Any, Any, Any]]:
    client_path = find_oauth_client()
    if client_path is None:
        raise SetupError(client_setup_message())
    libraries = require_google_libraries()
    Request, Credentials, InstalledAppFlow, _build, _HttpError, _MediaFileUpload = libraries
    cache_path = token_cache_path()
    credentials = None

    if cache_path.exists():
        try:
            credentials = Credentials.from_authorized_user_file(cache_path, [YOUTUBE_SCOPE])
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                write_json(cache_path, json.loads(credentials.to_json()))
            if credentials.valid and credentials.has_scopes([YOUTUBE_SCOPE]):
                return credentials, libraries
        except Exception as exc:  # A bad cache should be replaced by explicit consent, never guessed.
            if not interactive:
                raise AuthUnavailable(f"Cached YouTube token could not be used: {exc}") from exc
            credentials = None

    if not interactive:
        raise AuthUnavailable(
            "No valid cached YouTube upload token. Run --live as the channel owner to consent."
        )

    print(f"OAuth consent is required. Opening the browser with Desktop client: {client_path}")
    flow = InstalledAppFlow.from_client_secrets_file(client_path, [YOUTUBE_SCOPE])
    credentials = flow.run_local_server(port=0, prompt="consent")
    write_json(cache_path, json.loads(credentials.to_json()))
    print(f"Saved YouTube token cache: {cache_path}")
    return credentials, libraries


def error_reason(error: Any) -> str:
    content = getattr(error, "content", b"")
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        payload = json.loads(content)
        errors = payload.get("error", {}).get("errors", [])
        if errors and isinstance(errors[0], dict):
            return str(errors[0].get("reason", "unknown"))
    except (TypeError, ValueError, AttributeError):
        pass
    return "unknown"


def http_status(error: Any) -> int | None:
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    return status if isinstance(status, int) else None


def resumable_upload(request: Any, http_error_type: Any) -> dict[str, Any]:
    retries = 0
    while True:
        try:
            _status, response = request.next_chunk()
            if response is not None:
                return response
        except http_error_type as exc:
            reason = error_reason(exc)
            status = http_status(exc)
            if reason == "quotaExceeded":
                raise QuotaExceeded from exc
            if reason == "uploadLimitExceeded":
                raise UploadLimitExceeded from exc
            if status is not None and 500 <= status < 600 and retries < 3:
                retries += 1
                delay_seconds = 2**retries
                print(f"YouTube returned HTTP {status}; retry {retries}/3 in {delay_seconds}s.")
                time.sleep(delay_seconds)
                continue
            raise
        except OSError as exc:
            if retries < 3:
                retries += 1
                delay_seconds = 2**retries
                print(f"Network error; retry {retries}/3 in {delay_seconds}s.")
                time.sleep(delay_seconds)
                continue
            raise RuntimeError("Network failed after 3 retries.") from exc


def print_remaining(plans: list[UploadPlan], upload_log: dict[str, str]) -> None:
    remaining = [plan.date for plan in plans if plan.date not in upload_log]
    if remaining:
        print("Remaining (not in yt_upload_log.json): " + ", ".join(remaining))
    else:
        print("Remaining (not in yt_upload_log.json): none")


def run_check(plans: list[UploadPlan]) -> int:
    try:
        credentials, libraries = get_credentials(interactive=False)
    except (SetupError, AuthUnavailable) as exc:
        print(f"CHECK SKIPPED (authentication unavailable): {exc}")
        return 0

    _Request, _Credentials, _InstalledAppFlow, build, HttpError, _MediaFileUpload = libraries
    try:
        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        print(f"Checking {len(plans)} exact titles on channel {CHANNEL_ID} (best effort).")
        found_any = False
        for plan in plans:
            response = service.search().list(
                part="snippet",
                channelId=CHANNEL_ID,
                type="video",
                q=plan.title,
                maxResults=50,
            ).execute()
            matches = [
                item
                for item in response.get("items", [])
                if item.get("snippet", {}).get("title") == plan.title
            ]
            if matches:
                found_any = True
                ids = ", ".join(
                    str(item.get("id", {}).get("videoId", "unknown")) for item in matches
                )
                print(f"CHECK FOUND {plan.date}: {ids}")
            else:
                print(f"CHECK clear {plan.date}: no exact title match")
        if not found_any:
            print("CHECK RESULT: no exact-title duplicates found (best effort only).")
        return 0
    except HttpError as exc:
        reason = error_reason(exc)
        if reason == "quotaExceeded":
            print("CHECK INCOMPLETE: YouTube quota exceeded; continue or retry tomorrow.")
        else:
            print(f"CHECK INCOMPLETE: YouTube API error HTTP {http_status(exc) or 'unknown'} ({reason}).")
        return 0
    except OSError as exc:
        print(f"CHECK INCOMPLETE: network error ({exc}).")
        return 0


def upload_body(plan: UploadPlan) -> dict[str, Any]:
    return {
        "snippet": {
            "title": plan.title,
            "description": plan.description,
            "categoryId": "27",
            "defaultLanguage": "th",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": plan.publish_at,
            "selfDeclaredMadeForKids": False,
        },
    }


def run_live(
    manifest: dict[str, Any] | list[Any], plans: list[UploadPlan], limit: int
) -> int:
    upload_log = load_upload_log()
    pending = [plan for plan in plans if plan.date not in upload_log]
    skipped = [plan for plan in plans if plan.date in upload_log]
    for plan in skipped:
        print(f"SKIP {plan.date}: already logged as {upload_log[plan.date]}")

    selected = pending[:limit]
    deferred = pending[limit:]
    if deferred:
        print(
            "Deferred by per-run quota guard: " + ", ".join(plan.date for plan in deferred)
        )
    if not selected:
        print("No unlogged batch-2 uploads remain.")
        print_remaining(plans, upload_log)
        return 0

    try:
        credentials, libraries = get_credentials(interactive=True)
    except SetupError as exc:
        print(f"LIVE UPLOAD NOT STARTED: {exc}")
        print_remaining(plans, upload_log)
        return 1

    _Request, _Credentials, _InstalledAppFlow, build, HttpError, MediaFileUpload = libraries
    service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    failed = False

    for plan in selected:
        print(f"UPLOAD {plan.date}: {plan.relative_video_path} -> {plan.publish_at}")
        try:
            media = MediaFileUpload(
                str(plan.video_path), mimetype="video/mp4", chunksize=-1, resumable=True
            )
            request = service.videos().insert(
                part="snippet,status", body=upload_body(plan), media_body=media
            )
            response = resumable_upload(request, HttpError)
            video_id = response.get("id")
            if not isinstance(video_id, str) or not video_id:
                raise RuntimeError("YouTube returned no video ID after a completed upload.")

            # Log first: if a later filesystem interruption occurs, a rerun will
            # skip the date rather than risk creating a duplicate scheduled video.
            upload_log[plan.date] = video_id
            write_json(UPLOAD_LOG_PATH, upload_log)
            posted = plan.item.get("posted")
            if not isinstance(posted, dict):
                posted = {}
                plan.item["posted"] = posted
            posted["youtube"] = f"scheduled (yt-api {video_id})"
            save_manifest(manifest)
            print(f"SUCCESS {plan.date}: videoId={video_id}")
            try:  # C-fix 23Jul: confirmed post must reach post-ledger (never breaks upload flow)
                from clip_ledger import append_row
                print(f"LEDGER_{append_row('youtube', plan.date)} {plan.date}")
            except Exception as exc:
                print(f"LEDGER_WARN {plan.date}: {exc}")
        except QuotaExceeded:
            print("STOP: YouTube quotaExceeded. Resume tomorrow; no more uploads were attempted.")
            break
        except UploadLimitExceeded:
            print("STOP: YouTube uploadLimitExceeded. Resume after the channel upload limit resets.")
            break
        except HttpError as exc:
            failed = True
            print(
                f"FAILED {plan.date}: YouTube API error HTTP {http_status(exc) or 'unknown'} "
                f"({error_reason(exc)})."
            )
        except (OSError, RuntimeError) as exc:
            failed = True
            print(f"FAILED {plan.date}: {exc}")

    print_remaining(plans, upload_log)
    return 1 if failed else 0


def main() -> int:
    args = parse_args()
    try:
        manifest, items = load_manifest()
        plans = build_plans(items)
        upload_log = load_upload_log()
    except SetupError as exc:
        print(f"SETUP ERROR: {exc}")
        return 1

    if args.check:
        return run_check(plans)

    print_plan(plans)
    if not args.live:
        print("DRY RUN ONLY: no OAuth, API calls, uploads, manifest changes, or token writes.")
        print_remaining(plans, upload_log)
        return 0

    return run_live(manifest, plans, args.limit)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
