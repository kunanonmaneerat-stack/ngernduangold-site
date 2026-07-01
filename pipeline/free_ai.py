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

Key resolution order: env GOOGLE_API_KEY | GOOGLE_AI_STUDIO_KEY | GEMINI_API_KEY,
then gemini_key.txt (plain one-line), then ga4-admin/.env (KEY=VALUE).
If no key -> generate() returns (None, "NO_KEY") so every caller FAILS CLOSED:
it skips, never pays, never crashes. stdlib only; google-generativeai is imported lazily
(only when a key is actually present), so this module + --selftest run with zero deps.
"""
import os, sys, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
USAGE_DIR = os.path.join(REPO, "automation-log", "ai-usage")   # committed = proof of $0 to Cowork
ENV_FILE = r"C:\Users\nL_ku\ga4-admin\.env"                     # non-repo, owner-managed
KEY_FILE = r"C:\Users\nL_ku\gemini_key.txt"                     # non-repo, owner-managed (plain one-line key, matches run_gemini.bat)

# Free-tier models we are allowed to call (AI Studio free). Keep flash-class only.
FREE_MODELS = {"gemini-3.5-flash", "gemini-3.1-flash-lite",
               "gemini-2.5-flash", "gemini-2.5-flash-lite"}
# NOTE: gemini-2.0-flash / 2.0-flash-lite / 1.5-flash* removed 2026-06-28 — Google retired them
# (calls returned 404 "no longer available"). Default workhorse is gemini-3.5-flash (TIERS below).
# Any model whose name contains one of these = PAID / disallowed -> hard refuse.
PAID_MARKERS = ("veo", "imagen", "qwen", "wan2", "dashscope", "gpt-", "claude-", "-pro", "ultra")
# Conservative daily request cap, kept under the AI Studio free RPD so we never spill into billing.
FREE_DAILY_REQUESTS = 1200

# Task-fit intelligence tiers: a caller passes a tier alias (or an explicit model name).
# Match the model to the job — cheap for high-volume/trivial, smart for the work that matters.
# Owner ceiling = 3.5-flash (no Pro). To enable Pro later: point "max" at gemini-2.5-pro
# AND add "gemini-2.5-pro" to FREE_MODELS below (it is the only change needed).
TIERS = {
    "cheap": "gemini-3.1-flash-lite",   # high-volume / trivial / healthcheck pings
    "smart": "gemini-3.5-flash",        # default workhorse: trend research, creative scripts, vision QA
    "max":   "gemini-3.5-flash",        # current ceiling == smart (Pro disabled by owner choice)
}
DEFAULT_TIER = "smart"


def resolve_model(name):
    """Tier alias ('cheap'/'smart'/'max') -> model name; explicit model names pass through unchanged."""
    return TIERS.get(name, name)


def _now():
    return datetime.datetime.now()


def _load_key():
    k = (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_AI_STUDIO_KEY")
         or os.getenv("GEMINI_API_KEY"))
    if k:
        return k
    # plain one-line key file (matches run_gemini.bat: GOOGLE_API_KEY <- gemini_key.txt)
    try:
        v = open(KEY_FILE, encoding="utf-8-sig").read().strip().strip('"').strip("'")
        if v:
            return v
    except FileNotFoundError:
        pass
    try:
        for line in open(ENV_FILE, encoding="utf-8-sig"):
            s = line.strip()
            if s.startswith(("GOOGLE_API_KEY", "GOOGLE_AI_STUDIO_KEY", "GEMINI_API_KEY")) and "=" in s:
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


def generate(prompt, model=DEFAULT_TIER, images=None):
    """Returns (text, status). status: 'ok' | 'NO_KEY' | 'BLOCKED:..' | 'ERROR:..'.
    `model` may be a tier alias ('cheap'/'smart'/'max') or an explicit model name.
    Never raises, never escalates to a disallowed model."""
    model = resolve_model(model)
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
        assert not is_paid("gemini-2.5-flash"), "flash must be free"
        assert allow("gemini", "veo-3")[0] is False
        assert allow("gemini", "gemini-1.5-pro")[0] is False
        assert allow("gemini", "imagen-3")[0] is False
        assert resolve_model("smart") == "gemini-3.5-flash", "smart tier"
        assert resolve_model("cheap") == "gemini-3.1-flash-lite", "cheap tier"
        assert resolve_model("gemini-3.5-flash") == "gemini-3.5-flash", "explicit passthrough"
        txt, st = generate("x", model="veo-3")   # disallowed -> BLOCKED, never calls network / pays
        assert st.startswith("BLOCKED"), st
        print("selftest OK · tiers", TIERS, "· key_present:", bool(_load_key()))
    else:
        print("gemini requests today:", used_today("gemini"), "/", FREE_DAILY_REQUESTS,
              "· key_present:", bool(_load_key()))
