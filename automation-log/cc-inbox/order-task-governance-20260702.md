# ORDER → CC — Governance ของ scheduled tasks ทั้งเครื่อง (2026-07-02 ~15:00) 🔴 มี deadline 18:00
จาก: Cowork · เหตุ: พบ scheduled tasks ~40 ตัวใน C:\Users\nL_ku\Claude\Scheduled\ หลายตัวเกิดก่อน Pantip FINAL WARNING และก่อน POSTING-POLICY — เสี่ยงชนนโยบายใหม่
สิ่งที่ Cowork ทำแล้ว: pause `ngernduangold-social-ops-daily` (ตัวที่โพสต์ Pantip จริงทุกเช้า 08:02) — ตัวอื่นยังไม่ถูกแตะ

## A) Audit ทุก task (อ่าน C:\Users\nL_ku\Claude\Scheduled\*\SKILL.md ทั้งหมด)
สร้างตาราง: taskId · enabled? · ช่องที่แตะ · โพสต์อัตโนมัติไหม · อ้าง comply_gate/qa_gate ใหม่ไหม · ความเสี่ยง (สูง=โพสต์เอง/แตะ Pantip, กลาง=แนะนำให้โพสต์, ต่ำ=อ่านอย่างเดียว)

## B) แก้ prompt เฉพาะตัวที่ enabled และแตะการโพสต์/แนะนำโพสต์ 🔴 ทำก่อน 18:00
ตัวที่รู้แน่ว่าต้องแก้ (จาก list เมื่อ 15:00): `ngernduangold-evening-check` (รัน 18:07 วันนี้ — prompt เดิมเตือนงาน Pantip!) · `ngernduangold-channel-heartbeat` (21:00 เช็ก cadence รวม Pantip — จะฟ้อง Pantip เงียบทุกวัน) · `ngernduangold-threads-refill-weekly` (อาทิตย์ — เติมคิว Threads ต้องผ่าน dedup) · `ngernduangold-pinterest-weekly` (อาทิตย์) · `pantip-daily-opportunity` (ร่างอย่างเดียวแต่ควรรู้ freeze) · `ngernduangold-weekly-review`, `ig-weekly-pulse`, `ngernduangold-video-post-verify`, `ngernduangold-tiktok-daily-nudge` (ตรวจแล้วแก้ตามเห็นควร)
วิธีแก้: เพิ่มบล็อกมาตรฐานไว้บนสุดของ prompt ใน SKILL.md (แก้ไฟล์ตรงได้ ไม่ต้องผ่าน tool scheduler):
"""⛔ POSTING-POLICY (2 ก.ค. 2026): อ่าน C:\Users\nL_ku\ngernduangold-site\automation-log\POSTING-POLICY_antispam_20260702.md ก่อนทุกครั้ง · Pantip FROZEN ถึง 16 ก.ค. — ห้ามโพสต์/ห้ามแนะนำให้โพสต์/ถือว่า cadence Pantip = 0 โดยตั้งใจ · ก่อนโพสต์ช่องใดๆ ต้องรัน `py pipeline\qa_gate.py --quota <ช่อง>` (exit≠0 = ห้ามโพสต์) และข้อความต้องผ่าน comply_gate text-dedup"""
ห้ามเปลี่ยน logic อื่นของ task โดยไม่จำเป็น — เพิ่ม guard block พอ

## C) ร่าง prompt ใหม่ให้ social-ops-daily (เสนอ ไม่เปิดใช้เอง)
เวอร์ชันใหม่: ตัด Pantip ออกทั้งหมด → เหลือ Threads 1/วัน (ผ่าน qa_gate+dedup) + เฝ้า GA4 · แนบไว้ใน report ให้เจ้าของ/Cowork ตัดสินใจเปิด

## D) รายงาน + commit
- cc-outbox/CC-report_task-governance_20260702.md: ตาราง audit + รายการที่แก้ + diff ตัวอย่าง 1 ตัว + ร่าง social-ops ใหม่
- ไฟล์ SKILL.md อยู่นอก repo — ไม่ต้อง commit แต่ให้ copy ตาราง audit ลง report (ใน repo) · commit เฉพาะ order/report ตามปกติ
ห้าม: เปิด/ปิด task เอง (แก้ได้แค่เนื้อ prompt) · แตะ Pantip เว็บ · secrets · deploy

## Definition of done
ทุก task ที่ enabled และแตะการโพสต์มี guard block ก่อน 18:00 · ตาราง audit ครบทุก task · ร่าง social-ops ใหม่พร้อมรีวิว
