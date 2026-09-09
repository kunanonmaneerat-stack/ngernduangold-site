#!/usr/bin/env python3
"""Read-only QA for private editorial proposals; never publication authority.

The output describes only the exact bytes checked. A source-neutral lint result
does not acknowledge a factual source, create a calendar placement, reserve a
claim, or substitute for a separate governed review and owner decision.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "pipeline", ROOT / "automation-log"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import comply_gate
import post_ledger
try:
    from tools.week_content_freshness_guard import RISK_RULES
except ModuleNotFoundError:
    from week_content_freshness_guard import RISK_RULES

DISCLAIMER = "ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน"
CLASSIFICATION = "PROPOSED_SOURCE_NEUTRAL_REQUIRES_GOVERNED_REVIEW"
AUTHORITY_KEYS = {
    "publication_authority", "owner_approval_minted", "calendar_mutated",
    "source_review_receipt_minted", "media_qa_receipt_minted", "claim_reserved",
}
LOCAL_REVIEW_MAX_CODEPOINTS = 500


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path) -> tuple[object, bytes]:
    if path.is_symlink():
        raise ValueError("symlink evidence is not accepted")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("evidence changed during read")
    if len(raw) != after.st_size:
        raise ValueError("incomplete evidence read")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject(_value):
        raise ValueError("non-finite JSON number")

    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            reject(value)
        return number

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=reject, parse_float=finite), raw


def check_source_neutral_text(text: object, *, policy: object) -> dict:
    """Conservative pure scope lint, not source approval or owner authority.

    Callers must separately bind the exact content ID, caption, review chronology
    and current policy bytes. Known factual namespaces cannot opt out of their
    registry merely by passing this text-level check.
    """
    issues = []
    if not isinstance(text, str) or not text.strip():
        return {"allowed": False, "failures": ["draft text missing"],
                "classification": CLASSIFICATION, "publication_authorized": False}
    identity = policy.get("public_identity") if isinstance(policy, dict) else None
    if (not isinstance(identity, dict) or identity.get("page_only") is not True
            or not isinstance(identity.get("canonical_name"), str)
            or not identity.get("canonical_name", "").strip()):
        issues.append("page-only public identity is unproven")
        identity = {}
    if len(text) > LOCAL_REVIEW_MAX_CODEPOINTS:
        issues.append("caption exceeds local 500-codepoint review budget")
    if any(character == "\ufffd" or (unicodedata.category(character).startswith("C") and character != "\n")
           for character in text):
        issues.append("invisible/control/replacement character makes exact copy unsafe")
    if "\\n" in text or "\\r" in text:
        issues.append("literal newline escape in caption")
    if DISCLAIMER not in text:
        issues.append("full educational disclaimer missing")
    if "ผลิตด้วย AI" not in text:
        issues.append("AI-assisted draft disclosure missing")
    if re.search(r"https?://|www\.|\butm_|\b[A-Za-z0-9-]+\.(?:com|org|net|co\.th)\b", text, re.I):
        issues.append("outbound link is outside the source-neutral proposal scope")
    # Narrow Thai editorial lane: rates, named lenders, current policy/law,
    # product promotions and English factual copy need a separate source review.
    if re.search(r"\d|%|฿|ดอกเบี้ย|ธนาคาร|สินเชื่อ|บัตรเครดิต|มีลิงก์พันธมิตร|ซื้อเลย|ทัก.*(?:ซื้อ|สมัคร)|"
                 r"กสิกร|กรุงไทย|ไทยพาณิชย์|ออมสิน|ล่าสุด|ปัจจุบัน|กฎหมาย|ร้อยละ|เปอร์เซ็นต์|อัตรา|ค่าปรับ", text):
        issues.append("numeric, lending, merchant or current factual claim requires separate review")
    if re.search(r"[A-Za-z]", text.replace("ผลิตด้วย AI", "")):
        issues.append("non-Thai factual copy is outside this narrowly reviewed editorial lane")
    if any(unicodedata.category(character)[0] in {"L", "M"} and not "\u0e00" <= character <= "\u0e7f"
           for character in text.replace("ผลิตด้วย AI", "")):
        issues.append("foreign letters or combining marks are outside the Thai editorial review lane")
    for code, pattern in RISK_RULES:
        if pattern.search(text):
            issues.append("factual/editorial risk requires separate review: " + code)
    if re.search(r"กำไร|อนุมัติ|แน่นอน|ชัวร์|ไม่ขาดทุน|ไม่มีความเสี่ยง|ผ่านทุก", text):
        issues.append("certainty, return or approval claim is outside the source-neutral proposal scope")
    for key in ("forbidden_personal_claim_patterns", "forbidden_public_speakers"):
        patterns = identity.get(key)
        if not isinstance(patterns, list) or not all(isinstance(value, str) and value for value in patterns):
            issues.append("public identity pattern contract is missing or malformed")
            continue
        for pattern in patterns:
            try:
                expression = pattern if key == "forbidden_personal_claim_patterns" else r"(?<![a-z])" + re.escape(pattern) + r"(?![a-z])"
                if re.search(expression, text, re.I):
                    issues.append("personal or internal-agent public speaker is forbidden")
            except re.error:
                issues.append("public identity pattern contract is invalid")
    ok, compliance = comply_gate.check(text)
    if not ok:
        issues.extend(compliance)
    return {"allowed": not issues, "failures": issues,
            "classification": CLASSIFICATION, "publication_authorized": False}


def evaluate_document(document: object, *, policy: dict, duplicate_check=None) -> dict:
    result = {
        "state": "BLOCKED_DRAFT_QA", "publication_authorized": False,
        "source_review": "NOT_GRANTED", "findings": [], "drafts": [],
        "scope": "PRIVATE_DRAFT_QA_ONLY_NOT_LIVE_QUEUE_OR_PUBLICATION_READINESS",
    }
    findings = result["findings"]
    if not isinstance(document, dict):
        findings.append("draft pack must be an object")
        return result
    if (document.get("schema_version") != 2
            or document.get("artifact_type") != "NON_EXECUTABLE_PRIVATE_EDITORIAL_PROPOSALS"
            or document.get("state") != "DRAFT_ONLY_BLOCKED"
            or document.get("source_classification") != CLASSIFICATION):
        findings.append("draft pack lifecycle/classification is not fail-closed")
    authority = document.get("authority")
    if (not isinstance(authority, dict) or set(authority) != AUTHORITY_KEYS
            or any(value is not False for value in authority.values())):
        findings.append("draft pack must not claim authority or side effects")
    identity = policy.get("public_identity") if isinstance(policy, dict) else None
    if (not isinstance(identity, dict) or identity.get("page_only") is not True
            or not isinstance(identity.get("canonical_name"), str)
            or document.get("public_speaker") != identity.get("canonical_name")):
        findings.append("page-only public identity is unproven")
        identity = {}
    drafts = document.get("drafts")
    if not isinstance(drafts, list) or len(drafts) != 7:
        findings.append("weekly proposal must contain exactly seven drafts")
        return result
    ids, days, prior = set(), [], []
    for row in drafts:
        if not isinstance(row, dict):
            findings.append("malformed draft row")
            continue
        draft_id, text = row.get("draft_id"), row.get("text")
        issues = []
        if not isinstance(draft_id, str) or not re.fullmatch(r"nsw-\d{8}-[a-z0-9-]+-v2", draft_id) or draft_id in ids:
            issues.append("draft identity must be unique and revisioned")
        else:
            ids.add(draft_id)
        try:
            day = date.fromisoformat(row["editorial_day"])
            if row["editorial_day"] != day.isoformat():
                issues.append("editorial day must use canonical YYYY-MM-DD")
            if not isinstance(draft_id, str) or not draft_id.startswith("nsw-" + day.strftime("%Y%m%d") + "-"):
                issues.append("draft identity and editorial day differ")
            days.append(day)
        except (KeyError, TypeError, ValueError):
            issues.append("invalid editorial day")
        if row.get("media") is not None or row.get("source_ids") != [] or row.get("links") != []:
            issues.append("source-neutral text proposal must carry no media, links or factual source IDs")
        if not isinstance(text, str) or not text.strip():
            issues.append("draft text missing")
            text = ""
        if row.get("ai_assisted") is not True:
            issues.append("AI-assisted draft metadata missing")
        issues.extend(check_source_neutral_text(text, policy=policy)["failures"])
        caption_hash = _hash(text.encode("utf-8"))
        if row.get("caption_sha256") != caption_hash:
            issues.append("exact caption SHA-256 mismatch")
        normalized = post_ledger.normalize_text(text)
        if any(difflib.SequenceMatcher(None, normalized, value).ratio() >= post_ledger.TEXT_SIM_THRESHOLD for value in prior):
            issues.append("duplicate or near-duplicate within draft pack")
        prior.append(normalized)
        if duplicate_check is None:
            issues.append("local ledger dedup not checked")
        else:
            try:
                duplicate, reason, _finding = duplicate_check(text)
                if duplicate:
                    issues.append("local ledger dedup blocked: " + reason)
            except Exception as exc:
                issues.append("local ledger dedup unavailable: " + type(exc).__name__)
        result["drafts"].append({"draft_id": draft_id, "caption_sha256": caption_hash,
                                 "codepoints": len(text), "qa_passed": not issues,
                                 "issues": issues})
    if len(days) != 7 or days != [days[0] + timedelta(days=index) for index in range(7)]:
        findings.append("editorial coverage must be seven ordered consecutive dates")
    if not findings and all(row["qa_passed"] for row in result["drafts"]):
        result["state"] = "DRAFT_QA_PASSED_PUBLICATION_BLOCKED"
    return result


def evaluate(path: Path, *, repo: Path = ROOT, channel: str = "threads") -> dict:
    """Bind the local evaluation to pack/policy/ledger/identity evidence bytes."""
    try:
        if channel not in {"threads", "facebook"}:
            raise ValueError("unsupported draft-review channel")
        document, raw = _read(path)
        policy_path = repo / ".system_control/policy.json"
        policy, policy_raw = _read(policy_path)
        ledger = repo / "automation-log/post-ledger.jsonl"
        if not ledger.is_file() or ledger.is_symlink():
            raise ValueError("local ledger evidence is missing or unsafe")
        watched = [path, policy_path, ledger,
                   repo / "automation-log/post-ledger-identity-bindings.jsonl",
                   repo / "automation-log/post-ledger-collision-tombstones.json"]
        before = {str(item): _hash(item.read_bytes()) if item.is_file() else None for item in watched}
        if before[str(path)] != _hash(raw) or before[str(policy_path)] != _hash(policy_raw):
            raise ValueError("evidence changed after initial read")
        result = evaluate_document(document, policy=policy,
                                  duplicate_check=lambda text: post_ledger.is_duplicate_text(channel, text, path=ledger))
        after = {str(item): _hash(item.read_bytes()) if item.is_file() else None for item in watched}
        if before != after:
            raise ValueError("evidence changed during draft validation")
        result.update({"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "channel": channel, "pack_sha256": _hash(raw), "evidence_sha256": after,
                       "dedup_scope": "PERMANENT_EXACT_AND_ROLLING_30_DAY_NEAR_LOCAL_CHANNEL_LEDGER_ONLY"})
        return result
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"state": "UNKNOWN", "publication_authorized": False,
                "source_review": "NOT_GRANTED", "findings": [type(exc).__name__ + ": " + str(exc)], "drafts": []}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--channel", choices=("threads", "facebook"), default="threads")
    args = parser.parse_args(argv)
    result = evaluate(args.pack, channel=args.channel)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["state"] == "DRAFT_QA_PASSED_PUBLICATION_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
