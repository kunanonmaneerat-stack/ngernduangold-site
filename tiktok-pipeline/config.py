# config.py — shared paths + Qwen (OpenAI-compatible) client. $0, fail-soft, no crash without key.
# Real runs need a free Qwen key (OpenRouter/DashScope). Without it, scripts exit politely
# OR run with --dry-run (deterministic rule-based fallback, no LLM) to test the orchestration.
import os, sys, json, re, pathlib

# Windows console may be cp874 (Thai) and crash on '·'/emoji in prints — force UTF-8, never raise.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT     = pathlib.Path(__file__).resolve().parent
INPUT    = ROOT / "input"
DRAFTS   = ROOT / "drafts"
READY    = ROOT / "ready-for-cowork"
CAPTIONS = ROOT / "captions"
# clip library: set TIKTOK_CLIPS_DIR to Cowork's outputs folder; default = repo/clips
CLIPS_DIR = pathlib.Path(os.environ.get("TIKTOK_CLIPS_DIR", str(ROOT / "clips")))
FONTS_DIR = pathlib.Path(os.environ.get("TIKTOK_FONTS_DIR", str(ROOT / "fonts")))
for _d in (INPUT, DRAFTS, READY, CAPTIONS):
    _d.mkdir(exist_ok=True)

QWEN_API_KEY  = os.environ.get("QWEN_API_KEY", "").strip()
QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
QWEN_MODEL    = os.environ.get("QWEN_MODEL", "qwen/qwen-2.5-72b-instruct").strip()
HAS_KEY       = bool(QWEN_API_KEY)

NO_KEY_HELP = """\
[tiktok-pipeline] QWEN_API_KEY ไม่ได้ตั้ง — โหมด Qwen ปิดอยู่.
ขอ key ฟรี (free-tier) ได้ที่:
  • OpenRouter : https://openrouter.ai/keys  (มีรุ่นฟรี เช่น qwen/qwen-2.5-72b-instruct:free)
  • DashScope  : https://dashscope.console.aliyun.com  (Qwen ทางการ มีโควตาฟรี)
แล้วตั้ง env (PowerShell):  $env:QWEN_API_KEY="sk-..."   ;  $env:QWEN_BASE_URL="https://openrouter.ai/api/v1"  ;  $env:QWEN_MODEL="qwen/qwen-2.5-72b-instruct"
หรือทดสอบ pipeline แบบไม่ใช้ LLM ก่อน:  python src/01_research.py --dry-run  (แล้ว 02/03/04 --dry-run ตามลำดับ)
"""

def jload(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))

def jsave(p, obj):
    pathlib.Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def gate(dry_run):
    """Return True if the LLM path should run. Polite-exit if no key and not dry-run."""
    if dry_run:
        return False
    if not HAS_KEY:
        print(NO_KEY_HELP)
        sys.exit(0)
    return True

def extract_json(text):
    """Pull the first JSON array/object out of an LLM reply (handles ```json fences / prose)."""
    if not text:
        raise ValueError("empty LLM reply")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    for op, cl in (("[", "]"), ("{", "}")):
        i, j = text.find(op), text.rfind(cl)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(text)

def qwen_chat(system, user, temperature=0.4, max_tokens=2800):
    """OpenAI-compatible chat call to the Qwen endpoint. Raises if no key."""
    if not HAS_KEY:
        raise RuntimeError("QWEN_API_KEY not set")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
        r = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature, max_tokens=max_tokens)
        return r.choices[0].message.content
    except ImportError:
        import urllib.request
        body = json.dumps({"model": QWEN_MODEL,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                           "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
        req = urllib.request.Request(QWEN_BASE_URL + "/chat/completions", data=body,
                                     headers={"Authorization": "Bearer " + QWEN_API_KEY, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
