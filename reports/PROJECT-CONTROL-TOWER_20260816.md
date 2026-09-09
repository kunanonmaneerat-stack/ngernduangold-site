# Project Control Tower — ยกระดับคุณค่า ความถูกต้อง และรายได้

> **SUPERSEDED สำหรับสถานะล่าสุด:** โปรดใช้ `AFFILIATE-PAGE-ONLY-AUDIT_20260816.md` เป็นรายงานตัดสินใจหลัก รายงานนี้เก็บไว้เป็นหลักฐานรอบก่อนและมีตัวเลข privacy/source/release ที่ล้าสมัยแล้ว

> สถานะตรวจล่าสุด: 16 สิงหาคม 2026 · Asia/Bangkok  
> ขอบเขต: นโยบาย, เว็บ, สินค้า, งานโพสต์, วิดีโอ, automation, GA4/GSC, sales ledger และแหล่งข้อมูลทางการ  
> คำตัดสิน: **งานในเครื่องได้รับการยกระดับแล้ว แต่ยังห้ามเผยแพร่/commit/push/deploy จนกว่าด่าน STOP จะผ่าน**

## 1. คำตอบแบบสั้นที่สุด

โปรเจกต์ไม่ได้ติดที่ “โพสต์น้อย” เพียงอย่างเดียว จุดที่ทำให้รายได้ไม่เดินคือข้อมูลตัดสินใจยังปนการทดสอบ, หน้าเว็บจริงยังล้าหลังกว่าไฟล์ในเครื่อง, สินค้าหนึ่งรายการเคยเปิดรับเงินทั้งที่ไม่มีไฟล์ส่งมอบ, และงานอัตโนมัติหลายชุดเคยมีสิทธิ์เกินนโยบาย การเร่งทราฟฟิกก่อนปิดจุดเหล่านี้จะขยายความเสียหายมากกว่ารายได้

รอบนี้จึงลงมือแก้ฐานก่อน ได้แก่ ปิดกลไกรับเงินของสินค้าที่ส่งไม่ได้, แยก event ตามเจตนาจริง, แก้รายงานที่อ่าน schema ผิด, ปิด publisher เก่า, ทำ policy/manifest/source guard แบบ fail-closed, แก้ข้อความการเงินสำคัญ และ build เว็บในเครื่องผ่านทั้งหมด

เป้าหมายถัดไปไม่ใช่ “เพิ่มจำนวนโพสต์” แต่เป็นวงจรนี้:

**แหล่งทางการผ่าน → เนื้อหามีประโยชน์ → หน้าเว็บตรงคำถาม → CTA ตรงเจตนา → วัด downstream intent → นับเฉพาะยอดขายที่ยืนยันแล้ว → ขยายเพียงหนึ่ง funnel ที่ชนะ**

## 2. ด่านตัดสินปัจจุบัน

| ด่าน | หลักฐานปัจจุบัน | คำตัดสิน | สิ่งที่ทำได้ตอนนี้ |
|---|---|---|---|
| Privacy ของ public repo | FAIL 30 findings จาก 32 tracked files | **STOP** | ตรวจ/ทำแผน private, rotate, redact และ history cleanup; ห้าม push/deploy |
| แหล่งข้อมูลทางการ | 26/26 ตอบ HTTP 200, errors=0, แต่ review_required=21 | **STOP เฉพาะการเผยแพร่** | อ่านและรับรองทีละแหล่ง; ห้าม acknowledge แบบเหมา |
| สิทธิ์เผยแพร่ | role matrix ให้ social publish/commit/push/deploy แก่ owner เท่านั้น | **OWNER-ONLY** | Codex/Cowork/Claude Code ทำร่าง, QA และรายงานในเครื่องเท่านั้น |
| GA4 internal traffic | IP ปัจจุบันไม่อยู่ใน CIDR ที่กำหนด | **UNTRUSTED** | ใช้ตัวเลขเป็น observed signal; ห้ามประกาศ winner หรือ scale |
| `letter-kit-199` | ไม่มี PDF 10 หน้าตามคำสัญญา | **STOP** | ปิดขาย/ปิด traffic; สร้าง+QA deliverable หรือ retire |
| Pantip | paused, quota=0, phase เดิมหมด 14 ส.ค. | **NO-OP** | ไม่ร่าง ไม่โพสต์ ไม่แปะลิงก์ จนมี phase ใหม่ |
| Video future schedule | ไม่มีรายการที่ผ่าน publication gate ครบ | **NO-OP** | ใช้ `b4-p01` เพื่อ QA ภายใน; ห้าม backlog publish |
| Manifest | PASS 23 items หลังแยก legacy unknown | **PASS ด้านสัญญาไฟล์** | ใช้เพื่อ reconciliation; ไม่ใช่สิทธิ์เผยแพร่ |

