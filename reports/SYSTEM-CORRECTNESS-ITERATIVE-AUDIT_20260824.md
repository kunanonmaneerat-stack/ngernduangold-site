# รายงานวนตรวจ แก้ไข และยืนยันความถูกต้องของระบบ — 24 สิงหาคม 2026

> **SUPERSEDED — ห้ามใช้คะแนน 100/100 เป็นสถานะปัจจุบัน:** การทบทวน adversarial รอบถัดมาในวันเดียวกันพบ counterexample เพิ่มที่ทำซ้ำได้และแก้ไขแล้ว รวมทั้ง merchant runtime URL, quota/gap ข้ามบัญชี, official RSS content type, receipt consumer contract และ release provenance รายงานฉบับนี้จึงคงไว้เป็นหลักฐานประวัติเท่านั้น; ให้ใช้ evidence bundle และรายงาน re-audit ล่าสุดแทน

ตรวจจาก working tree ปัจจุบันและ evidence bundle `audit-loop-20260824-0310-final-runtime` เวลา 03:10 น. Asia/Bangkok โดยใช้ interpreter เดียวกับ Windows tasks

## คำตอบสรุป

รอบตรวจแบบ adversarial จบโดย **ไม่พบ defect ใหม่ที่ทำซ้ำได้ในขอบเขต local-safe ที่ระบุด้านล่าง** หลังแก้ counterexample ทุกตัวและรัน clean round ซ้ำ คะแนนความถูกต้องของ implementation ในขอบเขตที่ทดสอบคือ **100/100** แต่คะแนน maturity เชิงปฏิบัติการ/รายได้เป็นคนละเรื่องและยังอยู่ที่ **40/100 ระดับ instrumented**

สถานะควบคุมจริงคือ `VALID_WITH_BLOCKERS` และรอบจบแบบ `COMPLETED_WITH_BLOCKERS`; `validation_passed=true`, regression ใหม่ 0, publication ready=false, growth ready=false จึง **ยังห้ามโพสต์ ตั้งเวลา deploy หรือสรุปรายได้** จนกว่า blocker ภายนอกและหลักฐานเจ้าของจะครบ

คำว่า 100/100 ในรายงานนี้ไม่ใช่คำรับรองว่า software ทุกสภาวะในอนาคตไร้ข้อผิดพลาด แต่หมายถึง test matrix, exact counterexamples และขอบเขตตรวจอิสระรอบสุดท้ายไม่พบข้อผิดพลาดคงค้างที่ทำซ้ำได้

## คะแนนแยกตามความหมาย

| มิติ | คะแนน | ผล |
|---|---:|---|
| Local implementation correctness ในขอบเขตที่ตรวจ | 100/100 | clean round ผ่าน ไม่มี counterexample ใหม่ |
| Evidence/control validation | PASS | hashes และ validation ตรงกัน |
| Operational/revenue maturity | 40/100 | instrumented แต่ยังมี hard blockers 3 กลุ่ม |
| Publication readiness | 0 ชิ้น | publication authority=false และ calendar publishable=0 |
| Growth experiment eligibility | ไม่ผ่าน | analytics/revenue ยังไม่ decisionable |

## ข้อผิดพลาดที่พบและแก้ในรอบนี้

