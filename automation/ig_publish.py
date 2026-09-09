#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ig_publish.py — IG Reels auto-publisher via Instagram Content Publishing API (order 2026-07-11)
#
# Flow (per Meta spec): POST /{ig-user-id}/media (REELS + video_url + caption)
#                        -> poll GET /{creation-id}?fields=status_code until FINISHED
#                        -> POST /{ig-user-id}/media_publish
#
# Env:
#   IG_ACCESS_TOKEN  (required for live)  long-lived user token, instagram_content_publish scope
#   IG_USER_ID       (required for live)  IG Business Account ID (NOT the username)
#   DRY_RUN          default "1" — validate schedule/URL/caption only, no API call
#   OVERRIDE_DATE    optional YYYY-MM-DD (default: today Asia/Bangkok)
#   BASE_URL         must be the canonical https://ngernduangold.com origin
#
# Exit: 0 = published/skipped/no-entry, 2 = FAILED (workflow turns red -> owner notified)
# Safety: caption must carry the education disclaimer + AI disclosure or we ABORT (comply fail-closed).
#         published.json prevents double-posting on re-runs (dedup guard).
import base64, io, os, sys, json, time, datetime, hashlib, re, urllib.request, urllib.parse, urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "automation-log"))
import post_ledger
from publication_authority import (
    PublicationBlocked,
    authorize_live_publication,
    verify_execution_authorization,
)
import media_publish_guard
SCHEDULE = os.path.join(ROOT, "reels", "schedule.json")
LOG_DIR = os.path.join(ROOT, "automation-log", "ig-reels")
PUBLISHED = os.path.join(LOG_DIR, "published.json")
ALERT = os.path.join(ROOT, "automation-log", "cowork-inbox", "IG-PUBLISH-FAIL.md")
GRAPH = "https://graph.facebook.com/v22.0"
CANONICAL_VIDEO_ORIGIN = "https://ngernduangold.com"
CANONICAL_VIDEO_HOST = "ngernduangold.com"
MAX_HOSTED_VIDEO_BYTES = 256 * 1024 * 1024
REMOTE_READ_CHUNK = 1024 * 1024

BASE_URL = os.environ.get("BASE_URL", "https://ngernduangold.com")
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER = os.environ.get("IG_USER_ID", "")
ACTOR = os.environ.get("PUBLICATION_ACTOR", "")
RECEIPT_NONCE = os.environ.get("PUBLICATION_RECEIPT_NONCE", "")
ATTEMPT_ROOT = Path(ROOT) / ".local-private" / "runtime" / "publication-attempts"
REMOTE_ID_PATTERN = re.compile(r"[0-9]{5,40}\Z")
REEL_FILENAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.mp4\Z", re.IGNORECASE)
CONTENT_ADDRESS_PATH_PATTERN = re.compile(
    r"/reels/sha256/([0-9a-f]{64})\.mp4\Z"
)
IMMUTABLE_REMOTE_KIND = "sha256-content-addressed-v1"
MIN_IMMUTABLE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Make hosted-media verification fail on every redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now_th():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)


def log(msg):
    print("[ig_publish] " + msg)


def fail(msg, date=""):
    log("FAIL: " + msg)
    os.makedirs(os.path.dirname(ALERT), exist_ok=True)
    with io.open(ALERT, "w", encoding="utf-8") as handle:
        handle.write(
            "# IG PUBLISH FAIL — %s\n\n- date: %s\n- error: %s\n- ดู runbook: automation-log/cc-outbox/RUNBOOK_ig-reels-api_20260711.md\n"
            % (now_th().strftime("%Y-%m-%d %H:%M"), date, msg)
        )
    sys.exit(2)


def _attempt_paths(placement_id):
    value = str(placement_id or "").strip()
    if not value:
        raise PublicationBlocked("placement_id is required for durable attempt state")
    key = hashlib.sha256(("instagram\0" + value).encode("utf-8")).hexdigest()
    return (
        ATTEMPT_ROOT / "pending" / "instagram" / (key + ".json"),
        ATTEMPT_ROOT / "terminal" / "instagram" / (key + ".json"),
    )


