#!/usr/bin/env python3
"""Focused contract checks for the owner-confirmed Pantip manual pilot."""

from __future__ import annotations

from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / ".system_control" / "policy.json"
CALENDAR = ROOT / ".system_control" / "content_calendar.json"
LEDGER = ROOT / "automation-log" / "post-ledger.jsonl"
WRITER = ROOT / "automation-log" / "post_ledger.py"
CONTENT_ID = "pantip-reply-44197340-v1"
PLACEMENT_ID = CONTENT_ID + "__pantip_main"
PUBLISHED_AT = "2026-08-16T15:54:44+07:00"
PERMALINK = "https://pantip.com/topic/44197340/comment6"
TEXT = """จากรายละเอียดตอนนี้ จุดเร่งด่วนคงไม่ใช่หาที่ใหม่เพื่อเอาส่วนต่างก่อนครับ เพราะค้าง 3 งวด และรถเคยจด รย.18 ทำให้โอกาสรีไฟแนนซ์พร้อมขอเงินเพิ่มยากขึ้น อีกทั้งถ้าอนุมัติจริงค่างวดรวมอาจสูงกว่าเดิม

สิ่งที่ทำได้วันนี้คือ ติดต่อเจ้าหนี้เดิมผ่านช่องทางทางการ ขอ 4 ตัวเลขเป็นลายลักษณ์อักษร: ยอดค้างทั้งหมด ยอดปิดบัญชี ค่างวดที่จ่ายไหวหากยืดระยะเวลา/ปรับโครงสร้าง และค่าธรรมเนียมทั้งหมด บอกเขาตรง ๆ ว่ารายได้สุทธิและค่าใช้จ่ายจำเป็นเหลือจ่ายได้เดือนละเท่าไร อย่ารับยอดผ่อนที่ยังเกินกำลังเพียงเพื่อให้เรื่องจบเร็ว

ถ้ารถเป็นเครื่องมือทำมาหากิน ลองคำนวณรายได้สุทธิจากรถหลังหักค่างวด ค่าน้ำมัน และค่าซ่อมก่อนตัดสินใจขายหรือกู้เพิ่ม ระหว่างนี้ระวังนายหน้าหรือไฟแนนซ์นอกระบบที่ขอค่าดำเนินการก่อน ขอ OTP หรือรับประกันผลอนุมัติ

ถ้าผู้ให้บริการตามสัญญาอยู่ภายใต้การกำกับของ ธปท. และติดต่อแล้วไม่ได้ทางเลือกหรือคำตอบชัดเจน ให้เก็บเลขเคสและเอกสาร แล้วโทร 1213 เพื่อสอบถามช่องทางช่วยเหลือที่ตรงกับสัญญาครับ

กู้เท่าที่จำเป็นและชำระคืนไหว"""


def load_writer():
    sys.path.insert(0, str(WRITER.parent))
    spec = importlib.util.spec_from_file_location("pantip_post_ledger", WRITER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    channel = policy["channels"]["pantip"]
    pilot = channel["manual_pilot"]
    assert channel["state"] == "limited"
    assert channel["auto"] is False and channel["automation_capable"] is False
    assert channel["publication_authorized"] is False
    assert channel["weekly_quota"] == pilot["weekly_quota"] == 1
    assert channel["phase_until"] == "2026-08-23"
    assert pilot["scope"] == "reply_existing_topic_only"
    assert pilot["status"] == "OBSERVING_48H"
    assert pilot["authorization_state"] == "ONE_TIME_APPROVAL_CONSUMED"
    assert pilot["review_must_pass_before_reauthorization"] is True
    assert pilot["per_piece_owner_confirmation_required"] is True
    assert set(pilot["forbidden"]) == {
        "new_topic", "body_link", "brand_mention", "price_or_offer",
        "affiliate_cta", "automated_publication",
    }
    assert pilot["first_content_id"] == CONTENT_ID
    assert pilot["first_placement_id"] == PLACEMENT_ID
    started = datetime.fromisoformat(pilot["started_at"])
    due = datetime.fromisoformat(pilot["review_due_at"])
    assert (due - started).total_seconds() == 48 * 60 * 60
    assert pilot["next_publication_not_before"] == pilot["review_due_at"]

    review = next(
        gate for gate in policy["gates"]
        if gate.get("task") == "pantip manual pilot 48h review"
    )
    assert review["status"] == "OPEN"
    assert review["review_due_at"] == pilot["review_due_at"]
    assert review["evidence"]["placement_id"] == PLACEMENT_ID
    assert review["evidence"]["permalink"] == PERMALINK

    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    matches = [row for row in rows if row.get("placement_id") == PLACEMENT_ID]
    assert len(matches) == 1
    row = matches[0]
    assert row["type"] == "text" and row["channel"] == "pantip"
    assert row["content_id"] == CONTENT_ID
    assert row["published_at"] == row["posted_at"] == row["ts"] == PUBLISHED_AT
    assert row["post_id"] == "comment-120045811"
    assert row["status"] == "published_confirmed"
    assert row["platform_evidence"]["permalink"] == PERMALINK
    writer = load_writer()
    expected_hash = hashlib.sha1(writer.normalize_text(TEXT).encode("utf-8")).hexdigest()
    assert row["text_hash"] == expected_hash

    lowered = TEXT.casefold()
    assert "http://" not in lowered and "https://" not in lowered
    assert "เงินเดือนสมองทอง" not in TEXT and "฿" not in TEXT and "บาท" not in TEXT

    calendar = json.loads(CALENDAR.read_text(encoding="utf-8"))
    assert calendar["purpose"] == "editorial_plan_only_no_publication"
    assert all(item.get("placement_id") != PLACEMENT_ID for item in calendar["placements"])

    with tempfile.TemporaryDirectory() as raw:
        writer.LEDGER = str(Path(raw) / "ledger.jsonl")
        evidence = {
            "object_type": "comment",
            "comment_number": 6,
            "comment_root_id": "comment-120045811",
            "topic_id": "44197340",
            "permalink": PERMALINK,
            "verification": "browser_live_after_publish",
        }
        first = writer.record_text_publication(
            "pantip", TEXT, content_id=CONTENT_ID, placement_id=PLACEMENT_ID,
            published_at=PUBLISHED_AT, post_id="comment-120045811",
            platform_evidence=evidence,
        )
        second = writer.record_text_publication(
            "pantip", TEXT, content_id=CONTENT_ID, placement_id=PLACEMENT_ID,
            published_at=PUBLISHED_AT, post_id="comment-120045811",
            platform_evidence=evidence,
        )
        assert first["appended"] is True
        assert second["appended"] is False and second["reason"].startswith("DUPLICATE:")

    print("pantip manual pilot contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
