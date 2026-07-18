# VIDEO-POST VERIFY ALERT — 2026-07-18  🔴 FAIL (resolution) · watermark CLEAN

**ผลตรวจ:** FAIL — วิดีโอที่โพสต์วันนี้ใช้ไฟล์ต้นทาง **720x1280** (ต้องเป็น 1080x1920 จาก `_vidout\reel_*`). ลายน้ำ Veo = สะอาด (ไม่ใช่ปัญหาลายน้ำ). เป็น defect ชุดเดียวกับ _VERIFY_ALERT_20260716 / 20260717 (วันที่ 3 ติดต่อกันของช่องโหว่ 720p ในคิว 11–19 ก.ค.).

## ตัวชี้ขาด (deterministic)
- content_manifest 2026-07-18 → reel = `reels/2026-07-18_kp06.mp4`
- `ffprobe reels/2026-07-18_kp06.mp4` = **720x1280**  → SPEC FAIL (ต้อง 1080x1920)
- เฟรม t=1s = รีลจริงมีฮุกขึ้นจอ “ออมทีละนิด ทุกวันเงินเดือนออก / วินัยเล็ก ๆ ที่เปลี่ยนชีวิต” (ธีมโหลออม) บัญชี @ngernduangold ถูกต้อง แคปชันมีลิงก์+disclosure ครบ → เป็นรีลจริง ไม่ใช่ clips-web plain → **defect = ความละเอียดอย่างเดียว**

## สรุปต่อช่อง (ธีมวันนี้ = ออม/auto-save multicast, slug kp06)
| ช่อง | โพสต์/ไอดี | ผล | เหตุผล |
|---|---|---|---|
| YouTube | Short `Fbk2A10zvqg` (publish 2026-07-18) | FAIL | ต้นทาง kp06 = 720x1280 · ไม่อยู่ใน batch2 1080 log (yt_upload_log 20–26 เท่านั้น) |
| Threads | video 19:33 (แคปชัน kp06 ตรงเป๊ะ) | FAIL | ต้นทาง kp06 = 720x1280 (ยืนยันจากแคปชันตรงกับ schedule.json) |
| Instagram | manifest scheduled-ui 19:00 (kp06) | FAIL(by source) | ต้นทาง 720x1280 · live UNVERIFIED (Meta MCP Pipeboard Free weekly-limit) |
| Facebook | manifest scheduled-ui 19:00 (kp06) | FAIL(by source) | ต้นทาง 720x1280 · live UNVERIFIED (Meta MCP weekly-limit / fb token code190) |

## Watermark frame-scan (บังคับ ข้อ 3) — PASS ทุกไฟล์ exit 0
- `reels/2026-07-18_kp06.mp4` → PASS 0/24
- `automation-log/_social-stage/_final_kp06.mp4` → PASS 0/24
- `_vidout/clean/reel_save-small-2026_clean.mp4` → PASS 0/60
- `_vidout/clean/reel_auto-save-2026_clean.mp4` → PASS 0/60
- `_vidout/clean/reel_emergency-fund-2026_clean.mp4` → PASS 0/60
- `_vidout/clean/reel_compound-interest-2026_clean.mp4` → PASS 0/60
- `_vidout/clean/reel_title-loan-2026_clean.mp4` → PASS 0/60
- ไม่มี Veo sparkle ในทุกไฟล์ · หลักฐานเฟรม: `automation-log/wm-evidence/_audit_kp06_20260718_t1.png` (720x1280, มีฮุก)

## Root cause
- `reels/` คิว 11–19 ก.ค. = 9/9 ไฟล์ 720x1280 ทั้งชุด (systematic) — ยืนยันด้วย ffprobe ตรง
- batch2 20–26 ก.ค. = 7/7 ไฟล์ 1080x1920 (fix ลงแล้ว, ช่องโหว่ปิดเอง 20 ก.ค.)
- 1080 master มีอยู่แต่ไม่ถูกใช้กับคิว 11–19: `_vidout/reel_*` (7) + `_vidout/clean/*_clean.mp4` (5)

## วิธีแก้ (เลือกทางใดทางหนึ่ง แล้วลบโพสต์เดิม + อัปใหม่)
1. เรนเดอร์ kp06 ใหม่ที่ 1080x1920, หรือ
2. **สลับไปใช้ 1080 clean reel ที่ธีมตรงกัน (มีอยู่แล้ว wm-clean):**
   - `_vidout/clean/reel_save-small-2026_clean.mp4` (โหลออม = ตรงฮุก kp06 ที่สุด), หรือ
   - `_vidout/clean/reel_auto-save-2026_clean.mp4`
   (ต่างจากเคส eb02 เมื่อ 17 ก.ค. ที่ไม่มี 1080 master ตรงฮุก — เคส kp06 นี้มี substitute 1080 ตรงธีม ใช้ได้เลย ตามโน้ต _VERIFY_ALERT_20260716)
3. ถ้าโพสต์วันนี้แก้ไม่ทัน: ปล่อยให้ช่องโหว่ปิดเองวันที่ 20 ก.ค. (batch2 1080) และเร่งอุด 18–19 ก.ค.

## Telegram
ข้ามการแจ้ง — creds `ga4-admin/telegram.env` ไม่ได้ mount ใน sandbox (ไม่มี bot token env) เหมือนรอบ 07-16/07-17. เจ้าของ: วาง telegram.env ให้เข้าถึงได้ถ้าต้องการแจ้งอัตโนมัติ.

_ตรวจโดย ngernduangold-video-post-verify (Cowork) · 2026-07-18T21:40:30+07:00 · READ-ONLY ไม่มีการโพสต์/ลบ/แก้_
