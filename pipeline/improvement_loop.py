"""Local-safe continuous improvement control loop for the page.

The loop observes, diagnoses, prioritizes, validates and reports.  It never
publishes, acknowledges sources, commits, pushes, deploys or moves money.  Local
code/content changes remain scoped work performed by an authorized agent session
and must be validated before the next run can treat them as current.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from private_runtime import IMPROVEMENT_RUNS_DIR  # noqa: E402

import release_contract  # noqa: E402
import observation_snapshot  # noqa: E402
import revenue_ledger  # noqa: E402
import task_run_receipt  # noqa: E402


CONTRACT = ROOT / ".system_control" / "improvement_policy.json"
POLICY = ROOT / ".system_control" / "policy.json"
GUARDS = {
    "privacy": ["tools/privacy_guard.py"],
    "public_identity": ["tools/public_identity_guard.py"],
    "automation_policy": ["tools/automation_policy_guard.py"],
    "merchant_offer": [
        "tools/merchant_offer_gate.py", "--generated-site", "site",
    ],
    "manifest": ["tools/manifest_contract.py"],
    "local_site": ["tools/postdeploy_smoke.py", "--src", "site"],
    "posting_plan": ["@private_posting_plan"],
    "daily_media": ["tools/daily_media_gate.py", "--fps", "3", "--json"],
}
DEFAULT_GUARD_TIMEOUT_SECONDS = 180
GUARD_TIMEOUT_SECONDS = {
    # A full 3-fps watermark scan covers every canonical video and has measured
    # above three minutes on this Windows host.  Keep the detection quality and
    # give this bounded local-only guard enough time inside the task's 2h SLA.
    "tools/daily_media_gate.py": 600,
}
GUARD_RUNTIME_LAUNCHERS = {
    # The media scanner depends on the pinned runtime contract (numpy/OpenCV).
    # Running it through the interpreter that happened to start this control
    # loop creates a false watermark failure on hosts with a lean system Python.
    "tools/daily_media_gate.py": ROOT / "pipeline" / "python_runtime.cmd",
}
CONTENT_CALENDAR_GUARD = ["tools/content_calendar_guard.py", "--json"]
LOCAL_SAFE_LIVE_RELEASE_SUMMARY = (
    "BLOCKED/UNKNOWN: local-safe mode forbids live network probes; "
    "live release parity was not observed. Supply a separately collected, "
    "hash-bound result explicitly when an authorized workflow has one. "
    "No live request was attempted."
)
GUARDRAIL_EVIDENCE = {
    "privacy_guard must pass": ("guard", "privacy"),
    "public_identity_guard must pass": ("guard", "public_identity"),
    "automation_policy_guard must pass": ("guard", "automation_policy"),
    "merchant_offer_gate must pass": ("guard", "merchant_offer"),
    "manifest_contract must pass": ("guard", "manifest"),
    "affiliate disclosure and attribution must pass": ("guard", "local_site"),
    "content-scoped official sources fail closed per placement": (
        "readiness", "content_scoped_sources"
    ),
    "no exact same-channel repost": ("guard", "posting_plan"),
    "no provider watermark in active publish media": ("guard", "daily_media"),
    "publication and deploy remain separately owner-gated": (
        "invariant", "external_mutation_authorized_false"
    ),
}
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
READINESS_CHECKS = (
    "publication_authority",
    "content_calendar",
    "live_release_parity",
    "revenue_ledger",
    "ga4",
    "gsc",
    "content_scoped_sources",
)
READINESS_SCHEMA_VERSION = 3
MATURITY_CRITERIA = (
    "evidence_current_and_bound",
    "guardrails_current",
    "revenue_ledger_trusted",
    "analytics_decisionable",
    "content_scoped_source_enforcement",
    "publication_inputs_ready",
    "verified_revenue_learning",
)
PRIORITY_ACTION_KINDS = (
    "repair_local_guard",
    "repair_measurement",
    "refresh_gsc_bundle",
    "refresh_official_source_snapshot",
    "repair_revenue_ledger",
    "audit_offer_and_attribution",
    "design_one_revenue_experiment",
)
OWNER_ACTION_KINDS = (
    "verify_ga4_internal_network",
    "review_official_sources",
)
EXTERNAL_OWNER_ACTIONS = {
    "social_publish", "public_comment_or_reply", "source_acknowledge",
    "git_commit", "git_push", "deploy", "financial_transaction",
    "external_notify", "external_storage_write", "package_install",
    "scheduler_mutation",
}
ERROR_LEARNING_SCHEMA = 1
ERROR_LEARNING_STATE_FILE = "_error-learning-state.json"
CONTROL_HEALTH_FILE = "_control-health.json"
TERMINAL_RUN_STATES = {
    "COMPLETED", "COMPLETED_WITH_BLOCKERS", "FAILED_VALIDATION", "FAILED",
}
CONTROL_HEALTH_KPI_IDS = {
    "terminal_control_run_rate_7d",
    "recurring_open_incidents",
    "regressed_incidents_per_run",
    "publication_blocker_false_fatal_count",
    "fresh_evidence_age_hours",
}
TASK_RECEIPT_NAMES = (
    "ngernduangold_daily",
    "ngernduangold_weekly",
)
TASK_RECEIPT_RUNNER_PATHS = {
    "ngernduangold_daily": (ROOT / "pipeline" / "run_daily.cmd").resolve(
        strict=False
    ),
    "ngernduangold_weekly": (ROOT / "pipeline" / "run_weekly.cmd").resolve(
        strict=False
    ),
}
TASK_RECEIPT_TOOL_PATH = (
    ROOT / "pipeline" / "task_run_receipt.py"
).resolve(strict=False)
TASK_RECEIPT_STUCK_AFTER_HOURS = 2
CALENDAR_PROCESS_EXIT = {
    "PASS": 0,
    "COMPLETED_BLOCKED": 1,
    "BLOCKED": 2,
    "STRUCTURAL_FINDINGS": 3,
    "RUNNER_FAILED": 3,
}
RUNTIME_CONTRACT_PATHS = (
    ".local-private/runtime/manual-publication-calendar.json",
    ".system_control/content_calendar.json",
    ".system_control/content_manifest.json",
    ".system_control/generative_media_policy.json",
    ".system_control/host_ip.json",
    ".system_control/improvement_policy.json",
    ".system_control/merchant_offers.json",
    ".system_control/policy.json",
    ".system_control/role_capabilities.json",
    ".system_control/yt_upload_log.json",
    "automation-log/knowledge-base/content-source-registry.json",
    "automation-log/knowledge-base/official-news-snapshot.json",
    "automation-log/knowledge-base/page2-source-registry.json",
    "automation-log/knowledge-base/social-source-registry.json",
    "automation-log/media-qa/published-media.json",
    "automation-log/post-ledger-collision-tombstones.json",
    "automation-log/post-ledger-identity-bindings.jsonl",
    "automation-log/post-ledger.jsonl",
    "automation-log/post_ledger.py",
    "automation-log/post_ledger_collision.py",
    "automation-log/post_ledger_identity.py",
    "automation-log/public_log_sanitize.py",
    "automation/ig_publish.py",
    "pipeline/comply_gate.py",
    "pipeline/ga4_decision_trust.py",
    "pipeline/ga4_pull.py",
    "pipeline/ga4_schema.py",
    "pipeline/gsc_pull.py",
    "pipeline/improvement_loop.py",
    "pipeline/official_news_monitor.py",
    "pipeline/observation_snapshot.py",
    "pipeline/revenue_ledger.py",
    "pipeline/python_runtime.cmd",
    "pipeline/requirements-runtime.txt",
    "pipeline/run_daily.cmd",
    "pipeline/run_weekly.cmd",
    "pipeline/task_run_receipt.py",
    "reels/schedule.json",
    "social-autopost/publish_fb.py",
    "social-autopost/publish_tiktok.py",
    "tiktok-pipeline/src/qa_watermark.py",
    "tools/automation_policy_guard.py",
    "tools/content_calendar_guard.py",
    "tools/content_compliance_gate.py",
    "tools/content_source_gate.py",
    "tools/daily_media_gate.py",
    "tools/editorial_draft_gate.py",
    "tools/generative_media_origin_gate.py",
    "tools/import_accesstrade_csv.py",
    "tools/log_sale.py",
    "tools/manifest_contract.py",
    "tools/media_publish_guard.py",
    "tools/merchant_offer_gate.py",
    "tools/post_guard.py",
    "tools/postdeploy_smoke.py",
    "tools/privacy_guard.py",
    "tools/private_runtime.py",
    "tools/publication_authority.py",
    "tools/public_identity_guard.py",
    "tools/release_contract.py",
    "tools/week_candidate_manifest_guard.py",
    "tools/week_content_freshness_guard.py",
    "tools/yt_upload_batch2.py",
)
OPTIONAL_RUNTIME_CONTRACT_PATHS = frozenset({
    ".local-private/runtime/manual-publication-calendar.json",
})


def _safe_runtime_dependency(raw):
    """Return a canonical repository-relative dependency or ``None``.

    Identity overlay rows can point at exact source and evidence files.  Those
    files are executable guard inputs even though their names are data-driven,
    so the same-run contract must bind them as well as the overlay itself.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip().replace("\\", "/")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    try:
        (ROOT / relative).resolve().relative_to(ROOT.resolve())
    except ValueError:
        return None
    return relative.as_posix()


def _runtime_contract_paths():
    """Return every same-run control, dedup, media, and QA dependency.

    Media gates inspect canonical assets and receipt/evidence files.  Binding
    only the gate code would leave a TOCTOU window where scanned bytes could be
    replaced before score validation.  Enumerating the bounded canonical media
    and QA roots makes additions, removals, and byte drift invalidate the run.
    """
    paths = list(RUNTIME_CONTRACT_PATHS)
    release_dependencies = set()
    for raw in (*release_contract.SOURCE_INPUTS, release_contract.PILOT_PATH):
        value = raw.as_posix() if isinstance(raw, Path) else str(raw)
        dependency = _safe_runtime_dependency(value)
        if dependency is None:
            raise ValueError(
                "release contract source path is unsafe: " + value
            )
        release_dependencies.add(dependency)
    paths.extend(sorted(release_dependencies.difference(paths)))
    bindings = ROOT / "automation-log" / "post-ledger-identity-bindings.jsonl"
    dependencies = set()
    try:
        for line in bindings.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or record.get("record_type") != (
                "post_ledger_identity_binding"
            ):
                continue
            source = record.get("source")
            if not isinstance(source, dict):
                continue
            for key in ("path", "evidence_path"):
                dependency = _safe_runtime_dependency(source.get(key))
                if dependency:
                    dependencies.add(dependency)
    except (OSError, UnicodeError, json.JSONDecodeError):
        # The overlay itself remains a required static contract input and the
        # posting-plan guard rejects an unreadable/malformed overlay.  Do not
        # infer dependencies from partial or invalid evidence.
        dependencies.clear()

    bounded_roots = (
        ROOT / "reels",
        ROOT / "media" / "pins",
        ROOT / "media" / "quotes",
        ROOT / "automation-log" / "media-qa",
    )
    for directory in bounded_roots:
        try:
            candidates = sorted(
                (item for item in directory.rglob("*") if item.is_file()),
                key=lambda item: item.relative_to(ROOT).as_posix(),
            )
        except OSError:
            candidates = []
        for candidate in candidates:
            dependency = _safe_runtime_dependency(
                candidate.relative_to(ROOT).as_posix()
            )
            if dependency:
                dependencies.add(dependency)

    # Candidate manifests can bind pack/summary artifacts outside media-qa.
    media_qa_root = ROOT / "automation-log" / "media-qa"
    try:
        manifests = sorted(media_qa_root.glob(
            "WEEK-TIKTOK-QUOTE-CANDIDATES_MANIFEST_R*.json"
        ))
    except OSError:
        manifests = []
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        pack = manifest.get("pack")
        summary = manifest.get("qa_summary")
        for value in (
            pack.get("path") if isinstance(pack, dict) else None,
            summary.get("path") if isinstance(summary, dict) else None,
        ):
            dependency = _safe_runtime_dependency(value)
            if dependency:
                dependencies.add(dependency)
        for row in manifest.get("assets") or []:
            if not isinstance(row, dict):
                continue
            for key in ("asset", "receipt"):
                dependency = _safe_runtime_dependency(row.get(key))
                if dependency:
                    dependencies.add(dependency)
    paths.extend(sorted(dependencies.difference(paths)))
    return tuple(paths)


def _strict_json_float(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    return value


def _reject_json_constant(raw):
    raise ValueError("non-finite JSON constant: " + str(raw))


def _reject_json_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: " + str(key))
        value[key] = item
    return value


def _load(path):
    value = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_float=_strict_json_float,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_json_duplicates,
    )
    if not isinstance(value, dict):
        raise ValueError(str(path) + " must contain an object")
    return value


