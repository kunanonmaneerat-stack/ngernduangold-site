#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retired Facebook batch-2 scheduler: permanently local-plan-only.

This agent-facing compatibility script may inspect the local manifest and print
the historical 21-26 July plan. It never contacts Facebook, reads credentials,
schedules a post, or writes the manifest. Live flags are rejected before any
project file is opened.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".system_control" / "content_manifest.json"
BASE = "https://ngernduangold.com"
DATES = [
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
    "2026-07-24",
    "2026-07-25",
    "2026-07-26",
]
FORBIDDEN = {"2026-07-20"}  # owner scheduled this manually; retain history only
LIVE_FLAGS = {"--go", "--live", "--publish", "--schedule"}


def unix_19th(date_str: str) -> int:
    year, month, day = map(int, date_str.split("-"))
    ict = datetime.timezone(datetime.timedelta(hours=7))
    dt = datetime.datetime(year, month, day, 19, 0, tzinfo=ict)
    return int(dt.timestamp())


def _live_requested(args: list[str]) -> bool:
    return bool(LIVE_FLAGS.intersection(args)) or os.environ.get("DRY_RUN") == "0"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if _live_requested(args):
        print(
            "BLOCKED: PERMANENTLY LOCAL-ONLY; this retired script cannot "
            "schedule or publish Facebook content."
        )
        return 2
    unknown = [arg for arg in args if arg != "--plan"]
    if unknown:
        print("BLOCKED: unsupported argument(s): %s" % ", ".join(unknown))
        print("usage: python schedule_fb_batch2.py [--plan]")
        return 2

    try:
        with MANIFEST.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print("LOCAL-PLAN FAIL: manifest unavailable or invalid: %s" % exc)
        return 2

    items = manifest.get("items")
    if not isinstance(items, list):
        print("LOCAL-PLAN FAIL: manifest.items is missing or invalid")
        return 2
    by_date = {
        item.get("date"): item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("date"), str)
    }

    if FORBIDDEN.intersection(DATES):
        print("LOCAL-PLAN FAIL: forbidden date found in historical batch")
        return 2

    now_ict = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=7))
    )
    results: list[tuple[str, str]] = []
    failed = False
    for date in DATES:
        item = by_date.get(date)
        if not isinstance(item, dict):
            results.append((date, "FAIL manifest item missing"))
            failed = True
            continue
        captions = item.get("captions") or {}
        caption = captions.get("fb") if isinstance(captions, dict) else None
        if not caption or "ข้อมูลเพื่อการศึกษา" not in caption:
            results.append((date, "FAIL caption/disclaimer missing"))
            failed = True
            continue
        if item.get("affiliate") and "มีลิงก์พันธมิตร" not in caption:
            results.append((date, "FAIL affiliate disclosure missing"))
            failed = True
            continue
        posted = item.get("posted") or {}
        if isinstance(posted, dict) and posted.get("fb"):
            results.append(
                (date, "HISTORY already recorded: %s" % str(posted["fb"])[:60])
            )
            continue
        reel = item.get("reel")
        if not isinstance(reel, str) or not reel:
            results.append((date, "FAIL reel path missing"))
            failed = True
            continue
        if unix_19th(date) <= int(now_ict.timestamp()):
            results.append((date, "HISTORY past date; no back-posting"))
            continue
        results.append(
            (date, "PLAN-ONLY %s at 19:00 ICT" % (BASE + "/" + reel.lstrip("/")))
        )

    print("=== FB batch2 LOCAL PLAN ONLY ===")
    print("No network, no scheduling, no publication, no file writes.")
    for date, result in results:
        print("%s : %s" % (date, result))
    print("2026-07-20 remains hard-excluded and untouched.")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
