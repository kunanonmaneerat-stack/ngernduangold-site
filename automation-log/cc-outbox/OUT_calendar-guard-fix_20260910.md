# รายงานแก้ calendar guard — 10 กันยายน 2026

แก้ข้อ 1 และข้อ 2 ตามสเปกแล้ว: guard แยก `STRUCTURAL_FINDINGS` ออกจาก `RUNNER_FAILED` โดยคง exit code 3 ทั้งสองกรณี และแยกสิทธิ์เจ้าของ TikTok ออกจากความพร้อมทางเทคนิค ผลทดสอบเฉพาะงานนี้ผ่าน 10/10 เทสต์ ปฏิทินยังมีปัญหาที่ต้องทบทวนและยังมี `publishable=0` ไม่ได้อนุมัติหรือเผยแพร่โพสต์ใด

## ไฟล์ที่แก้

1. `tools/content_calendar_guard.py` — เพิ่มสถานะและ exit mapping ใหม่ เปลี่ยนการจัดประเภท structural findings พร้อมข้อความ CLI และแก้ invariant TikTok
2. `tools/test_content_calendar_guard.py` — เพิ่ม `CalendarGuardFixTests` และโหมด `--calendar-guard-fix-only` ซึ่งไม่สร้างหรือลบไฟล์ fixture ปรับ assertion เก่าที่เกี่ยวข้องกับสถานะและ capability
3. `tools/preflight.py` — รับสตริงใหม่ใน exit/verdict contract และไม่ยอมให้สถานะ structural findings ผ่าน แม้ payload จะส่ง findings ว่าง
4. `pipeline/improvement_loop.py` — รับสตริงใหม่ แยก `content_calendar_structural_findings` ออกจาก `content_calendar_guard_failed` ทั้งตัวสร้าง readiness และตัวตรวจ blocker contract
5. `automation-log/cc-outbox/OUT_calendar-guard-fix_20260910.md` — รายงานนี้

ไม่ได้แก้ `.system_control/policy.json`, `.system_control/content_calendar.json` หรือ `.system_control/improvement_policy.json` ไม่ได้ git push, git add -A, stage, commit หรือลบไฟล์ใด

ก่อนเริ่มพบไฟล์ `automation-log/cowork-inbox/AGENT-SILENT-ALERT.md` มีการแก้ค้างอยู่ และสื่อ 16 ไฟล์มีสถานะ D อยู่แล้ว รวมทั้งไฟล์ untracked ของผู้ใช้ รายการเหล่านี้ไม่ได้เกิดจากงานนี้และไม่ได้แก้ไขคืน

## ข้อ 1: แยกข้อมูลมีปัญหาออกจาก runner ทำงานไม่ได้

`tools/content_calendar_guard.py:51` เพิ่ม `PROCESS_STRUCTURAL_FINDINGS = "STRUCTURAL_FINDINGS"` และ `EXIT_CODES` มีคีย์ใหม่นี้เป็น 3 โดยตรง จึงไม่พึ่ง fallback และไม่เกิด KeyError จากคีย์ที่หาย

ที่ `tools/content_calendar_guard.py:2639` ผลประเมินซึ่งมี structural findings ใช้สถานะใหม่ ส่วนการอ่านปฏิทินไม่ได้ การอ่าน hash ไม่สำเร็จ และข้อผิดพลาด CLI/runtime ยังใช้ `RUNNER_FAILED` ตามเดิม ทั้งสองกรณียังคืน `verdict=FAIL` และไม่เปิดทางเผยแพร่

CLI แบบข้อความมีแขนง `STRUCTURAL_FINDINGS` โดยเฉพาะที่ `tools/content_calendar_guard.py:2758` จึงไม่ตกไปพิมพ์ RUNNER_FAILED ส่วน JSON ส่งชื่อสถานะใหม่จากผลประเมิน

### ผลตรวจผู้บริโภคก่อนแก้

| ผู้บริโภค | สิ่งที่ตรวจพบและการดำเนินการ |
| --- | --- |
| `tools/preflight.py:1159` | มี mapping ของสตริง process_state กับ exit/verdict เพิ่มสถานะใหม่และคงการปิด publish readiness เมื่อโครงสร้างไม่ผ่าน |
| `pipeline/improvement_loop.py:156` | มี `CALENDAR_PROCESS_EXIT` เพิ่มสถานะใหม่ ทำให้ `execution_valid=True` แต่ `guard_passed=False` และ publication/growth readiness ยังปิด |
| `pipeline/improvement_loop.py:435` และ `:3065` | ตัวคำนวณและตัวตรวจ blockers ใช้ `content_calendar_structural_findings` ตรงกัน ส่วน runner failure คง `content_calendar_guard_failed` |
| `.system_control/improvement_policy.json:324` | RUNNER_FAILED อยู่ในข้อความนิยาม metric ของ terminal receipt ไม่ใช่ enum/mapping ที่รับ process_state จาก calendar จึงไม่แก้ |
| `tools/test_content_calendar_guard.py` | คง assertion สำหรับ invalid CLI และโหลดปฏิทินไม่ได้เป็น RUNNER_FAILED เปลี่ยนเฉพาะ assertion ของ status/source structural drift เป็น STRUCTURAL_FINDINGS |
| `tools/test_predeploy_acceptance.py`, `tools/write_predeploy_acceptance.py` | ตรวจผลจาก verdict/findings ไม่พบการเทียบสตริง RUNNER_FAILED ของ calendar จึงไม่แก้ |

