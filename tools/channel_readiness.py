#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""channel_readiness - can we post to channel X today, and if not, WHICH FIELD says no.

WHY THIS EXISTS: on 9 Sep 2026 the owner set publication_authorized=true on all
seven channels. Reading policy.json after that, every channel looks open. Four of
them are not: tiktok is testing_blocked, instagram and pinterest are paused with a
25 Aug review gate that has no recorded decision, pantip is limited under a final
warning. The permission field and the state field disagree, and nothing in the repo
answered "so can we post or not" without a human reading five files and holding the
whole policy in their head. That is how 65 placements ended up PLANNED_BLOCKED with
nobody able to say which of them could ever move.

WHAT THIS IS NOT: this does not authorize anything. tools/publication_authority.py
authorize_live_publication() is the only thing that lets a post out, and it demands
receipts, calendar slots and media QA evidence that do not exist at planning time.
READY here means "planning is not wasting its time on this leg today". It never
means "go".

THREE VERDICTS, and the third one is the point:
  READY    - every field checked says yes
  BLOCKED  - a field says no. The field path is always named. "blocked" with no
             field name is how a reader learns to stop reading the check.
  UNKNOWN  - could not be read. NEVER collapse this into BLOCKED. On 6 Aug a gate
             nearly reported "did not pass" for a test that was never run.

USAGE
  python tools/channel_readiness.py                  # all channels, actor=grok
  python tools/channel_readiness.py --actor cowork
  python tools/channel_readiness.py --channel threads --date 2026-09-10
  python tools/channel_readiness.py --json

EXIT CODES
  0 = at least one leg READY   1 = nothing READY   2 = could not read policy at all
