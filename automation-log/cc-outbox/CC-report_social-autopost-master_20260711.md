# CC report — MASTER: TikTok+IG auto-post pipeline · 11 ก.ค. 2026 (commit 7ae5be1)

## Definition-of-done: โครงสร้าง 100% + ทดสอบสุดทางที่ CC ทำได้ — เหลือ owner prereq 2 อย่าง (ช่องละ 1)

## Deliverable 1: โค้ด pipeline ครบใน repo (push main ตรง — CC ไม่ใช้ PR flow ใน repo นี้ ตาม convention เดิม)
| ชิ้น | ที่อยู่ | สถานะ |
|---|---|---|
| clips (host แล้ว) | `reels/*.mp4` → ngernduangold.com/reels/ | ✅ 9/9 live 200+video/mp4 |
| content-map รวม | `social-autopost/content_map.json` | ✅ 11–19 ก.ค. (igCaption+tiktokCaption+affiliate flag) |
| publish IG | `automation/ig_publish.py` + workflow `ig-reels` (20:00TH) | ✅ v22.0, DRY_RUN ผ่านกับ live |
| publish TikTok | `social-autopost/publish_tiktok.py` (Playwright, ทดลอง) | ✅ --check ผ่านจริง (browser→Studio→ตรวจ login ถูก) |
| orchestrator | `social-autopost/run_daily.py` (TikTok local 19:00) | ✅ channel isolation: IG=cloud Action, TikTok=local task — ช่องนึงพังไม่ลากอีกช่อง |
| token refresh cron | workflow `ig-token-check` (1,15 ของเดือน) | ✅ validate เสมอ + full-auto refresh ถ้าใส่ FB_APP_ID/SECRET+GH_ADMIN_TOKEN |
- หมายเหตุโครงสร้าง: ใช้ layout ที่ deploy แล้ว (`reels/` + `automation/` + `social-autopost/`) แทน `/social-autopost/clips/` — หน้าที่ครบตาม spec, ไม่ restructure ของที่ live แล้ว (order เปิดช่อง "ถ้าเหมาะกว่า")

## Deliverable 2: runbook ✅
`social-autopost/runbook.md` (master ทั้ง 2 ช่อง: prereq, ทดสอบ, เปิด/ปิด auto, แก้ selector, fallback) + `RUNBOOK_ig-reels-api_20260711.md` (IG ละเอียด)

## Deliverable 3: ผลทดสอบจริงช่องละ 1 คลิป
- **IG** 🟡 blocked-on-owner: ต้องมี token (Meta app ~30 นาที) — CC เทสสุดทางแล้ว (DRY_RUN กับ live: video 200 + caption ครบ) · โพสต์จริง = runbook IG §2
- **TikTok** 🟡 blocked-on-owner: ต้อง `--login` ครั้งเดียว — CC เทสสุดทางแล้ว: `--check` เปิด Chromium จริง → ไปหน้า TikTok Studio upload → ตรวจ login-redirect ถูกต้อง exit ตาม spec · ขั้นถัดไปเจ้าของ: `--login` → `--check` → DRY RUN (ทำถึงพร้อมโพสต์+screenshot ไม่กด Post) → `--live` 1 คลิป
- ตามคำสั่ง: **ไม่มี evasion technique ใด ๆ ในสคริปต์** · โดนบล็อกซ้ำ = สลับ fallback semi-auto (daily-reel-prep 18:30 มีอยู่แล้ว) หรือ Postiz

## Deliverable 4: อะไรผ่าน/ติด/เจ้าของทำต่อ
- ผ่าน: hosting, content-map, publishers 2 ตัว (+comply gate ปฏิเสธแคปชันขาด disclaimer/"ผลิตด้วย AI" ทั้งคู่), scheduler 2 ช่องแยกกัน, token cron, dedup กันโพสต์ซ้ำ, log+alert+screenshot, .gitignore กัน session รั่ว
- ติด: (1) โพสต์จริงทั้ง 2 ช่องรอ owner prereq (2) **batch 20–26 ก.ค.** — `SOCIAL-CAPTIONS_batch2` ยังไม่ถึง local (ไฟล์อยู่ outputs ฝั่ง Cowork) → caption sheet ปัจจุบันหมด 19 ก.ค. ระบบจะ log เตือนเอง
- เจ้าของทำต่อ (ครั้งเดียว): ① IG: Meta app + secrets 2 ตัว + เทส (runbook IG §1–2) ② TikTok: `--login` + เทส DRY→live 1 คลิป (runbook §TikTok)
- Compliance: AI-label — TikTok toggle สคริปต์พยายามเปิดให้อัตโนมัติ (หา switch ไม่เจอ = log บอก) · IG อาศัยคำในแคปชัน (API ตั้ง toggle ไม่ได้) · ห้าม bare % — sheet ปัจจุบันสะอาด + gate ใน publisher

---
## BATCH2 MERGED (11 ก.ค. ดึก · commit ล่าสุด) ✅
- **20–26 ก.ค. 7 วัน merge แล้ว** ทั้ง `content_map.json` (IG+TikTok) และ `reels/schedule.json` (IG) → ตารางครบ **16 วัน (11–26 ก.ค.)**
- **CC re-verify comply เอง 7/7 PASS**: disclaimer+"ผลิตด้วย AI" ทุก entry ทั้ง 2 แคปชัน · "มีลิงก์พันธมิตร" ตรง affiliate flag เป๊ะ (24,26=true) · ไม่มี bare % · TikTok ไม่มี URL + ลงท้าย #fyp ทุกตัว
- **clipFile 20–26 = placeholder** (`batch2/<n>_<slug>.mp4`) — คลิปยังไม่ render: ถ้าถึงวันโพสต์แล้วไฟล์ยังไม่มา ทั้ง 2 ช่องจะ **fail-alert อัตโนมัติ** (ทดสอบ fail-path แล้วทั้งคู่ ข้อความชี้ชัด) — ไม่โพสต์มั่ว ไม่เงียบหาย
- build อัปเป็น recursive copy: เจ้าของ/CC วางไฟล์จริงที่ `reels/batch2/` ชื่อตรง placeholder → push → host เองครบ ไม่ต้องแก้ config ใด
- **ค้างที่เจ้าของ/Cowork**: render คลิป batch2 จาก `VIDEO-FACTORY_batch2_20-26jul` ก่อน 20 ก.ค. → วางไฟล์เข้า `reels/batch2/` (หรือส่งให้ CC วาง+verify ให้)
