# RUNBOOK — IG Reels auto-publish ผ่าน Graph API · 11 ก.ค. 2026

ระบบ: คลิปโฮสต์ที่ `ngernduangold.com/reels/<date>_<slug>.mp4` (Netlify, ไม่ index) → GitHub Action `ig-reels` รันทุกวัน **20:00 ไทย** → เรียก Instagram Content Publishing API → Reel ขึ้น IG อัตโนมัติ พร้อมแคปชันจาก sheet ที่อนุมัติแล้ว (disclaimer + "ผลิตด้วย AI" ครบทุกตัว — script **ปฏิเสธโพสต์** ถ้าแคปชันขาด disclaimer)

## §1 Prereq เจ้าของ (ทำครั้งเดียว ~30 นาที)
1. IG @ngernduangold ต้องเป็น **Professional (Business/Creator)** และลิงก์กับ FB Page ของแบรนด์ (Settings → Business tools → เชื่อม Page · business_id `710600596463607`)
2. ไป https://developers.facebook.com → **Create App** → type "Business" → ตั้งชื่อ เช่น `ngern-reels`
3. ใน app → Add product **Instagram Graph API**
4. **Graph API Explorer** (https://developers.facebook.com/tools/explorer):
   - เลือก app ที่สร้าง → User Token → Add permissions: `instagram_content_publish`, `instagram_basic`, `pages_show_list`, `pages_read_engagement` → Generate Access Token (login + อนุญาต)
5. หา **IG Business Account ID** (ig-user-id — ไม่ใช่ username):
   - ใน Explorer เรียก `GET /me/accounts` → เอา Page id → เรียก `GET /{page-id}?fields=instagram_business_account` → ได้ id ตัวเลข (คาดว่า = asset_id `583765282304956` — ยืนยันด้วยการเรียกจริง)
6. แปลง token เป็น **long-lived (60 วัน)**:
   `GET https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=<APP_ID>&client_secret=<APP_SECRET>&fb_exchange_token=<SHORT_TOKEN>`
   → ได้ `access_token` ใหม่ (ห้ามแปะลงแชท/ไฟล์ใด ๆ ในเรโป)
7. ใส่ secrets ใน GitHub: repo `ngernduangold-site` → Settings → Secrets and variables → Actions → New repository secret:
   - `IG_ACCESS_TOKEN` = long-lived token
   - `IG_USER_ID` = ig-user-id จากข้อ 5

## §2 ทดสอบ 1 คลิปก่อนเปิด auto (บังคับ)
1. GitHub → Actions → workflow **ig-reels** → **Run workflow**:
   - ครั้งแรก: `dry_run=true` (default) → ดู log ต้องเห็น "video OK" + caption preview ถูกต้อง
   - ครั้งสอง (ช่วง low-traffic): `dry_run=false`, `date=` วันที่มีในตาราง → ดู log "PUBLISHED ... media_id=..."
2. เปิด IG ดูจริง: ขึ้นเป็น **Reel** · แคปชันครบ (disclaimer + ลิงก์ในไบโอ + hashtags) · วิดีโอเล่นปกติ
3. ผ่านแล้ว = ไม่ต้องทำอะไรเพิ่ม — cron 20:00 ไทยจะยิงรายวันเองจาก `reels/schedule.json` (มีถึง **19 ก.ค.**)

## §3 การทำงานปกติ
- โพสต์สำเร็จ → log ที่ `automation-log/ig-reels/log-<date>.md` + กันโพสต์ซ้ำด้วย `published.json`
- วันที่ไม่มีในตาราง → log เตือน "ต้องเติม batch" (ไม่ fail) — **เติม batch:** CC เพิ่มคลิป+แคปชันใน `reels/` + `schedule.json` (สั่งผ่าน order ได้; batch 20–26 ก.ค. รอไฟล์ `SOCIAL-CAPTIONS_batch2` จาก Cowork)
- โพสต์ fail → Action แดง (GitHub ส่งอีเมลแจ้งเจ้าของอัตโนมัติ) + ไฟล์ `automation-log/cowork-inbox/IG-PUBLISH-FAIL.md` บอกสาเหตุ

## §4 Token หมดอายุ (ทุก ~60 วัน)
**มี cron เช็กอัตโนมัติแล้ว**: workflow `ig-token-check` รันวันที่ 1 และ 15 ของเดือน — validate token เสมอ (พัง = Action แดง + อีเมลแจ้ง)
- **โหมด full-auto (แนะนำ)**: ใส่ secrets เพิ่ม 3 ตัว → `FB_APP_ID`, `FB_APP_SECRET` (จากหน้า Meta app), `GH_ADMIN_TOKEN` (GitHub PAT สิทธิ์ repo-admin สำหรับอัปเดต secret) — เหลือ <21 วัน ระบบจะแลก token ใหม่ + อัปเดต secret `IG_ACCESS_TOKEN` เองทั้งหมด ไม่ต้องแตะอีก
- **โหมด manual** (ไม่ใส่ 3 ตัวข้างบน): cron ยัง validate ให้ — พอใกล้หมด/หมด Action จะแดงเตือน แล้วทำมือตามนี้:
1. รันคำสั่งแลก token ข้อ §1.6 อีกครั้ง (ใช้ token ปัจจุบันเป็น fb_exchange_token ได้ ถ้ายังไม่หมดอายุ)
2. อัปเดต GitHub secret `IG_ACCESS_TOKEN` ค่าใหม่ — จบ
- ถ้าหมดอายุไปแล้ว (error code 190 ใน log): generate ใหม่จาก Graph API Explorer (§1.4) แล้วแลกเป็น long-lived

## §5 ปิด auto ชั่วคราว / กรณีฉุกเฉิน
- **ปิดทั้งระบบ**: GitHub → Actions → ig-reels → ปุ่ม "..." มุมขวา → **Disable workflow** (เปิดกลับ = Enable)
- **ข้ามวันเดียว**: ลบ entry วันนั้นออกจาก `reels/schedule.json` แล้ว commit
- **ลบคลิปออกจากเว็บ**: ลบไฟล์ใน `reels/` + commit (Netlify rebuild เอง)

## §6 ข้อจำกัด/คำเตือน
- **AI toggle บน IG**: API ตั้ง "สร้างด้วย AI" toggle ให้ไม่ได้ทุกกรณี → เราเปิดเผยด้วยข้อความ "ผลิตด้วย AI" ในแคปชันทุกโพสต์แทน (มี gate บังคับใน script)
- **GitHub scheduled workflow หยุดเองถ้า repo ไม่มี commit ~60 วัน** — เรามี cron log push รายวันอยู่แล้ว โอกาสโดนต่ำ แต่ถ้า Action เงียบให้เช็ค Actions tab ว่าถูก disable หรือไม่
- อัตราโพสต์: ระบบนี้ = 1 Reel/วัน ตามนโยบาย measured-frequency (อย่าเพิ่มความถี่โดยไม่ผ่าน Cowork)
- TikTok: **ทำผ่าน API ตรงไม่ได้** (ไม่มี organic posting API สำหรับบัญชีทั่วไป) — ใช้ (ก) ลากมือรายวันจาก `daily-reel-prep` 18:30 หรือ (ข) Postiz (พาร์ตเนอร์ TikTok ทางการ — มี MCP อยู่แล้ว แต่จำนโยบาย bot-posting suspended: ให้ Cowork/เจ้าของตัดสินใจ re-enable เอง)
