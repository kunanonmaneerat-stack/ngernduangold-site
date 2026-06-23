# BRIEF ขอไอเดียทำรายได้จริง — เว็บ affiliate การเงินไทย "เงินเดือนสมองทอง"
(สำหรับถาม Gemini · ให้ Cowork นำไอเดียมาลงมือทำต่อ)

## 1) โมเดลธุรกิจ
- เว็บคอนเทนต์การเงินส่วนบุคคลสำหรับ "มนุษย์เงินเดือนไทย" → ngernduangold.netlify.app
- รายได้ = affiliate ผ่าน AccessTrade (ลิงก์ atth.me) จ่ายเมื่อผู้ใช้สมัครผ่านลิงก์: บัตรเครดิต / สินเชื่อ / บัญชีออม / ประกัน
- ทีม = เจ้าของคนเดียว + Cowork (AI agent) ทำงานแทน · เน้นเครื่องมือฟรี/ที่มีอยู่ · งบโฆษณา ~0

## 2) ทรัพย์สินที่มีตอนนี้ (ทำเสร็จแล้ว)
- **เว็บ 43 หน้า** static (สร้างด้วย build_site.py · Python stdlib) · comply-safe (ยึด ธปท./ก.ล.ต./คปภ. · ใช้ "ช่วง" ไม่การันตี · ไม่ระบุชื่อแบงก์ใน hero)
- **5 คลัสเตอร์เนื้อหา** ลิงก์อิงกันแน่น: (ก) หนี้/บัตร (เครดิตบูโร, ดอกเบี้ย/จ่ายขั้นต่ำ, ปลดหนี้, แอปกู้ถูกกฎหมาย) (ข) เทียร์เงินเดือน 15k/20k/30k (ค) ภาษี (ลดหย่อน) (ง) ประกัน (สุขภาพ/เทียบประกัน/เดินทาง) (จ) ลงทุน/เกษียณ (กองทุน+DCA, วางแผนเกษียณ)
- **SEO พร้อม**: sitemap + robots + schema (Article/FAQ/Breadcrumb) + canonical + OG · GA4 ติด (G-17PPE0M1B8) · Google Search Console verified + submit sitemap แล้ว (รอ index 2-3 วัน)
- **affiliate links จริง**: บัตร (Krungsri), ออม (Kept), สินเชื่อ (KTC PROUD, ศรีสวัสดิ์, Car4Cash, รวมหนี้ HappyCash, รีไฟแนนซ์) — **ช่องว่าง: ยังไม่มีลิงก์ ประกันสุขภาพ/ชีวิต + กองทุน/SSF-RMF** (คลัสเตอร์ภาษี/ประกัน/ลงทุน เลย convert ไม่ได้)
- **Distribution อัตโนมัติ**: ต่อ Postiz Public API สำเร็จ → ตั้งเวลาโพสต์ Threads/TikTok/YT/FB/IG ได้เอง · เพิ่งตั้งคิว 10 บทความลง Threads (วันละ 1, 23 มิ.ย.–2 ก.ค.) · มีคลิปสั้น 36 ตัว (เจนด้วย Google Veo/Flow) ลง TikTok/YT/Reels
- **Agents (รันผ่าน Desktop Commander บนเครื่อง owner → ต่อ API ภายนอกได้)**: build_site, postiz_article_scheduler, ga4_pull, traffic_analyst, art-loop (stitch/stylist), cc_monitor
- **ทรัพยากรเพิ่ม**: Sakana AI API key (ยังไม่ wire), Hermes (Telegram gateway สั่ง LLM), Veo credits เหลือ ~460/1000, เข้าถึง LLM ฟรีหลายตัว
- **วัดผล**: scheduled task ทุกจันทร์ ดึง GA4+GSC สรุปว่าอะไรมาแรง

## 3) คอขวดจริง
- ทราฟฟิกยังน้อยมาก (เว็บใหม่ เพิ่งถูก index) → รายได้ยัง ~0 บาท
- คลัสเตอร์ใหม่ (ภาษี/ประกัน/ลงทุน) ดึงทราฟฟิกได้แต่ยัง monetize ไม่ได้ (ขาด affiliate link)
- ยังไม่รู้ว่า keyword/ช่อง/หน้าไหนจะ convert จริง (ยังไม่มีดาต้า)

## 4) Loop ปัจจุบัน
ผลิตคอนเทนต์ → เว็บ live → กระจาย (SEO + Social ตั้งเวลาเอง) → คนคลิก affiliate → วัดผล GA4/GSC → เสริมจุดที่มาแรง → วน

## 5) สิ่งที่อยากได้จาก Gemini (ขอละเอียด เป็น actionable)
1. **กลยุทธ์ทำรายได้จริงเร็วสุด** ด้วยงบ ~0 + automation ที่มี — เรียงลำดับความคุ้ม
2. **Traffic acquisition ที่ได้ผลจริงในไทยปี 2026** สำหรับ niche การเงิน (ช่องไหน, รูปแบบคอนเทนต์, keyword strategy, social ตัวไหนคุ้มเวลา)
3. **Conversion optimization**: ทำยังไงให้คน "คลิก affiliate + สมัครจริง" มากขึ้น (CTA, page layout, ความน่าเชื่อถือ, funnel, intent matching)
4. **เลือก offer/vertical ที่ payout สูง + convert ง่าย** ในตลาดไทย (บัตร vs สินเชื่อ vs ประกัน vs ออม) ควรโฟกัสตัวไหนก่อน
5. **เอา Sakana AI API + LLM ฟรี + automation มาใช้ให้เกิดประโยชน์สูงสุด** (เช่น personalize, scale content, programmatic SEO, A/B test)
6. **KPI + timeline 30/60/90 วัน** ที่ควรวัด
7. **กับดัก/ความเสี่ยง** ที่ต้องเลี่ยง (Google policy การเงิน/YMYL, affiliate compliance, content quality)

ตอบเป็นภาษาไทย ละเอียด เป็นขั้นตอนที่ Cowork (AI agent) เอาไปลงมือทำต่อได้ทันที
