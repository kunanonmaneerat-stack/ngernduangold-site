#!/usr/bin/env python3
"""telegram_notify — push ngernduangold alerts to Telegram real-time.

Best-effort: **NEVER raises into the caller** — a failed ping must not fail a routine.
stdlib only (urllib) — no pip dep.

⚠️ Creds are SECRET and this repo is PUBLIC — token/chat_id are NEVER stored here.
Resolved at runtime from, in order:
  1) environment vars  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  2) non-repo file      C:\\Users\\nL_ku\\ga4-admin\\telegram.env   (KEY=VALUE lines)
If creds are missing → skips silently (returns False), routine continues.

CLI:
  python telegram_notify.py --test            # send "alerts online" test ping
  python telegram_notify.py --text "ข้อความ"   # send arbitrary text (HTML)
"""
import os, sys, json, argparse, urllib.request

ENV_FILE = r"C:\Users\nL_ku\ga4-admin\telegram.env"   # non-repo (not public) — owner fills

def _load_creds():
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        return tok, chat
    try:
        for line in open(ENV_FILE, encoding="utf-8-sig"):  # -sig strips PowerShell Out-File BOM
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "TELEGRAM_BOT_TOKEN" and not tok:
                tok = v
            elif k == "TELEGRAM_CHAT_ID" and not chat:
                chat = v
    except FileNotFoundError:
        pass
    return tok, chat

def notify(text: str) -> bool:
    """Send to Telegram (HTML, no link preview). Returns True if accepted; never raises."""
    tok, chat = _load_creds()
    if not (tok and chat):
        sys.stderr.write("telegram_notify: creds missing (env or %s) — skipped\n" % ENV_FILE)
        return False
    url = "https://api.telegram.org/bot%s/sendMessage" % tok
    body = json.dumps({"chat_id": chat, "text": text,
                       "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8")
    for attempt in (1, 2):                      # try once + retry once
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            if urllib.request.urlopen(req, timeout=10).getcode() < 400:
                return True
        except Exception as e:
            if attempt == 2:
                sys.stderr.write("telegram_notify: failed after retry: %s\n" % e)
    return False

def approval(what: str, detail: str = "", link: str = "") -> bool:
    """Approval-request ping → owner's phone. Owner replies YES/NO in the Cowork chat
    (2-way bot reply is a later optional). Use before any PUBLIC post needing sign-off
    (Pantip / Threads / TikTok / comment reply)."""
    msg = "🔔 <b>APPROVAL NEEDED</b>: " + what
    if detail:
        msg += "\n" + detail
    if link:
        msg += "\n" + link
    msg += "\n→ ตอบ <b>YES</b> (อนุมัติโพสต์) / <b>NO</b> (ไม่อนุมัติ)"
    return notify(msg)

def posted(channel: str, topic: str = "", link: str = "") -> bool:
    """Done-notify — posting is PRE-APPROVED, so this is informational (NOT a gate).
    Sent AFTER a post is live. Format: ✅ โพสต์แล้ว: {channel} · {topic} · {link}."""
    msg = "✅ <b>โพสต์แล้ว</b>: " + channel
    if topic:
        msg += " · " + topic
    if link:
        msg += "\n" + link
    return notify(msg)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--approval", help="what needs approval (sends APPROVAL NEEDED ping)")
    ap.add_argument("--detail", default="", help="draft summary / context")
    ap.add_argument("--link", default="", help="optional link / permalink")
    ap.add_argument("--posted", help="channel just posted to (sends ✅ done-notify)")
    ap.add_argument("--topic", default="", help="topic/headline for the done-notify")
    a = ap.parse_args()
    if a.test:
        ok = notify("🔔 ngernduangold alerts ออนไลน์แล้ว — ระบบแจ้งเตือน Telegram พร้อมใช้งาน")
        print("TEST sent:", ok)
        sys.exit(0 if ok else 1)
    if a.posted:
        ok = posted(a.posted, a.topic, a.link)
        print("POSTED-notify sent:", ok)
        sys.exit(0 if ok else 1)
    if a.approval:
        ok = approval(a.approval, a.detail, a.link)
        print("APPROVAL sent:", ok)
        sys.exit(0 if ok else 1)
    print("sent:", notify(a.text)) if a.text else print("usage: --text '...' | --posted '<channel>' [--topic .. --link ..] | --approval '...' | --test")
