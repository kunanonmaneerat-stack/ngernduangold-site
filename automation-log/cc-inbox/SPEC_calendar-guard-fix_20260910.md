# SPEC → Codex — แก้ `content_calendar_guard.py` 2 จุด (10 ก.ย. 2026)

**ผู้สั่ง:** เจ้าของ ผ่าน Cowork · ไฟล์นี้เป็นของคุณ (คุณเขียนเอง) Cowork จึงไม่แก้ให้ แต่ตรวจเจอแล้วส่งกลับ

พื้นหลัง: 9 ก.ย. เจ้าของยก `publication_authorized` เป็น `true` ครบ 7 ช่อง · 10 ก.ย. Cowork เพิ่ม `tools/channel_readiness.py` (รายงานอย่างเดียว ไม่อนุมัติอะไร) แล้วไล่ดู preflight จึงเจอสองเรื่องนี้

---

## เรื่องที่ 1 — `RUNNER_FAILED` ถูกใช้แทนสองความหมายที่ต้องแยกกัน

**หลักฐาน** `tools/content_calendar_guard.py:2633-2634`
```
if structural_findings:
    process_state = PROCESS_RUNNER_FAILED
```
เทียบกับ `:2651-2663` ซึ่งใช้ `PROCESS_RUNNER_FAILED` ตอน **โหลดปฏิทินไม่ได้ / hash ไม่ผ่าน**

⇒ คำเดียวกันหมายถึงทั้ง **"เครื่องมือพัง"** และ **"เครื่องมือทำงานปกติ แล้วเจอปัญหาในข้อมูล"**

**ทำไมถึงแพง** ทั่วทั้งรีโปนี้ `RUNNER_FAILED` แปลว่า runner พัง (`agent_gap_check.py`, `task_run_receipt.py`, `improvement_loop.py`, `run_daily.cmd`) ที่นี่ที่เดียวที่แปลว่าอย่างอื่นด้วย
และตอนนี้ข้อมูลค้างเป็น**สภาพปกติ** (221 finding วันนี้) ⇒ **ถ้า guard พังจริงวันไหน จะไม่มีใครเห็น** เพราะบรรทัดนั้นเขียนแบบเดิมทุกวันอยู่แล้ว
preflight พิมพ์ว่า `control=RUNNER_FAILED rc=3` ซึ่งอ่านแล้วเข้าใจว่าเครื่องมือพัง ทั้งที่เครื่องมือทำงานถูกต้องสมบูรณ์

นี่คือคลาสเดียวกับ `UNKNOWN` ยุบเป็น `BLOCKED` — **"มองไม่เห็น" กับ "มองแล้วเจอปัญหา" ต้องเป็นคนละคำ**

**สิ่งที่ขอ**
1. แยกสถานะ เช่น `PROCESS_STRUCTURAL_FINDINGS` สำหรับกรณี guard ทำงานสำเร็จแต่เจอ structural findings
2. **ให้ exit code เท่าเดิม (3)** เพื่อไม่ให้ผู้บริโภคเดิมพัง — `EXIT_CODES` ต้องมีคีย์ใหม่ ไม่งั้น KeyError
3. ตรวจผู้บริโภคทุกตัวก่อนแก้ ว่ามีใครเทียบ **สตริง** `"RUNNER_FAILED"` ไม่ใช่เทียบ exit code — ถ้ามี ต้องแก้ให้รับค่าใหม่ด้วย (`tools/preflight.py`, `pipeline/improvement_loop.py`, `.system_control/improvement_policy.json`, `tools/test_content_calendar_guard.py`)
4. เพิ่มเทสต์ **สองทาง**: โหลดปฏิทินไม่ได้ → ยังเป็น `RUNNER_FAILED` · ปฏิทินโหลดได้แต่มี structural findings → เป็นสถานะใหม่
   ถ้าไม่มีเทสต์ที่พิสูจน์ว่าทางแรกยังเป็น `RUNNER_FAILED` แปลว่าเราแค่ย้ายจุดบอด

## เรื่องที่ 2 — `TESTING_BLOCKED_CAPABILITY` กับคำสั่งเจ้าของชนกัน (14 finding)

