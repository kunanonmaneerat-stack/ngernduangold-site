# Master schedule — 17–31 สิงหาคม 2026

> สถานะ ณ 16 สิงหาคม 2026 เวลา 19:18 · เขตเวลา Asia/Bangkok  
> เอกสารนี้เป็นทะเบียนกลางสำหรับตัดสินงาน ไม่ใช่หลักฐานว่า scheduled task ภายนอกเปิดอยู่  
> หาก registry สด, policy SSOT และไฟล์นี้ขัดกัน ให้หยุดและใช้กฎที่เข้มกว่า จนกว่าจะตรวจต้นทางได้
> ตัวเลขสถานะเป็น snapshot ไม่ใช่ authority: ใช้ `.system_control/content_calendar.json`, `.system_control/policy.json`, official snapshot และผล guard ล่าสุดเป็นคำตัดสินสดเสมอ

## เป้าหมายรอบนี้

1. ให้ความรู้ที่ตรวจสอบได้ทุกวัน และพาผู้อ่านไปยังหน้าที่ตรงกับคำถามจริง
2. วัดรายได้ด้วยสัญญาณแยกประเภท ไม่ใช้ traffic ภายในหรือการทดสอบของเราเป็น demand
3. ผลิตวิดีโอแบบ evidence-led ทีละชิ้น ไม่สร้างสต็อกก่อนรู้ผล
4. ห้ามให้ระบบเก่าหรือ task ซ้ำโพสต์เกินโควตา

## ด่านหยุดที่มีผลทันที

| ด่าน | สถานะ | ผลต่อการทำงาน |
|---|---|---|
| Privacy guard ของ public repo | **PASS — 0 finding / 32 tracked files ณ current worktree** | ประวัติ Git ที่เคยเปิดเผยยังเป็นงานแยก; current PASS ไม่อนุญาต push/deploy เอง |
| Official-source review | **STOP — 26 sources รอ human review จาก 31 sources** | fetch ล่าสุดไม่มี changed/error แต่ห้ามเรียกโพสต์ว่า publish-ready จนตรวจคำกล่าวอ้างและ acknowledge ทีละแหล่ง |
| Publication authority | **OWNER-ONLY / CURRENTLY BLOCKED** | Codex, Cowork, Claude Code และ GitHub Actions ไม่มีสิทธิ์โพสต์, commit, push หรือ deploy; owner ก็ต้องผ่าน privacy/source/policy/quota/QA gate ก่อน |
| Automation ownership | **PASS — registry สด 2 แหล่ง / shared ownership 12 รายการ / 0 conflict** | Cowork 92 งาน (เปิด 22) และ CCD 11 งาน (เปิด 7); งานเก่าที่ชี้ `RETIRED — NO-OP` ถูกพักผ่านตัวจัดการงานแล้ว และ guard ตรวจ action/working directory เพิ่มจากชื่อ task |
| GA4 / GSC observation | **STOP — snapshot เดิมเป็น schema v1 / `INVALID_METADATA`** | ห้ามใช้ sessions, clicks, impressions หรือ channel ranking ตัดสินจนดึง bundle v2 ใหม่ครบ; GA4 ต้องผ่าน internal-traffic coverage ตลอดหน้าต่าง 28 วัน และ GSC ต้องจบที่ D-3 |
| Revenue ledger | **STOP — `UNRECONCILED`** | dashboard แสดง `—` ไม่ใช่ 0; รอ frozen source export จริงแล้ว reconcile เป็น schema v4 แบบ append-only ก่อนใช้ paid commission เป็น North Star |
| Live release | **STOP — production/local parity 0/72** | local build ผ่าน 70/70 และ 140 placements แต่ production ยังมี 185 placements, taxonomy/attribution รุ่นเก่า และไม่มี release manifest ที่รองรับ; ห้ามส่ง traffic เพิ่ม |
| `letter-kit-199` | **STOP — ไม่มี PDF 10 หน้า** | ปิดจาก CTA/คิวโปรโมตทั้งหมด ห้ามรับเงินหรือส่ง traffic เข้าหน้าขาย |
| Pantip | **LIMITED MANUAL / OBSERVING 48H** | reply-only pilot ถูกโพสต์ 1 ครั้งและใช้โควตา 1/1 แล้ว; ห้ามโพสต์เพิ่ม/ใส่ลิงก์/แบรนด์/affiliate และรอ review 18 ส.ค. 15:54:44 |
| `b4-p01` | **QA PASS / PUBLISH BLOCKED** | มี media receipt แล้วและถูกสำรองเป็นหนึ่งในผู้สมัคร TikTok แต่ห้ามอัปโหลดจน live landing, bio route, dedup, calendar และ one-time publication receipt ผ่านครบ |
| Instagram / Pinterest | **PAUSED** | วันที่ 25 ส.ค. เป็นวัน review เท่านั้น ไม่เปิดเอง |
| TikTok | **TESTING_BLOCKED — 14 RESERVED / 0 PUBLISHABLE** | 17–30 ส.ค. เป็นแผนเตรียมทดสอบ ไม่ใช่คิวโพสต์; B3 เดิม 6/6 ถูกบล็อกเพราะ semantic parity แม้ไฟล์เทคนิคผ่าน จึงต้อง re-render; auto=false และ publication_authorized=false จนผ่านทุก blocker รายชิ้น |

