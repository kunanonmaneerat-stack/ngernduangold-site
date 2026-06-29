# CC-TASK — IG Reel auto-publish ผ่าน Instagram Graph API
สร้างโดย Cowork · 2026-06-28 · สำหรับ CC (Claude Code, git-connected) รันต่อ

## เป้าหมาย
โพสต์คลิป `ebook-promo-9x16.mp4` (1080×1920, ไม่มีลายน้ำ ตรวจแล้ว) เป็น **Reel** ลง IG @ngernduangold
ปลายทาง caption → ngernduangold.com/links

## เงื่อนไขก่อนเริ่ม (ขั้นเดียวที่ต้องมือเจ้าของ — ห้ามวางใน chat)
เจ้าของวาง 2 ค่านี้ลง `secrets/meta-token.json` (gitignored):
- `app_secret` ← จากหน้า API-Setup (กด "แสดง")
- `access_token` ← จากปุ่ม Generate token (section 2) ของแอป ngernduangold-poster
(fb_app_id=1010612441371715, ig_app_id=3111313922396530 มีให้แล้ว)

## ข้อจำกัดสำคัญของ Graph API
IG media publish **ดึงวิดีโอจาก public URL เท่านั้น** — อัปไฟล์โลคัลตรงไม่ได้
→ CC ต้อง host ไฟล์ก่อน (ดู STEP 1)

## STEP 1 — host คลิปให้เป็น public URL
- เอา `outputs/ebook-promo-9x16.mp4` ไปวางใน public ของเว็บ เช่น `public/media/ebook-promo-9x16.mp4`
- commit + push → Vercel deploy
- ได้ URL เช่น `https://ngernduangold.com/media/ebook-promo-9x16.mp4` (ยืนยันเปิดได้จริงด้วย curl -I → 200, content-type: video/mp4)

## STEP 2 — ดึง ig_user_id
```
GET https://graph.instagram.com/me?fields=user_id,username&access_token={access_token}
```
เก็บ user_id ลง meta-token.json ช่อง ig_user_id

## STEP 3 — สร้าง media container (REELS)
```
POST https://graph.instagram.com/v21.0/{ig_user_id}/media
  media_type=REELS
  video_url={PUBLIC_URL จาก STEP 1}
  caption={CAPTION ด้านล่าง}
  access_token={access_token}
```
→ ได้ creation_id

## STEP 4 — poll สถานะ container จน FINISHED
```
GET https://graph.instagram.com/v21.0/{creation_id}?fields=status_code,status&access_token={access_token}
```
วน ~ทุก 5 วิ จนได้ status_code=FINISHED (ถ้า ERROR ให้อ่าน status แล้วหยุด รายงานเจ้าของ)

## STEP 5 — publish
```
POST https://graph.instagram.com/v21.0/{ig_user_id}/media_publish
  creation_id={creation_id}
  access_token={access_token}
```
→ ได้ media id = โพสต์ขึ้นจริง

## STEP 6 — verify + log
- GET media id permalink → เก็บลิงก์โพสต์
- เขียนผลลง automation-log (วันที่ + permalink)
- ถ้า token หมดอายุระหว่างทาง: แลก long-lived ด้วย ig_app_id+app_secret ก่อน refresh

## CAPTION (IG Reel)
```
จ่ายขั้นต่ำมาตลอด แต่หนี้ไม่ลดสักที? 📘
คู่มือ + Worksheet ปลดหนี้บัตรเครดิต — ทำตามได้จริงทีละขั้น
ไม่ขายฝัน มีทั้งวิธีลดดอก + ช่องทางฟรีของรัฐในเล่ม
59฿ · ลิงก์ในไบโอ → ngernduangold.com/links
#ปลดหนี้ #หนี้บัตรเครดิต #มนุษย์เงินเดือน #วางแผนการเงิน #เงินเดือนสมองทอง
```

## หมายเหตุ
- ห้าม push secrets · meta-token.json อยู่ใน .gitignore แล้ว
- เจ้าของ fact-check ข้อความก่อน publish
- TikTok: ไม่มี API ฟรีให้ auto-publish (Content Posting API ต้องสมัคร developer + review) → ลงมือถือด้วย POST-PACK เร็วกว่า
