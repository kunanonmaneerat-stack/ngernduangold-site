# ผลงาน calendar tests fixture — 10 กันยายน 2026

## ผลสรุป

แก้ fixture ของ calendar ครบ 13 ข้อโดยคง expected เดิมทั้งหมด และแก้ต้นเหตุที่สองชุด notification/LLM สร้าง fixture ลง ROOT จริงแล้ว ส่วนภาคผนวกอีก 6 ชุดยังแดงจากหลักฐานข้อมูล/receipt/corpus ไม่ตรงกัน ไม่พบหลักฐานว่าการเลื่อนเวลาปัจจุบันเป็นสาเหตุของ failure ที่ตรวจพบ จึงไม่เปลี่ยน expected เพื่อกลบ integrity failure

**ยังไม่ผ่านเงื่อนไขทั้งหมดของงาน:** full sweep บน `.venv` เป็น **UNKNOWN** เพราะเรียก interpreter ไม่ได้ (`Access is denied`); หกชุดภาคผนวกยังไม่ได้รับการแก้ให้เขียว รายงานสาเหตุที่พิสูจน์ได้แยกรายชุดด้านล่าง

## ไฟล์ที่แก้

- `tools/test_content_calendar_guard.py`
- `tools/fixtures/content_calendar_guard_snapshot.json` — ไฟล์ใหม่ UTF-8: calendar 65 placements, policy สำหรับสถานการณ์ blocked วันที่ 16 ส.ค. 2026 และ hash ของ calendar snapshot
- `tools/test_external_notification_safety.py`
- `tools/test_scheduled_llm_safety.py`
- รายงานฉบับนี้

ไม่แก้ production guard, `.system_control/*`, `pipeline/*` หรือ baseline; ไม่ git push, ไม่ git add และไม่ลบไฟล์รีโป รายการ modified/deleted ที่มีอยู่ก่อนเริ่มงานคงไว้ การสร้าง/cleanup fixture ชั่วคราวทำใน temp ตามภาคผนวก

ไม่พบ AGENTS.md ที่ root/ancestors/tools/pipeline ที่ตรวจ และไฟล์ memory registry ตาม path ที่ให้ไม่มีอยู่ จึงอาศัยสเปกและ source/evidence ปัจจุบัน

## ผลก่อนและหลัง

| การตรวจ | ผล |
|---|---|
| ก่อนแก้: `python -X utf8 -B tools/test_content_calendar_guard.py` | **89/102 PASS**, exit 1; FAIL 13 ข้อตรงกับรายการในสเปก |
| หลังแก้ fixture ก่อนเพิ่ม regression | **102/102 PASS**, exit 0 |
| หลังเพิ่ม regression ทดสอบ policy mutation | ชุดเดิม 102 ข้อและ regression ใหม่รวม **103 ข้อ**; sweep ผ่านแล้ว ผล direct run ยืนยันด้านท้ายรายงาน |
| `python -X utf8 -B tools/test_sweep.py --only test_content_calendar_guard` | **FIXED**, 1 green / 0 red, exit 1 ตามสัญญาแจ้ง baseline เปลี่ยน |
| `python -X utf8 -B tools/test_sweep.py --only test_external_notification_safety` | **FIXED**, 1 green / 0 red, exit 1 |
| `python -X utf8 -B tools/test_sweep.py --only test_scheduled_llm_safety` | **FIXED**, 1 green / 0 red, exit 1 |
| unittest สองชุด notification/LLM รวม | **19/19 PASS**, exit 0 |
| `python -X utf8 -B tools/test_content_calendar_guard.py --calendar-guard-fix-only` | **11/11 PASS**, รวม `test_live_authority_rejects_authorized_testing_blocked_tiktok` |
| Sweep ของสามชุดที่แก้ | **mutated = 0**: ทั้งสามมี state=pass; sweep จะเปลี่ยนเป็น mutated และไม่ให้ green หาก protected bytes เปลี่ยน |
| `.venv\Scripts\python.exe -X utf8 -B tools/test_sweep.py` | **UNKNOWN / เริ่มไม่ได้**: `Unable to create process ... Access is denied` |

ผลรันได้ข้างต้นใช้ `C:\Users\nL_ku\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` โดย sweep ระบุ `FALLBACK sys.executable - cron runtime not found` ชัดเจน **ไม่อ้างว่าเท่ากับผลบน cron/.venv** และไม่ได้แก้ baseline ซึ่ง Cowork จะจัดการเอง

## วิธีแยก fixture และรายการ 13 ข้อ