## ตารางควบคุมงานเป้าหมาย

ตารางนี้คือรูปแบบที่ควรเหลือหลังตรวจ registry สด ห้ามสร้าง task ซ้ำจากชื่อโฟลเดอร์เพียงอย่างเดียว

| เวลา | ความถี่ | Owner / ชั้นงาน | งานที่อนุญาต | เงื่อนไข fail-closed |
|---|---|---|---|---|
| 07:00 | ทุกวัน | Windows `ngernduangold_daily` | ดึง metrics, QA, สร้าง draft/queue ภายใน | ห้าม post, commit, push, deploy; task Ready และผลรอบล่าสุดอาจ nonzero ได้เมื่อ blocker ทำงานถูกต้อง—ห้าม hard-code last result ในเอกสาร |
| 08:30 | อาทิตย์ | Windows `ngernduangold_weekly` | refresh official sources/GA4/GSC, สรุปสัปดาห์ และรัน improvement loop แบบ local-only | task Ready; รอบแรก 23 ส.ค.; source/GA4 blocker ต้องคืน nonzero โดยไม่โพสต์หรือส่งแจ้งเตือนภายนอก |
| 08:40 | ทุกวัน | delivery heartbeat เพียงตัวเดียว | ตรวจ delivery ของเมื่อวานและแจ้งเฉพาะ miss ที่มีหลักฐาน | ถ้า registry ยืนยัน owner ไม่ได้ ให้รายงานอย่างเดียว |
| 10:05 และ 16:05 ชั่วคราว | ทุกวันถึง 18 ส.ค. 16:05; จากนั้นกลับ 10:05 วันละครั้ง | Codex control tower เดิม (อัปเดต ไม่สร้างซ้ำ) | สรุป qualified traffic, intent, sales, content runway, blockers; ถึง 18 ส.ค. 16:00 ตรวจ Pantip comment แบบ read-only เพิ่ม | ACTIVE; แจ้ง Pantip เฉพาะถูกลบ/ซ่อน/เตือนหรือมีคำตอบสำคัญ; ห้ามตอบ/ไลก์/แก้/ลบเอง และให้ automation คืน cadence เดิมหลัง review |
| 09:22 | อาทิตย์ | link health | ตรวจ merchant/affiliate redirect แบบไม่ก่อ conversion | ห้ามเปิดปลายทางที่เสี่ยงสร้าง event จริงเกินจำเป็น |
| 09:40 | พุธ | funnel review | ตรวจ landing → CTA → LINE/payment แบบ read-only | ห้าม test purchase; ห้ามนับ own click เป็น demand |
| 10:10 | อาทิตย์แรกของเดือน | isolated clicktest | ตรวจ DOM/redirect และ event ที่ tag test/internal เท่านั้น | หาก exclude test traffic ไม่ได้ ให้หยุดที่ DOM/redirect |
| 12:15 | จ/พ/ศ | first signal | อ่าน metrics ที่ daily pull เสร็จแล้ว | ใช้ human/qualified filter; ไม่แก้ external state |
| 12:40 | ทุกวัน | เตรียม Threads knowledge | สร้าง/ตรวจร่างจากคลัง C; **ปัจจุบัน NO-OP ต่อการเผยแพร่** | owner-only หลัง privacy + source + policy + quota + dedup ผ่าน; สูงสุด 2 โพสต์/วันและห่างอย่างน้อย 3 ชม. |
| 12:50 | ทุกวัน | เตรียม Facebook main | สร้าง/ตรวจร่าง 1 ชิ้น; **ปัจจุบัน NO-OP ต่อการเผยแพร่** | owner-only หลังทุก gate ผ่าน; วันใด landing เป็นเว็บทางการไม่บังคับพากลับเว็บเรา |
| 15:30 | ทุกวัน | comment loop | อ่าน comment และร่างคำตอบ | owner approve ก่อนตอบจริง |
| 16:00 | เฉพาะ slot ที่ owner อนุมัติหลัง gate ผ่าน | Facebook second slot | เตรียม demo เครื่องมือ/ebook หลังมี value post อย่างน้อย 4 ชิ้น | ปัจจุบัน NO-OP; ต้องมี asset QA, disclosure, gap >=3 ชม.; ไม่ใช้ scarcity ปลอม |
| 17:30 | ทุกวัน | Facebook safety net เพียงตัวเดียว | draft-only เมื่อวันนั้น Facebook ยัง 0 post | ห้ามซ้ำ `fb-daily-draft` กับ `fb-evening-safetynet` |
| 19:00 | event-driven | video publisher | ทำงานเฉพาะคลิปที่อยู่ใน future manifest + schedule และ publication gate ผ่าน | ตอนนี้ future schedule ว่าง จึงต้อง **NO-OP** |
| 19:25 | ทุกวัน | local post guard | ตรวจ ledger, cap, gap, dedup | ไม่เปิด browser mutation |
| 21:30 | ทุกวัน | end-of-day verifier เพียงตัวเดียว | รวม delivery/channel/video verification | วันไม่มี video schedule ให้ skip video ไม่ใช่ fail |
| 22:00 | ทุกวัน | continuity backup | สำรอง state ขนาดเล็ก; จันทร์เพิ่ม docs/scripts | ต้องมี Drive auth; ห้ามสำรอง secrets/PII ไปพื้นที่ไม่ถูกต้อง |

