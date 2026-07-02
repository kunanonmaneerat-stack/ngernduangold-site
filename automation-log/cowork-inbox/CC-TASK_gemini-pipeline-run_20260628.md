# CC-TASK — รัน pipeline ด้วย gemini-3.5-flash + ปิดจุด 2.0-flash
สร้างโดย Cowork · 2026-06-28 · สำหรับ CC (อยู่บนเครื่องเจ้าของ มีคีย์ Gemini)

## บริบท — Cowork ทำอะไรไปแล้ว
แก้ `pipeline/free_ai.py` แล้ว (ยังไม่ commit — Cowork ไม่ push git):
- ตัด `gemini-2.0-flash / 2.0-flash-lite / 1.5-flash / 1.5-flash-8b` ออกจาก `FREE_MODELS` (Google retired → เคยขึ้น 404)
- อัปเดต selftest บรรทัด ~159 ใช้ `gemini-2.5-flash` เป็นตัวอย่าง
- ยืนยันด้วยการรันจริงแล้ว: `smart` → gemini-3.5-flash · `allow('gemini-2.0-flash')` → บล็อกสะอาด "not in allowlist" · `allow('veo-3')` → ยังบล็อก (การ์ด zero-budget ครบ)
- **TIERS ไม่ต้องแก้** — smart/max = gemini-3.5-flash อยู่แล้ว (default ของ pipeline)

## ขั้นตอนให้ CC ทำ (ตามลำดับ)

**1. commit + push โค้ดที่ Cowork แก้**
```
git add pipeline/free_ai.py
git commit -m "chore(ai): drop retired gemini-2.0/1.5 from allowlist, pin workhorse to gemini-3.5-flash"
git push
```

**2. ยืนยันคีย์ + สถานะ (บนเครื่องเจ้าของ)**
```
python pipeline/free_ai.py --status      # ต้องได้ key_present: True
python pipeline/free_ai.py --selftest    # บนเครื่องที่มีคีย์ต้องผ่าน (ใน sandbox ไม่มีคีย์เลย NO_KEY — ปกติ)
```

**3. ทดสอบ gemini-3.5-flash ยิงจริง 1 ครั้ง**
```
python -c "import pipeline.free_ai as f; print(f.generate('ping ตอบคำเดียวว่า OK', model='smart'))"
```
คาดหวัง: ได้ข้อความกลับ + status 'ok' (ถ้า NO_KEY/ERROR ให้หยุด รายงานเจ้าของ)

**4. กวาดหาจุดที่ยังอ้าง 2.0-flash (รวมไฟล์นอก repo)**
```
grep -rn "2\.0-flash\|gemini-2\.0\|gemini-1\.5" pipeline/ *.py
```
- ถ้าเจอ script ไหน hardcode model="gemini-2.0-flash" → เปลี่ยนเป็น tier alias `"smart"` (หรือ `"gemini-3.5-flash"`)
- เช็ก config/env นอก repo ที่ pipeline อ่าน (เช่น .env, *.json) ว่าไม่ได้ pin รุ่นเก่าไว้
- ไม่เจอ = ดี (แปลว่า 404 เดิมมาจากการเรียกมือ/ทดสอบครั้งเดียว)

**5. รัน pipeline จริง (ใช้ 3.5-flash ผ่าน tier smart)**
```
pipeline\run_daily.cmd
```
(หรือ entrypoint รายวันที่ใช้อยู่ — run_daily.cmd คือตัวหลัก)

**6. ตรวจผลหลังรัน**
```
tail -30 automation-log/ai-usage/2026-06-28.jsonl
```
เกณฑ์ผ่าน:
- มี `gemini-3.5-flash` ... `"ok": true` ใหม่
- **ไม่มี** `gemini-2.0-flash` 404 ใหม่หลังเวลา commit
- `veo-3`/รุ่นเสียเงิน ถ้ามีต้องเป็น "refused" (การ์ดทำงาน)

**7. push + รายงานกลับ Cowork**
- commit ผลลัพธ์/log ที่เปลี่ยน (`automation-log/...`) + push
- เขียนสรุปสั้นๆ ลง `automation-log/cowork-inbox/` ว่า: commit hash, key_present, ผลทดสอบ 3.5-flash, มี 404 ใหม่ไหม, pipeline รันจบไหม

## กฎ
- zero-budget: ห้ามเปิดรุ่นเสียเงิน (veo/imagen/*-pro/gpt-/claude-) — การ์ดใน free_ai.py กันไว้แล้ว อย่าปิด
- คีย์อยู่ในไฟล์นอก repo (gemini_key.txt / ga4-admin\.env) — ห้าม commit คีย์
- ถ้าเจอ error ที่แก้ไม่ได้ → หยุด รายงานเจ้าของ อย่าฝืน
