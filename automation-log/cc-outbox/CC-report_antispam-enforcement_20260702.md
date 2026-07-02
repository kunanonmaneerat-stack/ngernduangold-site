# CC report — antispam enforcement A-E (order-antispam-enforcement-20260702) — ✅ ครบ · guards ทำงานจริง
executed: 2026-07-02 บ่าย · ไม่แตะ Pantip เว็บ ✓ · zero-budget guards เดิมไม่แตะ ✓ · secrets ไม่แตะ ✓

## A) text-dedup ✅ (post_ledger + comply_gate)
- post_ledger.py ใหม่: normalize_text (ตัด URL/อีโมจิ/ช่องว่าง เหลือ letters+digits casefold — แก้เครื่องสำอางค์หนี dedup ไม่ได้),
  text_hash (sha1), is_duplicate_text(channel,text,days=30) = hash ตรง หรือ difflib similarity >=0.9 ในช่องเดียวกันย้อน 30 วัน,
  record_text_post (fail-closed: ปฏิเสธ dup เอง) เก็บ field: type=text, channel, text_hash, text_norm, text_first80, ts, source
- comply_gate.check_post(text, channel): เช็กเนื้อหา (check เดิม) + dedup — duplicate -> GATE_FAIL พร้อมชี้โพสต์เดิม (เวลา+80 ตัวอักษรแรก)
- unit test pipeline/test_text_dedup.py: **6/6 PASS** (ซ้ำเป๊ะ/ซ้ำหลัง normalize/คล้าย 95% = บล็อก · ต่างช่อง/เก่า 31 วัน/ข้อความใหม่ = ผ่าน)
- BACKFILL วันนี้ 4 รายการ (source=backfill-cowork-20260702): fb 1 (sprint day1) + threads 1 + pinterest 2 (พิน kept/title-loan)
  -> ยิงซ้ำถูกปฏิเสธจริง + check_post(fb ข้อความเดิม) = GATE_FAIL จริง (ทดสอบแล้ว)
- แถมแก้บั๊กแฝง: iter_ledger/load_index เดิม bind LEDGER ตอน def (default-arg) -> monkeypatch/ทดสอบไม่เห็นผล — แก้เป็น resolve ตอน call

## B) โควตา/วัน + Pantip hard-block ✅ (qa_gate)
- qa_gate.posting_quota(channel) + CLI `python pipeline/qa_gate.py --quota <ch>` (exit 2 = FAIL):
  ทุกช่อง <=2/วัน (pinterest <=5) + เว้นขั้นต่ำ 3 ชม. + FAIL บอกเวลาโพสต์ได้ครั้งถัดไปเสมอ
- **Pantip hard-block: FAIL เสมอ "FROZEN until 2026-07-16 (POSTING-POLICY)"** — ปลดได้เฉพาะเจ้าของแก้ policy file
- ทดสอบจริง: pantip=FAIL(exit2) ✓ · โควตาเต็ม 2/2=FAIL+บอกพรุ่งนี้ 08:00 ✓ · gap 1 ชม.=FAIL+บอกเวลา ✓ · gap 5 ชม.=ผ่าน ✓ · fb จริงวันนี้ 1/2=ผ่าน ✓
- regression: clip-dedup เดิมไม่แตะ (post_ledger check tiktok/debt = COLLISION เหมือนเดิม, test 6/6)

## C) AUTO-DM audit ✅ (สถานะ: ACTIVE — เหลืองาน dashboard ฝั่งเจ้าของ)
- ระบบ = CreatorFlow Free (ไม่ใช่ ManyChat/script) — "Comments -> DM" สถานะ **Live ตั้งแต่ 2026-06-21** บน IG @ngernduangold
  trigger ทุกโพสต์/Reel keyword เช็กสิทธิ์/เช็คสิทธิ์/สนใจ · เพดาน 500 DM/เดือน (rate ceiling ในตัว)
- opt-in: ✓ ผ่านเกณฑ์ order (ผู้ใช้คอมเมนต์ keyword เอง = ผู้ใช้เริ่ม)
- ❗ยังยืนยันไม่ได้จาก CC (ตั้งค่าอยู่ใน CreatorFlow dashboard บัญชีเจ้าของ — CC ไม่มีทางเข้า): delay >=30 วิ + follow-up <=1 ครั้ง
  -> ACTION เจ้าของ (~3 นาที): เปิด creatorflow.so -> Automations -> ตั้ง delay/จำกัด follow-up
- ❗BUG พบระหว่าง audit: ปุ่ม DM ลิงก์ **ngernduangold.netlify.app/quiz (โดเมนเก่า)** -> เจ้าของแก้เป็น ngernduangold.com/quiz ใน flow เดียวกัน

## D) ร่าง Pantip de-branded ✅ (FROZEN — ไม่โพสต์)
- ทั้ง 2 ไฟล์ใน social-review/pantip/: ตัดประโยคแบรนด์ออกทั้งประโยค อ่านลื่นเหมือนไม่เคยมี (d1: "...spreadsheet ของตัวเอง จนตอนนี้กลายเป็นนิสัยไปแล้ว")
- VERIFIED ทั้งคู่: แบรนด์=0 · ลิงก์=0 · ราคา=0 · ชื่อผลิตภัณฑ์=0 · comply_gate OK · header ใหม่ "de-branded · FROZEN ถึง 16 ก.ค. ขั้นต่ำ · เจ้าของโพสต์มือเท่านั้น"

## E) docs + commit/push ✅
- PROJECT-HANDOFF + OPERATING-NOTES: section 2026-07-02 (บ่าย) — FINAL WARNING, freeze 16 ก.ค.+, POSTING-POLICY = source of truth, guards ใหม่, AUTO-DM actions
- commit รวมไฟล์ใหม่วันนี้: POSTING-POLICY, OWNER-MANDATE_20260702, consult-gemini-3.5ext, order antispam + flow-assembly, launch-status, dashboard.html, guards ทั้งหมด
- NOTE E3: push รอบนี้มีไฟล์ root (docs) -> Netlify จะ build แต่ build_site.py ไม่เปลี่ยน = deploy ซ้ำเนื้อหาเดิม (ไม่มี site change; ไม่ใช่ deploy ฟีเจอร์)

## จุดที่ตัดสินใจเอง
- text_norm เก็บ normalized text เต็มในแถว ledger (จำเป็นต่อ similarity เทียบย้อนหลัง; เป็นข้อความโพสต์สาธารณะ ไม่มี PII)
- infra-fail ใน check_post (import ledger ไม่ได้) = append WARN ไม่ flip GATE_FAIL (duplicate เท่านั้นที่ FAIL ตาม order) — ledger อยู่ใน repo เดียวกัน โอกาสเกิดต่ำ
- pinterest pins backfill ใช้ข้อความบรรยายพิน (ไม่มีต้นฉบับ exact caption) — hash กันซ้ำที่ระดับ "พินเดิมซ้ำ" ได้เมื่อใช้ข้อความเดิมโพสต์ซ้ำ
## เหลือ (เจ้าของ): CreatorFlow 2 อย่างข้างบน · กด "รับทราบ" warning บน Pantip เว็บเอง (CC ห้ามแตะ)
