# SPEC → Codex (astra high) — ครึ่งของคุณในการส่งมอบงานโพสต์ให้ Grok (13 ก.ย. 2026)

**ผู้สั่ง:** เจ้าของ — *"ยกโปรเจกต์นี้ให้ Grok ดูแลงานโพสต์ · Cowork จัดบทบาท · มี Codex astra high · ทำร่วมกันทันที"*
**อ่านก่อน:** `automation-log/HANDOVER_grok-publisher_20260913.md` (บทบาท · เส้นทาง · schema §4-5) และ `automation-log/grok-routines/ROUTINE-*.md`
**บทบาทคุณตามที่ตกลงไว้ 9 ก.ย.:** ด่าน compliance อยู่**ก่อน** Grok หยิบใบงาน — คุณเป็นด่านนั้น

## 0. ก่อนอื่น — รายงานฉบับก่อนของคุณหายไปทั้งฉบับ

`OUT_system-followups_20260910.md` มาถึงเป็น `?` ทั้งภาษาไทย (encoding ตอนเขียนออก) เหลือแต่โค้ด · `.final.txt` บอกว่าข้อ 2 (GA4) และข้อ 3 (ปลดระวาง 64 ใบ) ส่งเป็น**แผน** — แผนนั้นหายไปด้วย
**ตั้งแต่นี้ทุกรายงานเขียนด้วย python `open(path, "w", encoding="utf-8", newline="\n")` เท่านั้น** ห้ามผ่าน shell redirect · จบแล้วรัน `tools/encoding_probe.py <ไฟล์>` และวาง**บรรทัดผลจริง**ลงท้ายรายงาน
งานแรกในสเปกนี้: เขียนแผนข้อ 2 และ 3 ที่หายไปใหม่ลง `OUT_system-followups_20260910.md` (ทับได้ เพราะของเดิมอ่านไม่ออกแล้ว) — สั้นได้ แต่ต้องมีการตัดสินใจครบ

## 1. `tools/grok_gate.py` — ด่านก่อนส่งออก (สำคัญที่สุด)

อินพุต: `placement_id` (จาก `content_calendar.json`) หรือไฟล์ใบงานร่าง · เอาต์พุต: JSON `{"verdict": "READY|BLOCKED|UNKNOWN", "checks": [...], "blocking_field": "...", "could_not_check": "..."}` + exit 0/2/3 (READY / BLOCKED / UNKNOWN — **ห้ามใช้ 3 ปนกับ runner failure** ให้ runner failure เป็น 4 หรือระบุชัด)

ต้องตรวจ (แต่ละข้อระบุ path ที่อ่าน):
- ชั้น 1-6 ของ `tools/channel_readiness.py` (import และเรียก `assess()` ตรง ๆ ห้ามลอกตรรกะ) กับ actor `grok`
- `publication_authority` — เรียก guard เดิมในโหมดที่**ไม่**สร้าง receipt/ไม่แตะ ledger ถ้ามีโหมดนั้น · ถ้าไม่มี ให้บอกว่าอะไรตรวจได้ล่วงหน้าและอะไรตรวจได้ตอนยิงเท่านั้น (นั่นคือขอบเขตของ UNKNOWN ไม่ใช่ข้ออ้าง)
- เนื้อหา: คำต้องห้าม (ดึงจาก policy ไม่ hard-code) · disclosure · ไม่มี CTA 199฿ · ไม่พูดในนาม agent (`public_identity_guard`) · dedup กับ ledger ด้วย `text_hash` — **ห้าม substring match** (OPERATING-NOTES §31 ครั้งที่ 9)
- approval รายชิ้น: ต้องมีหลักฐานที่เจ้าของทำ ไม่ใช่ field ที่ agent ตั้งเองได้ — บอกว่าหลักฐานนั้นควรเป็นอะไร (ไฟล์อนุมัติ? hash ที่เจ้าของเซ็น?) และตอนนี้ **ไม่มี** = BLOCKED ทุกใบ นี่ถูกต้อง อย่าประดิษฐ์ approval ให้ผ่าน
- **reverse test ทุกด่าน**: ต้องพิสูจน์ว่ายิงได้และเงียบได้ · `UNKNOWN` ต้องมีเคสที่ไม่ยุบเป็น BLOCKED

