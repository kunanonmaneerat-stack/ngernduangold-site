# OUT grok-gate — 13 กันยายน 2026

## ผลส่งมอบ

สร้าง tools/grok_gate.py, tools/grok_jobcards.py และ tools/grok_ingest.py พร้อม selftests ในไฟล์ที่สเปกระบุ แก้ tools/test_sweep.py ให้ค้นพบ selftests ทั้งสามและเพิ่ม automation-log/grok-handoff ใน PROTECTED_DIRS

ผลจริง: ปฏิทิน 65 placements → BLOCKED 65, READY 0; ทั้ง 65 มี approval.owner_evidence=BLOCKED ส่วนวันที่ 2026-09-13 ไม่มี placement จึงส่งออก READY 0 / held 0 ไม่ได้นำใบหมดอายุมาย้อนลงวันนี้

ข้อ 4 ยังไม่ activate: 4 จาก 5 suite ผ่าน; improvement_loop มี 18 failures / 2 errors และ producer ปัจจุบันไม่อยู่ใน trusted registry ซึ่งอยู่นอก block ที่อนุญาตให้แก้ รายละเอียดทุก failure อยู่ท้ายรายงาน ไม่เปลี่ยนสัญญาให้ตรวจอ่อนลง

ไม่มีการโพสต์ ส่งข้อความ สร้าง scheduler ใช้ receipt หรือแก้ ledger จริง ไม่มี git add, commit, push หรือการลบไฟล์งาน การทดสอบเขียนเฉพาะ fixture ใน temporary directories และ cleanup fixture ตาม test harness เดิม

## 0. กู้รายงานเดิม

เขียน automation-log/cc-outbox/OUT_system-followups_20260910.md ใหม่ด้วย Python UTF-8 ตามรูปแบบที่สั่ง มีการตัดสินใจ GA4 ครบ 4 ประเด็นและแผน retirement 64 ใบ รวมข้อยกเว้น p2-16__facebook_page2

แผน GA4 อ้างพฤติกรรมโค้ด uptime_check.py ที่อ่าน HTML ด้วย urllib ไม่รัน gtag; ส่วน browser flag / Admin filter เป็นข้อเสนอ ยังไม่ยืนยันใน GA4 สด ไม่แสดงที่อยู่เครือข่าย ไม่ดำเนินงาน retirement จากสเปกเก่าแทนงานปัจจุบัน

## 1. tools/grok_gate.py

รับ placement_id หรือ JSON draft ที่มี placement_id (หรือ job_id) แล้ว resolve กลับ source ของ placement ในปฏิทิน ฉบับ draft ต้องตรงข้อความ บัญชี ขา ช่อง และ slot ที่อ้าง ไม่ใช้ข้อความจาก draft ข้าม source; text SHA-256 คิดจากข้อความสุดท้ายหลัง source loader เดิมแปลง line break

เรียก channel_readiness.assess() โดยตรงด้วย actor=grok ครบชั้น 1–6 ตาม guard เดิม ทุก check มี field, verdict, paths, detail ผลรวมมี checks, blocking_field และ could_not_check. ถ้ามีเหตุห้ามที่ตรวจพบ ผลรวมเป็น BLOCKED แต่ยังเก็บ UNKNOWN รายด่านครบ; หากมีแต่สิ่งที่อ่านไม่ได้ ผลรวมเป็น UNKNOWN

Exit contract: READY=0, BLOCKED=2, UNKNOWN=3, RUNNER_FAILED=4. Argument usage error ของ argparse เป็น 2; unexpected execution exception เป็น 4 ไม่ปน UNKNOWN

แหล่งหลักฐานที่อ่าน:
- .system_control/content_calendar.json และ source.file ของ placement
- .system_control/policy.json, .system_control/role_capabilities.json, automation-log/post-ledger.jsonl สำหรับ readiness
- tiktok-pipeline/compliance_rules.json → forbidden; เรียก pipeline/comply_gate.py check() เสริมโดยไม่ลอก trigger list มา hard-code
- .system_control/compliance_checklist.md สำหรับ education disclosure; policy required_disclosure สำหรับ affiliate/video; public_identity_guard ใช้ patterns/speakers จาก policy
- post_ledger.is_duplicate_text() สำหรับ permanent text_hash และการตรวจความครบถ้วนของ identity; ยังรักษา near-duplicate rule เดิม ไม่ใช้ substring เพื่อเทียบโพสต์ใน ledger
- ไฟล์ media จริงสำหรับ SHA-256 และ guard สิทธิ์เดิมสำหรับ QA/source/target bindings
- ตรวจ privacy ด้วย sanitizer เดิม: หากข้อความจะถูก sanitize เปลี่ยน ต้อง BLOCKED ก่อนส่งออก; ปิด CTA numeric token 199 และ letter-kit-199 ตามสเปก; Pantip/Facebook video ถูกปิดใน handoff

