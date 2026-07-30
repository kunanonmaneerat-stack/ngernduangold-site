# ตรวจระบบอัตโนมัติ — 30 ก.ค. 2026

> คำถาม: "ระบบยังทำงานถูกต้องไหม หลังพักไปเพื่อประหยัด token"
> คำตอบสั้น: **ระบบไม่พัง — แต่ถูกปิดอยู่ 16 ตัว และไม่มีใครเปิดกลับ**

---

## 1. ภาพรวม: มี 2 ระบบ ตอนนี้เหลือวิ่งจริงระบบเดียว

| ระบบ | สถานะ | หลักฐาน |
|---|---|---|
| **ฝั่ง Claude Code (dispatcher)** | 🟢 วิ่งปกติ | `dispatcher.log` วิ่งล่าสุด 30 ก.ค. 07:16 + 07:30 · run_daily exit=0 |
| **ฝั่ง Cowork (scheduled tasks)** | 🔴 **ปิดหมด** | งานปฏิบัติการ ngernduangold ทุกตัว `enabled=false` |

routine ที่ยังมี log จริงเหลือ 4 ตัว (delivery-heartbeat · first-signal · comment-loop · pantip-monitor)
— ทั้ง 4 มาจากฝั่ง dispatcher ไม่ใช่ Cowork

---

## 2. หลักฐานว่า "ถูกปิด" ไม่ใช่ "พัง"

**16 งานหยุดพร้อมกันวันเดียว = 26 ก.ค.** (ไม่มีตัวไหน error ก่อนหยุด)

```
26 ก.ค. 01:05  ngernduangold-daily-check         26 ก.ค. 12:09  ngernduangold-threads-daily
26 ก.ค. 01:08  cowork-task-watchdog              26 ก.ค. 12:09  fb-evening-safetynet
26 ก.ค. 01:10  daily-social-post-reminder        26 ก.ค. 12:27  post-guard-daily
26 ก.ค. 02:10  pantip-daily-opportunity          26 ก.ค. 14:10  channel-heartbeat
26 ก.ค. 03:21  fbgroup-listen                    26 ก.ค. 14:25  yt-comment-link
26 ก.ค. 05:40  knowledge-post-noon               26 ก.ค. 14:33  fb-page-comment-link
26 ก.ค. 12:01  tiktok-daily-nudge                26 ก.ค. 14:33  video-post-verify
26 ก.ค. 15:07  drive-backup                      26 ก.ค. 17:04  uptime-monitor
```

**และ run-log ยืนยันตรงกัน:** 27 ก.ค. = 6 รอบ · **28-29 ก.ค. = 0 รอบ** · 30 ก.ค. = 4 รอบ

→ blackout 27-30 ก.ค. อธิบายได้ครบ: **ท่อขาด (batch3 ไม่ถูก wire) + คนคุมท่อถูกปิด (16 งาน)** เกิดพร้อมกัน

---

## 3. งานที่ยังเปิดอยู่ — เหลือ 3 ตัว และเป็นงาน "คิดแผน" ล้วน

| งาน | รอบถัดไป | หมายเหตุ |
|---|---|---|
| ngernduangold-loop-architect | เสาร์ 1 ส.ค. 10:00 | สร้าง agent ใหม่มาเติมช่องว่าง |
| ngernduangold-agent-auditor | อาทิตย์ 2 ส.ค. 20:00 | ตรวจคุณภาพงาน agent |
| ngernduangold-90day-gate | 9 ต.ค. | gate ตัดสิน pivot |

⚠️ **ความเสี่ยงที่ควรรู้:** สุดสัปดาห์นี้ทั้ง 2 ตัวจะ fire ขณะที่งานปฏิบัติการปิดหมด
→ loop-architect จะ "หาช่องว่างแล้วสร้าง agent เพิ่ม" ทั้งที่ agent เดิม 16 ตัวยังปิดอยู่ = สร้างของซ้ำ/เปลืองโดยเปล่า

---

## 4. เรื่องที่ปิดแล้วเจ็บทันที (เรียงตามความเสี่ยง)

| # | งานที่ปิด | ผลที่เกิดแล้ว |
|---|---|---|
| 1 | `cowork-task-watchdog` | **ตัวที่ควรเตือนว่า "งานอื่นถูกปิด" ก็ถูกปิดไปด้วย** → ไม่มีใครส่งเสียง 4 วัน |
| 2 | `ngernduangold-uptime-monitor` | ไม่มีการเช็กเว็บล่ม/Netlify pause มา 4 วัน (เว็บยังปกติ — ตรวจแล้วรอบนี้) |
| 3 | `ngernduangold-drive-backup` | **ไม่มี backup ขึ้น Drive มา 4 วัน** (ledger/manifest/log อยู่ในเครื่องอย่างเดียว) |
| 4 | `daily-social-post-reminder` + `post-guard-daily` | ไม่มีใครบอกว่าวันนี้ต้องอัปคลิปอะไร และไม่มีใครตรวจว่าอัปครบไหม |
| 5 | `pantip-daily-opportunity` | ปิดช่องที่ให้ผลสูงสุด (4.7 session/ชิ้น · 4 ใน 7 conversion ของทั้งเว็บ) |

