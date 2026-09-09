# รายงานตรวจสอบและยกระดับระบบ เงินเดือนสมองทอง — 23 สิงหาคม 2026

ตรวจล่าสุด 23:31 น. Asia/Bangkok จาก evidence bundle `audit-final-20260823-2325`

## คำตอบสรุป

ระบบควบคุมทำงานถูกต้องในสถานะ **VALID_WITH_BLOCKERS** และตรวจตัวเองได้จริง แต่ **ยังไม่พร้อมโพสต์ ไม่พร้อมทดลองขยาย และยังสรุปรายได้ไม่ได้** คะแนนปัจจุบันคือ **40/100 ระดับ instrumented**: หลักฐานรอบปัจจุบันผ่าน การผูกแหล่งข้อมูลรายชิ้นผ่าน และ guardrail ทั้ง 8 ชุดผ่าน แต่เสียคะแนนทั้งหมดในส่วนรายได้ ความน่าเชื่อถือของ analytics และความพร้อมเผยแพร่

รอบสุดท้ายจบแบบ `COMPLETED_WITH_BLOCKERS`, validation ผ่าน, พบ incident คงค้าง 4 รายการ, regression ใหม่ 0 และปิด incident ด่านสื่อได้ 1 รายการ ไม่มีการโพสต์ ตั้งเวลา ตอบคอมเมนต์ deploy commit push ใช้ paid API หรือเปลี่ยนบัญชีภายนอก

## สถานะปฏิบัติการ

| สถานะ | จำนวน | ความหมาย |
|---|---:|---|
| READY_FOR_OWNER_APPROVAL | 0 | ยังไม่มีชิ้นใดผ่านทุก gate |
| BLOCKED | 65 placements | ปฏิทินทั้งหมดคงเป็น `PLANNED_BLOCKED` |
| MISSED | 23 slots | ช่องเวลาเก่าถูกเก็บเป็น report-only ห้าม backfill/repost อัตโนมัติ |
| COMPLETED_BLOCKED | 3 runs/tasks | control loop ล่าสุดและ Windows tasks 2 ตัวทำงานจบพร้อมรายงาน blocker |
| SKIP | 1 channel | Instagram พักตาม policy รอทบทวน 25 ส.ค. |
| RUNNER_FAILED | 0 | ไม่พบ runner crash; Windows result code 2 หมายถึงจบพร้อม blocker |

หมายเหตุ: จำนวนแต่ละสถานะใช้คนละระดับข้อมูลและอาจซ้อนกัน เช่น MISSED เป็นส่วนหนึ่งของ placements ที่ BLOCKED

## จุดผิดพลาดที่แก้แล้ว

### 1. ความน่าเชื่อถือของข้อมูลรายได้และ dashboard

- ผูก dashboard กับโค้ดอ่านรายได้ทางอ้อมทุกตัว ไม่ให้ dashboard เก่าที่เคยแสดง “ศูนย์ที่เชื่อถือได้” รอดหลัง importer/ledger เปลี่ยน
- เพิ่ม transaction facts แบบไม่เปิดเผยรหัสธุรกรรมหรือข้อมูลส่วนตัว และคำนวณจำนวน สถานะ เงิน แหล่งที่มา และวันล่าสุดย้อนกลับจาก facts จริง ป้องกัน payload ศูนย์ปลอมที่แก้ตัวเลขให้สอดคล้องกันเอง
- แช่แข็งและตรวจแฮชไฟล์ GA4/GSC ทุกไฟล์ที่ observation ใช้ ปิดช่องข้อมูลเปลี่ยนระหว่างอ่าน
- แก้การตีความเวลา GA4 ให้เป็น Asia/Bangkok และปฏิเสธ timestamp ที่ไม่มี timezone

### 2. ลิงก์ affiliate และข้อความโปรโมชั่น

- บังคับ `/go` route, tracker และ provider ให้ตรงทะเบียนแบบเต็ม URL; suffix/query/fragment/domain ปลอมไม่ผ่าน
- โปรโมชั่นต้องมี `verified_on` ที่ยังไม่หมดอายุ
- qualifier ของ claim ต้องอยู่ใน structural block เดียวกัน และ claim เดิมที่ซ้ำในบล็อกเดียวกันถูกปฏิเสธ ไม่สามารถยืม qualifier กันได้
- ด่านจริงผ่าน 16 products, 2 promotions, 110 placements และ 98 documents

### 3. ขอบเขตการเผยแพร่

