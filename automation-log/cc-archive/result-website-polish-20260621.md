# RESULT → Cowork: ยกระดับหน้าตาเว็บ (build_site.py) — เสร็จ + verified

## ✅ สิ่งที่แก้ (build_site.py เท่านั้น · ไม่แตะ funnel/affiliate/UTM)
1. **Trust band ใต้ header ทุกหน้า** (ใส่ใน `head()` → ขึ้นทั้ง 32 หน้าจริง)
   `🗓 อัปเดต 2026 · 🔗 อ้างอิงหน้าทางการของผู้ให้บริการ · ⚖️ เทียบหลายเจ้าก่อนตัดสินใจ`
   สไตล์เบา var(--gold-soft)/var(--line) · มือถือยุบฟอนต์/แถวอัตโนมัติ
2. **Hero มีชีวิต** — SVG inline (กราฟขาขึ้นเส้นทอง) เป็น `.hero:before` พื้นหลังจาง .45 (ไม่โหลดรูปนอก, ไม่บัง content, z-index แก้ให้ตัวอักษรอยู่บน)
3. **ไอคอนหมวดบนการ์ด** — JS เติม emoji ตามหมวด (💳 บัตรเครดิต · 🏦 ออม · 💵 สินเชื่อ · 🏠 รีไฟแนนซ์/บ้าน · 🛡️ ประกัน · 📈 ลงทุน · 🧮 หนี้ · 🚗 รถ) แบบ global ใน SITE_JS · idempotent · ไม่แตะ markup การ์ดทีละอัน
4. **มือถือ tap target** — bump padding nav + ปรับ trust band/hero ที่ ≤600px

## 🔎 Verify (build จาก repo จริง)
- `python3 build_site.py` → BUILD_OK · 33 หน้า HTML
- affiliate links (atth.me) คงอยู่ · quiz.html/links.html ครบ · GA G-17PPE0M1B8 คงอยู่
- trust band 32/33 (อีกหน้าคือ google-site-verification stub — ต้องเปล่าตามนั้น ✅)
- AST parse OK

## ⚠️ พบ+ซ่อม: build_site.py ถูกตัดท้าย (truncated)
ระหว่างงาน พบไฟล์ `build_site.py` ในเครื่องถูกตัดกลางคำสั่งเขียน quiz.html (หายตั้งแต่ ~บรรทัด 1440 ถึงท้าย) — build แรกผ่าน แต่รอบถัดมาพัง = มี process ฝั่งเครื่องเขียนทับ/ตัดไฟล์ระหว่างทาง (ไม่ใช่จากการแก้เนื้อหา)
**กู้แล้ว:** ดึงตัวเต็มจาก `git HEAD` (1439 บรรทัด, valid) แล้ว splice = [ส่วนหน้าที่มี edit] + [tail สมบูรณ์จาก git] → ไฟล์สมบูรณ์ 1463 บรรทัด parse+build ผ่าน
> เฝ้าระวัง: ถ้าเปิด build_site.py ค้างใน editor ฝั่ง Windows ตอนผมแก้ อาจเขียนทับกันได้ — ปิด editor ก่อนให้ผมแก้ไฟล์เดียวกัน

## ▶️ ขั้นต่อไป (owner — deploy)
ผมไม่ commit/push ให้ (กฎความปลอดภัย) — เจ้าของรันเอง:
```
cd C:\Users\nL_ku\ngernduangold-site
py build_site.py            # rebuild ./site ด้วย env จริงของคุณ
git add build_site.py site
git commit -m "polish: trust band + hero motif + card icons + mobile tap targets"
git push                    # Netlify auto-deploy
```
หรือถ้า Netlify build เองจาก build_site.py ก็ push แค่ build_site.py พอ
