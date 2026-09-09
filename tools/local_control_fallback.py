#!/usr/bin/env python3
"""Run a bounded local control fallback when desktop scheduler slots are stale.

This is deliberately *not* a scheduler runner and its receipts are deliberately
stored outside ``scheduler-task-receipts``.  It executes only an exact allowlist
of read-only/local-only control checks, binds the observed scheduler gaps to
their task id, due time and stable task-record hash, and writes a terminal
receipt for this manual invocation.  The receipt never repairs, backfills or
completes a scheduler slot and never grants publication authority.

No publisher, notifier, tracker, network pull, deploy, build, scheduler editor
or external task launcher is reachable from the command allowlist below.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable, Iterable

try:  # Script execution and ``python -m unittest`` have different sys.path roots.
    from tools import agent_gap_check
except ImportError:  # pragma: no cover - exercised by direct CLI execution.
    import agent_gap_check  # type: ignore


SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPT_ROOT = (
    REPO_ROOT / ".local-private" / "runtime" / "manual-control-fallback"
)
FORBIDDEN_RECEIPT_ROOT = Path(agent_gap_check.SCHEDULER_RECEIPT_ROOT).resolve()
LOCAL_TZ = agent_gap_check.LOCAL_TZ
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BLOCKING_TASK_STATES = {
    "MISSED_OR_STUCK",
    "RUNNER_FAILED",
    "STUCK",
    "COMPLETED_BLOCKED",
    "UNKNOWN",
}
TERMINAL_STATES = {
    "LOCAL_CHECKS_COMPLETED",
    "LOCAL_CHECKS_COMPLETED_BLOCKED",
    "RUNNER_FAILED",
}
CHECK_STATES = {"PASS", "BLOCKED", "COMPLETED_BLOCKED", "RUNNER_FAILED"}
SUBPROCESS_TIMEOUT_SECONDS = 300


class FallbackEvidenceError(ValueError):
    """Raised when a receipt or local evidence binding is malformed."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aware_now(value: str | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(LOCAL_TZ)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FallbackEvidenceError("--now must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FallbackEvidenceError("--now must include a UTC offset")
    return parsed.astimezone(LOCAL_TZ)


