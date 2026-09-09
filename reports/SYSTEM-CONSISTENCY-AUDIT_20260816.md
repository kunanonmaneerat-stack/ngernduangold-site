# รายงานตรวจความสอดคล้องทั้งระบบ เงินเดือนสมองทอง

วันที่ตรวจ: 16 สิงหาคม 2569 (Asia/Bangkok)  
ขอบเขต: นโยบาย สิทธิ์การทำงาน ตารางคอนเทนต์ งานโพสต์ สื่อ เว็บไซต์ ลิงก์พันธมิตร การวัดผล รายได้ และระบบตรวจติดตาม

## ข้อสรุปสำหรับตัดสินใจ

สถานะรวมคือ **NO-GO สำหรับการโพสต์อัตโนมัติ การ deploy และการขยายทราฟฟิกในขณะนี้** แต่ไม่ใช่เพราะระบบล้มเหลวแบบเงียบ ระบบที่แก้แล้วกำลังทำหน้าที่ถูกต้องด้วยการหยุดเมื่อหลักฐานไม่ครบ

- เว็บในเครื่องที่ตรวจแล้วผ่าน smoke test 70/70 หน้า มี affiliate placement 140 จุด และ merchant registry ครบผู้ให้บริการที่ใช้จริง 16 ราย
- เว็บ production ยังต่างจากฉบับที่ตรวจแล้ว 0/72 รายการ มี affiliate placement รุ่นเก่า 185 จุด และยังไม่มี release manifest ที่รองรับ
- รายได้ยังเป็น `UNRECONCILED` จึงห้ามแสดงว่าเป็นศูนย์ที่ยืนยันแล้ว และห้ามเรียก `affiliate_click` ว่า conversion หรือรายได้
- GA4/GSC ถูกเปลี่ยนเป็น atomic observation bundle แล้ว แต่ข้อมูลเดิมยังไม่ผ่านสัญญาใหม่ ต้องดึงรอบใหม่สำเร็จครบชุดก่อนใช้ตัดสินใจ
- แหล่งข้อมูลทางการ 31 แหล่งตอบสนองโดยไม่มี fetch error แต่ 26 แหล่งยังรอ human review; ระบบจึงบล็อกคอนเทนต์ที่เกี่ยวข้องตามหลัก fail-closed
- ปฏิทินมี 65 placements / 40 content IDs แต่ publishable = 0 เพราะทุกช่องยัง `publication_authorized=false`
- ชุดสื่อ active ผ่านการตรวจที่ตั้งไว้: วิดีโอ canonical 24 ชิ้นและภาพ canonical 1 ชิ้น; ไฟล์ที่พบลายน้ำภายนอกถูกกักออกแล้ว

## ตารางสถานะความจริง

| ชั้นระบบ | สถานะ | หลักฐานปัจจุบัน | ผลต่อรายได้/ความเสี่ยง |
|---|---|---|---|
| เว็บในเครื่อง | ผ่าน | 70/70 หน้า, 140 affiliate placements | พร้อมเป็น release candidate หลังผ่าน owner/deploy gate |
| เว็บ production | บล็อก | live/local 0/72; event taxonomy และ release manifest ยังเก่า | ห้ามส่งทราฟฟิกเพิ่ม เพราะ attribution และบางข้อเสนอไม่ตรงฉบับตรวจแล้ว |
| Merchant/offer | ผ่านในเครื่อง | 16 providers, 2 promotion windows, 140 placements | ลดการจับคู่สินค้าผิดประเภทและข้อเสนอหมดอายุ |
| รายได้ | บล็อก | private ledger = `UNRECONCILED` | ห้ามรายงาน 0 บาทว่าเชื่อถือได้หรือเลือกช่องชนะ |
| GA4 | บล็อก | capture เดิมไม่ผ่าน trust/contract ใหม่ | ใช้ได้เพียงวินิจฉัย ห้าม scale |
| GSC | รอดึงรอบใหม่ | สัญญาใหม่ใช้ 28 วันสิ้นสุด D-3 และตรวจ coverage | ป้องกันข้อมูลไม่ final และยอด top-row ไม่ครบ |
| แหล่งทางการ | บล็อก | 31 sources, review pending 26, fetch errors 0 | ห้ามโพสต์ claim ที่ยังไม่ได้ human review |
| ตารางโพสต์ | ปลอดภัยแต่ยังไม่อนุญาต | 65 placements, 40 IDs, publishable 0 | ไม่มี backfill หรือโพสต์ซ้ำโดยอัตโนมัติ |
| สิทธิ์เผยแพร่ | บล็อก | ทุกช่อง `publication_authorized=false`; ต้องใช้ private one-time receipt | ป้องกัน actor string หรือไฟล์อนุมัติปลอม |
| สื่อ | ผ่านสำหรับ active set | 24 videos + 1 image; quarantine ไม่ถูกนำกลับมาใช้ | ลดความเสี่ยงลายน้ำและไฟล์ถูกสับเปลี่ยน |
| Automation ownership | ผ่าน | อ่าน registry จริง 2 แหล่ง; 7 งานมี live owner เดียว, 4 งานไม่มี live owner, 0 งาน both-live | ปิดความเสี่ยงยิงงานซ้ำและไม่ใช้ชื่อโฟลเดอร์เดา owner |
| Privacy ปัจจุบัน | ผ่าน tip/worktree | 32 tracked files, 0 current findings | ประวัติ Git เก่ายังเป็นงานแยก ไม่ควรถือว่าหายไป |

