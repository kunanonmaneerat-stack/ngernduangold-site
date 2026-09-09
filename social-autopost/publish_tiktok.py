#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# publish_tiktok.py — retired/local-only TikTok plan checker + owner-gated Studio fallback
#
# Default execution is strictly read-only: it resolves the local plan and never imports
# Playwright, launches a browser, or uploads a file.  The retained ``--live`` fallback is
# interactive-only and remains blocked by local authority, media, hash and dedup gates.
#
# โหมด:
#   python publish_tiktok.py [--plan] [--date YYYY-MM-DD]  # local plan only
#   python publish_tiktok.py --date YYYY-MM-DD --live ... # interactive fallback only
#
# Exit: 0 = ok/skip · 2 = fail (เขียน alert + screenshot ไว้ที่ logs/)
import io, os, sys, json, time, datetime, argparse, hashlib, re, urllib.parse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "automation-log"))
import media_publish_guard
import post_ledger
from publication_authority import (
    PublicationBlocked,
    authorize_live_publication,
    verify_execution_authorization,
)
PROFILE = os.path.join(HERE, ".tiktok-profile")          # gitignored — session/cookies ห้าม commit
LOGS = os.path.join(HERE, "logs")                        # gitignored
CONTENT_MAP = os.path.join(HERE, "content_map.json")
PUBLISHED = os.path.join(LOGS, "published-tiktok.json")
ALERT = os.path.join(ROOT, "automation-log", "cowork-inbox", "TIKTOK-PUBLISH-FAIL.md")
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
ATTEMPT_ROOT = Path(ROOT) / ".local-private" / "runtime" / "publication-attempts"
VIDEO_ID_PATTERN = re.compile(r"[0-9]{10,30}\Z")
PERMALINK_PATH_PATTERN = re.compile(r"/@([A-Za-z0-9._-]+)/video/([0-9]{10,30})/?\Z")
ACCOUNT_HANDLE_PATTERN = re.compile(r"[A-Za-z0-9._-]+\Z")
MEDIA_READ_CHUNK = 1024 * 1024

# selectors รวมไว้ที่เดียว — TikTok เปลี่ยน UI บ่อย แก้ตรงนี้จุดเดียว (ดู runbook §selector)
SEL = {
    "file_input": 'input[type="file"]',
    "caption_editor": 'div[contenteditable="true"]',
    "post_button": 'button[data-e2e="post_video_button"], button:has-text("Post"), button:has-text("โพสต์")',
    "upload_done_hint": 'div:has-text("Uploaded"), span:has-text("Uploaded"), [data-e2e="upload_done"]',
    "ai_label_section": 'div:has-text("AI-generated content")',
    "ai_label_switch": 'div:has-text("AI-generated content") input[type="checkbox"], '
                       'div:has-text("AI-generated content") [role="switch"]',
}


def now_th():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)


def log(msg):
    print("[tiktok] " + msg)


def fail(msg, page=None, date=""):
    log("FAIL: " + msg)
    os.makedirs(LOGS, exist_ok=True)
    shot = ""
    if page is not None:
        shot = os.path.join(LOGS, "fail-%s.png" % now_th().strftime("%Y%m%d-%H%M%S"))
        try:
            page.screenshot(path=shot, full_page=True)
            log("screenshot -> " + shot)
        except Exception:
            shot = "(screenshot failed)"
    os.makedirs(os.path.dirname(ALERT), exist_ok=True)
    with io.open(ALERT, "w", encoding="utf-8") as handle:
        handle.write(
            "# TIKTOK PUBLISH FAIL — %s\n\n- date: %s\n- error: %s\n- screenshot: %s\n"
            "- ดู safety contract และ retired/local-only status ใน social-autopost/runbook.md\n"
            % (now_th().strftime("%Y-%m-%d %H:%M"), date, msg, shot))
    sys.exit(2)


