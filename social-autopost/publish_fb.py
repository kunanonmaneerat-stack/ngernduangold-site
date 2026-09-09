#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# publish_fb.py — FB Page daily feed post + first-comment link ผ่าน Graph API (order 2026-07-11)
#
# Flow: POST /{page-id}/feed (message เท่านั้น ไม่มี URL ในบอดี้ — reach)
#       -> POST /{post_id}/comments (ลิงก์ในคอมเมนต์แรก)
#
# Env:
#   FB_PAGE_ID, FB_PAGE_TOKEN   (Page Access Token; แยกจาก IG secrets)
#   DRY_RUN default "1" · OVERRIDE_DATE optional YYYY-MM-DD
#
# Behaviors (mirror ig_publish):
#   - secrets ยังไม่มา -> SOFT SKIP เขียว + alert FB-PUBLISH-SKIP.md (ไม่แดงรายวัน)
#   - comply fail-closed: body ต้องมี disclaimer · ห้ามมี URL ในบอดี้ · affiliate=true ต้องมี "มีลิงก์พันธมิตร" · ไม่มี bare %
#   - dedup published-fb.json · โพสต์ขึ้นแล้วแต่คอมเมนต์พลาด -> บันทึก published (กันโพสต์ซ้ำ) + alert ให้เติมคอมเมนต์มือ
# Exit: 0 = ok/skip · 2 = fail
import io, os, sys, json, re, datetime, hashlib, time, urllib.request, urllib.parse, urllib.error
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
    canonical_text_payload,
    verify_execution_authorization,
)
HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT_MAP = os.path.join(HERE, "feed_content_map.json")
LOG_DIR = os.path.join(ROOT, "automation-log", "fb-feed")
PUBLISHED = os.path.join(LOG_DIR, "published-fb.json")
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
GRAPH = "https://graph.facebook.com/v22.0"

DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
PAGE_ID = os.environ.get("FB_PAGE_ID", "")
TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
ACTOR = os.environ.get("PUBLICATION_ACTOR", "")
RECEIPT_NONCE = os.environ.get("PUBLICATION_RECEIPT_NONCE", "")
ATTEMPT_ROOT = Path(ROOT) / ".local-private" / "runtime" / "publication-attempts"
REMOTE_ID_PATTERN = re.compile(r"[0-9]{5,40}(?:_[0-9]{5,40})*\Z")


def now_th():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)


def log(msg):
    print("[fb_feed] " + msg)


def write_note(name, body):
    os.makedirs(INBOX, exist_ok=True)
    with io.open(os.path.join(INBOX, name), "w", encoding="utf-8") as handle:
        handle.write(body)


def fail(msg, date=""):
    log("FAIL: " + msg)
    write_note("FB-PUBLISH-FAIL.md",
               "# FB PUBLISH FAIL — %s\n\n- date: %s\n- error: %s\n- ดู social-autopost/runbook.md §FB\n"
               % (now_th().strftime("%Y-%m-%d %H:%M"), date, msg))
    sys.exit(2)


