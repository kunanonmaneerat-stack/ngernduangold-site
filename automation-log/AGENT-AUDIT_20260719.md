# AGENT AUDIT — อาทิตย์ 19 ก.ค. 2026 20:00
ผู้ตรวจ: ngernduangold-agent-auditor (Cowork) · ขอบเขต: ngernduangold-* + pantip-* ที่ enabled
เกณฑ์: POSTING-POLICY_antispam_20260702.md (Pantip เฟส 1: ตอบเท่านั้น ≤3/สัปดาห์ เว้นวัน ไร้แบรนด์/ลิงก์/ราคา)

## สรุปสถานะ
| หมวด | สถานะ |
|---|---|
| 1. Cadence งานตั้งเวลา | 🟢 เขียว — ยิงครบทุกตัว ไม่มี approval-trap |
| 2. หลักฐานผลงานจริง (ledger) | 🟡 เหลือง — Threads วันนี้ไม่มีหลักฐาน |
| 3. Compliance + Pantip | 🟢 เขียว — คห.37 ยังอยู่ ไม่มีสัญญาณ mod |
| 4. เว็บ build + smoke | 🟢 เขียว — PASS 71/71 (แต่พบ site/ ค้างครึ่งทาง ซ่อมแล้ว) |
| 5. post-guard ตรวจ YouTube | 🔴 แดง — ตาบอด 4/4 วัน (token) |

## 1. Cadence — 🟢
ตรวจ 20 task (ngernduangold-* + pantip-*) ที่ enabled: lastRunAt ตรง cadence ทุกตัว
ไม่มี task ใหม่/แก้ใหม่ค้างรอ permission (ไม่มี approval-trap)

## 2. หลักฐานผลงาน — 🟡
- post-ledger.jsonl สัปดาห์นี้ (13–19 ก.ค.): 16 รายการ · ช่องบังคับครบ 100% (type/channel/ts/source)
- โควตาตามนโยบาย: ผ่านทุกช่อง (Pinterest 4 พิน/วัน ≤5 · ช่องอื่น ≤2/วัน)
- **19 ก.ค. ไม่มี ledger ของ Threads** ทั้งที่ ngernduangold-threads-daily ยิง 19:08 → น่าจะโพสต์ไม่สำเร็จ
  (post-guard 19:27 รายงาน THREADS = UNKNOWN "ไม่พบ caption prefix บนโปรไฟล์สาธารณะ")
- **ngernduangold-threads-ops-daily ไม่ผลิตงานมา 8 วัน** (ชิ้นสุดท้าย 11 ก.ค.) ทั้งที่ยัง enabled + ยิงทุกวัน
- manifest posted-status ค้าง: 16/17/18/19 ก.ค. ยังเป็น "Scheduled" ทั้งที่ ledger ยืนยันว่าโพสต์แล้ว (16–18)
- manifest batch1 (13–16 ก.ค.) captions ช่อง fb/youtube/threads ว่างเปล่า — batch2 (17 ก.ค. เป็นต้นไป) ครบแล้ว

## 3. Compliance — 🟢
สุ่มตรวจของจริง:
- **Pantip คห.37 กระทู้ 44163092 — ยังอยู่ครบ** (เปิดดูหน้าจริง) ไม่มีแบรนด์/ลิงก์/ราคา/ตัวเลขดอกเบี้ย
  สัปดาห์นี้ตอบ Pantip แค่ 1 ครั้ง (เพดาน 3) → **ไม่ต้อง freeze**
- disclosure ใน manifest 17–20 ก.ค.: ครบทุกช่อง ("ข้อมูลเพื่อการศึกษา" + affiliate ตามจริง + "ผลิตด้วย AI")
- สแกนหาเลขดอกเบี้ย/การันตีผลในทุก caption: **ไม่พบ**
- หมายเหตุเล็ก: caption Threads ใช้ disclosure แบบสั้น ตัด "ไม่ใช่คำแนะนำทางการเงิน" ออก (ยังผ่านเกณฑ์ ข้อ 3)

