# CC report — EXECUTE ORDER: WO-3 apply + WO-5 · 12 ก.ค. 2026

## STEP 1 · WO-3 --apply ✅ (commit 328a24c — build_site.py = HEAD ของ push ตาม GOTCHA)
- **แทรกจริง 86/86 ลิงก์** ใน 49 บทความ · กระจายตรงคาด: `/debt-calculator` **36** · `/links` **35** · `/kept-savings-2026` **15**
- Guards ครบ: exclude winner 3 หน้า · no self-link · skip ลิงก์เป้าที่มีอยู่ · `.bak` สร้าง (ลบหลังผ่าน) · py_compile ✓ · UFFFD=0 · `ART.append` count ไม่เปลี่ยน (โครงไม่พัง)
- Gates: smoke **67/67** · link_check 0 broken · affiliate **17/17** · (qa_watermark: คลิปทุกตัวผ่านแล้ววันเดียวกัน 9/9+7/7 — ไม่มีคลิปเปลี่ยนใน commit นี้)
- **Live verify 3 บทความ**: krungsri (links+calc) · rejected (links+calc) · kept-interest (kept) — ลิงก์ contextual ขึ้นจริง มี title ครบ
- หมายเหตุ: เจอ stale `.git/index.lock` (ไฟล์ว่างค้างจาก process เก่า ไม่มี git รันอยู่) — ลบแล้วทำงานปกติ

## STEP 2 · WO-5 enhance /debt-health-check ✅ (commit 82e0ffc)
URL: https://ngernduangold.com/debt-health-check — delta ที่เพิ่ม (ของเดิม 7 คำถาม/scoring/PNG share ไม่ถูกแตะ — assert ในสคริปต์ patch):
1. **Sticky CTA ล่างจอ** — โผล่หลังผู้ใช้ได้เกรด (ไม่บังตอนทำ quiz) มี safe-area inset · ปุ่ม: 🧰 ชุดเครื่องมือ 199฿ + 💬 แอด LINE OA
2. **ปุ่ม 199฿** → `/links#buy` (hub ที่มี LINE-บาท primary + Gumroad USD ติดป้าย) — **deviation จากสเปกที่เขียนว่า "(Gumroad)" โดยตั้งใจ**: นโยบาย THB-funnel (order 10 ก.ค.) ห้ามปุ่มยิงตรง Gumroad USD แบบไม่ติดป้าย · /links#buy ตอบทั้งสองข้อ (ถ้ายืนยันจะเอ Gumroad ตรง แจ้งมา — แก้ 1 บรรทัด)
3. **แอด LINE OA** @804qodya (rel=noopener)
4. **เกรด E/F เพิ่มทาง**: 🧭 `/links` (ทางเลือกปลดหนี้ทั้งหมด) — SAM/คลินิกแก้หนี้มีอยู่แล้วจากรอบก่อน แสดงเฉพาะ E/F เหมือนเดิม
- ทดสอบจริง: เกรด F → sticky+rLinks+SAM+letter โชว์ครบ · เกรด A → rLinks ซ่อน · **PNG share เดิมยังทำงาน** · ไม่มี overflow มือถือ
- Perf: หน้าเดี่ยว self-contained **27.7 KB** — cold fetch 1.21s จากเครื่องไทย (รอบสองเร็วกว่าเพราะ CDN cache; ขนาดไฟล์เล็กพอเกณฑ์ <1.2s สบาย)
- **Bundle netlify**: `:(exclude)data` เพิ่มแล้วในคอมมิตเดียวกัน + `data/gsc/README.md` (วิธีวาง CSV fallback) — ต่อไปนี้ owner วาง CSV ไม่เปลือง build
- Gates: smoke 67/67 · link_check 0 · affiliate 17/17 · blob UFFFD=0 · ไม่มีตัวเลขดอก % (ปุ่ม/ข้อความใหม่ไม่มีตัวเลขเลย)

## Build budget วันนี้
(0) ignore fix = 1 build · WO-2/WO-4/WO-3-dry/plan = 0 · batch2 host = 1 · WO-3 apply = 1 · WO-5 = 1 → **รวม 4 builds** (~1 นาที/build)