def _relative_entrypoint(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise FallbackEvidenceError("check entrypoint escapes repository") from exc


def _check_specs(now: dt.datetime) -> list[dict]:
    """Return the exact local-only allowlist for this invocation.

    Dates are frozen from the receipt clock.  The media checks cover today and
    the next two local dates so a run late in the day still covers the rolling
    48-hour editorial window without contacting any platform.
    """
    today = now.date()
    specs = [
        {
            "id": "automation_policy",
            "entrypoint": "tools/automation_policy_guard.py",
            "args": [],
            "exit_contract": {0: "PASS", 2: "BLOCKED"},
        },
        {
            "id": "privacy",
            "entrypoint": "tools/privacy_guard.py",
            "args": [],
            "exit_contract": {0: "PASS", 1: "BLOCKED", 2: "RUNNER_FAILED"},
        },
        {
            "id": "public_identity",
            "entrypoint": "tools/public_identity_guard.py",
            "args": ["--json"],
            "exit_contract": {0: "PASS", 2: "BLOCKED"},
        },
        {
            "id": "manifest_contract",
            "entrypoint": "tools/manifest_contract.py",
            "args": ["--today", today.isoformat()],
            "exit_contract": {0: "PASS", 1: "BLOCKED"},
        },
        {
            "id": "content_calendar",
            "entrypoint": "tools/content_calendar_guard.py",
            "args": ["--now", now.isoformat(), "--json"],
            "exit_contract": {
                0: "PASS", 1: "COMPLETED_BLOCKED", 2: "BLOCKED",
                3: "RUNNER_FAILED",
            },
        },
    ]
    for offset in range(3):
        local_date = today + dt.timedelta(days=offset)
        specs.append({
            "id": "daily_media_" + local_date.isoformat(),
            "entrypoint": "tools/daily_media_gate.py",
            "args": ["--today", local_date.isoformat(), "--fps", "3", "--json"],
            "exit_contract": {0: "PASS", 2: "BLOCKED"},
        })
    specs.extend([
        {
            "id": "ga4_decision_readiness",
            "entrypoint": "pipeline/ga4_readiness_report.py",
            "args": ["--now", now.isoformat()],
            "exit_contract": {0: "PASS", 2: "BLOCKED"},
        },
        {
            "id": "release_candidate_verify",
            "entrypoint": "tools/release_candidate.py",
            "args": ["verify"],
            "exit_contract": {0: "PASS", 1: "BLOCKED"},
        },
    ])
    _validate_check_specs(specs)
    return specs


def _validate_check_specs(specs: Iterable[dict]) -> None:
    """Fail closed if a future edit expands this runner into external action."""
    allowed_entrypoints = {
        "tools/automation_policy_guard.py",
        "tools/privacy_guard.py",
        "tools/public_identity_guard.py",
        "tools/manifest_contract.py",
        "tools/content_calendar_guard.py",
        "tools/daily_media_gate.py",
        "pipeline/ga4_readiness_report.py",
        "tools/release_candidate.py",
    }
    forbidden_fragments = {
        "publish", "post_agent", "schedule_fb", "schedule_ig", "deploy",
        "notify", "clicktest", "ga4_pull", "gsc_pull", "update-agent-silent",
        " pack", "--output", "--live",
    }
    seen: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict) or set(spec) != {
            "id", "entrypoint", "args", "exit_contract"
        }:
            raise FallbackEvidenceError("local check spec is malformed")
        check_id = spec["id"]
        entrypoint = spec["entrypoint"]
        args = spec["args"]
        contract = spec["exit_contract"]
        if not isinstance(check_id, str) or not check_id or check_id in seen:
            raise FallbackEvidenceError("local check id is invalid or duplicated")
        seen.add(check_id)
        if entrypoint not in allowed_entrypoints:
            raise FallbackEvidenceError("local check entrypoint is not allowlisted")
        path = (REPO_ROOT / entrypoint).resolve()
        if not path.is_file() or _relative_entrypoint(path) != entrypoint:
            raise FallbackEvidenceError("local check entrypoint is missing")
        if (not isinstance(args, list) or
                any(not isinstance(item, str) for item in args)):
            raise FallbackEvidenceError("local check arguments are malformed")
        rendered = " ".join([entrypoint, *args]).lower()
        if any(fragment in rendered for fragment in forbidden_fragments):
            raise FallbackEvidenceError("local check requests a forbidden action")
        if (not isinstance(contract, dict) or not contract or
                any(not isinstance(code, int) or isinstance(code, bool)
                    for code in contract) or
                any(state not in CHECK_STATES for state in contract.values())):
            raise FallbackEvidenceError("local check exit contract is malformed")


def _scheduler_snapshot(now: dt.datetime) -> dict:
    records, error = agent_gap_check.scheduler_records()
    if error or not isinstance(records, list):
        payload = {
            "status": "UNKNOWN",
            "reason_code": "SCHEDULER_REGISTRY_UNAVAILABLE",
            "record_count": 0,
            "blocking_task_count": 0,
            "blocking_tasks": [],
        }
        payload["snapshot_sha256"] = _sha_bytes(_canonical(payload))
        return payload

    _verdict, _detail, graded = agent_gap_check.judge_scheduler(now, records)
    by_identity = {
        (row.get("source"), row.get("id")): row for row in records
    }
    bindings = []
    for row in graded:
        if row.get("status") not in BLOCKING_TASK_STATES:
            continue
        key = (row.get("source"), row.get("id"))
        source_row = by_identity.get(key)
        record_sha = (source_row or {}).get("_task_record_sha256")
        due_at = row.get("due_at")
        if (not all(isinstance(item, str) and item
                    for item in (key[0], key[1], due_at)) or
                not isinstance(record_sha, str) or
                not SHA256_RE.fullmatch(record_sha)):
            payload = {
                "status": "UNKNOWN",
                "reason_code": "SCHEDULER_BINDING_INVALID",
                "record_count": len(records),
                "blocking_task_count": 0,
                "blocking_tasks": [],
            }
            payload["snapshot_sha256"] = _sha_bytes(_canonical(payload))
            return payload
        bindings.append({
            "source": key[0],
            "task_id": key[1],
            "due_at": due_at,
            "scheduler_state": row["status"],
            "last_attempt_state": row.get("last_attempt_status"),
            "task_record_sha256": record_sha,
        })
    bindings.sort(key=lambda item: (
        item["due_at"], item["source"], item["task_id"]
    ))
    payload = {
        "status": "BOUND",
        "reason_code": None,
        "record_count": len(records),
        "blocking_task_count": len(bindings),
        "blocking_tasks": bindings,
    }
    payload["snapshot_sha256"] = _sha_bytes(_canonical(payload))
    return payload


