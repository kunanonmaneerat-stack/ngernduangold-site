#!/usr/bin/env python3
"""Postiz article plan renderer: permanently local-plan-only.

This agent-facing compatibility script reads a local article plan and prints
future slots. It never reads an API key, discovers integrations, contacts
Postiz, schedules a post, or writes project files. ``--go`` and other live
mutation flags are rejected before the plan file is opened.

Usage:
    py pipeline/postiz_article_scheduler.py
    py pipeline/postiz_article_scheduler.py --file pipeline/article-posts.json
    py pipeline/postiz_article_scheduler.py --channel threads --per-day 1 --hour 19
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "pipeline" / "article-posts.json"
ICT = datetime.timezone(datetime.timedelta(hours=7))
LIVE_FLAGS = {"--go", "--live", "--publish", "--schedule"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a local Postiz article plan without network or mutation."
    )
    parser.add_argument("--file", default=str(CFG))
    parser.add_argument("--channel")
    parser.add_argument("--per-day", type=int)
    parser.add_argument("--hour", type=int)
    parser.add_argument("--plan", action="store_true")
    return parser


def _load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError("root must be a JSON object")
    return value


def _build_dates(post_count: int, per_day: int, hour: int) -> list[datetime.datetime]:
    start = (datetime.datetime.now(ICT) + datetime.timedelta(days=1)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    dates = []
    for index in range(post_count):
        slot_hour = hour + (index % per_day) * 2
        if slot_hour > 23:
            raise ValueError("daily slots exceed 23:00 ICT")
        dates.append(
            (start + datetime.timedelta(days=index // per_day)).replace(hour=slot_hour)
        )
    return dates


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if LIVE_FLAGS.intersection(raw_args):
        print(
            "BLOCKED: PERMANENTLY LOCAL-ONLY; this script cannot contact "
            "Postiz, schedule, or publish."
        )
        return 2

    try:
        args = _parser().parse_args(raw_args)
    except SystemExit as exc:
        return int(exc.code or 0)

    cfg_path = Path(args.file)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    try:
        cfg = _load_config(cfg_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("LOCAL-PLAN FAIL: config unavailable or invalid: %s" % exc)
        return 2

    channel = args.channel or cfg.get("channel", "threads")
    per_day = args.per_day if args.per_day is not None else cfg.get("per_day", 1)
    hour = args.hour if args.hour is not None else cfg.get("hour_ict", 19)
    posts = cfg.get("posts")
    if not isinstance(channel, str) or not channel.strip():
        print("LOCAL-PLAN FAIL: channel must be a non-empty string")
        return 2
    if not isinstance(posts, list):
        print("LOCAL-PLAN FAIL: posts must be a list")
        return 2
    try:
        per_day = int(per_day)
        hour = int(hour)
    except (TypeError, ValueError):
        print("LOCAL-PLAN FAIL: per_day and hour must be integers")
        return 2
    if per_day < 1:
        print("LOCAL-PLAN FAIL: per_day must be at least 1")
        return 2
    if hour < 0 or hour > 23:
        print("LOCAL-PLAN FAIL: hour must be between 0 and 23")
        return 2
    for index, post in enumerate(posts, start=1):
        if not isinstance(post, dict) or not str(post.get("topic") or "").strip():
            print("LOCAL-PLAN FAIL: post %d has no topic" % index)
            return 2

    try:
        dates = _build_dates(len(posts), per_day, hour)
    except ValueError as exc:
        print("LOCAL-PLAN FAIL: %s" % exc)
        return 2

    print("=== Postiz article LOCAL PLAN ONLY ===")
    print("No network, no integration lookup, no scheduling, no publication, no writes.")
    print(
        "channel=%s · per_day=%d · hour=%02d:00 ICT · posts=%d"
        % (channel, per_day, hour, len(posts))
    )
    print("\n--- local plan ---")
    for index, post in enumerate(posts):
        print(
            "%2d. %s · %s"
            % (index + 1, dates[index].strftime("%a %d/%m %H:%M ICT"), post["topic"])
        )
    print("\nLOCAL-PLAN COMPLETE: no external state changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
