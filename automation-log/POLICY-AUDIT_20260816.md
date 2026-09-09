# Policy audit และแผนปฏิบัติการรายได้ — 16 ส.ค. 2026

> **SUPERSEDED FOR CURRENT OPERATIONS:** เอกสารนี้เก็บเป็นหลักฐานการตรวจช่วงต้นวันเท่านั้น ตัวเลขและสิทธิ์บางส่วนด้านล่างเปลี่ยนแล้ว ห้ามใช้เป็นคำอนุญาตโพสต์/commit/push/deploy ให้ยึด `.system_control/role_capabilities.json`, `automation-log/MASTER-SCHEDULE_20260817-0831.md` และ `reports/PROJECT-CONTROL-TOWER_20260816.md` เป็นสถานะปัจจุบันร่วมกัน กฎล่าสุดคือ owner-only และทุกการเผยแพร่ยังถูก block ด้วย privacy/source gates

> ขอบเขต: ตรวจเอกสารนโยบาย, policy SSOT, scheduled-task prompts ที่พบ, ledger, GA4/GSC exports,
> product deliverables และเว็บที่ build แล้วในเครื่อง ไม่ถือว่า “มีไฟล์ task” แปลว่า task นั้นเปิดใช้งานจริง
> เพราะ registry ของ scheduler ไม่ได้อยู่ในรีโปนี้

## 1. ลำดับอำนาจที่ใช้ตัดสินเมื่อเอกสารขัดกัน

1. คำสั่งเจ้าของล่าสุดในแชต: เพิ่มรายได้ด้วยงานที่มีคุณค่า ให้ความรู้ น่าสนใจ และตรวจสอบได้
2. Owner mandate / standing rule ที่เป็นคำสั่งตรงและยังไม่ถูกยกเลิก
3. `.system_control/policy.json` สำหรับสถานะช่องทาง, quota และวันที่ตัดสินใจที่เปลี่ยนได้
4. สถานะจริงจาก scheduler registry + prompt ที่ใช้งานอยู่ (รอบนี้ยืนยัน registry ไม่ได้)
5. Anti-spam, compliance, facts, handoff และ run logs เป็นกฎเฉพาะทาง/หลักฐานย้อนหลัง

หลักฐานว่า `policy.json` เป็น SSOT ของ state: `.system_control/policy.json:3-11` และ
`OPERATING-NOTES.md:400-404` อย่างไรก็ดีไฟล์นี้มีการแก้ใน working tree ที่ยังไม่ commit จึงเป็น
SSOT เฉพาะเครื่องนี้ ณ ตอนตรวจ ไม่ใช่สถานะที่ยืนยันแล้วบน remote

## 2. คำสั่งเจ้าของที่ยังมีผล

- เป้าหมาย: ใช้ทรัพยากรที่มีให้เกิดประโยชน์สูงสุด มุ่งรายได้โดยถูกต้องและ compliant
  (`automation-log/OWNER-MANDATE_20260702.md:3-5`)
- Zero-budget; ห้ามซื้อบริการใหม่, ห้ามใส่ secrets ในไฟล์ tracked, ธุรกรรมการเงินให้เจ้าของทำเอง
  (`automation-log/OWNER-MANDATE_20260702.md:14-18`)
- ทุกชิ้นเป็นข้อมูลเพื่อการศึกษา, ไม่รับประกันผล, ชูช่องทางช่วยเหลือฟรี, fact-check ข้อเท็จจริงที่เปลี่ยนได้
  (`automation-log/OWNER-MANDATE_20260702.md:18-19`)
- งานปฏิบัติที่ย้อนกลับได้ เช่น ผลิตคอนเทนต์และจัดคิว ทำต่อได้เลย; สิ่งที่ irreversible ต่อสาธารณะยังต้องผ่าน gate
  (`automation-log/OWNER-MANDATE_20260702.md:22`)
- คำสั่งเดิมที่เคยให้ Cowork โพสต์แทนถูก supersede แล้ว: ปัจจุบัน owner เท่านั้นที่มี `social_publish=true` และยังต้องผ่าน privacy/source/publication gates
  (`.system_control/role_capabilities.json`)
- ห้ามเก็บ PII, token หรือรายได้จริงในแชต/ล็อก/รีโปสาธารณะ
  (`PROJECT-HANDOFF.md:79`, `OPERATING-NOTES.md:46,97`)