### หลักฐานอนุมัติและขอบเขต read-only authority

authorize_live_publication() ไม่มี preview mode และจะ consume receipt จึงไม่เรียกใน gate/ingest นี้ แต่พบ verify_execution_authorization() ในไฟล์เดิมที่ระบุชัดว่าไม่สร้าง ไม่ย้าย และไม่ consume receipt จึงเรียกตรง ๆ เมื่อมี consumed action

หลักฐานที่ยอมรับคือ private one-time receipt จาก owner-controlled interaction ซึ่ง bind content/placement/channel/target/caption/asset/slot และ evidence hashes ตามสัญญาเดิม ไม่ใช่ owner_approved=true, approved_by=owner หรือ JSON อนุมัติที่ agent เขียนเอง การยืนยันตัวเจ้าของต้องเกิดใน owner-controlled provisioning; bridge นี้ไม่สร้างหลักฐานแทน ไม่อ้างว่าการมีไฟล์เพียงอย่างเดียวพิสูจน์ลายเซ็นเจ้าของ

ตัวเชื่อมอ่าน action ที่ owner workflow บันทึกจาก return value ของ authorize_live_publication ได้ที่:
.local-private/runtime/publication-actions/<sha256(job_id UTF-8)>.json
หรือ execution_action ใน draft ที่ส่งเข้า gate โดยตรง Action ยังต้องผ่านการตรวจ consumed receipt จริงทุกครั้ง ตัวเชื่อมไม่สร้าง directory/file นี้ ไม่ส่ง nonce ไปในใบงาน และไม่เขียน action กลับ calendar เพราะจะทำให้ calendar hash ที่ receipt ผูกไว้เปลี่ยน

เมื่อยังไม่มี consumed action: approval.owner_evidence=BLOCKED และ publication_authority.execution=UNKNOWN พร้อมบอกว่ายังตรวจขั้น execution ไม่ได้ การส่งใบงานของสล็อตอนาคตก่อนเข้า window จึงยังถูก held; ต้องตรวจใหม่ในช่วงเวลาที่ guard เดิมอนุญาต การเชื่อมขั้น owner authorization/การส่ง action จาก owner workflow ยังไม่เปิดใช้งานในรอบนี้

### Reverse tests และผล

python -B tools/grok_gate.py --selftest → 7 tests, exit 0
- READY fixture และการปิดทีละชั้น 1–6, quota/gap
- คำต้องห้าม/disclosure/CTA 199/ตัวตน/ข้อมูลส่วนตัว: เคสผ่านและเคสห้าม
- receipt rejected/ไม่มี approval, slot เก่า, duplicate, media อ่านไม่ได้
- ledger หรือ policy อ่านไม่ได้ → UNKNOWN โดยไม่มี known denial มายุบผล
- ตรวจทั้ง 65 ใบจริงว่าไม่มี approval แล้วไม่หลุด READY

เคส READY ของ bridge ใช้ mocked execution verifier เฉพาะจุด owner workflow จึงเป็นหลักฐานการต่อวงจร ไม่ใช่การอนุมัติจริง ส่วน guard สิทธิ์เดิมทดสอบแยกด้วย fixture receipts จริงใน temporary repo:
python -B tools/test_publication_authority.py → 144/144 PASS, exit 0 (รวม consumed receipt, replay, content/target/source/media/policy drift, expiry และ concurrent consume)
python -B tools/test_channel_readiness.py → 21 cases, 0 failed, exit 0

UNKNOWN คงเหลือ: content.text_hash ของ 65 ใบมีหลักฐาน identity ไม่ครบ ตัวอย่าง Threads ที่ตรวจจริงมี 15 complete / 23 incomplete, dedup_completeness=UNKNOWN; ไม่ใช่การสรุปว่าเป็น duplicate ทั้งหมด ทั้ง 65 ยังมี publication_authority.execution=UNKNOWN ควบคู่กับเหตุ approval BLOCKED

