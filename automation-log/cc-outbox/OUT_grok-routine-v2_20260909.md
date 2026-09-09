# ผลตรวจรูทีน Grok v2 — 9 กันยายน 2026

## 1. รูทีน v2 ขัด policy.json ข้อไหน

**ผล: แนวทางตรวจล่วงหน้าและยืนยันโพสต์จริงใช้ได้ แต่ v2 ยังไม่ครบเงื่อนไขสำหรับเปิดโพสต์อัตโนมัติทุกช่อง** การยกสิทธิ์วันนี้ไม่ยก dated gate หรือการอนุมัติรายชิ้น

ตรวจ `.system_control/policy.json` ปัจจุบันแล้ว: `publication_control.default_publication_authorized` และ `channels.{youtube,facebook,threads,tiktok,instagram,pinterest,pantip}.publication_authorized` เป็น `true` ครบ; `publication_control._lifted_20260909.date = "2026-09-09"` และ `public_identity.forbidden_public_speakers` มี `grok` แล้ว ทั้งสองจุดที่ Cowork แก้ถูกต้อง ไม่ต้องแก้ซ้ำ

| Path ใน policy.json | ผลต่อ v2 |
|---|---|
| `publication_control.authority_rule` และ `publication_control._lifted_20260909.what_this_does_NOT_change` | ต้องผ่านทั้งสิทธิ์ช่อง + dated gate ที่เกี่ยวข้อง + owner approval รายชิ้น การเขียน attempt และผลลัพธ์ไม่แทนเงื่อนไขเหล่านี้; ต้องคง approval รายชิ้นของ v1 สำหรับทุกช่องที่ใช้บังคับ ไม่ใช่ระบุเฉพาะ Pantip |
| `channels.pantip.manual_pilot.forbidden`, `.scope`, `.weekly_quota`, `.week_definition`, `.review_must_pass_before_reauthorization`, `.authorization_state`; `gates[14].status` | v2 ยังตกหล่น: ห้าม `automated_publication`, ตอบกระทู้เดิมเท่านั้น, ≤1/สัปดาห์ จันทร์–อาทิตย์ Asia/Bangkok, ต้องผ่าน review ก่อนอนุมัติใหม่; สิทธิ์ครั้งเก่าใช้แล้ว และ review ยัง `OPEN` การอนุมัติรายชิ้นในวันนั้นเพียงอย่างเดียวจึงไม่ปลดข้อห้ามทั้งหมด |
| `channels.instagram.state`, `channels.pinterest.state`, `gates[5]` | ทั้งสองยัง `paused`; gate ทบทวน 25 ส.ค. ไม่มีผลตัดสินบันทึกไว้ วันผ่านไปไม่เท่ากับเปิดช่องกลับ **UNKNOWN:** ผลทบทวนจริงนอกไฟล์ตรวจไม่ได้; ห้ามอนุมานว่า gate ผ่าน |
| `channels.tiktok.state`, `channels.tiktok.reactivation_test.{status,end_not_after,blockers,cadence}` | ยัง `testing_blocked` / `PLANNED_BLOCKED`; แผนทดสอบสิ้นสุด 30 ส.ค. และกำหนดหนึ่งคลิป/วัน ต้องมีการทบทวนและผ่าน blocker รายชิ้นก่อน ไม่ใช้เพดานทั่วไป 2/วันแทน |
| `channels.facebook.video_path.{automated,owner}`; `publication_control.automation_capable_definition` | เส้นทาง Reel ที่บันทึกไว้ยัง `false` / `owner-only`; technical capability ไม่ใช่สิทธิ์เผยแพร่ **UNKNOWN:** ความสามารถ integration ของ Grok ยังไม่ได้ทดสอบ ห้ามสรุปว่า Grok ทำไม่ได้จากการเพิกถอน token ของแอปเดิม (ตาม `_lifted_20260909.cowork_error_on_record`) |
| `products.items[0].{status,promotion_authorized}` | letter-kit-199 ยัง `PROMISED-BUT-MISSING` / `false`; ห้าม CTA 199฿ ตรงตามสเปก นอกจากนี้ `products.items[1].promotion_authorized` และ `[2].promotion_authorized` ก็ยัง `false` จึงไม่เปิดขายโปรโมตสินค้าอื่นโดยอาศัยสิทธิ์ช่อง |
| `limits.posts_per_day.{default,pinterest}`, `limits.min_gap_hours` | ≤2/วัน/ช่อง, Pinterest ≤5, ห่าง ≥3 ชม. ตรงกับ v2 แต่ต้องรักษาโควตาเฉพาะช่องที่เข้มกว่า และแยกเวลาจริงออกจากเวลาจอง |
| `public_identity.{page_only,public_speaker_rule,forbidden_public_speakers,required_prompt_marker}` | พูดในนามเพจและห้าม byline agent ตรงกับ v2; prompt ที่ผลิตข้อความสาธารณะต้องมี `PUBLIC_IDENTITY_PAGE_ONLY` |
| `blackouts[2].scope`, `blackouts[2].until` | การพักยังครอบคลุม ALL Cowork scheduled tasks โดย `until=null`; การยกสิทธิ์ไม่ใช่คำสั่งเปิด scheduler กลับ ทั้งนี้ scope ไม่ได้เขียนว่าห้าม Grok ทุกชนิดหรือหยุด cron ทั้งระบบ |

