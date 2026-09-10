# ระบบโพสต์ — โครงที่ถูกต้อง (10 ก.ย. 2026)

*เขียนหลังยก `publication_authorized` ครบทุกช่องเมื่อ 9 ก.ย. แล้วพบว่า policy.json อ่านแล้ว "เปิดหมด" ทั้งที่จริงยังโพสต์ได้ 3 ช่อง*

---

## 1. ปัญหาที่ไฟล์นี้แก้

`policy.json` มีสองสนามที่พูดคนละเรื่องแต่ถูกอ่านรวมกัน:

| สนาม | ความหมายจริง | หลังยกกำแพง 9 ก.ย. |
|---|---|---|
| `channels.X.publication_authorized` | **เจ้าของอนุญาตไหม** | `true` ครบ 7 ช่อง |
| `channels.X.state` | **ช่องนั้นใช้งานได้ไหม** | active 2 · manual 1 · paused 2 · testing_blocked 1 · limited 1 |

ยกกำแพง = แตะสนามแรกเท่านั้น **สนามที่สองไม่ขยับ** — และสนามที่สองคือสิ่งที่หยุดจริงอยู่ 4 ช่อง

ก่อนวันนี้ คำถาม "วันนี้โพสต์ช่องไหนได้" ตอบไม่ได้ถ้าไม่เปิดอ่าน 5 ไฟล์แล้วจำทั้งหมดไว้ในหัว
นั่นคือสาเหตุที่ใบงาน 65 ใบเป็น `PLANNED_BLOCKED` หมด โดยไม่มีใครบอกได้ว่าใบไหนมีทางขยับ

## 2. โครงที่ถูกต้อง — 6 ชั้น เรียงตามลำดับที่ต้องผ่าน

```
1  publication_control.default_publication_authorized   สวิตช์ใหญ่ (หายไป = ปิด)
2  channels.X.publication_authorized                    สิทธิ์รายช่อง
3  channels.X.state + auto/auto_legs                    ช่องใช้ได้ไหม · ขานั้นบอททำได้ไหม
4  gates[] ที่ decides ช่องนี้                           วันถึงแล้วแต่ยังไม่บันทึกผล = ปิด
5  role_capabilities.actors.<actor>.social_publish      คนกดมีสิทธิ์ไหม (default = deny)
6  limits.posts_per_day + min_gap_hours                 วัดจาก ledger เวลาจริง
─────────────────────────────────────────────────────────────────────────
   ผ่านครบ 1-6 = "วางแผนได้"  ≠  "โพสต์ได้"
   authorize_live_publication() ยังเป็นด่านเดียวที่ปล่อยของออก
```

**ชั้น 1-6 ตอบได้ตอนวางแผน · ด่านจริงตอบได้ตอนยิงเท่านั้น** เพราะมันขอ receipt, calendar slot และ media QA ที่ยังไม่มีตอนวางแผน
การแยกสองอย่างนี้คือประเด็นทั้งหมด — เดิมเราไม่มีคำตอบชั้น 1-6 เลย จึงเห็นแต่ว่า "ด่านปฏิเสธ" โดยไม่รู้ว่าเพราะอะไร

## 3. วิธีอ่าน

```
python tools/channel_readiness.py --actor grok      # ทุกช่อง
python tools/channel_readiness.py --channel threads
python tools/channel_readiness.py --json            # ให้เครื่องอ่าน
```

**คำตัดสิน 3 ทาง ห้ามมีทางที่สี่ และห้ามยุบ**

| | ความหมาย | เงื่อนไขบังคับ |
|---|---|---|
| `READY` | ผ่านชั้น 1-6 | บอกจำนวนที่โพสต์ไปแล้ววันนี้/เพดาน |
| `BLOCKED` | มีสนามที่บอกว่าไม่ | **ต้องบอกชื่อ path ของสนามนั้นเสมอ** — "blocked" เฉยๆ คือวิธีสอนคนอ่านให้เลิกอ่าน |
| `UNKNOWN` | อ่านไม่ได้ | **ห้ามยุบเป็น BLOCKED** · ledger อ่านไม่ได้ = ไม่ READY ด้วย เพราะเพดานที่วัดไม่ได้ไม่ใช่เพดาน |

ทดสอบย้อนกลับไว้ 21 เคสใน `tools/test_channel_readiness.py` — ทุกด่านต้องพิสูจน์ได้ว่ายิงได้จริงและเงียบได้จริง
เหตุผลที่ต้องมี: ตอนนี้ 4 ใน 7 ช่องติดที่ชั้น 3 ⇒ ชั้น 4, 5, 6 **ไม่เคยถูกรันกับข้อมูลจริงเลย** ถ้าไม่ทดสอบตรงๆ มันจะนั่งพังเงียบๆ ได้เป็นเดือน