## ปฏิทินเนื้อหาและรายได้

คำว่า `DRAFT READY / PUBLICATION BLOCKED` หมายถึงโครงสร้างร่างผ่านตัวตรวจระดับไฟล์เท่านั้น ไม่ใช่การรับรองข้อเท็จจริงครบถ้วนและไม่ใช่คำอนุญาตให้โพสต์ ขณะนี้ทุกแถวถูกหยุดด้วย source-review และ publication-authority gate; privacy current-worktree ผ่านแล้วแต่ไม่ลบ hard stop อื่น

| วันที่ | 12:40 Threads / 12:50 Facebook | Landing / CTA | สถานะและจุดประสงค์ |
|---|---|---|---|
| 17 ส.ค. | `kn-30` ใช้แอป ธปท. หาเรื่องการเงินจากต้นทาง | หน้าทางการ ธปท.; ถามว่าเก็บแหล่งต้นทางไว้หรือยัง | **DRAFT READY / PUBLICATION BLOCKED · trust-first** |
| 18 ส.ค. | `kn-31` บัญชีเยาวชนกับขีดจำกัดการโอน | ข่าว/แนวทาง ธปท.; ชวนคุยกฎการโอนในบ้าน | **DRAFT READY / PUBLICATION BLOCKED · safety/value** |
| 19 ส.ค. | `kn-32` อ่านรายงานภาวะสินเชื่อให้เป็น | `/loan-approval-compare` · เตรียมความพร้อมก่อนยื่น | **DRAFT READY / PUBLICATION BLOCKED · revenue-intent** |
| 20 ส.ค. | `kn-33` ข่าวเศรษฐกิจกับงบส่วนตัว | `/salary-budgeting-2026` · เครื่องมือจัดงบ | **DRAFT READY / PUBLICATION BLOCKED · tool use** |
| 21 ส.ค. | `kn-34` จ่ายขั้นต่ำแล้วเงินต้นลดหรือไม่ | `/pay-off-credit-card-debt-2026` · ทดลองแผนชำระ | **DRAFT READY / PUBLICATION BLOCKED · high intent**; slot 16:00 ทำ ebook-59 demo ได้เฉพาะเมื่อ preview asset และทุก gate ผ่าน |
| 22 ส.ค. | `kn-35` ปรับโครงสร้างหนี้ต่างจากรีไฟแนนซ์ | `/debt-restructuring-2026` · คู่มือก่อนคุยเจ้าหนี้ | **DRAFT READY / PUBLICATION BLOCKED · debt-help first** |
| 23 ส.ค. | `kn-36` เช็กโครงการปิดหนี้ไวจากต้นทาง | `/close-debt-fast-2026` · ตรวจประเภทหนี้/ข้อยกเว้น | **DRAFT READY / PUBLICATION BLOCKED**; ห้ามโยง `letter-kit-199` |
| 24 ส.ค. | `kn-37` ตรวจแอปเงินกู้และใบอนุญาต | `/loan-online-legal-2026` · เช็กลิสต์ผู้ให้บริการ | **DRAFT READY / PUBLICATION BLOCKED · safety + commercial intent** |
| 25 ส.ค. | `kn-38` LTV ผ่อนคลายไม่เท่ากับกู้ได้เต็ม | `/refinance-home-2026` · วางแผนก่อน/หลังโอน | **DRAFT READY / PUBLICATION BLOCKED**; review IG/Pinterest/Pantip แยก ไม่เปิดอัตโนมัติ |
| 26 ส.ค. | `kn-39` Your Data และสิทธิ์ควบคุมข้อมูล | หน้าทางการ Your Data ธปท. | **DRAFT READY / PUBLICATION BLOCKED · trust-first** |
| 27 ส.ค. | `kn-40` แยกผู้เชี่ยวชาญออกจากมิจฉาชีพ | `/loan-online-legal-2026` · ตรวจชื่อ/ช่องทางก่อนโอน | **DRAFT READY / PUBLICATION BLOCKED · safety** |
| 28 ส.ค. | `kn-41` ส่งสลิป/บัตรประชาชนเท่าที่จำเป็น | `/credit-card-documents-2026` · เช็กลิสต์เอกสาร | **DRAFT READY / PUBLICATION BLOCKED · search/revenue assist**; ตรวจ refill คลังสำหรับ 1 ก.ย. เป็นต้นไป |
| 29 ส.ค. | `kn-42` อ่านโฆษณาสินเชื่อแบบไม่หลงคำเร่ง | `/loan-approval-compare` · ตารางคำถามก่อนตัดสินใจ | **DRAFT READY / PUBLICATION BLOCKED · responsible lending** |
| 30 ส.ค. | `kn-43` เช็กบทความการเงินว่าเขียนเพื่อช่วยหรือให้คลิก | `/about` · วิธีตรวจแหล่งข้อมูลของแบรนด์ | **DRAFT READY / PUBLICATION BLOCKED · trust/AI discoverability** |
| 31 ส.ค. | `kn-44` รถยังผ่อนไม่หมดกับทางเลือกใช้รถหาเงินก้อน | `/car-still-installment-loan-2026` · ตรวจสัญญา/ยอดคงเหลือ | **DRAFT READY / PUBLICATION BLOCKED · vehicle-finance intent** |

