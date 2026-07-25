# ตรวจ scheduled ทั้งระบบ — รอบที่ 2 (25 ก.ค. 2026 ค่ำ)
ตรวจหลังเปลี่ยนกลยุทธ์วันนี้ (intent guard 12 หน้า · LINE funnel · พัก 3 ช่อง) เพื่อหาจุดที่ task ยัง "ทำงานตามแผนเก่า"
ขอบเขต: 88 task ในระบบ · **enabled จริง 24 ตัว** (ที่เหลือปิดไว้แล้วพร้อมเหตุผลใน description)

---

## 🔴 พบ 6 จุดไม่สอดคล้อง — แก้ครบทั้งหมดแล้ว

### 1. `daily-social-post-reminder` — ละเมิดคำสั่งเจ้าของโดยตรง ⚠️ ร้ายแรงสุด
**เจอ:** prompt สั่งให้เตือน *"เจ้าของต้องเซ็ต IG_ACCESS_TOKEN + FB_PAGE_TOKEN ลง GitHub secrets"*
ขัดกับคำสั่งถาวร: **Meta token ยกเลิกถาวร 18 ก.ค. — ห้าม agent ไหนเตือนเรื่อง token นี้อีก**
ซ้ำร้าย สถานะในไฟล์ค้างที่ 16 ก.ค. และอ้างช่วง 13–26 ก.ค. → **หมดอายุทั้งไฟล์ตั้งแต่ 27 ก.ค.**
**แก้:** เขียน prompt ใหม่ — ห้ามเอ่ย token เด็ดขาด · ตัด IG ออก (พัก) · ตัด Threads ออก (มี task ดูแลแล้ว) · เหลือ 3 ช่อง TikTok/YouTube/FB · สั่งให้อ่านสถานะจาก manifest จริงแทนที่จะเชื่อข้อความค้างใน prompt · เพิ่มการเตือนเมื่อคลังคลิปเหลือ <3 วัน (batch3 หมด 2 ส.ค.)

### 2. `tools/post_guard.py` → check_instagram — เตือนขอ token ทุกวัน
**เจอ:** คืนค่า `BLOCKED — Provide IG workflow credentials` ทุกวันที่ไม่มี token = ขอสิ่งที่เจ้าของยกเลิกถาวร
**แก้:** เพิ่ม `IG_PAUSED_FROM/UNTIL` (26 ก.ค.–25 ส.ค.) → คืน `PAUSED` พร้อมเหตุผล GA4 · กรณีอื่นคืน `MANUAL-ONLY` แทน BLOCKED และเขียนกำกับว่า **ห้ามขอ token**
**ยืนยันหลังแก้:** `INSTAGRAM: PAUSED — IG paused by decision until 2026-08-25 (GA4: 1 session / 0 conv)` ✓

### 3. `tools/post_guard.py` → check_facebook — เตือนขอ token ทุกวันเช่นกัน
**เจอ:** `BLOCKED — FB_PAGE_ID/FB_PAGE_TOKEN are not configured` + แนะนำ "Configure the FB scheduler credentials"
**แก้:** เปลี่ยนเป็น `MANUAL-ONLY` + ระบุว่าเป็นการออกแบบ ไม่ใช่ปัญหา
**ยืนยันหลังแก้:** `FACEBOOK: MANUAL-ONLY — FB publishing is manual via Business Suite by design (Meta token revoked 18 Jul 2026)` ✓
> ผลรวมข้อ 2–3: guard เลิกขอ token แล้ว 100% — ที่ผ่านมามันฝึกให้เจ้าของ "ชินกับการเห็น BLOCKED" ซึ่งอันตรายกว่าไม่มี guard เพราะทำให้เตือนจริงถูกมองข้าม

### 4. `ngernduangold-channel-heartbeat` — จะเตือนเท็จทุกวันตั้งแต่ 2 ส.ค.
**เจอ:** กติกาเขียนว่า *"Pinterest: 3-4/สัปดาห์ → ⚠️ ถ้าเกิน 7 วัน"* — Pinterest พักแล้ว จึงจะ ⚠️ ทุกวันหลังครบ 7 วัน
**แก้:** เพิ่มตาราง "ช่องที่พักโดยตั้งใจ" พร้อมหลักฐาน → รายงานเป็น `⏸ พัก` ไม่ใช่ ⚠️ · ห้ามเสนอให้กลับไปโพสต์ก่อน 25 ส.ค.
**เพิ่มให้ด้วย:** ชั้นใหม่ "เช็กฟันเนลรายได้" ขึ้นก่อน cadence — เช็กว่ามีคนพิมพ์ "เคส" ไหม + sales-log มีรายการใหม่ไหม · ถ้า 0 ติดกัน ≥7 วัน ให้สรุปว่าปัญหาอยู่ต้นทาง · และให้ยก Pantip ขึ้นหัวรายงานถ้าสัปดาห์นี้ยังไม่ครบ 3 (เพราะเป็นช่องที่ session/ชิ้นสูงสุด)

### 5. `ngernduangold-ig-reels-post` — เตือนงานที่เราตัดสินใจไม่ทำ
**เจอ:** ยัง active ทุกจันทร์ 11:00 เตือน "batch ตั้ง IG Reel 7 คลิป" ขณะที่ IG พัก
**แก้:** ปิดพร้อม IG ถึง 25 ส.ค. (เปิดพร้อมกันกับ quote-card + ig-comment-cta)

