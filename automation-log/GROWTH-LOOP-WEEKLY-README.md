# 🔁 Weekly Growth Loop — คู่มือ (ngernduangold)

## ทำอะไร
ทุกวันจันทร์ 9 โมง (อัตโนมัติ): ดึงข้อมูลจริง GA4 + GSC → จัดอันดับ winner → บอก "ขยายผลอะไรต่อ"
ส่งเข้า **Telegram** + สรุปใน **Cowork** ให้เลย · ไม่ต้องทำเอง

## ชิ้นส่วน (pipeline/)
- `ga4_pull.py` — GA4 ราย source + **ราย page (ใหม่)** → ga4-metrics.csv / ga4-pages.csv
- `gsc_pull.py` — คีย์เวิร์ดจาก Search Console → gsc-queries.csv
- `weekly_growth_review.py` — รวม → จัดอันดับ → weekly-growth-YYYYMMDD.md
- `run_weekly.cmd` — รันทั้ง 3 ต่อกัน
- Cowork scheduled task: `weekly-growth-review-ngernduangold` (จันทร์ 9:00)

## รันเองตอนไหนก็ได้
```
cd C:\Users\nL_ku\ngernduangold-site
cmd /c pipeline\run_weekly.cmd
```

## เปิด "คีย์เวิร์ด GSC" (ตอนนี้ยังปิด — ติด scope)
GA4 token ปัจจุบันมีแค่ scope analytics ยังอ่าน Search Console ไม่ได้ (403). เลือกอย่างใดอย่างหนึ่ง:
- **ออโต้:** re-consent OAuth เพิ่ม scope `webmasters.readonly` → รัน `pipeline\ga4_auth.py` ใหม่ (เพิ่ม GSC scope) แล้ว gsc_pull จะดึงได้เอง
- **มือ (เร็วสุด):** Search Console → Performance → Export → save เป็น `automation-log\gsc-queries.csv` (คอลัมน์ query,clicks,impressions,ctr,position)

## อ่านผลยังไง
- **ช่องแปลงดี** → ทุ่มคอนเทนต์ช่องนั้นเพิ่ม
- **บทความ winner** → เขียนหัวข้อใกล้เคียง + ตั้งคิว Threads ดันซ้ำ
- **หน้ารั่ว** (คนเข้า 0 คลิก) → ปรับ CTA/ลิงก์ให้ตรง intent
- **GSC อันดับ 6-20** → ปรับ on-page ดันขึ้นหน้า 1
