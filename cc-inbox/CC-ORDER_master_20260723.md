# WORK ORDER → Claude Code: ชุดรวม 4 งาน (23 ก.ค. 2026 23:20 · จาก Cowork) — ทำตามลำดับ A→D

> บริบท: แอป automation ดับ 22–23 ก.ค. (Windows Update) กู้ระบบเสร็จแล้ว · วันนี้เปิดชั้นคอนเทนต์ใหม่ "quote-card" (คำคม+ภาพ Gemini ลง FB+IG อ./พฤ./ส. 08:30) · commit ฝั่ง Cowork ค้าง push อยู่หลายตัว
> กฎเหล็กเดิม: UTF-8 เท่านั้น · ห้าม `git add -A` · ห้ามแตะ secrets/ · zero-budget · ห้ามคำต้องห้าม (อนุมัติง่าย/แน่นอน/ไว, ไม่เช็คบูโร, การันตี, รับรองผล) · ห้ามเลขดอกเบี้ย/%

## A. รัน order เดิมที่ค้าง: internal-link boost (สำคัญสุด — ค้างตั้งแต่ 21 ก.ค.)
เปิดไฟล์ `cc-inbox/CC-ORDER_internal-link-boost_20260721.md` แล้วทำตามทุกข้อในนั้น สรุปหัวใจ:
- เพิ่มลิงก์ contextual `.ilinks` ใน build_site.py: เข้า target C **debt-letter-kit (แก้ orphan — สำคัญสุด referring ≥3)** จาก debt-consolidation/debt-restructuring/pay-off-credit-card-debt/debt-clinic-sam · เข้า A car-still-installment-loan-2026 (3 source) · เข้า B credit-card-salary-30000-2026 (3 source)
- anchor ตามที่ order ระบุ ห้ามคำต้องห้าม · 1 ลิงก์/source · dup-check ก่อนเพิ่ม (grep source→target ที่มีอยู่แล้ว = ข้าม)
- BUILD GATE บังคับ: `set SITE_GA=G-17PPE0M1B8` → `python build_site.py` → `python tools/postdeploy_smoke.py --src site` ต้อง PASS ทุกหน้า ไม่ผ่าน = หยุด ห้าม commit
- verify: grep นับลิงก์เข้า target ใน site/*.html ก่อน/หลัง ต้องเพิ่มตามจำนวน source

## B. push ทั้งหมด (หลัง A ผ่าน gate)
- commit ค้างฝั่ง Cowork ที่ต้องขึ้น remote: `ae8a0a8` (quote-card layer: คลัง QUOTE-CARDS_20260723-0822.md + media/quotes/qt-01*.png/jpg + ledger) · `ec9f63f` (ledger backfill คลิป FB 23 ก.ค.) · และ runlog อื่นถ้ามี
- รวมกับ commit ของงาน A แล้ว `git push origin main` ครั้งเดียว (= deploy Netlify หนึ่ง build ประหยัด build-minutes · หมายเหตุ: media/quotes อยู่นอก ignore-rule จะ trigger build อยู่แล้ว — ถูกต้อง เพราะงาน A ต้อง deploy)
- push แล้ว verify: `git status` สะอาด + remote ตรง local

## C. แก้ dispatcher: คลิปอัตโนมัติต้อง append post-ledger ทุกครั้ง (บั๊กเจอ 23 ก.ค.)
หลักฐาน: delivery-verify 21:1x พบคลิป FB credit-bureau ออกจริง ~19:2x แต่ไม่มีใน post-ledger.jsonl (Cowork ต้อง backfill มือ = ec9f63f) → dup-check/quota-check ของ fleet เพี้ยนได้
- หา flow ที่ dispatcher ฝั่ง CC โพสต์/ยืนยันคลิปรายวัน (ดู .system_control/ + dispatcher.log ว่า step ไหนรายงานสำเร็จ)
- เพิ่ม step: เมื่อยืนยันคลิปขึ้นช่องไหนสำเร็จ → append บรรทัด JSON ลง automation-log/post-ledger.jsonl รูปแบบเดียวกับที่มีอยู่: {"type":"video","channel":"facebook|youtube|instagram","text_first80":"<หัวข้อคลิป>","ts":"<ISO+07:00>","source":"cc-dispatcher"} · เขียนแบบ UTF-8 no-BOM append-only
- ทดสอบ dry-run 1 ครั้งว่าเขียน ledger ได้จริงโดยไม่ทำลายบรรทัดเดิม (ห้าม rewrite ทั้งไฟล์)

## D. เก็บกวาดคิว cc-inbox (กันสับสนรอบหน้า)
- สร้าง `cc-inbox/done/` แล้วย้าย order ที่จบแล้วเข้าไป: CC-ORDER_push-fleet-commits_20260721.md (push ไปแล้ว) · order-factfix-20260720.md · CC-ORDER_gsc-request-indexing_20260718.md · CC-ORDER_seo-strike_20260717.md (ตรวจก่อนย้ายว่าแต่ละอันจบจริง — อันไหนไม่จบให้รายงานแทน ห้ามย้าย)
- หลังทำ A เสร็จ ย้าย CC-ORDER_internal-link-boost_20260721.md + ไฟล์นี้ เข้า done/ ด้วย

## 📤 รายงานผล → cc-outbox/result-master-20260723-<ts>.md
ต้องมี: (A) source ที่แก้กี่หน้า + จำนวนลิงก์เข้า target ก่อน/หลัง + build/smoke PASS? (B) push แล้ว? commit hash ล่าสุดบน remote (C) แก้ dispatcher ที่ไฟล์ไหน + ผล dry-run (D) ย้ายไฟล์ไหนเข้า done/ บ้าง · ปัญหาที่เจอ+วิธีแก้
> D เพิ่มเติม: มี order เก่า untracked อีกหลายไฟล์ใน cc-inbox (APPROVE-push-ebook-launch-20260628, CC-MASTER-ORDER_deploy-debt-funnel_20260709, CC-ORDER_amplify-winners, CC-ORDER_calculator-revenue-wiring ฯลฯ) — ตรวจสถานะแต่ละอัน: จบแล้ว = ย้ายเข้า done/ · ยังไม่จบ = สรุปในรายงานว่าเหลืออะไร ห้ามเริ่มทำเองโดยไม่รายงานก่อน
