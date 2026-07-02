# ORDER → CC — บังคับใช้ POSTING-POLICY + เก็บงานค้างวันนี้ (2026-07-02 บ่าย)
จาก: Cowork ตาม OWNER-MANDATE · อ้างอิง: automation-log/POSTING-POLICY_antispam_20260702.md (อ่านก่อนเริ่ม)
บริบทเร่งด่วน: Pantip แจ้ง FINAL WARNING เป็นทางการวันนี้ — ผิดซ้ำครั้งเดียว = แบนถาวร ทั้งระบบต้องมี guard กันพลาดระดับโค้ด ไม่พึ่งความจำ

## PART A — text-dedup กันโพสต์ข้อความซ้ำ (เหตุ: Threads ซ้ำ 4 โพสต์ 23 มิ.ย.)
A1. อ่าน automation-log/post_ledger.py + post-ledger.jsonl เข้าใจ schema ปัจจุบัน (ตอนนี้กันซ้ำเฉพาะคลิป ±16 วัน)
A2. เพิ่มฟังก์ชัน `is_duplicate_text(channel, text, days=30)`:
   - normalize: ตัดช่องว่าง/อีโมจิ/URL ออกก่อนเทียบ → hash (sha1 ของ normalized text)
   - เทียบกับ ledger ย้อนหลัง 30 วันในช่องเดียวกัน · เกณฑ์ซ้ำ: hash ตรง หรือ similarity ≥0.9 (difflib.SequenceMatcher)
A3. บันทึกทุกโพสต์ใหม่ลง ledger พร้อม field: channel, text_hash, text_first80, ts
A4. เชื่อมเข้า comply_gate: ถ้า duplicate → GATE_FAIL พร้อมเหตุผล + ชี้โพสต์เดิมที่ชนกัน
A5. Unit test สั้น: เคสซ้ำเป๊ะ / ซ้ำ 95% / ต่างช่องกัน (ต้องผ่าน) / ผ่าน 31 วัน (ต้องผ่าน)
A6. Backfill: เพิ่ม entry ของโพสต์ที่ลงแล้ววันนี้ (FB 1, Threads 1, พิน 2 — ดู launch-status) กัน agent อื่นลงซ้ำพรุ่งนี้

## PART B — โควตา/วัน เข้า qa_gate
B1. อ่าน pipeline/qa_gate.py หา hook ที่เหมาะ (จุดตรวจก่อนอนุมัติ content package)
B2. เพิ่ม check `posting_quota(channel)`: อ่าน ledger วันนี้ · เกณฑ์จาก POSTING-POLICY: ทุกช่อง ≤2/วัน (pinterest ≤5) + ห่างขั้นต่ำ 3 ชม.
B3. เกินโควตา → FAIL พร้อมเวลาที่โพสต์ได้ครั้งถัดไป
B4. Hard-block Pantip: channel=pantip → FAIL เสมอ พร้อมข้อความ "FROZEN until 2026-07-16 (POSTING-POLICY)" — เอาออกได้เฉพาะเจ้าของแก้ policy file เอง

## PART C — audit AUTO-DM
C1. อ่าน automation-log/AUTO-DM-SETUP-2026-06-21.md → สรุปว่าระบบนี้ถูก activate จริงไหม ที่ไหน (ManyChat? script? หรือแค่แผน)
C2. ถ้า active: ตรวจว่ามี rate-limit + ข้อความแรกเป็น opt-in ("พิมพ์ เช็กสิทธิ์ เพื่อรับ..." = ผู้ใช้เริ่มเอง ถือว่า ok แต่ต้องหน่วง ≥30 วิ ก่อนตอบ + ไม่ follow-up ซ้ำเกิน 1 ครั้ง) — ถ้าไม่มี ให้เพิ่ม/ปิดชั่วคราวแล้วรายงาน
C3. ถ้าไม่ active: บันทึกใน report ว่า "ยังไม่เปิดใช้ — ก่อนเปิดต้องทำตาม C2" พอ

## PART D — ร่าง Pantip เวอร์ชันไร้แบรนด์ (เตรียมไว้ใช้หลัง 16 ก.ค. ไม่โพสต์ตอนนี้)
D1. แก้ social-review/pantip/draft-thread_debt-system_20260702.md: ตัดประโยคที่เอ่ย "เงินเดือนสมองทอง" ออกทั้งประโยค (ทีมเพจ...หลักเดียวกัน) — เนื้อหาที่เหลือต้องอ่านลื่นเหมือนไม่เคยมี
D2. เดียวกันกับ draft-thread_high-yield-savings_20260702.md (ถ้ามี brand/ชื่อผลิตภัณฑ์ เช่น Kept — แทนด้วยคำกลาง "บัญชีออมดอกสูงของธนาคาร")
D3. หัวไฟล์ทั้งสอง: เปลี่ยน note เป็น "de-branded แล้ว · FROZEN ถึง 16 ก.ค. ขั้นต่ำ · เจ้าของโพสต์มือเท่านั้น · ห้ามแบรนด์/ลิงก์/ราคาเด็ดขาด"

## PART E — sync docs + commit/push
E1. PROJECT-HANDOFF.md + OPERATING-NOTES.md: เพิ่ม section วันนี้ — Pantip FINAL WARNING (ผิดซ้ำ=แบนถาวร, freeze ถึง 16 ก.ค.+, กติกาใหม่อยู่ POSTING-POLICY) + มีไฟล์ POSTING-POLICY เป็น source of truth การโพสต์
E2. Commit ไฟล์ใหม่ทั้งหมดของวันนี้: POSTING-POLICY, OWNER-MANDATE, consult-gemini-3.5ext, order 3 ไฟล์ (revenue-sprint เสร็จแล้ว/flow-assembly/อันนี้), launch-status, flow-credits, dashboard_agent patch ที่ยังไม่ push (ถ้าเหลือ)
E3. กติกา push: commit ที่แตะ build_site.py/site ต้องเป็น commit สุดท้าย — รอบนี้ไม่มีไฟล์ deploy = push ได้เลยไม่ trigger Netlify
E4. รายงาน: cc-outbox/CC-report_antispam-enforcement_20260702.md — ผล A-E, จุดที่ตัดสินใจเอง, สิ่งที่เหลือ

## ห้าม
แตะ Pantip บนเว็บทุกกรณี · ปิดการ์ด zero-budget · แตะ secrets · deploy
## Definition of done
comply_gate ตก duplicate จริง (test ผ่าน) · qa_gate ตกโควตา+Pantip จริง · ร่าง Pantip ไร้แบรนด์ · docs sync · push เรียบร้อย