- Facebook ตรวจสิทธิ์ซ้ำทันที ก่อน API mutation ของคอมเมนต์ครั้งที่สอง
- daily reminder ถูกลดเป็น local-only card ไม่ส่ง Hermes/Telegram
- TikTok ตรวจบัญชีที่ล็อกอินแบบ exact ก่อนและหลัง login ตรวจ caption readback แบบ exact และบล็อก live เมื่อไม่มี authenticated-account reader ที่ผ่าน review
- แยกสถานะ completed-with-blockers ออกจาก runner failure ไม่ให้ exit code 2 ถูกตีความเป็นระบบล่ม

### 4. ปฏิทิน dedup quota และ ledger

- ตรวจระยะห่างข้ามเที่ยงคืนด้วย datetime เต็ม และรวมโพสต์สำเร็จจาก ledger เข้า cap/gap
- ปฏิเสธสถานะหรือ timestamp ที่อ่านไม่ได้
- ปฏิเสธ base ledger หลายแถวที่ใช้ dedup key เดียวกัน แม้มี status row มาบัง collision
- คง `PLANNED_BLOCKED` เป็น blocked และไม่ยกระดับเป็นพร้อมเอง

### 5. สื่อ ความเป็นส่วนตัว และตัวตนสาธารณะ

- privacy guard ตรวจหมายเลขโทรศัพท์ไทยที่มีเว้นวรรค จุด ขีด และ `+66` รวมทั้งไฟล์ generated/release ที่อาจถูก gitignore โดยไม่พิมพ์ค่าที่พบ
- แก้ false positive IPv6 จาก CSS pseudo-element
- เติม SHA-256 binding ให้หลักฐานภาพโปสเตอร์เดิมทั้งสองไฟล์; ด่านสื่อรอบเต็มผ่าน 45 วิดีโอและ 1 ภาพ
- public identity ผ่านในนามเพจเท่านั้น: 76 หน้า, 161 caption fields, 44 knowledge rows และ 10 outward prompts

### 6. เว็บ local/live และความทนทานของชุดทดสอบ

- live smoke บังคับ exact origin, ห้าม redirect, จำกัดขนาด/จำนวน และปฏิเสธ sitemap URL ที่อยู่นอก origin
- test loader ไม่หยุดทั้งชุดเมื่อ dependency ตัวหนึ่งเสีย และ observation test รันแบบ package ได้
- แก้ generator ของ `PREFLIGHT-ALERT.md` ไม่ให้สร้าง trailing whitespace และคงไฟล์ `.cmd` เป็น CRLF ทั้งไฟล์

## หลักฐานตรวจสอบหลังแก้

- Root regression suite: **133/133 ผ่าน**
- Preflight behavior matrix: **261/261 ผ่าน**
- Merchant gate tests: **71/71 ผ่าน**
- Revenue ledger tests: **20/20 ผ่าน**
- Observation bundle tests: **19/19 ผ่าน**
- Improvement-loop tests: **57/57 ผ่าน**
- Media scan: **45/45 วิดีโอ + 1/1 ภาพผ่าน**
- Privacy: **197 files ผ่าน**
- Local site: **70/70 หน้า, 110 affiliate buttons ผ่าน**
- Final control validation: **PASS**, runtime contract ไม่เปลี่ยนระหว่างรอบ

## Blocker ที่ยังห้ามโพสต์

1. **เว็บ live ต่างจาก local/release:** local ผ่าน 70/70 แต่ live parity ผ่าน 0/73 และพบ 185 ปุ่มบน live เทียบกับ 110 ปุ่มใน local รวมทั้ง taxonomy, `data-content-id`, provider registry และ HTML drift ห้าม deploy อัตโนมัติ; ต้องสร้าง release candidate ตรวจ แล้วขอสิทธิ์ deploy โดยเฉพาะ
2. **ปฏิทิน:** 65 placements, 40 content IDs, publishable 0, stale 23; source-scoped 37/37 ถูก block ด้วยเหตุผลรวม 246 รายการ
3. **สื่อ:** active placements 5 รายการของ `b4-p01` รอการฟังโดยมนุษย์ที่ผูกกับ exact asset hash; วิดีโอ R5 สัปดาห์ 24–30 ส.ค. ยังเป็น draft-only ด้วยเหตุเดียวกัน
4. **Permanent dedup:** ครบ 90/125 หรือ 72%; ยังขาด identity 35 รายการ จึงห้ามยืนยันว่าเป็นโพสต์ใหม่แบบถาวร
5. **GA4:** `UNTRUSTED / INVALID_METADATA`; ค่า sessions 102 และ affiliate_click 6 เป็น diagnostics เท่านั้น ห้ามเลือกช่องชนะ เวลา ความถี่ หรือ scale
6. **AccessTrade:** `INVALID_LEDGER / UNRECONCILED`; รายได้ที่ยืนยันแล้วเป็น **ไม่พร้อมใช้** ไม่ใช่ 0 บาท
7. **Official sources:** เปลี่ยน 13, error 1, รอ review 31; ต้องตรวจเฉพาะแหล่งที่ผูกกับ content ID นั้น
8. **Run/decision hygiene:** `ngernduangold-weekly-review` มี started row ค้าง 326 ชั่วโมง และ Pantip review เลยกำหนด 5 วัน ห้ามสร้าง terminal row หรือผลการตรวจย้อนหลังขึ้นเอง

