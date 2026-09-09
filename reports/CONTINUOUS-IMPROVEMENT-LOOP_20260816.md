# Continuous Improvement Loop — เงินเดือนสมองทอง

> **SUPERSEDED FOR CURRENT NUMBERS:** ตัวเลข revenue/GSC/preflight ในรายงานนี้เป็น snapshot เก่าก่อน schema และ provenance hardening โปรดใช้ `reports/LEARNING-UPLIFT_20260816.md` เป็นสถานะปัจจุบัน ห้ามตีความค่าศูนย์ด้านรายได้ในไฟล์นี้ว่าเป็น verified zero

> ตรวจรวมล่าสุด: 16 สิงหาคม 2026 · Asia/Bangkok  
> เป้าหมาย: สร้างคุณค่าและรายได้ affiliate อย่างสม่ำเสมอ โดยให้ “เงินเดือนสมองทอง” เป็นผู้พูดต่อสาธารณะเพียงตัวตนเดียว  
> สถานะ: **ระบบวิเคราะห์และปรับปรุงในเครื่องพร้อมใช้งาน; การเผยแพร่และการขยายรายได้ยัง BLOCKED ตามหลักฐานปัจจุบัน**

## ขอบเขตอำนาจ

Codex เป็น `internal_page_operator` สำหรับงานที่ย้อนกลับได้ในเครื่อง ได้แก่ อ่าน ค้นคว้า วิเคราะห์ แก้โค้ด/เนื้อหา ออกแบบ สร้างไฟล์ ทดสอบ และจัดระบบวัดผล

อำนาจนี้ไม่รวมการโพสต์/ตอบ/คอมเมนต์ต่อสาธารณะ, acknowledge แหล่งข้อมูลแทนผู้ตรวจ, ใช้เงินหรือโควตาเสียเงิน, commit, push หรือ deploy ตัวตนสาธารณะทั้งหมดต้องเป็นองค์กร “เงินเดือนสมองทอง” ไม่ใช่ชื่อ agent หรือบุคคลสมมติ

## วงจรที่ติดตั้งแล้ว

1. **Observe** — ดึง GA4, GSC, ledger รายได้ และ fingerprint แหล่งทางการแบบมีช่วงเวลา/แฮช/coverage
2. **Diagnose** — ตรวจ privacy, ตัวตนเพจ, offer, source, attribution, duplicate, quota, media และ build
3. **Prioritize** — เลือกปัญหาสูงสุดไม่เกิน 3 เรื่อง และห้ามเสนอ growth เมื่อหลักฐานหรือ guard ใดไม่พร้อม
4. **Validate** — ทดสอบแบบ fail-closed; ข้อมูลเก่า ไม่ครบ หรือไม่น่าเชื่อถือใช้ตัดสินไม่ได้
5. **Report** — เก็บหลักฐานรอบไว้ใน `.local-private/runtime/improvement-runs/`
6. **Owner queue** — ส่งเฉพาะรายการที่ต้องใช้สิทธิ์เจ้าของ โดยไม่ดำเนินการแทน

## ตารางทำงานจริง

| งาน | เวลา | บัญชี/ระดับสิทธิ์ | สิ่งที่ทำได้ |
|---|---|---|---|
| `ngernduangold_daily` | ทุกวัน 07:00 | `nL_ku`, Interactive/Limited | ตรวจและสร้างรายงานในเครื่อง; หยุดเมื่อ gate ล้ม |
| `ngernduangold_weekly` | ทุกวันอาทิตย์ 08:30 | `nL_ku`, Interactive/Limited | รีเฟรชหลักฐาน 28 วัน, สรุปผล, รันวัฏจักร local-safe |

ทั้งสองเส้นทางไม่มี social publish, browser mutation, Telegram/Slack/email, paid/network LLM, Git commit/push หรือ deploy โดยค่าเริ่มต้น งานรายวันสร้างเพียง local generation request แทนการเรียกโมเดลภายนอก

## สถานะธุรกิจที่ยืนยันได้

