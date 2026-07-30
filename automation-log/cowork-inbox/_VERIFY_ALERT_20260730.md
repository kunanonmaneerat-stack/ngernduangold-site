# 🚨 VIDEO-POST VERIFY — FAIL (30 ก.ค. 2026) · **อัปเดต 21:45 = ยกระดับเป็น WATERMARK FAIL**

> **รอบตรวจ 21:45 (รอบ 2 ของวัน)** — รอบ 21:35 รายงานไว้ว่าไฟล์ที่ post-plan สั่งโพสต์มัน "720x1280 = ตัว plain"
> รอบนี้**สแกนเฟรมจริงตาม SPEC ข้อ 3 (บังคับ)** แล้วพบว่ามัน**มีลายน้ำ Veo ด้วย** → ระดับจาก "ไฟล์ผิด" เป็น **HARD BLOCK**

---

## 🚨 WATERMARK FAIL — ห้ามโพสต์เด็ดขาด (หลักฐานใหม่ รอบ 21:45)

คำสั่งที่รัน:
```
py tiktok-pipeline\src\qa_watermark.py automation-log\video-out\debt-consolidate\0*.mp4 --fps 3
```

| ไฟล์ (ที่ post-plan สั่งโพสต์) | วันที่สั่ง | ffprobe | watermark scan | ผล |
|---|---|---|---|---|
| `video-out/debt-consolidate/01.mp4` | **31 ก.ค.** | 720x1280 ❌ | track **9/30** เฟรม | 🔴 FAIL |
| `video-out/debt-consolidate/02.mp4` | 1 ส.ค. | 720x1280 ❌ | track **29/30** เฟรม | 🔴 FAIL |
| `video-out/debt-consolidate/03.mp4` | 2 ส.ค. | 720x1280 ❌ | track **30/30** เฟรม | 🔴 FAIL |
| `video-out/debt-consolidate/04.mp4` | 3 ส.ค. | 720x1280 ❌ | track **30/30** เฟรม | 🔴 FAIL |
| `video-out/debt-consolidate/05.mp4` | 4 ส.ค. | 720x1280 ❌ | track **30/30** เฟรม | 🔴 FAIL |
| `video-out/save-paycheck/01.mp4` | 5 ส.ค. | 720x1280 ❌ | track **23/30** เฟรม | 🔴 FAIL |

- **exit code = 2 ทุกชุด** → ตาม SPEC ข้อ 3 = ห้ามโพสต์ไฟล์เหล่านี้เด็ดขาด
- ตำแหน่งลายน้ำเหมือนกันทุกไฟล์: `drift[src x571-629 y1131-1189]` = โซนล่างขวา = ลายน้ำ Veo sparkle ตัวเดียวกับที่ทำ 5 IG reel หลุดเมื่อ 9 ก.ค.
- **evidence PNG ที่สร้างรอบนี้** (`automation-log/wm-evidence/`, 30 ก.ค. 21:42):
  `01_f001.png` · `01_f006.png` · `01_f010.png` · `01_f029.png`

### ขอบเขตจริง — กว้างกว่าที่รายงานรอบก่อน
`automation-log/video-out/` **ทั้งคลัง = 36 คลิป 7 หัวข้อ เป็น 720x1280 หมด**
(credit-score / debt-consolidate / emergency-fund / first-card / refinance / save-paycheck / title-loan — สร้าง 22 มิ.ย. ทั้งหมด)
และ post-plan.json ดึงจากคลังนี้**ยาวถึง 9 ส.ค.** → ไม่ใช่ปัญหาเฉพาะไฟล์เดียว

