# 🔍 SEO Opportunity Map — จากข้อมูล GSC จริง (21 ก.ค. 2026, 28 วันล่าสุด)

ดึงสด `pipeline/gsc_pull.py` → gsc-queries.csv (13 query) + gsc-pages.csv (19 หน้า) · ยังไม่มี click เลย (0 ทุกแถว = คาดไว้ เว็บใหม่ ยังไม่ติดหน้า 1)

## ✅ ตรวจสุขภาพเทคนิคก่อน — เว็บจริงไม่มีบั๊ก
- canonical live = `https://ngernduangold.com/<slug>` ถูกต้อง (example.com อยู่แค่ไฟล์ build เก่าใน repo ที่ยังไม่ patch — Netlify ตั้ง SITE_BASE ตอน deploy ให้เอง ไม่กระทบ live)
- .html twin 301 → pretty URL ผ่าน _redirects แล้ว · sitemap = pretty form · robots index,follow ครบ
→ **ไม่มีงานแก้เทคนิคเร่งด่วน** ปัญหาคือ authority/อันดับ ไม่ใช่ของพัง

## 📊 ภาพจริง: query ที่มี impression (แต่ยังไม่มีคลิก)
| query cluster | impressions รวม | อันดับ | หน้าที่รับ |
|---|---|---|---|
| **รถผ่อนไม่หมด/จำนำ/รถเก่าเข้าไฟแนนซ์** | **~95** | 47–88 🔴 | car-still-installment-loan-2026 (pos 52, 92 imp) + old-car-financing-20years (pos 74) |
| **บัตรเครดิต เงินเดือน 30000** | **~65** | 32–38 🟠 | credit-card-salary-30000-2026 (pos 36, 55 imp) |

## 💡 ข้อค้นพบชี้ทิศ (สำคัญกว่าตัวเลข)
แยกหน้าเป็น 2 กลุ่มชัดเจน:
1. **หน้าที่ติดหน้า 1 แล้ว แต่ query คนค้นน้อย** (impression ต่ำ): credit-card-documents (pos 1) · debt-consolidation (pos 2) · freelance-loan (pos 2.3) · credit-card-salary-15000/20000 (pos 4) · cash-card-vs-credit-card (pos 6) · how-to-save-money (pos 6.5) · debt-restructuring (pos 9.5) — **เรารู้วิธีทำหน้าให้ติด แค่ query พวกนี้คนค้นน้อย**
2. **หน้าที่ query คนค้นเยอะ แต่เราอันดับแย่** (pos 35–52): car-still + credit-card-30000 — **query ดี แต่แข่งขันสูง โดเมนใหม่ยังสู้ authority ไม่ได้**

→ **บทสรุป: คอขวดคือ domain authority (อายุ+ลิงก์) ไม่ใช่คอนเทนต์** หน้าที่ควรติดเราเขียนดีแล้ว (car-still targeting "รถเกิน 20/25 ปี", "รถ 15 ปี" ครบใน FAQ) · สร้างหน้าใหม่เพิ่ม = ไม่ใช่ lever ที่คุ้มสุดตอนนี้ เพราะ query ที่มี impression มีหน้ารองรับดีอยู่แล้ว

## 🎯 lever เดียวที่ทำได้จริงที่งบศูนย์: internal linking ดัน 2 หน้าเป้าหมาย
โดเมน authority ต้องรอเวลา (ยุทธศาสตร์ patient SEO ยอมรับแล้ว) · สิ่งเดียวที่เราเร่งได้เองคือ **ส่ง link equity ภายในเว็บไปหา 2 หน้า impression สูง**
- หน้าที่ติดหน้า 1 แล้ว (authority สะสมบ้าง) → เพิ่มลิงก์ contextual ไปหา car-still + credit-card-30000
- เช่น: จากหน้า debt-restructuring/loan-cash/title-loan → ลิงก์ไป car-still-installment-loan · จากหน้า credit-card-salary-15000/20000 → ลิงก์ไป credit-card-salary-30000 (เชื่อม cluster เงินเดือน)