1. **JSON evidence กำกวม:** ด่าน publication, release, calendar, ledger, media, source, official-news, receipt, analytics และ control-health บางจุดยังรับ duplicate key หรือเลข overflow `1e999` แบบ last-wins/Infinity แก้ให้ reject duplicate, NaN, Infinity และ exponent overflow แบบ recursive พร้อม stable read และ regression tests
2. **Task receipt false trust:** การแก้ terminal receipt ล้มเหลวอาจทิ้ง PASS เก่า และ `record_step` อาจแข่งกับ `finish` แล้วเขียน RUNNING ทับผลจบ แก้ด้วย durable revocation marker, consumer validation, in-process/cross-process transition lease และ exact OS exit mapping
3. **Control-health reader ไม่เท่ากับ receipt reader:** receipt หลักปฏิเสธ duplicate key แต่ improvement consumer เคยนับเป็น trusted terminal แก้ให้ใช้ strict duplicate-key contract และจัดเป็น `INVALID_RECEIPTS`
4. **Media corpus TOCTOU:** publisher อาจตรวจ media/claim คนละ snapshot กับ mutation แก้ด้วย shared OS corpus claim lock, exact action/content/asset/path/hash binding และ revalidation ใต้ lockตลอด mutation boundary
5. **Release provenance TOCTOU:** pilot contract เคยถูกอ่านหลายครั้งจน `source_sha256` อาจเป็น bytes A แต่ `contract_sha256` เป็น bytes B แก้เป็น stable file-handle snapshot ครั้งเดียว ใช้ bytes เดียวกัน parse และ hashทุกตำแหน่ง
6. **PIL file-handle leak:** watermark scanner และ visual QA เปิดภาพโดยไม่ปิดเมื่อ provider เก็บ reference แก้ด้วย context manager/finally และทดสอบ retained-reference/resource-warning โดยตรง
7. **Public identity ช่อง dynamic:** ปิด dynamic import, eval/Function/timer string, HTML sink, CSS import และ remote stylesheet ที่อาจโหลดข้อมูล/ตัวตนนอกหน้า; ลบ Google Fonts ภายนอกจาก source และ rebuild site
8. **Quota, gap, dedup และ ledger:** บังคับ strict timestamps/status, exact positive policy values, newline-committed stable JSONL, whole-ledger parse ก่อนเชื่อ match, permanent identity/claim และข้ามเที่ยงคืนด้วย datetime เต็ม
9. **Merchant/revenue/dashboard trust:** tracker ต้องตรง provider/campaign/full URL; promotion ต้องมีหลักฐานสด; dashboard ถูกผูกกับ input และ transitive reader hashes ไม่แสดง pending เป็น paid และไม่ตีความ revenue ที่ยัง reconcile ไม่ได้เป็นศูนย์

## หลักฐานการทดสอบรอบสุดท้าย

- Full pytest: **569 passed + 313 subtests passed**
- Full unittest: **150 passed**
- Preflight behavior matrix: **275/275 passed**; 30 checks ถูกเรียกและมีทั้ง fire/quiet proof
- Calendar: **79/79**, reusable compliance **6/6**
- Public identity: **59/59** และ actual guard ผ่าน 76 หน้า
- Privacy: **18/18** และ actual scan 197 files ผ่าน
- Merchant: **82/82**; actual local/generated scope ผ่าน 16 products, 2 promotions, 110 placements
- Content source: **24/24**; official-news monitor contract ผ่าน
- Publication authority: **56/56**; media guard **34/34**
- Release/funnel: **25/25**; release candidate/manifest ผ่าน
- Runner/receipt: **66 tests + 48 subtests**; receipt-health consumer 8 testsผ่าน
- Actual media corpus: **45/45 วิดีโอ + 1/1 ภาพผ่าน**, findings=0
- Local site: **70/70 หน้า**, affiliate buttons 110 ตัวผ่าน
- `compileall` และ `git diff --check`: PASS
- Independent clean verdicts: `CLEAN_RUNNER_EXIT_CONTRACT`, `CLEAN_CALENDAR_MEDIA_PUBLISH_CONTRACT`, `CLEAN_PUBLIC_SOURCE_DATA_CONTRACT`

## สถานะงานปัจจุบัน

| สถานะ | จำนวน/ผล | หมายเหตุ |
|---|---:|---|
| READY_FOR_OWNER_APPROVAL | 0 | ไม่มีชิ้นใดผ่านทุก gate |
| BLOCKED | 65 placements | ทั้งหมดคง `PLANNED_BLOCKED`; publishable=0 |
| MISSED content slots | 23 | report-only; ห้าม backfill/repost อัตโนมัติ |
| Windows task missed runs | 0 | daily/weekly Ready และ enabled |
| Windows last result | 2 ทั้งคู่ | expected blocked exit; ไม่ใช่ result code crash แต่ receipt history ยังมี invalid 1 รายการ |
| RUNNER_FAILED 7 วัน | 1 historical | control-health เก็บไว้ ไม่ลบ/แก้ย้อนหลัง |
| UNVERIFIED_NONZERO 7 วัน | 1 historical | ไม่ยกเป็น success |
| STUCK task receipts 7 วัน | 0 | preflight ยังเห็น legacy started-only routine นอก trusted receipt contract 1 รายการ |
| SKIP/PAUSED | Instagram | รอ policy review 25 สิงหาคม |

