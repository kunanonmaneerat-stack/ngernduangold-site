#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unit test: post_ledger text-dedup (POSTING-POLICY_antispam_20260702 / order PART A5).
Run: python pipeline/test_text_dedup.py  -> exit 0 all pass, exit 1 fail. Uses a temp ledger."""
import os, sys, json, tempfile, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "automation-log"))
import post_ledger as PL
import comply_gate as CG

def main():
    fd, tmp = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    orig = PL.LEDGER
    PL.LEDGER = tmp
    try:
        base = "เงินเดือนชนเดือน? ลองหักก่อนใช้ โอนเข้าบัญชีดอกสูงอัตโนมัติวันเงินเดือนออก เหลือเท่าไหร่ค่อยใช้ เช็กเงื่อนไขก่อนเปิดบัญชี"
        r = PL.record_text_post("threads", base, source="unittest")
        assert r["appended"], "seed row must append"
        # 1) exact duplicate, same channel -> BLOCKED
        dup, why, _ = PL.is_duplicate_text("threads", base)
        assert dup, "exact dup must be caught"
        r2 = PL.record_text_post("threads", base)
        assert not r2["appended"], "record must refuse exact dup"
        # 1b) cosmetic edits (URL/emoji/space) -> still BLOCKED (normalize works)
        dup, why, _ = PL.is_duplicate_text("threads", base + " 🙏  https://example.com/x")
        assert dup, "normalized dup (url+emoji) must be caught"
        # 2) ~95% similar -> BLOCKED
        near = base.replace("เช็กเงื่อนไขก่อนเปิดบัญชี", "เช็กเงื่อนไขก่อนเปิดใช้")
        dup, why, _ = PL.is_duplicate_text("threads", near)
        assert dup, "95%-similar must be caught (got not-dup)"
        # 3) same text, DIFFERENT channel -> PASSES
        dup, why, _ = PL.is_duplicate_text("fb", base)
        assert not dup, "different channel must pass"
        # 4) exact text is permanent, even when the prior row is 31 days old
        old_ts = (PL.now_local() - datetime.timedelta(days=31)).isoformat(timespec="seconds")
        row = {"type": "text", "channel": "ig", "text_hash": PL.text_hash(base),
               "text_norm": PL.normalize_text(base), "text_first80": base[:80],
               "ts": old_ts, "source": "unittest-old"}
        open(tmp, "a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
        dup, why, _ = PL.is_duplicate_text("ig", base)
        assert dup, "31-day-old exact duplicate must remain blocked forever"
        # 4b) near similarity remains bounded to the existing 30-day window
        old_near = base.replace("เช็กเงื่อนไขก่อนเปิดบัญชี", "เช็กเงื่อนไขก่อนเปิดใช้")
        dup, why, _ = PL.is_duplicate_text("ig", old_near)
        assert not dup, "31-day-old near duplicate must pass outside the 30d window"
        # 5) genuinely different text, same channel -> PASSES
        dup, why, _ = PL.is_duplicate_text("threads", "กระทู้ชวนคุย: เพื่อนๆ แบ่งเงินเดือนยังไงให้รอดถึงสิ้นเดือน มาแชร์กัน")
        assert not dup, "different text must pass"
        # 6) an unreadable ledger/duplicate service must BLOCK, never warn-and-pass
        original_checker = PL.is_duplicate_text
        try:
            def broken_checker(*_args, **_kwargs):
                raise OSError("ledger unavailable")
            PL.is_duplicate_text = broken_checker
            ok, issues = CG.check_post("A practical checklist for planning a monthly budget.", "threads")
            assert not ok, "dedup infrastructure failure must fail closed"
            assert any("GATE_FAIL text-dedup unavailable" in issue for issue in issues)
        finally:
            PL.is_duplicate_text = original_checker
        print("test_text_dedup: 8/8 PASS")
        return 0
    finally:
        PL.LEDGER = orig
        os.unlink(tmp)

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
