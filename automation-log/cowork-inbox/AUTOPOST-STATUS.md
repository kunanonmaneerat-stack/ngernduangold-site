# AUTOPOST STATUS — social pipeline · อัปเดต 11 ก.ค. 2026 22:35TH

## Schedulers (ทั้งคู่ ENABLED)
| ช่อง | กลไก | นัดถัดไป (เวลาไทย) | โหมดตอนนี้ |
|---|---|---|---|
| IG Reels | GitHub Action `ig-reels` (cron 13:00 UTC) | **12 ก.ค. 20:00** | LIVE-ready แต่ token ยังไม่มา → **soft-skip + alert** (ไม่แดง) |
| TikTok | Windows Task `ngern-tiktok-daily` (NANON) | **12 ก.ค. 19:00** | **DRY** (ยังไม่ --login) — เตรียมถึงหน้าโพสต์+screenshot ไม่กด Post |

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
