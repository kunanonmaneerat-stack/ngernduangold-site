#!/usr/bin/env python3
"""Focused regression tests for the future-only blocked editorial calendar."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import content_calendar_guard as guard  # noqa: E402


CALENDAR = json.loads((ROOT / ".system_control/content_calendar.json").read_text(encoding="utf-8"))
POLICY = json.loads((ROOT / ".system_control/policy.json").read_text(encoding="utf-8"))
TODAY = date(2026, 8, 16)
NOW = datetime(2026, 8, 16, 23, 59, tzinfo=ZoneInfo("Asia/Bangkok"))


def _source_map(document):
    mapped = {}
    for placement in document["placements"]:
        if placement.get("source_ids"):
            mapped.setdefault(placement["content_id"], set()).update(placement.get("source_ids", []))
    return mapped


def _blocked_source(document):
    mapped = _source_map(document)

    def evaluate(content_id, _repo, _now):
        return {
            "allowed": False,
            "source_ids": sorted(mapped.get(content_id, set())),
            "failures": [f"{content_id}: relevant official source review is pending"],
        }

    return evaluate


def _pass_media(_asset, _receipt, _repo):
    suffix = Path(str(_asset)).suffix.casefold()
    media_type = "image" if suffix in {".jpg", ".jpeg", ".png", ".webp"} else "video"
    return {"verdict": "PASS", "media_type": media_type, "findings": []}


def _codes(result):
    return {item["code"] for item in result["findings"]}


with tempfile.TemporaryDirectory(prefix="calendar-library-") as raw_temp:
    ambiguous_library = Path(raw_temp) / "ambiguous.md"
    ambiguous_library.write_text(
        "| date | id | id | threads_text |\n"
        "| --- | --- | --- | --- |\n"
        "| 2026-08-24 | expected-id | silently-selected-id | copy |\n",
        encoding="utf-8",
    )
    try:
        guard._table_rows(ambiguous_library)
    except ValueError as exc:
        duplicate_headers_rejected = "duplicate editorial library table header" in str(exc)
    else:
        duplicate_headers_rejected = False


class _UnstableLibrary:
    def __init__(self):
        self.raw = (
            b"| date | id | threads_text |\n"
            b"| --- | --- | --- |\n"
            b"| 2026-08-24 | expected-id | copy |\n"
        )
        self.calls = 0

    def is_symlink(self):
        return False

    def stat(self):
        self.calls += 1
        return SimpleNamespace(
            st_size=len(self.raw),
            st_mtime_ns=self.calls,
        )

    def read_bytes(self):
        return self.raw


try:
    guard._table_rows(_UnstableLibrary())
except ValueError as exc:
    unstable_library_rejected = "changed while being read" in str(exc)
else:
    unstable_library_rejected = False


def _run(
    mutator=None,
    *,
    policy_mutator=None,
    ledger_rows=None,
    source=None,
    media=None,
    now=NOW,
    today=None,
):
    document = deepcopy(CALENDAR)
    policy = deepcopy(POLICY)
    if mutator:
        mutator(document)
    if policy_mutator:
        policy_mutator(policy)
    return guard.evaluate_document(
        document,
        repo=ROOT,
        today=today,
        now=now,
        policy=policy,
        ledger_rows=[] if ledger_rows is None else ledger_rows,
        source_evaluator=source or _blocked_source(document),
        media_evaluator=media or _pass_media,
    )


cases = []


def check(label, condition):
    cases.append(bool(condition))
    if __name__ == "__main__":
        print(("PASS " if condition else "FAIL ") + label)


check(
    "duplicate Markdown library headers fail closed instead of last-key-wins",
    duplicate_headers_rejected,
)
check(
    "editorial library changes during read fail closed",
    unstable_library_rejected,
)


def _section_failure(raw, marker="social_caption", expected="b4-p01"):
    with tempfile.TemporaryDirectory(prefix="calendar-section-") as raw_temp:
        path = Path(raw_temp) / "package.md"
        path.write_text(raw, encoding="utf-8")
        try:
            guard._section(path, marker, expected)
        except ValueError as exc:
            return str(exc)
    return ""


check(
    "BATCH4 section rejects a wrong Asset ID",
    "Asset ID does not match content_id" in _section_failure(
        "# Package\n\n- **Asset ID:** `other-id`\n\n## Social caption\n\ncopy\n"
    ),
)
check(
    "BATCH4 section rejects multiple Asset ID markers",
    "exactly one Asset ID marker" in _section_failure(
        "# Package\n\n- **Asset ID:** `b4-p01`\n"
        "- **Asset ID:** `b4-p01`\n\n## Social caption\n\ncopy\n"
    ),
)
check(
    "BATCH4 section rejects a duplicate target heading",
    "target heading must occur exactly once" in _section_failure(
        "# Package\n\n- **Asset ID:** `b4-p01`\n\n"
        "## Social caption\n\ncopy one\n\n## Social caption\n\ncopy two\n"
    ),
)


def strict_rejects(raw):
    try:
        guard._strict_json_loads(raw)
    except ValueError:
        return True
    return False


check("duplicate calendar JSON keys fail closed",
      strict_rejects('{"placements":[],"placements":[]}'))
check("overflow calendar JSON numbers fail closed",
      strict_rejects('{"placements":[],"probe":1e999}'))


actual = guard.evaluate(ROOT / ".system_control/content_calendar.json", repo=ROOT, now=NOW)
actual_dedup_findings = [
    item for item in actual.get("findings", []) if item.get("code") == "PERMANENT_DEDUP_INCOMPLETE"
]
actual_global_dedup_audit = [
    item for item in actual.get("findings", [])
    if item.get("code") == "PERMANENT_DEDUP_GLOBAL_AUDIT"
]
check(
    "actual calendar scopes the 124/125 permanent dedup gap to Facebook main",
    actual.get("verdict") == "FAIL"
    and actual.get("process_state") == "BLOCKED"
    and "PERMANENT_DEDUP_INCOMPLETE" in _codes(actual)
    and len(actual_dedup_findings) == 1
    and "channel fb is blocked" in actual_dedup_findings[0].get("message", "")
    and "36 complete, 1 incomplete" in actual_dedup_findings[0].get("message", "")
    and "affected accounts=facebook_main" in actual_dedup_findings[0].get("message", "")
    and "facebook_page2" not in actual_dedup_findings[0].get("message", "")
    and "unresolved duplicate canonical identity group" not in actual_dedup_findings[0].get("message", "")
    and len(actual_global_dedup_audit) == 1
    and actual_global_dedup_audit[0].get("classification") == guard.REPORT_ONLY
    and "124 complete, 1 incomplete" in actual_global_dedup_audit[0].get("message", "")
    and "coverage=99.2% (124/125 complete)" in actual_global_dedup_audit[0].get("message", "")
    and "ACCOUNT_GAP" not in _codes(actual)
    and guard.exit_code_for_result(actual) == 2
    and actual.get("counts", {}).get("publishable") == 0,
)


original_global_dedup_gate = guard.post_ledger.permanent_dedup_gate
original_channel_dedup_gate = guard.post_ledger.permanent_dedup_channel_gate
try:
    guard.post_ledger.permanent_dedup_gate = lambda _path: (
        False,
        "one unrelated legacy row is incomplete",
        {
            "coverage_percent": 99.0,
            "complete_rows": 99,
            "identity_rows": 100,
        },
    )
    guard.post_ledger.permanent_dedup_channel_gate = lambda channel, _path: (
        True,
        "permanent dedup channel history is complete",
        {
            "channel": channel,
            "coverage_percent": 100.0,
            "complete_rows": 1,
            "identity_rows": 1,
        },
    )
    global_only_dedup = guard.evaluate_document(
        deepcopy(CALENDAR),
        repo=ROOT,
        now=NOW,
        policy=deepcopy(POLICY),
        source_evaluator=_blocked_source(CALENDAR),
        media_evaluator=_pass_media,
    )
finally:
    guard.post_ledger.permanent_dedup_gate = original_global_dedup_gate
    guard.post_ledger.permanent_dedup_channel_gate = original_channel_dedup_gate

check(
    "global dedup incompleteness is audit-only when every selected account channel passes",
    global_only_dedup.get("process_state") == "COMPLETED_BLOCKED"
    and "PERMANENT_DEDUP_GLOBAL_AUDIT" in _codes(global_only_dedup)
    and "PERMANENT_DEDUP_INCOMPLETE" not in _codes(global_only_dedup)
    and global_only_dedup.get("counts", {}).get("publication_blocking_findings") == 0
    and guard.exit_code_for_result(global_only_dedup) == 1,
)
check(
    "canonical Page2 reschedule clears every shared Facebook structural gap",
    actual.get("counts", {}).get("structural_findings") == 0,
)
check(
    "all future library rows and required platforms are covered",
    actual["counts"].get("placements") == 65
    and actual["counts"].get("content_ids") == 34
    and actual["counts"].get("planned_blocked") == 65
    and actual["counts"].get("active_planned_blocked") == 65
    and actual["counts"].get("planned_blocked_total") == 65
    and actual["counts"].get("planned_blocked_stale") == 0
    and actual["counts"].get("reserved_blocked") == 27
    and actual["counts"].get("publishable") == 0,
)
check(
    "TikTok is a fourteen-day blocked runway, not a publication queue",
    len([item for item in CALENDAR["placements"] if item["account"] == "tiktok_main"]) == 14
    and CALENDAR["accounts"]["tiktok_main"]["account_handle"] == "@ngernduangold"
    and POLICY["channels"]["tiktok"]["state"] == "testing_blocked"
    and POLICY["channels"]["tiktok"]["auto"] is False
    and POLICY["channels"]["tiktok"]["publication_authorized"] is False,
)

baseline = _run()
check(
    "deterministic fixture baseline passes with exit 0",
    baseline["verdict"] == "PASS"
    and baseline.get("process_state") == "PASS"
    and guard.exit_code_for_result(baseline) == 0,
)
check(
    "calendar exposes exact content-scoped source enforcement counts",
    baseline["counts"].get("source_content_evaluated") == 26
    and baseline["counts"].get("source_content_allowed") == 0
    and baseline["counts"].get("source_content_blocked") == 26
    and baseline["counts"].get("source_failure_reasons") == 26
    and baseline["counts"].get("source_content_allowed")
    + baseline["counts"].get("source_content_blocked")
    == baseline["counts"].get("source_content_evaluated"),
)
check("current calendar has no stale slot at the aware baseline", baseline["counts"].get("stale_slots") == 0)

same_instant_utc = _run(now=datetime(2026, 8, 16, 16, 59, tzinfo=timezone.utc))
check("aware UTC now is normalized to Asia/Bangkok", same_instant_utc["verdict"] == "PASS")

naive_now = _run(now=datetime(2026, 8, 16, 23, 59))
check("naive evaluation time fails closed", "NOW_TIMEZONE" in _codes(naive_now))

conflicting_clock = _run(now=NOW, today=TODAY)
check("date and instant overrides cannot be combined", "NOW_CONFLICT" in _codes(conflicting_clock))

date_compatibility = _run(now=None, today=TODAY)
check("date-only compatibility override means Bangkok midnight", date_compatibility["verdict"] == "PASS")

naive_cli = subprocess.run(
    [sys.executable, str(ROOT / "tools/content_calendar_guard.py"), "--now", "2026-08-16T23:59:00"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=False,
)
check(
    "CLI rejects an offset-free --now timestamp",
    naive_cli.returncode == 3 and "must include a UTC offset or Z" in naive_cli.stderr,
)

naive_json_cli = subprocess.run(
    [
        sys.executable,
        str(ROOT / "tools/content_calendar_guard.py"),
        "--now",
        "2026-08-16T23:59:00",
        "--json",
    ],
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=False,
)
naive_json_payload = json.loads(naive_json_cli.stdout or "{}")
check(
    "invalid JSON-mode CLI is machine-readable and fail-closed",
    naive_json_cli.returncode == 3
    and naive_json_payload.get("process_state") == "RUNNER_FAILED"
    and naive_json_payload.get("counts", {}).get("publishable") == 0
    and {item.get("code") for item in naive_json_payload.get("findings", [])}
    == {"INVALID_CLI"},
)

before_first_slot = _run(now=datetime(2026, 8, 17, 12, 39, tzinfo=ZoneInfo("Asia/Bangkok")))
check("today's future slot remains a valid blocked plan", before_first_slot["verdict"] == "PASS")

after_first_slot = _run(now=datetime(2026, 8, 17, 12, 45, tzinfo=ZoneInfo("Asia/Bangkok")))
stale_findings = [item for item in after_first_slot["findings"] if item["code"] == "STALE_SLOT"]
check(
    "a missed blocked slot closes as COMPLETED_BLOCKED without becoming fatal",
    after_first_slot["verdict"] == "COMPLETED_BLOCKED"
    and after_first_slot.get("process_state") == "COMPLETED_BLOCKED"
    and after_first_slot["counts"].get("stale_slots") == 1
    and after_first_slot["counts"].get("planned_blocked") == 65
    and after_first_slot["counts"].get("active_planned_blocked") == 64
    and after_first_slot["counts"].get("planned_blocked_total") == 65
    and after_first_slot["counts"].get("planned_blocked_stale") == 1
    and after_first_slot["counts"].get("blocking_findings") == 0
    and after_first_slot["counts"].get("report_only_findings") == 1
    and after_first_slot["counts"].get("publishable") == 0
    and len(stale_findings) == 1
    and stale_findings[0].get("placement_id") == "kn-30__threads_main"
    and stale_findings[0].get("classification") == "REPORT_ONLY"
    and "2026-08-17T12:40:00+07:00" in stale_findings[0]["message"]
    and "PLANNED_BLOCKED" in stale_findings[0]["message"]
    and "do not backfill" in stale_findings[0]["message"],
)
check(
    "a later same-day slot is not marked stale early",
    all(item.get("placement_id") != "kn-30__facebook_main" for item in stale_findings),
)

check(
    "exit 1 is reserved for report-only COMPLETED_BLOCKED lifecycle",
    guard.exit_code_for_result(after_first_slot) == 1,
)

fatal_cli = subprocess.run(
    [
        sys.executable,
        str(ROOT / "tools/content_calendar_guard.py"),
        "--calendar",
        ".system_control/does-not-exist.json",
        "--json",
    ],
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=False,
)
fatal_cli_payload = json.loads(fatal_cli.stdout or "{}")
check(
    "CLI exit 3 is reserved for calendar load or runner failure",
    fatal_cli.returncode == 3
    and fatal_cli_payload.get("verdict") == "FAIL"
    and fatal_cli_payload.get("process_state") == "RUNNER_FAILED"
    and fatal_cli_payload.get("counts", {}).get("publishable") == 0,
)

rolled_calendar = _run(
    now=datetime(2026, 8, 23, 10, 0, tzinfo=ZoneInfo("Asia/Bangkok")),
)
check(
    "rolling lifecycle excludes historical blocked slots from the active backlog",
    rolled_calendar["verdict"] == "COMPLETED_BLOCKED"
    and rolled_calendar.get("process_state") == "COMPLETED_BLOCKED"
    and rolled_calendar["counts"].get("stale_slots", 0) > 1
    and rolled_calendar["counts"].get("report_only_findings", 0) > 1
    and rolled_calendar["counts"].get("blocking_findings") == 0
    and rolled_calendar["counts"].get("planned_blocked_total") == 65
    and rolled_calendar["counts"].get("planned_blocked") == 65
    and rolled_calendar["counts"].get("planned_blocked_stale")
    == rolled_calendar["counts"].get("stale_slots")
    and rolled_calendar["counts"].get("active_planned_blocked")
    + rolled_calendar["counts"].get("planned_blocked_stale")
    == rolled_calendar["counts"].get("planned_blocked_total")
    and rolled_calendar["counts"].get("publishable") == 0,
)

current_runway = _run(
    now=datetime(2026, 9, 5, 21, 45, tzinfo=ZoneInfo("Asia/Bangkok")),
)
check(
    "next-48-hour inventory is distinct from the rolling seven-day runway",
    current_runway["counts"].get("planned_blocked") == 65
    and current_runway["counts"].get("active_planned_blocked") == 3
    and current_runway["counts"].get("planned_blocked_total") == 65
    and current_runway["counts"].get("planned_blocked_stale") == 62
    and current_runway["counts"].get("next_48h_planned_blocked") == 1
    and current_runway["counts"].get("rolling_7d_planned_blocked") == 3
    and current_runway["counts"].get("rolling_7d_days_covered") == 3
    and current_runway["counts"].get("beyond_7d_planned_blocked") == 0,
)


def stale_status_drift(document):
    document["placements"][0]["status"] = "READY_FOR_OWNER_APPROVAL"


stale_status_result = _run(
    stale_status_drift,
    now=datetime(2026, 8, 23, 10, 0, tzinfo=ZoneInfo("Asia/Bangkok")),
)
check(
    "rolling lifecycle never downgrades a real status safety failure",
    stale_status_result["verdict"] == "FAIL"
    and stale_status_result.get("process_state") == "RUNNER_FAILED"
    and stale_status_result["counts"].get("blocking_findings", 0) > 0
    and "STATUS_NOT_BLOCKED" in _codes(stale_status_result)
    and guard.exit_code_for_result(stale_status_result) == 3,
)

observed_source_times = []
source_ids_by_content = _source_map(CALENDAR)


def record_source_time(content_id, _repo, slot_now):
    observed_source_times.append((content_id, slot_now))
    return {
        "allowed": False,
        "source_ids": sorted(source_ids_by_content.get(content_id, set())),
        "failures": [f"{content_id}: relevant official source review is pending"],
    }


source_clock_result = _run(source=record_source_time)
kn30_times = sorted(value for content_id, value in observed_source_times if content_id == "kn-30")
check("slot-scoped source fixture still matches blocked gates", source_clock_result["verdict"] == "PASS")
check(
    "one content-scoped source decision uses the latest exact platform slot",
    kn30_times == [
        datetime(2026, 8, 17, 5, 50, tzinfo=timezone.utc),
    ]
    and all(value.tzinfo is not None and value.utcoffset() is not None for _, value in observed_source_times),
)


def duplicate_placement(document):
    duplicate = deepcopy(document["placements"][0])
    document["placements"].append(duplicate)


check("duplicate placement ids fail", "PLACEMENT_DUPLICATE" in _codes(_run(duplicate_placement)))


def misnamespace_placement(document):
    document["placements"][0]["placement_id"] = "wrong__threads_main"


check(
    "placement identity must be canonically namespaced",
    "PLACEMENT_NAMESPACE" in _codes(_run(misnamespace_placement)),
)


def past_placement(document):
    document["placements"][0]["date"] = "2026-08-16"


past_codes = _codes(_run(past_placement))
check("past/backfill placement fails", "BACKFILL" in past_codes)


def missing_future_row(document):
    document["placements"] = [
        item for item in document["placements"]
        if item["placement_id"] != "kn-30__threads_main"
    ]


check("missing required future-library placement fails", "PLACEMENT_COVERAGE" in _codes(_run(missing_future_row)))


def publishable_status(document):
    document["placements"][0]["status"] = "SCHEDULED"


check("every placement must remain PLANNED_BLOCKED", "STATUS_NOT_BLOCKED" in _codes(_run(publishable_status)))


def remove_authority_block(document):
    placement = document["placements"][0]
    placement["blockers"].remove("publication_authority")


check("false channel authorization cannot fail open", "AUTHORITY_FAIL_OPEN" in _codes(_run(remove_authority_block)))


def remove_channel(policy):
    policy["channels"].pop("threads")


check("missing channel policy fails closed", "CHANNEL_POLICY" in _codes(_run(policy_mutator=remove_channel)))


def activate_paused_slot(document):
    placement = next(item for item in document["placements"] if item["account"] == "instagram_main")
    placement["slot_state"] = "BLOCKED"
    placement["blockers"].remove("channel_review")


paused_codes = _codes(_run(activate_paused_slot))
check("paused channels cannot receive active slots", "PAUSED_ACTIVE_SLOT" in paused_codes)


def route_to_retired(document):
    document["accounts"]["instagram_main"]["channel"] = "pinterest"
    document["accounts"]["instagram_main"]["policy_channel"] = "pinterest"


def retire_pinterest(policy):
    policy["channels"]["pinterest"]["state"] = "retired"


check(
    "retired channels cannot receive any placement",
    "RETIRED_PLACEMENT" in _codes(_run(route_to_retired, policy_mutator=retire_pinterest)),
)


def wrong_tiktok_target(document):
    document["accounts"]["tiktok_main"]["account_handle"] = "@wrong-target"


check("TikTok public target drift fails closed", "TIKTOK_TARGET" in _codes(_run(wrong_tiktok_target)))


def enable_tiktok_automation(policy):
    policy["channels"]["tiktok"]["automation_capable"] = True


check(
    "testing_blocked can never imply automation capability",
    "TESTING_BLOCKED_CAPABILITY" in _codes(_run(policy_mutator=enable_tiktok_automation)),
)


def drop_tiktok_blocker(document):
    placement = next(item for item in document["placements"] if item["account"] == "tiktok_main")
    placement["blockers"].remove("live_landing_parity")


check("TikTok mandatory blockers cannot be omitted", "TIKTOK_BLOCKERS" in _codes(_run(drop_tiktok_blocker)))


def enable_tiktok_cta(document):
    document["cta_catalog"]["tiktok-no-link"]["enabled"] = True


check("TikTok CTA remains disabled until landing parity", "CTA_NO_LINK" in _codes(_run(enable_tiktok_cta)))


def change_tiktok_source_field(document):
    placement = next(item for item in document["placements"] if item["account"] == "tiktok_main")
    placement["source"]["field"] = "creative_brief"


check("TikTok can only source the no-link caption field", "TIKTOK_SOURCE_FIELD" in _codes(_run(change_tiktok_source_field)))


def fail_open_tiktok_source(document):
    placement = next(item for item in document["placements"] if item["account"] == "tiktok_main")
    placement["gates"]["source_review"] = "NOT_REQUIRED"


check("TikTok official-source review cannot fail open", "TIKTOK_SOURCE" in _codes(_run(fail_open_tiktok_source)))


def pretend_b3_receipt_exists(document):
    placement = next(item for item in document["placements"] if item["placement_id"] == "b3-05__tiktok_main")
    placement["media_receipt"] = "automation-log/media-qa/b4-p01-video.json"
    placement["gates"]["media"] = "PASS"
    placement["blockers"].remove("semantic_parity_failed")


check(
    "aggregate scan cannot masquerade as a per-piece B3 receipt",
    "TIKTOK_RECEIPT" in _codes(_run(pretend_b3_receipt_exists)),
)


def detach_b3_semantic_report(document):
    placement = next(item for item in document["placements"] if item["placement_id"] == "b3-05__tiktok_main")
    placement["media_qa_report"] = "automation-log/media-qa/b4-p01-video.json"


check(
    "semantic B3 block must stay bound to its exact blocked QA report",
    "BLOCKED_MEDIA_QA_REPORT" in _codes(_run(detach_b3_semantic_report)),
)


def reintroduce_b3_07(document):
    document["content_sets"]["tiktok_reactivation"]["ids"].append("b3-07")


check("semantically mismatched b3-07 stays excluded", "TIKTOK_EXCLUSION" in _codes(_run(reintroduce_b3_07)))


def drift_tiktok_slot(document):
    placement = next(item for item in document["placements"] if item["placement_id"] == "wk36-sf05__tiktok_main")
    placement["date"] = "2026-08-31"


check(
    "TikTok week replacement cannot drift from its dated exact pack row",
    "TIKTOK_WEEK_SOURCE_SCOPE" in _codes(_run(drift_tiktok_slot))
    and "TIKTOK_WEEK_REPLACEMENT_EVIDENCE" in _codes(_run(drift_tiktok_slot)),
)


def exceed_cap(document):
    for content_id in ("kn-31", "kn-32"):
        placement = next(
            item for item in document["placements"]
            if item["content_id"] == content_id and item["account"] == "facebook_main"
        )
        placement["date"] = "2026-08-17"


check("policy-channel daily cap is enforced", "ACCOUNT_CAP" in _codes(_run(exceed_cap)))


def cross_account_cap(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "kn-31__facebook_main"
    )
    placement["date"] = "2026-08-17"
    page2 = next(
        item for item in document["placements"]
        if item["placement_id"] == "p2-11__facebook_page2"
    )
    page2["date"] = "2026-08-17"


check(
    "Facebook daily cap is shared across main and Page2 accounts",
    "ACCOUNT_CAP" in _codes(_run(cross_account_cap)),
)


check(
    "boolean daily caps are rejected instead of being treated as integer one",
    "CAP_POLICY" in _codes(_run(
        policy_mutator=lambda policy: policy["limits"]["posts_per_day"].update(
            {"default": True}
        ),
    )),
)


def break_gap(document):
    placement = next(item for item in document["placements"] if item["placement_id"] == "qt-12__facebook_main")
    placement["date"] = "2026-08-17"
    placement["time"] = "15:00"


check("policy-channel minimum gap is enforced", "ACCOUNT_GAP" in _codes(_run(break_gap)))


def cross_account_gap(document):
    page2 = next(
        item for item in document["placements"]
        if item["placement_id"] == "p2-11__facebook_page2"
    )
    page2["time"] = "13:10"


cross_account_gap_result = _run(cross_account_gap)
cross_account_gap_findings = [
    item for item in cross_account_gap_result["findings"]
    if item.get("code") == "ACCOUNT_GAP"
    and "wk36-sf02__facebook_main" in item.get("message", "")
    and "p2-11__facebook_page2" in item.get("message", "")
]
check(
    "12:50 Facebook main plus 13:10 Page2 fails the shared-channel gap",
    len(cross_account_gap_findings) == 1,
)
check(
    "exact 3-hour Facebook cross-page boundary remains allowed",
    "ACCOUNT_GAP" not in _codes(_run()),
)


for invalid_gap in (True, float("nan"), float("inf")):
    invalid_gap_result = _run(
        policy_mutator=lambda policy, value=invalid_gap: policy["limits"].update(
            {"min_gap_hours": value}
        )
    )
    check(
        f"non-finite/boolean minimum gap {invalid_gap!r} fails closed without crashing",
        "GAP_POLICY" in _codes(invalid_gap_result),
    )


def cross_midnight_gap(document):
    left = next(item for item in document["placements"] if item["placement_id"] == "kn-30__facebook_main")
    right = next(item for item in document["placements"] if item["placement_id"] == "kn-31__facebook_main")
    left["date"], left["time"] = "2026-08-17", "23:30"
    right["date"], right["time"] = "2026-08-18", "00:30"


check(
    "minimum gap uses absolute datetimes across midnight",
    "ACCOUNT_GAP" in _codes(_run(cross_midnight_gap)),
)


ledger_gap = [{
    "type": "text", "status": "posted", "channel": "facebook",
    "ts": "2026-08-17T11:30:00+07:00",
}]
check(
    "successful ledger posts participate in the planned-slot gap",
    "ACCOUNT_GAP" in _codes(_run(ledger_rows=ledger_gap)),
)


ledger_cap = [
    {
        "type": "text", "status": "posted", "channel": "facebook",
        "ts": "2026-08-17T06:00:00+07:00",
    },
    {
        "type": "video", "status": "published", "channel": "facebook",
        "published_at": "2026-08-17T20:00:00+07:00",
    },
]
check(
    "successful ledger posts participate in the daily account cap",
    "ACCOUNT_CAP" in _codes(_run(ledger_rows=ledger_cap)),
)


ledger_date_only = [{
    "type": "schedule", "status": "scheduled", "channel": "facebook",
    "scheduled_for": "2026-08-17",
}]
check(
    "date-only ledger schedule blocks when the exact minimum gap cannot be proven",
    "LEDGER_RATE_TIMESTAMP_UNKNOWN" in _codes(_run(ledger_rows=ledger_date_only)),
)


ledger_date_only_two_days_away = [{
    "type": "schedule", "status": "scheduled", "channel": "facebook",
    "scheduled_for": "2026-08-15",
}]
check(
    "fractional minimum gaps conservatively cover every possibly overlapping date",
    "LEDGER_RATE_TIMESTAMP_UNKNOWN" in _codes(_run(
        ledger_rows=ledger_date_only_two_days_away,
        policy_mutator=lambda policy: policy["limits"].update(
            {"min_gap_hours": 24.5}
        ),
    )),
)


ledger_unknown_status = [{
    "type": "text", "status": "pending-review", "channel": "facebook",
    "ts": "2026-08-17T06:00:00+07:00",
}]
check(
    "unrecognized ledger publication status fails closed",
    "LEDGER_RATE_STATUS_UNKNOWN" in _codes(_run(ledger_rows=ledger_unknown_status)),
)


for canonical_status in ("published_confirmed", "delivered_confirmed"):
    canonical_ledger_status = [{
        "type": "text", "status": canonical_status, "channel": "facebook",
        "ts": "2026-08-17T06:00:00+07:00",
    }]
    check(
        f"canonical ledger status {canonical_status} remains a recognized success",
        "LEDGER_RATE_STATUS_UNKNOWN" not in _codes(
            _run(ledger_rows=canonical_ledger_status)
        ),
    )


ledger_cancelled_near_slot = [{
    "type": "text", "status": "cancelled", "channel": "facebook",
    "ts": "2026-08-17T11:30:00+07:00",
}]
check(
    "cancelled ledger rows do not consume cap or gap",
    not ({"ACCOUNT_CAP", "ACCOUNT_GAP"} & _codes(_run(ledger_rows=ledger_cancelled_near_slot))),
)


out_of_order_key = "synthetic-dedup-key"
ledger_out_of_order_status = [
    {"type": "status", "dedup_key": out_of_order_key, "status": "cancelled"},
    {
        "type": "text", "dedup_key": out_of_order_key, "status": "posted",
        "channel": "facebook", "ts": "2026-08-17T11:30:00+07:00",
    },
]
out_of_order_codes = _codes(_run(ledger_rows=ledger_out_of_order_status))
check(
    "out-of-order status cannot cancel a later base row or bypass the gap",
    {"LEDGER_RATE_STATUS_AMBIGUOUS", "ACCOUNT_GAP"}.issubset(out_of_order_codes),
)


ledger_cancelled_transition = [
    {
        "type": "text", "dedup_key": out_of_order_key, "status": "posted",
        "channel": "facebook", "ts": "2026-08-17T11:30:00+07:00",
    },
    {"type": "status", "dedup_key": out_of_order_key, "status": "cancelled"},
]
check(
    "ordered terminal status resolves the base row before quota accounting",
    not ({"LEDGER_RATE_STATUS_AMBIGUOUS", "ACCOUNT_GAP"} &
         _codes(_run(ledger_rows=ledger_cancelled_transition))),
)


def duplicate_same_account_content(document):
    placement = deepcopy(next(item for item in document["placements"] if item["placement_id"] == "b4-p01__youtube_main"))
    placement["placement_id"] = "b4-p01__youtube_main__duplicate"
    placement["date"] = "2026-09-03"
    document["placements"].append(placement)


check(
    "same content id cannot repeat on the same account",
    "PERMANENT_CALENDAR_DUPLICATE" in _codes(_run(duplicate_same_account_content)),
)

ledger_duplicate = [{"type": "video", "channel": "youtube", "clip_id": "b4-p01"}]
check(
    "successful ledger identity permanently blocks same-account repost",
    "PERMANENT_LEDGER_DUPLICATE" in _codes(_run(ledger_rows=ledger_duplicate)),
)

ledger_duplicate_case_variant = [{
    "type": "video", "status": "published_confirmed",
    "channel": "youtube", "clip_id": "B4-P01",
}]
check(
    "ledger identity matching is case-insensitive across canonical content IDs",
    "PERMANENT_LEDGER_DUPLICATE" in _codes(
        _run(ledger_rows=ledger_duplicate_case_variant)
    ),
)

legacy_now_duplicate = [{
    "type": "now", "status": "posted", "channel": "tiktok", "clip_key": "b3-04",
}]
check(
    "legacy posted-now identity also permanently blocks a same-account repost",
    "PERMANENT_LEDGER_DUPLICATE" in _codes(_run(ledger_rows=legacy_now_duplicate)),
)

cancelled_legacy = [{
    "type": "schedule", "status": "cancelled", "channel": "youtube", "clip_key": "b4-p01",
}]
check(
    "explicitly cancelled legacy schedule does not create a false duplicate blocker",
    "PERMANENT_LEDGER_DUPLICATE" not in _codes(_run(ledger_rows=cancelled_legacy)),
)


def source_pass(_content_id, _repo, _now):
    all_ids = set()
    for placement in CALENDAR["placements"]:
        if placement["content_id"].startswith("kn-"):
            all_ids.update(placement.get("source_ids", []))
    return {"allowed": True, "source_ids": sorted(all_ids), "failures": []}


check(
    "source-gate state drift requires calendar review",
    "SOURCE_GATE_DRIFT" in _codes(_run(source=source_pass)),
)


def falsely_pass_kn34_source(document):
    for placement in document["placements"]:
        if placement["content_id"] == "kn-34":
            placement["gates"]["source_review"] = "PASS"
            placement["blockers"].remove("official_source_review")


def contradictory_source_result(document):
    blocked = _blocked_source(document)
    mapped = _source_map(document)

    def evaluate(content_id, repo, now):
        if content_id != "kn-34":
            return blocked(content_id, repo, now)
        return {
            "allowed": True,
            "source_ids": sorted(mapped[content_id]),
            "failures": ["official snapshot is stale"],
        }

    return evaluate


contradictory_document = deepcopy(CALENDAR)
falsely_pass_kn34_source(contradictory_document)
contradictory_source = _run(
    falsely_pass_kn34_source,
    source=contradictory_source_result(contradictory_document),
)
check(
    "source result cannot allow publication while carrying freshness failures",
    {"SOURCE_GATE_DRIFT", "SOURCE_FAIL_OPEN"}.issubset(
        _codes(contradictory_source)
    ),
)


def drop_one_declared_source(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "kn-34__threads_main"
    )
    placement["source_ids"] = placement["source_ids"][:-1]


check(
    "calendar placement cannot hide a required source by declaring a subset",
    "SOURCE_IDS" in _codes(_run(
        drop_one_declared_source,
        source=_blocked_source(CALENDAR),
    )),
)


def opt_factual_content_out_of_source_review(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "p2-09__facebook_page2"
    )
    placement["gates"]["source_review"] = "NOT_REQUIRED"
    placement["source_ids"] = None
    placement["blockers"].remove("official_source_review")


factual_opt_out = _run(
    opt_factual_content_out_of_source_review,
    source=_blocked_source(CALENDAR),
)
check(
    "factual content cannot opt out through its placement-controlled source gate",
    factual_opt_out["process_state"] == "RUNNER_FAILED"
    and factual_opt_out["counts"].get("source_content_evaluated") == 26
    and "SOURCE_GATE_DRIFT" in _codes(factual_opt_out)
    and "SOURCE_IDS_SHAPE" in _codes(factual_opt_out)
    and "SOURCE_FAIL_OPEN" in _codes(factual_opt_out),
)


def duplicate_ids_on_cached_later_platform(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "kn-34__facebook_main"
    )
    placement["source_ids"].append(placement["source_ids"][-1])


cached_duplicate = _run(duplicate_ids_on_cached_later_platform)
check(
    "every cached later-platform source claim rejects duplicate IDs",
    "SOURCE_IDS_DUPLICATE" in _codes(cached_duplicate)
    and any(
        item.get("code") == "SOURCE_IDS_DUPLICATE"
        and item.get("placement_id") == "kn-34__facebook_main"
        for item in cached_duplicate["findings"]
    ),
)


def malformed_ids_on_cached_later_platform(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "kn-34__facebook_main"
    )
    placement["source_ids"] = {
        source_id: True for source_id in placement["source_ids"]
    }


cached_malformed = _run(malformed_ids_on_cached_later_platform)
check(
    "every cached later-platform source claim rejects a non-list shape",
    "SOURCE_IDS_SHAPE" in _codes(cached_malformed)
    and any(
        item.get("code") == "SOURCE_IDS_SHAPE"
        and item.get("placement_id") == "kn-34__facebook_main"
        for item in cached_malformed["findings"]
    ),
)


def first_platform_claim_malformed_second_correct(document):
    placements = [
        item for item in document["placements"]
        if item["content_id"] == "kn-34"
    ]
    for placement in placements:
        placement["gates"]["source_review"] = "PASS"
        placement["blockers"].remove("official_source_review")
    placements[0]["source_ids"].append(placements[0]["source_ids"][-1])


def run_with_content_only_source_truth(mutator):
    document = deepcopy(CALENDAR)
    policy = deepcopy(POLICY)
    mutator(document)
    mapped = _source_map(CALENDAR)

    def content_truth(content_id, *_args, **_kwargs):
        allowed = content_id == "kn-34"
        return guard.content_source_gate.SourceGateResult(
            allowed,
            content_id,
            tuple(sorted(mapped.get(content_id, set()))),
            () if allowed else (f"{content_id}: source review pending",),
        )

    original = guard.content_source_gate.evaluate_content_source_gate
    guard.content_source_gate.evaluate_content_source_gate = content_truth
    try:
        return guard.evaluate_document(
            document,
            repo=ROOT,
            now=NOW,
            policy=policy,
            ledger_rows=[],
            source_evaluator=None,
            media_evaluator=_pass_media,
        )
    finally:
        guard.content_source_gate.evaluate_content_source_gate = original


first_claim_only = run_with_content_only_source_truth(
    first_platform_claim_malformed_second_correct
)
first_source_findings = [
    item for item in first_claim_only["findings"]
    if item.get("placement_id") == "kn-34__threads_main"
    and item.get("code", "").startswith("SOURCE")
]
second_source_findings = [
    item for item in first_claim_only["findings"]
    if item.get("placement_id") == "kn-34__facebook_main"
    and item.get("code", "").startswith("SOURCE")
]
check(
    "a malformed first-platform claim cannot poison cached content source truth",
    {item["code"] for item in first_source_findings} == {"SOURCE_IDS_DUPLICATE"}
    and not second_source_findings
    and first_claim_only["counts"].get("source_content_allowed") == 1
    and first_claim_only["counts"].get("source_content_blocked") == 25,
)


replacement_placements = [
    item for item in CALENDAR["placements"]
    if item.get("content_id") in {
        "wk36-sf02", "wk36-sf03", "wk36-sf04", "wk36-sf05"
    }
    and item.get("account") in {"threads_main", "facebook_main"}
]
check(
    "owner-authorized evergreen replacement preserves eight page-only slots",
    len(replacement_placements) == 8
    and {item.get("account") for item in replacement_placements}
    == {"threads_main", "facebook_main"}
    and {item.get("date") for item in replacement_placements}
    == {"2026-08-25", "2026-08-27", "2026-08-28", "2026-08-30"}
    and all(item.get("status") == "PLANNED_BLOCKED" for item in replacement_placements)
    and all(item.get("gates", {}).get("source_review") == "NOT_REQUIRED" for item in replacement_placements)
    and all(item.get("gates", {}).get("candidate_novelty") == "PASS_PER_ITEM" for item in replacement_placements)
    and all(item.get("gates", {}).get("global_permanent_dedup") == "BLOCKED" for item in replacement_placements),
)

replacement_pack = json.loads(
    (ROOT / "automation-log/WEEK-CONTENT-PACK_20260824-30.json").read_text(
        encoding="utf-8"
    )
)
replacement_pack_rows = {
    item["candidate_id"]: item for item in replacement_pack["days"]
}
check(
    "weekly replacements select only exact-copy conditional evergreen candidates",
    all(
        replacement_pack_rows[item["content_id"]].get("source_review")
        == "NOT_REQUIRED_IF_TEXT_REMAINS_EXACT"
        and replacement_pack_rows[item["content_id"]].get("source_ids") == []
        for item in replacement_placements
    ),
)


def detach_replacement_cta(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "wk36-sf03__threads_main"
    )
    placement["cta_id"] = "about"


check(
    "weekly replacement CTA and no-body-URL binding fail closed on drift",
    "REPLACEMENT_EVIDENCE" in _codes(_run(detach_replacement_cta)),
)


def drift_replacement_pack_hash(document):
    document["content_sets"]["weekly_replacements"]["pack_sha256"] = "0" * 64


check(
    "replacement pack hash drift fails closed",
    {"REPLACEMENT_PACK_HASH", "REPLACEMENT_EVIDENCE"}.issubset(
        _codes(_run(drift_replacement_pack_hash))
    ),
)


def detach_replacement_provenance(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "wk36-sf02__threads_main"
    )
    placement.pop("replacement_provenance")


check(
    "replacement cannot detach from its reversible superseded-slot receipt",
    "REPLACEMENT_PROVENANCE" in _codes(_run(detach_replacement_provenance)),
)


def orphan_non_source_ids(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "qt-12__facebook_main"
    )
    placement["source_ids"] = ["bot-credit-card-guidance"]


check(
    "non-source reservation cannot carry orphan source IDs",
    "SOURCE_IDS_ORPHAN" in _codes(_run(orphan_non_source_ids)),
)


def break_compliance_source_reference(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "p2-12__facebook_page2"
    )
    placement["source"]["field"] = "missing_copy"


check(
    "required compliance gate is integrated into calendar validation",
    "CONTENT_COMPLIANCE" in _codes(_run(break_compliance_source_reference)),
)


def failed_media(_asset, _receipt, _repo):
    return {"verdict": "FAIL", "findings": ["receipt mismatch"]}


check(
    "hash-bound media receipt failure blocks reserved video",
    "MEDIA_GATE_DRIFT" in _codes(_run(media=failed_media)),
)


def mislabel_video_as_image(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "b4-p01__facebook_main"
    )
    placement["format"] = "image"


check(
    "placement format cannot contradict the exact media receipt type",
    "MEDIA_TYPE_MISMATCH" in _codes(_run(mislabel_video_as_image)),
)


def human_audio_blocked_media(asset, _receipt, _repo):
    if str(asset).casefold().endswith(".mp4"):
        return {
            "verdict": "FAIL",
            "media_type": "video",
            "findings": ["human audio review is missing"],
        }
    return {"verdict": "PASS", "media_type": "image", "findings": []}


human_audio_blocked = _run(media=human_audio_blocked_media)
check(
    "missing exact human listening is a publication blocker, not runner failure",
    human_audio_blocked.get("process_state") == "BLOCKED"
    and guard.exit_code_for_result(human_audio_blocked) == 2
    and "MEDIA_HUMAN_AUDIO_REVIEW_REQUIRED" in _codes(human_audio_blocked)
    and "MEDIA_GATE_DRIFT" not in _codes(human_audio_blocked),
)


def orphan_media_receipt(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "qt-12__facebook_main"
    )
    placement["media"] = None


check(
    "media and hash-bound receipt cannot be orphaned from each other",
    "MEDIA_ORPHAN" in _codes(_run(orphan_media_receipt)),
)


def orphan_media_qa_report(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "qt-12__facebook_main"
    )
    placement["media"] = None
    placement["media_receipt"] = None
    placement["media_qa_report"] = "automation-log/video-production/b3-04_qa.json"


check(
    "media QA report cannot exist without its asset",
    "MEDIA_QA_ORPHAN" in _codes(_run(orphan_media_qa_report)),
)


quote_media_placements = [
    item for item in CALENDAR["placements"]
    if item.get("content_id") in {"qt-12", "qt-13", "qt-14"}
    and item.get("format") == "image"
]
check(
    "nine quote placements bind exact r5 media and channel copy while remaining blocked",
    len(quote_media_placements) == 9
    and all(item.get("media") and item.get("media_receipt") for item in quote_media_placements)
    and all(item.get("gates", {}).get("media") == "PASS" for item in quote_media_placements)
    and all(item.get("status") == "PLANNED_BLOCKED" for item in quote_media_placements)
    and all("publication_authority" in item.get("blockers", []) for item in quote_media_placements)
    and all("caption_adaptation" not in item.get("blockers", []) for item in quote_media_placements)
    and all("missing_media" not in item.get("blockers", []) for item in quote_media_placements)
    and all("visual_qa" not in item.get("blockers", []) for item in quote_media_placements)
    and all(
        item.get("source", {}).get("file")
        == "automation-log/WEEK-CONTENT-PACK_20260824-30.json"
        for item in quote_media_placements
        if item.get("content_id") in {"qt-12", "qt-13"}
    )
    and all(
        item.get("source", {}).get("field")
        == guard.QUOTE_PACK_CAPTION_FIELDS.get(item.get("placement_id"))
        for item in quote_media_placements
        if item.get("content_id") in {"qt-12", "qt-13"}
    )
    and all(
        item.get("source", {}).get("file")
        == "automation-log/QUOTE-CARDS_20260723-0822.md"
        and item.get("source", {}).get("field") == "caption"
        and item.get("media_binding_receipt")
        == "automation-log/QT14-MEDIA-BINDING-RECEIPT_20260830.json"
        for item in quote_media_placements
        if item.get("content_id") == "qt-14"
    ),
)

qt14_pinterest = next(
    item for item in CALENDAR["placements"]
    if item.get("placement_id") == "qt-14__pinterest_main"
)
calendar_file_hash = guard._sha256(ROOT / ".system_control/content_calendar.json")
check(
    "declared media binding receipt proves the exact calendar, source, asset and QA bytes",
    guard._media_binding_receipt_errors(
        qt14_pinterest,
        ROOT,
        calendar_file_sha256=calendar_file_hash,
    ) == [],
)

drifted_qt14_binding = deepcopy(qt14_pinterest)
drifted_qt14_binding["source"]["field"] = "quote_th"
drifted_qt14_binding_errors = guard._media_binding_receipt_errors(
    drifted_qt14_binding,
    ROOT,
    calendar_file_sha256=calendar_file_hash,
)
check(
    "media binding receipt rejects later source-field or placement drift",
    "media binding receipt source field differs from the placement source"
    in drifted_qt14_binding_errors
    and "media binding receipt placement SHA-256 differs from the current placement"
    in drifted_qt14_binding_errors,
)
check(
    "media binding receipt rejects a different whole-calendar hash",
    "media binding receipt calendar SHA-256 differs from the current calendar"
    in guard._media_binding_receipt_errors(
        qt14_pinterest,
        ROOT,
        calendar_file_sha256="0" * 64,
    ),
)


def drift_quote_channel_caption(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "qt-12__facebook_main"
    )
    placement["source"]["field"] = "threads_text"


drifted_quote_caption_codes = _codes(_run(drift_quote_channel_caption))
check(
    "quote channel copy cannot drift from its exact pack field and hash binding",
    "QUOTE_PACK_SOURCE_SCOPE" in drifted_quote_caption_codes
    and "REPLACEMENT_EVIDENCE" in drifted_quote_caption_codes,
)


def drift_variant_media_identity(document):
    placement = next(
        item for item in document["placements"]
        if item["placement_id"] == "qt-12__facebook_main"
    )
    placement["media_content_id"] = "qt-13-4x5-r5"


check(
    "variant media content identity is bound to its exact receipt",
    "MEDIA_CONTENT_ID" in _codes(_run(drift_variant_media_identity)),
)


def agent_speaker(document):
    document["accounts"]["threads_main"]["public_speaker"] = "Codex"


identity_codes = _codes(_run(agent_speaker))
check("agents cannot become public page speakers", "ACCOUNT_SPEAKER" in identity_codes)


def non_page_identity(document):
    document["accounts"]["facebook_page2"]["page_only"] = False


check("Page2 must remain a page-only Organization", "ACCOUNT_PAGE_ONLY" in _codes(_run(non_page_identity)))


class ContentCalendarGuardRegressionTests(unittest.TestCase):
    def test_regression_matrix(self):
        self.assertTrue(all(cases), f"content calendar guard tests: {sum(cases)}/{len(cases)} PASS")


if __name__ == "__main__":
    print(f"content calendar guard tests: {sum(cases)}/{len(cases)} PASS")
    raise SystemExit(0 if all(cases) else 1)
