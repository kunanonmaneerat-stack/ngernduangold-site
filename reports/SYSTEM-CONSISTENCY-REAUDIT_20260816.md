# รายงานตรวจซ้ำความถูกต้องและความสอดคล้องทั้งระบบ

## Executive Summary

ตรวจซ้ำ ณ 16 สิงหาคม 2026 เวลา 19:23 น. เขตเวลา Asia/Bangkok แล้ว สถานะที่ถูกต้องคือ **LOCAL/CONTROL PASS แต่ PUBLICATION/DEPLOYMENT NO-GO**

- ระบบควบคุมงานและ ownership ผ่าน: automation guard PASS, ไม่มี live owner ซ้ำ และสำเนา prompt ที่ไม่ได้ทำงานตรงกับเจ้าของจริง
- local build ผ่าน 70/70 หน้า, affiliate placements 140 จุด, identity/disclosure/attribution/media/calendar contracts ผ่าน
- ชุดทดสอบหลักผ่าน: pipeline 89/89 และ tool test scripts 48/48; compile และ diff check ผ่าน
- preflight จริงยังมี **3 FAIL / 7 WARN** จึงต้องบล็อกการโพสต์ การส่ง traffic และ deploy
- production ไม่ตรงกับ local ที่ตรวจแล้ว: live release parity **0/72**, มี affiliate placements รุ่นเก่า 185 จุด และไม่มี release manifest ที่รองรับ
- GA4/GSC snapshot ปัจจุบันเป็น metadata รุ่นเก่าและใช้ตัดสินใจไม่ได้; GA4 internal-traffic trust ยัง UNTRUSTED
- official-source review ค้าง 26 รายการ
- revenue ledger ปัจจุบันเป็น UNRECONCILED จึงต้องแสดงรายได้เป็น “ไม่พร้อมใช้” ไม่ใช่ 0 บาท

ข้อสรุปเชิงรายได้: ตอนนี้ความเสี่ยงจากการส่ง traffic ไปยัง production รุ่นเก่าสูงกว่าประโยชน์จากการรีบโพสต์ การปลดล็อกต้องทำตามลำดับในรายงานนี้ แล้วจึงเปิดเพียงหนึ่ง placement ที่มีหลักฐานครบเพื่อเริ่ม baseline ใหม่

## Final Truth Table

| โดเมน | สถานะ | หลักฐานล่าสุด | ผลต่อธุรกิจ |
|---|---|---|---|
| Automation ownership | PASS | Cowork 92 งาน/เปิด 22, CCD 11 งาน/เปิด 7, shared ownership 12/12 PASS | ลดงานยิงซ้ำและคำสั่งขัดกัน |
| Privacy/public identity | PASS | privacy 32 tracked files; identity 76 pages, 161 captions, 44 knowledge rows, 10 outward prompts | ออกนามเพจและไม่เปิดข้อมูลอ่อนไหวในรุ่น local |
| Local build/funnel | PASS | smoke 70/70, affiliate 140 placements, merchant gate 16 products/2 promotions/77 docs | รุ่น local พร้อมเป็นฐาน deploy หลัง gate อื่นผ่าน |
| Media | PASS แบบมีขอบเขต | canonical video 24/24 และ image 1/1 ผ่าน; ไฟล์ที่มีลายน้ำถูกกัก | ไม่พบ provider mark ที่มองเห็นได้ใน active set; ไม่ใช่การรับรอง watermark ที่มองไม่เห็นทุกชนิด |
| Content calendar | BLOCKED อย่างถูกต้อง | 65 placements, 40 content IDs, publishable 0 | ตารางไม่ backfill และไม่อนุญาตยิงก่อนหลักฐานครบ |
| Live release | FAIL | live/local parity 0/72; live 185 placements; release manifest ไม่รองรับ | ห้ามเพิ่ม traffic เพราะ attribution, taxonomy และข้อเสนอจริงยังเป็นรุ่นเก่า |
| Official sources | FAIL | 31 sources, review_required 26, errors 0 | ห้ามเผยแพร่ข้อความการเงินที่ยังไม่ผ่าน human acknowledgement |
| GA4/GSC measurement | FAIL | current snapshot เป็น schema v1/INVALID_METADATA; GA4 trust UNTRUSTED | sessions/clicks/impressions เดิมใช้จัดอันดับหรือประเมิน ROI ไม่ได้ |
| Revenue ledger | WARN/BLOCKED | UNRECONCILED: invalid metadata envelope at line 1 | ห้ามสรุปว่า verified revenue = 0; ต้อง reconcile จากหลักฐานจริง |
| Dashboard | PASS ด้านความซื่อสัตย์ | provenance ผูก producer/GA4/GSC/revenue และแสดง “—/UNRECONCILED” | ไม่สร้าง false zero หรือ false-ready อีก |

## จุดผิดพลาดที่แก้แล้ว

### 1. Control plane และสิทธิ์

