#!/usr/bin/env python3
"""Export only READY placements; local files are not delivery to Grok.

python -B tools/grok_jobcards.py --date 2026-09-13
No outbound transport, scheduling, receipts or ledger mutation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import grok_gate as gate

HANDOFF = "automation-log/grok-handoff"


def posted_count(rows, channel, day):
    """Count publications once, folding precisely the readiness aliases.

    Claims reserve capacity in the existing claim guard but are not 'posted'.
    Status results join claims by exact dedup_key; legacy posts remain counted.
    """
    claims = {r.get("dedup_key"): r for r in rows if r.get("status") == "claimed"}
    counted = set()
    for index, row in enumerate(rows):
        status = str(row.get("status", "posted")).lower()
        if status not in gate.ledger.SUCCESS_CONFIRM_STATUSES:
            continue
        parent = claims.get(row.get("dedup_key"), {}) if row.get("type") == "status" else {}
        raw = row.get("channel", parent.get("channel"))
        if gate.readiness.ALIASES.get(raw, raw) != channel:
            continue
        if row.get("type") not in gate.readiness.COUNTS_AS_A_POST and not parent:
            continue
        value = row.get("published_at") or row.get("posted_at") or row.get("ts")
        if gate.timestamp(value).date().isoformat() == day:
            counted.add(row.get("dedup_key") or ("row", index))
    return len(counted)


def make_card(job, result, root, now):
    p = job["placement"]
    policy = gate.read_json(root / gate.POLICY)
    rows = [gate.identity_guard._strict_json_loads(line) for line in
            (root / gate.LEDGER).read_text(encoding="utf-8").splitlines() if line.strip()]
    slot, channel = job["slot"], job["channel"]
    # Use exactly the existing authority window, never the broader example window.
    if channel == "youtube":
        before = slot - gate.authority.SCHEDULED_MAX_LEAD
        after = slot - gate.authority.SCHEDULED_MIN_LEAD - dt.timedelta(microseconds=1)
    else:
        before, after = slot, slot + gate.authority.IMMEDIATE_LATE_WINDOW
    media = p.get("media")
    media_hash = hashlib.sha256(gate.safe_path(media, root).read_bytes()).hexdigest() if media else None
    limits = policy["limits"]
    cap = limits["posts_per_day"].get(channel, limits["posts_per_day"].get("default"))
    action = job["action"]
    _receipt, consumed_at = gate.authority._load_consumed_receipt(root, action["nonce"])
    return {
        "job_id": job["job_id"], "channel": channel, "leg": p["format"],
        "account": action["target_identity"], "scheduled_at": slot.isoformat(),
        "window": {"not_before": before.isoformat(), "not_after": after.isoformat()},
        "content": {"text": job["text"], "text_sha256": gate.digest(job["text"]),
                    "media_ref": media, "media_sha256": media_hash},
        "disclosure_included": True,
        "gate": {"verdict": "READY", "checked_by": "codex", "checked_at": now.isoformat(),
                 "checks_sha256": gate.digest(gate.canonical(result["checks"]))},
        "approval": {"owner_approved": True, "piece_id": p["content_id"],
                     "approved_at": consumed_at.isoformat()},
        "limits": {"posts_per_day": cap, "min_gap_hours": limits["min_gap_hours"],
                   "posted_today_before_this": posted_count(rows, channel, now.date().isoformat())},
        "forbidden_in_text": gate.read_json(root / gate.RULES)["forbidden"] + ["199"],
        "report": {"claim_to": None, "result_to": None},
    }


def build(day, *, root=gate.ROOT, now=None):
    root = Path(root).resolve()
    dt.date.fromisoformat(day)
    now = (now or dt.datetime.now(gate.TZ)).astimezone(gate.TZ)
    calendar = gate.read_json(root / gate.CALENDAR)
    ready, held = [], []
    for p in calendar["placements"]:
        if p.get("date") != day:
            continue
        result = gate.assess(p["placement_id"], root=root, now=now)
        if result["verdict"] == "READY":
            try:
                card = make_card(gate.resolve_job(p["placement_id"], root), result, root, now)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                result = gate.finish([dict(field="jobcard.export_evidence", verdict="UNKNOWN",
                    paths=[gate.CALENDAR, gate.LEDGER], detail=type(exc).__name__)])
            else:
                ready.append(card)
                continue
        held.append({"placement_id": p["placement_id"], **result})
    return ready, held


def export(day, *, root=gate.ROOT, now=None):
    ready, held = build(day, root=root, now=now)
    directory = Path(root) / HANDOFF
    directory.mkdir(parents=True, exist_ok=True)
    issued = directory / ("jobcards_" + day + ".json")
    if issued.exists():
        previous = gate.read_json(issued)
        if previous and previous != ready:
            raise ValueError("issued nonempty jobcards are immutable; retain them for claim/result reconciliation")
    for suffix, data in (("", ready), ("_held", held)):
        path = directory / ("jobcards_" + day + suffix + ".json")
        if path.is_symlink():
            raise ValueError("handoff output cannot be a symlink")
        # Build both complete arrays before replacing either; a truncated file is
        # rejected by strict ingest, and held evidence never authorizes anything.
        open(path, "w", encoding="utf-8", newline="\n").write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return {"date": day, "ready": len(ready), "held": len(held),
            "transport": "UNKNOWN: awaiting routine 0; local export only"}


def selftest():
    import unittest
    from unittest.mock import patch

    class ExportTests(unittest.TestCase):
        def test_real_calendar_without_approval_exports_nothing(self):
            placements = gate.read_json(gate.ROOT / gate.CALENDAR)["placements"]
            dates = {p["date"] for p in placements}
            for day in dates:
                ready, held = build(day)
                unapproved = {p["placement_id"] for p in placements if p["date"] == day and not p.get("execution_action")}
                self.assertFalse({r["job_id"].split("@", 1)[0] for r in ready} & unapproved)
                self.assertTrue(unapproved <= {r["placement_id"] for r in held})
                self.assertTrue(all(r["verdict"] != "READY" for r in held))

        def test_only_ready_is_exported_unknown_and_blocked_held(self):
            calendar = {"placements": [{"placement_id": x, "date": "2026-09-13"} for x in ("a", "b", "c")]}
            def assess(pid, **kwargs):
                return dict(verdict={"a": "READY", "b": "BLOCKED", "c": "UNKNOWN"}[pid],
                            checks=[], blocking_field="approval" if pid == "b" else "",
                            could_not_check="ledger" if pid == "c" else "")
            with patch.object(gate, "read_json", return_value=calendar), patch.object(gate, "assess", side_effect=assess), patch.object(gate, "resolve_job", return_value={}), patch(__name__ + ".make_card", return_value={"job_id": "a"}):
                ready, held = build("2026-09-13")
            self.assertEqual(ready, [{"job_id": "a"}])
            self.assertEqual([r["verdict"] for r in held], ["BLOCKED", "UNKNOWN"])

        def test_alias_status_join_and_other_surface(self):
            rows = [dict(type="text", channel="fb", status="claimed", dedup_key="a"),
                    dict(type="status", status="posted", dedup_key="a", posted_at="2026-09-12T18:00:00Z"),
                    dict(type="text", channel="facebook-page2", status="posted", posted_at="2026-09-13T12:00:00+07:00")]
            self.assertEqual(posted_count(rows, "facebook", "2026-09-13"), 1)
            self.assertEqual(posted_count(rows[:1], "facebook", "2026-09-13"), 0)

    return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExportTests)).wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=dt.datetime.now(gate.TZ).date().isoformat())
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        result = export(args.date)
    except Exception as exc:
        print(json.dumps({"verdict": "RUNNER_FAILED", "could_not_check": type(exc).__name__}))
        return 4
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
