#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reverse test for channel_readiness: every verdict must be reachable, and every
guard must be shown to both fire and stay quiet.

A guard only tested in the state it happens to be in today is not tested. Four of
the seven channels are BLOCKED at channels.X.state right now, which means the gate
check, the quota check and the gap check never run against real data - they would
sit there for months looking fine. These cases run them on purpose.
"""
import sys, os, datetime, copy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_readiness as cr

NOW = datetime.datetime(2026, 9, 10, 20, 0, 0).astimezone()
TODAY = "2026-09-10"

BASE_POLICY = {
    "publication_control": {"default_publication_authorized": True},
    "limits": {"posts_per_day": {"default": 2, "pinterest": 5}, "min_gap_hours": 3},
    "gates": [],
    "channels": {},
}
ROLES_OK = {"default": "deny", "actors": {"bot": {"social_publish": True}}}
ROLES_NO = {"default": "deny", "actors": {"bot": {"social_publish": False}}}

results = []


def run(name, expect_verdict, expect_in_why, *, policy=None, roles=None,
        entry=None, actor="bot", ledger=None):
    pol = copy.deepcopy(BASE_POLICY)
    if policy:
        pol.update(copy.deepcopy(policy))
    ent = entry if entry is not None else {"state": "active", "auto": True,
                                           "kind": "text",
                                           "publication_authorized": True}
    pol["channels"]["demo"] = ent
    cr.KNOWN_CHANNELS.clear()
    cr.KNOWN_CHANNELS.update(pol["channels"])

    real = cr.ledger_activity
    if ledger is not None:
        cr.ledger_activity = lambda ch, today: ledger()
    try:
        rows = cr.assess(pol, roles or ROLES_OK, "demo", ent, actor, TODAY, NOW)
    finally:
        cr.ledger_activity = real

    got = rows[0]["verdict"] if rows else "NO ROW"
    why = rows[0]["why"] if rows else ""
    ok = (got == expect_verdict) and (expect_in_why.lower() in why.lower())
    results.append((ok, name, expect_verdict, got, why))


# --- every verdict must be reachable ---------------------------------------
run("clean channel -> READY", "READY", "0/2",
    ledger=lambda: (0, None, set()))

run("permission false -> names the field", "BLOCKED",
    "channels.demo.publication_authorized",
    entry={"state": "active", "auto": True, "kind": "text",
           "publication_authorized": False})

run("permission missing is not permission false, but still fails closed", "BLOCKED",
    "channels.demo.publication_authorized",
    entry={"state": "active", "auto": True, "kind": "text"})

run("global switch off", "BLOCKED", "default_publication_authorized",
    policy={"publication_control": {"default_publication_authorized": False}})

run("publication_control absent -> UNKNOWN, not BLOCKED", "UNKNOWN",
    "cannot tell authorized from unset", policy={"publication_control": None})

run("state paused beats permission true", "BLOCKED", "state = 'paused'",
    entry={"state": "paused", "auto": True, "kind": "text",
           "publication_authorized": True})

run("state absent -> UNKNOWN", "UNKNOWN", "state is absent",
    entry={"auto": True, "kind": "text", "publication_authorized": True})

run("owner-only leg", "BLOCKED", "owner-only",
    entry={"state": "manual", "auto": False, "kind": "video",
           "publication_authorized": True})

run("actor missing from role_capabilities", "BLOCKED",
    "role_capabilities.actors.ghost", actor="ghost", ledger=lambda: (0, None, set()))

run("actor present but social_publish false", "BLOCKED", "social_publish = False",
    roles=ROLES_NO)

# --- the guards that real data never exercises today -------------------------
run("undecided gate blocks", "BLOCKED", "no recorded decision",
    policy={"gates": [{"date": "2026-08-25", "task": "owner review",
                       "decides": ["demo return"]}]},
    ledger=lambda: (0, None, set()))

run("decided gate does not block", "READY", "0/2",
    policy={"gates": [{"date": "2026-08-25", "task": "owner review",
                       "status": "CLOSED", "decides": ["demo return"]}]},
    ledger=lambda: (0, None, set()))

run("future gate does not block", "READY", "0/2",
    policy={"gates": [{"date": "2026-12-01", "task": "later",
                       "decides": ["demo return"]}]},
    ledger=lambda: (0, None, set()))

run("gate about another channel does not block", "READY", "0/2",
    policy={"gates": [{"date": "2026-08-25", "task": "owner review",
                       "decides": ["instagram return"]}]},
    ledger=lambda: (0, None, set()))

run("quota reached", "BLOCKED", "already 2 today",
    ledger=lambda: (2, None, set()))

run("gap too short", "BLOCKED", "min_gap_hours",
    ledger=lambda: (1, NOW - datetime.timedelta(hours=2, minutes=52), set()))

run("gap just wide enough", "READY", "1/2",
    ledger=lambda: (1, NOW - datetime.timedelta(hours=3, minutes=1), set()))

run("unreadable ledger -> UNKNOWN, never READY", "UNKNOWN",
    "cannot be measured",
    ledger=lambda: (_ for _ in ()).throw(cr.Unknown("post-ledger.jsonl unreadable")))

run("stray ledger labels are surfaced, not swallowed", "READY", "undercounted",
    ledger=lambda: (0, None, {"facebok"}))


# --- the substring trap this repo has fallen into nine times -----------------
def gate_match_cases():
    pol = copy.deepcopy(BASE_POLICY)
    pol["gates"] = [
        {"date": "2026-08-25", "decides": ["threads of the conversation"], "task": "x"},
        {"date": "2026-08-25", "decides": ["interest rates article"], "task": "y"},
        {"date": "2026-08-25", "decides": ["pinterest return"], "task": "z"},
    ]
    a = cr.undecided_gates(pol, "pinterest", TODAY)
    b = cr.undecided_gates(pol, "threads", TODAY)
    ok_a = len(a) == 1 and "pinterest return" in a[0][4]
    # 'threads' really does appear as a word in 'threads of the conversation'.
    # A word-boundary match cannot tell those apart - which is exactly why the
    # matched sentence is printed instead of just the word BLOCKED.
    ok_b = len(b) == 1 and "conversation" in b[0][4]
    results.append((ok_a, "pinterest matches its own gate, not 'interest rates'",
                    "1 hit", "%d hit" % len(a), a[0][4] if a else ""))
    results.append((ok_b, "ambiguous word match is reported with its sentence",
                    "sentence shown", "sentence shown" if ok_b else "hidden",
                    b[0][4] if b else ""))


gate_match_cases()

fails = 0
for ok, name, expect, got, why in results:
    fails += 0 if ok else 1
    print("%-4s %-58s expect=%-8s got=%-8s %s"
          % ("PASS" if ok else "FAIL", name, expect, got, why[:70]))
print("\n%d case(s), %d failed" % (len(results), fails))
sys.exit(1 if fails else 0)