- inventory อ่าน registry จริงทั้ง Cowork/CCD และ Windows Scheduled Tasks โดยตรวจทั้งชื่อ action และ working directory
- ปิดงานเก่าที่ registry ยังเปิดแต่ prompt เป็น `RETIRED — NO-OP` ผ่านตัวจัดการที่รองรับ
- อุดคำสั่งโพสต์ซ้ำ/แจ้งเตือน/อัปโหลด storage/install package/แก้ scheduler ที่ซ่อนใน prompt รวมภาษาไทย
- เปลี่ยน notifier, LLM fallback, legacy schedulers และ browser publishers ให้ local/report-only หรือ fail closed
- publication receipt schema v2 ผูก content, placement, channel, target, caption, asset, slot และ hash ของ policy/role/calendar/validation/media-QA; consume ได้ครั้งเดียวและตรวจเวลา Bangkok ก่อน external boundary
- log runner ใช้ lock, fsync และ atomic latest; corrupted/unreadable run log กลายเป็น UNKNOWN/WARN ไม่ถูกข้าม

### 2. Funnel และเว็บไซต์

- ปิดเส้นทางขาย own-product ที่ `promotion_authorized=false` รวม 59/199 บาทใน hub, banner, quiz และเครื่องมือ local
- แก้ taxonomy KTC PROUD, product fit, affiliate metadata, semantic positions/content IDs และ event taxonomy
- merchant gate บังคับ registry coverage, status, official URL, freshness, product/intent fit, promotion window และ exact rel tokens
- Netlify build trigger ครอบคลุม policy, merchant registry, gates, manifest และ smoke tools ที่มีผลต่อ release
- แยก build time ออกจาก factual review time และไม่ประทับ `dateModified/lastmod` ปลอมทุกหน้า

### 3. Measurement และ revenue

- GA4/GSC bundle เขียนแบบ staged/atomic และเลื่อน sidecar เฉพาะเมื่อทุกตารางครบ
- GA4 แยก source/medium/channel, ตรวจ nonnegative integer, เก็บ event/page funnel ครบ และมี pagination/coverage/truncation evidence
- GSC ใช้หน้าต่าง finalized 28 วันจบ D-3, normalize/aggregate query และตรวจ coverage/row counts/hash
- observation/dashboard ผูก producer hash, property, event contract และ capture-time trust
- revenue เปลี่ยนเป็น schema v4 append-only lifecycle: event ID, idempotency, monotonic transitions, terminal states, source hash และ row counts
- exact text/clip dedup เป็นถาวรในช่องเดียว พร้อม lock และ fail closed เมื่อ ledger เสียหาย

## จุดอ่อนที่ยังเหลือ

### P0 — ต้องแก้ก่อนโพสต์หรือ deploy

1. **Production ยังเป็นรุ่นอันตรายต่อ conversion และความน่าเชื่อถือ**  
   `/debt-letter-kit` live ยังเปิดขาย deliverable ที่ไม่พร้อม, `/links` ยังมี taxonomy/attribution รุ่นเก่า และหน้ารายได้ 30,000 บาทมีข้อความเก่าขัดกับฉบับแก้ local

2. **Official source reviews ค้าง 26 รายการ**  
   fingerprint ปัจจุบันไม่มี fetch error แต่ policy กำหนดให้ human ตรวจและ acknowledge อย่างมี audit trail; agent ไม่ควรปลดเอง

3. **GA4 ยังไม่ trusted และ bundle จริงยังไม่ใช่ v2**  
   ต้องแก้ internal-traffic coverage ให้ครอบคลุมหน้าต่าง 28 วัน แล้วดึง GA4/GSC ใหม่; ห้ามใช้ตัวเลขเดิมเป็น baseline

4. **Revenue ยัง unreconciled**  
   ไม่มี raw intake จริงสำหรับสร้าง schema v4 อย่างซื่อสัตย์ จึงห้าม fabricate transaction หรือสรุป zero revenue

### P1/P2 — ยกระดับหลัง P0

- weekly-review มี `started` ค้างประมาณ 154 ชั่วโมง ต้อง reconcile ด้วยหลักฐานจริง ห้ามสร้าง terminal row ย้อนหลัง
- post ledger เก่า 81 แถวยังไม่มี identity ครบ และมีประวัติ TikTok `titleloan` ซ้ำจริง; gate ใหม่กันอนาคตได้แต่แก้หลักฐานย้อนหลังไม่ได้
- video runway จากวันนี้เป็น 0; B3 หกชิ้นผ่าน technical watermark scan แต่ถูกบล็อกด้าน semantic parity/claim และไม่มี approved receipt
- visible watermark detector ไม่ครอบคลุม SynthID/invisible provenance หรือ audible acoustic marks ทุกชนิด
- historical Git exposure ของข้อมูลเก่ายังต้องจัดการแยกจาก current-tip privacy PASS
- working tree มีการแก้จำนวนมากจากรอบ remediation; ก่อนส่งขึ้น remote ต้องแบ่ง scope, review diff และใช้ exact-path commit เท่านั้น

## แผนปลดล็อกแบบเรียงลำดับ