## Blocker ที่ยังถูกต้องและห้ามยกระดับเอง

1. **Publication:** authority=false; calendar 65 placements, 40 content IDs, source-scoped 37/37 blocked, publication blockers 6 และ permanent dedup 90/125 หรือ 72%
2. **Media human review:** `b4-p01` 5 placements ยังรอ human audio review ที่ผูก exact SHA-256 แม้ automated corpus scan ผ่าน
3. **Live release:** local ผ่าน แต่ live parity **0/72** และ production HTML/event taxonomy/link bindings ต่างจาก audited local release; ห้าม deploy อัตโนมัติ
4. **Official sources:** snapshot age 7.82 ชั่วโมงแต่ state=ERROR; changed 13, error 1, pending review 31 ห้าม acknowledge แทนเจ้าของ
5. **GA4:** `UNTRUSTED / INVALID_METADATA`; sessions 102, affiliate_click 6 และ buy_intent 2 เป็น diagnostics เท่านั้น
6. **GSC:** `STALE_WINDOW`; 23 rows, impressions 319, clicks 0 ยังไม่ decisionable
7. **Revenue:** `INVALID_LEDGER / UNRECONCILED`; paid/verified revenue เป็น `null` หรือ “ยังใช้ไม่ได้” ไม่ใช่ 0 บาท Browser diagnostic ที่เห็น pending 35 บาทไม่ใช่ paid revenue และยังขาด exact ALL-status CSV+SHA/import receipt
8. **Receipt history:** มี invalid receipt 1 รายการจากประวัติก่อน fix (`receipt step classification is inconsistent`) จึง trusted terminal rate เป็น unavailable แม้ observed terminal rate=1.0 ต้องเก็บเป็นหลักฐานจริง ห้ามแก้หรือสร้างผลย้อนหลัง
9. **Legacy operations:** preflight พบ delivery gap 8 วันและ started-only weekly-review เก่า ห้าม synthesize terminal row หรือโพสต์ชดเชย

## ลำดับยกระดับที่เป็นประโยชน์สูงสุด

1. เจ้าของยืนยัน private egress สำหรับ GA4 แล้ว repull exact 28-day bundle; จากนั้น repull GSC ด้วย window ปัจจุบัน
2. Export AccessTrade แบบ ALL statuses 28 วันจาก session เจ้าของ เก็บ raw CSV, browser assertion, SHA-256 และ import receipt แล้ว reconcile ledger
3. อ่าน source ที่ changed/error ตาม content ID และ acknowledge เฉพาะสิ่งที่เจ้าของตรวจจริง
4. ทำ human listening ต่อ final video hash และเติม permanent dedup identities ที่ขาด 35 รายการ
5. สร้าง release candidate จาก local, ตรวจ exact diff, ขอ deploy authority แยก และยืนยัน live parity ก่อนเปิด publication
6. เมื่อชิ้นใดผ่าน source + novelty + dedup + quota/gap + media + identity + link + release + private owner receipt ครบ จึงเปลี่ยนเฉพาะชิ้นนั้นเป็น `READY_FOR_OWNER_APPROVAL`

## หลักฐานต้นทาง

- `.local-private/runtime/improvement-runs/audit-loop-20260824-0310-final-runtime/run.json`
- `.local-private/runtime/improvement-runs/audit-loop-20260824-0310-final-runtime/validation.json`
- `.local-private/runtime/improvement-runs/audit-loop-20260824-0310-final-runtime/observation.json`
- `.local-private/runtime/improvement-runs/audit-loop-20260824-0310-final-runtime/diagnosis.json`
- `.local-private/runtime/improvement-runs/audit-loop-20260824-0310-final-runtime/control-health.json`
- `.local-private/runtime/improvement-runs/audit-loop-20260824-0310-final-runtime/maturity-scorecard.json`
- `.system_control/content_calendar.json`
- `.system_control/policy.json`
- `automation-log/post-ledger.jsonl`
- `automation-log/knowledge-base/official-news-snapshot.json`

รายงานนี้เป็นการตรวจภายในและไม่มอบสิทธิ์โพสต์ ตอบคอมเมนต์ ตั้งเวลา deploy หรือสร้าง traffic
