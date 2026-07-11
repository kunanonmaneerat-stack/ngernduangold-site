# Loop-Architect — รอบ เสาร์ 11 ก.ค. 2026

สรุป: **loop ครบทุกหน้าที่ → ไม่สร้าง agent ใหม่รอบนี้** (guardrail กัน sprawl; roster อยู่ที่ 50+ tasks แล้ว)

## Loop coverage map (stage → agent/ระบบที่ดูแล)
| stage | ดูแลโดย | หลักฐานสด (11 ก.ค.) |
|---|---|---|
| ผลิตคอนเทนต์ | CC: content_council/content_creators/build_site + ngernduangold-fb-daily-draft | latest.md routines |
| กระจาย FB | fb-daily-draft · fb-evening-safetynet · fb-page-comment-link | on-plan |
| กระจาย IG | ig-reels-post · daily-social-post-reminder | delivery-heartbeat IG recovered 07-10 |
| กระจาย Threads | threads-ops-daily · threads-refill-weekly | posted 1/1 daily |
| กระจาย Pinterest | pinterest-weekly | last pin 07-07 on-plan |
| กระจาย TikTok | tiktok-daily-nudge · tiktok-vmok-window-watcher | manual-upload (no-bot policy) |
| กระจาย Pantip | pantip-daily-opportunity (draft-only) | FROZEN til 16 ก.ค. cadence=0 |
| SEO/indexing | pipeline striking-distance daily · sitemap-bump(CC) · GSC-index one-time | striking-distance_20260711.csv |
| conversion (CRO) | CC: conversion-cro/funnel-fix/quiz-tune + daily-check + ig-weekly-pulse | funnel live |
| measurement | weekly-review · ig-weekly-pulse · evening-check · daily-check · traffic_monitor | traffic-monitor-20260711-0737 |
| monetization | newswatch(affiliate campaigns) · weekly-review(AccessTrade reconcile) · 90day-gate | link-health 8/8 |
| demand research | striking-distance daily · pantip-daily-opportunity · newswatch content-ops | striking-distance_20260711.csv |
| site health | pipeline/link_check.py (linkcheck daily) · uptime-monitor 6h · check_affiliate_links.py | linkcheck-2026-07-11.md |

## เสนอเจ้าของ (ไม่สร้างเอง — เป็น owner-decision/CC-patch ไม่ใช่ agent-gap)
1. **sub_id ยังไม่ถึง AccessTrade** (cowork-accesstrade-verify, มิ.ย.) — ต้องยืนยันว่า patch แล้วหรือยัง; ถ้ายัง = รายได้ที่เข้าจะ attribute ไม่ได้. งาน CC-code ไม่ใช่ agent.
2. **IG reel queue หมดบ่อย** (delivery-verify 6-day fail 07-04..07-09, กู้แล้ว 07-10) — owner เติมคลิป IG ล่วงหน้า; ปัจจุบัน channel/delivery-heartbeat จับได้อยู่แล้ว ไม่ต้องมี agent ใหม่.
3. **Pantip thaw 16 ก.ค.** (อีก 5 วัน) — PANTIP-LAUNCH-QUEUE_16JUL_starter.md + pantip-daily-opportunity เตรียมไว้แล้ว; re-entry ต้องมือเจ้าของ 100% ตาม policy (ไร้แบรนด์/ลิงก์ 3-5 โพสต์แรก).
4. (ทางเลือก) striking-distance → CC optimization order รายสัปดาห์: ตอนนี้มี CSV รายวันแต่ไม่มี agent แปลงเป็น order เจาะจง. borderline ซ้ำกับ weekly-review focus-pick → เสนอไว้ ยังไม่สร้างกัน sprawl.

## Guardrail ที่ยึด
ไม่มี gap ที่ (ชัด+คุ้ม+ฟรี+comply-safe+ไม่ซ้ำ) → ไม่สร้าง. การไม่สร้าง > สร้างของซ้ำ. Pantip ห้ามแตะ (frozen).
