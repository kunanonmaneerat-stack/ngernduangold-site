# ORDER (MASTER) → CC — Flow assembly + FB queue support (2 ก.ค. 2569, จาก Cowork ตามที่เจ้าของสั่ง)
> อ่านคู่กับ order-flow-assembly-20260702.md (ตาราง overlay 15 บรรทัด = รายละเอียด) · ฉบับนี้ = ลำดับ+เงื่อนไข+การแบ่งงานที่ถูกต้อง
> กฎเดิมยึดทุกข้อ: zero-budget (การ์ด free_ai.py ห้ามปิด) · ห้ามแตะ Pantip · ห้าม push commit ที่แตะ build_site.py ปนกับ commit อื่น (ต้องเป็น HEAD สุดท้ายเดี่ยวๆ — Netlify ignore rule) · ห้ามวางคีย์ในแชต

## 🔒 การแบ่งงาน (สำคัญ — อย่าสลับ)
- **Flow gen คลิปดิบ = Cowork ทำเอง** (ผ่าน browser labs.google) — CC ไม่มี Flow access ห้ามพยายาม gen
- **ประกอบ _final_ = CC** — เริ่มได้ก็ต่อเมื่อ Cowork ดาวน์โหลดคลิปดิบมาวางแล้วเท่านั้น

## สถานะ Flow ปัจจุบัน (2 ก.ค. ~17:00)
- โปรเจกต์ "02 ก.ค. 11:15" มี 15 media · ส่ง prompt ครบ 11 ฉากแล้ว: tl01–tl08 + kp01–kp03 (บางตัวยัง queued/active)
- **ขาด gen อีก 4 ฉาก** (Cowork ทำรอบหน้าเมื่อ backend หาย): kp04, kp05, eb01, eb02
- เครดิตเหลือ **259** (พอ 4 ฉาก × 15 = 60 + buffer retry) — ตั้ง output ×1 เสมอ กันเครดิตคูณ

---

## งาน A — ประกอบคลิป _final_ (CC เริ่มเมื่อถูก trigger)
**TRIGGER:** ไฟล์ `automation-log/cowork-inbox/RAW-READY_flow-<date>.md` โผล่ (Cowork เขียนหลังดาวน์โหลด+วางคลิปดิบเสร็จ ระบุ path โฟลเดอร์ดิบ + รายชื่อไฟล์ที่พร้อม) · **ห้ามเริ่มก่อน trigger** (คลิปยังไม่ครบ/ยังอยู่บน cloud)

ทำตาม order-flow-assembly-20260702.md ขั้น 1–6 กับ **เฉพาะคลิปที่ RAW-READY ระบุว่าพร้อม** (ทยอยได้ ไม่ต้องรอครบ 15):
1. ตรวจลายน้ำทุกไฟล์ (pattern `_wmchk` เดิม: แคปเฟรม 25/55/90% → grid) — ผ่านเท่านั้นถึงไปต่อ · ตัวไหนเจอลายน้ำ crop/แถบทับตาม workflow เดิม
2. overlay hook 2 บรรทัดตามตารางใน order-flow-assembly (ห้ามตัวเลขดอกเบี้ยบนจอ/ซับ) + end-card CTA "ลิงก์ในไบโอ → ngernduangold.com/links" + บรรทัดเล็ก "ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI"
3. เซฟ `_final_<id>.mp4` → `automation-log/_social-stage/`
4. อัปเดต `POST-PACK_week_20260706-0712.md`: แทน filler ด้วยคลิปจริง + เติมตาราง 13–19 ก.ค. (สลับ tl/kp, eb คู่ศุกร์-เสาร์) แคปชันสไตล์ QUEUE เดิม (ไบโอ+disclaimer AI, TikTok +#fyp)
5. `comply_gate` ทุกแคปชัน → commit+push (deploy-commit-last)
6. รายงาน `cc-outbox/CC-report_flow-assembly_<date>.md` (แนบ _wmchk grid + รายการ _final_ ที่เสร็จ + ที่ยังขาด)

**DoD งาน A:** _final_ ครบตามที่ RAW-READY ส่งมา · ลายน้ำเกลี้ยงทุกตัว · POST-PACK อัปเดต · commit+push · รายงานออก

---

## งาน B — FB queue 3–8 ก.ค. (บทบาท CC = สนับสนุน ไม่ใช่โพสต์เอง)
**การโพสต์ FB = Cowork ทำหลังเจ้าของยืนยันในแชตรายวัน** (คงเดิม) — CC **ห้ามโพสต์ FB เอง**
CC ทำ 2 อย่างเพื่อกันพลาด:
1. **Link-health รายวัน (เพิ่มใน scheduled ที่มีอยู่ หรือรันเมื่อสั่ง):** ยิง HEAD/GET หน้าปลายทางในคิววันนั้นจาก QUEUE_fb-threads_20260702-0708.md (title-loan-2026, kept-savings-2026, debt-consolidation-2026, emergency-fund-2026, credit-bureau-check-2026, park-money-high-interest-2026, /links) → ถ้าไม่ใช่ 200 แจ้ง cowork-inbox ก่อน 08:00 กันโพสต์ลิงก์ตาย
2. **หลัง Cowork รายงานว่าโพสต์แล้ว** (ไฟล์ cowork-inbox/fb-posted-<date>.md): บันทึก `post_ledger.record_text_post('facebook', <text>, source='queue-<date>')` เพื่อ dedup ไม่ให้ธีมซ้ำ · อย่า record ก่อนโพสต์จริง

**DoD งาน B:** รายงาน link-health รายวันก่อน 08:00 · ledger อัปเดตหลังโพสต์จริงทุกวัน · ไม่มี CC โพสต์ FB เอง

---

## ลำดับความสำคัญ + หมายเหตุ
- งาน B (link-health) เดินทุกวันอยู่แล้ว · งาน A รอ trigger RAW-READY (อาจ 3–4 ก.ค. แล้วแต่ Flow หาย)
- ทุก commit: แยก build_site.py ออกเป็น HEAD สุดท้ายถ้าจำเป็น (รอบนี้ assembly ไม่ควรแตะ build_site.py เลย — แค่ _social-stage + POST-PACK)
- ไม่แน่ใจอะไรถามกลับใน cc-outbox ก่อนทำ อย่าเดา
