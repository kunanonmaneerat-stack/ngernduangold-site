# ORDER → CC — Revenue Sprint 7 วัน (2-8 ก.ค.) · 2026-07-02
จาก: Cowork ตาม OWNER-MANDATE_20260702 · ที่มา: consult-gemini-3.5ext-revenue-20260702.md + GA4 จริง
หลักการ: reach คือคอขวด → ดัน traffic เข้า 2 หน้าที่พิสูจน์แล้ว (/kept-savings-2026 conv 93% · /title-loan-2026 conv 71% ค่าคอม 2,100฿/เคส) + ขาย e-book แบบ contextual

## P1 — โค้ด /links + หน้าแปลงสูง (build_site.py) 🔴 ทำก่อน
1. **/links: ยกการ์ด 2 ใบขึ้นบนสุด** (ใต้การ์ด e-book): "🏦 ออมดอกสูง Kept" + "💸 จำนำทะเบียนรถ" — ใช้ลิงก์ affiliate เดิม ห้ามแตะ utm/rel เดิม
2. **แบนเนอร์ e-book ตัวเล็กท้ายหน้า** /kept-savings-2026 + ทุกหน้ากลุ่มหนี้ (debt-consolidation, pay-off-credit-card, title-loan) ข้อความแนว "จัดการหนี้เป็นระบบ → คู่มือ+Worksheet 59฿" ลิงก์ Gumroad ตรง
3. **Quiz result: เพิ่มข้อเสนอ e-book หลังแสดงผลลัพธ์** (ทุก path ของผล quiz)
4. รัน build → verify: GA4 snippet ครบ, affiliate class/rel=sponsored เดิมครบ, canonical/OG ไม่หาย → commit+push → **แจ้งเจ้าของกด deploy**

## P2 — คอนเทนต์คิว 7 วัน (pipeline/Hermes dispatch)
5. ปรับ trend/script ของ pipeline สัปดาห์นี้ให้ **โฟกัสเฉพาะ 2 ธีม**: จำนำทะเบียน (pain: มีรถ หมุนเงินไม่ทัน อยากปิดหนี้บัตร) + Kept ออมดอกสูง — งดธีมแมสทั่วไปตาม avoid ของ consult
6. คิว FB + Threads รายวัน (ช่อง conv ดีสุด): ใช้ 4 กราฟิกใน ig-fb-post-pack.md ที่ค้างอยู่ + text tips สั้นจาก pipeline — FB ลิงก์หน้าปลายทางตรงในคอมเมนต์แรก
7. คลิปที่มีอยู่แล้วใน outputs เดิม (reel_title-loan-2026.mp4, reel_kept/emergency ฯลฯ) จัดเข้า _social-stage + POST-PACK ใหม่สำหรับสัปดาห์ 6-12 ก.ค. (YT คิวเดิมหมด 5 ก.ค. — ต่อคิวเลย 18:00 เดิม)
8. Flow เครดิต 1000: **แผนใช้ 15 คลิปแรก = title-loan 8 / kept 5 / e-book 2** — gen เป็น batch ตาม workflow เดิม (ตรวจ+จัดการลายน้ำทุกคลิป + แคปชันคง "ผลิตด้วย AI")

## P3 — Pantip (บัญชีเคยโดนเตือน — ระวังสุด)
9. pipeline ร่างกระทู้ความรู้ล้วน 2 กระทู้ (ปลดหนี้เป็นระบบ / รีวิวแนวคิดออมดอกสูง) **ไร้ลิงก์ ไร้ราคา ไร้ชื่อสินค้า** ฝังชื่อ "เงินเดือนสมองทอง" ธรรมชาติ 1 ครั้ง → วางที่ social-review/pantip ให้เจ้าของอ่าน+โพสต์เอง มือเท่านั้น ห้าม automation แตะ Pantip

## รายงานผล
- cc-outbox/CC-report_revenue-sprint_20260702.md + อัปเดต launch-status.json (Cowork จะ regen dashboard)
- ห้ามแตะ: การ์ด zero-budget · secrets · ห้าม deploy เอง
