# WORK ORDER → Claude Code: internal-link boost 2 หน้าเป้าหมาย SEO (21 ก.ค. 2026 · จาก Cowork)

> ยุทธศาสตร์ patient SEO (เจ้าของเคาะ 21 ก.ค. · ดู automation-log/STRATEGY-DECISION_20260721.md) · lever งบศูนย์เดียวที่ทำได้คือส่ง internal link equity ไปหาหน้า impression สูงที่อันดับยังแย่ · ข้อมูลอ้างอิง: automation-log/SEO-OPPORTUNITY_20260721.md + gsc-pages.csv

## 🎯 เป้าหมาย (พิสูจน์ด้วย GSC จริง)
เพิ่มลิงก์ภายในชี้เข้า **2 หน้านี้** (impression เยอะ อันดับแย่ ต้องดันด้วย link equity):
| หน้าเป้าหมาย | slug (ในไฟล์ = .html) | GSC ปัจจุบัน |
|---|---|---|
| A. รถผ่อนไม่หมด จำนำได้ไหม | `car-still-installment-loan-2026.html` | 92 imp · pos 52 |
| B. บัตรเครดิต เงินเดือน 30000 | `credit-card-salary-30000-2026.html` | 55 imp · pos 36 |
| C. **debt-letter-kit (หน้าขาย 199฿ North Star)** | `debt-letter-kit.html` (ถ้า slug ไม่มี .html ในโค้ด ใช้ตามจริง) | 🔴 **orphan — Google "unknown", ไม่มี referring page เลย** ต้องมีลิงก์ชี้เข้าด่วน |

## 📥 หน้าที่ให้เพิ่มลิงก์ออก (source = หน้าที่ติดหน้า 1 แล้ว มี authority · จาก gsc-pages.csv)
เพิ่ม **ลิงก์ contextual 1 อัน/หน้า** (ไม่เกินนี้ กัน over-optimization) จาก source → target ตามความเกี่ยวข้องหัวข้อ:

**🔴 เข้าเป้าหมาย C (debt-letter-kit) — สำคัญสุด แก้ orphan (เพิ่ม 21 ก.ค. 18:50):**
- หน้าเนื้อหาหนี้ที่พูดถึง "เจรจา/ลดดอกเบี้ย/จดหมายถึงเจ้าหนี้" → เพิ่มลิงก์ไป debt-letter-kit เช่น `debt-consolidation-2026.html` · `debt-restructuring-2026.html` · `pay-off-credit-card-debt-2026.html` · `debt-clinic-sam-2026.html` (เลือก 3-4 หน้าที่ context เข้ากับ "ตัวอย่างจดหมายเจรจาหนี้")
- anchor แนะนำ: **"ตัวอย่างจดหมายขอลดดอกเบี้ย/เจรจาหนี้"** หรือ **"ชุดจดหมายเจรจาเจ้าหนี้"** (ไม่มีคำต้องห้าม ไม่มีราคาในลิงก์)
- **เป้าหมาย: ให้ debt-letter-kit พ้นสถานะ orphan** (มี referring page ≥3) เพื่อให้ Google crawl+index หน้าขายจริง

**เข้าเป้าหมาย A (รถ/สินเชื่อมีหลักประกัน):**
- `debt-restructuring-2026.html` (pos 9.5) → A
- `debt-consolidation-2026.html` (pos 2) → A
- `loan-cash-2026.html` → A (ถ้ายังไม่มีลิงก์เข้า A)

**เข้าเป้าหมาย B (บัตรเครดิตตามเงินเดือน):**
- `credit-card-salary-15000-2026.html` (pos 4) → B
- `credit-card-salary-20000-2026.html` (pos 4) → B
- `credit-card-documents-2026.html` (pos 1) → B

→ ก่อนเพิ่ม: `grep -c 'car-still-installment-loan-2026' build_site.py` และ target B เช่นกัน — ถ้า source ไหนมีลิงก์เข้า target อยู่แล้ว ข้ามหน้านั้น (ไม่ซ้ำ)

