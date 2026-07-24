# RESULT — internal-link architecture ทั้งเว็บ (order 24 ก.ค. 2026)

สถานะ: **PHASE 0 + เฟส 1 + เฟส 2 เสร็จ · gate PASS ทุกข้อ · wave นี้ปิด orphan ได้ครบตามเกณฑ์**

## PHASE 0 — compliance fix ✅
`/links` hero tagline: "เทียบของจริง **อนุมัติไว** สมัครออนไลน์" → "เทียบของจริง **ก่อนตัดสินใจ** สมัครออนไลน์" (exact-string, จุดเดียว) · ยืนยันบนหน้า build แล้ว · ไม่แตะจุด grandfathered (ชื่อหน้า easy-approval / คำเตือนมิจฉาชีพ / "ไม่การันตี" 39 จุด) ตามที่ order ระบุ

## เฟส 1 — analyzer + baseline

สร้าง `tools/_link_audit.py` (ชั่วคราว ไม่ commit) — นับ **inbound unique source page** ต่อหน้า จาก `site/*.html`

**การตัดสินใจเชิงวิธีวัด 3 ข้อ (ต่างจากการนับ grep ดิบ — สำคัญต่อการอ่านตัวเลข):**
1. **ตัด footer + บล็อก "อ่านต่อ/ลิงก์ที่เกี่ยวข้อง" ออกจากการนับ** → เหลือเฉพาะลิงก์ในเนื้อหา (contextual) ตามเจตนา order · บล็อก "เรื่องอื่นในหมวด" (topical siblings) ยังนับ เพราะเป็นลิงก์ตามหัวข้อจริง · รายงานคอลัมน์ `all` (รวม boilerplate) คู่กันไว้เทียบ
2. **ตัดหน้า `noindex` ออกจากเป้าหมาย** — 6 หน้า infographic เป็น noindex (ไม่ใช่หน้า SEO) การยัด inbound ให้มันคือเสียแรงเปล่า · ตัด `google[hash].html` (ไฟล์ยืนยัน GSC) ด้วย
3. **บั๊กที่เจอและแก้ระหว่างทาง:** รอบแรกผมกัน `index.html` ออกจากการเป็น *source* ด้วย (ตั้งใจกันแค่ไม่ให้เป็น target) ทำให้ close-debt-fast แสดง 0 ทั้งที่หน้าแรกลิงก์อยู่ → แก้แล้ววัดใหม่ ตัวเลขในรายงานนี้คือหลังแก้

**Baseline: 70 หน้า indexable · contextual inbound<3 = 9 หน้า** — และ **หน้า priority/money ผ่าน ≥3 หมดแล้ว** จากงานรอบ 21–24 ก.ค. (debt-letter-kit=10 · debt-calculator=67 · debt-health-check=67 · loan-cash=59 · car-still=4 · salary-30000-2026=6 · refi-calc=8 · freedom-clock=3 · links=63 · quiz=56) → wave นี้จึงเป็น "หน้า orphan สนิท + near-orphan" ล้วน

## เฟส 2 — เพิ่ม 13 ลิงก์ contextual เข้า 7 หน้า

| หน้าเป้าหมาย | inbound ก่อน→หลัง | source ที่เพิ่ม (1 ลิงก์/หน้า) |
|---|---|---|
| loan-approval-compare | **0 → 3** | loan-cash-2026 · personal-loan-2026 · bureau-blacklist-loan-2026 |
| car-pawn-not-paid-off | 1 → **3** | car-still-installment-loan-2026 · car-title-loan-compare-2026 |
| close-debt-fast-2026 | 1 → **3** | debt-clinic-sam-2026 · pay-off-credit-card-debt-2026 |
| credit-card-salary-30000 (standalone) | 1 → **3** | credit-card-salary-30000-2026 · krungsri-credit-card-rejected-2026 |
| old-car-financing-20years | 1 → **3** | car-refinance-2026 · car-title-loan-compare-2026 |
| first-credit-card-student-2026 | 2 → **3** | credit-card-salary-15000-2026 |
| retirement-planning-salary-2026 | 2 → **3** | tax-deduction-salary-2026 |

- **inbound edges รวมทั้งเว็บ 1018 → 1031 (+13)** · ไม่มีหน้าไหน inbound ลดลง (เพิ่มอย่างเดียว) · ไม่มีหน้าหาย
- เพดาน ≤2 ลิงก์ใหม่/source: ผ่านทุกหน้า (car-still และ car-title-compare ใช้เต็ม 2 พอดี) · dup-check ก่อนเพิ่มทุกคู่ · ไม่แตะ .ilinks รอบ 21–24 ก.ค.

