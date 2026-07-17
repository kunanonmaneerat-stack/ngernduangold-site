# CC-REPORT — SEO Strike (order 17 ก.ค. 2026)

วันที่รายงาน: 18 ก.ค. 2026 (ทำงานคืน 17 ก.ค.) · commit หลัก: `3955714` · สถานะ: **เสร็จครบ Definition of Done**

## สรุป 1 บรรทัด

FIX-2 + FIX-3 ขึ้น live แล้ว (commit เดียว `3955714`), FIX-1 ไม่ต้องทำซ้ำเพราะ implement ไปแล้ว 10 ก.ค. — ยืนยันด้วย acceptance curls ทุกข้อผ่าน, gates ผ่านหมด, `affiliate_click` ยิงจริงทั้ง 2 หน้า

## FIX-1 — canonical / URL ซ้ำ ⚠️ decision different from order

**ไม่ได้ implement ใหม่** — งาน URL-consistency 10 ก.ค. (commit `35c9a76`) ครอบคลุมทุกข้อของ FIX-1 อยู่แล้ว:
canonical extensionless ทุกหน้า + per-page 301 (`.html` → extensionless) ใน `_redirects` + sitemap extensionless + post-build href normalizer

รอบนี้จึงรัน **acceptance checks กับ live** แทน (17 ก.ค. หลัง deploy):

| Check | ผล |
|---|---|
| `curl -I /credit-card-salary-30000-2026.html` | **301** → `Location: /credit-card-salary-30000-2026` ✓ |
| `<link rel="canonical">` ของหน้า 30000 | `https://ngernduangold.com/credit-card-salary-30000-2026` (ไม่มี .html) ✓ |
| `/` · `/kept-savings-2026` · `/debt-calculator` · `/links` | 200 ทั้งหมด ✓ |
| sitemap.xml มี URL ลงท้าย .html | ไม่มี ✓ |
| smoke ทุก URL ใน `gsc-pages.csv` (แบบ extensionless) | **15/15 = 200** ✓ |

## FIX-2 — `/car-still-installment-loan-2026` ✅ live

- Title/meta ตามไฟล์ order เป๊ะ: `รถผ่อนไม่หมด จำนำได้ไหม? ทางเลือกโอนเล่มและรีไฟแนนซ์ที่ควรรู้`
- h1 ใหม่มี "รถผ่อนไม่หมด" + h2 answer-first `รถผ่อนไม่หมด จำนำ/จัดไฟแนนซ์ได้ไหม — คำตอบสั้น` + 2 ย่อหน้าคำตอบวางเหนือเนื้อหาเดิม (เนื้อหาเดิมคงไว้ทั้งหมด)
- FAQ: แทน 2 ข้อควบช่วงอายุเดิมด้วย **4 ข้อ exact-match query** (รถผ่อนไม่หมดจำนำได้ไหม / เกิน 20 ปี / เกิน 25 ปี / 15 ปี) — คำตอบจากไฟล์ order, **ลบ [ตรวจสอบ] ทุกจุดหลังรีวิวถ้อยคำเป็นกลาง-ไม่การันตี**, ข้อเดิมอีก 3 ข้อคงไว้ → รวม 7 ข้อ
- FAQPage JSON-LD: generator สร้างอัตโนมัติจาก faqs list → LD 7 คำถาม **ตรงกับข้อความที่มองเห็นบนหน้า** (ตามข้อกำหนดใน order) — ตรวจ live แล้ว valid

## FIX-3 — `/credit-card-salary-30000-2026` ✅ live

- Title/meta ตามไฟล์ order เป๊ะ: `เงินเดือน 30000 วงเงินบัตรเครดิตได้เท่าไหร่? เช็กเพดานก่อนสมัคร`
- Section ใหม่ h2 `เงินเดือน 30,000 ขอวงเงินได้ประมาณเท่าไหร่` วางบนสุดหลัง h1:
  - เกณฑ์ ธปท.: รายได้ ≥30,000 แต่ <50,000 → เพดาน **ไม่เกิน 3 เท่าของรายได้เฉลี่ยต่อเดือน** → ที่ 30,000 = ไม่เกิน 90,000 บาท
  - **[ตรวจสอบประกาศ ธปท.] ทำแล้วจริง**: verify จากหน้า bot.or.th (satang-story/creditcard) 17 ก.ค. — ข้อความตรง "ตั้งแต่ 30,000 บาท แต่น้อยกว่า 50,000 บาท | 3 เท่าของรายได้เฉลี่ยต่อเดือน" → ลบ marker แล้ว + คง hedge "ไม่ใช่วงเงินที่รับประกันว่าจะอนุมัติ" + "โปรดตรวจประกาศฉบับล่าสุดประกอบ"
