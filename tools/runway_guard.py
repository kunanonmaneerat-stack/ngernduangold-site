#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""runway_guard - warn BEFORE the content pipe runs dry.

WHY THIS EXISTS (incident 27-30 Jul 2026):
  batch3 clips were rendered and listed in .system_control/content_manifest.json,
  but were never wired into reels/schedule.json or social-autopost/content_map.json
  (the two files the posting routines actually read). Those two files stopped at
  26 Jul, so every video channel went silent for 4 days. Nothing alerted, because
  every existing guard only checks AFTER a post fails - which is already too late.

  This guard checks the OTHER direction: how many days of content are still queued
  ahead of today, and whether the three sources agree with each other.

ASCII-ONLY SOURCE ON PURPOSE: this repo has a hard rule that scripts which touch
Thai text must not contain Thai literals (encoding corruption). All Thai stays in
the JSON data files and is never printed here.

USAGE
  python tools/runway_guard.py                 # human report, exit 1 if below threshold
  python tools/runway_guard.py --min-days 5    # custom threshold (default 4)
  python tools/runway_guard.py --json          # machine output for heartbeat/dispatcher

EXIT CODES
  0 = healthy      1 = runway below threshold      2 = sources disagree (drift)
"""
import os, sys, json, io, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

MANIFEST = os.path.join(REPO, ".system_control", "content_manifest.json")
SCHEDULE = os.path.join(REPO, "reels", "schedule.json")
CONTENT_MAP = os.path.join(REPO, "social-autopost", "content_map.json")
REELS_DIR = os.path.join(REPO, "reels")

DEFAULT_MIN_DAYS = 4


def _load(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dates_from_manifest(man):
    return sorted(i["date"] for i in man.get("items", []) if i.get("date"))


def collect(today):
    """Return (report_dict, exit_code)."""
    problems = []
    src = {}

    try:
        man = _load(MANIFEST)
        src["manifest"] = _dates_from_manifest(man)
        items = {i["date"]: i for i in man.get("items", []) if i.get("date")}
    except Exception as exc:
        return {"error": "cannot read manifest: %s" % exc}, 2

    for label, path in (("schedule", SCHEDULE), ("content_map", CONTENT_MAP)):
        try:
            src[label] = sorted(_load(path).keys())
        except Exception as exc:
            problems.append("%s unreadable: %s" % (label, exc))
            src[label] = []

    iso = today.isoformat()
    runway = {k: [d for d in v if d >= iso] for k, v in src.items()}
    days = {k: len(v) for k, v in runway.items()}
    last = {k: (v[-1] if v else None) for k, v in src.items()}

    # 1) the three sources must cover the same future days
    future_sets = {k: set(v) for k, v in runway.items()}
    base = future_sets.get("manifest", set())
    for k in ("schedule", "content_map"):
        missing = sorted(base - future_sets.get(k, set()))
        if missing:
            problems.append(
                "%s is missing %d future day(s) that manifest has: %s"
                % (k, len(missing), ", ".join(missing[:5]))
            )

    # 2) every queued day must point at a clip file that exists on disk
    missing_files = []
    try:
        sched = _load(SCHEDULE)
    except Exception:
        sched = {}
    for d in runway.get("schedule", []):
        fname = (sched.get(d) or {}).get("file", "")
        if not fname or not os.path.exists(os.path.join(REELS_DIR, fname)):
            missing_files.append("%s -> %s" % (d, fname or "<no file>"))
    if missing_files:
        problems.append("clip file missing for: " + "; ".join(missing_files[:5]))

    # 3) queued days must not be stuck in a pre-render status
    NOT_READY = {"Idea", "Draft", "Approved"}
    stuck = [d for d in runway.get("manifest", [])
             if items.get(d, {}).get("status") in NOT_READY]
    if stuck:
        problems.append("queued day(s) not rendered yet: " + ", ".join(stuck[:5]))

    effective = min(days.get("schedule", 0), days.get("content_map", 0))

    report = {
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "today": iso,
        "runway_days": days,
        "effective_runway_days": effective,
        "last_queued_day": last,
        "problems": problems,
    }

    if problems:
        return report, 2
    return report, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-days", type=int, default=DEFAULT_MIN_DAYS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", default=None, help="override date (YYYY-MM-DD), for tests")
    args = ap.parse_args()

    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.date.today())
    report, code = collect(today)

    if report.get("error"):
        print("runway_guard: ERROR %s" % report["error"])
        return 2

    eff = report["effective_runway_days"]
    if code == 0 and eff < args.min_days:
        code = 1

    report["threshold_days"] = args.min_days
    report["verdict"] = {0: "OK", 1: "LOW_RUNWAY", 2: "DRIFT"}[code]

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return code

    print("runway_guard [%s]  today=%s" % (report["verdict"], report["today"]))
    print("  days of content still queued ahead:")
    for k in ("manifest", "schedule", "content_map"):
        print("    %-12s %2d day(s)   last queued: %s"
              % (k, report["runway_days"].get(k, 0), report["last_queued_day"].get(k)))
    print("  effective runway = %d day(s)  (threshold %d)" % (eff, args.min_days))
    if report["problems"]:
        print("  PROBLEMS:")
        for p in report["problems"]:
            print("   - %s" % p)
    if code == 1:
        print("  ACTION: queue is running out. Render/wire the next batch now,")
        print("          or re-date unposted clips before the channels go silent.")
    if code == 2:
        print("  ACTION: sources disagree. A clip exists somewhere but the posting")
        print("          routines cannot see it. Fix before the next 19:00 slot.")
    return code


if __name__ == "__main__":
    sys.exit(main())
