#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reverse tests for the planned-park logic in runway_guard.

A guard that only proves it can stay quiet is useless: every guard here must
demonstrate BOTH that it fires when it should and that it stays quiet when it
should. The park feature is the highest-risk kind of code in this repo - it is
an excuse generator - so it gets tested from both directions.
"""
import os, sys, io, json, datetime, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runway_guard as RG

FAIL = []
def check(name, got, want):
    if got != want:
        FAIL.append("%s: got %r want %r" % (name, got, want))

def policy_file(park):
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
    io.open(path, "w", encoding="utf-8").write(
        json.dumps({"content_supply": {"planned_park": park}} if park is not None else {}))
    return path

D = datetime.date.fromisoformat

# --- inside the window: park is honoured -----------------------------------
p = policy_file({"from": "2026-08-09", "until": "2026-08-10", "reason": "gate"})
park, note = RG.read_park(D("2026-08-09"), p)
check("inside-start  park", bool(park), True)
check("inside-start  note", note, None)
park, note = RG.read_park(D("2026-08-10"), p)
check("inside-end    park", bool(park), True)   # `until` is inclusive
check("inside-end    note", note, None)

# --- before it begins: not yet a park --------------------------------------
park, note = RG.read_park(D("2026-08-08"), p)
check("before-start  park", park, None)
check("before-start  note", note, None)

# --- after it ends: MUST expire, this is the whole safety property ----------
park, note = RG.read_park(D("2026-08-11"), p)
check("after-end     park", park, None)
check("after-end     note", note, "EXPIRED:2026-08-10")
park, note = RG.read_park(D("2026-12-31"), p)
check("long-after    note", note, "EXPIRED:2026-08-10")
os.unlink(p)

# --- open-ended park is refused, not honoured ------------------------------
for bad in ({"from": "2026-08-09"},
            {"from": "2026-08-09", "until": None},
            {"from": "2026-08-09", "until": "forever"},
            {"from": "2026-08-09", "until": "2026-13-01"}):
    p = policy_file(bad)
    park, note = RG.read_park(D("2026-08-09"), p)
    check("open-ended %r park" % (bad.get("until"),), park, None)
    check("open-ended %r note" % (bad.get("until"),), bool(note and "refusing" in note), True)
    os.unlink(p)

# --- a park with only an end date still expires ----------------------------
p = policy_file({"until": "2026-08-10"})
check("no-from inside", bool(RG.read_park(D("2026-08-09"), p)[0]), True)
check("no-from expired", RG.read_park(D("2026-08-11"), p)[1], "EXPIRED:2026-08-10")
os.unlink(p)

# --- no park declared / no policy file at all: silent, not an error --------
p = policy_file(None)
check("no-park       park", RG.read_park(D("2026-08-09"), p)[0], None)
check("no-park       note", RG.read_park(D("2026-08-09"), p)[1], None)
os.unlink(p)
check("missing-file  park", RG.read_park(D("2026-08-09"), "/nonexistent/x.json")[0], None)
check("missing-file  note", RG.read_park(D("2026-08-09"), "/nonexistent/x.json")[1], None)

# --- a non-dict park is ignored, not crashed on ----------------------------
for junk in ("yes", 1, [], True):
    p = policy_file(junk)
    check("junk %r" % (junk,), RG.read_park(D("2026-08-09"), p), (None, None))
    os.unlink(p)

# --- the live policy file must declare a park that is still in the future ---
live, note = RG.read_park(datetime.date.today())
if note and note.startswith("EXPIRED:"):
    print("NOTE: the live planned_park expired on %s - runway_guard will now go "
          "loud if the queue is short. That is intended." % note.split(":", 1)[1])

print("test_runway_park: %d check(s) failed" % len(FAIL))
for f in FAIL:
    print("  FAIL " + f)
sys.exit(1 if FAIL else 0)
