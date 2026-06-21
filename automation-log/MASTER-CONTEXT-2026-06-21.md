# 📚 MASTER CONTEXT — ngernduangold (Cowork session 2026-06-21)

ละเอียดสำหรับ cross-check กับ Cowork session เก่า · มาร์ก: ✅ verify เองรอบนี้ (มีหลักฐาน) · 📒 จาก memory/ledger · ❓ ไม่รู้/สมมติ · ⏸️ ค้าง
เครื่องมือที่ใช้รอบนี้: Desktop Commander (คุมเครื่อง), Claude-in-Chrome (Browser 2), file tools, log_run.py · เวลาอ้างอิง ~2026-06-21T11:00–11:30+07:00

---

## 1) ธุรกิจ
- **ngernduangold-site** = เว็บ affiliate การเงินส่วนบุคคลไทย (แบรนด์ "เงินเดือนสมองทอง"/ngernduangold) ✅
- Static site: `build_site.py` → `./site` · deploy **Netlify** git-connected (ทุก push = build+publish) ✅
- โครงสร้าง: 23 บทความ + `/links` hub + `/quiz` (matcher) 📒
- รายได้ = **AccessTrade** ผ่านลิงก์ย่อ **atth.me** — บัตร (Krungsri), สินเชื่อ/รวมหนี้ (Srisawad/car4cash/happycash/refinance/ktcproud), ประกัน (เดินทาง MSIG+SCB = live; รถ/PA/CI = educational) ✅📒
- เจ้าของ = Non / **Kunanon Maneerat** (ยืนยันจากบัญชี AccessTrade) ✅ · ทำคนเดียว · pre-conversion

## 2) ศัพท์ → ของจริง (resolved ครบ)
| ศัพท์ | คือ | สถานะ |
|---|---|---|
| 3-model | Opus(ผม) + Gemini(`pipeline/free_ai.py`) + Qwen(`tiktok-pipeline/config.py`) | ✅ |
| CC | Claude Code (เครื่องเจ้าของ, เขียน ledger แถว cc-) | ✅ |
| **Hermes** | **Nous hermes-agent** ติดตั้งที่ `C:\Users\nL_ku\AppData\Local\hermes` (ดูข้อ 4) | ✅ |
| Daily Intent Engine | งานเช้า: research→draft→monitor→queue (Hermes รัน) | 📒 |
| playbook | `playbook-traffic-conversion-hermes-flow-2026-06-21.md` (เจ้าของเพิ่ม) | ✅ |
| memory notebook | `automation-log/latest.md` + `YYYY-MM.jsonl` ledger | ✅ |
| Cowork | = ผม (เซสชันนี้) | ✅ |

## 3) Repo: ngernduangold-site
- git: branch **main**, working tree สะอาด (มีแค่ไฟล์ .md ใหม่ที่ผมสร้าง) ✅
- last commits: `67cc21b` clicktest weekly · `986556d` runlog link-health · `512c915` GA opt-out localhost ✅
- ไดเรกทอรี: `build_site.py` (~299KB) · `pipeline/` (free_ai/qa_gate/script_gen/trend_ingest) · `tiktok-pipeline/` (src 00–07, captions, compliance, manifest, schedule) · `automation-log/` (ledger, POST-PROTOCOL, log_run, post_ledger, telegram_notify) · `tools/` (smoke/clicktest) · `site/`
- **clips .mp4 ไม่อยู่ใน repo** (อยู่ `TIKTOK_CLIPS_DIR` ของเจ้าของ) 📒

## 4) Hermes (AppData\Local\hermes) — ✅ verify
- ตัวจริง = **Nous hermes-agent** (มี `hermes-agent/` venv+node_modules+gateway+cron+kanban+skills+plugins)
- **Gateway launcher:** `gateway-service\Hermes_Gateway.cmd` → `hermes-agent\venv\Scripts\pythonw.exe -m hermes_cli.main gateway run` (detached, HERMES_HOME set)
- **สถานะรัน:** pythonw **PID 13280** ตั้งแต่ **2026-06-21 03:20:53** (+ python PID 20300) · `gateway.pid` = {"pid":13280}
- **log `logs\gateway.log`:** `✓ telegram connected` @ **03:21:12** · Telegram polling · 30 commands · รับ DM จาก user **"Nanon" (chat 8431211539)** ถึง ~09:51 · idle-evict 10:56 · 1 platform · channel directory 0 targets
- **Startup folder** (`...\Start Menu\Programs\Startup`): **`Hermes_Gateway.cmd`** (auto-start) + `GroqBot.bat` + OneNote.lnk + desktop.ini ✅
- config: `.env`, `config.yaml`, `auth.json`, `SOUL.md`, `memories\USER.md`, `kanban.db`, `cron\jobs`, `state.db`
- **Node MCP bundled:** gemini-mcp, firecrawl, binance-mcp, tradingview-mcp, context7, playwright-mcp, sequential-thinking, memory, fal-image-video-mcp, mcp-remote
- **Skills bundled:** creative/github/productivity(airtable,google-workspace,notion)/research/social-media(xurl)/software-dev/apple ฯลฯ
- ⚠️ หมายเหตุ: Hermes มี **gemini-mcp ของตัวเอง** แต่ "Gemini" ใน 3-model = `pipeline/free_ai.py` (คนละตัว ต้องใช้คีย์ Google AI Studio)

