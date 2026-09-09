# Affiliate Revenue + Page-Only Control Audit

> ตรวจรวมล่าสุด: 16 สิงหาคม 2026 · Asia/Bangkok  
> เป้าหมาย: สร้างรายได้ affiliate อย่างสม่ำเสมอ โดยให้ “เงินเดือนสมองทอง” เป็นผู้พูดต่อสาธารณะเพียงตัวตนเดียว  
> คำตัดสิน: **ระบบในเครื่องยกระดับและผ่าน regression แล้ว แต่การโพสต์/อัปโหลด/deploy ยังเป็น NO-GO จนกว่าจะปลดด่านที่ระบุด้านล่าง**

## 1. ข้อสรุปสำหรับตัดสินใจ

ปัญหาหลักไม่ใช่จำนวนโพสต์ แต่เป็นการส่งทราฟฟิกไปยัง production ที่ล้าหลังกว่าเนื้อหาที่ตรวจแล้ว พร้อมข้อมูลวัดผลที่ยังแยกผู้ใช้จริงออกจาก automation ไม่ได้ การเร่งโพสต์ในสภาพนี้อาจเพิ่มตัวเลขคลิก แต่ยังพิสูจน์รายได้ไม่ได้และขยายความเสี่ยงเรื่องคำกล่าวอ้าง/ตัวตนของเพจ

รอบนี้แก้ฐานสำคัญแล้ว:

1. บังคับให้หน้าเว็บ โพสต์ คอมเมนต์ ตอบกลับ CTA และร่างสาธารณะออกในนามองค์กร “เงินเดือนสมองทอง” เท่านั้น
2. แก้ข้อมูลสินค้า/ข้อเสนอ/CTA ที่คลาดเคลื่อน และเพิ่มด่านหมดอายุโปรโมชัน
3. ใส่ข้อมูลระบุตัวตนคอนเทนต์และตำแหน่งให้ลิงก์ affiliate ครบ 140 จุด
4. แก้การประทับวันที่ตรวจทานปลอมจากวัน build และแก้ช่วงรายงาน 28 วันที่เคยนับจริง 29 วัน
5. ปิด publisher เก่าและ uploader ทุกช่องให้ตรวจสิทธิ์ ผู้อนุมัติ ตัวตนเพจ และบัญชีปลายทางจริงก่อน network/OAuth
6. เพิ่ม release manifest และ live/local comparison เพื่อห้ามรายงานว่า production พร้อมทั้งที่ยังเป็นเวอร์ชันเก่า

## 2. สถานะด่านจริง

| ด่าน | ผลล่าสุด | คำตัดสิน |
|---|---:|---|
| Public identity | 76 หน้า, 161 caption fields, 44 knowledge rows, 10 outward prompts ผ่าน | PASS — ผู้พูดสาธารณะคือเพจเท่านั้น |
| Privacy ที่ worktree ปัจจุบัน | 32 tracked files, 0 finding | PASS เฉพาะ current tip; ประวัติ Git เดิมยังต้องตัดสินใจจัดการ |
| Affiliate integrity | 140/140 CTA มี provider, campaign, content ID, position และ sub-ID | PASS |
| Local web build | 70/70 หน้า, 140 CTA | PASS |
| Merchant offer gate | ต้นทางเผยแพร่ได้ 20 เอกสาร + generated HTML 77 ไฟล์ | PASS |
| Automation/publisher policy | ไม่พบ scheduled publisher หรือคำสั่ง push/deploy ที่ข้ามสิทธิ์ | PASS |
| Media/duplicate controls | ไฟล์มีปัญหาถูก quarantine; exact repost ถูกบล็อกถาวรตามช่อง | PASS สำหรับ active set |
| GA4 decision trust | egress ปัจจุบันไม่อยู่ใน internal CIDR ที่กำหนด | **FAIL / UNTRUSTED** |
| Official sources | pending review 26 แหล่ง | **FAIL / ห้ามเผยแพร่** |
| Live release parity | production ต่างจาก audited local release ทุกหน้าที่ตรวจ และไม่มี release manifest ที่รองรับ | **FAIL / ห้ามอ้างว่า live พร้อม** |
| Publication authority | `publication_authorized=false` ทุกช่อง | **NO-GO** |
| `letter-kit-199` | ไม่มี deliverable ตามคำสัญญา; กลไกรับเงินถูกปิด | **STOP** |

