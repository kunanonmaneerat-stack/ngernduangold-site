# PLAYBOOK: เพิ่ม Traffic + Conversion ทุก Social Platform ผ่าน Hermes → Claude Code
รอบ Opus 4.8 · 21 มิ.ย. 2026 · (Gemini Flash3.5 ext + Qwen3.7+ รอบสด = เสริมเซสชันหน้า)

## บริบทที่ยึด (ไม่ re-derive)
pre-conversion (~3 sess/วัน, affiliate_click ~0) · /quiz funnel tuned แล้ว (925daab) · CC **STANDBY** จน quiz_start ≥30-50 · ลีเวอร์ตอนนี้ = **traffic intent สูง ไม่ใช่โค้ด** · FB Groups #1 · **comment→DM** · ลิงก์เฉพาะ DM/bio/description (กัน shadowban) · คปภ.-safe + ห้าม fabricate + rel=sponsored

## 🔑 หลักคิดใหม่เมื่อมี Hermes ในระบบ
Hermes เปลี่ยน Cowork จาก "ทำเองทุก step" → **"วาทยกรสั่ง executor"** · ขยาย throughput งานน่าเบื่อ (research/draft/monitor/สั่ง CC) **โดยไม่ scale คนโพสต์** (= กัน shadowban) · สูตร: **Hermes ทำงานเตรียม 80% → คน approve+โพสต์เอง 20%**

## ⚙️ เครื่องยนต์กลาง: "Daily Intent Engine" (Hermes รันทุกเช้า — 🟢 auto)
1. **research:** ขูดกระทู้/โพสต์ intent สูงวันนี้ (Pantip: หนี้/สินเชื่อ/ออม/ประกัน · Threads/FB search) → คัด top 6-8
2. **draft:** ร่าง value-first ต่ออัน (คปภ.-safe, **ไม่มีลิงก์**) → เข้าคิวรออนุมัติ
3. **monitor:** GA4 funnel (filter hostname≠127.0.0.1) + AccessTrade clicks → digest + บอก quiz_start สะสม "ใกล้ 30 ไหม"
4. Cowork review → approve → **คนโพสต์เอง** → comment→DM ลิงก์ /quiz

## 📱 ต่อ Platform (traffic → conversion bridge → Hermes role → CC task)

