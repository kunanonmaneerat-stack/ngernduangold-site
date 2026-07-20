# นำ "Fleet Engineering" มาปรับใช้กับระบบเงินเดือนสมองทอง (20 ก.ค. 2026)

ที่มา: วิดีโอ AI LABS "Fleet Engineering Is Insane... The Next Evolution Of Vibe Coding" (เจ้าของชี้ t=591s)
หมายเหตุ: ดึง transcript ไม่ได้ (วิดีโอปิด caption fetch) — วิเคราะห์จากแนวคิด Fleet Engineering + จับคู่กับจุดเจ็บจริงของเรา · ถ้าเทคนิคช่วง 9:51 ต่างจากนี้เจ้าของแก้ได้

## แนวคิดหลัก (จากที่เข้าใจ)
Vibe coding เดิม = agent 1 ตัว ทำทีละงานเรียงกัน (sequential)
Fleet Engineering = **agent หลายตัวทำพร้อมกัน (parallel)** โดยแต่ละตัวอยู่ใน **workspace แยก (git worktree)** ไม่ชนกัน มี orchestrator สั่งงาน+รวมผล แล้วมี gate ตรวจ/เลือกผลดีสุด
3 เสาหลัก: **ขนาน (parallelism) · แยกตัว (isolation) · ควบคุม+รวมผล (orchestration/merge)**

## จับคู่กับระบบเราตอนนี้
| เสา Fleet | เรามีแล้ว? | ช่องว่าง |
|---|---|---|
| Orchestration | ✅ Cowork = สมอง + 15 scheduled tasks | มีอยู่ดี |
| Isolation | ❌ ทุกอย่างเขียน working tree เดียว | **คืนนี้ชน `.git/index.lock` ซ้ำ ๆ = อาการของ isolation ที่หายไป** |
| Parallelism | ❌ Codex รันทีละ spec เรียงกัน | ผลิตช้า — คอขวดจริงคือ "ผลิตทีละอย่าง" |

**ข้อค้นพบสำคัญ:** จุดเจ็บที่เราชนบ่อยสุด (git lock ตอนรันหลายอย่าง + ผลิตคอนเทนต์ทีละชุด) คือสิ่งที่ Fleet Engineering แก้โดยตรง — ไม่ใช่ของเล่นใหม่ แต่แก้ปัญหาที่มีอยู่

## สิ่งที่ปรับใช้ได้จริง (เรียงตามผลกระทบ)

### 1. 🔴 Worktree isolation — แก้ git lock ถาวร (ทำได้ทันที ความเสี่ยงต่ำ)
เครื่องมือ Agent ของ Cowork มี `isolation:"worktree"` ในตัว = แต่ละ agent ได้ worktree ของตัวเอง
→ รัน Codex/agent หลายตัวพร้อมกันโดยไม่ชน index.lock · แต่ละตัว commit ใน worktree ตัวเอง · Cowork merge ทีหลัง
→ **แก้อาการ `.git/index.lock: File exists` ที่เราต้องลบมือทุกครั้งคืนนี้**

### 2. 🟠 Parallel content production — ผลิตขนาน (pilot ได้เลย)
แทนที่ Codex รันทีละ spec (23→24→25...) ให้ Cowork spawn fleet ทำพร้อมกัน เช่นคืนเดียว:
- agent A: คลัง knowledge-post ชุดถัดไป (kn-15..28)
- agent B: คลัง page2 ชุดถัดไป (p2-09..16)
- agent C: สคริปต์ YT long-form
แต่ละตัว worktree แยก → Cowork QA + merge ทีเดียว · จาก 3 คืน เหลือ 1 คืน

### 3. 🟡 Fleet dashboard — เห็นสถานะทุก agent ที่เดียว (เสริม)
ตอนนี้สถานะกระจายในไฟล์ inbox หลายอัน · ทำ 1 หน้า (artifact) รวมสถานะทุก scheduled task + fleet run = orchestrator view

## ⚠️ ข้อควรระวัง (ไม่เอามาทั้งดุ้น)
- เพดานความปลอดภัยของ**การโพสต์**ยังเหมือนเดิม — Fleet เร่งการ**ผลิต/เขียนโค้ด** ไม่ใช่เร่งการยิงโพสต์ (โพสต์รัว= สแปม เจ็บ)
- คุณภาพต้องมี gate: agent ขนานผลิตเยอะ = ต้อง QA เข้มขึ้น ไม่ใช่ปล่อยผ่าน
- zero-budget คงเดิม · ไม่เพิ่ม token/credential

## คำแนะนำ (1 อย่าง)
เริ่มที่ **ข้อ 1+2 รวมกันเป็น pilot เดียว**: คืนนี้ให้ผม spawn fleet 2-3 agent แบบ worktree-isolated ผลิตคลังคอนเทนต์ชุดถัดไปพร้อมกัน (knowledge + page2) แล้ว QA+merge — ได้ทั้งพิสูจน์ว่า worktree แก้ git lock ได้จริง และเติมคลังล่วงหน้าไปในตัว
