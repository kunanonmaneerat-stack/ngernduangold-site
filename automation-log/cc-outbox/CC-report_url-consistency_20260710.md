# CC report — URL-consistency audit + fix ทั้งไซต์ — ✅ 0 mismatch · LIVE VERIFIED
executed: 2026-07-10 · commit 35c9a76 (build_site.py, push เดียวท้ายสุด) · audit CSV: automation-log/url-consistency-audit_20260710.csv

## A) AUDIT ก่อนแก้ (truth table จริง 62 หน้า — ไม่เดา)
- **DUP-200-BOTH = 60/62 หน้า** (Netlify pretty-URLs เสิร์ฟ extensionless โดยไม่ redirect + .html ก็ 200) — duplicate ทั้งไซต์
- GSC: car-still ถูก index แบบ **ext** (สวน canonical .html) · **salary-30000 มีทั้ง 2 ฟอร์มใน GSC** = signal split ของจริง
- ✅ slug จริงที่ Cowork ขอ: **/car-still-installment-loan-2026** และ **/credit-card-salary-30000-2026** (ตัวที่ทดสอบ 404 รอบก่อน = slug ย่อผิด: "car-still-2026"/"credit-card-salary-30000" ไม่มีอยู่จริง)
- ถูกอยู่แล้วก่อนแก้: quiz + links (301 ที่ทำไว้)

## B) Convention ที่เลือก: **EXTENSIONLESS** (ตามคำแนะนำ + audit สนับสนุน)
เหตุผล: Google เลือก ext เองเมื่อมี 2 ฟอร์ม (car-still) · quiz/links/debt-calculator เป็น ext อยู่แล้ว · เปลี่ยนที่ canonical/links แต่ .html เดิม 301 ครบ = ไม่สูญ ranking ของ 55 บทความ

## C) FIX (ทุกชั้น ใน build_site.py — generator แก้ที่เดียวคุมทั้งไซต์)
1. `_redirects`: **generate 301 ต่อหน้าอัตโนมัติ 68 บรรทัด** (`/x.html → /x 301!` + `/index.html → /`) — google-verify file ยกเว้น (ต้องอยู่ที่ .html เพื่อ GSC ownership) · /go/* + calculator 200-rewrite คงเดิม · 301! forced = ห้าม 200 สองฟอร์มอีก
2. head(): canonical + og:url = ext ทุกหน้า · JSON-LD mainEntityOfPage = ext
3. **post-build internal-href normalizer** (รันท้ายสุดหลังทุกหน้า write): href="/x.html" → "/x" ทั้ง nav/cards/cluster/banner/quiz-JS (รองรับ ?query/#frag, external + google ไม่แตะ) → **เหลือ 0 internal .html hrefs**
4. sitemap = ext ล้วน 62 URLs
- บั๊กที่เจอ+แก้ระหว่างทำ: บล็อก normalizer/redirects ต้องอยู่ **ท้ายสคริปต์** (links/quiz/calculator ถูก write ทีหลัง — ตำแหน่งแรกทำ clean-build พลาด)

## D) VERIFY
- local truth ซ้ำ: canonical ext 62/62 · internal .html hrefs = 0 · sitemap ext-only · 301 lines 68
- **LIVE (no-redirect probe) 10 ตัวอย่าง + winner ทุกหน้า: .html→301→ext (ไม่มี chain/loop) · ext→200 · google-verify ยัง 200 · เนื้อหา+affiliate ครบ (kept/calculator/links/kashjoy/ngernturbo)** — ALL PASS
- gates: smoke 62/62 · link_check 0 broken · affiliate 17/17 · comply ไม่แตะเนื้อหา
- GSC re-inspect (canonical ใหม่): ผลแนบบรรทัดบน · request-indexing = เจ้าของกด UI (API ไม่เปิดให้) — แนะกด 2 URL: /car-still-installment-loan-2026 + /credit-card-salary-30000-2026 + submit sitemap ใหม่ (1 คลิก)
## ผล: 1 หน้า = 1 canonical URL ทั้งไซต์ · signal ไม่ split อีก · harvest/verify รอบหน้าอ้าง URL ได้แม่นยำ
