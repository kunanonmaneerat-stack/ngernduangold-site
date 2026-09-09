# แผนยกระดับระบบให้เรียนรู้และสร้างรายได้อย่างมีหลักฐาน

> ตรวจสถานะจริง: 16 สิงหาคม 2026 เวลา 20:35 น. (Asia/Bangkok)  
> เป้าหมาย: ทำให้ระบบเปลี่ยนจาก “ปลอดภัยและมีเครื่องมือ” เป็น “เรียนรู้ได้ ตัดสินใจได้ และสร้างรายได้ affiliate ที่ตรวจสอบย้อนกลับได้”  
> คำตัดสินปัจจุบัน: **Maturity 30/100 — Instrumented; ยังไม่พร้อมเลือกผู้ชนะ ขยายผล หรือเผยแพร่**

## Executive Summary

ระบบได้รับการยกระดับจากคะแนนเชิงความรู้สึกเป็น scorecard แบบ fail-closed ที่ใช้หลักฐานจากรอบเดียวกัน คะแนนรวมไม่สามารถกลบ hard blocker ได้ และข้อมูลที่ไม่ครบจะถูกเรียกว่า “ไม่พร้อม” ไม่ใช่ศูนย์

- **ความสามารถระบบ:** 30/100 ระดับ `instrumented` — หลักฐานสดและ guard ผ่าน แต่ analytics, revenue, source และ publication inputs ยังไม่พร้อม
- **ความพร้อมเรียนรู้:** 0/3 — GA4, GSC และ revenue ยังใช้ตัดสินธุรกิจไม่ได้ แต่ระบบระบุวิธีซ่อมได้ครบ 3/3
- **Funnel ในเครื่อง:** 80/100 — inventory, release, attribution และ offer safety ผ่าน; pilot ถูกบล็อกอย่างถูกต้องเพราะยังวัด session-scoped outcome ไม่ได้
- **Funnel ที่ production:** 20/100 — พบ release drift 72, attribution 624 และ offer-safety 196 รายการ
- **Guardrails รอบจริง:** 8/8 ผ่าน — automation, media, local site, manifest, merchant, posting plan, privacy และ public identity
- **Growth experiment:** ไม่มีการเลือก และระบบไม่อนุญาตให้ daily loop เลือกเอง

ข้อสรุปเชิงธุรกิจคือ ตอนนี้ควรลงทุนกับ “ความน่าเชื่อถือของข้อมูลและการทำให้ production ตรงกับ local” ก่อนเพิ่มปริมาณโพสต์ เพราะการเร่ง traffic ขณะ attribution/offer/live release ยังผิด จะเพิ่มข้อมูลปนเปื้อนมากกว่าการเรียนรู้

## คะแนนที่ใช้จริง

| เกณฑ์ maturity | น้ำหนัก | ได้ | สถานะ | เกณฑ์ผ่านถัดไป |
|---|---:|---:|---|---|
| หลักฐานสดและผูก hash | 10 | 10 | PASS | รักษาหลักฐานให้อยู่ใน cadence เดียวกัน |
| Guardrails รอบเดียวกัน | 20 | 20 | PASS | Guard ทุกตัวต้อง exit 0 ต่อเนื่อง |
| Revenue ledger เชื่อถือได้ | 15 | 0 | HARD BLOCK | Reconcile schema ปัจจุบันและผ่าน full contract |
| Analytics ตัดสินใจได้ | 15 | 0 | HARD BLOCK | ซ่อม GA4 trust แล้ว repull; repull GSC bundle |
| Official sources ผ่าน review | 10 | 0 | HARD BLOCK | Review/acknowledge 26 source packets โดยผู้มีอำนาจ |
| Publication inputs พร้อม | 20 | 0 | HARD BLOCK | Live parity + publishable placement + authority ต้องผ่านพร้อมกัน |
| เรียนรู้จาก paid outcome | 10 | 0 | NOT YET | มี paid transaction ที่ไม่ซ้ำและรายได้ paid > 0 ในหน้าต่างปัจจุบัน |
| **รวม** | **100** | **30** | **INSTRUMENTED** | เกณฑ์ทดลอง growth คืออย่างน้อย 90 และไม่มี hard blocker |

