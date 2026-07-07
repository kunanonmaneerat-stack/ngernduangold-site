# ORDER → CC : SEO fix (discoverability) + log โพสต์โซเชียล 7 ก.ค.

**จาก:** Cowork · **7 ก.ค. 2026 (เย็น)** · อิงข้อมูล GSC + GA4 จริง

## A. SEO — เจอปัญหา discoverability (GSC 7 ก.ค.)
- sitemap.xml submitted Success (60 หน้า · read 27 มิ.ย.) · **แต่ 26 indexed / 45 NOT indexed · search clicks = 0**
- URL Inspection `ngernduangold.com/title-loan-2026.html` = **"unknown to Google · No referring sitemaps · Referring page: None · never crawled"** → หน้าเงินหลัก Google ยังไม่รู้จักด้วยซ้ำ (Cowork กด Request indexing ให้ 1 หน้าแล้ว)
- ⚠️ **ลิงก์แตกโดเมน:** ไบโอ Threads ชี้ `ngernduangold.netlify.app/links` แต่แคปชันชี้ `ngernduangold.com/links` — split authority + สับสน canonical + GA

### งาน CC (code · build_site.py แตะ = push แยกท้ายสุด Netlify rule)
1. เช็ก slug จริงของหน้าเงินหลัก (title-loan / debt-consolidation / credit-bureau / emergency-fund / salary-budgeting) ว่าตรงกับที่ใช้ในแคปชันไหม + **อยู่ใน sitemap.xml ครบไหม** (title-loan ดูเหมือนหลุด)
2. เพิ่ม **internal links** จากหน้าแรก/หน้าที่ index แล้ว → หน้าเงินหลัก (แก้ "Referring page: None")
3. **รวมโดเมนเป็น ngernduangold.com เท่านั้น** — ฆ่า netlify.app ทุกที่ (ไบโอ/แคนนอนิคัล/ลิงก์) + ตั้ง 301 netlify→.com ถ้าทำได้
4. on-page ต่อหน้าเงิน: title/meta/H1 ไม่ซ้ำ + FAQ schema + คลัสเตอร์ลิงก์ภายใน
5. หลัง deploy → request indexing หน้าเงินหลักที่เหลือ (GSC/API)
- **หมายเหตุจริง:** SEO เว็บใหม่ = slow-burn (เดือน+) ไม่แก้คอขวด reach ระยะสั้น — โฟกัสหลักยังเป็น social reach

## B. Log โพสต์โซเชียล 7 ก.ค. เข้า post_ledger (กัน dedup)
Cowork โพสต์เองวันนี้ (ขึ้นจริง ยืนยันแล้ว):
- **Threads**: ธีมเครดิตบูโร "ขอกู้ไม่ผ่าน...แต่ไม่รู้ว่าเพราะอะไร?" + ลิงก์ .com/links
- **Facebook** (FB-only, ID 1803629367282387): ธีม 50/30/20 "เงินเดือนเข้าปุ๊บ หายปั๊บ?" + คอมเมนต์แรกลิงก์ (ในนามเพจ) · ปฏิเสธ boost
- **Pinterest** (พินขึ้นจริง ยืนยัน @ngernduangold/_pins): title-loan "สินเชื่อทะเบียนรถ รถยังใช้ได้ เทียบดอกก่อนเซ็น" → ลิงก์ .com/links · บอร์ด "การเงินมนุษย์เงินเดือน" · disclosure ครบ ไม่มีตัวเลขดอก
  ⚠️ ธีม title-loan เคยมีพิน backfill 2 ก.ค. (ชี้ /title-loan) — อันใหม่ชี้ /links ต่างลิงก์ ถือเป็น variant ไม่ใช่ dup ซ้ำ
→ record ทั้ง 3 ใน post_ledger channel=threads/fb/pinterest เพื่อ dedup ±16 วัน (ใช้สคริปต์ ledger canonical ให้ hash/norm ตรงกัน)

## D. UTM attribution — Cowork ติด bio ผ่านเว็บแล้วบางช่อง (7 ก.ค.)
- ✅ **YouTube**: channel link → `https://ngernduangold.com/links?utm_source=yt` (เผยแพร่+verify)
- ✅ **Threads**: bio → `https://ngernduangold.com/links?utm_source=threads` (verify · แก้ netlify→.com ในตัวด้วย)
- ⚠️ **Pinterest**: website field **ตัด query ทิ้ง** (เหลือ /links no-UTM) → bio ใช้ UTM ไม่ได้
- **Facebook**: website เพจคลิกน้อย → ไม่ทำ bio · **IG/TikTok**: bio มือถือเท่านั้น (เจ้าของ) → ?utm_source=ig / tiktok
- 🛠️ **งาน CC — ทางแก้ถาวร:** สร้างหน้า redirect path-based `/go/{yt,pinterest,fb,ig,tiktok,threads}` → 301 → `/links?utm_source=<platform>` · path รอดทุกแพลตฟอร์ม (รวม Pinterest ที่ตัด query) → แล้ว bio ทุกช่องชี้ `/go/<platform>` (Cowork/เจ้าของอัปเดตทีหลัง) · clean สุด
- 📌 **จนกว่า /go ขึ้น:** ใส่ `?utm_source=<platform>` ที่ **ลิงก์คอนเทนต์** ทุกครั้ง — FB โพสต์/คอมเมนต์แรก=fb · Pinterest pin destination=pinterest · IG/TikTok caption=ig/tiktok — อัปเดต POST-PACK + daily reminder template ให้ทำอัตโนมัติ

## C. commit report+order (media/local ไม่ commit) · push ปกติ · build_site.py = push แยกท้ายสุด
