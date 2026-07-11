#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ig_token_check.py — validate IG long-lived token + optional auto-refresh (order 2026-07-11 GATE)
#
# Modes:
#   validate (always): GET /me with the token — invalid/expired => exit 2 (workflow red -> owner email)
#   expiry check (needs FB_APP_ID + FB_APP_SECRET): GET /debug_token — warn/exit 2 if < 14 days left
#   auto-refresh (needs FB_APP_ID + FB_APP_SECRET + OUT_FILE): exchange fb_exchange_token -> writes the
#       NEW token ONLY to OUT_FILE (never printed) — the workflow step pipes it into `gh secret set`.
#
# Exit: 0 = healthy (refreshed token written if applicable), 2 = invalid/expiring & not refreshable.
import io, os, sys, json, datetime, urllib.request, urllib.parse, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GRAPH = "https://graph.facebook.com/v22.0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
APP_ID = os.environ.get("FB_APP_ID", "")
APP_SECRET = os.environ.get("FB_APP_SECRET", "")
OUT_FILE = os.environ.get("OUT_FILE", "")


def get(path, params):
    url = GRAPH + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode("utf-8", "replace")[:400]}


def main():
    if not TOKEN:
        print("[token] IG_ACCESS_TOKEN not set — nothing to check (pipeline dormant)")
        return 0

    me = get("/me", {"access_token": TOKEN})
    if "error" in me:
        print("[token] INVALID/EXPIRED: %s" % me["error"])
        print("[token] -> re-issue per runbook §4 (Graph API Explorer -> exchange long-lived -> update secret)")
        return 2
    print("[token] valid (user id %s)" % me.get("id"))

    if not (APP_ID and APP_SECRET):
        print("[token] FB_APP_ID/FB_APP_SECRET not set — skip expiry check/auto-refresh (manual refresh per runbook §4)")
        return 0

    dbg = get("/debug_token", {"input_token": TOKEN, "access_token": APP_ID + "|" + APP_SECRET})
    exp = dbg.get("data", {}).get("expires_at", 0)
    if exp:
        left = datetime.datetime.fromtimestamp(exp, datetime.timezone.utc) - datetime.datetime.now(datetime.timezone.utc)
        print("[token] expires in %d days" % left.days)
    else:
        print("[token] no expiry reported (may be never-expiring page token) — OK")
        return 0

    # refresh when under 21 days (exchange resets the 60-day clock; harmless to do monthly)
    if left.days > 21:
        return 0
    print("[token] < 21 days left — attempting refresh (fb_exchange_token)")
    r = get("/oauth/access_token", {"grant_type": "fb_exchange_token", "client_id": APP_ID,
                                    "client_secret": APP_SECRET, "fb_exchange_token": TOKEN})
    new = r.get("access_token", "")
    if not new:
        print("[token] refresh FAILED: %s — re-issue manually per runbook §4" % r.get("error", r))
        return 2
    if OUT_FILE:
        io.open(OUT_FILE, "w", encoding="utf-8").write(new)
        print("[token] refreshed OK -> written to OUT_FILE for secret update (token not logged)")
    else:
        print("[token] refreshed OK but OUT_FILE not set — cannot persist; update secret manually (runbook §4)")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