## 5) Env keys — ✅ verify (Desktop Commander)
| key | User scope |
|---|---|
| QWEN_API_KEY | **SET** |
| QWEN_MODEL | **SET** |
| GEMINI_API_KEY / GOOGLE_API_KEY / GOOGLE_AI_API_KEY / GOOGLE_GENAI_API_KEY / GENAI_API_KEY / GOOGLE_AI_STUDIO_KEY | **ไม่ตั้ง** |
| GA_API_SECRET / ACCESSTRADE_API_KEY | **ไม่ตั้ง** |
- ไฟล์ fallback `ga4-admin/.env` = **ไม่พบ** (เช็ก 3 path) · python ระบบ = **3.11.15** ✅
- ⚠️ process ที่ DC spawn ไม่ inherit User env อัตโนมัติ (ต้องดึง `[Environment]::GetEnvironmentVariable($k,'User')` เข้า process ก่อนรัน)

## 6) Pipelines + ผลรันสด — ✅ verify
- `pipeline/free_ai.py` (Gemini): key = `GOOGLE_AI_STUDIO_KEY` | `GEMINI_API_KEY` | `ga4-admin/.env` → **ทั้งหมดไม่มี** → คืน `(None, 'NO_KEY')` (skip ปลอดภัย ไม่ crash) · ใช้ได้แค่ gemini-*-flash ฟรี
- `tiktok-pipeline/config.py` (Qwen): `qwen_chat()` ผ่าน OpenRouter · default model `qwen/qwen3-next-80b-a3b-instruct:free`
- **ผลรันสด (คีย์ Qwen ใช้ได้ แต่รุ่นฟรี block):**
  - `qwen/qwen3-next-80b-a3b-instruct:free` → **404** (ไม่ฟรีแล้ว ดันให้ใช้ paid qwen-2.5-72b)
  - `qwen/qwen3-coder:free` → **404** (deprecated → ...-turbo)
  - `meta-llama/llama-3.3-70b-instruct:free` → **429** (rate-limited, ต้อง BYOK)
  - OpenRouter `/models` list ทั้ง 3 ว่าฟรี (pricing.prompt==0) แต่ตอน call ถูก block
- สรุป: **Qwen/Gemini รันสดไม่ได้รอบนี้** (คง $0 ไม่แตะ paid)

## 7) Metrics ปัจจุบัน
**✅ AccessTrade (publisher.accesstrade.in.th · Browser 2 · บัญชี Kunanon Maneerat)** — รายงานรายวัน 7 วัน (จำนวนคลิก):
| 15 | 16 | 17 | 18 | 19 | 20 | 21 | รวม |
|---|---|---|---|---|---|---|---|
| 30 | 4 | 2 | 34 | 27 | 2 | 0 | **99** |
- Impressions 0 · CTR 0% · **conversion 0 ทุกวัน** · revenue 0 · EPC 0
- Conversion tab: 0 (7วัน + เดือนนี้) · **Sub ID tab: ว่าง** (น่าจะ keyed ที่ conversion → conv 0 = ว่างปกติ; **ยังไม่พิสูจน์ว่า sub_id หลุด**)
- 📒 GA4 affiliate_click 33 lifetime (TH, 6 real users), today 2 (−92.6%) [จาก ledger 06-20]

## 8) Diagnosis (Opus)
1. คอขวด = **distribution/volume** ไม่ใช่ funnel/tracking · โพสต์ตายตั้งแต่ 06-19 (FB suspended)
2. **conversion 0 ที่ 99 คลิก = ปกติ** (loan/card อนุมัติยาก) · คลิก track ปกติ
3. **attribution ยังคลุมเครือ** — Sub ID ว่างอาจเพราะ conv 0 ไม่ใช่บั๊ก → ต้อง verify param ก่อนแก้
4. first-win ที่มองข้าม = **insurance-travel (MSIG/SCB live) + lifestyle card** (friction ต่ำกว่าสินเชื่อ)
5. ลำดับช่องทาง: **Pantip #1** · Threads #2 (แทน FB ที่ suspend) · FB Groups รอ unsuspend · TikTok/IG/YT เสริม

## 9) 3-model consult (รัน 21 มิ.ย.)
- **Opus (ผม) = ตอบจริง** 3 คำถาม playbook (อยู่ใน `consult-3model-2026-06-21-action.md`)
- **Gemini = NO_KEY · Qwen/Llama free = 404/429** → ปลดล็อก: ตั้ง `GOOGLE_AI_STUDIO_KEY` (Gemini) / free tier ฟื้นหรือ BYOK (Qwen) → ผมรันสดเติมมุมได้

