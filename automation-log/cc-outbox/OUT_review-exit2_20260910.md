# ผล review exit 2 — 10 กันยายน 2026

**เห็นด้วยกับ commit `d28f50e`: `STRUCTURAL_FINDINGS` ควรออก 2 และสงวน 3 สำหรับ `RUNNER_FAILED`** ค้นแล้วไม่พบผู้บริโภคในโค้ดที่ตรวจซึ่งต้องแยก BLOCKED(2) กับ STRUCTURAL_FINDINGS(2) ด้วยเลขอย่างเดียวแล้วเสียพฤติกรรมจริง ส่วนเทสต์แดง 13 ข้อควรแก้ fixture/snapshot ทั้ง 13 ข้อ ไม่ควรลบ และไม่ควรเปลี่ยน expected ให้ยอมรับ structural findings เพียงเพื่อให้เขียว

ตรวจ source ปัจจุบันที่ HEAD `7a091e8b51de6d3abb9d417d9e968e2389e9032e` และ diff ของ `d28f50e` แล้ว: guard, preflight, improvement_loop และ test_content_calendar_guard ปัจจุบันไม่มี diff จากไฟล์ชุดเดียวกันใน commit ที่ขอ review

## 1. เหตุผลที่เห็นด้วย

- `tools/content_calendar_guard.py:65-70` กำหนด structural=2, runner failure=3; `:163-177` ยังคง `verdict=FAIL`, `publishable=0` และรายละเอียด findings/process_state ครบ การเปลี่ยนเลขไม่ได้ลดระดับผลประเมินให้ PASS
- `pipeline/run_daily.cmd:120-130` และ `pipeline/run_weekly.cmd:82-92` ประกาศให้ 1/2 เป็น closed state และหยุดเมื่อ >=3; daily ขั้นถัดไปคือ dispatcher `--local-only` ที่ `:131-133` ส่วน `:345-347` ยังคงสะสม rc=2 เป็นผล blocked ของงาน ไม่เปลี่ยนเป็นสำเร็จไร้ข้อจำกัด
- `pipeline/task_run_receipt.py:91-93,1793-1820` map 2 เป็น `BLOCKED/execution_valid=true`; 3 ไม่อยู่ในตาราง จึงใช้ known-contract default เป็น `RUNNER_FAILED/execution_valid=false` (`:108-110`) การทดสอบฟังก์ชัน classifier จริงให้ผลตรงกันทั้ง 0/1/2/3
- guard จริงผ่าน CLI ในรอบ review ได้ **rc=2, process_state=STRUCTURAL_FINDINGS, verdict=FAIL, publishable=0, structural_findings=65**; ทั้ง 65 เป็น `AUTHORITY_STATE_CHANGED` ยังมี publication blockers 13 รายการ (human audio 12, permanent dedup 1) จึงไม่ได้อ้างว่าปฏิทินพร้อมเผยแพร่
- ชุดเฉพาะการแก้ `python -X utf8 -B tools/test_content_calendar_guard.py --calendar-guard-fix-only` ผ่าน **11/11** รวม structural/CLI, โหลดหรือ hash ไม่ได้ยัง rc=3, preflight/readiness ยังคงปิด, และ TikTok authority/capability

หลักฐาน receipt ที่อ่านใหม่จาก `.local-private/runtime/task-runs/ngernduangold_daily/`:

| receipt filename | จำนวนขั้น | final_rc | terminal | calendar ขั้น 11 |
|---|---:|---:|---|---|
| `ngernduangold_daily-20260907T000002839094Z-32868-c576e1.json` | 26 | 2 | end / normal_end | raw_rc=2, BLOCKED, execution_valid=true |
| `ngernduangold_daily-20260908T174423545361Z-28608-e90c0a.json` | 26 | 2 | end / normal_end | raw_rc=2, BLOCKED, execution_valid=true |
| `ngernduangold_daily-20260909T000004034100Z-16608-942dc9.json` | 26 | 2 | end / normal_end | raw_rc=2, BLOCKED, execution_valid=true |
| `ngernduangold_daily-20260910T000002787682Z-22448-673b3c.json` | 11 | 3 | abort / step_nonzero | raw_rc=3, RUNNER_FAILED, execution_valid=false |

วันที่ในชื่อ receipt เป็น UTC: รายการ `20260908T174423...` เริ่ม 9 ก.ย. 00:44 น. ไทย จึงไม่ใช่หลักฐานของรอบเช้า 8 ก.ย. ไทย แต่ข้อเท็จจริงเรื่อง 26 ขั้นก่อนหน้าและ 11 ขั้นวันที่ 10 ก.ย. ตรงกับข้อมูลในไฟล์

