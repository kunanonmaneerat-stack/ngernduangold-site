# VIDEO-POST VERIFY — 2026-07-10 · ผล: PARTIAL (2 PASS · 1 ต้อง eyeball · FB=ไม่มีวิดีโอ)
รันโดย Cowork auditor (read-only) · เกณฑ์ตัดสินหลัก = qa_watermark frame-scan (fps=3) + ffprobe resolution + SPEC discriminator

## สรุปเร็ว
- ❗ ไม่พบไฟล์ผิด/720p/ลายน้ำ ✦ ที่ยืนยันได้ในโพสต์วันนี้ — และไม่ pass IG ทั้งหมด
- ✅ YouTube (credit-bureau) = PASS · ✅ TikTok (title-loan) = PASS · ⚠️ Instagram (title-loan) = ต้อง eyeball 1 ครั้ง · ➖ Facebook = โพสต์ลิงก์ /debt-calculator ไม่ใช่วิดีโอ

## รายช่อง
### ✅ YouTube — credit-bureau (คิว 18:00, delivery-verify ยืนยัน LIVE วันนี้)
- source = `_vidout/reel_credit-bureau-check-2026.mp4` (reel เก่า ตาม launch-status queue: 6-10 ก.ค.=reel ต้นฉบับ)
- ffprobe = **1080x1920** ✓ · qa_watermark = **PASS 0/30 เฟรม** (สแกนสด 10 ก.ค.) ✓
- ไม่ใช่ media/clips-web และไม่ใช่ 720x1280 → ผ่าน SPEC discriminator

### ✅ TikTok — title-loan (09:01, URL ยืนยัน /video/7653075156079742226) [นอกขอบเขต IG/FB/YT แต่เป็นวิดีโอวันนี้]
- source = `_vidout/clean/reel_title-loan-2026_clean.mp4` (จาก gated dir _vidout/clean)
- ffprobe = **1080x1920** ✓ · qa_watermark = **PASS 0/60 เฟรม** (สแกนสด) ✓

### ⚠️ Instagram — title-loan Reel (เช้า; tracker=โพสต์แล้ว "แชร์แล้ว"; delivery-verify=IG LIVE วันนี้)
- source ที่ tracker ระบุ = `reel_title-loan_footage.mp4` ("Cowork footage reel", เลือก FOOTAGE)
- **ไฟล์นี้ไม่อยู่ใน workspace ที่ mount** → frame-scan ไม่ได้ (auditor เข้าไม่ถึง Downloads/เครื่อง owner)
- Meta MCP (Pipeboard) = เกินโควตา Free รายสัปดาห์ (ยืนยันสด IG media ไม่ได้ทั้ง IG+FB)
- footage reel นี้ไม่ได้มาจาก gated dir (_vidout/clean หรือ _social-stage/_final_) → status ลายน้ำ "ยืนยันไม่ได้"
- ไม่ใช่ FAIL ที่ยืนยัน (detector ไม่ได้จับลายน้ำ — แค่รันกับไฟล์ไม่ได้) แต่ก็ไม่ใช่ PASS สะอาด

## สิ่งที่ owner ต้องทำ (IG เท่านั้น — 1 ครั้ง)
1. เปิด Reel title-loan ที่โพสต์วันนี้ในแอป IG (@ngernduangold) → ดู "มุมขวาล่าง" ทั้งคลิป หา ✦ sparkle (Veo watermark) ที่โซน x~79-87% y~88-93%
2. ถ้าเห็น ✦ → ลบ Reel แล้วโพสต์ใหม่ด้วย `_vidout/clean/reel_title-loan-2026_clean.mp4` (kinetic, qa_watermark PASS 0/60, 1080x1920)
3. ถ้าสะอาด → ไม่ต้องทำอะไร (แค่บันทึกว่าเคลียร์)
(รูปแบบเดียวกับ CONDITIONAL KEEP ของ DaBD2iIPWfl ใน watermark-fix-report_20260709)

## หมายเหตุระบบ (สาเหตุ gap คราวนี้)
- reel ต้นฉบับ 7 ตัว + clean 5 + _final 16 = สแกน 07-09 ผ่านหมด (mtime ไม่เปลี่ยน) → today's YT/TikTok source ยืนยันสะอาด
- gap เดียว = ตระกูล "footage reel" (มีคน/footage จริง) ที่ประกอบนอก dir ที่ auditor เห็น → ควร stage ลง `_vidout/clean` หรือ `_social-stage/_final_*` ก่อนโพสต์ทุกครั้ง เพื่อให้ frame-scan อัตโนมัติจับได้ (ปิด gap ถาวร)
- Meta MCP โควตาหมด → รอ reset สัปดาห์หน้า หรือใช้ on-platform eyeball แทน
