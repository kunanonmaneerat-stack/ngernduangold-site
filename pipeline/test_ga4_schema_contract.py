#!/usr/bin/env python3
"""Regression tests for the GA4 CSV field contract.  No network or file writes."""
import csv
import io

from ga4_schema import (
    PILOT_MEASUREMENT_FIELDS,
    affiliate_click,
    canonical_pilot_dimension,
    metric_int,
    pilot_table_errors,
)


def main():
    cases = [
        ("canonical", {"affiliate_click": "6"}, 6),
        ("legacy", {"conversion": "4"}, 4),
        ("canonical wins", {"affiliate_click": "2", "conversion": "99"}, 2),
        ("float text", {"affiliate_click": "3.0"}, 3),
        ("missing", {"sessions": "10"}, 0),
        ("invalid", {"affiliate_click": "n/a", "conversion": "7"}, 0),
    ]
    failed = []
    for name, row, want in cases:
        got = affiliate_click(row)
        print("%s: got=%s want=%s" % (name, got, want))
        if got != want:
            failed.append(name)

    current = list(csv.DictReader(io.StringIO(
        "source,sessions,quiz_start,affiliate_click,buy_intent_click\n"
        "pantip,14,0,4,0\nchatgpt,12,0,2,0\n"
    )))
    if sum(affiliate_click(row) for row in current) != 6:
        failed.append("current csv integration")
    if metric_int({"views": "13"}, "views") != 13:
        failed.append("generic metric")

    valid_pilot = {
        "provider": "ktccard",
        "cta_id": "salary30000-ktc-lower",
        "position": "after-faq",
        "content_id": "salary30k-2026",
        "acquisition_content_id": "unattributed",
        "sub_id": "website_salary30k-lower_ktccard",
        "channel": "website",
        "campaign": "ktccard",
        "affiliate_click_sessions": "2",
        "qualified_landing_sessions": "5",
        "measurement_scope": "session",
    }
    if pilot_table_errors(
        [valid_pilot], PILOT_MEASUREMENT_FIELDS["field_order"]
    ):
        failed.append("valid pilot session row")
    impossible = dict(valid_pilot, affiliate_click_sessions="6")
    if not any("exceeds" in error for error in pilot_table_errors([impossible])):
        failed.append("impossible pilot ratio")
    duplicate = pilot_table_errors([valid_pilot, dict(valid_pilot)])
    if not any("duplicate" in error for error in duplicate):
        failed.append("duplicate pilot dimensions")
    try:
        canonical_pilot_dimension("Social Card", "acquisition_content_id")
    except ValueError:
        pass
    else:
        failed.append("noncanonical pilot dimension")
    if canonical_pilot_dimension("(not set)", "acquisition_content_id") != "unattributed":
        failed.append("unattributed pilot sentinel")

    print("%d checks, %d failed" % (len(cases) + 7, len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