## 🔴 สิ่งที่เจอระหว่างทางและควรให้ Cowork ตัดสิน: keyword cannibalization 2 คู่

analyzer เผยว่าหน้า `_SEO_STANDALONE` ทับหัวข้อกับหน้า ART ที่เราเพิ่งดัน SEO:

| คู่ | หน้า A (ดันไปแล้ว) | หน้า B (standalone) |
|---|---|---|
| 1 | `car-still-installment-loan-2026` — "รถผ่อนไม่หมด จำนำได้ไหม? ทางเลือกโอนเล่มและรีไฟแนนซ์" (92 imp) | `car-pawn-not-paid-off` — "รถยังผ่อนไม่หมด จำนำหรือเข้าไฟแนนซ์ได้ไหม" |
| 2 | `credit-card-salary-30000-2026` — "เงินเดือน 30000 วงเงินบัตรเครดิตได้เท่าไหร่?" (55 imp) | `credit-card-salary-30000` — "เงินเดือน 30,000 สมัครบัตรเครดิตอะไรได้บ้าง" |

**สิ่งที่ผมทำภายใต้ scope order (ไม่ merge/ไม่ canonical เพราะเกินอำนาจ order):** จัดโครงลิงก์แบบ **hub→spoke** — ให้หน้า A (ตัวหลัก มี impression) เป็นผู้ลิงก์ไปหน้า B และเลือก anchor ที่**ชี้มุมเฉพาะของ B ไม่ใช่คำค้นซ้ำของ A**:
- B1 anchor = "สิทธิ์ตามสัญญาเช่าซื้อเมื่อรถยังผ่อนไม่หมด" (มุมเฉพาะของ B: สิทธิ์ตามสัญญา + เตือนจำนำนอกระบบ) ไม่ใช่ "รถผ่อนไม่หมดจำนำได้ไหม" ซ้ำ A
- B2 anchor = "เงินเดือน 30,000 เลือกบัตรตามการใช้งานและเอกสารที่ต้องเตรียม" (มุมเฉพาะของ B) ไม่ใช่ "วงเงินเท่าไหร่" ซ้ำ A

**ข้อเสนอให้ Cowork ตัดสินรอบหน้า:** ถ้า GSC 4–6 สัปดาห์ยังเห็นสองหน้าแย่ง query เดียวกัน ควรเลือกทางใดทางหนึ่ง — (ก) รวมเนื้อ B เข้า A + 301 · (ข) canonical B→A · (ค) เขียน B ใหม่ให้จับ query คนละตัวจริงจัง — **ผมไม่ตัดสินใจเองเพราะกระทบ URL/สัญญาณที่ดันมาแล้ว**

## หน้าที่เหลือ inbound<3 = 2 หน้า (ตั้งใจไม่แตะ + เหตุผล)
1. `workshop-hr` — contextual=1 แต่ **inbound รวม 61 หน้า (ลิงก์ใน footer ทุกหน้า)** → ในสายตา Google ไม่ใช่ orphan; เป็นหน้า B2B การยัดลิงก์ในบทความผู้บริโภคจะดูไม่เป็นธรรมชาติและไม่ตรง intent
2. `contact` — utility page (sitemap priority 0.4) inbound=2 จาก about+disclaimer · ไม่ใช่หน้า content SEO · **ข้อเสนอ:** ถ้าต้องการดัน ควรเพิ่มลิงก์ใน FOOTER (ดีต่อ E-E-A-T ด้วย) แต่ FOOTER กระทบทุกหน้า = ขอให้ Cowork เคาะก่อน ไม่ทำเองในรอบนี้

**wave ถัดไป: ไม่มีหน้า content ค้างในเกณฑ์ inbound<3 แล้ว** (ต่างจากที่ order เผื่อไว้ว่าอาจเหลือ inbound=2 จำนวนมาก)

## Gate
- build ผ่าน · **smoke 71/71** · affiliate 19/19 · link_check broken 0 · disclosure ครบทั้ง 12 source ที่แก้
- anchor ใหม่ 7 แบบ: ไม่มีคำต้องห้าม/ไม่มีเลข % · ไม่แตะ CTA/affiliate/เนื้อหาอื่น (เพิ่ม internal link ล้วน)
- `tools/_link_audit.py` **ไม่ commit** (ชั่วคราวตาม order) — ถ้าอยากใช้ตรวจรอบหน้า บอกได้ ผมจะ commit ให้เป็นเครื่องมือถาวร
