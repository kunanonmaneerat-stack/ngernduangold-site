# CC report — 2 interactive tools LIVE · 11 ก.ค. 2026 (commit aa8023b)

## ⚠️ Deviation สำคัญ (แจ้ง Cowork)
ไฟล์ `tool_refinance-savings-calculator.html` + `tool_debt-health-quiz.html` **ไม่เคยมาถึงเครื่อง CC** (ค้นทั้ง repo / cc-inbox ทั้งสองจุด / OneDrive / Downloads — ไม่พบ; Cowork env = cloud, ไฟล์ไม่ sync ลง local)
→ CC **สร้างเองจาก spec ในออเดอร์** (routing map/title/comply/feature ระบุครบ) แทนการ block งาน
→ **ขอให้ Cowork diff กับเวอร์ชัน node-tested ของตัวเอง** โดยเฉพาะสูตร scoring — ถ้าเกณฑ์ต่างกัน ส่ง order แก้จุดต่างมา (โครงหน้า/routing คงไว้ได้)

## LIVE URLs
- https://ngernduangold.com/debt-health-check — quiz 7 ข้อ (DTI + พฤติกรรม, 0–100 คะแนน) → เกรด A–F
- https://ngernduangold.com/refinance-savings-calculator — PMT amortized เดิม/ใหม่ + ดอกประหยัดสุทธิ + จุดคุ้มทุนค่าธรรมเนียม

## B) Routing ที่เลือก = **หน้ากลาง (ไม่ยิงตรง atth.me)**
- Quiz: A/B → /kept-savings-2026 · C/D → /debt-calculator · E/F → /debt-consolidation-2026 (+ secondary SAM clinic สำหรับ E/F) — UTM `dhq_{grade}` แยกเกรดใน GA4
- Refi calc CTA → /debt-consolidation-2026 (`refi_wedge`)
- เหตุผล: kept-savings (หน้ากลาง) = conv 93% พิสูจน์แล้วว่า explain-first ชนะ · comply ปลอดภัยกว่า (คนเพิ่งรู้เกรดตัวเอง ควรเห็นบริบทก่อนเจอ affiliate) · affiliate ยังคง **17/17 ไม่แตะ**

## C) Internal linking (ใหม่)
- nav ทุกหน้า: "เช็กหนี้ 60 วิ" → quiz **inbound 63 หน้า** · hero หน้าแรก CTA เด่น (เรือธง)
- calc_cta banner ต้นบทความ cluster: + quiz ทุก 9 หน้า · + refi calc 4 หน้าที่เกี่ยว (consolidation/restructuring/cc-interest/payoff-cc) → refi **inbound 6 หน้า**
- crosslinks 3 เครื่องมือถึงกันครบ (topnav + toolx)

## D) Comply by design
ดอกเบี้ย/ตัวเลขผู้ใช้กรอกเอง 100% ไม่ hardcode อัตราใด ๆ · badge "ไม่เก็บข้อมูล-คำนวณในเครื่อง / ไม่หนุนหนี้นอกระบบ" · disclosure การศึกษา+พันธมิตรครบ (CTA box + footer + บนการ์ดแชร์ canvas ด้วย)

## E) Verify
- **Adversarial review 4 เลนส์ (math/JS/comply/routing): 0 confirmed major** · แก้ 5 minor ก่อน push (typo "ทวง", paym เว้นว่างต้องเตือน (กัน DTI-0 เกรดเฟ้อ), term clamp 480 เดือน (กัน NaN overflow), footer disclosure quiz, badge ธปท. ที่ไม่ substantiated → reword)
- Gates: smoke **64/64** · link_check 0 broken · affiliate **17/17** · comply OK · blob UFFFD=0
- LIVE ทดสอบจริงผ่าน browser: quiz กรอกจริง → เกรด D route ถูก · calc 200k/48ด/20→12% → +35,327 บาท คุ้มทุน ~5 เดือน · **share PNG generate จริงทั้งคู่** (~1MB canvas 1080²) · mobile 375px ไม่มี overflow · ext=200 + .html→301 + canonical extensionless ✓

## Known-minor (จงใจไม่แก้)
- verdict "break-even นานกว่างวดผ่อน" เป็น dead branch (คณิตพิสูจน์แล้วเคส saveNet≤0 ดักก่อนเสมอ — ข้อความที่ user เห็นถูกต้องเสมอ)
- iOS Safari: navigator.share อาจเงียบถ้า gesture หมดอายุ — มี fallback รูป preview + คำแนะนำกดค้างบันทึกแล้ว

**กระสุน Pantip 16 ก.ค. พร้อม**: "ลองเช็กสุขภาพหนี้ก่อน ngernduangold.com/debt-health-check"
