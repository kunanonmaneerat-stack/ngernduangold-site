#!/usr/bin/env python3
"""trend_ingest — STEP 1: pull current Thai personal-finance trend topics + intent keywords
via Gemini (free tier). Writes pipeline/data/trends-YYYYMMDD.json.

Fail-closed: if there is no GOOGLE_AI_STUDIO_KEY the script SKIPS cleanly (exit 0, no paid
call, no crash) so the scheduler keeps running. NO evasion logic.
"""
import os, sys, json, datetime
try:  # cp874-safe UTF-8 stdout/stderr (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_ai

PROMPT = """คุณเป็นนักวางคอนเทนต์การเงินสำหรับมนุษย์เงินเดือนไทย (อายุ 25-45).
ให้ 8 หัวข้อการเงินที่คนกำลังค้นหา/เป็นกระแสตอนนี้ ครอบคลุม: บัตรเครดิต, สินเชื่อ/จำนำทะเบียน,
รวมหนี้, สินเชื่อส่วนบุคคล, ออมเงิน, ฟรีแลนซ์, ภาษี.
ตอบเป็น JSON array ล้วน (ห้ามมีข้อความอื่น) รูปแบบ:
[{"topic":"...","intent":"บัตร|เงินด่วน|หนี้|ออม","keyword":"คำค้นหลัก","money_page":"slug หน้าเว็บที่เกี่ยวข้อง"}]
กฎ: ห้ามแต่งตัวเลขดอกเบี้ย/วงเงิน. ใช้ภาษามนุษย์เงินเดือน."""


def main():
    txt, st = free_ai.generate(PROMPT, model="smart")  # trend research drives everything downstream
    if st == "NO_KEY":
        print("SKIP trend_ingest: no GOOGLE_AI_STUDIO_KEY (zero-budget fail-closed). "
              "Owner: add the free key to ga4-admin/.env, then pip install google-generativeai.")
        return 0
    if st != "ok" or not txt:
        print("trend_ingest: not ok ->", st)
        return 0
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(out_dir, exist_ok=True)
    fn = os.path.join(out_dir, "trends-" + datetime.datetime.now().strftime("%Y%m%d") + ".json")
    open(fn, "w", encoding="utf-8").write(txt)
    print("trends ->", fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
