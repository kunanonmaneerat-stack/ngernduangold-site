# CC report — MASTER ORDER ส่วนที่เหลือ (A SEO harvest · B winner links · C cleanup) — ✅ เสร็จ (A ปรับตามข้อมูลจริง)
executed: 2026-07-10 · gates: smoke 62/62 · affiliate 17/17 · link_check 0 broken · comply GATE_OK

## A) SEO striking-distance — ⚠️ VERDICT จากข้อมูลจริง: harvest 10 หน้ายังไม่มีให้เก็บ
- ดึง GSC จริง (query+page, 28 วัน): **ทั้ง property มี 7 rows เท่านั้น · pos 8-20 = 0 rows ทุก threshold (แม้ imp≥1)** — property อายุ ~2 สัปดาห์ (verified 27 มิ.ย.) ยังไม่มีคีย์ "เกือบหน้า 1" จริง → การแต่ง 10 หน้า = fabricate ไม่ใช่ data-driven
- CSV จริง: automation-log/striking-distance_20260710.csv (7 rows) · **ทำที่มีจริงแทน 2 หน้า (indexed-but-weak)**:
| หน้า | query จริง (imp/pos) | สิ่งที่แก้ |
|---|---|---|
| /car-still-installment-loan | "รถ(ยัง)ผ่อนไม่หมดจำนำได้ไหม" (35/pos~39) + **"รถเกิน15/20/25ปีเข้าไฟแนนซ์ได้ไหม" (10/pos61-70 — หน้าไม่เคยตอบ!)** | +2 FAQ อายุรถ (visible+FAQ JSON-LD, ไม่ fabricate เพดาน — "เช็กกับผู้ให้บริการ") + desc teaser อายุรถ |
| /credit-card-salary-30000 | "เงินเดือน 30000 วงเงินบัตรเครดิต" (12/pos~30) | title เดิมไม่มีคำว่า "วงเงิน" → ใหม่: "เงินเดือน 30,000 วงเงินบัตรเครดิตได้เท่าไหร่ สมัครใบไหนดี 2026" (คำถาม+ปี = CTR trigger) · FAQ วงเงินมีอยู่แล้ว+schema ✓ |
- **นัดทำซ้ำ**: pos-8-20 harvest ให้รันใหม่เมื่อ GSC สุกงอม (~2-4 สัปดาห์ — weekly-review จับ striking-distance อยู่แล้วอัตโนมัติ)
- A3 index: URL-inspection (API read-only) → salary-30000 = **Submitted and indexed** ✓ · car-still = **".html URL unknown to Google — Google index ตัว extensionless แทน"** 🔴 FLAG: canonical(.html) กับ URL ที่ Google เลือก (ไร้ .html) ไม่ตรงกัน (คลาสเดียวกับ quiz/links ที่เคยแก้) — เสนอรอบหน้า: 301 .html→extensionless หรือกลับกันให้ทั้งไซต์สม่ำเสมอ · **request-indexing = ทำผ่าน API ไม่ได้** (Google จำกัด Indexing API เฉพาะ JobPosting) → เจ้าของกดใน GSC UI: 2 URL ข้างบน

## B) Winner internal links — ✅ เกินเป้าอยู่แล้ว (ไม่ต้องเพิ่ม)
- **/kept-savings-2026 inbound (in-body, ไม่นับ nav) = 19 หน้า** (เป้า ≥8-10) — มาจาก kept_next 9 หน้า + saveCta calculator + ออม cluster + related cards
- **/debt-calculator = 13 หน้า in-body + nav ทุกหน้า (62) + calc banner ต้นบทความ debt-cluster 9/9** ✓
- before/after: ไม่เปลี่ยน (before ก็เกินเป้าแล้วจากงาน 2 รอบก่อน) — รายงานตัวเลขตามจริง

## C) Consistency cleanup — ✅
1. netlify.app ใน web source = **0** (build_site.py/debt-calculator/recommend_map สะอาด — เหลือเฉพาะใน docs/runbooks ซึ่งเป็น log ไม่ใช่หน้าเว็บ; ที่ค้างจริงคือปุ่ม DM ใน CreatorFlow = งาน dashboard เจ้าของ ตาม report AUTO-DM เดิม)
2. AXA /go/PhAKgrKX: check_affiliate_links ครอบคลุม (regex รองรับ /go/ ตั้งแต่ commit eef5270) + **resolve 200 ยืนยันซ้ำวันนี้** ✓ format แปลกแต่ใช้งานได้จริง
3. affiliate รวม = **17/17 live 0 problem** ✓

## commits: automation-log (CSV+report) → build_site.py แยกท้ายสุด · live verify แนบท้าย