## 4. เว็บ — 🟢
`SITE_GA=G-17PPE0M1B8 build_site.py` → exit 0 · `postdeploy_smoke.py --src site` → **PASS 71/71 · ปุ่ม atth.me 197**
ไม่ push (ตรวจ local เท่านั้น) · ไม่แตะไฟล์ที่ git ติดตาม

⚠️ ผลข้างเคียงจากการตรวจ (แก้เรียบร้อยแล้ว): build รอบแรกรันบน mount ข้ามระบบซึ่งช้ามาก จึงถูกตัดกลางคัน
ทำให้ `site/` ค้างครึ่งทาง (78 หน้าเขียนใหม่ แต่ URL-normalization + `_redirects` ไม่ทัน — 20 หน้ามีลิงก์ `.html` ค้าง)
→ build ใหม่จนจบบนดิสก์ในเครื่อง แล้วคัดลอกผลกลับมาทับ · ยืนยันซ้ำ: ลิงก์ค้าง 0 หน้า · smoke PASS

## 5. post-guard — 🔴
history.jsonl 13 รายการ ครอบคลุม 16–19 ก.ค. (guard เพิ่งสร้าง 16 ก.ค.) · has_fail = false ทุกครั้ง
แต่ **YOUTUBE = UNKNOWN ทั้ง 4 วัน** เหตุ: `cached YouTube token is invalid or expired` / `HTTP 403 insufficientPermissions`
→ guard "ผ่าน" เพราะตรวจไม่ได้ ไม่ใช่เพราะไม่มีปัญหา = false-green
เกี่ยวโดยตรงกับ incident วันนี้: คลิป eb02/eb03 เผยแพร่แล้ว 0 วิว (ธงแดงข้อ 5 ของกฎ anti-duplicate-promo)

## สิ่งที่ต้องแก้ (เรียงตามความเสี่ยง)
1. 🔴 **ซ่อม YouTube token ของ post-guard** — ตอนนี้ guard ตาบอด YT ทุกวันแต่รายงานว่าผ่าน ทำให้ incident 0 วิว
   ถูกจับได้ช้า และ has_fail=false ใช้เชื่อไม่ได้ จนกว่าจะแก้
2. 🟠 **เช็ก Threads วันนี้ (19 ก.ค.)** — ยิงแล้วแต่ไม่มี ledger/หลักฐาน ถ้าไม่ขึ้นจริงคือขาด 1 วัน
   และเส้นทาง file_upload อาจพังซ้ำรอย 18 ก.ค. (วันนั้นต้องโพสต์มือ)
3. 🟠 **ตัดสินใจกับ ngernduangold-threads-ops-daily** — enabled + ยิงทุกวัน แต่ไม่ผลิตอะไรมา 8 วัน
   ซ้ำหน้าที่กับ ngernduangold-threads-daily (19:00) → ปิดหรือแก้ให้ชัด กัน double-post ในอนาคต
4. 🟡 **อัปเดต manifest posted-status** — 16–18 ก.ค. โพสต์แล้วแต่ยังเป็น "Scheduled"
   ทำให้ตรวจย้อนหลังเชื่อ manifest ไม่ได้ ต้องไปพึ่ง ledger อย่างเดียว
5. 🟡 **build บน mount ช้าจนใช้งานจริงไม่ได้** — ถ้าจะให้ agent ตรวจเว็บอัตโนมัติได้ ต้องรันฝั่ง Windows
   หรือ build บนดิสก์ในเครื่องก่อนเสมอ
6. 🟡 **ig-weekly-pulse (จันทร์ 09:04)** ยังดึง reach จาก Meta ซึ่งใช้ไม่ได้แล้ว — ควรเขียนใหม่หรือปิด กัน task ที่สำเร็จไม่ได้ตลอดกาล

## ที่ทำได้ดี
- Pantip กลับมาแบบมีวินัยจริง: 1/3 ครั้ง เนื้อหาช่วยคนจริง ไร้แบรนด์ ไม่โดนลบ
- ระบบจับ incident YT 0 วิวได้เอง + ออกกฎ anti-duplicate-promo ทันทีในวันเดียวกัน
- ledger ช่องบังคับครบ 100% ไม่มีรายการตกหล่นฟิลด์