def _attempt_paths(placement_id):
    value = str(placement_id or "").strip()
    if not value:
        raise PublicationBlocked("placement_id is required for durable attempt state")
    key = hashlib.sha256(("tiktok\0" + value).encode("utf-8")).hexdigest()
    return (
        ATTEMPT_ROOT / "pending" / "tiktok" / (key + ".json"),
        ATTEMPT_ROOT / "terminal" / "tiktok" / (key + ".json"),
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
            "a durable TikTok attempt/terminal receipt already exists; "
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


def _validated_permalink(value, target_account):
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    try:
        parsed = urllib.parse.urlsplit(urllib.parse.urljoin("https://www.tiktok.com", raw))
    except Exception:
        return "", ""
    if parsed.scheme.casefold() != "https" or (parsed.hostname or "").casefold() not in {
        "tiktok.com", "www.tiktok.com",
    }:
        return "", ""
    match = PERMALINK_PATH_PATTERN.fullmatch(parsed.path)
    if match is None:
        return "", ""
    expected = str(target_account or "").strip().casefold().lstrip("@")
    if not expected or match.group(1).casefold() != expected:
        return "", ""
    video_id = match.group(2)
    return "https://www.tiktok.com/@%s/video/%s" % (match.group(1), video_id), video_id


def _normalized_account_handle(value, label):
    raw = value.strip() if isinstance(value, str) else ""
    normalized = raw[1:] if raw.startswith("@") else raw
    if not normalized or ACCOUNT_HANDLE_PATTERN.fullmatch(normalized) is None:
        raise PublicationBlocked("TikTok %s account handle is missing or invalid" % label)
    return normalized.casefold()


def _require_account_reader(account_reader):
    """Reject live mode until a reviewed authenticated-account reader is injected."""
    if not callable(account_reader):
        raise PublicationBlocked(
            "authenticated TikTok account verifier is unavailable; live publication is blocked"
        )


def _verify_authenticated_account(page, target_account, account_reader):
    """Bind the current authenticated Studio session to the exact policy target.

    The publisher deliberately owns no DOM selector for this value. A reviewed
    integration must inject a reader; absence, read failure, malformed data, or
    mismatch all fail closed.
    """
    _require_account_reader(account_reader)
    expected = _normalized_account_handle(target_account, "target")
    try:
        observed = account_reader(page)
    except Exception as exc:
        raise PublicationBlocked(
            "authenticated TikTok account identity is unreadable"
        ) from exc
    try:
        actual = _normalized_account_handle(observed, "authenticated")
    except PublicationBlocked as exc:
        raise PublicationBlocked(
            "authenticated TikTok account identity is unreadable"
        ) from exc
    if actual != expected:
        raise PublicationBlocked(
            "authenticated TikTok account does not match the authorized target"
        )
    return "@" + actual


def _assert_exact_caption(editor, expected_caption):
    """Read back the existing composer and require exact authorized text."""
    if not isinstance(expected_caption, str):
        raise PublicationBlocked("authorized TikTok caption is invalid")
    try:
        actual = editor.evaluate("element => element.innerText")
    except Exception as exc:
        raise PublicationBlocked("TikTok caption readback is unavailable") from exc
    if not isinstance(actual, str):
        raise PublicationBlocked("TikTok caption readback is unreadable")
    if actual != expected_caption:
        raise PublicationBlocked("TikTok caption readback does not match authorized text")
    return actual


def _require_submission_reader(submission_reader):
    """No generic click is allowed without a reviewed response-bound executor."""
    if not callable(submission_reader):
        raise PublicationBlocked(
            "action-bound TikTok submission verifier is unavailable; live publication is blocked"
        )


def _submit_with_action_bound_evidence(page, post_button, action, submission_reader):
    """Delegate the click to a reviewed executor and validate its exact response binding.

    The repository intentionally supplies no production executor: a future
    integration must observe the platform response for this exact click. Scanning
    the account page for any newly visible permalink is not action-bound and is
    never accepted here.
    """
    _require_submission_reader(submission_reader)
    try:
        evidence = submission_reader(page, post_button, dict(action))
    except Exception as exc:
        raise PublicationBlocked(
            "TikTok action-bound submission evidence is unavailable"
        ) from exc
    if not isinstance(evidence, dict):
        raise PublicationBlocked("TikTok submission evidence is unreadable")
    if evidence.get("source") != "platform-post-response-v1":
        raise PublicationBlocked("TikTok submission evidence source is not action-bound")
    request_id = str(evidence.get("platform_request_id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", request_id) is None:
        raise PublicationBlocked("TikTok submission evidence has no platform request id")
    for field in (
        "content_id", "placement_id", "target_identity", "caption_sha256", "asset_sha256"
    ):
        if str(evidence.get(field) or "").strip() != str(action.get(field) or "").strip():
            raise PublicationBlocked(
                "TikTok submission evidence does not match authorized %s" % field
            )
    permalink, linked_id = _validated_permalink(
        evidence.get("permalink"), action.get("target_identity")
    )
    video_id = str(evidence.get("video_id") or "").strip()
    if not permalink or VIDEO_ID_PATTERN.fullmatch(video_id) is None or video_id != linked_id:
        raise PublicationBlocked(
            "TikTok submission evidence has no exact account-bound video result"
        )
    return {
        "platform_request_id": request_id,
        "permalink": permalink,
        "video_id": video_id,
    }


def _finish_attempt(action, status, *, remote_platform_id="", permalink="", reason=""):
    normalized_id = str(remote_platform_id or "").strip()
    normalized_link = ""
    linked_id = ""
    if permalink:
        normalized_link, linked_id = _validated_permalink(
            permalink, action.get("target_identity")
        )
    if status == "POSTED":
        if not normalized_link or VIDEO_ID_PATTERN.fullmatch(normalized_id) is None:
            raise PublicationBlocked("TikTok POSTED requires a verified permalink and video id")
        if normalized_id != linked_id:
            raise PublicationBlocked("TikTok permalink/video id binding does not match")
    elif normalized_id or permalink:
        raise PublicationBlocked("unverified TikTok terminal state cannot carry remote success evidence")
    _pending, terminal = _attempt_paths(action.get("placement_id"))
    _write_exclusive_json(terminal, {
        "schema_version": 1,
        "status": status,
        "finalized_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "remote_platform_id": normalized_id or None,
        "permalink": normalized_link or None,
        "reason": str(reason or "")[:500] or None,
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


def _sha256_exact_asset(path):
    """Hash the exact regular file selected for the browser upload boundary."""
    selected = Path(path).resolve(strict=True)
    if not selected.is_file():
        raise PublicationBlocked("TikTok media asset is not a regular file")
    before = selected.stat()
    digest = hashlib.sha256()
    total = 0
    with selected.open("rb") as handle:
        while True:
            chunk = handle.read(MEDIA_READ_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    after = selected.stat()
    if (
        total != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise PublicationBlocked("TikTok media asset changed while hashing")
    return digest.hexdigest().upper()


def _fresh_media_boundary_hash(asset, receipt_path, expected_hash):
    """Rerun the full media gate and independent hash at a mutation boundary."""
    selected = Path(asset).resolve(strict=True)
    report = Path(receipt_path)
    media_result = media_publish_guard.evaluate(selected, report, repo=Path(ROOT))
    if not isinstance(media_result, dict) or media_result.get("verdict") != "PASS":
        findings = media_result.get("findings", []) if isinstance(media_result, dict) else []
        raise PublicationBlocked(
            "fresh media publication guard blocked: "
            + ("; ".join(str(item) for item in findings[:3]) or "no PASS verdict")
        )
    guard_hash = str(media_result.get("sha256") or "").strip().upper()
    fresh_hash = _sha256_exact_asset(selected)
    expected = str(expected_hash or "").strip().upper()
    for label, value in (
        ("guard", guard_hash), ("fresh", fresh_hash), ("authority", expected)
    ):
        if len(value) != 64 or any(ch not in "0123456789ABCDEF" for ch in value):
            raise PublicationBlocked("TikTok %s media hash is invalid" % label)
    if guard_hash != fresh_hash:
        raise PublicationBlocked("TikTok full media guard hash does not match exact asset bytes")
    if fresh_hash != expected:
        raise PublicationBlocked("TikTok media asset changed after authority was consumed")
    return fresh_hash


def _verified_upload_payload(asset, receipt_path, expected_hash):
    """Return immutable Playwright bytes only when all three hashes agree.

    Passing a path to ``set_input_files`` lets another process replace that file
    after our check but before Playwright reads it.  The byte buffer returned here
    is the exact hash-bound object that crosses the upload boundary.
    """
    selected = Path(asset).resolve(strict=True)
    report = Path(receipt_path)
    media_result = media_publish_guard.evaluate(selected, report, repo=Path(ROOT))
    if not isinstance(media_result, dict) or media_result.get("verdict") != "PASS":
        findings = media_result.get("findings", []) if isinstance(media_result, dict) else []
        raise PublicationBlocked(
            "fresh media publication guard blocked: "
            + ("; ".join(str(item) for item in findings[:3]) or "no PASS verdict")
        )
    try:
        payload_bytes = selected.read_bytes()
    except OSError as exc:
        raise PublicationBlocked("TikTok media asset is unreadable at upload boundary") from exc
    guard_hash = str(media_result.get("sha256") or "").strip().upper()
    payload_hash = hashlib.sha256(payload_bytes).hexdigest().upper()
    expected = str(expected_hash or "").strip().upper()
    for label, value in (
        ("guard", guard_hash), ("payload", payload_hash), ("authority", expected)
    ):
        if len(value) != 64 or any(ch not in "0123456789ABCDEF" for ch in value):
            raise PublicationBlocked("TikTok %s media hash is invalid" % label)
    if guard_hash != payload_hash:
        raise PublicationBlocked(
            "TikTok full media guard hash does not match immutable upload bytes"
        )
    if payload_hash != expected:
        raise PublicationBlocked("TikTok upload bytes changed after authority was consumed")
    return {
        "name": selected.name,
        "mimeType": "video/mp4",
        "buffer": payload_bytes,
    }, payload_hash


def launch(p, headed=True):
    os.makedirs(PROFILE, exist_ok=True)
    # เบราว์เซอร์ตรง ๆ ไม่แต่ง fingerprint/stealth — นโยบาย: ไม่ทำ evasion
    return p.chromium.launch_persistent_context(
        PROFILE, headless=not headed, viewport={"width": 1280, "height": 860},
        args=["--disable-blink-features=AutomationControlled"] if False else [])


def logged_in(page):
    page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    return "login" not in page.url


def mode_login(_p=None):
    """Legacy flag retained only to fail closed without opening a browser."""
    log("LOGIN DISABLED: retired publisher is local-plan-only; no browser was opened")
    return 2


def mode_check(_p=None):
    """Legacy flag retained only to fail closed without opening a browser."""
    log("CHECK DISABLED: retired publisher is local-plan-only; no browser was opened")
    return 2


def _load_content_map():
    try:
        with io.open(CONTENT_MAP, encoding="utf-8") as handle:
            value = json.load(handle)
    except Exception as exc:
        raise ValueError("content_map is missing or unreadable: %s" % str(exc)[:120]) from exc
    if not isinstance(value, dict):
        raise ValueError("content_map must contain a JSON object")
    return value


def _last_plan_date(cmap):
    return max(cmap) if cmap else "none"


def mode_post(
    p, date, live, actor=None, target_account=None, receipt_nonce=None,
    account_reader=None, submission_reader=None,
):
    # A direct caller cannot turn the old "dry run" back into a browser/upload path.
    if not live:
        return mode_plan(date)

    if date != now_th().date().isoformat():
        fail("live date must be today's Asia/Bangkok date (got %s)" % date, date=date)
    try:
        cmap = _load_content_map()
    except ValueError as exc:
        fail(str(exc), date=date)
    entry = cmap.get(date)
    if not isinstance(entry, dict):
        fail("no content_map entry for %s (last=%s)" % (date, _last_plan_date(cmap)), date=date)
    os.makedirs(LOGS, exist_ok=True)
    if os.path.exists(PUBLISHED):
        try:
            with io.open(PUBLISHED, encoding="utf-8") as handle:
                pub = json.load(handle)
        except Exception as exc:
            fail("published registry is unreadable: %s" % str(exc)[:120], date=date)
        if not isinstance(pub, dict):
            fail("published registry must contain a JSON object", date=date)
    else:
        pub = {}
    if date in pub:
        fail("already recorded for %s — duplicate live attempt blocked" % date, date=date)
    clip_name = entry.get("clipFile")
    if not isinstance(clip_name, str) or not clip_name.strip():
        fail("plan clipFile is missing", date=date)
    reels_root = (Path(ROOT) / "reels").resolve()
    try:
        clip_path = (reels_root / clip_name).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        fail("clip not found: %s" % str(exc)[:120], date=date)
    if clip_path.parent != reels_root or not clip_path.is_file():
        fail("clip must be one exact regular file under reels/", date=date)
    clip = str(clip_path)
    if not os.path.exists(clip):
        fail("clip not found: %s" % clip, date=date)
    caption = entry.get("tiktokCaption")
    if not isinstance(caption, str):
        fail("plan tiktokCaption is missing", date=date)
    if "ข้อมูลเพื่อการศึกษา" not in caption or "ผลิตด้วย AI" not in caption:
        fail("caption missing disclaimer/AI disclosure — refuse to post", date=date)
    try:
        _require_account_reader(account_reader)
        _require_submission_reader(submission_reader)
    except PublicationBlocked as exc:
        fail(str(exc), date=date)

    report_value = entry.get("mediaReceipt") or entry.get("media_receipt")
    if not isinstance(report_value, str) or not report_value.strip():
        fail("hash-bound mediaReceipt is missing", date=date)
    try:
        media_result = media_publish_guard.evaluate(
            Path(clip), Path(report_value.strip()), repo=Path(ROOT)
        )
    except Exception as exc:
        fail("media publication guard is unavailable: %s" % str(exc)[:120], date=date)
    if not isinstance(media_result, dict) or media_result.get("verdict") != "PASS":
        findings = media_result.get("findings", []) if isinstance(media_result, dict) else []
        fail("media publication guard blocked: %s" %
             ("; ".join(str(item) for item in findings[:3]) or "no PASS verdict"), date=date)
    actual_hash = str(media_result.get("sha256") or "").strip().upper()
    if len(actual_hash) != 64 or any(ch not in "0123456789ABCDEF" for ch in actual_hash):
        fail("media publication guard returned no exact SHA-256", date=date)
    content_id = entry.get("contentId") or entry.get("content_id")
    if not isinstance(content_id, str) or not content_id.strip():
        fail("plan contentId is missing", date=date)
    try:
        with io.open(os.path.join(ROOT, report_value), encoding="utf-8") as handle:
            receipt = json.load(handle)
    except Exception as exc:
        fail("media receipt cannot be read for content-id binding: %s" % str(exc)[:120], date=date)
    novelty = receipt.get("novelty_review") if isinstance(receipt, dict) else None
    receipt_content_id = novelty.get("content_id") if isinstance(novelty, dict) else None
    if receipt_content_id != content_id.strip():
        fail("media receipt content_id does not match plan contentId", date=date)

    try:
        duplicate_text, reason, _ = post_ledger.is_duplicate_text("tiktok", caption)
    except Exception as exc:
        fail("caption dedup gate is unavailable: %s" % str(exc)[:120], date=date)
    if duplicate_text:
        fail("caption duplicate blocked: %s" % reason, date=date)

    # A CLI actor label and repo-editable approval JSON are never live authority.
    # The exact private receipt is consumed only after every pure local media/text
    # validation has passed, and before any dedup mutation, browser, or upload.
    placement_id = entry.get("placement_id") or entry.get("placementId")
    action = None
    try:
        _assert_reconciliation_clear(placement_id)
        action = authorize_live_publication(
            repo=Path(ROOT), channel="tiktok", actor=actor,
            target_identity=target_account,
            approval=entry.get("approval"),
            content_id=content_id,
            placement_id=placement_id,
            caption=caption,
            asset_sha256=actual_hash,
            content_source_evidence={
                "source_file": "social-autopost/content_map.json",
                "source_file_sha256": {
                    "social-autopost/content_map.json": hashlib.sha256(
                        Path(CONTENT_MAP).read_bytes()
                    ).hexdigest(),
                },
                "entry": entry,
            },
            media_qa_path=report_value,
            scheduled_slot=(
                entry.get("scheduled_slot")
                or entry.get("scheduledSlot")
                or entry.get("scheduled_at")
            ),
            receipt_nonce=receipt_nonce,
        )
    except PublicationBlocked as exc:
        fail("publication authority blocked: %s" % exc, date=date)

    try:
        claimed, claim_key, reason = post_ledger.claim(
            "tiktok", "sha256:" + str(action.get("asset_sha256") or ""),
            action.get("scheduled_slot"),
            source="publish_tiktok-live", enforce_gap=True,
        )
    except Exception as exc:
        fail("media dedup claim is unavailable: %s" % str(exc)[:120], date=date)
    if not claimed:
        fail("media dedup blocked: %s" % reason, date=date)

    try:
        _begin_attempt(action)
    except PublicationBlocked as exc:
        fail("durable attempt blocked: %s" % exc, date=date)

    terminal_written = False
    driver = None
    ctx = None
    page = None
    try:
        if p is None:
            # Import and start Playwright only after authority, dedup and durable
            # PENDING_REMOTE state. Default/plan/login/check never reach this line.
            from playwright.sync_api import sync_playwright
            driver = sync_playwright().start()
            p = driver
        ctx = launch(p, headed=True)
        page = ctx.new_page()
        if not logged_in(page):
            fail("session หลุด — รัน --login ใหม่", page, date)
        _verify_authenticated_account(page, target_account, account_reader)
        log("upload page OK: " + page.url)

        # Re-run the full media gate and independently hash the exact asset at
        # this boundary.  Never reuse the earlier pre-browser hash.
        upload_payload, actual_hash = _verified_upload_payload(
            clip, report_value, action.get("asset_sha256")
        )
        # Hold the shared corpus generation claim through the browser upload
        # mutation; a registry/manifest advance after the earlier scan blocks
        # before Playwright can transmit the file.
        with media_publish_guard.publication_corpus_claim(
            clip,
            report_value,
            expected_asset_sha256=action.get("asset_sha256"),
            expected_content_id=action.get("content_id"),
            repo=Path(ROOT),
        ):
            verify_execution_authorization(
                repo=Path(ROOT),
                action=action,
                caption=caption,
                asset_sha256=actual_hash,
                media_qa_path=report_value,
            )
            page.set_input_files(SEL["file_input"], upload_payload)
        log("file set: " + os.path.basename(clip))
        # รออัปโหลด/ประมวลผล (ไฟล์ ~2MB ปกติไม่นาน แต่เผื่อ 3 นาที)
        try:
            page.wait_for_selector(SEL["upload_done_hint"], timeout=180000)
        except Exception:
            page.wait_for_timeout(20000)   # บาง UI ไม่มีข้อความ Uploaded — ให้เวลาเพิ่มแล้วไปต่อ
        log("upload processed")

        ed = page.locator(SEL["caption_editor"]).first
        ed.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        ed.type(caption, delay=15)
        _assert_exact_caption(ed, caption)
        log("caption typed (%d chars)" % len(caption))

        # AI-generated label: TikTok toggle ได้ — พยายามเปิด ถ้าหา switch ไม่เจอไม่ถือว่า fail
        try:
            sec = page.locator(SEL["ai_label_section"]).first
            sec.scroll_into_view_if_needed(timeout=5000)
            sw = page.locator(SEL["ai_label_switch"]).first
            state = sw.get_attribute("aria-checked") or sw.get_attribute("checked") or ""
            if state in ("false", "", None):
                sw.click()
                log("AI-generated label: toggled ON")
            else:
                log("AI-generated label: already ON")
        except Exception as e:
            log("AI label switch not found (%s) — พึ่งคำ 'ผลิตด้วย AI' ในแคปชัน (มีแล้ว) + แจ้งใน log" % e)

        shot = os.path.join(LOGS, "ready-%s.png" % date)
        page.screenshot(path=shot, full_page=True)
        log("pre-post screenshot -> " + shot)

        if not live:
            fail("internal safety error: non-live execution reached browser", page, date)

        # Upload processing can take minutes.  Re-run the complete media gate
        # and exact byte hash again before the irreversible Post click.
        actual_hash = _fresh_media_boundary_hash(clip, report_value, action.get("asset_sha256"))
        with media_publish_guard.publication_corpus_claim(
            clip,
            report_value,
            expected_asset_sha256=action.get("asset_sha256"),
            expected_content_id=action.get("content_id"),
            repo=Path(ROOT),
        ):
            verify_execution_authorization(
                repo=Path(ROOT),
                action=action,
                caption=caption,
                asset_sha256=actual_hash,
                media_qa_path=report_value,
            )
            _verify_authenticated_account(page, target_account, account_reader)
            _assert_exact_caption(ed, caption)
            submission = _submit_with_action_bound_evidence(
                page,
                page.locator(SEL["post_button"]).first,
                action,
                submission_reader,
            )
        permalink = submission["permalink"]
        video_id = submission["video_id"]
        log("Post response verified — รอภาพยืนยัน")
        shot2 = os.path.join(LOGS, "posted-%s.png" % date)
        page.screenshot(path=shot2, full_page=True)
        _finish_attempt(
            action, "POSTED", remote_platform_id=video_id, permalink=permalink
        )
        terminal_written = True
        post_ledger.confirm(claim_key, post_id=video_id, status="POSTED")
        pub[date] = {"file": entry["clipFile"], "ts": now_th().strftime("%Y-%m-%d %H:%M:%S+07:00"),
                     "screenshot": shot2, "sha256": actual_hash,
                     "status": "POSTED", "post_id": video_id,
                     "permalink": permalink}
        _atomic_json_write(PUBLISHED, pub)
        log("POSTED %s -> %s (screenshot: %s)" % (date, permalink, shot2))
        return 0
    except SystemExit as exc:
        if not terminal_written:
            try:
                _finish_attempt(action, "UNKNOWN", reason=str(exc))
            except Exception:
                pass
        raise
    except Exception as e:
        if not terminal_written:
            try:
                _finish_attempt(action, "UNKNOWN", reason=str(e))
            except Exception:
                pass
        if terminal_written:
            fail(
                "remote publication is terminal POSTED, but local ledger/registry "
                "reconciliation is incomplete; automatic retry disabled: %s"
                % str(e)[:300],
                page,
                date,
            )
        fail("publication attempt is UNKNOWN; automatic retry disabled; reconciliation-only: %s"
             % str(e)[:300], page, date)
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
        if driver is not None:
            try:
                driver.stop()
            except Exception:
                pass


def mode_plan(date):
    """resolve entry + comply check ของวันที่กำหนด โดยไม่เปิดเบราว์เซอร์ (ใช้ monitor/พิสูจน์การเลือกคลิป)"""
    try:
        cmap = _load_content_map()
    except ValueError as exc:
        log("PLAN FAIL: " + str(exc))
        return 2
    entry = cmap.get(date)
    if not isinstance(entry, dict):
        log("PLAN %s: no entry (last=%s)" % (date, _last_plan_date(cmap)))
        return 2
    clip_name = entry.get("clipFile")
    cap = entry.get("tiktokCaption")
    clip = os.path.join(ROOT, "reels", clip_name) if isinstance(clip_name, str) else ""
    exists = bool(clip and os.path.isfile(clip))
    comply = isinstance(cap, str) and "ข้อมูลเพื่อการศึกษา" in cap and "ผลิตด้วย AI" in cap
    log("PLAN %s: clip=%s (exists=%s) | affiliate=%s | comply=%s" % (
        date, clip_name or "MISSING", exists, entry.get("affiliate"), "PASS" if comply else "FAIL"))
    if isinstance(cap, str):
        log("PLAN caption: " + cap.replace(chr(10), " | ")[:200])
    return 0 if comply and exists else 2


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--actor", default="",
                    help="explicit role key from .system_control/role_capabilities.json")
    ap.add_argument("--target-account", default="",
                    help="explicit account handle that must match policy")
    ap.add_argument(
        "--receipt-nonce",
        default=os.environ.get("PUBLICATION_RECEIPT_NONCE", ""),
        help="nonce of an owner-provisioned private one-time publication receipt",
    )
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--date", default="")
    a = ap.parse_args(argv)
    if a.login:
        return mode_login()
    if a.check:
        return mode_check()
    date = a.date or now_th().strftime("%Y-%m-%d")
    if not a.live:
        return mode_plan(date)
    if a.plan:
        ap.error("--plan and --live are mutually exclusive")
    return mode_post(None, date, True, a.actor, a.target_account, a.receipt_nonce)


if __name__ == "__main__":
    sys.exit(main())