1. **Owner review แหล่งอ้างอิง 26 รายการ**  
   ตรวจ claim ต่อ content ID, บันทึก reviewer/time/rationale/hash แล้ว acknowledge เฉพาะแหล่งที่ unchanged

2. **ซ่อม measurement trust และดึงข้อมูลใหม่**  
   ยืนยัน internal-traffic coverage ตลอด 28 วัน, ดึง GA4 schema v2 และ GSC schema v2 จบ D-3, ต้องผ่าน hash/coverage/truncation checks

3. **นำเข้ารายได้จากหลักฐานจริง**  
   สร้าง raw lifecycle events จาก vendor evidence, freeze source, reconcile schema v4 และให้ dashboard/provenance ผ่าน; ถ้าไม่มีหลักฐานให้คง UNRECONCILED

4. **ตรวจ release candidate local ซ้ำ**  
   privacy, identity, merchant, media, calendar, disclosure, attribution, manifest และ local smoke ต้อง PASS ใน snapshot เดียวกัน

5. **Owner-authorized deploy รุ่น local ที่ตรวจแล้ว**  
   deploy exact release เท่านั้น; ห้ามใช้โค้ด live เก่าหรือ push commits อื่นปน

6. **ตรวจ production หลัง deploy**  
   live/release parity ต้องผ่านทุกหน้าที่อยู่ใน manifest; `/debt-letter-kit` ต้องไม่มีราคา/พร้อมเพย์/ส่งสลิป/data-buy, salary page ต้องไม่มี claim เก่า, `/links` ต้องมี taxonomy/content attribution รุ่นใหม่

7. **เปิดโพสต์หนึ่ง placement แบบ bounded pilot**  
   ใช้ private receipt v2, exact slot/target/content/asset hash, source/media/revenue gates ผ่าน แล้วดูผลเป็น baseline ใหม่โดยไม่ปนข้อมูลก่อน remediation

8. **ขยายทีละช่องจากหลักฐาน**  
   เพิ่มเฉพาะช่องและคอนเทนต์ที่มี qualified click/lead/paid commission จริง; Pantip รอ review 48 ชั่วโมง และ TikTok ต้องมี 14 ชิ้นที่ semantic/source/media QA ผ่านก่อน reactivation test

## Acceptance Criteria ก่อน GO

- preflight = 0 FAIL
- official source pending ที่เกี่ยวข้องกับ placement = 0 และมี audit trail
- GA4/GSC observation = CURRENT + decisionable + trusted at capture
- revenue = RECONCILED หรือระบุชัดว่าไม่มี evidence โดยไม่แสดง false zero
- live release parity = PASS ทุกหน้าที่อยู่ใน release manifest
- calendar placement = publishable 1 รายการพร้อม private receipt v2 ที่ valid และยังไม่ถูก consume
- post ledger integrity = OK, ไม่มี duplicate identity, quota และ gap ผ่าน
- media receipt/hash ตรงกับ final bytes และ full-frame review ผ่าน

## Validation Evidence

| การตรวจ | ผล |
|---|---:|
| Pipeline unit tests | 89/89 PASS |
| Tool test scripts | 48/48 PASS |
| Preflight actual | 3 FAIL / 7 WARN |
| Automation policy guard actual | PASS |
| Privacy guard actual | PASS |
| Public identity actual | PASS |
| Content calendar guard | PASS, 65 placements / 40 IDs / 0 publishable |
| Merchant source + generated site | PASS, 16 products / 2 promotions / 140 placements / 77 docs |
| Local smoke | 70/70 PASS |
| Active media gate | 24 videos + 1 image PASS |
| Live/release smoke | 0/72 FAIL, 185 links |
| Compile / diff check | PASS |

## Evidence Paths and Sources

- `C:\Users\nL_ku\ngernduangold-site\automation-log\MASTER-SCHEDULE_20260817-0831.md`
- `C:\Users\nL_ku\ngernduangold-site\.system_control\content_calendar.json`
- `C:\Users\nL_ku\ngernduangold-site\.system_control\policy.json`
- `C:\Users\nL_ku\ngernduangold-site\tools\preflight.py`
- `C:\Users\nL_ku\ngernduangold-site\tools\postdeploy_smoke.py`
- `C:\Users\nL_ku\ngernduangold-site\automation-log\dashboard.html`
- Live pages checked without following affiliate trackers:
  - https://ngernduangold.com/debt-letter-kit
  - https://ngernduangold.com/links
  - https://ngernduangold.com/credit-card-salary-30000-2026

## Caveats

- รายงานนี้รับรองความสอดคล้องของ local snapshot และ control contracts ที่ตรวจ ณ เวลาระบุ ไม่รับรองว่าการ deploy/โพสต์ในอนาคตจะไม่ drift
- ไม่ได้คลิก affiliate tracker, ไม่โพสต์, ไม่ deploy, ไม่ commit และไม่ push
- ไม่มีระบบใดรับประกันรายได้; เป้าหมายคือทำให้การทดลองวัดผลได้ ซื่อสัตย์ต่อข้อมูล และหยุดอัตโนมัติเมื่อหลักฐานไม่พอ