คงกฎ `automation-log/POSTING-POLICY_antispam_20260702.md` ด้วย: dedup, disclosure เพื่อการศึกษา/พันธมิตรเมื่อเกี่ยวข้อง/AI เมื่อใช้, ห้ามตัวเลขดอกเบี้ยและการันตีในภาพ–เสียง–แคปชัน, ใช้เครื่องมือทางการก่อนหรือ human-in-loop, และข้อจำกัดเฉพาะช่อง ไม่ใช่ตรวจเพียงโควตา คง zero-budget ห้าม ads/boost ตามสเปกโดยตรง

## 2. ตรวจ compliance ตรงจุดไหนของสาย

**เห็นด้วย: Codex ตรวจก่อน Grok หยิบใบงาน** ตรวจข้อความและสื่อฉบับสุดท้าย แหล่งข้อมูล/ปลายทาง disclosure ตัวตนเพจ สินค้า dedup สิทธิ์ช่อง dated gate และ approval รายชิ้น แล้วผูกผลกับ `content_id`, `placement_id`, บัญชี, slot และ hash ของข้อความ/สื่อ/หลักฐาน

ก่อนส่งจริง Grok ต้องตรวจซ้ำเฉพาะสิ่งที่เปลี่ยนได้: hash ยังตรง, approval ยังใช้ได้, บัญชีตรง, slot ไม่หมดอายุ, ledger อ่านได้ครบ, เวลาโพสต์จริงและโควตาล่าสุด แล้วจองผ่านกลไก ledger เดิมอย่าง atomic ก่อนแตะแพลตฟอร์ม เปลี่ยนข้อความ/สื่อ/บัญชี/เวลาแล้วต้องตรวจใหม่; ห้ามยก `BLOCKED` เป็นพร้อมเอง

ใช้ `READY` เฉพาะเมื่อหลักฐานที่ต้องใช้ครบและผ่าน; `BLOCKED` เมื่อรู้ว่าขาดหรือผิดพร้อมชื่อ field; `UNKNOWN` เมื่ออ่าน/ตรวจหลักฐานไม่ได้พร้อมเหตุ ทั้งสองสถานะหลังหยุดโพสต์เหมือนกันแต่ต้องคงคำตัดสินแยกกัน หลังส่งตรวจ URL เปิดได้จริง พร้อมข้อความ สื่อ บัญชี และเวลา แล้วจึงบันทึกสำเร็จ การตรวจหลังโพสต์เป็นการกระทบยอด ไม่แทนด่านก่อนส่ง

## 3. ใบงานและ ledger เก็บที่ไหนให้เป็นที่เดียว

**ใช้ของเดิม: ใบงานแผนกลาง `.system_control/content_calendar.json` ที่ `placements[]`; ผลปฏิบัติงานกลาง `automation-log/post-ledger.jsonl`** เชื่อมด้วย `content_id` / `placement_id` และบัญชี; อ่านข้อความจาก `placements[].source.file` + `row_id` + `field` ตามต้นทางเดิม ไม่คัดลอกเป็นใบงาน Grok อีกชุด ไม่ใช้ไฟล์ post-queue รายวันเป็นแหล่งแก้แผนคู่ขนาน

ตรวจไฟล์แล้วมี 65 placements ทุกแถวเป็น `PLANNED_BLOCKED` และไม่มี placement วันที่ 9 ก.ย. 2026 จึงไม่มีใบงานพร้อมของวันนี้ให้หยิบจากแผนนี้ การยกสิทธิ์ระดับช่องไม่แก้สถานะใบงานเอง

**ข้อจำกัดจริงที่ห้ามกลบ:** โค้ด `tools/publication_authority.py:381` เลือกปฏิทินเฉพาะ Threads เป็น `.local-private/runtime/manual-publication-calendar.json` ซึ่งตรวจแล้ว **ไม่มีไฟล์**; schema ต้องเป็น owner-controlled, text-only และ owner-approved (`:386–452`) จึงยังพูดไม่ได้ว่าระบบปัจจุบันมีใบงานพร้อมยิงจากไฟล์เดียวครบทุกช่อง ให้ใช้แผนกลางเดิมสำหรับออกแบบงาน แต่ Threads ยังติดไฟล์อนุมัติตามสัญญาโค้ดเดิม ไม่เสนอสร้างแหล่งใบงานใหม่หรือข้าม guard ในงานตรวจนี้