## 🔧 วิธีทำ (ในไฟล์ต้นทางเดียว: build_site.py)
build_site.py มี 2 กลไกลิงก์ — เลือกใช้ **inline `.ilinks`** (เนียนกว่า related card เพราะอยู่ในเนื้อความ ส่ง signal ดีกว่า):
- แพตเทิร์นที่มีอยู่แล้ว (ลอกสไตล์): `<span class="ilinks">เกี่ยวข้อง: <a href="/title-loan-2026.html">สินเชื่อทะเบียนรถ</a> · <a href="/car-still-installment-loan-2026.html">รถยังผ่อนอยู่ จำนำได้ไหม</a></span>`
- หา body block ของแต่ละ source page (เช่น `slug...=` / `body...+=`) แล้วแทรก `.ilinks` 1 อันในย่อหน้าที่เนื้อหาเกี่ยวข้อง (เช่น ในหน้า debt-restructuring ย่อหน้าที่พูดถึงสินเชื่อมีหลักประกัน/ทางเลือกกู้)
- **href ใช้ extensionless** (`/car-still-installment-loan-2026` ไม่ต้อง .html) ตาม URL-CONSISTENCY บรรทัด 2817 (build normalize ให้อยู่แล้ว แต่เขียน extensionless ไปเลยชัดกว่า)

## ✍️ anchor text (บังคับใช้ตามนี้ — ตรง search intent + comply)
- เข้า A ใช้: **"รถผ่อนไม่หมด จำนำได้ไหม"** หรือ **"รถยังผ่อนอยู่ กู้/รีไฟแนนซ์ได้ไหม"**
- เข้า B ใช้: **"บัตรเครดิต เงินเดือน 30000 ได้วงเงินเท่าไร"** หรือ **"เงินเดือน 30000 สมัครบัตรเครดิต"**

## ⛔ COMPLIANCE (ผิดข้อเดียว = งานเสีย ห้าม deploy)
- anchor/ข้อความใหม่ **ห้ามมี**: ตัวเลขดอกเบี้ย/ค่าธรรมเนียม/% · คำ "อนุมัติง่าย/อนุมัติแน่นอน/อนุมัติไว/ไม่เช็คบูโร/การันตี/รับรองผล"
  (หมายเหตุ: related card เดิมที่มีคำ "อนุมัติง่าย อนุมัติไว" เป็น **ชื่อหน้าเดิม** ห้ามไปแก้ของเดิม — แค่ห้ามสร้าง anchor ใหม่ที่มีคำพวกนี้)
- ห้ามแตะเนื้อหา/CTA/affiliate ของหน้าอื่น · ห้ามเพิ่มลิงก์เกิน 1 อัน/source · แก้เฉพาะ build_site.py
- UTF-8 · ห้าม `git add -A`

## ✅ BUILD GATE (บังคับ — ต้อง PASS ก่อน commit)
1. `cd C:\Users\nL_ku\ngernduangold-site`
2. `set SITE_GA=G-17PPE0M1B8` (หรือ `$env:SITE_GA` ใน PowerShell) แล้ว `python build_site.py`
3. `python tools/postdeploy_smoke.py --src site` — **ต้อง PASS ทุกหน้า** (canonical/GA/affiliate listener/og) · ไม่ PASS = หยุด แก้ให้ผ่านก่อน ห้าม commit
4. verify link เพิ่มจริง: `grep -c "car-still-installment-loan-2026" site/*.html | ...` เทียบก่อน/หลัง ต้องเพิ่มขึ้นตามจำนวน source ที่แก้ · เช่นเดียวกับ credit-card-salary-30000

## 🚀 หลัง gate PASS
- `git add build_site.py site/` (เฉพาะที่เปลี่ยน) `&& git commit -m "seo: internal-link boost -> car-still + credit-card-salary-30000 from page-1 authority pages"`
- `git push origin main` (นี่คือ deploy → Netlify · internal-link ความเสี่ยงต่ำ + gate ผ่านแล้ว = push ได้เลย ไม่ต้องรอเจ้าของ) · **ยกเว้น** smoke มี assert ใดหลุด = หยุด เขียนรายงานรอเจ้าของ

## 📤 เสร็จแล้ว → cc-outbox/result-internal-link-boost-<ts>.md
รายงาน: source กี่หน้าที่แก้ · จำนวนลิงก์เข้า A/B ก่อน-หลัง · build+smoke PASS ไหม · push แล้วไหม · commit hash
