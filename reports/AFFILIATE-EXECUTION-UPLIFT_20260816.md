# ผลการยกระดับระบบ Affiliate และสถานะพร้อมดำเนินการ

> ตรวจสถานะจริงล่าสุด: 17 สิงหาคม 2026 เวลา 01:44 น. (Asia/Bangkok)  
> ขอบเขต: วิเคราะห์ แก้ระบบ วัดผล ตรวจความสอดคล้อง และเตรียม release ในเครื่อง โดยไม่โพสต์ ไม่ deploy ไม่ acknowledge แหล่งข้อมูล และไม่เปลี่ยนสิทธิ์เผยแพร่แทนเจ้าของ

## Executive Summary

วันที่ 16 ส.ค. ระบบยกระดับจาก **Maturity 30/100 เป็น 45/100** และ learning readiness จาก **0/3 เป็น 2/3** ได้จริง เมื่อขึ้นวันที่ 17 ส.ค. freshness contract เคยลดชั่วคราวเป็น 30/100 และ 1/3 เพราะ revenue coverage หมดอายุ จากนั้นตรวจ AccessTrade ผ่านเซสชันที่ล็อกอินแล้วและ reconcile หลักฐาน schema 5 ถึงวันที่ 17 ส.ค. ทำให้สถานะปัจจุบันกลับเป็น **45/100 และ 2/3**: GSC และ revenue `CURRENT`; GA4 ยัง `UNTRUSTED`

งาน local ที่ตรวจครบอยู่ที่ **80/100**: inventory, exact release, attribution และ offer safety ผ่านทั้งหมด แต่ production ยังอยู่ที่ **20/100** เพราะยังเป็น release เก่า จึงยังไม่ควรเพิ่ม traffic หรือเริ่ม pilot จนกว่าจะผ่านขั้นตอน owner review และ deploy แบบผูก manifest

หลักฐาน revenue ล่าสุด reconcile ถึง 17 ส.ค. แล้ว: **paid 0 บาท / 0 รายการ** และ **pending 35 บาท / 1 รายการ** Dashboard แสดงสองสถานะแยกกัน และ pending ไม่ถูกนับเป็นรายได้หรือ North Star

วงจรจริงรอบล่าสุดจบแบบ `FAILED_VALIDATION` ตามหลัก fail-closed ไม่ใช่ระบบล้ม: guard 8/8 ผ่าน แต่ระบบตั้งใจไม่เลือก winner, ไม่ scale และไม่โพสต์ เพราะยังมี hard blocker 3 กลุ่ม ได้แก่ analytics, official-source review และ publication inputs

## ความคืบหน้าที่วัดได้

| ตัวชี้วัด | ก่อนยกระดับ | ปัจจุบัน | เป้าหมายถัดไป |
|---|---:|---:|---:|
| Maturity score | 30/100 | **45/100 ปัจจุบัน** | >=90/100 และไม่มี hard blocker |
| Learning readiness | 0/3 | **2/3 ปัจจุบัน** (GSC + revenue) | 3/3 |
| Local release/funnel | 80/100 | **80/100** | ผ่านคงที่ + receipt/authority |
| Production release/funnel | 20/100 | **20/100** | >=80/100 หลัง exact deploy |
| Paid affiliate revenue | ไม่ทราบอย่างเชื่อถือได้ | **CURRENT: 0 บาท / 0 paid** | รายได้ paid จริง >0 |
| Pending commission | ไม่ reconcile | **CURRENT: 35 บาท / 1 pending** | ติดตามจนเป็น paid/rejected/refunded |

คะแนนปัจจุบัน 45 มาจากหลักฐานสด 10/10, guardrails 20/20 และ revenue ledger ที่เชื่อถือได้ 15/15 ส่วน analytics, sources, publication และ paid outcome ยังได้ 0 ระบบไม่ให้คะแนนจาก pending หรือ snapshot ที่หมดอายุ

## สิ่งที่แก้และยืนยันแล้ว

### 1. Revenue ไม่รายงานศูนย์ปลอมอีกต่อไป

- ตรวจหลักฐานจากบัญชี AccessTrade แบบ read-only พบ 1 conversion มูลค่า 35 บาท สถานะรออนุมัติ
- บันทึกเป็น lifecycle event แบบ private และ reconcile แบบ schema 5 ด้วย raw CSV + browser evidence + receipt + frozen source ที่ hash-bound และตรวจซ้ำก่อน/หลังติดตั้ง
- แยก `paid`, `pending`, `approved`, `rejected`, `cancelled`, `refunded` ชัดเจน
- Provider/transaction IDs ถูกเก็บเฉพาะ hash; Sub ID ไม่มี จึงบังคับ attribution เป็น `UNATTRIBUTED / MERCHANT_TOTAL_ONLY` และ `page_cta_attribution_ready=false`
- Dashboard ปัจจุบันแยก paid 0 และ pending 35 ชัดเจน ห้ามใช้ pending เป็น North Star