## 2. tools/grok_jobcards.py

python -B tools/grok_jobcards.py --date 2026-09-13 → exit 0:
{"date": "2026-09-13", "ready": 0, "held": 0, "transport": "UNKNOWN: awaiting routine 0; local export only"}

ไฟล์จริง:
- automation-log/grok-handoff/jobcards_2026-09-13.json = []
- automation-log/grok-handoff/jobcards_2026-09-13_held.json = []

build() เรียก gate ราย placement ของวัน ใบ READY เท่านั้นเข้า array หลัก; BLOCKED/UNKNOWN เข้าไฟล์ held พร้อมชื่อ field และรายละเอียด สิ่งที่นับเป็น posted_today_before_this คือ publication success ที่ join status กลับ claim ด้วย dedup_key อย่างตรงตัว ใช้ ALIASES ชุดเดียวกับ channel_readiness (fb/facebook, yt/youtube) แยก facebook-page2 และไม่นับ claim ที่ยังไม่สำเร็จเป็น posted

window ยึด authority เดิม ซึ่งแคบกว่าตัวอย่าง HANDOVER: ช่อง immediate ใช้ slot ถึง +10 นาที; YouTube ใช้ lead window เดิม Hash ข้อความและสื่ออ่านจากฉบับสุดท้ายจริง บัญชีใช้ target ที่ receipt ตรวจแล้ว approval.approved_at ใช้เวลา consume ของ receipt ไม่ใช้ field ที่บอตตั้งเองเป็นหลักฐาน

report.claim_to/result_to ยังเป็น null เพราะรูทีน 0 ยังไม่มีผลรับส่ง ไม่แต่ง endpoint และไม่ส่งออกภายนอก ใบงานไม่ใช่หลักฐานว่า Grok รับแล้วหรือโพสต์ได้ เมื่อมี nonempty export แล้วจะไม่เขียนทับด้วยชุดใหม่ เพื่อรักษา claim/result reconciliation

python -B tools/grok_jobcards.py --selftest → 3 tests, exit 0:
1. ตรวจปฏิทินทุกวันที่มีงานว่ารายการไม่มี approval ไม่อยู่ใน READY
2. READY/BLOCKED/UNKNOWN synthetic split
3. alias, claim/status join, วัน Asia/Bangkok และบัญชีคนละ surface

test_sweep ค้นพบทั้งสาม selftest จริง และเรียก --selftest ผ่าน _run_one_unfenced ด้วย interpreter ที่ทดสอบได้: ทั้งสาม pass, exit 0 ไม่รัน full sweep จึงไม่อ้างว่าทั้ง repository เขียวหรือ cron สำเร็จ

## 3. tools/grok_ingest.py

รับ literal JSON, path หรือ stdin (-); strict JSON ปฏิเสธ duplicate keys/nonfinite numbers. claim schema ต้องมี kind/job_id/at/text_sha256_seen เท่านั้น; result ยอมรับเฉพาะ fields ใน HANDOVER

claim:
- อ่านเฉพาะ job_id ที่อยู่ใน READY export, ตรวจ SHA-256, เวลาผู้รับและ window, canonical binding ของ text/account/channel/leg/media
- เรียก gate ใหม่ แล้วเรียก post_ledger.claim_text_publication() ตรง ๆ ให้ lock/dedup/quota/minimum-gap ถูกตรวจใน critical section เดิม
- เขียน claim_ack หลังได้ reservation จริง ผูก dedup_key, job SHA-256, text/media hash, account และ window
- ไม่ผ่าน → claim_rejected พร้อมเหตุ; UNKNOWN คง verdict UNKNOWN. ack เดิมไม่ถูกเขียนทับให้ขัดกัน ไม่มี ack ที่ยืนยันได้ให้หยุดและ reconcile
- Windows ใช้ percent encoding ของ job_id ในชื่อ <encoded-job_id>.ack.json เพราะ ISO timestamp มี : ซึ่งใช้ในชื่อไฟล์ Windows ไม่ได้; reversible และกัน path traversal

