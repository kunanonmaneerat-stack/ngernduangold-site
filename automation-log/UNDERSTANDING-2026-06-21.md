# 🧠 สิ่งที่ Claude เข้าใจทั้งหมด — ngernduangold (snapshot 21 มิ.ย. 2026)

มาร์ก: ✅ = ยืนยันเองรอบนี้ (มีหลักฐาน) · 📒 = จาก memory/ledger (ยังไม่ verify ซ้ำ) · ❓ = ยังไม่รู้/สมมติ

---

## 1) ธุรกิจคืออะไร
- **ngernduangold-site** = เว็บ affiliate การเงินส่วนบุคคลภาษาไทย (แบรนด์ "เงินเดือนสมองทอง"/ngernduangold) ✅
- Static site สร้างด้วย `build_site.py` → `./site` · deploy **Netlify** (git-connected, ทุก push = auto build+publish) ✅
- โครงสร้าง: 23 บทความ + hub `/links` + `/quiz` (ตัวจับคู่ offer) 📒
- รายได้ = affiliate **AccessTrade** ผ่านลิงก์ย่อ **atth.me**: บัตรเครดิต (Krungsri), สินเชื่อ/รวมหนี้ (Srisawad, car4cash, happycash, refinance, ktcproud), ประกัน (เดินทาง MSIG/SCB = live · รถ/PA/โรคร้าย = educational เปล่า) ✅📒
- เจ้าของ = Non / Kunanon Maneerat · ทำคนเดียว · ระยะ **pre-conversion** ✅

## 2) ศัพท์ → ของจริง (กุญแจไขความสับสนตอนเริ่ม)
| ศัพท์ | คือ |
|---|---|
| **3-model consult** | Opus (Claude/ผม) + **Gemini** (`pipeline/free_ai.py`, Google AI Studio flash ฟรี) + **Qwen** (`tiktok-pipeline`, OpenRouter ฟรี) — รันเป็น Python ใต้ env key บนเครื่องเจ้าของ ไม่ใช่ MCP ที่ผมเรียกจาก Cowork ✅ |
| **CC** | **Claude Code** — โค้ดดิ้งเอเจนต์บนเครื่องเจ้าของ รัน routine + เขียน ledger (แถว `cc-…`) ✅ |
| **Hermes** | วาทยกร/executor ที่ควรรัน engine ทุกเช้า + สั่ง CC · สั่งผ่าน "แอป/Telegram" · **หาบนเครื่องไม่เจอ** (ไม่มี process/scheduled task) → ยังไม่รัน หรืออยู่นอกเครื่อง ✅❓ |
| **Daily Intent Engine** | งานเช้า: research กระทู้ intent สูง → ร่างคำตอบ value-first → monitor GA4/AccessTrade → เข้าคิวรอ approve 📒 |
| **playbook traffic-conversion** | ไฟล์ `playbook-traffic-conversion-hermes-flow-2026-06-21.md` (รอบ Opus 4.8) ✅ |
| **memory notebook / สมุดโน้ต** | `automation-log/latest.md` + jsonl ledger ✅ |
| **Cowork** | = ผม (เซสชันนี้) ทำ step approve/เตรียมโพสต์/MCP ในแพตเทิร์น handoff ✅ |