ledger ปัจจุบันอ่าน UTF-8 และ parse JSONL ได้ 177 แถว; การอ่านได้ครั้งนี้ไม่ยืนยันความครบของประวัติบนแพลตฟอร์ม **UNKNOWN:** ยังไม่ได้ตรวจ runtime ของ Grok ว่าอ่าน path นี้จริง เรียก guard จริง หรือมีโพสต์นอก ledger หรือไม่ (`OPERATING-NOTES.md:848` ข้อ 29 เตือนเรื่องตรวจผิดไฟล์/guard ไม่ถูกเรียก)

## 4. Failure mode ที่ v2 ยังไม่ครอบคลุม

**พบจริงจากโค้ด: `attempt` เป็นบันทึกการลอง ไม่ใช่การจองกันซ้ำ** `automation-log/post_ledger.py:229–234` จัด `attempt` ใน `_NON_IDENTITY_TYPES`; `load_index` ที่ `:1096–1113` ข้ามแถวที่ไม่มี identity จึงไม่กัน dedup/โควตาด้วย attempt อย่างที่ v2 อาจเข้าใจ ledger จริงมี attempt 14 แถว และไม่มี `dedup_key`, `content_id`, `placement_id` ในแถวเหล่านั้น

กลไกที่จะพลาด: เขียน attempt → แพลตฟอร์มรับโพสต์แล้ว → process ถูกปิดก่อนเขียนผล → รอบใหม่ไม่เห็น publication identity จึงอาจส่งซ้ำ หรือสอง worker ตรวจเพดานพร้อมกันแล้วผ่านทั้งคู่ คำว่า “หลังจบเขียนผลเสมอ” รับประกันไม่ได้เมื่อ process ตาย นี่เป็นเส้นทางล้มเหลวที่อนุมานจากโค้ด ไม่ใช่ข้อกล่าวหาว่า Grok เคยโพสต์ซ้ำแล้ว

แนวทางที่ต้องเพิ่มในรูทีน: ใช้ claim ที่มีอยู่ (`claim_text_publication` ที่ `post_ledger.py:1641` / `claim` ที่ `:1712`) ซึ่งจองภายใต้ lock และบันทึกถาวรก่อนส่ง; คง attempt ตามสเปกเป็น audit ประกอบ ไม่ให้แทน claim; กำหนด recovery สำหรับ claim ค้าง/ผล `unknown` โดยตรวจแพลตฟอร์มก่อน retry และไม่ถือ timeout ว่า failed แน่นอน การนับเว้นช่วงต้องแยกเวลาจริงจากเวลาจองของ claim และจองความจุไว้จนกระทบยอดได้

**พบอีกจุด:** การเพิ่ม `grok` ใน forbidden byline ไม่ได้เพิ่มสิทธิ์ผู้ปฏิบัติงาน `.system_control/role_capabilities.json` ยัง `default=deny` และไม่มี `actors.grok`; `tools/publication_authority.py:922` ตรวจ `social_publish` ของ actor ดังนั้นใช้ actor `grok` ผ่านเส้นทางนี้จะถูกปฏิเสธ อีกทั้งฟังก์ชันนี้ไม่รองรับ direct publication ของ Pinterest/Pantip (`:889?890`) — ห้ามแก้ด้วยการปลอม actor หรือข้าม guard

ขอบเขตงานนี้: ตรวจไฟล์และโค้ดแบบอ่านอย่างเดียว แล้วเขียนทับรายงานนี้เพียงไฟล์เดียว ไม่ได้รัน publisher/guard ที่อาจเขียน receipt หรือ ledger ไม่ได้เปิดเว็บหรือโพสต์จริง ไม่ได้เปลี่ยน policy/ใบงาน/สิทธิ์ และไม่อ้างว่าทดสอบ Grok end-to-end แล้ว ไม่ใช้ git push, git add -A หรือคำสั่งลบ

> หมายเหตุ Cowork: บรรทัดปิดท้ายเดิมของ Codex เป็นภาษาไทยที่ถูกแปลงเป็น `?` ตอนเขียนออกผ่าน codepage ที่ไม่มีอักขระไทย เนื้อหาข้อ 1-4 ข้างบนไม่ได้รับผลกระทบ (ตรวจแล้ว decode UTF-8 ผ่าน ไม่มี U+FFFD) — บรรทัดนั้นเคยเขียนว่าตรวจ UTF-8 ผ่านและไม่มี U+FFFD ซึ่งจริงทั้งคู่ แต่ตัวมันเองพังไปแล้ว จึงเพิ่ม verdict `flattened` ลง `tools/encoding_probe.py` วันนี้
