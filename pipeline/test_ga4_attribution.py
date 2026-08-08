#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unit test: every GA4 event must be filed under its OWN channel.

Run: python pipeline/test_ga4_attribution.py   -> exit 0 all pass, exit 1 fail.  No network.

On 9 Aug 2026 a direct GA4 query showed both buy_intent_click events came from (direct) on
1 Aug, while automation-log/ga4-metrics.csv filed them under pantip.  Cause: the aggregating
loop assigned the channel variable only in the affiliate_click branch, so buy_intent rows
inherited the previous affiliate row's channel.  The output stayed perfectly plausible - the
totals were right, only the attribution was wrong - and it survived a week of daily runs and
one strategy note built on top of it.

Case 1 replays the exact production ordering that produced the wrong file.  The reverse
tests matter just as much: a fold that filed EVERYTHING under direct would also pass case 1.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ga4_pull as G  # noqa: E402

FAILS = []


CHECKS = []


def check(name, got, want):
    CHECKS.append(name)
    ok = got == want
    print("  %-56s %-22s %s" % (name, got, "OK" if ok else "FAIL (want %s)" % (want,)))
    if not ok:
        FAILS.append(name)


def fold(rows):
    agg = {}

    def slot(c):
        return agg.setdefault(c, {"sessions": 0, "quiz_start": 0,
                                  "affiliate_click": 0, "buy_intent_click": 0})

    G.fold_event_rows(rows, slot)
    return agg


def main():
    # 1. the real 28-day rows, in the order GA4 returned them (eventCount desc):
    #    pantip's affiliate row arrives immediately before the (direct) buy_intent row,
    #    so the leaked variable held "pantip" at exactly the wrong moment.
    print("PRODUCTION ORDERING  (the exact shape that mis-filed the file)")
    agg = fold([("pantip", "affiliate_click", 4),
                ("(direct)", "buy_intent_click", 2),
                ("chatgpt.com", "affiliate_click", 2)])
    check("buy_intent lands on direct, not the previous row's pantip",
          agg.get("direct", {}).get("buy_intent_click", 0), 2)
    check("pantip keeps its affiliate clicks", agg["pantip"]["affiliate_click"], 4)
    check("pantip is NOT credited with buy intent", agg["pantip"]["buy_intent_click"], 0)

    # 2. reverse: a fold that always used the CURRENT row would still be wrong if it
    #    ignored the source entirely. Pantip buy-intent must land on pantip.
    print("REVERSE  (a fold hard-wired to one channel must not pass)")
    agg = fold([("(direct)", "affiliate_click", 3),
                ("pantip", "buy_intent_click", 1)])
    check("real pantip buy intent lands on pantip", agg["pantip"]["buy_intent_click"], 1)
    check("direct is not credited with it", agg["direct"].get("buy_intent_click", 0), 0)

    # 3. a buy_intent row arriving FIRST has no previous row to leak from - the case the
    #    old code happened to get right, which is why the bug stayed hidden some days.
    print("ORDERING INDEPENDENCE")
    a = fold([("(direct)", "buy_intent_click", 2), ("pantip", "affiliate_click", 4)])
    b = fold([("pantip", "affiliate_click", 4), ("(direct)", "buy_intent_click", 2)])
    check("same rows, either order, same result", a == b, True)

    # 4. unrelated events must not be counted as either metric
    print("EVENT FILTER")
    agg = fold([("pantip", "page_view", 99), ("pantip", "scroll", 5)])
    check("page_view is not a click", agg.get("pantip", {}).get("affiliate_click", 0), 0)
    check("no phantom channel created", "pantip" in agg, False)

    # 5. channel normalisation still applies (m.facebook -> fb)
    print("NORMALISATION")
    agg = fold([("m.facebook", "buy_intent_click", 1)])
    check("m.facebook folds into fb", agg.get("fb", {}).get("buy_intent_click", 0), 1)

    print("")
    print("%d checks, %d failed" % (len(CHECKS), len(FAILS)))
    if FAILS:
        print("FAILED:", ", ".join(FAILS))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