## 2. `tools/grok_jobcards.py` — ส่งออกใบงานของวัน

อ่าน placements ของวัน → เรียก `grok_gate` ต่อใบ → เขียน `jobcards_<YYYY-MM-DD>.json` ตาม schema §4 ของ HANDOVER **เฉพาะใบที่ READY** · ใบ BLOCKED/UNKNOWN ลงไฟล์คู่ `jobcards_<date>_held.json` พร้อมชื่อ field
- `content.text_sha256` คำนวณจากข้อความฉบับสุดท้ายจริง · `limits.posted_today_before_this` นับจาก ledger ด้วย alias เดียวกับ `channel_readiness.ALIASES`
- ที่วางไฟล์: **ยังไม่รู้** — ขึ้นกับคำตอบรูทีน 0 ข้อ 5 ของ Grok · ตอนนี้เขียนลง `automation-log/grok-handoff/` ในรีโป แล้วให้ Cowork ย้ายทีหลัง · เพิ่ม `automation-log/grok-handoff` ใน `test_sweep.PROTECTED_DIRS`
- วันนี้ผลต้องเป็น 0 ใบ READY (ไม่มี approval) — **นั่นคือผลที่ถูก** ให้เทสต์ยืนยันว่าเมื่อไม่มี approval ไม่มีใบไหนหลุดออกมา

## 3. `tools/grok_ingest.py` — รับ claim/result เข้า ledger

อินพุต: ไฟล์/ข้อความ JSON จาก Grok ตาม schema §5 · พฤติกรรม:
- `kind=claim` → เรียก `post_ledger.claim_text_publication` (ที่ `:1641`) ให้จองภายใต้ lock · สำเร็จ = เขียน `claim_ack` กลับ (ไฟล์ `<job_id>.ack.json`) · จองไม่ได้ (มีคนจองแล้ว/hash ไม่ตรง/นอก window) = `claim_rejected` พร้อมเหตุ
- `kind=result` → ตรวจ schema เคร่งครัด: `posted` ต้องมี `post_url` + `verified` ครบ 3 true **ไม่ครบ = ปฏิเสธ ไม่เขียน posted** · `unknown` ต้องมี `could_not_see` · แล้วเขียนแถวผลผูกกับ claim เดิม
- **idempotent**: result ซ้ำสำหรับ job_id เดิมต้องไม่สร้างแถวซ้ำ
- **ห้าม** ingest แก้ไฟล์อื่นนอก ledger และไฟล์ ack

## 4. re-activate receipt attestation (คุณเป็นเจ้าของสัญญานี้)

`improvement_loop` ล้ม RUNNER_FAILED ทุกวันตั้งแต่ 11 ก.ย. เพราะ `improvement_policy.json → task_receipt_monitoring.activation_attestation` pin hash ของ `task_run_receipt.py` เวอร์ชันก่อน v5 ของคุณ · การ activate ต้องให้ 5 suite exit 0 รวม `pipeline/test_improvement_loop.py` ที่แดงมาก่อนทั้งหมดนี้ (18 fail / 2 error)
**ขอ:** ทำให้ 5 suite เขียวจริง แล้ว activate ใหม่ตามสัญญาของคุณเอง · **อนุญาตให้แก้ `improvement_policy.json` เฉพาะ block activation_attestation** · ถ้า test_improvement_loop เขียวไม่ได้ในงานนี้ ให้บอกว่าเพราะอะไรทีละ failure (ไม่ใช่ตัวเลขรวม)

## 5. รายงาน
`automation-log/cc-outbox/OUT_grok-gate_20260913.md` (python utf-8 เท่านั้น — ดูข้อ 0) · แต่ละข้อ 1-4: ทำอะไร เทสต์อะไรเพิ่ม ผลรัน `UNKNOWN` ที่เหลือ · ปิดท้ายด้วยบรรทัดผล `encoding_probe` จริง
ห้าม git push · ห้าม git add -A · ห้ามลบ · ห้ามแตะ `.system_control/policy.json` `role_capabilities.json` · ห้ามโพสต์อะไรออกไปภายนอกไม่ว่าเพื่อทดสอบ