GSC ยัง `CURRENT` ณ รอบนี้ แต่ receipt หมดอายุ 24 ส.ค. 00:00 น. ต้อง refresh ก่อนใช้ในรอบถัดไป

## ลำดับยกระดับที่ถูกต้อง

### P0 — ต้องผ่านก่อนเผยแพร่

1. เจ้าของยืนยันว่า private egress ปัจจุบันเป็นของตนก่อนแก้ GA4 exclusion แล้ว repull exact 28-day bundle
2. ดึง AccessTrade transaction view 28 วันจาก session ที่ยืนยันตัวตน พร้อม scope/filter หลักฐาน แล้ว reconcile ledger จน full contract ผ่าน
3. ตรวจ official-source change/error ราย content ID; acknowledge เฉพาะรายการที่อ่านและยืนยันแล้ว
4. ฟังไฟล์ final จริงและบันทึก human review ที่ผูก SHA-256; เติม permanent identity อีก 35 รายการ
5. สร้าง release candidate จาก local, ตรวจ exact diff, ขอ deploy authority แล้วต้องได้ live parity 73/73 ก่อนเปิดโพสต์

### P1 — คืนความต่อเนื่องของคอนเทนต์

1. หลัง P0 ผ่าน ให้ลงทะเบียน R5 drafts วันที่ 24–30 ส.ค. เป็น per-channel `PLANNED_BLOCKED` ก่อน
2. รัน source, novelty, dedup, cap/gap, media, landing, identity และ release gate ต่อ placement
3. เฉพาะชิ้นที่ผ่านครบจึงเปลี่ยนเป็น `READY_FOR_OWNER_APPROVAL`; owner approval ต้องผูก content, channel, caption, asset hash และเวลาแบบรายชิ้น
4. ปิด weekly-review ค้างและ Pantip decision ด้วยหลักฐานจริง ไม่สร้างสถานะย้อนหลัง

### P2 — ปิด residual risk เชิงสถาปัตยกรรม

- สร้าง remote reconciler สำหรับ `PENDING/UNKNOWN`
- ใช้ immutable byte snapshot สำหรับ TikTok/YouTube และ content-addressed URL สำหรับ Instagram
- ทำ shared atomic dedup/quota/gap claim ให้ Facebook, Instagram และ YouTube
- ผูก TikTok remote result กับ submission ID/asset/caption ไม่อาศัย “permalink ใหม่ล่าสุด”
- แยก signer/OS ACL สำหรับ owner receipt เพื่อให้เป็นหลักฐานอิสระจาก publisher process

## วงจรเรียนรู้ที่ระบบทำได้แล้ว

ระบบรอบปัจจุบันใช้ลูป `observe → validate evidence → score → diagnose incident → enqueue bounded action → rerun → compare fingerprint` และ fail closed เมื่อหลักฐานไม่ครบ รอบสุดท้ายมี incident คงค้าง 4, recurring 4, regression 0 และ resolved 1 จึงแยก “แก้โค้ดแล้ว” ออกจาก “ธุรกิจพร้อมแล้ว” ได้ถูกต้อง

เกณฑ์ปิดงานในรอบถัดไปคือ runtime hash คงที่, guard ทุกชุดผ่าน, GA4/revenue decisionable, source รายชิ้น current, live parity ผ่าน, dedup 125/125, media human review ครบ และมี placement อย่างน้อย 1 ชิ้นที่ผ่านทุก gate ก่อนขอเจ้าของอนุมัติ

## หลักฐานต้นทาง

- `.local-private/runtime/improvement-runs/audit-final-20260823-2325/run.json`
- `.local-private/runtime/improvement-runs/audit-final-20260823-2325/validation.json`
- `.local-private/runtime/improvement-runs/audit-final-20260823-2325/maturity-scorecard.json`
- `.local-private/runtime/improvement-runs/audit-final-20260823-2325/observation.json`
- `.local-private/runtime/improvement-runs/audit-final-20260823-2325/diagnosis.json`
- `.system_control/content_calendar.json`
- `.system_control/policy.json`
- `automation-log/post-ledger.jsonl`
- `automation-log/knowledge-base/official-news-snapshot.json`

รายงานนี้เป็น snapshot ตรวจสอบภายใน ไม่ใช่สิทธิ์เผยแพร่หรือ deploy
