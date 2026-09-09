# รายงานตรวจสอบ agent รายสัปดาห์ — 30 ส.ค. 2026 (20:00)

> ## ⚠️ อ่านก่อน: สัปดาห์นี้ทับ blackout ที่ยังไม่ถูกบันทึก — ตัวเลขทุกตัวข้างล่างเชื่อไม่ได้เต็มร้อย
>
> **หลักฐาน (4 ทาง ชี้ตรงกัน):**
> - `automation-log/2026-08.jsonl` มีวันที่ ≥10 ส.ค. แค่: 10, 13, 14, 15, 16, 17 แล้ว **ข้ามไป 30 ส.ค.** → รู 12 วัน (18–29 ส.ค.)
> - `post-ledger.jsonl` แถวสุดท้าย = 16 ส.ค. · **สัปดาห์ที่ตรวจ (24–30 ส.ค.) มี 0 แถว**
> - `post-guard/history.jsonl` เว้นจาก 14 ส.ค. → 20, 24, 29, 30 (3 วันจาก 16 วัน)
> - **หลักฐานชี้ขาด — งาน one-time ยิงย้อนหลังเป็นกลุ่มก้อน:** `ig-weekly-pulse` (fireAt 24 ส.ค.) lastRunAt **29 ส.ค. 18:53** · `bybit-api-key-rotation` (fireAt 27 ส.ค.) lastRunAt **29 ส.ค. 19:23** · พร้อมงานจันทร์ (`weekly-review`, `cascade-bot-weekly-check`) และงานพุธ (`funnel-endpoint-check`) **ยิงพร้อมกันหมดในวันเสาร์ 29 ส.ค. 18:53–19:23** = คิวค้างถูกไล่ทีเดียวตอนแอปเปิดกลับ
>
> **ตรงกับอาการที่ policy.json อธิบายไว้เองเป๊ะ:** งาน Cowork ยิงเฉพาะตอนแอปเปิด เจ้าของไม่อยู่ = agent หยุดเงียบโดยชั้น cron ยังเดินปกติ ไฟล์บนดิสก์จึงดูไม่ผิดอะไร
>
> **แต่ blackout นี้ยังไม่อยู่ใน `policy.json → blackouts[]`** (ตัวล่าสุดที่บันทึกคือ 3–5 ส.ค.) และ **ยาวกว่าทั้งสองครั้งก่อนรวมกัน** (12 วัน เทียบ 4 + 3)

---

## สรุปสี

| หมวด | สถานะ |
|---|---|
| 1. cadence งาน vs โควตา | 🟡 เหลือง |
| 2. task root สองฝั่ง | 🟡 เหลือง (ตรวจซ้ำไม่ได้จากที่รัน) |
| 3. ผลงานจริงจากหลักฐาน | 🔴 แดง |
| 4. compliance สุ่ม | 🟡 เหลือง |
| 5. เว็บ local build + smoke | 🟢 เขียว |
| 6. ตัวตรวจเอง (self-test) | 🟢 เขียว |
| 7. ช่วงเงียบ / blackout | 🔴 แดง |

---

## 6. ตัวตรวจเอง — 🟢 เขียว (รายงานฉบับนี้จึงเชื่อถือได้ในส่วนที่ guard ครอบคลุม)

ผ่านหมดทั้ง 4 ตัว: `test_preflight_checks` 282/0 (รวม meta-check ว่า check_* ทั้ง 30 ตัวถูกเรียกใน main จริง) · `test_post_guard_status` 27/0 · `uptime_check --selftest` 22/0 · `agent_gap_check --selftest` 63/0

## 5. เว็บ local — 🟢 เขียว

`build_site.py` exit 0 (90 ไฟล์) · `postdeploy_smoke.py --src site` → **70/70 หน้าผ่าน · ปุ่ม atth.me 110 ตัว · PASS** · merchant offer gate PASS ทั้ง 2 scope · **ไม่ได้ push** ตามคำสั่ง

## 3. ผลงานจริง — 🔴 แดง

**ไม่มีอะไรถูกเผยแพร่เลย 14 วัน** (ชิ้นสุดท้าย 16 ส.ค.)

**สำคัญ: นี่ไม่ใช่ระบบพัง แต่เป็นการแช่แข็งโดยตั้งใจ** — policy.json แก้ 16 ส.ค. เพิ่ม `publication_control.default_publication_authorized=false` และตั้ง `publication_authorized=false` **ครบทั้ง 7 ช่อง** · post-guard ตั้งแต่ 24 ส.ค. รายงาน FACEBOOK/TIKTOK/THREADS = `PUBLICATION-BLOCKED` โดย `has_fail=False` = guard เห็นว่าถูกต้องแล้ว