| ตัวชี้วัด | ค่าล่าสุด | ใช้ตัดสินได้หรือไม่ |
|---|---:|---|
| Verified affiliate revenue (28 วัน) | 0 บาท | ใช้ได้; ledger ผ่าน contract แต่ยังไม่มี commission ที่ยืนยัน |
| Confirmed affiliate commissions | 0 | ใช้ได้ |
| GA4 sessions | 102 | วินิจฉัยเท่านั้น; capture เป็น UNTRUSTED |
| GA4 affiliate clicks | 6 | สัญญาณ intent เท่านั้น ไม่ใช่ conversion/รายได้ |
| GA4 buy intent | 2 | สัญญาณ intent เท่านั้น |
| GSC page impressions | 301 | ใช้จัดลำดับ SEO ได้; bundle CURRENT/non-truncated |
| GSC clicks | 0 | ใช้ได้ ณ snapshot ปัจจุบัน |
| Official-source review pending | 26 | BLOCK การเผยแพร่ |

คำตัดสินของวงจรจริงรอบ `20260816-120739` คือ `COMPLETED_WITH_BLOCKERS`: guard ควบคุมผ่าน, publication blocked, ไม่มี growth experiment และเลือกเพียง `repair_measurement`

## สิ่งที่ระบบจะไม่ทำ

- ไม่เรียก `affiliate_click` ว่า conversion หรือรายได้
- ไม่เลือกช่อง/โพสต์ชนะจาก GA4 ที่ปน internal traffic
- ไม่เร่งความถี่หรือโพสต์ย้อนหลังเพื่อชดเชยคิวว่าง
- ไม่ใช้ข้อความ/วิดีโอซ้ำแบบ exact ต่อช่อง และไม่ใช้ไฟล์ watermark ที่ถูก quarantine
- ไม่โปรโมต offer หมดอายุ/ผิดผลิตภัณฑ์ หรือสินค้าที่ส่งมอบไม่ได้
- ไม่พูดในนาม Codex, Claude, Gemini หรือบุคคลผู้ใช้
- ไม่ส่งข้อความภายนอก ใช้โควตาเสียเงิน commit/push/deploy จาก scheduled loop

## Blocker ที่ต้องแก้ก่อนเติบโต

1. **GA4 trust** — ตัวกรอง internal traffic ยังครอบคลุมช่วงตัดสิน 28 วันไม่ครบ จึงต้องยืนยันเครือข่ายเจ้าของและเก็บช่วงสะอาดใหม่
2. **Official sources** — เจ้าของ/ผู้ตรวจต้องพิจารณา claim packets และรับรอง 26 แหล่งทีละรายการ
3. **Revenue proof** — ต้องมี commission ที่ยืนยันและผูกกลับถึง source/content ก่อนขยาย funnel
4. **Publication authority** — ทุกช่องยัง `publication_authorized=false`; งานสร้างสรรค์จึงเป็น draft/QA เท่านั้น

## หลักฐานตรวจสุดท้าย

- Test files: **52/52 PASS**
- Local build/verification: **77 pages PASS**
- Smoke: **70/70 pages, 140 affiliate buttons PASS**
- Privacy: **32 tracked files, 0 finding**
- Public identity: **76 pages, 161 captions, 44 knowledge rows, 10 prompts PASS**
- Merchant offers: **2 products, 2 promotions, 20 source documents PASS**
- Manifest: **23 items PASS**
- Active media: **24 videos + 1 image PASS**; quarantine ไม่ถูกสแกนเป็นสื่อใช้งาน
- Python compile, diff check: **PASS**; staged files: **0**
- Full preflight: **2 FAIL / 5 WARN** โดย FAIL เฉพาะ GA4 trust และ official-source review

## หมายเหตุเหตุการณ์ระหว่างตรวจ

การเรียก weekly review เพื่อตรวจระบบหนึ่งครั้งเคยส่ง owner-only Telegram notification ออกไปโดยอัตโนมัติ ไม่ใช่โพสต์สาธารณะ หลังพบแล้วได้ถอด transport sink ทั้ง weekly/daily และเพิ่ม regression ที่ยืนยัน network notification เป็นศูนย์ เหตุการณ์นี้ไม่ถูกปกปิดและไม่ควรเกิดซ้ำจากค่าเริ่มต้น

## เกณฑ์เริ่มทดลองรายได้

อนุญาตให้เลือก experiment เดียวต่อรอบได้เมื่อครบทั้งหมด: guard ผ่าน, source ของชิ้นนั้นได้รับการทบทวน, GA4 capture/current trust ผ่าน, ledger รายได้เชื่อถือได้, landing/CTA/offer พร้อม และมี publication authorization เฉพาะชิ้น จากนั้นวัด D7/D14 ด้วย verified revenue เป็น North Star และใช้ clicks เป็นเพียง leading indicator
