# VIDEO-POST VERIFY - 2026-07-16 - ผล: FAIL (ความละเอียด 720p) · WATERMARK สะอาด
รันโดย Cowork auditor (อ่านอย่างเดียว · ไม่โพสต์/ไม่ลบ/ไม่แก้) · เกณฑ์ตัดสินหลัก = qa_watermark frame-scan (fps=3) + ffprobe resolution + SPEC discriminator

## สรุปเร็ว (อ่านตรงนี้พอ)
- ✅ WATERMARK FRAME-SCAN = PASS ทุกไฟล์ (0 เฟรมลายน้ำ Veo) — อันตรายเฉียบพลัน (ลายน้ำ ✦ หลุด) ไม่มีในโพสต์วันนี้
- ❌ YouTube วันนี้ = kp05 = **720x1280** = FAIL ตามกฎ SPEC (ต้อง 1080x1920 จาก _vidout\reel_*) — ดีเฟกต์ซ้ำคลาสเดียวกับ _VERIFY_ALERT_20260628 (ชุด _final batch1 720p)
- ⚠️ ไม่ใช่เคสอันตราย: kp05 เป็นคลิป flow ที่ผลิตจริง (มีฮุก + CTA 'ลิงก์ในไบโอ/ngernduangold.com/links' + disclosure 'ผลิตด้วย AI' + ธีมถูก = เงินสำรอง) ยืนยันด้วยการดึงเฟรม — ไม่ใช่คลิป plain clips-web, ไม่มีลายน้ำ, บัญชีถูก → ดีเฟกต์ 'ความละเอียดอย่างเดียว'
- ⚠️ IG/FB โพสต์วันนี้ (delivery-verify = LIVE) แต่ Meta MCP เกินโควตา Free รายสัปดาห์ → ยืนยัน media สดไม่ได้; ถ้า IG/FB ใช้ไฟล์ batch1 ตัวเดียวกัน = ดีเฟกต์ 720p เดียวกัน → owner eyeball

## รายช่อง/โพสต์ (16 ก.ค.)
| ช่อง | โพสต์วันนี้ | ไฟล์ต้นทาง (local) | ความละเอียด | wm-scan (fps3) | ฮุก/CTA/disclosure/บัญชี | ผล |
|---|---|---|---|---|---|---|
| YouTube | kp05 (คิว YT 16 ก.ค. ตาม launch-status; delivery-verify=LIVE 18:00) | reels/2026-07-16_kp05.mp4 = _social-stage/_final_kp05.mp4 | 720x1280 | PASS 0/24 | ครบ/ถูก (ยืนยันเฟรม t3,t6) | ❌ FAIL (720x1280 < SPEC 1080x1920) |
| Instagram | multicast (delivery-verify=LIVE) | ยืนยันไฟล์สดไม่ได้ (Meta MCP quota) | น่าจะ 720p (batch1) | batch1 local=PASS | ยืนยันสดไม่ได้ | ⚠️ UNVERIFIED (eyeball) |
| Facebook | multicast (delivery-verify=LIVE) | ยืนยันไฟล์สดไม่ได้ (Meta MCP quota) | น่าจะ 720p (batch1) | batch1 local=PASS | ยืนยันสดไม่ได้ | ⚠️ UNVERIFIED (eyeball) |

หมายเหตุ: delivery-verify (21:21) ระบุ 'emergency-fund multicast' — 'emergency-fund' = **ธีม** ของ kp05 (แคปชัน 'อยากมีเงินสำรอง? เริ่มจากก้อนเล็ก...') ไม่ใช่ไฟล์ _vidout/reel_emergency-fund มาสเตอร์ 1080p. คิว YT 16 ก.ค. = kp05 ตาม launch-status.json + reels/schedule.json + .system_control/content_manifest.json ตรงกัน.

