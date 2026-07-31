# ⚠️ VIDEO-POST VERIFY FAIL — 2026-06-27 (auditor: Cowork ngernduangold-video-post-verify)

ผล: **FAIL** — โพสต์วิดีโอวันนี้ใช้ "ไฟล์ผิดเวอร์ชัน" (คลิป plain 720x1280) แทน reel ที่ถูก (1080x1920)
เหตุ: การลงมือเองนอกไพป์ไลน์ผ่าน browser (source="cowork-manual-browser") ข้าม pre-publish gate ของ CC
ตรวจแบบชี้ขาดด้วย ffprobe + เทียบเฟรมภาพ (ดู _verify_frames/ ใน outputs)

## สรุปต่อโพสต์
| ช่อง | โพสต์ | ไฟล์ที่ลงจริง | ความละเอียด | ผล |
|------|-------|----------------|--------------|-----|
| YouTube Shorts | M2TyHVnWkKU (เช็กเครดิตบูโรเองได้ฟรี...) | automation-log/video-out/credit-score/01.mp4 | 720x1280 | ❌ FAIL |
| TikTok | debt-consolidate (~12:00 ICT) | automation-log/video-out/debt-consolidate/01.mp4 | 720x1280 | ❌ FAIL |
| Instagram | รูปการ์ด /p/DaFi8CdIKY7/ (ไม่ใช่วิดีโอ) | (ภาพนิ่ง) | n/a | ⚠️ ไม่ใช่ไฟล์ผิด แต่ reel เย็นตกคิว ไม่ลง IG |
| Facebook | reel เย็น 20:00 "เงินเดือนเข้าวันเดียว หายวันที่สอง?" | ยืนยันไม่ได้ (Meta MCP เต็มลิมิต free) | UNVERIFIED | ⚠️ ต้องตาเปล่ายืนยัน 1080x1920 |

## หลักฐานชี้ขาด (deterministic)
- ตัวที่ถูก: _vidout/reel_debt-consolidation-2026.mp4 = 1080x1920 (มีฮุกขึ้นจอ + CTA "ลิงก์ในไบโอ" + แถบ disclaimer + แฮนเดิล @ngernduangold)
- ตัวที่ลงจริง: video-out/debt-consolidate/01.mp4 = 720x1280 (Veo ดิบ ไม่มีฮุก/CTA/disclaimer/แฮนเดิล) — เฟรมเทียบยืนยันแล้ว
- video-out/<topic>/0N.mp4 ทุกไฟล์ = 720x1280 (เป็นไฟล์เรนเดอร์ดิบ เทียบเท่าตัว plain ใน media/clips-web) → ห้ามใช้โพสต์
- ledger: post-ledger.jsonl 2026-06-27 มี 2 entry (tiktok+yt) source=video-out/... ไม่ใช่ _vidout/reel_* → ผิดกฎ SPEC ข้อ YT

## วิธีแก้ (อ่านอย่างเดียว auditor ไม่แตะของจริง — Non/CC ทำต่อ)
1) YouTube: ลบ/แทนที่ Short M2TyHVnWkKU → อัปใหม่ด้วย _vidout/reel_credit-bureau-check-2026.mp4 (1080x1920)
   ใช้ title/description จาก _youtube_shorts_PACK_20260626.md (คงลิงก์บทความ + disclaimer + affiliate disclosure)
2) TikTok: ลบโพสต์ debt-consolidate วันนี้ → อัปใหม่ด้วย _vidout/reel_debt-consolidation-2026.mp4 (1080x1920)
3) Instagram: reel เย็น 27 มิ.ย. ตกคิว (reel ล่าสุดยังเป็น DaDM37miWE5 ของ 26 มิ.ย.) → retry reel ตัวเดียวกับ FB เย็นนี้ ด้วยไฟล์ _vidout/reel_*
4) Facebook: ตาเปล่ายืนยัน reel 20:00 ว่าเป็น 1080x1920 มีฮุก+CTA+disclosure (ไม่ใช่ 720 plain) — ถ้า plain ให้แทนที่
5) แก้รากเหง้า: ห้ามโพสต์จาก automation-log/video-out/<topic>/0N.mp4 (เป็นไฟล์ดิบ 720) — โพสต์ได้เฉพาะ _vidout/reel_*.mp4 (1080x1920) เท่านั้น
   ข้อเสนอ: อัปเดต _video_post_verify_SPEC.md เพิ่ม video-out/ เข้า blacklist (ตอนนี้ระบุแค่ media/clips-web)

## กันโพสต์ซ้ำ (เกี่ยวเนื่อง)
post-plan 28 มิ.ย. entry แรกใช้ video-out/debt-consolidate/01.mp4 อีก → TikTok จะซ้ำ + ยังเป็นไฟล์ 720 ผิด
→ ดูรายละเอียดใน _cc_task_dedup_tiktok_check_ig_reel_20260627.md (TASK A/B)

---
auditor run: 2026-06-27 (Cowork, read-only) · ไม่มีการเขียน "ok" ลง latest.md เพราะมี FAIL
