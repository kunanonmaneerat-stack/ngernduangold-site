# VIDEO-POST VERIFY ALERT — 2026-07-19  🔴 FAIL (resolution) · watermark CLEAN 30/30

**ผลตรวจ:** FAIL — คลิปวันนี้ (eb03) ใช้ไฟล์ต้นทาง **720x1280** (สเปกบังคับ 1080x1920 จาก `_vidout\reel_*`). ลายน้ำ Veo = สะอาดทั้ง 30/30 ไฟล์ (exit 0) — **ไม่ใช่ปัญหาลายน้ำ ไม่ต้อง BLOCK**.
เป็น defect ชุดเดียวกับ _VERIFY_ALERT_20260716 / 20260717 / 20260718 = **วันที่ 4 ติดต่อกัน และเป็นวันสุดท้ายของช่องโหว่ 720p** (คิว 11–19 ก.ค.) — ช่องโหว่ปิดเอง 20 ก.ค.

## ตัวชี้ขาด (deterministic)
- content_manifest 2026-07-19 → id `2026-07-19_eb03` · reel = `reels/2026-07-19_eb03.mp4`
- `ffprobe reels/2026-07-19_eb03.mp4` = **720x1280** (24fps, 8.0s) → SPEC FAIL (ต้อง 1080x1920)
- `automation-log/_social-stage/_final_eb03.mp4` (ต้นทาง staging) = **720x1280** เช่นกัน → ต้นทางเองก็ 720p ไม่ใช่ downscale ตอนโพสต์
- เฟรม t=1s = **รีลจริงมีฮุกขึ้นจอ** "คู่มือ + Worksheet ปลดหนี้ / ทำตามได้ทีละขั้น" · ไม่มี Veo sparkle · **ไม่ใช่ clips-web plain** → defect = ความละเอียดอย่างเดียว

## สรุปต่อช่อง (ธีมวันนี้ = โปรโมตคู่มือปลดหนี้, slug eb03)
| ช่อง | โพสต์/ไอดี | ผล | เหตุผล |
|---|---|---|---|
| YouTube | Short `z2bI43D9B7s` (publish ~18:00–18:30 ICT 19 ก.ค.) | **FAIL** | ต้นทาง eb03 = 720x1280 · **ไม่อยู่ใน yt_upload_log.json** (มีเฉพาะ batch2 20–26 ก.ค. 1080) |
| Instagram | manifest scheduled-ui 19:00 (business-suite-batch1) | **FAIL (by source)** | ต้นทาง 720x1280 · live **UNVERIFIED** (Pipeboard Free weekly-limit หมดโควตา) |
| Facebook | manifest scheduled-ui 19:00 (business-suite-batch1) | **FAIL (by source)** | ต้นทาง 720x1280 · live **UNVERIFIED** (weekly-limit / native token code190) |
| Threads | ไม่มีโพสต์วิดีโอวันนี้ (kn-01 = text) | n/a | heartbeat 21:15 ยืนยัน no reel post today |
| TikTok | บัญชี suspended | n/a | ไม่มีโพสต์ที่คาดหวัง |

## 🔴 Watermark frame-scan (ข้อ 3 บังคับ) — **PASS 30/30 · exit 0 · ไม่มี Veo sparkle**
| ชุด | ไฟล์ | ผล |
|---|---|---|
| คลิปวันนี้ | `reels/2026-07-19_eb03.mp4` | PASS 0/24 |
| คลิปวันนี้ (staging) | `_social-stage/_final_eb03.mp4` | PASS 0/24 |
| `_vidout/clean/` | 5/5 (auto-save · compound-interest · emergency-fund · save-small · title-loan) | PASS 0/60 ทุกไฟล์ |
| `_social-stage/_final_*` | 16/16 (dc01-05 · sp01-02 · eb02-03 · kp04-06 · tl01b/03/04/05) | PASS 0/24–30 ทุกไฟล์ |
| `reels/batch2/` (20–26 ก.ค. ตั้งคิว YT แล้ว) | 7/7 | PASS 0/30 ทุกไฟล์ |
| `reels/` batch3 b3-01..07 (27 ก.ค.–2 ส.ค.) | 7/7 | PASS 0/61–74 ทุกไฟล์ |

