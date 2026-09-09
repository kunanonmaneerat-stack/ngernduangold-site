#!/usr/bin/env python3
"""Regression checks for the inclusive GA4/GSC reporting window."""
import datetime

import ga4_pull
import gsc_pull


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def main():
    check("GA4 28-day range starts 27 days ago",
          ga4_pull._api_window(28) == ("27daysAgo", "today"))
    ga_start, ga_end = ga4_pull._calendar_window(datetime.date(2026, 8, 16), 28)
    check("GA4 absolute capture window is bound to one date",
          (ga_start, ga_end) == ("2026-07-20", "2026-08-16"))
    start, end = gsc_pull._date_window(datetime.date(2026, 8, 16), 28)
    check("GSC finalized 28-day range ends at D-3",
          (start, end) == ("2026-07-17", "2026-08-13"))
    check("GSC inclusive range contains exactly 28 dates",
          (datetime.date.fromisoformat(end) -
           datetime.date.fromisoformat(start)).days + 1 == 28)
    for helper in (ga4_pull._api_window, ga4_pull._calendar_window,
                   gsc_pull._date_window):
        try:
            helper(days=0)
        except ValueError:
            continue
        raise AssertionError("zero-day range must fail closed")
    try:
        gsc_pull._date_window(datetime.date(2026, 8, 16), 28, -1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative GSC finalization lag must fail closed")
    print("reporting window: 6 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