**UNKNOWN:** ผล scheduled run เต็มหลัง commit และผลรอบเช้าถัดไป ยังไม่มีการรันเพื่อพิสูจน์ในงานนี้ การที่ rc=2 ผ่าน calendar branch ไม่รับประกันว่าขั้นอื่นจะจบครบทั้งหมด

## 2. ผู้บริโภคที่ตรวจและผลของการใช้เลขร่วมกัน

ค้น direct references ด้วย `git grep` ใน source ที่ติดตาม และ `rg` ใน pipeline/tools/social-autopost/automation-log สำหรับชื่อ guard, calendar-v1, CALENDAR_RC, CALENDAR_PROCESS_EXIT และ calendar result/exit จากนั้นอ่านแขนงตัดสินใจที่พบ

| ผู้บริโภค / หลักฐาน | ผลที่ตรวจพบ |
|---|---|
| `pipeline/run_daily.cmd:125-130,345-347` | แยกสองชนิดจากเลขไม่ได้ แต่ทั้งสองต้องคง blocked และให้ monitoring ไปต่อ; rc=2 ถูกสะสมไว้ ไม่มีแขนงที่ต้องให้ structural ผ่านหรือเผยแพร่ |
| `pipeline/run_weekly.cmd:87-92` | ใช้เงื่อนไข 1/2/3 แบบเดียวกัน ไม่มีความต้องการแยกสองชนิดเพื่อควบคุมขั้นถัดไป |
| `pipeline/task_run_receipt.py:91-93,1808-1820` | receipt เก็บระดับรวมเป็น BLOCKED ไม่เก็บชนิด structural ใน semantic_state; นี่คือการลดรายละเอียดในสรุป แต่ยังบันทึกว่า blocked และการรันตรวจถูกต้อง ไม่ใช่ PASS |
| `tools/local_control_fallback.py:139-145,314-321,354-371` | map 2 เป็น BLOCKED และ terminal ยังมี `CHECK_BLOCKED_content_calendar` / `LOCAL_CHECKS_COMPLETED_BLOCKED`; ไม่พบแขนงอนุญาต publication จากการรวมเลข |
| `tools/preflight.py:1158-1176,1191-1234` | อ่าน process_state และ classification; BLOCKED ที่ไม่มี structural อาจผ่าน calendar structure แต่ publish readiness FAIL; STRUCTURAL_FINDINGS ยังทำให้ทั้งสอง FAIL จึงแยกความหมายได้แม้ rc เท่ากัน |
| `pipeline/improvement_loop.py:156-162,435-447,508-512,3033-3068` | ตรวจ rc คู่ process_state และแยก blocker `content_calendar_structural_findings` จาก `content_calendar_blocked`; ทั้งคู่ไม่เป็น guard ready และไม่เป็น publication ready |
| `tools/write_predeploy_acceptance.py:438-455` และ `tools/test_predeploy_acceptance.py:186-205` | ใช้ผล evaluate โดยตรง แยก structural จาก finding classification และผูก decision กับ process_state/counts/findings ไม่ได้ใช้ rc เป็นตัวแยก |

**สรุปข้อ 2: หาแล้วไม่มีจุดเสียหายจริงจากการใช้เลข 2 ร่วมกันในผู้บริโภคที่ตรวจ** รายละเอียดที่ receipt/fallback รวมเหลือ BLOCKED ต้องอ่าน guard JSON เมื่อต้องวินิจฉัยสาเหตุ ซึ่ง preflight/improvement_loop ทำอยู่แล้ว ไม่พบเหตุให้ย้อนเป็น exit 3

ขอบเขตการค้นไม่ใช่การรับรองผู้บริโภคนอก repository ที่ไม่ได้ให้ตรวจ; root search/status อ่าน `.pytest_cache` ไม่ได้ จึงไม่อ้างว่าค้นพื้นที่นั้นครบ แต่ source references ข้างต้นอ่านได้

ข้อสังเกตเล็กน้อย: `tools/content_calendar_guard.py:2692` ยังมี docstring ว่า findings กับ runner failure ใช้ 3 ร่วมกัน ข้อความนี้ล้าสมัยเมื่อเทียบกับ mapping จริงที่ `:65-70` ควรแก้คำอธิบายในงานแก้ครั้งถัดไป ไม่ใช่เหตุคัดค้าน exit 2 และยังไม่ได้แก้ใน review นี้

## 3. เทสต์แดง 13 ข้อ — ข้อละบรรทัด