คำสั่งที่รัน: `py tiktok-pipeline\src\qa_watermark.py <files> --fps 3 --evidence-dir automation-log\wm-evidence`
หลักฐานเฟรม: `automation-log\wm-evidence\_audit_eb03_20260719_t1.png` (720x1280 มีฮุก ไม่มีลายน้ำ) + `_audit_eb03_20260719_t5.png`

## กติกา source (ข้อ 3)
`_final_eb03.mp4` อยู่ใน `_social-stage\` = **ผ่านกติกา source dir** (ไม่ได้ใช้ `media\clips\*-2026.mp4` ดิบ) — แต่ตกเกณฑ์ความละเอียด

## Root cause (ยืนยันด้วย ffprobe ตรงรอบนี้)
- `reels/` คิว 11–19 ก.ค. = **9/9 ไฟล์ 720x1280** (systematic ทั้งชุด)
- `reels/batch2/` 20–26 ก.ค. = **7/7 ไฟล์ 1080x1920** · YT ตั้งคิวผ่าน API ครบ (Idt4Zby8JKU … wr4pG3HrE1I)
- `reels/` batch3 27 ก.ค.–2 ส.ค. = **7/7 ไฟล์ 1080x1920**
→ **ช่องโหว่ 720p ปิดเองตั้งแต่ 20 ก.ค. — วันนี้คือวันสุดท้ายที่เสีย**

## วิธีแก้ (เจ้าของเลือก)
1. **ไม่ทำอะไร (แนะนำ)** — เหลือวันเดียว ช่องโหว่ปิดเองพรุ่งนี้ · ต้นทุนการลบ+อัปใหม่ > ประโยชน์ (คลิปโปรโมตตัวนี้ reach ต่ำอยู่แล้ว)
2. ถ้าต้องการความสมบูรณ์: เรนเดอร์ eb03 ใหม่ที่ 1080x1920 → ลบ Short `z2bI43D9B7s` + โพสต์ IG/FB → อัปใหม่
3. **ไม่มี 1080 master ธีมตรงให้สลับ** — `_vidout\clean\*` ทั้ง 5 เป็นธีมออม/หนี้ ไม่ตรงฮุก eb03 (ต่างจากเคส kp06 เมื่อวานที่มีตัวแทนตรงธีม)

## ข้อสังเกตเพิ่ม (นอกขอบสเปก แต่เป็นคลิปเดียวกัน)
- แคปชัน YouTube ของ eb03 เขียนว่า "ลิงก์ในไบโอ" — YouTube ไม่มีไบโอ · บรรเทาด้วย pinned comment 21:28 (มีลิงก์) → ควรแก้ template ให้ใส่ URL ตรงใน description
- **anti-duplicate-promo (กฎใหม่ 19 ก.ค.):** eb02 (17 ก.ค.) + eb03 (19 ก.ค.) = คลิปโปรโมตสินค้าตัวเอง 2 ตัวใน 3 วัน → เกินเพดาน "≤ 1 ครั้ง/2 สัปดาห์/ช่อง" (eb03 ตั้งคิวไว้ก่อนกฎถูกเขียน) · batch2 20–26 ไม่มีคลิปโปรโมต = ปัญหาหายเอง

## Telegram
ข้ามการแจ้ง — creds `C:\Users\nL_ku\ga4-admin\telegram.env` ไม่ได้ mount ใน sandbox (ไม่มี TELEGRAM_BOT_TOKEN env) เหมือนรอบ 07-16/17/18 · เจ้าของ: วาง telegram.env ให้เข้าถึงได้ถ้าต้องการแจ้งอัตโนมัติ

_ตรวจโดย ngernduangold-video-post-verify (Cowork) · 2026-07-19T21:52+07:00 · READ-ONLY ไม่มีการโพสต์/ลบ/แก้_
