# RESULT — คำตัดสิน 3 ข้อ + audit tool (order 25 ก.ค. 2026)

สถานะ: **ข้อ 2 + ข้อ 3 เสร็จ · gate PASS · push รวม commit ค้างของ Cowork ครบ** · ข้อ 1 ไม่มีงานฝั่ง CC (รับทราบ: รอ GSC 24 ส.ค. – 7 ก.ย.)

## ข้อ 2 — ลิงก์ "ติดต่อเรา" ในฟุตเตอร์ ✅

- แก้ template `FOOTER` ใน build_site.py **จุดเดียว** — ต่อท้ายแถวเดิม: `นโยบายความเป็นส่วนตัว & การเปิดเผยข้อมูล · สำหรับองค์กร/HR: Workshop การเงินพนักงาน · **ติดต่อเรา**` (คั่นด้วย ` · ` ตามรูปแบบเดิม, href extensionless ตาม URL convention)
- **ผลจริง: ลง 61 ไฟล์จาก 78** — ส่วนที่เหลือ 17 ไฟล์ **ไม่ได้ใช้ FOOTER template นี้โดยการออกแบบเดิมของระบบ** ไม่ใช่ความผิดพลาด:
  - 6 หน้า infographic (noindex, ไฟล์ standalone)
  - 4 หน้า `_SEO_STANDALONE` (car-pawn, credit-card-salary-30000, loan-approval-compare, old-car-financing) — ไฟล์ root ที่ build แค่ inject `<head>` + GA
  - 6 หน้า `_TOOL_PAGES` (debt-calculator, debt-health-check, refinance-savings-calculator, debt-freedom-clock, workshop-hr, debt-letter-kit) — เช่นกัน
  - 1 ไฟล์ยืนยัน GSC
  → ถ้าต้องการให้ครบ 78 ต้องแก้ฟุตเตอร์ในไฟล์ root แต่ละไฟล์ (คนละกลไก) — **ไม่ทำในรอบนี้เพราะ order ระบุ "แก้ที่ template ฟุตเตอร์ใน build_site.py จุดเดียว"** สั่งเพิ่มได้ถ้าต้องการ
- **ผลต่อ inbound ของ /contact: 2 → 60** (คอลัมน์ `all`) = แก้ปัญหา orphan ตามเจตนาแล้ว
  หมายเหตุการอ่านตัวเลข: คอลัมน์ `in` (contextual) ยังเป็น 2 เพราะ analyzer **ตัดฟุตเตอร์ออกจากการนับโดยตั้งใจ** (ลิงก์ฟุตเตอร์เหมือนกันทุกหน้า ไม่บอกความเกี่ยวข้องเชิงหัวข้อ) — Google เห็น 60 หน้า ซึ่งคือผลที่ต้องการจากคำตัดสินนี้
- Gate: build ผ่าน · **smoke 71/71** · disclosure ฟุตเตอร์เดิมไม่หาย

## ข้อ 3 — `tools/link_audit.py` เป็นเครื่องมือถาวร ✅

- path: **`tools/link_audit.py`** (ตัด `_` นำหน้าแล้ว) · commit ในก้อนเดียวกับข้อ 2
- **path เป็น relative จาก repo root แล้ว** — เดิม hard-code `C:\Users\nL_ku\ngernduangold-site` ตอนนี้คำนวณจากตำแหน่งไฟล์ (`REPO = dirname(dirname(__file__))`) → ย้ายเครื่อง/รันจาก path ไหนก็ทำงาน
- docstring หัวไฟล์ครบตามสั่ง: ใช้ทำอะไร (ทำไม index coverage ถึงเป็นคอขวด) · รันยังไง (ต้อง build ก่อน + ตัวอย่าง `--min` / `--json`) · **อ่านผลยังไง** (อธิบายทุกคอลัมน์: `in` vs `all` ต่างกันยังไง และเคส workshop-hr ที่ `in` ต่ำแต่ `all` สูง = ไม่ใช่ orphan อย่าไปยัดลิงก์) · สิ่งที่ไม่ถูกวัดและเพราะอะไร · กติกาตอนเพิ่มลิงก์ (≤2/source, anchor ห้ามคำต้องห้าม/%)
- ทดสอบรันจริงหลัง build: `indexable pages=70 | contextual inbound<3 = 2` (workshop-hr, contact) ตรงกับรอบก่อน ✓