**สิ่งที่ต้องตัดสิน: ไม่มีวันหมดอายุหรือ gate ไหนกำกับว่าการแช่แข็งนี้จะปลดเมื่อไร** — ไม่มีรายการใน `gates[]` ที่ผูกกับมัน การแช่แข็งที่ไม่มีวันปลดกับการตายเงียบ หน้าตาเหมือนกันบนดิสก์

### manifest ตามหลัง ledger อีกครั้ง (ครั้งที่ 3)
`ledger` บันทึกโพสต์สำเร็จ แต่ `manifest.posted` ยังเป็น `null`:

| clip | ช่อง | ledger | manifest |
|---|---|---|---|
| b3-02 | facebook | video สำเร็จ | `null` |
| b3-03 | threads | video สำเร็จ | `null` |
| b3-04 | threads | video สำเร็จ | `null` |

**ledger คือความจริง** · เสี่ยง: routine ที่เห็น `null` อาจโพสต์ซ้ำจนผิดกฎ anti-spam บนช่องที่มีประวัติผิดมาแล้ว

### YouTube วัดไม่ได้ 62 จาก 76 รอบ (82%)
`YOUTUBE=UNKNOWN` เกือบทุกแถวใน post-guard เหตุผลที่ guard เขียนเอง: *"No yt_upload_log entry and manifest captions.youtube has no first-line title to match"* — ช่องที่ตรวจไม่ได้ 82% ของเวลา ไม่นับว่าถูกเฝ้า

## 7. ช่วงเงียบ — 🔴 แดง

นอกจาก blackout ข้างบน: **`agent_gap_check --json` คืน `scheduler: unknown` — "cowork registry candidate count is 0" และ `scheduler_tasks: []`**

⚠️ **ข้อควรระวังก่อนเชื่อ:** ผมรันจาก sandbox Linux ซึ่งเข้าถึง `C:\Users\nL_ku\Claude\Scheduled` ไม่ได้ ผลนี้จึงอาจเป็นผลของ *ที่ที่รัน* ไม่ใช่ guard พัง — **ต้องรันบน Windows จริงเพื่อชี้ขาด** ถ้ารันบน Windows แล้วยังได้ 0 แปลว่า guard ที่ควรจับ blackout นี้ตาบอดพอดีในรอบที่มี blackout จริง

ส่วน activity ทำงานปกติ: ร่องรอยล่าสุด post-guard 30 ส.ค. 19:27 (0.6 ชม.)

## 1. cadence vs โควตา — 🟡 เหลือง

งานรายวันที่ยังเดินจริงวันนี้: `cowork-task-watchdog` · `uptime-monitor` · `daily-social-post-reminder` · `fb-evening-safetynet` · `post-guard-daily` · `knowledge-post-noon` · `fbgroup-listen` · `cowork-cc-review-loop` (6 ชม.) — ยิงตามรอบครบ

**เปลือง token:** `post-guard-daily` · `channel-heartbeat` · `video-post-verify` · `fb-page-comment-link` · `fb-evening-safetynet` — **5 งาน/วัน ตรวจช่องที่ `publication_authorized=false` ทุกช่อง** คือรันไปก็โพสต์ไม่ได้ตามนิยาม ได้ผลลัพธ์เดิมทุกวันว่า "blocked"

## 2. task root — 🟡 เหลือง

`policy.task_roots` (snapshot 16 ส.ค.): cowork_folders 103 · registry 92 · enabled 26 · orphans 11 · cc_folders 12 · ghosts 0
`list_scheduled_tasks` รอบนี้คืน ~90 รายการ — ใกล้เคียง snapshot ไม่มีสัญญาณ drift

**ตรวจซ้ำด้วย PowerShell ไม่ได้จากที่รัน** (path Windows ไม่ reachable จาก sandbox) — ข้อนี้ยังค้าง ต้องกวาดบนเครื่องจริง

## 4. compliance — 🟡 เหลือง

ทั้งช่วงมีของเผยแพร่ **ชิ้นเดียว**: Pantip คห.6 กระทู้ 44197340 (16 ส.ค.)