กฎสำคัญ: หากมี hard blocker คะแนนจะไม่ถูกตีความว่า growth-ready แม้คะแนนรวมสูง และหลักฐาน stale จะให้คะแนน 0

## จุดคะแนนต่ำและสิ่งที่ยกระดับแล้ว

### 1. Measurement และการเรียนรู้จากข้อมูล

ปัญหาเดิมคือไฟล์ CSV อาจถูกอ่านก่อนตรวจ hash, GA4 ที่ `UNTRUSTED` อาจถูก repull โดยไม่ซ่อม trust, และข้อมูลไม่ครบ/NaN/Infinity อาจถูกตีความเหมือนค่าจริง

สิ่งที่แก้แล้ว:

- ผูกผลรวมหลังอ่านกลับเข้ากับ sidecar hash/row count เพื่อปิดช่อง TOCTOU
- บังคับ GA4 ที่ capture/current trust ไม่ผ่านให้ทำ `REPAIR_GA4_TRUST_THEN_REPULL`
- แยกคำสั่งซ่อมแบบ canonical: `REPAIR_GA4_TRUST_THEN_REPULL`, `REPULL_GSC`, `RECONCILE_REVENUE`
- ปฏิเสธ metadata เก่า, ช่วงเวลาผิด, NaN/Infinity, row count ไม่ตรง และ hash ไม่ตรง
- สร้าง `learning_readiness` ที่ตรวจซ้ำได้จาก raw facts ไม่เชื่อ boolean ที่ผู้ใดเขียนมา

สถานะจริงยังเป็น 0/3:

| แหล่ง | สถานะ | การแก้ที่ถูกต้อง |
|---|---|---|
| GA4 | INVALID_METADATA + UNTRUSTED | ยืนยัน internal-network coverage ก่อน แล้วจึงดึง 28-day bundle ใหม่ |
| GSC | INVALID_METADATA | ดึง finalized 28-day bundle ใหม่พร้อม coverage/hash |
| Revenue | INVALID_LEDGER | Reconcile ledger ตาม lifecycle schema ปัจจุบัน; ห้ามรายงานว่า 0 บาท |

### 2. Revenue semantics

North Star ถูกแก้เป็น:

1. `paid_affiliate_revenue_thb_28d`
2. `paid_affiliate_transactions_28d`

`affiliate_click`, `buy_intent_click`, pending และ approved เป็นเพียง leading/diagnostic indicators ไม่ใช่รายได้ และ refunded/cancelled/rejected ต้องไม่ถูกรวมเป็น paid outcome

ระบบจะอนุญาตให้เรียนรู้ด้านรายได้ก็ต่อเมื่อ private ledger อ่านได้, reconcile แล้ว, contract ผ่าน, มี transaction identity ไม่ซ้ำ และยอดเงินเป็น finite canonical money เท่านั้น

### 3. Funnel และ production parity

| มุมมอง | คะแนน | ความหมาย |
|---|---:|---|
| Local audited release | 80/100 | สี่หมวด release contract ผ่าน; ไม่ใช่สิทธิ์ deploy/post |
| Production | 20/100 | ผ่านเฉพาะ inventory; exact release, attribution และ offer safety ล้ม |
| Operational pilot | BLOCKED | ขาด measurement fields แบบ session-scoped, trusted analytics และ placement receipt |

Production findings ที่ต้องเป็นศูนย์ก่อนยกระดับเป็น 80:

- Exact release: **72**
- Attribution: **624**
- Offer safety: **196**
- CTA ที่ขาด `data-content-id`: **185 จุด**

Local release manifest schema 2 ผูก 117 artifacts กับ 12 source/gate/measurement inputs จึงสามารถพิสูจน์ exact release ได้ แต่ production ปัจจุบันยังไม่มี manifest ที่ตรงกัน