### ⚠ สิ่งที่ต้องทำทันที
1. **อย่าโพสต์ตามการ์ด `today-post-*.md` เด็ดขาด** — ไฟล์มีทั้งความชัดผิดและลายน้ำ
2. ยึด `reels/schedule.json` + `.system_control/content_manifest.json` เป็นคิวจริง (31 ก.ค. = **b3-05**, ไฟล์ `reels/2026-07-31_b3-05.mp4`)
3. แก้ `pipeline/daily_post_reminder.py` ให้อ่านจาก manifest/schedule — ห้ามอ่าน post-plan.json
4. เสนอ: **ย้าย `automation-log/video-out/` ทั้งโฟลเดอร์เข้า quarantine** (เช่น `_quarantine_watermarked/`) กันหยิบไปโพสต์โดยไม่ตั้งใจ
5. เพิ่ม qa_watermark เข้า pre-publish gate ของทุกช่อง (ตอนนี้ตรวจเฉพาะตอน verify รายวัน)

### ✅ ยังไม่มีคลิปผิดหลุดออกไป
post-ledger ไม่มี entry ที่ใช้ไฟล์เหล่านี้เลย · วิดีโอที่เผยแพร่จริงวันนี้มีตัวเดียว = YouTube b3-01 ที่ PASS ทุกเกณฑ์ (ดูด้านล่าง)
ความเสี่ยงคือ **คืนนี้/พรุ่งนี้ถ้าเจ้าของทำตามการ์ด**

### ♻ ตรวจซ้ำรอบนี้: คลิป batch3 ที่จะโพสต์จริง — สะอาดทั้ง 7 ตัว
```
b3-01 PASS 0/74   b3-05 PASS 0/66   b3-02 PASS 0/61   b3-06 PASS 0/65
b3-03 PASS 0/63   b3-07 PASS 0/66   b3-04 PASS 0/71     exit 0 ทุกตัว
```
ffprobe = 1080x1920 h264 ครบ 7/7 · ไม่มี evidence PNG ใหม่จากกลุ่มนี้เลย
grep `clips-web`/`720x1280` ใน schedule.json + content_manifest.json = **0 hit**

---

<!-- ===== ด้านล่างนี้ = รายงานรอบ 21:35 เก็บไว้ครบ ===== -->

# ⚠️ VIDEO-POST VERIFY — FAIL 1 รายการ (30 ก.ค. 2026)

**สรุป:** คลิปที่ "โพสต์จริง" วันนี้ถูกต้อง 100% (YouTube b3-01) — แต่ **ใบสั่งโพสต์ที่ส่งให้เจ้าของกดเอง ชี้ไปที่ไฟล์ผิด**
ยังไม่มีคลิปผิดหลุดออกไป (ไม่มี entry ใน post-ledger) แต่ถ้าเจ้าของทำตามใบสั่งพรุ่งนี้ = โพสต์ผิดทันที

---

## 🔴 FAIL — post-plan.json / cowork-inbox สั่งโพสต์คลิป plain 720x1280

| หัวข้อ | รายละเอียด |
|---|---|
| ไฟล์เตือน | `automation-log/cowork-inbox/today-post-2026-07-30.md` (สร้าง 07:15 วันนี้) |
| ต้นเหตุ | `automation-log/post-plan.json` (`updated: 20260730-0715`) |
| ตัวสร้าง | `pipeline/daily_post_reminder.py` — อ่าน post-plan.json อย่างเดียว ไม่ได้อ่าน manifest/schedule |
| ไฟล์ที่สั่งให้โพสต์ | `automation-log/video-out/debt-consolidate/01.mp4` |
| ffprobe ผลจริง | **720x1280** = ตรงนิยาม "ตัว plain ที่ผิด" ใน SPEC เป๊ะ (ที่ถูกต้อง = 1080x1920) |
| อายุไฟล์ | สร้าง 22 มิ.ย. — คนละสายกับ pipeline batch3 ที่ใช้อยู่ |
| path ในไฟล์ | `/sessions/zealous-adoring-ride/mnt/...` = session mount เก่า resolve ไม่ได้แล้ว |
| หัวข้อ | "หนี้บัตร/รวมหนี้" — **ไม่ตรง** กับคิวจริง 31 ก.ค. (b3-05 เงินเดือน 30,000 วงเงินบัตร) |
| ขอบเขต | ไม่ใช่ของวันนี้วันเดียว — ซ้ำเหมือนกันทุกวันตั้งแต่ 20-30 ก.ค. (11 วันติด) และวางแผนล่วงหน้าถึง 5 ส.ค. |

