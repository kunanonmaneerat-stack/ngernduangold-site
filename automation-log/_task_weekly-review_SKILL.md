---
name: ngernduangold-weekly-review
description: สเปก local-only สำหรับรายงานทบทวนรายสัปดาห์ — canonical GA4/GSC/verified revenue + policy/ledger/receipts
---

⛔ LOCAL-ONLY EVIDENCE REVIEW: อ่านสถานะปัจจุบันจาก `.system_control/policy.json` เท่านั้น และใช้เฉพาะหลักฐาน local ที่มีอยู่ ห้ามรัน `run_weekly.cmd`/Run now, web/API/browser/login, โพสต์/ตอบ/ตั้งเวลา, เปิด tracker, สร้าง test traffic, แก้ scheduler, commit/push/deploy หรือเปลี่ยนสถานะภายนอก ช่องหรือ gate ที่ไม่มีหลักฐานสดให้เป็น `UNKNOWN/BLOCKED` ห้ามอาศัยกฎ Pantip หรือโควตาเก่าในไฟล์นี้

ทำ "รายงานทบทวนรายสัปดาห์" ของโปรเจกต์ affiliate การเงินไทย แบรนด์ "เงินเดือนสมองทอง" แล้วสรุปสั้นๆ เป็นภาษาไทย เน้น actionable. ทำเงียบๆ อย่า re-derive สิ่งที่รู้แล้ว

บริบท: เว็บ ngernduangold.com (โดเมนจริง) · ฮับ /links · GA4 property "ngernduangold web" Measurement ID G-17PPE0M1B8 · GSC property https://ngernduangold.com/ · AccessTrade publisher.accesstrade.in.th · FB เพจหลัก id 583765282304956
เป้าหลัก: verified affiliate revenue ที่กระทบยอดได้ รายได้สินค้าเจ้าของเองต้องมี paid+fulfilled receipt แยกต่างหาก; traffic/click เป็นเพียงสัญญาณต้นทางและไม่ใช่รายได้
หมายเหตุ: follower FB 1,000 เป็นฐานเก่า reach แทบ 0 · ก๊อกคลิกพิสูจน์แล้ว = Facebook + direct (bio) · ตั้งแต่ 18 ก.ค. bio Threads มี UTM แล้ว (utm_source=threads&utm_medium=bio)

🧭 ยุทธศาสตร์ปัจจุบัน (21 ก.ค. 2026 เจ้าของเคาะ = patient SEO งบศูนย์): ใช้ GSC เป็นตัววัดหลักได้ **เฉพาะเมื่อ canonical GSC state = `CURRENT / READY` ในรายงานรอบเดียวกัน**; ถ้าเป็น `STALE_WINDOW`, `INVALID_*`, `UNAVAILABLE` หรือ marker หาย ให้รายงาน `BLOCKED/UNKNOWN` และห้ามใช้ตัวเลขเลือกคีย์/หน้า/สั่งปรับ SEO · GA4 รายวันเงียบไม่ใช่วิกฤต แต่จะใช้ตัดสินได้เฉพาะ `CURRENT / READY` เช่นกัน · เป้าเฝ้าคือ 2 cluster: (1) รถผ่อนไม่หมด/จำนำ → car-still-installment-loan-2026 (2) บัตรเครดิตเงินเดือน 30000 → credit-card-salary-30000-2026 · เมตริกชัยชนะ = อันดับ 2 หน้านี้ขยับต่ำกว่า 30 · lever งบศูนย์ = internal link + freshness · คาดเห็นผล 6–12 สัปดาห์

