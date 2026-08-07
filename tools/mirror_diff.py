#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mirror_diff - show exactly HOW a task id differs between the two task roots.

preflight's `task mirror` check can only say "these two disagree". That is enough
to notice a problem and useless for fixing one, so every time it fires someone has
to hand-roll a diff - and on Windows that means fighting PowerShell quoting first.
This makes the follow-up one command.

WHY TWO ROOTS EXIST AT ALL: the Cowork agent and Claude Code each own a scheduler
directory. A task that both may run must mean the same thing in both, or the two
agents quietly execute different orders under one name (OPERATING-NOTES 29).

USAGE
  python tools/mirror_diff.py                 # every id that differs
  python tools/mirror_diff.py <task-id>       # full diff for one id

EXIT CODES
  0 = the two roots agree      1 = at least one id differs
"""
import os, sys, io, difflib

COWORK = os.path.expanduser(os.path.join("~", "Claude", "Scheduled"))
CC = os.path.expanduser(os.path.join("~", ".claude", "scheduled-tasks"))


def read(root, tid):
    p = os.path.join(root, tid, "SKILL.md")
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def ids(root):
    if not os.path.isdir(root):
        return set()
    return {d for d in os.listdir(root)
            if os.path.exists(os.path.join(root, d, "SKILL.md"))}


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else None
    shared = sorted(ids(COWORK) & ids(CC))
    if want:
        shared = [t for t in shared if t == want] or [want]

    differing = []
    for tid in shared:
        a, b = read(CC, tid), read(COWORK, tid)
        if a is None or b is None:
            print("%-42s only in %s" % (tid, "cowork" if a is None else "cc"))
            differing.append(tid)
            continue
        if a == b:
            if want:
                print("%s: identical in both roots" % tid)
            continue
        differing.append(tid)
        al, bl = a.splitlines(), b.splitlines()
        d = list(difflib.unified_diff(al, bl, "cc-root/" + tid, "cowork-root/" + tid,
                                      lineterm="", n=1))
        print("=" * 70)
        print("%s  cc=%d lines  cowork=%d lines  (%d diff lines)"
              % (tid, len(al), len(bl), len(d)))
        print("=" * 70)
        limit = len(d) if want else 40
        for line in d[:limit]:
            try:
                print(line)
            except UnicodeEncodeError:
                print(line.encode("utf-8", "replace").decode("utf-8", "replace"))
        if len(d) > limit:
            print("... %d more diff lines - rerun with the id to see all" % (len(d) - limit))

    if not differing:
        print("mirror_diff: the two roots agree on all %d shared id(s)" % len(shared))
        return 0
    print("\nmirror_diff: %d id(s) differ: %s" % (len(differing), ", ".join(differing)))
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
