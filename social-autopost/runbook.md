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

---
## GO-LIVE CHECKLIST (เรียงตามเวลา — เจ้าของกดตามนี้เป๊ะ ๆ)
**สถานะตอนนี้ (11 ก.ค.):** scheduler เปิดแล้วทั้งคู่ — IG นัดถัดไป 12 ก.ค. 20:00TH (soft-skip จนกว่ามี token) · TikTok task `ngern-tiktok-daily` 19:00TH (โหมด dry จนกว่า login)

☐ **1. IG (~30 นาที — ทำก่อน 20:00 ของวันที่อยากให้โพสต์แรกขึ้น)**
   1.1 developers.facebook.com → Create App (Business) → Add product "Instagram Graph API"
   1.2 Graph API Explorer → permissions: instagram_content_publish, instagram_basic, pages_show_list, pages_read_engagement → Generate Token
   1.3 หา ig-user-id: GET /me/accounts → {page-id}?fields=instagram_business_account
   1.4 แลก long-lived: GET /v22.0/oauth/access_token?grant_type=fb_exchange_token&client_id=<APP_ID>&client_secret=<APP_SECRET>&fb_exchange_token=<TOKEN>
   1.5 GitHub repo → Settings → Secrets → Actions → เพิ่ม `IG_ACCESS_TOKEN` + `IG_USER_ID`
   1.6 (ทดสอบทันทีไม่รอ 20:00) Actions → ig-reels → Run workflow → date=วันนี้, dry_run=false → เช็ค Reel ขึ้นจริง
   → เสร็จข้อนี้ = IG hands-off ตลอด 16 วัน (และต่อ ๆ ไปเมื่อเติม batch)

☐ **2. TikTok (~10 นาที)**
   2.1 `cd C:\Users\nL_ku\ngernduangold-site && python social-autopost\publish_tiktok.py --login` → login ในเบราว์เซอร์ → ปิดหน้าต่าง
   2.2 `python social-autopost\publish_tiktok.py --check` → ต้อง "CHECK OK"
   2.3 `python social-autopost\publish_tiktok.py --date <วันนี้>` → DRY: ดู screenshot ใน social-autopost\logs\ ว่าหน้าพร้อมโพสต์+แคปชันถูก
   2.4 `python social-autopost\publish_tiktok.py --date <วันนี้> --live` → โพสต์จริง 1 คลิป → เช็คบนแอป
   2.5 สลับ task เป็น live: `schtasks /Change /TN "ngern-tiktok-daily" /TR "cmd /c cd /d C:\Users\nL_ku\ngernduangold-site && python social-autopost\run_daily.py --live >> social-autopost\logs\daily.log 2>&1"`

☐ **3. ก่อน 20 ก.ค.:** วางคลิป batch2 ที่ `reels\batch2\` ชื่อตรง placeholder ใน content_map → `git add reels && git commit && git push` (หรือส่งไฟล์ให้ CC จัดการ+verify hosting)

---
## ช่อง FB Page (feed text + ลิงก์คอมเมนต์แรก — order 11 ก.ค. กลางคืน)
- **Scope IG feed ที่เลือก: (ก)** — IG ใช้ Reels จาก pipeline เดิมเป็นหลัก ไม่ผลิตรูปนิ่งรายวัน (default ตาม order)
- คลังโพสต์: `social-autopost/feed_content_map.json` (12–18 ก.ค. = 7 โพสต์จาก 4 หัวข้อ REACH-PACK: จ่ายขั้นต่ำ/โปะใบไหน/วันปลอดหนี้/เจรจาแบงก์ + variants) — Cowork ส่ง 14-day pack มาเติมต่อได้
- Scheduler: GitHub Action `fb-feed` รายวัน **15:00TH** (08:00 UTC — สล็อต Planner แนะนำ, ไม่ชน Reels 20:00/TikTok 19:00) · channel-isolated
- กติกาใน publisher (fail-closed): body มี disclaimer · **ไม่มี URL ในบอดี้** (ลิงก์อยู่คอมเมนต์แรกเท่านั้น) · affiliate=true ต้องมี "มีลิงก์พันธมิตร" · ไม่มี bare % · dedup รายวัน · soft-skip เขียว+alert ถ้า secrets ยังไม่มา

### Prereq เจ้าของ (ใช้ Meta app เดียวกับ IG — เพิ่ม permission)
1. Graph API Explorer → เพิ่ม permissions: `pages_manage_posts`, `pages_manage_engagement`, `pages_read_engagement` → Generate token ใหม่ → แลก long-lived (ขั้นเดียวกับ IG §1.4)
2. เอา **Page Access Token**: เรียก `GET /me/accounts` ด้วย long-lived user token → ในผลลัพธ์มี `access_token` ของเพจ เงินเดือนสมองทอง (page token จาก long-lived user token = อายุยาวอัตโนมัติ) + `id` ของเพจ
3. GitHub → Settings → Secrets → Actions: เพิ่ม `FB_PAGE_ID` + `FB_PAGE_TOKEN`
4. ทดสอบ: Actions → fb-feed → Run workflow → date=วันนี้, dry_run=false → เช็คโพสต์ขึ้นเพจ + คอมเมนต์แรกมีลิงก์กดได้ → จบ auto รายวัน

### ปิด/แก้
- ปิดชั่วคราว: Actions → fb-feed → Disable workflow · ข้ามวัน: ลบ entry ใน feed_content_map.json
- token พัง (code 190 ใน log): ทำ Prereq ข้อ 1–3 ใหม่ · โพสต์ขึ้นแต่คอมเมนต์พลาด: alert จะบอกข้อความคอมเมนต์ให้เติมมือ (โพสต์ไม่ถูกยิงซ้ำ — dedup กันแล้ว)