การค้นอ้างอิงยังพบข้อจำกัดที่ยืนยันจากโค้ดได้: `pipeline/run_daily.cmd:129` และ `pipeline/run_weekly.cmd:91` พิมพ์ RUNNER_FAILED เมื่อ rc ตั้งแต่ 3 ขึ้นไป; `pipeline/task_run_receipt.py:91` ใช้ `calendar-v1` ซึ่งจำแนกจากรหัสออกและตกสู่ค่าเริ่มต้น RUNNER_FAILED สำหรับ 3; `tools/local_control_fallback.py:144` map รหัส 3 เป็น RUNNER_FAILED เช่นกัน สิ่งเหล่านี้ไม่ได้อ่านสตริง process_state ใหม่จาก guard จึงยังแยกสองความหมายไม่ได้

ไม่ได้ขยายงานไปแก้ exit-only consumers เหล่านี้ เพราะสเปกกำหนดให้คง rc=3 และอนุญาตการแก้ผู้บริโภคที่เทียบสตริงของ guard เท่านั้น ข้อเสนอสำหรับงานถัดไปคือให้ตัวรันเหล่านี้อ่านและตรวจ JSON process_state คู่กับ rc ก่อนจำแนก ห้ามเปลี่ยนรหัส 3 ทั้งหมดเป็น structural findings เพราะจะซ่อน runner failure จริง การแก้ครั้งนี้จึงยืนยันการแยกความหมายที่ guard, preflight และ improvement readiness ได้ แต่ยังไม่ใช่การแก้ข้อความ/receipt ทุกเส้นทางของ scheduler

## ข้อ 2: เลือกแยกสิทธิ์เจ้าของออกจาก state และ blockers

เลือกทางแรก เนื่องจาก policy ปัจจุบันแยก technical capability กับ action authorization ไว้แล้ว:

- `.system_control/policy.json:16` ระบุว่า automation_capable เป็นความสามารถทางเทคนิค และไม่ได้ให้สิทธิ์ publish, schedule, promote หรือ resume
- `.system_control/role_capabilities.json:10` ระบุว่า actor booleans เป็นขีดความสามารถสูงสุดของบทบาท และ hard stops/gates ยังบังคับใช้
- policy TikTok ปัจจุบันเป็น `publication_authorized=true`, `state=testing_blocked`, `auto=false`, `automation_capable=false`

แก้ `tools/content_calendar_guard.py:1546` ให้ `TESTING_BLOCKED_CAPABILITY` ตรวจ `auto` และ `automation_capable` ว่าต้องเป็น False อย่างเคร่งครัด โดยไม่รวมสิทธิ์ `publication_authorized` ของเจ้าของ ไม่ได้ปิดเสียง finding: หากเปิด auto หรือ automation_capable ยังพบ finding นี้ และยังตรวจ reservation, channel_review, mandatory blockers, owner confirmation, history dedup และ landing parity ตามเดิม

ด่านจริง `tools/publication_authority.py:907` ตรวจ state ก่อนสิทธิ์ publication; `ALLOWED_STATES` ที่บรรทัด 62 มีเพียง active/manual/testing จึงไม่รับ testing_blocked เทสต์เรียก `authorize_live_publication` จริงโดยอ่าน policy, roles และ calendar จริง และยืนยัน exception ตรงข้อความ `channels.tiktok.state is not live-eligible` ไม่ได้ mock การตัดสินใจของด่านนี้ การเรียกจบก่อนถึงขั้นรับ receipt หรือเผยแพร่

ไม่ได้เปลี่ยน policy และไม่ได้ลบ `AUTHORITY_STATE_CHANGED`: 65 รายการนี้ยังแสดงว่าปฏิทินบันทึก publication gate เป็น BLOCKED ขณะที่สิทธิ์เจ้าของเปลี่ยนแล้ว ต้องมีการทบทวนปฏิทิน ไม่ควรอ้างว่าการแก้ capability ทำให้สลอตพร้อมเผยแพร่โดยอัตโนมัติ

## ผลรันก่อนและหลัง

