# 🧩 ชั้นใหม่: Content-Creator Agents + Head + Push Agent (2026-06-21)

ต่อยอด pipeline เดิม — เพิ่ม "ชั้นผลิตคอนเทนต์พร้อมโพสต์" + หัวหน้าทีม + เอเจนต์ดีพลอย
(ทุกตัวผลิตดราฟต์→ไฟล์ · ไม่โพสต์/ไม่ deploy เองเงียบ ๆ · ผ่าน comply_gate)

## โมดูล
| ไฟล์ | บทบาท |
|---|---|
| `pipeline/content_creators.py` | 6 ครีเอเตอร์รายแพลตฟอร์ม: **fb · ig · tiktok · threads · pantip · yt** — เอาต์พุต "พร้อมโพสต์จริง" ฟอร์แมตเนทีฟ + ฝัง learning จริง (comment-CTA "เช็กสิทธิ์", ฮุกไม่ซ้ำ, แฮชแท็ก) |
| `pipeline/head_content.py` | หัวหน้าทีม — สั่งครบ 6 ช่องต่อ 1 หัวข้อ → รวมเป็นแพ็กเกจ → ส่งให้ Cowork คุมต่อ (เขียน `content-packages/` + `cowork-inbox/`) เรียง Pantip,IG ก่อน (ROI reach สูงสุด) |
| `pipeline/push_agent.py` | เอเจนต์เตรียม-ดีพลอย: **truncation guard** (กันบั๊กไฟล์ถูกตัด) → build → verify (33 หน้า/affiliate/quiz ครบ) → git add+commit → **ด่านอนุมัติก่อน push** |

## วิธีใช้ (รันบนเครื่อง owner — free_llm ใช้คีย์จาก registry)
```
py pipeline/head_content.py "หนี้บัตรหลายใบ จ่ายขั้นต่ำไม่ลด อยากรวมหนี้"
   → ได้ content-packages/<ts>-...md (6 ช่อง พร้อมโพสต์) + cowork-inbox/content-<ts>.md
py pipeline/content_creators.py ig "บัตรใบแรก เงินเดือน 15000"   # ทีละช่อง
py pipeline/push_agent.py            # เตรียม deploy + กันพลาด แล้วหยุดก่อน push
set PUSH_APPROVED=1 && py pipeline/push_agent.py --push   # อนุมัติขึ้นเว็บจริง
```

## flow ใหม่ (เชื่อมของเดิม)
หัวข้อ (orders/metrics-feedback) → **head_content → 6 content_creators** → แพ็กเกจ → **cowork-inbox**
→ **Cowork คุม**: เลือกคิวตาม reach · ช่องตั้งเวลาได้ฟรี (IG/FB/TikTok/YT) คุมตั้งเวลา · Pantip ส่ง owner วาง
→ โพสต์ → comment "เช็กสิทธิ์" → auto-DM → /quiz → affiliate → metrics_loop วัด → ป้อนหัวข้อรอบใหม่

## หมายเหตุความปลอดภัย (push_agent)
- **ไม่ push อัตโนมัติเงียบ ๆ** — push = ขึ้นเว็บสาธารณะ (กลับยาก) ต้องมีคนยืนยันรอบสุดท้าย
  โดยเฉพาะหลังเจอบั๊ก build_site.py ถูกตัดท้าย 2 ครั้ง — guard นี้จะ "หยุดก่อน deploy" ถ้าไฟล์ไม่ครบ
- ต้องการให้ push เอง: ใส่ `--push` + `PUSH_APPROVED=1` (เจตนาชัดเจน) = ปลอดภัยกว่า auto-deploy
