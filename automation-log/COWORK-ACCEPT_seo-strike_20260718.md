# Cowork acceptance — SEO Strike (ตรวจของจริงบน live, 18 ก.ค. 2026)

ตรวจอิสระจากรายงาน CC (commit 3955714 / report e998b5b) ด้วยสคริปต์ fetch live: **17/17 PASS**

- 301: ทั้ง 2 URL .html → extensionless ถูกปลายทาง
- car-still: 200 · canonical extensionless · title ใหม่ "รถผ่อนไม่หมด จำนำได้ไหม…" · FAQPage JSON-LD · FAQ อายุรถครบ · ไม่มี [ตรวจสอบ]
- salary-30000: 200 · title "เงินเดือน 30000 วงเงินบัตรเครดิตได้เท่าไหร่? เช็กเพดานก่อนสมัคร" · เกณฑ์ 3 เท่า + hedge "ไม่ใช่วงเงินรับประกัน" · canonical · ไม่มี [ตรวจสอบ]
- sitemap: 200 · ไม่มี .html
- FIX-1 decision-different ของ CC (งานทำแล้ว 10 ก.ค. + acceptance แทนการทำซ้ำ) = ยอมรับ ถูกต้อง

แก้ข้อมูล CC 1 จุด: GSC property `https://ngernduangold.com/` **verified และใช้งานได้จริง** (gsc_pull.py ดึงข้อมูลผ่าน API จาก property นี้เมื่อ 17 ก.ค. 19:45) → เจ้าของกด Request indexing บน .com ได้เลย ไม่ต้อง verify ใหม่

จุดวัดผล: จันทร์ 20 ก.ค. (W30) เช็ก position ขยับ · 3 ส.ค. (W31) เช็กคลิกแรกจาก Google

## ภาคผนวก: ตรวจรับ CC-ORDER_gsc-request-indexing (18 ก.ค.)
- CC จบที่แผน B ตาม DoD (ข) — ไล่เส้นทาง UI ครบถ้วนโดยไม่ผิดกติกาเหล็กสักข้อ (extension `[]` / CDP ปิด / cookies ล็อก WinError 32 หยุดตามกติกา / ไม่แตะ login) = ยอมรับ
- Cowork ยืนยัน live: `<lastmod>2026-07-18</lastmod>` ปรากฏ **2 จุดพอดี** ตรง 2 URL เป้า (credit-card-salary-30000-2026, car-still-installment-loan-2026) · design self-healing ผ่าน
- งานมือคงเหลือของเจ้าของ (ทางเร่งที่เร็วกว่า): กด Request indexing 2 URL ใน GSC (~2 นาที)
- ระบบ: bridge extension ⇄ แอป Claude ยังหลุด (side panel ล็อกอินแล้ว) — ทางแก้ที่แนะ: รีสตาร์ตแอป Claude desktop 1 ครั้ง
