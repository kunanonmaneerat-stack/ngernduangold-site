# รายงานตรวจระบบเงินเดือนสมองทอง — 23 สิงหาคม 2026

ตรวจ ณ `2026-08-23T14:55:31+07:00` ภายใต้โหมด local-safe และในนามเพจเท่านั้น

## ข้อสรุปผู้บริหาร

ระบบควบคุมปลอดภัยและตรวจสอบย้อนกลับได้ดีขึ้นอย่างมีนัยสำคัญ แต่ **ยังไม่พร้อมโพสต์ ไม่พร้อมเลือกช่องชนะ และไม่พร้อมเพิ่มสเกล affiliate** คะแนนหลักฐานล่าสุดอยู่ที่ **40/100 (instrumented)** สถานะ `VALID_WITH_BLOCKERS`; evidence bundle ผ่าน validation, ไม่พบ regression ใหม่ และ executable guard 8 กลุ่มผ่านทั้งหมด

ผลลัพธ์ที่สำคัญที่สุดคือระบบไม่สามารถเลื่อน `PLANNED_BLOCKED` เป็นพร้อมเอง, ไม่ใช้ source queue รวมมาอนุญาตชิ้นงาน, ไม่ตี click เป็น conversion, ไม่ตีรายได้ที่ตรวจไม่ได้เป็นศูนย์ และไม่ยอมให้ snapshot/registry/media/approval เปลี่ยนหลัง owner receipt แล้วหลุดไปแตะ API

สิ่งที่ยังขวางรายได้คือหลักฐานต้นน้ำ ไม่ใช่คุณภาพตัว guard: GA4 ไม่ trusted, GSC stale, ledger รายได้ไม่ reconciled, official-source snapshot invalid/pending, permanent dedup coverage ยังไม่ครบ, ไม่มีชิ้นใด publishable และ production ยังไม่ตรง local release

## สถานะงานปัจจุบัน

| สถานะ | จำนวน | ความหมาย |
|---|---:|---|
| `READY_FOR_OWNER_APPROVAL` | 0 | ยังไม่มีชิ้นใดผ่านทุก gate จึงไม่มีคำขออนุมัติโพสต์ |
| `BLOCKED` ภายใน 48 ชั่วโมง | 7 | ทุกแถวยังคง `PLANNED_BLOCKED`; ห้าม backfill หรือ promote |
| `COMPLETED_BLOCKED` | 22 | slot เก่าที่ไม่เคย eligible; เก็บไว้เป็นประวัติ ไม่จัดเป็น missed post |
| `RUNNER_FAILED` | 0 ที่พิสูจน์ได้ | Windows task ไม่ missed/ไม่ stuck; แต่ยังไม่มี schema-2 receipt หลังเริ่ม instrumentation |
| `MISSED` | 0 | ไม่มี eligible/authorized slot ที่ถูกพลาด |
| `SKIP` | 2 เงื่อนไข | Pantip temporary monitor หมดอายุแล้ว; Instagram ยัง paused รอ review 25 ส.ค. |

เจ็ด placement ในหน้าต่าง 48 ชั่วโมงคือ `b3-04__tiktok_main`, `kn-37__threads_main`, `kn-37__facebook_main`, `tt-r14-08__tiktok_main`, `kn-38__threads_main`, `kn-38__facebook_main` และ `p2-11__facebook_page2` ทุกชิ้นติด publication authority และ official-source review; TikTok ยังติด channel review, owner confirmation, live dedup/landing/bio parity และ media receipt โดย `tt-r14-08` ไม่มี media ด้วย

## สิ่งที่แก้แล้วและตรวจผ่าน

