# VIDEO-POST VERIFY - FAIL (2 ก.ย. 2026)

> ตรวจ 2 ก.ย. 2026 (read-only) · ไม่มีการโพสต์/ลบ/แก้ไขใดๆ จากรอบนี้

## สรุปหนึ่งบรรทัด
วันนี้ **ไม่มีวิดีโอถูกโพสต์เลย (0 โพสต์ ทุกช่อง)** จึงไม่มีไฟล์ผิดหลุดออกไป — FAIL ที่เห็นคือ
**media guard บล็อกคลิปที่ยัง "รอคนฟังเสียง"** ไม่ใช่ลายน้ำ ไม่ใช่ไฟล์ผิดเวอร์ชัน

## รายการที่ FAIL (1 รายการ)
| ช่อง | placement | วันที่ | เหตุผล |
|---|---|---|---|
| Instagram | `b4-p01__instagram_main` | 2026-09-02 19:00 | media guard FAIL: `human audio review is missing` |

ไฟล์ที่เกี่ยวข้อง: **`reels/2026-08-16_b4-p01.mp4`**

## ไฟล์นั้น "ไม่ได้เสีย" — หลักฐาน
- ffprobe: **1080x1920** h264 (ไม่ใช่ 720x1280 ไม่ใช่ตัว plain)
- ตรงกับที่ปฏิทินระบุ (`content_calendar.json` -> `b4-p01__instagram_main.media`)
- ลายน้ำ: `qa_watermark.py` **PASS** (65 เฟรม · track_frames=0 · track_frac=0.0)
- visual review: PASS (contact sheet + hook + end frame)
- receipt: `automation-log/media-qa/b4-p01-video.json` (sha256 D0A07323...8DAC)

**สิ่งที่ขาดจริงๆ:** receipt ยังไม่มีบล็อก `audio_review` ที่ยืนยันโดยมนุษย์
(`tools/media_publish_guard.py:459`) ระบบเองจัดประเภทเคสนี้ว่า `is_human_blocked`
(`tools/next48_media_revalidation.py:122`) = รอคนตรวจ ไม่ใช่สื่อบกพร่อง

## ผลลายน้ำรอบ 07:00 (อ่านผล ไม่ได้สแกนซ้ำ)
- verdict FAIL · `2026-09-02T07:01:41+07:00` · finding มีข้อเดียวคือ human audio review
- veo-frame-scan **44/44 PASS** · ทุกไฟล์ track_frames = 0 -> **ไม่มีลายน้ำที่ไหนเลย**
- hash-bound-media-guard 4 PASS / 1 FAIL (b4-p01 ข้างบน)
- ไม่มีไฟล์ใน `reels/` หรือ `_vidout/` ถูกแก้หลัง 07:00 วันนี้ -> ไม่ต้องสแกนซ้ำ

## จับคู่ ledger กับ manifest
- `post-ledger.jsonl`: **0 แถวของเดือน ก.ย.** (แถวล่าสุด 2026-08-16) -> ไม่มีโพสต์ให้จับคู่
- `content_manifest.json`: item ล่าสุดคือ 2026-08-08 -> ไม่มี item ของวันนี้
- ปฏิทิน: 65/65 placement = `PLANNED_BLOCKED`, ทุกช่อง `publication_authorized=false`
- YouTube: ไม่มีงานอัปโหลดใหม่ (task file ล่าสุด 26 มิ.ย.) · `latest.md` รอบล่าสุดของ routine นี้คือ 14 ส.ค. (ok)

## ชื่อไฟล์แจ้งเตือนทำให้เข้าใจผิด
`cowork-inbox/WATERMARK-ALERT.md` เขียนว่า "canonical/future media coverage FAIL - See dispatcher.log"
— ไม่มีคำว่าลายน้ำ ไม่มีชื่อไฟล์ ต้องเปิด dispatcher.log ถึงจะรู้เหตุ
คนอ่านครั้งแรกจะเข้าใจว่าเจอลายน้ำ ทั้งที่ลายน้ำผ่านหมด ควรเปลี่ยนชื่อ/ข้อความให้ตรงเหตุ

