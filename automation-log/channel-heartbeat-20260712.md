# Channel Heartbeat — 7 ช่อง (12 ก.ค. 2026, 21:00)
> ตรวจ+รายงานอย่างเดียว ไม่โพสต์ · ที่มา: post-ledger.jsonl, cowork-inbox/threads-ops-20260712 (09:04) · today-post-2026-07-12 · _pinterest_RUN_20260712 · _auditor_report_20260712 (20:00) · reel-repost-tracker · POSTING-POLICY_20260702 · Meta MCP (Pipeboard) Free = เกินโควตา → FB/IG สดยืนยันไม่ได้ ใช้ delivery log

| ช่อง | cadence คาดหวัง | ล่าสุด / วันนี้ | สถานะ |
|---|---|---|---|
| Threads | ทุกวัน 1/วัน | ✅ วันนี้ 12 ก.ค. 09:04 (ธีมจำนำทะเบียน 407 ตัว · ผ่าน qa_gate/comply_gate · verify live "1 นาที") | ✅ ตามแผน* |
| Pantip | ทุกวัน (FROZEN) | 0 วันนี้ — โดยตั้งใจ · thaw ≥16 ก.ค. เหลือ 4 วัน · auditor ยืนยัน freeze เคารพ | 💤 ดอร์มันต์ (ตั้งใจ) |
| Pinterest | 2-3/สัปดาห์ | ✅ วันนี้ 3 พิน 11:25 (weekly, บอร์ดถูก, qa_gate OK 0/5, ลิงก์ own-domain) | ✅ ตามแผน |
| TikTok | ต่ำ/manual | โพสต์ล่าสุด 10 ก.ค. 09:01 (title-loan) ~2 วัน · คลิปถัดไป debt-consolidate 01 คิว จ 13/07 (เจ้าของกดเอง) | ✅ ตามแผน (ไม่ bot) |
| Facebook | ไม่รายวัน | ล่าสุด ~10 ก.ค. (debt-calculator) · healthy per delivery log · live ❓ (Meta free quota) | ✅ ตามแผน (live ❓) |
| Instagram | ไม่รายวัน | ล่าสุด 10 ก.ค. (title-loan reel LIVE) · auto-API ยัง dormant + 404 tl01b ค้าง | ✅ ตามแผน (auto ❓) |
| YouTube | รายวัน (ปัจจุบัน) | คิวเต็ม 6–19 ก.ค. (pipeline 11-13 & 15-19) · 12 ก.ค. อยู่ในหน้าต่างคิว · batch-day stage 7 คลิป 13-19 | ✅ ตามแผน |

สรุป: ✅ 6 · 💤 1 (Pantip ตั้งใจ) · ⚠️ 0 — สุขภาพดี เท่ารอบก่อน (11 ก.ค. = 6✅/1💤/0⚠️)

## ช่องที่ต้องสนใจ
1. Threads* — โพสต์ขึ้นจริง (verify live) แต่ text_hash 005a8a09… **ไม่พบใน post-ledger.jsonl** (grep=0) ทั้งที่ proof-of-run เขียน appended=True. โพสต์ไม่ได้หาย แต่ ledger อาจไม่ persist → text-dedup รอบหน้าอ้าง ledger ได้ไม่ครบ. เจ้าของ/CC: เช็ก record_text_post ว่าเขียนลงไฟล์จริงไหม.
2. IG — โพสต์ 10 ก.ค. OK แต่ระบบ auto-API ยัง DORMANT (รอ secrets) + reel 12 ก.ค. (tl01b) HTTP 404 (ชื่อไฟล์เพี้ยน). ต้องแก้ก่อนเปิด auto — runbook: §1 secrets → §2 ทดสอบ 1 คลิป → แก้ URL 404.
3. TikTok — manual/human-in-loop (ห้าม bot ถูกต้อง) · 2 วันจากโพสต์ล่าสุด ยังไม่เข้าเกณฑ์เตือน (>10 วัน) · debt-consolidate 01 รอเจ้าของกด จ 13/07 19:00.
4. FB — live ❓ (Meta/Pipeboard Free เกินโควตา) · content healthy ~10 ก.ค. · ถ้าอยากยืนยันสดต้องใช้ token/Pro หรือเช็กมือ.
5. Pantip 💤 — freeze เหลือ 4 วัน (16 ก.ค.) · starter queue staged · หมายเหตุ auditor: draft pantip 07-12 เพี้ยน (model scratchpad รั่ว) แต่โพสต์ 0 = ไม่มี harm · ห้ามโพสต์/แนะนำโพสต์.

บริบท (นอกสโคป): first-signal ยัง 0 conv จากโซเชียล · GA4 วันนี้ affiliate_click=72, conversion หลักมาจาก direct(42)/fb(19)/ig(6)/pantip(4) · reach ยังเป็นคอขวด.
