#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Is ngernduangold.com actually serving the site? Answer it for free.

WHY THIS FILE EXISTS
  Until 1 Aug 2026 this question was answered by a Cowork agent task that fired
  every 6 hours - 120 LLM runs a month, each one booting the Chrome extension,
  opening a tab on the owner's machine and taking a screenshot, to decide a
  yes/no that an HTTP request answers. The site gets roughly one session a day,
  so the value at risk during an outage is a fraction of a session; the check
  was costing far more than the thing it protected.

  Worse, it was not even reliable coverage: the agent task only runs while the
  desktop app is open, and the extension needs a reachable browser. This script
  runs inside run_daily.cmd, which fires from Windows Task Scheduler at 07:00
  whether or not anything else in the stack is alive - the same property that
  made run_daily the right home for preflight.

WHAT "UP" MEANS HERE
  Not "returned 200". Netlify's paused-site and usage-limit pages are perfectly
  healthy HTTP responses, and that is precisely the failure we care about. So a
  pass requires the homepage to contain the brand name AND at least two of the
  four category words - i.e. the page a reader would actually get.

OUTPUT
  exit 0 = up, and any stale alert file is removed
  exit 2 = down, and automation-log/cowork-inbox/SITE-DOWN-ALERT.md is written
           (the morning routines read that folder, so this reaches a human)
  exit 1 = could not tell (no network from this box, DNS failure, timeout).
           Deliberately NOT the same as down: "I could not look" must never be
           reported as "the site is broken", or the alert becomes noise and
           gets ignored on the day it is real.

USAGE
  py tools\\uptime_check.py             # check, write/clear the alert file
  py tools\\uptime_check.py --quiet     # exit code only, no stdout
  py tools\\uptime_check.py --selftest  # prove judge() still fires; no network

