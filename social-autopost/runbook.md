# RUNBOOK — social-autopost (TikTok + IG) · ปรับปรุง 16 ส.ค. 2026

ภาพรวม: IG และ FB มีเส้นทางแยกของตนเอง ส่วน **TikTok อยู่สถานะ retired / local-only** ไม่มีงานอัตโนมัติที่อัปโหลดหรือเผยแพร่ วงจรตามตารางทำได้เพียงตรวจแผนในเครื่อง
แหล่งข้อมูลเดียว: `social-autopost/content_map.json` (วันที่ → คลิป + แคปชัน IG/TikTok + affiliate flag) — สร้างจาก caption sheet ที่อนุมัติแล้ว · คลิปอยู่ `reels/` (host ที่ ngernduangold.com/reels/ สำหรับ IG อยู่แล้ว)

## ช่อง IG (เสถียร — ทำก่อน)
→ ดูรายละเอียดเต็มที่ `automation-log/cc-outbox/RUNBOOK_ig-reels-api_20260711.md`
สรุป: owner ทำ Meta app + ใส่ secrets `IG_ACCESS_TOKEN`/`IG_USER_ID` (~30 นาที) → ทดสอบ 1 คลิปผ่าน Actions → auto รายวัน · token มี cron เช็ก/ต่ออายุ (`ig-token-check`)

## ช่อง TikTok — retired / local-only

### ข้อเท็จจริง API ปัจจุบัน