result:
- posted ต้องมี HTTPS post permalink ของช่องและ verified สามค่าเป็น bool true จริงครบ (1 หรือ "true" ไม่ผ่าน)
- unknown ต้องมี could_not_see; failed ต้องมี error
- ตรวจ unique claim ที่ผูก hash ของ jobcard และ content/placement เดิมภายใต้ ledger lock ก่อน append status
- posted ตรวจเวลาอยู่ใน window; ทุกผลตรวจ chronology
- exact replay คืน idempotent=true และไม่เพิ่มแถว; conflicting result ไม่เพิ่มแถวและต้อง reconcile
- unknown ไม่สร้าง posted ไม่ส่ง confirm success และไม่อนุญาต retry อัตโนมัติ

ขอบเขต write ของ ingest คือ ledger และ ack; lock ชั่วคราวเป็นส่วนของ post_ledger primitive ที่สเปกกำหนด ไม่มีการสร้าง receipt, แก้ calendar/policy/jobcards หรือโพสต์ภายนอก actual ledger ไม่ถูกเขียนในการทำงานรอบนี้

python -B tools/grok_ingest.py --selftest → 6 tests, exit 0:
- verified แต่ละค่าผิด/หายและ URL หาย
- unknown/failed ต้องมีหลักฐาน
- claim ผ่าน real writer/lock/append และมี ack; duplicate/hash/window/UNKNOWN gate/reservation rejected ไม่เพิ่ม ledger
- result posted + exact replay + conflict, claim binding และ bytes คงเดิมเมื่อถูกปฏิเสธ
- unknown result ผ่าน real ledger parser/append/replay และไม่มี posted
- malformed result ไม่เรียก append, ชื่อ ack ปลอดภัยกับ Windows

UNKNOWN: ยังไม่มี transport ที่พิสูจน์ตัวผู้ส่ง/ที่มาของ ack, ยังไม่มี browser submission หรือ permalink reconciliation จริง CLI เป็น local bridge เท่านั้น; verified ใน payload เป็นสิ่งที่ Grok รายงาน ไม่ใช่หลักฐานว่า Codex เปิด URL ตรวจเอง

### Suite เดิมของ atomic claims ที่ตรวจเพิ่ม

python -B pipeline/test_post_ledger_publication_claims.py → 6 tests, 1 failure, exit 1:
test_minimum_gap_is_part_of_the_same_atomic_claim คาดว่าชนะ 1 claim แต่ได้ 2 เพราะ fixture ใช้ 2026-08-25 ขณะที่ load_index(WINDOW_DAYS=16) ใช้วันปัจจุบันเป็น cutoff จึงไม่มี historical timestamps ใน by_channel_time

ทดสอบวินิจฉัยแยกโดย freeze เฉพาะ post_ledger.now_local ในหน่วยความจำเป็น 2026-08-25 แล้วรัน suite เดิม → 6/6 ผ่าน, exit 0 ยืนยันสาเหตุ fixture clock โดยไม่ได้แก้ไฟล์ suite หรือ post_ledger และไม่ใช้ผลนี้กลบการรันปกติที่แดง Bridge ตรวจ receiver clock/window ก่อน claim และส่งเวลาปัจจุบันเข้าสู่ writer จึงไม่รับ backdated claim แบบ fixture นี้

## 4. Receipt attestation — NOT REACTIVATED

รันทั้ง 5 suite จริงด้วย python -B และ PYTHONDONTWRITEBYTECODE=1:
| Suite | ผลจริง |
|---|---|
| pipeline/test_task_run_receipt.py | 72 tests, OK, exit 0 |
| pipeline/test_improvement_loop.py | 117 tests, 18 failures / 2 errors, exit 1 |
| pipeline/test_improvement_loop_wiring.py | 4 tests, OK, exit 0 |
| tools/test_improvement_policy.py | 9 tests, OK, exit 0 |
| tools/test_batch_exit_contract.py | 20 tests, OK, exit 0 |

Python ที่รันสำเร็จคือ C:\Users\nL_ku\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe. .venv ของ repo เริ่ม process ไม่ได้ (Access is denied). Runtime ที่ใช้ไม่มี numpy; suite ที่รายงานผ่านข้างต้นรันสำเร็จด้วย dependencies ที่ใช้จริง ไม่อ้างว่าเป็น full cron/media runtime