Full preflight ล่าสุดจบที่ **2 FAIL / 5 WARN**: FAIL คือ GA4 trust และ official-source review; WARN คือไม่มีคิววิดีโออนาคต, weekly-review tombstone เก่า, sales ledger ว่างแม้พบ affiliate clicks, และ direct traffic ที่มีแนวโน้มเป็น automation

## 3. จุดผิดที่พบและแก้แล้ว

### ตัวตนและความน่าเชื่อถือของเพจ

- หน้า About เคยอ้างประสบการณ์ส่วนบุคคลของผู้จัดทำโดยไม่มีหลักฐาน เปลี่ยนเป็นกระบวนการบรรณาธิการของเพจ การใช้แหล่งทางการ และการเปิดเผยการใช้ AI อย่างตรงไปตรงมา
- ร่างบางชุดเคยใช้ “ผม/ฉัน” หรือเสนอให้ agent ออกไปพูดแทน แก้เป็น page-only และเพิ่ม guard ตรวจทั้งหน้าเว็บ แคปชัน คลังความรู้ และ scheduled prompts
- metadata ทุกหน้าระบุ author/publisher เป็น Organization “เงินเดือนสมองทอง”; Codex, Claude, Cowork, ChatGPT และ Gemini ห้ามเป็นผู้พูดสาธารณะ

### ความถูกต้องของข้อเสนอ affiliate

- KTC PROUD เคยถูกอธิบายเป็นสินเชื่อส่วนบุคคลแบบผ่อนงวด แก้เป็นบัตรกดเงินสดวงเงินหมุนเวียนตามข้อมูลทางการ และนำออกจากคำแนะนำรวม/ปรับโครงสร้างหนี้ที่ไม่เหมาะสม
- ข้อความใต้ redirect เคยทำให้เข้าใจว่า tracker เป็น “ลิงก์ทางการ/ปลอดภัย” แก้เป็นคำอธิบายระบบ affiliate อย่างโปร่งใส
- CTA รถที่พาไปผู้ให้บริการรายเดียวเคยใช้ถ้อยคำคล้ายเปรียบเทียบหลายเจ้า แก้ให้ตรงกับปลายทางจริง
- ข้อเสนอ KTC และ HappyCash ถูกแยกเป็น product availability กับ promotion window; โปรที่ยังไม่เริ่ม ถูกพัก หรือหมดอายุจะทำให้ build ล้มเมื่อยังมี claim เหลืออยู่
- Gate ครอบคลุม build source, canonical root HTML, future content manifest/knowledge rows และ generated pages/quiz โดยไม่ปน archive หรือ quarantine

### Attribution และการตัดสินรายได้

- CTA affiliate 140 จุดเคยขาด `data-content-id` และ `data-pos` เกือบทั้งหมด ปัจจุบันครบ 140/140
- runtime ส่ง metadata ผ่าน interstitial ครบ และแยก acquisition content จาก landing content ไม่ให้ตัวตนคอนเทนต์ทับกัน
- หน้าเงินเดือน 30,000 เคยใช้ content ID ของวิดีโอ B4 ที่ยังไม่เผยแพร่ แยกเป็น identity ของหน้า evergreen แล้ว
- event `affiliate_click` ถูกจำกัดให้เป็น affiliate จริง; intent ของสินค้าเพจ, LINE และ internal navigation ถูกแยกประเภทเพื่อไม่ปน KPI
- schema `affiliate_click` ที่เคยถูกรายงานเป็น `conversion=0` ใน dashboard/weekly/optimizer ถูกทำให้ใช้ contract เดียวกัน
- GA4/GSC helper แก้ inclusive window จาก 29 calendar dates ให้เป็น 28 วันที่ถูกต้อง แต่ CSV ปัจจุบันยังเป็น snapshot เก่า จึงห้ามเรียกตัวเลขชุดนี้ว่า “28 วัน” จน pull รอบถัดไป

