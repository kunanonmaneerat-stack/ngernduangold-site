# 🎨 ART-LOOP — head of art → Google Stitch → Claude Code → monitor → Cowork

วงจรยกระดับความสวยงามเว็บ (เพิ่ม 2026-06-22) ต่อยอดจาก CC-bridge เดิม

```
[1] art_to_stitch.py        หัวหน้า Art & Graphic อ่านเว็บจริง
        │                    -> brief.md + stitch-prompt.txt + cc-routing.md
        ▼                       (automation-log/art-direction/<ts>/)
[2] Cowork (คน+Claude)       เอา stitch-prompt.txt ไปวางที่
        │                    https://stitch.withgoogle.com  -> เจนดีไซน์ใหม่
        ▼                    ดึงผล (HTML/CSS หรือภาพ) กลับ
[3] cc_bridge.send()         งานที่ "Claude Code ทำดีกว่า" (implement โค้ด)
        │                    -> automation-log/cc-inbox/order-<ts>.md
        ▼
[4] Claude Code (owner เปิด)  implement ดีไซน์เป็นโค้ดใน build_site.py
        │                    -> automation-log/cc-outbox/result-<ts>.md
        ▼                       (ห้าม commit/push/deploy เอง — ดู CC-PROTOCOL.md)
[5] cc_monitor.py            เฝ้าสถานะ (read-only) -> cowork-inbox/cc-status-<ts>.md
    cc_review.py /           รีวิวลึก -> cowork-review/  (อันนี้ consume ผล)
    report_to_cowork.py
        ▼
[6] Cowork                   วิเคราะห์ -> ตัดสิน -> สั่งรอบใหม่ / ให้ owner กด deploy
```

## ใครทำอะไร
| ขั้น | ไฟล์ | บทบาท | scope |
|---|---|---|---|
| หัวหน้าศิลป์ | `pipeline/art_to_stitch.py` | อ่านเว็บ → brief + Stitch prompt + routing | read-only เสนอ |
| (เดิม) art/graphic | `pipeline/art_agents.py` | เสนอปรับ HTML/CSS → CC | read-only เสนอ |
| ส่งงานให้ CC | `pipeline/cc_bridge.py` `send()` | เขียนออเดอร์ cc-inbox + ping | file handoff |
| CC execute | Claude Code (owner เปิด) | implement → cc-outbox | ❌ ไม่ commit/deploy |
| **monitor** | `pipeline/cc_monitor.py` | สถานะวงจร → Cowork (ไม่ย้ายไฟล์) | read-only |
| review ลึก | `pipeline/cc_review.py` / `report_to_cowork.py` | รีวิว+consume → cowork-review | ย้ายเข้า archive |
| ตัดสิน | Cowork | วิเคราะห์ → สั่งรอบใหม่ | คุม |
| deploy จริง | Owner | กด deploy | คนเท่านั้น |

## รัน
```
py pipeline/art_to_stitch.py     # ออก Stitch prompt + brief (ตอนอยากยกระดับดีไซน์)
# -> Cowork เอา stitch-prompt.txt ไปเจนที่ stitch.withgoogle.com
# -> ได้ผล -> cc_bridge.send(...) หรือเขียน cc-inbox/order-*.md
py pipeline/cc_monitor.py        # เช็กสถานะวงจร (อยู่ใน run_daily อัตโนมัติด้วย)
py pipeline/cc_review.py         # รีวิวลึกเมื่อ CC ทำเสร็จ
```

## กฎ (สืบทอดจาก CC-PROTOCOL.md)
- CC: ❌ ห้าม commit/push/deploy/โพสต์จริง · ✅ ร่าง+วิเคราะห์+เขียนผล cc-outbox
- งานแตะของจริง → "ธงต้องขออนุมัติ" ให้ Cowork/Owner ตัดสิน
- comply: ช่วงไม่การันตี · ไม่ระบุชื่อแบงก์/ผลิตภัณฑ์ใน hero · ธปท. Responsible Lending

## เพิ่ม: Stylist agent (ระหว่าง Stitch → Claude Code)
`pipeline/stylist.py` — เปิดดู preview → ตรวจ "ถูกต้อง+ถูกจริต" (brand tokens, ฟอนต์, มือถือ, AA, comply, ไม่มีชื่อแบงก์ใน hero, DM CTA) → ปรับ safe a11y/taste fix เขียน `*.styled.html` + `stylist-report` → `cc_bridge.send` ส่ง Claude Code (apply+fold เข้า build_site.py คง GA4/affiliate/SEO) → **`cc_monitor`/`cc_review` รายงานกลับ Cowork** (ตัวเดิม ไม่สร้างซ้ำ).

วงจรเต็มหลังเพิ่ม stylist:
```
art_to_stitch → Stitch (Cowork) → preview → stylist (ตรวจ+ปรับ+ถูกจริต) →
cc_bridge → Claude Code (fold โค้ดจริง) → cc_monitor + cc_review → Cowork → owner deploy
```
