# CC report — Newswatch integration A-E (order-newswatch-integration-20260702) — ✅ ครบ (E ทำด้วย)
executed: 2026-07-02 เย็น · zero-budget ✓ การ์ด free_ai ไม่แตะ ✓ Pantip ไม่แตะ ✓ ไม่อัป Gumroad เอง ✓

## A) commit ฐานข้อมูล ✅ — knowledge-base/FACTS_current.md + order + รายงานนี้ (push แรก)
## B) กันร่างเก่า ✅
- สแกน content-packages + _social-stage: เจอ 2 ไฟล์มี "ขั้นต่ำ 5%/5-10%" (20260621-2210 + 20260701-0730 เงินเดือน 15000) -> ติดป้าย ⚠️ OUTDATED-FACTS บรรทัดแรกแล้วทั้งคู่ · ไม่พบ "คุณสู้เราช่วย+ชวนสมัคร"
- comply_gate: เพิ่ม STALE-FACTS **warn** (ไม่ block): "ขั้นต่ำ 5%" -> เตือน 8% ถึง 31 ธ.ค. 69 · "คุณสู้เราช่วย"+ลงทะเบียน/สมัคร -> เตือนปิดรับแล้ว — ทดสอบ: warn โชว์โดย ok ไม่ flip, rule จริงยัง fail ปกติ, ข้อความสะอาดผ่าน
## C) e-book audit ✅ (ข้อจำกัด: source ไม่อยู่เครื่องนี้)
- หา source แล้ว: PDF 35 หน้า + Worksheet.xlsx **อยู่ใน Cowork sandbox outputs (นอก repo public ตาม launchplan)** + สำเนา live บน Gumroad — เครื่อง local ไม่มีไฟล์ -> CC เปิดตรวจเนื้อในเองไม่ได้
- ส่งมอบแทน: **_social-stage/EBOOK-v1.1-UPDATE-PACK_20260702.md** = จุดต้องตรวจ 5 ข้อเทียบ FACTS (8%+หมดอายุ · คุณสู้เราช่วยปิดรับ · เงื่อนไขคลินิกแก้หนี้ · เพิ่ม section "ปิดหนี้ไว ไปต่อได้" พร้อมข้อความวางได้เลย · เพดาน title-loan) + changelog 1 หน้า "อัปเดต ก.ค. 69" + ขั้นตอนเจ้าของอัป Gumroad 1 คลิก + ร่างโพสต์ประกาศ "ผู้ซื้อเดิมโหลดฟรี" (comply OK, ลงคิวหลัง v1.1 ขึ้นเท่านั้น)
- ACTION: Cowork (ผู้ถือ source) ทำ v1.1 ตาม pack -> เจ้าของ Replace file บน Gumroad
## D) dashboard freshness ✅ — dashboard_agent._launch อ่าน "ตรวจล่าสุด: **YYYY-MM-DD**" จาก FACTS_current.md -> บรรทัด "📚 facts ตรวจล่าสุด <วันที่> · อายุ N วัน" ในการ์ด Launch (เกิน 14 วัน = สีเตือน #e0a93c + ข้อความรัน newswatch) — ทดสอบ render ผ่าน (วันนี้เขียว อายุ 0 วัน)
## E) หน้า SEO ใหม่ ✅ — /close-debt-fast-2026.html "ปิดหนี้ไว ไปต่อได้ 2569"
- เนื้อหาตาม FACTS เป๊ะ (เกณฑ์ NPL/ยอดรวม "ไม่เกินหนึ่งแสนบาท"/ผ่อน "ไม่มีดอกเบี้ย ไม่เกินสามปี" — สะกดเลขเป็นคำ ผ่านทั้ง comply_gate + stitch body 0 FAIL) + คำเตือนมิจฉาชีพ + fallback ไม่เข้าเกณฑ์ -> คลินิกแก้หนี้/ปลดหนี้บัตร/รวมหนี้
- CTA ตาม order: e-book banner (เพิ่ม slug เข้า EBOOK_PAGES) + ลิงก์ /links + cluster links (debt-collection-rights, rebuild-credit, debt-clinic-sam) · ไม่มี atth.me บนหน้า (educational + ชูช่องทางฟรีรัฐ)
- QA: build ok · canonical/index,follow/sitemap ✓ · smoke **61/61 PASS** (หน้าใหม่นับแล้ว) · หมายเหตุ: เจอ+แก้ stitch false-positive class เดิม (เครดิต ชิด </h3>) ด้วย reword
- PUSH แยกท้ายสุดตามกติกา ignore-rule (commit build_site.py = HEAD สุดท้าย) -> Netlify build -> live-verify แนบท้าย
## หมายเหตุ: EBOOK-UPDATE-PACK อยู่ _social-stage (gitignored ตาม design — media/drafts local; Cowork เห็น pack ผ่านเครื่อง owner/รายงานนี้สรุปครบแล้ว)
