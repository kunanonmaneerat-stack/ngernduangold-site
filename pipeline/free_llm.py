"""free_llm.py — rotating free/cheap LLM client for the ngernduangold engine.

หลักการ: มี "pool" โมเดลเรียงตามลำดับความสำคัญ · เรียกทีละตัว · ตัวไหนยอดหมด/เต็ม
(402/429) หรือไม่มี (404) ก็ข้ามไปตัวถัดไปอัตโนมัติ -> "เต็มแล้วสลับ วนทั้งเดือน".

คีย์อ่านจาก ENVIRONMENT เท่านั้น (ห้าม hardcode -- repo public):
  setx GLM_KEY      "<zhipu key>"       # glm-4.5-flash (ฟรี)
  setx QW_KEY       "<dashscope-intl>"  # qwen-plus / qwen-turbo
  setx DEEPSEEK_KEY "<sk-...>"          # deepseek-chat (เมื่อมียอด)
  (QWEN_API_KEY = OpenRouter เดิม ใช้เป็น fallback)

ใช้:  from free_llm import generate
      text, model = generate("คำถาม...")   # คืน (ข้อความ, ชื่อโมเดล) หรือ (None, None)
stdlib only.
"""
import os, json, urllib.request, urllib.error
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# (label, base_url, model, env_key_name)
POOL = [
    # PRIORITY = เก่งสุดก่อน. OpenRouter free frontier นำ · qwen เป็น fallback ที่นิ่ง+ไทยดี.
    # OpenRouter free (verified live 2026-06-24) ใช้คีย์ QWEN_API_KEY (OpenRouter). เต็ม/429 -> สลับตัวถัดไปอัตโนมัติ.
    ("or-nemotron-ultra", "https://openrouter.ai/api/v1/chat/completions", "nvidia/nemotron-3-ultra-550b-a55b:free", "QWEN_API_KEY"),  # 550B MoE frontier reasoning -- LEAD
    ("qwen-plus",      "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-plus", "QW_KEY"),       # reliable, strong Thai -- primary fallback
    ("qwen-turbo",     "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-turbo", "QW_KEY"),
    ("glm-4.5-flash",  "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4.5-flash", "GLM_KEY"),
    ("deepseek-chat",  "https://api.deepseek.com/chat/completions", "deepseek-chat", "DEEPSEEK_KEY"),
    ("or-nemotron-nano", "https://openrouter.ai/api/v1/chat/completions", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "QWEN_API_KEY"),  # 30B reasoning free fallback
]

SKIP_CODES = (401, 402, 403, 404, 429)


def _get_key(name):
    """อ่านคีย์: process env ก่อน, ถ้าว่างอ่านจาก HKCU\\Environment (setx) -- กัน env เก่าค้างใน process แม่."""
    v = os.environ.get(name, "")
    if v:
        return v
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        val = winreg.QueryValueEx(k, name)[0]
        winreg.CloseKey(k)
        return val or ""
    except Exception:
        return ""


def _call(url, model, key, prompt, system, max_tokens, temperature):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = json.dumps({"model": model, "messages": msgs,
                       "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.load(r)
        m = d["choices"][0]["message"]
        txt = (m.get("content") or m.get("reasoning_content") or "")
        if "\ufffd" in txt:  # provider returned a lossy/truncated multibyte char; strip the marker so it never reaches written files
            import sys as _s; _s.stderr.write("[free_llm] WARN stripped U+FFFD from " + str(model) + " response\n")
            txt = txt.replace("\ufffd", "")
        return txt.strip()


def generate(prompt, system="", max_tokens=2000, temperature=0.4, verbose=False):
    """ลองทีละตัวใน POOL -- คืน (text, model_label) ของตัวแรกที่สำเร็จ, ไม่งั้น (None, None)."""
    for label, url, model, env in POOL:
        key = _get_key(env)
        if not key:
            if verbose:
                print("[free_llm] skip", label, "(no", env + ")")
            continue
        try:
            txt = _call(url, model, key, prompt, system, max_tokens, temperature)
            if txt and len(txt.strip()) > 10:
                if verbose:
                    print("[free_llm] OK", label)
                return txt, label
        except urllib.error.HTTPError as e:
            if verbose:
                print("[free_llm]", label, "HTTP", e.code, "-> rotate")
            if e.code in SKIP_CODES:
                continue
        except Exception as e:
            print("[free_llm]", label, "ERR", str(e)[:120], "-> rotate")
            continue
    return None, None
