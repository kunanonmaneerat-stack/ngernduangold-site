# CC report — Wave 1+2 SHIPPED ครบ 4 หน้า · 11 ก.ค. 2026 (commits aa8023b + 546fac4)

## ⚠️ Deviation เดิม (ยังยืน)
ไฟล์ `tool_*` / `page_*` ทั้ง 4 **ไม่เคยถึงเครื่อง CC** (outputs = env ของ Cowork ไม่ sync ลง local) → CC สร้างจาก spec ทั้งหมด
**หลักฐานว่าสูตรตรงกัน**: เคสทดสอบที่ Cowork ให้ (300k/16%→9%/36 = ~36,000) — เวอร์ชัน CC ให้ **+36,259 บาท** ✓ ตรง node-test
`VIDEO-FACTORY_SOP+5scripts` ก็ไม่พบ local → งาน G (ถอด 50 บทความเป็นสคริปต์) **block รอไฟล์** — ส่งมาทาง cc-inbox แล้ว CC เริ่มได้เลย

## LIVE ทั้ง 4 (canonical extensionless + .html→301 + og+twitter card + GA ครบ)
| หน้า | og:image | routing | verify live |
|---|---|---|---|
| /debt-health-check | og-tool-quiz.png (custom) | A/B→kept · C/D→calc · E/F→consolidation+SAM | เกรด D route ✓ PNG ✓ |
| /refinance-savings-calculator | og-tool-refi.png | → /debt-consolidation-2026 | **+36,259** (เคส spec) ✓ PNG ✓ |
| /debt-freedom-clock | og-tool-clock.png | → /debt-calculator (+refi ในเคสดอกกิน) | ก.ค.2571 · slider +3000 → เร็วขึ้น 9 เดือน ✓ PNG ✓ |
| /workshop-hr | og-workshop-hr.png | LINE @804qodya + mailto (ไม่มี affiliate) | ปุ่มครบ · FAQ-LD · 0 console error ✓ |

- OG cards ทั้ง 4 = gen ด้วย PIL ($0, brand ink/gold, ฟอนต์ Leelawadee) ไม่ใช่ Express (zero-budget rule) · เสิร์ฟ 200 image/png ครบ
- Routing เลือก**หน้ากลาง** (ไม่ยิงตรง atth.me) — trust-first + A/B ทีหลังตามคำแนะนำใน order · affiliate เดิม **17/17 ไม่แตะ**

## Internal linking (นับจริงหลัง build)
quiz **65 หน้า** (nav sitewide+hero) · refi **8 หน้า** (banner 4 cluster + car-title ใหม่ + crosslinks) · clock **3** (calc/quiz/refi crosslinks) · workshop-hr **61 หน้า** (footer sitewide + about)

## Review ก่อน push (4 เลนส์ adversarial) — 3 MAJOR จับได้+แก้แล้ว
1. **setMonth day-overflow**: ใช้วันที่ 29–31 เดือนปลอดหนี้เพี้ยน +1 เดือน (ทั้งจอ+การ์ดแชร์) → fix `setDate(1)` ก่อนบวกเดือน
2. **workshop footer เคลมเกิน** "ไม่มีลิงก์พันธมิตรในห้อง" ทั้งที่เครื่องมือที่ใช้ในห้อง route ไปหน้าที่มี → reword เปิดเผยตรงไปตรงมา (คงไว้เฉพาะ "ไม่ขายผลิตภัณฑ์ในห้อง" ที่จริง)
3. **Deploy hazard**: build fail-open + ไฟล์ใหม่ untracked = push แล้ว 404 sitewide ได้ → commit เดียวครบ 10 ไฟล์ + เพิ่ม **fail-closed guard** ใน build_site.py (ไฟล์ tool/og หาย = build ล้ม ไม่ deploy เว็บพัง)
+ minor: ข้อความเคส >600 เดือนแยกจากเคสจ่ายไม่พอดอก (เดิมพูดผิดข้อเท็จจริง) · เคลมต้นทุน B2B แบบเทียบข้ามผลิตภัณฑ์ → reword hedged

## Gates: smoke **66/66** · link_check 0 broken · affiliate **17/17** · comply OK · blob UFFFD=0 · mobile 375px ไม่มี overflow ทุกหน้า

## Owner/Cowork ตัดสินใจ 2 จุด
1. **อีเมล B2B** ใช้ gmail เจ้าของ (kunanonmaneerat@) — ถ้าอยากได้ email ทางการกว่านี้แจ้งแก้ 1 บรรทัด
2. **ราคา workshop** ไม่ใส่ตัวเลข (ใบเสนอราคาฟรีไม่ผูกมัด) — CC ไม่ invent ราคาแทนเจ้าของ · ถ้าจะใส่ "เริ่มต้น X฿" ส่งตัวเลขมา
