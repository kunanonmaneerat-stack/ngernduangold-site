# ✅ 2 สเตปสุดท้ายปลดล็อกรายได้ (งานในบัญชีเจ้าของ — ผมเตรียมโค้ดรอแล้ว)

## Step 1 — ดึงลิงก์ AccessTrade ประกัน/กองทุน (~2 นาที)
ผมเข้าแทนไม่ได้ (ล็อกอิน + กด Join/ยอมรับเงื่อนไข = ต้องเป็นคุณ) · ยืนยันแล้วว่า AccessTrade มีหมวด **Financial** (200+ แคมเปญ)
1. Login publisher AccessTrade → Dashboard
2. เมนู **แคมเปญ/Campaigns** → filter **Financial / ประกัน**
3. หาแคมเปญ: **ประกันสุขภาพ/ชีวิต** (เช่น เมืองไทย, AXA, FWD, Cigna, Rabbit) + **กองทุน/ลงทุน** (ถ้ามี)
4. กด **Join** (ถ้ายังไม่เข้าร่วม) → **Get Link** → copy ลิงก์ `atth.me/...`
5. **วางลิงก์ในแชต** บอกว่าอันไหน = ประกันสุขภาพ / ชีวิต / กองทุน
   → ผม wire เข้า build_site.py ให้ทันที → หน้า health-insurance / tax / invest convert ได้เลย

## Step 2 — เปิด GSC keyword (re-consent ครั้งเดียว) ✅ โค้ดแก้แล้ว
ผมเติม scope `webmasters.readonly` ใน ga4_auth.py ให้แล้ว เหลือคุณรัน 1 ครั้ง:
```
cd C:\Users\nL_ku\ngernduangold-site
py pipeline\ga4_auth.py
```
→ เบราว์เซอร์เปิด → เลือกบัญชี Google (เจ้าของ GSC) → ถ้าเตือน unverified: **Advanced → Go to app → Allow** (จะเห็นขอสิทธิ์ Search Console เพิ่ม)
→ เสร็จ! weekly loop จันทร์หน้าจะมี **คีย์เวิร์ด GSC** ครบ (ชี้คีย์อันดับ 6-20 ดันขึ้นหน้า 1)

**ทางเลือกไม่ต้อง re-consent:** Search Console → Performance → Export → save เป็น `automation-log\gsc-queries.csv`

---
ทำเสร็จอันไหนบอกผมได้เลย · Step 1 วางลิงก์มา = ผมทำให้ทันที