เปรียบเทียบ guard ด้วยเวลาประเมินเดียวกัน `2026-09-10T12:00:00+07:00` เพื่อไม่ให้สลอตเคลื่อนข้ามเวลาระหว่างการทดสอบ:

```powershell
python -X utf8 -B tools/content_calendar_guard.py --now 2026-09-10T12:00:00+07:00 --json
```

| รายการ | ก่อนแก้ | หลังแก้ |
| --- | ---: | ---: |
| process_state | RUNNER_FAILED | STRUCTURAL_FINDINGS |
| exit code | 3 | 3 |
| findings ทั้งหมด | 221 | 207 |
| structural findings | 79 | 65 |
| publication blockers | 13 | 13 |
| report-only findings | 129 | 129 |
| TESTING_BLOCKED_CAPABILITY | 14 | 0 |
| AUTHORITY_STATE_CHANGED | 65 | 65 |
| PAST_PLACEMENT | 64 | 64 |
| STALE_SLOT | 64 | 64 |
| MEDIA_HUMAN_AUDIO_REVIEW_REQUIRED | 12 | 12 |
| PERMANENT_DEDUP_INCOMPLETE | 1 | 1 |
| PERMANENT_DEDUP_GLOBAL_AUDIT | 1 | 1 |
| placements / content IDs | 65 / 34 | 65 / 34 |
| active / stale planned blocked | 1 / 64 | 1 / 64 |
| publishable | 0 | 0 |

เรียก `preflight.check_content_calendar_contract()` หลังแก้โดยใช้ subprocess guard จริง ได้:

```text
calendar structure: FAIL
65 structural finding(s); control=STRUCTURAL_FINDINGS rc=3; run tools/content_calendar_guard.py --json
publish readiness: FAIL — calendar structure did not pass
```

นี่เป็นผลของข้อมูลที่ตรวจพบ ไม่ใช่ UNKNOWN และไม่ใช่ runner พัง

### เทสต์

