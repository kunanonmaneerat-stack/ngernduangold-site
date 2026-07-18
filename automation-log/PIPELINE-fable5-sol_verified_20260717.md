# คู่มือ Fable5 (สมอง) + GPT-5.6 Sol (มือ) — ผลตรวจยันกับ docs ทางการ (17 ก.ค. 2026)

ที่มา: เจ้าของส่งคู่มือ implementation 3-stage (Fable5 วางแผน → Sol รัน → Fable5 QA) · Cowork ตรวจกับ platform.claude.com/docs + developers.openai.com ก่อนรับใช้ · ตัวคู่มือเต็ม (โค้ด python) อยู่ในแชต 17 ก.ค.

## ผลตรวจ: แม่นเกือบทั้งหมด — ยืนยันถูกต้อง
- Fable5 ราคา $10/$50 ต่อ MTok (ไม่มีราคา introductory — ตัว $2/$10 ที่เห็นในบางแหล่งคือ Sonnet 5)
- ไม่มี budget_tokens · adaptive thinking เป็นโหมดเดียว · คุมความลึกด้วย `output_config.effort` — ตรงตามคู่มือ
- cache: write 5 นาที $12.50 (1.25x) · cache hit $1/MTok (0.1x) · อายุ 5 นาที — ตรง
- Batch API ลด 50%: Fable5 = $5/$25 — ตรง · ส่วนลด batch+cache ซ้อนกันได้
- โบนัสที่คู่มือไม่ได้บอก: Fable5 ได้ 1M context ราคาเดียว (ไม่มี surcharge ยาว)
- Sol $5/$30 · **cost cliff 272K ตรงเป๊ะ**: input >272K → คิด 2x input / 1.5x output ($10/$45) กับ**ทั้ง request**
- Sol cache: write 1.25x · read ลด 90%

## จุดแก้/ระวัง 3 จุดก่อน build จริง
1. **effort มีระดับ `xhigh`** สูงกว่า high (คู่มือบอก high คือสูงสุด — ไม่ใช่) · docs แนะสงวน xhigh ไว้งานหินจริง งานทั่วไป high พอ
2. **Fable5 ไม่รองรับ temperature / top_p / prefill** — ใส่ไปจะ error อย่าเผลอยกโค้ดเก่ามาใช้
3. **ยังยันไม่ได้ 2 claim**: (a) alias `"gpt-5.6"` ชี้ Sol (b) "refusal → auto fallback Opus 4.8" — ข้อ (b) ไม่น่าใช่พฤติกรรมระดับ API ให้เขียน handle refusal เองเสมอ · เช็ค docs สดตอน deploy

## การใช้กับงาน ngernduangold (ตัดสินใจ 17 ก.ค.)
- **ห้ามเอา pipeline API นี้มาแทน flow คอนเทนต์ปัจจุบัน** — เราจ่าย seat เหมาอยู่แล้ว (Cowork = Fable5 ผ่านแอป · Codex CLI = gpt-5.6-terra ผ่านแพลน ChatGPT) ย้ายไป API = เริ่มจ่ายต่อ token ทันทีโดยงานไม่ดีขึ้น
- pipeline นี้เหมาะกับ**โปรเจกต์ dev ที่ต้องรันแบบโปรแกรม** (บอท/โปรดักต์อัตโนมัติของเจ้าของ) — ใช้ไฟล์นี้เป็น reference ตอน build
- หลักการที่รับเข้าระบบเราทันที: **"สมองห้ามอยู่ใน loop"** → เขียนเข้า CODEX-DELEGATION.md แล้ว (พิสูจน์เองก่อนหน้า: Codex รอบ 7 ผม poll คั่นกลาง = 3 ชม. · รอบ 8 สั่งจบ-รอ-ตรวจครั้งเดียว = 2 นาที)

แหล่ง: platform.claude.com/docs/en/about-claude/pricing (fetch ตรง 17 ก.ค.) · docs models/introducing-claude-fable-5 + developers.openai.com/api/docs (ผ่าน search)
