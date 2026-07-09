# CC report — MASTER ORDER deploy-debt-funnel (TASK 1-5) — ✅ ครบ · LIVE VERIFIED
executed: 2026-07-09 · idempotent-checked ก่อนแก้ (ยังไม่มี LINE/toolkit/tagline ในโค้ด = ทำใหม่ทั้งหมด) · zero-budget · ไม่มีตัวเลข/การันตีดอกเบี้ยใหม่ · commits: content b38a84b → **build_site.py 94ef056 แยก push ท้ายสุด** (ignore-rule ยืนยัน BUILD RUN)

## TASK 1 — /debt-calculator ✅ LIVE
- build_site.py: copy แบบ **head-inject** (canonical /debt-calculator + og:title/desc/image + GA_SNIPPET) — เหตุผล: ไฟล์ standalone ของ Cowork ไม่มี GA4/og → ถ้า copy ตรงๆ smoke gate บน Netlify จะ FAIL ทั้ง deploy; inject ตอน build = ไฟล์ root คงเดิม + หน้า funnel ได้ analytics
- _redirects += `/debt-calculator  /debt-calculator.html  200` (ตาม order) · เพิ่มเข้า sitemap (0.8)
- #lineBtn ยืนยัน = line.me/R/ti/p/@804qodya target=_blank ✓ (Cowork wire ไว้ถูก)
- SMOKE: site/debt-calculator.html ✓ (16.4KB) · JS inline ไม่มี dep นอก ✓ · **LIVE 200: calcJS ✓ lineBtn ✓ GA4 ✓**

## TASK 2 — ปุ่มแอด LINE ทุกหน้า ✅ LIVE
- nav ใน head() template: เพิ่ม "แอด LINE" (เขียว #06C755, target=_blank noopener) → ขึ้นทุกหน้าอัตโนมัติ + แถม "ปลดหนี้" เป็น nav item แรก → /debt-calculator (T4 debt-เด่น + T5 internal link ทุกหน้า)
- SMOKE: ตรวจ article/home/quiz มีครบ · **LIVE: navLINE ✓ navปลดหนี้ ✓**

## TASK 3 — /links funnel-fix ✅ LIVE
- ลำดับใหม่ (ลด choice overload ตาม Gemini): **การ์ด LINE ฟรี (บนสุด)** → label "คู่มือของเราเอง (ไม่ใช่ลิงก์พันธมิตร)" → **e-book 59฿ ⭐แนะนำ** (+social proof "อัปเดต ก.ค. 69 · มาตรการรัฐล่าสุด · Excel กรอกได้") → **🧰 ชุดเครื่องมือปลดหนี้ 199฿** (debt-toolkit) → Quiz → **divider "ทางเลือกการเงินจากพันธมิตรของเรา (ลิงก์พันธมิตร)"** → Kept/Srisawad + หมวดเดิมด้านล่าง
- FTC disclosure ยังถูกต้อง (affil_disclose แทรกก่อน atth.me anchor แรกอัตโนมัติ ไม่ขึ้นกับลำดับ) · comply_gate ทุก block ใหม่ GATE_OK
- SMOKE: order ascending ✓ · **LIVE: LINE-card ✓ toolkit199 ✓ aff-divider ✓**
- note T3.4: "หน้าขาย e-book" ฝั่ง Gumroad = Cowork แก้เอง (CC เพิ่ม social proof บนการ์ด /links แล้ว)

## TASK 4 — wedge tagline ✅ LIVE
- home <title>/meta/og + hero: "**ปลดหนี้ด้วยตัวเลขจริง ไม่ขายฝัน**" + ลิงก์เครื่องคำนวณใน hero · about เพิ่ม positioning เดียวกัน · cluster อื่นคงครบ (แค่ debt เด่นสุดใน nav/hero)
- **LIVE: tagline บนหน้าแรก ✓**

## TASK 5 — SEO ✅
- internal links → /debt-calculator: nav ทุกหน้า + บรรทัด "🧮 ลองเครื่องคำนวณฟรีก่อน" ใน ebook_banner = โผล่บน 5 หน้า traffic/conv ดีสุด (kept-savings, debt-consolidation, pay-off-credit-card, title-loan, close-debt-fast)
- sitemap priority: debt-consolidation / pay-off-credit-card-debt / title-loan → **0.9** (ที่เหลือ 0.8 เดิม) + debt-calculator 0.8
- เจ้าของ: กด GSC Request-Indexing (/debt-calculator + 3 หน้าหนี้) เอง

## GATES รวม: smoke **62/62 PASS** (หน้า calculator นับรวมแล้ว) · link_check **0 broken** (69 หน้า) · comply_gate GATE_OK · byte-safe UFFFD=0
## DoD: ครบทุกข้อ — /debt-calculator LIVE · LINE ทุกหน้า · /links การ์ดครบ+e-book เด่น · tagline ขึ้นหน้าแรก · sitemap/internal links อัปเดต · 0 broken · disclosure ครบ
