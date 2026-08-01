# RESULT — พรอมป์ตฝั่ง CC ค้างที่ 2 ก.ค. (order 1 ส.ค. 2026)

สถานะ: **งาน 1-4 เสร็จ** · preflight **0 fail** · test_preflight_checks **99 checks ALL PASS**

## 🔴 สิ่งที่พบก่อนอื่น: บล็อก ⛔ ที่ Cowork ใส่ไว้ ไม่มีผลกับ scheduler

มีไฟล์ SKILL.md **สองที่ และมันไม่ sync กัน**:
| path | บทบาท | ใครอ่าน |
|---|---|---|
| `~\.claude\scheduled-tasks\<task>\SKILL.md` | **prompt ที่ scheduler รันจริง** | agent ตอนรัน |
| `~\Claude\Scheduled\<task>\SKILL.md` | runbook/mirror | Cowork ตอนตรวจ · prompt อ้างถึงเป็น "runbook เต็ม" |

บล็อก `⛔ หยุด` เมื่อ 1 ส.ค. ถูกใส่ที่ **mirror** เท่านั้น ส่วนไฟล์ที่ agent อ่านจริงยังสั่ง *"เตรียม 5-8 กระทู้ · ปิดด้วย 1 ลิงก์บทความ · Pantip FROZEN ถึง 16 ก.ค. · ngernduangold.netlify.app"* ครบทุกบรรทัด
→ ทั้งสองที่ถูกแก้แล้วในรอบนี้ และตอนนี้ mirror ของ 6 งาน = สำเนาตรงของตัวจริง (ยกเว้น pantip ที่ mirror ตั้งใจให้เป็น runbook ยาว) · สำเนาเดิมเก็บเป็น `.bak-20260801`

## งาน 1 — `ngernduangold-pantip-monitor` ✅ เขียนใหม่ทั้งไฟล์ (ทั้งสองที่)

ลบข้อความเก่าที่ขัดกันออกหมด ไม่ใช่ทับซ้อนสองชั้น:
- ~~5-8 กระทู้/วัน~~ → **1 กระทู้ + สำรอง 1 ต่อรอบ**
- ~~แนบ 1 ลิงก์/คำตอบ~~ → **ห้ามลิงก์ทุกชนิด รวมบทความของเราเอง**
- ~~posting = pre-approved~~ → **ห้ามโพสต์เอง เจ้าของกดทีละโพสต์**
- ~~FROZEN ถึง 16 ก.ค.~~ / ~~netlify.app~~ → **ชี้ policy.json + ngernduangold.com**
- frontmatter description เดิมยังเขียนว่า *"[ปิด 20 มิ.ย. — รวบเข้า social-ops-daily]"* ทั้งที่งานรันทุกวัน → แก้ให้ตรงความจริง
- เพิ่ม: ส่งร่าง **เข้าแชตโดยตรง** (ไฟล์ .md เป็นสำเนาอ้างอิง ไม่ใช่ช่องทางส่งมอบ) · บันทึก ledger เฉพาะเมื่อโพสต์จริง · proof-of-run บังคับแม้รอบที่ไม่เจอกระทู้

## งาน 2 — อีก 5 ไฟล์ ✅ + เจอเพิ่ม 1 ไฟล์ที่ order ไม่ได้ลิสต์

ทุกไฟล์ขึ้นต้นด้วยคำสั่งอ่าน `policy.json` แทนการเขียนข้อเท็จจริงซ้ำ (ตามที่ order ย้ำ) และแทน Meta MCP/Postiz ด้วยเครื่องมือที่มีจริง ไม่ใช่แค่ลบคำ:

| ไฟล์ | เปลี่ยนกลไกเป็น |
|---|---|
| `delivery-verify` | `py tools\post_guard.py --json` — สถานะ OK/SOURCE-SIDE/FAILED/NOT-POSTED ที่แปลเป็นการกระทำได้ + ใช้ exit 2 ตัดสินว่าจะเตือน |
| `delivery-heartbeat` | guard ย้อน 1 วัน + อ่าน `post-guard/history.jsonl` หา **ช่องที่ล้มติดกัน ≥2 วัน** (บทบาทที่ต่างจาก verify จริง ๆ) |
| `comment-loop` | Chrome อ่านคอมเมนต์เอง · ตัด Meta MCP · ย้ำว่าไม่มี pre-approved |
| `first-signal` | ตัดบรรทัด FROZEN · เตือนไม่ให้ตีความ n=1 เป็นสัญญาณ |
| `queue-keeper` (ปิดอยู่) | **ลบคำสั่ง Postiz ทั้งหมด** เหลือ "งานนี้ปิดถาวร ถ้าถูกเรียกให้รายงานแล้วหยุด" + ชี้ว่าคิวจริงดูที่ manifest/preflight |
| `link-health` (order ว่าสะอาด) | **ไม่สะอาด** — ยังชี้ netlify.app → แก้เป็น ngernduangold.com + ให้รัน `check_affiliate_links.py` ก่อน |
| 🆕 `weekly-review` | **ไม่ได้อยู่ใน order แต่ enabled และรันจันทร์นี้** ยังสั่ง Postiz + Meta MCP → เขียนใหม่เป็น GSC-first ตามยุทธศาสตร์ patient SEO |

