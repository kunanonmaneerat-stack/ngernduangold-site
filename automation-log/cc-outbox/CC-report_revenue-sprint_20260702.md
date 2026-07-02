# CC report — Revenue Sprint 7 วัน (order-revenue-sprint-20260702) — ✅ P1+P2+P3 ครบ
executed: 2026-07-02 · zero-budget ✓ · ไม่แตะ free_ai guards/secrets ✓

## P1 — โค้ด /links + หน้าแปลงสูง (build_site.py) ✅ DEPLOYED
1. /links: การ์ด 2 ใบใหม่ใต้การ์ด e-book — "🏦 ออมดอกสูง Kept — สมัครฟรี" + "💸 จำนำทะเบียนรถ — เงินด่วน รถยังใช้ได้" ผ่าน helper bcta() เดิม -> utm/rel เหมือนปุ่ม affiliate เดิมทุกประการ (rel="sponsored noopener nofollow", utm_content=website_links_kept / _srisawad, LINKS_CHANNEL_JS rewrite ต่อ channel ทำงานเหมือนเดิม). ลำดับ verify แล้ว: quiz -> e-book -> Kept -> จำนำทะเบียน -> หมวดเดิม
2. แบนเนอร์ e-book (class ebkbn, rel=noopener ล้วน ไม่ใช่ affiliate + ระบุ "ไม่ใช่ลิงก์พันธมิตร") ท้ายเนื้อหา 4 หน้า: kept-savings + debt-consolidation + pay-off-credit-card-debt + title-loan — verify: ebkbn=1 ทั้ง 4 หน้า, หน้าอื่น=0
3. Quiz result: ข้อเสนอ e-book (rmore style, rel=noopener) ต่อท้ายผลลัพธ์ทุก path (showRes ยิงทุกเส้น)
4. build exit 0 · smoke 60/60 PASS (GA4 snippet, rel=sponsored ครบ 190 ปุ่ม, canonical/OG, FTC disclosure-order) · commit+push แล้ว (push = Netlify auto-deploy ตาม pipeline ปกติของ repo — ตรวจ live แนบท้ายรายงาน)

## P2 — คอนเทนต์คิว 7 วัน ✅
5. pipeline/trend_ingest.py PROMPT = SPRINT FOCUS 2-8 ก.ค. เฉพาะ 2 ธีม (จำนำทะเบียน -> title-loan-2026 / ออมดอกสูง -> kept-savings-2026) งดธีมแมส — บล็อกมีวันที่กำกับ ลบออกได้หลังจบ sprint
6. คิว FB+Threads รายวัน 2-8 ก.ค.: _social-stage/QUEUE_fb-threads_20260702-0708.md (7 วัน x 2 ช่อง, FB ลิงก์หน้าปลายทางในคอมเมนต์แรก, Threads ไร้ลิงก์) — comply_gate GATE_OK. หมายเหตุ: ig-fb-post-pack.md (กราฟิก 4 ใบ) ไม่อยู่ใน repo local — อยู่ฝั่ง Cowork outputs -> Cowork แนบกราฟิกตอน stage
7. คลิปเดิม 7 ตัวจาก _vidout staged เข้า _social-stage แล้ว + POST-PACK_week_20260706-0712.md (YT 18:00 ต่อคิวเดิม + IG 20:00 + TikTok 19:00) — วันที่ 11-12 เป็น filler นอกธีม (สลับเป็นคลิปใหม่จาก Flow ถ้าเจนทัน) · กัน dedup: ห้าม ebook-promo ซ้ำในสัปดาห์ (±16 วัน) + สั่ง post_ledger check ก่อนตั้งทุกตัว · หมายเหตุ: ไม่มีไฟล์ reel_kept ใน _vidout — ธีมออมใช้ emergency-fund + salary-budgeting แทน (คลิป kept แท้อยู่ใน FLOW-PLAN)
8. FLOW-PLAN_15clips_20260702.md: 15 คลิป = title-loan 8 (tl01-08) / kept 5 (kp01-05) / e-book 2 (eb01-02) พร้อม hook+ฉากต่อคลิป, กติกา (ตรวจลายน้ำทุกคลิป, แคปชัน "ผลิตด้วย AI", ไร้ตัวเลขดอก/วงเงิน), naming _final_*.mp4 (~225/1000 เครดิต)

## P3 — Pantip (ระวังสุด) ✅ DRAFTS ONLY
9. 2 ร่างที่ social-review/pantip/: draft-thread_debt-system (เปิดไพ่/Avalanche-Snowball/คลินิกแก้หนี้) + draft-thread_high-yield-savings (หักก่อนใช้/เงินสำรอง/ระวังมิจฯ) — ตรวจแล้วทั้งคู่: comply_gate GATE_OK · ลิงก์=0 · ราคา=0 · ชื่อสินค้า=0 · แบรนด์ "เงินเดือนสมองทอง" ธรรมชาติ 1 ครั้งพอดี · เจ้าของอ่าน+โพสต์มือเท่านั้น (automation ไม่แตะ Pantip)

## launch-status.json อัปเดตแล้ว (pending ใหม่: stage คิว/gen Flow/โพสต์ Pantip) — Cowork regen dashboard ได้เลย
## LIVE VERIFY (หลัง push): ดูบรรทัดท้ายรายงานนี้ (CC เติมผล live check /links)

## LIVE VERIFY (interim, ~15 นาทีหลัง push)
- push ยืนยัน: origin/main=2294f60 · Netlify build-gate = build_site.py + postdeploy_smoke (ชุดเดียวกับที่ผ่าน local 60/60 — build เดียวกัน deterministic ถ้า gate พังจะ deploy ไม่ขึ้นเลย)
- urllib เช็ก /links ยังเห็นเวอร์ชันเก่า ~7 นาทีแรก = อาการ CDN stale-cache ที่รู้จัก (OPERATING-NOTES 06-26: หน้าเดิม stale ได้ ~40 นาที · browser = truth · Netlify ไม่สน ?query)
- CC ตั้ง poller ยาว (ทุก 60 วิ x 40 นาที) ไว้แล้ว — ผลสุดท้ายจะแจ้งใน chat/รายงานถัดไป · Cowork/เจ้าของเช็กเร็วสุด = เปิด https://ngernduangold.com/links ใน browser (มองหาการ์ด "🏦 ออมดอกสูง Kept" ใต้การ์ด e-book)
