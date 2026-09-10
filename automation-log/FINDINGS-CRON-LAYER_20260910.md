# ชั้น cron กำลังล้มทุกวัน และไม่มีใครถูกบอก (10 ก.ย. 2026)

*เจอระหว่างไล่ผลกระทบของการยกสิทธิ์ 9 ก.ย. · ไม่ได้ตั้งใจหา แต่เจอเพราะเริ่มรันเทสต์ที่ไม่เคยมีใครรัน*

> **ทำไมเรื่องนี้ใหญ่:** สถาปัตยกรรมทั้งระบบพิงอยู่บนประโยคเดียวคือ
> *"ชั้น cron ฟรี ไม่กินโทเคน และไม่มีวันพลาด"* — ชั้น agent พักได้ เพราะชั้น cron ยังอยู่
> ตอนนี้ชั้น cron **รันจริงทุกวัน แต่จบด้วยสถานะล้มเหลวทุกวัน** และไม่มีอะไรพูดออกมา

---

## 1. หลักฐานดิบ — Windows Task Scheduler

| งาน | สถานะ | รันล่าสุด | ผลลัพธ์ |
|---|---|---|---|
| `ngernduangold_daily` | Ready | **10 ก.ย. 07:00** | **rc=3** |
| `ngernduangold_weekly` | Ready | **6 ก.ย. 08:30** | **rc=2** |
| `ngernduangold-daily-queue` | Disabled | 30 ก.ค. | rc=3221225786 (`0xC000013A` = ถูกสั่งหยุด) |
| `ngern-tiktok-daily` | Disabled | ไม่เคยรัน | rc=267011 (ยังไม่เคยรัน) |

ตามธรรมนูญของรีโปนี้ **rc=3 = `RUNNER_FAILED`** ⇒ งานรายวันจบด้วย "ตัวรันพัง" ทุกวัน

## 2. แก้ข้อสรุปเดิมของข้อนี้ — อ่าน receipt แล้ว การอนุมานผิดครึ่งหนึ่ง

**ฉบับแรกของไฟล์นี้เขียนว่า** รอบรายสัปดาห์ abort ที่ calendar guard ทุกครั้ง และ `weekly.log` ที่หยุด 10 ส.ค. คือหลักฐาน
ระบุไว้ว่าเป็นการอนุมาน — และเมื่อเปิด receipt จริง (`.local-private/runtime/task-runs/`) มันผิด:

| | receipt บอกอะไร |
|---|---|
| รายสัปดาห์ 6 ก.ย. | **ครบ 10 ขั้น จบปกติ** rc=2 · calendar=BLOCKED(2) · ga4_pull=BLOCKED(2) · gsc=PASS · growth_review=PASS · improvement_loop=BLOCKED(2) |
| `weekly.log` ที่หยุด 10 ส.ค. | **แค่ย้ายที่** — `log_path` ใน receipt ชี้ไป `.local-private/runtime/weekly.log` ไม่ใช่ความล้มเหลว |
| รายวัน 7 · 8 · 9 ก.ย. | ครบ 26 ขั้น จบปกติ rc=2 |
| **รายวัน 10 ก.ย.** | **abort ที่ขั้น 11/26** · `content_calendar_guard raw_rc=3 semantic_state=RUNNER_FAILED execution_valid=false` |

⇒ **การ abort เพิ่งเกิดวันนี้เป็นวันแรก** และสาเหตุคือ **การยกสิทธิ์ 9 ก.ย. ของผมเอง**:
ยกสิทธิ์ → guard สร้าง `AUTHORITY_STATE_CHANGED` 65 รายการ (structural) → exit 3 → `run_daily.cmd:130` abort
ทุกอย่างหลังขั้น 11 ไม่ได้รันเช้านี้: dispatcher · ga4_pull · preflight tests · runway guard · ledger guards
และ receipt บันทึกว่า `execution_valid=false` ให้ guard ที่รันสำเร็จสมบูรณ์

**บทเรียนที่แพงกว่าบั๊ก:** ผมเขียนข้อสรุปจาก log ที่หยุดเขียน แทนที่จะเปิด receipt ซึ่งอยู่ห่างไปสามโฟลเดอร์
"log เงียบ" กับ "งานล้ม" เป็นคนละเรื่อง — คลาสเดียวกับ `lastRunAt` ที่หลอกระบบนี้ 12 วัน

### แก้แล้ว 10 ก.ย.