## 🟡 สิ่งที่เจอระหว่าง gate (ไม่ได้แก้ — อยู่นอก scope order นี้)

ตอนตรวจ disclosure ทั้งเว็บแบบเข้มงวด เจอ **2 เรื่องที่ควรรู้**:

1. **gate เดิมของผมเองมี false positive**: การ grep คำว่า `มีลิงก์พันธมิตร` จะ match คำว่า "**ไม่**มีลิงก์พันธมิตร" ด้วย (substring) — หน้า standalone 3 หน้าเขียนว่า "หน้านี้ไม่มีลิงก์พันธมิตร" ซึ่งถูกต้องตามจริง (หน้าเหล่านี้ไม่มี affiliate link) แต่ gate เดิมอ่านว่า "ผ่าน" ด้วยเหตุผลผิด → ผมตรวจซ้ำแบบแยก affiliate link จริง (`href` ที่ชี้ atth.me นอก `<script>`) เทียบกับข้อความ disclosure แล้ว
2. **ผลการตรวจที่ถูกต้อง: ทั้งเว็บสอดคล้องหมด ยกเว้น `loan-approval-compare.html` 1 หน้า** — หน้านี้ไม่มี affiliate link จริง (0 ลิงก์) และไม่ได้เขียนทั้ง "มีลิงก์พันธมิตร" หรือ "ไม่มีลิงก์พันธมิตร" ต่างจากหน้า standalone พี่น้องอีก 3 หน้าที่ระบุชัด · ปัจจุบันเขียนอ้อมว่า "ลิงก์ผลิตภัณฑ์ภายนอกให้เข้าผ่านหน้า /links ตามการเปิดเผยของเว็บไซต์"
   → **ไม่ใช่การละเมิด** (ไม่มี affiliate ก็ไม่ต้อง disclose affiliate) แต่ไม่สม่ำเสมอกับพี่น้อง · แก้ได้ใน 1 บรรทัดที่ไฟล์ root `loan-approval-compare.html` ให้เขียน "หน้านี้ไม่มีลิงก์พันธมิตร" เหมือนอีก 3 หน้า — **รอสั่ง** (order นี้ระบุ "แก้เฉพาะที่ระบุ")

## Push ✅

commit ที่ขึ้น remote รอบนี้ (push ครั้งเดียว):

| commit | เจ้าของ | เนื้อหา |
|---|---|---|
| `b22be10` | Cowork | funnel: CRITICAL fix — LINE chat was OFF (sales dead-end) |
| `4c60482` | Cowork | cc-order: verdicts (ไฟล์ order นี้เอง) |
| `5a6b9ba` | Cowork | docs: rich menu verified already live |
| (CC) | CC | seo: footer contact link + promote link_audit to permanent tool |
| (CC, HEAD) | CC | รายงานฉบับนี้ + ย้าย order เข้า done/ |

- **commit ค้างของ Cowork ขึ้นครบ 3 ตัว** (ค้นแล้วไม่พบ commit ชื่อ "sales-log system" ในสิ่งที่ค้าง — ที่ค้างจริงคือ LINE funnel fix + rich menu + order file; ถ้า sales-log ยังไม่ commit ฝั่ง Cowork แจ้งได้ ผมจะ push ให้รอบหน้า)
- ย้ายเข้า `cc-inbox/done/`: order นี้ + `CC-ORDER_internal-link-architecture_20260724.md` (ตัวหลังย้ายไปแล้วตั้งแต่รอบก่อน — ยืนยันอยู่ใน done/ ครบ) → **cc-inbox ว่าง**
