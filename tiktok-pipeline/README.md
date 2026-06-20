# 🎬 TikTok Content Pipeline (Gemini × Qwen 3.7)

Pipeline **ข้อความ/ออร์เคสเทรชัน** สำหรับ @ngernduangold: pain จริง → Qwen (research → script → compliance audit) → **สคริปต์ผ่าน compliance + production manifest** ให้ Cowork เอาไป generate วิดีโอ → เจ้าของอัปมือจากแอป TikTok.

> **ขอบเขต CC (นี่):** ออกสคริปต์ผ่าน compliance + manifest เท่านั้น · **ไม่** generate วิดีโอ (Cowork ทำผ่าน MCP) · **ไม่** โพสต์ (เจ้าของอัปมือ) · **ไม่** automate การโพสต์.

## กฎเหล็ก (บังคับในทุกสคริปต์)
$0 · ห้าม fabricate ตัวเลข/เบี้ย/ดอก/รีวิว (เลขทุกตัวอ้างอิงบทความ/แหล่งจริง) · คปภ. ไม่การันตีผล + มี disclosure · ไม่สวมรอยคนจริง (TTS/AI OK) · **ห้ามใส่ลิงก์ในคลิป/แคปชัน → bio เท่านั้น** · ไม่ automate posting.

## วิธีรัน end-to-end

### A) มี Qwen key (คุณภาพเต็ม)
```powershell
$env:QWEN_API_KEY="sk-..."          # ขอฟรีที่ openrouter.ai/keys หรือ dashscope
$env:QWEN_BASE_URL="https://openrouter.ai/api/v1"
$env:QWEN_MODEL="qwen/qwen-2.5-72b-instruct"
python src/01_research.py ; python src/02_script.py ; python src/03_compliance.py ; python src/04_manifest.py
```
(ใช้ `;` ไม่ใช่ `&&` — PowerShell)

### B) ไม่มี key — ทดสอบโครงสร้าง (deterministic fallback, ไม่ใช้ LLM)
```powershell
python src/01_research.py --dry-run ; python src/02_script.py --dry-run ; python src/03_compliance.py --dry-run ; python src/04_manifest.py --dry-run
```
ถ้ารัน `01`/`02` โดยไม่มี key และไม่ใส่ `--dry-run` → พิมพ์วิธีขอ key แล้ว exit อย่างสุภาพ (ไม่ crash). `03` (regex compliance) + `04` (assembly) รันได้เสมอ.

## ไฟล์ที่ออก
- `drafts/topics.json` (01) · `drafts/scripts.json` (02) · `drafts/scripts_clean.json` + `drafts/compliance_report.md` (03)
- `ready-for-cowork/production-manifest.json` + `UPLOAD-CHECKLIST.md` (04) ← **Cowork/เจ้าของอ่าน 2 ไฟล์นี้**

## Compliance gate (03)
2 ชั้น: (ก) **regex** จับคำต้องห้าม (`compliance_rules.json`) + แทนคำ + เช็ก URL ใน onscreen/tts (hard-fail) · (ข) **Qwen rewrite** เฉพาะคลิปที่ flag (ถ้ามี key). ทุกคลิปได้ `compliance_pass` + `flags[]` + `number_warnings[]` (ตัวเลขที่ต้องเช็กแหล่งโดยคน — soft, ไม่ fail). **เฉพาะ `compliance_pass:true` เท่านั้นเข้า manifest.**

## ปรับแต่ง
- `input/pain_seed.json` — seed pain (รองรับ `--source` plugin ภายหลัง เช่น Bright Data/exa)
- `article_map.json` — topic → slug จริง + UTM (`?utm_source=tiktok&utm_medium=bio&utm_campaign=ttwarmup`)
- `compliance_rules.json` — คำต้องห้าม/คำแทน/disclosure
- prompt อยู่ใน `src/01_research.py` (RESEARCH_PROMPT) + `src/02_script.py` (SCRIPT_PROMPT) แก้ได้