สเปกที่ผมส่ง Codex เมื่อเช้าสั่งให้ **คง exit 3** สำหรับ `STRUCTURAL_FINDINGS` — สเปกนั้นผิดตั้งแต่ต้น
เพราะตัว runner เขียนสัญญาไว้ชัดในไฟล์ตัวเอง (`run_daily.cmd:122`): *"exit 3 is reserved for runner failure"*
structural findings = ปฏิทินต้องให้เจ้าของทบทวน ไม่มีอะไรออก = สถานะปิดเพื่อความปลอดภัย = **exit 2** ตามนิยามเดิมของ runner ทุกตัว

- `content_calendar_guard.EXIT_CODES[STRUCTURAL_FINDINGS]` 3 → **2** · `RUNNER_FAILED` ยังเป็น 3 คนเดียว
- `preflight.py` · `improvement_loop.py` ตามไป
- เทสต์ใหม่ `test_structural_findings_never_share_the_runner_failure_exit` — ตรวจว่ารหัสของ structural ต่ำกว่ารหัส runner failure **และ** ตาราง `calendar-v1` ใน `task_run_receipt.py` รู้จักรหัสนั้นโดยตรง (รหัสที่ตารางไม่รู้จักตกไปเป็น RUNNER_FAILED)
- ผลจริง: `content_calendar_guard --json` คืน **2** · พรุ่งนี้ 07:00 `run_daily.cmd:128` จะเขียน "BLOCKED - monitoring continues" แล้วเดินต่อ

ผู้บริโภค 4 ตัวที่จำแนกด้วยเลข exit (`run_daily.cmd` · `run_weekly.cmd` · `task_run_receipt.py` · `local_control_fallback.py`) **ไม่ต้องแก้แล้ว** — เมื่อเลขถูก ตัวอ่านเลขก็ถูกตาม

## 3. GA4 ตายตั้งแต่ 6 ก.ย. — ไล่แล้ว สาเหตุเป็นโครงสร้าง ไม่ใช่อุบัติเหตุ

`ga4_pull.log` ทุกรอบตั้งแต่ 6 ก.ย.: *"GA4 pull blocked before credentials/network: capture trust is not TRUSTED"*

รัน `ga4_decision_trust.evaluate_ga4_decision_trust()` ตรง ๆ ได้เหตุผล:
> `private egress state is outside configured internal CIDRs; GA4 coverage attestation is missing`

**แปล:** IP ขาออกของเครื่องนี้ (จาก `host-state.json` เช็กทุกเช้า 07:00) **ไม่อยู่ใน 3 รายการ `/32` ที่ตั้ง filter "Internal Traffic" ใน GA4 ไว้** (ยืนยันครั้งสุดท้าย 7 ส.ค.)
ISP หมุน IP ของเครื่องนี้ข้าม block — `rotation_history` บันทึกไว้เอง: 1 ส.ค. → 7 ส.ค. "6 วันต่อมา และไปอยู่คนละ /24"
⇒ filter ที่ยึด IP **จะหลุดทุกครั้งที่ ISP หมุน** และสัญญา `GA4-COVERAGE-ATTESTATION-CONTRACT.md` บอกว่าทุกครั้งที่ CIDR เปลี่ยน ต้องเริ่มหน้าต่างสะอาด **28 วัน** ใหม่
⇒ **ภายใต้แบบนี้หน้าต่าง 28 วันไม่มีวันครบ** เพราะ IP หมุนเร็วกว่านั้น · ระบบวัดผลถูกออกแบบให้พังซ้ำโดยโครงสร้าง

*(ไม่พิมพ์ที่อยู่เครือข่ายลงไฟล์นี้ตามกฎ policy · ตรวจได้เองด้วยสคริปต์เทียบ `host-state.json` กับ `ga4-policy-private.json`)*

**ทางแก้ระยะสั้น (เจ้าของกดเอง — ห้าม agent แก้ GA4 Admin · ห้ามขยายเป็น /16):**
GA4 Admin → Data Streams → Configure tag settings → Define internal traffic → เพิ่ม IP ปัจจุบันเป็น `/32` → แล้วบอก Cowork ให้บันทึก observation ตามสัญญา
ผล: ข้อมูลกลับมาเข้า แต่ "สะอาด" ต้องรออีก 28 วัน และจะหลุดอีกตอน ISP หมุนครั้งหน้า