### 6. `ngernduangold-weekly-review` — **ขัดแย้งกันเองในไฟล์เดียว**
**เจอ:** บรรทัดยุทธศาสตร์บอก *"เลิกคาด sessions 400-500/สัปดาห์"* แต่ขั้นตอนที่ 8 ยังสั่ง *"รายงานความคืบหน้าเทียบแผน 14 วัน (sessions เป้า 400-500/สัปดาห์)"* → รายงานจะสรุปว่า "ต่ำกว่าเป้ามาก" ทุกสัปดาห์ทั้งที่เลิกใช้เป้านั้นแล้ว
ยังเตือน *"IG comment-CTA อ./ศ./ส."* ที่เพิ่งพักด้วย
**แก้:** ลบเป้า 400–500 ออกทั้งไฟล์ + เขียนกำกับห้ามใช้ · ตัดการเตือน IG/Pinterest · เพิ่ม 5 อย่าง:
- **session ต่อชิ้นงาน** เป็นเกณฑ์ตัดสินพัก/คืนช่อง (ฐาน 25 ก.ค.: pantip 14.5 · fb 2.5 · threads 0.6 · ig 0.2 · pinterest 0.0)
- เฝ้า **12 หน้าที่ถอด affiliate above-fold** เป็นพิเศษใน GSC
- North Star เพิ่มตัวชี้วัด **จำนวนคนพิมพ์ "เคส" ใน LINE**
- ชั้น **FB Groups เฟสช่วยเคส** (อ่าน FBGROUP-LISTEN_*.md)
- **เตือน Pantip เฟส 1 หมด 30 ก.ค.** ต้องตัดสินเฟส 2

---

## ✅ ตรวจแล้วถูกต้อง ไม่ต้องแก้ (18 ตัว)

| task | ความถี่ | ตรวจแล้วว่า |
|---|---|---|
| `pantip-daily-opportunity` | ทุกวัน 09:10 | ห้าม auto-post ถาวร ✓ · มี gate เตือนเฟส 1 หมด 30 ก.ค. ✓ · **ช่องที่ ROI สูงสุด** |
| `ngernduangold-fbgroup-listen` | ทุกวัน 10:20 | เพิ่งอัปเป็นเฟสช่วยเคส + soft-CTA + workflow 3 นาที/เคส ✓ |
| `ngernduangold-threads-daily` | ทุกวัน 19:00 | idempotent ✓ (threads ยัง 0.6 session/ชิ้น — คงไว้ ไม่เพิ่ม) |
| `ngernduangold-knowledge-post-noon` | ทุกวัน 12:40 | dup-check + ledger ✓ |
| `ngernduangold-fb-page-comment-link` | ทุกวัน 21:30 | idempotent ✓ |
| `ngernduangold-yt-comment-link` | ทุกวัน 21:15 | dup-check 2 ชั้น ✓ |
| `ngernduangold-fb-evening-safetynet` | ทุกวัน 19:00 | เพดาน ≤2/วัน ✓ ไม่ auto-post |
| `ngernduangold-tiktok-daily-nudge` | ทุกวัน 19:00 | มี "ห้ามเตือนเรื่อง token" อยู่แล้ว ✓ · kill-criterion 10 ส.ค. ชัด |
| `ngernduangold-post-guard-daily` | ทุกวัน 19:25 | script แก้แล้วตามข้อ 2–3 |
| `ngernduangold-daily-check` | ทุกวัน 08:05 | ตรวจฟันเนล ✓ |
| `cowork-task-watchdog` | ทุกวัน 08:00 | health check ✓ |
| `ngernduangold-video-post-verify` | ทุกวัน 21:30 | ตรวจไฟล์ถูกต้อง ✓ |
| `ngernduangold-uptime-monitor` | ทุก 6 ชม. | ✓ |
| `ngernduangold-drive-backup` | ทุกวัน 22:00 | mirror sales-log + post-ledger (แก้ไปแล้วรอบก่อน) ✓ |
| `ngernduangold-page2-loan-post` | อ./ศ. 13:10 | ✓ |
| `ngernduangold-funnel-endpoint-check` | พุธ 09:40 | อ่านอย่างเดียว ✓ |
| `ngernduangold-newswatch-weekly` | จันทร์ 10:30 | ✓ |
| `ngernduangold-agent-auditor` / `loop-architect` | อา./ส. | ✓ |
| `ngernduangold-90day-gate-debt-pivot` | 9 ต.ค. | ✓ |

**ไม่เกี่ยวแบรนด์นี้ (ปล่อยไว้):** airbnb ×3 (ภาษี/บัญชี) — enabled ถูกต้องตามรอบ

---

## 📌 บทเรียนที่ควรจำ
**Task ไม่ได้พังเพราะรันไม่ได้ — พังเพราะรันสำเร็จโดยใช้แผนที่เลิกใช้แล้ว**
ทั้ง 6 จุดที่เจอวันนี้ ทุกตัว `lastRunAt` เป็นวันนี้/เมื่อวาน = รันผ่านหมด แต่ผลลัพธ์ผิดทิศ
โดยเฉพาะ 3 ตัวที่ขอ token ที่เจ้าของยกเลิกถาวรไปแล้ว — เตือนซ้ำทุกวันจนกลายเป็นเสียงรบกวน ซึ่งทำให้ **เตือนจริงถูกมองข้าม**

→ ทุกครั้งที่เปลี่ยนกลยุทธ์ ต้องกวาด scheduled ทั้งชุดทันที ไม่ใช่รอให้ watchdog เจอ
→ เพิ่มเข้าเช็คลิสต์: เปลี่ยนช่อง/นโยบาย = grep หา task ที่อ้างถึงช่อง/นโยบายนั้น ก่อนปิดงาน

---
*ตรวจ 88 task · enabled 24 · แก้ 6 · ยืนยันถูกต้อง 18 · ทุกการแก้ verify กับ output จริงแล้ว*