"""
import os, sys, io, json, argparse, datetime, re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join(REPO, ".system_control", "policy.json")
ROLES = os.path.join(REPO, ".system_control", "role_capabilities.json")
LEDGER = os.path.join(REPO, "automation-log", "post-ledger.jsonl")

# Which channel.state values allow a post to be planned at all.
# Read off the policy _readme and the channel entries, not invented here:
#   active         - normal operation
#   manual         - the channel works but a leg may be owner-only (see auto_legs)
# Everything else (paused, testing_blocked, limited) is a stop with its own reason
# recorded in the channel entry.
PLANNABLE_STATES = {"active", "manual"}

# Ledger channel labels are not clean. Counting only "facebook" misses rows written
# as "fb", which would UNDERCOUNT the daily quota - and undercounting a quota fails
# in the dangerous direction (it lets an extra post through). Aliases fold in; a
# genuinely different surface gets its own bucket and does NOT fold in.
ALIASES = {
    "fb": "facebook",          # same page, sloppy label
    "yt": "youtube",           # same channel, sloppy label
}
SEPARATE_SURFACES = {
    "facebook-page2",          # a different page - its own quota
    "fb-group",                # groups are not the page feed
    "system",                  # bookkeeping rows, not posts
    # Not social channels at all. Listed explicitly rather than left to fall into
    # the stray warning: a warning that fires on things that are fine is how a
    # reader learns to skim the line that will one day say something real.
    "line", "line-oa", "gumroad",
}
COUNTS_AS_A_POST = {"text", "video", "image", "comment", "story"}
TIME_FIELDS = ("posted_at", "published_at", "ts")


class Unknown(Exception):
    """Raised when a fact cannot be read. Kept distinct from 'the fact says no'."""


def _load(path, label):
    try:
        return json.loads(io.open(path, encoding="utf-8").read())
    except FileNotFoundError:
        raise Unknown("%s not found at %s" % (label, os.path.relpath(path, REPO)))
    except Exception as exc:
        raise Unknown("%s could not be parsed: %s" % (label, exc))


def _parse_ts(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def undecided_gates(policy, channel, today):
    """Gates whose date has arrived, that decide this channel, with no decision recorded.

    This matches the channel name inside free text ("instagram return"), which is
    the substring-match pattern that has bitten this repo nine times. Two guards:
    a word-boundary match, and the matched sentence is printed so a human can see
    what it matched on instead of trusting the word 'blocked'.
    """
    hits = []
    pattern = re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(channel), re.I)
    for i, gate in enumerate(policy.get("gates", []) or []):
        if not isinstance(gate, dict):
            continue
        date = gate.get("date")
        if not isinstance(date, str) or date > today:
            continue
        decides = gate.get("decides") or []
        matched = [d for d in decides if isinstance(d, str) and pattern.search(d)]
        if not matched:
            continue
        status = str(gate.get("status", "")).upper()
        if status in ("CLOSED", "DECIDED", "DONE", "PASSED"):
            continue
        hits.append((i, date, gate.get("task", "?"), status or "no status field", matched[0]))
    return hits


def ledger_activity(channel, today):
    """-> (posts_today, last_post_dt, unknown_labels). Raises Unknown if unreadable."""
    if not os.path.exists(LEDGER):
        raise Unknown("post-ledger.jsonl not found - quota and gap cannot be measured")
    posts_today, last, strays = 0, None, set()
    try:
        lines = io.open(LEDGER, encoding="utf-8").read().splitlines()
    except Exception as exc:
        raise Unknown("post-ledger.jsonl unreadable: %s" % exc)
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            raise Unknown("post-ledger.jsonl line %d is not JSON - refusing to "
                          "report a quota from a file I cannot fully read" % n)
        raw = row.get("channel")
        if not isinstance(raw, str):
            continue
        if raw in SEPARATE_SURFACES:
            continue
        name = ALIASES.get(raw, raw)
        if name != channel:
            if name not in KNOWN_CHANNELS and raw not in SEPARATE_SURFACES:
                strays.add(raw)
            continue
        if row.get("type") not in COUNTS_AS_A_POST:
            continue
        if str(row.get("status", "posted")).lower() in ("failed", "skipped"):
            continue
        dt = None
        for f in TIME_FIELDS:
            dt = _parse_ts(row.get(f))
            if dt:
                break
        if dt is None:
            continue
        if dt.date().isoformat() == today:
            posts_today += 1
        if last is None or dt > last:
            last = dt
    return posts_today, last, strays


KNOWN_CHANNELS = set()


def legs_for(entry):
    """Which post types this channel can carry, and whether each is automatable.

    facebook is the reason this is per-leg: state=manual and auto=false describe the
    VIDEO slot only - auto_legs says text and comment are automated. Reporting one
    verdict for the whole channel would call facebook blocked while the text leg
    posts daily, or call it open while the reel leg is owner-only.
    """
    kind = entry.get("kind") or "post"
    auto = entry.get("auto")
    auto_legs = entry.get("auto_legs") or []
    legs = []
    legs.append((kind, bool(auto)))
    for leg in auto_legs:
        if leg != kind:
            legs.append((leg, True))
    return legs


def assess(policy, roles, channel, entry, actor, today, now):
    """-> list of dict(leg, verdict, why). One row per leg."""
    out = []
    pc = policy.get("publication_control")
    limits = policy.get("limits") or {}
    per_day = (limits.get("posts_per_day") or {})
    cap = per_day.get(channel, per_day.get("default"))
    min_gap = limits.get("min_gap_hours")

    def row(leg, verdict, why):
        out.append({"channel": channel, "leg": leg, "verdict": verdict, "why": why})

    for leg, automatable in legs_for(entry):
        # 1. the permission field itself
        if not isinstance(pc, dict):
            row(leg, "UNKNOWN", "publication_control missing from policy.json - "
                                "cannot tell authorized from unset")
            continue
        if pc.get("default_publication_authorized") is not True:
            row(leg, "BLOCKED", "publication_control.default_publication_authorized "
                                "is not true (authority_rule: missing or false fails closed)")
            continue
        if entry.get("publication_authorized") is not True:
            row(leg, "BLOCKED", "channels.%s.publication_authorized = %r" %
                (channel, entry.get("publication_authorized")))
            continue

        # 2. channel state - the field the 9 Sep lift did NOT touch
        state = entry.get("state")
        if state is None:
            row(leg, "UNKNOWN", "channels.%s.state is absent" % channel)
            continue
        if state not in PLANNABLE_STATES:
            row(leg, "BLOCKED", "channels.%s.state = %r (permission is true; the "
                                "state is what stops it)" % (channel, state))
            continue

        # 3. is this leg automatable at all
        if not automatable:
            row(leg, "BLOCKED", "channels.%s leg %r is owner-only (auto=false and not "
                                "in auto_legs) - a bot cannot take this leg" % (channel, leg))
            continue

        # 4. dated gates that decide this channel and recorded no decision
        gates = undecided_gates(policy, channel, today)
        if gates:
            i, date, task, status, matched = gates[0]
            row(leg, "BLOCKED", "gates[%d] %s %r has no recorded decision (%s) and "
                                "decides %r - a date passing is not a decision"
                % (i, date, task, status, matched))
            continue

        # 5. actor capability
        actors = (roles or {}).get("actors") or {}
        if actor not in actors:
            row(leg, "BLOCKED", "role_capabilities.actors.%s does not exist and "
                                "default = %r" % (actor, (roles or {}).get("default")))
            continue
        if actors[actor].get("social_publish") is not True:
            row(leg, "BLOCKED", "role_capabilities.actors.%s.social_publish = %r"
                % (actor, actors[actor].get("social_publish")))
            continue

        # 6. anti-spam ceiling, measured from what actually happened
        try:
            posts_today, last, strays = ledger_activity(channel, today)
        except Unknown as exc:
            row(leg, "UNKNOWN", "%s - a ceiling that cannot be measured is not a "
                                "ceiling, so this is not READY either" % exc)
            continue
        if cap is None:
            row(leg, "UNKNOWN", "limits.posts_per_day has no cap for %s and no default"
                % channel)
            continue
        if posts_today >= cap:
            row(leg, "BLOCKED", "limits.posts_per_day = %d, already %d today in the "
                                "ledger" % (cap, posts_today))
            continue
        if min_gap and last is not None:
            gap = (now - last).total_seconds() / 3600.0
            if gap < min_gap:
                row(leg, "BLOCKED", "limits.min_gap_hours = %s, last real post was "
                                    "%.2f h ago (measured from the ledger, not the "
                                    "schedule)" % (min_gap, gap))
                continue

        note = ""
        if strays:
            note = " | ledger has unmapped channel labels %s - if any is really %s " \
                   "the quota above is undercounted" % (sorted(strays), channel)
        row(leg, "READY", "%d/%s today%s" % (posts_today, cap, note))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", default="grok")
    ap.add_argument("--channel")
    ap.add_argument("--date")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    now = datetime.datetime.now().astimezone()
    today = a.date or now.date().isoformat()

    try:
        policy = _load(POLICY, "policy.json")
    except Unknown as exc:
        print("UNKNOWN: %s" % exc)
        print("Nothing can be assessed. This is not the same as 'nothing is allowed'.")
        return 2
    try:
        roles = _load(ROLES, "role_capabilities.json")
    except Unknown as exc:
        roles = None
        roles_note = str(exc)
    else:
        roles_note = None

    channels = policy.get("channels") or {}
    KNOWN_CHANNELS.update(channels)

    rows = []
    for name, entry in channels.items():
        if a.channel and name != a.channel:
            continue
        if not isinstance(entry, dict):
            rows.append({"channel": name, "leg": "-", "verdict": "UNKNOWN",
                         "why": "channels.%s is not an object" % name})
            continue
        if roles is None:
            rows.append({"channel": name, "leg": "-", "verdict": "UNKNOWN",
                         "why": roles_note})
            continue
        rows.extend(assess(policy, roles, name, entry, a.actor, today, now))

    if a.json:
        print(json.dumps({"date": today, "actor": a.actor, "rows": rows},
                         ensure_ascii=False, indent=2))
    else:
        print("channel readiness  date=%s  actor=%s" % (today, a.actor))
        print("planning aid only - authorize_live_publication() is still the gate\n")
        for r in rows:
            print("%-8s %-9s %-7s %s" % (r["channel"], r["leg"], r["verdict"], r["why"]))
        ready = [r for r in rows if r["verdict"] == "READY"]
        unk = [r for r in rows if r["verdict"] == "UNKNOWN"]
        print("\n%d leg(s) checked: %d READY, %d BLOCKED, %d UNKNOWN"
              % (len(rows), len(ready), len(rows) - len(ready) - len(unk), len(unk)))

    return 0 if any(r["verdict"] == "READY" for r in rows) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