---

## 5. ของใหม่ที่ทำเสร็จรอบนี้: `tools/runway_guard.py`

ปิดช่องว่างที่ทำให้ blackout รอบนี้เงียบสนิท — guard เดิมทุกตัวตรวจ **หลัง** โพสต์ไม่ออก (สายไปแล้ว)
ตัวนี้ตรวจ **ก่อน**: เหลือของในคิวกี่วัน และ 3 ไฟล์ต้นทางตรงกันไหม

```
python tools/runway_guard.py            # exit 0 = ปกติ · 1 = คิวใกล้หมด · 2 = ไฟล์ไม่ตรงกัน
python tools/runway_guard.py --json     # ให้ heartbeat/dispatcher กินต่อ
```

**ทดสอบย้อนเหตุการณ์จริง 27 ก.ค.** (จำลองสถานะก่อนแก้) → guard จับได้ทันที:
```
runway_guard [DRIFT]  today=2026-07-27
  manifest 7 วัน | schedule 0 วัน | content_map 0 วัน
  PROBLEMS: schedule is missing 7 future day(s) that manifest has: 2026-07-30, ...
  exit=2
```
**สถานะวันนี้:** `[OK] effective runway = 7 วัน` (ถึง 5 ส.ค.)

ตรวจ 3 ชั้น: (1) ของเหลือกี่วัน (2) 3 ไฟล์ตรงกันไหม (3) ไฟล์คลิปมีจริงบนดิสก์ + status เลย Rendered แล้ว

---

## 6. ข้อเสนอเปิดระบบกลับ — เปิดเท่าที่คุ้ม ไม่เปิดหมด

เกณฑ์: ดูจาก session/ชิ้น จริงใน GA4 ไม่ใช่ "เคยเปิดไว้ก็เปิดต่อ"

**ชั้น 1 — กันเจ็บ (ควรเปิดแน่นอน · กิน token น้อยมาก)**
- `ngernduangold-uptime-monitor` (ทุก 6 ชม.) — เว็บล่ม = ทุกอย่างจบ
- `cowork-task-watchdog` (08:00) — ตัวที่จะไม่ให้เกิดเหตุแบบนี้ซ้ำ
- `ngernduangold-drive-backup` (22:00) — ข้อมูลอยู่ในเครื่องอย่างเดียวมา 4 วันแล้ว

**ชั้น 2 — ส่งของ batch3 ที่เพิ่งต่อคิวไว้ถึง 5 ส.ค.**
- `daily-social-post-reminder` (08:00) — บอกว่าวันนี้อัปคลิปไหน
- `ngernduangold-post-guard-daily` (19:25) — ตรวจ 5 ช่องว่าขึ้นครบไหม
- `ngernduangold-threads-daily` (19:00) — โพสต์ Threads อัตโนมัติ *(หมายเหตุ: Threads = 0 session/22 ชิ้น — ถ้าจะตัด ตัดตัวนี้ก่อนเพื่อน)*

**ชั้น 3 — ช่องที่ทำเงินจริง**
- `pantip-daily-opportunity` (09:10) — 4.7 session/ชิ้น สูงสุดในระบบ

**ยังไม่ต้องเปิด:** IG/Pinterest/quote-card (พักตามแผนถึง 25 ส.ค.) · fbgroup-listen (ติดที่เจ้าของยังไม่ได้กด join กลุ่ม) · gsc-index-nudge (เอกสารของมันเองระบุว่าไม่ให้ผลเพิ่ม) · page2 · threads-refill

---

## 7. สรุปคำตอบ

ระบบ **ไม่มีอะไรพัง** — โค้ด gate เว็บ smoke 71/71 · link audit ผ่าน · dispatcher วิ่งทุกวัน · validate 0 error
สิ่งที่เกิดคือ **ปิดไว้แล้วลืมเปิด** และตัวที่ควรเตือนเรื่องนี้ (`cowork-task-watchdog`) ก็ถูกปิดไปพร้อมกัน

*ตรวจ 30 ก.ค. 2026 · จาก scheduled-task list จริง + run-log ก.ค. 129 รอบ + dispatcher.log*
