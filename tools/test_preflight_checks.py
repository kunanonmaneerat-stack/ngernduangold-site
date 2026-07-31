#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the preflight guards added 31 Jul 2026.

WHY THIS FILE EXISTS
  Every guard in here was written after a real incident, and each one was verified
  once by hand in the session that wrote it. A guard verified only once is a guard
  that quietly rots: the dangerous failure mode is not "it breaks loudly", it is
  "it keeps returning PASS after it has gone blind". So every check must prove it
  can BOTH fire and stay quiet, on every run.

  Covers:
    check_posting_cap      - <=2 posts/day/channel, >=3h apart (POSTING-POLICY rule 2)
    check_repeat_failures  - same channel failing repeatedly, and recovery detection
    manifest_posted_status - the "published" vocabulary gap in post_guard

USAGE
  py tools\\test_preflight_checks.py        # exit 0 = all pass

ASCII-ONLY SOURCE: repo rule - scripts that touch Thai must not contain Thai literals.
"""
import io, os, sys, json, datetime, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.path.join(HERE, "_test_ledger.tmp.jsonl")

import preflight as P
import post_guard as G

TODAY = datetime.date.today().isoformat()
YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print("  %-52s %-5s (want %-5s) %s" % (label, got, want, "OK" if ok else "*** FAIL"))
    return ok


def run_cap(rows):
    importlib.reload(P)
    with io.open(TMP, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    P.LEDGER = TMP
    P.results[:] = []
    P.check_posting_cap()
    return P.results[0]["status"]


def run_fail(rows):
    importlib.reload(P)
    with io.open(TMP, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    P.LEDGER = TMP
    P.results[:] = []
    P.check_repeat_failures()
    return P.results[0]


def live(hh, ch="facebook", ty="text", day=None):
    return {"type": ty, "channel": ch, "text_first80": "x",
            "ts": "%sT%s:00:00+07:00" % (day or TODAY, hh)}


def sched(i, publish_day):
    """A clip uploaded now but shown to the audience on publish_day."""
    return {"type": "video", "channel": "youtube", "clip_id": "c%d" % i,
            "text_first80": "x", "ts": "%sT09:%02d:00+07:00" % (TODAY, i * 3),
            "publish_at": publish_day, "source": "cc-dispatcher"}


def fail(ch, hh, day=None, why="NOT POSTED - x"):
    return {"type": "failure", "channel": ch, "text_first80": why,
            "ts": "%sT%s:00:00+07:00" % (day or TODAY, hh)}


print("POSTING CAP  (POSTING-POLICY rule 2: <=2/day/channel, >=3h apart)")
check("live posts 5h apart", run_cap([live("09"), live("14")]), "PASS")
check("live posts 1h apart", run_cap([live("09"), live("10")]), "FAIL")
check("3 live posts, well spaced -> over cap",
      run_cap([live("09"), live("13"), live("17")]), "FAIL")
check("comment does not count as a post",
      run_cap([live("09"), {"type": "comment", "channel": "facebook",
                            "text_first80": "c", "ts": TODAY + "T09:30:00+07:00"}]), "PASS")
check("empty ledger", run_cap([]), "PASS")
check("breach dated yesterday is history, not a gate",
      run_cap([live("09", day=YESTERDAY), live("10", day=YESTERDAY)]), "WARN")
# The false positive that this check shipped with on day one:
check("YT catch-up, 3 clips publishing on 3 days",
      run_cap([sched(0, TODAY), sched(1, "2026-08-01"), sched(2, "2026-08-02")]), "PASS")
check("YT 3 clips all publishing the SAME day",
      run_cap([sched(0, TODAY), sched(1, TODAY), sched(2, TODAY)]), "FAIL")
check("one scheduled + one live on the same day",
      run_cap([sched(0, TODAY), live("09")]), "PASS")
check("pinterest 3 pins spaced (cap is 5)",
      run_cap([live(h, "pinterest", "image") for h in ("01", "05", "09")]), "PASS")
check("pinterest 6 pins",
      run_cap([live(h, "pinterest", "image")
               for h in ("01", "05", "09", "13", "17", "21")]), "FAIL")

print("\nPOLICY WIRING  (numbers must come from policy.json, and fail safe without it)")
importlib.reload(P)
check("cap default read from policy", P.POST_CAP_DEFAULT, 2)
check("pinterest override read from policy", P.POST_CAP_BY_CHANNEL.get("pinterest"), 5)
check("min gap read from policy", P.POST_MIN_GAP_HOURS, 3)
_saved, P.POLICY = P.POLICY, os.path.join(HERE, "no-such-policy.json")
_caps, _gap, _types = P._limits()
P.POLICY = _saved
check("missing policy still enforces the written rule", (_caps.get("default"), _gap), (2, 3))

print("\nREPEAT FAILURES  (must fire when broken, go quiet once genuinely fixed)")
check("one failure is noise", run_fail([fail("facebook", "09")])["status"], "PASS")
check("two failures same channel", run_fail([fail("facebook", "09"), fail("facebook", "11")])["status"], "WARN")
check("three failures same channel",
      run_fail([fail("facebook", "09"), fail("facebook", "11"), fail("facebook", "13")])["status"], "FAIL")
check("delivered again after the last failure = recovered",
      run_fail([fail("facebook", "09"), fail("facebook", "11"), fail("facebook", "13"),
                live("15")])["status"], "PASS")
check("a success BEFORE the last failure is not recovery",
      run_fail([live("08"), fail("facebook", "09"), fail("facebook", "11"),
                fail("facebook", "13")])["status"], "FAIL")
check("failures older than the window are ignored",
      run_fail([fail("facebook", "09", day="2026-06-01"),
                fail("facebook", "11", day="2026-06-01")])["status"], "PASS")
_r = run_fail([fail("tiktok", "09"), fail("tiktok", "11")])
check("auto=false + no auto_legs is tagged as drift", "DRIFT" in _r["detail"], True)
_r = run_fail([fail("facebook", "09"), fail("facebook", "11")])
check("a channel with declared auto_legs is not drift", "DRIFT" in _r["detail"], False)

print("\nMANIFEST VOCABULARY  (post_guard must understand what the uploader writes)")
def status(v):
    r = G.manifest_posted_status({"posted": {"youtube": v}}, "YOUTUBE", "youtube")
    return (r or {}).get("status") if isinstance(r, dict) else None
check("'published (...)' - what yt_upload writes past its slot", status("published (yt-api X)"), "POSTED")
check("'scheduled (...)'", status("scheduled (yt-api X)"), "SCHEDULED-UI")
check("'posted (...)'", status("posted (fb reel)"), "POSTED")
check("empty string is not a claim", status(""), None)
check("unknown word is not a claim", status("queued"), None)
check("'scheduled ... published' stays scheduled",
      status("scheduled, will be published 19:00"), "SCHEDULED-UI")

try:
    os.remove(TMP)
except OSError:
    pass

bad = results.count(False)
print("\n%d checks, %d failed" % (len(results), bad))
print("ALL PASS" if not bad else "*** FAILURES ABOVE ***")
sys.exit(1 if bad else 0)
