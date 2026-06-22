# 📊 รายงานทบทวนรายสัปดาห์ — เงินเดือนสมองทอง (2026-06-22)
ช่วง 15–21 มิ.ย. 2026 · ที่มา: GA4(UI 541618281) · GSC(UI) · Meta MCP(583765282304956) · automation-log

## TL;DR
เครื่องยนต์พร้อม (เว็บ/ฟันเนล/อีเวนต์/คอนเทนต์ 36 คลิป) แต่ **คอขวด = การกระจาย (distribution)** — แทบไม่มีคอนเทนต์ถึงคนจริง: FB reach 0 · IG ถูกระงับ · YT นิ่ง · TikTok อัปมือ · Threads 1/8 ช่องเดียวที่ส่งคนจริงคือ Pantip (เล็กแต่ intent สูง)
**โฟกัสสัปดาห์หน้า = อัด Pantip ห้องสินธร 5–8 คำตอบ value-first/วัน** + แก้บั๊ก sub_id ไม่ถึง AccessTrade (ตอนนี้วัด conversion รายช่องไม่ได้)

## 📊 ตัวเลขสัปดาห์นี้ (7 วัน)
| ตัวชี้วัด | ค่า | อ่านว่า |
|---|---|---|
| Active users (GA4) | 22 (+29%) · TH 11 / ต่างชาติ-บอท ~11 | เล็กมาก ยังปนภายใน/บอท |
| Top page (views) | /links 77 · home 41 · /quiz 14 · /contact 14 | hub ถูกเห็นมากสุด (ส่วนใหญ่ internal/test) |
| Sessions/channel | Unassigned 47 · Organic Social 17 · Direct 8 · Referral 2 · Organic Search 1 | organic search ≈ 0 |
| affiliate_click | ~1/วัน · CTR ≪ 5% | ยังไม่มี intent click จริง |
| quiz_complete | 0 | ฟันเนลยังไม่ปิด |
| GSC (clicks/impr) | 0 / 0 · index = "processing" | SEO ยังไม่ขึ้น (เว็บใหม่ รอ 1–3 เดือน) |
| FB reach (last_7d) | engagement 0 · views 0 | ยืนยัน reach ตาย (ฐาน 1,000 ยุคเกม) |
| AccessTrade | clicks 99/7d · conversion 0 · **Sub ID ว่าง** | คลิกมีจริง แต่ sub_id ไม่ถึง AT |

**Short-form sessions/สัปดาห์:** fb 42 (ไม่ใช่ reach จริง = legacy/test) · ig 2 · tiktok 2 · yt 1 → **ไม่มี surface ทะลุ 10/สัปดาห์** จาก reach จริง = ยังไม่มีช่องให้ double-down
**Sub-id breakdown (clicks↔conversion/ช่อง):** ❌ ทำไม่ได้ — AccessTrade Sub ID tab ว่าง (utm_content ไม่ถึง AT) ต้อง patch param ก่อน reconcile.py ถึงจะมีข้อมูล

## 🎬 Liveliness (รอบ 14)
- ความถี่จริง: TikTok = อัปมือเท่านั้น (bot หยุด 19 มิ.ย.) · schedule clip 8–21 (27 มิ.ย.–10 ก.ค.) ยังไม่โพสต์ · IG **ถูกระงับ (วันที่ 2, token ปกติ)** · YT นิ่ง · Threads 1/8 · FB โพสต์มือ 1 (reach 0)
- comment-loop: IG 0 คอมเมนต์ · FB 2 โพสต์ คอมเมนต์ละ 1 (self-link) → ไม่มีคอมเมนต์ผู้ใช้จริงให้ตอบ
- Stories: ไม่พบหลักฐานดึง sessions ขึ้น (ig sessions=2 + IG ระงับ) → **ลด Stories กลับโฟกัส short-form + Pantip** ตามเกณฑ์ "1 สัปดาห์ไม่ขยับ"
- format engagement: โพสต์จริงน้อยเกินชี้ format ที่ดีสุด (ข้อมูลไม่พอ)
- คอนเทนต์: 36 คลิปพร้อม · เครดิตเหลือ 460/1000 → **หยุดเจน เก็บเครดิต** คอขวด = การโพสต์ (เจ้าของอัปเอง)

## 🎬 TikTok kill-criterion
posted 0/14 (schedule ปัจจุบัน future-dated) · โพสต์มือช่วงต้น ~2–3 คลิป · operation อายุ ~1 สัปดาห์
→ **ยังไม่ถึง 30 วัน = ยังไม่ตัดสิน** (รายงานความคืบหน้าเฉยๆ) · TikTok = อัปมือ low-freq ต่อ

## ✅ อะไรเวิร์ก
- **/links hub** = หน้าถูกเห็นมากสุด (77 views) · click-test 11/11 ยิง affiliate_click + sub_id ถูกต้อง → ระบบเก็บเงินพร้อม รอแค่คนเข้า
- **IG reach** มีจริง (194 views จาก 5 โพสต์) แต่ 0 click-through → reach ได้ แต่คอนเทนต์ไม่ดึงคลิก (และตอนนี้ IG ระงับ)
- **Pantip** = referral เล็กแต่จริง (6 sessions) + intent สูงสุด (ตาม Opus playbook) → ช่อง organic เดียวที่ควรอัด

## 🎯 โฟกัส 1 อย่าง สัปดาห์หน้า
**อัด Pantip ห้องสินธร 5–8 คำตอบ value-first/วัน** (ลิงก์เฉพาะ DM/โปรไฟล์ → /quiz) — intent สูงสุด เร็วสุด เป็น organic เดียวที่ส่งคนจริง ช่องอื่นไม่ส่งของ (FB reach 0 · IG ระงับ · TikTok มือ)
**ตัวเปิดทางที่ต้องทำคู่กัน:** patch sub_id เข้า AccessTrade (utm_content → AT Sub ID) ไม่งั้นวัดไม่ได้ว่าช่องไหนทำเงิน = บินตาบอด

## 🔔 เตือน routine
- Pantip ห้องสินธร 5–8 กระทู้/วัน + FB เพจหลัก 1 โพสต์/วัน (ลิงก์ในคอมเมนต์)
- เปิด dashboard.html (cockpit) + Pantip answer pack (pantip-engine-fresh-2026-06-21.md / 8 กระทู้ร่างพร้อม)

_อ้างอิงกลยุทธ์: playbook-traffic-conversion-hermes-flow-2026-06-21.md (Opus 4.8 W1 = อัด traffic intent สูง สะสม quiz_start ยังไม่แตะโค้ด)_