## 3) สถาปัตยกรรมระบบ
- `build_site.py` (โมโนลิธ ~299KB) · `pipeline/` (Gemini cost-guard `free_ai` + trend/script/qa) · `tiktok-pipeline/` (Qwen: `00_registry`→`07_render`, captions, compliance, manifest, schedule) · `automation-log/` (ledger, POST-PROTOCOL, post_ledger, telegram_notify) · `tools/` (smoke/clicktest) ✅
- **Dedup protocol** (POST-PROTOCOL.md): ตัดสินก่อนโพสต์เสมอ (Postiz ลบ scheduled ไม่ได้), twin ±16 วัน, fail-closed บน cron ✅
- **กฎเหล็ก compliance**: $0 · ห้าม fabricate ตัวเลข · คปภ. disclosure · ห้ามลิงก์ในคลิป/แคปชัน (bio เท่านั้น) · rel=sponsored 📒
- **ช่องทาง**: Pantip (#1 intent) · FB Groups (#1) · Threads · TikTok (มือ) · IG · YouTube Shorts ✅📒
- **Funnel**: ทุก traffic → `/quiz` → atth → AccessTrade · GA4 `affiliate_click` อ่าน sub_id จาก `utm_content`, channel จาก `utm_source` · หน้า /links + /quiz มี JS rewrite utm เป็น channel ✅

## 4) สถานะปัจจุบัน — ✅ ยืนยันรอบนี้ (หลักฐาน)
- **AccessTrade** (publisher.accesstrade.in.th, ล็อกอิน Kunanon): คลิก **99/7วัน** (15:30·16:4·17:2·18:34·19:27·20:2·21:0) · **conversion 0 · รายได้ 0** · **แท็บ Sub ID = ว่างเปล่า** ✅
- **env keys (เครื่องจริง)**: `QWEN_API_KEY`+`QWEN_MODEL` = **SET** (User scope) · Gemini/Google/GA/AccessTrade = **ไม่ตั้ง** · python 3.11.15 ✅
- **git**: branch `main`, สะอาด (มีแค่ไฟล์ md ใหม่ของผม) ✅
- **Hermes**: ไม่มี process/scheduled task · Chrome ต่อ 2 ตัว (ใช้ Browser 2) ✅
- affiliate links 8/8 OK (atth.me 200) ✅📒

## 5) สถานะ — 📒 จาก memory (ยังไม่ verify ซ้ำ)
- GA4 affiliate_click **33 lifetime** (TH, 6 real users) · today 2 (−92.6%) [06-20]
- CRO/funnel ทำครบ · quiz tuned (2Q, hero above-fold, events start/complete/recommendation_view) · **data-hygiene STANDBY จน quiz_start ≥30–50**
- bot-posting **suspended ตั้งแต่ 06-19** (FB) · FB/IG/YT last-live 06-19 · Threads/TikTok login-wall
- 21 คลิป/แคปชัน compliance-pass ใน production-manifest · ตารางโพสต์ 06-27→07-10 · **ไฟล์ mp4 ไม่อยู่ใน repo** (อยู่ TIKTOK_CLIPS_DIR ของเจ้าของ)
- Threads 8-hook drafts พร้อม (06-19) · Pantip answer pack เตรียมไว้

## 6) วินิจฉัย (Opus synthesis)
1. **คอขวด = distribution/volume ไม่ใช่ funnel/tracking** · โพสต์ตายตั้งแต่ 06-19
2. **conversion 0 ที่ ~33–99 คลิก = noise ปกติ** ของ affiliate สาย loan/card (อนุมัติยาก) — คลิก track ปกติ ไม่ใช่บั๊ก
3. **ช่องโหว่จริง = sub_id ไม่ถึง AccessTrade** (`utm_content` ≠ พารามิเตอร์ sub-id ที่ AccessTrade รู้จัก) → attribution บอด · แก้ได้ แต่ไม่เร่ง ต้องใช้ param ที่ถูก
4. **ลำดับ**: กู้ distribution (Pantip+FB Groups+Threads มือ) → สะสม quiz_start → ที่ ≥30 ค่อยให้ CC แก้จุด drop ใหญ่สุดทีละจุด · ลิงก์เฉพาะ DM/bio

## 7) ข้อจำกัด (ผมทำอะไรไม่ได้จาก Cowork)
- เรียก Gemini/Qwen สด, trigger Hermes/CC = ไม่ได้ (เครื่อง/คีย์เจ้าของ)
- โพสต์แทน = ไม่ได้ (บัญชีเจ้าของ + สาธารณะ + ต้อง approve) · ล็อกอิน AccessTrade แทน = ไม่ได้ (อ่านอย่างเดียว)
- push/deploy ขึ้นเว็บจริง = ไม่ทำจนได้ OK
- **ทำได้**: คุมเครื่องผ่าน Desktop Commander + Chrome (ได้รับสิทธิ์แล้ว), แก้ไฟล์ใน repo, build test

## 8) ของที่ต้องตามต่อ / รอตัดสินใจ
- 🔧 **แก้ sub_id tracking** ใน build_site.py (verify param AccessTrade ก่อน → patch → test → ไม่ push จน OK)
- ⚙️ **Qwen รันได้แล้ว** (คีย์ตั้งแล้ว) — ตรงข้ามกับ ledger ที่ยังขึ้น "cc-qwen-setup pending PART A" → **memory ต้องอัปเดต**
- 📮 **โพสต์ = เจ้าของ** (ผมเตรียมก๊อปวางหมดแล้ว)

## 9) ไฟล์ที่ผมสร้างเซสชันนี้ (ใน automation-log/)
- `consult-2026-06-21-3model.md` — Opus-leg consult + ช่องเสียบ Gemini/Qwen
- `START-HERE-2026-06-21.md` — action sheet อิง playbook (Pantip-first, คลังคำตอบ, คำสั่ง Hermes [A], จังหวะ 2 สัปดาห์)
- `pantip-engine-2026-06-21.md` — กระทู้จริง 3 + คำตอบเฉพาะเคส + วิธีหากระทู้สด
- (เจ้าของเพิ่ม) `playbook-traffic-conversion-hermes-flow-2026-06-21.md`

---
**บรรทัดเดียว:** เว็บ/funnel พร้อมแล้ว · ปัญหาคือไม่มีคนเข้า (โพสต์ตายตั้งแต่ 19 มิ.ย.) ไม่ใช่โค้ดพัง · คลิกเข้า AccessTrade ปกติ conversion 0 เพราะ volume · งานเดียวที่สำคัญ = กลับมาโพสต์ Pantip/FB/Threads มือ ลิงก์ใน DM/bio · แก้โค้ดเฉพาะ sub_id (ไม่เร่ง) เมื่อ verify param เสร็จ