รอบนี้ยืนยัน **85 PASS / 13 FAIL จาก 98 ข้อที่รันได้แบบอ่านอย่างเดียว** อีก 4 ข้อเป็น **UNKNOWN / ไม่รัน** เพราะสร้างและลบไฟล์ temporary; จึงไม่รายงานว่าทดสอบครบ 102 หรือยืนยัน 89/102 ใหม่ จำนวน 13 ข้อที่ fail ตรงกับสเปก

วิธีตรวจ: โหลด source ของ test เป็น AST ในหน่วยความจำ ประเมิน top-level เดิมและเก็บผล `check()` โดยข้าม block สร้าง temporary ที่บรรทัด 255 และ checks ที่ 339,360,366,373 เท่านั้น; ปิด bytecode ของ process/child ด้วย `-B` และ `PYTHONDONTWRITEBYTECODE=1`, ใช้ Python audit hook ปฏิเสธการเขียน/สร้าง/ลบ/ย้ายไฟล์ใน process ตรวจ ไม่มีการแก้ไฟล์ test และไม่ได้เรียก full unittest discovery

ต้นเหตุ: `tools/test_content_calendar_guard.py:218-221` อ่าน calendar/policy ปัจจุบัน แต่ตรึงเวลาไว้ 16 ส.ค.; `_run()` ที่ `:302-324` deepcopy policy ปัจจุบันนั้น จึงไม่ใช่ fixture ที่คงที่จริง ผล baseline ได้ structural 65 รายการซึ่งเป็น `AUTHORITY_STATE_CHANGED` ทั้งหมด การมีสิทธิ์แล้วแต่ calendar ยังคง authority gate/blocker ทำให้เกิด finding ตาม `tools/content_calendar_guard.py:1563-1568` และ structural มีลำดับก่อน publication/report-only ตาม `:2650-2657`

การแก้ snapshot ในข้อเสนอต่อไปนี้หมายถึง **fixture ทดสอบที่แยกจาก live policy และมี dependencies สอดคล้องกับวันที่/สถานการณ์** ไม่ใช่ย้อนสิทธิ์เจ้าของหรือแก้ `.system_control/` และไม่ใช่เปลี่ยน expected PASS/BLOCKED เป็น STRUCTURAL_FINDINGS เพื่อซ่อนปัญหา