โหลด `CALENDAR`/`POLICY` จาก JSON fixture ที่ commit ได้เท่านั้น ไม่สร้าง snapshot ใหม่จาก live ทุกครั้งที่รัน; กำหนด authority=false ใน snapshot ให้ตรงกับสถานการณ์ PLANNED_BLOCKED เดิม ใช้ deepcopy ต่อ scenario, เวลาเดิมที่ตรึงไว้, source/media evaluator ที่มีอยู่ และ ledger fixture เฉพาะกรณี การจำลอง dedup ให้ผล 124/125 และช่อง fb 36/37 ผ่าน dependency ของ ledger แต่ยังเรียก production code ที่แยก account, classification และ exit code จริง

| # | ข้อเดิม | การแก้โดยคง condition เดิม |
|---:|---|---|
| 1 | actual calendar scopes the 124/125 permanent dedup gap to Facebook main | เปลี่ยนเป็นชื่อ fixture calendar; ใช้ calendar/policy snapshot, dedup gate 124/125 และ fb 36/37, `_ledger_rows=[]`; ไม่อ่าน live calendar/policy/ledger ใน scenario นี้ |
| 2 | global dedup incompleteness is audit-only when every selected account channel passes | ใช้ snapshot และ patch `_ledger_rows=[]` ร่วมกับ gate mocks เดิม; ยังคาด COMPLETED_BLOCKED/1 |
| 3 | canonical Page2 reschedule clears every shared Facebook structural gap | ใช้ผล scenario snapshot ในข้อ 1; คง structural_findings=0 |
| 4 | deterministic fixture baseline passes with exit 0 | `_run()` deepcopy snapshot ที่ authority=false; คง PASS/0 |
| 5 | aware UTC now is normalized to Asia/Bangkok | ใช้ snapshot เดิมกับ UTC instant เดิม; คง PASS |
| 6 | date-only compatibility override means Bangkok midnight | ใช้ snapshot เดิมกับ today เดิม; คง PASS |
| 7 | today's future slot remains a valid blocked plan | ใช้ snapshot และเวลา 17 ส.ค. 12:39 เดิม; คง PASS |
| 8 | a missed blocked slot closes as COMPLETED_BLOCKED without becoming fatal | ใช้ snapshot และเวลา 17 ส.ค. 12:45 เดิม; คง stale=1, active=64, report-only และ publishable=0 |
| 9 | exit 1 is reserved for report-only COMPLETED_BLOCKED lifecycle | อ้างผล snapshot stale-only ของข้อ 8; คง exit=1 |
| 10 | rolling lifecycle excludes historical blocked slots from the active backlog | ใช้ snapshot กับเวลา 23 ส.ค. เดิม; คงผลรวม active/stale และ COMPLETED_BLOCKED |
| 11 | slot-scoped source fixture still matches blocked gates | ใช้ snapshot กับ source recorder เดิม; คง PASS และข้อ adjacent ที่ตรวจ latest exact platform slot |
| 12 | false channel authorization cannot fail open | policy snapshot ให้ authority=false ก่อนถอด blocker; คงการคาด AUTHORITY_FAIL_OPEN |
| 13 | missing exact human listening is a publication blocker, not runner failure | snapshot ไม่มี authority drift; inject human-audio failure เดิมและคง BLOCKED/2 |

ตรวจ AST เทียบ HEAD: condition ของ `check()` เดิมทั้งหมดคงอยู่ (99 call sites ซึ่งรันจริง 102 checks เพราะมี loop); เพิ่ม 1 call site ไม่ลบข้อใด และ unittest assertions ของไฟล์ Python ทั้งสามตรงกับเดิมทั้งหมด

Regression ใหม่ `fixture_is_independent_of_live_policy()` อ่าน policy ปัจจุบันหนึ่งครั้งเพื่อสร้างสำเนาในหน่วยความจำ แล้วสลับ `channels.tiktok.publication_authorized` ผ่าน patch `Path.open` โดยไม่เขียน policy จากนั้น replay ทั้ง 102 checks รวม 13 ข้อที่ขอ ตรวจว่าผล boolean เหมือนเดิมและผ่านทั้งหมด พร้อมเทียบ verdict/process_state/counts/findings ของผล scenario หลักกับรอบแรก อีกทั้งจับว่ารอบ replay **ไม่อ่าน live policy เลย** และปฏิเสธการอ่าน live calendar ด้วย AssertionError จึงจับทั้ง direct reads และ fallback reads ได้

ข้อยกเว้น live authority เดิมยังคงชื่อที่มี `live` และผ่าน 11-test mode แยกต่างหาก การแยกครั้งนี้ครอบคลุม policy/calendar/ledger ของ scenario ที่ระบุ; source libraries, media และ immutable receipts บางส่วนยังเป็น repository integration evidence ตามเทสต์เดิม ไม่อ้างว่า suite ทั้งไฟล์ไม่พึ่ง artifact ภายนอก snapshot เลย