## 📋 แผนปฏิบัติ (เรียงตาม ROI · zero-budget)
1. **[ทำได้เลย·CC] internal-link injection** — เพิ่มลิงก์ contextual จากหน้า authority → 2 หน้าเป้าหมาย (ผ่าน build_site.py related-links หรือ inline) · ต้องผ่าน build gate
2. **[รอเวลา] freshness signal** — อัปเดต "อัปเดตล่าสุด" + เพิ่ม FAQ ใหม่ในหน้าเป้าหมายเป็นระยะ (Google ชอบหน้าสด)
3. **[gate 27 ก.ค.] ตัดสิน programmatic SEO** — ตอนนี้ข้อมูลบอกว่า **ยังไม่ต้องรีบสร้างหน้าใหม่จำนวนมาก** จนกว่าหน้าที่มีอยู่จะเริ่มไต่อันดับ (พิสูจน์ว่าโดเมนเริ่มมี authority ก่อน) — ป้องกันผลิตหน้าเปล่าที่ไม่ติด
4. **[วัดผล] weekly GSC** — เฝ้า 2 cluster นี้: อันดับขยับลงต่ำกว่า 30 เมื่อไร = สัญญาณ authority เริ่มมา

## ⏱️ ความคาดหวังที่สมจริง
เว็บอายุไม่กี่สัปดาห์ อันดับ 35–52 บน query แข่งสูง = ปกติ · การขยับเข้าหน้า 1 (top 10) วัดเป็น **6–12 สัปดาห์** ถ้าทำ internal link + freshness + สะสมหน้าคุณภาพต่อเนื่อง · ไม่มีทางลัดที่งบศูนย์ — นี่คือเหตุผลที่เลือก "patient SEO"

## 🔴 UPDATE 18:45 — เช็ก index จริงใน GSC (Cowork ลงมือ) เจอปัญหาใหญ่กว่าอันดับ
GSC Page indexing: **index แล้ว 30 หน้า · ยังไม่ index 89** (Discovered-not-indexed 83 · Crawled-not-indexed 2 · Alternate-canonical 4=.html twin ปกติ)

ตรวจรายหน้าสำคัญด้วย URL Inspection:
| หน้า | สถานะจริง | ทำ |
|---|---|---|
| /debt-letter-kit (**North Star 199฿**) | 🔴 "unknown to Google" + **orphan (ไม่มี referring page) + ไม่อยู่ใน sitemap ที่ Google เห็น** | ✅ request indexing แล้ว |
| /loan-cash-2026 (money hub) | 🟠 discovered-not-indexed (มีลิงก์เข้าแล้ว แต่ authority ไม่พอ) | ✅ request indexing แล้ว |
| /debt-health-check | ✅ indexed (แค่ 0 impression) | ข้าม |
| /debt-calculator | ✅ indexed (แค่ 0 impression) | ข้าม |

**ข้อค้นพบชี้ขาด:**
1. **debt-letter-kit หน้าขายจริง 199฿ Google มองไม่เห็นเลย + เป็นหน้ากำพร้า** — ต้องมี internal link ชี้เข้า (สำคัญกว่า 2 target เดิม) → เพิ่มเข้า CC order internal-link รอบหน้า
2. "0 impression" ≠ "ไม่ index" — หลายหน้า index แล้วแต่ยังไม่ติดอันดับ = ยืนยัน bottleneck คือ authority/เวลา ตรงกับยุทธศาสตร์ patient SEO
3. request indexing ช่วย nudge หน้า money ที่ discovered-not-indexed ได้ (ทำได้งบศูนย์ · quota ~10-12/วัน)

→ ทำต่อ: (ก) เครื่อง gsc-index-nudge ทยอย request หน้า money ที่ยังไม่ index วันละไม่กี่หน้า (ข) CC order ต่อไปเพิ่มลิงก์ชี้ debt-letter-kit ให้พ้น orphan
