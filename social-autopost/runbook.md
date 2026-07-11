# RUNBOOK — social-autopost (TikTok + IG) · 11 ก.ค. 2026

ภาพรวม: คลิปรายวัน 1 ตัว → **IG Reels 20:00** (Graph API, GitHub Action — เสถียร) + **TikTok 19:00** (Playwright ขับ TikTok Studio บนเครื่องเจ้าของ — **ทดลอง**, มี fallback)
แหล่งข้อมูลเดียว: `social-autopost/content_map.json` (วันที่ → คลิป + แคปชัน IG/TikTok + affiliate flag) — สร้างจาก caption sheet ที่อนุมัติแล้ว · คลิปอยู่ `reels/` (host ที่ ngernduangold.com/reels/ สำหรับ IG อยู่แล้ว)

## ช่อง IG (เสถียร — ทำก่อน)
→ ดูรายละเอียดเต็มที่ `automation-log/cc-outbox/RUNBOOK_ig-reels-api_20260711.md`
สรุป: owner ทำ Meta app + ใส่ secrets `IG_ACCESS_TOKEN`/`IG_USER_ID` (~30 นาที) → ทดสอบ 1 คลิปผ่าน Actions → auto รายวัน · token มี cron เช็ก/ต่ออายุ (`ig-token-check`)

## ช่อง TikTok (ทดลอง — ทำหลัง IG ผ่าน)
**ความจริงที่ต้องรู้:** ไม่มี API ทางการ → ใช้เบราว์เซอร์จริง (Playwright, ติดตั้งในเครื่องแล้ว: v1.60 + chromium)
เสี่ยง anti-bot/ToS — สคริปต์**ไม่ใส่เทคนิคหลบ detection ใด ๆ** (นโยบาย) ถ้าโดนบล็อก = สลับ fallback ไม่ฝืน

### เจ้าของทำครั้งเดียว
```
cd C:\Users\nL_ku\ngernduangold-site
python social-autopost\publish_tiktok.py --login     ← เบราว์เซอร์เปิด, login บัญชีแบรนด์, ปิดหน้าต่าง
python social-autopost\publish_tiktok.py --check     ← ต้องขึ้น "CHECK OK"
```
session เก็บใน `social-autopost/.tiktok-profile/` (**gitignored — ห้าม commit**)

### ทดสอบ 1 คลิป (บังคับก่อนเปิด auto)
```
python social-autopost\publish_tiktok.py --date 2026-07-12            ← DRY RUN: ทำถึงพร้อมโพสต์ + screenshot, ไม่กด Post
python social-autopost\publish_tiktok.py --date 2026-07-12 --live     ← โพสต์จริง 1 คลิป
```
เช็คบน TikTok: คลิปขึ้น · แคปชันครบ (disclaimer + ผลิตด้วย AI + #fyp) · **AI-label toggle** — สคริปต์พยายามเปิดให้ ถ้า UI หาไม่เจอจะบอกใน log (แคปชันมีคำ "ผลิตด้วย AI" เป็น disclosure หลักอยู่แล้ว)

### เปิด auto รายวัน 19:00 (หลังเทสผ่าน)
```
schtasks /Create /TN "ngern-tiktok-daily" /SC DAILY /ST 19:00 /TR "cmd /c cd /d C:\Users\nL_ku\ngernduangold-site && python social-autopost\run_daily.py --live >> social-autopost\logs\daily.log 2>&1"
```
ปิดชั่วคราว: `schtasks /Change /TN "ngern-tiktok-daily" /DISABLE` (เปิดกลับ `/ENABLE`)
หมายเหตุ: ต้องเป็นช่วงที่เครื่องเปิดอยู่ — ถ้าเครื่องปิด 19:00 งานจะข้ามวัน (Task Scheduler ตั้ง "Run task as soon as possible after a scheduled start is missed" ได้ใน UI)

### ถ้าพัง (ดู log + screenshot ที่ social-autopost/logs/ + alert ที่ automation-log/cowork-inbox/TIKTOK-PUBLISH-FAIL.md)
- **session หลุด** → `--login` ใหม่
- **selector เปลี่ยน** (TikTok ปรับ UI): แก้ dict `SEL` หัวไฟล์ `publish_tiktok.py` จุดเดียว — เปิด upload page ด้วยมือ, กด F12 หา element ใหม่ (หรือส่ง order ให้ CC แก้)
- **โดนบล็อก/แคปช่า ซ้ำ ๆ** → หยุดใช้ (อย่าฝืน/อย่าหาทางหลบ) → **fallback semi-auto**: scheduled task `daily-reel-prep` (18:30) เตรียมคลิป+แคปชันไว้แล้ว เจ้าของลากไฟล์เอง 1 คลิก หรือย้ายไป Postiz (TikTok partner ทางการ)

## Compliance (ทั้งสองช่อง)
- แคปชันจาก sheet อนุมัติเป๊ะ — publisher ทั้งคู่มี **gate ปฏิเสธโพสต์** ถ้าไม่มี "ข้อมูลเพื่อการศึกษา"+"ผลิตด้วย AI"
- ห้าม % ดอกเบี้ยตายตัวในแคปชัน (sheet ปัจจุบันไม่มี) · ความถี่ = 1 คลิป/ช่อง/วัน ห้ามเพิ่มเองโดยไม่ผ่าน Cowork
- dedup: IG `published.json` (repo) · TikTok `logs/published-tiktok.json` (local) — กันโพสต์ซ้ำเมื่อ re-run

## เติม batch (แคปชันหมด 19 ก.ค.)
`SOCIAL-CAPTIONS_batch2_20-26jul` ยังอยู่ฝั่ง Cowork → วางเข้า cc-inbox แล้วสั่ง CC เติม: CC จะเพิ่มคลิปเข้า `reels/` + `reels/schedule.json` (IG) + `social-autopost/content_map.json` (TikTok) ชุดเดียวจบ
