# ORDER → CC — metrics upgrade + เก็บกวาดวงจร + sync docs (2026-07-02)
จาก: Cowork (audit ทั้งระบบ 2 ก.ค.) · อ้างอิงฉบับเต็ม: `cc-inbox/CC-TASK_metrics-upgrade_20260702.md` (repo root)

## A) traffic-monitor มองไม่เห็นข้อมูลจริง (หลัก)
- อาการ: traffic-monitor-*.md อ่านแค่ metrics.csv → clicks=0 ทุกวัน ทั้งที่ ga4-funnel.csv มี affiliate_click 69
- แก้: หาสคริปต์ generate traffic-monitor → เพิ่ม section "GA4 (จริง)" อ่าน ga4-funnel/ga4-pages/ga4-metrics.csv + เพิ่มช่อง yt/pinterest/threads + ช่อง sales (Gumroad manual ได้)
- ข้อจำกัด: zero-budget เท่านั้น

## B) เก็บกวาดวงจร CC↔Cowork
1. archive ออเดอร์เก่า >7 วันใน automation-log/cc-inbox → cc-archive (order-20260622-125012, order-art-refined-20260621, order-artupgrade-20260622-110801) ถ้าไม่มีงานค้างจริง
2. cc-outbox 9 ไฟล์ Cowork รีวิวแล้ว → ย้าย cc-archive ยกเว้นธง Stitch fold (รอเจ้าของ) คงไว้
3. commit working tree ค้าง (OPERATING-NOTES, PROJECT-HANDOFF, pipeline/*.py, council log) + push ตาม protocol

## C) sync ข้อเท็จจริงเข้า docs (PROJECT-HANDOFF / OPERATING-NOTES)
- Pantip: กระทู้ 44143972 ถูกลบ (ขายของ/โฆษณา) + บัญชีเคยโดน mod-warning (29 มิ.ย.) → นโยบาย: ห้ามกระทู้มีลิงก์ขาย/ราคา จนกว่าเจ้าของสั่ง
- IG Reel e-book ขึ้นแล้ว: DaRaYRLD80W (2 ก.ค.) cross-post FB+IG · FB Reel ซ้ำไร้แคปชัน (5:39) ลบแล้ว (ถังขยะ 30 วัน)
- Cowork เพิ่มระบบใหม่ 2 ชิ้น (commit ด้วย):
  * `automation-log/launch-status.json` — data source สถานะ launch (Cowork/CC/เจ้าของแก้ไฟล์นี้ → dashboard อัปเดตเอง)
  * `pipeline/dashboard_agent.py` — เพิ่ม `_launch()` render การ์ด "🚀 Launch" จาก JSON (ทดสอบรันแล้ว ผ่าน)
- Cowork ตั้ง scheduled check ฝั่ง Cowork ทุกเช้า 08:00 แล้ว (ตรวจ YT/IG/funnel อ่านอย่างเดียว) — บันทึกใน OPERATING-NOTES กัน monitor ซ้ำซ้อน

## Definition of done
- traffic-monitor รอบถัดไปมี GA4 section + ช่องครบ
- cc-inbox เหลือเฉพาะงาน active · docs sync แล้ว · commit + push เรียบร้อย
- เขียนรายงานผลที่ cc-outbox/CC-report_metrics-upgrade_20260702.md