### 4. Pilot ที่เรียนรู้ได้จริง

Pilot เดิมเกือบได้ 100 แบบผิด เพราะนิยาม metric เป็น session ratio แต่ producer ไม่ได้สร้าง numerator/denominator และ dimensions ที่จำเป็น ตอนนี้ถูกลดเป็น 80 และ `BLOCKED` อย่างถูกต้อง

ก่อนเริ่ม pilot ต้องเพิ่มทั้งหมด:

- `affiliate_click_sessions`
- `qualified_landing_sessions`
- session-scoped content/placement/CTA dimensions
- GA4 capture และ current trust = `TRUSTED`
- publishable placement receipt และสิทธิ์ดำเนินการแยกต่างหาก

สมมติฐาน uplift 8% ถูกลดชั้นเป็น provisional/low confidence ต้อง reset หลัง baseline ที่เชื่อถือได้ครั้งแรก และห้ามใช้ประกาศ winner หรือ scale

## วงจรพัฒนาที่ติดตั้งแล้ว

### Daily — Observe, Diagnose, Validate และ Queue Repair

1. เก็บหลักฐานรอบเดียวกัน
2. รัน guardrails
3. คำนวณ maturity score แบบ provisional
4. สร้าง action queue พร้อม owner, acceptance criteria, TTL และ stable dedupe
5. จัดคิวงานซ่อมสูงสุด 3 รายการ; การ apply ต้องทำใน scoped agent session แยกต่างหาก
6. ห้ามเลือก growth experiment, winner, cadence หรือ scale

### Weekly — Ratify และจัดคิว experiment ได้ไม่เกินหนึ่งรายการ

Weekly queue งาน `design_one_revenue_experiment` ได้ไม่เกินหนึ่งรายการ แต่ยังไม่ได้เลือกหรือเริ่ม experiment จริง Eligibility ต้องครบทุกข้อ:

- Scorecard current และคะแนนอย่างน้อย 90
- ไม่มี hard blocker
- Learning sources ผ่าน 3/3
- มี paid transaction ที่ยืนยันได้และ paid revenue เป็นบวก
- ใช้ weekly cadence และหลักฐานสถานะ `CURRENT`

Same-policy baseline และ criterion transition แบบ failed -> passed ใช้เฉพาะรับรอง progression; รอบแรกเป็น `NO_BASELINE` ได้ หาก hard blocker เปิดใหม่ ระบบบันทึก `REGRESSED` และไม่เลือกงาน growth ใหม่ แต่ยังไม่มี executor ที่พิสูจน์ว่าสั่งหยุด experiment เดิมอัตโนมัติ

## KPI framework

| ชั้น | KPI | บทบาท | ห้ามตีความเป็น |
|---|---|---|---|
| North Star | Paid affiliate revenue 28d | ผลลัพธ์ธุรกิจ | click value โดยประมาณ |
| North Star | Unique paid transactions 28d | ความสม่ำเสมอของรายได้ | pending/approved lead |
| Driver | Trusted affiliate-click rate | คุณภาพ CTA/funnel | commission |
| Driver | Organic clicks to monetized pages | คุณภาพ SEO traffic | รายได้ |
| Driver | Qualified landing sessions | คุณภาพ traffic เข้าหน้าเป้าหมาย | conversion หากไม่มี paid proof |
| Learning | Decision-ready sources passed / 3 | ความพร้อมใช้ข้อมูล | performance |
| Learning | Valid weekly experiments / eligible weeks | คุณภาพวงจรเรียนรู้ | จำนวน experiment มาก ๆ |
| Guardrail | Live parity findings | ความถูกต้อง release | technical debt ที่เลื่อนได้ |
| Guardrail | Source-review pending | ความถูกต้อง YMYL | warning ธรรมดา |
| Guardrail | Duplicate/watermark/privacy findings | ความปลอดภัยแบรนด์ | trade-off เพื่อความเร็ว |