- ไม่มีเลขดอกเบี้ยทุกจุด (เท่าของรายได้ = เกณฑ์ทางการ ไม่ใช่ดอกเบี้ย — ตาม iron rule ที่ order อนุญาต)

## Gates (รันหลัง patch + rebuild)

- `py_compile` build_site.py ผ่าน · build ผ่าน (SITE_BASE + GA จริง)
- `tools/postdeploy_smoke.py --src site`: **67/67 หน้า · ปุ่ม atth.me 193** ✓
- `pipeline/link_check.py`: pages 74 · broken 0 ✓
- `check_affiliate_links.py`: **17/17 · 0 problem** ✓ (ไม่มีลิงก์ affiliate เพิ่ม/หาย)
- disclosure เดิมคงครบทั้ง 2 หน้า ("ข้อมูลเพื่อการศึกษา" + ประกาศลิงก์พันธมิตร) ✓

## affiliate_click ยังยิงจริง (ตรวจในเบราว์เซอร์บน live, วิธี gtag-stub + preventDefault = ไม่ปนสถิติจริง)

Flow ของไซต์ = interstitial 2 จังหวะ ทำงานครบทั้งสองหน้า:

- **car-still**: click ปุ่ม → `interstitial_view` (srisawad) → กดไปต่อ → `interstitial_continue` + **`affiliate_click`** พร้อม `sub_id=website_car-still-installment-loan-2026.html_srisawad` ✓
- **salary-30000**: ลำดับเดียวกัน → **`affiliate_click`** พร้อม `sub_id=website_credit-card-salary-30000-2026.html_krungsri` ✓

(หมายเหตุ: sub_id ยังมี `.html` ในชื่อหน้า — เป็น scheme attribution เดิมที่ตั้งใจคงไว้ ไม่เกี่ยวกับ URL ที่ผู้ใช้เห็น ไม่ได้แตะ)

## Commits

| commit | เนื้อหา |
|---|---|
| `35c9a76` (10 ก.ค.) | FIX-1 เดิม: canonical extensionless + 301 + sitemap + normalizer |
| `3955714` (17 ก.ค.) | FIX-2 + FIX-3 ใน build_site.py (commit สุดท้ายของ push ตาม GOTCHA Netlify ignore-rule) |
| commit ถัดไป | report ฉบับนี้ (automation-log = path ที่ Netlify ignore → ไม่เกิดบิลด์) |

หมายเหตุ decision: order ให้ "commit เป็นช่วงๆ แยกตาม FIX" — FIX-2/FIX-3 อยู่ในไฟล์เดียวกัน (build_site.py) และกฎ GOTCHA บังคับให้ commit ที่แตะ build_site.py เป็น commit สุดท้ายของ push จึงรวมเป็น commit เดียว message ระบุทั้งสอง FIX ชัดเจน; FIX-1 ไม่มี commit ใหม่เพราะไม่ได้แก้อะไร

## แนะนำ owner (optional)

เข้า GSC UI → URL Inspection → **Request indexing** 2 URL นี้เพื่อเร่ง recrawl:
1. `https://ngernduangold.com/car-still-installment-loan-2026`
2. `https://ngernduangold.com/credit-card-salary-30000-2026`
(GSC verified เฉพาะ property netlify.app — ถ้า inspect บน .com ยังไม่ได้ ให้ verify .com ก่อนตาม runbook GSC เดิม)

## Definition of Done — เช็คครบ

- [x] FIX-1 curls ผ่านทุกข้อ (ของเดิมยังทำงาน)
- [x] FIX-2/3 ขึ้นเว็บจริง canonical ถูก
- [x] ไม่มี [ตรวจสอบ] หลุด (ตรวจทั้ง source และ live HTML)
- [x] ไม่มีเลขดอกเบี้ย
- [x] build + gates ผ่านก่อน push
- [x] affiliate_click ยิงจริงทั้ง 2 หน้า
- [x] report ฉบับนี้