## 4. สถานะจริง 10 ก.ย. 2026 (actor = grok)

| ช่อง | ขา | ผล | สนามที่ตัดสิน |
|---|---|---|---|
| youtube | video | ✅ READY | 0/2 วันนี้ |
| facebook | text | ✅ READY | 0/2 วันนี้ |
| facebook | comment | ✅ READY | 0/2 วันนี้ |
| threads | video | ✅ READY | 0/2 วันนี้ |
| facebook | video | 🔴 BLOCKED | `auto=false` และไม่อยู่ใน `auto_legs` — Reel เป็นขาของเจ้าของเท่านั้น |
| tiktok | video | 🔴 BLOCKED | `channels.tiktok.state = testing_blocked` |
| instagram | video | 🔴 BLOCKED | `channels.instagram.state = paused` |
| pinterest | image | 🔴 BLOCKED | `channels.pinterest.state = paused` |
| pantip | forum | 🔴 BLOCKED | `channels.pantip.state = limited` |

**4 ขาพร้อมวางแผน · แต่ยังไม่มีใบงานให้หยิบ** — ปฏิทิน `.system_control/content_calendar.json` มี 65 placements เป็น `PLANNED_BLOCKED` ทั้งหมด และไม่มีใบของวันนี้
⇒ คอขวดจริงตอนนี้คือ **ของ ไม่ใช่สิทธิ์** ยกกำแพงแล้วแต่ไม่มีอะไรจะส่ง

## 5. สิ่งที่เพิ่มวันนี้และเหตุผล

- **`role_capabilities.actors.grok`** — ก่อนหน้านี้ไม่มี actor ชื่อนี้เลย `default = deny` จึงปฏิเสธทุกครั้ง **และการปฏิเสธนั้นดูเหมือนปัญหาของช่อง** เพิ่มเข้าไปเพื่อให้ตัวขวางที่เหลือโผล่ออกมาให้เห็น
  `social_publish: true` (คำสั่งเจ้าของ) · `local_write: false` — Grok กดโพสต์ ไม่ใช่คนเขียนหรือคนตัดสิน
  ตาม `capability_semantics` เดิม: นี่คือเพดานของบทบาท **ไม่ใช่การอนุมัติโพสต์ชิ้นใด**
- **`grok` ใน `forbidden_public_speakers`** (9 ก.ย.) — ผู้ปฏิบัติงานภายใน ไม่ใช่ byline

## 6. ที่ยังไม่รู้ — ต้องทดสอบ ห้ามเดาไปทางไหนทั้งนั้น

1. **Grok โพสต์ช่องไหนได้จริงบ้าง** ยังไม่มีใครถาม — ผมเคยสรุปผิดว่า FB/Threads ทำไม่ได้เพราะ Meta token ถูกเพิกถอน ซึ่งเป็นการอนุมานความสามารถของเครื่องมือที่ไม่เคยตรวจ จากข้อเท็จจริงของบัญชีเราเอง (บันทึกไว้แล้วใน `policy.json → _lifted_20260909.cowork_error_on_record`)
2. **`publication_authority` ไม่มีเส้นทางเผยแพร่ตรงสำหรับ pinterest / pantip** (Codex ตรวจพบ) — ต่อให้เปิด state แล้วก็ยังไม่มีทางออก
3. **Threads ต้องมี `.local-private/runtime/manual-publication-calendar.json`** ซึ่งตอนนี้ **ไม่มีไฟล์** — threads แสดง READY ที่ชั้น 1-6 แต่จะตกที่ด่านจริง

## 7. ต้องรอเจ้าของ

- 🔴 **Bybit API key หมดอายุวันนี้ 10 ก.ย.** — เงินจริง · `C:\groq_bybit_bot` · agent ห้ามแตะทั้งหมด
- gate 25 ส.ค. เรื่อง instagram / pinterest **ยังไม่มีผลบันทึก** — วันผ่านไปไม่เท่ากับเปิดช่องกลับ
- Pantip review 18 ส.ค. ยัง `OPEN` · โควตา ≤1/สัปดาห์ · FINAL WARNING
- `products.letter-kit-199` = `PROMISED-BUT-MISSING` — ห้าม CTA 199฿ จนกว่าจะมีของส่ง
- ยืนยันการลบไฟล์สื่อ 16 ไฟล์ที่ค้าง unstaged อยู่
