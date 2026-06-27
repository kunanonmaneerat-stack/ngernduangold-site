# CC → Cowork report — 2026-06-27 (dedup TikTok 28 มิ.ย. + IG reel เย็น)

## TASK A — กันโพสซ้ำ TikTok 28 มิ.ย. = DONE (วิธี 1: per-channel dedup record)
สรุป: dedup เป็น "ราย-channel" (dedup_key=sha1(channel|clip_key|date), is_twin ±16 วัน) → ใช้วิธี 1 ตามที่แนะนำ
- บันทึก ledger 2 แถวของโพสต์ที่ Cowork ลงมือเอง (วันจริง 2026-06-27, source="cowork-manual-browser"):
  * tiktok + debt (debt-consolidate/01) — Cowork ลง TikTok ~12:00
  * yt + score (credit-score/01) — Cowork ลง YT ~11:40 (post_id M2TyHVnWkKU)
  * **ไม่บันทึก ig** เพราะ Cowork ลง IG เป็น "รูป" /p/DaFi8CdIKY7/ (คนละคอนเทนต์กับ debt-consolidate/01)
- แก้ resolver: post_ledger.resolve_clip_key รองรับ dispatcher slug แล้ว (เดิม "debt-consolidate/01.mp4" → None เพราะอ่านแค่ basename "01"). เพิ่ม SLUG_TO_KEY: debt-consolidate→debt, credit-score→score, save-paycheck→save, title-loan→titleloan, emergency-fund→em
- ACCEPTANCE dry-run (post_ledger check, รอบ 28 มิ.ย. debt-consolidate):
  * tiktok → COLLISION (exit 2) = **ไม่ลงซ้ำ** ✓
  * ig → CLEAR (exit 0) = **ลง 01 ได้ปกติ** ✓
  * yt → CLEAR (exit 0) = **ลง 01 ได้ปกติ** ✓
- commit e5d8fab (post_ledger.py + post-ledger.jsonl), pushed → Cowork pull เห็น (ทั้ง 2 ไฟล์ tracked). blob UFFFD=0.
- ⚠️ FLAG credit-score/01 (YT): ในแผนตกราว ~29 ก.ค. (>16 วันจาก 27 มิ.ย.) → อยู่นอกหน้าต่าง dedup ±16 วัน → twin-check จะ "ไม่" บล็อกอัตโนมัติเมื่อถึงวันนั้น (บันทึก yt+score ไว้แล้วเป็น hygiene แต่ window ไม่ครอบ). แนะนำ: ตอน credit-score ใกล้คิวจริง ให้ Cowork ข้าม YT คลิป 01 (หรือ re-check ledger ตอนนั้น). แผนถูก regenerate จาก "พรุ่งนี้" ทุกครั้งที่รัน post_dispatcher อยู่แล้ว วันที่จริงจะเลื่อน
- หมายเหตุกลไก: post-plan.json เป็น "ไกด์ให้คนกดโพสต์เอง" (post_dispatcher/posting_kit/daily_post_reminder = อ่าน/เขียนไฟล์ ไม่ auto-post). dedup ทำงานผ่าน "Cowork รัน post_ledger check ก่อนโพสต์" ตาม POST-PROTOCOL — ตอนนี้ check จะ fail-closed ให้เฉพาะ TikTok ของ debt วันที่ 28

## TASK B — IG reel เย็น 27 มิ.ย. ไม่ลง (FB ลง) = DIAGNOSED, ต้อง owner/Cowork retry
- ROOT CAUSE: **Meta OAuth token ใช้ไม่ได้** — เรียก Meta MCP (เพจแบรนด์) ได้ error: `code 190 "Invalid OAuth access token - Cannot parse access token"`. ตรงกับอาการ "Meta MCP degraded: pipeboard limit + invalid tokens" ที่ heartbeat เคยขึ้น
- ทำไม FB ลงแต่ IG ไม่ลง: รอบโพสต์เย็นรันใน environment ของ Cowork (เครื่อง local ไม่มี log การโพสต์ ~20:00 — cron local มีแค่ delivery-verify 21:13 + heartbeat 08:25 ที่ "ตรวจ" ไม่ใช่ "โพสต์"). FB reel ขึ้นผ่านช่องทางที่ยังเวิร์ก (Cowork browser/หรือ FB path ที่ token ยังใช้ได้) ส่วน IG reel publish ตก เพราะ token invalid / IG ต้องใช้ publish-flow ที่เข้มกว่า
- CC ทำไมไม่ retry เอง: (1) token invalid (code 190) → CC โพสต์/verify ผ่าน Meta MCP ไม่ได้จริง ๆ (2) นโยบาย no-bot-post/anti-shadowban + confirm-before-post → CC ไม่โพสต์โซเชียลเอง
- ทางแก้ (owner/Cowork): (1) refresh Meta/IG access token (pipeboard) ก่อน (นี่คือ blocker) → (2) โพสต์ IG reel ย้อนหลังด้วยมือ ให้ตรงกับ FB reel เย็นนี้ (คลิป+แคปชัน "เงินเดือนเข้าวันเดียว หายวันที่สอง?") — **อย่าโพสต์ FB ซ้ำ** (FB ขึ้นแล้ว)
- สถานะสุดท้ายเย็น 27 มิ.ย.: FB reel = LIVE (Cowork ยืนยัน ~20:05) · IG reel = **FAIL/ตกคิว** (ยังไม่มีรีล 27 มิ.ย.; โพสต์ IG ล่าสุด = รูป /p/DaFi8CdIKY7/) → รอ retry มือ

## guardrails ที่ทำตาม
ไม่ commit ค่าที่ทำให้ลงซ้ำ (ที่ commit = dedup record ที่ "กัน" ซ้ำ) · ไม่โพสต์โซเชียลจาก CC · byte-safe Thai UTF-8 · ยืนยัน blob UFFFD=0
