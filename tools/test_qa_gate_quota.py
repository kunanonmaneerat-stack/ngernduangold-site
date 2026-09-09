#!/usr/bin/env python3
"""Regression tests for policy-backed social posting quotas."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import qa_gate  # noqa: E402

TZ = timezone(timedelta(hours=7))
NOW = datetime(2026, 8, 16, 17, 0, tzinfo=TZ)
POLICY = {
    "limits": {
        "posts_per_day": {"default": 2, "pinterest": 5},
        "min_gap_hours": 3,
        "post_types": ["text", "video", "image"],
    },
    "channels": {
        "facebook": {"state": "manual", "publication_authorized": False},
        "threads": {"state": "active", "publication_authorized": False},
        "tiktok": {"state": "retired", "publication_authorized": False},
        "pinterest": {"state": "paused", "publication_authorized": False},
    },
}


def row(kind, hour, channel="facebook"):
    return {
        "type": kind,
        "channel": channel,
        "ts": "2026-08-16T%02d:00:00+07:00" % hour,
    }


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def main():
    current_policy = json.loads(
        (ROOT / ".system_control" / "policy.json").read_text(encoding="utf-8")
    )
    current_limits = current_policy["limits"]
    check(
        "dated quota decision is explicit and no longer unresolved",
        current_limits["posts_per_day"]["default"] == 2
        and current_limits["min_gap_hours"] >= 3
        and "DECIDED" in current_limits["_conflict"]
        and "unresolved" not in current_limits["_conflict"].lower(),
    )

    ok, reason = qa_gate.publication_authority("owner")
    check(
        "owner actor label never grants publication authority",
        not ok and "not authentication" in reason,
    )

    ok, reason = qa_gate.prepublish_policy_gate("facebook", policy=POLICY)
    check(
        "publication_authorized=false blocks prepublish",
        not ok and "publication_authorized=false" in reason,
    )

    future_policy = {
        "channels": {"facebook": {"state": "manual", "publication_authorized": True}}
    }
    ok, reason = qa_gate.prepublish_policy_gate("facebook", policy=future_policy)
    check(
        "qa_gate stays non-authoritative even if policy changes",
        not ok and "cannot authenticate" in reason,
    )

    ok, reason = qa_gate.prepublish_policy_gate("facebook", policy={})
    check("missing prepublish policy fails closed", not ok and "fail closed" in reason)

    output = StringIO()
    with redirect_stdout(output):
        rc = qa_gate.main(["--quota", "facebook", "--actor", "owner"])
    check(
        "quota CLI rejects actor labels with quota-only label",
        rc == 2 and "QUOTA-ONLY BLOCKED" in output.getvalue(),
    )

    original_quota = qa_gate.posting_quota
    qa_gate.posting_quota = lambda _channel: (True, "test quota available")
    try:
        output = StringIO()
        with redirect_stdout(output):
            rc = qa_gate.main(["--quota", "facebook"])
    finally:
        qa_gate.posting_quota = original_quota
    check(
        "quota success is labelled non-authoritative",
        rc == 0
        and "QUOTA-ONLY OK" in output.getvalue()
        and "NOT PUBLICATION AUTHORITY" in output.getvalue(),
    )

    ok, reason = qa_gate.posting_quota(
        "facebook",
        now=NOW,
        ledger_rows=[row("attempt", 12), row("text", 12)],
        policy=POLICY,
    )
    check("attempt rows do not consume quota", ok and "1/2" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook",
        now=NOW,
        ledger_rows=[row("attempt", 12), row("text", 12), row("video", 16)],
        policy=POLICY,
    )
    check("two published rows fill quota", not ok and "2/2" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook",
        now=NOW,
        ledger_rows=[row("failure", 16), row("skipped", 16), row("text", 12)],
        policy=POLICY,
    )
    check("failure and skipped rows do not consume quota", ok and "1/2" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook",
        now=NOW,
        ledger_rows=[row("text", 15)],
        policy=POLICY,
    )
    check("minimum gap uses published rows", not ok and "18:00" in reason)

    ok, reason = qa_gate.posting_quota(
        "tiktok", now=NOW, ledger_rows=[], policy=POLICY
    )
    check("retired channel is blocked", not ok and "retired" in reason)

    ok, reason = qa_gate.posting_quota(
        "pinterest", now=NOW, ledger_rows=[], policy=POLICY
    )
    check("paused channel is blocked", not ok and "paused" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy={}
    )
    check("missing policy fails closed", not ok and "fail closed" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy={"channels": {}}
    )
    check("missing channel fails closed", not ok and "missing" in reason)

    unknown = {"channels": {"facebook": {"state": "unknown"}}}
    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy=unknown
    )
    check("unknown state fails closed", not ok and "not explicitly allowed" in reason)

    limited = {"channels": {"facebook": {
        "state": "limited", "phase_until": "2026-08-15", "weekly_quota": 3,
    }}}
    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy=limited
    )
    check("expired limited phase fails closed", not ok and "not explicitly allowed" in reason)

    limited["channels"]["facebook"].update(
        {"phase_until": "2026-08-20", "weekly_quota": 0}
    )
    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy=limited
    )
    check("zero-quota limited phase fails closed", not ok and "not explicitly allowed" in reason)

    pantip_limited = {
        "limits": {
            "posts_per_day": {"default": 2, "pinterest": 5},
            "min_gap_hours": 3,
            "post_types": ["text", "video", "image"],
        },
        "channels": {"pantip": {
            "state": "limited", "kind": "forum",
            "phase_until": "2026-08-20", "weekly_quota": 3,
            "publication_authorized": True,
            "auto": False,
            "automation_capable": False,
            "manual_pilot": {
                "status": "READY_FOR_CONFIRMED_REPLY",
                "scope": "reply_existing_topic_only",
                "forbidden": ["automated_publication"],
                "authorization_state": "FRESH_PER_PIECE_APPROVAL",
                "authorized_content_id": "pantip-fixture-v2",
                "authorized_placement_id": "pantip-fixture-v2__pantip_main",
                "per_piece_owner_confirmation_required": True,
                "review_must_pass_before_reauthorization": True,
                "review_due_at": "2026-08-15T15:54:44+07:00",
                "next_publication_not_before": "2026-08-15T15:54:44+07:00",
            },
        }},
        "gates": [{
            "task": "pantip manual pilot 48h review",
            "status": "PASS",
            "review_due_at": "2026-08-15T15:54:44+07:00",
        }],
    }
    week_rows = [
        {"type": "text", "channel": "pantip", "ts": "2026-08-09T18:30:00+00:00"},
        {"type": "text", "channel": "pantip", "ts": "2026-08-12T12:00:00+07:00"},
        {"type": "text", "channel": "pantip", "ts": "2026-08-14T12:00:00+07:00"},
        {"type": "attempt", "channel": "pantip", "ts": "2026-08-15T12:00:00+07:00"},
        {"type": "failure", "channel": "pantip", "ts": "2026-08-15T13:00:00+07:00"},
        {"type": "text", "channel": "pantip", "ts": "2026-08-09T12:00:00+07:00"},
    ]
    ok, reason = qa_gate.posting_quota(
        "pantip", now=NOW, ledger_rows=week_rows, policy=pantip_limited,
        content_id="pantip-fixture-v2",
        placement_id="pantip-fixture-v2__pantip_main",
    )
    check("limited channel enforces Monday-Sunday quota",
          not ok and "3/3" in reason)

    ok, reason = qa_gate.posting_quota(
        "pantip", now=NOW, ledger_rows=week_rows[1:], policy=pantip_limited,
        content_id="pantip-fixture-v2",
        placement_id="pantip-fixture-v2__pantip_main",
    )
    check("attempts, failures, and out-of-week rows do not consume weekly quota",
          ok and "week 2/3" in reason)

    invalid_limits = json.loads(json.dumps(POLICY))
    invalid_limits["limits"]["min_gap_hours"] = float("nan")
    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy=invalid_limits
    )
    check("non-finite policy gap fails closed", not ok and "limits invalid" in reason)

    invalid_limits = json.loads(json.dumps(POLICY))
    invalid_limits["limits"]["posts_per_day"]["default"] = True
    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy=invalid_limits
    )
    check("boolean policy cap fails closed", not ok and "limits invalid" in reason)

    invalid_limits = json.loads(json.dumps(POLICY))
    invalid_limits["limits"]["post_types"] = ["video", "image"]
    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW, ledger_rows=[], policy=invalid_limits
    )
    check("omitted counted post type fails closed", not ok and "limits invalid" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW,
        ledger_rows=[{"type": "text", "channel": "facebook",
                      "ts": "2026-08-16T12:00:00"}], policy=POLICY,
    )
    check("naive ledger timestamp fails closed", not ok and "invalid publication" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW,
        ledger_rows=[{"type": "video", "channel": "facebook",
                      "ts": "2026-08-16T09:00:00+07:00",
                      "publish_at": "2026-08-16"}], policy=POLICY,
    )
    check("date-only schedule reserves capacity and blocks unknown gap",
          not ok and "fail closed" in reason)

    ok, reason = qa_gate.posting_quota(
        "facebook", now=NOW.replace(tzinfo=None), ledger_rows=[], policy=POLICY,
    )
    check("naive current time fails closed", not ok and "timezone-aware" in reason)

    strict_rejected = 0
    for raw in ('{"pass":false,"pass":true}', '{"pass":true,"unused":NaN}',
                '{"pass":true,"unused":1e999}'):
        try:
            qa_gate._strict_json_loads(raw)
        except ValueError:
            strict_rejected += 1
    check("visual/policy JSON rejects duplicate and non-finite values", strict_rejected == 3)

    print("27 checks, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
