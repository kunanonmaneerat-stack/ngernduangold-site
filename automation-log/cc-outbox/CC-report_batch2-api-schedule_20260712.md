# CC report — batch2 API schedule (FB 21–26 + IG 20–26) · 12 ก.ค. ค่ำ (commits 4f8f510 + ea7d961)

## 🛑 BLOCKED-ON-TOKEN — ตามคำสั่ง "ติด token = หยุด รายงาน ห้าม retry"
เช็คครบ 3 แหล่ง ไม่มี token ใช้ได้เลย:
1. **GitHub Actions secrets = ว่างเปล่า** (`gh secret list` ไม่มีรายการใดเลย)
2. fb-pages MCP token = ตาย (OAuth code 190 — ยืนยันซ้ำ)
3. `secrets/meta-token.json` = placeholder (token 43 ตัวอักษร parse ไม่ได้ — ของจริงยาว 150+)

**Token ที่ต้องได้จากเจ้าของ (ระบุชัดตาม order):**
| ช่อง | secret | ใช้กับ | วิธีได้ |
|---|---|---|---|
| IG 20–26 | `IG_ACCESS_TOKEN` + `IG_USER_ID` (GitHub secrets) | pipeline ig-reels เดิม | runbook IG §1 (~30 นาที) |
| FB 21–26 | `FB_PAGE_ID` + `FB_PAGE_TOKEN` (GitHub secrets **และ/หรือ** ใส่ env ให้ CC รัน local 1 ครั้ง) | schedule_fb_batch2.py | runbook §FB (app เดียวกัน +3 permissions) |

## ตาราง วันที่ × ช่อง (สถานะปัจจุบัน — verify จริง ไม่เดา)
| วันที่ | TikTok | IG | FB |
|---|---|---|---|
| 13–19 | ✅ **scheduled 19:00 ครบ (verify บน Studio จริง)** | ⏳ รอ token → pipeline ยิงเองรายวัน 19:00 | 13–18 = feed text รอ token (fb-feed) |
| 20 | scheduled ✅ | ⏳ รอ token | 🔒 **MANUAL แล้ว — ไม่ถูกแตะ + hard-guard ในโค้ด/manifest** |
| 21–26 | scheduled ✅ | ⏳ รอ token | ⏳ รอ token → รัน scheduler 1 ครั้งจบ (dry-run ผ่านแล้ว 6/6) |

## สิ่งที่ทำเสร็จรอบนี้ (token-less ครบทุกข้อของ order)
1. **ยืนยัน FB วันที่ 20 ไม่ถูกแตะ**: hard-excluded ในโค้ด (assert) + `posted.fb[20]="manual...DO NOT re-schedule"` ใน manifest + dup-guard ชั้นสอง query `GET /{page}/scheduled_posts` ก่อนตั้งทุกอัน
2. **`schedule_fb_batch2.py`** พร้อมยิง: `/videos` + `file_url`(hosted) + `scheduled_publish_time`=19:00+07 + `published=false` · caption จาก manifest · DRY ผ่าน 6/6 (timestamps ถูก) · error = หยุดทันทีไม่ retry
3. **posted-tracking wired + backfill แบบมีหลักฐาน**: `posted.tiktok[13–19]` = scheduled (เปิด Studio ดูจริงทีละวัน) · IG/FB 13–19 คง null ตามจริง (pipeline ยัง soft-skip เพราะไม่มี token — **ขอแก้ premise ของ order ที่ว่า "13–19 live ครบ 5 ช่อง": จริงเฉพาะ TikTok**) · dedup ฝั่ง publisher ครบ 11–19
4. **captions.fb 20–26 populated** ใน manifest (เดิมว่าง — จำเป็นต้องเติมเพื่อใช้ตาม order; รูปแบบ hook+disclaimer+hashtags **ไม่มี URL ในบอดี้** ตามกติกา reach · ลิงก์คอมเมนต์แรก schedule ล่วงหน้าไม่ได้ — เป็นงานมือ/Cowork หลังโพสต์ขึ้น) · validator PASS 16/16
5. **IG cron → 19:00TH** (12:00 UTC) ตาม order "ทุกอัน 19:00" · push แบบ 0 build (workflow commit อยู่ใต้ skip-path HEAD)

## ทันทีที่ token มา
- IG: ใส่ 2 secrets → นัดถัดไป 19:00 ยิงเอง (20–26 ครบอัตโนมัติ + dedup กันซ้ำ)
- FB: ใส่ 2 secrets แล้วสั่ง CC "รัน FB scheduler จริง" → `DRY_RUN=0` 1 ครั้ง = ตั้งครบ 21–26 + อัปเดต manifest อัตโนมัติ

---
## REFI UPGRADE APPLIED (16 ก.ค. · commit 4d15b7b — สเปกอนุมัติแล้ว) ✅ LIVE
- **โหมดใหม่ "ไม่รู้ดอกใหม่ — ลองช่วงสมมติ"**: กรอก 3 ตัวเลขจากใบแจ้งหนี้ (ยอดคงเหลือ/งวดที่เหลือ/ค่างวด) → derive ต้นทุนดอกปัจจุบันด้วย bisection ฝั่ง client → slider 3 ระดับ (นิดหน่อย/ปานกลาง/มาก) โชว์**ช่วงประหยัด+ช่วงค่างวดใหม่เป็นบาท ไม่มีเลขดอกเบี้ยใด ๆ** + คำเตือน "ได้ใบเสนอจริงค่อยใช้โหมดแม่นสุด"
- **Sticky CTA** (option ก ตามอนุมัติ): 📊 /debt-consolidation-2026 (หน้ากลาง — ไม่มี atth ตรง) + 💬 LINE OA — โผล่หลังได้ผลลัพธ์ทั้งสองโหมด
- **GA events**: refi_result_view (mode: exact/range) + refi_slider_change (band) — guard typeof gtag
- **Gates ครบ**: **F3 regression ผ่านทั้ง local และ LIVE = +36,259 บาท** (สูตรเดิมไม่ถูกแตะ, assert ใน patch) · smoke 67/67 · link_check 0 · affiliate 17/17 (ไม่เพิ่มลิงก์) · ไม่มีเลข % ใน copy ใหม่ (assert+live check) · blob UFFFD=0 · mobile 375px ไม่ overflow · build 1 ครั้ง commit เดียว = HEAD
- Live sanity range mode: 150k/30งวด/6,500 → นิดหน่อย ~4.8–9.6k · มาก ~16.5–23.4k บาท (สมเหตุผล เพิ่มตามระดับ)
