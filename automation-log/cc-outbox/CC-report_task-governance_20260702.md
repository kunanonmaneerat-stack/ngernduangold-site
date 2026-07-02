# CC report — Task Governance (order-task-governance-20260702) — ✅ A-D ครบ · guard ลงก่อน 18:00
executed: 2026-07-02 ~15:30-16:00 · ไม่เปิด/ปิด task ใด ✓ (แก้เฉพาะเนื้อ prompt) · ไม่แตะ Pantip เว็บ/secrets/deploy ✓

## B) GUARD BLOCK ลงแล้ว 37 ไฟล์ (ก่อน deadline 18:00) — บล็อกมาตรฐานตามที่ order กำหนด วางบนสุดของ prompt (ใต้ frontmatter) · idempotent (มีแล้วไม่ซ้ำ)
- 🔴 ตัวเร่งด่วน: **ngernduangold-evening-check (รัน 18:07 วันนี้) ✓ ลงแล้ว+ตรวจแล้ว** · channel-heartbeat ✓ · threads-refill-weekly ✓ · pinterest-weekly ✓ · pantip-daily-opportunity ✓ · weekly-review ✓ · ig-weekly-pulse ✓ · video-post-verify ✓ · tiktok-daily-nudge ✓
- ตัวเพิ่มจาก audit (โพสต์/ร่าง/แนะนำโพสต์): pantip-monitor, comment-loop, delivery-verify, first-signal, delivery-heartbeat, daily-check, 4channel-cadence, weekly-traffic-review, loop-architect, agent-auditor, weekly-seo-money-review, weekly-growth-review-ngernduangold
- ตัว paused/disabled แต่โพสต์หนัก (กัน re-enable แล้วลืม): social-ops-daily, daily-pantip-threads-engine, queue-keeper, daily-cycle, tiktok-weekly-content-engine, tiktok-fill-queue-now, video-post, ig-reels-post
- belt+braces: guard ลงทั้ง **runbook (C:\Users\nL_ku\Claude\Scheduled\<id>\SKILL.md)** และ **registry prompt (C:\Users\nL_ku\.claude\scheduled-tasks\<id>\SKILL.md)** ของ 8 ตัว local ที่ prompt มี instruction inline
- diff ตัวอย่าง (evening-check): เดิม frontmatter -> เนื้อ prompt ("เตือนเช็คงาน Pantip/FB...") · ใหม่ = frontmatter -> **⛔ POSTING-POLICY block** -> เนื้อเดิมไม่แตะ

## A) AUDIT ตาราง (48 runbooks; enabled จาก local registry + list Cowork 15:00 · สูง=โพสต์เอง/แตะ Pantip · กลาง=ร่าง/แนะนำโพสต์ · ต่ำ=อ่านอย่างเดียว)
| taskId | enabled | ช่อง | โพสต์เอง? | เสี่ยง | guard |
|---|---|---|---|---|---|
| ngernduangold-social-ops-daily | ⏸ paused (Cowork 2 ก.ค.) | Pantip+Threads | ✅ เคยโพสต์ Pantip จริง | 🔴 สูงสุด | ✓ |
| daily-pantip-threads-engine | ❌ disabled (19 มิ.ย.) | Threads(+Pantip ref) | ✅ (เดิม) | 🔴 | ✓ |
| ngernduangold-queue-keeper | ❌ disabled | Postiz multi | ✅ (เดิม) | 🔴 | ✓ |
| ngernduangold-daily-cycle | ⏸ paused (26 มิ.ย.) | multi+Pantip | ✅ (เดิม) | 🔴 | ✓ |
| tiktok-weekly-content-engine | ❌ disabled | TikTok multi | ✅ (เดิม) | 🔴 | ✓ |
| tiktok-fill-queue-now / video-post / ig-reels-post | ⏸ paused | TikTok/IG | ✅ (เดิม) | 🔴 | ✓ |
| ngernduangold-evening-check | ✅ (18:07) | เตือนงาน Pantip/FB | ❌ แนะนำ | 🟠 กลาง | ✓ |
| ngernduangold-channel-heartbeat | ✅ (21:00) | cadence ทุกช่องรวม Pantip | ❌ ฟ้อง/แนะนำ | 🟠 | ✓ |
| ngernduangold-threads-refill-weekly | ✅ (อาทิตย์) | Threads เติมคิว | ⚠️ เติมคิว | 🔴 | ✓ |
| ngernduangold-pinterest-weekly | ✅ (อาทิตย์) | Pinterest | ⚠️ พิน | 🟠 | ✓ |
| pantip-daily-opportunity | ✅ | Pantip (ร่างอย่างเดียว) | ❌ ร่าง | 🟠 | ✓ |
| ngernduangold-pantip-monitor | ✅ (08:19) | Pantip ร่างตอบ | ❌ ร่าง | 🟠 | ✓ |
| ngernduangold-comment-loop | ✅ (12:52) | ทุกช่อง ร่างตอบ | ❌ ร่าง | 🟠 | ✓ |
| ngernduangold-delivery-verify | ✅ (21:16) | ทุกช่อง verify+fallback | ⚠️ fallback อาจชวนโพสต์ | 🟠 | ✓ |
| ngernduangold-first-signal | ✅ (12:24) | แนะ push ช่อง | ❌ แนะนำ | 🟠 | ✓ |
| ngernduangold-delivery-heartbeat | ✅ (08:29) | log ช่องที่ออก | ❌ | 🟡 ต่ำ | ✓ |
| ngernduangold-weekly-review | ✅ (จันทร์) | รีวิวรวม Pantip cadence | ❌ แนะนำ | 🟠 | ✓ |
| ig-weekly-pulse · video-post-verify · tiktok-daily-nudge | ✅ (Cowork) | IG/vid/TikTok | ❌/nudge | 🟠 | ✓ |
| 4channel-cadence · weekly-traffic-review · loop-architect · agent-auditor · daily-check · weekly-seo-money-review · weekly-growth-review-ngernduangold | สถานะไม่ชัด (Cowork sched) | วิเคราะห์/แนะนำ | ❌ | 🟠/🟡 | ✓ |
| link-health · clicktest · uptime-monitor · drive-backup · gsc-index · reindex · domain-buy | ✅/kept | อ่าน/ตรวจอย่างเดียว | ❌ | 🟢 | ไม่จำเป็น |
| นอกโปรเจกต์ (airbnb x3, apex, herald, feedflow, grab-shopee-lazada, flow-batch, full-optimize, validate-gemini, verify-full-scan, cowork-task-watchdog) | — | ไม่ใช่ช่องโซเชียล ngernduangold | ❌ | 🟢 | ไม่จำเป็น |