## ความผิดพลาดสำคัญที่พบและแก้แล้ว

### 1. รายงานรายได้เคยแสดงศูนย์แบบมั่นใจเกินหลักฐาน

สาเหตุเดิมคือ writer และ reader ใช้คนละ schema และ metadata-only/legacy rows ถูกตีความได้ว่า trusted zero ผลคือ dashboard อาจแสดง 0 บาท ทั้งที่ยังแยกไม่ได้ระหว่าง “ไม่มีรายได้จริง” กับ “ข้อมูลยังไม่ reconcile”

สิ่งที่แก้:

- แยก private raw intake ออกจาก reconciled ledger
- ใช้ lifecycle ชัดเจน: `pending`, `approved`, `paid`, `rejected`, `refunded`, `cancelled`
- รายได้ North Star นับเฉพาะ `paid`
- การ reconcile ต้องผูก checksum และจำนวนแถวจาก frozen export
- ใช้ lock, fsync และ atomic replace; ข้อมูลผิดรูปหรือยอดติดลบผิดสถานะจะ fail closed
- dashboard ปัจจุบันแสดง `— / UNRECONCILED` แทน 0/TRUSTED

### 2. การวัดผลเคยรวมความหมายคนละประเภท

ปัญหาเดิมรวม `google/organic` กับ `google/cpc`, ใช้ `affiliate_click` แทน conversion และอาจเขียน CSV บางส่วนก่อน query ครบ

สิ่งที่แก้:

- GA4 แยก source + medium + channel และเก็บ raw source
- event contract ครบ `affiliate_click`, `buy_intent_click`, `line_lead_click`, `video_start`, `answer_seen`, `internal_cta_click`
- bundle ทั้งสามตารางถูก stage และ promote พร้อมกัน; sidecar ขยับเป็นลำดับสุดท้ายเท่านั้น
- ผูก trust ณ เวลา capture ไม่ยอมให้เปลี่ยน config ภายหลังแล้วทำให้ข้อมูลเก่ากลายเป็น trusted
- GSC ใช้ช่วง 28 วันสิ้นสุด D-3, normalize query, รวม duplicate, คำนวณ CTR ใหม่ และตรวจ truncation/row counts/hash

### 3. สินค้าและข้อเสนอเคยจับคู่ผิดประเภท

ตัวอย่างที่แก้แล้วคือ KTC PROUD ซึ่งเป็นบัตรกดเงินสดแบบวงเงินหมุนเวียน ไม่ใช่สินเชื่อผ่อนงวดคงที่ และ KTC P BERM เป็นสินเชื่อทะเบียนรถ ไม่ใช่บัตรกดเงินสดทั่วไป

สิ่งที่แก้:

- merchant registry ครบ 16 providers ที่ปรากฏในเว็บ
- ทุก provider มีสถานะ, official URL, วันตรวจ, product type และรายการ content IDs ที่อนุญาต
- promotion window ตรวจทั้งก่อนเริ่ม ระหว่างช่วง และหลังหมดอายุ
- provider ที่ไม่รู้จัก รีวิวเกินอายุ สถานะ paused หรือวางผิด intent จะบล็อก build/release
- เงินเดือน 20,000 บาทแก้เกณฑ์วงเงินบัตรตามแหล่ง ธปท. เป็นไม่เกิน 1.5 เท่าของรายได้เฉลี่ยต่อเดือนสำหรับช่วงรายได้ 15,000 ถึงต่ำกว่า 30,000 บาท

### 4. สิทธิ์เผยแพร่เคยเชื่อเพียงข้อความ `actor=owner`

สิ่งที่แก้:

- FB, IG, TikTok และ YouTube ต้องใช้ private one-time receipt
- receipt ผูก channel, target account, content ID, placement ID, caption hash, asset hash, slot และ nonce
- consume แบบ atomic ก่อน external boundary; replay และ concurrent race ผ่านได้เพียงครั้งเดียว
- เขียน `PENDING_REMOTE` ก่อนเปิด network/browser และจบด้วย `POSTED`, `UNKNOWN` หรือ `PARTIAL_REMOTE`
- ถ้าหลักฐาน remote ไม่ครบ จะห้าม retry แบบเสี่ยงโพสต์ซ้ำและส่งเข้า reconciliation เท่านั้น

### 5. ประวัติโพสต์เดิมมีข้อมูลระบุตัวตนคอนเทนต์ไม่ครบ

สิ่งที่แก้:

- ledger reader ตรวจทุก physical JSONL row; แถวกลางเสีย/ว่าง หรือท้ายไฟล์ขาด จะเป็น `CORRUPT`/`UNKNOWN`
- permanent exact dedup ตามข้อความ normalized และ canonical clip key ในบัญชีเดียวกัน
- check+append อยู่ใต้ lock เดียวและ fsync ก่อนปล่อย lock

ข้อจำกัดคงเหลือ: actual ledger integrity ผ่าน แต่ identity coverage ยังไม่ครบในประวัติเก่า (44 แถวครบ / 81 แถว legacy ไม่ครบ) จึงรับรองย้อนหลังทั้งหมดไม่ได้ ต้องถือแถวเหล่านั้นเป็น blind spot และห้ามใช้การไม่มี match เป็นหลักฐานว่าไม่เคยโพสต์

### 6. สื่อที่มีลายน้ำเคยหลุดผ่านการตรวจเฉพาะขอบภาพ

สิ่งที่แก้:

- กักไฟล์ Gemini sparkle 2 ภาพ และชุด Veo ที่พบปัญหาออกจาก active/site build
- daily media gate ตรวจ canonical reels ทุกไฟล์ ไม่ใช่เฉพาะ staging glob
- future asset ต้องมี hash-bound QA receipt; quarantine/outside-root/symlink ถูกปฏิเสธ
- active canonical set ผ่านการตรวจ 24 วิดีโอและ 1 ภาพ

ข้อจำกัด: เครื่องตรวจเฟรมไม่ใช่หลักฐาน “ไม่มี watermark ทุกชนิด” และไม่ตรวจ SynthID ที่มองไม่เห็น จึงยังต้องมี full-frame human/vision review สำหรับสื่อใหม่ทุกชิ้น

### 7. Preflight เคยให้เวลาตรวจตัวตนเพจสั้นกว่าคลังจริง

รอบตรวจรวมครั้งแรกให้เวลา public identity guard 45 วินาที แต่คลังจริงใช้เวลามากกว่านั้น จึงรายงาน `guard unavailable` ทั้งที่รันเดี่ยวผ่าน แก้เป็นงบ 180 วินาทีและเพิ่ม regression ป้องกันการลดกลับ รอบตรวจรวมถัดมาผ่านครบ 76 หน้า, 161 caption fields, 44 knowledge rows และ 10 outward prompts

## จุดที่ยังผิด/ไม่สอดคล้องและต้องปิดก่อน GO

### P0 — ต้องหยุดก่อนส่งทราฟฟิกหรือเผยแพร่

1. **Production release drift ทั้งเว็บ**  
   เว็บจริงผ่าน release comparison 0/72 และยังใช้ listener/event taxonomy รุ่นเก่า ขณะที่ local ผ่าน 70/70 การโพสต์ CTA ตอนนี้จะส่งคนเข้าสู่เว็บที่ measurement และข้อเสนอไม่ตรงฉบับตรวจแล้ว

2. **หน้า live ชุดจดหมาย 199 บาทยังรับคำสั่งซื้อทั้งที่ไม่มี deliverable**  
   local ปิด CTA และพาไปเครื่องมือตรวจสุขภาพหนี้แล้ว แต่ production ยังต้อง deploy ฉบับตรวจแล้วก่อนจึงปลอดภัย

3. **GA4 และรายได้ยังไม่ decision-ready**  
   ห้ามเรียก raw click ว่า conversion, ห้ามเลือก “ช่องชนะ” และห้ามเพิ่มความถี่จากข้อมูลชุดนี้

4. **Official source review ค้าง 26 แหล่ง**  
   การ fetch ไม่พบ error ไม่ได้เท่ากับการตรวจคำกล่าวอ้าง ต้องมีผู้มีอำนาจอ่าน claim-to-source แล้ว acknowledge พร้อมหลักฐาน