คำสั่งเฉพาะงานซึ่งไม่สร้าง bytecode หรือไฟล์ fixture:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -X utf8 -B tools/test_content_calendar_guard.py --calendar-guard-fix-only
```

ก่อนแก้ production code เทสต์ชุดแรก 9 ข้อผ่าน 6 และล้มเหลว 3 ข้อ ตรงกับ structural classification, consumer execution classification และ TikTok owner authority หลังแก้ผ่าน 9/9 จากนั้นเพิ่ม regression สำหรับ payload structural ที่ส่ง findings ว่าง ผลสุดท้ายผ่าน **10/10**, exit 0, เวลา 11.209 วินาที

| เทสต์ที่เพิ่ม | สิ่งที่พิสูจน์ | ผลสุดท้าย |
| --- | --- | --- |
| `test_calendar_load_failure_stays_runner_failed` | จำลองอ่านปฏิทินไม่ได้แล้วคง RUNNER_FAILED, CALENDAR_LOAD, rc=3, publishable=0 | PASS |
| `test_calendar_hash_failure_stays_runner_failed` | จำลองอ่าน hash ไม่ได้หลังโหลดสำเร็จแล้วคง RUNNER_FAILED และ rc=3 | PASS |
| `test_loaded_calendar_structural_findings_and_cli` | parse/hash ปฏิทินจริง แล้วใส่ status drift ในหน่วยความจำ ได้ STRUCTURAL_FINDINGS; JSON/ข้อความ CLI คืน rc=3 | PASS |
| `test_real_missing_calendar_cli_stays_runner_failed` | เรียก CLI จริงด้วย path ที่อ่านเป็นไฟล์ไม่ได้ ได้ RUNNER_FAILED และ CALENDAR_LOAD | PASS |
| `test_tiktok_owner_authority_is_separate_from_capability` | owner authority ทั้ง false/true ไม่ก่อ capability finding หากเทคนิคยังปิด และ publishable=0 | PASS |
| `test_tiktok_auto_and_automation_still_detected` | เปิด auto หรือ automation_capable แล้ว finding ยังทำงาน | PASS |
| `test_tiktok_reservation_and_blockers_still_enforced` | ทำ reservation ผิด ตัด mandatory blocker หรือเปิด owner gate แล้วถูกตรวจพบ | PASS |
| `test_live_authority_rejects_authorized_testing_blocked_tiktok` | ด่านจริงปฏิเสธ TikTok ด้วย state แม้เจ้าของอนุญาตแล้ว | PASS |
| `test_consumers_distinguish_structural_findings_from_runner_failure` | preflight ปิด readiness ทั้งคู่; improvement แยก execution_valid และ blocker ถูกต้อง | PASS |
| `test_preflight_cannot_accept_empty_structural_findings_payload` | payload อ้าง STRUCTURAL_FINDINGS แต่ findings ว่างและ publishable=1 ก็ไม่ผ่าน | PASS |

ตรวจ syntax ด้วย `compile()` ในหน่วยความจำผ่าน 4/4 ไฟล์ Python และ `git diff --check` ผ่านสำหรับไฟล์ที่แก้

**UNKNOWN — ผล full legacy regression suite, full preflight และ full improvement/scheduler run:** ไม่ได้รันทั้งชุด เทสต์เดิมใน `tools/test_content_calendar_guard.py:235` และ `:330` สร้างไฟล์ด้วย TemporaryDirectory และลบทิ้งเมื่อออกจาก context จึงใช้โหมดเฉพาะงานที่ไม่แตะไฟล์อื่นตามข้อจำกัดนี้ อีกทั้ง assertion เก่าหลายข้อผูกกับ snapshot เดือนสิงหาคม ไม่ได้แก้ snapshot หรืออ้างว่าทั้งชุดผ่าน ผลที่ยืนยันในรายงานนี้จำกัดอยู่ที่ 10 เทสต์, guard จริง และ calendar preflight จริงตามรายละเอียดข้างต้น

## ข้อ 3: ข้อเสนอปลดระวางเท่านั้น ยังไม่ได้ลงมือ

ยืนยันว่ามี 64/65 placements ผ่านเวลาแล้ว ที่เหลือคือ `p2-16__facebook_page2` วันที่ 11 กันยายน 2026 เวลา 13:10 Asia/Bangkok ซึ่งยังเป็น PLANNED_BLOCKED และมี blockers อยู่ ไม่ใช่รายการพร้อมโพสต์

เสนอให้เจ้าของอนุมัติรายการ placement IDs ที่จะปลดระวางอย่างชัดเจน แล้วทำงานแยกดังนี้:

1. เก็บ snapshot ปฏิทินเดิมครบทั้งไฟล์พร้อม SHA-256 และบันทึกเหตุผล/เวลา/ผู้อนุมัติ โดยรักษา placement_id, slot เดิม, status, blockers และหลักฐานทุกชิ้น
2. เพิ่มทะเบียน retirement แบบ append-only ที่อ้าง snapshot hash และ placement IDs ให้แยก historical inventory จาก active inventory โดยไม่ลบแถวประวัติ
3. ออกแบบ schema/guard และ consumer ให้รู้จักรายการปลดระวางก่อนเริ่มใช้จริง สลอตที่ต้องการใช้ใหม่ควรสร้างรายการใหม่และอ้างกลับรายการเดิม ไม่เปลี่ยนวันเก่าเพื่อ backfill หรือ promote
4. เทสต์ว่าประวัติยังค้นและตรวจสอบย้อนหลังได้ dedup ยังรวมประวัติทั้งหมด และรายการปลดระวางไม่ถูกนับเป็น active runway หรือ publishable

ยังไม่มีการสร้าง snapshot/retirement registry หรือแก้ปฏิทินตามข้อเสนอนี้

## ขอบเขตและความครบถ้วนของไฟล์

ตรวจ hash ก่อน/หลังแล้วไฟล์ควบคุมที่ห้ามเปลี่ยนยังตรงกัน:

| ไฟล์ | SHA-256 ก่อนและหลัง |
| --- | --- |
| `.system_control/policy.json` | `94df3d7ab3426d3ed2e719314cbb7c93a3698023278b181b50ebed6a2c412c23` |
| `.system_control/content_calendar.json` | `978b5c91453d548e1285193a80428f7936ccce052be7ed2d6b9739969a762d23` |
| `.system_control/improvement_policy.json` | `b2bf55ee421c070db501876e479a3a5c8741c6635aaa2119d0d46b1f0ebd856f` |

ไฟล์ที่เขียนทั้งห้าเป็น UTF-8 ตรวจปิดท้ายด้วย `tools/encoding_probe.py` ครบทั้งห้า รวมรายงานฉบับนี้ โดยต้องไม่มี U+FFFD และไม่มีบรรทัดภาษาไทยที่กลายเป็นเครื่องหมายคำถาม ผลการตรวจสุดท้ายบันทึกด้านล่าง

```text
encoding_probe: 5 file(s) scanned, 0 need a human, 0 BOM-only
exit code: 0
```

ตรวจ UTF-8 strict และ U+FFFD ซ้ำผ่านครบห้าไฟล์ รายงานภาษาไทยและไฟล์เทสต์ไม่มีเครื่องหมายคำถามเลย ส่วนเครื่องหมายคำถามใน guard/preflight เป็นข้อความและโค้ดเดิม ไม่ได้เพิ่มหรือเปลี่ยนในการแก้ครั้งนี้ `git status --short` ปิดท้ายแสดงการเปลี่ยนเพิ่มจากสถานะก่อนเริ่มเฉพาะสี่ไฟล์ Python และรายงานที่อนุญาต