## แผนยกระดับตามลำดับผลตอบแทน

### ขั้น 1 — ทำข้อมูลให้ตัดสินใจได้

1. เจ้าของยืนยัน private egress สำหรับ GA4 โดยไม่เปิดเผยค่าใน repo
2. เก็บ GA4 bundle ใหม่หลัง trust ผ่าน
3. Reconcile revenue ledger จริง; หากไม่มี raw intake ให้คงสถานะ unavailable แทนการสร้างศูนย์
4. เก็บ GSC finalized 28-day bundle ใหม่

**เกณฑ์จบ:** learning readiness = 3/3 และ maturity อย่างน้อย 60 โดยไม่มี data hard blocker

### ขั้น 2 — ทำ production ให้ตรง audited local

1. ตรวจ owner-approved release scope
2. Deploy exact manifest-bound release ผ่านเส้นทางที่ได้รับอนุญาต
3. ตรวจ production ซ้ำให้ exact release, attribution และ offer safety findings = 0
4. Regenerate dashboard จาก sidecars/producers ปัจจุบัน

**เกณฑ์จบ:** production release/funnel score = 80, live parity 100%, `preflight --full` ไม่มี dashboard/live-release fail

### ขั้น 3 — เปิด learning pilot แบบจำกัด

1. เพิ่ม session-scoped pilot measurement contract
2. เก็บ baseline แรกที่ trusted แล้ว reset threshold
3. ใช้ content/placement เดียว, เปลี่ยนตัวแปรเดียว, มี stop conditions
4. วัด paid outcome เป็น North Star และรายงาน uncertainty

**เกณฑ์จบ:** score >= 90, learning 3/3, paid outcome เป็นบวก, source/offer/publication gates ผ่าน และมี receipt เฉพาะ placement

### ขั้น 4 — ขยายเฉพาะสิ่งที่ชนะจริง

- ขยายเพียงหนึ่งตัวแปรต่อรอบ
- รักษา holdout/baseline
- หยุดทันทีเมื่อ guard, trust, offer หรือ source regress
- ห้ามเพิ่มความถี่จาก click อย่างเดียว

## Owner action queue ปัจจุบัน

มี 2 รายการที่ระบบไม่ควรทำแทนเจ้าของ:

1. **Review official sources 26 รายการ** — ตรวจ claim packet และบันทึกการ acknowledge อย่างมีหลักฐาน
2. **Verify GA4 internal network** — ยืนยันว่า private egress เป็นของเจ้าของก่อนแก้ coverage

Codex สามารถรับงานต่อใน scoped agent session ได้ 3 รายการเมื่อ prerequisites พร้อม ตามลำดับ governed queue:

1. Repair GA4 trust evidence แล้ว repull
2. Reconcile revenue ledger จากเหตุการณ์จริง
3. Repull GSC bundle

## Validation และข้อจำกัด

- Pipeline tests: 105/105 PASS
- Improvement policy: 8/8 PASS
- Release/funnel readiness regression tests: 18/18 PASS
- Preflight contract: 243/243 PASS
- Python compile: PASS
- Diff integrity: PASS
- Actual local-safe loop: `FAILED_VALIDATION`, maturity 30, ไม่มี growth experiment, external mutation = false
- Actual `preflight --full`: 4 FAIL / 7 WARN — dashboard proof, GA4 trust, official sources และ live release

ความเชื่อมั่นสูงต่อสถานะระบบและ blocker เพราะอิงหลักฐานรอบเดียวกันและ tests แบบ adversarial ความเชื่อมั่นต่อระยะเวลาหรือขนาดรายได้ยังต่ำ เพราะยังไม่มี trusted paid baseline จึงไม่ควรทำ forecast รายได้ในตอนนี้

ไม่มีการโพสต์, deploy, commit, push, tracker click, เปลี่ยน publication authorization หรือสร้างยอดธุรกรรมจากงานนี้