✅ **ผ่าน:** ไม่มีเลขดอกเบี้ย · ไม่การันตีผล · ไม่มีลิงก์ · ไม่มีแบรนด์/ราคา/CTA · ไม่มีการอ้างตัวตนบุคคล (ไม่พบ ผม/ฉัน/ดิฉัน) · ชี้ไปสายด่วน ธปท. 1213 ซึ่งเป็นแหล่งทางการ — ตรงตาม `forbidden` ของ manual pilot ครบ

❌ **ขาด:** `"ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน"` — `compliance_checklist.md` วางข้อนี้ไว้ใต้หัวข้อ **"ทุกโพสต์/ทุกช่อง"** ไม่มีข้อยกเว้นรายช่อง

✅ **"ผลิตด้วย AI" ไม่ต้องมี — ไม่ใช่ข้อผิด** (เปิดอ่านบรรทัดจริงแล้ว): checklist เขียนว่า *"คลิปที่เจนด้วย AI →"* และ POSTING-POLICY ข้อ 3 เขียน *"(คลิป/ภาพ AI)"* — ข้อความล้วนอยู่นอกขอบเขต

⚠️ **ตรวจไม่ได้:** คห.ยังอยู่ไหม (สัญญาณ mod) — web_fetch ถูกบล็อกด้วยกฎ provenance และรอบนี้ไม่มีเบราว์เซอร์ **ยังค้าง ต้องเปิดดูด้วยตา** เพราะ Pantip อยู่สถานะ FINAL WARNING

---

## สิ่งที่ต้องแก้ เรียงตามความเสี่ยง

| # | เรื่อง | ทำไมเสี่ยง |
|---|---|---|
| 1 | **บันทึก blackout 18–29 ส.ค. ลง `policy.blackouts[]`** + รัน `agent_gap_check` บน Windows เพื่อชี้ขาดว่า guard ตาบอดจริงไหม | blackout ยาวสุดเท่าที่เคยมี ไม่ถูกบันทึก และตัวที่ควรจับมันคืนค่า unknown |
| 2 | **สินค้า 199฿ ไม่มีอยู่จริง** — `products.letter-kit-199` = `PROMISED-BUT-MISSING`, `deliverable: null` | นี่คือ North Star ทั้งอัน · หน้าเว็บสัญญา "PDF 10 หน้า" 3 ครั้ง แต่ไฟล์ไม่มีในเครื่อง — รับเงินแล้วส่งของไม่ได้ |
| 3 | **คลังโพสต์เที่ยงหมดพรุ่งนี้** — `KNOWLEDGE-POSTS-C` คลุมถึง **31 ส.ค.** และงานเติมคลังเป็น one-time ที่ปิดอยู่ (รันล่าสุด 13 ส.ค.) | 1 ก.ย. งานเที่ยงจะไม่มีอะไรให้อ่าน ไม่มีใครเฝ้าหน้าผานี้ |
| 4 | **งาน 15 วันยังไม่ commit** — 1,663 ไฟล์เปลี่ยน เนื้อหาจริง (policy.json +328/−73) commit ล่าสุด 15 ส.ค. · `drive-backup` เป็น "readiness audit only" ไม่ได้สำรองจริง | ดิสก์พัง = เสียงาน 2 สัปดาห์รวมนโยบายทั้งชุด |
| 5 | **manifest ค้าง 3 ช่อง** (b3-02 fb, b3-03/b3-04 threads) | อาจโพสต์ซ้ำ = ผิด anti-spam |
| 6 | **bybit API key เหลือ 11 วัน** (หมด 10 ก.ย.) งานเตือน **ปิดอยู่** และเพิ่งยิงย้อนหลัง 29 ส.ค. | บอทเทรดเงินจริง |
| 7 | **ตัดสินวันปลดแช่แข็ง** — ตั้ง gate มีวันที่ ไม่งั้นแยกไม่ออกจากตายเงียบ | 14 วัน 0 โพสต์ ไม่มีเงื่อนไขปลด |
| 8 | **YouTube UNKNOWN 82%** — ซ่อม yt_upload_log/manifest title matching | ช่องที่วัดไม่ได้ = ไม่ถูกเฝ้า |
| 9 | **เปิดดู Pantip คห.6 ว่ายังอยู่** + เติม disclosure การศึกษาในเทมเพลตตอบ | FINAL WARNING ผิดซ้ำ = แบนถาวร |
| 10 | **ลด cadence 5 งาน/วันที่ตรวจช่อง blocked** | เปลือง token ได้ผลเดิมทุกวัน |

*ตรวจอย่างเดียว ไม่ได้แก้ไขอะไร ไม่ได้ push*
