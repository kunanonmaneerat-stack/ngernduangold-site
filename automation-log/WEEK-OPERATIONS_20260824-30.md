# แผนปฏิบัติการคอนเทนต์ 24–30 สิงหาคม 2026

สถานะ ณ 23 สิงหาคม 2026: `DRAFT_ONLY / VALID_WITH_BLOCKERS`

## ข้อสรุปก่อนลงมือ

- ปฏิทินหลักมี 29 placements ในช่วง 24–30 สิงหาคม แต่ทั้ง 29 รายการยังเป็น `PLANNED_BLOCKED` จึงไม่ได้เปลี่ยนเป็นพร้อมโพสต์และไม่ได้สร้างสล็อตซ้ำ
- สร้างชุดข้อความสำรอง 7 วันและวิดีโอ TikTok candidate r5 จำนวน 7 ชิ้นไว้ใน `WEEK-CONTENT-PACK_20260824-30.json` โดยตัดข้อเท็จจริงเฉพาะเวลา ราคา ผลิตภัณฑ์ ลิงก์ และ affiliate CTA ออกทั้งหมด แก้ถ้อยคำที่เสี่ยงเหมารวม/กำกวมแล้ว และใช้เสียงพากย์ local TTS แบบ voice-only ให้คลิปจบหลังเสียงพูด 0.696–0.884 วินาที ภาพ/ข้อความ/full decode/hash/watermark และ audio continuity ผ่านเชิงเทคนิค แต่ยังบันทึกข้อจำกัดตามจริงว่า `HUMAN_LISTENING_NOT_RUN`
- `qt-12` และ `qt-13` มีภาพ candidate r5 ในเครื่องครบ 4 ไฟล์แบบไม่ทับหลักฐานเดิม (FB/IG 4:5 และ Pinterest 2:3) พร้อม hash และ visual/watermark QA = `PASS`; อย่างไรก็ดี ภาพเหล่านี้ยังไม่ได้ผูกกับ calendar placement จึงเป็น `LOCAL_MEDIA_TECHNICAL_PASS / PUBLICATION_BLOCKED` ไม่ใช่สื่อพร้อมโพสต์
- ห้ามนำ candidate ใหม่ไปแทน `kn-37`–`kn-43` อัตโนมัติ ต้องลงทะเบียน permanent dedup, ตรวจ slot collision และสร้าง approval bundle รายชิ้นก่อน ปัจจุบัน dedup coverage ดีขึ้นเป็น 57/125 (45.6%) แต่ยังขาด 68 แถวและมี duplicate canonical identity ที่ยังไม่ปิด 1 กลุ่ม

## ตารางทำงาน 7 วัน