### 2. GSC พร้อมใช้ตัดสินใจ

- ดึงข้อมูลจริงแบบ read-only รอบใหม่ช่วง finalized 28 วัน: 18 ก.ค.–14 ส.ค. 2026
- 16 query rows, 24 page rows, ไม่ถูกตัดทอน และ hash ตรง
- ผล query ปัจจุบัน: **301 impressions / 0 clicks** (16 query rows; page table 24 rows / 343 impressions / 0 clicks)
- สถานะ `CURRENT`; ใช้เป็นหลักฐานการมองเห็นบน Search ได้

### 3. GA4 บอกสาเหตุจริงครบ ไม่ซ่อน blocker

GA4 ยัง `UNTRUSTED` เพราะมีสองเงื่อนไขพร้อมกัน:

1. private egress ปัจจุบันอยู่นอกช่วงที่ตั้งเป็น internal traffic
2. internal-traffic coverage ยังไม่ครบหน้าต่างตัดสินใจ 28 วัน

ระบบจึงแสดง GA4 เป็น `UNAVAILABLE` และไม่ใช้ sessions/clicks เก่าเลือกผู้ชนะ เวลาโพสต์ หรือ scale การทำงาน

### 4. Pilot measurement ถูกยกระดับเป็น session-scoped

เพิ่ม contract ที่ผูก click session, qualified landing session, landing page, content, placement, CTA และ acquisition เข้าด้วยกัน พร้อม pagination/completeness/hash checks ปิดช่องที่ session เข้าหน้าอื่นแล้วค่อยคลิกจน numerator สูงเกินจริง

ตัว measurement design พร้อมแล้ว แต่ operational pilot ยัง `BLOCKED` จน GA4 trusted, มี placement receipt และมี execution authority แยกต่างหาก

### 5. Official sources สดและ trace ได้ครบ

- ตรวจ 31/31 แหล่งสำเร็จ, errors 0, changed 0
- ยังมี **26 รายการรอ owner review/acknowledgement**
- knowledge items kn-29..kn-44 ถูก map ครบ 16/16 และยังบล็อกเผยแพร่ตามจริง
- คิวแก้ถูกต้องคือ `review_official_sources` ไม่ใช่ดึงข้อมูลซ้ำโดยไม่จำเป็น

### 6. Local release พร้อมเชิงเทคนิค แต่ production ยังไม่ตรง

Local audited package:

- release manifest schema 2: 117 files / 14 source inputs / 4 contracts
- content-addressed candidate: 118 archive members / 104,235,390 bytes / SHA-256 ผูก receipt และ `deployment_authorized=false`
- local smoke 70/70 pages
- affiliate CTAs 140 จุดผ่าน attribution contract
- merchant gate: 16 products / 2 promotions / 140 placements / 77 documents
- local score 80/100; publication ยัง `NOT_AUTHORIZED`

Production ปัจจุบัน:

- score 20/100
- exact release findings 72
- attribution findings 624
- offer-safety findings 196

ดังนั้น local package เป็น candidate ที่ตรวจแล้ว แต่ยังไม่ใช่หลักฐานว่า production ปลอดภัยจนกว่าจะ deploy exact package และตรวจหลัง deploy อีกครั้ง

## คิวงานที่ถูกต้องตามลำดับ

| ลำดับ | เจ้าของงาน | งาน | เกณฑ์ผ่าน |
|---:|---|---|---|
| 1 | Owner | ตรวจ claim packet 26 รายการและ acknowledge ทีละรายการ | snapshot ใหม่ pending=0, errors=0 |
| 2 | Owner | ยืนยัน private egress สำหรับ GA4 ก่อนแก้ช่วง exclusion | หลักฐาน trust ใหม่ไม่เปิดเผยค่า private |
| 3 | Codex หลังข้อ 2 | ซ่อม GA4 trust แล้วเก็บ bundle 28 วันใหม่ | GA4 `CURRENT` + `TRUSTED`; learning=3/3 |
| 4 | Owner-authorized release | deploy exact manifest-bound local package | live exact/attribution/offer findings=0 |
| 5 | Codex + owner receipt | เปิด bounded pilot หนึ่งตัวแปร | score>=90, receipt/authority ครบ, paid outcome เป็น North Star |

หากยืนยัน/แก้ GA4 coverage วันที่ 16 สิงหาคม 2026 หน้าต่างสะอาด 28 วันจะครบเร็วสุดประมาณ **12 กันยายน 2026** ก่อนหน้านั้นใช้ได้เฉพาะ diagnostics ห้ามตัดสิน winner หรือ scale

