# ✅ GA4 เชื่อมเกือบเสร็จ — เหลือ 4 ขั้นที่คุณทำเองในเบราว์เซอร์ปกติ (~3 นาที)

> ผมตั้งให้หมดแล้ว: Property ID, Data API, OAuth consent screen, โค้ด, ไลบรารี
> ติดอย่างเดียว: ดาวน์โหลดไฟล์ client_secret ผ่าน "เบราว์เซอร์อัตโนมัติ" ไม่ลงที่ที่ระบบเข้าถึงได้
> → ขั้นที่เหลือให้ทำใน **Chrome ปกติของคุณ** (ไฟล์จะลง Downloads จริง)

## สิ่งที่เสร็จแล้ว (ไม่ต้องทำซ้ำ)
- Property ID = **541618281** (ตั้ง ENV GA4_PROPERTY_ID ให้แล้ว)
- GA4 บันทึก event **affiliate_click = 33 ครั้ง** แล้ว (conversion มีข้อมูลรออยู่จริง)
- Data API = เปิดแล้ว · OAuth consent screen = ตั้งแล้ว (Internal)
- โค้ด ga4_auth.py + ga4_pull.py (รองรับ OAuth token) + ไลบรารี = พร้อม

## 4 ขั้นที่เหลือ (ทำใน Chrome หน้าต่างปกติของคุณ)
1. เปิด **https://console.cloud.google.com/auth/clients?project=project-dfe909e5-2bf4-431e-824**
   → กด **+ Create client** → Application type = **Desktop app** → Create
   → ในกล่องที่เด้ง กด **Download JSON** (คราวนี้ไฟล์จะลง Downloads ของคุณจริง)
   *(client เก่า 2 อันที่ผมลองสร้างไว้ ลบทิ้งหรือปล่อยไว้ก็ได้ — ใช้อันใหม่ที่โหลด JSON สำเร็จ)*
2. ย้าย/เปลี่ยนชื่อไฟล์ที่โหลดมา → วางที่
   `C:\Users\nL_ku\ngernduangold-site\secrets\ga4-client.json`
   *(โฟลเดอร์ secrets gitignore แล้ว ไม่หลุด repo)*
3. เปิด PowerShell แล้วรัน (เบราว์เซอร์จะเด้งให้ล็อกอิน → กด **Allow**):
   ```
   py C:\Users\nL_ku\ngernduangold-site\pipeline\ga4_auth.py
   ```
   สำเร็จจะขึ้น: `OK -> เซฟ token ที่ ...ga4-token.json`
4. รันดึงข้อมูลจริง:
   ```
   py C:\Users\nL_ku\ngernduangold-site\pipeline\ga4_pull.py
   ```
   สำเร็จจะขึ้น: `OK -> ga4-metrics.csv | ช่อง=.. sessions=.. quiz=.. conv=..`

เสร็จแล้ว loop ปิดวง: ทุกวัน run_daily จะดึง conversion เข้า analyst → verdict ฟันได้จริง
> ติดตรงไหน ส่ง error มา / หรือบอกผมว่าโหลด JSON เสร็จแล้ว เดี๋ยวผมรัน ga4_auth + ga4_pull ให้ต่อ
