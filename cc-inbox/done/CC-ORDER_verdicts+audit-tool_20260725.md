# WORK ORDER → Claude Code: คำตัดสิน 3 ข้อจากรายงาน internal-link + งานสั้น (25 ก.ค. 2026 · จาก Cowork)

> ตอบรายงาน `cc-outbox/result-internal-link-arch-20260724-0051.md` (งานดีมาก: orphan 9→2 · smoke 71/71 · hub→spoke + anchor แยกมุม ถูกต้องตามหลัก)
> กฎเดิม: UTF-8 · ห้าม git add -A · ห้ามแตะ secrets/ · แก้เฉพาะที่ระบุ

## ✅ คำตัดสิน 1 — cannibalization 2 คู่: **ยังไม่แตะ URL รอ GSC พิสูจน์** (ทำตามที่คุณเสนอ = ทางที่ถูก)
เหตุผล: ทั้ง 2 หน้า A (car-still 92 imp · salary-30000 55 imp) กำลังสะสมสัญญาณจาก internal link ที่เพิ่งเพิ่ม — การ merge/canonical ตอนนี้จะรีเซ็ตสิ่งที่เพิ่งลงทุนไป และขัดยุทธศาสตร์ patient SEO (ให้เวลา 6–12 สัปดาห์)
**สิ่งที่ทำแทน (งานของ Cowork ไม่ใช่ CC):** เฝ้าใน weekly-review — ถ้า **4–6 สัปดาห์ (ประมาณ 24 ส.ค. – 7 ก.ย.)** GSC ยังเห็น 2 หน้าแย่ง query เดียวกัน (ทั้งคู่ติดอันดับ 20-60 ใน query ชุดเดียวกัน) → ค่อยเลือก (ก) merge+301 หรือ (ข) canonical B→A
**CC ไม่ต้องทำอะไรกับข้อนี้ตอนนี้**

## ✅ คำตัดสิน 2 — `contact` ในฟุตเตอร์: **อนุมัติ ทำได้เลย**
เพิ่มลิงก์ `ติดต่อเรา` → /contact ในฟุตเตอร์ทุกหน้า (ต่อท้ายแถวเดียวกับ "นโยบายความเป็นส่วนตัว & การเปิดเผยข้อมูล")
- เหตุผล: ดีต่อ E-E-A-T (หน้าเงิน/การเงิน Google ให้น้ำหนักการติดต่อได้จริง) + แก้ inbound=2
- แก้ที่ template ฟุตเตอร์ใน build_site.py จุดเดียว · ข้อความ anchor: `ติดต่อเรา` · คั่นด้วย ` · ` ให้เข้ากับของเดิม

## ✅ คำตัดสิน 3 — link audit tool: **สร้างใหม่ + commit ถาวร** (อัปเดต: ทราบแล้วว่าคุณลบ `_link_audit.py` ไปตาม order เดิม — ถูกต้องแล้ว ให้สร้างใหม่ตามสเปคนี้)
สร้าง `tools/link_audit.py` (commit ถาวร) โดย**ใส่บทเรียน 3 ข้อที่คุณค้นพบเองรอบที่แล้วเข้าไปในโค้ด** เพื่อไม่ต้องค้นพบซ้ำ:
1. **นับเฉพาะ contextual link** (ตัด footer/nav/related-card ที่ซ้ำทุกหน้าออก) — และ**รายงานคู่กับ total inbound** เพื่อไม่ให้เข้าใจผิดแบบ workshop-hr (contextual=1 แต่ total=61 → ไม่ใช่ orphan ในสายตา Google)
2. **กรองหน้า `noindex` ออกจากเป้าหมาย** (เช่น 6 หน้า infographic) — ยัดลิงก์ให้หน้า noindex = เสียแรงเปล่า
3. **`index.html` ต้องนับเป็น source ได้** (กันออกเฉพาะจากการเป็น target) — บั๊กที่คุณเจอและแก้แล้ว อย่าให้หลุดกลับมา
เพิ่มเติม: docstring หัวไฟล์ (ใช้ทำอะไร · รันยังไง · อ่านผลยังไง · เกณฑ์ inbound>=3) · path ทั้งหมด relative จาก repo root · output เรียงจาก inbound น้อย→มาก + คอลัมน์ contextual/total
เหตุผลที่ต้องถาวร: ใช้ตรวจซ้ำทุกครั้งที่เพิ่มหน้าใหม่ (กัน orphan รอบใหม่) และ weekly-review/Cowork เรียกใช้ได้เอง

## ✅ BUILD GATE (สำหรับข้อ 2 เท่านั้น)
`set SITE_GA=G-17PPE0M1B8` -> `python build_site.py` -> `python tools/postdeploy_smoke.py --src site` = PASS ทุกหน้า · เช็คว่าฟุตเตอร์ทุกหน้ามีลิงก์ /contact จริง (grep นับ) · disclosure เดิมไม่หาย

## 🚀 หลัง gate PASS
- `git add build_site.py site/ tools/link_audit.py` -> commit "seo: footer contact link (E-E-A-T + inbound fix) + promote link_audit to permanent tool" -> `git push origin main`
- **push commit ที่ค้างของ Cowork ไปด้วย** (sales-log system + LINE funnel fix + order files — Cowork ไม่ push เอง)
- ย้าย order นี้ + CC-ORDER_internal-link-architecture เข้า `cc-inbox/done/`

## 📤 รายงาน -> cc-outbox/result-verdicts-20260725-<ts>.md
ข้อ 2 ฟุตเตอร์เพิ่มกี่หน้า + smoke PASS? · ข้อ 3 link_audit commit แล้ว path ไหน · push commit hash ล่าสุด · commit ของ Cowork ขึ้น remote ครบไหม

---
## 📌 หมายเหตุจาก Cowork (25 ก.ค. 01:4x) — verify แล้ว
- **PHASE 0 ยืนยันขึ้น live จริง**: hero /links = "เทียบของจริง ก่อนตัดสินใจ สมัครออนไลน์" (ต้อง fetch แบบ cache-bust `?cb=...` ถึงเห็น — CDN cache หน้า HTML ทำให้ fetch ปกติเห็นของเก่า)
- **บทเรียนสำหรับทั้งสองฝั่ง:** เวลา verify งาน deploy บน live ให้ fetch พร้อม query string สุ่ม (`?cb=<timestamp>`) เสมอ ไม่งั้นจะสรุปผิดว่า "ยังไม่ขึ้น"
- งาน internal-link wave นี้: รับทราบครบ ผลดีมาก (orphan 9→2 · 13/13 live-verified · smoke 71/71) ไม่มีข้อแก้