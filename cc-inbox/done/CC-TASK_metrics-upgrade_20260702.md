# CC TASK — ยกระดับการวัดผล + เก็บกวาดวงจร (จาก Cowork audit 2026-07-02)
ที่มา: audit ทั้งระบบพบว่า traffic-monitor รายวันมองไม่เห็นข้อมูลจริง

## A) รวม GA4 เข้ารายงานรายวัน (หลัก)
ปัญหา: traffic-monitor-*.md อ่านแค่ metrics.csv → รายงาน clicks=0 ทุกวัน
ทั้งที่ GA4 จริง (ga4-funnel.csv): quiz_start 4 · quiz_complete 3 · affiliate_click 69
งาน:
1. หาสคริปต์ที่ generate traffic-monitor (คาดว่าใน pipeline/ หรือ tools/)
2. เพิ่ม section "GA4 (จริง)" ในรายงาน: อ่าน ga4-funnel.csv + ga4-pages.csv + ga4-metrics.csv ถ้าไฟล์มี
3. เพิ่มช่อง yt / pinterest / threads ใน per-channel table (จาก post-ledger ถ้า track ได้ หรือ mark n/a)
4. ถ้ามีทาง pull ยอดขาย Gumroad ฟรี (CSV export manual ก็ได้) เพิ่มบรรทัด "sales" — ถ้าไม่มี ให้ทำช่องว่างไว้ + note ให้เจ้าของกรอก
ข้อจำกัด: zero-budget เท่านั้น ห้ามเพิ่ม dependency เสียเงิน

## B) เก็บกวาดวงจร CC↔Cowork
1. archive ออเดอร์เก่า >7 วันใน automation-log/cc-inbox → cc-archive (3 ไฟล์: order-20260622-125012, order-art-refined-20260621, order-artupgrade-20260622-110801) ถ้าไม่มีงานค้างจริง
2. cc-outbox 9 ไฟล์: Cowork รีวิวแล้วรอบนี้ — ย้ายไป cc-archive ได้ ยกเว้นธงที่รอเจ้าของ (Stitch fold) คงไว้
3. commit working tree ที่ค้าง (OPERATING-NOTES, PROJECT-HANDOFF, pipeline/*.py, council log) ตาม protocol ปกติ

## C) sync ข้อเท็จจริงเข้า docs
- PROJECT-HANDOFF.md / OPERATING-NOTES.md: อัปเดตสถานะ Pantip = กระทู้ 44143972 ถูกลบ (ขายของ/โฆษณา) + บัญชีเคยโดน mod-warning (29 มิ.ย.) → นโยบายใหม่: ห้ามกระทู้ที่มีลิงก์ขาย/ราคา จนกว่าเจ้าของสั่ง
- IG Reel e-book ขึ้นแล้ว: DaRaYRLD80W (2 ก.ค.) — cross-post FB+IG สำเร็จผ่าน Business Suite composer
- อ้างอิงฉบับเต็ม: outputs ของ Cowork session ล่าสุด `SESSION-HANDOFF_20260702-v2.md`

## Definition of done
- traffic-monitor รอบถัดไปโชว์ GA4 section + ช่องครบ
- cc-inbox เหลือเฉพาะงาน active · commit + push เรียบร้อย