### Freshness, source และ production truth

- เลิกใช้วัน build เป็น Article `dateModified`, sitemap `lastmod` และข้อความ “อัปเดตล่าสุด” แบบเหมารวม
- มี metadata เฉพาะ 11 หน้าที่แก้/ทบทวนจริงในรอบนี้; sitemap มี `lastmod` เฉพาะหน้าที่มีหลักฐาน
- เพิ่มแหล่งทางการและ binding note ให้ landing ที่จะรองรับ kn-34, kn-37, kn-38 และ kn-44
- post agent ส่ง exact `content_id` เข้าด่าน source แล้ว; หากรายการวันนี้ถูกบล็อก จะ exit nonzero แทนการรายงาน 0 slot แบบสำเร็จปลอม
- เพิ่ม release manifest แบบ aggregate SHA-256 และตรวจ canonical HTML แบบ live/local โดยไม่ตาม tracker

### Automation และบัญชีปลายทาง

- เอาคำสั่ง commit/push ที่ซ่อนใน scheduled tasks ออก และทำ prompt mirror ให้ตรงกัน
- Facebook, Instagram, TikTok และ YouTube live path ต้องผ่าน actor role, channel authorization, per-item owner approval, privacy, page identity และบัญชีปลายทางที่ตรง SSOT
- YouTube ตรวจ channel ID ทั้งก่อน OAuth และจากบัญชีที่ OAuth ยืนยันจริงก่อนแตะ media/upload; missing/mismatch/ambiguous จะหยุดโดยไม่พิมพ์ ID
- link-health ตรวจ direct merchant/static placement เท่านั้น ไม่เปิด `atth.me` เพื่อสร้าง self-click
- exact duplicate text/clip ต่อช่องถูกบล็อกตลอดประวัติ และ check+append ใช้ lock เดียวกันเพื่อลด race condition

## 4. ภาพรายได้ที่มีอยู่จริง

Snapshot ปัจจุบันเป็นช่วงเก่าแบบ inclusive 29 วันและ **GA4 ยัง UNTRUSTED** จึงใช้เป็น observed signal เท่านั้น:

- 108 sessions
- 6 affiliate-click events
- 2 buy-intent events
- 0 confirmed affiliate commission/sale ใน ledger
- GSC 315 impressions, 0 clicks
- salary-30k 154 impressions, car-still-installment 100, refinance-home 28

สองหน้าแรกกิน 254/315 หรือประมาณ **80.6%** ของ impressions และสามหน้าแรกรวมประมาณ **89.5%** จึงควรแก้/ปล่อย production ชุดที่ตรวจแล้วก่อนกระจายกำลังทำบทความจำนวนมาก แต่ห้ามตีความ 6 events เป็น 6 ผู้สนใจจริงหรือเป็นรายได้ เพราะ direct 73 sessions (68%) ยังมีลักษณะ traffic จาก automation และ GA internal filtering ยังไม่ผ่าน

 production ปัจจุบันยังแสดง HTML รุ่นเก่าทั้งเว็บเมื่อเทียบกับ local release; มี legacy salary URL ที่ไม่มี canonical คู่ใน local และไม่มี `release-manifest.json` ตาม schema ใหม่ ดังนั้นข้อมูล live ยังไม่ใช่ฐานที่พร้อมรับ traffic รอบใหม่

## 5. คอนเทนต์รายได้ที่เตรียมไว้

เลือกข้อความแบบ text-only เพื่อลดคอขวดสื่อและไม่โพสต์ซ้ำ:

