#!/usr/bin/env python3
"""Time-aware contract tests for Pantip quota/timing eligibility."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from pantip_eligibility import evaluate_pantip_eligibility  # noqa: E402
import post_timing  # noqa: E402
import qa_gate  # noqa: E402


TZ = timezone(timedelta(hours=7))
NOW = datetime(2026, 8, 23, 10, 6, 53, tzinfo=TZ)
CONTENT_ID = "pantip-reply-fixture-v2"
PLACEMENT_ID = CONTENT_ID + "__pantip_main"


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def approved_policy():
    due = "2026-08-18T15:54:44+07:00"
    return {
        "limits": {
            "posts_per_day": {"default": 2},
            "min_gap_hours": 3,
            "post_types": ["text", "video", "image"],
        },
        "channels": {"pantip": {
            "state": "limited",
            "kind": "forum",
            "auto": False,
            "automation_capable": False,
            "phase_until": "2026-08-23",
            "weekly_quota": 1,
            "publication_authorized": True,
            "manual_pilot": {
                "status": "READY_FOR_CONFIRMED_REPLY",
                "scope": "reply_existing_topic_only",
                "forbidden": ["automated_publication"],
                "authorization_state": "FRESH_PER_PIECE_APPROVAL",
                "authorized_content_id": CONTENT_ID,
                "authorized_placement_id": PLACEMENT_ID,
                "per_piece_owner_confirmation_required": True,
                "review_must_pass_before_reauthorization": True,
                "review_due_at": due,
                "next_publication_not_before": due,
            },
        }},
        "gates": [{
            "task": "pantip manual pilot 48h review",
            "status": "PASS",
            "review_due_at": due,
        }],
    }


def main():
    current = json.loads(
        (ROOT / ".system_control" / "policy.json").read_text(encoding="utf-8")
    )
    result = evaluate_pantip_eligibility(current, now=NOW)
    check(
        "current consumed approval and overdue review fail closed",
        not result.allowed
        and any("consumed" in reason for reason in result.failures)
        and any("overdue" in reason for reason in result.failures),
    )
    check(
        "publication authority is part of Pantip eligibility",
        any("publication_authorized" in reason for reason in result.failures),
    )

    ok, reason = qa_gate.posting_quota(
        "pantip", now=NOW, ledger_rows=[], policy=current
    )
    check(
        "quota helper cannot bypass the manual-pilot state",
        not ok and "Pantip eligibility blocked" in reason,
    )

    policy = approved_policy()
    result = evaluate_pantip_eligibility(policy, now=NOW)
    check(
        "generic timing identity cannot reuse a per-piece approval",
        not result.allowed and any("exact content_id" in reason for reason in result.failures),
    )

    result = evaluate_pantip_eligibility(
        policy, now=NOW, content_id=CONTENT_ID, placement_id=PLACEMENT_ID
    )
    check("exact passed review and fresh piece authority are eligible", result.allowed)

    ok, reason = qa_gate.posting_quota(
        "pantip", now=NOW, ledger_rows=[], policy=policy,
        content_id=CONTENT_ID, placement_id=PLACEMENT_ID,
    )
    check("quota can evaluate the exact approved piece", ok and "week 0/1" in reason)

    consumed = deepcopy(policy)
    consumed["channels"]["pantip"]["manual_pilot"]["authorization_state"] = (
        "ONE_TIME_APPROVAL_CONSUMED"
    )
    check(
        "consumed one-time approval blocks even after review passes",
        not evaluate_pantip_eligibility(
            consumed, now=NOW, content_id=CONTENT_ID, placement_id=PLACEMENT_ID
        ).allowed,
    )

    open_review = deepcopy(policy)
    open_review["gates"][0]["status"] = "OPEN"
    result = evaluate_pantip_eligibility(
        open_review, now=NOW, content_id=CONTENT_ID, placement_id=PLACEMENT_ID
    )
    check(
        "overdue OPEN review blocks",
        not result.allowed and any("overdue" in reason for reason in result.failures),
    )

    no_authority = deepcopy(policy)
    no_authority["channels"]["pantip"]["publication_authorized"] = False
    check(
        "false publication authority blocks an otherwise passing pilot",
        not evaluate_pantip_eligibility(
            no_authority, now=NOW, content_id=CONTENT_ID, placement_id=PLACEMENT_ID
        ).allowed,
    )

    mismatch = evaluate_pantip_eligibility(
        policy,
        now=NOW,
        content_id="pantip-other-v1",
        placement_id="pantip-other-v1__pantip_main",
    )
    check(
        "a different piece cannot reuse fresh owner approval",
        not mismatch.allowed and any("does not match" in reason for reason in mismatch.failures),
    )

    wrong_account = deepcopy(policy)
    wrong_placement = CONTENT_ID + "__facebook_main"
    wrong_account["channels"]["pantip"]["manual_pilot"]["authorized_placement_id"] = (
        wrong_placement
    )
    result = evaluate_pantip_eligibility(
        wrong_account,
        now=NOW,
        content_id=CONTENT_ID,
        placement_id=wrong_placement,
    )
    check(
        "a cross-channel placement cannot masquerade as the approved Pantip piece",
        not result.allowed and any("canonical Pantip" in reason for reason in result.failures),
    )

    with tempfile.TemporaryDirectory(prefix="pantip_eligibility_") as raw:
        path = Path(raw) / "policy.json"
        path.write_text(json.dumps(policy), encoding="utf-8")
        check(
            "generic timing excludes even a fresh per-piece Pantip approval",
            post_timing.eligible_platforms(path, now=NOW) == [],
        )
        path.write_text(json.dumps(consumed), encoding="utf-8")
        check(
            "timing excludes consumed Pantip approval",
            post_timing.eligible_platforms(path, now=NOW) == [],
        )

    result = evaluate_pantip_eligibility({}, now=NOW)
    check("missing Pantip policy fails closed", not result.allowed)

    print("pantip eligibility: 14/14 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