### Facebook Page 2 — ช่องสำรอง 15:50 ถึง 28 ส.ค.; รอบ ก.ย. คง 13:10

ข้อความชุดนี้มีช่องเวลาในปฏิทินแล้วแต่ยังเป็น `PLANNED_BLOCKED`; การมีเวลาไม่เท่ากับสิทธิ์เผยแพร่

| วันที่ | เวลา | Content | สถานะ |
|---|---:|---|---|
| 18 ส.ค. | 15:50 | `p2-09` เช็กก่อนรีไฟแนนซ์บ้าน | BLOCKED — เติม AI disclosure, source binding, compliance และ permanent claim |
| 21 ส.ค. | 15:50 | `p2-10` สินเชื่อสวัสดิการเทียบทั่วไป | BLOCKED — เงื่อนไขเดียวกัน |
| 25 ส.ค. | 15:50 | `p2-11` ความเสี่ยงผู้ค้ำ | BLOCKED — เงื่อนไขเดียวกัน |
| 28 ส.ค. | 15:50 | `p2-12` เตรียมขอสินเชื่อครั้งแรก | BLOCKED — เงื่อนไขเดียวกัน |
| 1 ก.ย. | 13:10 | `p2-13` เครดิตบูโรกับการขอสินเชื่อ | BLOCKED — เงื่อนไขเดียวกัน |
| 4 ก.ย. | 13:10 | `p2-14` อันตรายสินเชื่อนอกระบบ | BLOCKED — เงื่อนไขเดียวกัน |
| 8 ก.ย. | 13:10 | `p2-15` ปิดหนี้ก่อนกำหนด | BLOCKED — เงื่อนไขเดียวกัน |
| 11 ก.ย. | 13:10 | `p2-16` ผ่อนสั้นเทียบผ่อนยาว | BLOCKED — เงื่อนไขเดียวกัน |