### P1 — ต้องแก้ก่อนเปิด automation เต็มรูปแบบ

1. **Historical attribution ใช้ต่อไม่ได้**  
   live affiliate anchors 185 จุดไม่มี `data-content-id`/`data-pos` และ event เก่าปน CTA ที่ไม่ใช่ affiliate ต้องเริ่ม baseline ใหม่หลัง deploy และ quarantine ข้อมูลเก่าจาก ranking

2. **Merchant redirect ปลายทางยังไม่ควรถูกตรวจด้วยการคลิกลิงก์ tracking**  
   registry และ official page ตรวจได้โดยไม่สร้าง self-click แต่การยืนยันว่า redirect จริงยังตรง merchant ต้องใช้หลักฐานจาก affiliate dashboard/admin endpoint ไม่ใช่เปิด `atth.me`

3. **ประวัติ Git สาธารณะ**  
   privacy guard ปัจจุบันผ่านไม่ได้ลบข้อมูลที่เคยอยู่ใน Git history การ sanitize/rotate/visibility เป็นงาน owner แยกต่างหากก่อน push/deploy

### งาน ownership ที่ปิดแล้วในรอบนี้

- ตัวตรวจอ่าน Claude registry จริงทั้ง Cowork และ CCD พร้อมตรวจ path, record ซ้ำ, enabled state และความคงที่ของ snapshot
- 7 งานที่เปิดมี live owner เดียวทั้งหมด; 3 งานถูกปิดโดย registry และ `ngernduangold-gsc-weekly` ที่ไม่มี registry ถูก tombstone ทั้งสอง roots เป็น `RETIRED — NO-OP`
- production automation guard และ regression 70/70 ผ่าน; prompt ไม่สามารถอ้างตัวเองว่าเป็น mirror/tombstone เพื่อซ่อน enabled registry ได้

## แผนแก้ให้สอดคล้องทั้งหมด

### ระยะ 0 — รักษา NO-GO จนหลักฐานครบ

- คง `publication_authorized=false` ทุกช่อง
- ห้าม backfill งานเก่า ห้าม retry attempt ที่อยู่ `PENDING_REMOTE/UNKNOWN/PARTIAL_REMOTE`
- ห้าม deploy/push ผ่าน actor string หรือสคริปต์ legacy
- ใช้ dashboard เฉพาะสถานะและ blocker; ไม่ใช้ยอดรายได้/ช่องชนะ

### ระยะ 1 — ปิด blocker ที่ไม่ต้องโพสต์

1. Human review official sources 26 รายการแบบผูก content ID และบันทึก reviewer/time/evidence
2. ตั้ง internal traffic exclusion ให้ตรง egress ปัจจุบัน แล้วดึง GA4 bundle ใหม่ครบชุด
3. ดึง GSC bundle ใหม่ด้วยช่วง 28 วันสิ้นสุด D-3
4. นำ frozen affiliate export ที่มี checksum/row count เข้า private reconciliation; ห้ามกรอก conversion จากความจำ
5. ตรวจ historical Git exposure และดำเนินการตาม owner security decision

### ระยะ 2 — เตรียม audited release

1. Build เว็บใหม่จาก source ปัจจุบัน
2. รัน privacy, identity, source, merchant, disclosure, attribution, calendar, media, manifest และ smoke gates
3. สร้าง release manifest ผูก hash ของทุกไฟล์
4. Owner ใช้ช่องทาง deploy ที่มี proof จริงและ exact scope
5. หลัง deploy รัน live/local compare; ต้องผ่าน 72/72 หรือจำนวนใหม่ที่ derive จาก manifest และต้องไม่มี legacy salary URL
6. ตรวจหน้า P0 โดยตรง: debt-letter-kit ไม่มี 199 บาท/PromptPay/ส่งสลิป; salary-30000 ไม่มี claim 45k–60k; `/links` ใช้ event taxonomy ใหม่

### ระยะ 3 — เปิดโพสต์แบบจำกัดและวัดผลใหม่

- เปิดทีละ channel/placement ด้วย private one-time receipt เท่านั้น
- ใช้ text-only content ที่ source review ผ่านก่อน; สื่อใช้เฉพาะชิ้นที่มี per-piece receipt
- เริ่ม baseline ใหม่วัน deploy; ข้อมูลเก่าถูกติดป้าย contaminated/legacy
- แยก North Star เป็น `paid affiliate commission THB`; driver คือ qualified affiliate click, buy intent, landing engagement และ GSC clicks
- ห้าม scale จนมี paid transaction ที่ reconcile ได้หรือ trusted-zero export ครบช่วงทดสอบ

