#!/usr/bin/env python3
"""Adversarial checks for private, one-time publication receipts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.publication_authority import (
    PublicationBlocked,
    authorize_live_publication,
    caption_sha256,
    content_source_sha256,
    media_qa_evidence_sha256,
    no_media_qa_sha256,
    verify_execution_authorization,
)
from tools import publication_authority as authority_module


NOW = datetime(2026, 8, 16, 9, tzinfo=timezone.utc)
SLOT = "2026-08-16T16:00:00+07:00"
VIDEO_BYTES = b"publication-authority-video-fixture"
ASSET = hashlib.sha256(VIDEO_BYTES).hexdigest()
CAPTION = "exact publication caption"
THREADS_CAPTION = (
    "ก่อนเริ่มสัปดาห์ ลองเขียนรายการที่ต้องจัดการ แล้วเลือกเพียงหนึ่งเรื่องที่ทำได้ก่อน\n\n"
    "ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน · ผลิตด้วย AI"
)
MEDIA_QA_PATH = "automation-log/media-qa/video.json"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def validation() -> dict:
    return {
        # approved_by is deliberately irrelevant: this repo-editable object is
        # validation evidence and cannot authenticate the owner.
        "approved_by": "owner",
        "approved_at": "2026-08-16T08:00:00+07:00",
        "source_checked_at": "2026-08-16T08:00:00+07:00",
        "publication": "approved",
        "privacy_gate": "pass",
        "public_identity": "pass",
        "source_gate": "pass",
        "dedup": "pass",
        "qa": "pass",
    }


def content_evidence(repo: Path) -> dict:
    relative = "fixture/content.json"
    return {
        "source_file": relative,
        "source_file_sha256": {
            relative: hashlib.sha256((repo / relative).read_bytes()).hexdigest()
        },
        "entry": {"content_id": "content-1", "caption": CAPTION},
    }


def receipt(repo: Path, nonce: str, **overrides) -> dict:
    value = {
        "schema_version": 2,
        "content_id": "content-1",
        "placement_id": "content-1__facebook_main",
        "channel": "facebook",
        "target_identity": "page-123",
        "caption_sha256": caption_sha256(CAPTION),
        "asset_sha256": None,
        "scheduled_slot": SLOT,
        "expires_at": "2026-08-16T10:00:00+00:00",
        "nonce": nonce,
    }
    value.update(overrides)
    value.setdefault(
        "policy_sha256",
        hashlib.sha256(
            (repo / ".system_control/policy.json").read_bytes()
        ).hexdigest(),
    )
    value.setdefault(
        "role_capabilities_sha256",
        hashlib.sha256(
            (repo / ".system_control/role_capabilities.json").read_bytes()
        ).hexdigest(),
    )
    value.setdefault(
        "content_calendar_sha256",
        hashlib.sha256(
            (repo / ".system_control/content_calendar.json").read_bytes()
        ).hexdigest(),
    )
    value.setdefault(
        "content_source_sha256",
        content_source_sha256(content_evidence(repo), validation()),
    )
    if value["asset_sha256"] is None:
        media_hash = no_media_qa_sha256(value["content_id"], value["placement_id"])
    else:
        media_hash = media_qa_evidence_sha256(
            (repo / MEDIA_QA_PATH).read_bytes(),
            (repo / ".system_control/generative_media_policy.json").read_bytes(),
        )
    value.setdefault("media_qa_sha256", media_hash)
    return value


def put_receipt(repo: Path, value: dict) -> Path:
    path = (
        repo
        / ".local-private/runtime/publication-receipts/pending"
        / (value["nonce"] + ".json")
    )
    write_json(path, value)
    return path


def base_call(repo: Path, nonce: str | None, **overrides):
    values = {
        "repo": repo,
        "channel": "facebook",
        "actor": "owner",
        "target_identity": "page-123",
        "approval": validation(),
        "content_id": "content-1",
        "placement_id": "content-1__facebook_main",
        "caption": CAPTION,
        "asset_sha256": None,
        "content_source_evidence": content_evidence(repo),
        "media_qa_path": None,
        "scheduled_slot": SLOT,
        "receipt_nonce": nonce,
        "now": NOW,
        "guard_runner": lambda _relative: 0,
    }
    values.update(overrides)
    return authorize_live_publication(**values)


def blocked(label: str, call, contains: str | None = None) -> None:
    try:
        call()
    except PublicationBlocked as exc:
        if contains and contains.casefold() not in str(exc).casefold():
            raise AssertionError(f"{label}: unexpected reason: {exc}") from exc
        print("PASS", label)
        return
    raise AssertionError(label)


def initialize_repo(repo: Path, *, role_default: object = "deny") -> None:
    write_json(repo / "fixture/content.json", {"content_id": "content-1"})
    video_path = repo / "reels/video.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(VIDEO_BYTES)
    write_json(
        repo / ".system_control/policy.json",
        {
            "channels": {
                "facebook": {
                    "state": "manual",
                    "publication_authorized": True,
                    "page_id": "page-123",
                },
                "instagram": {
                    "state": "manual",
                    "publication_authorized": True,
                    "account_id": "ig-123",
                },
                "tiktok": {
                    "state": "testing",
                    "publication_authorized": True,
                    "account_handle": "@account",
                },
                "youtube": {
                    "state": "active",
                    "publication_authorized": True,
                    "channel_id": "youtube-channel-123",
                },
            }
        },
    )
    roles = {
        "actors": {
            "owner": {"social_publish": True},
            "codex": {"social_publish": False},
        }
    }
    if role_default is not None:
        roles["default"] = role_default
    write_json(repo / ".system_control/role_capabilities.json", roles)
    accounts = {}
    placements = []
    for channel in ("facebook", "instagram", "tiktok", "youtube"):
        account = channel + "_main"
        accounts[account] = {"channel": channel, "policy_channel": channel}
        placements.append(
            {
                "placement_id": f"content-1__{account}",
                "content_id": "content-1",
                "account": account,
                "date": "2026-08-16",
                "time": "16:00",
                "publication_authorized": True,
            }
        )
    write_json(
        repo / ".system_control/content_calendar.json",
        {
            "schema_version": 2,
            "timezone": "Asia/Bangkok",
            "accounts": accounts,
            "placements": placements,
        },
    )
    write_json(
        repo / MEDIA_QA_PATH,
        {
            "schema_version": 1,
            "asset": "reels/video.mp4",
            "sha256": ASSET,
            "media_type": "video",
            "media_origin": {
                "generator_origin": "LOCAL_HTML_SVG_FFMPEG_WINDOWS_TTS",
                "contains_flow_pixels": False,
                "contains_flow_audio": False,
                "synthid_expected": False,
            },
            "reviewed_at": "2026-08-16T08:00:00+07:00",
            "novelty_review": {
                "status": "PASS",
                "content_id": "content-1",
                "reviewer": "fixture-reviewer",
            },
            "human_audio_review": {
                "status": "PASS",
                "reviewer_is_human": True,
                "reviewer_type": "OWNER",
                "reviewer": "fixture-owner",
                "asset_sha256": ASSET,
                "reviewed_at": "2026-08-16T08:00:00+07:00",
            },
            "watermark": {
                "visual_review": {
                    "status": "PASS",
                    "reviewer": "fixture-human-reviewer",
                    "evidence": ["reels/video.mp4"],
                    "evidence_sha256": {"reels/video.mp4": ASSET},
                },
                "automated_scan": {"status": "PASS", "fps": 3.0},
            },
        },
    )
    write_json(
        repo / ".system_control/generative_media_policy.json",
        {
            "schema_version": 1,
            "strict_no_watermark": True,
            "google_flow": {
                "role": "IDEATION_STORYBOARD_ONLY",
                "final_pixels_allowed": False,
                "final_audio_allowed": False,
            },
            "final_asset_required_fields": [
                "generator_origin", "contains_flow_pixels",
                "contains_flow_audio", "synthid_expected",
            ],
            "allowed_final_origins": [
                "LOCAL_HTML_SVG_FFMPEG_WINDOWS_TTS"
            ],
        },
    )


def next_nonce(index: int) -> str:
    return (f"receipt-{index:04d}-" + "x" * 64)[:48]


def initialize_threads_repo(repo: Path) -> None:
    """Synthetic owner provision only; never touches the real project policy."""
    initialize_repo(repo)
    policy_path = repo / ".system_control/policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["channels"]["threads"] = {
        "state": "manual", "publication_authorized": True,
        "account_handle": "@Page_Account",
    }
    policy["public_identity"] = {
        "canonical_name": "เงินเดือนสมองทอง", "page_only": True,
        "forbidden_personal_claim_patterns": [], "forbidden_public_speakers": [],
    }
    write_json(policy_path, policy)
    calendar_path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
    calendar = {"schema_version": 1, "timezone": "Asia/Bangkok", "accounts": {}, "placements": []}
    # This synthetic execution contract is deliberately not the real project's
    # editorial_plan_only_no_publication calendar, which remains blocked.
    calendar["purpose"] = "owner_controlled_manual_publication"
    calendar["accounts"]["threads_main"] = {"channel": "threads", "policy_channel": "threads"}
    calendar["placements"].append({
        "placement_id": "content-1__threads_main", "content_id": "content-1",
        "account": "threads_main", "date": "2026-08-16", "time": "16:00",
        "publication_authorized": True, "format": "text", "media": None,
        "status": "OWNER_APPROVED", "slot_state": "APPROVED_IMMEDIATE",
        "media_receipt": None, "blockers": [], "gates": {
            "publication_authority": "PASS", "source_review": "NOT_REQUIRED",
            "media": "NOT_REQUIRED", "dedup": "PASS", "page_identity": "PASS",
        },
    })
    write_json(calendar_path, calendar)
    (repo / "fixture/threads-caption.txt").write_bytes(THREADS_CAPTION.encode("utf-8"))
    write_json(repo / "fixture/threads-review.json", {
        "schema_version": 1, "content_id": "content-1",
        "caption_sha256": caption_sha256(THREADS_CAPTION),
        "decision": "SOURCE_NEUTRAL_EXACT_TEXT", "source_ids": [],
        "checked_at": "2026-08-16T08:00:00+00:00",
        "expires_at": "2026-08-16T10:00:00+00:00",
    })


def threads_evidence(repo: Path) -> dict:
    evidence = content_evidence(repo)
    evidence["entry"]["caption"] = THREADS_CAPTION
    relative = "fixture/threads-caption.txt"
    evidence["publication_text_file"] = relative
    evidence["source_file_sha256"][relative] = hashlib.sha256(
        (repo / relative).read_bytes()
    ).hexdigest()
    relative = "fixture/threads-review.json"
    evidence["source_neutral_review_file"] = relative
    evidence["source_file_sha256"][relative] = hashlib.sha256(
        (repo / relative).read_bytes()
    ).hexdigest()
    return evidence


def threads_receipt(repo: Path, nonce: str, *, source=None, approval=None, **overrides) -> dict:
    values = {
        "schema_version": 3,
        "content_calendar_path": authority_module.THREADS_MANUAL_CALENDAR_PATH.as_posix(),
        "content_calendar_sha256": hashlib.sha256(
            (repo / authority_module.THREADS_MANUAL_CALENDAR_PATH).read_bytes()
        ).hexdigest(),
        "channel": "threads", "target_identity": "@page_account",
        "placement_id": "content-1__threads_main",
        "caption_sha256": caption_sha256(THREADS_CAPTION),
        "content_source_sha256": content_source_sha256(
            threads_evidence(repo) if source is None else source,
            validation() if approval is None else approval,
        ),
    }
    values.update(overrides)
    return receipt(repo, nonce, **values)


def threads_call(repo: Path, nonce: str | None, **overrides):
    values = {
        "channel": "threads", "target_identity": "page_account",
        "placement_id": "content-1__threads_main",
        "caption": THREADS_CAPTION,
        "content_source_evidence": threads_evidence(repo),
    }
    values.update(overrides)
    return base_call(repo, nonce, **values)


def check_threads_authority() -> int:
    checks = 0
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_threads_repo(repo)
        blocked("Threads missing private owner receipt", lambda: threads_call(repo, None), "receipt")
        checks += 1
        nonce = next_nonce(200)
        pending = put_receipt(repo, threads_receipt(repo, nonce))
        action = threads_call(repo, nonce)
        assert action["target_identity"] == "page_account" and not pending.exists()
        assert verify_execution_authorization(
            repo=repo, action=action, caption=THREADS_CAPTION, asset_sha256=None,
            media_qa_path=None, now=NOW,
        )["verified"] is True
        print("PASS Threads exact text-only action is consumed and revalidated")
        checks += 1
        blocked("Threads consumed receipt cannot authorize twice", lambda: threads_call(repo, nonce), "consumed")
        checks += 1
        blocked("Threads expired execution slot", lambda: verify_execution_authorization(
            repo=repo, action=action, caption=THREADS_CAPTION, asset_sha256=None,
            media_qa_path=None, now=datetime(2026, 8, 16, 9, 11, tzinfo=timezone.utc),
        ), "passed")
        checks += 1
        blocked("Threads execution caption drift", lambda: verify_execution_authorization(
            repo=repo, action=action, caption=THREADS_CAPTION + " drift", asset_sha256=None,
            media_qa_path=None, now=NOW,
        ), "caption changed")
        checks += 1
        (repo / "fixture/threads-caption.txt").write_bytes(b"changed")
        blocked("Threads bound text file drift after consume", lambda: verify_execution_authorization(
            repo=repo, action=action, caption=THREADS_CAPTION, asset_sha256=None,
            media_qa_path=None, now=NOW,
        ), "hash does not match")
        checks += 1

    call_cases = (
        ("unauthorized actor", {"actor": "codex"}, "social_publish"),
        ("wrong account", {"target_identity": "other_page"}, "does not match policy"),
        ("URL is not an account handle", {"target_identity": "https://www.threads.com/@page_account"}, "single Threads"),
        ("multiple at signs", {"target_identity": "@@page_account"}, "single Threads"),
        ("unsupported video", {"asset_sha256": ASSET}, "text-only"),
        ("media receipt on text", {"media_qa_path": MEDIA_QA_PATH}, "text-only"),
        ("empty text", {"caption": " "}, "non-empty"),
        ("caption not exact file", {"caption": CAPTION + " changed"}, "exact caption"),
        ("early slot", {"now": datetime(2026, 8, 16, 8, 59, tzinfo=timezone.utc)}, "early"),
    )
    for index, (label, overrides, reason) in enumerate(call_cases, 210):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(repo, nonce))
            blocked("Threads " + label, lambda: threads_call(repo, nonce, **overrides), reason)
            assert pending.exists()
            checks += 1

    proof_cases = (
        ("expired proof", {"expires_at": "2026-08-16T08:59:00+00:00"}, "expired"),
        ("mismatched caption proof", {"caption_sha256": "a" * 64}, "caption binding"),
        ("mismatched source proof", {"content_source_sha256": "a" * 64}, "evidence binding"),
        ("mismatched target proof", {"target_identity": "wrong_page"}, "target binding"),
        ("wrong placement proof", {"placement_id": "different__threads_main"}, "placement_id binding"),
    )
    for index, (label, overrides, reason) in enumerate(proof_cases, 230):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(repo, nonce, **overrides))
            blocked("Threads " + label, lambda: threads_call(repo, nonce), reason)
            assert pending.exists()
            checks += 1

    for index, field in enumerate(authority_module.REQUIRED_VALIDATIONS, 250):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            approval = validation()
            approval[field] = "blocked"
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(repo, nonce, approval=approval))
            blocked("Threads requires " + field, lambda: threads_call(repo, nonce, approval=approval), "not approved")
            assert pending.exists()
            checks += 1

    for index, (field, value, reason) in enumerate((
        ("publication_authorized", False, "not explicitly true"),
        ("format", "video", "text-only"),
        ("media", "video.mp4", "text-only"),
        ("gates", {"media": "PASS"}, "NOT_REQUIRED"),
        ("status", "PLANNED_BLOCKED", "unresolved blockers"),
        ("status", None, "not owner-approved"),
        ("status", "UNKNOWN", "not owner-approved"),
        ("status", "POSTED", "not owner-approved"),
        ("slot_state", None, "not owner-approved"),
        ("slot_state", "RESERVED_BLOCKED", "not owner-approved"),
        ("blockers", ["source_review"], "unresolved blockers"),
    ), 270):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
            calendar = json.loads(path.read_text(encoding="utf-8"))
            calendar["placements"][-1][field] = value
            write_json(path, calendar)
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(repo, nonce))
            blocked("Threads calendar " + field, lambda: threads_call(repo, nonce), reason)
            assert pending.exists()
            checks += 1

    for index, mode in enumerate(("missing_binding", "stale_source", "policy_false", "editorial_only_calendar"), 290):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            source, approval = threads_evidence(repo), validation()
            if mode == "missing_binding":
                source["source_file_sha256"].pop("fixture/threads-caption.txt")
                reason = "bound SHA-256"
            elif mode == "stale_source":
                approval["source_checked_at"] = "2026-08-15T08:00:00+07:00"
                reason = "stale"
            elif mode == "editorial_only_calendar":
                path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
                calendar = json.loads(path.read_text(encoding="utf-8"))
                calendar["purpose"] = "editorial_plan_only_no_publication"
                write_json(path, calendar)
                reason = "not an editorial-only plan"
            else:
                path = repo / ".system_control/policy.json"
                policy = json.loads(path.read_text(encoding="utf-8"))
                policy["channels"]["threads"]["publication_authorized"] = False
                write_json(path, policy)
                reason = "not explicitly true"
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(repo, nonce, source=source, approval=approval))
            blocked("Threads " + mode, lambda: threads_call(
                repo, nonce, content_source_evidence=source, approval=approval,
            ), reason)
            assert pending.exists()
            checks += 1
    for field in ("publication_authority", "source_review", "media", "dedup", "page_identity"):
        for state in (None, "BLOCKED"):
            with tempfile.TemporaryDirectory() as raw:
                repo = Path(raw)
                initialize_threads_repo(repo)
                path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
                calendar = json.loads(path.read_text(encoding="utf-8"))
                gates = calendar["placements"][-1]["gates"]
                if state is None:
                    del gates[field]
                else:
                    gates[field] = state
                write_json(path, calendar)
                nonce = next_nonce(300)
                pending = put_receipt(repo, threads_receipt(repo, nonce))
                blocked("Threads missing/blocked placement gate " + field,
                        lambda: threads_call(repo, nonce), "calendar gates")
                assert pending.exists()
                checks += 1

    review_cases = (
        ("source review expired", {"expires_at": NOW.isoformat()}, "stale"),
        ("source review future", {"checked_at": "2026-08-16T09:01:00+00:00"}, "future"),
        ("source review overlong", {"expires_at": "2026-08-18T08:00:00+00:00"}, "24 hours"),
        ("source review wrong content", {"content_id": "other"}, "binding is invalid"),
        ("source review wrong caption", {"caption_sha256": "b" * 64}, "binding is invalid"),
        ("source review carries sources", {"source_ids": ["bot-credit"]}, "binding is invalid"),
        ("source review generic pass", {"decision": "PASS"}, "binding is invalid"),
        ("source review boolean schema", {"schema_version": True}, "binding is invalid"),
        ("source review unexpected fields", {"extra": True}, "fields are not exact"),
    )
    for index, (label, changes, reason) in enumerate(review_cases, 310):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            path = repo / "fixture/threads-review.json"
            review = json.loads(path.read_text(encoding="utf-8"))
            review.update(changes)
            write_json(path, review)
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(repo, nonce))
            blocked("Threads " + label, lambda: threads_call(repo, nonce), reason)
            assert pending.exists()
            checks += 1

    for index, mode in enumerate(("missing_review", "unbound_review", "known_factual", "risky_caption"), 330):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            content_id, caption = "content-1", THREADS_CAPTION
            if mode == "known_factual":
                content_id = "kn-43"
                path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
                calendar = json.loads(path.read_text(encoding="utf-8"))
                calendar["placements"][-1]["content_id"] = content_id
                write_json(path, calendar)
            if mode == "risky_caption":
                caption = "รับประกันกำไรแน่นอน\n\n" + THREADS_CAPTION
                (repo / "fixture/threads-caption.txt").write_bytes(caption.encode("utf-8"))
                path = repo / "fixture/threads-review.json"
                review = json.loads(path.read_text(encoding="utf-8"))
                review["caption_sha256"] = caption_sha256(caption)
                write_json(path, review)
            source = threads_evidence(repo)
            if mode == "missing_review":
                del source["source_neutral_review_file"]
                reason = "source_neutral_review_file"
            elif mode == "unbound_review":
                del source["source_file_sha256"]["fixture/threads-review.json"]
                reason = "bound SHA-256"
            elif mode == "known_factual":
                reason = "factual source namespace"
            else:
                reason = "text validation is blocked"
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(
                repo, nonce, source=source, content_id=content_id,
                caption_sha256=caption_sha256(caption),
            ))
            blocked("Threads " + mode, lambda: threads_call(
                repo, nonce, content_source_evidence=source,
                content_id=content_id, caption=caption,
            ), reason)
            assert pending.exists()
            checks += 1

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_threads_repo(repo)
        path = repo / "fixture/threads-review.json"
        review = json.loads(path.read_text(encoding="utf-8"))
        review["expires_at"] = "2026-08-16T09:02:00+00:00"
        write_json(path, review)
        nonce = next_nonce(350)
        put_receipt(repo, threads_receipt(repo, nonce))
        action = threads_call(repo, nonce)
        blocked("Threads review expiry is enforced after receipt consumption", lambda: verify_execution_authorization(
            repo=repo, action=action, caption=THREADS_CAPTION, asset_sha256=None,
            media_qa_path=None, now=datetime(2026, 8, 16, 9, 3, tzinfo=timezone.utc),
        ), "source-neutral review is stale")
        checks += 1
    return checks


def check_manual_calendar_selection() -> int:
    checks = 0
    path_cases = (
        ("wrong selected path", {"content_calendar_path": ".system_control/content_calendar.json"}, "selected calendar path"),
        ("arbitrary selected path", {"content_calendar_path": "fixture/other.json"}, "selected calendar path"),
        ("wrong selected hash", {"content_calendar_sha256": "c" * 64}, "evidence binding"),
    )
    for index, (label, changes, reason) in enumerate(path_cases, 400):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            nonce = next_nonce(index)
            pending = put_receipt(repo, threads_receipt(repo, nonce, **changes))
            blocked("Threads manual " + label, lambda: threads_call(repo, nonce), reason)
            assert pending.exists()
            checks += 1

    for index, mode in enumerate(("missing", "empty", "mixed_channel", "account_alias", "duplicate", "extra_row_field", "bad_time", "boolean_schema"), 410):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
            document = json.loads(path.read_text(encoding="utf-8"))
            nonce = next_nonce(index)
            if mode == "missing":
                pending = put_receipt(repo, threads_receipt(repo, nonce))
                path.unlink()
                reason = "missing or unreadable"
            else:
                if mode == "empty":
                    document["placements"] = []
                    reason = "empty"
                elif mode == "mixed_channel":
                    document["accounts"]["threads_main"]["policy_channel"] = "facebook"
                    reason = "mix channels"
                elif mode == "account_alias":
                    document["accounts"]["another_threads_account"] = document["accounts"]["threads_main"]
                    reason = "accounts"
                elif mode == "duplicate":
                    document["placements"].append(dict(document["placements"][0]))
                    reason = "exactly once"
                elif mode == "extra_row_field":
                    document["placements"][0]["unexpected"] = True
                    reason = "fields are not exact"
                elif mode == "bad_time":
                    document["placements"][0]["time"] = "25:00"
                    reason = "slot is invalid"
                else:
                    document["schema_version"] = True
                    reason = "schema/purpose"
                write_json(path, document)
                pending = put_receipt(repo, threads_receipt(repo, nonce))
            blocked("Threads manual calendar " + mode, lambda: threads_call(repo, nonce), reason)
            assert pending.exists()
            checks += 1

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_threads_repo(repo)
        nonce = next_nonce(430)
        value = threads_receipt(repo, nonce, schema_version=2)
        value.pop("content_calendar_path")
        pending = put_receipt(repo, value)
        blocked("Threads rejects legacy schema2 calendar ambiguity", lambda: threads_call(repo, nonce), "schema_version")
        assert pending.exists()
        checks += 1
        nonce = next_nonce(431)
        value = threads_receipt(repo, nonce)
        value.pop("content_calendar_path")
        pending = put_receipt(repo, value)
        blocked("Threads schema3 requires calendar path", lambda: threads_call(repo, nonce), "fields are not exact")
        assert pending.exists()
        checks += 1
        nonce = next_nonce(432)
        pending = put_receipt(repo, receipt(repo, nonce, schema_version=3,
            content_calendar_path=authority_module.THREADS_MANUAL_CALENDAR_PATH.as_posix()))
        blocked("legacy channel cannot take Threads schema3", lambda: base_call(repo, nonce), "schema_version")
        assert pending.exists()
        checks += 1

    for index, mode in enumerate(("action_path", "consumed_path", "calendar_drift", "calendar_removed"), 440):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            initialize_threads_repo(repo)
            nonce = next_nonce(index)
            put_receipt(repo, threads_receipt(repo, nonce))
            action = threads_call(repo, nonce)
            if mode == "action_path":
                action["content_calendar_path"] = ".system_control/content_calendar.json"
                reason = "selected calendar path"
            elif mode == "consumed_path":
                path = repo / ".local-private/runtime/publication-receipts/consumed" / (nonce + ".json")
                record = json.loads(path.read_text(encoding="utf-8"))
                record["receipt"]["content_calendar_path"] = ".system_control/content_calendar.json"
                write_json(path, record)
                reason = "selected calendar path"
            elif mode == "calendar_drift":
                path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
                document = json.loads(path.read_text(encoding="utf-8"))
                document["placements"][0]["time"] = "16:01"
                write_json(path, document)
                reason = "content_calendar_sha256 drifted"
            else:
                (repo / authority_module.THREADS_MANUAL_CALENDAR_PATH).unlink()
                reason = "missing or unreadable"
            blocked("Threads manual execution " + mode, lambda: verify_execution_authorization(
                repo=repo, action=action, caption=THREADS_CAPTION,
                asset_sha256=None, media_qa_path=None, now=NOW,
            ), reason)
            checks += 1

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_threads_repo(repo)
        nonce = next_nonce(450)
        pending = put_receipt(repo, threads_receipt(repo, nonce))
        def mutate_manual(_relative):
            path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
            document = json.loads(path.read_text(encoding="utf-8"))
            document["placements"][0]["time"] = "16:01"
            write_json(path, document)
            return 0
        blocked("manual calendar mutation before consume", lambda: threads_call(
            repo, nonce, guard_runner=mutate_manual,
        ), "changed during authorization")
        assert pending.exists()
        checks += 1

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_threads_repo(repo)
        nonce = next_nonce(451)
        put_receipt(repo, threads_receipt(repo, nonce))
        # A different plan is neither read nor silently promoted for Threads.
        (repo / ".system_control/content_calendar.json").write_text("invalid editorial JSON", encoding="utf-8")
        action = threads_call(repo, nonce)
        assert action["content_calendar_path"] == authority_module.THREADS_MANUAL_CALENDAR_PATH.as_posix()
        assert verify_execution_authorization(repo=repo, action=action, caption=THREADS_CAPTION,
            asset_sha256=None, media_qa_path=None, now=NOW)["verified"] is True
        print("PASS Threads selects only its fixed private manual calendar")
        checks += 1

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_repo(repo)
        # Legacy selection stays schema2 + the existing path, even when an
        # unrelated private Threads calendar is malformed.
        path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("invalid manual JSON", encoding="utf-8")
        nonce = next_nonce(452)
        put_receipt(repo, receipt(repo, nonce))
        action = base_call(repo, nonce)
        assert "content_calendar_path" not in action
        assert verify_execution_authorization(repo=repo, action=action, caption=CAPTION,
            asset_sha256=None, media_qa_path=None, now=NOW)["verified"] is True
        print("PASS legacy calendar and schema2 receipt selection is unchanged")
        checks += 1
    for mode in ("calendar", "review"):
        with tempfile.TemporaryDirectory() as raw:
            from tools import editorial_draft_gate
            repo = Path(raw)
            initialize_threads_repo(repo)
            nonce = next_nonce(460)
            put_receipt(repo, threads_receipt(repo, nonce))
            action = threads_call(repo, nonce)
            real_lint = editorial_draft_gate.check_source_neutral_text
            def mutate_after_real_lint(text, *, policy):
                result = real_lint(text, policy=policy)
                if mode == "calendar":
                    path = repo / authority_module.THREADS_MANUAL_CALENDAR_PATH
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["placements"][0]["time"] = "16:01"
                else:
                    path = repo / "fixture/threads-review.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["decision"] = "CHANGED"
                write_json(path, value)
                return result
            with patch.object(editorial_draft_gate, "check_source_neutral_text", side_effect=mutate_after_real_lint):
                blocked("Threads detects in-flight execution " + mode + " drift", lambda: verify_execution_authorization(
                    repo=repo, action=action, caption=THREADS_CAPTION,
                    asset_sha256=None, media_qa_path=None, now=NOW,
                ), "changed during")
            checks += 1
    return checks


def main() -> int:
    checks = check_threads_authority() + check_manual_calendar_selection()
    for label, raw in (
        ("duplicate policy JSON keys fail closed", '{"channels":{},"channels":{"facebook":{}}}'),
        ("overflow policy JSON numbers fail closed", '{"channels":{},"probe":1e999}'),
    ):
        try:
            authority_module._strict_json_loads(raw)
        except ValueError:
            print("PASS " + label)
        else:
            raise AssertionError(label)
        checks += 1
    with tempfile.TemporaryDirectory() as raw:
        malformed = Path(raw) / "nonfinite.json"
        malformed.write_text('{"unexpected":NaN}', encoding="utf-8")
        blocked(
            "non-finite publication evidence JSON is rejected",
            lambda: authority_module._object_evidence(malformed, "fixture evidence"),
            "missing or unreadable",
        )
        checks += 1
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_repo(repo)

        blocked(
            "actor='owner' plus repo approval cannot authorize without private receipt",
            lambda: base_call(repo, None),
            "private publication receipt",
        )
        checks += 1

        nonce = next_nonce(1)
        pending = put_receipt(repo, receipt(repo, nonce))
        result = base_call(repo, nonce)
        assert result["consumed"] is True and not pending.exists()
        assert (
            repo
            / ".local-private/runtime/publication-receipts/consumed"
            / f"{nonce}.json"
        ).is_file()
        print("PASS exact receipt is atomically consumed")
        checks += 1
        execution = verify_execution_authorization(
            repo=repo,
            action=result,
            caption=CAPTION,
            asset_sha256=None,
            media_qa_path=None,
            now=NOW,
        )
        assert execution["verified"] is True
        print("PASS execution revalidation accepts the exact consumed action")
        checks += 1

        expiry_nonce = next_nonce(3)
        expiry_value = receipt(
            repo, expiry_nonce, expires_at="2026-08-16T09:05:00+00:00"
        )
        put_receipt(repo, expiry_value)
        expiry_action = base_call(repo, expiry_nonce)
        assert expiry_action["expires_at"] == "2026-08-16T09:05:00+00:00"
        assert verify_execution_authorization(
            repo=repo,
            action=expiry_action,
            caption=CAPTION,
            asset_sha256=None,
            media_qa_path=None,
            now=datetime(2026, 8, 16, 9, 4, 59, tzinfo=timezone.utc),
        )["verified"] is True
        print("PASS execution receipt is valid strictly before expiry")
        checks += 1

        for label, execution_time in (
            ("at expiry", datetime(2026, 8, 16, 9, 5, tzinfo=timezone.utc)),
            ("after expiry", datetime(2026, 8, 16, 9, 6, tzinfo=timezone.utc)),
        ):
            mutation_calls = []

            def verify_then_mutate(current=execution_time):
                verify_execution_authorization(
                    repo=repo,
                    action=expiry_action,
                    caption=CAPTION,
                    asset_sha256=None,
                    media_qa_path=None,
                    now=current,
                )
                mutation_calls.append("remote mutation")

            blocked(
                "execution receipt blocks " + label,
                verify_then_mutate,
                "expired",
            )
            assert mutation_calls == []
            checks += 1

        missing_expiry_action = dict(expiry_action)
        missing_expiry_action.pop("expires_at")
        blocked(
            "execution action missing receipt expiry",
            lambda: verify_execution_authorization(
                repo=repo,
                action=missing_expiry_action,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=NOW,
            ),
            "expires_at is missing",
        )
        checks += 1
        mismatched_expiry_action = {
            **expiry_action,
            "expires_at": "2026-08-16T09:06:00+00:00",
        }
        blocked(
            "execution action expiry mismatches consumed receipt",
            lambda: verify_execution_authorization(
                repo=repo,
                action=mismatched_expiry_action,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=NOW,
            ),
            "no longer matches",
        )
        checks += 1

        consumed_path = (
            repo
            / ".local-private/runtime/publication-receipts/consumed"
            / f"{expiry_nonce}.json"
        )
        consumed_record = json.loads(consumed_path.read_text(encoding="utf-8"))
        malformed_record = json.loads(json.dumps(consumed_record))
        malformed_record["receipt"]["expires_at"] = "not-a-time"
        write_json(consumed_path, malformed_record)
        blocked(
            "malformed consumed receipt expiry",
            lambda: verify_execution_authorization(
                repo=repo,
                action=expiry_action,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=NOW,
            ),
            "expires_at is invalid",
        )
        checks += 1
        missing_record = json.loads(json.dumps(consumed_record))
        missing_record["receipt"].pop("expires_at")
        write_json(consumed_path, missing_record)
        blocked(
            "consumed receipt expiry is missing",
            lambda: verify_execution_authorization(
                repo=repo,
                action=expiry_action,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=NOW,
            ),
            "contract is invalid",
        )
        checks += 1
        future_record = json.loads(json.dumps(consumed_record))
        future_record["consumed_at"] = "2026-08-16T09:04:00+00:00"
        write_json(consumed_path, future_record)
        blocked(
            "future consumed receipt chronology",
            lambda: verify_execution_authorization(
                repo=repo,
                action=expiry_action,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=NOW,
            ),
            "chronology is in the future",
        )
        write_json(consumed_path, consumed_record)
        checks += 1

        freshness_nonce = next_nonce(4)
        put_receipt(
            repo,
            receipt(
                repo,
                freshness_nonce,
                expires_at="2026-08-18T03:00:00+00:00",
            ),
        )
        freshness_action = base_call(repo, freshness_nonce)
        blocked(
            "source freshness is rechecked after authorization delay",
            lambda: verify_execution_authorization(
                repo=repo,
                action=freshness_action,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=datetime(2026, 8, 17, 2, tzinfo=timezone.utc),
            ),
            "source_checked_at is stale",
        )
        checks += 1

        policy_path = repo / ".system_control/policy.json"
        execution_policy_original = policy_path.read_bytes()
        execution_policy_drift = json.loads(execution_policy_original.decode("utf-8"))
        execution_policy_drift["post_consume_drift_fixture"] = True
        write_json(policy_path, execution_policy_drift)
        blocked(
            "post-consume policy drift blocks execution",
            lambda: verify_execution_authorization(
                repo=repo,
                action=result,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=NOW,
            ),
            "drifted after receipt consumption",
        )
        policy_path.write_bytes(execution_policy_original)
        checks += 1
        blocked(
            "post-consume immediate slot expiry blocks execution",
            lambda: verify_execution_authorization(
                repo=repo,
                action=result,
                caption=CAPTION,
                asset_sha256=None,
                media_qa_path=None,
                now=datetime(2026, 8, 16, 9, 10, 1, tzinfo=timezone.utc),
            ),
            "passed",
        )
        checks += 1
        blocked(
            "consumed receipt replay",
            lambda: base_call(repo, nonce),
            "replay",
        )
        checks += 1

        youtube_nonce = next_nonce(2)
        put_receipt(
            repo,
            receipt(
                repo,
                youtube_nonce,
                channel="youtube",
                target_identity="youtube-channel-123",
                placement_id="content-1__youtube_main",
                asset_sha256=ASSET,
            ),
        )
        youtube_action = base_call(
            repo,
            youtube_nonce,
            channel="youtube",
            target_identity="youtube-channel-123",
            placement_id="content-1__youtube_main",
            asset_sha256=ASSET,
            media_qa_path=MEDIA_QA_PATH,
            now=datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc),
        )
        assert youtube_action["channel"] == "youtube"
        assert youtube_action["target_identity"] == "youtube-channel-123"
        print("PASS YouTube exact private receipt is supported")
        checks += 1
        blocked(
            "post-consume YouTube slot too-close blocks execution",
            lambda: verify_execution_authorization(
                repo=repo,
                action=youtube_action,
                caption=CAPTION,
                asset_sha256=ASSET,
                media_qa_path=MEDIA_QA_PATH,
                now=datetime(2026, 8, 16, 8, 45, tzinfo=timezone.utc),
            ),
            "too close",
        )
        checks += 1

        # Every action field is independently bound. A failed binding must not
        # consume the receipt, allowing the exact requested action to use it once.
        mismatch_cases = (
            ("content id", {"content_id": "content-other"}, {}),
            ("placement id", {"placement_id": "other__facebook"}, {}),
            ("channel", {
                "channel": "tiktok",
                "target_identity": "@account",
                "placement_id": "content-1__tiktok_main",
                "asset_sha256": ASSET,
                "media_qa_path": MEDIA_QA_PATH,
            }, {}),
            ("target", {}, {"target_identity": "page-other"}),
            ("caption", {"caption": CAPTION + " changed"}, {}),
            ("asset", {
                "channel": "instagram",
                "target_identity": "ig-123",
                "asset_sha256": ASSET,
                "placement_id": "content-1__instagram_main",
                "media_qa_path": MEDIA_QA_PATH,
            }, {
                "channel": "instagram",
                "target_identity": "ig-123",
                "asset_sha256": "b" * 64,
                "placement_id": "content-1__instagram_main",
            }),
            ("scheduled slot", {"scheduled_slot": "2026-08-16T16:01:00+07:00"}, {}),
        )
        for offset, (label, call_overrides, receipt_overrides) in enumerate(mismatch_cases, 10):
            case_nonce = next_nonce(offset)
            value = receipt(repo, case_nonce, **receipt_overrides)
            put_receipt(repo, value)
            blocked(
                label + " binding mismatch",
                lambda c=call_overrides, n=case_nonce: base_call(repo, n, **c),
                {
                    "placement id": "placement",
                    "scheduled slot": "slot",
                }.get(label, "binding"),
            )
            checks += 1

        expired_nonce = next_nonce(30)
        put_receipt(
            repo,
            receipt(repo, expired_nonce, expires_at="2026-08-16T08:59:59+00:00"),
        )
        blocked(
            "expired receipt",
            lambda: base_call(repo, expired_nonce),
            "expired",
        )
        checks += 1

        media_nonce = next_nonce(31)
        put_receipt(
            repo,
            receipt(
                repo,
                media_nonce,
                channel="instagram",
                target_identity="ig-123",
                placement_id="content-1__instagram_main",
            ),
        )
        blocked(
            "media receipt cannot use null asset hash",
            lambda: base_call(
                repo,
                media_nonce,
                channel="instagram",
                target_identity="ig-123",
            ),
            "requires an asset",
        )
        checks += 1

        guard_nonce = next_nonce(32)
        guard_pending = put_receipt(repo, receipt(repo, guard_nonce))
        blocked(
            "local guard failure happens before receipt consumption",
            lambda: base_call(
                repo,
                guard_nonce,
                guard_runner=lambda relative: 2 if "public_identity" in relative else 0,
            ),
            "public identity",
        )
        assert guard_pending.is_file()
        checks += 1

        # Schema v2 binds every exact evidence input. Benign semantic-preserving
        # edits still invalidate the receipt and never consume it.
        for offset, (label, relative) in enumerate(
            (
                ("policy evidence drift", ".system_control/policy.json"),
                ("role evidence drift", ".system_control/role_capabilities.json"),
                ("calendar evidence drift", ".system_control/content_calendar.json"),
            ),
            50,
        ):
            case_nonce = next_nonce(offset)
            pending = put_receipt(repo, receipt(repo, case_nonce))
            evidence_path = repo / relative
            original = evidence_path.read_bytes()
            changed = json.loads(original.decode("utf-8"))
            changed["benign_drift_fixture"] = offset
            write_json(evidence_path, changed)
            blocked(label, lambda n=case_nonce: base_call(repo, n), "evidence binding")
            assert pending.is_file()
            evidence_path.write_bytes(original)
            checks += 1

        content_nonce = next_nonce(53)
        content_pending = put_receipt(repo, receipt(repo, content_nonce))
        changed_content = content_evidence(repo)
        changed_content["entry"]["caption"] += " drift"
        blocked(
            "content-source evidence drift",
            lambda: base_call(
                repo, content_nonce, content_source_evidence=changed_content
            ),
            "content_source_sha256",
        )
        assert content_pending.is_file()
        checks += 1

        media_drift_nonce = next_nonce(54)
        media_drift_pending = put_receipt(
            repo,
            receipt(
                repo,
                media_drift_nonce,
                channel="instagram",
                target_identity="ig-123",
                placement_id="content-1__instagram_main",
                asset_sha256=ASSET,
            ),
        )
        media_path = repo / MEDIA_QA_PATH
        media_original = media_path.read_bytes()
        media_changed = json.loads(media_original.decode("utf-8"))
        media_changed["benign_drift_fixture"] = True
        write_json(media_path, media_changed)
        blocked(
            "media-QA evidence drift",
            lambda: base_call(
                repo,
                media_drift_nonce,
                channel="instagram",
                target_identity="ig-123",
                placement_id="content-1__instagram_main",
                asset_sha256=ASSET,
                media_qa_path=MEDIA_QA_PATH,
            ),
            "media_qa_sha256",
        )
        assert media_drift_pending.is_file()
        media_path.write_bytes(media_original)
        checks += 1

        for offset, (label, mutate, expected) in enumerate((
            (
                "missing media origin blocks before private receipt consumption",
                lambda value: value.pop("media_origin"),
                "unknown origin",
            ),
            (
                "Flow pixels block before private receipt consumption",
                lambda value: value["media_origin"].update(
                    {"contains_flow_pixels": True}
                ),
                "Flow pixels",
            ),
            (
                "missing human audio review blocks before private receipt consumption",
                lambda value: value.pop("human_audio_review"),
                "human audio review",
            ),
            (
                "wrong visual evidence hash blocks before private receipt consumption",
                lambda value: value["watermark"]["visual_review"][
                    "evidence_sha256"
                ].update({"reels/video.mp4": "0" * 64}),
                "visual evidence SHA-256",
            ),
        ), 70):
            changed = json.loads(media_original.decode("utf-8"))
            mutate(changed)
            write_json(media_path, changed)
            case_nonce = next_nonce(offset)
            pending = put_receipt(
                repo,
                receipt(
                    repo, case_nonce, channel="instagram",
                    target_identity="ig-123",
                    placement_id="content-1__instagram_main",
                    asset_sha256=ASSET,
                ),
            )
            blocked(
                label,
                lambda n=case_nonce: base_call(
                    repo, n, channel="instagram", target_identity="ig-123",
                    placement_id="content-1__instagram_main",
                    asset_sha256=ASSET, media_qa_path=MEDIA_QA_PATH,
                ),
                expected,
            )
            assert pending.is_file()
            media_path.write_bytes(media_original)
            checks += 1

        missing_hash_nonce = next_nonce(55)
        missing_hash_receipt = receipt(repo, missing_hash_nonce)
        missing_hash_receipt.pop("content_calendar_sha256")
        missing_hash_pending = put_receipt(repo, missing_hash_receipt)
        blocked(
            "schema v2 missing evidence hash",
            lambda: base_call(repo, missing_hash_nonce),
            "missing=content_calendar_sha256",
        )
        assert missing_hash_pending.is_file()
        checks += 1

        invalid_hash_nonce = next_nonce(56)
        invalid_hash_pending = put_receipt(
            repo,
            receipt(repo, invalid_hash_nonce, policy_sha256="not-a-hash"),
        )
        blocked(
            "schema v2 malformed evidence hash",
            lambda: base_call(repo, invalid_hash_nonce),
            "exact SHA-256",
        )
        assert invalid_hash_pending.is_file()
        checks += 1

        v1_nonce = next_nonce(57)
        v1_pending = put_receipt(
            repo,
            receipt(repo, v1_nonce, schema_version=1),
        )
        blocked(
            "legacy schema v1 receipt is rejected",
            lambda: base_call(repo, v1_nonce),
            "schema_version",
        )
        assert v1_pending.is_file()
        checks += 1

        in_flight_nonce = next_nonce(58)
        in_flight_pending = put_receipt(repo, receipt(repo, in_flight_nonce))
        policy_path = repo / ".system_control/policy.json"
        policy_original = policy_path.read_bytes()

        def mutate_policy_after_validation(_relative):
            changed = json.loads(policy_original.decode("utf-8"))
            changed["in_flight_drift_fixture"] = True
            write_json(policy_path, changed)
            return 0

        blocked(
            "policy drift during authorization",
            lambda: base_call(
                repo, in_flight_nonce, guard_runner=mutate_policy_after_validation
            ),
            "changed during authorization",
        )
        assert in_flight_pending.is_file()
        policy_path.write_bytes(policy_original)
        checks += 1

        for offset, (label, moment, reason) in enumerate(
            (
                (
                    "immediate execution before Bangkok slot",
                    datetime(2026, 8, 16, 8, 59, 59, tzinfo=timezone.utc),
                    "early",
                ),
                (
                    "immediate execution after Bangkok slot window",
                    datetime(2026, 8, 16, 9, 10, 1, tzinfo=timezone.utc),
                    "passed",
                ),
            ),
            60,
        ):
            case_nonce = next_nonce(offset)
            pending = put_receipt(repo, receipt(repo, case_nonce))
            blocked(
                label,
                lambda n=case_nonce, t=moment: base_call(repo, n, now=t),
                reason,
            )
            assert pending.is_file()
            checks += 1

        for offset, (label, moment, reason) in enumerate(
            (
                (
                    "scheduled execution more than 24h early",
                    datetime(2026, 8, 15, 8, 59, 59, tzinfo=timezone.utc),
                    "too early",
                ),
                (
                    "scheduled execution inside 15m safety lead",
                    datetime(2026, 8, 16, 8, 45, 0, tzinfo=timezone.utc),
                    "too close",
                ),
                (
                    "scheduled execution after Bangkok slot",
                    datetime(2026, 8, 16, 9, 0, 0, tzinfo=timezone.utc),
                    "passed",
                ),
            ),
            70,
        ):
            case_nonce = next_nonce(offset)
            pending = put_receipt(
                repo,
                receipt(
                    repo,
                    case_nonce,
                    channel="youtube",
                    target_identity="youtube-channel-123",
                    placement_id="content-1__youtube_main",
                    asset_sha256=ASSET,
                ),
            )
            blocked(
                label,
                lambda n=case_nonce, t=moment: base_call(
                    repo,
                    n,
                    channel="youtube",
                    target_identity="youtube-channel-123",
                    placement_id="content-1__youtube_main",
                    asset_sha256=ASSET,
                    media_qa_path=MEDIA_QA_PATH,
                    now=t,
                ),
                reason,
            )
            assert pending.is_file()
            checks += 1

        # The exclusive consumed marker admits exactly one concurrent winner.
        race_nonce = next_nonce(33)
        put_receipt(repo, receipt(repo, race_nonce))

        def race_call():
            try:
                base_call(repo, race_nonce)
                return "allowed"
            except PublicationBlocked:
                return "blocked"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: race_call(), range(2)))
        assert sorted(outcomes) == ["allowed", "blocked"], outcomes
        print("PASS atomic concurrent consume admits one winner")
        checks += 1

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        initialize_repo(repo, role_default=None)
        blocked(
            "missing role default deny",
            lambda: base_call(repo, next_nonce(40)),
            "default to deny",
        )
        checks += 1
        initialize_repo(repo, role_default="allow")
        blocked(
            "non-deny role default",
            lambda: base_call(repo, next_nonce(41)),
            "default to deny",
        )
        checks += 1

    root = Path(__file__).resolve().parents[1]
    direct_publishers = {
        "instagram": root / "automation/ig_publish.py",
        "facebook": root / "social-autopost/publish_fb.py",
        "tiktok": root / "social-autopost/publish_tiktok.py",
        "youtube": root / "tools/yt_upload_batch2.py",
    }
    required_call_bindings = {
        "content_id",
        "placement_id",
        "caption",
        "asset_sha256",
        "content_source_evidence",
        "media_qa_path",
        "scheduled_slot",
        "receipt_nonce",
    }
    for channel, path in direct_publishers.items():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "authorize_live_publication"
        ]
        assert len(calls) == 1, (channel, len(calls))
        keywords = {item.arg for item in calls[0].keywords if item.arg}
        assert required_call_bindings <= keywords, (channel, keywords)
        print(f"PASS {channel} direct publisher binds the private receipt contract")
        checks += 1

    instagram_source = direct_publishers["instagram"].read_text(encoding="utf-8")
    instagram_main = instagram_source[instagram_source.index("def main():"):]
    media_guard = instagram_main.index("media_publish_guard.evaluate(")
    authority = instagram_main.index("authorize_live_publication(")
    attempt = instagram_main.index("_begin_attempt(action)")
    hosted_get = instagram_main.index("hosted_evidence = _verify_hosted_video(")
    evidence = instagram_main.index("_record_hosted_media_evidence(", hosted_get)
    create = instagram_main.index('result = api("/%s/media"')
    publish = instagram_main.index('"/%s/media_publish"', create)
    create_verify = instagram_main.index("verify_execution_authorization(", evidence)
    publish_verify = instagram_main.index("verify_execution_authorization(", create)
    assert media_guard < authority < attempt < hosted_get < evidence < create_verify < create
    assert create < publish_verify < publish
    print("PASS Instagram exact hosted bytes and authority precede both mutations")
    checks += 1

    print(f"publication authority: {checks}/{checks} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
