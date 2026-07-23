# WORK ORDER → Claude Code: push commit ค้าง (21 ก.ค. 2026 · จาก Cowork)

> Cowork commit ไว้แต่ push ไม่ได้ (กติกา: Cowork ห้าม push · CC เป็นคนดัน) — ฝากดันให้

## งาน (สั้น ตรง)
push commit ที่ยังไม่ขึ้น remote → `origin/main`

## ✅ ตรวจแล้วว่าปลอดภัย (Cowork เช็คก่อนส่ง)
`git diff --name-only origin/main..main` = 9 ไฟล์ **docs/automation-log/task-mirror + tools/post_guard.py เท่านั้น** — **ไม่มี site/ ไม่มี build_site.py ไม่มี .html/templates** → **ไม่กระทบ Netlify content ไม่ต้อง rebuild**

commit ที่ค้าง (บนสุด = ล่าสุด):
- 105ef5e make Fleet a permanent pattern
- 0927f70 fleet pilot: 2 parallel agents → คลัง kn-15..28 + p2-09..16
- ca50629 fb group scan
- f69a415 threads daily clip recovered + fbgroup-listen guards
- 5459951 fix post_guard threads false-OK

## ขั้นตอน
1. `cd C:\Users\nL_ku\ngernduangold-site`
2. ยืนยันซ้ำ: `git diff --name-only origin/main..main` — ถ้าพบไฟล์ใน `site/` หรือ `build_site.py` หรือ `.html` **หยุด** แล้วรัน build gate ปกติ (`SITE_GA=G-17PPE0M1B8 python build_site.py && python tools/postdeploy_smoke.py --src site` ต้อง PASS) ก่อน push · ถ้าไม่พบ (คาดว่าไม่พบ) → ข้ามไปข้อ 3 ได้เลย
3. `git push origin main`
4. verify: `git log origin/main..main --oneline` ต้องว่าง (= ขึ้นครบ)

## ห้าม
- แก้/เพิ่ม commit เอง · touch ไฟล์อื่น · แตะ secrets
- `git add -A` (ไม่ต้อง add อะไร แค่ push commit ที่ Cowork ทำไว้แล้ว)

## เสร็จแล้ว → เขียนผลลง cc-outbox/result-push-fleet-<ts>.md
รายงาน: push สำเร็จไหม · `git log origin/main..main` ว่างไหม · มี error ไหม