TikTok มี [Content Posting API](https://developers.tiktok.com/products/content-posting-api) อย่างเป็นทางการแล้ว 2 รูปแบบ:

- **Direct Post** ใช้ scope `video.publish`; ต้องมีแอปที่ลงทะเบียน เปิดผลิตภัณฑ์ Content Posting API ผ่านการอนุมัติ scope และได้รับสิทธิ์จากบัญชีเป้าหมาย ก่อนเริ่มโพสต์ต้องเรียก `creator_info/query` และใช้ตัวเลือกความเป็นส่วนตัว/ความยาวที่ API ส่งกลับจริง
- **Upload draft** ใช้ scope `video.upload`; ส่งสื่อเข้ากล่องของผู้ใช้เพื่อให้ผู้ใช้เปิด TikTok ตรวจแก้และกดโพสต์เอง
- Direct Post จาก client ที่ยังไม่ผ่าน audit ถูกจำกัดการมองเห็นเป็น private/`SELF_ONLY`; การเผยแพร่สาธารณะต้องผ่าน audit ตาม [Direct Post reference](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post) และ [Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines)
- `FILE_UPLOAD` รองรับวิดีโอในเครื่อง ส่วน `PULL_FROM_URL` ต้องยืนยันความเป็นเจ้าของโดเมน/URL prefix ก่อน
- Guidelines ของ API ห้าม integration ซ้อนชื่อแบรนด์ โลโก้ watermark ลิงก์ หรือข้อความโปรโมตลงในสื่อ ดังนั้น receipt ที่ระบุเพียงว่า "ไม่ใช่ provider watermark" ยังไม่พอสำหรับเส้นทาง API; ต้องทบทวนภาพจริงตามเกณฑ์ TikTok อีกครั้งก่อนยื่น audit/ส่งสื่อ

โปรเจกต์นี้ **ยังไม่มี TikTok developer app, scope/token, creator-info flow หรือ audit evidence ที่ลงทะเบียนไว้ใน SSOT** จึงยังห้ามใช้ API เพื่อส่งสื่อ และห้ามตีความว่ามี API แล้วเท่ากับพร้อมเปิด auto

### คำสั่งตรวจแผนที่ปลอดภัย

```powershell
cd C:\Users\nL_ku\ngernduangold-site
python social-autopost\publish_tiktok.py --date 2026-08-16
python social-autopost\publish_tiktok.py --plan --date 2026-08-16
```

ทั้งสองคำสั่งอ่าน `content_map.json` และตรวจว่าคลิป/คำเปิดเผยมีอยู่เท่านั้น: **ไม่ import Playwright, ไม่เปิดเบราว์เซอร์, ไม่ login และไม่ส่งไฟล์** วันที่ไม่มีแผนหรือไฟล์หายต้องจบด้วย exit code 2. `--login` และ `--check` เดิมถูกปิดและคืน exit code 2 โดยไม่เปิดเบราว์เซอร์

### เส้นทาง `--live` ที่เก็บไว้เป็น fallback

เส้นทางนี้ไม่ใช่ scheduler และไม่ใช่การอนุญาตให้เผยแพร่ ตัวโปรแกรมจะหยุดก่อน import/เปิด Playwright หากข้อใดข้อหนึ่งไม่ครบ:

1. วันที่ต้องตรงกับวันปัจจุบันในไทยและมี entry เฉพาะชิ้นใน `content_map.json`
2. policy ต้องเปิดช่อง TikTok, actor ต้องมี `social_publish`, บัญชีเป้าหมายต้องตรง และมี owner approval รายชิ้นครบ
3. คลิปต้องมี `contentId`, `mediaReceipt` และ `approval.asset_sha256` ที่ตรงกับไฟล์จริง
4. hash-bound visual/watermark/novelty QA ต้อง PASS และ content ID ใน receipt ต้องตรงกับแผน
5. แคปชันและคลิปต้องผ่าน permanent dedup; โปรแกรมเขียน write-ahead claim ก่อนแตะเบราว์เซอร์เพื่อกันการยิงซ้ำพร้อมกัน

แม้ผ่านทั้งหมดก็ยังเป็น owner-controlled fallback และผลหลังคลิกจะบันทึกเป็น `submitted_unverified` จนกว่าจะตรวจผลใน TikTok/Studio จริง ห้ามใส่ `--live` ใน `run_daily.py`, Task Scheduler, GitHub Actions หรือ loop อัตโนมัติ

### Scheduled route

`social-autopost/run_daily.py` เรียกได้เฉพาะ `publish_tiktok.py --plan` และไม่รับ `--live` งาน `ngern-tiktok-daily` ต้องคงสถานะ disabled; **ห้าม `/ENABLE`** จนกว่า policy/บัญชี/แผน 14 วัน/หลักฐาน dedup/landing page และเส้นทาง API ที่ผ่าน review จะครบแล้วได้รับอนุมัติรอบใหม่

ทดสอบ safety contract:

```powershell
python tools\test_tiktok_publisher_safety.py
python tools\test_external_notification_safety.py
```

## Compliance (ทั้งสองช่อง)
- แคปชันจาก sheet อนุมัติเป๊ะ — publisher ทั้งคู่มี **gate ปฏิเสธโพสต์** ถ้าไม่มี "ข้อมูลเพื่อการศึกษา"+"ผลิตด้วย AI"
- ห้าม % ดอกเบี้ยตายตัวในแคปชัน (sheet ปัจจุบันไม่มี) · ความถี่ = 1 คลิป/ช่อง/วัน ห้ามเพิ่มเองโดยไม่ผ่าน Cowork
- dedup: IG `published.json` (repo) · TikTok ใช้ทั้ง `logs/published-tiktok.json`, caption dedup และ write-ahead claim ใน `automation-log/post-ledger.jsonl`

## เติม batch (แคปชันหมด 19 ก.ค.)
`SOCIAL-CAPTIONS_batch2_20-26jul` ยังอยู่ฝั่ง Cowork → วางเข้า cc-inbox แล้วสั่ง CC เติม: CC จะเพิ่มคลิปเข้า `reels/` + `reels/schedule.json` (IG) + `social-autopost/content_map.json` (TikTok) ชุดเดียวจบ

---
## GO-LIVE CHECKLIST (เรียงตามเวลา — เจ้าของกดตามนี้เป๊ะ ๆ)
**สถานะ TikTok ตอนนี้ (16 ส.ค.):** retired / local-only; ไม่มีคำสั่งอัปโหลดหรือโพสต์ใน scheduler และคำสั่งตรวจแผนไม่แตะเบราว์เซอร์

☐ **1. IG (~30 นาที — ทำก่อน 20:00 ของวันที่อยากให้โพสต์แรกขึ้น)**
   1.1 developers.facebook.com → Create App (Business) → Add product "Instagram Graph API"
   1.2 Graph API Explorer → permissions: instagram_content_publish, instagram_basic, pages_show_list, pages_read_engagement → Generate Token
   1.3 หา ig-user-id: GET /me/accounts → {page-id}?fields=instagram_business_account
   1.4 แลก long-lived: GET /v22.0/oauth/access_token?grant_type=fb_exchange_token&client_id=<APP_ID>&client_secret=<APP_SECRET>&fb_exchange_token=<TOKEN>
   1.5 GitHub repo → Settings → Secrets → Actions → เพิ่ม `IG_ACCESS_TOKEN` + `IG_USER_ID`
   1.6 (ทดสอบทันทีไม่รอ 20:00) Actions → ig-reels → Run workflow → date=วันนี้, dry_run=false → เช็ค Reel ขึ้นจริง
   → เสร็จข้อนี้ = IG hands-off ตลอด 16 วัน (และต่อ ๆ ไปเมื่อเติม batch)

☐ **2. TikTok — ห้าม go-live ตอนนี้**
   2.1 ใช้ `publish_tiktok.py --plan --date <วันนี้>` เพื่อตรวจ local plan เท่านั้น
   2.2 สร้าง developer app/ขอ scope/ออกแบบ consent + creator-info UI และผ่าน audit ก่อนพิจารณาเส้นทาง API สาธารณะ
   2.3 ทำแผนสื่อที่ไม่ซ้ำและ QA ครบตาม runway แล้วจึงขออนุมัติเปิด policy/บัญชี/ชิ้นงานรอบใหม่
   2.4 ห้ามเปิด scheduled task หรือใช้ Playwright fallback ระหว่างที่ข้อ 2.2–2.3 ยังไม่ครบ

☐ **3. ก่อน 20 ก.ค.:** วางคลิป batch2 ที่ `reels\batch2\` ชื่อตรง placeholder ใน content_map → `git add reels && git commit && git push` (หรือส่งไฟล์ให้ CC จัดการ+verify hosting)

---
## ช่อง FB Page (feed text + ลิงก์คอมเมนต์แรก — order 11 ก.ค. กลางคืน)
- **Scope IG feed ที่เลือก: (ก)** — IG ใช้ Reels จาก pipeline เดิมเป็นหลัก ไม่ผลิตรูปนิ่งรายวัน (default ตาม order)
- คลังโพสต์: `social-autopost/feed_content_map.json` (12–25 ก.ค. = 14 โพสต์: REACH-PACK หนี้ 12–18 + SAVE-PACK ออม/บูโร/รวมหนี้ 19–25 เติมเมื่อ 16 ก.ค.) — หมดคิว 25 ก.ค. เติม pack ถัดไปก่อนวันนั้น
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