def _canonical_hash(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _zero_or_empty_list(value):
    return bool(
        isinstance(value, int) and not isinstance(value, bool) and value == 0
        or isinstance(value, list) and not value
    )


def _parse_utc(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _readiness_hash(readiness):
    return _canonical_hash({
        "schema_version": readiness.get("schema_version"),
        "target_channel": readiness.get("target_channel"),
        "blockers": readiness.get("blockers"),
        "checks": readiness.get("checks"),
    })


def _readiness_expected_blockers(checks):
    blockers = []
    publication = checks.get("publication_authority", {})
    if publication.get("passed") is not True:
        blockers.append("publication_authority_false")
    calendar = checks.get("content_calendar", {})
    process_state = calendar.get("process_state")
    if process_state == "BLOCKED":
        blockers.append("content_calendar_blocked")
    elif process_state == "STRUCTURAL_FINDINGS":
        blockers.append("content_calendar_structural_findings")
    elif process_state not in {"PASS", "COMPLETED_BLOCKED"}:
        blockers.append("content_calendar_guard_failed")
    elif calendar.get("passed") is not True:
        blockers.append("content_calendar_publishable_zero")
    if checks.get("live_release_parity", {}).get("passed") is not True:
        blockers.append("live_release_parity_failed")
    if checks.get("revenue_ledger", {}).get("passed") is not True:
        blockers.append("revenue_ledger_unreconciled")
    if checks.get("ga4", {}).get("passed") is not True:
        blockers.append("ga4_trust_or_bundle_failed")
    if checks.get("gsc", {}).get("passed") is not True:
        blockers.append("gsc_bundle_failed")
    if checks.get("content_scoped_sources", {}).get("passed") is not True:
        blockers.append("content_scoped_source_enforcement_failed")
    return blockers


def readiness_contract_errors(readiness, observation=None, decision_time=None):
    """Prove that readiness is complete, internally consistent and raw-fact bound."""
    if not isinstance(readiness, dict):
        return ["decision readiness must be an object"]
    errors = []
    if readiness.get("schema_version") != READINESS_SCHEMA_VERSION:
        errors.append("decision readiness schema is unsupported")
    checks = readiness.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(READINESS_CHECKS):
        errors.append("decision readiness checks are incomplete")
        checks = checks if isinstance(checks, dict) else {}
    for name in READINESS_CHECKS:
        row = checks.get(name)
        if not isinstance(row, dict) or not isinstance(row.get("passed"), bool):
            errors.append("decision readiness check is malformed: " + name)

    publication = checks.get("publication_authority", {})
    authorized = publication.get("authorized_channels")
    available = publication.get("available_authorized_channels")
    target_channel = publication.get("target_channel")
    available_fact = bool(
        isinstance(available, list)
        and available == sorted(set(available))
        and all(isinstance(item, str) and item for item in available)
    )
    authority_fact = bool(
        isinstance(target_channel, str) and target_channel
        and isinstance(authorized, list)
        and authorized == [target_channel]
        and available_fact
        and target_channel in available
        and readiness.get("target_channel") == target_channel
    )
    if publication.get("passed") is not authority_fact:
        errors.append("publication authority check contradicts its evidence")
    if not available_fact:
        errors.append("publication authority inventory is malformed")

    calendar = checks.get("content_calendar", {})
    publishable = calendar.get("publishable")
    publishable_valid = (
        isinstance(publishable, int) and not isinstance(publishable, bool)
        and publishable >= 0
    )
    process_state = calendar.get("process_state")
    calendar_exit = calendar.get("exit_code")
    process_valid = bool(
        process_state in CALENDAR_PROCESS_EXIT
        and isinstance(calendar_exit, int) and not isinstance(calendar_exit, bool)
        and calendar_exit == CALENDAR_PROCESS_EXIT[process_state]
    )
    execution_fact = bool(process_valid and process_state != "RUNNER_FAILED")
    guard_fact = bool(process_valid and process_state in {"PASS", "COMPLETED_BLOCKED"})
    calendar_fact = bool(
        guard_fact and publishable_valid and publishable > 0
    )
    if calendar.get("execution_valid") is not execution_fact:
        errors.append("content calendar execution state contradicts its evidence")
    if calendar.get("guard_passed") is not guard_fact:
        errors.append("content calendar guard state contradicts its evidence")
    if calendar.get("passed") is not calendar_fact:
        errors.append("content calendar check contradicts its evidence")
    calendar_payload = calendar.get("payload")
    if (
        not isinstance(calendar_payload, dict)
        or calendar.get("payload_hash") != _canonical_hash(calendar_payload)
    ):
        errors.append("content calendar payload evidence is missing or mismatched")
    if not isinstance(calendar.get("summary"), str) or not calendar[
        "summary"
    ].strip():
        errors.append("content calendar summary evidence is missing")

    release = checks.get("live_release_parity", {})
    release_fact = bool(
        isinstance(release.get("exit_code"), int)
        and not isinstance(release.get("exit_code"), bool)
        and release.get("exit_code") == 0
    )
    if release.get("passed") is not release_fact:
        errors.append("live release parity check contradicts its evidence")
    release_summary = release.get("summary")
    if not isinstance(release_summary, str) or not release_summary.strip():
        errors.append("live release parity summary evidence is missing")
    else:
        expected_release_hash = _canonical_hash({
            "passed": release_fact,
            "exit_code": release.get("exit_code"),
            "summary": release_summary,
            "full_output_sha256": release.get("full_output_sha256"),
            "full_output_path": release.get("full_output_path"),
            "full_output_lines": release.get("full_output_lines"),
        })
        if release.get("evidence_hash") != expected_release_hash:
            errors.append("live release parity evidence hash is mismatched")
    release_output_hash = release.get("full_output_sha256")
    release_output_path = release.get("full_output_path")
    release_output_lines = release.get("full_output_lines")
    if (
        not isinstance(release_output_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", release_output_hash)
        or not isinstance(release_output_path, str)
        or not release_output_path.startswith("guard-evidence/subprocess/")
        or ".." in Path(release_output_path).parts
        or not isinstance(release_output_lines, int)
        or isinstance(release_output_lines, bool)
        or release_output_lines < 1
    ):
        errors.append("live release parity full output evidence is invalid")

    expected_blockers = _readiness_expected_blockers(checks)
    if readiness.get("blockers") != expected_blockers:
        errors.append("decision readiness blockers do not match checks")
    ready = not expected_blockers
    if readiness.get("status") != ("READY" if ready else "BLOCKED"):
        errors.append("decision readiness status contradicts blockers")
    if readiness.get("growth_ready") is not ready:
        errors.append("growth readiness contradicts blockers")
    if readiness.get("publication_ready") is not ready:
        errors.append("publication readiness contradicts blockers")
    try:
        expected_hash = _readiness_hash(readiness)
    except (TypeError, ValueError):
        expected_hash = None
    if not expected_hash or readiness.get("evidence_hash") != expected_hash:
        errors.append("decision readiness evidence hash is missing or mismatched")

    if isinstance(observation, dict):
        sources = observation.get("sources")
        sources = sources if isinstance(sources, dict) else {}
        metrics = observation.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        observed_at = _parse_utc(observation.get("observed_at"))
        evaluated_at = (
            _parse_utc(decision_time)
            if decision_time is not None
            else observed_at
        )
        if decision_time is not None and evaluated_at is None:
            errors.append("decision readiness evaluation time is invalid")
        revenue_fact = False
        if evaluated_at is not None:
            revenue_fact = _revenue_learning_contract(
                observation, evaluated_at
            )["learning_ready"]
        if checks.get("revenue_ledger", {}).get("passed") is not revenue_fact:
            errors.append("revenue readiness is not bound to the observation")
        ga4 = sources.get("ga4")
        ga4 = ga4 if isinstance(ga4, dict) else {}
        ga4_trust = ga4.get("trust")
        ga4_trust = ga4_trust if isinstance(ga4_trust, dict) else {}
        ga4_bundle = ga4.get("bundle")
        ga4_bundle = ga4_bundle if isinstance(ga4_bundle, dict) else {}
        ga4_expiry_error = observation_snapshot.decision_expiry_error(
            ga4_bundle, evaluated_at, "GA4"
        )
        ga4_fact = bool(
            ga4_trust.get("trusted") is True
            and ga4_bundle.get("decisionable") is True
            and ga4_bundle.get("state") == "CURRENT"
            and ga4_bundle.get("capture_trust") == "TRUSTED"
            and ga4_bundle.get("current_trust") == "TRUSTED"
            and ga4_expiry_error is None
        )
        if checks.get("ga4", {}).get("passed") is not ga4_fact:
            errors.append("GA4 readiness is not bound to the observation")
        if (
            checks.get("ga4", {}).get("expires_at") != ga4_bundle.get("expires_at")
            or checks.get("ga4", {}).get("expiry_error") != ga4_expiry_error
        ):
            errors.append("GA4 expiry evidence is not bound to the observation")
        gsc = sources.get("gsc")
        gsc = gsc if isinstance(gsc, dict) else {}
        gsc_bundle = gsc.get("bundle")
        gsc_bundle = gsc_bundle if isinstance(gsc_bundle, dict) else {}
        gsc_expiry_error = observation_snapshot.decision_expiry_error(
            gsc_bundle, evaluated_at, "GSC"
        )
        gsc_fact = bool(
            gsc_bundle.get("decisionable") is True
            and gsc_bundle.get("state") == "CURRENT"
            and gsc_expiry_error is None
        )
        if checks.get("gsc", {}).get("passed") is not gsc_fact:
            errors.append("GSC readiness is not bound to the observation")
        if (
            checks.get("gsc", {}).get("expires_at") != gsc_bundle.get("expires_at")
            or checks.get("gsc", {}).get("expiry_error") != gsc_expiry_error
        ):
            errors.append("GSC expiry evidence is not bound to the observation")
    source_check = checks.get("content_scoped_sources", {})
    source_counts = (
        calendar_payload.get("counts")
        if isinstance(calendar_payload, dict) else None
    )
    source_counts = source_counts if isinstance(source_counts, dict) else {}
    source_values = [
        source_counts.get("source_content_evaluated"),
        source_counts.get("source_content_allowed"),
        source_counts.get("source_content_blocked"),
        source_counts.get("source_failure_reasons"),
    ]
    source_count_contract = bool(
        all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in source_values)
        and source_values[1] + source_values[2] == source_values[0]
    )
    source_fact = bool(
        calendar.get("execution_valid") is True
        and source_count_contract
        and source_counts.get("structural_findings") == 0
    )
    if source_check.get("passed") is not source_fact:
        errors.append("content-scoped source readiness contradicts calendar evidence")
    for field, value in zip((
        "evaluated", "allowed", "blocked", "failure_reasons"
    ), source_values):
        if source_check.get(field) != value:
            errors.append(
                "content-scoped source count contradicts calendar evidence: " + field
            )
    return errors


def readiness_file_evidence_errors(readiness, run_dir):
    """Verify the private full-output artifact named by release readiness."""
    try:
        release = readiness["checks"]["live_release_parity"]
        relative = Path(release["full_output_path"])
        selected_root = Path(run_dir).resolve()
        path = (selected_root / relative).resolve()
        if path.parent != (selected_root / relative.parent).resolve():
            raise ValueError("release evidence path escapes its declared parent")
        path.relative_to(selected_root)
        data = path.read_bytes()
    except (KeyError, TypeError, ValueError, OSError):
        return ["live release parity full output artifact is unavailable"]
    errors = []
    if hashlib.sha256(data).hexdigest() != release.get("full_output_sha256"):
        errors.append("live release parity full output artifact hash is mismatched")
    try:
        line_count = len(data.decode("utf-8").splitlines())
    except UnicodeDecodeError:
        errors.append("live release parity full output artifact is not UTF-8")
    else:
        if line_count != release.get("full_output_lines"):
            errors.append("live release parity full output line count is mismatched")
    return errors


def _atomic(path, payload):
    observation_snapshot.atomic_json(path, payload)


@contextlib.contextmanager
def _exclusive_run_lock(runs_root):
    """Allow only one process to advance the global learning pointers.

    The lock is held by the operating-system file handle, so a crashed process
    releases it automatically.  Keep the marker file instead of using a stale
    lock-file deletion heuristic that could evict a slow but live control run.
    """
    root = Path(runs_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "_active-run.lock"
    handle = lock_path.open("a+b", buffering=0)
    if lock_path.stat().st_size == 0:
        handle.write(b"\0")
    handle.seek(0)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            raise RuntimeError(
                "another improvement control run is already active"
            ) from exc
        acquired = True
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def collect_runtime_contract():
    """Snapshot on-disk control inputs before observation and detect later drift."""
    files = []
    for relative in _runtime_contract_paths():
        path = ROOT / relative
        if relative in OPTIONAL_RUNTIME_CONTRACT_PATHS:
            # Manual publication is separately owner-controlled. An absent
            # calendar is valid closed state, not missing mandatory evidence;
            # its later appearance/removal must still invalidate this snapshot.
            try:
                path.lstat()
            except FileNotFoundError:
                files.append({"path": relative, "state": "ABSENT",
                              "size_bytes": None, "sha256": None})
                continue
            except OSError:
                files.append({"path": relative, "state": "UNREADABLE",
                              "size_bytes": None, "sha256": None})
                continue
            if path.is_symlink():
                files.append({"path": relative, "state": "UNSAFE",
                              "size_bytes": None, "sha256": None})
                continue
        if not path.is_file():
            files.append({"path": relative, "state": "MISSING",
                          "size_bytes": None, "sha256": None})
            continue
        data = path.read_bytes()
        files.append({
            "path": relative,
            "state": "PRESENT",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    result = {"schema_version": 1, "files": files}
    result["contract_hash"] = _canonical_hash(result)
    return result


def runtime_contract_errors(contract, *, verify_current=False):
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        return ["runtime contract is missing or has an unsupported schema"]
    errors = []
    files = contract.get("files")
    if not isinstance(files, list):
        return ["runtime contract file evidence is missing"]
    paths = [row.get("path") for row in files if isinstance(row, dict)]
    if paths != list(_runtime_contract_paths()):
        errors.append("runtime contract paths are incomplete or reordered")
    for row in files:
        if not isinstance(row, dict):
            errors.append("runtime contract row is malformed")
            continue
        if (row.get("path") in OPTIONAL_RUNTIME_CONTRACT_PATHS
                and row.get("state") == "ABSENT"):
            if row.get("sha256") is not None or row.get("size_bytes") is not None:
                errors.append("absent optional runtime input carries file evidence")
            continue
        present = row.get("state") == "PRESENT"
        sha = row.get("sha256")
        size = row.get("size_bytes")
        if not present:
            errors.append("runtime contract input is missing: %s" % row.get("path"))
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            errors.append("runtime contract hash is invalid: %s" % row.get("path"))
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append("runtime contract size is invalid: %s" % row.get("path"))
    try:
        expected_hash = _canonical_hash({
            key: value for key, value in contract.items() if key != "contract_hash"
        })
    except (TypeError, ValueError):
        expected_hash = None
    if not expected_hash or contract.get("contract_hash") != expected_hash:
        errors.append("runtime contract hash is missing or mismatched")
    if verify_current and not errors and contract != collect_runtime_contract():
        errors.append("runtime contract changed during the control run")
    return errors


def _seal_error_learning_state(state):
    state.pop("state_hash", None)
    state["state_hash"] = _canonical_hash(state)
    return state


def _error_learning_hash_valid(state):
    if not isinstance(state, dict) or not isinstance(state.get("state_hash"), str):
        return False
    try:
        body = {key: value for key, value in state.items() if key != "state_hash"}
        return state["state_hash"] == _canonical_hash(body)
    except (TypeError, ValueError):
        return False


def _empty_error_learning_state():
    return _seal_error_learning_state({
        "schema_version": ERROR_LEARNING_SCHEMA,
        "updated_at": None,
        "last_run_id": None,
        "previous_state_hash": None,
        "incidents": {},
        "actions": {},
        "summary": {
            "current_incidents": 0,
            "open_incidents": 0,
            "new_incidents": [],
            "recurring_incidents": [],
            "regressed_incidents": [],
            "resolved_incidents": [],
        },
    })


def error_learning_state_errors(
    state, current_findings=None, *, not_before=None, not_after=None
):
    """Validate the persistent incident memory without trusting its claims."""
    if not isinstance(state, dict) or state.get("schema_version") != ERROR_LEARNING_SCHEMA:
        return ["error-learning state is missing or has an unsupported schema"]
    errors = []
    lower_bound = _parse_utc(not_before) if not_before is not None else None
    upper_bound = _parse_utc(not_after) if not_after is not None else None
    if not_before is not None and lower_bound is None:
        errors.append("error-learning chronology lower bound is invalid")
    if not_after is not None and upper_bound is None:
        errors.append("error-learning chronology upper bound is invalid")
    if lower_bound is not None and upper_bound is not None and lower_bound > upper_bound:
        errors.append("error-learning chronology bounds are inverted")
    if not _error_learning_hash_valid(state):
        errors.append("error-learning state hash is missing or mismatched")
    updated_at = state.get("updated_at")
    updated = None
    last_run_id = state.get("last_run_id")
    previous_hash = state.get("previous_state_hash")
    if updated_at is None:
        if last_run_id is not None:
            errors.append("empty error-learning state cannot name a last run")
    else:
        updated = _parse_utc(updated_at)
        if updated is None:
            errors.append("error-learning updated_at must be timezone-aware")
        else:
            if lower_bound is not None and updated < lower_bound:
                errors.append("error-learning updated_at predates the terminal run")
            if upper_bound is not None and updated > upper_bound:
                errors.append("error-learning updated_at exceeds the proven chronology")
        if (
            not isinstance(last_run_id, str)
            or not RUN_ID_RE.fullmatch(last_run_id) or ".." in last_run_id
        ):
            errors.append("error-learning last_run_id is invalid")
    if previous_hash is not None and (
        not isinstance(previous_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", previous_hash)
    ):
        errors.append("error-learning previous state hash is invalid")
    incidents = state.get("incidents")
    actions = state.get("actions")
    if not isinstance(incidents, dict):
        errors.append("error-learning incidents must be an object")
        incidents = {}
    if not isinstance(actions, dict):
        errors.append("error-learning actions must be an object")
        actions = {}
    for fingerprint, row in incidents.items():
        if not isinstance(row, dict) or row.get("fingerprint") != fingerprint:
            errors.append("error-learning incident identity is malformed")
            continue
        if row.get("status") not in {"OPEN", "REGRESSED", "RESOLVED"}:
            errors.append("error-learning incident status is invalid: " + fingerprint)
        for field in ("occurrences", "consecutive_runs", "regression_count"):
            value = row.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append("error-learning incident count is invalid: %s.%s" %
                              (fingerprint, field))
        if row.get("occurrences") == 0:
            errors.append("error-learning incident occurrences must be positive: " + fingerprint)
        if (
            isinstance(row.get("consecutive_runs"), int)
            and not isinstance(row.get("consecutive_runs"), bool)
            and isinstance(row.get("occurrences"), int)
            and not isinstance(row.get("occurrences"), bool)
            and row["consecutive_runs"] > row["occurrences"]
        ):
            errors.append("error-learning incident consecutive count exceeds occurrences: " + fingerprint)
        first_seen = _parse_utc(row.get("first_seen_at"))
        last_seen = _parse_utc(row.get("last_seen_at"))
        if first_seen is None or last_seen is None or last_seen < first_seen:
            errors.append("error-learning incident timestamps are invalid: " + fingerprint)
        elif updated is not None and last_seen > updated:
            errors.append(
                "error-learning incident timestamp exceeds state chronology: "
                + fingerprint
            )
        incident_run_id = row.get("last_run_id")
        if (
            not isinstance(incident_run_id, str)
            or not RUN_ID_RE.fullmatch(incident_run_id) or ".." in incident_run_id
        ):
            errors.append("error-learning incident last run is invalid: " + fingerprint)
        evidence_hash = row.get("last_evidence_hash")
        if (
            not isinstance(evidence_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", evidence_hash)
        ):
            errors.append("error-learning incident evidence hash is invalid: " + fingerprint)
        if row.get("status") in {"OPEN", "REGRESSED"}:
            consecutive = row.get("consecutive_runs")
            if (
                row.get("resolved_at") is not None
                or not isinstance(consecutive, int) or isinstance(consecutive, bool)
                or consecutive < 1
            ):
                errors.append("open error-learning incident lifecycle is inconsistent: " + fingerprint)
        elif row.get("status") == "RESOLVED":
            resolved = _parse_utc(row.get("resolved_at"))
            if resolved is None or row.get("consecutive_runs") != 0:
                errors.append("resolved error-learning incident lifecycle is inconsistent: " + fingerprint)
            elif (
                last_seen is not None and resolved < last_seen
                or updated is not None and resolved > updated
            ):
                errors.append(
                    "resolved error-learning incident chronology is inconsistent: "
                    + fingerprint
                )
    for kind, row in actions.items():
        if not isinstance(row, dict) or row.get("kind") != kind:
            errors.append("error-learning action identity is malformed")
            continue
        if kind not in PRIORITY_ACTION_KINDS:
            errors.append("error-learning action kind is undeclared: " + str(kind))
        if row.get("status") not in {"OPEN", "REGRESSED", "RESOLVED"}:
            errors.append("error-learning action status is invalid: " + str(kind))
        for field in ("occurrences", "consecutive_runs", "regression_count"):
            value = row.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append("error-learning action count is invalid: %s.%s" %
                              (kind, field))
        if row.get("occurrences") == 0:
            errors.append("error-learning action occurrences must be positive: " + str(kind))
        if (
            isinstance(row.get("consecutive_runs"), int)
            and not isinstance(row.get("consecutive_runs"), bool)
            and isinstance(row.get("occurrences"), int)
            and not isinstance(row.get("occurrences"), bool)
            and row["consecutive_runs"] > row["occurrences"]
        ):
            errors.append("error-learning action consecutive count exceeds occurrences: " + str(kind))
        first_seen = _parse_utc(row.get("first_seen_at"))
        last_seen = _parse_utc(row.get("last_seen_at"))
        if first_seen is None or last_seen is None or last_seen < first_seen:
            errors.append("error-learning action timestamps are invalid: " + str(kind))
        elif updated is not None and last_seen > updated:
            errors.append(
                "error-learning action timestamp exceeds state chronology: "
                + str(kind)
            )
        action_run_id = row.get("last_run_id")
        if (
            not isinstance(action_run_id, str)
            or not RUN_ID_RE.fullmatch(action_run_id) or ".." in action_run_id
        ):
            errors.append("error-learning action last run is invalid: " + str(kind))
        if row.get("status") in {"OPEN", "REGRESSED"}:
            consecutive = row.get("consecutive_runs")
            if (
                row.get("resolved_at") is not None
                or not isinstance(consecutive, int) or isinstance(consecutive, bool)
                or consecutive < 1
            ):
                errors.append("open error-learning action lifecycle is inconsistent: " + str(kind))
        elif row.get("status") == "RESOLVED":
            resolved = _parse_utc(row.get("resolved_at"))
            if resolved is None or row.get("consecutive_runs") != 0:
                errors.append("resolved error-learning action lifecycle is inconsistent: " + str(kind))
            elif (
                last_seen is not None and resolved < last_seen
                or updated is not None and resolved > updated
            ):
                errors.append(
                    "resolved error-learning action chronology is inconsistent: "
                    + str(kind)
                )
    summary = state.get("summary")
    if not isinstance(summary, dict):
        errors.append("error-learning summary must be an object")
        summary = {}
    current_fingerprints = summary.get("current_fingerprints", [])
    if (
        not isinstance(current_fingerprints, list)
        or any(not isinstance(item, str) for item in current_fingerprints)
        or current_fingerprints != sorted(set(current_fingerprints))
    ):
        errors.append("error-learning current fingerprints must be a sorted unique list")
        current_fingerprints = []
    declared_current = summary.get("current_incidents")
    if declared_current != len(current_fingerprints):
        errors.append("error-learning current incident count is inconsistent")
    expected_open = sum(
        row.get("status") in {"OPEN", "REGRESSED"}
        for row in incidents.values() if isinstance(row, dict)
    )
    if summary.get("open_incidents") != expected_open:
        errors.append("error-learning open incident count is inconsistent")
    for fingerprint in current_fingerprints:
        if incidents.get(fingerprint, {}).get("status") not in {"OPEN", "REGRESSED"}:
            errors.append("error-learning current fingerprint is not open: " + fingerprint)
    for field in (
        "new_incidents", "recurring_incidents", "regressed_incidents",
        "resolved_incidents",
    ):
        values = summary.get(field)
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) for item in values)
            or values != sorted(set(values))
        ):
            errors.append("error-learning summary list is invalid: " + field)
    if current_findings is not None:
        expected = {_finding_fingerprint(row) for row in _learnable_findings(current_findings)}
        declared = set(current_fingerprints)
        if declared != expected:
            errors.append("error-learning current fingerprints contradict diagnosis")
        for fingerprint in expected:
            if incidents.get(fingerprint, {}).get("status") not in {"OPEN", "REGRESSED"}:
                errors.append("current incident is not open in error-learning state")
    return errors


def _committed_error_learning_snapshot(runs_root, run_id, *, now):
    """Load learning only from a terminal, validation-passed run commit."""
    if (
        not isinstance(now, dt.datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("error-learning current time must be timezone-aware")
    current = now.astimezone(dt.timezone.utc)
    root = Path(runs_root).resolve()
    if (
        not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id)
        or ".." in run_id
    ):
        raise ValueError("error-learning last run identity is unsafe")
    run_dir = (root / run_id).resolve()
    if run_dir.parent != root:
        raise ValueError("error-learning last run escapes the run root")
    try:
        run = _load(run_dir / "run.json")
        validation = _load(run_dir / "validation.json")
        snapshot = _load(run_dir / "error-learning.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "error-learning state is not bound to complete run evidence"
        ) from exc
    started = _parse_utc(run.get("started_at"))
    finished = _parse_utc(run.get("finished_at"))
    if (
        run.get("run_id") != run_id
        or run.get("status") not in {"COMPLETED", "COMPLETED_WITH_BLOCKERS"}
        or run.get("validation_passed") is not True
        or validation.get("passed") is not True
        or started is None or finished is None or finished < started
    ):
        raise ValueError(
            "error-learning state is not bound to a validated terminal run"
        )
    if started > current or finished > current:
        raise ValueError("error-learning terminal run timestamp is in the future")
    snapshot_errors = error_learning_state_errors(
        snapshot, not_before=started, not_after=min(finished, current)
    )
    if snapshot_errors:
        raise ValueError(
            "error-learning run snapshot is invalid: "
            + "; ".join(snapshot_errors)
        )
    if (
        snapshot.get("last_run_id") != run_id
        or run.get("error_learning_state_hash") != snapshot.get("state_hash")
    ):
        raise ValueError("error-learning run commit hash is mismatched")
    return finished, snapshot


def _load_error_learning_state(runs_root, *, now=None):
    """Load the latest validated learning commit, recovering a stale pointer.

    The per-run terminal marker is committed before the global pointer.  If a
    process stops between those writes, the next run can recover the newer
    validated snapshot without accepting a STARTED/FAILED run as learning.
    """
    current = now or dt.datetime.now(dt.timezone.utc)
    if (
        not isinstance(current, dt.datetime)
        or current.tzinfo is None
        or current.utcoffset() is None
    ):
        raise ValueError("error-learning current time must be timezone-aware")
    current = current.astimezone(dt.timezone.utc)
    root = Path(runs_root).resolve()
    path = root / ERROR_LEARNING_STATE_FILE
    state = _empty_error_learning_state()
    baseline_finished = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    if path.is_file():
        state = _load(path)
        errors = error_learning_state_errors(state, not_after=current)
        if errors:
            raise ValueError(
                "invalid error-learning state: " + "; ".join(errors)
            )
        last_run_id = state.get("last_run_id")
        if last_run_id is not None:
            try:
                baseline_finished, snapshot = (
                    _committed_error_learning_snapshot(
                        root, last_run_id, now=current
                    )
                )
            except ValueError as exc:
                raise ValueError("invalid error-learning state: " + str(exc)) from exc
            if snapshot != state:
                raise ValueError(
                    "invalid error-learning state: error-learning state "
                    "contradicts its last run snapshot"
                )

    latest = (baseline_finished, state)
    committed_candidates = []
    if root.is_dir():
        for run_dir in root.iterdir():
            if not run_dir.is_dir():
                continue
            try:
                run = _load(run_dir / "run.json")
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            finished = _parse_utc(run.get("finished_at"))
            if (
                run.get("run_id") != run_dir.name
                or run.get("status") not in {
                    "COMPLETED", "COMPLETED_WITH_BLOCKERS"
                }
                or run.get("validation_passed") is not True
                or finished is None or finished < baseline_finished
                or finished > current
            ):
                continue
            try:
                committed_finished, snapshot = (
                    _committed_error_learning_snapshot(
                        root, run_dir.name, now=current
                    )
                )
            except ValueError:
                # An unrelated corrupt terminal directory must not prevent a
                # valid committed pointer (or its intact descendants) from
                # being loaded.  The corrupt row is never accepted as state.
                continue
            committed_candidates.append(
                (committed_finished, run_dir.name, snapshot)
            )

    # Recover only a continuous state-hash chain.  Finished timestamps have
    # second precision, so equality is valid and cannot be used as the sole
    # ordering signal.  More than one successor of the same state is a fork,
    # which must fail closed instead of selecting an arbitrary branch.
    remaining = list(committed_candidates)
    while True:
        successors = [
            item for item in remaining
            if item[0] >= latest[0]
            and item[2].get("previous_state_hash") == latest[1].get(
                "state_hash"
            )
        ]
        if not successors:
            break
        if len(successors) != 1:
            raise ValueError(
                "invalid error-learning state: ambiguous recovery chain"
            )
        successor = successors[0]
        latest = (successor[0], successor[2])
        remaining.remove(successor)
    return latest[1]


def _finding_fingerprint(finding):
    identity = {
        "id": str(finding.get("id", "unknown")),
        "fact": str(finding.get("fact", "")),
    }
    return _canonical_hash(identity)


def _learnable_findings(findings):
    return [
        row for row in findings if isinstance(row, dict)
        and row.get("severity") in {"P0", "P1", "P2"}
        and isinstance(row.get("id"), str) and row.get("id")
        and isinstance(row.get("fact"), str) and row.get("fact")
    ]


def _incident_recency(row):
    parsed = _parse_utc(row.get("last_seen_at")) if isinstance(row, dict) else None
    return parsed or dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def build_error_learning_state(previous, diagnosis, *, run_id, observed_at,
                               max_incidents=500, recurring_after_runs=2,
                               now=None):
    """Learn incident recurrence, resolution and regression from a complete run.

    The fingerprint deliberately excludes volatile counts so the same root symptom
    can accumulate evidence across runs. Raw evidence is represented by a hash.
    """
    observed = _parse_utc(observed_at)
    if observed is None:
        raise ValueError("error-learning observed_at must be timezone-aware")
    current = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(current, dt.datetime) or current.tzinfo is None:
        raise ValueError("error-learning current time must be timezone-aware")
    current = current.astimezone(dt.timezone.utc)
    if observed > current:
        raise ValueError("error-learning observed_at cannot be in the future")
    previous_errors = error_learning_state_errors(previous, not_after=observed)
    if previous_errors:
        raise ValueError("previous error-learning state is invalid: " +
                         "; ".join(previous_errors))
    if (
        not isinstance(recurring_after_runs, int)
        or isinstance(recurring_after_runs, bool) or recurring_after_runs < 2
    ):
        raise ValueError("error-learning recurring threshold must be at least two")
    incidents = json.loads(json.dumps(previous.get("incidents", {})))
    actions = json.loads(json.dumps(previous.get("actions", {})))
    current_rows = {}
    for finding in _learnable_findings(diagnosis.get("findings", [])):
        current_rows[_finding_fingerprint(finding)] = finding

    new_ids = []
    regressed_ids = []
    recurring_ids = []
    resolved_ids = []
    for fingerprint, finding in sorted(current_rows.items()):
        prior = incidents.get(fingerprint)
        evidence_hash = _canonical_hash(finding.get("evidence"))
        if not isinstance(prior, dict):
            row = {
                "fingerprint": fingerprint,
                "finding_id": finding["id"],
                "severity": finding["severity"],
                "fact": finding["fact"],
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
                "occurrences": 1,
                "consecutive_runs": 1,
                "regression_count": 0,
                "status": "OPEN",
                "resolved_at": None,
                "last_evidence_hash": evidence_hash,
                "last_run_id": run_id,
            }
            new_ids.append(finding["id"])
        else:
            was_resolved = prior.get("status") == "RESOLVED"
            row = dict(prior)
            row.update({
                "severity": finding["severity"],
                "fact": finding["fact"],
                "last_seen_at": observed_at,
                "occurrences": int(prior.get("occurrences", 0)) + 1,
                "consecutive_runs": 1 if was_resolved else
                                    int(prior.get("consecutive_runs", 0)) + 1,
                "regression_count": int(prior.get("regression_count", 0)) +
                                    (1 if was_resolved else 0),
                "status": "REGRESSED" if was_resolved else "OPEN",
                "resolved_at": None,
                "last_evidence_hash": evidence_hash,
                "last_run_id": run_id,
            })
            if was_resolved:
                regressed_ids.append(finding["id"])
            if row["occurrences"] >= recurring_after_runs:
                recurring_ids.append(finding["id"])
        incidents[fingerprint] = row

    for fingerprint, prior in list(incidents.items()):
        if fingerprint in current_rows or not isinstance(prior, dict):
            continue
        if prior.get("status") in {"OPEN", "REGRESSED"}:
            prior = dict(prior)
            prior.update({"status": "RESOLVED", "resolved_at": observed_at,
                          "consecutive_runs": 0})
            incidents[fingerprint] = prior
            resolved_ids.append(str(prior.get("finding_id", "unknown")))

    current_actions = {
        row.get("type") for row in diagnosis.get("priorities", [])
        if isinstance(row, dict) and isinstance(row.get("type"), str)
    }
    for kind in sorted(set(actions) | current_actions):
        prior = actions.get(kind) if isinstance(actions.get(kind), dict) else {}
        if kind in current_actions:
            was_resolved = prior.get("status") == "RESOLVED"
            actions[kind] = {
                "kind": kind,
                "first_seen_at": prior.get("first_seen_at") or observed_at,
                "last_seen_at": observed_at,
                "occurrences": int(prior.get("occurrences", 0)) + 1,
                "consecutive_runs": 1 if was_resolved else
                                    int(prior.get("consecutive_runs", 0)) + 1,
                "regression_count": int(prior.get("regression_count", 0)) +
                                    (1 if was_resolved else 0),
                "status": "REGRESSED" if was_resolved else "OPEN",
                "resolved_at": None,
                "last_run_id": run_id,
            }
        elif prior.get("status") in {"OPEN", "REGRESSED"}:
            actions[kind] = {**prior, "status": "RESOLVED",
                             "resolved_at": observed_at,
                             "consecutive_runs": 0}

    if not isinstance(max_incidents, int) or isinstance(max_incidents, bool) or max_incidents < 1:
        raise ValueError("error-learning max_incidents must be a positive integer")
    if len(incidents) > max_incidents:
        open_rows = {key: row for key, row in incidents.items()
                     if row.get("status") != "RESOLVED"}
        if len(open_rows) > max_incidents:
            raise ValueError(
                "open error-learning incidents exceed the configured memory bound"
            )
        resolved_rows = sorted(
            ((key, row) for key, row in incidents.items()
             if row.get("status") == "RESOLVED"),
            key=lambda item: _incident_recency(item[1]), reverse=True,
        )
        room = max(0, max_incidents - len(open_rows))
        incidents = {**open_rows, **dict(resolved_rows[:room])}

    current_fingerprints = sorted(current_rows)
    open_count = sum(row.get("status") in {"OPEN", "REGRESSED"}
                     for row in incidents.values())
    state = {
        "schema_version": ERROR_LEARNING_SCHEMA,
        "updated_at": observed_at,
        "last_run_id": run_id,
        "previous_state_hash": previous.get("state_hash"),
        "incidents": incidents,
        "actions": actions,
        "summary": {
            "current_incidents": len(current_fingerprints),
            "open_incidents": open_count,
            "current_fingerprints": current_fingerprints,
            "new_incidents": sorted(set(new_ids)),
            "recurring_incidents": sorted(set(recurring_ids)),
            "regressed_incidents": sorted(set(regressed_ids)),
            "resolved_incidents": sorted(set(resolved_ids)),
        },
    }
    return _seal_error_learning_state(state)


def _priority_learning_key(priority, learning_state):
    history = learning_state.get("actions", {}) if isinstance(learning_state, dict) else {}
    row = history.get(priority.get("type"), {}) if isinstance(history, dict) else {}
    return (
        priority.get("rank", 99),
        -int(row.get("regression_count", 0) or 0),
        -int(row.get("consecutive_runs", 0) or 0),
        -int(row.get("occurrences", 0) or 0),
        priority.get("type", ""),
    )


def _operational_only_validation_errors(errors):
    prefixes = (
        "guard failure:", "official-source snapshot is missing",
        "decision readiness blocked:", "maturity evidence is stale or invalid",
        "maturity hard blockers:",
    )
    return bool(errors) and all(str(item).startswith(prefixes) for item in errors)


def _has_complete_evidence_bundle(run_dir, row, contract=None):
    """Return whether a terminal row represents a usable evidence bundle.

    FAILED is terminal for runner continuity, but an exception path can finish
    before observation/diagnosis/validation exist.  It must never refresh the
    evidence-age KPI.  Only schema-2 bundles have the cross-artifact hashes and
    recomputable scorecard contract required to prove completeness.  Older
    directories are historical diagnostics only; file presence must never
    refresh the current-evidence clock.
    """
    if not isinstance(row, dict) or row.get("status") not in {
        "COMPLETED", "COMPLETED_WITH_BLOCKERS", "FAILED_VALIDATION",
    }:
        return False
    if run_dir is None:
        return False
    required = (
        "observation.json", "diagnosis.json", "validation.json",
        "maturity-scorecard.json",
    )
    selected = Path(run_dir)
    if not all((selected / name).is_file() for name in required):
        return False
    try:
        observation = _load(selected / "observation.json")
        diagnosis = _load(selected / "diagnosis.json")
        validation = _load(selected / "validation.json")
        scorecard = _load(selected / "maturity-scorecard.json")
        if not all(isinstance(item, dict) for item in (
            observation, diagnosis, validation, scorecard
        )):
            return False
        # Canonicalization is also the finite-number check for every artifact.
        observation_hash = _canonical_hash(observation)
        diagnosis_hash = _canonical_hash(diagnosis)
        validation_hash = _canonical_hash(validation)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    started = _parse_utc(row.get("started_at"))
    finished = _parse_utc(row.get("finished_at"))
    if started is None or finished is None or finished < started:
        return False
    # Legacy bundles predate cross-artifact bindings.  Strict JSON proves only
    # parseability, not that the four files belonged to one validated run.  Do
    # not let an unbound legacy directory outrank current hash-valid evidence.
    if row.get("schema_version") != 2:
        return False
    evaluated = _parse_utc(scorecard.get("evaluated_at"))
    observed = _parse_utc(observation.get("observed_at"))
    if evaluated is None or observed is None:
        return False
    validation_passed = row.get("validation_passed")
    validation_errors = validation.get("errors")
    try:
        active_contract = contract or _load(CONTRACT)
        expected_scorecard = build_maturity_scorecard(
            observation,
            active_contract,
            cadence=scorecard.get("cadence"),
            now=evaluated,
            previous=None,
        )
    except (OSError, TypeError, ValueError, AttributeError, json.JSONDecodeError):
        return False
    # A chain of internally consistent hashes only proves that the files agree
    # with each other.  Recompute every observation-derived fact before a run
    # can refresh evidence age or become a weekly progression baseline.  The
    # progression itself is checked when the current run supplies the exact
    # prior baseline; it is intentionally excluded here because historical
    # discovery does not yet know that predecessor.
    evidence_fields = (
        "schema_version", "cadence", "observed_at", "evaluated_at",
        "policy_hash", "evidence_status", "score", "raw_score",
        "maximum_score", "stage", "hard_blockers", "criteria",
        "learning_ready", "learning_blockers", "next_data_actions",
        "evidence_hash",
    )
    evidence_matches = all(
        scorecard.get(key) == expected_scorecard.get(key)
        for key in evidence_fields
    )
    return bool(
        row.get("run_id") == selected.name
        and row.get("cadence") in {"daily", "weekly"}
        and scorecard.get("cadence") == row.get("cadence")
        and isinstance(validation_passed, bool)
        and validation.get("schema_version") == 2
        and validation.get("passed") is validation_passed
        and isinstance(validation_errors, list)
        and (not validation_passed or not validation_errors)
        and validation.get("control_state") in {
            "READY", "VALID_WITH_BLOCKERS", "INVALID"
        }
        and row.get("control_state") == validation.get("control_state")
        and observed is not None and started <= observed <= finished
        and evaluated is not None and started <= evaluated <= finished
        and _scorecard_hash_valid(scorecard)
        and evidence_matches
        and diagnosis.get("maturity_scorecard") == scorecard
        and row.get("maturity_score") == scorecard.get("score")
        and row.get("maturity_stage") == scorecard.get("stage")
        and validation.get("maturity_score") == scorecard.get("score")
        and validation.get("maturity_stage") == scorecard.get("stage")
        and row.get("maturity_scorecard_hash") == scorecard.get(
            "scorecard_hash"
        )
        and row.get("observation_hash") == observation_hash
        and row.get("diagnosis_hash") == diagnosis_hash
        and row.get("validation_hash") == validation_hash
    )


def _bound_path_matches(value, expected):
    if not isinstance(value, str) or not value:
        return False
    try:
        selected = Path(value).resolve(strict=False)
        required = Path(expected).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
    selected_text = str(selected)
    required_text = str(required)
    if os.name == "nt":
        selected_text = os.path.normcase(selected_text)
        required_text = os.path.normcase(required_text)
    return selected_text == required_text


def _task_receipt_contract_errors(
    receipt, *, task_name, run_id, current, trusted_producer_hashes=None
):
    """Validate the receipt fields used by control-health calculations.

    A self-hash alone only proves byte stability.  The consumer also checks the
    lifecycle, identities and transition facts before a receipt can enter a
    denominator or prove a terminal runner invocation.
    """
    if not isinstance(receipt, dict):
        return ["receipt is not an object"]
    if not isinstance(current, dt.datetime) or current.tzinfo is None:
        return ["receipt validation time is invalid"]
    current = current.astimezone(dt.timezone.utc)
    future_limit = current + task_run_receipt.RECEIPT_FUTURE_SKEW
    errors = []
    if not task_run_receipt.verify_receipt(receipt):
        errors.append("receipt hash is invalid")
    if receipt.get("schema_version") != task_run_receipt.SCHEMA_VERSION:
        errors.append("receipt schema is unsupported")
    task_contract = None
    try:
        task_contract = task_run_receipt._validate_task_contract_binding(receipt)
    except task_run_receipt.ReceiptError as exc:
        errors.append(str(exc))
    if receipt.get("task_name") != task_name or receipt.get("run_id") != run_id:
        errors.append("receipt identity is mismatched")
    if not task_run_receipt.SAFE_ID_RE.fullmatch(str(run_id)):
        errors.append("receipt run identity is unsafe")
    if receipt.get("origin") != "RUNNER_INVOCATION_UNVERIFIED":
        errors.append("receipt origin is unsupported")
    publication_state = receipt.get("publication_state")
    if not isinstance(publication_state, str) or publication_state not in {
        "BLOCKED_LOCAL_ONLY", "BLOCKED", "NOT_ATTEMPTED",
    }:
        errors.append("receipt publication state is invalid")
    if not isinstance(receipt.get("log_path"), str) or not receipt["log_path"]:
        errors.append("receipt log path is invalid")

    started = _parse_utc(receipt.get("started_at"))
    if started is None:
        errors.append("receipt start time is invalid")
    elif started > future_limit:
        errors.append("receipt start time is in the future")
    status = receipt.get("status")
    steps = receipt.get("steps")
    if not isinstance(steps, list):
        errors.append("receipt steps are invalid")
        steps = []
    step_ids = []
    previous_finished = started
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append("receipt step is malformed")
            continue
        step_id = step.get("step_id")
        if (
            not isinstance(step_id, str)
            or not task_run_receipt.SAFE_ID_RE.fullmatch(step_id)
        ):
            errors.append("receipt step identity is invalid")
        else:
            step_ids.append(step_id)
        sequence = step.get("sequence")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence != index
        ):
            errors.append("receipt step sequence is invalid")
        raw_rc = step.get("raw_rc")
        if not isinstance(raw_rc, int) or isinstance(raw_rc, bool):
            errors.append("receipt step exit code is invalid")
        step_wrapper = step.get("wrapper")
        if not isinstance(step_wrapper, str) or step_wrapper not in {
            "required", "graded", "internal"
        }:
            errors.append("receipt step wrapper is invalid")
        step_contract_name = step.get("contract")
        if not isinstance(step_contract_name, str) or not step_contract_name:
            errors.append("receipt step contract is invalid")
        for field in ("semantic_state", "classification_basis"):
            if not isinstance(step.get(field), str) or not step[field]:
                errors.append("receipt step %s is invalid" % field)
        execution_valid = step.get("execution_valid")
        if execution_valid is not None and not isinstance(execution_valid, bool):
            errors.append("receipt step execution validity is invalid")
        evidence_mode = step.get("evidence_mode")
        if not isinstance(evidence_mode, str) or evidence_mode not in {"record", "exec"}:
            errors.append("receipt step evidence mode is invalid")
        command_fields = {"executable", "argument_count", "command_hash"}
        if evidence_mode == "record":
            if (
                task_contract is not None
                and task_contract.get("enforcement") == "STRICT_ORDERED"
                and (
                    step.get("wrapper") != "internal"
                    or step.get("contract") != "internal-v1"
                )
            ):
                errors.append("receipt record step is not internal evidence")
            if command_fields.intersection(step):
                errors.append("receipt record step contains command evidence")
        elif evidence_mode == "exec":
            argument_count = step.get("argument_count")
            if (
                not isinstance(step.get("executable"), str)
                or not step["executable"]
                or not isinstance(argument_count, int)
                or isinstance(argument_count, bool)
                or argument_count < 0
                or not task_run_receipt.SHA256_RE.fullmatch(
                    str(step.get("command_hash", ""))
                )
            ):
                errors.append("receipt exec step command evidence is invalid")
        duration_ms = step.get("duration_ms")
        if (
            not isinstance(duration_ms, int) or isinstance(duration_ms, bool)
            or duration_ms < 0
        ):
            errors.append("receipt step duration is invalid")
        if (
            isinstance(raw_rc, int)
            and not isinstance(raw_rc, bool)
            and task_contract is not None
            and isinstance(step_wrapper, str)
            and isinstance(step_contract_name, str)
        ):
            try:
                expected = task_run_receipt.classify_step(
                    step_wrapper, step_contract_name, raw_rc,
                    classifier_version=task_contract["classifier_version"],
                )
            except task_run_receipt.ReceiptError as exc:
                errors.append(str(exc))
                expected = {}
            launch_error = step.get("launch_error")
            if "launch_error" in step and (
                not isinstance(launch_error, str) or not launch_error
            ):
                errors.append("receipt step launch error is invalid")
            if isinstance(launch_error, str) and launch_error:
                expected = {
                    "semantic_state": "RUNNER_FAILED",
                    "execution_valid": False,
                    "classification_basis": "child_launch_error",
                }
            for key, value in expected.items():
                if step.get(key) != value:
                    errors.append("receipt step classification is inconsistent")
                    break
        step_started = _parse_utc(step.get("started_at"))
        step_finished = _parse_utc(step.get("finished_at"))
        if step_started is None or step_finished is None:
            errors.append("receipt step timing is invalid")
        else:
            if step_finished < step_started:
                errors.append("receipt step timing is invalid")
            if previous_finished is not None and step_started < previous_finished:
                errors.append("receipt step chronology is invalid")
            if step_finished > future_limit:
                errors.append("receipt step time is in the future")
            previous_finished = step_finished
    if len(step_ids) != len(set(step_ids)):
        errors.append("receipt step identities are duplicated")
    try:
        task_run_receipt._validate_step_manifest_progress(receipt)
    except task_run_receipt.ReceiptError as exc:
        errors.append(str(exc))

    runner = receipt.get("runner")
    runner = runner if isinstance(runner, dict) else {}
    tool = receipt.get("receipt_tool")
    tool = tool if isinstance(tool, dict) else {}
    expected_runner = TASK_RECEIPT_RUNNER_PATHS.get(task_name)
    if expected_runner is None or not _bound_path_matches(
        runner.get("path"), expected_runner
    ):
        errors.append("receipt runner path is not bound to the monitored task")
    if not _bound_path_matches(tool.get("path"), TASK_RECEIPT_TOOL_PATH):
        errors.append("receipt tool path is not bound to the monitored producer")
    hash_pattern = re.compile(r"^[0-9a-f]{64}$")
    if not hash_pattern.fullmatch(str(runner.get("sha256_start", ""))):
        errors.append("receipt runner start hash is invalid")
    if not hash_pattern.fullmatch(str(tool.get("sha256_start", ""))):
        errors.append("receipt tool start hash is invalid")
    trusted_hashes = trusted_producer_hashes
    if trusted_hashes is None:
        trusted_hashes = [_path_sha256(TASK_RECEIPT_TOOL_PATH)]
    if (
        not isinstance(trusted_hashes, list)
        or not trusted_hashes
        or any(
            not isinstance(value, str)
            or not task_run_receipt.SHA256_RE.fullmatch(value)
            for value in (trusted_hashes or [])
        )
    ):
        errors.append("trusted receipt producer registry is invalid")
    elif tool.get("sha256_start") not in trusted_hashes:
        errors.append("receipt tool hash is not an attested producer")

    terminal = isinstance(status, str) and status in task_run_receipt.TERMINAL_STATUSES
    expected_transitions = len(steps) + (1 if terminal else 0)
    transition_counter = receipt.get("transition_counter")
    if (
        not isinstance(transition_counter, int)
        or isinstance(transition_counter, bool)
        or transition_counter != expected_transitions
    ):
        errors.append("receipt transition count is invalid")
    if status == "RUNNING":
        if any(receipt.get(key) is not None for key in (
            "terminal_kind", "terminal_reason", "terminal_step_id",
            "finished_at", "final_rc",
        )):
            errors.append("running receipt has terminal fields")
        if receipt.get("execution_state") != "RUNNING":
            errors.append("running receipt execution state is invalid")
        if runner.get("sha256_end") is not None or runner.get(
            "stable_during_run"
        ) is not None:
            errors.append("running receipt has end-run evidence")
        if tool.get("sha256_end") is not None or tool.get(
            "stable_during_run"
        ) is not None:
            errors.append("running receipt has receipt-tool end evidence")
    elif terminal:
        expected_kind = "end" if status == "FINISHED" else "abort"
        finished = _parse_utc(receipt.get("finished_at"))
        final_rc = receipt.get("final_rc")
        terminal_reason = receipt.get("terminal_reason")
        terminal_step_id = receipt.get("terminal_step_id")
        if receipt.get("terminal_kind") != expected_kind:
            errors.append("terminal receipt kind is invalid")
        if (
            not isinstance(terminal_reason, str)
            or not task_run_receipt.SAFE_ID_RE.fullmatch(terminal_reason)
        ):
            errors.append("terminal receipt reason is invalid")
        elif status == "FINISHED":
            if terminal_reason != "normal_end" or terminal_step_id is not None:
                errors.append("finished receipt has contradictory terminal evidence")
        elif terminal_reason == "normal_end":
            errors.append("aborted receipt uses normal-end reason")
        elif terminal_reason == "step_nonzero":
            last_step = steps[-1] if steps and isinstance(steps[-1], dict) else {}
            if (
                not isinstance(terminal_step_id, str)
                or terminal_step_id != last_step.get("step_id")
                or last_step.get("raw_rc") == 0
                or final_rc == 0
            ):
                errors.append("aborted receipt is not bound to its last non-zero step")
        elif terminal_step_id is not None:
            errors.append("non-step abort names a terminal step")
        if (
            finished is None
            or (previous_finished is not None and finished < previous_finished)
            or finished > future_limit
        ):
            errors.append("terminal receipt finish time is invalid")
        if not isinstance(final_rc, int) or isinstance(final_rc, bool):
            errors.append("terminal receipt final exit is invalid")
        state = receipt.get("execution_state")
        if not isinstance(state, str) or state not in {
            "PASS", "COMPLETED_WITH_BLOCKERS", "COMPLETED_BLOCKED",
            "UNVERIFIED_NONZERO", "RUNNER_FAILED",
        }:
            errors.append("terminal receipt execution state is invalid")
        runner_stable = runner.get("stable_during_run")
        if not isinstance(runner_stable, bool):
            errors.append("terminal receipt runner stability is invalid")
        elif runner_stable is False and state != "RUNNER_FAILED":
            errors.append("runner drift did not fail closed")
        runner_end_hash = runner.get("sha256_end")
        if not hash_pattern.fullmatch(str(runner_end_hash or "")):
            errors.append("receipt runner end hash is invalid")
        elif runner_stable is True and runner_end_hash != runner.get("sha256_start"):
            errors.append("terminal receipt runner hash stability is invalid")
        tool_stable = tool.get("stable_during_run")
        if not isinstance(tool_stable, bool):
            errors.append("terminal receipt tool stability is invalid")
        elif tool_stable is False and state != "RUNNER_FAILED":
            errors.append("receipt-tool drift did not fail closed")
        tool_end_hash = tool.get("sha256_end")
        if not hash_pattern.fullmatch(str(tool_end_hash or "")):
            errors.append("receipt tool end hash is invalid")
        elif tool_stable is True and tool_end_hash != tool.get("sha256_start"):
            errors.append("terminal receipt receipt-tool hash stability is invalid")
        if isinstance(final_rc, int) and not isinstance(final_rc, bool):
            try:
                expected_state = task_run_receipt._derive_execution_state(
                    receipt, expected_kind, final_rc,
                    terminal_reason=terminal_reason,
                    terminal_step_id=terminal_step_id,
                )
            except (TypeError, ValueError):
                errors.append("terminal receipt execution evidence is malformed")
                expected_state = None
            if runner_stable is False or tool_stable is False:
                expected_state = "RUNNER_FAILED"
            if expected_state is not None and state != expected_state:
                errors.append("terminal receipt execution state is inconsistent")
    else:
        errors.append("receipt lifecycle status is invalid")
    return list(dict.fromkeys(errors))


def _legacy_receipt_attestation_index(rows):
    errors = []
    index = {}
    identities = set()
    if not isinstance(rows, list):
        return {}, ["legacy receipt attestation registry is missing"]
    if not rows:
        return {}, []
    required = {
        "task_name", "run_id", "receipt_hash", "migration_state", "errors",
    }
    for row in rows:
        row_errors = []
        if not isinstance(row, dict) or set(row) != required:
            errors.append("legacy receipt attestation shape is invalid")
            continue
        task_name = row.get("task_name")
        run_id = row.get("run_id")
        receipt_hash = row.get("receipt_hash")
        migration_state = row.get("migration_state")
        reasons = row.get("errors")
        if task_name not in TASK_RECEIPT_NAMES:
            row_errors.append("legacy receipt attestation task is invalid")
        if not isinstance(run_id, str) or not task_run_receipt.SAFE_ID_RE.fullmatch(run_id):
            row_errors.append("legacy receipt attestation run identity is invalid")
        if not isinstance(receipt_hash, str) or not task_run_receipt.SHA256_RE.fullmatch(
            receipt_hash
        ):
            row_errors.append("legacy receipt attestation hash is invalid")
        if not isinstance(migration_state, str) or migration_state not in {
            "LEGACY_UNVALIDATED", "LEGACY_INVALID"
        }:
            row_errors.append("legacy receipt attestation state is invalid")
        if not isinstance(reasons, list) or any(
            not isinstance(reason, str) or not reason for reason in (reasons or [])
        ):
            row_errors.append("legacy receipt attestation errors are invalid")
        elif migration_state == "LEGACY_INVALID" and not reasons:
            row_errors.append("legacy invalid receipt is missing its prior errors")
        elif migration_state == "LEGACY_UNVALIDATED" and reasons:
            row_errors.append("legacy unvalidated receipt has contradictory errors")
        if row_errors:
            errors.extend(row_errors)
            continue
        identity = (task_name, run_id)
        key = (task_name, run_id, receipt_hash)
        if identity in identities:
            errors.append("legacy receipt attestation is duplicated")
        else:
            identities.add(identity)
            index[key] = row
    return index, list(dict.fromkeys(errors))


TASK_RECEIPT_ACTIVATION_TEST_PATHS = (
    "pipeline/test_task_run_receipt.py",
    "pipeline/test_improvement_loop.py",
    "pipeline/test_improvement_loop_wiring.py",
    "tools/test_improvement_policy.py",
    "tools/test_batch_exit_contract.py",
)


def _activation_test_sources_hash():
    rows = []
    for relative in TASK_RECEIPT_ACTIVATION_TEST_PATHS:
        digest = _path_sha256(ROOT / relative)
        if digest is None:
            return None
        rows.append({"path": relative, "sha256": digest})
    return _canonical_hash(rows)


def _activation_verification_errors(verification, activated_at):
    required = {
        "verified_at", "test_sources_sha256", "suite_results", "result_hash",
    }
    if not isinstance(verification, dict) or set(verification) != required:
        return ["task receipt activation verification is invalid"]
    errors = []
    verified_at = _parse_utc(verification.get("verified_at"))
    if (
        verified_at is None
        or activated_at is None
        or verified_at < activated_at
        or verified_at > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    ):
        errors.append("task receipt activation verification time is invalid")
    if verification.get("test_sources_sha256") != _activation_test_sources_hash():
        errors.append("task receipt activation test-source hash is invalid")
    expected_suites = {
        "task_receipt_tests", "improvement_loop_tests", "wiring_tests",
        "policy_tests", "batch_exit_tests",
    }
    suite_results = verification.get("suite_results")
    if not isinstance(suite_results, dict) or set(suite_results) != expected_suites:
        errors.append("task receipt activation suite results are invalid")
    else:
        for result in suite_results.values():
            if (
                not isinstance(result, dict)
                or set(result) != {"tests", "exit_code"}
                or not isinstance(result.get("tests"), int)
                or isinstance(result.get("tests"), bool)
                or result["tests"] < 1
                or result.get("exit_code") != 0
            ):
                errors.append("task receipt activation suite results are invalid")
                break
    unsigned = {
        key: value for key, value in verification.items() if key != "result_hash"
    }
    claimed_hash = verification.get("result_hash")
    if (
        not isinstance(claimed_hash, str)
        or not task_run_receipt.SHA256_RE.fullmatch(claimed_hash)
        or claimed_hash != _canonical_hash(unsigned)
    ):
        errors.append("task receipt activation verification hash is invalid")
    return list(dict.fromkeys(errors))


def _task_receipt_monitoring_errors(monitoring):
    """Validate the complete policy contract used to admit receipt evidence."""
    if not isinstance(monitoring, dict):
        return ["task receipt monitoring contract is missing"]
    errors = []
    required = {
        "schema_version", "instrumentation_started_at", "tasks",
        "contract_revision", "finished_requires_complete_manifest",
        "legacy_schema_policy", "legacy_receipt_attestations",
        "activation_attestation", "trusted_receipt_producer_sha256",
        "stuck_after_hours", "origin", "scheduler_launch_proven",
        "scheduler_sla_source",
    }
    if set(monitoring) != required:
        errors.append("task receipt monitoring contract shape is invalid")
    if monitoring.get("schema_version") != task_run_receipt.SCHEMA_VERSION:
        errors.append("task receipt monitoring schema must match the receipt producer")
    if monitoring.get("tasks") != list(TASK_RECEIPT_NAMES):
        errors.append("task receipt monitoring tasks are incomplete or reordered")
    if monitoring.get("contract_revision") != (
        "task-version-ordered-command-manifest-v3"
    ):
        errors.append("task receipt ordered-step contract revision is invalid")
    if monitoring.get("finished_requires_complete_manifest") is not True:
        errors.append("task receipt complete-manifest requirement is disabled")
    if not isinstance(monitoring.get("legacy_schema_policy"), str) or not (
        monitoring.get("legacy_schema_policy", "").strip()
    ):
        errors.append("task receipt legacy schema policy is missing")
    _, legacy_errors = _legacy_receipt_attestation_index(
        monitoring.get("legacy_receipt_attestations")
    )
    errors.extend(legacy_errors)
    instrumentation_at = _parse_utc(monitoring.get("instrumentation_started_at"))
    if instrumentation_at is None:
        errors.append("task receipt instrumentation start is invalid")

    activation = monitoring.get("activation_attestation")
    activation_required = {
        "activated_at", "receipt_producer_sha256", "receipt_consumer_sha256",
        "contract_registry_sha256", "verification",
    }
    if not isinstance(activation, dict) or set(activation) != activation_required:
        errors.append("task receipt activation attestation is invalid")
    else:
        activated_at = _parse_utc(activation.get("activated_at"))
        if activated_at is None or activated_at != instrumentation_at:
            errors.append("task receipt activation time is not exact")
        for field, actual_hash in (
            ("receipt_producer_sha256", _path_sha256(TASK_RECEIPT_TOOL_PATH)),
            ("receipt_consumer_sha256", _path_sha256(Path(__file__).resolve())),
            (
                "contract_registry_sha256",
                task_run_receipt.task_contract_registry_hash(),
            ),
        ):
            claimed = activation.get(field)
            if (
                not isinstance(claimed, str)
                or not task_run_receipt.SHA256_RE.fullmatch(claimed)
                or claimed != actual_hash
            ):
                errors.append("task receipt activation %s is invalid" % field)
        errors.extend(_activation_verification_errors(
            activation.get("verification"), activated_at
        ))

    trusted = monitoring.get("trusted_receipt_producer_sha256")
    trusted_valid = bool(
        isinstance(trusted, list)
        and trusted
        and all(
            isinstance(value, str)
            and task_run_receipt.SHA256_RE.fullmatch(value)
            for value in trusted
        )
        and len(trusted) == len(set(trusted))
    )
    if not trusted_valid:
        errors.append("trusted receipt producer registry is invalid")
    elif (
        isinstance(activation, dict)
        and activation.get("receipt_producer_sha256") not in trusted
    ):
        errors.append("activated receipt producer is not trusted")
    stuck_after = monitoring.get("stuck_after_hours")
    if (
        not isinstance(stuck_after, int)
        or isinstance(stuck_after, bool)
        or stuck_after != TASK_RECEIPT_STUCK_AFTER_HOURS
    ):
        errors.append("task receipt stuck threshold must match the bounded runner timeout")
    if monitoring.get("origin") != "RUNNER_INVOCATION_UNVERIFIED":
        errors.append("task receipt monitoring origin is invalid")
    if monitoring.get("scheduler_launch_proven") is not False:
        errors.append("task receipts must not claim a scheduler launch")
    if not isinstance(monitoring.get("scheduler_sla_source"), str) or not (
        monitoring.get("scheduler_sla_source", "").strip()
    ):
        errors.append("task receipt scheduler SLA boundary is missing")
    return list(dict.fromkeys(errors))


def _task_receipt_health(task_runs_root, *, current, cutoff,
                         instrumentation_started_at, current_identity=None,
                         stuck_after_hours=TASK_RECEIPT_STUCK_AFTER_HOURS,
                         monitoring_schema_version=None,
                         monitored_tasks=None,
                         legacy_receipt_attestations=None,
                         trusted_producer_hashes=None,
                         monitoring_contract_errors=None):
    """Measure attested command sequences without claiming a proven parent."""
    selected_root = Path(task_runs_root)
    valid_rows = []
    invalid_rows = []
    historical_invalid_rows = []
    pre_activation_rows = []
    legacy_rows = []
    matched_legacy_keys = set()
    legacy_index, legacy_registry_errors = _legacy_receipt_attestation_index(
        legacy_receipt_attestations
    )
    producer_registry_valid = bool(
        isinstance(trusted_producer_hashes, list)
        and trusted_producer_hashes
        and all(
            isinstance(value, str)
            and task_run_receipt.SHA256_RE.fullmatch(value)
            for value in trusted_producer_hashes
        )
        and len(trusted_producer_hashes) == len(set(trusted_producer_hashes))
    )
    instrumentation_at = _parse_utc(instrumentation_started_at)
    threshold_valid = bool(
        isinstance(stuck_after_hours, int)
        and not isinstance(stuck_after_hours, bool)
        and stuck_after_hours >= 1
    )
    monitoring_contract_valid = bool(
        monitoring_schema_version == task_run_receipt.SCHEMA_VERSION
        and isinstance(monitored_tasks, list)
        and monitored_tasks == list(TASK_RECEIPT_NAMES)
        and not legacy_registry_errors
        and producer_registry_valid
        and not monitoring_contract_errors
    )
    effective_stuck_hours = (
        stuck_after_hours if threshold_valid else TASK_RECEIPT_STUCK_AFTER_HOURS
    )
    for task_name in TASK_RECEIPT_NAMES:
        task_dir = selected_root / task_name
        if not task_dir.is_dir():
            continue
        candidate_paths = set(task_dir.glob("*.json"))
        marker_suffix = ".terminal-revoked"
        for marker in task_dir.glob(".*.json" + marker_suffix):
            canonical_name = marker.name[1:-len(marker_suffix)]
            candidate_paths.add(task_dir / canonical_name)
        for path in sorted(candidate_paths):
            run_id = path.stem
            try:
                task_run_receipt.assert_receipt_not_revoked(path)
                if path.stat().st_size > task_run_receipt.MAX_RECEIPT_BYTES:
                    raise task_run_receipt.ReceiptError(
                        "receipt exceeds the bounded evidence size"
                    )
                receipt = _load(path)
                task_run_receipt.assert_receipt_not_revoked(path)
            except (
                OSError,
                ValueError,
                json.JSONDecodeError,
                RecursionError,
                task_run_receipt.ReceiptError,
            ) as exc:
                detail = (
                    str(exc)
                    if isinstance(exc, task_run_receipt.ReceiptError)
                    else "receipt is unreadable: %s" % type(exc).__name__
                )
                invalid_rows.append({
                    "task_name": task_name,
                    "run_id": run_id,
                    "errors": [detail],
                })
                continue
            started = _parse_utc(receipt.get("started_at"))
            finished = _parse_utc(receipt.get("finished_at"))
            receipt_schema = receipt.get("schema_version")
            if receipt_schema != task_run_receipt.SCHEMA_VERSION:
                exact_legacy_schema = (
                    isinstance(receipt_schema, int)
                    and not isinstance(receipt_schema, bool)
                    and receipt_schema == 2
                )
                legacy_hash = receipt.get("receipt_hash")
                attestation = (
                    legacy_index.get((task_name, run_id, legacy_hash))
                    if isinstance(legacy_hash, str) else None
                )
                legacy_errors = []
                if not exact_legacy_schema:
                    legacy_errors.append("receipt schema is unsupported")
                if not task_run_receipt.verify_receipt(receipt):
                    legacy_errors.append("legacy receipt hash is invalid")
                if (
                    receipt.get("task_name") != task_name
                    or receipt.get("run_id") != run_id
                ):
                    legacy_errors.append("legacy receipt identity is mismatched")
                if receipt.get("origin") != "RUNNER_INVOCATION_UNVERIFIED":
                    legacy_errors.append("legacy receipt origin is unsupported")
                if instrumentation_at is None or started is None or started >= instrumentation_at:
                    legacy_errors.append("legacy receipt is outside the attested migration window")
                if attestation is None:
                    legacy_errors.append("legacy receipt is not exactly attested")
                if legacy_errors:
                    invalid_rows.append({
                        "task_name": task_name,
                        "run_id": run_id,
                        "errors": list(dict.fromkeys(legacy_errors)),
                    })
                    continue
                legacy_rows.append({
                    "task_name": task_name,
                    "run_id": run_id,
                    "schema_version": receipt_schema,
                    "status": receipt.get("status"),
                    "started_at": receipt.get("started_at"),
                    "receipt_hash": receipt.get("receipt_hash"),
                    "migration_state": attestation["migration_state"],
                    "artifact_state": "PRESENT",
                    "errors": list(attestation["errors"]),
                })
                matched_legacy_keys.add((task_name, run_id, legacy_hash))
                continue
            errors = _task_receipt_contract_errors(
                receipt, task_name=task_name, run_id=run_id,
                current=current, trusted_producer_hashes=trusted_producer_hashes,
            )
            pre_activation_identity_bound = bool(
                task_run_receipt.verify_receipt(receipt)
                and receipt.get("task_name") == task_name
                and receipt.get("run_id") == run_id
            )
            pre_activation = bool(
                instrumentation_at is not None
                and instrumentation_at <= current
                and started is not None
                and started < instrumentation_at
                and pre_activation_identity_bound
            )
            if started is not None and started > current:
                errors.append("receipt start time is in the future")
            if finished is not None and finished > current:
                errors.append("receipt finish time is in the future")
            if errors:
                invalid_row = {
                    "task_name": task_name,
                    "run_id": run_id,
                    "errors": list(dict.fromkeys(errors)),
                }
                if pre_activation:
                    # The activation epoch intentionally starts a new trusted
                    # KPI window.  A parseable current-schema receipt that
                    # started before that boundary remains visible for audit,
                    # but cannot poison or contribute to the new window.
                    invalid_row.update({
                        "schema_version": receipt_schema,
                        "status": receipt.get("status"),
                        "started_at": receipt.get("started_at"),
                        "finished_at": receipt.get("finished_at"),
                        "receipt_hash": receipt.get("receipt_hash"),
                        "classification": "PRE_ACTIVATION_INVALID",
                    })
                    historical_invalid_rows.append(invalid_row)
                    pre_activation_rows.append(invalid_row)
                elif started is not None and started < cutoff:
                    historical_invalid_rows.append(invalid_row)
                else:
                    # A future or unparseable start cannot prove that the bad
                    # artifact is outside the active window, so it remains an
                    # active fail-closed receipt error.
                    invalid_rows.append(invalid_row)
                continue
            if pre_activation:
                pre_activation_rows.append({
                    "task_name": task_name,
                    "run_id": run_id,
                    "schema_version": receipt_schema,
                    "status": receipt.get("status"),
                    "started_at": receipt.get("started_at"),
                    "finished_at": receipt.get("finished_at"),
                    "receipt_hash": receipt.get("receipt_hash"),
                    "classification": "PRE_ACTIVATION_VALID_DIAGNOSTIC_ONLY",
                    "errors": [],
                })
                continue
            valid_rows.append((task_name, receipt, started, finished))

    for key, attestation in legacy_index.items():
        if key in matched_legacy_keys:
            continue
        task_name, run_id, receipt_hash = key
        legacy_rows.append({
            "task_name": task_name,
            "run_id": run_id,
            "schema_version": 2,
            "status": None,
            "started_at": None,
            "receipt_hash": receipt_hash,
            "migration_state": attestation["migration_state"],
            "artifact_state": "MISSING_OR_MUTATED",
            "errors": [
                *list(attestation["errors"]),
                "legacy attested artifact is missing or mutated",
            ],
        })

    window = [
        row for row in valid_rows if cutoff <= row[2] <= current
    ]
    stuck_cutoff = current - dt.timedelta(hours=effective_stuck_hours)
    all_running_rows = [
        row for row in window if row[1].get("status") == "RUNNING"
    ]
    excluded_current = [
        row for row in all_running_rows
        if current_identity == (row[0], row[1].get("run_id"))
        and row[2] > stuck_cutoff
    ]
    eligible_window = [row for row in window if row not in excluded_current]
    terminal_rows = [
        row for row in eligible_window
        if row[1].get("status") in task_run_receipt.TERMINAL_STATUSES
    ]
    running_rows = [
        row for row in eligible_window if row[1].get("status") == "RUNNING"
    ]
    stuck_rows = [row for row in running_rows if row[2] <= stuck_cutoff]
    active_rows = [row for row in running_rows if row[2] > stuck_cutoff]

    # Coverage is a per-task assertion.  Seeing one task cannot prove that the
    # other monitored runner was instrumented throughout the same window.  Keep
    # this separate from scheduler correlation: MISSING means "no trustworthy
    # receipt for this task in the control window", not that a scheduled slot
    # was necessarily missed.
    active_presence_rows = [
        row for row in all_running_rows if row[2] > stuck_cutoff
    ]
    per_task_coverage = {}
    for task_name in TASK_RECEIPT_NAMES:
        task_invalid = [
            row for row in invalid_rows if row.get("task_name") == task_name
        ]
        task_terminal = [row for row in terminal_rows if row[0] == task_name]
        task_stuck = [row for row in stuck_rows if row[0] == task_name]
        task_active = [
            row for row in active_presence_rows if row[0] == task_name
        ]
        task_window = [row for row in window if row[0] == task_name]
        if task_invalid:
            task_state = "INVALID"
        elif task_terminal:
            task_state = "OBSERVED"
        elif task_stuck:
            task_state = "STUCK"
        elif task_active:
            task_state = "ACTIVE_ONLY"
        else:
            task_state = "MISSING"
        per_task_coverage[task_name] = {
            "state": task_state,
            "window_observed": len(task_window),
            "window_terminal": len(task_terminal),
            "window_active": len(task_active),
            "window_stuck": len(task_stuck),
            "invalid_receipts": len(task_invalid),
        }

    if (
        instrumentation_at is None or instrumentation_at > current
        or not threshold_valid or not monitoring_contract_valid
    ):
        coverage_state = "INVALID_MONITORING_CONTRACT"
    elif invalid_rows:
        coverage_state = "INVALID_RECEIPTS"
    elif not valid_rows:
        coverage_state = "NO_RECEIPTS"
    elif instrumentation_at > cutoff:
        coverage_state = "PARTIAL_WINDOW"
    elif any(
        item["state"] != "OBSERVED" for item in per_task_coverage.values()
    ):
        coverage_state = "INCOMPLETE_TASK_COVERAGE"
    else:
        coverage_state = "FULL_WINDOW"
    # A still-active invocation has not yet had the opportunity to write a
    # terminal receipt, so it is diagnostic state rather than a rate failure.
    # A RUNNING receipt becomes accountable only after the bounded task timeout
    # and is then counted as stuck in the denominator.
    denominator = len(terminal_rows) + len(stuck_rows)
    observed_rate = (
        len(terminal_rows) / denominator if denominator else None
    )
    trusted_rate = observed_rate if coverage_state == "FULL_WINDOW" else None
    states = [row[1].get("execution_state") for row in terminal_rows]
    completed_blocked = sum(
        row[1].get("status") == "ABORTED"
        and row[1].get("execution_state") == "COMPLETED_BLOCKED"
        for row in terminal_rows
    )
    return {
        "coverage_state": coverage_state,
        "origin": "RUNNER_INVOCATION_UNVERIFIED",
        "scheduler_launch_proven": False,
        "per_task_coverage": per_task_coverage,
        "missing_window_tasks": [
            task_name for task_name, item in per_task_coverage.items()
            if item["state"] == "MISSING"
        ],
        "window_observed": len(window),
        "window_started": len(eligible_window),
        "window_settled": len(terminal_rows) + len(stuck_rows),
        "window_rate_denominator": denominator,
        "window_terminal": len(terminal_rows),
        "window_active": len(active_rows),
        "window_stuck": len(stuck_rows),
        "excluded_current_running_receipt": len(excluded_current),
        "window_runner_failed": states.count("RUNNER_FAILED"),
        "window_unverified_nonzero": states.count("UNVERIFIED_NONZERO"),
        "window_completed_with_blockers": states.count(
            "COMPLETED_WITH_BLOCKERS"
        ),
        "window_completed_blocked": completed_blocked,
        "observed_publication_blocker_false_fatals": completed_blocked,
        "observed_terminal_rate": observed_rate,
        "trusted_terminal_rate": trusted_rate,
        "invalid_receipt_count": len(invalid_rows),
        "invalid_receipts": invalid_rows,
        "historical_invalid_receipt_count": len(historical_invalid_rows),
        "historical_invalid_receipts": historical_invalid_rows,
        "pre_activation_receipt_count": len(pre_activation_rows),
        "pre_activation_valid_receipt_count": sum(
            row.get("classification") == "PRE_ACTIVATION_VALID_DIAGNOSTIC_ONLY"
            for row in pre_activation_rows
        ),
        "pre_activation_receipts": pre_activation_rows,
        "pre_activation_invalid_receipt_count": sum(
            row.get("classification") == "PRE_ACTIVATION_INVALID"
            for row in pre_activation_rows
        ),
        "legacy_receipt_count": len(legacy_rows),
        "legacy_receipts": legacy_rows,
        "legacy_artifact_missing_count": sum(
            row.get("artifact_state") == "MISSING_OR_MUTATED"
            for row in legacy_rows
        ),
        "legacy_invalid_receipt_count": sum(
            row.get("migration_state") == "LEGACY_INVALID" for row in legacy_rows
        ),
        "legacy_unvalidated_receipt_count": sum(
            row.get("migration_state") == "LEGACY_UNVALIDATED"
            for row in legacy_rows
        ),
        "legacy_attestation_registry_errors": legacy_registry_errors,
        "all_invalid_receipt_count": (
            len(invalid_rows) + len(historical_invalid_rows)
            + sum(
                row.get("migration_state") == "LEGACY_INVALID"
                for row in legacy_rows
            )
        ),
        "instrumentation_started_at": (
            instrumentation_at.isoformat(timespec="seconds")
            if instrumentation_at is not None else None
        ),
        "stuck_after_hours": effective_stuck_hours,
        "monitoring_schema_version": monitoring_schema_version,
        "monitoring_contract_valid": monitoring_contract_valid,
        "monitoring_contract_errors": list(monitoring_contract_errors or []),
    }


def assess_current_evidence(run_dir, row, *, now=None, contract=None):
    """Reassess a saved bundle for today's decisions without rewriting it.

    Internal bundle integrity and its historical score do not attest to current
    files. Freshness starts at observation, not the end of a slow guard run.
    """
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ValueError("evidence evaluation time must be timezone-aware")
    result = {
        "run_id": row.get("run_id") if isinstance(row, dict) else None,
        "state": "UNKNOWN", "decision_state": "UNKNOWN",
        "historical_score": None, "current_score": None,
        "observation_age_hours": None, "changed_inputs": [], "errors": [],
    }
    try:
        contract = contract or _load(CONTRACT)
        if not _has_complete_evidence_bundle(run_dir, row, contract):
            raise ValueError("no complete hash-valid evidence bundle")
        root = Path(run_dir).resolve()
        observation = _load(root / "observation.json")
        scorecard = _load(root / "maturity-scorecard.json")
        result["historical_score"] = scorecard.get("score")
        finished = _parse_utc(row.get("finished_at"))
        if finished is None or finished > current:
            raise ValueError("bundle completion is in the future or invalid")
        fresh, age, freshness_error = _observation_freshness(
            observation, row.get("cadence"), contract, current
        )
        result["observation_age_hours"] = age
        validation = _load(root / "validation.json")
        if (
            row.get("status") not in {"COMPLETED", "COMPLETED_WITH_BLOCKERS"}
            or row.get("validation_passed") is not True
            or validation.get("passed") is not True
            or validation.get("control_state") not in {"READY", "VALID_WITH_BLOCKERS"}
        ):
            result.update(state="INVALID", decision_state="BLOCKED")
            result["errors"].append("saved control validation did not pass")
            return result
        runtime = observation.get("runtime_contract")
        errors = runtime_contract_errors(runtime)
        if errors:
            raise ValueError("; ".join(errors))
        current_runtime = collect_runtime_contract()
        old_inputs = {item["path"]: item for item in runtime["files"]}
        new_inputs = {item["path"]: item for item in current_runtime["files"]}
        result["changed_inputs"] = sorted(
            name for name in old_inputs.keys() | new_inputs.keys()
            if old_inputs.get(name) != new_inputs.get(name)
        )
        evidence_errors = readiness_file_evidence_errors(
            observation.get("decision_readiness", {}), root
        )
        guards = observation.get("guards")
        if not isinstance(guards, dict):
            raise ValueError("guard evidence map is invalid")
        for name, guard in guards.items():
            try:
                relative = Path(guard["evidence_path"])
                if relative.is_absolute():
                    raise ValueError("absolute guard evidence path")
                path = (root / relative).resolve()
                path.relative_to(root)
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != guard.get("evidence_sha256"):
                    raise ValueError("guard evidence hash mismatch")
            except (KeyError, TypeError, ValueError, OSError):
                evidence_errors.append("guard output unavailable or changed: " + str(name))
        if evidence_errors:
            raise ValueError("; ".join(evidence_errors))
        if result["changed_inputs"]:
            result.update(state="INPUT_DRIFT", decision_state="BLOCKED")
            result["errors"].append("current inputs differ from the saved bundle")
        elif not fresh:
            result.update(state="STALE", decision_state="BLOCKED")
        else:
            # Child analytics/revenue/source evidence can expire within the
            # outer observation SLA. Recompute against the actual decision time.
            current_scorecard = build_maturity_scorecard(
                observation, contract, cadence=row["cadence"], now=current
            )
            if current_scorecard.get("evidence_status") != "CURRENT":
                result.update(state="INVALID", decision_state="BLOCKED")
                result["errors"].append(
                    "child evidence is no longer current or internally valid"
                )
            else:
                saved_ready = (
                    row.get("status") == "COMPLETED"
                    and validation.get("control_state") == "READY"
                    and validation.get("operational_blockers") == []
                )
                result.update(
                    state="CURRENT", current_score=current_scorecard["score"],
                    decision_state="BLOCKED" if (
                        current_scorecard["hard_blockers"] or not saved_ready
                    )
                    else "READY_FOR_OWNER_APPROVAL",
                )
        if freshness_error:
            result["errors"].append(freshness_error)
    except (KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        result["errors"].append(str(exc))
    return result


def build_control_health(runs_root, learning_state, *, now=None,
                         current_state=None, task_runs_root=None,
                         receipt_monitoring=None, current_task_identity=None):
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ValueError("control-health time must be timezone-aware")
    current = current.astimezone(dt.timezone.utc)
    cutoff = current - dt.timedelta(days=7)
    rows = []
    selected_root = Path(runs_root).resolve()
    if selected_root.is_dir():
        for run_dir in selected_root.iterdir():
            if (
                not RUN_ID_RE.fullmatch(run_dir.name)
                or ".." in run_dir.name
                or run_dir.resolve().parent != selected_root
                or not run_dir.is_dir()
            ):
                continue
            try:
                row = _load(run_dir / "run.json")
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            if current_state and row.get("run_id") == current_state.get("run_id"):
                continue
            rows.append((run_dir, row))
    if isinstance(current_state, dict):
        current_run_dir = None
        current_run_id = current_state.get("run_id")
        if (
            isinstance(current_run_id, str)
            and RUN_ID_RE.fullmatch(current_run_id)
            and ".." not in current_run_id
        ):
            candidate = (selected_root / current_run_id).resolve()
            if candidate.parent == selected_root.resolve() and candidate.is_dir():
                current_run_dir = candidate
        rows.append((current_run_dir, current_state))
    window = []
    latest_terminal = None
    latest_bundle = None
    legacy_unproven_false_fatal_signals = 0
    for run_dir, row in rows:
        started = _parse_utc(row.get("started_at"))
        finished = _parse_utc(row.get("finished_at"))
        terminal = bool(finished and row.get("status") in TERMINAL_RUN_STATES)
        evidence_complete = bool(
            started is not None
            and finished is not None
            and started <= finished <= current
            and _has_complete_evidence_bundle(run_dir, row)
        )
        if evidence_complete and (latest_terminal is None or finished > latest_terminal):
            latest_terminal = finished
            latest_bundle = (run_dir, row)
        if started is not None and cutoff <= started <= current:
            window.append((run_dir, row, terminal))
        if (
            row.get("status") == "FAILED_VALIDATION" and run_dir is not None
            and started is not None and cutoff <= started <= current
        ):
            try:
                validation = _load(run_dir / "validation.json")
            except (OSError, ValueError, json.JSONDecodeError):
                validation = {}
            if _operational_only_validation_errors(validation.get("errors", [])):
                legacy_unproven_false_fatal_signals += 1
    bundle_started_count = len(window)
    bundle_terminal_count = sum(1 for _, _, terminal in window if terminal)
    receipt_root = (
        Path(task_runs_root) if task_runs_root is not None
        else selected_root.parent / "task-runs"
    )
    monitoring = receipt_monitoring
    if monitoring is None:
        try:
            monitoring = _load(CONTRACT).get("task_receipt_monitoring", {})
        except (OSError, ValueError, json.JSONDecodeError):
            monitoring = {}
    monitoring = monitoring if isinstance(monitoring, dict) else {}
    monitoring_errors = _task_receipt_monitoring_errors(monitoring)
    if current_task_identity is None:
        env_task = os.environ.get("NGERNDUANGOLD_TASK_NAME")
        env_run = os.environ.get("NGERNDUANGOLD_TASK_RUN_ID")
        if env_task in TASK_RECEIPT_NAMES and isinstance(env_run, str) and (
            task_run_receipt.SAFE_ID_RE.fullmatch(env_run)
        ):
            current_task_identity = (env_task, env_run)
    receipt_health = _task_receipt_health(
        receipt_root, current=current, cutoff=cutoff,
        instrumentation_started_at=monitoring.get(
            "instrumentation_started_at"
        ),
        current_identity=current_task_identity,
        stuck_after_hours=monitoring.get(
            "stuck_after_hours", TASK_RECEIPT_STUCK_AFTER_HOURS
        ),
        monitoring_schema_version=monitoring.get("schema_version"),
        monitored_tasks=monitoring.get("tasks"),
        legacy_receipt_attestations=monitoring.get(
            "legacy_receipt_attestations", []
        ),
        trusted_producer_hashes=monitoring.get(
            "trusted_receipt_producer_sha256",
            [_path_sha256(TASK_RECEIPT_TOOL_PATH)],
        ),
        monitoring_contract_errors=monitoring_errors,
    )
    incidents = learning_state.get("incidents", {}) if isinstance(
        learning_state, dict
    ) else {}
    incidents = incidents if isinstance(incidents, dict) else {}
    learning_last_run = learning_state.get("last_run_id") if isinstance(
        learning_state, dict
    ) else None
    recurring_fingerprint_count = sum(
        isinstance(row, dict)
        and row.get("status") in {"OPEN", "REGRESSED"}
        and isinstance(row.get("occurrences"), int)
        and not isinstance(row.get("occurrences"), bool)
        and row.get("occurrences") >= 2
        for row in incidents.values()
    )
    regressed_fingerprint_count = sum(
        isinstance(row, dict)
        and row.get("status") == "REGRESSED"
        and row.get("last_run_id") == learning_last_run
        for row in incidents.values()
    )
    observed_false_fatal = receipt_health[
        "observed_publication_blocker_false_fatals"
    ]
    trusted_false_fatal = (
        observed_false_fatal
        if receipt_health["coverage_state"] == "FULL_WINDOW"
        else None
    )
    current_evidence = assess_current_evidence(
        *(latest_bundle or (None, None)), now=current
    )
    state = {
        "schema_version": 3,
        "evaluated_at": current.isoformat(timespec="seconds"),
        "window_days": 7,
        "kpis": {
            "terminal_control_run_rate_7d": (
                receipt_health["trusted_terminal_rate"]
            ),
            "observed_terminal_control_run_rate_7d":
                receipt_health["observed_terminal_rate"],
            "task_receipt_coverage_state": receipt_health["coverage_state"],
            "started_runs_7d": receipt_health["window_started"],
            "settled_runs_7d": receipt_health["window_settled"],
            "terminal_runs_7d": receipt_health["window_terminal"],
            "active_runs_7d": receipt_health["window_active"],
            "stuck_runs_7d": receipt_health["window_stuck"],
            "runner_failed_runs_7d": receipt_health["window_runner_failed"],
            "unverified_nonzero_runs_7d":
                receipt_health["window_unverified_nonzero"],
            "completed_blocked_runs_7d":
                receipt_health["window_completed_blocked"],
            "completed_with_blockers_runs_7d":
                receipt_health["window_completed_with_blockers"],
            "invalid_task_receipts": receipt_health["invalid_receipt_count"],
            "recurring_open_incidents": recurring_fingerprint_count,
            "regressed_incidents_per_run": regressed_fingerprint_count,
            "publication_blocker_false_fatal_count": trusted_false_fatal,
            "observed_publication_blocker_false_fatal_count":
                observed_false_fatal,
            "legacy_unproven_false_fatal_signals":
                legacy_unproven_false_fatal_signals,
            "fresh_evidence_age_hours": (
                current_evidence["observation_age_hours"]
            ),
        },
        "targets": {
            "terminal_control_run_rate_7d": 1.0,
            "recurring_open_incidents": 0,
            "regressed_incidents_per_run": 0,
            "publication_blocker_false_fatal_count": 0,
        },
        "learning_state_hash": learning_state.get("state_hash")
        if isinstance(learning_state, dict) else None,
        "task_receipts": receipt_health,
        "current_evidence": current_evidence,
        "improvement_bundles": {
            "started_7d": bundle_started_count,
            "terminal_7d": bundle_terminal_count,
            "terminal_rate_7d": (
                bundle_terminal_count / bundle_started_count
                if bundle_started_count else None
            ),
            "note": (
                "diagnostic only; improvement bundles cannot observe runner "
                "failures that occur before improvement_loop starts"
            ),
        },
    }
    state["health_hash"] = _canonical_hash(state)
    return state


def _event(run_dir, phase, status, detail=""):
    row = {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "phase": phase,
        "status": status,
        "detail": detail,
    }
    with (run_dir / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _guard_output_evidence(parts, run_dir, output):
    """Persist complete subprocess evidence privately and return a bounded view."""
    output = output if isinstance(output, str) else str(output or "")
    encoded = output.encode("utf-8")
    identity = hashlib.sha256(
        json.dumps(list(parts), ensure_ascii=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    stem = Path(str(parts[0])).stem or "guard"
    relative = Path("guard-evidence") / "subprocess" / (
        "%s-%s.txt" % (stem, identity)
    )
    path = Path(run_dir) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8", newline="\n")
    lines = output.splitlines()
    summary_lines = lines if len(lines) <= 8 else [lines[0], *lines[-7:]]
    return {
        "evidence_path": relative.as_posix(),
        "evidence_sha256": hashlib.sha256(encoded).hexdigest(),
        "evidence_bytes": len(encoded),
        "evidence_lines": len(lines),
        "summary": "\n".join(summary_lines)[:2000],
    }


def _run_private_posting_plan_guard(run_dir):
    """Run post_guard with generated evidence redirected to this private run."""
    module_path = ROOT / "tools" / "post_guard.py"
    spec = importlib.util.spec_from_file_location("improvement_post_guard", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("post guard cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    private_output = run_dir / "guard-evidence" / "post-guard"
    module.POST_GUARD_DIR = private_output
    module.HISTORY_PATH = private_output / "history.jsonl"
    stdout = io.StringIO()
    stderr = io.StringIO()
    previous_argv = sys.argv
    try:
        sys.argv = [str(module_path), "--json"]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return_code = int(module.main())
    finally:
        sys.argv = previous_argv
    evidence = _guard_output_evidence(
        ["@private_posting_plan"], run_dir,
        stdout.getvalue() + stderr.getvalue(),
    )
    return {
        "exit_code": return_code,
        "passed": return_code == 0,
        "process_state": (
            "PASS" if return_code == 0
            else "COMPLETED_BLOCKED" if return_code in {1, 2}
            else "RUNNER_FAILED"
        ),
        "timeout_seconds": None,
        **evidence,
    }


def _run_guard(parts, run_dir):
    if parts == ["@private_posting_plan"]:
        try:
            return _run_private_posting_plan_guard(run_dir)
        except Exception as exc:
            return {
                "exit_code": 3,
                "passed": False,
                "process_state": "RUNNER_FAILED",
                "timeout_seconds": None,
                "summary": "posting-plan guard unavailable (%s)" % type(exc).__name__,
            }
    runtime_launcher = GUARD_RUNTIME_LAUNCHERS.get(parts[0])
    command = (
        [str(runtime_launcher), str(ROOT / parts[0]), *parts[1:]]
        if runtime_launcher is not None
        else [sys.executable, str(ROOT / parts[0]), *parts[1:]]
    )
    timeout_seconds = GUARD_TIMEOUT_SECONDS.get(
        parts[0], DEFAULT_GUARD_TIMEOUT_SECONDS
    )
    try:
        result = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=timeout_seconds, check=False)
        stdout = result.stdout or ""
        evidence = _guard_output_evidence(
            parts, run_dir, stdout + (result.stderr or "")
        )
        rc = int(result.returncode)
        guard = {
            "exit_code": rc,
            "passed": rc == 0,
            "process_state": (
                "PASS" if rc == 0 else "COMPLETED_BLOCKED" if rc in {1, 2}
                else "RUNNER_FAILED"
            ),
            "timeout_seconds": timeout_seconds,
            **evidence,
        }
        if "--json" in parts:
            try:
                guard["payload"] = json.loads(stdout)
            except (TypeError, ValueError):
                guard["payload"] = None
        return guard
    except Exception as exc:
        return {
            "exit_code": 3,
            "passed": False,
            "process_state": "RUNNER_FAILED",
            "timeout_seconds": timeout_seconds,
            "summary": "guard unavailable (%s)" % type(exc).__name__,
        }


def _local_safe_live_release_result(run_dir=None):
    """Return hash-bound UNKNOWN evidence without making a network request.

    Local-safe control runs are observational but local-only.  A live parity
    check is therefore unavailable unless an authorized caller injects a
    separately collected ``live_release_result``.  Persist the protected
    non-action as the complete release evidence for normal control runs so the
    readiness bundle stays auditable and fail-closed.
    """
    output = LOCAL_SAFE_LIVE_RELEASE_SUMMARY
    if run_dir is not None:
        evidence = _guard_output_evidence(
            ["@local_safe_live_release_not_probed"], Path(run_dir), output
        )
    else:
        encoded = output.encode("utf-8")
        evidence = {
            # Standalone readiness callers have no run directory.  Keep a
            # structurally valid but deliberately unavailable artifact path;
            # any later file-evidence validation will fail closed.
            "evidence_path": (
                "guard-evidence/subprocess/"
                "local-safe-live-release-not-probed.txt"
            ),
            "evidence_sha256": hashlib.sha256(encoded).hexdigest(),
            "evidence_bytes": len(encoded),
            "evidence_lines": len(output.splitlines()),
            "summary": output,
        }
    return {
        "exit_code": 2,
        "passed": False,
        "process_state": "COMPLETED_BLOCKED",
        "timeout_seconds": None,
        **evidence,
    }


def evaluate_decision_readiness(observation, policy, calendar_result,
                                live_release_result, target_channel=None):
    """Return one fail-closed gate for growth and publication decisions.

    Raw observations may still be reported while blocked.  A missing, malformed,
    false or zero readiness fact is a blocker; only explicit positive evidence
    can authorize a growth experiment or winner-driven draft generation.
    """
    blockers = []
    checks = {}

    channels = policy.get("channels") if isinstance(policy, dict) else None
    channels = channels if isinstance(channels, dict) else {}
    normalized_target = str(target_channel).strip().lower() if target_channel else None

    def channel_is_authorized(channel):
        return bool(isinstance(channel, dict)
                    and channel.get("publication_authorized") is True)

    # Publication authority is candidate/channel scoped.  Treat an omitted
    # target as unknown instead of allowing an authorized channel elsewhere in
    # policy to combine with an unrelated publishable calendar count.  The
    # inventory remains diagnostic; it cannot satisfy the execution gate.
    available_authorized_channels = sorted(
        name for name, channel in channels.items()
        if isinstance(name, str) and channel_is_authorized(channel)
    )
    if normalized_target:
        channel = channels.get(normalized_target)
        authorized_channels = (
            [normalized_target] if channel_is_authorized(channel) else []
        )
    else:
        authorized_channels = []
    authority_ready = bool(authorized_channels)
    checks["publication_authority"] = {
        "passed": authority_ready,
        "target_channel": normalized_target,
        "authorized_channels": authorized_channels,
        "available_authorized_channels": available_authorized_channels,
    }
    if not authority_ready:
        blockers.append("publication_authority_false")

    calendar_payload = (
        calendar_result.get("payload")
        if isinstance(calendar_result, dict) else None
    )
    calendar_payload = calendar_payload if isinstance(calendar_payload, dict) else {}
    calendar_counts = calendar_payload.get("counts")
    calendar_counts = calendar_counts if isinstance(calendar_counts, dict) else {}
    publishable = calendar_counts.get("publishable")
    publishable_valid = (
        isinstance(publishable, int) and not isinstance(publishable, bool)
        and publishable >= 0
    )
    process_state = calendar_payload.get("process_state")
    calendar_exit = (
        calendar_result.get("exit_code")
        if isinstance(calendar_result, dict) else None
    )
    process_valid = bool(
        process_state in CALENDAR_PROCESS_EXIT
        and isinstance(calendar_exit, int) and not isinstance(calendar_exit, bool)
        and calendar_exit == CALENDAR_PROCESS_EXIT[process_state]
    )
    calendar_execution_valid = bool(
        process_valid and process_state != "RUNNER_FAILED"
    )
    calendar_guard_ready = bool(
        process_valid and process_state in {"PASS", "COMPLETED_BLOCKED"}
    )
    calendar_ready = bool(calendar_guard_ready and publishable_valid and publishable > 0)
    calendar_summary = (
        calendar_result.get("summary")
        if isinstance(calendar_result, dict)
        and isinstance(calendar_result.get("summary"), str)
        and calendar_result.get("summary").strip()
        else "no calendar guard summary was captured"
    )
    checks["content_calendar"] = {
        "passed": calendar_ready,
        "execution_valid": calendar_execution_valid,
        "guard_passed": calendar_guard_ready,
        "process_state": process_state,
        "exit_code": calendar_exit,
        "publishable": publishable if publishable_valid else None,
        "summary": calendar_summary[:2000],
        "payload": calendar_payload,
        "payload_hash": _canonical_hash(calendar_payload),
    }
    if not calendar_execution_valid:
        blockers.append("content_calendar_guard_failed")
    elif process_state == "STRUCTURAL_FINDINGS":
        blockers.append("content_calendar_structural_findings")
    elif process_state == "BLOCKED":
        blockers.append("content_calendar_blocked")
    elif not publishable_valid or publishable == 0:
        blockers.append("content_calendar_publishable_zero")

    source_values = [
        calendar_counts.get("source_content_evaluated"),
        calendar_counts.get("source_content_allowed"),
        calendar_counts.get("source_content_blocked"),
        calendar_counts.get("source_failure_reasons"),
    ]
    source_count_contract = bool(
        all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in source_values)
        and source_values[1] + source_values[2] == source_values[0]
    )
    source_enforcement_ready = bool(
        calendar_execution_valid
        and source_count_contract
        and calendar_counts.get("structural_findings") == 0
    )
    checks["content_scoped_sources"] = {
        "passed": source_enforcement_ready,
        "scope": "CONTENT_ID_EXACT_MAPPING",
        "evaluated": source_values[0],
        "allowed": source_values[1],
        "blocked": source_values[2],
        "failure_reasons": source_values[3],
    }
    if not source_enforcement_ready:
        blockers.append("content_scoped_source_enforcement_failed")

    release_exit = (
        live_release_result.get("exit_code")
        if isinstance(live_release_result, dict) else None
    )
    release_ready = bool(
        isinstance(live_release_result, dict)
        and live_release_result.get("passed") is True
        and isinstance(release_exit, int)
        and not isinstance(release_exit, bool)
        and release_exit == 0
    )
    release_summary = (
        live_release_result.get("summary")
        if isinstance(live_release_result, dict)
        and isinstance(live_release_result.get("summary"), str)
        and live_release_result.get("summary").strip()
        else "no live release parity summary was captured"
    )
    release_evidence_sha256 = (
        live_release_result.get("evidence_sha256")
        if isinstance(live_release_result, dict) else None
    )
    release_evidence_path = (
        live_release_result.get("evidence_path")
        if isinstance(live_release_result, dict) else None
    )
    release_evidence_lines = (
        live_release_result.get("evidence_lines")
        if isinstance(live_release_result, dict) else None
    )
    checks["live_release_parity"] = {
        "passed": release_ready,
        "exit_code": release_exit,
        "summary": release_summary[:2000],
        "full_output_sha256": release_evidence_sha256,
        "full_output_path": release_evidence_path,
        "full_output_lines": release_evidence_lines,
    }
    checks["live_release_parity"]["evidence_hash"] = _canonical_hash({
        "passed": release_ready,
        "exit_code": release_exit,
        "summary": checks["live_release_parity"]["summary"],
        "full_output_sha256": release_evidence_sha256,
        "full_output_path": release_evidence_path,
        "full_output_lines": release_evidence_lines,
    })
    if not release_ready:
        blockers.append("live_release_parity_failed")

    sources = observation.get("sources") if isinstance(observation, dict) else None
    sources = sources if isinstance(sources, dict) else {}
    metrics = observation.get("metrics") if isinstance(observation, dict) else None
    metrics = metrics if isinstance(metrics, dict) else {}
    revenue = metrics.get("verified_affiliate_revenue")
    revenue = revenue if isinstance(revenue, dict) else {}
    observed_at = _parse_utc(
        observation.get("observed_at") if isinstance(observation, dict) else None
    )
    if observed_at is None:
        revenue_state = {
            "learning_ready": False,
            "quality_state": "INVALID",
            "errors": ["observation timestamp is invalid"],
        }
    else:
        revenue_state = _revenue_learning_contract(observation, observed_at)
    revenue_ready = revenue_state["learning_ready"]
    checks["revenue_ledger"] = {
        "passed": revenue_ready,
        "error": revenue.get("error"),
        "quality_state": revenue_state.get("quality_state"),
        "contract_errors": revenue_state.get("errors", []),
    }
    if not revenue_ready:
        blockers.append("revenue_ledger_unreconciled")

    ga4 = sources.get("ga4")
    ga4 = ga4 if isinstance(ga4, dict) else {}
    ga4_trust = ga4.get("trust")
    ga4_trust = ga4_trust if isinstance(ga4_trust, dict) else {}
    ga4_bundle = ga4.get("bundle")
    ga4_bundle = ga4_bundle if isinstance(ga4_bundle, dict) else {}
    ga4_expiry_error = observation_snapshot.decision_expiry_error(
        ga4_bundle, observed_at, "GA4"
    )
    ga4_ready = bool(
        ga4_trust.get("trusted") is True
        and ga4_bundle.get("decisionable") is True
        and ga4_bundle.get("state") == "CURRENT"
        and ga4_bundle.get("capture_trust") == "TRUSTED"
        and ga4_bundle.get("current_trust") == "TRUSTED"
        and ga4_expiry_error is None
    )
    checks["ga4"] = {
        "passed": ga4_ready,
        "trust": ga4_trust.get("label", "UNTRUSTED"),
        "bundle": ga4_bundle.get("state", "UNAVAILABLE"),
        "capture_trust": ga4_bundle.get("capture_trust"),
        "current_trust": ga4_bundle.get("current_trust"),
        "expires_at": ga4_bundle.get("expires_at"),
        "expiry_error": ga4_expiry_error,
    }
    if not ga4_ready:
        blockers.append("ga4_trust_or_bundle_failed")

    gsc = sources.get("gsc")
    gsc = gsc if isinstance(gsc, dict) else {}
    gsc_bundle = gsc.get("bundle")
    gsc_bundle = gsc_bundle if isinstance(gsc_bundle, dict) else {}
    gsc_expiry_error = observation_snapshot.decision_expiry_error(
        gsc_bundle, observed_at, "GSC"
    )
    gsc_ready = bool(
        gsc_bundle.get("decisionable") is True
        and gsc_bundle.get("state") == "CURRENT"
        and gsc_expiry_error is None
    )
    checks["gsc"] = {
        "passed": gsc_ready,
        "bundle": gsc_bundle.get("state", "UNAVAILABLE"),
        "expires_at": gsc_bundle.get("expires_at"),
        "expiry_error": gsc_expiry_error,
    }
    if not gsc_ready:
        blockers.append("gsc_bundle_failed")

    ready = not blockers
    result = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "status": "READY" if ready else "BLOCKED",
        "growth_ready": ready,
        "publication_ready": ready,
        "target_channel": normalized_target,
        "blockers": blockers,
        "checks": checks,
    }
    result["evidence_hash"] = _readiness_hash(result)
    return result


def collect_decision_readiness(*, observation=None, target_channel=None,
                               run_dir=None, policy=None,
                               calendar_result=None, live_release_result=None):
    """Collect current local-only evidence without initiating a live probe.

    A separately authorized workflow may pass a pre-collected, hash-bound
    ``live_release_result``.  When it is absent, live parity remains explicitly
    BLOCKED/UNKNOWN; local-safe mode never turns missing network evidence into a
    PASS and never creates test traffic.
    """
    observed = observation if observation is not None else observation_snapshot.collect()
    try:
        selected_policy = policy if policy is not None else _load(POLICY)
    except Exception:
        selected_policy = {}
    calendar = calendar_result
    if calendar is None:
        calendar = _run_guard(CONTENT_CALENDAR_GUARD, run_dir)
    live_release = live_release_result
    if live_release is None:
        live_release = _local_safe_live_release_result(run_dir)
    return evaluate_decision_readiness(
        observed, selected_policy, calendar, live_release,
        target_channel=target_channel,
    )


def observe(run_dir, *, runtime_contract=None):
    selected_runtime_contract = (
        runtime_contract if isinstance(runtime_contract, dict)
        else collect_runtime_contract()
    )
    _event(run_dir, "observe", "started")
    payload = observation_snapshot.collect()
    payload["runtime_contract"] = selected_runtime_contract
    payload["guards"] = {
        name: _run_guard(command, run_dir) for name, command in GUARDS.items()
    }
    payload["decision_readiness"] = collect_decision_readiness(
        observation=payload, run_dir=run_dir
    )
    _atomic(run_dir / "observation.json", payload)
    _event(run_dir, "observe", "finished")
    return payload


def _owner_action(kind, reason, evidence, expires_at):
    body = {"kind": kind, "request_only": True, "reason": reason,
            "evidence": evidence, "expires_at": expires_at}
    stable = {key: body[key] for key in ("kind", "reason", "evidence")}
    return {**body, "dedupe_key": _canonical_hash(stable),
            "action_hash": _canonical_hash(body)}


def guardrail_contract_errors(contract):
    """Return missing or non-executable evidence mappings in the policy contract."""
    declared = contract.get("guardrails")
    if not isinstance(declared, list) or not declared or any(
        not isinstance(item, str) or not item for item in declared
    ):
        return ["improvement policy guardrails must be a non-empty string list"]
    errors = []
    for item in declared:
        evidence = GUARDRAIL_EVIDENCE.get(item)
        if evidence is None:
            errors.append("guardrail has no evidence mapping: " + item)
            continue
        kind, key = evidence
        if kind == "guard":
            command = GUARDS.get(key)
            executable = bool(command) and (
                command[0] == "@private_posting_plan" or (ROOT / command[0]).is_file()
            )
            if not executable:
                errors.append("guardrail command is unavailable: " + item)
        elif kind not in {"observation", "readiness", "invariant"}:
            errors.append("guardrail evidence kind is invalid: " + item)
    extras = sorted(set(GUARDRAIL_EVIDENCE) - set(declared))
    if extras:
        errors.append("evidence mappings are not declared by policy: " + ", ".join(extras))
    return errors


def improvement_contract_errors(contract):
    """Validate every governance surface used to score or queue work."""
    errors = list(guardrail_contract_errors(contract))
    if contract.get("schema_version") != 2:
        errors.append("improvement policy schema must be 2")
    cadence = contract.get("cadence")
    cadence = cadence if isinstance(cadence, dict) else {}
    if set(cadence) != {"daily", "weekly"}:
        errors.append("daily and weekly cadence contracts are required")
    for name in ("daily", "weekly"):
        row = cadence.get(name)
        if not isinstance(row, dict):
            errors.append("cadence contract is malformed: " + name)
            continue
        age = row.get("max_observation_age_hours")
        due = row.get("review_due_hours")
        age_valid = isinstance(age, int) and not isinstance(age, bool) and age > 0
        if not age_valid:
            errors.append("cadence evidence age must be a positive integer: " + name)
        if (
            not isinstance(due, int) or isinstance(due, bool) or due <= 0
            or age_valid and due <= age
        ):
            errors.append("cadence review window must exceed evidence age: " + name)
        if not isinstance(row.get("growth_experiment_selection"), bool):
            errors.append("cadence growth selection flag is missing: " + name)
    if cadence.get("daily", {}).get("growth_experiment_selection") is not False:
        errors.append("daily cadence must not select growth experiments")
    if cadence.get("weekly", {}).get("growth_experiment_selection") is not True:
        errors.append("weekly cadence must own growth experiment selection")

    scoring = contract.get("maturity_scorecard")
    scoring = scoring if isinstance(scoring, dict) else {}
    if scoring.get("schema_version") != 1:
        errors.append("maturity scorecard schema must be 1")
    if scoring.get("model") != "same-run-gated-evidence":
        errors.append("maturity scorecard model must require same-run evidence")
    if scoring.get("progression_authority") != "weekly":
        errors.append("weekly cadence must be the progression authority")
    if scoring.get("stale_evidence_score") != 0:
        errors.append("stale evidence must score zero")
    declared = scoring.get("criteria")
    declared = declared if isinstance(declared, list) else []
    ids = [row.get("id") for row in declared if isinstance(row, dict)]
    if len(ids) != len(set(ids)) or set(ids) != set(MATURITY_CRITERIA):
        errors.append("maturity criteria must exactly match executable evaluators")
    weights = []
    for row in declared:
        if not isinstance(row, dict):
            errors.append("maturity criterion must be an object")
            continue
        weight = row.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            errors.append("maturity weight must be a positive integer: %s" % row.get("id"))
        else:
            weights.append(weight)
        if not isinstance(row.get("hard_blocker"), bool):
            errors.append("maturity hard_blocker flag is missing: %s" % row.get("id"))
        if not isinstance(row.get("acceptance"), str) or not row["acceptance"].strip():
            errors.append("maturity acceptance criterion is missing: %s" % row.get("id"))
    maximum = scoring.get("max_score")
    maximum_valid = (
        isinstance(maximum, int) and not isinstance(maximum, bool)
        and maximum > 0
    )
    if not maximum_valid:
        errors.append("maturity max_score must be a positive integer")
    elif sum(weights) != maximum:
        errors.append("maturity weights must sum to max_score")
    cap = scoring.get("hard_blocker_score_cap")
    threshold = scoring.get("minimum_growth_experiment_score")
    cap_valid = (
        maximum_valid and isinstance(cap, int) and not isinstance(cap, bool)
        and 0 <= cap < maximum
    )
    if not cap_valid:
        errors.append("hard blocker score cap is invalid")
    if (
        not cap_valid or not isinstance(threshold, int)
        or isinstance(threshold, bool) or not cap < threshold <= maximum
    ):
        errors.append("growth experiment score threshold is invalid")
    stages = scoring.get("stages")
    stages = stages if isinstance(stages, list) else []
    stage_thresholds = [row.get("minimum_score") for row in stages if isinstance(row, dict)]
    if (
        not stages or len(stage_thresholds) != len(stages)
        or any(not isinstance(value, int) or isinstance(value, bool) for value in stage_thresholds)
        or stage_thresholds != sorted(set(stage_thresholds))
        or stage_thresholds[0] != 0
        or not maximum_valid or stage_thresholds[-1] > maximum
    ):
        errors.append("maturity stages must have unique ascending integer thresholds from zero")

    catalog = contract.get("action_catalog")
    catalog = catalog if isinstance(catalog, dict) else {}
    expected_actions = set(PRIORITY_ACTION_KINDS) | set(OWNER_ACTION_KINDS)
    if set(catalog) != expected_actions:
        errors.append("action catalog must exactly match executable action kinds")
    for kind in sorted(expected_actions):
        row = catalog.get(kind)
        criteria = row.get("acceptance_criteria") if isinstance(row, dict) else None
        if not isinstance(row, dict) or row.get("owner") not in {"codex", "owner"}:
            errors.append("action owner is invalid: " + kind)
        if not isinstance(criteria, list) or not criteria or any(
            not isinstance(item, str) or not item.strip() for item in (criteria or [])
        ):
            errors.append("action acceptance criteria are missing: " + kind)
    ttl = contract.get("limits", {}).get("owner_action_ttl_hours")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        errors.append("owner action TTL must be a positive integer")
    if contract.get("limits", {}).get("max_growth_experiments_per_week") != 1:
        errors.append("at most one growth experiment may be selected per week")
    feedback = contract.get("feedback_cadence")
    feedback = feedback if isinstance(feedback, dict) else {}
    rules = feedback.get("progression_rules")
    if not isinstance(rules, list) or not rules or any(
        not isinstance(item, str) or not item.strip() for item in (rules or [])
    ):
        errors.append("feedback progression rules must be a non-empty string list")
    health_kpis = contract.get("control_health_kpis")
    health_kpis = health_kpis if isinstance(health_kpis, list) else []
    health_ids = [row.get("id") for row in health_kpis if isinstance(row, dict)]
    if len(health_ids) != len(health_kpis) or set(health_ids) != CONTROL_HEALTH_KPI_IDS:
        errors.append("control health KPIs must exactly match executable evaluators")
    for row in health_kpis:
        if not isinstance(row, dict):
            continue
        for field in ("definition", "decision"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append("control health KPI %s is missing %s" %
                              (row.get("id"), field))
        if "target" not in row:
            errors.append("control health KPI target is missing: %s" % row.get("id"))
    receipt_monitoring = contract.get("task_receipt_monitoring")
    receipt_monitoring = (
        receipt_monitoring if isinstance(receipt_monitoring, dict) else {}
    )
    errors.extend(_task_receipt_monitoring_errors(receipt_monitoring))
    if (
        receipt_monitoring.get("schema_version")
        != task_run_receipt.SCHEMA_VERSION
    ):
        errors.append(
            "task receipt monitoring schema must match the receipt producer"
        )
    if receipt_monitoring.get("tasks") != list(TASK_RECEIPT_NAMES):
        errors.append("task receipt monitoring tasks are incomplete or reordered")
    if receipt_monitoring.get("contract_revision") != (
        "task-version-ordered-command-manifest-v3"
    ):
        errors.append("task receipt ordered-step contract revision is invalid")
    if receipt_monitoring.get("finished_requires_complete_manifest") is not True:
        errors.append("task receipt complete-manifest requirement is disabled")
    if not isinstance(
        receipt_monitoring.get("legacy_schema_policy"), str
    ) or not receipt_monitoring.get("legacy_schema_policy", "").strip():
        errors.append("task receipt legacy schema policy is missing")
    _, legacy_registry_errors = _legacy_receipt_attestation_index(
        receipt_monitoring.get("legacy_receipt_attestations")
    )
    errors.extend(legacy_registry_errors)
    instrumentation_at = _parse_utc(
        receipt_monitoring.get("instrumentation_started_at")
    )
    if instrumentation_at is None:
        errors.append("task receipt instrumentation start is invalid")
    activation = receipt_monitoring.get("activation_attestation")
    activation_required = {
        "activated_at", "receipt_producer_sha256", "receipt_consumer_sha256",
        "contract_registry_sha256", "verification",
    }
    if not isinstance(activation, dict) or set(activation) != activation_required:
        errors.append("task receipt activation attestation is invalid")
    else:
        activated_at = _parse_utc(activation.get("activated_at"))
        if activated_at is None or activated_at != instrumentation_at:
            errors.append("task receipt activation time is not exact")
        binding_checks = (
            (
                "receipt_producer_sha256",
                _path_sha256(TASK_RECEIPT_TOOL_PATH),
            ),
            (
                "receipt_consumer_sha256",
                _path_sha256(Path(__file__).resolve()),
            ),
            (
                "contract_registry_sha256",
                task_run_receipt.task_contract_registry_hash(),
            ),
        )
        for field, actual_hash in binding_checks:
            claimed_hash = activation.get(field)
            if (
                not isinstance(claimed_hash, str)
                or not task_run_receipt.SHA256_RE.fullmatch(claimed_hash)
                or claimed_hash != actual_hash
            ):
                errors.append("task receipt activation %s is invalid" % field)
        errors.extend(_activation_verification_errors(
            activation.get("verification"), activated_at
        ))
    trusted_producers = receipt_monitoring.get(
        "trusted_receipt_producer_sha256"
    )
    trusted_producers_valid = bool(
        isinstance(trusted_producers, list)
        and trusted_producers
        and all(
            isinstance(value, str)
            and task_run_receipt.SHA256_RE.fullmatch(value)
            for value in trusted_producers
        )
        and len(trusted_producers) == len(set(trusted_producers))
    )
    if not trusted_producers_valid:
        errors.append("trusted receipt producer registry is invalid")
    elif (
        isinstance(activation, dict)
        and activation.get("receipt_producer_sha256") not in trusted_producers
    ):
        errors.append("activated receipt producer is not trusted")
    stuck_after = receipt_monitoring.get("stuck_after_hours")
    if (
        not isinstance(stuck_after, int) or isinstance(stuck_after, bool)
        or stuck_after != TASK_RECEIPT_STUCK_AFTER_HOURS
    ):
        errors.append(
            "task receipt stuck threshold must match the bounded runner timeout"
        )
    if receipt_monitoring.get("origin") != "RUNNER_INVOCATION_UNVERIFIED":
        errors.append("task receipt monitoring origin is invalid")
    if receipt_monitoring.get("scheduler_launch_proven") is not False:
        errors.append("task receipts must not claim a scheduler launch")
    if not isinstance(receipt_monitoring.get("scheduler_sla_source"), str) or not (
        receipt_monitoring.get("scheduler_sla_source", "").strip()
    ):
        errors.append("task receipt scheduler SLA boundary is missing")
    learning = contract.get("error_learning")
    learning = learning if isinstance(learning, dict) else {}
    if learning.get("schema_version") != ERROR_LEARNING_SCHEMA:
        errors.append("error-learning policy schema must be 1")
    if learning.get("identity_fields") != ["id", "fact"]:
        errors.append("error-learning identity must use id and fact")
    recurring = learning.get("recurring_after_runs")
    maximum_incidents = learning.get("max_incidents")
    if not isinstance(recurring, int) or isinstance(recurring, bool) or recurring < 2:
        errors.append("error-learning recurring threshold must be at least two runs")
    if (
        not isinstance(maximum_incidents, int) or isinstance(maximum_incidents, bool)
        or maximum_incidents < 1
    ):
        errors.append("error-learning max_incidents must be a positive integer")
    if learning.get("state_file") != ERROR_LEARNING_STATE_FILE:
        errors.append("error-learning state file contradicts the private runtime")
    for field in ("resolution_rule", "priority_rule", "repair_boundary"):
        if not isinstance(learning.get(field), str) or not learning[field].strip():
            errors.append("error-learning policy is missing " + field)
    if contract.get("operator", {}).get("unattended_external_mutation") is not False:
        errors.append("improvement operator must not have unattended external mutation")
    external_actions = contract.get("external_actions_requiring_owner_action")
    if not isinstance(external_actions, list) or set(external_actions) != EXTERNAL_OWNER_ACTIONS:
        errors.append("external owner-action boundary is incomplete")
    return list(dict.fromkeys(errors))


def _observation_freshness(observation, cadence, contract, now):
    observed = _parse_utc(observation.get("observed_at")) if isinstance(observation, dict) else None
    maximum = contract.get("cadence", {}).get(cadence, {}).get(
        "max_observation_age_hours"
    )
    if observed is None or not isinstance(maximum, int) or isinstance(maximum, bool):
        return False, None, "observation timestamp or cadence limit is invalid"
    age = (now - observed).total_seconds() / 3600.0
    if age < 0 or age > maximum:
        return False, round(age, 3), "observation is outside the cadence evidence window"
    return True, round(age, 3), None


def _revenue_learning_contract(observation, observed_at):
    metrics = observation.get("metrics") if isinstance(observation, dict) else None
    metrics = metrics if isinstance(metrics, dict) else {}
    revenue = metrics.get("verified_affiliate_revenue")
    revenue = revenue if isinstance(revenue, dict) else {}
    expected_end = observed_at.astimezone(dt.timezone(dt.timedelta(hours=7))).date()
    validator = getattr(revenue_ledger, "learning_contract_errors", None)
    if not callable(validator):
        errors = ["revenue learning validator is unavailable"]
    else:
        try:
            errors = list(validator(
                revenue, expected_end=expected_end, observed_at=observed_at
            ))
        except Exception as exc:
            errors = ["revenue learning validation failed (%s)" % type(exc).__name__]
    trusted = bool(revenue.get("trusted") is True and not errors)
    learning_ready = bool(
        trusted and revenue.get("learning_ready") is True
        and revenue.get("reconcile_required") is False
    )
    paid_revenue = _finite_number(revenue.get("paid_revenue_thb"))
    paid_transactions = revenue.get("paid_transactions")
    paid_transactions_valid = (
        isinstance(paid_transactions, int)
        and not isinstance(paid_transactions, bool)
        and paid_transactions >= 0
    )
    positive = bool(
        learning_ready and paid_revenue is not None and paid_revenue > 0
        and paid_transactions_valid and paid_transactions > 0
    )
    next_action = revenue.get("next_action")
    next_actions = [next_action] if isinstance(next_action, str) and next_action else []
    return {
        "trusted": trusted,
        "learning_ready": learning_ready,
        "positive_outcome": positive,
        "quality_state": revenue.get("quality_state", "INVALID"),
        "reconcile_required": revenue.get("reconcile_required") is True,
        "errors": errors,
        "next_actions": next_actions,
    }


def _learning_readiness_contract(observation, observed_at):
    sources = observation.get("sources") if isinstance(observation, dict) else None
    sources = sources if isinstance(sources, dict) else {}
    metrics = observation.get("metrics") if isinstance(observation, dict) else None
    metrics = metrics if isinstance(metrics, dict) else {}
    ga4 = sources.get("ga4")
    ga4 = ga4 if isinstance(ga4, dict) else {}
    gsc = sources.get("gsc")
    gsc = gsc if isinstance(gsc, dict) else {}
    revenue = metrics.get("verified_affiliate_revenue")
    revenue = revenue if isinstance(revenue, dict) else {}
    try:
        expected = observation_snapshot.build_learning_readiness(
            ga4.get("bundle", {}), gsc.get("bundle", {}), revenue,
            expected_end=observed_at.astimezone(
                dt.timezone(dt.timedelta(hours=7))
            ).date(),
            decision_time=observed_at,
        )
    except Exception as exc:
        expected = {
            "schema_version": 1,
            "status": "BLOCKED",
            "ready": False,
            "score": {"passed": 0, "total": 3},
            "blockers": ["learning_contract_unavailable"],
            "actions": [],
            "sources": {},
        }
        return expected, [
            "learning readiness recomputation failed (%s)" % type(exc).__name__
        ]
    declared = observation.get("learning_readiness") if isinstance(observation, dict) else None
    errors = []
    if not isinstance(declared, dict):
        errors.append("learning readiness is missing")
    elif declared != expected:
        errors.append("learning readiness contradicts recomputed source contracts")
    return expected, errors


def _scorecard_hash(scorecard):
    return _canonical_hash({
        key: value for key, value in scorecard.items() if key != "scorecard_hash"
    })


def _seal_scorecard(scorecard):
    scorecard["scorecard_hash"] = _scorecard_hash(scorecard)
    return scorecard


def _scorecard_hash_valid(scorecard):
    if not isinstance(scorecard, dict):
        return False
    try:
        return scorecard.get("scorecard_hash") == _scorecard_hash(scorecard)
    except (TypeError, ValueError):
        return False


def _attach_progression(scorecard, previous, cadence, contract,
                        regressed_incidents=None):
    authority = contract.get("maturity_scorecard", {}).get("progression_authority")
    regressions = sorted(set(
        item for item in (regressed_incidents or [])
        if isinstance(item, str) and item
    ))
    if cadence != authority:
        scorecard["progression"] = {
            "status": "PROVISIONAL_DAILY",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
        }
        return _seal_scorecard(scorecard)
    if scorecard.get("evidence_status") != "CURRENT":
        scorecard["progression"] = {
            "status": "CURRENT_EVIDENCE_INVALID",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
        }
        return _seal_scorecard(scorecard)
    if regressions:
        scorecard["growth_experiment_eligible"] = False
        scorecard["progression"] = {
            "status": "ERROR_REGRESSION_BLOCKED",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
            "regressed_incidents": regressions,
            "previous_scorecard_hash": (
                previous.get("scorecard_hash")
                if isinstance(previous, dict) else None
            ),
        }
        return _seal_scorecard(scorecard)
    if previous is None:
        scorecard["progression"] = {
            "status": "NO_BASELINE",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
        }
        return _seal_scorecard(scorecard)
    if (
        not _scorecard_hash_valid(previous)
        or previous.get("evidence_status") != "CURRENT"
    ):
        scorecard["progression"] = {
            "status": "INVALID_BASELINE",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
        }
        return _seal_scorecard(scorecard)
    if previous.get("cadence") != authority or (
        previous.get("policy_hash") != scorecard.get("policy_hash")
    ):
        scorecard["progression"] = {
            "status": "BASELINE_RESET",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
        }
        return _seal_scorecard(scorecard)
    previous_at = _parse_utc(previous.get("evaluated_at"))
    current_at = _parse_utc(scorecard.get("evaluated_at"))
    maximum_gap = contract.get("cadence", {}).get(authority, {}).get(
        "review_due_hours"
    )
    if (
        previous_at is None or current_at is None
        or not isinstance(maximum_gap, int) or isinstance(maximum_gap, bool)
        or (current_at - previous_at).total_seconds() < 0
        or (current_at - previous_at).total_seconds() > maximum_gap * 3600
    ):
        scorecard["progression"] = {
            "status": "STALE_BASELINE",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
        }
        return _seal_scorecard(scorecard)
    if (
        not isinstance(previous.get("score"), int)
        or isinstance(previous.get("score"), bool)
        or previous["score"] < 0
        or previous["score"] > contract.get("maturity_scorecard", {}).get("max_score", 0)
    ):
        scorecard["progression"] = {
            "status": "INVALID_BASELINE",
            "comparable": False,
            "delta": None,
            "newly_passed": [],
            "reopened_hard_blockers": [],
        }
        return _seal_scorecard(scorecard)
    previous_rows = {
        row.get("id"): row for row in previous.get("criteria", [])
        if isinstance(row, dict)
    }
    current_rows = {
        row.get("id"): row for row in scorecard.get("criteria", [])
        if isinstance(row, dict)
    }
    if set(previous_rows) != set(MATURITY_CRITERIA) or set(current_rows) != set(MATURITY_CRITERIA):
        status = "INVALID_BASELINE"
        delta = None
        newly_passed = []
        reopened = []
        comparable = False
    else:
        delta = scorecard["score"] - previous["score"]
        newly_passed = sorted(
            criterion for criterion in MATURITY_CRITERIA
            if previous_rows[criterion].get("passed") is False
            and current_rows[criterion].get("passed") is True
        )
        reopened = sorted(
            criterion for criterion in MATURITY_CRITERIA
            if previous_rows[criterion].get("passed") is True
            and current_rows[criterion].get("passed") is False
            and current_rows[criterion].get("hard_blocker") is True
        )
        comparable = True
        if delta > 0 and not newly_passed:
            status = "INVALID_DELTA"
            comparable = False
        elif reopened or delta < 0:
            status = "REGRESSED"
        elif delta > 0:
            status = "IMPROVED"
        else:
            status = "UNCHANGED"
    scorecard["progression"] = {
        "status": status,
        "comparable": comparable,
        "delta": delta,
        "newly_passed": newly_passed,
        "reopened_hard_blockers": reopened,
        "previous_scorecard_hash": previous.get("scorecard_hash"),
    }
    return _seal_scorecard(scorecard)


def build_maturity_scorecard(observation, contract, cadence="daily", now=None,
                             previous=None, regressed_incidents=None):
    """Score only explicit current evidence; hard blockers cap the result."""
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ValueError("scorecard time must be timezone-aware")
    # Preserve the exact evaluation instant.  Hash-bound freshness must not be
    # rounded toward CURRENT at a sub-second SLA boundary, and the persisted
    # value must reproduce the same scorecard byte-for-byte during validation.
    current = current.astimezone(dt.timezone.utc)
    regressions = sorted(set(
        item for item in (regressed_incidents or [])
        if isinstance(item, str) and item
    ))
    fresh, age_hours, freshness_error = _observation_freshness(
        observation, cadence, contract, current
    )
    readiness = observation.get("decision_readiness") if isinstance(observation, dict) else None
    readiness_errors = readiness_contract_errors(
        readiness, observation, decision_time=current
    )
    checks = readiness.get("checks", {}) if isinstance(readiness, dict) else {}
    observed_at = _parse_utc(observation.get("observed_at")) if isinstance(observation, dict) else None
    observed_at = observed_at or current
    revenue_state = _revenue_learning_contract(observation, current)
    learning, learning_errors = _learning_readiness_contract(
        observation, current
    )
    learning_sources = learning.get("sources", {})
    learning_sources = learning_sources if isinstance(learning_sources, dict) else {}

    expected_guards = sorted(
        key for kind, key in GUARDRAIL_EVIDENCE.values() if kind == "guard"
    )
    guards = observation.get("guards") if isinstance(observation, dict) else None
    guards = guards if isinstance(guards, dict) else {}
    failed_guards = []
    for name in expected_guards:
        row = guards.get(name)
        passed = bool(
            isinstance(row, dict) and row.get("passed") is True
            and isinstance(row.get("exit_code"), int)
            and not isinstance(row.get("exit_code"), bool)
            and row.get("exit_code") == 0
        )
        if not passed:
            failed_guards.append(name)
    external_invariant = bool(
        contract.get("operator", {}).get("unattended_external_mutation") is False
    )

    sources = observation.get("sources") if isinstance(observation, dict) else None
    sources = sources if isinstance(sources, dict) else {}
    ga4 = sources.get("ga4")
    ga4 = ga4 if isinstance(ga4, dict) else {}
    ga4_trust = ga4.get("trust")
    ga4_trust = ga4_trust if isinstance(ga4_trust, dict) else {}
    ga4_bundle = ga4.get("bundle")
    ga4_bundle = ga4_bundle if isinstance(ga4_bundle, dict) else {}
    gsc = sources.get("gsc")
    gsc = gsc if isinstance(gsc, dict) else {}
    gsc_bundle = gsc.get("bundle")
    gsc_bundle = gsc_bundle if isinstance(gsc_bundle, dict) else {}
    official = sources.get("official_sources")
    official = official if isinstance(official, dict) else {}
    official_errors = official.get("errors")
    official_reviews = official.get("review_required")
    source_enforcement = checks.get("content_scoped_sources", {})
    source_enforcement = (
        source_enforcement if isinstance(source_enforcement, dict) else {}
    )
    publication_ready = bool(
        checks.get("publication_authority", {}).get("passed") is True
        and checks.get("content_calendar", {}).get("passed") is True
        and checks.get("live_release_parity", {}).get("passed") is True
    )
    fact_rows = {
        "evidence_current_and_bound": {
            "passed": bool(fresh and not readiness_errors and not learning_errors),
            "evidence": {
                "age_hours": age_hours,
                "freshness_error": freshness_error,
                "readiness_errors": readiness_errors,
                "learning_readiness_errors": learning_errors,
                "readiness_hash": readiness.get("evidence_hash") if isinstance(readiness, dict) else None,
            },
        },
        "guardrails_current": {
            "passed": bool(not failed_guards and external_invariant),
            "evidence": {
                "failed_guards": failed_guards,
                "external_mutation_authorized": not external_invariant,
            },
        },
        "revenue_ledger_trusted": {
            "passed": bool(
                not learning_errors
                and learning_sources.get("revenue", {}).get("ready") is True
                and revenue_state["learning_ready"]
            ),
            "evidence": {
                "quality_state": revenue_state["quality_state"],
                "reconcile_required": revenue_state["reconcile_required"],
                "contract_errors": revenue_state["errors"],
            },
        },
        "analytics_decisionable": {
            "passed": bool(
                not learning_errors
                and learning_sources.get("ga4", {}).get("ready") is True
                and learning_sources.get("gsc", {}).get("ready") is True
            ),
            "evidence": {
                "ga4_trust": ga4_trust.get("label", "UNTRUSTED"),
                "ga4_bundle": ga4_bundle.get("state", "UNAVAILABLE"),
                "ga4_capture_trust": ga4_bundle.get("capture_trust"),
                "ga4_current_trust": ga4_bundle.get("current_trust"),
                "gsc_bundle": gsc_bundle.get("state", "UNAVAILABLE"),
            },
        },
        "content_scoped_source_enforcement": {
            "passed": source_enforcement.get("passed") is True,
            "evidence": {
                "scope": source_enforcement.get("scope"),
                "evaluated": source_enforcement.get("evaluated"),
                "allowed": source_enforcement.get("allowed"),
                "blocked": source_enforcement.get("blocked"),
                "failure_reasons": source_enforcement.get("failure_reasons"),
                "global_monitor_state_diagnostic": official.get(
                    "state", "UNAVAILABLE"
                ),
                "global_pending_diagnostic": official_reviews,
                "global_errors_diagnostic": official_errors,
            },
        },
        "publication_inputs_ready": {
            "passed": publication_ready,
            "evidence": {
                name: checks.get(name, {}).get("passed")
                for name in ("publication_authority", "content_calendar", "live_release_parity")
            },
        },
        "verified_revenue_learning": {
            "passed": revenue_state["positive_outcome"],
            "evidence": {
                "learning_ready": revenue_state["learning_ready"],
                "positive_verified_outcome": revenue_state["positive_outcome"],
            },
        },
    }
    scoring = contract.get("maturity_scorecard", {})
    criteria = []
    for declared in scoring.get("criteria", []):
        criterion_id = declared["id"]
        fact = fact_rows.get(criterion_id, {"passed": False, "evidence": {
            "error": "criterion evaluator unavailable",
        }})
        evidence = fact["evidence"]
        criteria.append({
            "id": criterion_id,
            "weight": declared["weight"],
            "hard_blocker": declared["hard_blocker"],
            "acceptance": declared["acceptance"],
            "passed": fact["passed"] is True,
            "awarded": declared["weight"] if fact["passed"] is True else 0,
            "evidence": evidence,
            "evidence_hash": _canonical_hash(evidence),
        })
    raw_score = sum(row["awarded"] for row in criteria)
    hard_blockers = [
        row["id"] for row in criteria
        if row["hard_blocker"] and not row["passed"]
    ]
    if not fresh:
        score = int(scoring.get("stale_evidence_score", 0))
        evidence_status = "STALE"
    else:
        score = raw_score
        if hard_blockers:
            score = min(score, int(scoring.get("hard_blocker_score_cap", 0)))
        # Both readiness envelopes are part of the same-run binding contract.
        # A contradictory learning-readiness payload must never retain the
        # top-level CURRENT label merely because decision_readiness itself is
        # internally consistent.  The criterion already fails closed; keep
        # the envelope state consistent so reports and weekly progression do
        # not treat malformed evidence as a current comparable baseline.
        evidence_status = (
            "CURRENT"
            if not readiness_errors and not learning_errors
            else "INVALID"
        )
    stages = sorted(scoring.get("stages", []), key=lambda row: row["minimum_score"])
    stage = stages[0]["id"] if stages else "unknown"
    for row in stages:
        if score >= row["minimum_score"]:
            stage = row["id"]
    cadence_row = contract.get("cadence", {}).get(cadence, {})
    experiment_eligible = bool(
        cadence_row.get("growth_experiment_selection") is True
        and evidence_status == "CURRENT"
        and not hard_blockers
        and learning.get("ready") is True
        and not learning_errors
        and revenue_state["positive_outcome"]
        and score >= scoring.get("minimum_growth_experiment_score", 101)
        and not regressions
    )
    policy_hash = _canonical_hash(contract)
    card = {
        "schema_version": 1,
        "cadence": cadence,
        "observed_at": observation.get("observed_at") if isinstance(observation, dict) else None,
        "evaluated_at": current.isoformat(timespec="microseconds"),
        "policy_hash": policy_hash,
        "evidence_status": evidence_status,
        "score": score,
        "raw_score": raw_score,
        "maximum_score": scoring.get("max_score"),
        "stage": stage,
        "hard_blockers": hard_blockers,
        "criteria": criteria,
        "growth_experiment_eligible": experiment_eligible,
        "learning_ready": bool(learning.get("ready") is True and not learning_errors),
        "learning_blockers": list(learning.get("blockers", [])) + (
            ["learning_readiness_evidence_invalid"] if learning_errors else []
        ),
        "next_data_actions": list(learning.get("actions", [])),
    }
    card["evidence_hash"] = _canonical_hash({
        "observed_at": card["observed_at"],
        "policy_hash": policy_hash,
        "criteria": [
            {"id": row["id"], "passed": row["passed"],
             "evidence_hash": row["evidence_hash"]}
            for row in criteria
        ],
        "score": score,
        "hard_blockers": hard_blockers,
    })
    return _attach_progression(
        card, previous, cadence, contract,
        regressed_incidents=regressions,
    )


def _govern_action(kind, *, rank, reason, scope, contract, observed_at,
                   request_only=False, expires_at=None):
    catalog = contract.get("action_catalog", {}).get(kind, {})
    created_at = observed_at
    expiry = _parse_utc(expires_at) if expires_at else None
    ttl = contract.get("limits", {}).get("owner_action_ttl_hours")
    if expiry is not None and isinstance(ttl, int) and not isinstance(ttl, bool):
        created_at = (expiry - dt.timedelta(hours=ttl)).isoformat(timespec="seconds")
    body = {
        "kind": kind,
        "owner": catalog.get("owner"),
        "status": "OPEN",
        "rank": rank,
        "reason": reason,
        "scope": scope,
        "acceptance_criteria": catalog.get("acceptance_criteria", []),
        "request_only": bool(request_only),
        "observed_at": observed_at,
        "created_at": created_at,
        "expires_at": expires_at,
    }
    stable = {key: body[key] for key in (
        "kind", "owner", "reason", "scope", "acceptance_criteria", "request_only"
    )}
    body["dedupe_key"] = _canonical_hash(stable)
    body["action_hash"] = _canonical_hash(body)
    return body


def build_action_queue(priorities, owner_actions, contract, observed_at):
    items = []
    for priority in priorities:
        items.append(_govern_action(
            priority["type"], rank=priority["rank"], reason=priority["reason"],
            scope=priority["scope"], contract=contract, observed_at=observed_at,
        ))
    for action in owner_actions:
        items.append(_govern_action(
            action["kind"], rank=action.get("rank", 2), reason=action["reason"],
            scope=action["evidence"], contract=contract, observed_at=observed_at,
            request_only=True, expires_at=action["expires_at"],
        ))
    items.sort(key=lambda row: (row["rank"], row["owner"] != "owner", row["kind"]))
    return {
        "schema_version": 1,
        "observed_at": observed_at,
        "status": "OPEN" if items else "CLEAR",
        "items": items,
        "queue_hash": _canonical_hash(items),
    }


def action_queue_errors(queue, contract, *, now=None):
    errors = []
    if not isinstance(queue, dict) or queue.get("schema_version") != 1:
        return ["action queue is missing or malformed"]
    items = queue.get("items")
    if not isinstance(items, list):
        return ["action queue items are missing"]
    if queue.get("status") != ("OPEN" if items else "CLEAR"):
        errors.append("action queue status contradicts its items")
    try:
        if queue.get("queue_hash") != _canonical_hash(items):
            errors.append("action queue hash is mismatched")
    except (TypeError, ValueError):
        errors.append("action queue is not canonical JSON")
    seen = set()
    current = now or dt.datetime.now(dt.timezone.utc)
    for item in items:
        if not isinstance(item, dict):
            errors.append("action queue item is malformed")
            continue
        kind = item.get("kind")
        catalog = contract.get("action_catalog", {}).get(kind)
        if not isinstance(catalog, dict):
            errors.append("action queue kind is undeclared: %s" % kind)
            continue
        if item.get("owner") != catalog.get("owner"):
            errors.append("action owner contradicts policy: %s" % kind)
        if item.get("status") != "OPEN":
            errors.append("action queue contains a non-open item: %s" % kind)
        if item.get("acceptance_criteria") != catalog.get("acceptance_criteria"):
            errors.append("action acceptance criteria contradict policy: %s" % kind)
        if item.get("owner") == "owner" and item.get("request_only") is not True:
            errors.append("owner action is not request-only: %s" % kind)
        if item.get("owner") == "codex" and item.get("request_only") is not False:
            errors.append("local action is incorrectly marked as owner authority: %s" % kind)
        try:
            expected_hash = _canonical_hash({
                key: value for key, value in item.items() if key != "action_hash"
            })
        except (TypeError, ValueError):
            expected_hash = None
        if not expected_hash or item.get("action_hash") != expected_hash:
            errors.append("action item hash is missing or mismatched: %s" % kind)
        stable = {key: item.get(key) for key in (
            "kind", "owner", "reason", "scope", "acceptance_criteria", "request_only"
        )}
        try:
            expected_dedupe = _canonical_hash(stable)
        except (TypeError, ValueError):
            expected_dedupe = None
        dedupe = item.get("dedupe_key")
        if (
            not expected_dedupe or dedupe != expected_dedupe
            or dedupe in seen
        ):
            errors.append("action dedupe key is missing or duplicated: %s" % kind)
        seen.add(dedupe)
        if item.get("owner") == "owner":
            expiry = _parse_utc(item.get("expires_at"))
            created = _parse_utc(item.get("created_at"))
            ttl = contract.get("limits", {}).get("owner_action_ttl_hours")
            if (
                expiry is None or created is None or expiry <= current
                or expiry <= created
                or not isinstance(ttl, int) or isinstance(ttl, bool)
                or (expiry - created).total_seconds() > ttl * 3600
            ):
                errors.append("owner action is expired or has no expiry: %s" % kind)
    return errors


def diagnose(observation, contract, cadence="daily", now=None,
             previous_scorecard=None, learning_state=None,
             regressed_incidents=None):
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ValueError("diagnosis time must be timezone-aware")
    current = current.astimezone(dt.timezone.utc)
    findings = []
    priorities = []
    owner_actions = []
    scorecard = build_maturity_scorecard(
        observation, contract, cadence=cadence, now=current,
        previous=previous_scorecard,
        regressed_incidents=regressed_incidents,
    )

    readiness = observation.get("decision_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    readiness_errors = readiness_contract_errors(
        readiness, observation, decision_time=current
    )
    readiness_blockers = readiness.get("blockers")
    readiness_blockers = readiness_blockers if isinstance(readiness_blockers, list) else []
    if readiness_errors:
        readiness_blockers = list(readiness_blockers) + [
            "decision_readiness_evidence_invalid"
        ]
    readiness_ready = bool(
        not readiness_errors
        and readiness.get("status") == "READY"
        and readiness.get("growth_ready") is True
        and readiness.get("publication_ready") is True
        and not readiness_blockers
    )
    if not readiness_ready:
        findings.append({
            "severity": "P1",
            "id": "decision_readiness_blocked",
            "fact": "Growth and publication decisions are blocked",
            "evidence": {
                "blockers": readiness_blockers,
                "contract_errors": readiness_errors,
            },
        })

    expected_guards = {
        key for kind, key in GUARDRAIL_EVIDENCE.values() if kind == "guard"
    }
    guards = observation.get("guards")
    guards = guards if isinstance(guards, dict) else {}
    failed_guards = sorted(
        name for name in expected_guards
        if not (
            isinstance(guards.get(name), dict)
            and guards[name].get("passed") is True
            and isinstance(guards[name].get("exit_code"), int)
            and not isinstance(guards[name].get("exit_code"), bool)
            and guards[name].get("exit_code") == 0
        )
    )
    if failed_guards:
        findings.append({"severity": "P0", "id": "guard_failure",
                         "fact": "Local safety/integrity guard failed",
                         "evidence": failed_guards})
        priorities.append({"rank": 1, "type": "repair_local_guard",
                           "scope": failed_guards,
                           "reason": "Safety failures always precede growth work"})

    observed_at = _parse_utc(observation.get("observed_at")) or current
    learning, learning_errors = _learning_readiness_contract(
        observation, current
    )
    learning_sources = learning.get("sources", {})
    learning_sources = learning_sources if isinstance(learning_sources, dict) else {}
    learning_actions = {
        row.get("source"): row for row in learning.get("actions", [])
        if isinstance(row, dict)
    }
    if learning_errors:
        findings.append({
            "severity": "P0",
            "id": "learning_readiness_invalid",
            "fact": "Declared learning readiness does not match source contracts",
            "evidence": learning_errors,
        })

    sources = observation.get("sources")
    sources = sources if isinstance(sources, dict) else {}
    ga4 = sources.get("ga4")
    ga4 = ga4 if isinstance(ga4, dict) else {}
    ga4_trust = ga4.get("trust")
    ga4_trust = ga4_trust if isinstance(ga4_trust, dict) else {}
    ga4_bundle = ga4.get("bundle")
    ga4_bundle = ga4_bundle if isinstance(ga4_bundle, dict) else {}
    if learning_sources.get("ga4", {}).get("ready") is not True:
        action = learning_actions.get("ga4", {}).get("action", "REPULL_GA4")
        findings.append({"severity": "P1", "id": "ga4_not_decisionable",
                         "fact": "GA4 raw values cannot drive a decision",
                         "evidence": {"trust": ga4_trust.get("label", "UNTRUSTED"),
                                      "bundle": ga4_bundle.get("state", "UNAVAILABLE"),
                                      "capture_trust": ga4_bundle.get("capture_trust"),
                                      "current_trust": ga4_bundle.get("current_trust"),
                                      "next_action": action}})
        priorities.append({"rank": 2, "type": "repair_measurement",
                           "scope": [action, "28-day bundle metadata"],
                           "reason": "No winner, timing, cadence or scale action is allowed"})
        if action == "REPAIR_GA4_TRUST_THEN_REPULL":
            ttl = int(contract.get("limits", {}).get("owner_action_ttl_hours", 48))
            expires = (current + dt.timedelta(hours=ttl)).isoformat(timespec="seconds")
            owner_actions.append(_owner_action(
                "verify_ga4_internal_network",
                "Confirm that the private current egress belongs to the owner before changing the exclusion range",
                [ga4_trust.get("label", "UNTRUSTED"),
                 ga4_bundle.get("state", "UNAVAILABLE")], expires))

    gsc = sources.get("gsc")
    gsc = gsc if isinstance(gsc, dict) else {}
    gsc_bundle = gsc.get("bundle")
    gsc_bundle = gsc_bundle if isinstance(gsc_bundle, dict) else {}
    if learning_sources.get("gsc", {}).get("ready") is not True:
        action = learning_actions.get("gsc", {}).get("action", "REPULL_GSC")
        findings.append({"severity": "P1", "id": "gsc_not_current",
                         "fact": "GSC raw values have no current hash-bound 28-day bundle",
                         "evidence": {"state": gsc_bundle.get("state", "UNAVAILABLE"),
                                      "next_action": action}})
        priorities.append({"rank": 3, "type": "refresh_gsc_bundle",
                           "scope": [action, "queries", "pages", "metadata"],
                           "reason": "Do not prioritize SEO from mixed or undated files"})

    source = sources.get("official_sources")
    source = source if isinstance(source, dict) else {}
    source_current = source.get("current") is True
    source_clear = source.get("clear_for_publication") is True
    if not source_current:
        findings.append({"severity": "P1", "id": "official_source_snapshot_unavailable",
                         "fact": "Official-source evidence is missing, stale, or invalid",
                         "evidence": source})
        priorities.append({"rank": 2, "type": "refresh_official_source_snapshot",
                           "scope": ["official source change detector"],
                           "reason": "Missing or stale source evidence cannot be treated as reviewed"})
    elif not source_clear:
        findings.append({"severity": "P1", "id": "official_source_review",
                         "fact": "The global monitor queue still requires explicit review; only matching content_id claims are publication blockers",
                         "evidence": source})
    if source_current and (source.get("errors") or source.get("review_required")):
        ttl = int(contract.get("limits", {}).get("owner_action_ttl_hours", 48))
        expires = (current + dt.timedelta(hours=ttl)).isoformat(timespec="seconds")
        owner_actions.append(_owner_action(
            "review_official_sources",
            "Review exact claim packets; acknowledgement is not delegated to the internal operator",
            ["review_required=%s" % source.get("review_required"),
             "errors=%s" % source.get("errors")], expires))

    metrics = observation.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    revenue = metrics.get("verified_affiliate_revenue")
    revenue = revenue if isinstance(revenue, dict) else {}
    revenue_state = _revenue_learning_contract(observation, current)
    if not revenue_state["learning_ready"] or learning_errors:
        next_action = learning_actions.get("revenue", {}).get(
            "action", "RECONCILE_REVENUE"
        )
        findings.append({"severity": "P1", "id": "revenue_ledger_unavailable",
                         "fact": "Verified affiliate revenue is unavailable, not zero",
                         "evidence": {
                             "quality_state": revenue_state["quality_state"],
                             "contract_errors": revenue_state["errors"],
                             "next_action": next_action,
                         }})
        priorities.append({"rank": 2, "type": "repair_revenue_ledger",
                           "scope": [next_action, "private sales ledger"],
                           "reason": "Revenue outcome must be reconciled before growth decisions"})
    else:
        paid_revenue = _finite_number(revenue.get("paid_revenue_thb"))
        paid_transactions = revenue.get("paid_transactions")
        ga4_metrics = metrics.get(
            "ga4_observed_not_decisionable_unless_trusted", {}
        )
        ga4_metrics = ga4_metrics if isinstance(ga4_metrics, dict) else {}
        intent = _finite_number(ga4_metrics.get("affiliate_click"))
        # A positive raw GA4 count is not "trusted intent" unless the
        # hash-bound GA4 source itself is decision-ready.  The metric namespace
        # is intentionally named ``*_not_decisionable_unless_trusted``; using
        # its value alone would turn blocked analytics into an incident and can
        # create a false regression when a previously unavailable revenue
        # ledger is correctly reconciled to zero.
        trusted_intent = bool(
            learning_sources.get("ga4", {}).get("ready") is True
            and intent is not None and intent > 0
        )
        no_positive_outcome = bool(
            paid_revenue is not None and paid_revenue <= 0
            and isinstance(paid_transactions, int)
            and not isinstance(paid_transactions, bool)
            and paid_transactions == 0
        )
        if no_positive_outcome and trusted_intent:
            findings.append({
                "severity": "P2",
                "id": "verified_zero_revenue",
                "fact": "No positive paid affiliate revenue exists in the current window",
                "evidence": {
                    "window_start": revenue.get("window_start"),
                    "window_end": revenue.get("window_end"),
                    "positive_paid_revenue": False,
                    "paid_transactions": 0,
                },
            })
            if (
                scorecard["learning_ready"]
                and not scorecard["hard_blockers"]
            ):
                priorities.append({
                    "rank": 4,
                    "type": "audit_offer_and_attribution",
                    "scope": ["landing continuity", "merchant outcome capture",
                              "commission logging"],
                    "reason": "Trusted intent without money is not a reach winner",
                })
        elif no_positive_outcome:
            findings.append({
                "severity": "INFO",
                "id": "verified_zero_revenue_observed",
                "fact": (
                    "The reconciled revenue window contains zero paid affiliate "
                    "revenue, but no trusted intent evidence is available"
                ),
                "evidence": {
                    "window_start": revenue.get("window_start"),
                    "window_end": revenue.get("window_end"),
                    "positive_paid_revenue": False,
                    "paid_transactions": 0,
                    "trusted_intent": False,
                    "decision_use": "OUTCOME_ONLY_NO_FUNNEL_INFERENCE",
                },
            })
        elif scorecard["growth_experiment_eligible"]:
            priorities.append({
                "rank": 4,
                "type": "design_one_revenue_experiment",
                "scope": ["one revenue-producing source/funnel"],
                "reason": "Scale only verified money with guardrails intact",
            })
        elif cadence == "daily" and revenue_state["positive_outcome"]:
            findings.append({
                "severity": "INFO",
                "id": "growth_review_deferred_to_weekly",
                "fact": "Positive verified revenue is held for the weekly experiment review",
                "evidence": scorecard["evidence_hash"],
            })

    if scorecard["hard_blockers"]:
        priorities = [
            row for row in priorities
            if row["type"] not in {
                "audit_offer_and_attribution", "design_one_revenue_experiment"
            }
        ]
    priorities = sorted(
        priorities,
        key=lambda row: _priority_learning_key(row, learning_state or {}),
    )
    max_items = int(contract.get("limits", {}).get("max_priorities_per_run", 3))
    priorities = priorities[:max_items]
    action_queue = build_action_queue(
        priorities, owner_actions, contract, observation.get("observed_at")
    )
    return {
        "schema_version": 2,
        "findings": findings,
        "priorities": priorities,
        "owner_actions": owner_actions,
        "action_queue": action_queue,
        "maturity_scorecard": scorecard,
        "decision_readiness": readiness,
        "learning_ready": scorecard["learning_ready"],
        "learning_blockers": scorecard["learning_blockers"],
        "next_data_actions": scorecard["next_data_actions"],
        "external_mutation_authorized": False,
    }


def _diagnose_with_error_learning(observation, contract, *, cadence, now,
                                  previous_scorecard, previous_learning_state,
                                  run_id):
    """Build a final diagnosis whose progression is gated by same-run errors."""
    learning_config = contract.get("error_learning", {})

    def build_learning(selected_diagnosis):
        return build_error_learning_state(
            previous_learning_state,
            selected_diagnosis,
            run_id=run_id,
            observed_at=observation.get("observed_at"),
            max_incidents=learning_config.get("max_incidents", 500),
            recurring_after_runs=learning_config.get("recurring_after_runs", 2),
            now=now,
        )

    diagnosis = diagnose(
        observation,
        contract,
        cadence=cadence,
        now=now,
        previous_scorecard=previous_scorecard,
        learning_state=previous_learning_state,
    )
    error_learning = build_learning(diagnosis)
    regressions = error_learning.get("summary", {}).get(
        "regressed_incidents", []
    )
    regressions = sorted(set(
        item for item in regressions if isinstance(item, str) and item
    ))
    if regressions:
        # Re-run the deterministic diagnosis with the newly observed regression
        # gate, then rebuild action lifecycle facts from that final queue.  This
        # prevents an IMPROVED label or growth experiment from surviving beside
        # a same-run incident that had previously been resolved.
        diagnosis = diagnose(
            observation,
            contract,
            cadence=cadence,
            now=now,
            previous_scorecard=previous_scorecard,
            learning_state=previous_learning_state,
            regressed_incidents=regressions,
        )
        error_learning = build_learning(diagnosis)
        final_regressions = error_learning.get("summary", {}).get(
            "regressed_incidents", []
        )
        if final_regressions != regressions:
            raise ValueError("error-learning regression gate is not deterministic")
    return diagnosis, error_learning


def validate(run_dir, observation, diagnosis, contract=None, now=None,
             learning_state=None, error_learning=None,
             require_runtime_contract=False, previous_scorecard=None,
             run_id=None):
    errors = []
    if not all((run_dir / name).is_file() for name in ("observation.json", "diagnosis.json")):
        errors.append("required phase artifact is missing")
    if diagnosis.get("external_mutation_authorized") is not False:
        errors.append("local-safe run granted an external mutation")
    contract = contract or _load(CONTRACT)
    errors.extend(improvement_contract_errors(contract))
    runtime_contract = observation.get("runtime_contract")
    if require_runtime_contract or runtime_contract is not None:
        errors.extend(runtime_contract_errors(
            runtime_contract, verify_current=require_runtime_contract
        ))
    maximum = min(int(contract.get("limits", {}).get("max_priorities_per_run", 3)), 3)
    priorities = diagnosis.get("priorities")
    priorities = priorities if isinstance(priorities, list) else []
    if len(priorities) > maximum:
        errors.append("priority limit exceeded")
    expected_guards = {
        key for kind, key in GUARDRAIL_EVIDENCE.values() if kind == "guard"
    }
    guards = observation.get("guards")
    guards = guards if isinstance(guards, dict) else {}
    failed_guards = sorted(name for name in expected_guards if not (
        isinstance(guards.get(name), dict)
        and guards[name].get("passed") is True
        and isinstance(guards[name].get("exit_code"), int)
        and not isinstance(guards[name].get("exit_code"), bool)
        and guards[name].get("exit_code") == 0
    ))
    sources = observation.get("sources")
    sources = sources if isinstance(sources, dict) else {}
    official = sources.get("official_sources")
    official = official if isinstance(official, dict) else {}
    readiness = observation.get("decision_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    readiness_errors = readiness_contract_errors(
        readiness, observation, decision_time=now
    )
    if require_runtime_contract:
        readiness_errors.extend(readiness_file_evidence_errors(readiness, run_dir))
    readiness_blockers = readiness.get("blockers")
    readiness_blockers = readiness_blockers if isinstance(readiness_blockers, list) else []
    decision_ready = bool(
        not readiness_errors
        and readiness.get("status") == "READY"
        and readiness.get("growth_ready") is True
        and readiness.get("publication_ready") is True
        and not readiness_blockers
    )
    if readiness_errors:
        errors.append("decision readiness evidence invalid: " +
                      ", ".join(readiness_errors))
    scorecard = diagnosis.get("maturity_scorecard")
    if not _scorecard_hash_valid(scorecard):
        errors.append("maturity scorecard hash is missing or mismatched")
        scorecard = scorecard if isinstance(scorecard, dict) else {}
    cadence = scorecard.get("cadence")
    evaluated_at = _parse_utc(scorecard.get("evaluated_at"))
    expected_diagnosis = None
    expected_error_learning = None
    regressed_incidents = []
    if error_learning is not None:
        if (
            not isinstance(error_learning, dict)
            or not isinstance(run_id, str)
            or not RUN_ID_RE.fullmatch(run_id)
            or ".." in run_id
            or not isinstance(learning_state, dict)
        ):
            errors.append(
                "error-learning validation requires a safe run identity and prior state"
            )
        elif error_learning.get("last_run_id") != run_id:
            errors.append("error-learning run identity is mismatched")
        elif require_runtime_contract and Path(run_dir).name != run_id:
            errors.append("validation run directory identity is mismatched")
        elif cadence in {"daily", "weekly"} and evaluated_at is not None:
            try:
                expected_diagnosis, expected_error_learning = (
                    _diagnose_with_error_learning(
                        observation,
                        contract,
                        cadence=cadence,
                        now=evaluated_at,
                        previous_scorecard=previous_scorecard,
                        previous_learning_state=learning_state,
                        run_id=run_id,
                    )
                )
                expected_diagnosis["error_learning"] = {
                    "state_hash": expected_error_learning["state_hash"],
                    **expected_error_learning["summary"],
                }
                regressed_incidents = expected_error_learning.get(
                    "summary", {}
                ).get("regressed_incidents", [])
                regressed_incidents = sorted(set(
                    item for item in regressed_incidents
                    if isinstance(item, str) and item
                ))
                if error_learning != expected_error_learning:
                    errors.append(
                        "error-learning state contradicts prior state and current evidence"
                    )
            except Exception as exc:
                expected_diagnosis = None
                expected_error_learning = None
                errors.append(
                    "error-learning state could not be recomputed (%s)"
                    % type(exc).__name__
                )
    if cadence not in {"daily", "weekly"} or evaluated_at is None:
        errors.append("maturity scorecard cadence or evaluation time is invalid")
    else:
        try:
            expected_scorecard = build_maturity_scorecard(
                observation, contract, cadence=cadence,
                now=evaluated_at, previous=previous_scorecard,
                regressed_incidents=regressed_incidents,
            )
        except Exception as exc:
            expected_scorecard = None
            errors.append(
                "maturity scorecard could not be recomputed (%s)" % type(exc).__name__
            )
        if expected_scorecard is not None:
            # Compare the complete canonical scorecard.  A field whitelist let
            # forged schema/denominator/progression values survive after an
            # attacker simply resealed the self-hash.
            for key in sorted(set(scorecard) | set(expected_scorecard)):
                if scorecard.get(key) != expected_scorecard.get(key):
                    errors.append("maturity scorecard contradicts evidence: " + key)
    hard_blockers = scorecard.get("hard_blockers")
    hard_blockers = hard_blockers if isinstance(hard_blockers, list) else [
        "maturity_scorecard_invalid"
    ]
    growth_actions = [
        item for item in priorities
        if isinstance(item, dict) and item.get("type") == "design_one_revenue_experiment"
    ]
    if growth_actions and (
        cadence != "weekly"
        or scorecard.get("growth_experiment_eligible") is not True
        or hard_blockers
        or len(growth_actions) > int(
            contract.get("limits", {}).get("max_growth_experiments_per_week", 1)
        )
    ):
        errors.append("growth experiment selected without weekly scorecard eligibility")
    if hard_blockers and any(
        item.get("type") in {
            "audit_offer_and_attribution", "design_one_revenue_experiment"
        }
        for item in priorities if isinstance(item, dict)
    ):
        errors.append("growth work selected while a hard blocker is unresolved")
    if diagnosis.get("learning_ready") is not scorecard.get("learning_ready"):
        errors.append("diagnosis learning readiness contradicts scorecard")
    if diagnosis.get("learning_blockers") != scorecard.get("learning_blockers"):
        errors.append("diagnosis learning blockers contradict scorecard")
    if diagnosis.get("next_data_actions") != scorecard.get("next_data_actions"):
        errors.append("diagnosis next data actions contradict scorecard")
    if cadence in {"daily", "weekly"} and evaluated_at is not None:
        if expected_diagnosis is None and error_learning is None:
            try:
                expected_diagnosis = diagnose(
                    observation, contract, cadence=cadence, now=evaluated_at,
                    previous_scorecard=previous_scorecard,
                    learning_state=learning_state,
                    regressed_incidents=regressed_incidents,
                )
            except Exception as exc:
                expected_diagnosis = None
                errors.append(
                    "diagnosis could not be recomputed (%s)" % type(exc).__name__
                )
        if expected_diagnosis is not None:
            for key in sorted(set(diagnosis) | set(expected_diagnosis)):
                if diagnosis.get(key) != expected_diagnosis.get(key):
                    errors.append("diagnosis contradicts evidence: " + key)
    current = now or dt.datetime.now(dt.timezone.utc)
    expected_queue = build_action_queue(
        priorities,
        diagnosis.get("owner_actions", [])
        if isinstance(diagnosis.get("owner_actions"), list) else [],
        contract,
        observation.get("observed_at"),
    )
    if diagnosis.get("action_queue") != expected_queue:
        errors.append("action queue does not match diagnosed priorities and owner requests")
    errors.extend(action_queue_errors(
        diagnosis.get("action_queue"), contract, now=current
    ))
    for action in diagnosis.get("owner_actions", []):
        if not isinstance(action, dict):
            errors.append("owner action is malformed")
            continue
        body = {key: action.get(key) for key in (
            "kind", "request_only", "reason", "evidence", "expires_at"
        )}
        stable = {key: action.get(key) for key in ("kind", "reason", "evidence")}
        try:
            hash_valid = action.get("action_hash") == _canonical_hash(body)
            dedupe_valid = action.get("dedupe_key") == _canonical_hash(stable)
        except (TypeError, ValueError):
            hash_valid = dedupe_valid = False
        if (
            action.get("request_only") is not True
            or action.get("kind") not in OWNER_ACTION_KINDS
            or not hash_valid or not dedupe_valid
        ):
            errors.append("owner action is not a hash-bound request")
    if error_learning is not None:
        selected_error_learning = (
            error_learning if isinstance(error_learning, dict) else {}
        )
        errors.extend(error_learning_state_errors(
            selected_error_learning,
            current_findings=diagnosis.get("findings", []),
            not_after=current,
        ))
        learning_updated = _parse_utc(selected_error_learning.get("updated_at"))
        observation_time = _parse_utc(observation.get("observed_at"))
        if observation_time is None or learning_updated != observation_time:
            errors.append(
                "error-learning updated_at does not match the current observation"
            )
        expected_learning_summary = {
            "state_hash": selected_error_learning.get("state_hash"),
            **selected_error_learning.get("summary", {}),
        }
        if diagnosis.get("error_learning") != expected_learning_summary:
            errors.append("diagnosis error-learning summary is missing or mismatched")
    operational_blockers = []
    if failed_guards:
        operational_blockers.append("guard_failure:" + ",".join(failed_guards))
    operational_blockers.extend(str(item) for item in readiness_blockers)
    operational_blockers.extend("readiness_invalid:" + str(item)
                                for item in readiness_errors)
    if scorecard.get("evidence_status") != "CURRENT":
        operational_blockers.append("maturity_evidence_not_current")
    operational_blockers.extend("maturity:" + str(item) for item in hard_blockers)
    operational_blockers.extend(
        "error_regression:" + item for item in regressed_incidents
    )
    operational_blockers = list(dict.fromkeys(operational_blockers))
    operational_ready = bool(
        not errors and not failed_guards and decision_ready
        and scorecard.get("learning_ready") is True and not hard_blockers
        and not regressed_incidents
    )
    return {"schema_version": 2, "passed": not errors, "errors": errors,
            "control_state": (
                "INVALID" if errors else
                "READY" if operational_ready else "VALID_WITH_BLOCKERS"
            ),
            "operational_blockers": operational_blockers,
            "growth_ready": operational_ready,
            "publication_ready": operational_ready,
            "maturity_score": scorecard.get("score"),
            "maturity_stage": scorecard.get("stage", "unknown"),
            "growth_experiment_eligible": bool(
                operational_ready
                and scorecard.get("growth_experiment_eligible") is True
            ),
            "guard_summary": {
                name: bool(
                    isinstance(guards.get(name), dict)
                    and guards[name].get("passed") is True
                    and guards[name].get("exit_code") == 0
                )
                for name in sorted(expected_guards)
            }}


def render_report(run_id, cadence, observation, diagnosis, validation,
                  control_health=None):
    sources = observation.get("sources", {})
    metrics = observation.get("metrics", {})
    ga4 = sources.get("ga4", {})
    gsc = sources.get("gsc", {})
    revenue = metrics.get("verified_affiliate_revenue", {})
    scorecard = diagnosis.get("maturity_scorecard", {})
    progression = scorecard.get("progression", {})
    error_learning = diagnosis.get("error_learning", {})
    health_kpis = (control_health or {}).get("kpis", {})
    false_fatal = health_kpis.get("publication_blocker_false_fatal_count")
    terminal_rate = health_kpis.get("terminal_control_run_rate_7d")
    runtime_contract = observation.get("runtime_contract", {})
    lines = [
        "# Improvement Loop — %s" % run_id,
        "",
        "- cadence: `%s`" % cadence,
        "- mode: `local-safe`",
        "- public identity: `เงินเดือนสมองทอง`",
        "- external mutation: `BLOCKED`",
        "- GA4: `%s / %s`" % (
            ga4.get("trust", {}).get("label", "UNTRUSTED"),
            ga4.get("bundle", {}).get("state", "UNAVAILABLE"),
        ),
        "- GSC bundle: `%s`" % gsc.get("bundle", {}).get("state", "UNAVAILABLE"),
        "- revenue ledger: `%s / %s`" % (
            revenue.get("quality_state", "UNAVAILABLE"),
            "LEARNING_READY" if scorecard.get("learning_ready") else "BLOCKED",
        ),
        "- decision readiness: `%s`" % (
            observation.get("decision_readiness", {}).get("status", "BLOCKED")
        ),
        "- maturity: `%s/%s · %s`" % (
            scorecard.get("score", 0), scorecard.get("maximum_score", 100),
            scorecard.get("stage", "unknown"),
        ),
        "- score progression: `%s`" % progression.get("status", "UNAVAILABLE"),
        "- control validation: `%s`" % validation.get("control_state", "INVALID"),
        "- runtime contract: `%s`" %
        str(runtime_contract.get("contract_hash", "UNAVAILABLE"))[:16],
        "",
        "## Priorities",
        "",
    ]
    if diagnosis["priorities"]:
        for display_rank, item in enumerate(diagnosis["priorities"], start=1):
            lines.append("%d. **%s** — %s" % (display_rank, item["type"], item["reason"]))
    else:
        lines.append("- No safe improvement action was selected.")
    lines.extend(["", "## Data feedback", ""])
    if diagnosis.get("next_data_actions"):
        for item in diagnosis["next_data_actions"]:
            lines.append("- `%s`: `%s` (%s)" % (
                item.get("source", "unknown"), item.get("action", "BLOCKED"),
                item.get("reason_code", "unknown"),
            ))
    elif diagnosis.get("learning_ready") is True:
        lines.append("- All three learning sources are current.")
    else:
        blockers = diagnosis.get("learning_blockers")
        blockers = blockers if isinstance(blockers, list) else []
        lines.append(
            "- Learning sources are BLOCKED/INVALID; no safe data action was derived."
        )
        for blocker in blockers:
            lines.append("  - `%s`" % blocker)
    lines.extend(["", "## Error learning", "",
                  "- current incidents: `%s`" %
                  error_learning.get("current_incidents", 0),
                  "- recurring incidents: `%s`" %
                  len(error_learning.get("recurring_incidents", [])),
                  "- regressions this run: `%s`" %
                  len(error_learning.get("regressed_incidents", [])),
                  "- resolved this run: `%s`" %
                  len(error_learning.get("resolved_incidents", [])),
                  "- terminal control-run rate (7d): `%s`" %
                  (terminal_rate if terminal_rate is not None else "UNAVAILABLE"),
                  "- publication-blocker false-fatals observed: `%s`" %
                  (false_fatal if false_fatal is not None else "UNAVAILABLE")])
    lines.extend(["", "## Owner action requests", ""])
    if diagnosis["owner_actions"]:
        for item in diagnosis["owner_actions"]:
            lines.append("- `%s` — %s · hash `%s`" %
                         (item["kind"], item["reason"], item["action_hash"][:12]))
    else:
        lines.append("- None")
    lines.extend(["", "## Validation", "",
                  "- control validation: `%s`" % ("PASS" if validation["passed"] else "FAIL"),
                  "- growth readiness: `%s`" %
                  ("READY" if validation.get("growth_ready") else "BLOCKED"),
                   "- publication readiness: `%s`" %
                   ("READY" if validation.get("publication_ready") else "BLOCKED"),
                  "- growth experiment: `%s`" %
                  ("ELIGIBLE" if validation.get("growth_experiment_eligible") else "BLOCKED"), ""])
    return "\n".join(lines)


def _load_previous_weekly_scorecard(runs_root):
    candidates = []
    selected_root = Path(runs_root)
    if not selected_root.is_dir():
        return None
    try:
        contract = _load(CONTRACT)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if improvement_contract_errors(contract):
        return None
    current = dt.datetime.now(dt.timezone.utc)
    for run_dir in selected_root.iterdir():
        if not run_dir.is_dir():
            continue
        try:
            run = _load(run_dir / "run.json")
            scorecard = _load(run_dir / "maturity-scorecard.json")
            validation = _load(run_dir / "validation.json")
            validation_hash = _canonical_hash(validation)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        finished = _parse_utc(run.get("finished_at"))
        started = _parse_utc(run.get("started_at"))
        evaluated = _parse_utc(scorecard.get("evaluated_at"))
        if (
            run.get("schema_version") != 2
            or run.get("run_id") != run_dir.name
            or run.get("cadence") != "weekly"
            or started is None or finished is None or evaluated is None
            or not (started <= evaluated <= finished <= current)
            or run.get("status") not in {
                "COMPLETED_WITH_BLOCKERS", "COMPLETED"
            }
            or not _has_complete_evidence_bundle(run_dir, run, contract=contract)
            or run.get("validation_passed") is not True
            or validation.get("passed") is not True
            or scorecard.get("cadence") != "weekly"
            or scorecard.get("evidence_status") != "CURRENT"
            or not _scorecard_hash_valid(scorecard)
            or run.get("maturity_score") != scorecard.get("score")
            or run.get("maturity_stage") != scorecard.get("stage")
            or run.get("maturity_scorecard_hash") != scorecard.get(
                "scorecard_hash"
            )
            or run.get("validation_hash") != validation_hash
        ):
            continue
        candidates.append((finished, run_dir.name, scorecard))
    return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def execute(cadence="daily", mode="local-safe", run_id=None):
    if cadence not in {"daily", "weekly"}:
        raise ValueError("cadence must be daily or weekly")
    if mode != "local-safe":
        raise ValueError("only local-safe mode is implemented")
    contract = _load(CONTRACT)
    contract_errors = improvement_contract_errors(contract)
    if contract_errors:
        raise ValueError("invalid improvement policy: " + "; ".join(contract_errors))
    run_id = run_id or dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).strftime("%Y%m%d-%H%M%S")
    if not RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
        raise ValueError("run_id must be a safe local identifier")
    runs_root = Path(IMPROVEMENT_RUNS_DIR).resolve()
    with _exclusive_run_lock(runs_root):
        return _execute_locked(cadence, mode, run_id, contract, runs_root)


def _execute_locked(cadence, mode, run_id, contract, runs_root):
    previous_learning_state = _load_error_learning_state(runs_root)
    previous_scorecard = (
        _load_previous_weekly_scorecard(runs_root) if cadence == "weekly" else None
    )
    run_dir = (runs_root / run_id).resolve()
    if run_dir.parent != runs_root:
        raise ValueError("run_id escapes the private run directory")
    run_dir.mkdir(parents=True, exist_ok=False)
    started_at = dt.datetime.now(dt.timezone.utc)
    state = {"schema_version": 2, "run_id": run_id, "cadence": cadence,
             "mode": mode, "status": "STARTED",
             # Observation snapshots currently declare whole-second precision.
             # Keep the lower lifecycle bound at that same conservative
             # precision; the exact evaluation and finish instants below retain
             # microseconds so freshness and terminal ordering stay fail-closed.
             "started_at": started_at.isoformat(timespec="seconds")}
    _atomic(run_dir / "run.json", state)
    _event(run_dir, "run", "started")
    run_committed = False
    try:
        runtime_contract = collect_runtime_contract()
        observation = observe(run_dir, runtime_contract=runtime_contract)
        _event(run_dir, "diagnose", "started")
        diagnosis_at = dt.datetime.now(dt.timezone.utc)
        diagnosis, error_learning = _diagnose_with_error_learning(
            observation,
            contract,
            cadence=cadence,
            now=diagnosis_at,
            previous_scorecard=previous_scorecard,
            previous_learning_state=previous_learning_state,
            run_id=run_id,
        )
        diagnosis["error_learning"] = {
            "state_hash": error_learning["state_hash"],
            **error_learning["summary"],
        }
        _atomic(run_dir / "diagnosis.json", diagnosis)
        _atomic(run_dir / "maturity-scorecard.json",
                diagnosis["maturity_scorecard"])
        _atomic(run_dir / "action-queue.json", diagnosis["action_queue"])
        _atomic(run_dir / "error-learning.json", error_learning)
        _event(run_dir, "diagnose", "finished")
        validation = validate(
            run_dir, observation, diagnosis, contract, now=diagnosis_at,
            learning_state=previous_learning_state,
            error_learning=error_learning,
            require_runtime_contract=True,
            previous_scorecard=previous_scorecard,
            run_id=run_id,
        )
        _atomic(run_dir / "validation.json", validation)
        _event(run_dir, "validate", "finished" if validation["passed"] else "failed")
        status = (
            "FAILED_VALIDATION" if not validation["passed"]
            else "COMPLETED_WITH_BLOCKERS" if diagnosis["findings"]
            else "COMPLETED"
        )
        finished_at = dt.datetime.now(dt.timezone.utc)
        state.update({"status": status,
                      "finished_at": finished_at.isoformat(timespec="microseconds"),
                      "validation_passed": validation["passed"],
                      "validation_hash": _canonical_hash(validation),
                      "control_state": validation.get("control_state"),
                      "maturity_score": diagnosis["maturity_scorecard"]["score"],
                      "maturity_stage": diagnosis["maturity_scorecard"]["stage"],
                      "maturity_scorecard_hash": diagnosis[
                          "maturity_scorecard"
                      ]["scorecard_hash"],
                      "observation_hash": _canonical_hash(observation),
                      "diagnosis_hash": _canonical_hash(diagnosis),
                      "learning_ready": diagnosis["learning_ready"],
                      "error_learning_state_hash": error_learning["state_hash"],
                      "open_incident_count": error_learning["summary"]["open_incidents"],
                      "regressed_incident_count": len(
                          error_learning["summary"]["regressed_incidents"]
                      ),
                      "priority_count": len(diagnosis["priorities"]),
                      "owner_action_count": len(diagnosis["owner_actions"])})
        effective_learning = (
            error_learning if validation["passed"] else previous_learning_state
        )
        control_health = build_control_health(
            runs_root, effective_learning, now=finished_at, current_state=state
        )
        _atomic(run_dir / "control-health.json", control_health)
        report = render_report(
            run_id, cadence, observation, diagnosis, validation,
            control_health=control_health,
        )
        (run_dir / "report.md").write_text(report, encoding="utf-8", newline="\n")
        _atomic(run_dir / "owner-actions.json", {"actions": diagnosis["owner_actions"]})
        # Commit the per-run terminal marker before advancing either global
        # pointer.  A later write failure leaves a recoverable terminal run,
        # never a global learning state bound to STARTED/FAILED evidence.
        _atomic(run_dir / "run.json", state)
        run_committed = True
        _event(run_dir, "run", "finished", state["status"])
        if validation["passed"]:
            _atomic(runs_root / ERROR_LEARNING_STATE_FILE, error_learning)
        _atomic(runs_root / CONTROL_HEALTH_FILE, control_health)
        return state, run_dir
    except Exception as exc:
        if run_committed:
            (run_dir / "recovery-required.txt").write_text(
                "terminal run committed; global pointer update failed\n"
                "%s: %s\n" % (type(exc).__name__, str(exc)[:300]),
                encoding="utf-8",
                newline="\n",
            )
            _event(run_dir, "global_state", "failed", type(exc).__name__)
            raise
        state.update({"status": "FAILED",
                      "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds"),
                      "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])})
        _atomic(run_dir / "run.json", state)
        (run_dir / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _event(run_dir, "run", "failed", state["error"])
        raise


class _ImprovementArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid CLI arguments: " + message)


def main():
    parser = _ImprovementArgumentParser()
    parser.add_argument("command", choices=("run", "status"))
    parser.add_argument("--cadence", choices=("daily", "weekly"), default="daily")
    parser.add_argument("--mode", default="local-safe")
    parser.add_argument("--run-id")
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args()
        if args.command == "status":
            if args.run_id or args.mode != "local-safe":
                raise ValueError("status is read-only and does not accept run overrides")
            current = dt.datetime.now(dt.timezone.utc)
            learning = _load_error_learning_state(IMPROVEMENT_RUNS_DIR, now=current)
            health = build_control_health(IMPROVEMENT_RUNS_DIR, learning, now=current)
            evidence = health["current_evidence"]
            if args.json:
                print(json.dumps(health, ensure_ascii=False, sort_keys=True))
            else:
                print("improvement evidence: %s | decision=%s | run=%s | score=%s" % (
                    evidence["state"], evidence["decision_state"],
                    evidence["run_id"], evidence["current_score"],
                ))
            return 0 if evidence["decision_state"] == "READY_FOR_OWNER_APPROVAL" else 2
        state, run_dir = execute(args.cadence, args.mode, args.run_id)
    except Exception as exc:
        print("improvement loop FAIL: %s" % exc)
        return 3
    payload = {**state, "run_dir": str(run_dir)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print("improvement loop: %s | priorities=%d owner_actions=%d | %s" %
              (state["status"], state["priority_count"], state["owner_action_count"], run_dir))
    status = state.get("status")
    if status == "COMPLETED":
        return 0
    if status in {"COMPLETED_WITH_BLOCKERS", "FAILED_VALIDATION"}:
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