สาเหตุร่วมที่ตรวจพบจริงใน improvement_loop:
- activation_attestation.receipt_producer_sha256 ไม่ตรง producer ปัจจุบัน
- receipt_consumer_sha256 ไม่ตรง consumer ปัจจุบัน
- contract_registry_sha256 ไม่ตรง ordered manifest ปัจจุบัน
- verification.test_sources_sha256 ไม่ตรง test sources ปัจจุบัน

ทดลองแก้เฉพาะ hashes และ result_hash ของ candidate ในหน่วยความจำ (ไม่เขียนไฟล์) แล้ว improvement_contract_errors() เหลือ:
activated receipt producer is not trusted

producer ปัจจุบัน: d69383e7016a3451b03154f67c3bdadd38972240438c805a3c8fa14564b2094c
hash นี้ไม่อยู่ใน task_receipt_monitoring.trusted_receipt_producer_sha256. Consumer บังคับไว้ทั้ง _task_receipt_monitoring_errors และ improvement_contract_errors. trusted_receipt_producer_sha256 อยู่นอก activation_attestation ซึ่งสเปกอนุญาตให้แก้เพียง block เดียว จึงไม่มี candidate ที่ผ่านสัญญาปัจจุบันได้ด้วยขอบเขตนี้

ไม่แก้ trusted registry ไม่แก้ consumer ให้ข้าม trust ไม่เขียน activation ใหม่หรือผล suite ปลอม ไม่แก้ tests เพื่อลบ failure. improvement_policy.json ไม่ถูกแก้ จุดที่ต้องเพิ่มในงานถัดไปคืออนุญาต scoped registry update ของ producer hash นี้ แล้วตรวจ candidate/รัน 5 suite ให้ผ่านก่อน activate และตรวจซ้ำกับไฟล์ที่ activate จริง วัน activated_at ยังต้องเท่ากับ instrumentation_started_at ตามสัญญาเดิม ห้ามเลื่อนเอง

### เหตุราย failure/error (ไม่รวมเป็นตัวเลขอย่างเดียว)

ทุกข้อมี traceback/assertion จริงในภาคผนวก:
1. test_control_health_keeps_legacy_false_fatals_unproven — contract เสียก่อนประเมิน receipt ทำให้ได้ INVALID_MONITORING_CONTRACT แทน NO_RECEIPTS
2. test_each_business_readiness_condition_fails_closed / publication_authority_false — expected business blocker ถูกปนด้วย 4 activation hash errors ทำให้ validated.passed=false
3. ... / content_calendar_publishable_zero — validation ไม่ผ่านจาก 4 activation hashes
4. ... / content_calendar_guard_failed — validation ไม่ผ่านจาก 4 activation hashes
5. ... / content_calendar_blocked — validation ไม่ผ่านจาก 4 activation hashes
6. ... / live_release_parity_failed — validation ไม่ผ่านจาก 4 activation hashes
7. ... / revenue_ledger_unreconciled — validation ไม่ผ่านจาก 4 activation hashes
8. ... / ga4_trust_or_bundle_failed — validation ไม่ผ่านจาก 4 activation hashes
9. ... / gsc_bundle_failed — validation ไม่ผ่านจาก 4 activation hashes
10. ... / content_scoped_source_enforcement_failed — validation ไม่ผ่านจาก 4 activation hashes
11. test_failed_media_guard_is_valid_completed_blocker — media business blocker ควรเป็น completed evidence แต่ contract errors ทำให้ validation ไม่ผ่าน
12. test_future_weekly_terminal_cannot_mask_the_latest_valid_baseline — loader ไม่รับ baseline ภายใต้ contract ที่เสีย คืน None แทน scorecard
13. test_missing_global_monitor_is_diagnostic_not_a_content_scoped_blocker — diagnostic-only case ไม่ผ่าน validation เพราะ activation hashes
14. test_persisted_evaluation_time_recomputes_identical_scorecard — ไม่ผ่าน validation จาก activation hashes ก่อนยืนยัน scorecard ที่ persisted
15. test_ready_weekly_scorecard_and_queue_validate — READY fixture ถูกปฏิเสธโดย activation contract
16. test_regressed_error_learning_blocks_progression_and_growth_eligibility — expected regression fixture ไม่ผ่าน validation เพราะ activation contract
17. test_task_receipt_activation_attestation_binds_live_contract_code — ตรวจ policy จริงแล้วพบ 4 hashes ไม่ตรงโดยตรง
18. test_validated_weekly_run_is_hash_bound_progression_baseline — loader คืน None เพราะ baseline ไม่ผ่าน contract ปัจจุบัน
19. ERROR test_global_pointer_failure_preserves_recoverable_terminal_run — execute() raise ValueError invalid improvement policy ก่อนถึง pointer failure injection
20. ERROR test_run_writes_terminal_state_and_no_external_authority — execute() raise ValueError invalid improvement policy ก่อนสร้าง terminal state

