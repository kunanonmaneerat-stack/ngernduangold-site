# CC report — อุด "ราคา 2 สกุล/2 เส้นทาง" → บาททั้งเส้น (order 10 ก.ค.) — ✅ LIVE
executed: 2026-07-10 · commit 0edbbb6 (build_site.py เดียว = HEAD สุดท้าย, ignore-rule BUILD RUN ✓)

## A1 occurrence sweep: เจอ 4 จุด (ทั้งหมดใน build_site.py) — แก้ครบ 4/4
1. EBOOK_URL constant (→ banner 5 หน้าบทความ) 2. /links ปุ่ม 59฿ 3. /links ปุ่ม 199฿ 4. quiz result offer
(debt-calculator = 0 อยู่แล้ว ✓ · dashboard/launch-status = log ไม่ใช่หน้าเว็บ)

## A2 /links — LIVE ✓
- 59฿ + 199฿: **primary = LINE (ทางไลน์ · พร้อมเพย์)** + data-note ราคา · **secondary = text-link เล็ก .paysec ติดป้าย "Gumroad · คิดเป็น USD"** (utm secondary/guide59_card·toolkit199_card)
- id="buy" บน label "คู่มือของเราเอง (ไม่ใช่ลิงก์พันธมิตร)" (disclosure คงเดิม) · secondary เล็กกว่า primary จริง (ลิงก์ข้อความ ไม่ใช่ปุ่ม)
- ⚠️ ชื่อ class ตาม order (.btn-secondary/hubsec) ชนกับ class เดิมของหน้า → ใช้ **.paysec** (พฤติกรรม/สเปกเหมือนเดิมทุกอย่าง)

## A3 CTA ฝังในบทความ/quiz → /links#buy — LIVE ✓
- ebook_banner (kept-savings, debt-consolidation, pay-off, title-loan, close-debt-fast) → /links?utm article/footer/guide59#buy (internal)
- quiz result → /links?utm quiz/result/guide59#buy · **gumroad ใน kept-savings = 0 แล้ว (live-verified)**

## A5 gates + sweep ซ้ำ
- re-grep ทั้ง built site: **ปุ่มซื้อยิงตรง Gumroad ไม่ติดป้าย = 0** — เหลือเฉพาะ 2 labeled secondaries บน /links ตาม spec
- smoke 62/62 · check_affiliate_links 15/15 (affiliate ไม่กระทบ) · link_check 0 broken · comply GATE_OK (59/199฿ = ราคา ไม่ใช่ดอกเบี้ย)
- LIVE (~นาทีแรก): 59-LINE ✓ 199-LINE ✓ USD-secondary x2 ✓ id=buy ✓ kept→#buy ✓

## B (Gumroad dashboard — เจ้าของ/Cowork-browser เท่านั้น, CC ไม่แตะ)
1) เพิ่มลิงก์กลับใน description 2 สินค้า: ngernduangold.com + line.me/R/ti/p/@804qodya 2) ป้าย "ราคาไทย 59/199฿ · Gumroad คิดเป็น USD โดยประมาณ · อยากจ่ายบาทตรง ๆ ทาง LINE" 3) (ออปชัน) cross-sell Kept ท้าย description
## ผล: เส้นจ่ายเงินสินค้าเราเอง = บาท/LINE ทุกจุดในเว็บ (calculator ✓ /links ✓ บทความ ✓ quiz ✓) · Gumroad = ทางเลือกรองติดป้ายโปร่งใสที่เดียวบน /links
