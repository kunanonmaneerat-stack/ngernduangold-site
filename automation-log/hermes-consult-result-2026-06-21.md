# 🤝 Hermes Consult Result — 21 มิ.ย. 2026 (สั่งจริงผ่าน CLI agent)

## สถานะการสั่ง
- ✅ **สั่ง Hermes agent สำเร็จ** — `hermes chat -q "..." -Q` (one-shot, agent ตัวเดียวกับที่คุยใน Telegram) · runtime 106s · session `20260621_130213_3417f0`
- เหตุที่ไม่ได้ "ผ่าน Telegram" ตรง ๆ: **Telegram Desktop ไม่ได้ติดตั้งบนเครื่อง** + ส่งแทน user ผ่าน bot ไม่ได้ → เลยสั่ง agent ตัวเดียวกันผ่าน CLI
- ⚠️ **คำตอบดิบคุณภาพต่ำ** — โมเดล default `stepfun/step-3.7-flash:free` ออกมาปนภาษา/เพี้ยนหลายช่วง · ผมกลั่นเฉพาะที่ coherent

## ไอเดียจาก Hermes ที่คุ้มเสริมเข้า playbook (กลั่นแล้ว)
1. **Reverse-CTA** — ในกลุ่ม/คอมเมนต์ใช้กรอบ "ถ้าลองที่อื่นแล้วยังไม่ใช่ ลองทำ quiz ก่อนตัดสินใจ" → ลด resistance + จับคนกำลังตัดสินใจ
2. **DM-retargeting** — เก็บลิสต์คนกด bio แต่ยังไม่ทำ quiz → follow-up 24-48 ชม. ด้วย pain-point ("หลายคนถามว่าหนี้ 3 หมื่นจัดการยังไง") → ส่ง quiz
3. **Trigger-word hygiene** — เลี่ยงคำ "ฟรี / click here / direct link" (โดน spam classifier) → ใช้ "ไม่กดสปอนเซอร์ ไม่มีค่าใช้จ่าย" + CTA "ถามใน DM"
4. **DM throttling** — ส่ง DM เว้นจังหวะ (ไม่รัว) + ใช้ quick reply ไม่ยัดลิงก์ = ลดเสี่ยง flag
5. **Micro-community bridge** — ดึงสมาชิกกลุ่มการเงินที่พูดน่าเชื่อถือเป็น "สะพาน" (ไม่ใช่ sponsor จ่ายเงิน) → เข้ากับ $0
6. (ตรงกับ playbook เดิม = ยืนยันซ้ำ) FB Groups ห้ามลิงก์/แท็ก โพสต์เช้า-เย็น · Pantip ตอบในเธรด · YouTube pinned comment · Threads reply ด้วยคำถาม

---
## ⛔ อัปเดต: fan-out Gemini/Qwen ตัวจริง = ทำที่ $0 ไม่ได้ (verify ครบ ~13:20)
ลองผ่าน `hermes chat -m <model>` (route provider nous):
- `google/gemini-3.5-flash` → **paid — เครดิตไม่พอ** ("balance too low") · `qwen/qwen3.7-plus` → paid เช่นกัน
- `nvidia/nemotron-3-ultra-550b:free` · `nvidia/nemotron-3-super-120b:free` · `tencent/hy3-preview:free` → **HTTP 404 not wired** (catalog list ไว้แต่ backend ไม่ได้ต่อ)
- OpenRouter free (qwen/llama ผ่านคีย์ QWEN) → 404/429
- **โมเดลฟรีที่รันได้จริงตัวเดียว = `stepfun/step-3.7-flash:free`** (default) → คุณภาพต่ำ = ที่กลั่นไว้ข้างบนแล้ว

### ทางได้ Gemini/Qwen จริง
- **$0:** ตั้ง `GOOGLE_AI_STUDIO_KEY` (Google AI Studio free tier) → `pipeline/free_ai.py` รัน gemini-flash ฟรี → Cowork รันให้ทันที = ได้ Gemini ตัวจริง
- **paid:** เติมเครดิต Nous portal → `hermes chat -m google/gemini-3.5-flash` + `-m qwen/qwen3.7-plus`

### มุมที่ครบแล้วตอนนี้ (ใช้งานได้จริง)
Opus (`GROWTH-PLAYBOOK-6PLATFORM` 6 แพลตฟอร์ม + คำสั่ง Hermes→CC) + Hermes/StepFun (5 ไอเดียกลั่นข้างบน) = multi-angle 2 เสียงที่ทำงานได้แล้ว · ขาดแค่เสียง Gemini/Qwen สะอาด ซึ่งรอ key หรือเครดิต