## 3. สถานะช่องทางที่ใช้ปฏิบัติ ณ ตอนตรวจ

| ช่องทาง | สถานะที่ยึด | สิ่งที่ทำต่อได้ | สิ่งที่ห้าม/ต้องรอ |
|---|---|---|---|
| YouTube | active, UI/upload route | ผลิต Short ใหม่เมื่อไฟล์ 1080x1920 + เสียง + QA ผ่าน | video runway เป็นศูนย์; ห้ามนับ script ว่าเป็นคลิปพร้อม |
| Facebook | manual ผ่าน Business Suite/browser | เตรียมร่างความรู้วันละ 1 ชิ้น; owner โพสต์หลังทุก gate ผ่าน | ห้ามขอ Meta token ใหม่ (`policy.json:27-39`) |
| Threads | active | เตรียมร่าง repurpose; owner-only หลังทุก gate ผ่าน; policy รองรับสูงสุด 2/วันและต้องห่าง >=3 ชั่วโมง | ไม่ควรผลิต bespoke มาก เพราะ traffic ต่อชิ้นต่ำ |
| Instagram | paused | ทบทวนใหม่หลัง 25 ส.ค. | ไม่ auto-resume (`policy.json:66-73`) |
| Pinterest | paused | ทบทวนใหม่หลัง 25 ส.ค. | ไม่ auto-resume (`policy.json:74-80`) |
| TikTok | retired | 0 โพสต์; เก็บเป็นประวัติเท่านั้น | ห้ามสร้างคิวใหม่ (`policy.json:55-62`) |
| Pantip | final warning; phase หมด 14 ส.ค. | 0 โพสต์/0 ร่างในตอนนี้ | ต้องมีคำตัดสิน phase ใหม่และอนุมัติรายชิ้น; ห้ามลิงก์/แบรนด์/ราคา (`policy.json:93-107`) |
| FB Groups | read/draft only | ฟังคำถามและเตรียมคำตอบให้เจ้าของ | เจ้าของเป็นผู้โพสต์ ไม่เกิน 1 กลุ่ม/วัน |

ข้อสรุปแบบ fail-closed: Pantip มีสัญญาณ traffic ดีที่สุดในอดีต แต่ความเสี่ยงบัญชีถาวรสูงกว่า upside
จึงห้ามตีความ `gate = OPEN` ที่หมดวันที่แล้วว่าเป็นสิทธิ์โพสต์

## 4. ความขัดแย้งที่พบและคำตัดสินชั่วคราว

### 4.1 เพดาน 1 หรือ 2 โพสต์/วัน

- standing rule เดิมเขียน 1/วัน (`STANDING-RULE_autopost.md:7`)
- policy ปัจจุบันบันทึกมติ 31 ก.ค. เป็น 2/วันและเว้น >=3 ชั่วโมง (`policy.json:116-119`)
- Threads มีคำอนุมัติ 2/วันชัดเจน; ช่องอื่นยังมีหลักฐานตีความต่างกัน

คำตัดสินชั่วคราว: Threads ใช้เพดาน 2/วันเมื่อจำเป็น; ช่องอื่นใช้ 1 main post/วันจนเจ้าของยืนยัน
เพื่อรักษาคุณภาพและไม่ใช้เพดานเป็นเป้าปริมาณ

### 4.2 บทบาท commit/push

`STANDING-RULE_autopost.md:9` และ `OPERATING-NOTES.md:21,97` ห้าม Cowork/Claude push แต่ prompt เก่าหลายตัว
ยังสั่ง commit/push จึงถือ prompt เหล่านั้น stale จนแก้หรือปิด ไม่ให้คำสั่งใน prompt ชนะ role policy

### 4.3 เอกสารประวัติกับ state ปัจจุบัน

`PROJECT-HANDOFF.md:37-43` และ `CURRENT-STATE_20260718.md:6-11` ยังอธิบาย routing/วันที่ยุคก่อน
จึงใช้เพื่อเข้าใจประวัติเท่านั้น ไม่ใช้เปิด TikTok/IG/Pantip หรือ Meta automation กลับมา

### 4.4 ข่าว/ข้อเท็จจริง

คลัง facts เดิมตรวจล่าสุดเก่ากว่าคอนเทนต์รอบนี้และ newswatch เคยถูกพัก จึงเพิ่ม change detector สำหรับ
แหล่งทางการ และแยก source/date/refresh rule ต่อโพสต์ ห้ามให้ fingerprint ที่เปลี่ยนไปอัปเดตคำกล่าวอ้างอัตโนมัติ;
ต้องอ่านต้นทางก่อนเผยแพร่เสมอ

