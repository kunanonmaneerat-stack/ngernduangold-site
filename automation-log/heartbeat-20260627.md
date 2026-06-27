# ngernduangold — Channel Heartbeat 2026-06-27 (กลางวัน ~14:30 ICT)

_ตรวจ+รายงานอย่างเดียว ไม่โพสต์เอง · cadence ต่างกันตามแผน (กัน shadowban)_
_วันนี้เป็นวัน "ครบทุกช่อง": Cowork รัน push ทุกช่อง autonomous (EOD doc 11:46) → 7/7 มีคอนเทนต์สดวันนี้_

| ช่อง | cadence ที่คาดหวัง | อัปเดตล่าสุด / วันนี้ (27 มิ.ย.) | สถานะ |
|---|---|---|---|
| Pantip | ทุกวัน ≤5/วัน | **4 LIVE** brand 9373300 (social-ops 08:38, GATE_OK 0 fix, value-first ไม่แปะลิงก์) · blocker wrong-acct แก้แล้ว | ✅ ตามแผน |
| Threads | ทุกวัน 1/วัน | **2 LIVE** /post/DaEjJw9iRW8 (จำนำทะเบียน เช้า) + เครดิตบูโรเช็กฟรี (Cowork) | ✅ ตามแผน |
| Facebook | ลื่นไหล (เตือน >14วัน) | **1 LIVE** loan-online-legal-2026 · การ์ด OG ขึ้น NGERNDUANGOLD.COM ถูกต้อง | ✅ ตามแผน |
| Instagram | ลื่นไหล (เตือน >14วัน) | **1 LIVE** รูป /p/DaFi8CdIKY7/ + ลิงก์ในคอมเมนต์แรก (reel เย็นรอ token) | ✅ ตามแผน |
| TikTok | manual/ความถี่ต่ำ (เตือน >~10วัน) | **1 LIVE** debt-consolidate (content mgr, 24 โพสต์) — **restart วันนี้ หลังเงียบตั้งแต่ 06-16 (~11วัน)** | ✅ ตามแผน (เพิ่งปลุก) |
| YouTube | ลื่นไหล (เตือน >14วัน) | **1 Short LIVE (Public)** M2TyHVnWkKU เครดิตบูโร · ช่อง 5→6 วิดีโอ | ✅ ตามแผน (เพิ่งขึ้น) |
| Pinterest | 2-3/สัปดาห์ (เตือนถ้า >7วันไม่มี pin) | **มี pin ใหม่วันนี้** (onboarding แก้แล้ว) · PACK 5 pin lead + QUEUE อีก 10 | ✅ ตามแผน (เพิ่งเริ่มจริง) |

## ช่องที่ต้องสนใจ (ทุกช่อง ✅ วันนี้ — เป็นการเฝ้าเชิงรุก ไม่ใช่ของพัง)
1. **TikTok** — เพิ่ง restart วันนี้หลังเงียบ ~11วัน. คงโพสต์มือ/ความถี่ต่ำ (ห้าม bot-post = ต้นเหตุ shadowban). เฝ้าไม่ให้คลิปถัดไปสลิปกลับไปเงียบ >10วันโดยไม่ตั้งใจ.
2. **YouTube** — Short ตัวแรกจาก batch 4 ขึ้นแล้ว · อีก 3 ตัว (emergency-fund/debt-consolidation/first-credit-card) พร้อม — ทยอยปล่อย. description (ลิงก์ .com) ต้องเติมมือ ~20วิ (YT = Lexical ใส่อัตโนมัติไม่ได้).
3. **Pinterest** — คำถามค้าง "ตั้งค่าหรือยัง" = ปิดแล้ว: onboarding ผ่าน + pin ขึ้นวันนี้. ต่อไปรักษา 2-3/สัปดาห์จาก QUEUE — อย่ารัว (บัญชีใหม่).
4. **Pantip automation (CC)** — วันนี้ผ่านเพราะ blocker brand-acct แก้แล้ว (4/5). เฝ้าให้ CC daily ล็อกอิน brand 9373300 ค้างถาวร ไม่ใช่ personal 8912721 ไม่งั้นเช้าถัดๆ ไป fail-closed อีก.
5. **owner ค้าง (จาก EOD):** รีเฟรช Meta token (→ IG reel เย็นกลับมา + ปลด Meta MCP rate-limit ให้ heartbeat เช็ก FB/IG สดได้) · FB "ลิงก์ที่ยืนยันแล้ว" + IG bio ยังเป็น netlify เก่า → แก้เป็น .com.

## หมายเหตุการตรวจ
- Meta MCP (get_facebook_posts/get_instagram_posts) = **rate-limited (Free plan, ครบโควตาสัปดาห์)** → ยืนยัน FB/IG ไม่ได้ผ่าน API. ใช้ permalink ที่ Cowork verify ผ่าน browser วันนี้ + GA4 แทน (ไม่ใช่ "พัง" — แค่เช็กสดซ้ำผ่าน MCP ไม่ได้).
- หลักฐาน: 2026-06.jsonl (social-ops 08:38 ok: pantip 4 / threads 1), _eod_allchannels_20260627.md (FB/IG/TikTok/YT permalink browser-verified), _pinterest_PACK/QUEUE_20260627.md, _MASTER-OVERVIEW_20260627.md.
