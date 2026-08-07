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
  0 = healthy (OK) or approved pause (PARKED)
  1 = runway below threshold (LOW_RUNWAY), or an approved pause that has
      expired with the queue still short (PARK_OVERRUN - report this loudly)
  2 = sources disagree (DRIFT), or the park declaration itself is unusable

VERDICTS
  OK · PARKED · LOW_RUNWAY · PARK_OVERRUN · DRIFT
  See the PLANNED PARK block below for why an empty queue is not always a fault.
"""
import os, sys, json, io, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

MANIFEST = os.path.join(REPO, ".system_control", "content_manifest.json")
SCHEDULE = os.path.join(REPO, "reels", "schedule.json")
CONTENT_MAP = os.path.join(REPO, "social-autopost", "content_map.json")
REELS_DIR = os.path.join(REPO, "reels")
POLICY = os.path.join(REPO, ".system_control", "policy.json")

DEFAULT_MIN_DAYS = 4


# --------------------------------------------------------------------------
# PLANNED PARK (added 7 Aug 2026)
#
# An empty queue is not always a failure. On 6 Aug the batch3 gate deliberately
# parked video production for 9-10 Aug to wait for the 10 Aug decision, rather
# than render clips that might be thrown away. Before this block, that planned
# pause looked identical to the 27-30 Jul incident where the pipe silently broke.
#
# Two failure modes are possible here and BOTH must be avoided:
#   crying wolf  - screaming LOW_RUNWAY every day of an approved pause, which
#                  trains the owner to ignore this guard exactly when it matters
#   sleeping     - a park with no end date, or an end date nobody enforces,
#                  hides a genuinely dead pipe forever
#
# So a park is only honoured while it is unexpired. The moment `until` passes
# with the queue still short, the verdict becomes PARK_OVERRUN and is LOUDER
# than a plain low runway: the plan itself has now failed, not just the queue.
# A park with a missing or unparseable `until` is refused outright - that is the
# same "permanent rule written as a fixed date" bug class OPERATING-NOTES warns
# about, just inverted into a permanent excuse.
#
# A park NEVER suppresses DRIFT (exit 2). Sources disagreeing means a clip
# exists that the posting routines cannot see - that is broken plumbing, and
# no scheduling decision makes it acceptable.
# --------------------------------------------------------------------------
def read_park(today, policy_path=None):
    """-> (park_dict_or_None, note_or_None).

    park_dict is returned only when today falls inside a well-formed window.
    note carries a problem string when the park declaration itself is unusable.
    """
    path = policy_path or POLICY
    try:
        with io.open(path, encoding="utf-8") as fh:
            pol = json.load(fh)
    except Exception:
        return None, None  # no policy = no park, not an error

    park = (pol.get("content_supply") or {}).get("planned_park")
    if not isinstance(park, dict):
        return None, None

    raw_until = park.get("until")
    try:
        until = datetime.date.fromisoformat(raw_until)
    except Exception:
        return None, ("planned_park has no usable 'until' (%r) - refusing to honour "
                      "an open-ended pause" % (raw_until,))

    try:
        start = datetime.date.fromisoformat(park.get("from"))
    except Exception:
        start = None  # a park with only an end date still expires, so allow it

    if start and today < start:
        return None, None            # park has not begun
    if today > until:
        return None, "EXPIRED:%s" % until.isoformat()
    return dict(park, _until=until.isoformat()), None


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

    # A planned park can downgrade a low runway, but never a drift, and never
    # once it has expired. See the PLANNED PARK block above.
    park, park_note = read_park(today)
    parked = False
    if park_note and park_note.startswith("EXPIRED:"):
        if code == 1:
            code = 1
            report["problems"].append(
                "planned park ended %s and the queue is still short - the plan "
                "failed, not just the queue" % park_note.split(":", 1)[1])
            report["park_overrun"] = True
    elif park_note:
        report["problems"].append(park_note)
        if code == 0:
            code = 2
    elif park and code == 1:
        parked = True
        report["park"] = {"until": park["_until"],
                          "reason": park.get("reason"),
                          "decided_by": park.get("decided_by")}
        code = 0

    report["threshold_days"] = args.min_days
    if parked:
        report["verdict"] = "PARKED"
    elif report.get("park_overrun"):
        report["verdict"] = "PARK_OVERRUN"
    else:
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
    if parked:
        p = report["park"]
        print("  PARKED until %s by decision: %s" % (p["until"], p.get("decided_by")))
        print("    reason: %s" % p.get("reason"))
        print("  This is an approved pause, not a broken pipe. It stops being")
        print("  approved at %s - after that this guard goes loud." % p["until"])
    if report.get("park_overrun"):
        print("  ACTION (LOUD): the approved pause has EXPIRED and nothing was queued.")
        print("          Whatever the pause was waiting for either did not happen or")
        print("          did not produce content. Escalate to the owner, do not extend")
        print("          the park silently.")
    elif code == 1:
        print("  ACTION: queue is running out. Render/wire the next batch now,")
        print("          or re-date unposted clips before the channels go silent.")
    if code == 2:
        print("  ACTION: sources disagree. A clip exists somewhere but the posting")
        print("          routines cannot see it. Fix before the next 19:00 slot.")
    return code


if __name__ == "__main__":
    sys.exit(main())
