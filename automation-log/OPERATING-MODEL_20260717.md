# Operating Model — เช็ค 8 ช่องทาง + แบ่งงานใหม่ (17 ก.ค. 2026)

## สถานะ 8 ช่องทาง (ตรวจจริง 00:40 ICT)

| # | ช่องทาง | สถานะ | หมายเหตุ |
|---|---------|--------|----------|
| 1 | TikTok | ✅ ตั้งเวลาถึง 26 ก.ค. (19:00 ทุกวัน) | ยอดต่ำสุด — batch3 ต้องมี voiceover ตาม directive |
| 2 | YouTube | ✅ 13–26 ครบ · 20–25 ชื่อ search-first ใหม่ · 26 อัปอัตโนมัติ 15:10 วันนี้ | ช่องแข็งสุด — โฟกัสหลัก |
| 3 | Facebook Page | ✅ ตั้งเวลาถึง 26 ก.ค. (Business Suite) | guard ยังอ่านสถานะ FB ไม่เห็น (งานปรับ guard คิว Codex) |
| 4 | Instagram | ✅ ตั้งเวลาถึง 26 ก.ค. | ผู้ติดตามน้อย — โตตาม content ใหม่ |
| 5 | Threads | ✅ zero-touch tasks 17–26 พร้อม | ตัวแรกรันคืนนี้ 19:00 (อาจถามอนุมัติ tool ครั้งแรก) |
| 6 | เว็บไซต์ | ✅ ทุกหน้า 200 (/, /links, /debt-calculator, /debt-health-check, /kept-savings-2026, sitemap) | จุดอ่อนใหญ่สุด: Organic Search 2 sessions/28วัน |
| 7 | LINE OA (@804qodya) | ⚠️ ไม่มี automation — เช็คจากระบบไม่ได้ | **ด่วน: คลิป 22 (22 ก.ค.) สั่งคนพิมพ์ "ขอจดหมาย" — ต้องเตรียมข้อความตอบ+ไฟล์ตัวอย่างจดหมายก่อน 22 ก.ค.** |
| 8 | Pantip | 🟢 ปลด freeze 17 ก.ค. (คำสั่งเจ้าของ) | เฟส 1 ถึง 30 ก.ค.: ตอบกระทู้คนอื่น value-only ไร้แบรนด์/ลิงก์/ราคา ≤3/สัปดาห์ · **เจ้าของโพสต์มือเท่านั้น ห้าม auto-post** (post-final-warning) · draft แรกพร้อม: `automation-log/_pantip_LIVE-opportunity_debt-cashflow-loop_20260716.md` → กระทู้ 44163092 |

## แบ่งงานใหม่ (มีผลทันที)

### ระบบอัตโนมัติ (0 มือ — ไม่ต้องมีใครแตะ)
- โพสต์ 5 ช่องโซเชียล 17–26 ก.ค. 19:00 (TikTok/FB/IG = scheduled ในแพลตฟอร์ม · Threads = zero-touch task · YT 26 = auto-upload 15:10)
- ยามตรวจโพสต์ทุกวัน 19:27 (post_guard) → รายงาน FAIL เท่านั้นที่ต้องดู

### Cowork (Claude) — งาน UI/ตรวจสอบที่สคริปต์ทำไม่ได้
- เฝ้า first-run Threads 17 ก.ค. คืนนี้ + แก้หน้างานถ้าติด
- W30 analytics วันจันทร์ 20 ก.ค. (YT Studio + GA4 + TikTok) → วัดผลชื่อ search-first
- ดึง GSC striking-distance queries (ครั้งเดียว) → ส่งเป็น spec ให้ Codex

### Codex (gpt-5.6-terra) — งานไฟล์/สคริปต์ทั้งหมด (โควตา: reset แล้ว + reset ได้อีก 1)
- คิวถัดไป #1: SEO content sprint — เขียน/อัปเกรดหน้าเว็บจาก GSC striking-distance (แก้จุดอ่อน Organic Search 2/28วัน)
- คิวถัดไป #2 (เล็ก): ปรับ post_guard ให้อ่าน manifest posted field → ตัด UNKNOWN ของ FB/IG
- กติกาเดิม: spec file UTF-8 · ห้าม push/add -A · แตะเฉพาะไฟล์ที่สั่ง

### เจ้าของ (Non) — สิ่งที่ automation ทำแทนไม่ได้
0. **Pantip (โพสต์มือเท่านั้น — post-final-warning)**: คำตอบแรกร่างพร้อมแล้วใน `automation-log/_pantip_LIVE-opportunity_debt-cashflow-loop_20260716.md` → copy ไปตอบกระทู้ pantip.com/topic/44163092 · จากนั้น Cowork จะป้อน draft ใหม่ให้ ≤3 อัน/สัปดาห์
1. **ก่อน 22 ก.ค.**: เตรียมชุดตอบ LINE "ขอจดหมาย" (ข้อความ + ไฟล์ตัวอย่างจดหมายลดดอกเบี้ย)
2. **ก่อน 27 ก.ค.**: ผลิตคลิป batch3 ตาม automation-log/CONTENT-DIRECTIVE_batch3.md — หัวใจ: มีเสียงพูดจริงทุกคลิป
3. **ทุกวัน ~19:30 (10 นาที)**: ตอบคอมเมนต์/DM ทุกช่อง — engagement ช่วงชั่วโมงแรกดันการกระจายแรงสุด
4. LINE broadcast 1 ครั้ง/สัปดาห์ (แนะนำศุกร์เย็น) ชวนเข้า /links

## จุดวัดผล
- จันทร์ 20 ก.ค.: W30 measure (Cowork)
- จันทร์ 3 ส.ค.: เกณฑ์ batch3 — TikTok ≥50 วิว/คลิป/48ชม. · YT Shorts ใหม่ ≥100 วิว/7วัน · ไม่ผ่าน → ลด TikTok เหลือ 3 คลิป/สัปดาห์ เทแรงให้ YouTube+เว็บ
