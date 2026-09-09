#!/usr/bin/env python3
"""Fail-closed freshness guard for the 24-30 August evergreen draft pack.

This guard proves only that the exact reviewed copy remains an evergreen,
no-source candidate.  It never grants publication authority, acknowledges an
official source, refreshes a source checksum, or changes the content calendar.
Factual, promotional, merchant-specific, rate, or source-required copy fails
closed and must use the normal content-scoped official-source workflow.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_PACK = ROOT / "automation-log" / "WEEK-CONTENT-PACK_20260824-30.json"
DEFAULT_RECEIPT = (
    ROOT / "automation-log" / "WEEK-CONTENT-FRESHNESS_20260823.json"
)
DEFAULT_SNAPSHOT = (
    ROOT / "automation-log" / "knowledge-base" / "official-news-snapshot.json"
)
EXPECTED_PACK_ID = "week-content-20260824-30-r5"
EXPECTED_DATES = tuple(f"2026-08-{day:02d}" for day in range(24, 31))
RECEIPT_SCHEMA = 1
SCAN_VERSION = "week-evergreen-risk-v1"
SOURCE_DECISION = "NOT_REQUIRED_ONLY_WHILE_EXACT_COPY_HASH_MATCHES"
VALID_THROUGH = "2026-08-30T23:59:59+07:00"

BINDING_PATHS = {
    "content_calendar_sha256": ROOT / ".system_control" / "content_calendar.json",
    "policy_sha256": ROOT / ".system_control" / "policy.json",
    "post_ledger_sha256": ROOT / "automation-log" / "post-ledger.jsonl",
    "official_news_snapshot_sha256": DEFAULT_SNAPSHOT,
}

# These are high-signal publication blockers, not a claim that regex can prove
# all possible semantics.  The exact-copy receipt is the durable review boundary;
# any edit invalidates it even when none of these tokens appears.
RISK_RULES = (
    ("external_url_or_tracker", re.compile(
        r"(?:https?://|www\.|atth\.me|bit\.ly|linktr\.ee)", re.I)),
    ("affiliate_or_conversion_cta", re.compile(
        r"(?:affiliate|แอฟฟิลิเอต|ลิงก์ใน(?:ไบโอ|โปรไฟล์)|"
        r"สมัคร(?:เลย|วันนี้)|กดลิงก์|เช็กสิทธิ์)", re.I)),
    ("rate_price_fee_or_return_claim", re.compile(
        r"(?:%|฿|\$|บาท|ดอกเบี้ย|APR|อัตรา(?:ดอก|ผล|แลก)|"
        r"ค่าธรรมเนียม|วงเงิน|เงินคืน|cashback|ผลตอบแทน)", re.I)),
    ("promotion_or_currentness_claim", re.compile(
        r"(?:โปรโมชั่น|โปรโมช|ส่วนลด|โค้ด(?:ลด|โปร)|หมดเขต|ถึงวันที่|"
        r"ล่าสุด|ปัจจุบัน|ขณะนี้|วันนี้เท่านั้น|เฉพาะวันนี้)", re.I)),
    ("financial_provider_or_network", re.compile(
        r"(?:AccessTrade|KTC|Kept|Krungsri|กรุงศรี|SCB|ไทยพาณิชย์|"
        r"AXA|MSIG|Tune\s*Protect|FWD|ศรีสวัสดิ์|เงินเทอร์โบ|Kashjoy)", re.I)),
    ("guarantee_or_easy_approval_claim", re.compile(
        r"(?:รับประกัน|การันตี|อนุมัติไว|ผ่านง่าย|ได้แน่นอน|กำไรแน่นอน)", re.I)),
    ("dated_external_fact", re.compile(r"(?:20[2-9]\d|25\d{2})")),
)


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _aware_datetime(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("checked_at is missing")
    value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("checked_at must include a timezone")
    return value


def _public_copy(day: dict[str, Any]) -> dict[str, Any]:
    image = day.get("image_spec") if isinstance(day.get("image_spec"), dict) else {}
    tiktok = (
        day.get("tiktok_draft")
        if isinstance(day.get("tiktok_draft"), dict)
        else {}
    )
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


def _semantic_payload(day: dict[str, Any]) -> dict[str, Any]:
    image = day.get("image_spec") if isinstance(day.get("image_spec"), dict) else {}
    tiktok = (
        day.get("tiktok_draft")
        if isinstance(day.get("tiktok_draft"), dict)
        else {}
    )
    return {
        "date": day.get("date"),
        "candidate_id": day.get("candidate_id"),
        "theme": day.get("theme"),
        "public_copy": _public_copy(day),
        "creative_direction": {
            "facebook_instagram": image.get("facebook_instagram"),
            "pinterest": image.get("pinterest"),
            "tiktok_shots": tiktok.get("shots"),
        },
    }


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _risk_findings(day: dict[str, Any]) -> list[dict[str, str]]:
    # The scheduled date and internal candidate id are lineage, not claims made
    # to the audience.  Scan every audience-facing or creative semantic field,
    # but do not misclassify the calendar date itself as an external fact.
    claim_surface = _semantic_payload(day)
    claim_surface.pop("date", None)
    claim_surface.pop("candidate_id", None)
    combined = "\n".join(_strings(claim_surface))
    findings: list[dict[str, str]] = []
    for code, pattern in RISK_RULES:
        match = pattern.search(combined)
        if match:
            findings.append({"code": code, "match": match.group(0)})
    return findings


def _copy_shape_findings(day: dict[str, Any]) -> list[str]:
    candidate_id = str(day.get("candidate_id") or "candidate")
    findings: list[str] = []
    copy = _public_copy(day)
    for field in ("threads_text", "facebook_text"):
        value = copy.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(f"{candidate_id}: {field} is missing")
    tiktok = copy["tiktok"]
    for field in ("hook", "voiceover", "end_card"):
        value = tiktok.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(f"{candidate_id}: tiktok {field} is missing")
    onscreen = tiktok.get("onscreen_text")
    if not isinstance(onscreen, list) or not onscreen or any(
        not isinstance(value, str) or not value.strip() for value in onscreen
    ):
        findings.append(f"{candidate_id}: tiktok onscreen_text is malformed")
    if day.get("quote_text") is not None:
        if not isinstance(day.get("quote_text"), str) or not day["quote_text"].strip():
            findings.append(f"{candidate_id}: quote_text is malformed")
        overlay = copy.get("image_overlay_text")
        if not isinstance(overlay, str) or not overlay.strip():
            findings.append(f"{candidate_id}: quote overlay is missing")
    return findings


def build_receipt_document(
    pack_path: Path = DEFAULT_PACK,
    snapshot_path: Path = DEFAULT_SNAPSHOT,
    *,
    checked_at: str,
) -> dict[str, Any]:
    """Build an inspectable authoring receipt without writing or authorizing."""
    pack = _load_object(pack_path, "weekly pack")
    snapshot = _load_object(snapshot_path, "official source snapshot")
    rows = []
    authoring_findings: list[str] = []
    if pack.get("pack_id") != EXPECTED_PACK_ID:
        authoring_findings.append("weekly pack id is not the frozen r5 pack")
    if pack.get("state") != "DRAFT_ONLY":
        authoring_findings.append("weekly pack must remain DRAFT_ONLY")
    if not isinstance(pack.get("global_blockers"), list) or not pack["global_blockers"]:
        authoring_findings.append("weekly pack global blockers were removed")
    rules = pack.get("content_rules") if isinstance(pack.get("content_rules"), dict) else {}
    for field in ("body_url", "affiliate_cta", "financial_product_claim"):
        if rules.get(field) is not False:
            authoring_findings.append(
                f"weekly pack content rule {field} must remain false"
            )
    days = pack.get("days")
    if not isinstance(days, list) or len(days) != 7:
        authoring_findings.append("weekly pack must contain exactly seven candidates")
        days = []
    if tuple(
        day.get("date") for day in days if isinstance(day, dict)
    ) != EXPECTED_DATES:
        authoring_findings.append("weekly pack dates are not exactly 2026-08-24..30")
    candidate_ids = [
        day.get("candidate_id") for day in days if isinstance(day, dict)
    ]
    if (
        len(candidate_ids) != 7
        or any(not isinstance(value, str) or not value for value in candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
    ):
        authoring_findings.append("weekly pack candidate ids are malformed or duplicated")

    for day in days:
        risks = _risk_findings(day) if isinstance(day, dict) else [
            {"code": "malformed_candidate", "match": "non-object"}
        ]
        if not isinstance(day, dict):
            authoring_findings.append("weekly pack candidate row is malformed")
        else:
            candidate_id = str(day.get("candidate_id") or "candidate")
            authoring_findings.extend(_copy_shape_findings(day))
            if day.get("source_ids") != []:
                authoring_findings.append(
                    f"{candidate_id}: source-required/factual candidate is not allowed in the evergreen lane"
                )
            if day.get("source_review") not in {
                "NOT_REQUIRED", "NOT_REQUIRED_IF_TEXT_REMAINS_EXACT"
            }:
                authoring_findings.append(
                    f"{candidate_id}: source_review is not an evergreen state"
                )
            authoring_findings.extend(
                f"{candidate_id}: time-sensitive/factual risk {risk['code']} matched {risk['match']!r}"
                for risk in risks
            )
        rows.append({
            "date": day.get("date") if isinstance(day, dict) else None,
            "candidate_id": day.get("candidate_id") if isinstance(day, dict) else None,
            "source_ids": day.get("source_ids") if isinstance(day, dict) else None,
            "source_review_recorded": (
                day.get("source_review") if isinstance(day, dict) else None
            ),
            "source_decision": SOURCE_DECISION,
            "public_copy_sha256": (
                _canonical_sha256(_public_copy(day)) if isinstance(day, dict) else ""
            ),
            "semantic_payload_sha256": (
                _canonical_sha256(_semantic_payload(day))
                if isinstance(day, dict) else ""
            ),
            "high_risk_findings": risks,
        })

    binding_rows = {}
    pack_binding = pack.get("source_binding") or {}
    for field, path in BINDING_PATHS.items():
        actual = _file_sha256(path)
        recorded = str(pack_binding.get(field) or "").upper()
        binding_rows[field] = {
            "recorded_sha256": recorded,
            "observed_sha256": actual,
            "match": recorded == actual,
        }
        if field != "official_news_snapshot_sha256" and recorded != actual:
            authoring_findings.append(f"{field}: frozen non-news binding mismatch")

    snapshot_binding = binding_rows["official_news_snapshot_sha256"]
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    try:
        receipt_pack_path = pack_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        receipt_pack_path = str(pack_path.resolve())
    return {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_id": "week-content-freshness-20260823-r1",
        "checked_at": checked_at,
        "pack": {
            "path": receipt_pack_path,
            "pack_id": pack.get("pack_id"),
            "state": pack.get("state"),
            "sha256": _file_sha256(pack_path),
        },
        "scope": {
            "classification": "EVERGREEN_BEHAVIORAL_EXACT_COPY",
            "official_source_ids": [],
            "source_rule": SOURCE_DECISION,
            "scan_version": SCAN_VERSION,
            "valid_through": VALID_THROUGH,
        },
        "candidates": rows,
        "binding_check": binding_rows,
        "official_news_snapshot": {
            "pack_recorded_sha256": snapshot_binding["recorded_sha256"],
            "observed_sha256": snapshot_binding["observed_sha256"],
            "binding_status": (
                "MATCH"
                if snapshot_binding["match"]
                else "STALE_NOT_AUTO_REFRESHED"
            ),
            "required_source_ids": [],
            "checked_at": snapshot.get("checked_at"),
            "summary": {
                "configured_sources": summary.get("configured_sources"),
                "successful_sources": summary.get("successful_sources"),
                "changed_this_run": summary.get("changed_this_run"),
                "current_errors": summary.get("current_errors"),
                "pending_owner_reviews": summary.get("pending_owner_reviews"),
                "network_probe": summary.get("network_probe"),
                "freshness_state": summary.get("freshness_state"),
            },
        },
        "assessment": {
            "freshness_verdict": (
                "PASS_EVERGREEN_EXACT_COPY"
                if not authoring_findings
                else "BLOCKED_FACTUAL_OR_PROMOTIONAL_COPY"
            ),
            "publication_ready": False,
            "process_state": (
                "COMPLETED_BLOCKED" if not authoring_findings else "BLOCKED"
            ),
            "authoring_findings": authoring_findings,
            "blockers": [
                "stale_global_official_news_binding_not_refreshed",
                "receipt_is_authoring_evidence_not_publication_authority",
                "pack_remains_draft_only_with_existing_global_blockers",
            ],
        },
        "external_actions": {
            "posts": 0,
            "schedules": 0,
            "source_acknowledgements": 0,
            "tracker_clicks": 0,
            "commits": 0,
            "pushes": 0,
            "deploys": 0,
        },
    }


def evaluate(
    pack_path: Path = DEFAULT_PACK,
    receipt_path: Path = DEFAULT_RECEIPT,
    snapshot_path: Path = DEFAULT_SNAPSHOT,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    findings: list[str] = []
    global_findings: list[str] = []
    try:
        pack = _load_object(pack_path, "weekly pack")
        receipt = _load_object(receipt_path, "freshness receipt")
        snapshot = _load_object(snapshot_path, "official source snapshot")
    except Exception as exc:
        return {
            "freshness_verdict": "BLOCKED",
            "publication_ready": False,
            "process_state": "RUNNER_FAILED",
            "findings": [f"input unreadable: {type(exc).__name__}: {exc}"],
            "global_findings": [],
        }

    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        findings.append("freshness receipt schema is unsupported")
    if receipt.get("receipt_id") != "week-content-freshness-20260823-r1":
        findings.append("freshness receipt id is unsupported")
    try:
        receipt_time = _aware_datetime(receipt.get("checked_at"))
    except Exception as exc:
        findings.append(str(exc))
        receipt_time = None
    decision_time = now or datetime.now(timezone.utc)
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        findings.append("decision time must include a timezone")
    elif receipt_time is not None and receipt_time > decision_time:
        findings.append("freshness receipt is from the future")

    if pack.get("pack_id") != EXPECTED_PACK_ID:
        findings.append("weekly pack id is not the frozen r5 pack")
    if pack.get("state") != "DRAFT_ONLY":
        findings.append("weekly pack must remain DRAFT_ONLY")
    if not isinstance(pack.get("global_blockers"), list) or not pack["global_blockers"]:
        findings.append("weekly pack global blockers were removed")
    rules = pack.get("content_rules") if isinstance(pack.get("content_rules"), dict) else {}
    for field in ("body_url", "affiliate_cta", "financial_product_claim"):
        if rules.get(field) is not False:
            findings.append(f"weekly pack content rule {field} must remain false")

    receipt_pack = receipt.get("pack") if isinstance(receipt.get("pack"), dict) else {}
    actual_pack_hash = _file_sha256(pack_path)
    if str(receipt_pack.get("sha256") or "").upper() != actual_pack_hash:
        findings.append("frozen weekly pack SHA-256 differs from the freshness receipt")
    if receipt_pack.get("pack_id") != pack.get("pack_id"):
        findings.append("freshness receipt is bound to another pack id")
    try:
        expected_pack_path = pack_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        expected_pack_path = str(pack_path.resolve())
    if receipt_pack.get("path") != expected_pack_path:
        findings.append("freshness receipt pack path mismatch")
    if receipt_pack.get("state") != "DRAFT_ONLY":
        findings.append("freshness receipt does not preserve DRAFT_ONLY")

    scope = receipt.get("scope") if isinstance(receipt.get("scope"), dict) else {}
    if scope.get("classification") != "EVERGREEN_BEHAVIORAL_EXACT_COPY":
        findings.append("freshness scope classification is unsupported")
    if scope.get("official_source_ids") != []:
        findings.append("evergreen receipt must have an empty official source scope")
    if scope.get("source_rule") != SOURCE_DECISION:
        findings.append("evergreen source rule is not exact-copy-bound")
    if scope.get("scan_version") != SCAN_VERSION:
        findings.append("evergreen risk scan version is unsupported")
    if scope.get("valid_through") != VALID_THROUGH:
        findings.append("evergreen receipt validity boundary is missing or changed")
    else:
        valid_through = _aware_datetime(VALID_THROUGH)
        if (
            decision_time.tzinfo is not None
            and decision_time.utcoffset() is not None
            and decision_time > valid_through
        ):
            findings.append("evergreen receipt expired after its scheduled week")

    days = pack.get("days")
    if not isinstance(days, list) or len(days) != 7:
        findings.append("weekly pack must contain exactly seven candidates")
        days = []
    dates = [day.get("date") for day in days if isinstance(day, dict)]
    ids = [day.get("candidate_id") for day in days if isinstance(day, dict)]
    if tuple(dates) != EXPECTED_DATES:
        findings.append("weekly pack dates are not exactly 2026-08-24..30")
    if len(ids) != 7 or any(not isinstance(value, str) or not value for value in ids):
        findings.append("weekly pack candidate ids are malformed")
    elif len(ids) != len(set(ids)):
        findings.append("weekly pack candidate ids are duplicated")

    receipt_rows = receipt.get("candidates")
    if not isinstance(receipt_rows, list) or len(receipt_rows) != len(days):
        findings.append("freshness receipt candidate coverage is incomplete")
        receipt_rows = []
    by_id = {}
    for row in receipt_rows:
        if not isinstance(row, dict):
            findings.append("freshness receipt candidate row is malformed")
            continue
        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in by_id:
            findings.append("freshness receipt candidate id is missing or duplicated")
            continue
        by_id[candidate_id] = row

    candidate_results = []
    for day in days:
        if not isinstance(day, dict):
            findings.append("weekly pack candidate row is malformed")
            continue
        candidate_id = str(day.get("candidate_id") or "candidate")
        row_findings = _copy_shape_findings(day)
        risks = _risk_findings(day)
        if day.get("source_ids") != []:
            row_findings.append(
                f"{candidate_id}: source-required/factual candidate is not allowed in the evergreen lane"
            )
        if day.get("source_review") not in {
            "NOT_REQUIRED", "NOT_REQUIRED_IF_TEXT_REMAINS_EXACT"
        }:
            row_findings.append(f"{candidate_id}: source_review is not an evergreen state")
        for risk in risks:
            row_findings.append(
                f"{candidate_id}: time-sensitive/factual risk {risk['code']} matched {risk['match']!r}"
            )
        row = by_id.get(candidate_id)
        if row is None:
            row_findings.append(f"{candidate_id}: exact-copy receipt row is missing")
        else:
            if row.get("date") != day.get("date"):
                row_findings.append(f"{candidate_id}: receipt date mismatch")
            if row.get("source_review_recorded") != day.get("source_review"):
                row_findings.append(f"{candidate_id}: recorded source_review mismatch")
            if row.get("source_ids") != []:
                row_findings.append(f"{candidate_id}: receipt source scope is not empty")
            if row.get("source_decision") != SOURCE_DECISION:
                row_findings.append(f"{candidate_id}: receipt source decision is not exact-copy-bound")
            if row.get("high_risk_findings") != []:
                row_findings.append(f"{candidate_id}: receipt preserves a high-risk finding")
            if row.get("public_copy_sha256") != _canonical_sha256(_public_copy(day)):
                row_findings.append(f"{candidate_id}: public-copy SHA-256 mismatch")
            if row.get("semantic_payload_sha256") != _canonical_sha256(
                _semantic_payload(day)
            ):
                row_findings.append(f"{candidate_id}: semantic-payload SHA-256 mismatch")
        findings.extend(row_findings)
        candidate_results.append({
            "candidate_id": candidate_id,
            "date": day.get("date"),
            "status": "PASS_EVERGREEN_EXACT_COPY" if not row_findings else "BLOCKED",
            "source_scope": [],
            "risk_findings": risks,
            "findings": row_findings,
        })

    pack_binding = pack.get("source_binding") if isinstance(pack.get("source_binding"), dict) else {}
    receipt_bindings = (
        receipt.get("binding_check")
        if isinstance(receipt.get("binding_check"), dict)
        else {}
    )
    observed_bindings = {}
    for field, path in BINDING_PATHS.items():
        actual = _file_sha256(snapshot_path if field == "official_news_snapshot_sha256" else path)
        recorded = str(pack_binding.get(field) or "").upper()
        match = recorded == actual
        observed_bindings[field] = {
            "recorded_sha256": recorded,
            "observed_sha256": actual,
            "match": match,
        }
        receipt_row = receipt_bindings.get(field)
        if not isinstance(receipt_row, dict) or receipt_row != observed_bindings[field]:
            findings.append(f"{field}: dated binding evidence changed or is malformed")
        if field == "official_news_snapshot_sha256":
            if not match:
                global_findings.append(
                    "weekly pack official-news snapshot binding is stale and was not auto-refreshed"
                )
        elif not match:
            findings.append(f"{field}: frozen non-news binding mismatch")

    snapshot_receipt = (
        receipt.get("official_news_snapshot")
        if isinstance(receipt.get("official_news_snapshot"), dict)
        else {}
    )
    expected_snapshot_status = (
        "MATCH"
        if observed_bindings["official_news_snapshot_sha256"]["match"]
        else "STALE_NOT_AUTO_REFRESHED"
    )
    snapshot_summary = (
        snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    )
    expected_snapshot_receipt = {
        "pack_recorded_sha256": observed_bindings[
            "official_news_snapshot_sha256"
        ]["recorded_sha256"],
        "observed_sha256": observed_bindings[
            "official_news_snapshot_sha256"
        ]["observed_sha256"],
        "binding_status": expected_snapshot_status,
        "required_source_ids": [],
        "checked_at": snapshot.get("checked_at"),
        "summary": {
            "configured_sources": snapshot_summary.get("configured_sources"),
            "successful_sources": snapshot_summary.get("successful_sources"),
            "changed_this_run": snapshot_summary.get("changed_this_run"),
            "current_errors": snapshot_summary.get("current_errors"),
            "pending_owner_reviews": snapshot_summary.get("pending_owner_reviews"),
            "network_probe": snapshot_summary.get("network_probe"),
            "freshness_state": snapshot_summary.get("freshness_state"),
        },
    }
    if snapshot_receipt != expected_snapshot_receipt:
        findings.append("dated official-news snapshot evidence changed or is malformed")

    try:
        from tools.content_source_gate import validate_official_snapshot_contract

        envelope = validate_official_snapshot_contract(
            snapshot,
            required_source_ids=None,
            now=receipt_time or decision_time,
            freshness_hours=24,
        )
        if not envelope.allowed:
            findings.extend(
                "official-news envelope: " + failure for failure in envelope.failures
            )
    except Exception as exc:
        findings.append(f"official-news envelope validation failed: {type(exc).__name__}: {exc}")

    assessment = receipt.get("assessment") if isinstance(receipt.get("assessment"), dict) else {}
    if assessment.get("publication_ready") is not False:
        findings.append("freshness receipt must never claim publication readiness")
    if assessment.get("freshness_verdict") != "PASS_EVERGREEN_EXACT_COPY":
        findings.append("freshness receipt assessment is not the reviewed evergreen verdict")
    if assessment.get("process_state") != "COMPLETED_BLOCKED":
        findings.append("freshness receipt must remain COMPLETED_BLOCKED")
    if assessment.get("authoring_findings") != []:
        findings.append("freshness receipt preserves an authoring freshness failure")
    actions = receipt.get("external_actions")
    if not isinstance(actions, dict) or any(value != 0 for value in actions.values()):
        findings.append("freshness receipt records an external action")
    if pack.get("state") != "DRAFT_ONLY" or not pack.get("global_blockers"):
        findings.append("publication blockers are not preserved")

    freshness_pass = not findings
    process_state = (
        "COMPLETED_BLOCKED"
        if freshness_pass and global_findings
        else "BLOCKED" if not freshness_pass else "COMPLETED_BLOCKED"
    )
    return {
        "freshness_verdict": (
            "PASS_EVERGREEN_EXACT_COPY" if freshness_pass else "BLOCKED"
        ),
        "publication_ready": False,
        "process_state": process_state,
        "pack_id": pack.get("pack_id"),
        "pack_sha256": actual_pack_hash,
        "candidate_count": len(candidate_results),
        "candidates": candidate_results,
        "binding_check": observed_bindings,
        "official_news_scope": [],
        "findings": findings,
        "global_findings": global_findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", default=str(DEFAULT_PACK))
    parser.add_argument("--receipt", default=str(DEFAULT_RECEIPT))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--now", help="timezone-aware ISO-8601 decision time")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        decision_time = _aware_datetime(args.now) if args.now else None
    except Exception as exc:
        print(f"week-content-freshness: RUNNER_FAILED: {exc}", file=sys.stderr)
        return 3
    result = evaluate(
        Path(args.pack), Path(args.receipt), Path(args.snapshot), now=decision_time
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "week-content-freshness: %s / publication=%s / state=%s"
            % (
                result["freshness_verdict"],
                "READY" if result["publication_ready"] else "BLOCKED",
                result["process_state"],
            )
        )
        for finding in result["findings"] + result["global_findings"]:
            print("- " + finding)
    # This guard is intentionally not a publication-ready gate.  rc=2 is the
    # project's normal completed-with-blockers contract, not a runner crash.
    return 2 if result["process_state"] != "RUNNER_FAILED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