| วันที่ | งานเที่ยงสำรอง | งานวิดีโอ/ภาพ | ช่องทางที่ตรวจ | สถานะตัดสิน |
|---|---|---|---|---|
| 24 ส.ค. | `wk36-sf01` แบ่งเงินเป็นสามช่อง | วิดีโอ TikTok r5 12.125 วินาทีผ่าน QA เชิงเทคนิค | Threads, Facebook, TikTok | `LOCAL_MEDIA_TECHNICAL_PASS / HUMAN_LISTENING_NOT_RUN / BLOCKED_BINDING` |
| 25 ส.ค. | `wk36-sf02` พักการซื้อหนึ่งคืน | วิดีโอ TikTok r5 8.125 วินาทีผ่าน QA เชิงเทคนิค | Threads, Facebook, TikTok; review IG/Pinterest gate | `LOCAL_MEDIA_TECHNICAL_PASS / HUMAN_LISTENING_NOT_RUN / BLOCKED_BINDING` |
| 26 ส.ค. | `qt-12` ไม่เทียบสถานะการเงินกับภาพชีวิตผู้อื่น | ภาพ r5 FB/IG 4:5 และ Pinterest 2:3 ผ่าน; วิดีโอ r5 12.417 วินาทีผ่านเชิงเทคนิค | Threads, Facebook, TikTok | `LOCAL_MEDIA_TECHNICAL_PASS / HUMAN_LISTENING_NOT_RUN / BLOCKED_BINDING` |
| 27 ส.ค. | `wk36-sf03` รายจ่ายที่ให้คุณค่า | วิดีโอ r5 8.250 วินาทีผ่านเชิงเทคนิค; `b4-p01` คงบล็อก source/manifest | Threads, Facebook, TikTok, YouTube, Instagram | `LOCAL_MEDIA_TECHNICAL_PASS / HUMAN_LISTENING_NOT_RUN / BLOCKED_BINDING` |
| 28 ส.ค. | `wk36-sf04` จดรายการรายจ่ายโดยไม่ตัดสิน | วิดีโอ r5 8.000 วินาทีผ่าน QA เชิงเทคนิค | Threads, Facebook, TikTok, Page 2 | `LOCAL_MEDIA_TECHNICAL_PASS / HUMAN_LISTENING_NOT_RUN / BLOCKED_BINDING` |
| 29 ส.ค. | `qt-13` เติบโตจากความสม่ำเสมอ | ภาพ r5 FB/IG 4:5 และ Pinterest 2:3 ผ่าน; วิดีโอ r5 9.875 วินาทีผ่านเชิงเทคนิค | Threads, Facebook, TikTok | `LOCAL_MEDIA_TECHNICAL_PASS / HUMAN_LISTENING_NOT_RUN / BLOCKED_BINDING` |
| 30 ส.ค. | `wk36-sf05` เก็บ 1 พฤติกรรม ลด 1 รายจ่าย ทดลอง 1 วิธี | วิดีโอ r5 10.333 วินาทีผ่าน QA เชิงเทคนิค | Threads, Facebook, TikTok, Pinterest | `LOCAL_MEDIA_TECHNICAL_PASS / HUMAN_LISTENING_NOT_RUN / BLOCKED_BINDING` |

## วงรอบตรวจทุกวัน

ตัวตรวจ Codex เดิม `ngernduangold-weekly-control-tower` ถูก reuse และเปลี่ยนชื่อเป็น `Ngernduangold publishing and comment control tower` แล้ว ตรวจวันละสองรอบเวลา 08:45 และ 21:45 Asia/Bangkok พร้อมแจ้งเฉพาะความผิดปกติ ไม่ได้สร้าง automation ซ้ำ

หลักฐาน liveness ปัจจุบันแยกดังนี้:

- Windows `ngernduangold_weekly` รอบ 19:17–19:22 และ `ngernduangold_daily` รอบ 19:22–19:30 วันที่ 23 สิงหาคม จบ `FINISHED / COMPLETED_WITH_BLOCKERS / final_rc=2`; receipt ล่าสุดมี 10 และ 26 ขั้นตามลำดับ ตัว runner กับ receipt tool คง hash เดิมตลอดการรัน และไม่มี `RUNNER_FAILED` ในสองรอบล่าสุด
- evidence bundle ล่าสุดยังเก็บข้อผิดพลาดประวัติไว้ตามจริง: weekly receipt รุ่นก่อนซ่อม 1 รายการมี classification ไม่สอดคล้อง และสถิติ 7 วันยังมี historical `RUNNER_FAILED` 1 รอบ ห้ามลบหรือแปลงเป็น PASS; ใช้สอง receipt ล่าสุดเป็นหลักฐานสถานะปัจจุบัน
- `ngernduangold-daily-queue` เป็น legacy duplicate ที่ disabled อยู่ ให้จัดเป็น `SKIP / LEGACY_DUPLICATE` ไม่ใช่ `MISSED`
- Claude/Cowork project schedulers ไม่มีหลักฐานรันใหม่ตั้งแต่ 18 สิงหาคม ให้จัดเป็น `SCHEDULER_STALE / MISSED_OR_STUCK` จนกว่าจะมี receipt ใหม่ ห้ามถือ `enabled=true` ว่ายังทำงาน

### รอบเช้า

