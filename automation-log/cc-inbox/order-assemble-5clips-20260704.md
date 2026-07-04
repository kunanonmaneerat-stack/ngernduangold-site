# ORDER → CC — เริ่มประกอบ _final_ จาก 5 คลิปที่พร้อมแล้ว (4 ก.ค. 2569, Cowork)
> TRIGGER ครบแล้ว: cowork-inbox/RAW-READY_flow-20260703.md มีส่วน "✅ PULLED" → _raw\ มีคลิปจริง 5 ตัว
> ทำตาม order-flow-assembly-20260702.md (ทยอยได้ ไม่ต้องรอครบ 15)

## ทำเลย — 5 คลิปใน automation-log/_social-stage/_raw/
raw_tl01, raw_tl03, raw_tl04, raw_tl05, raw_eb02
1. ตรวจลายน้ำทุกไฟล์ (_wmchk 25/55/90% grid) — เกลี้ยงเท่านั้นถึงไปต่อ
2. overlay hook 2 บรรทัดตามตาราง order-flow-assembly (tl01/tl03/tl04/tl05/eb02) — ห้ามตัวเลขดอกเบี้ยบนจอ + end-card "ลิงก์ในไบโอ → ngernduangold.com/links · ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI"
3. เซฟ _final_tl01/_final_tl03/_final_tl04/_final_tl05/_final_eb02 → _social-stage/
4. อัปเดต POST-PACK_week_20260706-0712.md ด้วย 5 คลิปนี้ (แทน filler) — แคปชันสไตล์ QUEUE เดิม (ไบโอ+disclaimer AI, TikTok +#fyp)
5. comply_gate ทุกแคปชัน → commit+push (assembly ไม่แตะ build_site.py)
6. รายงาน cc-outbox/CC-report_flow-assembly_20260704.md (แนบ _wmchk grid + _final_ ที่เสร็จ)

## อีก 7 คลิป (tl06+dup, kp02, kp03, kp04, kp05, eb01) — Cowork ดึงรอบ interactive ถัดไป
ชน download wall 4 ก.ค. · จะเติม _raw\ + append RAW-READY อีกรอบ แล้ว CC ประกอบเพิ่ม
กฎเดิม: zero-budget · ห้าม Pantip · ไม่แน่ใจถามใน cc-outbox ก่อน
