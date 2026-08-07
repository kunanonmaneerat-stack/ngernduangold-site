#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_forensics - line up when a task's prompt was last edited against when it
last actually PRODUCED something.

WHY THIS EXISTS (8 Aug 2026). `cowork-task-watchdog` has advanced its lastRunAt
every single morning since 1 Aug and has not written a report on any of those
mornings. lastRunAt is set at dispatch, so it only proves the run STARTED. The
leading theory is that editing a task's prompt invalidates the tool approvals
stored on that task, so the next unattended run stops at a permission prompt that
nobody is there to answer - it does not error, it just never finishes.

That theory is testable: if it is right, tasks whose prompt was edited recently
should stop producing output on the next scheduled run, and tasks whose prompt was
untouched should keep producing. This lines up both columns so the question can be
answered from data instead of argued from plausibility.

It matters beyond one task: five prompts were rewritten on 7-8 Aug. If the theory
holds, all five are now waiting on an approval the owner has to grant once.

USAGE
  python tools/task_forensics.py            # both roots, most recently edited first
  python tools/task_forensics.py --days 10  # only prompts edited in the last N days
"""
import os, sys, io, json, argparse, datetime, re, glob

HOME = os.path.expanduser("~")
ROOTS = [os.path.join(HOME, "Claude", "Scheduled"),
         os.path.join(HOME, ".claude", "scheduled-tasks")]
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNLOG_GLOB = os.path.join(REPO, "automation-log", "20??-??.jsonl")
REPORT_DIRS = [os.path.join(HOME, "Claude", "watchdog-logs"),
               os.path.join(REPO, "automation-log")]


def last_runlog_per_routine():
    """routine -> (ts, status) from log_run.py output."""
    out = {}
    for fn in sorted(glob.glob(RUNLOG_GLOB)):
        try:
            for line in io.open(fn, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if "routine" in e and "ts" in e:
                    out[e["routine"]] = (str(e["ts"]), str(e.get("status", "?")))
        except OSError:
            continue
    return out


def newest_artifact_mentioning(task):
    """Newest file whose NAME contains the task id, across the report dirs.

    Deliberately name-based: a task that produces a file named after itself is the
    only kind of output that can be attributed without guessing.
    """
    best = None
    for d in REPORT_DIRS:
        if not os.path.isdir(d):
            continue
        for root, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for n in names:
                if task in n:
                    p = os.path.join(root, n)
                    try:
                        m = os.path.getmtime(p)
                    except OSError:
                        continue
                    if best is None or m > best[0]:
                        best = (m, p)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None,
                    help="only show prompts edited in the last N days")
    args = ap.parse_args()

    runlogs = last_runlog_per_routine()
    now = datetime.datetime.now()
    rows = []
    # A task can only be judged on its runlog if its prompt actually ORDERS one.
    # The first version of this tool printed "-" for both "stopped logging" and
    # "never logged in its life", which made 30-odd healthy tasks look dead and
    # nearly produced a confident wrong diagnosis. Same class as every other bug in
    # OPERATING-NOTES 31: two different states rendered identically.
    def logs_proof(path):
        try:
            body = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return False
        return "log_run.py" in body
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        label = "cowork" if "Scheduled" in root else "cc"
        for task in sorted(os.listdir(root)):
            skill = os.path.join(root, task, "SKILL.md")
            if not os.path.isfile(skill):
                continue
            edited = datetime.datetime.fromtimestamp(os.path.getmtime(skill))
            if args.days and (now - edited).days > args.days:
                continue
            ts, status = runlogs.get(task, ("-", "-"))
            art = newest_artifact_mentioning(task)
            art_when = (datetime.datetime.fromtimestamp(art[0]).strftime("%m-%d %H:%M")
                        if art else "-")
            rows.append((edited, label, task, ts[:16], status, art_when,
                         logs_proof(skill)))

    rows.sort(reverse=True)
    print("%-16s %-7s %-38s %-17s %-8s %-6s %s"
          % ("prompt edited", "root", "task", "last runlog", "status", "logs?", "newest own artifact"))
    print("-" * 118)
    judgeable, silent_since_edit, never_logs = 0, [], 0
    for edited, label, task, ts, status, art, logs in rows:
        flag = ""
        if not logs:
            never_logs += 1
            ts, status = "(never logs)", "-"
        else:
            judgeable += 1
            if ts != "-":
                try:
                    d = datetime.datetime.fromisoformat(ts).replace(tzinfo=None)
                    if d < edited:
                        flag = "  <<< silent since the prompt was edited"
                        silent_since_edit.append(task)
                except Exception:
                    pass
        print("%-16s %-7s %-38s %-17s %-8s %-6s %s%s"
              % (edited.strftime("%m-%d %H:%M"), label, task[:38], ts, status,
                 "yes" if logs else "no", art, flag))

    print()
    print("%d task(s) shown - %d order a runlog and can be judged, %d never log at all."
          % (len(rows), judgeable, never_logs))
    print("A task that never logs is NOT evidence of failure; it is evidence of missing")
    print("instrumentation. Reading those two the same way is how a healthy system gets")
    print("declared broken. Only the '<<<' lines are actual candidates for investigation.")
    if silent_since_edit:
        print()
        print("silent since their prompt changed (%d): %s"
              % (len(silent_since_edit), ", ".join(sorted(set(silent_since_edit))[:6])))
        print("  -> check these against tasks whose prompt ALSO changed but kept logging.")
        print("     If both groups exist, editing a prompt is not the cause.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