## 3. สิ่งที่แก้แล้วและประโยชน์ต่อรายได้

### ความซื่อสัตย์ของสินค้าและ CTA

- นำราคา, PromptPay, ขั้นตอนสั่งซื้อ, `data-buy`, คำสัญญา PDF และ LINE ซื้อสินค้าออกจาก `debt-letter-kit.html`; เหลือเฉพาะตัวอย่างฟรีและเครื่องมือภายใน
- ป้องกัน build ที่เคยเปลี่ยนลิงก์แต่ยังทิ้งข้อความ “สั่งซื้อ/โอนเงิน” ให้ดูเหมือนขายอยู่
- เปลี่ยน CTA รถที่เคยพาไปรีไฟแนนซ์บ้าน และ CTA กรุงศรีแบบกว้างที่จริงพาไปบัตร Lady ให้กลับเป็น internal guide ที่ตรงบริบท
- แยก Gumroad product IDs ให้คงที่ และห้าม logger รับสินค้าที่ block หรือชื่อสินค้าที่ไม่รู้จัก

ผลต่อธุรกิจ: ลดความเสี่ยงรับเงินแล้วส่งของไม่ได้ ลดคลิกผิดเจตนา และทำให้ conversion ที่เกิดขึ้นตีความได้จริง

### ความถูกต้องของเนื้อหาการเงิน

- แก้ขั้นต่ำบัตรเครดิตเป็น 8% สำหรับ 1 ม.ค.–31 ธ.ค. 2569 ตามประกาศ ธปท.
- แก้เนื้อหาเงินเดือน 30,000 ให้สอดคล้องเกณฑ์วงเงิน และตัดคำว่า “วงเงินรวม” ที่ต้นทางไม่รองรับ
- แก้ LTV ให้สื่อว่าเพดาน 100% ในกรณีเข้าเงื่อนไขไม่เท่ากับได้รับอนุมัติเต็มจำนวน
- เพิ่ม registry แหล่งทางการให้ `kn-29` ถึง `kn-44` และ monitor แบบแยก fingerprint เนื้อหาที่มองเห็นได้จาก token/nonce ที่เปลี่ยนทุกครั้ง

