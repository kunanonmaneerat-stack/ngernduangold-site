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
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from tools import content_source_gate, media_publish_guard
    from tools.publication_authority import (
        PublicationBlocked,
        authorize_live_publication,
        verify_execution_authorization,
    )
except ImportError:  # Direct ``py tools/yt_upload_batch2.py`` execution.
    import content_source_gate
    import media_publish_guard
    from publication_authority import (
        PublicationBlocked,
        authorize_live_publication,
        verify_execution_authorization,
    )


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation-log"))
import post_ledger
MANIFEST_PATH = ROOT / ".system_control" / "content_manifest.json"
UPLOAD_LOG_PATH = ROOT / ".system_control" / "yt_upload_log.json"
SECRETS_DIR = ROOT / "secrets"
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
# Default window kept for backwards compatibility (batch-2). Any other batch is
# selected with --dates / --from / --to so this uploader is not batch-specific.
# Added 30 Jul 2026: batch3 (b3-01..b3-07) could not be uploaded because this
# constant silently excluded every date outside 20-26 Jul -> the script reported
# "manifest is missing batch-2 dates" instead of uploading the clips that existed.
DEFAULT_TARGET_DATES = tuple(f"2026-07-{day:02d}" for day in range(20, 27))
TARGET_DATES = DEFAULT_TARGET_DATES  # rebound from CLI in main()
MAX_UPLOADS_PER_RUN = 6
TITLE_SUFFIX = " #Shorts"
BANGKOK = timezone(timedelta(hours=7))
ATTEMPT_ROOT = ROOT / ".local-private" / "runtime" / "publication-attempts"
YOUTUBE_REMOTE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{6,64}\Z")
MAX_IMMUTABLE_UPLOAD_BYTES = 256 * 1024 * 1024


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


