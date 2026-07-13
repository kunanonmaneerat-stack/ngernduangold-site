# ▶️ CC ORDER — batch2 โพสต์ผ่าน API (FB 21–26 + IG 20–26) · 12 ก.ค. ค่ำ
เหตุ: FB manual ผ่าน Business Suite ติด **media-cache bug** (composer ยัดคลิปล่าสุดกลับมาทุกครั้ง + reset FB+IG ติดบล็อกอัตราส่วน IG 9:16) → เจ้าของอนุมัติย้าย FB 21–26 + IG 20–26 ไป Graph API
**คลิป 20 FB ตั้ง manual แล้ว (20 ก.ค. 19:00, single) — ห้ามตั้ง FB วันที่ 20 ซ้ำเด็ดขาด**

## ⚠️ DUP-GUARD (สำคัญสุด)
- **FB: ตั้งเฉพาะ 21, 22, 23, 24, 25, 26** (ไม่เอา 20 — manual ทำแล้ว · ตั้งซ้ำ = โพสต์ซ้ำ)
- **IG: ตั้ง 20, 21, 22, 23, 24, 25, 26** (ครบ 7 — IG ยังไม่มีอะไรตั้ง)
- ก่อนสร้างแต่ละอัน: query scheduled posts ที่มีอยู่ ถ้าวันนั้น/ช่องนั้นมีแล้ว = ข้าม
- 1 โพสต์/ช่อง/วัน · **19:00 Asia/Bangkok (UTC+7)** ทุกอัน · disclosure คงตาม manifest (24 & 26 = affiliate)

## อินพุต
- คลิป: `reels/batch2/NN_*.mp4` (live บน ngernduangold.com แล้ว — ใช้ hosted URL หรือไฟล์ตาม pipeline)
- แคปชัน: `.system_control/content_manifest.json` → `captions.fb` / `captions.ig` ต่อวัน (ใช้ตามนั้น ห้ามแก้)
- Token: FB Page access token + IG access token (เจ้าของเซ็ตให้ = รายการ "IG/FB token" ที่ค้าง) — ถ้ายังไม่มี ให้บอกชัดว่าต้องได้ token อะไรบ้าง

## FB 21–26 — Graph API (schedule ตรง)
- `POST /{page-id}/video_reels` (หรือ `/videos`) · `scheduled_publish_time` = unix(วันนั้น 19:00 +07) · `published=false`
- video = hosted mp4 URL · `description` = `captions.fb[date]`
- ยืนยัน: ได้ id + `scheduled_publish_time` ตรงทุกอัน (6 อัน)

## IG 20–26 — ig-reels pipeline เดิม
- ใช้ automation ที่มี (Content Publishing API: create container → publish) ตั้งยิง 19:00 +07 ต่อวัน (cron/Actions หรือกลไก schedule ของ pipeline)
- caption = `captions.ig[date]` (7 อัน)

## หลังตั้งเสร็จ
- อัปเดต manifest: `posted.fb[21–26]` + `posted.ig[20–26]` = timestamp ที่ schedule · `posted.fb[20]` = "manual" · (= wire posted tracking)
- **back-fill `posted` 13–19 ครบ 5 ช่อง** (manifest posted ว่างแต่ 13–19 live แล้ว — กัน false gap ตั้งซ้ำในอนาคต)
- commit manifest (skip-build · `.system_control` ถูก ignore แล้ว) — **`git add` เจาะจง ห้าม -A**
- หมายเหตุ: ไฟล์ order นี้ + เอกสาร scratch อื่นเป็น untracked → git clean ลบได้ ถ้าอยากเก็บให้ commit เข้า automation-log/

## รายงานกลับ Cowork
- ตาราง: วันที่ × ช่อง → scheduled / failed + เหตุผล
- วัน/ช่องไหนต้องรอ token เจ้าของ (ระบุ token ที่ต้องการ)
- **ยืนยัน FB วันที่ 20 ไม่ถูกแตะ**
- ถ้าติด token / API error → หยุด รายงาน ห้าม retry รัว (กัน rate-limit/shadowban)
