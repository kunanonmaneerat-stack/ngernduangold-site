"""Offline compatibility surface for the retired network LLM pool.

The old implementation rotated from nominally free providers into Qwen/DeepSeek
fallbacks that could consume paid quota.  Scheduled/local callers also had no
authenticated owner proof, so an actor string or flag could never safely enable
that network action.  Network generation is therefore disabled at this shared
sink: ``generate`` is a no-op and ``_call`` fails closed before any HTTP request.

An authenticated owner-managed generation path may be implemented later as a
separate capability.  It must not be restored with a CLI actor/flag alone.
"""
import os
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


class NetworkGenerationBlocked(RuntimeError):
    """Raised before a legacy provider call can reach the network."""


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
    raise NetworkGenerationBlocked(
        "network LLM generation is disabled; authenticated owner authority is not configured"
    )


def generate(prompt, system="", max_tokens=2000, temperature=0.4, verbose=False):
    """Return an offline miss without reading credentials or touching network."""
    if verbose:
        print("[free_llm] BLOCKED: network/paid generation requires authenticated owner authority")
    return None, None
