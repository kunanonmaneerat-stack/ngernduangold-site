# 🧠 3-Model Growth Synthesis — FINAL (21 มิ.ย. 2026)
**Opus 4.8 + Qwen-plus + GLM-4.5-flash** (เสียงจริงทั้ง 3 · merge โดย Opus)

## โมเดลที่ใช้จริงรอบนี้
| โมเดล | ช่องทาง | สถานะ |
|---|---|---|
| Opus 4.8 (ผม) | Cowork | ✅ เสียงหลัก (GROWTH-PLAYBOOK) |
| **Qwen-plus** | DashScope international (คีย์ใหม่ sk-ws-) | ✅ ตอบเต็ม 2226 ตัวอักษร |
| **GLM-4.5-flash** | Zhipu (ฟรี) | ✅ ตอบเต็ม 2552 ตัวอักษร |
| Gemini / DeepSeek / Nous-Qwen | — | ⛔ ยอด/เครดิตหมด (402/429) |

---

## 🔥 3 เสียงเห็นตรงกัน = ทำเลย (มั่นใจสูงสุด)
1. **value-first + เล่าประสบการณ์จริง** (ไม่ขายตรง)
2. **ลิงก์เฉพาะ DM/bio** — ห้ามในโพสต์/คำตอบหลัก
3. **เลี่ยงคำ trigger** (ฟรี/ผ่านแน่นอน/คลิกเลย/รวมหนี้) → คำธรรมชาติ ("ลองเช็กว่าเข้าเกณฑ์ไหม", "หาทางออกหนี้")
4. **คอนเทนต์ต่างกันต่อแพลตฟอร์ม** (ห้ามโพสต์เดียวกันพร้อมกัน) · แท็กเฉพาะกลุ่มจริง ≤5
5. **ตอบในเธรดด้วยข้อมูลเฉพาะ → DM แบบ personalized** · **trust + social proof** สำคัญสุดตอน pre-conversion

## 🆕 มุมเด่นเฉพาะตัว (ของใหม่ที่คุ้มเพิ่ม)
**Qwen-plus:**
- **keyword→DM auto-reply** — โพสต์ "ส่งคำว่า 'เช็กหนี้' มาที่ DM ระบบส่งลิงก์ให้" (เลี่ยง throttle link-in-bio บน TikTok/YT)
- **pre-qualify 2 คำถามใน DM ก่อนส่งลิงก์ quiz** ("มีหนี้กี่รายการ?", "รายได้/เดือน?") → ลด bounce เพิ่ม % ที่ทำ quiz จบ
- **แก้ drop-off quiz ขั้น 3-4** — tooltip "ไม่ต้องกรอกเอกสารจริงตอนนี้ แค่ประมาณการ"
- **คปภ. social proof เชิงรูปธรรม** — "กรมธรรม์ออกโดยบริษัทที่ คปภ. กำกับ ตรวจเลขใบอนุญาตได้ที่ oic.or.th"
- Reels ≤20 วิ "Before-After หนี้" voiceover จริง (ไม่ใช่ AI)

**GLM-4.5-flash:**
- **Quiz → Content loop** — แปลงคำถาม/ผล /quiz เป็นคอนเทนต์ทุกแพลตฟอร์ม (กระทู้/hook/reel) = ปั๊มฟรีจาก asset เดียว
- **1 DM-link/โพสต์** (กฎเชิงปริมาณ) + ประโยคเปิดเผย
- **มุมประกัน:** อธิบายความคุ้มครอง + เทียบเบี้ย ลดความกังวลก่อนปิด

**Opus (เสริมโครง):** 6-platform plays + คำสั่ง Hermes→CC + first-win re-route (insurance-travel/lifestyle card) + STANDBY โค้ดจน quiz_start≥30 + แก้ attribution

---

## 🎯 แผนรวม (เรียงลำดับ)
- **P0 distribution:** Pantip 3-5/วัน (DM-gated) + Threads question-hook ("เคยรวมหนี้แล้วผ่านไหม?") + FB Groups value (ไม่มีลิงก์)
- **P0 content engine (Hermes 🟢):** Quiz→Content loop ป้อนทุกแพลตฟอร์มทุกเช้า
- **P1 conversion lift:** DM pre-qualify 2 คำถาม ก่อนส่ง quiz · keyword→DM auto-reply · first-win = ประกันเดินทาง/บัตร lifestyle
- **P1 funnel micro-fix (ผ่าน CC เมื่อ quiz_start≥30):** tooltip "แค่ประมาณการ" ที่ quiz ขั้น 3-4 + คปภ. license social proof
- **Hygiene เสมอ:** 1 DM-link/โพสต์ · คำธรรมชาติ · คอนเทนต์ต่างต่อแพลตฟอร์ม · ≤5 แท็ก

## 🔁 Free-Model Rotation Pool (สลับเมื่อเต็ม วนทั้งเดือน)
ตอนนี้ **มี 2 ตัวใช้ได้จริง** → ลำดับลอง (helper ข้าม 402/429/404 อัตโนมัติ):
1. **glm-4.5-flash** (Zhipu, ฟรี) ✅
2. **qwen-plus** (DashScope intl, คีย์ใหม่) ✅
3. qwen-turbo (DashScope intl) ✅ สำรอง
4. deepseek-chat / gemini-2.5-flash → รอเติมเครดิต
5. stepfun:free (Hermes) → สำรองสุดท้าย (คุณภาพต่ำ)

→ ขั้นต่อไป ผมทำ `pipeline/free_llm.py` (อ่านคีย์จาก env, ลองตามลำดับ, ข้ามตัวที่เต็ม) ให้ engine เรียก LLM ฟรีได้ไม่ต้องห่วงตัวไหนเต็ม — **ต้อง setx GLM_KEY + QW_KEY ก่อน** (ตอนนี้คีย์ยังไม่ persist)

## คำสั่ง Hermes→CC (เสริม)
> Hermes: ทุกเช้า — (A) Quiz→Content: แปลง /quiz เป็น 3 คอนเทนต์ (Pantip/Threads/TikTok) + 1 มุมประกัน(คุ้มครอง+เทียบเบี้ย) (B) ร่าง DM flow: pre-qualify 2 คำถาม → ส่งลิงก์ quiz + keyword→DM auto-reply ("เช็กหนี้") (C) ลิงก์ DM 1 ครั้ง/โพสต์ คำธรรมชาติ · เข้าคิวรอ approve ห้ามโพสต์เอง · ใช้ free_llm pool (glm→qwen)
> เมื่อ quiz_start≥30 → สั่ง Claude Code (read-only): หา drop ขั้น 3-4 + เสนอ tooltip "แค่ประมาณการ" (ไม่แก้ไฟล์จน owner OK)
