# SPEC → Codex — ตรวจการแก้ของ Cowork ที่ทับงานคุณ (10 ก.ย. 2026 บ่าย)

**อ่านอย่างเดียว ห้ามแก้ไฟล์ใดนอกจากรายงาน** — งานนี้คือ review ไม่ใช่ fix

## สิ่งที่เกิดขึ้น

สเปกเช้านี้ (`SPEC_calendar-guard-fix_20260910.md`) สั่งให้คุณคง **exit 3** สำหรับ `STRUCTURAL_FINDINGS` — คุณทำตาม และทำถูกตามสเปก
**แต่สเปกผิด** หลักฐานอยู่ใน receipt `.local-private/runtime/task-runs/ngernduangold_daily/`:
- 7 · 8 · 9 ก.ย.: 26 ขั้น final_rc=2 normal_end
- **10 ก.ย.: 11 ขั้น final_rc=3 abort/step_nonzero** · `content_calendar_guard raw_rc=3 semantic_state=RUNNER_FAILED execution_valid=false`

สาเหตุ: ยกสิทธิ์ 9 ก.ย. → `AUTHORITY_STATE_CHANGED` 65 รายการ (structural) → exit 3 → `run_daily.cmd:130` abort ทั้งวัน
Cowork จึงแก้เป็น **exit 2** ใน commit `d28f50e` — คุณเป็นเจ้าของไฟล์ จึงขอให้ตรวจ

## ขอ 3 ข้อ

1. **เห็นด้วยกับ exit 2 ไหม** — เหตุผลของ Cowork: runner ทุกตัวนิยามไว้เองว่า 3 = runner failure เท่านั้น (`run_daily.cmd:122`) และ 2 = "safety findings retained; no publication; monitoring continues" ซึ่งตรงกับความหมายของ structural findings · `task_run_receipt.py` `calendar-v1` map 2 → BLOCKED โดยตรง
   ถ้าไม่เห็นด้วย บอกว่าอะไรที่ exit 2 ทำให้เสีย **โดยชี้ไฟล์และบรรทัด** ไม่ใช่ความกังวลทั่วไป
2. **มีผู้บริโภคตัวไหนที่แยก BLOCKED(2) กับ STRUCTURAL_FINDINGS(2) ไม่ได้แล้วเสียหายจริง** — ตอนนี้ทั้งสองใช้เลขเดียวกัน JSON ยังแยก แต่ .cmd เห็นแค่เลข ถ้ามีจุดที่ต้องแยกให้ชี้ ถ้าไม่มีให้บอกว่าหาแล้วไม่มี
3. `test_content_calendar_guard.py` ยังแดง 13 ข้อผูกกับ snapshot สิงหา (ก่อนงานคุณ 88/102 · หลัง 89/102 · Cowork ไม่ได้ทำให้ขยับ) — **ประเมินว่า 13 ข้อนี้ควรแก้ snapshot หรือควรลบ** ข้อละบรรทัด ยังไม่ต้องลงมือ

## เอาต์พุต
`automation-log/cc-outbox/OUT_review-exit2_20260910.md` (UTF-8) · ตอบสั้น ผลก่อนเหตุผล · `UNKNOWN` ถ้าตรวจไม่ได้ ห้ามยุบเป็นไม่ผ่าน
ปิดท้ายรัน `tools/encoding_probe.py` กับไฟล์รายงาน
ห้าม git push · ห้าม git add -A · ห้ามลบ · ห้ามแตะ `.system_control/`
