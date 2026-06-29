# ⚠️ VIDEO-POST VERIFY FAIL — 2026-06-28 (auditor: Cowork ngernduangold-video-post-verify)

ผล: **FAIL** — ไพป์ไลน์วิดีโอที่ "สเตจ + ตั้งคิว" สำหรับเปิดตัว e-book วันนี้ และคลิปสัปดาห์นี้ เป็น **ไฟล์ผิดเวอร์ชัน (720x1280)** ไม่ใช่ reel มาสเตอร์ที่ถูก (1080x1920 ใน `_vidout\reel_*`) — ดีเฟกต์เดียวกับ 2026-06-27 ที่ยังไม่ได้แก้
หมายเหตุสำคัญ (ไม่ตีโพยตีพาย): **ยังไม่มีวิดีโอผิดขึ้นไลฟ์จริงวันนี้** เพราะ IG/TikTok auto-post วันนี้ = BLOCKED 0/8 (รอ owner: token + fact-check). FAIL นี้คือ "ดักที่ต้นทาง/คิว" ก่อนของผิดจะออก = ตรงตามเจตนา SPEC

ตรวจชี้ขาดด้วย ffprobe (อ่านอย่างเดียว ไม่แตะไฟล์จริง/ไม่โพสต์/ไม่ลบ)

## สรุปต่อช่อง/โพสต์ (วันนี้ 28 มิ.ย.)
| ช่อง | สิ่งที่วางแผนวันนี้/สัปดาห์นี้ | ไฟล์ต้นทาง | ความละเอียด | สถานะจริง | ผล |
|------|------------------------------|-----------|-------------|-----------|-----|
| Instagram | L=ebook โพสต์ทันที + dc01-05/sp01-02 ตั้งคิว 29มิ.ย.-5ก.ค. | `_social-stage\_final_*` | dc/sp=720x1280 ; ebook=1080x1920 | 0/8 BLOCKED (ยังไม่โพสต์) | ❌ FAIL (ไฟล์ผิด 7/8 รออยู่ในคิว) |
| TikTok | dc01-05/sp01-02 ตั้งคิว 29มิ.ย.-5ก.ค. | `_social-stage\_final_*` | 720x1280 | 0/8 BLOCKED (ยังไม่โพสต์) | ❌ FAIL (ไฟล์ผิดรอคิว) |
| Facebook | ไม่มีวิดีโอใหม่วันนี้ (ล่าสุด 06-27 ตาม heartbeat) | - | - | Meta MCP เช็กสดไม่ได้ | ⚠️ UNVERIFIED |
| YouTube | POST-PACK อ้าง "ตั้ง 7 Shorts แล้ว 29มิ.ย.-5ก.ค. 18:00" (dc/sp) | คาดว่า `_social-stage\_final_*` | 720x1280 (ไฟล์สเตจ) | ไม่มีใน post-ledger.jsonl (0 entry 06-28) | ❌ FAIL-risk / UNVERIFIED |
| (carry-over 06-27) | YT M2TyHVnWkKU + TikTok debt-consolidate | `video-out\...\01.mp4` | 720x1280 | ไลฟ์อยู่ ยังไม่แก้ | ❌ ยังค้าง |

## หลักฐานชี้ขาด (ffprobe width x height)
- ❌ `_social-stage\_final_dc01.mp4`..`_final_dc05.mp4` = 720x1280 (5 ไฟล์)
- ❌ `_social-stage\_final_sp01.mp4`..`_final_sp02.mp4` = 720x1280 (2 ไฟล์)
- ✅ `_social-stage\ebook-promo-9x16.mp4` = 1080x1920 (ตัวเดียวที่ถูกความละเอียด)
- ✅ `_vidout\reel_*.mp4` (7 มาสเตอร์: credit-bureau-check, debt-consolidation, emergency-fund, first-credit-card-student, refinance-home, salary-budgeting, title-loan) = 1080x1920 ครบ — **แต่ไม่ถูกใช้** กับชุด dc/sp สัปดาห์นี้
- ref: `media\clips-web\*.mp4` = 720x1280 (ตัว plain known-bad)
- ข้อสังเกต: POST-PACK ระบุว่าคลิปสเตจ "ลายน้ำ Flow เกลี้ยง + มีข้อความบนจอตรงสคริปต์" = มีฮุก (ดีกว่าคลิปดิบ) แต่ **720x1280 = hard FAIL ตามกฎความละเอียดของ SPEC** และไม่ใช่มาสเตอร์ `_vidout\reel_*` 1080x1920

## เหตุ (root cause)
ไพป์ไลน์ auto-post รายสัปดาห์เรนเดอร์/สำเนา "final" ลง `_social-stage\` เป็น 720x1280 (ยกเว้น ebook-promo) — ไม่ผ่าน gate "ต้องเป็น 1080x1920 จาก `_vidout\reel_*`" ซ้ำรอย 06-27

## วิธีแก้ (auditor อ่านอย่างเดียว — Non/CC ทำต่อ)
1) **ห้ามโพสต์/ตั้งคิว** `_social-stage\_final_dc01-05` และ `_final_sp01-02` (720x1280). เรนเดอร์ใหม่ที่ 1080x1920 หรือใช้มาสเตอร์ `_vidout\reel_*` (มีครบ 7 ตัว 1080x1920) แทน ก่อนปล่อย IG/TikTok/YT
2) **YouTube**: เปิด Studio ยืนยัน 7 Shorts ที่อ้างว่าตั้งคิว (29มิ.ย.-5ก.ค.) — ถ้ามาจากไฟล์ 720 ให้ลบ+อัปใหม่จาก `_vidout\reel_*` (1080x1920). ทั้งหมดไม่มีใน post-ledger.jsonl → ต้อง log ด้วย
3) **ebook-promo-9x16.mp4** (1080x1920) ความละเอียดผ่าน — ใช้เปิดตัว e-book ได้ แต่ยืนยันฮุก/CTA/disclosure บนเฟรมก่อน
4) **carry-over 06-27** ยังค้าง: แทนที่ YT M2TyHVnWkKU + TikTok debt ด้วย `_vidout\reel_*` ตาม `_VERIFY_ALERT_20260627.md`
5) **กันรากเหง้า**: บังคับ gate ในไพป์ไลน์รายสัปดาห์ (รับเฉพาะ 1080x1920 + path `_vidout\reel_*`) และเพิ่ม `_social-stage\` (ไฟล์ 720) เข้า blacklist เดียวกับ `media\clips-web` + `video-out`

## ข้อจำกัดการ verify วันนี้
- IG/FB: Meta MCP (Pipeboard) ถึงลิมิตรายสัปดาห์แผนฟรี → เช็กสดไม่ได้ = UNVERIFIED (ใช้ ledger+log ตาม fallback ของ SPEC)
- YouTube: ไม่มี API ใน Cowork → ใช้ ledger (post-ledger.jsonl ไม่มี entry 06-28) + POST-PACK (อ้างตั้งคิวแล้ว แต่ยืนยันไม่ได้)

---
auditor run: 2026-06-28 (Cowork, read-only) · ไม่เขียน "ok" ลง latest.md เพราะมี FAIL · ดีเฟกต์ = ไฟล์วิดีโอ 720x1280 ในคิว (ต้องเป็น 1080x1920 จาก _vidout\reel_*)
