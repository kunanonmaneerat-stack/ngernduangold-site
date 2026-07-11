# CC report — IG Reels auto-publish pipeline พร้อมใช้ (DORMANT รอ token) · 11 ก.ค. 2026 (commit 7d20a79)

## สถานะ: โครงสร้างเสร็จ 100% + verify แล้ว — **ยังไม่โพสต์อะไรทั้งสิ้น** จนเจ้าของใส่ secrets + กดทดสอบเอง (ตามลำดับใน runbook)

## 1) Hosting ✅ LIVE
- คลิป 9 ตัว (11–19 ก.ค.) ที่ `ngernduangold.com/reels/<date>_<slug>.mp4` — ตรวจครบ **9/9 = 200 + video/mp4** + เล่นจริงใน browser (720x1280)
- mapping ตรง order เป๊ะ: 11=kp04 · 12=tl01b · 13=tl03 · 14=tl04 · 15=tl05 · 16=kp05 · 17=eb02 · 18=kp06 · 19=eb03
- **ไม่อยู่ใน sitemap/nav + robots `Disallow: /reels/`** ✓ (asset สำหรับ API ล้วน)
- ⚠️ policy exception ที่จงใจ: mp4 เข้า public repo (18MB) — จำเป็นเพราะ Netlify build จาก git และคลิปเหล่านี้คือ content ที่เผยแพร่ public อยู่แล้ว · เก่าแล้วลบทิ้งได้ (runbook §5)

## 2) Publisher `automation/ig_publish.py` ✅
- 2-step ตามสเปก: `POST /media` (REELS+video_url+caption+share_to_feed) → poll `status_code=FINISHED` (สูงสุด 5 นาที) → `POST /media_publish`
- caption = เวอร์ชัน IG จาก POST-PACK ที่อนุมัติแล้ว **เป๊ะทุกบรรทัด** (hook + ลิงก์ในไบโอ + disclaimer + hashtags; eb02/eb03 ใช้ "มีลิงก์ขายคู่มือของเราเอง" ตาม sheet)
- Guard 4 ชั้น: (1) **comply fail-closed** — แคปชันไม่มี "ข้อมูลเพื่อการศึกษา"+"ผลิตด้วย AI" = ปฏิเสธโพสต์ (2) URL precheck 200+video/mp4 ก่อนเรียก Meta (3) dedup `published.json` กันโพสต์ซ้ำตอน re-run (4) token expired (code 190) = ข้อความชี้ runbook §4 ชัด ๆ
- fail → exit 2 → Action แดง (GitHub อีเมลแจ้งเจ้าของ) + เขียน `cowork-inbox/IG-PUBLISH-FAIL.md`
- DRY_RUN ทดสอบกับ live แล้วผ่าน (12 ก.ค.: video OK + caption ครบ)

## 3) Scheduler `.github/workflows/ig-reels.yml` ✅
- cron `0 13 * * *` = **20:00 ไทย** รายวัน · เลือกคลิป+แคปชันของวันเองจาก `reels/schedule.json` · หมด sheet = log เตือน "ต้องเติม batch" (ไม่ fail)
- manual run (ทดสอบ): เลือก date + dry_run ได้ · scheduled run = LIVE อัตโนมัติเมื่อมี secrets
- log commit กลับ repo (Netlify ignore rule ข้าม automation-log = ไม่ rebuild)

## 4) Runbook → `cc-outbox/RUNBOOK_ig-reels-api_20260711.md`
§1 owner setup ทีละขั้น (Meta app → permissions 4 ตัว → ig-user-id → long-lived token → GitHub secrets) · §2 **บังคับทดสอบ 1 คลิป dry→จริง ก่อนเปิด auto** · §4 token refresh ทุก ~50 วัน · §5 kill switch (Disable workflow) · §6 caveats (AI toggle ตั้งผ่าน API ไม่ได้ → เปิดเผยด้วยข้อความในแคปชันแทน + มี gate บังคับ)

## ยังค้าง / หมายเหตุ
- **batch 20–26 ก.ค.**: `SOCIAL-CAPTIONS_batch2` อยู่ใน outputs ของ Cowork ไม่ถึง local — ส่งมาแล้ว CC เติม schedule ให้ (คลิป dc01–dc05/sp01/sp02 อยู่ใน _social-stage แล้วบางส่วน)
- **นโยบาย bot-posting suspended (19 มิ.ย.)**: order นี้ = เจ้าของสั่ง re-enable เฉพาะ **IG 1 Reel/วัน ผ่าน official API** (ไม่ใช่ web-bot แบบเดิม) — บันทึกไว้ว่าเป็นการตัดสินใจระดับ owner · TikTok ไม่แตะตามคำสั่ง
- Gates เว็บไม่กระทบ: smoke 67/67 · link_check 0 · affiliate 17/17

## เจ้าของทำต่อ (ครั้งเดียว): runbook §1 (~30 นาที) → §2 ทดสอบ 1 คลิป → จบ, hands-off

---
## RECONCILE กับ order ฉบับละเอียด (11 ก.ค. ค่ำ · commit c037a33) — deliverables ครบ 5/5
1. **คลิป host แล้ว (URL list)** ✅ — 9/9 = 200 + video/mp4 + เล่นจริง:
   `ngernduangold.com/reels/` → `2026-07-11_kp04` · `12_tl01b` · `13_tl03` · `14_tl04` · `15_tl05` · `16_kp05` · `17_eb02` · `18_kp06` · `19_eb03` (.mp4)
   (path ใน repo = `reels/` → serve ที่ `/reels/` ตาม URL spec · ไม่อยู่ใน sitemap/nav + robots Disallow ✓)
2. **สคริปต์ + scheduler ใน repo** ✅ — `automation/ig_publish.py` (อัปเป็น **v22.0 + poll 5 วิ/timeout 5 นาที ตาม spec เป๊ะ**) + `.github/workflows/ig-reels.yml` (cron 0 13 * * * = 20:00TH) · error handling ครบ: container fail / publish fail / token 190 → log + alert file + Action แดง, ไม่พัง pipeline (exit-code แยกชั้น)
3. **runbook step-by-step** ✅ — `RUNBOOK_ig-reels-api_20260711.md` + **token refresh cron ใหม่**: workflow `ig-token-check` (วันที่ 1+15) validate เสมอ; ใส่ `FB_APP_ID`+`FB_APP_SECRET`+`GH_ADMIN_TOKEN` = **full auto-refresh** ก่อนครบ 60 วัน (แลก token + อัปเดต secret เอง ไม่ log ค่า token)
4. **ผลทดสอบ 1 โพสต์จริง** 🟡 BLOCKED-ON-OWNER — ต้องมี `IG_ACCESS_TOKEN`/`IG_USER_ID` ก่อน (prereq §1 ~30 นาที) · CC ทดสอบได้สุดทางแล้ว: DRY_RUN กับ live ผ่าน (video OK + caption ครบ disclaimer/AI) · ขั้น publish จริง = runbook §2 (manual run, dry_run=false, 1 คลิป ช่วง low-traffic)
5. **TikTok ไม่ถูกแตะ** ✅ — ยืนยัน: ไม่มีโค้ด/config ใดแตะ TikTok · แยกไป Postiz/manual ตามนโยบาย
- Compliance: แคปชันจาก sheet อนุมัติเป๊ะ (local POST-PACK ตรงกับ ig_tiktok_clips sheet) · ไม่มี bare % · AI-toggle caveat flag แล้ว (เปิดเผยผ่านข้อความ+gate บังคับ) · batch 20–26 รอไฟล์ SOCIAL-CAPTIONS_batch2 เข้า cc-inbox
