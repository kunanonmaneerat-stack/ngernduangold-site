# RESULT — FACTFIX P0+P1 (go-order 24 ก.ค. 2026)

สถานะ: **P0+P1 deploy แล้ว · P2 ครบตามโหมด report-don't-guess** · gate PASS ทุกข้อ

## P0 — debt-clinic-sam-2026 · แก้ครบ 5 จุด ✅
who ul (มีรายได้/≤70ปี/ค้าง>120วัน/≤2ล้าน) · terms (ผ่อนสูงสุด 10 ปี) · notqualify (เพดาน 2 ล้าน) · faq35 ข้อ1+ข้อ2 (คำตอบใหม่ "ได้ — รับถึง 2 ล้าน...") · meta description ใหม่ · แถมอัปเดตวันที่หน้าเป็น 24 ก.ค. 2026 ตาม go-order
- ใช้ exact-string find/replace ทุกจุด (assert count==1) — ไม่อิงเลขบรรทัด · .ilinks ที่เพิ่มรอบก่อนไม่ถูกแตะ (ยืนยันคงอยู่หลัง build)

## P1 — close-debt-fast-2026 · แก้ครบ 4 จุด ✅ (verify ก่อน commit ทุกข้อ)
ตรวจกับ **bot.or.th/cleardebt สดวันนี้ (24 ก.ค.)** — ทุกข้ออ้างเชิงปฏิบัติ**ตรงแหล่งทางการ จึงใช้ข้อความ "ใหม่" ตาม order เต็ม ไม่ต้องลดภาษา**:
| ข้ออ้าง | ผล verify |
|---|---|
| ช่องทาง 3 ทาง: bot.or.th/cleardebt · ธนาคารเจ้าหนี้ · SAM | ✓ ตรงหน้าเว็บ ธปท. |
| SAM LINE @samsocialamc · call center 1443 กด 6 | ✓ ระบุตรงตัว |
| ข้อยกเว้น: จำนำทะเบียนรถ + nano finance บสย. / ศาลพิพากษา / ฟ้องรวม / บัญชีม้า | ✓ ครบทั้ง 4 กลุ่ม |
| SAM แจ้งผลทาง SMS | ✓ |
| ลูกหนี้ SFIs → บบส.อารีย์ (ARI-AMC) | ✓ |
| จ่ายครบ → ยกดอก/ค่าธรรมเนียมค้างทั้งจำนวน · โครงการ ~3 ปี ครั้งเดียว | ✓ |
- จุดที่แก้: who +2 bullet (ยกเว้นจำนำทะเบียน = สำคัญกับกลุ่ม affiliate เรา) · get +ยกดอก+ข้อควรรู้เรื่องเวลา · how 3 ช่องทาง+SMS+ARI-AMC · scam สอดคล้อง 3 ช่องทาง

## Gate + QA ✅
- build ผ่าน · smoke **71/71** · affiliate 19/19 · disclosure ครบ 2 หน้า
- grep `1 แสน`/`100,000` บริบทคลินิกแก้หนี้: **เหลือ 2 hits = ตัวคำถาม FAQ "หนี้เกิน 1 แสนบาท เข้าคลินิกแก้หนี้ได้ไหม?" (visible+JSON-LD) ที่ order สั่งคงคำถามไว้เอง** — คำตอบใหม่บอก 2 ล้านถูกต้อง · นอกนั้น 0 · site-wide บริบทคลินิกแก้หนี้+1แสน ตกค้าง 0
- debt-clinic-sam: 120วัน/2ล้าน/10ปี ครบ 3 จุด (body·FAQ·meta) ✓ · close-debt-fast: บรรทัดยกเว้นจำนำทะเบียนปรากฏจริง ✓
- หมายเหตุ "อัปเดตล่าสุด" close-debt-fast: หน้านี้ไม่มีบรรทัดวันที่คงที่ — ใช้ BUILD_DATE อัตโนมัติ (ณ deploy = ปัจจุบันเสมอ) จึงไม่มีอะไรต้องแก้

## P2 (report-don't-guess) ✅
1. **ebook**: `_social-stage/EBOOK-v1.1-UPDATE-PACK_20260702.md` เป็นแผนอัปเดตที่ครอบเรื่องนี้อยู่แล้ว (มี "ตรวจเงื่อนไขคลินิกแก้หนี้ล่าสุด" + สถานะคุณสู้ฯ) — **การแก้บทในไฟล์อีบุ๊กจริง + อัป Gumroad = งาน owner/Cowork** (ไฟล์ต้นฉบับอีบุ๊กไม่อยู่ใน repo นี้) → เหลือรายการนี้ให้สั่งต่อ
2. **content-packages grep**: พบ 4 ไฟล์ร่างเก่ามี "จ่ายขั้นต่ำ 5%"/"คุณสู้ เราช่วย" → mark แล้วที่ `automation-log/DO-NOT-REUSE_stale-facts_20260724.md` · ระบบมีของดีอยู่แล้ว: `pipeline/comply_gate.py` L65-67 WARN stale-fact ดักสองวลีนี้อัตโนมัติ
3. **kept-savings**: หน้า live **ไม่มีตัวเลขดอกเบี้ยเลย (0 hits ตัวเลข %)** = comply-by-design → ไม่มีอะไรขัดกับประกาศ 4 ก.พ. 69 · ไม่แก้อะไรตามคำสั่ง

## Push + เก็บกวาด
- commit: factfix (build_site.py) + P2/moves — push เดียว (HEAD = report นี้ → trigger Netlify build)
- ย้ายเข้า done/: `order-factfix-20260720.md` + `CC-ORDER_go-factfix-P0_20260724.md` ✓
- live verify หลัง deploy: CC ตรวจ 120วัน/2ล้าน/10ปี + ข้อยกเว้นจำนำทะเบียนบนหน้า live แล้วรายงานในแชท
