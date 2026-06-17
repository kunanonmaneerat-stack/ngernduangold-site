# 🤖 Free pipeline — LIVE-RUN sample (proof of real Gemini generation, $0)

รันจริง 2026-06-18 ผ่าน Gemini MCP (key ของเจ้าที่อยู่ใน MCP server · model `gemini-3-flash-preview` = free tier · ไม่มี paid call · ไม่มี evasion). ⚠️ free tier มี rate-limit จริง (เจอ 429 ตอนใช้ grounding หนัก → flash ธรรมดาผ่าน) = ยืนยันว่า cost-guard (`free_ai.py`) จำเป็นและถูกทาง.

## STEP 1 — trend_ingest (ตัวอย่างจริง)
```json
[{"topic":"วิธีบริหารเงินเดือน 15,000 ให้มีเงินเก็บและพอกินถึงสิ้นเดือน","intent":"ออม/งบประมาณ"},
 {"topic":"เทคนิคใช้สิทธิลดหย่อนภาษี สำหรับมือใหม่ยื่นปีแรก","intent":"ภาษี"}]
```

## STEP 2 — script_gen (5 variants จริง · หัวข้อ "รวมหนี้" · happycash · debt-consolidation-2026)
| # | format | hook (0–1.5วิ) | cta question |
|---|---|---|---|
| 1 | number-shock | "จ่ายขั้นต่ำ 5 ใบ วนไปแบบนี้ อีก 10 ปีก็ไม่หมด!" | เดือนนี้คุณเหลือเงินใช้จริงกี่บาท? |
| 2 | compare | "จ่ายกระจาย 4 ที่ กับ จ่ายที่เดียว... แบบไหนเบากว่า?" | ถ้าลดเหลือยอดเดียว ชีวิตจะง่ายขึ้นไหม? |
| 3 | myth-bust | "ใครบอกว่า 'รวมหนี้' คือการสร้างหนี้เพิ่ม? เข้าใจผิด!" | อยากปิดหนี้ทั้งหมดให้จบในกี่ปี? |
| 4 | pov | "เงินเดือน 3 หมื่น แต่ค่าบัตรปาไป 2 หมื่นห้า... จะรอดไหม?" | เหนื่อยไหมกับการหมุนเงินทุกสิ้นเดือน? |
| 5 | checklist | "3 สัญญาณเตือน! ถ้ามีครบ... ต้อง 'รวมหนี้' ด่วน" | คุณติดสัญญาณเตือนกี่ข้อ? |

ทุก variant: 1 ความคิด · จบด้วยคำถามปลายเปิด + "ลิงก์ในไบโอ" · disclosure "*เพื่อการศึกษา · กู้เท่าที่จำเป็น" · ไม่แต่งตัวเลขดอกเบี้ย/ไม่การันตีอนุมัติ · ผูก money_page + provider.

## STEP 3–4 — clip + QA
- STEP3 = ffmpeg engine เดิม (ไม่ gen video paid) ใช้ hook/มุมจาก variants ข้างบน + หมุน 7 format
- STEP4 = `qa_gate.py <frame>` (Gemini vision, checklist D) → pass เท่านั้นไป Postiz · ไม่มี key = degrade เป็น human eyeball

## STEP 5 — publish = Postiz + `post_ledger.py` DEDUP GATE เดิม (ปิด loop)

## หมายเหตุ autonomous
demo นี้รันผ่าน **MCP** (interactive). ให้ **scheduler รันเองอัตโนมัติ** ต้องมี key เป็น **env / ga4-admin/.env** (cron python เข้า MCP ไม่ได้) → เจ้าของวางเอง 1 บรรทัด แล้ว `free_ai.py` อ่านได้ทันที.