## C) ร่าง prompt ใหม่ social-ops-daily (ไร้ Pantip) — เสนอเท่านั้น ยังไม่เปิดใช้ ❌
```
ทำ social-ops รายวันของ "เงินเดือนสมองทอง" (เวอร์ชัน post-Pantip-freeze, 2026-07-02):
⛔ POSTING-POLICY: อ่าน automation-log/POSTING-POLICY_antispam_20260702.md ก่อน · Pantip FROZEN — ห้ามแตะทุกกรณี (ไม่ร่าง ไม่เช็ก ไม่แนะนำ)
งาน:
1) Threads 1 โพสต์/วัน: เลือกข้อความจากคิว automation-log/_social-stage/QUEUE_fb-threads_*.md ของวันนั้น (หรือแต่งใหม่ตามธีม sprint)
   -> ก่อนโพสต์: (ก) py pipeline\qa_gate.py --quota threads (exit!=0 = หยุด รายงาน)
                (ข) python -c "comply_gate.check_post(text, channel='threads')" ต้อง GATE_OK (เนื้อหา+text-dedup 30 วัน)
   -> โพสต์แบบ value-first ไม่มีลิงก์ (ลิงก์อยู่ไบโอ) -> บันทึก post_ledger.record_text_post('threads', text, source='social-ops-daily')
2) เฝ้า GA4 30 วิ: py pipeline\ga4_pull.py แล้วดู affiliate_click วันนี้ + หน้า top -> ถ้าเห็น spike/ดรอปผิดปกติ แจ้ง Telegram สั้นๆ
3) รายงานผลลง automation-log/cowork-inbox/social-ops-<date>.md: โพสต์อะไร/ข้าม (เหตุผล quota/dedup) + ตัวเลข GA4 3 บรรทัด
ห้าม: Pantip ทุกกรณี · เกิน 1 โพสต์ Threads/วัน · ลิงก์ขาย/ราคาในโพสต์ · bot-engagement
```
(ให้เจ้าของ/Cowork ตัดสินใจเปิด — ถ้าเปิด แนะนำเวลา 08:0x เดิม แต่เปลี่ยน taskId ใหม่ เช่น ngernduangold-threads-ops-daily เพื่อเก็บประวัติตัวเก่าไว้)

## D) หมายเหตุ
- SKILL.md ทั้งหมดอยู่นอก repo -> ไม่ commit (ตาราง audit + guard list + diff ตัวอย่างอยู่ในรายงานนี้แทน) · commit เฉพาะ order+report
- ไม่ได้เปิด/ปิด task ใด · ไม่แตะ logic อื่นของ prompt (เพิ่ม guard block อย่างเดียว)
- เสนอเพิ่ม (ไม่ทำเองรอสั่ง): task ที่ paused ซ้ำซ้อนหลายตัว (daily-cycle, video-post, queue-keeper, tiktok engine) น่า archive ออกจาก scheduler ไปเลยในรอบ governance ถัดไป ลด surface