## 5. สินค้าและเส้นทางรายได้

| รายได้ | สถานะ | การตัดสินใจ |
|---|---|---|
| affiliate links | เปิดใช้ได้เมื่อ placement/UTM/disclosure ผ่าน | ใช้บทความตรง intent แทนส่งทุกคนไป `/links` |
| ebook 59 บาท | มีไฟล์ส่งมอบในเครื่อง (`policy.json:622-629`) | โปรโมตแบบสาธิตคุณค่าจริงได้ |
| debt toolkit 199 บาท | hosted product คนละตัวกับ letter kit (`policy.json:631-637`) | คงแยกชื่อ/คำสัญญาให้ชัด |
| letter kit 199 บาท | ไม่มี PDF; deliverable เป็น null (`policy.json:611-620`) | ปิดรับเงินและ CTA ซื้อจนสร้าง+QA ไฟล์จริง |
| workshop/บริการ | ยังไม่มีหลักฐาน conversion | ทดลองด้วย lead intent ที่แยก event ชัด ไม่รวมกับ affiliate click |

## 6. สิ่งที่หลักฐานรายได้บอกจริง

- GA4 export ล่าสุดมี 119 sessions แต่ direct 82 (69%) ถูกวินิจฉัยว่า synthetic/internal เป็นส่วนใหญ่
  จึงห้ามใช้ total sessions เป็นตัวแทนคนอ่านจริง
- affiliate clicks ที่ยืนยันได้ 6: Pantip 4 และ ChatGPT 2; schema `affiliate_click` เคยถูก consumer หลายตัวอ่านผิดเป็น
  `conversion` จนรายงานเป็นศูนย์ ทั้งที่ funnel total ยังเป็น 6
- GSC มี impressions แต่ 0 clicks; โอกาสที่ควรแก้ก่อนเพิ่มปริมาณคือหน้าเงินเดือน 30,000, รถยังผ่อนไม่หมด
  และรีไฟแนนซ์บ้าน
- sales ledger ยังไม่มีเงินขายที่บันทึก; ห้ามเรียก buy-intent จาก own test ว่า demand

ข้อสรุป: รายได้ยังไม่ติดเพราะ qualified reach, trust และเส้นทาง CTA มากกว่าปัญหา “โพสต์ไม่พอ” อย่างเดียว
กลยุทธ์จึงต้องเป็น useful post -> topic page/tool -> affiliate/ebook ที่ส่งมอบได้ ไม่ใช่ post -> link hub ทุกครั้ง

## 7. สิ่งที่แก้และตรวจแล้วในรอบนี้

- GA4 schema helper เดียว รองรับหัวใหม่และ legacy; dashboard/monitor/review/optimizer อ่าน 6 clicks ถูกต้อง
- click events แยก affiliate, own-product, LINE lead และ internal CTA
- letter-kit ปิดรับเงินแบบ fail-closed; preflight เห็นสถานะ paused แทนการหลอกว่า deliverable พร้อม
- QA quota นับเฉพาะโพสต์ที่เผยแพร่สำเร็จ ไม่เอา attempt/failure/skipped มากินโควตา
- queue selector ตัด retired/paused channel, เลือกคลังความรู้ของ “วันนี้” ก่อน package สุ่ม และ block package ที่มี
  compliance/fact/encoding flags
- post timing ตัด direct/search/AI/internal ออก, ไม่เรียก sample น้อยว่า “เวลาที่ดีที่สุด” และไม่แนะนำช่องที่
  `phase_until` หมดแล้ว; รอบล่าสุดจึงไม่มี Pantip ใน timing/queue
- สร้างคลังโพสต์ 16–31 ส.ค. 16 วัน พร้อม source/target/refresh date; validator ผ่าน 16/16 แถว
- official-source monitor ตรวจ 5 ต้นทางล่าสุดโดยไม่ดึง affiliate redirect และไม่อัปเดต facts อัตโนมัติ
- build/smoke ผ่าน 71/71 หน้า; affiliate static check ผ่าน 180 placements/18 unique links โดยยิง redirect 0 ครั้ง
- privacy guard สแกนเฉพาะ tracked structured/log filesและไม่สะท้อนค่าที่พบ
- regression checks รอบสุดท้ายผ่าน: quota 6/6, Responsible Lending 5/5, queue/timing policy 6/6,
  GA4 schema 8/8, attribution 10/10 และ privacy guard unit tests 6/6