**ทำไมรอบก่อนไม่เจอ:** verify รอบเดิมตรวจแค่ `schedule.json` / `content_manifest.json` / `content_map.json` (ซึ่งถูกต้องหมด) — ไม่เคยตรวจ `post-plan.json` กับ `cowork-inbox/today-post-*.md` ซึ่งเป็นเส้นที่ส่งถึงมือคนโดยตรง

### วิธีแก้
1. **อย่าโพสต์ตามการ์ด `today-post-*.md` จนกว่าจะแก้** — ยึด `reels/schedule.json` เป็นหลัก
2. แก้ `pipeline/daily_post_reminder.py` ให้อ่านจาก `.system_control/content_manifest.json` (หรือ `reels/schedule.json`) แทน `post-plan.json`
3. ถ้ายังจะใช้ post-plan.json ต่อ ให้ regenerate ใหม่จาก manifest + เปลี่ยน path เป็น repo-relative (ห้าม absolute `/sessions/...`)
4. เพิ่ม `post-plan.json` + `cowork-inbox/today-post-*.md` เข้าเป้าหมายของ verify agent (ตอนนี้ตรวจแล้วในรอบนี้)

### คิวจริงที่ถูกต้อง (จาก BATCH3-RESCUE_20260730)
| วันที่ | คลิป | ไฟล์ |
|---|---|---|
| 31 ก.ค. | b3-05 | `reels/2026-07-31_b3-05.mp4` |
| 1 ส.ค. | b3-02 | `reels/2026-07-28_b3-02.mp4` |
| 2 ส.ค. | b3-06 | `reels/2026-08-01_b3-06.mp4` |
| 3 ส.ค. | b3-03 | `reels/2026-07-29_b3-03.mp4` |
| 4 ส.ค. | b3-07 | `reels/2026-08-02_b3-07.mp4` |
| 5 ส.ค. | b3-04 | `reels/2026-07-30_b3-04.mp4` |

---

## ✅ PASS — YouTube (โพสต์จริงวันนี้ ช่องเดียว)

video `fxCEKQ2Q8oE` · b3-01 "รถยังผ่อนไม่หมดจำนำได้ไหม" · 20:59

| เกณฑ์ SPEC | ผล |
|---|---|
| source path | `reels/2026-07-27_b3-01.mp4` — ไม่ใช่ clips-web / media\clips ดิบ ✅ |
| ffprobe | 1080x1920 · h264 · 24fps · aac · 24.5 วิ ✅ |
| md5 ตรงต้นฉบับ | `c614fcc9…48e9` = `_vidout/b3-01_autotest.mp4` เป๊ะ ✅ |
| watermark frame-scan fps3 | **PASS 0/74 เฟรม** · exit 0 · ไม่มี evidence PNG ใหม่ ✅ |
| ฮุกขึ้นจอ | "รถยังผ่อนไม่หมด? / ต้องใช้เงินด่วน แต่ไม่อยากขายรถ?" + @ngernduangold + CTA ลิงก์ในไบโอ ✅ |
| topic match | manifest / schedule.json / content_map.json ชี้ไฟล์เดียวกันทั้ง 3 ที่ ไม่มี cross-wire ✅ |
| description | ลิงก์ `ngernduangold.com/car-pawn-not-paid-off?utm_source=yt` + disclaimer การศึกษา + ผลิตด้วย AI ✅ |
| affiliate disclosure | `affiliate=false` ถูกต้อง — หน้าปลายทางมี atth.me = 0 ตัวจริง (ตรวจแล้ว) ✅ |
| channel | uploader hardcode `UCVuqb7l5rJ4Q7PUKSIgsL4w` ✅ |

**เสี่ยงชี้ผิดไฟล์ที่รอดมาได้:** มีไฟล์ชื่อ `reels/2026-07-30_b3-04.mp4` (ชื่อไฟล์ตรงกับวันนี้) แต่คิวจริงวันนี้คือ b3-01 — ตรวจแล้วทั้ง manifest/schedule/content_map ชี้ b3-01 ถูกต้อง ไม่มีการสลับ