| ID | วันที่แผน | Intent | Landing | สถานะ |
|---|---|---|---|---|
| kn-34 | 21 ส.ค. | จ่ายหนี้บัตร/ลดเงินต้น | pay-off-credit-card-debt | copy ready; source pending |
| kn-37 | 24 ส.ค. | ตรวจแอป/ผู้ให้บริการสินเชื่อ | loan-online-legal | copy ready; source pending |
| kn-38 | 25 ส.ค. | LTV/รีไฟแนนซ์บ้าน | refinance-home | copy ready; source pending |
| kn-44 | 31 ส.ค. | รถยังผ่อนไม่หมด | car-still-installment-loan | copy ready; source pending |

ผล item-scoped source gate ล่าสุด:

- kn-34: `bot-card-minimum-2026`, `bot-happy-debtor` รอ review
- kn-37: `bot-license-check`, `bot-license-loan` รอ review
- kn-38: `bot-before-loan`, `bot-ltv-2026-extension` รอ review
- kn-44: แหล่งเรื่อง hire purchase, secured loan, debt management และ license รอ review

สถานะที่ถูกต้องคือ **CREATIVE READY / PUBLICATION BLOCKED** ไม่ใช่ publish-ready

## 6. ลำดับปลดล็อกรายได้ที่คุ้มที่สุด

1. แก้ GA4 internal-traffic contract ให้ trust ผ่าน แล้ว pull GA4/GSC รอบใหม่ตามช่วง 28 วันที่แก้แล้ว
2. ให้ owner/human ตรวจ claim packet และ acknowledge เฉพาะแหล่งที่เกี่ยวกับ kn-34/37/38/44; ห้าม ack เหมา
3. ตัดสินใจเรื่องประวัติข้อมูลอ่อนไหวใน Git ก่อน push/deploy และคง current privacy guard เป็น required check
4. Owner อนุมัติ deploy audited local release; หลัง deploy ต้องให้ live/local release comparison และ release manifest ผ่าน 100%
5. เปิด `publication_authorized` เป็นรายช่อง/รายชิ้นเท่านั้น แล้วโพสต์ในนาม “เงินเดือนสมองทอง” พร้อม disclosure และ exact content ID
6. เริ่มจากหนึ่ง funnel ไม่ยิงพร้อมกันทั้งหมด: หน้า intent สูง → affiliate CTA → provider outbound → confirmed commission
7. ประเมิน D0/D7 ด้วย qualified events และยอดยืนยันจริง; เพิ่มความถี่เฉพาะ funnel ที่ผ่าน trust และมี downstream signal

ลำดับทดสอบที่แนะนำหลัง production ตรง local: **kn-34 → kn-37 → kn-38 → kn-44** โดยเว้นช่วงให้เห็นผลและหลีกเลี่ยง creative fatigue

## 7. หลักฐานตรวจรอบสุดท้าย

- Test scripts: 40/40 PASS
- Python compile ของไฟล์ที่เปลี่ยน/เพิ่ม: 84/84 PASS
- Public identity: PASS
- Privacy current worktree: PASS
- Automation policy: PASS
- Merchant source gate: PASS 20 documents
- Generated merchant gate: PASS 77 HTML files
- Manifest contract: PASS 23 items
- Local smoke: PASS 70/70 pages, 140 affiliate buttons
- Active media gate: PASS 24 videos + 1 image; ไม่พบ provider watermark ใน sampled frames
- Local release manifest: PASS และตรงกับ artifact 117 ไฟล์
- `git diff --check`: PASS
- Staged files: 0
- Live release compare: expected FAIL; production ยังไม่ใช่ audited local release
- Full preflight: expected FAIL 2 / WARN 5

## 8. สิ่งที่ไม่ได้ทำ

- ไม่ post/comment/reply/upload ใด ๆ
- ไม่ acknowledge แหล่งข้อมูลแทนมนุษย์
- ไม่ deploy, commit, push หรือ stage
- ไม่เปิดลิงก์ affiliate tracker เพื่อทดสอบ
- ไม่นับ click/buy-intent เป็นรายได้โดยไม่มีหลักฐาน commission

รายงานนี้แทนสถานะเก่าใน `PROJECT-CONTROL-TOWER_20260816.md` สำหรับการตัดสินใจล่าสุด