## หลักฐานชี้ขาด (ffprobe WxH + qa_watermark)
- ❌ reels/2026-07-16_kp05.mp4 = 720x1280 · wm PASS 0/24 (สแกนสด 16 ก.ค.)
- ❌ คิว YT batch1 ทั้งชุด 11-19 ก.ค. = 720x1280 ทุกไฟล์ (kp04/tl01b/tl03/tl04/tl05/kp05/eb02/kp06/eb03) — เป็นระบบ ไม่ใช่ one-off
- ❌ _social-stage/_final_*.mp4 (dc/sp/eb/kp/tl 16 ไฟล์) = 720x1280 ทั้งหมด
- ✅ _vidout/reel_*.mp4 (7 มาสเตอร์) = 1080x1920 ครบ · ✅ _vidout/clean/*_clean.mp4 (5 ตัว: emergency-fund/compound/save-small/auto-save/title-loan) = 1080x1920 · wm PASS 0/60 ต่อไฟล์ — **แต่ไม่ถูกใช้กับคิว YT 11-19**
- ref: media/clips-web/*.mp4 = 720x1280 (ตัว plain known-bad); kp05 **ไม่ใช่** clips-web (มีฮุกบนจอ + coin footage)

## ราก (root cause) — ซ้ำ 06-28
สาย batch1 flow (_social-stage/_final_ kp/eb/tl) เรนเดอร์ที่ 720x1280; คิว YouTube 11-19 ก.ค. ใช้ไฟล์ชุดนี้ (owner/Cowork ตั้งเวลาไว้ 5-9 ก.ค. ตาม launch-status 'watermark-free') โดยไม่ผ่าน gate 'ต้อง 1080x1920 จาก _vidout\reel_*'. เป็นดีเฟกต์คลาสเดียวกับที่ auditor เคย FAIL ไว้ 06-28 (ยังไม่ปิด gap สำหรับสาย kp/eb/tl — clean-render 07-09 ทำเป็น 1080 ให้แค่ 5 topic reels ไม่รวม batch1)

## วิธีแก้ (owner/CC — auditor อ่านอย่างเดียว)
1) เรนเดอร์ batch1 (kp/eb/tl) ใหม่ที่ 1080x1920 หรือสลับคิว YT ที่เหลือ (17=eb02, 18=kp06, 19=eb03) ไปใช้ 1080 · kp05 (ธีมออม) แทนได้ด้วย _vidout/clean/reel_save-small_clean.mp4 หรือ auto-save_clean.mp4 (1080, wm-clean) ถ้าจะลบ+อัปใหม่
2) ถ้า 720p batch1 = ทางเลือกที่ 'ยอมรับแล้ว' (คลิป footage ที่ลายน้ำเกลี้ยง) → **อัปเดต SPEC** ให้ยกเว้นสาย batch1 ไม่งั้นจะ FAIL ซ้ำทุกวัน 11-19
3) บังคับ gate 1080x1920 ใน pipeline เรนเดอร์ batch1 (รับเฉพาะ 1080x1920)

## ข้อจำกัดการ verify วันนี้
- IG/FB: Meta MCP (Pipeboard) เกินโควตา Free รายสัปดาห์ → เช็ก media สดไม่ได้ทั้งคู่ (ใช้ delivery-verify=LIVE + local batch1 scan เป็น fallback)
- Telegram: creds อยู่นอก repo (C:\Users\nL_ku\ga4-admin\telegram.env / env var) เข้าไม่ถึงจาก Cowork sandbox → notify best-effort = skipped (ไม่ส่ง). owner ควรรับทราบผ่านไฟล์นี้ + cowork-inbox
- หลักฐานเฟรม kp05 (มีฮุก+CTA+disclosure, 720p, ไม่มีลายน้ำ): automation-log/wm-evidence/kp05_20260716_t3.png, _t6.png

---
auditor run: 2026-07-16 (Cowork, read-only) · ไม่เขียน 'ok' ลง latest.md เพราะมี FAIL (720x1280) · ดีเฟกต์ = ความละเอียดต่ำกว่า SPEC (watermark สะอาด)