1. ตรวจ receipt ของ Windows `ngernduangold_daily` และงานสัปดาห์ในวันอาทิตย์ ไม่ถือ `enabled=true` เป็นหลักฐานว่ารันสำเร็จ
2. โหลด evidence bundle ล่าสุดที่ complete และ hash-valid
3. ตรวจ runway 7 วันแยกจาก eligibility 48 ชั่วโมง
4. ตรวจ source freshness เฉพาะชิ้น, permanent dedup, quota/gap, identity/privacy และ live-local parity
5. จัดสถานะเป็น `READY_FOR_OWNER_APPROVAL`, `REPLY_DRAFT_REQUIRED`, `OWNER_DECISION_REQUIRED`, `BLOCKED`, `SKIP`, `COMPLETED_BLOCKED`, `RUNNER_FAILED`, `MISSED`, `STUCK` หรือ `UNKNOWN`

### ก่อนแต่ละสล็อต

1. ตรวจว่า placement ยังอยู่ในปฏิทินและไม่มี claim/dedup collision
2. ถ้ามีสื่อ ต้อง bind hash ของไฟล์จริงกับ visual QA และ watermark QA; ห้ามใช้ไฟล์ที่ยัง `MISSING`, `NOT_RUN` หรือ hash ไม่ตรง
3. ตรวจข้อความ exact, account, slot, policy hash และ owner approval ของชิ้นนั้น
4. ถ้า gate ใดไม่ผ่าน ให้คง `PLANNED_BLOCKED`; ห้ามโพสต์ทดแทนเอง

### รอบหลังสล็อตและคอมเมนต์

1. อ่าน inbox/activity แบบไม่กดไลก์ ไม่ตอบ และไม่แก้ไข
2. dedup ด้วย comment id + permalink; แยกคำถามจริง, spam, ความเห็นทั่วไป และเหตุเสี่ยงทางการเงิน/ข้อมูลส่วนตัว
3. สร้างร่างคำตอบ exact เฉพาะรายการที่ต้องตอบ และขออนุมัติรายรายการก่อนส่งในนาม “เงินเดือนสมองทอง”
4. ตรวจ ledger/receipt ของโพสต์ที่ควรเกิดขึ้น; ถ้าไม่มี receipt ภายใน SLA ให้ `MISSED_OR_STUCK` ไม่อนุมานว่าโพสต์แล้ว

## ผลตรวจคอมเมนต์สด 23 สิงหาคม

| ช่องทาง | ผลอ่านแบบไม่แก้ไข | งานตอบ |
|---|---|---|
| YouTube Studio | ตัวกรอง unanswered แสดงว่าไม่พบความคิดเห็น | ไม่มี |
| Facebook | ตัวกรองยังไม่ได้อ่านแสดงว่าไม่มีความคิดเห็น | ไม่มี |
| Instagram | แสดงว่าไม่มีความคิดเห็น | ไม่มี |
| TikTok Studio | แสดงว่ายังไม่มีความคิดเห็น | ไม่มี |
| Threads | ตัวกรอง “การตอบกลับ” แสดงว่ายังไม่มีกิจกรรม | ไม่มี |
| Pantip topic 44197340 comment 6 | ความเห็นสมาชิก 9373300 ยังสาธารณะ; ไม่พบ moderator warning; มีความเห็นใหม่ 8–9 แต่ไม่ได้ถามเพจโดยตรง | `NO_REPLY` |

## เงื่อนไขหยุด

- ไม่โพสต์หรือตอบเมื่อ `publication_authorized=false`
- ไม่ถือคำอนุมัติแบบกว้างเป็นการอนุมัติ exact text/media/slot รายชิ้น
- ไม่ใช้สื่อที่ไม่มี hash receipt หรือยังไม่ได้ตรวจลายน้ำ
- ไม่ใส่ลิงก์ affiliate จน landing/bio parity, merchant structure และ disclosure ผ่าน
- ไม่เปิด `ngernduangold-daily-queue` ซึ่งเป็น legacy duplicate ที่ปิดไว้