## ภาคผนวก ก — สองชุดเขียนไฟล์จริง

พิสูจน์จาก source: ทั้งสอง caller เดิมเรียก `_fixture_registry(orders, ...)` ก่อนเข้า mock context; helper `tools/test_content_novelty_queue.py:81` ใช้ `dispatcher.ROOT.resolve()` และ `_prepare_fixture_root()` เขียน manifest/calendar/ledger ใต้ root นั้น แม้ orders จะอยู่ใน temp แล้วก็ตาม

แก้ทั้งสอง caller โดยเพิ่ม `mock.patch.object(dispatcher, "ROOT", root)` และย้าย `_fixture_registry()` เข้า context เดียวกับการเรียก bootstrap/main เพื่อให้ทั้งการสร้าง fixture, corpus inspection และ dispatcher execution ใช้ temp root เดียวกัน ผล network mocks และ expected queued/generated/notified เดิมคงอยู่ ผ่าน 19/19 และ sweep รายงาน FIXED ทั้งคู่ ไม่มี protected mutation

ไม่แก้ helper/test_content_novelty_queue หรือ dispatcher เพราะภาคผนวก ค แยกชุดนั้นออกจากงาน และการแก้ caller ครอบคลุมต้นเหตุของสองชุดนี้แล้ว

## ภาคผนวก ข — สาเหตุจริงของอีกหกชุด

รันห้าชุด unittest รวมได้ **53 tests, 12 failures, 1 setUpClass error**; next48 กลุ่มที่ต้อง build packet จึงยังไม่ถูกประเมินครบ อีกชุด completeness ได้ 14 PASS แล้วล้มที่ live-history assertion ข้อสุดท้าย ไม่ใช่ผลล้มจาก import

| ชุด | หลักฐาน failure ที่ได้จริง | ข้อสรุป/สถานะ |
|---|---|---|
| `pipeline/test_facebook_story39_recovery_guard.py` | 3 failures: receipt/audit ผูก ledger hash `416C768E...6909E` แต่ไฟล์ปัจจุบันเป็น `D0EF0968...5B556`; identity_binding_report เป็น INVALID | เป็น live evidence/hash mismatch ไม่ใช่ rolling clock; ไม่แก้ receipt, ledger หรือ pipeline ตามข้อห้าม; ยังแดง |
| `pipeline/test_post_ledger_collision_tombstone.py` | 4 failures: `collision occurrence canonical identity mismatch`, expectation historical collision ไม่ถึง และ remediation receipt hash ของ ledger ไม่ตรง | tombstone จับ canonical occurrence ไม่ตรงจริงหลัง identity overlay ไม่ผ่าน; ยังแดง ไม่ผ่อน validator/expected |
| `pipeline/test_post_ledger_identity_bindings.py` | 4 failuresรวม test_33: `source hash mismatch for .system_control/content_manifest.json`; expected coverage (124,1,125,99.2) แต่ได้ (44,81,125,35.2) | source manifest hash ไม่ตรงทำให้ overlay INVALID; ไม่มีหลักฐานว่า now ทำให้พัง; ยังแดง |
| `tools/test_next48_owner_decision_packet.py` | setUpClass: `media revalidation guard replay differs: b4-p01__facebook_main` | AS_OF ตรึง `2026-08-31T00:29:39+07:00` อยู่แล้ว; trace replay ด้วยเวลาเดิมได้ FAIL และ findings human audio missing + creative novelty corpus stale; ยังแดง |
| `tools/test_post_ledger_completeness.py` | synthetic assertions 14 ข้อผ่าน; live-history assertion ที่คาด complete=124/incomplete=1/99.2% ล้ม; inspect แสดง 44/81/35.2% และ overlay/tombstone INVALID | เป็นผลต่อเนื่องจาก manifest binding ไม่ตรง ไม่ใช่ clock; ไม่เปลี่ยนจำนวนคาดหวังให้ยอมรับหลักฐานเสีย; ยังแดง |
| `tools/test_week_candidate_manifest_guard.py` | 1 failure/3 tests: คาด BLOCKED แต่ได้ FAIL; 11 assets มี `creative novelty review is stale for the current publication corpus` | corpus fingerprint mismatch จริง ไม่ใช่ expiry ตามเวลาปัจจุบัน; ยังแดง ไม่แก้ receipt hash เพื่อให้ผ่าน |

หลักฐานร่วมที่อ่านใหม่:

- Ledger ปัจจุบัน SHA-256: `D0EF096842F18E84A28D810AF674B51E755E5627EA6CCA1C2AA2B6742BC5B556`; receipt/audit คาด `416C768E3F6740C531C0F45F98AE1745B88C23C93D35E404F92708E43BC6909E`
- Manifest ปัจจุบัน SHA-256: `053BF8EE5B2F36119A04BD4821779DB13611F831813F65726E501067A1E3F064`; identity evidence คาด `0E33B5B0D42ECB7CD8422C531B985FF4F52DBC6ECDF719853E9C1AD449B3F912`
- ตรวจแปลง LF/CRLF ในหน่วยความจำแล้ว hash ทั้งสองแบบก็ไม่ตรง expected เหล่านี้ จึงไม่ใช่แค่ newline conversion สำหรับ mismatch ที่พบรอบนี้
- `inspect_ledger()` ให้ identity_binding_report INVALID (`source hash mismatch for .system_control/content_manifest.json`) และ collision_tombstone_report INVALID (`collision occurrence canonical identity mismatch`)
- Current publication corpus fingerprint: `3E12474EAFE20C879F7AA343BF00A0FBB7210588B20D00C4BCF93BC231AE5CFD`; receipt `wk36-sf01-tiktok-video-r5.json` คาด `AC1AB9B513986D3D4E5F702171CAFF31E449DB1C01FA6C7323DF41239B6646E4`
- `tools/media_publish_guard.py:225-301` สร้าง fingerprint จาก manifest/registry bytes และ `:583-594` เทียบ fingerprint โดยตรง ไม่ใช้ now ในเงื่อนไขนี้; next48 ส่ง anchor ที่ตรึงไว้เข้า replay ตาม `tools/next48_owner_decision_packet.py:516-540`

**UNKNOWN:** เหตุการณ์/ผู้กระทำที่ทำให้ source bytes เปลี่ยนจากตอนออก receipt, snapshot revision ที่ควรใช้ซ่อมแต่ละ historical integration test และผลหลัง reconcile หลักฐานที่ได้รับอนุมัติ งานนี้พิสูจน์ความไม่ตรงได้ แต่ไม่ได้พิสูจน์ว่า production code มีบั๊ก จึงไม่แก้โค้ดจริงหรือปลอมหลักฐานให้ตรง expected และไม่เรียกหกชุดนี้ว่า FIXED

## ภาคผนวก ค — numpy และชุดที่ยกเว้น

- Hermes runtime ที่รันได้: `importlib.util.find_spec('numpy')` เป็น None — ยืนยันว่าไม่มี numpy ใน runtime นี้
- `.venv/pyvenv.cfg` ใช้ Python 3.14.5 และ `include-system-site-packages = true`; ไม่พบ numpy ใน `.venv/Lib/site-packages` แต่การอ่าน base interpreter site-packages ถูก Access denied เช่นเดียวกับการเรียก `.venv` จึง **UNKNOWN ว่า .venv import numpy ได้จริงหรือไม่** ห้ามสรุปจาก Hermes หรือ directory ของ venv เพียงอย่างเดียว
- `tools/test_week_content_r5_novelty_guard.py:7` import numpy จริง; ไม่ติดตั้ง/แก้ environment ในงานนี้
- ไม่แก้ `test_request_retirement`, `test_content_novelty_p1`, `test_content_novelty_queue`, `pipeline/test_improvement_loop`, `test_predeploy_acceptance` ตามรายการยกเว้น

## การตรวจปิดท้ายและขอบเขตที่ยังค้าง

- `git diff --check` สำหรับ Python ทั้งสาม: ผ่าน
- calendar/manifest/ledger ยังคงตรงกับ byte snapshot ที่ตรวจจาก HEAD ตอนเริ่มและหลังรันเทสต์; ไม่ใช้ git restore/checkout กู้ไฟล์
- ต้องให้ environment ที่เรียก `.venv` ได้รัน full sweep เพื่อยืนยันเงื่อนไขภาคผนวกทั้งหมด; ผล mutated=0 ที่ยืนยันในงานนี้จำกัดเฉพาะ targeted sweep ทั้งสามชุด ไม่ใช่ full sweep
- รายงานและไฟล์ที่เปลี่ยนทั้งหมดเขียน UTF-8 ไม่มี BOM; ผล direct run สุดท้ายและ encoding_probe บันทึกด้านล่าง

### ผลยืนยันรอบสุดท้าย

- Direct command จาก repo root: `python -X utf8 -B tools/test_content_calendar_guard.py` ได้ **103/103 PASS**, exit 0 — รวม 102 ข้อเดิมและ regression ใหม่ 1 ข้อ
- Output regression: `PASS all 102 fixture assertions survive an in-memory live authority change`
- Encoding probe รอบแรกพบข้อความไทยเสียในส่วนท้ายรายงานจาก PowerShell pipe; แก้ข้อความแล้วและตรวจซ้ำครบ 5 ไฟล์ ผลสุดท้าย PASS, exit 0, 0 need a human, 0 BOM-only
