# 🚀 Growth Playbook — Traffic + Conversion 6 แพลตฟอร์ม (ผ่าน Hermes → Claude Code)
รอบ Opus 4.8 · 21 มิ.ย. 2026 · Gemini-flash3.5 + Qwen3.7 = fan-out ผ่าน Hermes (Part D)

## สถานะโมเดล (ซื่อสัตย์)
- **Opus 4.8 (ผม):** ให้สดจริง = เนื้อหาทั้งหมดข้างล่าง
- **Gemini / Qwen:** Cowork เรียกสดไม่ได้ (Gemini ไม่มีคีย์ · Qwen free 404/429) → **ใช้ Hermes fan-out** (Part D) เพราะ Hermes มี gemini-mcp + OpenRouter → ได้มุม 2-3 จริง

## หลักคิดเดียว (ที่ stage นี้)
ยังไม่ใช่ "เพิ่ม conversion rate" (ยังไม่มีทราฟฟิกให้ optimize) — แต่คือ **ผลิตทราฟฟิก intent สูงเข้ากรวยเดียว (/quiz) ให้ได้ conversion แรกเพื่อเรียนรู้**.
**Hermes เปลี่ยนเศรษฐศาสตร์:** ทำงานน่าเบื่อ 80% (หา/ร่าง/เฝ้า/สั่ง CC) ได้ระดับ scale **โดยไม่ scale คนโพสต์** (= กัน shadowban). สูตร = **Hermes เตรียม 80% → คน approve+โพสต์ 20% → ทุกอย่างวิ่งเข้า /quiz ผ่าน DM/bio → CC ลับ funnel+attribution ให้คม**.

---

## 📱 ต่อแพลตฟอร์ม (Traffic → Conversion bridge → Hermes 🟢auto → คน → CC)

### 1. Pantip — #1 (intent สูงสุด เร็วสุด)
- **Traffic:** ตอบ 3-5 กระทู้สด/วัน (หนี้/รวมหนี้/สินเชื่อ/ออม/ประกัน) value-first · **+ ตั้งกระทู้เอง** (รีวิว [SR]/ไกด์เทียบ) ที่ติด Google ระยะยาว
- **Conversion bridge:** ห้ามลิงก์ในคำตอบ → /quiz ในโปรไฟล์ Pantip + "ทักมา/ดูโปรไฟล์" → DM
- **Hermes 🟢:** tag-scrape กระทู้สด (tag ที่ใช้ได้: บัตรเครดิต·สินเชื่อส่วนบุคคล·การออมเงิน·ประกันภัยการเดินทาง) → score intent+freshness+low-reply → ร่างคำตอบเฉพาะเคส (คปภ-safe ไม่มีลิงก์) → คิว · เฝ้า profile-click
- **คน:** approve+ตอบ 3-5/วัน · ตอบ follow-up · DM คนสนใจ
- **CC (เมื่อคำถามซ้ำ):** สร้างบทความ long-tail ตอบคำถามนั้น → Pantip ชี้ โปรไฟล์→บทความ→/links + บทความติด Google (ทบต้น)

### 2. Threads — #2 ตอนนี้ (FB suspended)
- **Traffic:** 2-3 hook/วัน (เลขจริง ไม่ขายฝัน) + reply เธรดการเงินดัง · text-only ไม่ต้องมีคลิป
- **Conversion:** bio /links + "คอมเมนต์ 'สนใจ'"→DM · hook→reply แรกใส่ /links
- **Hermes 🟢:** ร่าง hook จากคลัง 8 มุม + หาเธรดดังให้ reply + เฝ้า engagement
- **คน:** approve+โพสต์ · reply · DM
- **CC:** หมุน format hook + A/B ว่า hook ไหนดัน bio-click (เมื่อ GA มีข้อมูล)

### 3. FB — Groups #1 (ปกติ) · ตอนนี้ **suspended ตั้งแต่ 06-19**
- **ตอนนี้:** คนโพสต์มือในกลุ่มการเงิน (value ไม่มีลิงก์ · "คอมเมนต์สนใจ→DM") · **appeal ปลด suspend ก่อน re-automate** · Reels รียูสทีหลัง
- **Hermes 🟢:** ร่างโพสต์กลุ่ม + คัดกลุ่ม + ร่าง comment→DM (คิวเท่านั้น ห้าม auto-post ระหว่าง suspend)
- **CC:** —

