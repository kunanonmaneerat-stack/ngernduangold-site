# แผนใช้งานเต็มประสิทธิภาพทุก surface ทุก platform (18 ก.ค. 2026)
เข็มทิศของ loop-architect และทุก agent — surface ไหน "เปิดแล้ว/คิวไหน/ใครทำ/ทำไมไม่ทำ" · อัปเดตเมื่อสถานะเปลี่ยน

## หลักการ
1. ทุก surface ใหม่ต้องมี: dup-check + ledger + เพดานความถี่ (anti-spam) ก่อนปล่อยเครื่องรัน
2. ลิงก์ = จุดที่คลิกได้จริงเท่านั้น (YT comment · Threads reply · IG story sticker · LINE) — ที่คลิกไม่ได้ใช้ CTA "ลิงก์หน้าโปรไฟล์"
3. เพดานรวมต่อช่องตาม POSTING-POLICY · เจอสัญญาณ throttle/เตือน = ลดทันที

## ตารางสถานะ (18 ก.ค. 2026)
| Platform | Surface | สถานะ | เครื่อง/ผู้ทำ |
|---|---|---|---|
| YouTube | Shorts รายวัน 19:00 | ✅ | ตั้งเวลา UI (batch3 คิวถึง 2 ส.ค.) |
| YouTube | คอมเมนต์ปักหมุด+ลิงก์ใต้ Short | ✅ เริ่มคืนนี้ | task yt-comment-link 21:25 |
| YouTube | long-form 1/สัปดาห์ | 🔜 สัปดาห์หน้า | Codex เขียนสคริปต์ → เจ้าของอัด/หรือ TTS |
| Instagram | Reels รายวัน 19:00 | ✅ | ตั้งเวลา Business Suite |
| Instagram | คอมเมนต์ CTA ใต้ Reel | ✅ | task ig-comment-cta อ./ศ./ส. 21:45 |
| Instagram | Stories + link sticker | 🔜 19 ก.ค. | Cowork (Business Suite composer) → ถ้าเวิร์กตั้งเป็น task 2-3/สัปดาห์ |
| Instagram | Carousel จากพิน 12 ใบ | 🔜 19-20 ก.ค. | Cowork โพสต์ชุดแรก · แคปชั่นจาก pinterest METADATA |
| Instagram | bio UTM | 🧍 เจ้าของ (มือถือเท่านั้น) | ลิงก์: ngernduangold.com/links?utm_source=ig&utm_medium=bio |
| Facebook | Reels รายวัน | ✅ | ตั้งเวลา Business Suite |
| Facebook | comment-link ใต้โพสต์ | ✅ | task 21:30 + guard 3 ชั้น |
| Facebook | แชร์ Reel เข้า Story | 🔜 19 ก.ค. พร้อม IG Story | Cowork (composer เดียวกันติ๊ก 2 ที่) |
| Facebook | Groups (borrowed reach) | ⏸ ตัดสิน 27 ก.ค. | ต้องมี guardrail ก่อน (คิวตามผลปรึกษา) |
| TikTok | คลิปรายวัน | ✅ (มือถือเจ้าของ + nudge 19:01) | batch3 ไฟล์พร้อมใน reels/ |
| TikTok | คอมเมนต์ปักหมุด CTA | ✅ เพิ่มใน nudge แล้ว | เจ้าของ 10 วิ/วัน หลังอัพ |
| TikTok | photo-mode จากพิน | 🔜 สัปดาห์หน้า | Codex ทำ kit → เจ้าของอัพมือถือ |
| TikTok | bio | ⛔ ปล่อยตามเดิม (ตัดสินใจถาวร 18 ก.ค. — <1k ลิงก์กดไม่ได้) | — |
| Threads | วิดีโอ 1/วัน 19:00 | ✅ | task threads-daily (file_upload) |
| Threads | reply-link ใต้โพสต์ตัวเอง | ✅ เพิ่มแล้ว เริ่มพรุ่งนี้ | ในตัว threads-daily ข้อ 8 |
| Threads | text post เสริม | 🔜 ประเมิน 22 ก.ค. | ถ้า video+reply รัน 3 วันไม่มีปัญหา ค่อยเพิ่ม (กัน over-post) |
| Pinterest | 3-4 พิน/สัปดาห์ | ✅ | task อาทิตย์ 11:00 |
| Pinterest | พินชี้ 4 หน้า SEO ใหม่ | ✅ เพิ่ม rotation แล้ว เริ่มพรุ่งนี้ | ในตัว pinterest-weekly |
| LINE OA | auto-reply "ขอจดหมาย" + UTM | ✅ | live |
| LINE OA | step message +24 ชม. | ✅ | live (ID 315613) |
| LINE OA | rich menu (เมนูลิงก์ถาวร) | 🔜 19 ก.ค. | Cowork (manager.line.biz ล็อกอินค้าง) |
| LINE OA | broadcast รายสัปดาห์ | 🔜 20 ก.ค. เริ่มชุดแรก | Codex ร่าง → เจ้าของเคาะ → Cowork ส่ง (ฟรี 300 ข้อความ/เดือน) |
| LINE OA | VOOM | ⛔ ยังไม่ทำ — reach ต่ำ ไม่คุ้มตอนนี้ | ทบทวน ส.ค. |
| Pantip | ตอบ ≤3/สัปดาห์ เฟส 1 + CTA หลังไมค์ | ✅ เต็มเพดานปลอดภัยแล้ว | 09:10 หา · เจ้าของเคาะ · Cowork โพสต์ |
| Pantip | ตั้งกระทู้เอง | ⏸ เฟส 2 หลัง 30 ก.ค. ถ้าสะอาด | — |
| เว็บ/SEO | บทความ + 4 comparison | ✅ | GSC index คิวพรุ่ง 10:00 |
| เว็บ/SEO | programmatic SEO ขยาย | 🔜 หลังเห็นผล 4 หน้าแรก (จันทร์ 27) | Codex batch |

## คิวเปิดใช้ (ลำดับ)
- **19 ก.ค. (พรุ่งนี้ บ่าย — เบราว์เซอร์ว่าง):** IG Story + link sticker + FB Story (ชิ้นแรกจากพิน winner) · LINE rich menu (ลิงก์ /links · /debt-letter-kit · "พิมพ์ ขอจดหมาย") · IG carousel ชุดแรก
- **20 ก.ค.:** LINE broadcast #1 (Codex ร่าง เจ้าของเคาะ) · Pantip ตอบครั้งที่ 2
- **21-25 ก.ค.:** YT long-form สคริปต์แรก (Codex) · TikTok photo-mode kit (Codex) · Threads text ประเมิน 22
- **27 ก.ค.:** FB Groups ตัดสิน + guardrail · ประเมินเต็มระบบ + แผน programmatic SEO
