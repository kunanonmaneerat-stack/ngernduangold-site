#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unit test: post_guard TikTok/Threads status must always be actionable (order 30 Jul, task 2).

Run: python tools/test_post_guard_status.py   -> exit 0 all pass, exit 1 fail.  Uses a temp ledger.

Why this file exists
--------------------
Both channels used to answer UNKNOWN forever: TikTok because logged-out profile scraping
stopped returning rehydration JSON, Threads because its HTML is client-rendered.  An UNKNOWN
verdict tells nobody what to do, so the daily guard was effectively blind on 2 of 5 channels.
Worse, on 30 Jul the guard counted a `type=failure` row as proof of success (fixed in e85fa55).

The rule under test: every outcome maps to an action.
    OK          downstream confirmed
    SOURCE-SIDE we recorded/scheduled it; platform check impossible -> eyeball later
    FAILED      the ledger says the attempt failed -> fix the pipeline, repost
    NOT-POSTED  no evidence anywhere -> it did not go out, post it
The reverse test (OPERATING-NOTES rule 11: a guard that always passes may be blind) is the
`failure`/`missing` cases below -- they must NOT come back green.
"""
import io
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post_guard as PG  # noqa: E402

TARGET = date(2026, 7, 30)
FAILS: list[str] = []


def check(name: str, got: str, want: str) -> None:
    ok = got == want
    print("  %-52s %-12s %s" % (name, got, "OK" if ok else "FAIL (want %s)" % want))
    if not ok:
        FAILS.append(name)


def write_ledger(rows: list[dict]) -> None:
    path = PG.AUTOMATION_LOG / "post-ledger.jsonl"
    with io.open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def row(kind: str, channel: str, text: str = "x", day: str = "2026-07-30T19:00:00+07:00") -> dict:
    return {"type": kind, "channel": channel, "text_first80": text, "ts": day, "source": "unittest"}


ITEM_WITH_CAPTIONS = {
    "date": "2026-07-30",
    "captions": {"tiktok": "แคปชันทดสอบ tiktok", "threads": "แคปชันทดสอบ threads"},
    "posted": {"tiktok": None, "threads": None},
}
ITEM_MANIFEST_SCHEDULED = {
    "date": "2026-07-30",
    "captions": {"tiktok": "แคปชันทดสอบ tiktok", "threads": "แคปชันทดสอบ threads"},
    "posted": {"tiktok": "scheduled-ui 19:00 (cowork)", "threads": None},
}


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="guard_status_"))
    real_log = PG.AUTOMATION_LOG
    PG.AUTOMATION_LOG = tmpdir
    # never touch the network in a unit test: pretend the public profile is unreachable,
    # which is exactly the production condition these statuses were written for.
    real_page = PG.public_profile_page
    PG.public_profile_page = lambda url: (None, "TestOffline")
    try:
        print("THREADS (ledger is the source of truth — we post it ourselves)")
        write_ledger([row("video", "threads")])
        check("posted: video row on the day", PG.check_threads(TARGET, ITEM_WITH_CAPTIONS)["status"], "OK")

        write_ledger([row("failure", "threads", "NOT POSTED - extension unreachable")])
        check("failed: failure row must NOT read green", PG.check_threads(TARGET, ITEM_WITH_CAPTIONS)["status"], "FAILED")

        write_ledger([])
        check("missing: no row at all", PG.check_threads(TARGET, ITEM_WITH_CAPTIONS)["status"], "NOT-POSTED")

        write_ledger([row("text", "threads", "knowledge-post เที่ยง", "2026-07-30T12:42:00+07:00")])
        check("noon text post is not the daily clip", PG.check_threads(TARGET, ITEM_WITH_CAPTIONS)["status"], "NOT-POSTED")

        write_ledger([row("failure", "threads", "attempt 1 failed", "2026-07-30T19:11:00+07:00"),
                      row("video", "threads", "retry worked", "2026-07-30T19:40:00+07:00")])
        check("retry after failure wins", PG.check_threads(TARGET, ITEM_WITH_CAPTIONS)["status"], "OK")

        print("TIKTOK (downstream unverifiable — report from the source side)")
        checked = PG.now_bangkok().replace(year=2026, month=7, day=30, hour=21, minute=30)
        write_ledger([row("video", "tiktok")])
        check("posted: ledger video row", PG.check_tiktok(TARGET, ITEM_WITH_CAPTIONS, checked)["status"], "SOURCE-SIDE")

        write_ledger([])
        check("manifest scheduled, no ledger", PG.check_tiktok(TARGET, ITEM_MANIFEST_SCHEDULED, checked)["status"], "SOURCE-SIDE")

        write_ledger([row("failure", "tiktok", "upload rejected")])
        check("failed: failure row", PG.check_tiktok(TARGET, ITEM_WITH_CAPTIONS, checked)["status"], "FAILED")

        write_ledger([])
        check("missing: nothing anywhere", PG.check_tiktok(TARGET, ITEM_WITH_CAPTIONS, checked)["status"], "NOT-POSTED")

        print("INVARIANT")
        write_ledger([])
        for name, verdict in (("threads", PG.check_threads(TARGET, ITEM_WITH_CAPTIONS)),
                              ("tiktok", PG.check_tiktok(TARGET, ITEM_WITH_CAPTIONS, checked))):
            check("%s never returns UNKNOWN" % name, "UNKNOWN" if verdict["status"] == "UNKNOWN" else "actionable", "actionable")
            check("%s carries an action" % name, "yes" if verdict.get("action", "-") != "-" else "no", "yes")
    finally:
        PG.AUTOMATION_LOG = real_log
        PG.public_profile_page = real_page
        for leftover in tmpdir.glob("*"):
            leftover.unlink()
        tmpdir.rmdir()

    print("\n%d checks, %d failed" % (13, len(FAILS)))
    if FAILS:
        print("FAILED:", ", ".join(FAILS))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