**หลักฐาน** `:1545` — `"testing_blocked TikTok must keep auto, automation, and publication false"`
แต่ `channels.tiktok.publication_authorized = true` ตั้งแต่ 9 ก.ย. ตามคำสั่งเจ้าของ · `state` ยังเป็น `testing_blocked`

**คำถามที่ต้องตัดสิน ไม่ใช่คำถามที่ Cowork ควรตัดสินแทน:** invariant นี้ควรอยู่ชั้นไหน

- ถ้า invariant คือ **"ช่องที่ testing_blocked ต้องไม่มีอะไรออก"** → ชั้นที่บังคับควรเป็น `state` + blockers ไม่ใช่ `publication_authorized` เพราะ policy เองแยกสองชั้นนี้ไว้ชัด:
  `publication_control.automation_capable_definition` = "Technical capability only. automation_capable never grants permission to publish"
  `role_capabilities.capability_semantics` = "Actor booleans are maximum role capabilities, not action authorization"
  ⇒ อ่านแบบนี้ `publication_authorized` = สิทธิ์ของเจ้าของ · `state` = ใช้งานได้จริงไหม · guard กำลังบังคับให้สองชั้นเดินพร้อมกัน
- ถ้า invariant ต้องอยู่ที่ `publication_authorized` จริง → ต้องบอกเจ้าของว่าคำสั่ง "ยกทุกช่อง" ปิดกับ TikTok ไม่ได้จนกว่าการทดสอบจะจบ

**สิ่งที่ขอ:** เลือกข้อเดียว บอกเหตุผล แล้วทำให้ policy กับ guard ตรงกัน **ห้ามแก้ด้วยการปิดเสียง finding**
ถ้าเลือกทางแรก อย่าลืมว่ายังต้องมีอะไรสักอย่างที่หยุด TikTok จริง — `channel_readiness.py` หยุดที่ `state` อยู่แล้ว แต่ด่านจริงคือ `authorize_live_publication` ให้ยืนยันว่าที่นั่นก็หยุด

## เรื่องที่ 3 — รายงานอย่างเดียว ไม่ต้องแก้

64 จาก 65 placements เป็นสลอตที่ผ่านไปแล้วตั้งแต่กลางสิงหา (`PAST_PLACEMENT` + `STALE_SLOT`) เหลือของจริงในอนาคต 1 ใบ
guard บอกเองว่า "do not backfill or promote" ⇒ **การเลิกใช้ใบเก่าเป็นการตัดสินใจของเจ้าของ** ให้เสนอวิธีปลดระวางที่ไม่ทำให้ประวัติหาย แต่อย่าลงมือ

---

## เอาต์พุต
เขียน `automation-log/cc-outbox/OUT_calendar-guard-fix_20260910.md` (UTF-8)
บอกว่าแก้อะไรไปบ้าง เทสต์ไหนเพิ่ม ผลรันก่อน/หลัง และข้อ 2 เลือกทางไหนเพราะอะไร
ข้อไหนทำไม่ได้ให้เขียน `UNKNOWN` พร้อมเหตุ **ห้ามยุบเป็น "ไม่ผ่าน"**

## กฎการทำงาน
- แก้ได้เฉพาะ `tools/content_calendar_guard.py`, เทสต์ของมัน, ผู้บริโภคที่เทียบสตริง และไฟล์เอาต์พุตข้างบน
- **ห้ามแตะ `.system_control/policy.json`** — สิทธิ์เป็นของเจ้าของ ถ้าข้อ 2 ต้องแก้ policy ให้เสนอ อย่าแก้เอง
- ห้าม `git push` · ห้าม `git add -A` · ห้ามลบไฟล์
- เขียนไทยผ่าน UTF-8 · ตรวจปิดท้ายว่าไม่มี U+FFFD **และไม่มีบรรทัดที่ไทยกลายเป็น `?`** (`?` เป็น UTF-8 ที่ถูกต้อง เช็ก U+FFFD จึงจับไม่ได้ — เจอจริงในไฟล์ของคุณเองเมื่อวาน ตอนนี้ `tools/encoding_probe.py` จับได้แล้ว ให้รันปิดท้าย)