1. **Source authority แบบ content-scoped** — ผูก `content_id → source_ids → official_urls` แบบ exact, เพิ่ม source IDs ให้ registry ครบ, ทำ schema-3/queue-chain validation แบบ fail-closed และห้าม local checksum หรือ actor string ปลอมเป็น owner acknowledgement ปัจจุบันตรวจ 37 content IDs: allowed 0, blocked 37, structural finding 0
2. **Publication authority/TOCTOU** — hook ที่ inject เข้ามาเป็นเพียง extra blocker; canonical gate รันเสมอ, private consumed receipt ผูก action/evidence, snapshot+registry hash ถูกตรวจซ้ำ, source freshness ถูกตรวจซ้ำหลัง OAuth และตรวจอีกครั้งก่อน external mutation
3. **Official change detection** — script-only และ claim ใน script ที่ซ่อนหลัง boilerplate ไม่สามารถถูกสรุป `unchanged`; raw drift ถูกส่งเข้า owner review แม้อาจเกิด false-positive มากขึ้น
4. **Calendar/dedup** — namespace และ placement claim ถูกตรวจทุกแพลตฟอร์มอย่างอิสระ; calendar 65 placements มี structural error 0 แต่ permanent identity coverage ยัง 44/125 (35.2%), incomplete 81 และพบ duplicate canonical identity 1 กลุ่ม
5. **Media/privacy/identity** — วิดีโอ canonical 24 ไฟล์และภาพ 1 ไฟล์ผ่าน hash/watermark QA; privacy scan 51 candidate files ผ่าน; public identity ผ่าน 76 pages, 161 caption fields, 44 knowledge rows และ 10 outward prompts
6. **Merchant/link/site local** — merchant offer gate ผ่าน 16 products, 2 promotions, 140 placements, 97 documents; local build smoke ผ่าน 70/70 pages และ 140 affiliate buttons
7. **Local release evidence** — สร้างและตรวจ content-addressed release candidate ในเครื่องแล้ว 118 members; candidate verification ผ่าน และ predeploy acceptance ผ่าน 11/11 โดยหลักฐานนี้ไม่ให้อำนาจ deploy
8. **Runner semantics** — daily/weekly runner แยก business blockerออกจาก runner failure, มี terminal reason/step และ hash-stable receipt contract; tests ทั้ง tools 172/172 และ pipeline 177/177 ผ่าน

## ผล preflight รอบปิดงาน

preflight เต็มชุดได้ `20 PASS / 7 WARN / 4 FAIL` หลังแก้ dashboard analytics-reader provenance ที่ stale แล้ว จุด FAIL ที่เหลือคือ delivery gap 7 วัน, GA4 internal-traffic trust, publish readiness จาก `PERMANENT_DEDUP_INCOMPLETE` และ live/release parity ทั้งหมดเป็น blocker จริงที่ระบบหยุดไว้ ไม่ใช่ test crash หรือหลักฐานว่ามี authorized post ถูกพลาด

WARN ที่ต้องติดตามคือ video queue/clip queue ว่าง, legacy weekly-review มี started row ค้าง, revenue ยัง unreconciled, traffic diagnosis ถูก suppress, official-source review ยังไม่ครบ และ decision เก่าของ Pantip ยังแสดง overdue ใน generic register แม้ temporary monitoring condition หมดอายุและต้อง `SKIP` ตามขอบเขตปัจจุบัน

## จุดบกพร่องที่ยังเปิดอยู่

### P0 — ข้อมูลตัดสินใจยังไม่น่าเชื่อถือ

- GA4: `UNTRUSTED / INVALID_METADATA`; private egress ไม่อยู่ใน CIDR ที่ยืนยัน และ coverage internal traffic ยังไม่ครบ 28 วัน ตัวเลข observed จึงเป็น diagnostic เท่านั้น
- GSC: `STALE_WINDOW`; ห้ามใช้ impression/click เก่าเลือกหัวข้อ เวลา หรือช่องชนะ
- Revenue: `STALE_COVERAGE / UNRECONCILED`; coverage ล่าสุดสิ้นสุด 17 ส.ค. และ paid/verified fields เป็น `null` รายได้จึง **ไม่พร้อมใช้ตัดสิน ไม่ใช่ศูนย์บาท**
- Official sources: snapshot `INVALID`, pending owner review 30, changed 20, error 0; queue attestation ขาดและมี content-type mismatch อย่างน้อยหนึ่ง source

### P1 — พร้อมในเครื่อง แต่ยังไม่พร้อมปล่อยจริง

- Production smoke ผ่าน 0/72 pages ขณะที่ local ผ่าน 70/70; production มี 185 affiliate buttons และยังขาด event taxonomy/data-content-id พร้อม release drift
- publication authority ไม่มี channel ที่ authorized และ calendar publishable = 0
- permanent dedup coverage ต่ำ ทำให้ historical identity ยังป้องกันซ้ำไม่ได้ครบ

