# AUTOPOST STATUS — social pipeline · อัปเดต 11 ก.ค. 2026 22:35TH

## Schedulers (ทั้งคู่ ENABLED)
| ช่อง | กลไก | นัดถัดไป (เวลาไทย) | โหมดตอนนี้ |
|---|---|---|---|
| IG Reels | GitHub Action `ig-reels` (cron 13:00 UTC) | **12 ก.ค. 20:00** | LIVE-ready แต่ token ยังไม่มา → **soft-skip + alert** (ไม่แดง) |
| TikTok | Windows Task `ngern-tiktok-daily` (NANON) | — | **Disabled ชั่วคราว** (login ติด rate-limit — เส้นทาง = semi-auto ผ่าน browser pane / ลอง QR ใหม่พรุ่งนี้) |
| FB Page | GitHub Action `fb-feed` (cron 08:00 UTC) | **12 ก.ค. 15:00** | soft-skip + alert จนกว่ามี FB_PAGE_ID/FB_PAGE_TOKEN · feed map 12–18 พร้อม 7 โพสต์ |

## พฤติกรรมช่วงรอปลดล็อก (พิสูจน์แล้วทุกเส้น 11 ก.ค.)
- IG ไม่มี token → เขียน `IG-PUBLISH-SKIP.md` + จบเขียว · พอ secrets มา นัดถัดไปโพสต์จริงเอง
- วัน 20–26 คลิปยังไม่ render → fail-alert "clip not found / url 404" ชัดเจน ไม่โพสต์มั่ว
- dedup: รันซ้ำวันเดิม = skip ทั้ง 2 ช่อง (ทดสอบด้วย drill state แล้วลบคืน)
- TikTok เลือกคลิป+แคปชันถูกวัน + comply PASS (โหมด --plan ตรวจได้ไม่ต้องเปิดเบราว์เซอร์)

## BLOCKED-ON-OWNER (เรียงตามเวลา — exact steps ท้าย social-autopost/runbook.md)
1. **IG token** (~30 นาที ก่อน 20:00 พรุ่งนี้ = โพสต์แรกพรุ่งนี้เลย)
2. **TikTok --login** + เทส + สลับ task เป็น --live
3. **render batch2** วางที่ reels/batch2/ ก่อน 20 ก.ค.

## FIRST LIVE POST (หลัง prereq): IG — 12 ก.ค. 20:00TH (_final_tl01b จำนำทะเบียน) ถ้า token มาก่อนเวลานัด

## QA ยืนยันก่อนโพสต์จริง (11 ก.ค. 22:45TH — ตามที่ owner สั่ง)
- **ลายน้ำ Google Flow/Veo: 9/9 PASS** (qa_watermark NCC detector, track 0 เฟรมทุกคลิป reels/11-19)
- **ข้อมูลกำกับตามที่ Cowork กำหนด: 16/16 วัน PASS** (disclaimer+ผลิตด้วย AI ทั้ง IG/TikTok caption · มีลิงก์พันธมิตร ตรง affiliate flag · ไม่มี bare % · TikTok ไม่มี URL ในโพสต์)
- TikTok task = Disabled ชั่วคราว (login ติด rate-limit) — เส้นทางทดสอบ = semi-auto ผ่าน browser pane ที่ owner login ไว้

## TikTok BREAKTHROUGH (11 ก.ค. 23:35TH)
- **GATE ทดสอบ 1 คลิปจริง = ผ่าน**: owner โพสต์ kp04 ขึ้น live (11 ก.ค. 23:29) + **ตั้งเวลา tl01b 12 ก.ค. 19:00** ผ่าน TikTok Studio native scheduler — แคปชันตรง sheet อนุมัติครบทุกบรรทัดทั้งคู่ (verify บน Studio จริง)
- เส้นทาง TikTok ที่ใช้จริง = **native schedule ผ่าน Studio** (เสถียรกว่า Playwright, ไม่มีประเด็น anti-bot) — dedup 11-12 บันทึกแล้วกัน Playwright ยิงซ้ำ
- ชีทตั้งเวลา 13–19 รวดเดียว: `cowork-inbox/TIKTOK-SCHEDULE-SHEET_13-19jul.md` (path+แคปชันพร้อมก๊อป ~10 นาทีครบสัปดาห์)
- ⚠️ พบโพสต์เก่า 1 ตัว 'หนี้บัตรหลายใบ จ่ายขั้นต่ำ...' สถานะ **'อยู่ระหว่างการตรวจสอบ' + เฉพาะฉัน** — ฝาก Cowork ประเมิน (ไม่ใช่โพสต์ของรอบนี้)
