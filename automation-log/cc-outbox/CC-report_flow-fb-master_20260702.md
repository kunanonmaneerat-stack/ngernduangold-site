# CC report — flow-fb-master งาน A+B (order-flow-fb-master-20260702) — B พร้อมใช้แล้ว · A = WAIT ตามเงื่อนไข
executed: 2026-07-02 ค่ำ · zero-budget ✓ · Pantip ไม่แตะ ✓ · build_site.py ไม่แตะ (ตามคาด) ✓ · CC ไม่โพสต์ FB เอง ✓

## งาน A — ประกอบคลิป: ⏳ WAITING FOR TRIGGER (ถูกต้องตาม order)
- ตรวจแล้ว: `cowork-inbox/RAW-READY_flow-*.md` **ยังไม่มี** -> ยังไม่เริ่ม (order ห้ามเริ่มก่อน trigger — คลิปดิบยังอยู่บน cloud)
- เตรียมพร้อมแล้วฝั่ง CC: ตาราง overlay 15 บรรทัดอ่านแล้ว · โฟลว์ _wmchk 25/55/90% + crop/แถบทับ = pattern ชุด dc/sp เดิม · ปลายทาง _social-stage + POST-PACK_week_20260706-0712 (จะแทน filler 11-12 + เติม 13-19 ก.ค. เมื่อคลิปมา)
- เมื่อ RAW-READY โผล่: CC เริ่มทันทีเฉพาะคลิปที่ระบุพร้อม (ทยอยได้) -> รายงาน CC-report_flow-assembly_<date>.md พร้อม _wmchk grid

## งาน B — FB queue support: ✅ ทั้ง 2 ข้อ
### B1 link-health รายวันก่อน 08:00
- สร้าง `pipeline/fb_queue_linkcheck.py` (stdlib, $0): ยิงทุกหน้าปลายทางในคิว (title-loan / kept-savings / debt-consolidation / emergency-fund / credit-bureau-check / park-money / links) เช็ก 200+เนื้อหา -> เขียน `cowork-inbox/linkhealth-fb-<date>.md` · มีลิงก์พัง = ไฟล์ติดธง ⚠️ + exit 1
- **รันแล้ววันนี้: ✅ 7/7 หน้า = HTTP 200** (linkhealth-fb-2026-07-02.md)
- ตารางอัตโนมัติ: **wired เข้า run_daily.cmd แล้ว** (รันทุกวัน ~05:02 = ก่อน 08:00 เสมอ, ไม่ต้องสร้าง task ใหม่/ไม่แตะ scheduler) — เพิ่ม 2 บรรทัดหลัง ga4_pull, logic อื่นไม่แตะ
### B2 record หลังโพสต์จริง
- โปรโตคอลพร้อม: เมื่อ `cowork-inbox/fb-posted-<date>.md` โผล่ -> CC รัน `post_ledger.record_text_post('facebook', <text>, source='queue-<date>')` — **ไม่ record ก่อนโพสต์จริง**
- สถานะวันนี้: ledger มี fb 2 แถวแล้ว (day-1 sprint = CC backfill ตอนบ่าย + ประกาศ e-book v1.1 = Cowork record เองแล้ว 18:17) -> วันนี้ครบ ไม่ record ซ้ำ (dedup ก็กันอยู่แล้ว)
- สังเกต: Cowork แก้คิว 3 ก.ค. (Threads = ประกาศ v1.1) แล้ว — text-dedup จะกันชนกับโพสต์ FB ประกาศเมื่อวานให้อัตโนมัติถ้าข้อความคล้าย >90% ข้ามช่องไม่ชน (คนละ channel)

## คำถามเปิด (ไม่เดา — ตอบใน cc-inbox ได้)
ไม่มีที่ block งาน · จุดเดียวที่เลือกเอง: ตารางเวลา link-health ใช้ run_daily 05:02 (option "เพิ่มใน scheduled ที่มีอยู่") แทนการสร้าง cron ใหม่ — ถ้าต้องการเวลาอื่น/เพิ่มรอบ บอกได้