def _attempt_paths(placement_id):
    value = str(placement_id or "").strip()
    if not value:
        raise PublicationBlocked("placement_id is required for durable attempt state")
    key = hashlib.sha256(("facebook\0" + value).encode("utf-8")).hexdigest()
    return (
        ATTEMPT_ROOT / "pending" / "facebook" / (key + ".json"),
        ATTEMPT_ROOT / "terminal" / "facebook" / (key + ".json"),
    )


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
    if pending.exists() or terminal.exists():
        raise PublicationBlocked(
            "a durable Facebook attempt/terminal receipt already exists; "
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


def _finish_attempt(action, status, *, remote_platform_id="", reason="", details=None):
    normalized = str(remote_platform_id or "").strip()
    detail_value = details if isinstance(details, dict) else {}
    comment_id = str(detail_value.get("comment_id") or "").strip()
    if status in {"POSTED", "PARTIAL_REMOTE"} and REMOTE_ID_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked("Facebook remote terminal state requires a valid post id")
    if status == "POSTED" and REMOTE_ID_PATTERN.fullmatch(comment_id) is None:
        raise PublicationBlocked("Facebook POSTED requires a valid first-comment id")
    if normalized and REMOTE_ID_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked("Facebook remote post id has an invalid format")
    _pending, terminal = _attempt_paths(action.get("placement_id"))
    _write_exclusive_json(terminal, {
        "schema_version": 1,
        "status": status,
        "finalized_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "remote_platform_id": normalized or None,
        "permalink": None,
        "reason": str(reason or "")[:500] or None,
        "details": detail_value,
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


def api(path, params):
    params = dict(params)
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(GRAPH + path, data=data), timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        if '"code":190' in body:
            raise RuntimeError("PAGE TOKEN EXPIRED/INVALID (code 190) — ดู runbook §FB token. " + body)
        raise RuntimeError("HTTP %d: %s" % (e.code, body))


def main():
    date = os.environ.get("OVERRIDE_DATE") or now_th().strftime("%Y-%m-%d")
    with io.open(CONTENT_MAP, encoding="utf-8") as handle:
        cmap = json.load(handle)
    entry = cmap.get(date)
    if not entry:
        log("no feed entry for %s — ต้องเติมคลังโพสต์ (last=%s) · Cowork ส่ง 14-day pack มาเติมได้" % (date, max(cmap)))
        return 0
    os.makedirs(LOG_DIR, exist_ok=True)
    if os.path.exists(PUBLISHED):
        with io.open(PUBLISHED, encoding="utf-8") as handle:
            pub = json.load(handle)
    else:
        pub = {}
    if date in pub:
        log("already posted %s (post_id=%s) — skip (dedup)" % (date, pub[date].get("post_id")))
        return 0

    text, comment = entry["fbText"], entry["firstComment"]

    # comply fail-closed (กติกา order §6)
    if "ข้อมูลเพื่อการศึกษา" not in text:
        fail("body missing disclaimer — refuse to post", date)
    if "http://" in text or "https://" in text or "ngernduangold.com" in text:
        fail("URL in post body (ต้องอยู่คอมเมนต์แรกเท่านั้น) — refuse", date)
    if entry.get("affiliate") and "มีลิงก์พันธมิตร" not in text:
        fail("affiliate post missing affiliate marker — refuse", date)
    if re.search(r"\d+\s*%", text + comment):
        fail("bare % found — refuse", date)
    if "ngernduangold.com" not in comment:
        fail("firstComment missing link", date)

    if DRY_RUN:
        log("DRY_RUN=1 — validated %s | body %d chars | comment: %s" % (date, len(text), comment[:80]))
        return 0
    if not PAGE_ID or not TOKEN:
        write_note("FB-PUBLISH-SKIP.md",
                   "# FB LIVE BLOCKED — credentials missing — %s\n\n- date: %s\n"
                   "- No external publish was attempted.\n"
                   % (now_th().strftime("%Y-%m-%d %H:%M"), date))
        log("FAIL: explicit live run has no FB credentials; no network action attempted")
        return 2
    placement_id = entry.get("placement_id") or entry.get("placementId")
    action = None
    attempt_started = False
    terminal_written = False
    text_claim_key = ""
    post_id = ""
    comment_id = ""
    try:
        _assert_reconciliation_clear(placement_id)
        action = authorize_live_publication(
            repo=Path(ROOT), channel="facebook", actor=ACTOR,
            target_identity=PAGE_ID,
            approval=entry.get("approval"),
            content_id=entry.get("content_id") or entry.get("contentId"),
            placement_id=placement_id,
            caption=canonical_text_payload({
                "first_comment": comment,
                "post_body": text,
            }),
            asset_sha256=None,
            content_source_evidence={
                "source_file": "social-autopost/feed_content_map.json",
                "source_file_sha256": {
                    "social-autopost/feed_content_map.json": hashlib.sha256(
                        Path(CONTENT_MAP).read_bytes()
                    ).hexdigest(),
                },
                "entry": entry,
            },
            media_qa_path=None,
            scheduled_slot=(
                entry.get("scheduled_slot")
                or entry.get("scheduledSlot")
                or entry.get("scheduled_at")
            ),
            receipt_nonce=RECEIPT_NONCE,
        )
        claimed, text_claim_key, claim_reason = post_ledger.claim_text_publication(
            "facebook",
            text,
            action.get("scheduled_slot"),
            content_id=action.get("content_id"),
            placement_id=action.get("placement_id"),
            source="publish_fb-live",
            enforce_gap=True,
        )
        if not claimed:
            raise PublicationBlocked(
                "Facebook atomic publication claim blocked: %s" % claim_reason
            )
        _begin_attempt(action)
        attempt_started = True

        verify_execution_authorization(
            repo=Path(ROOT),
            action=action,
            caption=canonical_text_payload({
                "first_comment": comment,
                "post_body": text,
            }),
            asset_sha256=None,
            media_qa_path=None,
        )

        result = api("/%s/feed" % PAGE_ID, {"message": text})
        post_id = str(result.get("id") or "").strip() if isinstance(result, dict) else ""
        if REMOTE_ID_PATTERN.fullmatch(post_id) is None:
            raise RuntimeError("Facebook feed publish returned no valid remote post id")
        log("posted: " + post_id)

        # A first comment is a second irreversible public mutation. Revalidate
        # the consumed action immediately before it so a policy, calendar,
        # source, or authority revocation after the feed post stops here.
        verify_execution_authorization(
            repo=Path(ROOT),
            action=action,
            caption=canonical_text_payload({
                "first_comment": comment,
                "post_body": text,
            }),
            asset_sha256=None,
            media_qa_path=None,
        )
        result = api("/%s/comments" % post_id, {"message": comment})
        comment_id = str(result.get("id") or "").strip() if isinstance(result, dict) else ""
        if REMOTE_ID_PATTERN.fullmatch(comment_id) is None:
            raise RuntimeError("Facebook first comment returned no valid remote comment id")
        log("first comment: " + comment_id)

        _finish_attempt(
            action, "POSTED", remote_platform_id=post_id,
            details={"comment_id": comment_id},
        )
        terminal_written = True
        post_ledger.confirm(text_claim_key, post_id=post_id, status="POSTED")
        pub[date] = {
            "post_id": post_id,
            "comment_id": comment_id,
            "status": "POSTED",
            "ts": now_th().strftime("%Y-%m-%d %H:%M:%S+07:00"),
        }
        _atomic_json_write(PUBLISHED, pub)
        with io.open(
            os.path.join(LOG_DIR, "log-%s.md" % date), "w", encoding="utf-8"
        ) as handle:
            handle.write(
                "# FB post %s\n\n- post_id: %s\n- comment_id: %s\n\n```\n%s\n```\n\nfirst comment:\n```\n%s\n```\n"
                % (date, post_id, comment_id, text, comment)
            )
        log("DONE %s" % date)
        return 0
    except BaseException as exc:
        if attempt_started and not terminal_written:
            try:
                partial = REMOTE_ID_PATTERN.fullmatch(post_id) is not None
                _finish_attempt(
                    action,
                    "PARTIAL_REMOTE" if partial else "UNKNOWN",
                    remote_platform_id=post_id if partial else "",
                    reason=str(exc),
                    details={"comment_id": comment_id or None},
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
        fail("publication attempt is unresolved; automatic retry disabled; reconciliation-only: %s"
             % str(exc)[:300], date)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        fail(str(e))