### 4. TikTok — manual มือถือ
- **Blocker:** คลิป .mp4 ไม่อยู่ใน repo (โฟลเดอร์เจ้าของ) · Qwen key ตั้งแล้ว (แต่รุ่นฟรี 404 ตอนนี้ — รอ free ฟื้น/BYOK) · manifest 21 คลิปมีแล้ว
- **Traffic:** 1 คลิป/วันจากคลังเดิม · hook 3 วิแรก · sound trending · ไม่มีลิงก์ในคลิป
- **Conversion:** bio /links + pinned comment /quiz
- **Hermes 🟢:** ร่าง script/hook/caption + วิจัย sound (คิว)
- **คน:** render/อัปจากแอป · ตอบคอมเมนต์
- **CC:** — (CC = สคริปต์/manifest ไม่โพสต์)

### 5. IG — รียูส (effort ต่ำ)
- cross-post Reels (TikTok/FB) + Stories poll/Q&A → link sticker /links · **Hermes 🟢** ร่าง caption + แผน cross-post

### 6. YouTube Shorts — ทบต้น search
- รียูส Shorts + title เจาะคีย์เวิร์ด · description /links + pinned /quiz · **Hermes 🟢** ร่าง title/description SEO

---

## 🎯 เครื่องยนต์ Conversion (ข้ามแพลตฟอร์ม)
1. **กรวยเดียว /quiz** — ทุก bio/โปรไฟล์ชี้ที่นี่ · DM = ช่องลิงก์ (กัน shadowban)
2. **First-win re-route:** ดัน **insurance-travel (MSIG/SCB live) + lifestyle card** ให้ cold traffic (friction ต่ำกว่าสินเชื่อ) → ได้ conversion แรกเร็ว → เรียนรู้
3. **Attribution:** แก้ sub_id→AccessTrade (รอ verify param) ให้ conversion แรก attribute ได้รายช่อง
4. **วัด micro-conversion** (quiz_start/complete/recommendation_view/affiliate_click) เป็น proxy · **STANDBY โค้ดจน quiz_start ≥30**
5. **Kill criterion:** 2 สัปดาห์ ตัดแพลตฟอร์มที่ quiz_start=0

---

## 🔗 Part C — คำสั่ง Cowork → Hermes → Claude Code (ก๊อปวางใน Telegram/แอป Hermes)

**[1] DAILY ENGINE — 🟢 Hermes ทำเอง**
> Hermes: รัน daily growth engine — (1) Pantip: tag-scrape กระทู้สด (บัตรเครดิต/สินเชื่อส่วนบุคคล/การออมเงิน/ประกันภัยการเดินทาง) คัด top 6 intent สูง+ตอบน้อย+สดสุด → ร่างคำตอบเฉพาะเคส คปภ-safe ไม่มีลิงก์ (2) Threads: ร่าง 3 hook (เลขจริง) + 2 เธรดดังให้ reply (3) FB: ร่าง 1 โพสต์กลุ่ม (คิวเฉย ห้ามโพสต์ — บัญชี suspend) (4) digest: GA4 (filter 127.0.0.1) quiz_start/affiliate_click + AccessTrade clicks + quiz_start สะสม. **ทุกอย่างเข้าคิวรอ approve · ห้ามโพสต์เอง**

**[2] CONTENT ASSETS — 🟢**
> Hermes: ร่าง 5 hook TikTok + 5 caption Threads + 3 โพสต์กลุ่ม FB หัวข้อ <X> · คปภ-safe · ลิงก์เฉพาะ DM/bio · เข้าคิว

**[3] MONITOR + ALERT — 🟢**
> Hermes: ทุกเช้า รายงาน quiz_start สะสม + affiliate_click รายช่อง (sub_id) + clicks AccessTrade · ถ้า quiz_start ≥30 → แจ้งเตือน + เด้ง [4]

