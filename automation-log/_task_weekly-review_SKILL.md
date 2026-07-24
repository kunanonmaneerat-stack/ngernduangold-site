---
name: ngernduangold-weekly-review
description: รายงานทบทวนรายสัปดาห์ (จันทร์ 9 โมง) — GA4 + GSC + เบราว์เซอร์ (FB/TikTok) + AccessTrade + North Star 199฿ → เลือกโฟกัสสัปดาห์
---

⛔ POSTING-POLICY: อ่าน C:\Users\nL_ku\ngernduangold-site\automation-log\POSTING-POLICY_antispam_20260702.md (ฉบับล่าสุด) ก่อนทุกครั้ง · Pantip = เฟส 1 (17–30 ก.ค.) ตอบกระทู้เท่านั้น ≤3/สัปดาห์ เว้นวัน ไร้แบรนด์/ลิงก์ — ห้ามแนะนำเกินโควตานี้เด็ดขาด · ก่อนโพสต์ช่องใดๆ ต้องรัน `py pipeline\qa_gate.py --quota <ช่อง>` (exit≠0 = ห้ามโพสต์) และข้อความต้องผ่าน comply_gate text-dedup

ทำ "รายงานทบทวนรายสัปดาห์" ของโปรเจกต์ affiliate การเงินไทย แบรนด์ "เงินเดือนสมองทอง" แล้วสรุปสั้นๆ เป็นภาษาไทย เน้น actionable. ทำเงียบๆ อย่า re-derive สิ่งที่รู้แล้ว

บริบท: เว็บ ngernduangold.com (โดเมนจริง) · ฮับ /links · GA4 property "ngernduangold web" Measurement ID G-17PPE0M1B8 · GSC property https://ngernduangold.com/ · AccessTrade publisher.accesstrade.in.th · FB เพจหลัก id 583765282304956
เป้าหลัก: human click เข้า /links และหน้าเครื่องมือ ให้แตะ 20–30/วัน → conversion สินเชื่อ + ยอดขายชุดจดหมาย 199฿
หมายเหตุ: follower FB 1,000 เป็นฐานเก่า reach แทบ 0 · ก๊อกคลิกพิสูจน์แล้ว = Facebook + direct (bio) · ตั้งแต่ 18 ก.ค. bio Threads มี UTM แล้ว (utm_source=threads&utm_medium=bio)

🧭 ยุทธศาสตร์ปัจจุบัน (21 ก.ค. 2026 เจ้าของเคาะ = patient SEO งบศูนย์): **นำด้วย GSC เป็นตัววัดหลัก · GA4 รายวันเงียบ = ปกติของเกมนี้ ห้ามตีความเป็นวิกฤต** · ตัดสินที่ "เทรนด์ GSC รายสัปดาห์" ไม่ใช่ sessions รายวัน · เป้าเฝ้าคือ 2 cluster ที่มี impression จริง (ดู automation-log/SEO-OPPORTUNITY_20260721.md): (1) รถผ่อนไม่หมด/จำนำ → car-still-installment-loan-2026 (2) บัตรเครดิตเงินเดือน 30000 → credit-card-salary-30000-2026 · เมตริกชัยชนะ = อันดับ 2 หน้านี้ขยับต่ำกว่า 30 (ตอนนี้ 36–52) · lever ที่ทำได้งบศูนย์ = internal link + freshness · คาดเห็นผล 6–12 สัปดาห์ · เลิกคาด sessions 400-500/สัปดาห์ (ฐานเก่าก่อน pivot)