- live read-only check เวลา 02:xx น.: Meta Planner สัปดาห์ 16–22 ส.ค. ไม่แสดง scheduled post;
  Threads โพสต์ล่าสุดราว 22 ชั่วโมงก่อน จึงยังไม่พบโพสต์ของวันที่ 16 ส.ค. แต่ต้องตรวจ ledger/dedup อีกครั้ง
  ณ เวลากดเผยแพร่

## 8. Blocker ที่ยังไม่ควรกลบ

1. video runway เป็นศูนย์และ planned park หมด 13 ส.ค.; ต้องตัดสิน batch4 แล้วผลิต 1080x1920 + audio จริง หรือกำหนด cadence ใหม่
2. scheduled task `ngernduangold-batch3-gate-final` เป็นงานวันที่ 10 ส.ค. แต่ prompt ยังอยู่และขัด policy; ต้องปิด/แก้ใน registry
3. Pantip phase หมด 14 ส.ค.; ต้องตัดสิน “ต่อ reply-only / ปิด / phase ใหม่” ก่อนทำอะไร
4. GA4 internal-IP rule ไม่ตรง IP ปัจจุบัน ทำให้ total traffic ยังไม่น่าเชื่อถือ ต้องแก้ใน GA4 Admin โดยเจ้าของสิทธิ์
5. รีโปเป็น public และ privacy guard แบบ fail-closed พบ 34 จุดใน 32 tracked files; การลบเฉพาะ working treeไม่ลบอดีต
   ต้องวางแผน rotate/redact/history cleanup ก่อน push
6. `policy.json` และไฟล์ state หลายตัวมี user changes ที่ยังไม่ commit; ห้ามให้ automation กวาด commit รวมโดยไม่ตรวจ scope

ผล preflight รอบ 02:21 ยังเป็น `2 FAIL / 7 WARN`: FAIL คือ video runway และ prompt drift เท่านั้น;
deliverable, posting cap, disclosure, attribution และ official-source freshness ผ่าน แต่คำเตือนเรื่อง sales ledger,
synthetic traffic, GA4 internal traffic, gate ค้าง และ content cliff ยังต้องติดตาม

## 9. แผน 14 วันเพื่อรายได้ที่ไม่ลดคุณค่า

1. เตรียมร่าง FB + Threads วันละ 1 หัวข้อจากคลัง C; owner เท่านั้นที่เผยแพร่หลัง privacy/source/quota/compliance/dedup ผ่านครบ
2. สัปดาห์ละ 3 หน้า: ปรับ title/intro/FAQ ของหน้า GSC impression สูง และเพิ่ม official source/date บนหน้า
3. ทำ YouTube Shorts 5 ชิ้นจากคำค้น intent สูง เฉพาะหลัง batch decision และ asset QA ผ่าน
4. วันที่ 7 และ 14 อ่านผลแบบ qualified: social/organic sessions ที่ตัด internal, affiliate click, line lead, product intent,
   landing-page CTR และยอดขายที่บันทึกจริง แยกกัน
5. โปรโมต ebook 59 บาทหลังโพสต์คุณค่าอย่างน้อย 4 ชิ้น โดยสาธิตหนึ่งหน้า/หนึ่งเครื่องมือจริง ไม่ใช้ scarcity ปลอม
6. ห้ามซื้อ traffic, เปิดช่อง paused/retired, ขาย letter-kit หรือกลับไป Pantip ก่อน blocker ถูกปิด

## 10. คำตัดสินที่ต้องได้จากเจ้าของ

- Pantip หลัง 14 ส.ค.: ปิดต่อ หรืออนุญาต reply-only รอบใหม่พร้อมวันหมดอายุ
- ช่องอื่นนอกจาก Threads: ยืนยันเพดาน 1 หรือ 2 main posts/วัน
- Video: อนุมัติ batch4 5 ชิ้น, ลด cadence หรือยุติ โดยยึดผล YouTube Studio ล่าสุด
- Privacy: อนุญาตให้ทำ remediation/rotate/history rewrite แยกเป็นงานควบคุมความเสี่ยงหรือไม่
- Letter kit: จะสร้าง deliverable 10 หน้าให้ตรงคำสัญญา หรือยุติสินค้าอย่างถาวร