## วิธีแก้ (เรียงตามลำดับ)
1. ให้เจ้าของฟังเสียงคลิป `reels/2026-08-16_b4-p01.mp4` แล้วเติมบล็อก `audio_review` ลง
   `automation-log/media-qa/b4-p01-video.json` ให้ครบตามที่ guard ต้องการ:
   `status: PASS` · `reviewer_is_human: true` · `reviewer_type: OWNER` (หรือ HUMAN) ·
   ชื่อผู้ตรวจ · `asset_sha256` ตรงกับ D0A07323...8DAC · `reviewed_at` มี timezone และไม่เป็นอนาคต
2. รัน `tools/media_publish_guard.py` ใหม่ให้ verdict = PASS แล้วค่อยลบ
   `automation-log/cowork-inbox/WATERMARK-ALERT.md` (ตอนนี้ยังลบไม่ได้ เพราะเงื่อนไขยังไม่ผ่าน)
3. **ไม่ต้องลบหรืออัปโหลดใหม่ที่ช่องไหน** เพราะยังไม่มีอะไรถูกโพสต์
4. หมายเหตุ: ต่อให้ audio review ผ่าน IG ก็ยังไม่โพสต์อัตโนมัติ เพราะ publication authority ยังปิดอยู่

## หลักฐาน
- `.local-private/runtime/dispatcher.log` -> verdict JSON `"today": "2026-09-02"` เวลา 07:01:41
- `.system_control/content_calendar.json` -> placement `b4-p01__instagram_main`
- `automation-log/media-qa/b4-p01-video.json`
- `automation-log/post-ledger.jsonl` (0 แถวเดือน ก.ย.)


---

## รอบตรวจซ้ำ 21:46 (2 ก.ย. 2026)

สถานะ **ไม่เปลี่ยนจากรอบ 14:49** — ยังคง FAIL ด้วยเหตุเดิมเพียงข้อเดียว

- `post-ledger.jsonl` ไม่ถูกแก้เลยตั้งแต่ 16 ส.ค. 16:01 -> **วันนี้ไม่มีโพสต์วิดีโอเลยทุกช่อง** ไม่มีไฟล์ผิดหลุดออกไป
- ไม่มีไฟล์ .mp4 ใน `reels/` หรือ `_vidout/` ถูกแก้เลยทั้งวัน -> ไม่ต้องสแกนลายน้ำซ้ำ ใช้ผลรอบ 07:00 ได้
- `WATERMARK-ALERT.md` ยังเป็นไฟล์เดิมเวลา 07:03 ไม่มีรอบใหม่มาเขียนทับ

### หลักฐานใหม่ที่รอบก่อนยังไม่ได้ทำ (ตรวจไฟล์จริงรอบนี้)

- `reels/2026-08-16_b4-p01.mp4` -> ffprobe = **h264 1080x1920** (ไม่ใช่ 720x1280 ไม่ใช่คลิป plain)
- sha256 ของไฟล์บนดิสก์ = **D0A07323...8DAC** **ตรงกับ receipt แบบเป๊ะทุกไบต์**
  -> ยืนยันว่าไฟล์ยังเป็นตัวเดิมที่ผ่าน QA **ไม่ถูกสลับ** เป็นตัว plain หรือตัวที่มีลายน้ำ
- คีย์ใน receipt `automation-log/media-qa/b4-p01-video.json`: schema_version, asset, sha256,
  media_type, reviewed_at, media_origin, novelty_review, watermark
  -> **ไม่มีคีย์ `audio_review`** = ตรงกับเหตุ FAIL ที่ guard รายงานพอดี
- `watermark.visual_review.status` = **PASS** (ไม่พบลายน้ำของผู้ให้บริการ)

**สรุป:** ไม่มีอะไรใหม่ต้องแก้ วิธีแก้ยังเป็นข้อ 1-4 ด้านบนเหมือนเดิม
(ให้มนุษย์ฟังเสียงแล้วเติมบล็อก `audio_review` ลง receipt) ยังไม่มีอะไรถูกโพสต์ จึงไม่ต้องลบหรืออัปใหม่ที่ช่องใด
