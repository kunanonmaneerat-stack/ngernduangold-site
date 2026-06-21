# 🧩 3-Model Consult → Action Sheet (21 มิ.ย. 2026)

## สถานะโมเดล (ซื่อสัตย์ — รันสดจากเครื่อง)
| โมเดล | ผล | เหตุ / ปลดล็อก |
|---|---|---|
| **Opus** (ผม) | ✅ ตอบจริง (ข้างล่าง) | — |
| **Gemini** (`free_ai.py`) | ⛔ NO_KEY | ตั้ง `GOOGLE_AI_STUDIO_KEY` หรือ `GEMINI_API_KEY` (หรือวางไฟล์ `ga4-admin/.env`) แล้วรันได้ทันที |
| **Qwen** (OpenRouter free) | ⛔ 404 | `qwen3-next:free` + `qwen3-coder:free` ถูกถอด/ดันให้ใช้ paid · คีย์ใช้ได้ ติดแค่รุ่นฟรีหมุนหาย |
| Llama-3.3-70B free (สำรอง) | ⛔ 429 | rate-limited upstream (ต้อง BYOK ถึงจะมีโควต้า) |

> คง **$0** ตาม playbook (ไม่แตะ paid) + ไม่กุเอาต์พุตแทนโมเดลที่รันไม่ได้ · พอคีย์ Gemini พร้อม/free tier ฟื้น ผมรันสดเติมมุมที่ 2-3 ให้

---

## มุม Opus — ตอบ 3 คำถาม consult ของ playbook

### Q1 · ลำดับ platform ถูกไหม (Pantip+FB Groups นำ)?
ถูกหลักการ แต่ **ปรับตามความจริงที่เพิ่ง verify**:
- **Pantip = #1 จริง** — intent สูงสุด (คนถามตรง ๆ "รวมหนี้ที่ไหน/กู้ผ่านไหม" = ปลายกรวย) · ทำคนเดียวได้ · ไม่ต้องมีคลิป → คุ้มแรงสุด
- **FB Groups: ลดชั่วคราว** — บัญชี FB โดน suspend ตั้งแต่ 06-19 → เสี่ยง/ช้า ดันกลับเมื่อบัญชีเคลียร์
- **Threads = #2 ตอนนี้** (ไม่ติด suspend · text-only · มี drafts พร้อม) เสียบแทน FB ชั่วคราว
- เหตุผลโครงสร้าง: ที่ volume ต่ำมาก (99 คลิก/7วัน) **"ความลึกของ intent" สำคัญกว่า "reach"** → เทไปที่คนพร้อมตัดสินใจ

### Q2 · หลัง conversion แรก เพิ่ม autonomy engine ตรงไหนก่อน?
- **ก่อน conversion แรก:** engine autonomous เฉพาะ **research + draft + monitor** (🟢) · โพสต์ยังให้คนกด (กัน shadowban + ช่วงสร้าง trust)
- **หลัง conversion แรก (พิสูจน์ว่า funnel ปิดได้):** เปิด **monitor → auto-trigger CC read-only** เมื่อ quiz_start ≥30 (playbook [B]) ก่อน — ยังไม่ auto-โพสต์/auto-commit
- **ให้ Hermes ทำเองเร็วสุด = reconcile ledger ↔ Postiz queue อัตโนมัติ** (งานน่าเบื่อ เสี่ยงต่ำ) เพื่อปิด gap "โพสต์นอกระบบ ledger ไม่เห็น" ใน POST-PROTOCOL

### Q3 · จุด conversion ที่ถูกมองข้าม (volume ต่ำ + อนุมัติยาก)?
1. **Attribution บอด (sub_id ไม่ถึง AccessTrade)** — verify แล้วว่า Sub ID tab ว่าง → ตอน conversion แรกมา จะไม่รู้ช่อง/หน้าไหนปิดได้ → optimize ผิดจุด · **ต้องแก้ก่อนมี conversion** (กำลังทำใน build_site)
2. **Offer×audience friction** — loan/card อนุมัติยาก = conversion lag นาน · จุดมองข้าม = **insurance-travel (MSIG/SCB live) + lifestyle card** friction ต่ำ ตัดสินใจเร็ว → ใช้เป็น **"first-win"** target ของ cold traffic ก่อนดันสินเชื่อ
3. **วัด micro-conversion เป็น proxy** — ที่ volume ต่ำ ใช้ `quiz_complete`/`recommendation_view`/`affiliate_click` แทนการรอ revenue (รอ revenue = loop ช้าเกินจะเรียนรู้) · ledger STANDBY-until-quiz_start≥30 ถูกแล้ว

---
## ทำอะไรต่อ (priority)
1. **P0 distribution:** Pantip 3-5/วัน + Threads 2-3/วัน (FB พักจน unsuspend) — ลิงก์ DM/bio
2. **P1 first-win re-route:** Daily Intent Engine เล็ง insurance-travel + lifestyle card สำหรับ cold traffic
3. **P1 แก้ attribution:** patch sub_id → AccessTrade (กำลังทำ) เพื่อพร้อมอ่านผลตอน conversion แรก
4. **เปิด Gemini:** ตั้ง `GOOGLE_AI_STUDIO_KEY` → ผมรัน consult สดเติมมุม Gemini/Qwen ได้
