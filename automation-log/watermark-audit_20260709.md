# Watermark audit (Veo ✦ sparkle) — 2026-07-09/10 · detector = tiktok-pipeline/src/qa_watermark.py (NCC astroid template)
วิธี: ffmpeg สุ่มเฟรม fps=3 ทั้งความยาว → template-match รูป ✦ (astroid, NCC≥0.78 — คาลิเบรต: ✦ จริง ~0.95, คอนเทนต์สว่างสุด ≤0.69) ในโซนขวาล่าง → นับเฟรมซ้ำเชิงตำแหน่ง (สแปกเคิลกระพริบ/ดริฟต์) · FAIL = ≥4 เฟรม & ≥15%

## ผลรวม: FAIL 8 · PASS 24
| ไฟล์ | ผล | track | drift bounds (src px) |
|---|---|---|---|
| media/clips/title-loan-2026.mp4 | ❌ FAIL | 30/30 | x571-629 y1131-1189 |
| media/clips/credit-bureau-check-2026.mp4 | ❌ FAIL | 28/30 | x571-629 y1131-1189 |
| media/clips/refinance-home-2026.mp4 | ❌ FAIL | 23/30 | เดียวกัน |
| media/clips/salary-budgeting-2026.mp4 | ❌ FAIL | 23/30 | เดียวกัน |
| media/clips/emergency-fund-2026.mp4 | ❌ FAIL | 11/30 | เดียวกัน |
| media/clips/debt-consolidation-2026.mp4 | ❌ FAIL | 9/30 | เดียวกัน |
| media/clips/first-credit-card-student-2026.mp4 | ❌ FAIL | 8/30 | เดียวกัน |
| _vidout/hybrid_debt.mp4 | ❌ FAIL | 7/30 | x856-943 y1696-1783 (1080p; **ทะลุ scrim**) |
| _vidout/reel_*.mp4 (7 ไฟล์) | ✅ PASS | 0 | — |
| _social-stage/_final_* (16) + ebook-promo | ✅ PASS | 0 | — |
| _vidout/clean/reel_*_clean.mp4 (5 ใหม่) | ✅ PASS | 0 | — |

## ROOT CAUSE (หลักฐานจากโค้ด + สแกน)
1. **ทุกไฟล์ media/clips (Veo ดิบ) มี ✦ 7/7** — home zone คงที่: **x 79-87% · y 88-93%** ของเฟรม (ดริฟต์เล็กในกล่องนี้ + กระพริบ จึงตรวจเจอเป็นช่วงๆ)
2. **scrim ของ _hb_batch.py เป็นแบบกึ่งโปร่ง (alpha สูงสุด 0.90, ไล่เฉดจาก y=60%)** → ที่ตำแหน่ง ✦ alpha ~0.85-0.90 = ลายน้ำ "ทะลุ" บนฉากสว่าง — พิสูจน์ด้วย hybrid_debt.mp4 ที่ FAIL ทั้งที่มี scrim (✦ อยู่ y88-93% ใต้ scrim แต่ยังเห็น) → 5 reel IG ที่หลุดคือ render ตระกูลนี้ (สำเนา local ถูกล้างไปแล้ว)
3. รูโหว่ verify: task video-post-verify เดิมเช็ก resolution/แคปชัน/ชื่อไฟล์ — ไม่เคย frame-scan → ปิดแล้ว (T4)
- หลักฐานเฟรม (กรอบแดงชี้ ✦): automation-log/wm-evidence/*.png