ASCII-ONLY SOURCE: repo rule for scripts that touch Thai (OPERATING-NOTES 19).
The Thai below is \\u escapes on purpose - raw Thai in a .py here has been
corrupted before. Decoded it is the brand name plus the four homepage category
cards (credit card / saving / loan / insurance), which is what a working page
must actually render.
"""
import io, os, sys, time, json, argparse, datetime

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except ImportError:                                   # pragma: no cover
    from urllib2 import Request, urlopen, URLError, HTTPError

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
INBOX = os.path.join(REPO, "automation-log", "cowork-inbox")
ALERT = os.path.join(INBOX, "SITE-DOWN-ALERT.md")
URL = "https://ngernduangold.com/"
TIMEOUT = 20

# The brand name, then the four category cards. Rendered page must show the
# brand plus >=2 categories. Escapes, not literals - see the module docstring.
BRAND = u"\u0e40\u0e07\u0e34\u0e19\u0e40\u0e14\u0e37\u0e2d\u0e19\u0e2a\u0e21\u0e2d\u0e07\u0e17\u0e2d\u0e07"  # ngoen duean samong thong
CATEGORIES = [
    u"\u0e1a\u0e31\u0e15\u0e23\u0e40\u0e04\u0e23\u0e14\u0e34\u0e15",              # credit card
    u"\u0e2d\u0e2d\u0e21\u0e40\u0e07\u0e34\u0e19",                                # saving
    u"\u0e2a\u0e34\u0e19\u0e40\u0e0a\u0e37\u0e48\u0e2d",                          # loan
    u"\u0e1b\u0e23\u0e30\u0e01\u0e31\u0e19",                                      # insurance
]
# Netlify's own failure pages return 200, so match on their wording too.
PAUSED_MARKERS = ["site not available", "this site was paused",
                  "usage limits", "site has been suspended",
                  "deploy failed", "page not found"]


def fetch():
    """(status, body, error). Cache-busted so a CDN copy cannot mask an outage."""
    url = "%s?uptime=%d" % (URL, int(time.time()))
    req = Request(url, headers={
        "User-Agent": "ngernduangold-uptime-check/1.0 (+run_daily.cmd)",
        "Cache-Control": "no-cache",
    })
    try:
        r = urlopen(req, timeout=TIMEOUT)
        raw = r.read()
        return getattr(r, "status", r.getcode()), raw.decode("utf-8", "replace"), None
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, body, None
    except URLError as e:
        return None, "", "network: %s" % (getattr(e, "reason", e),)
    except Exception as e:                              # noqa: BLE001
        return None, "", "%s: %s" % (type(e).__name__, e)


def judge(status, body):
    """-> (verdict, reason). verdict in {up, down, unknown}."""
    if status is None:
        return "unknown", "no response"
    low = body.lower()
    hit = [m for m in PAUSED_MARKERS if m in low]
    if hit:
        return "down", "netlify/error page (matched %r), HTTP %s" % (hit[0], status)
    if status >= 500:
        return "down", "HTTP %s from origin" % status
    if status >= 400:
        return "down", "HTTP %s on the homepage" % status
    found = [c for c in CATEGORIES if c in body]
    if BRAND not in body:
        return "down", "HTTP %s but the brand name is missing (%d/%d category words present)" % (
            status, len(found), len(CATEGORIES))
    if len(found) < 2:
        return "down", "HTTP %s, brand present but only %d/%d category cards rendered" % (
            status, len(found), len(CATEGORIES))
    return "up", "HTTP %s, brand + %d/%d category cards present, %d bytes" % (
        status, len(found), len(CATEGORIES), len(body))


def write_alert(reason, status):
    if not os.path.isdir(INBOX):
        os.makedirs(INBOX)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# SITE DOWN - ngernduangold.com",
        "",
        "Detected %s by tools/uptime_check.py (run_daily.cmd, no LLM involved)." % now,
        "",
        "- url    : %s" % URL,
        "- http   : %s" % status,
        "- reason : %s" % reason,
        "",
        "## What to do",
        "1. Open the Netlify dashboard -> Usage / Billing. A bandwidth or build-minute",
        "   cap pauses the site while still answering HTTP 200, which is why this check",
        "   reads the page body rather than trusting the status code.",
        "2. If Netlify is healthy, check the most recent deploy for a build failure.",
        "3. While the site is down, hold posting. Driving traffic to a dead page burns",
        "   the reach and teaches the algorithm the link is bad.",
        "",
        "This file is deleted automatically by the next passing check.",
    ]
    with io.open(ALERT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def clear_alert():
    if os.path.exists(ALERT):
        try:
            os.remove(ALERT)
            return True
        except OSError:
            pass
    return False


def selftest():
    """Prove judge() can BOTH fire and stay quiet, without touching the network.

    Written because this script's real-world answer from a sandbox is always
    "unknown" - which looks identical to a checker that has stopped working.
    """
    good = u"<html><body><h1>%s</h1>%s</body></html>" % (
        BRAND, u"".join(CATEGORIES))
    cases = [
        ("healthy homepage",              200, good,                      "up"),
        ("netlify paused page",           200, "This site was paused",    "down"),
        ("usage limits page",             200, "reached its usage limits", "down"),
        ("200 but empty body",            200, "",                        "down"),
        ("200, brand only, no categories", 200, u"<h1>%s</h1>" % BRAND,    "down"),
        ("brand + 2 of 4 categories",     200, BRAND + CATEGORIES[0] + CATEGORIES[3], "up"),
        ("brand + 1 category only",       200, BRAND + CATEGORIES[0],     "down"),
        ("origin 500",                    500, good,                      "down"),
        ("404",                           404, "Page not found",          "down"),
        ("no response at all",            None, "",                       "unknown"),
    ]
    bad = 0
    for label, st, body, want in cases:
        got, why = judge(st, body)
        ok = got == want
        bad += 0 if ok else 1
        print("  %-34s %-8s (want %-8s) %s" % (label, got, want, "OK" if ok else "*** FAIL"))
        if not ok:
            print("      reason: %s" % why)
    print("\n%d cases, %d failed" % (len(cases), bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="exercise judge() on synthetic pages; no network")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    status, body, err = fetch()
    verdict, reason = judge(status, body)
    if err and verdict == "unknown":
        reason = err

    if verdict == "up":
        cleared = clear_alert()
        if not args.quiet:
            print("uptime  UP    %s%s" % (reason, "  (cleared stale alert)" if cleared else ""))
        code = 0
    elif verdict == "down":
        write_alert(reason, status)
        if not args.quiet:
            print("uptime  DOWN  %s  -> wrote %s" % (reason, ALERT))
        code = 2
    else:
        # Cannot see the internet from here. Say so; do not cry wolf, and do not
        # clear an existing alert either - this run proves nothing either way.
        if not args.quiet:
            print("uptime  UNKNOWN  %s (not treated as an outage)" % reason)
        code = 1

    if args.json:
        print(json.dumps({"verdict": verdict, "http": status, "reason": reason},
                         ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