**ทางแก้ระยะยาว (เสนอ — ต้องให้ Codex ออกแบบเพราะแตะ trust evaluator ที่มันเขียน):**
เลิกระบุ internal traffic ด้วย IP · ใช้ `traffic_type=internal` ที่ฝั่งเบราว์เซอร์ของเจ้าของแทน (gtag `set` จาก flag ใน localStorage ที่เจ้าของเปิดครั้งเดียว)
GA4 data filter "Internal Traffic" กรองที่ค่า `traffic_type` อยู่แล้ว — กฎ IP เป็นแค่วิธีหนึ่งในการตั้งค่านั้น
สิ่งที่ได้: ไม่ขึ้นกับ IP · ไม่ต้องหมุน · หน้าต่าง 28 วันครบได้จริง
สิ่งที่ต้องคิดให้ครบก่อนทำ: trust evaluator ต้องเปลี่ยนจาก "egress อยู่ใน CIDR ไหม" เป็น "เบราว์เซอร์ที่เจ้าของใช้ติด flag ไหม" ซึ่งพิสูจน์จากเครื่องยากกว่า — Codex ต้องบอกว่าพิสูจน์ได้ไหม ถ้าไม่ได้ก็บอกว่าไม่ได้

**ผลต่อการอ่านตัวเลข:** ตั้งแต่ 6 ก.ย. ไม่มีข้อมูลเข้า · "ไม่มียอด" ช่วงนี้ = `UNKNOWN` ไม่ใช่ `0`

## 4. ทำไมถึงไม่มีใครเห็น — และสิ่งที่เพิ่มวันนี้เพื่อไม่ให้ซ้ำ

รีโปนี้มีไฟล์เทสต์ **116 ไฟล์** · ชั้น cron รันอยู่ **1 ไฟล์** (`tools/test_preflight_checks.py` ที่ `run_daily.cmd:249`)
⇒ อีก 115 ชุดไม่มีตัวรันตามตารางเลย · guard ผุได้โดยไม่มีบรรทัดไหนเปลี่ยน

เพิ่ม **`tools/test_sweep.py`** — รันทุกชุด เทียบกับ baseline แล้วรายงานเฉพาะ**สิ่งที่ขยับ**

| | ความหมาย | ผล |
|---|---|---|
| `BROKE` | เคยเขียว ตอนนี้แดง | exit 1 — นี่คือสัญญาณเตือน |
| `FIXED` | อยู่ใน baseline แต่ตอนนี้เขียว | exit 1 — **ต้องเอาออกจาก baseline** |
| `KNOWN` | แดงตามที่บันทึกไว้ | เงียบ แต่นับและลงวันที่ |
| `cannot_run` | import ไม่ผ่าน | แยกจาก `fail` — ชุดที่ import ไม่ได้ไม่ได้ปกป้องอะไรเลย เรียกว่า "เทสต์ตก" คือปิดบังว่ามันไม่ใช่เทสต์อยู่ตอนนี้ |

**ทำไม `FIXED` ต้องทำให้ล้มด้วย:** รายการข้ออ้างที่มีแต่โตขึ้นคือวิธีที่ "รู้อยู่แล้วว่าพัง" กลายเป็น "พังถาวร"
ถ้าแก้อะไรได้ ต้องบังคับให้ลิสต์สั้นลง ไม่งั้น baseline จะกลายเป็นที่ซุกของเสีย

## 5. ผลสำรวจครั้งแรก — 116 ชุด เขียว 99 แดง 17

บันทึกไว้ที่ `.system_control/test_baseline.json` · แดง 17 แยกได้เป็นสองกองที่ต้องแก้คนละแบบ

| กอง | จำนวน | ความหมาย |
|---|---|---|
| `cannot_run` | **10** | import ไม่ผ่านตั้งแต่ต้น — **ไม่ได้ตก แต่ไม่เคยได้รัน** |
| `fail` | 7 | รันจริงแล้ว assertion ตก |

กอง `cannot_run` ส่วนใหญ่อ้างถึงโมดูลที่ดูเหมือนไม่มีอยู่แล้ว —
`editorial_draft_gate` · `live_domain_observation` · `local_control_fallback` · `render_week_quote_cards` ·
`week_tiktok_r5_guard` · `week_content_r5_novelty_guard` · `tools.test_content_novelty_queue`
บวก `numpy` ที่ไม่ได้ติดตั้ง
⇒ **นี่คือเทสต์ของโค้ดที่ถูกลบหรือเปลี่ยนชื่อไปแล้ว** ปล่อยไว้จะดูเหมือนมีการป้องกัน ทั้งที่ไม่มี