### สื่อ — reserved slot เท่านั้น

| Asset | ช่องเวลาที่สำรอง | สิ่งที่ต้องทำก่อน |
|---|---|---|
| `b4-p01` | YouTube 27 ส.ค. 19:00; Threads 29 ส.ค. 19:00; Facebook 31 ส.ค. 19:00; Instagram 2 ก.ย. 19:00 | publication authority, exact future manifest/schedule และ prepublish receipt; Instagram ต้องผ่าน review แยก |
| `qt-12` | Facebook 26 ส.ค. 16:00; Instagram 27 ส.ค. 19:00; Pinterest 30 ส.ค. 10:00 | ต้องมีภาพ render จริง + visual QA + hash receipt; IG/Pinterest ยัง paused |
| `qt-13` | Facebook 29 ส.ค. 16:00; Instagram 31 ส.ค. 19:00; Pinterest 2 ก.ย. 10:00 | เงื่อนไขเดียวกัน |
| `qt-14` | Facebook 2 ก.ย. 16:00; Instagram 3 ก.ย. 19:00; Pinterest 6 ก.ย. 10:00 | ภาพ 4:5 และ 2:3 ผลิตแบบ local-only แล้ว; visual/watermark QA และ exact-hash receipt ผ่าน แต่ยังคงบล็อก publication authority และ channel review ตามช่องทาง |
| Flow/Veo B-roll รอบ 16 ส.ค. | **ไม่มีช่องเวลา** | คำขอล้มเหลว ไม่มีไฟล์ให้ใช้และห้ามนับเป็น asset |
| `letter-kit-199` | **STOP / ไม่มีช่องเวลา** | สร้างและ QA PDF 10 หน้าให้ตรงคำสัญญา หรือปิด offer/CTA |

TikTok มี 14 reserved placements ที่ `PLANNED_BLOCKED` ทั้งหมดและ 0 publishable; Pantip ใช้โควตา manual pilot 1/1 แล้วและอยู่ระหว่างสังเกต 48 ชั่วโมง ทั้งสองช่องจึงไม่มีงานเผยแพร่เพิ่มโดยตั้งใจ ส่วน Instagram/Pinterest มีเพียง reserved slots ที่ไม่ทำงานจนกว่าจะมีการทบทวนและอนุมัติใหม่

## จุดวัดผลและกฎตัดสิน

### 23 สิงหาคม — checkpoint 7 วัน

อ่านเฉพาะข้อมูลหลังตัด internal/test:

