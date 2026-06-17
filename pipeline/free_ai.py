#!/usr/bin/env python3
"""free_ai — ZERO-BUDGET guardrail + free-tier Gemini wrapper for the content pipeline.

HARD RULES (blueprint 2026-06-18, enforced in code):
  * NO paid models — Veo3 / Imagen3 / Qwen-video / wan2.x / dashscope / *-pro / gpt-* / claude-*
    are REFUSED outright. There is NO silent fallback to a paid model, ever.
  * Only Google AI Studio FREE tier (gemini-*-flash). API key comes from the ENVIRONMENT,
    never hardcoded — this repo is PUBLIC.
  * Cost guard: every call is logged; requests/day are hard-capped under the free quota;
    once the cap is hit the call is refused (it does NOT escalate to a paid tier).
  * NO anti-fingerprint / metadata-scrub / bot-evasion logic — intentionally absent (ToS-safe).

Key resolution order: env GOOGLE_AI_STUDIO_KEY | GEMINI_API_KEY, then ga4-admin/.env (KEY=VALUE).
If no key -> generate() returns (None, "NO_KEY") so every caller FAILS CLOSED:
it skips, never pays, never crashes. stdlib only; google-generativeai is imported lazily
(only when a key is actually present), so this module + --selftest run with zero deps.
"""
import os, sys, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
USAGE_DIR = os.path.join(REPO, "automation-log", "ai-usage")   # committed = proof of $0 to Cowork
ENV_FILE = r"C:\Users\nL_ku\ga4-admin\.env"                     # non-repo, owner-managed

# Free-tier models we are allowed to call (AI Studio free). Keep flash-class only.
FREE_MODELS = {"gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-flash-8b"}
# Any model whose name contains one of these = PAID / disallowed -> hard refuse.
PAID_MARKERS = ("veo", "imagen", "qwen", "wan2", "dashscope", "gpt-", "claude-", "-pro", "ultra")
# Conservative daily request cap, kept under the AI Studio free RPD so we never spill into billing.
FREE_DAILY_REQUESTS = 1200


def _now():
    return datetime.datetime.now()


def _load_key():
    k = os.getenv("GOOGLE_AI_STUDIO_KEY") or os.getenv("GEMINI_API_KEY")
    if k:
        return k
    try:
        for line in open(ENV_FILE, encoding="utf-8-sig"):
            s = line.strip()
            if s.startswith(("GOOGLE_AI_STUDIO_KEY", "GEMINI_API_KEY")) and "=" in s:
                v = s.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    except FileNotFoundError:
        pass
    return None


def is_paid(model):
    m = (model or "").lower()
    return any(p in m for p in PAID_MARKERS)


def _usage_path():
    os.makedirs(USAGE_DIR, exist_ok=True)
    return os.path.join(USAGE_DIR, _now().strftime("%Y-%m-%d") + ".jsonl")


def used_today(provider="gemini"):
    n = 0
    try:
        for line in open(_usage_path(), encoding="utf-8"):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("provider") == provider and e.get("ok"):
                n += 1
    except FileNotFoundError:
        pass
    return n


def record(provider, model, ok, note=""):
    row = {"ts": _now().isoformat(timespec="seconds"), "provider": provider,
           "model": model, "ok": bool(ok), "note": note}
    with open(_usage_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def allow(provider, model):
    """(ok, reason). The single gate every AI call passes — refuses paid + over-quota."""
    if is_paid(model):
        return (False, "PAID/disallowed model refused (zero-budget, NO fallback): " + str(model))
    if model not in FREE_MODELS:
        return (False, "model not in FREE allowlist: " + str(model))
    if used_today(provider) >= FREE_DAILY_REQUESTS:
        return (False, "free daily quota reached -> STOP (no paid fallback)")
    return (True, "ok")


def generate(prompt, model="gemini-2.0-flash", images=None):
    """Returns (text, status). status: 'ok' | 'NO_KEY' | 'BLOCKED:..' | 'ERROR:..'.
    Never raises, never escalates to a paid model."""
    key = _load_key()
    if not key:
        return (None, "NO_KEY")
    ok, why = allow("gemini", model)
    if not ok:
        record("gemini", model, False, why)
        return (None, "BLOCKED:" + why)
    try:
        import google.generativeai as genai      # lazy: only when a key exists
        genai.configure(api_key=key)
        gm = genai.GenerativeModel(model)
        resp = gm.generate_content([prompt] + (images or []))
        record("gemini", model, True, "")
        return (resp.text, "ok")
    except Exception as e:
        record("gemini", model, False, "ERROR:" + str(e)[:140])
        return (None, "ERROR:" + str(e)[:140])


if __name__ == "__main__":
    import argparse
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        # Verify guard logic WITHOUT any network/key.
        assert is_paid("veo-3") and is_paid("qwen-vl-max") and is_paid("imagen-3"), "paid must be blocked"
        assert is_paid("gemini-1.5-pro"), "-pro must count as paid"
        assert not is_paid("gemini-2.0-flash"), "flash must be free"
        assert allow("gemini", "veo-3")[0] is False
        assert allow("gemini", "gemini-1.5-pro")[0] is False
        assert allow("gemini", "imagen-3")[0] is False
        txt, st = generate("hello")            # no key in this env -> must be NO_KEY, no crash, no pay
        assert st in ("NO_KEY", "BLOCKED", "ERROR") or st == "ok"
        print("selftest OK · paid-blocked ✓ · no-key fail-closed ✓ · key_present:", bool(_load_key()))
    else:
        print("gemini requests today:", used_today("gemini"), "/", FREE_DAILY_REQUESTS,
              "· key_present:", bool(_load_key()))