def _attempt_evidence_path(placement_id):
    value = str(placement_id or "").strip()
    if not value:
        raise PublicationBlocked("placement_id is required for durable attempt evidence")
    key = hashlib.sha256(("instagram\0" + value).encode("utf-8")).hexdigest()
    return ATTEMPT_ROOT / "evidence" / "instagram" / (key + ".json")


def _write_exclusive_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PublicationBlocked(
            "durable publication state already exists; automatic retry is disabled; reconciliation-only"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _assert_reconciliation_clear(placement_id):
    pending, terminal = _attempt_paths(placement_id)
    evidence = _attempt_evidence_path(placement_id)
    if pending.exists() or terminal.exists() or evidence.exists():
        raise PublicationBlocked(
            "a durable Instagram attempt/terminal receipt already exists; "
            "automatic retry is disabled; reconciliation-only"
        )


def _begin_attempt(action):
    pending, _terminal = _attempt_paths(action.get("placement_id"))
    _write_exclusive_json(pending, {
        "schema_version": 1,
        "status": "PENDING_REMOTE",
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
    })


def _record_hosted_media_evidence(action, evidence):
    """Persist remote-byte evidence before creating an Instagram container."""
    pending, terminal = _attempt_paths(action.get("placement_id"))
    if not pending.is_file() or terminal.exists():
        raise PublicationBlocked(
            "hosted-media evidence requires one active PENDING_REMOTE attempt"
        )
    evidence_hash = str(evidence.get("evidence_sha256") or "").casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_hash):
        raise PublicationBlocked("hosted-media evidence has no valid evidence hash")
    action_binding = hashlib.sha256(
        json.dumps(action, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _write_exclusive_json(_attempt_evidence_path(action.get("placement_id")), {
        "schema_version": 1,
        "status": "REMOTE_MEDIA_VERIFIED",
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action_sha256": action_binding,
        "hosted_media": evidence,
    })


def _finish_attempt(action, status, *, remote_platform_id="", reason="", details=None):
    normalized = str(remote_platform_id or "").strip()
    if status == "POSTED" and REMOTE_ID_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked("Instagram POSTED requires a valid remote media id")
    if normalized and REMOTE_ID_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked("Instagram remote media id has an invalid format")
    _pending, terminal = _attempt_paths(action.get("placement_id"))
    _write_exclusive_json(terminal, {
        "schema_version": 1,
        "status": status,
        "finalized_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "remote_platform_id": normalized or None,
        "permalink": None,
        "reason": str(reason or "")[:500] or None,
        "details": details if isinstance(details, dict) else {},
    })


def _atomic_json_write(path, value):
    selected = Path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary = selected.with_name(
        selected.name + ".tmp-%s-%s" % (os.getpid(), time.time_ns())
    )
    payload = json.dumps(value, ensure_ascii=False, indent=1).encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, selected)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _canonical_video_url(file_name, base_url=None):
    """Build an exact canonical HTTPS URL without accepting alternate origins."""
    raw_base = BASE_URL if base_url is None else base_url
    parsed = urllib.parse.urlsplit(str(raw_base or ""))
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != CANONICAL_VIDEO_HOST
        or parsed.netloc.casefold() != CANONICAL_VIDEO_HOST
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PublicationBlocked(
            "Instagram hosted media must use canonical HTTPS origin "
            + CANONICAL_VIDEO_ORIGIN
        )
    name = str(file_name or "").strip()
    if not REEL_FILENAME_PATTERN.fullmatch(name) or Path(name).name != name:
        raise PublicationBlocked("Instagram reel file name is not a safe MP4 basename")
    return CANONICAL_VIDEO_ORIGIN + "/reels/" + urllib.parse.quote(name, safe="._-")


def _immutable_remote_asset_contract(entry, expected_asset_hash):
    """Require an exact content-addressed URL contract for Meta's later fetch.

    A successful GET of a mutable ``/reels/name.mp4`` cannot prove which bytes
    Meta will fetch after container creation.  Live publication is therefore
    blocked unless the schedule binds a SHA-256 URL and the response later proves
    the corresponding immutable cache/content-digest contract.
    """
    expected = str(expected_asset_hash or "").strip().casefold()
    if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise PublicationBlocked("immutable remote asset has no valid SHA-256")
    contract = entry.get("remote_asset") if isinstance(entry, dict) else None
    if not isinstance(contract, dict):
        raise PublicationBlocked(
            "Instagram live publication requires an immutable content-addressed remote_asset contract"
        )
    if contract.get("schema_version") != 1 or contract.get("kind") != IMMUTABLE_REMOTE_KIND:
        raise PublicationBlocked("Instagram remote_asset contract schema/kind is invalid")
    declared = str(contract.get("sha256") or "").strip().casefold()
    if declared != expected:
        raise PublicationBlocked("Instagram remote_asset SHA-256 does not match guarded media")
    raw_url = str(contract.get("url") or "").strip()
    try:
        parsed = urllib.parse.urlsplit(raw_url)
    except ValueError as exc:
        raise PublicationBlocked("Instagram remote_asset URL is invalid") from exc
    match = CONTENT_ADDRESS_PATH_PATTERN.fullmatch(parsed.path)
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != CANONICAL_VIDEO_HOST
        or parsed.netloc.casefold() != CANONICAL_VIDEO_HOST
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or match is None
        or match.group(1) != expected
    ):
        raise PublicationBlocked(
            "Instagram remote_asset URL is not the exact SHA-256 content address"
        )
    canonical = CANONICAL_VIDEO_ORIGIN + parsed.path
    if raw_url != canonical:
        raise PublicationBlocked("Instagram remote_asset URL is not canonical")
    return {
        "schema_version": 1,
        "kind": IMMUTABLE_REMOTE_KIND,
        "sha256": expected,
        "url": canonical,
    }


