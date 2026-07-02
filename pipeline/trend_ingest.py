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
[SPRINT FOCUS 2-8 ก.ค. 2026 — ตาม OWNER-MANDATE_20260702: ให้หัวข้อเฉพาะ 2 ธีมนี้เท่านั้น
 (1) จำนำทะเบียนรถ/สินเชื่อทะเบียนรถ — pain: มีรถ หมุนเงินไม่ทัน อยากปิดหนี้บัตร (money_page: title-loan-2026)
 (2) ออมเงินดอกสูง/บัญชีเงินฝากดิจิทัล — pain: เงินเดือนชนเดือน อยากให้เงินงอก (money_page: kept-savings-2026)
 งดธีมแมสทั่วไป (ภาษี/ฟรีแลนซ์/บัตร) จนกว่าจะพ้นสัปดาห์ sprint แล้วค่อยลบบล็อกนี้]
ให้ 8 หัวข้อการเงินที่คนกำลังค้นหา/เป็นกระแสตอนนี้ ภายใต้ 2 ธีมข้างบน (สลับกัน ~ครึ่งต่อครึ่ง).
ตอบเป็น JSON array ล้วน (ห้ามมีข้อความอื่น) รูปแบบ:
[{"topic":"...","intent":"เงินด่วน|หนี้|ออม","keyword":"คำค้นหลัก","money_page":"slug หน้าเว็บที่เกี่ยวข้อง"}]
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