| Platform | Traffic play | Conversion bridge | Hermes (🟢 ร่าง/เฝ้า) | CC (เมื่อ trigger) |
|---|---|---|---|---|
| **Pantip** (intent สูงสุด, เร็วสุด) | ตอบ 3-5 กระทู้ value-first/วัน | ชวนต่อ DM/โปรไฟล์ → /quiz หรือชี้ /links | หากระทู้ + ร่างคำตอบ + เฝ้ากระทู้ใหม่ | บทความ long-tail จากคำถามที่ถามซ้ำ → ฟีดให้ตอบได้ลิงก์ /links |
| **Threads** | hook สั้น 1-2/วัน (เลขจริง ไม่ขายฝัน) + reply เธรดการเงินดัง | bio /links · "คอมเมนต์สนใจ"→DM | ร่าง hook + หาเธรด reply | — |
| **FB** (Groups #1 + Reels) | value 3-4 โพสต์/สัปดาห์ในกลุ่ม + ตอบคอมเมนต์ทุกวัน + Reels รียูส 1/วัน | "คอมเมนต์ 'สนใจ' เดี๋ยวส่งให้"→DM ลิงก์ (เว้น 1-2 นาที/เคส) | ร่างโพสต์กลุ่ม + คัดคอมเมนต์ที่ต้อง DM + เฝ้ากลุ่มใหม่ | — |
| **TikTok** (manual มือถือ) | 1-2 คลิป/วัน · hook 3 วิแรก · sound trending · ไม่มีลิงก์ในคลิป | bio /links + pinned comment → /quiz | ร่าง script/hook/caption + วิจัย sound | — |
| **IG** | cross-post Reels (TikTok/FB) + Stories poll/Q&A | bio /links · link sticker · DM | ร่าง caption + แผน cross-post | — |
| **YouTube** (Shorts) | รียูส Shorts + title เจาะคีย์เวิร์ด | description /links + pinned comment /quiz | ร่าง title/description SEO | — |

## 🎯 เร่ง Conversion (ข้ามทุก platform)
ทุก traffic → **/quiz ตัวเดียว** → atth → AccessTrade · วัด funnel · เมื่อ **quiz_start ≥30-50** → Hermes alert → Cowork สั่ง CC แก้จุด drop ใหญ่สุด**ทีละจุด** (ตาม handoff-CC-standby-data-triggered เดิม) · **ลิงก์เฉพาะ DM/bio/description** ห้ามในโพสต์/คลิปหลัก

## 🔗 Cowork → Hermes → Claude Code: command templates (พิมพ์สั่ง Hermes ในแอป/Telegram)

**[A] daily engine — 🟢 Hermes ทำเอง**
> "Hermes: รัน daily intent engine — (1) หากระทู้ Pantip + โพสต์ Threads/FB intent สูงวันนี้ หัวข้อ หนี้/สินเชื่อ/ออม/ประกัน คัด top 6 (2) ร่าง value-first answer ต่ออัน คปภ.-safe ไม่มีลิงก์ (3) GA4 digest (filter 127.0.0.1) + AccessTrade clicks + บอก quiz_start สะสม. ทุกอย่างเข้าคิวรอ approve **ห้ามโพสต์เอง**"

**[B] trigger CC อ่านอย่างเดียว — 🟡 Cowork approve การ trigger**
> "Hermes: ถ้า quiz_start ≥30 ใช้ skill claude-code สั่ง Claude Code (**read-only**): อ่าน GA4 funnel + ระบุ drop ใหญ่สุด 1 จุด + เสนอ fix 1 อย่าง (**อย่าแก้ไฟล์**) รายงานกลับ. ถ้ายังไม่ถึง 30 → standby + รายงานตัวเลข"

**[C] CC ลงมือแก้ — หลัง Cowork อนุมัติ fix นั้น**
> "Hermes: สั่ง Claude Code ทำ fix ที่อนุมัติ: <จุด> · เปลี่ยนชุดเดียว · ห้าม regress events/sub_id/hero≤2/interstitial/คปภ. · build + commit + push + รายงาน hash"

**[D] content assets — 🟢**
> "Hermes: ร่าง 5 hook TikTok + 5 caption Threads + 3 โพสต์กลุ่ม FB หัวข้อ <X> คปภ.-safe ลิงก์เฉพาะ DM/bio → คิว"

## 🚦 กฎเหล็ก (อยู่ใน Hermes duty แล้ว)
🟢 research/draft/monitor/schedule/**CC-readonly** = auto · 🟡 โพสต์จริง/CC commit-push/แก้ money page = **approve** · 🔴 เงิน/KYC/fabricate/self-click affiliate = **ห้าม**

## 🗓️ 2-week sprint
- **W1:** รัน engine [A] ทุกเช้า · Pantip 3-5/วัน + FB Groups + Threads · **สะสม quiz_start** (ยังไม่แตะโค้ด)
- **W2:** ถ้า quiz_start ≥30 → trigger [B]/[C] แก้ funnel จุดเดียว · **ตัด platform ที่ quiz_start=0** · จับ affiliate_click ตัวแรก

## ❓ คำถามให้ Gemini + Qwen รอบสด (เซสชันหน้า)
1. ลำดับ platform จัดถูกไหมสำหรับ solo+pre-conversion (Opus: Pantip+FB Groups นำ)?
2. Hermes ควรได้ autonomy เพิ่มตรงไหนก่อน หลัง conversion แรก?
3. จุด conversion ที่ Opus มองข้าม?

> บรรทัดเดียว: **Hermes = เครื่องยนต์ research+draft+monitor+สั่ง-CC ทุกเช้า · คนแค่ approve+โพสต์ · ทุก traffic → /quiz · แก้ funnel เมื่อ quiz_start ≥30 ผ่าน Hermes→CC · ลิงก์เฉพาะ DM/bio**