ขั้นตอน:0. **WINDOWS ARTIFACT CONSUMER (ห้ามรันซ้ำ):** อ่าน `automation-log/weekly-growth-<YYYYMMDD>.md` และ schema-3 terminal receipt ของ `ngernduangold_weekly` ที่มีอยู่เท่านั้น `FINISHED + COMPLETED_WITH_BLOCKERS` = `COMPLETED_BLOCKED` แม้ final_rc=2; `FINISHED + COMPLETED` = `COMPLETED`; `ABORTED/RUNNER_FAILED` = `RUNNER_FAILED`; ไม่มีรอบที่ถึงกำหนด = `MISSED`; หลักฐานอ่านไม่ได้/ไม่ hash-valid = `UNKNOWN`. ใช้ weekly-growth ต่อได้เมื่อ receipt ผ่าน contract, step `weekly_growth_review` rc=0, อยู่ใน SLA และ marker ครบเท่านั้น มิฉะนั้น `BLOCKED` และห้ามสร้าง artifact ใหม่เอง
0a. **CANONICAL TRUST (บังคับ):** ใน `weekly-growth-<YYYYMMDD>.md` ต้องมีหัวข้อ `Canonical evidence states — ห้ามเขียนยกระดับ` และ marker `canonical-evidence-state:v1`. คัดลอก state ของ GA4, GSC และ verified affiliate revenue ลงรายงานปลายทางแบบตรงตัว ห้ามสรุปจาก CSV ดิบ/รายงานเก่า/ตัวเลขที่อ่านได้ว่า `CURRENT`, `READY`, `TRUSTED`, “เชื่อได้”, “ยอดจริง” หรือ 0 ถ้า canonical source ไม่ผ่าน. ถ้าหัวข้อหรือ marker หาย ให้ทั้งสามแหล่งเป็น `UNKNOWN/BLOCKED` ทันที
1. อ่าน release attestation, live-local parity และ offer/product gate จากหลักฐาน local; ห้ามเปิดเว็บ ถ้า `letter-kit-199` ยัง `PROMISED-BUT-MISSING` ให้รายงาน blocker และห้ามเสนอ CTA/การรับชำระ
2. **GA4:** ใช้ sessions/affiliate_click/engagement เพื่อวินิจฉัยและเลือก winner/หน้ารั่วได้เฉพาะ canonical GA4 = `CURRENT / READY`; นอกนั้นแสดงดิบพร้อม `BLOCKED` และห้ามออก action จากตัวเลข
3. **GSC:** ใช้ clicks/impressions, striking-distance และสถานะ index เพื่อเลือกคีย์/หน้าได้เฉพาะ canonical GSC = `CURRENT / READY`; นอกนั้นห้ามเรียก GSC ว่า “ตัวหลักที่เชื่อได้” และห้ามสร้างข้อสรุปแนวโน้มจากไฟล์เก่า
4. **FB reach:** ใช้ post ledger/metrics/evidence receipt local ที่อยู่ใน SLA เท่านั้น; ไม่มีหลักฐานให้ `UNKNOWN` ห้ามเปิดเพจ
5. **TikTok:** อ่าน state และ evidence local เท่านั้น; `paused`/`retired` = `SKIP` ห้ามเปิดโปรไฟล์หรือเสนอให้กลับมาทำ
6. **AccessTrade:** ใช้ canonical reconciled ledger เท่านั้น; pending/click/conversion ไม่ใช่ paid revenue และห้าม login
7. **🎯 North Star:** อ่าน verified affiliate revenue จาก canonical state เดียวกัน; รายงานตัวเลข/ศูนย์/แนวโน้มได้เฉพาะ `CURRENT / READY` ถ้าไม่ผ่านให้ `UNAVAILABLE — ห้ามตีความเป็น 0` รายได้สินค้าเจ้าของเองต้องมี paid+fulfilled receipt แยกต่างหาก มิฉะนั้น `UNAVAILABLE`; ห้ามใช้ Gumroad คนละสินค้าแทน letter kit
8. อ่าน automation-log/CONSULT-ANSWERS_20260718.md ส่วนสังเคราะห์ — รายงานความคืบหน้าเทียบแผน 14 วัน (sessions เป้า 400-500/สัปดาห์)

สรุปออกมาเป็น:
- 📊 ตัวเลขสัปดาห์นี้: แสดงเฉพาะ state ที่ `READY`; verified affiliate revenue แยกจาก own-product paid+fulfilled evidence และห้ามใส่ตัวเลขแทน `UNAVAILABLE`
- 🔥 winner/หน้ารั่ว/striking-distance/action ต้องเขียน `[basis=GA4]`, `[basis=GSC]`, `[basis=REVENUE]` หรือ `[basis=LOCAL_POLICY]` และแสดงได้เฉพาะ source ที่ `READY`; เมื่อ source ถูกบล็อก อนุญาตเฉพาะ data-repair action `[basis=LOCAL_POLICY]`
- 🎬 TikTok: ความคืบหน้า vs kill-criterion
- ✅ อะไรเวิร์ก / ❌ อะไรไม่เวิร์ก (แยก "พิสูจน์แล้ว" จาก "ยังข้อมูลน้อย")
- 🎯 โฟกัส 1 อย่างสัปดาห์หน้า + 2-3 action โดยทุกข้อมี evidence basis ตามกฎข้างบน
- เตือนเฉพาะ routine/state ที่อ่านได้จาก policy และ receipt ปัจจุบัน ห้ามท่องโควตา วัน หรือสถานะเก่า

ถ้าขั้นไหนทำไม่ได้ให้เป็น `UNKNOWN/BLOCKED` และห้ามข้าม canonical guard เขียนกระชับโดยแยกข้อเท็จจริง สิ่งไม่ทราบ และข้อเสนอซ่อม local

เขียน draft ที่ path ตรงตัวแล้วรัน `py pipeline\report_trust_guard.py --source-report automation-log\weekly-growth-<YYYYMMDD>.md --report automation-log\WEEKLY-REVIEW_<YYYYMMDD>.draft.md`. exit=0 เท่านั้นจึงยอมรับ/ส่งรายงานได้ ถ้า nonzero, source marker หาย หรือ source เกิน SLA ให้หยุดและส่งเฉพาะสถานะ `BLOCKED`; ห้ามส่ง draft หรือ actionable findings
---
## 📜 proof-of-run (local only)
เขียน `started` ก่อนงานที่อาจล้ม และเขียน terminal row ตามจริง: `ok` เฉพาะเมื่อ source+guard ผ่าน, `partial` เมื่อมี UNKNOWN/BLOCKED ที่รายงานได้, `fail` เมื่อ runner/guard ล้ม ห้ามใช้ Git เป็น proof-of-run