def _parse_receipt_nonce_bindings(values: list[str]) -> dict[str, str]:
    """Parse repeatable ``YYYY-MM-DD=nonce`` bindings without exposing nonces."""
    bindings: dict[str, str] = {}
    for raw in values:
        if not isinstance(raw, str) or "=" not in raw:
            raise SetupError("--receipt-nonce must use YYYY-MM-DD=nonce")
        raw_date, nonce = raw.split("=", 1)
        try:
            normalized_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date().isoformat()
        except ValueError as exc:
            raise SetupError("--receipt-nonce date must use YYYY-MM-DD") from exc
        if not nonce.strip():
            raise SetupError("--receipt-nonce value must be non-empty")
        if normalized_date in bindings:
            raise SetupError("--receipt-nonce contains a duplicate date")
        bindings[normalized_date] = nonce.strip()
    return bindings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Schedule ngernduangold YouTube Shorts from the manifest. Dry-run is the default."
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
    parser.add_argument(
        "--dates",
        default=None,
        help="Comma-separated YYYY-MM-DD list to upload instead of the default batch-2 window.",
    )
    parser.add_argument(
        "--actor",
        default=None,
        help=(
            "Actor key from .system_control/role_capabilities.json. "
            "Required with --live; never inferred as owner."
        ),
    )
    parser.add_argument(
        "--target-channel-id",
        default=None,
        help=(
            "Exact YouTube channel target. Required with --live and must match "
            ".system_control/policy.json; the value is never printed."
        ),
    )
    parser.add_argument(
        "--receipt-nonce",
        action="append",
        default=[],
        metavar="YYYY-MM-DD=NONCE",
        help=(
            "Private one-time publication receipt binding. Repeat exactly once for "
            "each --dates item; nonce values are never printed."
        ),
    )
    parser.add_argument(
        "--from",
        dest="date_from",
        default=None,
        help="Start of an inclusive YYYY-MM-DD range (use with --to).",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        default=None,
        help="End of an inclusive YYYY-MM-DD range (use with --from).",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_UPLOADS_PER_RUN:
        parser.error(f"--limit must be between 1 and {MAX_UPLOADS_PER_RUN}")
    if args.dates and (args.date_from or args.date_to):
        parser.error("use either --dates or --from/--to, not both")
    if bool(args.date_from) != bool(args.date_to):
        parser.error("--from and --to must be used together")
    if args.live and not args.dates:
        parser.error("--live requires explicit --dates; default or range backfills are read-only only")
    if args.live and not isinstance(args.actor, str):
        parser.error("--live requires explicit --actor from role_capabilities.json")
    if args.live and not args.actor.strip():
        parser.error("--live requires a non-empty --actor")
    if args.live and not isinstance(args.target_channel_id, str):
        parser.error("--live requires explicit --target-channel-id")
    if args.live and not args.target_channel_id.strip():
        parser.error("--live requires a non-empty --target-channel-id")
    try:
        args.receipt_nonces = _parse_receipt_nonce_bindings(args.receipt_nonce)
    except SetupError as exc:
        parser.error(str(exc))
    if args.live:
        requested_dates = {
            value.strip() for value in str(args.dates).split(",") if value.strip()
        }
        if set(args.receipt_nonces) != requested_dates:
            parser.error(
                "--live requires exactly one --receipt-nonce YYYY-MM-DD=NONCE "
                "for every --dates item"
            )
    elif args.receipt_nonces:
        parser.error("--receipt-nonce is accepted only with --live")
    return args


def resolve_target_dates(args: argparse.Namespace) -> tuple[str, ...]:
    """Turn CLI date options into the tuple build_plans() filters on."""
    import datetime as _dt

    def _parse(label: str, value: str) -> _dt.date:
        try:
            return _dt.date.fromisoformat(value.strip())
        except ValueError:
            raise SetupError(f"{label} must be YYYY-MM-DD, got {value!r}") from None

    if args.dates:
        out = tuple(_parse("--dates", d).isoformat() for d in args.dates.split(",") if d.strip())
        if not out:
            raise SetupError("--dates was empty")
        if len(set(out)) != len(out):
            raise SetupError("--dates contains a duplicate date")
        return out
    if args.date_from:
        start, end = _parse("--from", args.date_from), _parse("--to", args.date_to)
        if end < start:
            raise SetupError("--to must not be earlier than --from")
        span = (end - start).days + 1
        if span > 31:
            raise SetupError(f"date range too wide ({span} days); cap is 31")
        return tuple((start + _dt.timedelta(days=i)).isoformat() for i in range(span))
    return DEFAULT_TARGET_DATES


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


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SetupError(f"{label} not found: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError(f"{label} is unreadable or invalid JSON: {path}") from exc
    if not isinstance(document, dict):
        raise SetupError(f"{label} must be a JSON object: {path}")
    return document


def _configured_youtube_channel_id(channel_policy: Any) -> str:
    """Return the SSOT target without ever formatting its value into an error."""
    if not isinstance(channel_policy, dict):
        raise SetupError("Policy is missing channels.youtube")
    configured = channel_policy.get("channel_id")
    if not isinstance(configured, str) or not configured.strip():
        raise SetupError("Policy channels.youtube.channel_id is missing")
    return configured.strip()


def validate_youtube_target_identity(
    channel_policy: Any, target_channel_id: str | None
) -> str:
    """Bind a requested live target to policy before OAuth or network access."""
    configured = _configured_youtube_channel_id(channel_policy)
    if not isinstance(target_channel_id, str) or not target_channel_id.strip():
        raise SetupError("Live YouTube target channel identity is missing")
    if target_channel_id.strip() != configured:
        raise SetupError("Live YouTube target channel does not match policy")
    return configured


def verify_authenticated_youtube_channel(service: Any, expected_channel_id: str) -> None:
    """Fail closed unless OAuth belongs to the one policy-authorized channel."""
    if not isinstance(expected_channel_id, str) or not expected_channel_id.strip():
        raise SetupError("Authorized YouTube channel identity is missing")
    try:
        response = service.channels().list(part="id", mine=True, maxResults=2).execute()
    except Exception as exc:
        raise SetupError(
            "Authenticated YouTube channel identity could not be verified"
        ) from exc
    items = response.get("items") if isinstance(response, dict) else None
    if not isinstance(items, list) or len(items) != 1:
        raise SetupError("Authenticated YouTube channel identity is unavailable or ambiguous")
    actual = items[0].get("id") if isinstance(items[0], dict) else None
    if not isinstance(actual, str) or not actual.strip():
        raise SetupError("Authenticated YouTube channel identity is unavailable or ambiguous")
    if actual.strip() != expected_channel_id.strip():
        raise SetupError("Authenticated YouTube channel does not match policy")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SetupError(f"Cannot hash live asset: {path}") from exc
    return digest.hexdigest().upper()


def _hash_bound_upload_buffer(path: Path, expected_hash: object) -> tuple[io.BytesIO, str]:
    """Snapshot exact authorized bytes into a private in-memory upload object.

    Google resumable uploads read their media body after request construction.
    Passing the mutable source path leaves a check/use race; this buffer is the
    exact object whose SHA-256 was authorized and later uploaded.
    """
    expected = str(expected_hash or "").strip().upper()
    if re.fullmatch(r"[0-9A-F]{64}", expected) is None:
        raise PublicationBlocked("YouTube upload authority has no valid asset SHA-256")
    try:
        selected = Path(path).resolve(strict=True)
        before = selected.stat()
        if not selected.is_file() or before.st_size <= 0:
            raise PublicationBlocked("YouTube upload asset is not a non-empty regular file")
        if before.st_size > MAX_IMMUTABLE_UPLOAD_BYTES:
            raise PublicationBlocked("YouTube upload asset exceeds immutable buffer limit")
        payload = selected.read_bytes()
        after = selected.stat()
    except PublicationBlocked:
        raise
    except OSError as exc:
        raise PublicationBlocked("YouTube upload asset is unreadable") from exc
    if (
        len(payload) != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise PublicationBlocked("YouTube upload asset changed while snapshotting")
    actual = hashlib.sha256(payload).hexdigest().upper()
    if actual != expected:
        raise PublicationBlocked("YouTube immutable upload bytes do not match authority")
    return io.BytesIO(payload), actual


def _attempt_paths(placement_id: object) -> tuple[Path, Path]:
    value = str(placement_id or "").strip()
    if not value:
        raise PublicationBlocked("placement_id is required for durable attempt state")
    key = hashlib.sha256(("youtube\0" + value).encode("utf-8")).hexdigest()
    return (
        ATTEMPT_ROOT / "pending" / "youtube" / (key + ".json"),
        ATTEMPT_ROOT / "terminal" / "youtube" / (key + ".json"),
    )


def _write_exclusive_json(path: Path, value: object) -> None:
    selected = Path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    try:
        descriptor = os.open(selected, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PublicationBlocked(
            "durable publication state already exists; automatic retry is disabled; "
            "reconciliation-only"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            selected.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _assert_reconciliation_clear(placement_id: object) -> None:
    pending, terminal = _attempt_paths(placement_id)
    if pending.exists() or terminal.exists():
        raise PublicationBlocked(
            "a durable YouTube attempt/terminal receipt already exists; automatic retry "
            "is disabled; reconciliation-only"
        )


def _begin_attempt(action: Mapping[str, object]) -> None:
    pending, _terminal = _attempt_paths(action.get("placement_id"))
    _write_exclusive_json(
        pending,
        {
            "schema_version": 1,
            "status": "PENDING_REMOTE",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "action": dict(action),
        },
    )


def _finish_attempt(
    action: Mapping[str, object],
    status: str,
    *,
    remote_platform_id: str = "",
    reason: str = "",
) -> None:
    if status not in {"POSTED", "UNKNOWN"}:
        raise PublicationBlocked("YouTube attempt terminal status is invalid")
    normalized = str(remote_platform_id or "").strip()
    if status == "POSTED" and YOUTUBE_REMOTE_ID_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked("YouTube POSTED requires a valid remote video id")
    if status == "UNKNOWN" and normalized:
        raise PublicationBlocked("YouTube UNKNOWN cannot assert a remote video id")
    _pending, terminal = _attempt_paths(action.get("placement_id"))
    _write_exclusive_json(
        terminal,
        {
            "schema_version": 1,
            "status": status,
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "action": dict(action),
            "remote_platform_id": normalized or None,
            "permalink": None,
            "reason": str(reason or "")[:500] or None,
            "details": {},
        },
    )


def _parse_aware_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SetupError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise SetupError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise SetupError(f"{label} must include a timezone")
    return parsed


def _run_privacy_guard(repo: Path) -> int:
    try:
        completed = subprocess.run(
            [sys.executable, str(repo / "tools" / "privacy_guard.py")],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 2
    return completed.returncode


def _run_media_publish_guard(asset: Path, report: Path, repo: Path) -> dict[str, Any]:
    try:
        result = media_publish_guard.evaluate(asset, report, repo=repo)
    except Exception as exc:
        raise SetupError(f"media_publish_guard could not evaluate the asset: {exc}") from exc
    if not isinstance(result, dict):
        raise SetupError("media_publish_guard returned an invalid result")
    return result


def validate_live_upload(
    plans: list[UploadPlan],
    *,
    explicit_dates: bool,
    actor: str | None,
    target_channel_id: str | None,
    receipt_nonces: Mapping[str, str] | None,
    checked_at: datetime | None = None,
    repo: Path = ROOT,
    schedule_document: dict[str, Any] | None = None,
    policy_document: dict[str, Any] | None = None,
    role_document: dict[str, Any] | None = None,
    source_document: dict[str, Any] | None = None,
    content_source_check: Any = None,
    privacy_check: Any = None,
    media_guard: Any = None,
    authority_guard_runner: Any = None,
) -> dict[str, dict[str, Any]]:
    """Consume exact private receipts and return one bound action per plan.

    Everything here is local and must pass before OAuth libraries, credentials,
    browser consent, or a YouTube service object are touched. Dry-run/check modes
    do not call this gate and retain their historical planning behaviour.
    """
    if not explicit_dates:
        raise SetupError("live upload requires explicit --dates; defaults/ranges cannot publish")
    if not isinstance(actor, str) or not actor.strip():
        raise SetupError("live upload requires an explicit actor")
    actor = actor.strip()
    if not plans:
        raise SetupError("live upload has no exact plans to authorize")
    if not isinstance(receipt_nonces, Mapping):
        raise SetupError("live upload requires per-piece private receipt bindings")
    nonce_bindings = {
        str(key): value
        for key, value in receipt_nonces.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    missing_receipts = [plan.date for plan in plans if plan.date not in nonce_bindings]
    if missing_receipts:
        raise SetupError("live upload requires one private receipt for every selected piece")
    if checked_at is None:
        checked_at = datetime.now(BANGKOK)
    if checked_at.tzinfo is None:
        raise SetupError("live authorization time must include a timezone")
    repo = Path(repo).resolve()

    schedule = schedule_document
    if schedule is None:
        schedule = _read_json_object(repo / "reels" / "schedule.json", "Reel schedule")
    if not isinstance(schedule, dict):
        raise SetupError("Reel schedule must be a JSON object")
    policy = policy_document
    if policy is None:
        policy = _read_json_object(repo / ".system_control" / "policy.json", "Policy")
    if not isinstance(policy, dict):
        raise SetupError("Policy must be a JSON object")
    roles = role_document
    if roles is None:
        roles = _read_json_object(
            repo / ".system_control" / "role_capabilities.json", "Role capabilities"
        )
    if not isinstance(roles, dict):
        raise SetupError("Role capabilities must be a JSON object")
    source_snapshot_path = (
        repo / "automation-log" / "knowledge-base" / "official-news-snapshot.json"
    ).resolve()
    if source_snapshot_path.is_symlink():
        raise SetupError("Official-source snapshot must not be a symlink")
    try:
        source_snapshot_raw = source_snapshot_path.read_bytes()
        sources = json.loads(source_snapshot_raw.decode("utf-8"))
    except Exception as exc:
        raise SetupError("Official-source snapshot is missing or unreadable") from exc
    if not isinstance(sources, dict):
        raise SetupError("Official-source snapshot must be a JSON object")
    if source_document is not None and source_document != sources:
        raise SetupError(
            "Injected official-source snapshot does not match repository evidence"
        )
    extra_content_source_check = content_source_check

    def canonical_content_source_check(
        exact_content_id: str, selected_repo: Path, decision_time: datetime
    ) -> dict[str, Any]:
        registry_path, library = content_source_gate.repo_content_source_contract(
            exact_content_id, selected_repo
        )
        if registry_path is None:
            return {
                "allowed": False,
                "failures": [
                    f"{exact_content_id}: factual content has no canonical source registry"
                ],
                "source_ids": [],
                "registry_sha256": "",
                "source_file_sha256": {},
            }
        registry_path = registry_path.resolve()
        if registry_path.is_symlink():
            raise SetupError("Canonical content-source registry must not be a symlink")
        try:
            registry_raw = registry_path.read_bytes()
            registry_document = json.loads(registry_raw.decode("utf-8"))
        except Exception as exc:
            raise SetupError("Canonical content-source registry is missing or unreadable") from exc
        if not isinstance(registry_document, dict):
            raise SetupError("Canonical content-source registry must be a JSON object")
        decision = content_source_gate.evaluate_content_source_gate(
            exact_content_id,
            registry_path,
            source_snapshot_path,
            library_name=library,
            now=decision_time.astimezone(timezone.utc),
            _registry_document=registry_document,
            _snapshot_document=sources,
        )
        registry_relative = registry_path.relative_to(selected_repo).as_posix()
        snapshot_relative = source_snapshot_path.relative_to(selected_repo).as_posix()
        registry_sha256 = hashlib.sha256(registry_raw).hexdigest()
        return {
            "allowed": decision.allowed,
            "failures": list(decision.failures),
            "source_ids": list(decision.source_ids),
            "registry_sha256": registry_sha256,
            "source_file_sha256": {
                snapshot_relative: hashlib.sha256(source_snapshot_raw).hexdigest(),
                registry_relative: registry_sha256,
            },
        }

    channels = policy.get("channels")
    channel_policy = channels.get("youtube") if isinstance(channels, dict) else None
    if not isinstance(channel_policy, dict):
        raise SetupError("Policy is missing channels.youtube")
    if str(channel_policy.get("state", "")).strip().casefold() != "active":
        raise SetupError("Policy channels.youtube.state must be active for live upload")
    if channel_policy.get("publication_authorized") is not True:
        raise SetupError("Policy channels.youtube.publication_authorized is not explicitly true")
    authorized_target = validate_youtube_target_identity(channel_policy, target_channel_id)

    actors = roles.get("actors")
    if not isinstance(actors, dict):
        raise SetupError("Role capabilities is missing actors")
    actor_capabilities = actors.get(actor)
    if not isinstance(actor_capabilities, dict) or actor_capabilities.get("social_publish") is not True:
        raise SetupError(f"Actor {actor!r} has no social_publish authority")

    privacy_runner = privacy_check or (lambda: _run_privacy_guard(repo))
    try:
        privacy_rc = int(privacy_runner())
    except Exception as exc:
        raise SetupError("Privacy gate is unavailable") from exc
    if privacy_rc != 0:
        raise SetupError(f"Privacy gate is blocked (exit {privacy_rc})")

    seen_dates: set[str] = set()
    authority_inputs: list[tuple[str, dict[str, Any]]] = []
    today = checked_at.astimezone(BANGKOK).date()
    guard_runner = media_guard or _run_media_publish_guard
    reels_root = (repo / "reels").resolve()
    for plan in plans:
        if plan.date in seen_dates:
            raise SetupError(f"Live plan contains duplicate date {plan.date}")
        seen_dates.add(plan.date)
        try:
            target_date = datetime.strptime(plan.date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise SetupError(f"Live plan date is invalid: {plan.date!r}") from exc
        if target_date < today:
            raise SetupError(
                f"Live target {plan.date} is historical in Asia/Bangkok; catch-up publication is blocked"
            )
        if plan.title != make_title(plan.description):
            raise SetupError(
                f"{plan.date}: YouTube title does not exactly derive from captions.youtube"
            )
        try:
            publish_slot = datetime.strptime(
                plan.publish_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise SetupError(f"{plan.date}: publish_at is invalid") from exc
        if publish_slot <= checked_at.astimezone(timezone.utc) + timedelta(
                minutes=PUBLISH_NOW_GRACE_MIN):
            raise SetupError(
                f"{plan.date}: scheduled slot has passed or is inside the safety grace; "
                "a fresh owner-approved slot is required"
            )
        if plan.item.get("status") != "Scheduled":
            raise SetupError(f"{plan.date}: manifest status must be exactly Scheduled")
        eligibility = plan.item.get("publication_eligibility")
        normalized_eligibility = (
            eligibility.strip().casefold() if isinstance(eligibility, str) else ""
        )
        if normalized_eligibility not in {"allowed", "ready"}:
            shown = eligibility if isinstance(eligibility, str) and eligibility.strip() else "missing"
            raise SetupError(
                f"{plan.date}: publication_eligibility must be explicitly ALLOWED or READY; "
                f"found {shown}"
            )
        content_id = plan.item.get("id")
        if not isinstance(content_id, str) or not content_id.strip():
            raise SetupError(f"{plan.date}: manifest item is missing id/content_id")
        content_id = content_id.strip()

        scheduled = schedule.get(plan.date)
        if not isinstance(scheduled, dict):
            raise SetupError(f"{plan.date}: exact schedule row is missing")
        scheduled_content_id = scheduled.get("content_id")
        if not isinstance(scheduled_content_id, str) or scheduled_content_id.strip() != content_id:
            raise SetupError(f"{plan.date}: schedule content_id does not match manifest id")
        placement_id = scheduled.get("placement_id")
        if not isinstance(placement_id, str) or not placement_id.strip():
            raise SetupError(f"{plan.date}: schedule placement_id is missing")
        placement_id = placement_id.strip()
        scheduled_file = scheduled.get("file")
        if not isinstance(scheduled_file, str) or not scheduled_file.strip():
            raise SetupError(f"{plan.date}: schedule file is missing")
        scheduled_relative = Path(scheduled_file.strip())
        if scheduled_relative.is_absolute():
            raise SetupError(f"{plan.date}: schedule file must be relative to reels/")
        scheduled_asset = (reels_root / scheduled_relative).resolve()
        try:
            scheduled_asset.relative_to(reels_root)
        except ValueError as exc:
            raise SetupError(f"{plan.date}: schedule file escapes reels/") from exc
        if scheduled_asset != plan.video_path.resolve():
            raise SetupError(f"{plan.date}: schedule asset does not match manifest reel")

        approval = scheduled.get("approval")
        if not isinstance(approval, dict):
            raise SetupError(f"{plan.date}: structured publication approval is missing")
        required_statuses = {
            "qa": {"pass", "approved"},
            "publication": {"approved"},
            "privacy_gate": {"pass", "approved"},
            "publication_gate": {"pass", "approved"},
            "public_identity": {"pass", "approved"},
            "source_gate": {"pass", "approved"},
            "dedup": {"pass", "approved"},
        }
        for field, accepted in required_statuses.items():
            raw = approval.get(field)
            normalized = raw.strip().casefold() if isinstance(raw, str) else ""
            if normalized not in accepted:
                raise SetupError(f"{plan.date}: approval.{field} is not authorized")
        approved_by = approval.get("approved_by")
        if not isinstance(approved_by, str) or approved_by.strip() != "owner":
            raise SetupError(f"{plan.date}: per-piece approved_by must be owner")
        owner_capabilities = actors.get("owner")
        if not isinstance(owner_capabilities, dict) or owner_capabilities.get("social_publish") is not True:
            raise SetupError("Role capabilities does not authorize owner social_publish")
        approved_at = _parse_aware_timestamp(
            approval.get("approved_at"), f"{plan.date}: approval.approved_at"
        )
        if approved_at.astimezone(timezone.utc) > checked_at.astimezone(timezone.utc):
            raise SetupError(f"{plan.date}: approval.approved_at is in the future")
        _parse_aware_timestamp(
            approval.get("source_checked_at"),
            f"{plan.date}: approval.source_checked_at",
        )
        try:
            source_decision = canonical_content_source_check(content_id, repo, checked_at)
        except Exception as exc:
            raise SetupError(
                f"{plan.date}: content-scoped official-source gate is unavailable"
            ) from exc
        if not isinstance(source_decision, dict):
            raise SetupError(
                f"{plan.date}: content-scoped official-source gate returned invalid evidence"
            )
        if source_decision.get("allowed") is not True:
            failures = source_decision.get("failures")
            detail = (
                "; ".join(str(item) for item in failures[:3])
                if isinstance(failures, list)
                else "exact content source is blocked"
            )
            raise SetupError(
                f"{plan.date}: content-scoped official-source gate blocked ({detail})"
            )
        exact_source_ids = source_decision.get("source_ids")
        if (
            not isinstance(exact_source_ids, list)
            or not exact_source_ids
            or any(
                not isinstance(item, str) or not item.strip()
                for item in exact_source_ids
            )
            or len(exact_source_ids) != len(set(exact_source_ids))
        ):
            raise SetupError(
                f"{plan.date}: content-scoped official-source IDs are missing or malformed"
            )
        registry_sha256 = source_decision.get("registry_sha256")
        if (
            not isinstance(registry_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", registry_sha256) is None
        ):
            raise SetupError(
                f"{plan.date}: content source registry SHA-256 is missing or malformed"
            )
        source_file_sha256 = source_decision.get("source_file_sha256")
        if (
            not isinstance(source_file_sha256, dict)
            or len(source_file_sha256) != 2
            or any(
                not isinstance(path, str)
                or not path.strip()
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                for path, digest in source_file_sha256.items()
            )
        ):
            raise SetupError(
                f"{plan.date}: exact source-file SHA-256 bindings are missing or malformed"
            )
        if extra_content_source_check is not None:
            try:
                extra_decision = extra_content_source_check(content_id, repo, checked_at)
            except Exception as exc:
                raise SetupError(
                    f"{plan.date}: additional content-source check is unavailable"
                ) from exc
            if not isinstance(extra_decision, dict):
                raise SetupError(
                    f"{plan.date}: additional content-source check returned invalid evidence"
                )
            if extra_decision.get("allowed") is not True:
                extra_failures = extra_decision.get("failures")
                extra_detail = (
                    "; ".join(str(item) for item in extra_failures[:3])
                    if isinstance(extra_failures, list)
                    else "additional check denied the exact content"
                )
                raise SetupError(
                    f"{plan.date}: additional content-source check blocked publication "
                    f"({extra_detail})"
                )
            extra_source_ids = extra_decision.get("source_ids")
            if (
                not isinstance(extra_source_ids, list)
                or not extra_source_ids
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in extra_source_ids
                )
                or len(extra_source_ids) != len(set(extra_source_ids))
            ):
                raise SetupError(
                    f"{plan.date}: additional content-scoped source IDs are missing or malformed"
                )
            extra_registry_sha256 = extra_decision.get("registry_sha256")
            if (
                not isinstance(extra_registry_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", extra_registry_sha256) is None
            ):
                raise SetupError(
                    f"{plan.date}: additional content source registry SHA-256 is missing or malformed"
                )
            if (
                extra_source_ids != exact_source_ids
                or extra_registry_sha256 != registry_sha256
            ):
                raise SetupError(
                    f"{plan.date}: additional content-source evidence does not exactly match canonical evidence"
                )

        report_value = scheduled.get("qa_report")
        if not isinstance(report_value, str) or not report_value.strip():
            raise SetupError(f"{plan.date}: schedule qa_report is missing")
        report_path = (repo / report_value.strip()).resolve()
        try:
            media_result = guard_runner(plan.video_path, report_path, repo)
        except SetupError:
            raise
        except Exception as exc:
            raise SetupError(f"{plan.date}: media_publish_guard is unavailable") from exc
        if not isinstance(media_result, dict) or media_result.get("verdict") != "PASS":
            findings = media_result.get("findings", []) if isinstance(media_result, dict) else []
            detail = "; ".join(str(item) for item in findings[:3]) or "no PASS verdict"
            raise SetupError(f"{plan.date}: media_publish_guard blocked publication ({detail})")
        actual_hash = str(media_result.get("sha256") or "").strip().upper()
        if len(actual_hash) != 64 or any(char not in "0123456789ABCDEF" for char in actual_hash):
            raise SetupError(f"{plan.date}: media_publish_guard returned no exact SHA-256")
        if _sha256(plan.video_path) != actual_hash:
            raise SetupError(f"{plan.date}: media_publish_guard SHA-256 does not match asset bytes")
        approved_hash = str(approval.get("asset_sha256") or "").strip().upper()
        if approved_hash != actual_hash:
            raise SetupError(f"{plan.date}: approved asset_sha256 does not match current asset")
        receipt = _read_json_object(report_path, f"{plan.date}: Media QA receipt")
        novelty = receipt.get("novelty_review")
        receipt_content_id = novelty.get("content_id") if isinstance(novelty, dict) else None
        if not isinstance(receipt_content_id, str) or receipt_content_id.strip() != content_id:
            raise SetupError(f"{plan.date}: QA receipt content_id does not match manifest id")
        try:
            _assert_reconciliation_clear(placement_id)
        except PublicationBlocked as exc:
            raise SetupError(f"{plan.date}: {exc}") from exc
        authority_inputs.append(
            (
                plan.date,
                {
                    "repo": repo,
                    "channel": "youtube",
                    "actor": actor,
                    "target_identity": authorized_target,
                    "approval": approval,
                    "content_id": content_id,
                    "placement_id": placement_id,
                    "caption": plan.description,
                    "asset_sha256": actual_hash,
                    "content_source_evidence": {
                        "manifest_item": plan.item,
                        "official_source_snapshot": sources,
                        "source_ids": exact_source_ids,
                        "source_registry_sha256": registry_sha256,
                        "source_file_sha256": source_file_sha256,
                        "schedule_row": scheduled,
                        "source_files": [
                            ".system_control/content_manifest.json",
                            "automation-log/knowledge-base/official-news-snapshot.json",
                            "reels/schedule.json",
                        ],
                    },
                    "media_qa_path": report_value.strip(),
                    "scheduled_slot": plan.publish_at,
                    "receipt_nonce": nonce_bindings[plan.date],
                    "now": checked_at,
                    "guard_runner": authority_guard_runner,
                },
            )
        )

    authorized_actions: dict[str, dict[str, Any]] = {}
    for plan_date, inputs in authority_inputs:
        try:
            action = authorize_live_publication(
                repo=inputs["repo"],
                channel=inputs["channel"],
                actor=inputs["actor"],
                target_identity=inputs["target_identity"],
                approval=inputs["approval"],
                content_id=inputs["content_id"],
                placement_id=inputs["placement_id"],
                caption=inputs["caption"],
                asset_sha256=inputs["asset_sha256"],
                content_source_evidence=inputs["content_source_evidence"],
                media_qa_path=inputs["media_qa_path"],
                scheduled_slot=inputs["scheduled_slot"],
                receipt_nonce=inputs["receipt_nonce"],
                now=inputs["now"],
                guard_runner=inputs["guard_runner"],
            )
        except PublicationBlocked as exc:
            raise SetupError(
                f"{plan_date}: shared publication authority blocked: {exc}"
            ) from exc
        if not isinstance(action, dict) or action.get("consumed") is not True:
            raise SetupError(
                f"{plan_date}: shared publication authority returned no consumed action"
            )
        authorized_actions[plan_date] = action

    return authorized_actions


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
    print(f"Planned Shorts: {len(plans)}")
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
        # Keep the local tuple slot name for compatibility, but supply the
        # stream-based class so run_live never hands Google a mutable path.
        from googleapiclient.http import MediaIoBaseUpload as MediaFileUpload
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
        policy = _read_json_object(ROOT / ".system_control" / "policy.json", "Policy")
        channels = policy.get("channels")
        channel_policy = channels.get("youtube") if isinstance(channels, dict) else None
        channel_id = _configured_youtube_channel_id(channel_policy)
    except SetupError as exc:
        print(f"CHECK BLOCKED (target identity unavailable): {exc}")
        return 1
    try:
        credentials, libraries = get_credentials(interactive=False)
    except (SetupError, AuthUnavailable) as exc:
        print(f"CHECK SKIPPED (authentication unavailable): {exc}")
        return 0

    _Request, _Credentials, _InstalledAppFlow, build, HttpError, _MediaFileUpload = libraries
    try:
        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        print(f"Checking {len(plans)} exact titles on the policy-configured channel (best effort).")
        found_any = False
        for plan in plans:
            response = service.search().list(
                part="snippet",
                channelId=channel_id,
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


# A scheduled publish time that has passed (or is too close to guarantee a safe
# upload) must never be converted into an immediate public release.  A fresh
# per-piece approval and future slot are required instead.
PUBLISH_NOW_GRACE_MIN = 15


def publishes_in_the_past(plan: UploadPlan, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    slot = datetime.strptime(plan.publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return slot <= now + timedelta(minutes=PUBLISH_NOW_GRACE_MIN)


def upload_body(plan: UploadPlan) -> dict[str, Any]:
    snippet = {
        "title": plan.title,
        "description": plan.description,
        "categoryId": "27",
        "defaultLanguage": "th",
    }
    if publishes_in_the_past(plan):
        raise SetupError(
            "scheduled slot has passed or is inside the safety grace; "
            "immediate public fallback is forbidden"
        )
    status = {
        "privacyStatus": "private",
        "publishAt": plan.publish_at,
        "selfDeclaredMadeForKids": False,
    }
    return {"snippet": snippet, "status": status}


def run_live(
    manifest: dict[str, Any] | list[Any],
    plans: list[UploadPlan],
    limit: int,
    *,
    explicit_dates: bool = False,
    actor: str | None = None,
    target_channel_id: str | None = None,
    receipt_nonces: Mapping[str, str] | None = None,
    checked_at: datetime | None = None,
) -> int:
    try:
        upload_log = load_upload_log()
    except SetupError as exc:
        print(f"LIVE UPLOAD NOT STARTED: {exc}")
        return 1
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
        authorized_actions = validate_live_upload(
            selected,
            explicit_dates=explicit_dates,
            actor=actor,
            target_channel_id=target_channel_id,
            receipt_nonces=receipt_nonces,
            checked_at=checked_at,
        )
    except SetupError as exc:
        print(f"LIVE UPLOAD BLOCKED: {exc}")
        return 1

    try:
        credentials, libraries = get_credentials(interactive=True)
    except SetupError as exc:
        print(f"LIVE UPLOAD NOT STARTED: {exc}")
        print_remaining(plans, upload_log)
        return 1

    _Request, _Credentials, _InstalledAppFlow, build, HttpError, MediaFileUpload = libraries
    service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    try:
        verify_authenticated_youtube_channel(service, str(target_channel_id or ""))
    except SetupError as exc:
        print(f"LIVE UPLOAD BLOCKED: {exc}")
        print_remaining(plans, upload_log)
        return 1
    failed = False

    for plan in selected:
        _mode = f"scheduled {plan.publish_at}"
        print(f"UPLOAD {plan.date}: {plan.relative_video_path} -> {_mode}")
        action = authorized_actions[plan.date]
        attempt_started = False
        terminal_written = False
        claim_key = ""
        upload_buffer = None
        try:
            # OAuth consent can take time. Re-check the exact bytes immediately
            # before MediaFileUpload so evidence drift or a too-close/past slot
            # cannot reuse an old owner approval and QA receipt.
            verify_execution_authorization(
                repo=ROOT,
                action=action,
                caption=plan.description,
                asset_sha256=_sha256(plan.video_path),
                media_qa_path=action.get("media_qa_path"),
            )
            upload_buffer, upload_hash = _hash_bound_upload_buffer(
                plan.video_path, action.get("asset_sha256")
            )
            claimed, claim_key, claim_reason = post_ledger.claim(
                "youtube",
                "sha256:" + upload_hash,
                action.get("scheduled_slot"),
                source="yt-upload-live",
                enforce_gap=True,
            )
            if not claimed:
                raise PublicationBlocked(
                    "YouTube atomic media claim blocked: %s" % claim_reason
                )
            _begin_attempt(action)
            attempt_started = True
            media = MediaFileUpload(
                upload_buffer, mimetype="video/mp4", chunksize=-1, resumable=True
            )
            request = service.videos().insert(
                part="snippet,status", body=upload_body(plan), media_body=media
            )
            # Request construction is local. Re-check source, policy, calendar,
            # media, slot and the exact novelty-corpus generation while holding
            # the shared claim through the resumable upload mutation.
            with media_publish_guard.publication_corpus_claim(
                plan.video_path,
                action.get("media_qa_path"),
                expected_asset_sha256=action.get("asset_sha256"),
                expected_content_id=action.get("content_id"),
                repo=ROOT,
            ):
                verify_execution_authorization(
                    repo=ROOT,
                    action=action,
                    caption=plan.description,
                    asset_sha256=upload_hash,
                    media_qa_path=action.get("media_qa_path"),
                )
                if _sha256(plan.video_path) != upload_hash:
                    raise RuntimeError(
                        "source asset changed after immutable upload snapshot; upload blocked"
                    )
                response = resumable_upload(request, HttpError)
                video_id = response.get("id")
                if (
                    not isinstance(video_id, str)
                    or YOUTUBE_REMOTE_ID_PATTERN.fullmatch(video_id.strip()) is None
                ):
                    raise RuntimeError(
                        "YouTube returned no video ID after a completed upload."
                    )
                video_id = video_id.strip()

                # Terminal remote evidence must be durable before legacy success
                # registries. Keep the corpus lock through save_manifest(), the
                # only in-repo writer of this guard's manifest generation.
                _finish_attempt(action, "POSTED", remote_platform_id=video_id)
                terminal_written = True
                post_ledger.confirm(claim_key, post_id=video_id, status="POSTED")

                upload_log[plan.date] = video_id
                write_json(UPLOAD_LOG_PATH, upload_log)
                posted = plan.item.get("posted")
                if not isinstance(posted, dict):
                    posted = {}
                    plan.item["posted"] = posted
                # Record what ACTUALLY happened. Writing "scheduled" for a video that was
                # published immediately makes downstream guards (video-post-verify,
                # channel-heartbeat) reason about a state that never existed.
                _how = "scheduled"
                posted["youtube"] = f"{_how} (yt-api {video_id})"
                save_manifest(manifest)
            print(f"SUCCESS {plan.date}: videoId={video_id}")
        except BaseException as exc:
            if attempt_started and not terminal_written:
                try:
                    _finish_attempt(action, "UNKNOWN", reason=str(exc))
                except Exception:
                    pass
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            failed = True
            if isinstance(exc, QuotaExceeded):
                print(
                    "STOP: YouTube quotaExceeded after a durable attempt began; "
                    "state is UNKNOWN and reconciliation-only."
                )
            elif isinstance(exc, UploadLimitExceeded):
                print(
                    "STOP: YouTube uploadLimitExceeded after a durable attempt began; "
                    "state is UNKNOWN and reconciliation-only."
                )
            elif isinstance(exc, HttpError):
                print(
                    f"FAILED {plan.date}: YouTube API error HTTP "
                    f"{http_status(exc) or 'unknown'} ({error_reason(exc)}); "
                    "automatic retry disabled; reconciliation-only."
                )
            elif terminal_written:
                print(
                    f"FAILED {plan.date}: remote publication is terminal POSTED, but "
                    f"local ledger/registry reconciliation is incomplete ({exc}); "
                    "automatic retry disabled."
                )
            else:
                print(
                    f"FAILED {plan.date}: {exc}; automatic retry disabled; "
                    "reconciliation-only."
                )
            break
        finally:
            if upload_buffer is not None:
                upload_buffer.close()

    print_remaining(plans, upload_log)
    return 1 if failed else 0


def main() -> int:
    global TARGET_DATES
    args = parse_args()
    try:
        TARGET_DATES = resolve_target_dates(args)
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

    return run_live(
        manifest,
        plans,
        args.limit,
        explicit_dates=bool(args.dates),
        actor=args.actor,
        target_channel_id=args.target_channel_id,
        receipt_nonces=args.receipt_nonces,
    )


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