ขั้นตอน:0. **AUTO FAST-PATH (ทำก่อนเสมอ):** รัน `cmd /c C:\Users\nL_ku\ngernduangold-site\pipeline\run_weekly.cmd` ผ่าน Desktop Commander → สร้าง `automation-log/weekly-growth-<YYYYMMDD>.md` → ใช้เป็นฐานข้อ 2/3
1. เช็คเว็บออนไลน์: web_fetch https://ngernduangold.com/debt-letter-kit (โหลดได้ + CTA LINE อยู่)
2. **GA4:** จาก weekly-growth file: sessions ต่อ source (แยก utm_source=fb/ig/threads/yt/line ที่เริ่มวัดได้แล้ว) · affiliate_click ต่อช่อง · engagement · หน้า winner/หน้ารั่ว
3. **GSC:** clicks/impressions + striking-distance queries + สถานะ index 4 หน้าใหม่ 18 ก.ค. (loan-approval-compare, car-pawn-not-paid-off, old-car-financing-20years, credit-card-salary-30000) และ 2 หน้า SEO-strike 17 ก.ค.
4. **FB reach (เบราว์เซอร์):** เปิดเพจ FB ดูโพสต์สัปดาห์นี้: ไลก์/คอมเมนต์/แชร์ที่มองเห็น โดยเฉพาะโพสต์ที่มี link-in-comment (Meta token ยกเลิกถาวร — ห้ามใช้ Meta MCP)
5. **TikTok:** เปิดโปรไฟล์ @ngernduangold ดู views คลิปสัปดาห์นี้ — เทียบ kill-criterion: ≥30 วัน view เฉลี่ย <300 → เตือนทบทวน (batch3 มีเสียงพูดเริ่ม 27 ก.ค. ให้เวลาใหม่ถึง 10 ส.ค.)
6. **AccessTrade:** conversion + payout ต่อ sub_id ถ้า login ได้
7. **🎯 North Star (สำคัญสุด — ตามผลปรึกษา 2 โมเดล 18 ก.ค.):** (1) **ยอดขายชุดจดหมาย 199฿ ที่โอนจริง** — ขายผ่าน LINE @804qodya (คนพิมพ์ "ขอชุดจดหมาย"/โอนพร้อมเพย์ — รัน `py tools\sales_week.py` อ่านยอดจริง (199฿/59฿/affiliate) จาก automation-log/sales-log.jsonl แยก channel_source · ว่าง=เตือนเจ้าของบันทึกทุกดีลด้วย `py tools\log_sale.py --product letter-kit-199 --amount 199 --source line` (ห้าม PII)) ← **รายได้จริงคือ metric ตัดสิน ไม่ใช่ micro-conversion** (2) LINE OA friends เพิ่ม/สัปดาห์ (manager.line.biz insights) (3) จำนวนคนพิมพ์ "จดหมาย/ขอจดหมาย" (4) traffic /debt-letter-kit + /debt-calculator
8. อ่าน automation-log/CONSULT-ANSWERS_20260718.md ส่วนสังเคราะห์ — รายงานความคืบหน้าเทียบแผน 14 วัน (sessions เป้า 400-500/สัปดาห์)

สรุปออกมาเป็น:
- 📊 ตัวเลขสัปดาห์นี้: sessions รวม+ต่อ source · affiliate clicks · GSC clicks/impressions · **ยอดขาย 199฿ จริง + LINE friends ใหม่** · FB reach
- 🔥 winner + หน้ารั่ว + striking-distance
- 🎬 TikTok: ความคืบหน้า vs kill-criterion
- ✅ อะไรเวิร์ก / ❌ อะไรไม่เวิร์ก (แยก "พิสูจน์แล้ว" จาก "ยังข้อมูลน้อย")
- 🎯 โฟกัส 1 อย่างสัปดาห์หน้า + 2-3 action
- เตือน routine ที่ถูกต้อง: Pantip ≤3 ตอบ/สัปดาห์ เฟส 1 · FB คอมเมนต์ลิงก์รายวัน (อัตโนมัติแล้ว) · IG comment-CTA อ./ศ./ส.

ถ้าขั้นไหนทำไม่ได้ ข้าม + บอกตรงๆ. เขียนกระชับ ลงมือต่อได้ทันที
---
## 📜 proof-of-run (ตอนจบทุกรอบ — บังคับ)
1) `python C:/Users/nL_ku/ngernduangold-site/automation-log/log_run.py --routine ngernduangold-weekly-review --status ok --summary "สรุปสั้น 1 บรรทัด" --metrics '{}'`
2) `cd C:/Users/nL_ku/ngernduangold-site ; git add automation-log ; git commit -m "runlog: ngernduangold-weekly-review" ; git push`  (ใช้ `;` ไม่ใช่ `&&`)