ที่สำคัญที่สุดในกอง `fail` **เกิดจากการยกสิทธิ์เมื่อวาน**:

```
tools/test_pantip_manual_pilot_contract.py:49
    assert channel["publication_authorized"] is False
    AssertionError
```
`tools/test_pantip_eligibility.py` และ `tools/test_request_retirement.py` ก็แดงด้วยเหตุเดียวกัน

⇒ **มีสัญญาที่บังคับให้ Pantip เป็น `publication_authorized: false` มาตั้งแต่ pilot** และการยกกำแพง 9 ก.ย. ทำให้สัญญานั้นขาด
สัญญานี้ผูกกับ review 18 ส.ค. ที่ยัง `OPEN` (เกินกำหนด 23 วัน)

## 6. การตัดสินใจเดียวที่ต้องเป็นของเจ้าของ

**Pantip: จะเอาทางไหน**

- **(ก) ปิด `channels.pantip.publication_authorized` กลับเป็น `false` จนกว่า review 18 ส.ค. จะปิด** ← Cowork แนะนำทางนี้
  เหตุผล: `state = limited` หยุดการโพสต์อยู่แล้ว ⇒ ปิดกลับ **ไม่เสียอะไรในทางปฏิบัติเลย** แต่ได้สัญญาความปลอดภัยคืน
  และ Pantip เป็นช่องเดียวที่ความผิดพลาดมีราคาเป็น **แบนถาวร**
- **(ข) ปิด review 18 ส.ค. ก่อน แล้วค่อยคงสิทธิ์ไว้** — ต้องมีคำตัดสินจริงบันทึกลง `gates`

Cowork **ไม่แก้เอง** เพราะเป็นการย้อนคำสั่งที่เจ้าของเพิ่งสั่งตรงๆ เมื่อวาน หลังจากแย้งไปแล้วครั้งหนึ่ง
ตราบใดที่ยังไม่ตัดสิน `channel_readiness` ก็รายงาน Pantip เป็น BLOCKED ที่ `state` อยู่แล้ว ไม่มีอะไรรั่วออกไป

## 7. คิวถัดไป เรียงตามความเจ็บ

1. **แก้ผู้บริโภคที่จำแนกด้วย exit code อย่างเดียว 4 ตัว** ⇒ รอบรายวัน/รายสัปดาห์จะเลิก abort และเลิกรายงานผิดว่าตัวรันพัง
2. **ไล่ว่าทำไม GA4 capture trust ถึงตก** ⇒ ตัวเลขกลับมา
3. **17 ชุดแดง** — ไล่ทีละกลุ่ม: กลุ่มที่ import ไม่ได้ (numpy หายไป ฯลฯ) กับกลุ่มที่ assertion ตกจริง คนละงานกัน
4. **ปลดระวาง placement เก่า 64 ใบ** ตามวิธีที่ Codex เสนอ (snapshot + ทะเบียน append-only ไม่ลบประวัติ)

## 8. เรื่องที่ไม่ใช่ของโปรเจกต์นี้

ฉบับก่อนหน้าของไฟล์นี้ (และ `SYSTEM-POSTING_20260910.md`, `RESUME-CHECKLIST_20260905.md`, `AGENT-AUDIT_20260830.md`) มีการเตือนเรื่องบอทเทรดปนอยู่ — สี่ครั้งในสิบวัน สองครั้งโดยผมในวันเดียว
เจ้าของสั่ง 10 ก.ย.: *"ไม่เกี่ยวกับโปรเจกต์นี้ จัดให้ถูก"*

ลบออกจากไฟล์นี้แล้ว · เรื่องของโปรเจกต์อื่นอยู่ที่ `PROJECT-BOUNDARIES.md` และโฟลเดอร์ของโปรเจกต์นั้นเท่านั้น
และเพิ่ม `preflight.check_project_boundary` — รายงานของ ngernduangold ที่ลงวันที่ตั้งแต่ 10 ก.ย. ห้ามมีคำของโปรเจกต์อื่น ไม่งั้น preflight FAIL · เหตุผลที่ต้องเป็นกลไก: ทุกครั้งที่หลุด คนเขียนมีเหตุผลดีเสมอ ("เงินจริง เร่งด่วน") — ขอบเขตพังทีละข้อยกเว้นที่ฟังขึ้นนี่แหละ
