# CC report — ขยายตัวชนะ (data-driven จาก GA4 10 ก.ค.) — ✅ LIVE ครบ
executed: 2026-07-10 · commits: f22b224 (calculator) → 01c969c (build_site.py แยกท้ายสุด) · gates: affiliate 15/15 · smoke 62/62 · link_check 0 broken · comply GATE_OK

## แก้ #1 — saveCta (kept-savings wedge หลังปลดหนี้) ✅ LIVE
- #saveCta เขียวอ่อน ใน #results ต่อจาก refiCta (โผล่พร้อมผลลัพธ์ ไม่แตะ JS) → /kept-savings-2026?utm kept_wedge (winner GA4 conv ~93%) · มุม "ปลดหนี้แล้วอย่าให้วนกลับ = เงินสำรอง" · ไม่มีตัวเลขดอก

## แก้ #2 — routing ไป winner ✅
- /links: **ตรวจแล้วไม่ต้องแก้** — Kept + จำนำทะเบียน เป็น 2 CTA แรกของโซน affiliate อยู่แล้ว (ตัวก่อนหน้าเป็น grid นำทางหมวด ไม่ใช่ offers) → idempotent skip
- **kept_next** บน 9 หน้า debt-cluster: แถบเขียว "ปลดหนี้แล้ว ขั้นต่อไป: กันเงินสำรองไว้ในบัญชีดอกสูง →" ท้ายเนื้อหา (utm article/nextstep/kept_wedge) · ไม่ self-link บน kept-savings ✓
- /debt-consolidation-2026 (3/13 conv): **verdict = CTA ชัด + above fold อยู่แล้ว** (top_offer "สินเชื่อรวมหนี้ ยุบหลายก้อน..." ก่อน h1 + cmp_widget HAPPYDEBT best) → placement ไม่ใช่ปัญหา · n=13 เล็ก + intent รวมหนี้ research-heavy — lever ที่ใส่วันนี้ (calc banner + refi wedge + kept_next) คือคำตอบที่เหมาะ ไม่ยัด CTA เพิ่ม

## LIVE VERIFY (~นาทีแรก): saveCta ✓ kept_wedge utm ✓ refiCta คงเดิม ✓ kept_next บน debt page ✓ calc-banner คงเดิม ✓
## Loop "อย่าให้รั่ว" ครบ: reach → บทความหนี้ (calc banner) → calculator → refi wedge (เครื่องยนต์เงิน) + saveCta → kept 93% + kept_next ท้ายทุกหน้าหนี้ · ที่เหลือของเกม 90 วัน = reach (community/human-driven ตาม order)