- qualified social sessions แยก Facebook / Threads / YouTube
- qualified organic sessions และ landing entrances
- `affiliate_click` เฉพาะลิงก์ sponsored/affiliate
- `buy_intent_click`, `line_lead_click`, `internal_cta_click` แยกกัน (`buy_intent_click` เป็นชื่อ canonical ที่ระบบและข้อมูลย้อนหลังใช้อยู่)
- landing CTA CTR ต่อหน้าและต่อ `content_id`
- ยอดขายจริงจาก ledger ที่ไม่มี PII ในรายงาน

**GO:** มี qualified click/lead ใหม่ที่ผูกกลับถึง content หรือ landing ได้ → ทำ sequel 1 ชิ้นในคลัสเตอร์นั้น  
**HOLD:** มี impression/session แต่ไม่มี CTA → ปรับ title, intro, FAQ หรือ CTA ของหน้าเดียว ไม่เปลี่ยนหลายตัวพร้อมกัน  
**STOP:** มีแต่ internal/test หรือ schema ไม่ตรง → ซ่อม measurement ก่อนเพิ่ม traffic

### 30 สิงหาคม — checkpoint 14 วัน

**SCALE ONE:** ขยายเพียงคลัสเตอร์เดียวที่มีทั้ง qualified traffic และ downstream intent  
**DO NOT SCALE:** 0 sales เมื่อ sales-page views ยังต่ำกว่า 50 ไม่ใช่หลักฐานว่า offer แพ้  
**PRODUCT:** โปรโมต ebook-59 ต่อได้เมื่อ delivery/link ยังผ่าน; `letter-kit-199` ไม่นับในทดลองจน deliverable มีจริง  
**VIDEO:** ผล `b4-p01` ใช้ตัดสิน batch ถัดไปได้หลัง publication gate และครบ measurement windowเท่านั้น

## Cleanup queue — ทำหลังมี registry export สดเท่านั้น

1. ปิด/tombstone งาน one-shot ที่จบแล้ว: batch3/batch4 gates รุ่นเก่า, bridge clips, refill เดิม, FB backfill 10–14 ส.ค., buy-intent gate 8 ส.ค.
2. รวม verifier สี่ชั้นให้เหลือ heartbeat เช้าและ verifier ปลายวันอย่างละหนึ่ง
3. รวม Facebook safety net ให้เหลือตัวเดียว
4. ลด Threads idle-window จากทุกชั่วโมงเป็น event-driven หนึ่งรอบ เมื่อ future video schedule มีรายการ
5. ปิด task ที่ขัด channel state: TikTok testing_blocked และห้าม browser/upload; IG/Pinterest paused
6. แก้ weekly-review ที่ค้าง `started` ให้เขียน terminal status เสมอ
7. ห้ามลบจากชื่อ folder; ต้องยืนยัน task id ใน live registry ก่อนทุกครั้ง

## Source of truth ที่ใช้

- `.system_control/policy.json` — channel state, limits, gates, product deliverability, task roots
- `automation-log/POSTING-POLICY_antispam_20260702.md` — cap/gap/disclosure และ Threads slots
- `.system_control/content_calendar.json` — ปฏิทิน future-only แบบ machine-readable; แถวที่ block เป็นเพียง slot สำรอง ไม่ใช่คิวเผยแพร่
- `automation-log/KNOWLEDGE-POSTS-C_20260816-0831.md` — คลังข้อความที่ผ่านโครงสร้าง 16/16 แต่ยังไม่ publish-ready ขณะ source review ค้าง 26 รายการ
- `automation-log/knowledge-base/content-source-registry.json` + `official-news-snapshot.json` — binding และสถานะทบทวนแหล่งทางการ; pending ใด ๆ ต้อง block โพสต์ที่เกี่ยวข้อง
- `.system_control/content_manifest.json` + `reels/schedule.json` — สิทธิ์ของ asset ต่อคิววิดีโอ
- `automation-log/post-ledger.jsonl` — dedup/delivery evidence
- reports ของ GA4/GSC — ใช้เมื่อ schema และ internal-traffic guard ผ่านเท่านั้น