**[4] CC READ-ONLY (data-triggered) — 🟡 Cowork approve การ trigger**
> Hermes: ใช้ skill claude-code สั่ง Claude Code (**read-only**): อ่าน GA4 funnel → ระบุจุด drop ใหญ่สุด 1 จุด + เสนอ fix 1 อย่าง (**อย่าแก้ไฟล์**) รายงานกลับ

**[5] CC FIX (หลัง Cowork อนุมัติ fix) — 🟡**
> Hermes: สั่ง Claude Code ทำ fix ที่อนุมัติ: <จุด> · เปลี่ยนชุดเดียว · ห้าม regress events/sub_id/hero≤2/interstitial/คปภ · build + smoke + commit + push + รายงาน hash

**[6] CC ATTRIBUTION (งานค้าง) — 🟡**
> Hermes: สั่ง Claude Code: verify param sub-id ที่ AccessTrade รองรับ (จากหน้าสร้างลิงก์ หรือ atth.me ตัวอย่าง) → ถ้า `utm_content` ไม่ใช่ param ที่ถูก ให้ patch build_site.py ส่ง param ที่ถูก + build + smoke (ไม่ regress) → **ไม่ push จน owner OK** → รายงาน diff

**[7] PANTIP→ARTICLE COMPOUND — 🟡**
> Hermes: คำถาม Pantip ที่ถามซ้ำ ≥3 ครั้ง/สัปดาห์ → สั่ง Claude Code สร้างบทความ long-tail ตอบคำถามนั้น (มี /links CTA) + ใส่ internal link → build + push → รายงาน url

---

## 🤝 Part D — ให้ Hermes ดึงมุม Gemini + Qwen มา merge (ก๊อปวางใน Hermes)
> Hermes: ปรึกษา 2 โมเดลนี้ด้วยคำถามเดียวกัน แล้วสรุปเทียบกับมุม Opus (ไฟล์ consult-3model action):
> **คำถาม:** "เว็บ affiliate การเงิน pre-conversion (99 คลิก/7วัน, conv 0, โพสต์ตาย 06-19, ช่องทาง Pantip/Threads/FB/TikTok/IG/YT, ลิงก์ DM/bio, $0). วิธีเพิ่ม traffic+conversion ทุกแพลตฟอร์มแบบ Hermes ทำ 80% คนโพสต์ 20% — ขอ 3 ไอเดียที่ Opus อาจมองข้าม + จุดเสี่ยง shadowban ต่อแพลตฟอร์ม"
> (a) ผ่าน **gemini-mcp** (gemini-flash) (b) ผ่าน **OpenRouter Qwen** (ถ้า free 404 ลองรุ่นฟรีที่ available หรือใช้ key) → รายงานกลับเป็น bullet 3 มุม + ชี้ว่าต่างจาก Opus ตรงไหน

> ถ้าอยากให้ Opus (ผมในCowork) merge รอบสุดท้าย: เอาเอาต์พุต Gemini+Qwen ที่ Hermes ได้มาวางในแชต ผมรวมเป็น action sheet เดียวให้

---

## 🗓️ ลำดับลงมือ (2 สัปดาห์)
- **W1:** รัน [1] ทุกเช้า · Pantip 3-5/วัน + Threads 2-3/วัน (FB พัก) · ดัน insurance-travel/lifestyle card เป็น first-win · สะสม quiz_start · **ไม่แตะโค้ด** (ยกเว้น [6] attribution เมื่อ verify param ได้)
- **W2:** quiz_start ≥30 → [4]→[5] แก้ funnel จุดเดียว · ตัดแพลตฟอร์ม quiz_start=0 · จับ affiliate_click/conversion ตัวแรก · เริ่ม [7] บทความทบต้น

**บรรทัดเดียว:** Hermes ผลิต pipeline ทุกเช้า (หา+ร่าง+เฝ้า+สั่ง CC) · คน approve+โพสต์พอประมาณ · ทุกทาง→/quiz ผ่าน DM/bio · first-win = ประกันเดินทาง/บัตร lifestyle · แก้โค้ดเมื่อ data trigger ผ่าน Hermes→CC เท่านั้น