def _immutable_cache_control(value):
    tokens = [item.strip().casefold() for item in str(value or "").split(",")]
    if "immutable" not in tokens:
        return False
    for token in tokens:
        if token.startswith("max-age="):
            raw = token.split("=", 1)[1].strip().strip('"')
            if raw.isdigit() and int(raw) >= MIN_IMMUTABLE_MAX_AGE_SECONDS:
                return True
    return False


def _content_digest_header(expected_hash):
    encoded = base64.b64encode(bytes.fromhex(expected_hash)).decode("ascii")
    return "sha-256=:%s:" % encoded


def _sha256_local_file(path):
    selected = Path(path).resolve(strict=True)
    if not selected.is_file():
        raise PublicationBlocked("Instagram local media is not a regular file")
    size = selected.stat().st_size
    if size <= 0 or size > MAX_HOSTED_VIDEO_BYTES:
        raise PublicationBlocked("Instagram local media size is outside the bounded verifier limit")
    digest = hashlib.sha256()
    total = 0
    with selected.open("rb") as handle:
        while True:
            chunk = handle.read(REMOTE_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_HOSTED_VIDEO_BYTES:
                raise PublicationBlocked("Instagram local media exceeded the bounded verifier limit")
            digest.update(chunk)
    if total != size:
        raise PublicationBlocked("Instagram local media changed while hashing")
    return digest.hexdigest(), total


def _verify_hosted_video(
    request, local_asset, expected_asset_hash, remote_contract, opener=None
):
    """GET and hash the exact hosted bytes with no redirects and a hard byte cap."""
    if not isinstance(request, urllib.request.Request) or request.get_method() != "GET":
        raise PublicationBlocked("hosted-media verification requires an HTTP GET request")
    contract = _immutable_remote_asset_contract(
        {"remote_asset": remote_contract}, expected_asset_hash
    )
    canonical_url = contract["url"]
    if request.full_url != canonical_url:
        raise PublicationBlocked("hosted-media request URL is not the exact canonical URL")

    expected = str(expected_asset_hash or "").strip().casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PublicationBlocked("hosted-media verification has no expected asset hash")
    local_hash, local_size = _sha256_local_file(local_asset)
    if local_hash != expected:
        raise PublicationBlocked("local media changed after the full media publication guard")

    selected_opener = opener or urllib.request.build_opener(_NoRedirectHandler())
    digest = hashlib.sha256()
    total = 0
    with selected_opener.open(request, timeout=30) as response:
        status = getattr(response, "status", None)
        final_url = response.geturl()
        content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].casefold()
        content_encoding = str(response.headers.get("Content-Encoding", "")).strip().casefold()
        raw_length = str(response.headers.get("Content-Length", "")).strip()
        cache_control = str(response.headers.get("Cache-Control", "")).strip()
        content_digest = str(response.headers.get("Content-Digest", "")).strip()
        if status != 200 or final_url != canonical_url:
            raise PublicationBlocked("hosted media did not return direct canonical HTTP 200")
        if not content_type.startswith("video/"):
            raise PublicationBlocked("hosted media did not return a video content type")
        if content_encoding not in ("", "identity"):
            raise PublicationBlocked("hosted media used an unsupported content encoding")
        if not _immutable_cache_control(cache_control):
            raise PublicationBlocked(
                "hosted media response has no verifiable immutable cache contract"
            )
        if content_digest != _content_digest_header(expected):
            raise PublicationBlocked(
                "hosted media Content-Digest is missing or does not match SHA-256 address"
            )
        if raw_length:
            if not raw_length.isdigit() or int(raw_length) != local_size:
                raise PublicationBlocked("hosted media Content-Length does not match local bytes")
        while True:
            remaining = local_size - total
            chunk = response.read(min(REMOTE_READ_CHUNK, remaining + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > local_size or total > MAX_HOSTED_VIDEO_BYTES:
                raise PublicationBlocked("hosted media exceeded the exact bounded byte length")
            digest.update(chunk)

    remote_hash = digest.hexdigest()
    if total != local_size or remote_hash != local_hash:
        raise PublicationBlocked("hosted media bytes do not exactly match the local asset")
    evidence = {
        "schema_version": 1,
        "method": "GET",
        "redirects_allowed": False,
        "url": canonical_url,
        "byte_length": total,
        "local_sha256": local_hash,
        "remote_sha256": remote_hash,
        "remote_asset_contract": contract,
        "cache_control": cache_control,
        "content_digest": content_digest,
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    evidence["evidence_sha256"] = hashlib.sha256(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return evidence


def api(path, params, method="GET"):
    params = dict(params)
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = GRAPH + path
    req = urllib.request.Request(url + ("?" + data.decode() if method == "GET" else ""),
                                 data=None if method == "GET" else data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        if '"code":190' in body:
            raise RuntimeError("TOKEN EXPIRED/INVALID (code 190) — refresh long-lived token, see runbook §4. " + body)
        raise RuntimeError("HTTP %d: %s" % (e.code, body))


def main():
    date = os.environ.get("OVERRIDE_DATE") or now_th().strftime("%Y-%m-%d")
    with io.open(SCHEDULE, encoding="utf-8") as handle:
        sched = json.load(handle)
    entry = sched.get(date)
    if not entry:
        log("no schedule entry for %s — ต้องเติม batch ใน reels/schedule.json (last=%s)" % (date, max(sched)))
        return 0
    os.makedirs(LOG_DIR, exist_ok=True)
    pub = {}
    if os.path.exists(PUBLISHED):
        with io.open(PUBLISHED, encoding="utf-8") as handle:
            pub = json.load(handle)
    if date in pub:
        log("already published %s (media_id=%s) — skip (dedup guard)" % (date, pub[date].get("media_id")))
        return 0

    caption = entry["caption"]

    # comply fail-closed: approved-sheet markers must be present
    if "ข้อมูลเพื่อการศึกษา" not in caption or "ผลิตด้วย AI" not in caption:
        fail("caption missing disclaimer/AI disclosure — refuse to publish", date)

    if DRY_RUN:
        try:
            _canonical_video_url(entry["file"])
        except PublicationBlocked as exc:
            fail(str(exc), date)
        log("DRY_RUN=1 — local schedule/caption validated; no network call. caption preview:")
        log(caption.replace("\n", " | ")[:220])
        return 0
    if not TOKEN or not IG_USER:
        log("FAIL: explicit live run has no IG credentials; no network action attempted")
        return 2

    placement_id = entry.get("placement_id") or entry.get("placementId")
    action = None
    attempt_started = False
    terminal_written = False
    claim_key = ""
    cid = ""
    hosted_evidence = {}
    try:
        local_asset = Path(ROOT) / "reels" / entry.get("file", "")
        media_qa_path = (
            entry.get("qa_report")
            or entry.get("media_receipt")
            or entry.get("media_qa_report")
        )
        media_result = media_publish_guard.evaluate(
            local_asset,
            Path(ROOT) / str(media_qa_path or ""),
            repo=Path(ROOT),
        )
        if media_result.get("verdict") != "PASS":
            raise PublicationBlocked(
                "full media publication guard blocked before network: "
                + "; ".join(map(str, media_result.get("findings") or []))[:500]
            )
        asset_hash = str(media_result.get("sha256") or "").casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", asset_hash):
            raise PublicationBlocked("full media publication guard returned no asset hash")
        remote_contract = _immutable_remote_asset_contract(entry, asset_hash)
        video_url = remote_contract["url"]
        _assert_reconciliation_clear(placement_id)
        action = authorize_live_publication(
            repo=Path(ROOT), channel="instagram", actor=ACTOR,
            target_identity=IG_USER,
            approval=entry.get("approval"),
            content_id=entry.get("content_id") or entry.get("contentId"),
            placement_id=placement_id,
            caption=caption,
            asset_sha256=asset_hash,
            content_source_evidence={
                "source_file": "reels/schedule.json",
                "source_file_sha256": {
                    "reels/schedule.json": hashlib.sha256(
                        Path(SCHEDULE).read_bytes()
                    ).hexdigest(),
                },
                "entry": entry,
            },
            media_qa_path=media_qa_path,
            scheduled_slot=(
                entry.get("scheduled_slot")
                or entry.get("scheduledSlot")
                or entry.get("scheduled_at")
            ),
            receipt_nonce=RECEIPT_NONCE,
        )
        _begin_attempt(action)
        attempt_started = True

        # PENDING_REMOTE exists before this first network read.  Redirects are
        # disabled and every hosted byte must equal the exact guarded local MP4.
        req = urllib.request.Request(video_url, method="GET", headers={
            "User-Agent": "ngernduangold-hosted-media-verifier/1.0",
            "Accept": "video/*",
            "Accept-Encoding": "identity",
        })
        hosted_evidence = _verify_hosted_video(
            req, local_asset, asset_hash, remote_contract
        )
        _record_hosted_media_evidence(action, hosted_evidence)
        log("video bytes verified: %s (%s)" % (
            video_url, hosted_evidence["evidence_sha256"]
        ))

        claimed, claim_key, claim_reason = post_ledger.claim(
            "instagram",
            "sha256:" + asset_hash,
            action.get("scheduled_slot"),
            source="ig-publish-live",
            enforce_gap=True,
        )
        if not claimed:
            raise PublicationBlocked(
                "Instagram atomic media claim blocked: %s" % claim_reason
            )

        # Revalidate the consumed authority and the exact novelty-corpus
        # generation while holding the shared corpus claim through the remote
        # container mutation. A stale registry generation never reaches Graph.
        with media_publish_guard.publication_corpus_claim(
            local_asset,
            media_qa_path,
            expected_asset_sha256=action.get("asset_sha256"),
            expected_content_id=action.get("content_id"),
            repo=Path(ROOT),
        ):
            verify_execution_authorization(
                repo=Path(ROOT),
                action=action,
                caption=caption,
                asset_sha256=asset_hash,
                media_qa_path=media_qa_path,
            )
            result = api("/%s/media" % IG_USER, {
                "media_type": "REELS", "video_url": video_url,
                "caption": caption, "share_to_feed": "true"}, method="POST")
        cid = str(result.get("id") or "").strip() if isinstance(result, dict) else ""
        if REMOTE_ID_PATTERN.fullmatch(cid) is None:
            raise RuntimeError("media container returned no valid platform id")
        log("creation_id=" + cid)

        status = ""
        for _ in range(60):
            time.sleep(5)
            state = api("/%s" % cid, {"fields": "status_code"})
            status = str(state.get("status_code") or "") if isinstance(state, dict) else ""
            log("status=" + status)
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError("remote media container reported ERROR")
        if status != "FINISHED":
            raise RuntimeError("remote media container was not FINISHED before timeout")

        # Long-running container processing can outlive an approval, policy, or
        # corpus generation. Reclaim and revalidate immediately before publish.
        with media_publish_guard.publication_corpus_claim(
            local_asset,
            media_qa_path,
            expected_asset_sha256=action.get("asset_sha256"),
            expected_content_id=action.get("content_id"),
            repo=Path(ROOT),
        ):
            verify_execution_authorization(
                repo=Path(ROOT),
                action=action,
                caption=caption,
                asset_sha256=asset_hash,
                media_qa_path=media_qa_path,
            )
            result = api(
                "/%s/media_publish" % IG_USER,
                {"creation_id": cid},
                method="POST",
            )
        media_id = str(result.get("id") or "").strip() if isinstance(result, dict) else ""
        if REMOTE_ID_PATTERN.fullmatch(media_id) is None:
            raise RuntimeError("publish returned no valid remote media id")

        _finish_attempt(
            action, "POSTED", remote_platform_id=media_id,
            details={
                "creation_id": cid,
                "hosted_media_evidence_sha256": hosted_evidence.get("evidence_sha256"),
                "hosted_media_sha256": hosted_evidence.get("remote_sha256"),
                "hosted_media_byte_length": hosted_evidence.get("byte_length"),
            },
        )
        terminal_written = True
        post_ledger.confirm(claim_key, post_id=media_id, status="POSTED")
        pub[date] = {"creation_id": cid, "media_id": media_id,
                     "file": entry["file"], "status": "POSTED",
                     "hosted_media_evidence_sha256": hosted_evidence.get("evidence_sha256"),
                     "ts": now_th().strftime("%Y-%m-%d %H:%M:%S+07:00")}
        _atomic_json_write(PUBLISHED, pub)
        with io.open(
            os.path.join(LOG_DIR, "log-%s.md" % date), "w", encoding="utf-8"
        ) as handle:
            handle.write(
                "# IG Reel published %s\n\n- file: %s\n- creation_id: %s\n- media_id: %s\n- caption:\n\n```\n%s\n```\n"
                % (date, entry["file"], cid, media_id, caption)
            )
        log("PUBLISHED %s -> media_id=%s" % (date, media_id))
        return 0
    except BaseException as exc:
        if attempt_started and not terminal_written:
            try:
                _finish_attempt(
                    action, "UNKNOWN", reason=str(exc),
                    details={
                        "creation_id": cid or None,
                        "hosted_media_evidence_sha256": hosted_evidence.get("evidence_sha256"),
                        "hosted_media_sha256": hosted_evidence.get("remote_sha256"),
                        "hosted_media_byte_length": hosted_evidence.get("byte_length"),
                    },
                )
            except Exception:
                pass
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        if terminal_written:
            fail(
                "remote publication is terminal POSTED, but local ledger/registry "
                "reconciliation is incomplete; automatic retry disabled: %s"
                % str(exc)[:300],
                date,
            )
        fail("publication attempt is UNKNOWN; automatic retry disabled; reconciliation-only: %s"
             % str(exc)[:300], date)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        fail(str(e))