---

## ⏭️ N/A — ไม่ใช่ความผิดพลาดเรื่องไฟล์

| ช่อง | สถานะ |
|---|---|
| Instagram | พักตามแผนถึง 25 ส.ค. (CHANNEL-DECISION_20260725) — ไม่มีโพสต์ = ปกติ |
| Facebook | ไม่มีโพสต์วิดีโอวันนี้ใน ledger — เป็นปัญหา "ส่งของไม่ออก" ของ delivery-heartbeat ไม่ใช่ไฟล์ผิด |
| Threads | 19:11 ล้มเหลว "Claude in Chrome ไม่เชื่อมต่อ" — ไม่มีอะไรถูกเผยแพร่ = ไม่มีความเสี่ยงไฟล์ผิด |
| TikTok | ไม่มี entry ใน ledger (0 ครั้งใน 28 วัน) |

---

## 🔍 ตรวจเชิงรุก — คลิป batch3 ทั้ง 7 ตัวที่จะโพสต์ถึง 5 ส.ค.

watermark frame-scan `--fps 3` **PASS ทุกตัว exit 0** · ไม่มี evidence PNG ใหม่เลย (0 ไฟล์)

```
b3-01  0/74 เฟรม   1080x1920 h264 24fps aac 24.5s
b3-05  0/66 เฟรม   1080x1920 h264 24fps aac 22.0s
b3-02  0/61 เฟรม   1080x1920 h264 24fps aac 20.3s
b3-06  0/65 เฟรม   1080x1920 h264 24fps aac 21.7s
b3-03  0/63 เฟรม   1080x1920 h264 24fps aac 21.0s
b3-07  0/66 เฟรม   1080x1920 h264 24fps aac 22.0s
b3-04  0/71 เฟรม   1080x1920 h264 24fps aac 23.5s
```
staging เก่า `_vidout/clean/` สุ่มตรวจ 2 ตัว = PASS 0/60 ทั้งคู่
grep หา `clips-web` / `720x1280` ใน schedule.json + content_manifest.json + content_map.json = **0 hit**

---

## 📌 ข้อสังเกตเล็กน้อย (ไม่ block)

1. **disclosure บนจอ vs ในแคปชัน ไม่ตรงกัน** — ตัวอักษรที่เบิร์นในคลิป b3-01 เขียน "มีลิงก์พันธมิตร" แต่ manifest ตั้ง `affiliate=false` และแคปชันไม่มีบรรทัดนั้น เป็นการ disclose เกิน (ปลอดภัยกว่า ไม่ผิดกฎ) แต่ควรทำ overlay ให้ตรงกับ flag ในรอบผลิตหน้า
2. **Meta MCP ใช้ไม่ได้ต่อเนื่องเป็นรอบที่ 7** — `get_instagram_posts` / `get_facebook_posts` คืน `Failed to fetch pages: Bad Request` (token เพจถูกเพิกถอนตั้งแต่ 18 ก.ค.) จึงตรวจ IG/FB จาก ledger + manifest แทน pixel-check จริง
3. **Telegram ส่งไม่ได้จากรอบนี้** — creds อยู่ที่ `C:\Users\nL_ku\ga4-admin\telegram.env` ซึ่งอยู่นอก folder ที่ agent เข้าถึงได้ → ใช้ไฟล์เตือน + cowork-inbox แทนตามที่ SPEC กำหนดไว้เป็น fallback
4. **SPEC ยังล้าสมัย** (ค้างมาตั้งแต่ 20 ก.ค.) — `_video_post_verify_SPEC.md` ยังระบุแค่ `_vidout\reel_*` แต่ของจริงโพสต์จาก `reels/` ควรอัปเดต SPEC + source-gate ให้ตรงของจริง

---
*ตรวจ 30 ก.ค. 2026 · อ่านอย่างเดียว ไม่ได้โพสต์/ลบ/แก้อะไร · ตัวเลขทุกตัวจากไฟล์จริง*
