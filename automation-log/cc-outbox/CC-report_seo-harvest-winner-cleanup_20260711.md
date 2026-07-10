# CC report — SEO harvest + ดัน winner + cleanup · 11 ก.ค. 2026

## A) Striking-distance harvest — **property ยังไม่สุก (ยืนยันด้วยข้อมูลจริง)**
- GSC 28 วัน (query+page): **ทั้งหมด 7 row** · filter pos 8–20 AND imp>=30 = **0 row** · แม้ผ่อนเป็น pos 8–20 อย่างเดียวก็ **0 row** (ทุก query อยู่ pos 29–70)
- CSV: `automation-log/striking-distance_20260711.csv`
- ตาม guardrail: **ข้าม A2/A3** (ไม่ fabricate หน้า/คีย์เวิร์ด) — top signal จริงตอนนี้:

| query | page | imp | pos |
|---|---|---|---|
| รถผ่อนไม่หมดจํานําได้ไหม | /car-still-installment-loan-2026 | 18 | 39.2 |
| รถยังผ่อนไม่หมดจํานําได้ไหม | /car-still-installment-loan-2026 | 17 | 38.4 |
| เงินเดือน 30000 วงเงินบัตรเครดิต | /credit-card-salary-30000-2026(.html) | 8+4 | 29.8/33.8 |

หมายเหตุ: 2 หน้านี้ถูก on-page optimize ไปแล้วรอบ 10 ก.ค. (title/meta/FAQ) — รอ Google recrawl · weekly-review จะจับ pos 8–20 อัตโนมัติเมื่อ property โต

## B) Winner internal links — **เกินเป้าอยู่แล้ว ไม่ต้องเพิ่ม**
| หน้า | เป้า | ก่อน (10 ก.ค.) | หลัง (วันนี้) |
|---|---|---|---|
| /kept-savings-2026 | >=8–10 หน้า | 19 หน้า | **19 หน้า (21 ลิงก์)** |
| /debt-calculator | ครบ cluster | 13+ | **61 หน้า (77 ลิงก์)** |
- calc banner "ต้นบทความ" บน debt-cluster: **9/9** (CALC_CLUSTER ตัวจริงใน build_site.py)

## C) Cleanup
1. **netlify.app -> ngernduangold.com**: source พบ 6 จุด → แก้ 3 (README.md build-cmd · tiktok-pipeline/README.md bio · ready-for-cowork/UPLOAD-CHECKLIST.md ← ตัวเสี่ยงสุด Cowork copy ลง bio ได้) · คงไว้ 3 โดยตั้งใจ: OPERATING-NOTES.md (bug-log ประวัติศาสตร์) + pipeline/_pantip_scrape_out.json + _draft.txt (untracked scratch/บันทึกโพสต์จริงที่โพสต์ไปแล้ว — ห้าม rewrite)
2. **AXA PA `/go/PhAKgrKX` = แคมเปญถูกต้อง ยืนยันแล้ว**: atth.me ตอบ 200 + meta-refresh → `https://www.axa.co.th/personal-accident-protection?...atnct1=...atnct2=...` = **Personal Accident จริง** พร้อม AccessTrade tracking params ครบ · checker ครอบคลุม format นี้
3. **check_affiliate_links = 17/17, 0 problem** ✅

## D) Gates + verify
- comply_gate self-test OK (ไม่มีหน้า content ถูกแตะรอบนี้) · smoke **62/62** · link_check **0 broken / 0 route**
- build_site.py **ไม่ถูกแก้รอบนี้** (B เกินเป้าอยู่แล้ว ไม่มี code change) → ไม่มี deploy commit · commit นี้ = docs+CSV+report เท่านั้น (Netlify จะโชว์ Canceled = expected)
- Live sample 3 หน้า: debt-consolidation (FAQ-LD ✓ kept-link ✓ calc-banner ✓ kashjoy ✓) · car-still (FAQ-LD ✓ title-query ✓ affiliate ✓) · kept-savings (affiliate ✓ disclosure ✓ canonical extensionless ✓)

**Owner action เดิมยังค้าง**: GSC UI Request-Indexing `/credit-card-salary-30000-2026` + re-submit sitemap