> เหตุผลที่แตะ `weekly-review` ทั้งที่นอก order: เป็นอาการเดียวกันเป๊ะ + จะรันใน 2 วัน การเว้นไว้คือทิ้งงานครึ่งเดียวทั้งที่รู้แล้ว

## 🧰 ปิดวงจร: เพิ่ม `check_dead_tooling` ใน preflight (คำตอบของ "ทำยังไงไม่ให้ค้างซ้ำอีก 4 สัปดาห์")

`check_prompt_drift` ที่มีอยู่ตรวจแค่ **วันที่**ที่ policy เป็นเจ้าของ — จึงขึ้น `PASS` มาตลอดขณะที่ 6 prompt สั่งเรียก Postiz/Meta MCP อยู่ (guard ที่ผ่านตลอดเพราะมองไม่เห็น — OPERATING-NOTES ข้อ 11)

เช็กใหม่: prompt ที่ยัง **สั่งให้ใช้** ของที่เลิกใช้แล้ว = drift · การ **เอ่ยชื่อเพื่อห้าม** ต้องผ่าน (บริบทเดียวกับบั๊ก `ไม่มีลิงก์พันธมิตร` เมื่อ 25 ก.ค.)
ขอบเขตความรับผิดชอบ: **FAIL** เฉพาะ task ที่ CC เป็นเจ้าของ (`.claude\scheduled-tasks`) · **WARN + รายชื่อ** สำหรับ prompt ฝั่ง Cowork ที่เราไม่มีสิทธิ์แก้ (ไม่ทำให้ gate แดงค้างจนคนเลิกสนใจ)
มี 8 เคสทดสอบ (สั่งใช้=FAIL · ห้ามใช้=PASS · ของคนอื่น=WARN) — suite รวม **99 checks ALL PASS**

**ผลรันจริง:** own prompts **สะอาดทั้งหมด (96 สแกน)** · พบ **13 prompt ฝั่ง Cowork** ยังเอ่ยของที่ตายแล้ว → รายชื่อขึ้นทุกวันใน preflight เช่น `ngernduangold-4channel-cadence` · `ngernduangold-90day-gate-debt-pivot` · `ngernduangold-agent-auditor` · `ngernduangold-gsc-index-insurance` · `ngernduangold-ig-reels-post` — **ฝากฝั่ง Cowork ตัดสิน**

## งาน 3 — Pantip ผลิตซ้ำสองที่: **CC ลดเป็น จ/พ/ศ แล้ว · เสนอให้ CC เป็นเจ้าของตัวเดียว**

- เปลี่ยน cron ของ `ngernduangold-pantip-monitor` เป็น `10 8 * * 1,3,5` แล้ว + แก้ description
- **เสนอ: ปิด `pantip-daily-opportunity` ฝั่ง Cowork แล้วให้ CC ถือตัวเดียว** เหตุผล: CC อยู่เครื่องเดียวกับ `policy.json` + `qa_gate.py` + `comply_gate` จึงบังคับกฎด้วย *เครื่องมือ* ได้จริง ไม่ใช่ด้วยดุลยพินิจ (ประเด็นที่ order ยกมาเอง) และเรียก `log_run` ได้ทุกรอบ
- **ผมปิด task ฝั่ง Cowork เองไม่ได้** — รอ Cowork เคาะ ถ้าเห็นต่างและอยากให้ Cowork ถือแทน ผมปิดฝั่ง CC ให้ทันที

## งาน 4 — proof-of-run: **เลือก "บังคับทุกงานเรียก log_run"** (ไม่เลิกใช้ runlog)

เหตุผล: runlog เป็นสะพานเดียวที่ Cowork/watchdog เห็นสถานะฝั่ง CC ผ่าน GitHub — เลิกใช้ = ตาบอดสนิท ส่วนอาการ "สัญญาณเตือนเท็จ" แก้ที่ความครอบคลุม ไม่ใช่ทิ้งเครื่องมือ
ทำแล้วฝั่ง CC: **ทั้ง 7 ไฟล์ที่แก้มีบล็อก proof-of-run บังคับ และระบุชัดว่า "รอบที่ไม่มีอะไรให้ทำก็ต้องบันทึก"** (เคสจริง 1 ส.ค.: รอบที่ไม่เจอกระทู้ไม่ได้บันทึก จึงดูเหมือนงานตาย)
3 งานที่ runlog ค้างในตาราง order (`pantip-daily-opportunity` · `fbgroup-listen` · `channel-heartbeat`) เป็น task ฝั่ง Cowork — ฝากเติมบล็อกเดียวกัน

## Gate + commit
- `py tools\preflight.py` → **0 fail / 3 warn** (warn = open decisions ใกล้ครบ + posting-cap ของเมื่อวาน + dead-tooling ฝั่ง Cowork)
- `py tools\test_preflight_checks.py` → **99 checks, 0 failed ALL PASS**
- frontmatter ทุกไฟล์อยู่บรรทัดแรก ตรวจแล้วครบ 10/10
- commit: preflight + test (ไฟล์ task อยู่นอก repo จึงไม่มีใน commit)
