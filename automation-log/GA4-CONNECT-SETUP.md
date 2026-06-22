# 🔌 เชื่อม GA4 → ปลดล็อก verdict (owner ทำครั้งเดียว ~10 นาที, ฟรี)

> ทำไม: ตอนนี้ loop วัด reach ได้ (Meta) แต่ไม่มี conversion → analyst ค้าง INSUFFICIENT
> เชื่อม GA4 แล้ว `ga4_pull.py` จะดึง sessions/quiz_start/conversion จริงเข้า loop ทุกวันอัตโนมัติ
> **ส่วนที่ Cowork ทำแทนไม่ได้ = การกด Authorize / สร้าง service account (ต้องเป็นคุณ)** ที่เหลือผมต่อโค้ดให้พร้อมแล้ว

เว็บมี GA4 tag ติดอยู่แล้ว (G-17PPE0M1B8) — งานนี้แค่เปิดสิทธิ์ให้สคริปต์ "อ่าน" ข้อมูลออกมา

## 4 ขั้นที่คุณต้องกดเอง
1. **หา Property ID (ตัวเลข)** — GA4 → Admin (เฟือง) → Property settings → คัดเลขใต้ชื่อ เช่น `412345678`
   (คนละตัวกับ Measurement ID `G-17PPE0M1B8`)
2. **เปิด Data API + สร้าง Service Account** — ที่ https://console.cloud.google.com
   - สร้าง/เลือกโปรเจกต์ (ฟรี) → "APIs & Services" → Enable **"Google Analytics Data API"**
   - "Credentials" → Create credentials → **Service account** → สร้างเสร็จเข้าไปที่ tab **Keys** → Add key → JSON → ดาวน์โหลด
   - วางไฟล์ที่ `C:\Users\nL_ku\ngernduangold-site\secrets\ga4-sa.json` (โฟลเดอร์นี้ gitignore แล้ว ไม่หลุดขึ้น repo)
3. **ให้ service account อ่าน GA4 ได้** — GA4 → Admin → Property Access Management → "+" → ใส่อีเมล service account
   (ลงท้าย `@...iam.gserviceaccount.com` ที่อยู่ในไฟล์ json) → สิทธิ์ **Viewer**
4. **ตั้งค่า + ติดตั้ง + ทดสอบ** ใน PowerShell:
   ```
   setx GA4_PROPERTY_ID "ใส่เลข_property_id_ของจริง"
   py -m pip install google-analytics-data google-auth
   py C:\Users\nL_ku\ngernduangold-site\pipeline\ga4_pull.py
   ```
   สำเร็จจะเห็น: `OK -> ga4-metrics.csv | ช่อง=.. sessions=.. quiz=.. conv=..`

## หลังเชื่อมแล้วเกิดอะไร
- `ga4-metrics.csv` ถูกสร้าง → `traffic_analyst` อ่านอัตโนมัติ → verdict เปลี่ยนจาก "ยังไม่เชื่อม" เป็นตัวเลขจริง
- พอมี reach + คนคลิกเข้าเว็บ → verdict จะฟันได้จริง (PROVEN/REFUTED) ตามกฎคุณ
- รันเองทุกวันแล้ว (อยู่ใน run_daily.cmd ก่อน analyst) — ไม่ต้องสั่งซ้ำ

## (ออปชัน) ให้ conversion เป๊ะขึ้น
- quiz_start นับจากการเปิดหน้า `/quiz` อัตโนมัติ — ใช้ได้เลย ไม่ต้องตั้งอะไร
- conversion (คลิกออกไป AccessTrade) ตั้ง GA4 event ชื่อ `affiliate_click` ที่ปุ่มลิงก์
  (หรือเปลี่ยนชื่อ event ที่จะนับผ่าน ENV `GA4_CONV_EVENT`)
- ไม่ตั้งก็ได้ — เริ่มจาก sessions + quiz_start ก่อนก็พอปลดล็อก loop

> ⚠️ อย่า commit ไฟล์ `secrets/ga4-sa.json` (gitignore กันให้แล้ว) · ถ้าคีย์หลุดให้ revoke ใน Cloud Console
