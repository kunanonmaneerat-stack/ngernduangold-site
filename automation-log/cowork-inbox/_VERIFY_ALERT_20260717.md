# VIDEO-POST VERIFY — ALERT 2026-07-17  (FAIL: resolution · watermark CLEAN)

โพสต์วิดีโอวันนี้ (มัลติแคสต์ธีม "ปลดหนี้ + Worksheet" = eb02) ใช้ไฟล์ **720x1280** แทนที่จะเป็นรีล **1080x1920** → SPEC FAIL (resolution).
สแกนลายน้ำ Veo = ผ่านสะอาดทุกไฟล์ (ไม่ใช่เคสลายน้ำ). เป็นดีเฟกต์คลาสเดิมกับ 16 ก.ค. (_VERIFY_ALERT_20260716) และ 28 มิ.ย.

## ตัวชี้ขาด (deterministic)
- ไฟล์ต้นทางวันนี้: `reels/2026-07-17_eb02.mp4` → ffprobe = **720x1280** (กติกา: ต้อง 1080x1920 จาก `_vidout/reel_*`) → **FAIL**
- `qa_watermark.py --fps 3` = **PASS** (frames 24, track 0/24, track_frac 0.0) → ไม่มี sparkle Veo
- เฟรม t1: มีฮุกขึ้นจอ "35 หน้า ย่อยวิธีปลดหนี้ให้ทำตามได้ / คู่มือ + Worksheet · ลิงก์ในไบโอ" + disclosure ครบในแคปชัน
  → เป็นรีลจริงมีฮุก/CTA **ไม่ใช่** clips-web, บัญชีถูก (@ngernduangold), ธีมถูก → ดีเฟกต์ที่ "ความละเอียด" อย่างเดียว
- หลักฐานเฟรม: `automation-log/wm-evidence/_audit_eb02_20260717_t1.png` (มีฮุก, 720p, ไม่มีลายน้ำ)

## รายช่อง (จาก delivery-verify 21:32 + schedule.json = ต้นทางไฟล์เดียว eb02)
| ช่อง | โพสต์ | ผล | เหตุผล |
|---|---|---|---|
| YouTube | 5-O94Kppve8 (18:00) | FAIL | ต้นทาง eb02 = 720x1280 |
| Instagram | Da5KnvVCmwx (19:00) | FAIL* | LIVE ยืนยันแล้ว; ตรวจ media ผ่าน Meta MCP ไม่ได้ (Free weekly quota); ต้นทางเดียว eb02 720p |
| Threads | Da5JNyfkrb_ (18:49) | (นอกสโคป IG/FB/YT) | ต้นทางเดียว |
| Facebook | — | UNVERIFIED | ทุกช่องทาง verify ตาย (Meta MCP quota / token code190 / Chrome ext หลุด) — ไม่ถือ miss |

*IG ยืนยัน media ตรงไม่ได้เพราะ quota แต่ต้นทาง = ไฟล์เดียวกับ YT (eb02 720p) จึง FAIL โดยอนุมาน

## สแกนทั้งชุด (ยืนยันเชิงระบบ)
- `reels/` 11-19 ก.ค. (คิว live): **9/9 = 720x1280** → FAIL เชิงระบบ
- `reels/batch2/` 20-26 ก.ค.: **7/7 = 1080x1920** ✔ (ถูกต้อง, ยังไม่โพสต์; yt_upload_log มี videoId คิวแล้ว)
- `_vidout/reel_` (7) + `_vidout/clean` (5): 1080x1920 ✔ (มาสเตอร์ถูก แต่ "ไม่ถูกใช้" กับ 11-19)
- watermark ทั้ง 16 ไฟล์ (วันนี้ + 11-19 + batch2): PASS หมด, exit 0, sparkle 0

## รากเหตุ
คิว `reels/` (11-19 ก.ค.) ถูกสร้างจากคลิป staging `_social-stage/_final_*` ที่เป็น 720x1280 แทนมาสเตอร์ 1080x1920.
`batch2` (ตั้งแต่ 20 ก.ค.) เรนเดอร์ 1080 ถูกแล้ว → ช่องโหว่ปิดเองวันที่ 20 ก.ค. แต่ **17-19 ก.ค. ยังจะโพสต์ 720p ถ้าไม่แก้**.

## วิธีแก้ (เจ้าของ)
1. วันนี้ (17) โพสต์ไปแล้ว → เลือก: (ก) ลบ + อัปใหม่ด้วยรีล 1080 ของ eb02, หรือ (ข) ยอมรับ 720p วันนี้ แล้วสลับ 18 (kp06) + 19 (eb03) เป็น 1080 ก่อนเวลาโพสต์
2. หมายเหตุสำคัญ: ยังไม่มีมาสเตอร์ 1080 ที่ตรงฮุก eb02 ("คู่มือ + Worksheet ปลดหนี้") ใน `_vidout/reel_` หรือ `_vidout/clean` → ต้อง **เรนเดอร์ eb02 / kp06 / eb03 ใหม่ที่ 1080x1920** (ห้ามเอา clip plain มาแทน). ถ้าจะสลับธีม ใช้ `batch2/20_debt-health-check` (1080, ธีมหนี้) ได้แต่เปลี่ยนครีเอทีฟ
3. ตั้งแต่ 20 ก.ค. `batch2` = 1080 อยู่แล้ว ไม่ต้องแก้
4. ป้องกันถาวร: บังคับ pre-publish gate (ffprobe = 1080x1920) ที่ตัวสร้างคิว `reels/` ให้ดึงจาก `_vidout/` ไม่ใช่ `_social-stage/_final_`

## Notify
- Telegram: **ข้ามส่ง** — creds อยู่นอก repo (`C:\Users\nL_ku\ga4-admin\telegram.env` ไม่ mount, ไม่มี env var) เหมือน 16 ก.ค.
- วางสำเนาไฟล์นี้ที่ `automation-log/cowork-inbox/` แล้ว

---
ตรวจโดย ngernduangold-video-post-verify (Cowork) · 2026-07-17 · READ-ONLY (ไม่โพสต์/ลบ/แก้คลิปใดๆ)