## 10) Pantip (✅ verify วิธีที่เวิร์ก)
- **หน้า tag = เรียงใหม่สุด** ใช้ได้: `บัตรเครดิต` · `สินเชื่อส่วนบุคคล` · `การออมเงิน` · `ประกันภัยการเดินทาง`
- **tag 404 (slug ไม่มี):** สินเชื่อ, หนี้, รวมหนี้, ออมเงิน, ประกันเดินทาง, จำนำทะเบียนรถ, เงินฝาก, เงินเดือน
- search default = relevance (ได้กระทู้เก่า 2025) · JS sort "ใหม่→เก่า" **ไม่ทำงาน** · forum/sinthorn = ข่าว/หุ้นเยอะ ไม่ตรง intent
- เทคนิค: ID สูง = ใหม่ (ปัจจุบัน ~44.13M) · in-page `fetch('/tag/..')` + DOMParser ดึงได้เร็ว · `/topic/<id>` มี og:description = OP snippet
- **5 กระทู้สดที่เลือก** (ใน `pantip-engine-fresh-2026-06-21.md`): 44134668 (หนี้บัตร 240k/หมายศาล) · 44133405 (top-up บ้าน) · 44134803 (Seasy Cash เงินไม่เข้า) · 44134968 (เก็บเงิน 6 หลัก) · 44102201 (เลือกประกันเดินทาง)

## 11) build_site.py — attribution wiring (📒 จาก grep)
- GA `affiliate_click`: อ่าน `sub_id` จาก `utm_content`, `channel` จาก `utm_source`
- link builder: ต่อ `utm_source/utm_medium/utm_campaign/utm_content` ท้าย atth.me
- `LINKS_CHANNEL_JS`/`PICK_JS` rewrite utm ตาม channel ที่เข้ามา
- atth.me ตัวอย่าง: krungsri `00dayn002a0x` · srisawad `00c27p002a0x` · MSIG `000bqk002a0x` · SCB `00db8m002a0x`

## 12) ข้อจำกัด / ทำได้-ไม่ได้จาก Cowork
- ✅ ทำได้: คุมเครื่อง (Desktop Commander), Chrome (Browser 2), แก้ไฟล์ repo, รัน python, log_run
- ⛔ ไม่ได้: โพสต์แทน (บัญชี+สาธารณะ+approve) · ล็อกอิน/กรอกรหัสแทน · push/deploy จนได้ OK · เรียก Gemini/Qwen สด (ไม่มีคีย์/รุ่นฟรี block) · self-click affiliate (กัน pollute)

## 13) ⏸️ ค้าง (1 อย่าง)
**build_site sub-id patch** — verify ไม่จบ: Sub ID report ว่างคลุมเครือ + AccessTrade SPA ค้าง (find/get_page_text/หน้า campaign timeout) เปิดหน้าสร้างลิงก์ไม่ได้ · **HOLD patch** (กันแก้ของไม่พัง) · ปลดล็อก = ส่ง atth.me ลิงก์ที่ใส่ Sub ID มา 1 อัน หรือให้ retry dashboard

## 14) ไฟล์ที่สร้างเซสชันนี้ (automation-log/)
1. `consult-2026-06-21-3model.md` — Opus-leg consult + ช่องเสียบ Gemini/Qwen
2. `START-HERE-2026-06-21.md` — action sheet อิง playbook (Pantip-first + คำสั่ง Hermes [A] + คลังคำตอบ)
3. `pantip-engine-2026-06-21.md` — 3 กระทู้ตัวอย่าง + คำตอบ + วิธีหา
4. `UNDERSTANDING-2026-06-21.md` — snapshot ความเข้าใจครั้งแรก
5. `consult-3model-2026-06-21-action.md` — 3-model action sheet (Opus จริง + สถานะโมเดล)
6. `pantip-engine-fresh-2026-06-21.md` — 5 กระทู้สด + คำตอบเฉพาะเคส
7. `MASTER-CONTEXT-2026-06-21.md` — ไฟล์นี้
8. ledger `2026-06.jsonl` + `latest.md` — เพิ่ม 3 แถว (cc-qwen-setup=ok, cowork-hermes-verify, cowork-accesstrade-verify) ผ่าน log_run.py
9. (root, เจ้าของเพิ่ม) `playbook-traffic-conversion-hermes-flow-2026-06-21.md`

## 15) Timeline การกระทำเซสชันนี้ (สำหรับ cross-check)
1. mount โฟลเดอร์ (ลองหลาย path → `C:\Users\nL_ku\ngernduangold-site`) → โหลด memory/playbook
2. เขียน consult/START-HERE/pantip-engine/UNDERSTANDING
3. ขอสิทธิ์คุมเครื่อง → recon (git, env, Hermes, Chrome×2)
4. AccessTrade: เปิด dashboard Browser 2 → daily 99 คลิก/conv 0 / Sub ID ว่าง
5. Pantip: tag pages → 5 กระทู้สด + คำตอบ
6. Hermes: ยืนยัน gateway รัน + telegram connected + Startup
7. log_run.py อัปเดต latest.md (3 แถว)
8. รัน 3-model: Qwen 404 / Gemini NO_KEY / Llama 429 → ส่ง Opus action sheet
9. build_site sub-id: verify ไม่จบ (SPA ค้าง) → HOLD