แหล่งหลัก: [ธปท. มาตรการ LTV](https://www.bot.or.th/th/news-and-media/news/news-20260514.html), [ธปท. ขั้นต่ำบัตรเครดิต 8% ปี 2569](https://www.bot.or.th/content/dam/bot/fipcs/documents/FPG/2568/ThaiPDF/25680245.pdf), [SEC Check First](https://market.sec.or.th/LicenseCheck/Search?language=th)

### ระบบวัดผลและรายงาน

- สร้าง schema helper เดียวรองรับทั้ง `affiliate_click` และหัว legacy `conversion`; dashboard, traffic monitor, weekly review และ optimizer ไม่อ่าน 6 clicks เป็นศูนย์อีก
- แยก `affiliate_click`, `buy_intent_click`, `line_lead_click` และ `internal_cta_click`; affiliate นับเฉพาะ sponsored/affiliate จริง
- เพิ่ม decision-trust gate: เมื่อ internal-IP ไม่ตรง รายงานห้ามตั้ง winner หรือแนะนำเพิ่มความถี่
- sales logger มี `sale_id`, status, product/price validation, dedup และไม่เก็บ buyer email ใน ledger ใหม่

ผลต่อธุรกิจ: เปลี่ยนจาก “นับคลิกอะไรก็ได้” เป็น “รู้ว่าคลิกนั้นมีเจตนาอะไรและนำไปสู่รายได้หรือไม่”

### Automation และความปลอดภัย

- ปิด scheduled Facebook/Instagram publisher เก่าและเอา executable git chains ออกจาก prompt ที่พบทั้งสอง root
- policy loaders เปลี่ยนเป็น fail-closed เมื่อไฟล์หาย, JSON พัง, channel หาย, state ไม่รู้จัก, phase หมด หรือ quota=0
- quota สำหรับ limited channel นับรายสัปดาห์จริง; attempt/failure/out-of-week ไม่กินโควตา
- publisher จริงต้องผ่าน authority/privacy/policy/quota/dedup/QA gate ก่อน browser mutation
- daily/weekly batch เก็บ exit code ของ critical steps ไม่ให้คำสั่งท้ายกลบ failure และล้าง watermark alert เฉพาะเมื่อ scan ผ่านจริง
- policy ทั้ง 7 ช่องแยก `automation_capable` ออกจากอำนาจจริงและตั้ง `publication_authorized=false`; สินค้าใช้ `DELIVERABLE_READY` แทนคำว่า READY ที่อาจถูกตีความเป็นสิทธิ์โปรโมต
- ปิด prompt ที่ยังเรียก live YouTube, browser comment, Page 2 publisher, knowledge publisher และ one-shot/backfill เก่า; งานที่ยังมีประโยชน์เหลือเฉพาะ local draft/reconciliation
- ขยาย automation guard ให้ตรวจ executable git, live uploader, browser publish/comment และ deploy command; รอบสุดท้าย PASS โดยไม่พบ mutator ที่ยัง executable

ผลต่อธุรกิจ: ลดโพสต์ซ้ำ ลดบัญชีเสี่ยง ลด deployment ผิดชุด และทำให้ failure ที่กระทบรายได้ไม่ถูกซ่อน

### เว็บและวิดีโอ

- local production build ผ่าน smoke 71/71 canonical pages
- static affiliate check พบ 141 placements, 0 problem และ 0 network request ไป tracking redirect
- `b4-p01` มี MP4/VTT/poster และผ่าน pilot QA ในเครื่อง แต่ถูก block จากการเผยแพร่จนกว่าจะมี privacy + schedule + publication approval
- finalizer ตรวจ alias ของ video/voice/output/report ก่อนเขียน ป้องกัน report ลบหรือเขียนทับไฟล์สื่อ

### หลักฐาน regression รอบสุดท้าย

| ชุดตรวจ | ผล |
|---|---|
| Python compile | PASS 47/47 |
| Regression scripts | PASS 24/24 |
| Production build/smoke | PASS 71/71 หน้า; 125 build outputs |
| Affiliate/disclosure | PASS 78 หน้า, 141 placements, 0 problem, 0 tracking-network request |
| Manifest contract | PASS 23 items |
| Automation policy guard | PASS |
| Source binding | 16/16 knowledge rows ผูกกับ monitored official URLs ครบ |
| Official fetch | 26/26 HTTP 200, errors=0 |
| Full preflight | **EXPECTED BLOCK:** 16 PASS, 7 WARN, 2 FAIL |

สอง FAIL ที่เหลือคือ privacy guard และ official-source review 21 รายการ ไม่มี unexpected build/test failure การที่ test ผ่านจึงหมายถึงระบบหยุดถูกจุด ไม่ได้หมายความว่าอนุญาตเผยแพร่แล้ว

## 4. ฐานข้อมูลที่มี — และข้อจำกัด

| ตัวชี้วัด | ค่าที่สังเกตได้ | ใช้ตัดสินได้หรือไม่ |
|---|---:|---|
| GA4 sessions 28 วัน | 119 | **ไม่ได้** จน internal filter ตรง |
| GA4 affiliate clicks | 6 | ใช้เป็นสัญญาณเท่านั้น; taxonomy/traffic เดิมปน |
| GA4 buy-intent clicks | 2 | ใช้เป็นสัญญาณเท่านั้น; ต้องผูก `content_id`/landing |
| Verified sales ใน ledger | 0 | ใช้ได้: ยังไม่มีรายได้ที่ยืนยันใน ledger |
| GSC query impressions | 276 | ใช้หาโอกาสคำค้นได้ |
| GSC page impressions | 317 | ใช้จัดลำดับหน้าได้ แต่ห้ามเทียบตรงกับ query total |
| GSC clicks | 0 | ใช้ได้ ณ export ล่าสุด แต่ไฟล์มีอายุถึง 10 ส.ค. |
| Post-ledger ที่มี `content_id` | 0/176 | **ใช้ D7/D14 attribution ไม่ได้** |

ข้อสรุป: ยังไม่มีหลักฐานพอจะบอกว่า channel หรือโพสต์ใด “ชนะ” ขณะนี้สิ่งที่รู้จริงคือมี impression แต่ยังไม่เปลี่ยนเป็นคลิก, funnel attribution ต่อ content ยังขาด, และยอดขายที่ยืนยันยังเป็นศูนย์

## 5. KPI contract ใหม่

ให้ถือ D0 เป็นเวลา `published_at` ที่ยืนยันจากแพลตฟอร์ม ไม่ใช่วันใน schedule

| ชั้น funnel | KPI ที่ใช้ | Guardrail |
|---|---|---|
| Reach | qualified sessions, landing entrances, GSC clicks | ตัด internal/test; แยก source |
| Value | `answer_seen`, tool completion, video start/complete | ต้องมี `content_id` และ landing |
| Intent | affiliate, product, LINE, internal CTA แยก event | ห้ามรวมเป็น conversion เดียว |
| Commerce | checkout start, verified order, approved affiliate revenue | ใช้ `sale_id`/status/dedup; ไม่เก็บ PII |
| Quality | refund, complaint, broken link, stale fact, delivery failure | หากเพิ่มขึ้นให้ STOP แม้คลิกโต |

กฎตัดสิน:

- **GO:** มี qualified downstream intent หรือ verified sale ที่ผูกกลับถึง content/landing ได้
- **HOLD:** มี impression/session แต่ไม่มี CTA intent ให้แก้ title/intro/FAQ/CTA เพียงหน้าเดียว
- **STOP:** มีแต่ internal/test, source pending, schema ไม่ตรง, deliverable ไม่พร้อม หรือ privacy fail
- **SCALE ONE:** ขยายครั้งละหนึ่ง content cluster/funnel หลังผ่าน D7 และ D14 เท่านั้น

## 6. ตารางปฏิบัติ 14 วัน

ตารางนี้เป็นงานที่ทำได้โดยไม่ฝ่าด่าน ไม่ใช่คำสั่งโพสต์อัตโนมัติ

| ช่วง | งานหลัก | Output ที่ต้องมี | เกตจบช่วง |
|---|---|---|---|
| วัน 1–2 | Owner ตัดสิน privacy: private repo ชั่วคราวหรือแผน rotate/redact/history; แก้ GA4 internal traffic | decision log ที่ไม่เปิดเผยค่า sensitive, filter verification | privacy PASS และ GA4 trust PASS/มี baseline date |
| วัน 1–4 | ทบทวน 21 official sources ทีละรายการเทียบ claim ของ `kn-29..44` | reviewer, reviewed_at, source hash, claim scope, next review | ไม่มี pending สำหรับชิ้นที่จะเผยแพร่ |
| วัน 3–5 | QA local→production parity; deploy แบบ atomic โดย owner หลัง privacy ผ่าน | build 71/71, live smoke, canonical/schema/CTA diff | live ไม่มี letter-kit purchase, stale 5–10%, CTA ผิด และเนื้อหาเงินเดือนเก่า |
| วัน 5–7 | ติด `content_id`/`cta_id`, แยก event และยืนยัน D0 จาก platform | event debug evidence และ ledger join ได้ | test/internal ไม่ปน qualified metrics |
| วัน 6–10 | เตรียม value posts วันละ 1 ชิ้นจากคลัง C; owner เลือกเผยแพร่เฉพาะชิ้นที่ทุก gate เขียว | useful post + official source + topic landing + disclosure | policy/quota/gap/dedup/source/privacy/QA PASS ก่อนทุกชิ้น |
| วัน 8–11 | ปรับ 1 หน้า GSC impression สูงต่อรอบ: title, intro, FAQ หรือ CTA เพียงตัวแปรเดียว | change log + hypothesis + baseline | ไม่เปลี่ยนหลายตัวพร้อมกัน |
| วัน 11–14 | อ่าน D7/D14 จาก verified D0; เลือกหนึ่ง cluster ทำ sequel หรือ HOLD | qualified reach → intent → sale table | มี attribution จริงก่อน scale |

ลำดับ content draft ใช้ `kn-30` ถึง `kn-44` ตาม Master Schedule แต่ทุกแถวยังเป็น `DRAFT READY / PUBLICATION BLOCKED` จน review และ privacy ผ่าน ไม่ควรชดเชยวันที่พลาดด้วยการโพสต์ย้อนหลังหลายชิ้น

### Review slots 17–30 สิงหาคม

| วันที่ | ชุดตรวจ | หลักฐานที่ต้องได้ | Public action |
|---|---|---|---|
| 17 ส.ค. | `kn-29` + `kn-30` | เกณฑ์บัตร, แอป/ผู้พัฒนา และ live landing parity | NO-OP |
| 18 ส.ค. | `kn-31` | วันที่ rollout ธนาคาร/e-money และข้อยกเว้น | NO-OP |
| 19 ส.ค. | `kn-32` | รายงาน Q2 และถ้อยคำที่ไม่ตีความเป็นผลรายบุคคล | NO-OP |
| 20 ส.ค. | `kn-33` | release period และถ้อยคำไม่เหมารวมทุกครัวเรือน | NO-OP |
| 21 ส.ค. | `kn-34` | กฎบัตร 8%/วันสิ้นสุด และ landing ไม่มี stopped offer | NO-OP |
| 22 ส.ค. | `kn-35` + `kn-36` | workflow ปรับหนี้, eligibility และไม่มี traffic ไป letter kit | NO-OP |
| 23 ส.ค. | `kn-37` | License Check, ชื่อนิติบุคคล และ CTA ไม่แซงช่องทางทางการ | NO-OP |
| 24 ส.ค. | `kn-38` | ขอบเขต LTV, effective/expiry date และ landing parity | NO-OP |
| 25 ส.ค. | `kn-39` | utility flow เทียบ Your Data rules และ consent fields | NO-OP |
| 26 ส.ค. | `kn-40` + `kn-41` | SEC registry, data minimization และช่องทางส่งเอกสาร | NO-OP |
| 27 ส.ค. | `kn-42` | Responsible Lending claim-by-claim และ disclosure | NO-OP |
| 28 ส.ค. | `kn-43` | helpful-content checklist เทียบ `/about` ที่ทำได้จริง | NO-OP |
| 29 ส.ค. | `kn-44` | สัญญา/ยอดปิด, ownership และปลายทาง CTA | NO-OP |
| 30 ส.ค. | Global checkpoint | monitor strict=0, validator=0, privacy clear, live smoke และ owner approval | ไม่ครบข้อใด = NO-OP |

## 7. วงจรอัปเดตต่อเนื่อง

### ทุกวัน 07:00

1. refresh source fingerprints แบบไม่ acknowledge อัตโนมัติ
2. ดึง GA4/GSC/sales aggregate
3. รัน privacy, source, policy, manifest, offer, build/smoke และ queue guards
4. สร้างร่าง/รายงานในเครื่องเท่านั้นเมื่อ authority ไม่อนุญาต
5. เก็บ terminal status `ok|warn|fail`; ห้ามให้ failure ถูกกลบ

### ทุกสัปดาห์

1. ตรวจ source coverage ของ content 7 วันข้างหน้า
2. reconcile manifest/ledger/platform evidence โดยไม่โพสต์ backlog เพื่อซ่อมหลักฐาน
3. อ่าน D7/D14 ด้วย qualified metrics เท่านั้น
4. ปิด/รวม task ซ้ำหลังมี scheduler registry export สด
5. เลือกเพียงหนึ่ง experiment ที่เชื่อมคุณค่า → intent → verified revenue

### ทุกเดือน

1. ตรวจ refund/complaint/stale fact/delivery failures
2. ทบทวนสินค้าว่าส่งมอบได้ครบ 100%
3. rotate/privacy audit และ dependency/source inventory
4. retire หน้า/offer/task ที่ไม่ผ่านมาตรฐาน แทนการปล่อยค้าง

## 8. งานที่ต้องเป็นเจ้าของเท่านั้น

1. ตัดสิน public-repo remediation และจัดการ secret/identifier/history ที่เคยเปิดเผย
2. แก้ GA4 Admin internal traffic และยืนยันจาก Realtime/DebugView โดยไม่เปิดเผย IP ในรายงาน
3. เป็นผู้กด deploy และ social publish หลังทุก gate ผ่าน
4. ทดสอบธุรกรรม/checkout/refund จริง และตัดสินว่าจะสร้างหรือ retire `letter-kit-199`
5. export scheduler registry เพื่อยืนยัน enabled task, trigger, owner และ prompt hash

## 9. หลักฐานตรวจที่ต้องรักษา

- Master schedule: `automation-log/MASTER-SCHEDULE_20260817-0831.md`
- Authority: `.system_control/role_capabilities.json`
- Policy SSOT: `.system_control/policy.json`
- Source registry/snapshot: `automation-log/knowledge-base/content-source-registry.json`, `official-news-snapshot.json`
- Content library: `automation-log/KNOWLEDGE-POSTS-C_20260816-0831.md`
- Manifest/schedule: `.system_control/content_manifest.json`, `reels/schedule.json`
- Revenue evidence: `automation-log/sales-log.jsonl` และ aggregate reports ที่ไม่มี PII

## 10. นิยามคำว่า “พร้อม”

โปรเจกต์พร้อมเผยแพร่เมื่อครบพร้อมกันทั้งหมด:

1. privacy guard ผ่านและ owner อนุมัติ scope ที่จะออกสาธารณะ
2. source ของชิ้นนั้น reviewed/fresh/unchanged และ claim อยู่ใน scope
3. channel state, quota, weekly cap, gap, dedup และ disclosure ผ่าน
4. landing/CTA/deliverable/build/live smoke ผ่าน
5. actor มี authority และมี publication record ที่เจาะจง content/channel/date
6. measurement แยก internal/test และผูก `content_id` ได้

ถ้าข้อใดข้อหนึ่งไม่ผ่าน ให้สร้างคุณค่าในเครื่องต่อได้ แต่ต้อง **NO-OP ต่อการเผยแพร่**