### P2 — หลักฐานการเดินงานยังไม่ครบ

- `ngernduangold_daily` และ `ngernduangold_weekly` อยู่สถานะ Ready, missed runs = 0; last result = 2 แต่ instrumentation เริ่มหลังรอบเช้า จึงยังระบุ terminal class ของรอบนั้นไม่ได้จาก receipt ใหม่ (`NO_RECEIPTS`, origin `RUNNER_INVOCATION_UNVERIFIED`)
- runlog เก่ายังมี `ngernduangold-weekly-review` started โดยไม่มี terminal row ประมาณ 318 ชั่วโมง ต้อง reconcile โดยไม่สร้างผลลัพธ์ย้อนหลังปลอม
- canonical YouTube positive execution path ยังไม่มี unmocked fixture ที่ผ่าน เพราะ owner-controlled source acknowledgement verifier ยังไม่ถูกสร้าง นี่เป็น liveness gap ที่ปลอดภัยแบบ fail-closed

## แผนยกระดับตามลำดับประโยชน์รายได้

1. **กู้ measurement trust** — เจ้าของยืนยัน private egress ownership ก่อนแก้ CIDR, repull GA4 แบบ hash-bound ครบ 28 วัน และ repull GSC page-grain ให้ current เกณฑ์ผ่านคือ GA4 `TRUSTED`, GSC `CURRENT`, metadata hash ตรงทั้งหมด
2. **reconcile รายได้จริง** — import/export AccessTrade แบบ schema-5 จากไฟล์ owner-provided, ปิด coverage ครบหน้าต่าง, reconcile lifecycle และ paid commission ตาม transaction ID เกณฑ์ผ่านคือตัวเลข paid/verified เป็น canonical money พร้อม provenance; ห้ามใช้ click แทน
3. **ปิด source review อย่างมีอำนาจจริง** — สร้าง owner-controlled signed/private acknowledgement verifier, แก้ source content-type mismatch และ refresh snapshot; ห้ามให้ agent หรือไฟล์ใน repo รับรองตัวเอง
4. **ปิด permanent dedup** — เติม identity ให้ 81 รายการและ reconcile duplicate กลุ่มเดิมโดยไม่ลบ ledger append-only เกณฑ์ผ่านคือ 125/125 และ collision 0 ก่อนเปิด slot
5. **ปิด live/local parity ภายใต้อำนาจแยกต่างหาก** — local candidate แบบ content-addressed และ predeploy evidence พร้อมแล้ว แต่ห้าม deploy เอง; เมื่อได้รับ deploy authority ที่เจาะจง จึงปล่อย exact candidate และตรวจ event taxonomy/data-content-id/live smoke ซ้ำ
6. **เปิดโพสต์แบบทีละชิ้น** — หลังทุก gate ผ่าน จึงสร้าง `READY_FOR_OWNER_APPROVAL` พร้อม exact content ID, caption hash, asset hash, source hashes, account, slot และ one-time receipt; ไม่อนุมัติเป็น batch กว้าง

## วงจรเรียนรู้ที่ระบบใช้ต่อได้

`observe → validate contracts → diagnose → rank local-safe actions → execute guards → bind evidence hashes → compare incidents/regressions → request exact owner action`

วงจรนี้ทำงานแล้วในระดับ instrumented แต่ `learning_ready=false` เพราะยังไม่มี trusted analytics, reconciled paid revenue และ publication input ที่พร้อม การเพิ่มความถี่หรือเลือก winner ก่อนปิดสามเงื่อนไขนี้จะเป็นการเรียนรู้จากข้อมูลผิด

## ขอบเขตที่ไม่ได้แตะ

รอบนี้ไม่มีการโพสต์ ตั้งเวลา ตอบคอมเมนต์ กดไลก์ เปิด tracker/AccessTrade สร้าง test traffic acknowledge source ใช้ paid API/LLM deploy commit push หรือแก้ Windows scheduled task การเปลี่ยนแปลงทั้งหมดเป็น local control code, registry metadata, tests และ evidence artifacts