## ผลตรวจรอบสุดท้าย

- Pipeline tests: **118/118 PASS**
- Preflight adversarial contract: **251/251 PASS**
- Release/funnel readiness: **25/25 PASS**
- Release candidate adversarial contract: **24/24 PASS**
- Predeploy acceptance: ผูก candidate receipt เพิ่มเป็น **11/11 PASS** หลัง final repack
- `git diff --check`: PASS (มีเฉพาะคำเตือน line-ending)
- Actual preflight วันที่ 17 ส.ค.: **2 FAIL / 7 WARN** — GA4 trust และ official reviews; live release parity ยังเป็น blocker แยกใน release readiness (production 20/100)
- Actual local-safe improvement loop วันที่ 17 ส.ค.: **Maturity 45**, learning 2/3, growth experiment 0; GA4 ต้องแก้ trust ก่อน repull

## การยกระดับรอบปิดงาน 17 สิงหาคม

- `run_daily.cmd` และ `run_weekly.cmd` ไม่ปล่อยให้ GA4/GSC/link-health ที่ล้มจากเครือข่ายบัง media QA, dashboard, improvement diagnostics และ final preflight อีกต่อไป แต่ยังสะสม exit code เป็น failure ตามเดิม
- รัน `run_weekly.cmd` จริงแล้วได้ exit รวม 2 ตามคาด: GA4 ถูกบล็อกก่อน credential/network, GSC ยังรีเฟรชสำเร็จ, weekly report และ improvement evidence ถูกเขียนต่อ และไม่มี growth action
- `ga4_pull.py` หยุดก่อนสร้างโฟลเดอร์ โหลด credential หรือแตะ API หาก capture trust ไม่ผ่าน และ `TrustResult`/uptime stdout/JSON/self-test ไม่แสดง IP หรือ CIDR
- Netlify trigger ครอบคลุม `.system_control/content_manifest.json` และ `tools/comply_gate_stitch.py` ที่ build อ่านจริง; release provenance เพิ่มจาก 12 เป็น 14 inputs
- เพิ่ม deterministic candidate archive และ receipt ที่ตรวจสมาชิกทุกไฟล์, fixed ZIP metadata, tracked-state hash และ untracked-content hash; adversarial tests ยืนยันว่าการแก้เนื้อหาใต้ชื่อไฟล์เดิมทำให้ receipt ใช้ไม่ได้ และ receipt ห้ามอ้าง deployment/rollback authority
- Source review แยกผลชัดเจน: 21 แหล่งรองรับ claim; `kn-29` และ `kn-35` ต้อง COPY_FIX+SOURCE_ADD; `kn-40`, `kn-42`, `kn-43` ต้อง SOURCE_ADD; `kn-44` ต้อง OWNER_JUDGMENT จากสัญญาและยอดปิดจริง
- ตรวจ AccessTrade ผ่านเซสชันที่เข้าสู่ระบบแล้วแบบอ่านอย่างเดียว โดยใช้ `วันที่เกิดผล` + `สถานะทั้งหมด` + `ทุกแคมเปญ` ช่วง 19 ก.ค.–17 ส.ค. 2026: พบ KTC Proud 1 conversion สถานะ `PENDING` ผลตอบแทน 35 บาท, approved/paid 0 และ Sub ID report ว่าง จึงจัดเป็น `MERCHANT_LEVEL_UNATTRIBUTED` เท่านั้น ไม่เลือกหน้า/CTA ผู้ชนะ ไม่ใช้ raw clicks/CVR/EPC เพื่อ scale และไม่ได้คลิกลิงก์ affiliate

## คำตัดสิน

ระบบมีความน่าเชื่อถือและเรียนรู้ได้ดีขึ้นอย่างชัดเจน แต่ยังไม่สมควรโพสต์หรือ deploy ต่อแบบอัตโนมัติในขณะนี้ การหยุดที่จุดนี้เป็นการรักษาประโยชน์ของเจ้าของ เพราะช่วยป้องกันการส่ง traffic ไปยัง production ที่ attribution/offer ยังล้าสมัย และป้องกันการตัดสินใจจาก GA4 ที่ยังปนเปื้อน

ขั้นตอนที่ให้ผลตอบแทนสูงสุดต่อไปคือ **owner review 26 sources + owner ยืนยัน GA4 private egress** จากนั้น Codex สามารถทำส่วนที่เหลือต่อได้ทันทีตามคิว โดยไม่ต้องรื้อระบบใหม่

ไม่มีการโพสต์, deploy, commit, push, source acknowledgement, เปลี่ยน publication authorization, คลิกลิงก์ affiliate หรือสร้างยอดธุรกรรมจากงานรอบนี้