| # | จุดตรวจใน `tools/test_content_calendar_guard.py` | คำตัดสินและวิธีแก้ที่เสนอ |
|---:|---|---|
| 1 | `:404` actual calendar scopes the 124/125 permanent dedup gap to Facebook main | **แก้ snapshot ไม่ลบ** — ตรึง ledger/calendar/policy ของกรณี 124/125 ให้เข้าชุดกันและไม่มี authority drift; คงตรวจ Facebook-main scope, global REPORT_ONLY และ rc=2 โดยไม่ hard-code จำนวนจาก live ledger ที่เปลี่ยนได้ |
| 2 | `:459` global dedup incompleteness is audit-only when every selected account channel passes | **แก้ snapshot ไม่ลบ** — ใช้ policy fixture ที่ไม่มี structural findings เพื่อให้ fake global/channel dedup ตรวจ REPORT_ONLY → COMPLETED_BLOCKED/1 ได้จริง; ปัจจุบัน publication findings=0 แต่ authority structural=65 |
| 3 | `:467` canonical Page2 reschedule clears every shared Facebook structural gap | **แก้ snapshot ไม่ลบ** — เก็บกรณี reschedule เป็น fixture และตรวจ gap ที่เกี่ยวกับ Facebook/Page2 โดยตรง; assertion ว่า live calendar ไม่มี structural ทุกชนิดถูก authority drift ที่ไม่เกี่ยวกับ reschedule รบกวน |
| 4 | `:492` deterministic fixture baseline passes with exit 0 | **แก้ snapshot ไม่ลบ** — สร้าง baseline calendar+policy ที่กำหนด authority=false ใน fixture อย่างชัดเจนและตรึง dependencies; คง PASS/0 เป็นฐานสำหรับ mutation tests |
| 5 | `:511` aware UTC now is normalized to Asia/Bangkok | **แก้ snapshot ไม่ลบ** — ใช้ baseline เดียวกันที่ไม่มี authority drift และเปรียบเทียบ counts/findings ของ instant เดียวกันสอง timezone เพิ่มจากการตรวจ PASS อย่างเดียว |
| 6 | `:520` date-only compatibility override means Bangkok midnight | **แก้ snapshot ไม่ลบ** — ใช้ fixture คงที่แล้วเทียบ date override กับ aware Bangkok midnight โดยตรง; ปัจจุบัน FAIL เพราะ structural ไม่ได้พิสูจน์ว่าการแปลงเวลาผิด |
| 7 | `:558` today's future slot remains a valid blocked plan | **แก้ snapshot ไม่ลบ** — ตรึง first-slot time และ policy ให้เป็น pre-slot scenario; คงความคาดหวังว่า slot ยังไม่ stale และผลเป็น PASS/0 |
| 8 | `:562` a missed blocked slot closes as COMPLETED_BLOCKED without becoming fatal | **แก้ snapshot ไม่ลบ** — ใช้ policy fixture ที่ไม่มี structural เพื่อทดสอบ STALE_SLOT แบบ REPORT_ONLY; รอบนี้ stale=1, active=64 ถูกแล้ว แต่ authority=65 ทำให้ไม่เข้า lifecycle-only state |
| 9 | `:586` exit 1 is reserved for report-only COMPLETED_BLOCKED lifecycle | **แก้ snapshot ไม่ลบ** — ผูกกับ stale-only fixture ของข้อ 8 และคง assert exit=1; ไม่เปลี่ยนเป็น 2 เพราะจะเลิกตรวจสัญญา report-only |
| 10 | `:616` rolling lifecycle excludes historical blocked slots from the active backlog | **แก้ snapshot ไม่ลบ** — ตรึง calendar/clock/policy เพื่อแยก active/stale; รอบนี้ total=65, stale=20, active=45 แต่ state ถูก authority findings ยกระดับ ควรคงการตรวจผลรวมและ publishable=0 |
| 11 | `:684` slot-scoped source fixture still matches blocked gates | **แก้ snapshot ไม่ลบ** — ใช้ baseline authority fixture เดียวกันเพื่อให้ source-only scenario ผ่าน และคง check latest exact platform slot ที่ `:685-690`; ผล source-clock รอบนี้มีเฉพาะ authority structural 65 รายการ |
| 12 | `:742` false channel authorization cannot fail open | **แก้ snapshot ไม่ลบ** — กำหนด channel ของ placement ที่ทดสอบให้ publication_authorized=false ใน policy fixture ก่อนเอา blocker ออก; ปัจจุบัน policy เป็น true จึงไม่เข้าเงื่อนไข AUTHORITY_FAIL_OPEN ตามชื่อเทสต์ |
| 13 | `:1467` missing exact human listening is a publication blocker, not runner failure | **แก้ snapshot ไม่ลบ** — ใช้ fixture ที่ไม่มี authority drift แล้ว inject เฉพาะ missing audio; รอบนี้พบ MEDIA_HUMAN_AUDIO_REVIEW_REQUIRED=12 ถูกต้อง แต่ structural=65 มีลำดับก่อน BLOCKED จึงต้องคง BLOCKED/2 สำหรับกรณี audio-only |

diff ของ Cowork เปลี่ยน legacy assertion ที่ `:657-666` ให้ status safety failure ออก 2 และเทสต์ข้อนี้ผ่านในรอบตรวจ ส่วน 13 checks ในตารางไม่ได้ถูกแก้โดย commit นั้น ข้อสรุปว่าไม่มี fail ใหม่จาก diff นี้อาศัย source diff และผล 98 ข้อปัจจุบัน; ไม่ได้รัน full historical suite เพื่อยืนยันตัวเลข 88/102 ก่อนงานเช้า

## ขอบเขตและการตรวจไฟล์

- เขียนเฉพาะรายงานนี้ ไม่มีการแก้ source/test/config, ไม่มี git add หรือ git push และไม่ได้ลบไฟล์ใด
- `.system_control/` ถูกอ่านโดย guard/test เท่าที่จำเป็น ไม่มีการเขียนหรือแก้สิทธิ์; รายการไฟล์ modified/deleted ที่เห็นใน git status มีอยู่ก่อนเริ่ม review และไม่ได้ดำเนินการกับรายการเหล่านั้น
- Python production path `C:\Users\nL_ku\AppData\Local\Python\pythoncore-3.14-64\python.exe` เรียกไม่ได้ (`Access is denied`); ใช้ `python` ที่ resolve เป็น Hermes venv สำหรับการทดสอบข้างต้น จึง **UNKNOWN** สำหรับการรันทดสอบด้วย production interpreter ภายใต้ session นี้ ไม่จัดเป็น test FAIL
- ไม่รัน daily/weekly/fallback orchestration หรือ predeploy writer เพราะจะเขียนหลักฐาน/ผลข้างเคียงนอกไฟล์รายงาน
- รายงานเขียนเป็น UTF-8 ไม่มี BOM; ปิดท้ายตรวจด้วย `python -X utf8 -B tools/encoding_probe.py automation-log/cc-outbox/OUT_review-exit2_20260910.md`
- ผล encoding_probe: PASS (exit 0) — 1 file scanned, 0 need a human, 0 BOM-only