def _run_check(
    spec: dict,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    entrypoint = (REPO_ROOT / spec["entrypoint"]).resolve()
    stored_argv = ["python", spec["entrypoint"], *spec["args"]]
    command_binding = {
        "argv": stored_argv,
        "entrypoint_sha256": _sha_file(entrypoint),
        "exit_contract": {
            str(code): state for code, state in sorted(spec["exit_contract"].items())
        },
    }
    command_sha = _sha_bytes(_canonical(command_binding))
    env = os.environ.copy()
    env.update({
        "NGERNDUANGOLD_LOCAL_FALLBACK": "1",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "",
    })
    try:
        result = command_runner(
            [sys.executable, str(entrypoint), *spec["args"]],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        exit_code = result.returncode
        stdout = result.stdout if isinstance(result.stdout, bytes) else str(
            result.stdout or ""
        ).encode("utf-8", errors="replace")
        stderr = result.stderr if isinstance(result.stderr, bytes) else str(
            result.stderr or ""
        ).encode("utf-8", errors="replace")
        state = spec["exit_contract"].get(exit_code, "RUNNER_FAILED")
        failure_class = None
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8", errors="replace")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8", errors="replace")
        state = "RUNNER_FAILED"
        failure_class = "TimeoutExpired"
    except Exception as exc:  # Evidence remains terminal without leaking details.
        exit_code = None
        stdout = b""
        stderr = b""
        state = "RUNNER_FAILED"
        failure_class = type(exc).__name__
    return {
        "id": spec["id"],
        "argv": stored_argv,
        "entrypoint_sha256": command_binding["entrypoint_sha256"],
        "command_sha256": command_sha,
        "exit_code": exit_code,
        "state": state,
        "failure_class": failure_class,
        "stdout_bytes": len(stdout),
        "stdout_sha256": _sha_bytes(stdout),
        "stderr_bytes": len(stderr),
        "stderr_sha256": _sha_bytes(stderr),
    }


def _terminal_state(snapshot: dict, checks: list[dict]) -> tuple[str, list[str]]:
    blockers = []
    if snapshot["status"] != "BOUND":
        blockers.append(snapshot["reason_code"] or "SCHEDULER_BINDING_UNKNOWN")
    elif snapshot["blocking_task_count"]:
        blockers.append("SCHEDULER_DUE_GAPS_REMAIN_%d" % snapshot["blocking_task_count"])
    failed = [item["id"] for item in checks if item["state"] == "RUNNER_FAILED"]
    blocked = [
        item["id"] for item in checks
        if item["state"] in {"BLOCKED", "COMPLETED_BLOCKED"}
    ]
    blockers.extend("CHECK_RUNNER_FAILED_" + item for item in failed)
    blockers.extend("CHECK_BLOCKED_" + item for item in blocked)
    if failed:
        return "RUNNER_FAILED", blockers
    if blockers:
        return "LOCAL_CHECKS_COMPLETED_BLOCKED", blockers
    return "LOCAL_CHECKS_COMPLETED", blockers


def _receipt_integrity(document: dict) -> str:
    unsigned = dict(document)
    unsigned.pop("receipt_integrity_sha256", None)
    return _sha_bytes(_canonical(unsigned))


def _safe_receipt_root(receipt_root: Path) -> Path:
    root = receipt_root.resolve()
    try:
        root.relative_to(FORBIDDEN_RECEIPT_ROOT)
    except ValueError:
        pass
    else:
        raise FallbackEvidenceError(
            "manual fallback receipts cannot enter scheduler-task-receipts"
        )
    return root


def _write_receipt(document: dict, receipt_root: Path) -> Path:
    root = _safe_receipt_root(receipt_root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = document["started_at"].replace("-", "").replace(":", "")
    stamp = stamp.replace("+07:00", "+0700").replace(".", "")
    target = root / (stamp + "-" + document["run_id"][:12] + ".json")
    if target.exists():
        raise FallbackEvidenceError("fallback receipt target already exists")
    raw = json.dumps(
        document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode("utf-8") + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=".fallback-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target


def run_fallback(
    *,
    now: dt.datetime,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
    scheduler_snapshot: dict | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[dict, Path]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise FallbackEvidenceError("fallback clock must be timezone-aware")
    now = now.astimezone(LOCAL_TZ)
    started_at = now.isoformat()
    snapshot = scheduler_snapshot if scheduler_snapshot is not None else _scheduler_snapshot(now)
    _validate_snapshot(snapshot)
    specs = _check_specs(now)
    checks = [_run_check(spec, command_runner=command_runner) for spec in specs]
    completed_at = dt.datetime.now(LOCAL_TZ).isoformat()
    terminal_state, blockers = _terminal_state(snapshot, checks)
    producer_sha = _sha_file(Path(__file__).resolve())
    run_basis = {
        "started_at": started_at,
        "producer_sha256": producer_sha,
        "scheduler_snapshot_sha256": snapshot["snapshot_sha256"],
        "command_sha256": [item["command_sha256"] for item in checks],
    }
    run_id = _sha_bytes(_canonical(run_basis))
    result_sha = _sha_bytes(_canonical({
        "scheduler_snapshot": snapshot,
        "checks": checks,
        "terminal_state": terminal_state,
        "blockers": blockers,
    }))
    document = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": "MANUAL_LOCAL_CONTROL_FALLBACK",
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "producer": {
            "path": "tools/local_control_fallback.py",
            "sha256": producer_sha,
        },
        "scope": {
            "local_only": True,
            "network_allowed": False,
            "scheduler_mutation_allowed": False,
            "external_task_launch_allowed": False,
            "publication_allowed": False,
            "notification_allowed": False,
        },
        "scheduler_claims": {
            "scheduler_dispatch_proven": False,
            "scheduler_task_completion_claimed": False,
            "due_slots_repaired_or_backfilled": False,
            "compatible_with_scheduler_task_receipt": False,
        },
        "scheduler_snapshot": snapshot,
        "checks": checks,
        "terminal": {
            "state": terminal_state,
            "result_sha256": result_sha,
            "blockers": blockers,
            "meaning": (
                "terminal evidence for this manual local control invocation only; "
                "scheduler slots and external deliverables remain unchanged"
            ),
        },
    }
    document["receipt_integrity_sha256"] = _receipt_integrity(document)
    path = _write_receipt(document, receipt_root)
    return document, path


def _validate_snapshot(snapshot: object) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "status", "reason_code", "record_count", "blocking_task_count",
        "blocking_tasks", "snapshot_sha256",
    }:
        raise FallbackEvidenceError("scheduler snapshot contract is malformed")
    claimed_sha = snapshot["snapshot_sha256"]
    unsigned = dict(snapshot)
    unsigned.pop("snapshot_sha256")
    if (not isinstance(claimed_sha, str) or not SHA256_RE.fullmatch(claimed_sha) or
            claimed_sha != _sha_bytes(_canonical(unsigned))):
        raise FallbackEvidenceError("scheduler snapshot hash mismatch")
    if snapshot["status"] not in {"BOUND", "UNKNOWN"}:
        raise FallbackEvidenceError("scheduler snapshot status is unsupported")
    if (not isinstance(snapshot["record_count"], int) or
            isinstance(snapshot["record_count"], bool) or
            snapshot["record_count"] < 0 or
            not isinstance(snapshot["blocking_task_count"], int) or
            isinstance(snapshot["blocking_task_count"], bool) or
            snapshot["blocking_task_count"] < 0 or
            not isinstance(snapshot["blocking_tasks"], list) or
            snapshot["blocking_task_count"] != len(snapshot["blocking_tasks"])):
        raise FallbackEvidenceError("scheduler snapshot counts are malformed")
    required_binding = {
        "source", "task_id", "due_at", "scheduler_state",
        "last_attempt_state", "task_record_sha256",
    }
    for item in snapshot["blocking_tasks"]:
        if not isinstance(item, dict) or set(item) != required_binding:
            raise FallbackEvidenceError("scheduler task binding is malformed")
        if (item["scheduler_state"] not in BLOCKING_TASK_STATES or
                not isinstance(item["task_record_sha256"], str) or
                not SHA256_RE.fullmatch(item["task_record_sha256"])):
            raise FallbackEvidenceError("scheduler task binding is invalid")
        for key in ("source", "task_id", "due_at"):
            if not isinstance(item[key], str) or not item[key]:
                raise FallbackEvidenceError("scheduler task identity is invalid")


def validate_receipt(
    path: Path,
    *,
    verify_current_code: bool = True,
    verify_current_scheduler: bool = True,
) -> dict:
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise FallbackEvidenceError("receipt is unreadable strict JSON") from exc
    required_top = {
        "schema_version", "receipt_kind", "run_id", "started_at", "completed_at",
        "producer", "scope", "scheduler_claims", "scheduler_snapshot", "checks",
        "terminal", "receipt_integrity_sha256",
    }
    if not isinstance(document, dict) or set(document) != required_top:
        raise FallbackEvidenceError("receipt top-level contract is malformed")
    if (not isinstance(document["schema_version"], int) or
            isinstance(document["schema_version"], bool) or
            document["schema_version"] != SCHEMA_VERSION or
            document["receipt_kind"] != "MANUAL_LOCAL_CONTROL_FALLBACK"):
        raise FallbackEvidenceError("receipt schema is unsupported")
    if document["receipt_integrity_sha256"] != _receipt_integrity(document):
        raise FallbackEvidenceError("receipt integrity hash mismatch")
    _validate_snapshot(document["scheduler_snapshot"])
    try:
        started_at = dt.datetime.fromisoformat(document["started_at"])
        completed_at = dt.datetime.fromisoformat(document["completed_at"])
    except (TypeError, ValueError) as exc:
        raise FallbackEvidenceError("receipt timestamps are malformed") from exc
    if (started_at.tzinfo is None or started_at.utcoffset() is None or
            completed_at.tzinfo is None or completed_at.utcoffset() is None or
            completed_at < started_at):
        raise FallbackEvidenceError("receipt timestamps are not a valid interval")
    if verify_current_scheduler:
        current_snapshot = _scheduler_snapshot(started_at.astimezone(LOCAL_TZ))
        if current_snapshot != document["scheduler_snapshot"]:
            raise FallbackEvidenceError(
                "receipt scheduler task/due/hash binding is stale"
            )
    claims = document["scheduler_claims"]
    if claims != {
        "scheduler_dispatch_proven": False,
        "scheduler_task_completion_claimed": False,
        "due_slots_repaired_or_backfilled": False,
        "compatible_with_scheduler_task_receipt": False,
    }:
        raise FallbackEvidenceError("receipt makes an unsupported scheduler claim")
    scope = document["scope"]
    if scope != {
        "local_only": True,
        "network_allowed": False,
        "scheduler_mutation_allowed": False,
        "external_task_launch_allowed": False,
        "publication_allowed": False,
        "notification_allowed": False,
    }:
        raise FallbackEvidenceError("receipt scope is not local-only")
    terminal = document["terminal"]
    if (not isinstance(terminal, dict) or
            terminal.get("state") not in TERMINAL_STATES or
            not isinstance(terminal.get("result_sha256"), str) or
            not SHA256_RE.fullmatch(terminal["result_sha256"]) or
            not isinstance(terminal.get("blockers"), list)):
        raise FallbackEvidenceError("receipt terminal contract is malformed")
    checks = document["checks"]
    if not isinstance(checks, list) or not checks:
        raise FallbackEvidenceError("receipt check evidence is missing")
    check_fields = {
        "id", "argv", "entrypoint_sha256", "command_sha256", "exit_code",
        "state", "failure_class", "stdout_bytes", "stdout_sha256",
        "stderr_bytes", "stderr_sha256",
    }
    expected_specs = _check_specs(started_at.astimezone(LOCAL_TZ))
    if len(checks) != len(expected_specs):
        raise FallbackEvidenceError("receipt check allowlist coverage differs")
    for item, spec in zip(checks, expected_specs):
        if not isinstance(item, dict) or set(item) != check_fields:
            raise FallbackEvidenceError("receipt check contract is malformed")
        if item["state"] not in CHECK_STATES:
            raise FallbackEvidenceError("receipt check state is unsupported")
        for key in ("entrypoint_sha256", "command_sha256", "stdout_sha256", "stderr_sha256"):
            if not isinstance(item[key], str) or not SHA256_RE.fullmatch(item[key]):
                raise FallbackEvidenceError("receipt check hash is malformed")
        argv = item["argv"]
        if (not isinstance(argv, list) or len(argv) < 2 or argv[0] != "python" or
                not all(isinstance(arg, str) for arg in argv)):
            raise FallbackEvidenceError("receipt command binding is malformed")
        entrypoint = (REPO_ROOT / argv[1]).resolve()
        if _relative_entrypoint(entrypoint) != argv[1]:
            raise FallbackEvidenceError("receipt command escapes repository")
        expected_argv = ["python", spec["entrypoint"], *spec["args"]]
        if item["id"] != spec["id"] or argv != expected_argv:
            raise FallbackEvidenceError("receipt command differs from local allowlist")
        if verify_current_code and _sha_file(entrypoint) != item["entrypoint_sha256"]:
            raise FallbackEvidenceError("receipt entrypoint hash is stale")
        command_binding = {
            "argv": expected_argv,
            "entrypoint_sha256": item["entrypoint_sha256"],
            "exit_contract": {
                str(code): state
                for code, state in sorted(spec["exit_contract"].items())
            },
        }
        if item["command_sha256"] != _sha_bytes(_canonical(command_binding)):
            raise FallbackEvidenceError("receipt command contract hash mismatch")
        expected_state = (
            spec["exit_contract"].get(item["exit_code"], "RUNNER_FAILED")
            if item["exit_code"] is not None else "RUNNER_FAILED"
        )
        if item["state"] != expected_state:
            raise FallbackEvidenceError("receipt check state contradicts exit contract")
    producer = document["producer"]
    if (not isinstance(producer, dict) or
            producer.get("path") != "tools/local_control_fallback.py" or
            not isinstance(producer.get("sha256"), str) or
            not SHA256_RE.fullmatch(producer["sha256"])):
        raise FallbackEvidenceError("receipt producer binding is malformed")
    if verify_current_code and _sha_file(Path(__file__).resolve()) != producer["sha256"]:
        raise FallbackEvidenceError("receipt producer hash is stale")
    expected_terminal_state, expected_blockers = _terminal_state(
        document["scheduler_snapshot"], checks
    )
    if (terminal["state"] != expected_terminal_state or
            terminal["blockers"] != expected_blockers):
        raise FallbackEvidenceError("receipt terminal state is not fail-closed")
    expected_result = _sha_bytes(_canonical({
        "scheduler_snapshot": document["scheduler_snapshot"],
        "checks": checks,
        "terminal_state": terminal["state"],
        "blockers": terminal["blockers"],
    }))
    if terminal["result_sha256"] != expected_result:
        raise FallbackEvidenceError("receipt result hash mismatch")
    return document


def _exit_for_terminal(state: str) -> int:
    if state == "LOCAL_CHECKS_COMPLETED":
        return 0
    if state == "LOCAL_CHECKS_COMPLETED_BLOCKED":
        return 2
    return 3


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--now")
    run_parser.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("receipt", type=Path)
    validate_parser.add_argument("--allow-stale-code", action="store_true")
    validate_parser.add_argument("--allow-stale-scheduler", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            document = validate_receipt(
                args.receipt,
                verify_current_code=not args.allow_stale_code,
                verify_current_scheduler=not args.allow_stale_scheduler,
            )
            print(
                "local-control-fallback receipt: VALID %s %s"
                % (document["terminal"]["state"], document["run_id"])
            )
            return _exit_for_terminal(document["terminal"]["state"])
        now = _aware_now(args.now)
        document, path = run_fallback(
            now=now, receipt_root=args.receipt_root
        )
        print(
            "local-control-fallback: %s checks=%d scheduler_gaps=%d"
            % (
                document["terminal"]["state"],
                len(document["checks"]),
                document["scheduler_snapshot"]["blocking_task_count"],
            )
        )
        print("receipt -> " + str(path))
        print("scheduler completion claimed -> false")
        return _exit_for_terminal(document["terminal"]["state"])
    except FallbackEvidenceError as exc:
        print("local-control-fallback: RUNNER_FAILED " + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
