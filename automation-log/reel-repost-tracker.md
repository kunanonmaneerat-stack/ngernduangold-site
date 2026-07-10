# Reel repost tracker — avoid duplicate posting (Cowork)
RULE: post ONE asset per topic. Deleted reels are GONE from IG so clean reposts are NOT duplicates. Before posting: check tracker + posted-log + LIVE IG grid. Never post same clip/topic twice.

| topic | source Flow clip | Cowork footage reel | chosen | POSTED? |
|---|---|---|---|---|
| title-loan | title-loan-2026.mp4 | reel_title-loan_footage.mp4 | FOOTAGE | ✅ POSTED 2026-07-10 (Reel, caption+disclosure+hashtags, verified "แชร์แล้ว") |
| emergency-fund | emergency-fund-2026.mp4 | reel_emergency-fund_footage.mp4 | FOOTAGE | NOT YET (post 2026-07-11, 1/day) |
| compound-interest | (no Flow clip) | - | KINETIC (CC _vidout/clean) | NOT YET |
| save-small / jars | (no Flow clip) | - | KINETIC (CC _vidout/clean) | NOT YET |
| auto-save | (no Flow clip) | - | KINETIC (CC _vidout/clean) | NOT YET |

## LEARNINGS (2026-07-10 posting)
- COVER FIX: the opening `fade=t=in` makes frame 0 BLACK -> IG default reel cover is black. For future reels REMOVE the opening fade (keep only a short fade-out or none) so frame 0 = woman + hook = good auto-cover. (title-loan posted with a dark cover; acceptable one-off; can be edited in-app.)
- POSTING RECIPE THAT WORKS (IG web, OS control):
  1. Fresh IG window: `Start-Process chrome "--new-window https://www.instagram.com/ngernduangold/"` (avoids the broken CDP tab + IME URL mangling).
  2. โพสต์ใหม่ -> โพสต์ -> เลือกจากคอมพิวเตอร์.
  3. File dialog: copy reel to C:\Users\nL_ku\Downloads first (short path). Click the filename EDIT field BY LABEL (Windows-MCP Click), then Windows-MCP Shortcut `ctrl+a` then `ctrl+v` (clipboard has the path). SendKeys ^v does NOT work; Windows-MCP Shortcut ctrl+v DOES. Click "เปิด".
  4. Crop: เลือกครอบตัด -> 9:16 -> ถัดไป.
  5. Edit screen (cover): skip if fade-in removed. ถัดไป.
  6. Caption: Set-Clipboard the caption (Thai+emoji OK via PowerShell here-string), click caption field BY LABEL, Shortcut ctrl+v. Verify char count.
  7. แชร์ -> wait ~6s -> "แชร์คลิป Reels ของคุณแล้ว" = success.
- Gotchas: window keeps resizing (raw-mouse coords drift, unreliable — prefer Windows-MCP Click BY LABEL). Stray cmd.exe/File Explorer windows steal focus (minimize via ShowWindow). ESC to a dialog needs AppActivate('เปิด') first.

## 2026-07-10 — TikTok: title-loan (clean) ✅ POSTED
- ช่อง: TikTok @ngernduangold
- ไฟล์: reel_title-loan_clean.mp4 (no-fade, clean cover, 1080P, 3.46MB)
- URL: https://www.tiktok.com/@ngernduangold/video/7653075156079742226
- แคปชัน: "รถยังอยู่ เงินก็หมุนได้ 🚗..." + disclosure (มีลิงก์พันธมิตร · ผลิตด้วย AI) + 7 hashtags, ไม่มีลิงก์ (ลิงก์อยู่ใน bio)
- สถานะ: อยู่ระหว่าง TikTok review (จะ auto public) — visibility ตั้ง ทุกคน
- วิธี: OS upload — filename field via Windows-MCP Type(label,clear,press_enter); caption via Set-Clipboard+ctrl+a+ctrl+v
- LEARNING: Windows-MCP Type(label=<id>, text, clear=true, press_enter=true) วางลง filename edit ได้ชัวร์กว่า raw-click; Shortcut ต้องส่ง string "ctrl+v" ไม่ใช่ list

### สถานะโพสวันนี้ (10 ก.ค.) — 1/ช่อง/วัน
- IG ✅ title-loan (เช้า) | FB ✅ debt-calculator 03:32 | Threads ✅ auto 08:53 | TikTok ✅ title-loan 09:01 | YouTube ⏳ ถัดไป | Pinterest (รายสัปดาห์)

### แก้สถานะ YouTube (10 ก.ค. 09:10) — ตรวจซ้ำแล้ว
- YouTube มี Short ตั้งเวลาไว้ของ "วันนี้" อยู่แล้ว: "ขอกู้ไม่ผ่าน...เช็กเครดิตบูโร" (credit-score, 10 ก.ค.)
- Pipeline คุม 11–13 ก.ค. (emergency ถอนได้ทันที / title-loan มีรถ=ทางเลือก / รวมหนี้ก้อนเดียว) และ 15–19 ก.ค.
- => สลอต 1/วัน ของ YouTube วันนี้เต็มแล้ว → ไม่โพสต์ compound-interest ซ้ำ (กัน double-post/shadowban)
- compound-interest_clean.mp4 พร้อมใน Downloads + _vidout/clean สำหรับสลอตว่างในอนาคต

## ✅ สรุปการโพสต์วันนี้ (10 ก.ค. 2026) — ครบทุกช่อง เคารพ 1/ช่อง/วัน
| ช่อง | เนื้อหา | สถานะ |
|---|---|---|
| Instagram | title-loan (คลิปสะอาด) | ✅ โพสต์แล้ว (เช้า) |
| Facebook | debt-calculator | ✅ โพสต์แล้ว 03:32 |
| Threads | การเงินไม่มีสูตรเดียว | ✅ auto 08:53 |
| TikTok | title-loan (clean cover) | ✅ Cowork โพสต์ 09:01 |
| YouTube | credit-score #Shorts | ✅ pipeline ตั้งเวลาไว้ (วันนี้) |
| Pinterest | (รายสัปดาห์) | – ครั้งถัดไปตามรอบ |
| Pantip | (ร่างรีวิวเท่านั้น) | – FINAL WARNING, ไม่ auto |