## ขอบเขตไฟล์และ QA

ไฟล์ที่เขียนใน workspace รอบนี้มี 8 ไฟล์:
1. tools/grok_gate.py
2. tools/grok_jobcards.py
3. tools/grok_ingest.py
4. tools/test_sweep.py
5. automation-log/grok-handoff/jobcards_2026-09-13.json
6. automation-log/grok-handoff/jobcards_2026-09-13_held.json
7. automation-log/cc-outbox/OUT_system-followups_20260910.md
8. automation-log/cc-outbox/OUT_grok-gate_20260913.md

ไม่แก้ policy.json/role_capabilities.json, improvement_policy.json, post_ledger.py, task_run_receipt.py หรือ improvement_loop.py. Workspace มี modified/deleted files อยู่ก่อนเริ่ม; ไม่ลบ/คืน/แก้รายการเหล่านั้น git diff --check สำหรับงานผ่าน; ข้อความ Git เรื่อง LF→CRLF เป็น warning เท่านั้น ไม่ใช่การรันหรือผล runtime

## ภาคผนวก: ผล failure ของ improvement_loop จากการรันจริง

```text
======================================================================
ERROR: test_global_pointer_failure_preserves_recoverable_terminal_run (__main__.ImprovementLoopTests.test_global_pointer_failure_preserves_recoverable_terminal_run)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1922, in test_global_pointer_failure_preserves_recoverable_terminal_run
    loop.execute(run_id="recoverable-run")
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\improvement_loop.py", line 5003, in execute
    raise ValueError("invalid improvement policy: " + "; ".join(contract_errors))
ValueError: invalid improvement policy: task receipt activation receipt_producer_sha256 is invalid; task receipt activation receipt_consumer_sha256 is invalid; task receipt activation contract_registry_sha256 is invalid; task receipt activation test-source hash is invalid

======================================================================
ERROR: test_run_writes_terminal_state_and_no_external_authority (__main__.ImprovementLoopTests.test_run_writes_terminal_state_and_no_external_authority)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1856, in test_run_writes_terminal_state_and_no_external_authority
    state, run_dir = loop.execute(run_id="test-run")
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\improvement_loop.py", line 5003, in execute
    raise ValueError("invalid improvement policy: " + "; ".join(contract_errors))
ValueError: invalid improvement policy: task receipt activation receipt_producer_sha256 is invalid; task receipt activation receipt_consumer_sha256 is invalid; task receipt activation contract_registry_sha256 is invalid; task receipt activation test-source hash is invalid

======================================================================
FAIL: test_control_health_keeps_legacy_false_fatals_unproven (__main__.ImprovementLoopTests.test_control_health_keeps_legacy_false_fatals_unproven)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 2358, in test_control_health_keeps_legacy_false_fatals_unproven
    self.assertEqual(
AssertionError: 'INVALID_MONITORING_CONTRACT' != 'NO_RECEIPTS'
- INVALID_MONITORING_CONTRACT
+ NO_RECEIPTS


======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='publication_authority_false')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='content_calendar_publishable_zero')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='content_calendar_guard_failed')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='content_calendar_blocked')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='live_release_parity_failed')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='revenue_ledger_unreconciled')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='ga4_trust_or_bundle_failed')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='gsc_bundle_failed')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_each_business_readiness_condition_fails_closed (__main__.ImprovementLoopTests.test_each_business_readiness_condition_fails_closed) (expected='content_scoped_source_enforcement_failed')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1653, in test_each_business_readiness_condition_fails_closed
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_failed_media_guard_is_valid_completed_blocker (__main__.ImprovementLoopTests.test_failed_media_guard_is_valid_completed_blocker)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1423, in test_failed_media_guard_is_valid_completed_blocker
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_future_weekly_terminal_cannot_mask_the_latest_valid_baseline (__main__.ImprovementLoopTests.test_future_weekly_terminal_cannot_mask_the_latest_valid_baseline)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1245, in test_future_weekly_terminal_cannot_mask_the_latest_valid_baseline
    self.assertEqual(loop._load_previous_weekly_scorecard(root), expected)
AssertionError: None != {'schema_version': 1, 'cadence': 'weekly'[3857 chars]a61'}

======================================================================
FAIL: test_missing_global_monitor_is_diagnostic_not_a_content_scoped_blocker (__main__.ImprovementLoopTests.test_missing_global_monitor_is_diagnostic_not_a_content_scoped_blocker)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1439, in test_missing_global_monitor_is_diagnostic_not_a_content_scoped_blocker
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_persisted_evaluation_time_recomputes_identical_scorecard (__main__.ImprovementLoopTests.test_persisted_evaluation_time_recomputes_identical_scorecard)
Sub-second wall time must not change hash-bound evidence on reload.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 985, in test_persisted_evaluation_time_recomputes_identical_scorecard
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_ready_weekly_scorecard_and_queue_validate (__main__.ImprovementLoopTests.test_ready_weekly_scorecard_and_queue_validate)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 952, in test_ready_weekly_scorecard_and_queue_validate
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_regressed_error_learning_blocks_progression_and_growth_eligibility (__main__.ImprovementLoopTests.test_regressed_error_learning_blocks_progression_and_growth_eligibility)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 777, in test_regressed_error_learning_blocks_progression_and_growth_eligibility
    self.assertTrue(validated["passed"], validated["errors"])
AssertionError: False is not true : ['task receipt activation receipt_producer_sha256 is invalid', 'task receipt activation receipt_consumer_sha256 is invalid', 'task receipt activation contract_registry_sha256 is invalid', 'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_task_receipt_activation_attestation_binds_live_contract_code (__main__.ImprovementLoopTests.test_task_receipt_activation_attestation_binds_live_contract_code)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1296, in test_task_receipt_activation_attestation_binds_live_contract_code
    self.assertEqual(loop.improvement_contract_errors(contract), [])
AssertionError: Lists differ: ['task receipt activation receipt_producer[195 chars]lid'] != []

First list contains 4 additional elements.
First extra element 0:
'task receipt activation receipt_producer_sha256 is invalid'

+ []
- ['task receipt activation receipt_producer_sha256 is invalid',
-  'task receipt activation receipt_consumer_sha256 is invalid',
-  'task receipt activation contract_registry_sha256 is invalid',
-  'task receipt activation test-source hash is invalid']

======================================================================
FAIL: test_validated_weekly_run_is_hash_bound_progression_baseline (__main__.ImprovementLoopTests.test_validated_weekly_run_is_hash_bound_progression_baseline)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\nL_ku\ngernduangold-site\pipeline\test_improvement_loop.py", line 1159, in test_validated_weekly_run_is_hash_bound_progression_baseline
    self.assertEqual(selected, scorecard)
AssertionError: None != {'schema_version': 1, 'cadence': 'weekly'[3857 chars]1fc'}

----------------------------------------------------------------------
Ran 117 tests in 58.937s

FAILED (failures=18, errors=2)
improvement loop FAIL: invalid CLI arguments: argument command: invalid choice: 'invalid' (choose from 'run', 'status')
improvement loop FAIL: boom
improvement loop: COMPLETED | priorities=1 owner_actions=0 | private-run
improvement loop: COMPLETED_WITH_BLOCKERS | priorities=1 owner_actions=0 | private-run
improvement loop: FAILED | priorities=1 owner_actions=0 | private-run
improvement loop: UNKNOWN | priorities=1 owner_actions=0 | private-run
improvement loop: FAILED_VALIDATION | priorities=1 owner_actions=0 | private-run
```

## Encoding verification

รายงานทั้งสองเขียนด้วย open(path, 'w', encoding='utf-8', newline='\n').write(text) เท่านั้น บรรทัดด้านล่างจะนำมาจาก tools/encoding_probe.py หลังเขียนไฟล์จริง

encoding_probe: 1 file(s) scanned, 0 need a human, 0 BOM-only