### ระยะ 4 — วงจรป้องกันถาวร

**ทุกวัน**

1. ตรวจ policy/role/calendar/registry ownership
2. ตรวจ source fingerprint และ merchant review/promotion expiry
3. ตรวจ privacy, page identity, disclosure, attribution และ release parity
4. ตรวจสื่อทุก canonical/future route พร้อม hash receipt
5. ดึง analytics แบบ atomic; query ใดล้มเหลวให้คง bundle เดิมและคืน nonzero
6. สรุป blocker แบบ local-only โดยไม่มี notification/publish/browser side effect

**ทุกสัปดาห์**

1. Reconcile revenue กับ frozen affiliate export
2. ตรวจ D-3 GSC coverage/truncation และ GA4 capture-time trust
3. ตรวจ content fatigue/dedup ด้วย text hash, asset hash, audio hash และ perceptual similarity
4. รีวิว provider taxonomy/official URL/expiry และ landing intent fit
5. เลือกการทดลองเพียงหนึ่งรายการเมื่อ privacy + source + measurement + revenue + release gates ผ่านทั้งหมด

## เกณฑ์ GO ที่วัดได้

| เกณฑ์ | ต้องเป็น |
|---|---|
| Production parity | ทุก URL ใน release manifest ตรง local; ไม่มี legacy URL |
| Official sources | relevant `review_required=0`, errors=0, fresh ตาม SLA |
| GA4 | bundle ใหม่ครบ, capture-time trust = TRUSTED, hash/rows/window ผ่าน |
| GSC | bundle ใหม่ครบ, D-3, non-truncated หรือประกาศ coverage ชัด |
| Revenue | schema 3 reconciled; paid/pending/approved แยกได้ หรือ trusted zero จาก frozen export |
| Publication | channel authorized + private one-time receipt + exact target |
| Calendar | exactly one placement owner, cap/gap/dedup/source/media gates ผ่าน |
| Media | per-piece hash-bound receipt; ไม่มี active quarantined asset |
| Automation | exactly one live registry task ต่อ task ID |
| Privacy | current guard ผ่าน และ owner ตัดสิน historical exposure แล้ว |

## ผลตรวจรวมรอบสุดท้าย

- Full preflight: **3 FAIL / 7 WARN**; FAIL เหลือเฉพาะ GA4 trust, official source review และ live release parity
- Local build smoke: **70/70 PASS**, affiliate placements 140
- Live/local release compare: **0/72 FAIL**, live affiliate placements 185
- Automation ownership/policy: production PASS; regression **70/70 PASS**
- Preflight regressions: **229/229 PASS**
- Pipeline/analytics tests: **76/76 PASS**
- Merchant gate: **16 providers / 2 promotions / 140 placements / 77 documents PASS**
- Publication authority: **21/21 PASS**
- Active media inventory: **24/24 videos + 1/1 image PASS**; quarantine scanned 0
- Python compile: **130 changed/new files PASS**
- Whitespace/diff check: PASS (มีเพียงคำเตือน line-ending ของ working tree)

## สิ่งที่ไม่ได้ทำในรอบนี้

- ไม่โพสต์ ไม่เปิด browser composer ไม่อัปโหลดสื่อ
- ไม่ click affiliate tracker เพื่อหลีกเลี่ยง self-click
- ไม่ acknowledge official sources แทนมนุษย์
- ไม่สร้าง/แก้ conversion หรือรายได้ที่ไม่มีหลักฐาน
- ไม่ commit, push หรือ deploy
- ไม่ลบ/ย้อนงาน concurrent หรือไฟล์เดิมของผู้ใช้

## แหล่งทางการที่ใช้ยืนยันข้อเท็จจริงตัวอย่าง

- ธปท. เรื่องบัตรเครดิตและเกณฑ์วงเงิน: https://www.bot.or.th/th/satang-story/digital-fin-lit/creditcard.html
- KTC PROUD: https://www.ktc.co.th/loan/ktc-proud?lang=th_TH
- KTC P BERM: https://www.ktc.co.th/ktc-p-berm
- Happy Cash: https://www.lhbank.co.th/th/personal/loans/happy-cash-personal-loan/

## ข้อจำกัดของรายงาน

รายงานนี้ยืนยันสถานะ local working tree และการอ่านเว็บ production ณ วันที่ตรวจ ไม่ได้รับประกันรายได้ ผลของ affiliate ขึ้นกับ demand, approval, merchant attribution และการส่งมอบจริง การขยายควรเกิดหลังมีข้อมูลที่ reconcile ได้ ไม่ใช่จากจำนวนคลิกดิบ