## วัดผล GA4 (verify ของเดิม)
bio = `ngernduangold.netlify.app/links?utm_source=tiktok&utm_medium=bio&utm_campaign=ttwarmup`.
หน้า `/links` มี JS (`LINKS_CHANNEL_JS`) อ่าน `utm_source` → rewrite ปุ่ม affiliate เป็น sub_id `tiktok_links_{provider}` อัตโนมัติ; คลิกยิง event `affiliate_click{channel:tiktok, sub_id:tiktok_links_*}`.
**ดูใน GA4:** Reports → Traffic acquisition (filter `session source = tiktok`) + Events → `affiliate_click` (param `channel=tiktok` / `sub_id` ขึ้นต้น `tiktok_`). เทียบกับ 4-week kill-criterion ใน UPLOAD-CHECKLIST.md.

---

## 🎬 Handoff #2 — production ครบวงจร $0 (registry + caption + schedule + render free)

> **render คลิปฟรี 100% ด้วย PIL + ffmpeg** (ไม่ใช้ AI credit / virality_predictor ที่กินเครดิต). คลังคลิป ~21 ไฟล์มีอยู่แล้ว.

### ไฟล์/สคริปต์เพิ่ม
- `clip_registry.json` (source of truth) — สร้างจาก `src/00_registry.py` (สแกน `vid_*.mp4` + ffprobe duration + map topic→slug + cta)
- `captions/<clip>.txt` — สร้างจาก `src/05_captions.py` (week1 approved verbatim + template-gen ที่เหลือ + compliance 2 ชั้น)
- `ready-for-cowork/posting-schedule.csv` — `src/make_schedule.py` (14 วัน owner tracker + kill-criterion)
- `src/06_burn_disclosure.py` — **opt-in** burn disclosure 3 วิท้ายคลิป (default ไม่รัน · ต้อง `pip install pillow`)
- `src/07_render.py` — render คลิปใหม่จาก render-spec JSON (ต้อง `pip install pillow numpy` + `fonts/`)

### env
```powershell
$env:TIKTOK_CLIPS_DIR="<โฟลเดอร์คลัง vid_*.mp4 ของ Cowork>"   # ให้ 00/05/06 หาคลิปเจอ
$env:TIKTOK_FONTS_DIR="<โฟลเดอร์ Bold/Reg/XBold .ttf>"         # ให้ 06/07 หาฟอนต์เจอ (Sarabun)
```

### Flow A — คลังเดิม → caption + schedule (ทำได้ทันที ฟรี)
```powershell
python src/00_registry.py ; python src/05_captions.py ; python src/make_schedule.py
```
→ ได้ `clip_registry.json` + `captions/*.txt` (compliant) + `posting-schedule.csv` → เจ้าของอัปมือตามตาราง (caption ก็อปจาก `captions/<clip>.txt`)

### Flow B — ผลิตคลิปใหม่ (เมื่อมี Qwen key · ฟรี ไม่ใช้ AI credit)
```powershell
python src/01_research.py ; python src/02_script.py ; python src/03_compliance.py     # สคริปต์ผ่าน compliance
# (adapter: scripts_clean.json -> render-spec JSON ต่อคลิป) แล้ว:
python src/07_render.py --spec <spec.json> --out captions_clip.mp4                     # render ฟรี PIL+ffmpeg
python src/00_registry.py ; python src/05_captions.py                                 # ลงทะเบียน + caption
```
> `04_manifest.py` จะเรียก `05_captions` ต่อท้ายอัตโนมัติถ้ามี `clip_registry.json` (best-effort).

### กฎเหล็ก (เหมือนเดิม): $0 · ไม่ fabricate · **ไม่ใส่ลิงก์ในคลิป/แคปชัน** (bio เท่านั้น) · ไม่ automate posting · ไม่เติมเครดิต/งบ · ⭐/ตัวเลข = อ้างอิงจริงเท่านั้น

