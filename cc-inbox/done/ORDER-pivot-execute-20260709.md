# ORDER — Execute debt-wedge pivot (reposition + funnel-fix + SEO) · 9 ก.ค. 2026
Re-stage ของ order-pivot-debt-wedge + order-funnel-fix (บันทึกว่าวางแล้วแต่หายจาก inbox)
**ทำแบบ idempotent: เช็คสถานะปัจจุบันก่อน ถ้าทำไปแล้วให้ข้าม อย่าทำซ้ำ**
อ้างอิงสเปกเต็ม: `outputs/FABLE5-STRATEGY_20260709.md` + `outputs/GEMINI-GROWTH-ADVICE_20260709.md`

## A. Reposition แบรนด์เป็น wedge "ปลดหนี้ด้วยตัวเลขจริง"
1. Homepage hero + `<title>`/meta description: เพิ่ม positioning "ปลดหนี้ด้วยตัวเลขจริง ไม่ขายฝัน" (ยังคงชื่อแบรนด์ เงินเดือนสมองทอง)
2. /about + og-default: sync tagline เดียวกัน
3. อย่าลบหน้า cluster อื่น (ประกัน/บัตร) — แค่ลดน้ำหนักใน nav/หน้าแรก ให้ธีมหนี้/รีไฟแนนซ์เด่นสุด

## B. Funnel-fix (Gemini: มี 71 คลิก 0 ขาย = รอยรั่ว)
1. `/links`: ลดทางเลือกที่ทำให้งง — แยก **e-book 59฿ เป็น primary CTA เด่นชัดบนสุด** ออกจากรายการ affiliate (affiliate อยู่ถัดลงไปเป็นหมวด)
2. หน้าขาย e-book: เพิ่ม **social proof** (เช่น "อัปเดต ก.ค. 69" / จำนวนหน้า / worksheet ที่ได้) + **ตัวอย่างเนื้อหาด้านใน** (สารบัญ/ภาพ 1-2 หน้า) ให้เห็นคุณค่าก่อนซื้อ
3. คงปุ่ม 59฿ → Gumroad เดิม · ห้ามแตะราคา/ดอกเบี้ยการันตี

## C. SEO (ส่วนที่ CC ทำได้)
1. เพิ่ม internal link จากบทความ traffic ดีสุด → หน้า cluster หนี้/รีไฟแนนซ์ + หน้า /debt-calculator (เมื่อ deploy)
2. ยก priority ใน sitemap.xml ให้ 3 หน้าหนี้ที่ดีสุด
3. (เจ้าของ: กด GSC Request-Indexing 3 หน้านี้รายตัว — CC ทำแทนไม่ได้)

## ข้อจำกัด
- build_site.py แตะเมื่อไหร่ = commit/push **แยกท้ายสุด** (Netlify ignore rule)
- ห้ามตัวเลข/การันตีดอกเบี้ย · disclosure + affiliate disclosure ครบทุกหน้า
- media gitignored · commit เฉพาะหน้าเว็บ+report+order
