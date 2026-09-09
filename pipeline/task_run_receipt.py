"""Atomic private receipts for the Windows batch runners.

The receipt records execution evidence only.  It never grants publication
authority and it deliberately refuses to classify an unknown non-zero process
exit as a successful semantic block.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import datetime as dt
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time


SCHEMA_VERSION = 3
TASK_CONTRACT_SCHEMA_VERSION = 2
STEP_CLASSIFIER_VERSION = 2
RECEIPT_INSPECTION_SCHEMA_VERSION = 1
LEGACY_RECEIPT_SCHEMA_VERSION = 2
CLI_EVIDENCE_ERROR = 90
CLI_LEGACY_UNVERIFIED = 1
CLI_COMPLETED_BLOCKED = 2
CLI_RUNNER_FAILED = 3
RECEIPT_FUTURE_SKEW = dt.timedelta(minutes=5)
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PYTHON = str(
    Path(
        r"C:\Users\nL_ku\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    ).resolve(strict=False)
)
RUNTIME_LAUNCHER = str(
    (REPO_ROOT / "pipeline" / "python_runtime.cmd").resolve(strict=False)
)
DEFAULT_ROOT = (
    REPO_ROOT
    / ".local-private"
    / "runtime"
    / "task-runs"
)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_STATUSES = {"FINISHED", "ABORTED"}
BLOCKING_STATES = {
    "BLOCKED",
    "COMPLETED_BLOCKED",
    "DEGRADED_UNCLASSIFIED",
    "REVIEW_REQUIRED",
}
VERIFIED_BLOCKING_STATES = {
    "BLOCKED",
    "COMPLETED_BLOCKED",
    "REVIEW_REQUIRED",
}
_ACTIVE_TRANSITIONS: set[str] = set()
_ACTIVE_TRANSITIONS_GUARD = threading.Lock()
# A scheduled runner starts a fresh Python process for every receipt transition.
# Windows filesystem filters can briefly retain the byte-range lock after the
# preceding process has exited.  A one-shot non-blocking acquisition turns that
# harmless hand-off into a false RUNNER_FAILED before the first guard runs.
# Keep the wait short and bounded: real overlap still fails closed, while a
# transient inter-process hand-off gets a deterministic chance to settle.
TRANSITION_LEASE_WAIT_SECONDS = 2.0
TRANSITION_LEASE_RETRY_SECONDS = 0.05


STEP_CLASSIFIER_REGISTRY = {
    1: {
        "negative_exit": {
            "semantic_state": "RUNNER_FAILED",
            "execution_valid": False,
            "classification_basis": "process_terminated_by_signal",
        },
        "contract_exit_maps": {
            "internal-v1": {"0": "PASS"},
            "zero-only-v1": {"0": "PASS"},
            "calendar-v1": {
                "0": "PASS", "1": "COMPLETED_BLOCKED", "2": "BLOCKED",
            },
            "posting-kit-v1": {"0": "PASS_OR_SKIP", "1": "REVIEW_REQUIRED"},
            "scan-on-1-v1": {"0": "PASS_OR_SKIP", "1": "BLOCKED"},
            "improvement-loop-v1": {"0": "PASS", "2": "BLOCKED"},
            "validation-on-1-v1": {"0": "PASS", "1": "BLOCKED"},
            "privacy-guard-v1": {"0": "PASS", "1": "BLOCKED"},
            "review-or-block-v1": {
                "0": "PASS", "1": "REVIEW_REQUIRED", "2": "BLOCKED",
            },
            "official-news-v1": {
                "0": "PASS", "1": "REVIEW_REQUIRED", "2": "BLOCKED",
            },
            "block-on-2-v1": {"0": "PASS", "2": "BLOCKED"},
            "queue-agent-v1": {"0": "PASS", "2": "BLOCKED"},
        },
        "known_contract_default": {
            "semantic_state": "RUNNER_FAILED",
            "execution_valid": False,
        },
        "fallback_zero": {
            "semantic_state": "PASS",
            "execution_valid": True,
            "classification_basis": "process_exit_zero",
        },
        "fallback_nonzero": {
            "classification_basis": "no_proven_exit_contract",
            "execution_valid": None,
            "graded_one_state": "DEGRADED_UNCLASSIFIED",
            "other_state": "NONZERO_UNCLASSIFIED",
        },
    },
}

# Classifier definitions are immutable evidence contracts.  Adding a new exit
# mapping to version 1 changed its hash and made already-sealed schema-3
# receipts unverifiable.  Preserve the exact pre-novelty definition as v1 and
# extend a copy for new receipts instead.
STEP_CLASSIFIER_REGISTRY[2] = copy.deepcopy(STEP_CLASSIFIER_REGISTRY[1])
STEP_CLASSIFIER_REGISTRY[2]["contract_exit_maps"]["novelty-queue-v1"] = {
    "0": "PASS", "10": "SKIP", "20": "BLOCKED",
}


TASK_STEP_CONTRACT_REGISTRY = {
    ("ngernduangold_daily", "daily-runner-v3"): {
        "version": "daily-runner-v3",
        "classifier_version": 1,
        "runner_name": "run_daily.cmd",
        "runner_sha256": (
            "621f43a0f24052374fbeb17a03d1aefd3fcbbd92deddeba963beb651915ea30f"
        ),
        "expected_steps": (
            ("runner.chdir", "internal", "internal-v1"),
            ("runner.log_directory", "internal", "internal-v1"),
            ("runner.log_prepare", "internal", "internal-v1"),
            ("comply_gate_stitch", "required", "scan-on-1-v1"),
            ("uptime_check", "graded", "review-or-block-v1"),
            ("agent_gap_check", "graded", "review-or-block-v1"),
            ("automation_policy_guard", "required", "block-on-2-v1"),
            ("privacy_guard", "required", "privacy-guard-v1"),
            ("public_identity_guard", "required", "block-on-2-v1"),
            ("manifest_contract", "required", "validation-on-1-v1"),
            ("content_calendar_guard", "graded", "calendar-v1"),
            ("dispatcher", "required", "generic"),
            ("daily_content", "required", "generic"),
            ("ga4_pull", "required", "block-on-2-v1"),
            ("fb_queue_linkcheck", "required", "validation-on-1-v1"),
            ("daily_media_gate", "required", "block-on-2-v1"),
            ("improvement_loop", "required", "improvement-loop-v1"),
            ("traffic_analyst", "required", "generic"),
            ("post_agent", "required", "queue-agent-v1"),
            ("credit_tracker_status", "required", "generic"),
            ("dashboard_agent", "required", "generic"),
            ("posting_kit", "graded", "posting-kit-v1"),
            ("hermes_digest", "required", "generic"),
            ("cc_monitor", "required", "generic"),
            ("preflight_self_test", "required", "zero-only-v1"),
            ("preflight", "graded", "review-or-block-v1"),
        ),
    },
    ("ngernduangold_weekly", "weekly-runner-v3"): {
        "version": "weekly-runner-v3",
        "classifier_version": 1,
        "runner_name": "run_weekly.cmd",
        "runner_sha256": (
            "8682665c7495cff8a24fdaa4c85c63ca8baf55687b55f0714ebda0f050575f20"
        ),
        "expected_steps": (
            ("runner.chdir", "internal", "internal-v1"),
            ("runner.log_directory", "internal", "internal-v1"),
            ("runner.log_prepare", "internal", "internal-v1"),
            ("comply_gate_stitch", "required", "scan-on-1-v1"),
            ("official_news_monitor", "graded", "official-news-v1"),
            ("content_calendar_guard", "graded", "calendar-v1"),
            ("ga4_pull", "required", "block-on-2-v1"),
            ("gsc_pull", "required", "block-on-2-v1"),
            ("weekly_growth_review", "required", "zero-only-v1"),
            ("improvement_loop", "required", "improvement-loop-v1"),
        ),
    },
}

# Preserve the v3 contracts so their historical receipts remain verifiable.
# The v4 runners use the hash-bound, import-preflighted launcher while keeping
# the same ordered local-only control steps.
for task_name, old_version, new_version, runner_sha256 in (
    (
        "ngernduangold_daily",
        "daily-runner-v3",
        "daily-runner-v4",
        "b9cc0a4592d64c082c244143029a514fd9f249bdb0cca4058f1a0dd81a93566f",
    ),
    (
        "ngernduangold_weekly",
        "weekly-runner-v3",
        "weekly-runner-v4",
        "6ce1930f95c62cacff26ca71a6c7cf54c7f6330116b87f189a42cf3f1115bb44",
    ),
):
    next_spec = copy.deepcopy(
        TASK_STEP_CONTRACT_REGISTRY[(task_name, old_version)]
    )
    next_spec["version"] = new_version
    next_spec["runner_sha256"] = runner_sha256
    TASK_STEP_CONTRACT_REGISTRY[(task_name, new_version)] = next_spec


def _repo_path(*parts: str) -> str:
    return str(REPO_ROOT.joinpath(*parts).resolve(strict=False))


TASK_STEP_COMMAND_REGISTRY = {
    ("ngernduangold_daily", "daily-runner-v3"): {
        "comply_gate_stitch": (
            PRODUCTION_PYTHON, _repo_path("tools", "comply_gate_stitch.py"),
            _repo_path("components", "stitch"),
        ),
        "uptime_check": (PRODUCTION_PYTHON, _repo_path("tools", "uptime_check.py")),
        "agent_gap_check": (
            PRODUCTION_PYTHON, _repo_path("tools", "agent_gap_check.py"),
            "--update-agent-silent-alert-file",
        ),
        "automation_policy_guard": (
            PRODUCTION_PYTHON, _repo_path("tools", "automation_policy_guard.py"),
        ),
        "privacy_guard": (PRODUCTION_PYTHON, _repo_path("tools", "privacy_guard.py")),
        "public_identity_guard": (
            PRODUCTION_PYTHON, _repo_path("tools", "public_identity_guard.py"),
        ),
        "manifest_contract": (
            PRODUCTION_PYTHON, _repo_path("tools", "manifest_contract.py"),
        ),
        "content_calendar_guard": (
            PRODUCTION_PYTHON, _repo_path("tools", "content_calendar_guard.py"),
            "--json",
        ),
        "dispatcher": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "dispatcher.py"), "--local-only",
        ),
        "daily_content": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "daily_content.py"), "--local-only",
        ),
        "ga4_pull": (PRODUCTION_PYTHON, _repo_path("pipeline", "ga4_pull.py")),
        "fb_queue_linkcheck": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "fb_queue_linkcheck.py"),
        ),
        "daily_media_gate": (
            PRODUCTION_PYTHON, _repo_path("tools", "daily_media_gate.py"),
            "--fps", "3", "--json",
        ),
        "improvement_loop": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "improvement_loop.py"),
            "run", "--cadence", "daily", "--mode", "local-safe", "--json",
        ),
        "traffic_analyst": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "traffic_analyst.py"),
        ),
        "post_agent": (PRODUCTION_PYTHON, _repo_path("pipeline", "post_agent.py")),
        "credit_tracker_status": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "credit_tracker.py"), "status",
        ),
        "dashboard_agent": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "dashboard_agent.py"),
        ),
        "posting_kit": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "posting_kit.py"),
            "--allow-missing-legacy-plan",
        ),
        "hermes_digest": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "hermes_digest.py"), "--local-only",
        ),
        "cc_monitor": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "cc_monitor.py"), "--local-only",
        ),
        "preflight_self_test": (
            PRODUCTION_PYTHON, _repo_path("tools", "test_preflight_checks.py"),
        ),
        "preflight": (PRODUCTION_PYTHON, _repo_path("tools", "preflight.py")),
    },
    ("ngernduangold_weekly", "weekly-runner-v3"): {
        "comply_gate_stitch": (
            PRODUCTION_PYTHON, _repo_path("tools", "comply_gate_stitch.py"),
            _repo_path("components", "stitch"),
        ),
        "official_news_monitor": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "official_news_monitor.py"),
            "--strict",
        ),
        "content_calendar_guard": (
            PRODUCTION_PYTHON, _repo_path("tools", "content_calendar_guard.py"),
            "--json",
        ),
        "ga4_pull": (PRODUCTION_PYTHON, _repo_path("pipeline", "ga4_pull.py")),
        "gsc_pull": (PRODUCTION_PYTHON, _repo_path("pipeline", "gsc_pull.py")),
        "weekly_growth_review": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "weekly_growth_review.py"),
            "--local-only",
        ),
        "improvement_loop": (
            PRODUCTION_PYTHON, _repo_path("pipeline", "improvement_loop.py"),
            "run", "--cadence", "weekly", "--mode", "local-safe", "--json",
        ),
    },
}


def _runtime_launcher_commands(commands: dict[str, tuple[str, ...]]) -> dict:
    """Replace only the interpreter token; preserve every script and argument."""
    converted = {}
    for step_id, command in commands.items():
        if not command or command[0] != PRODUCTION_PYTHON:
            raise RuntimeError("scheduled Python command registry is malformed")
        converted[step_id] = (RUNTIME_LAUNCHER, *command[1:])
    return converted


TASK_STEP_COMMAND_REGISTRY[(
    "ngernduangold_daily", "daily-runner-v4"
)] = _runtime_launcher_commands(
    TASK_STEP_COMMAND_REGISTRY[("ngernduangold_daily", "daily-runner-v3")]
)
TASK_STEP_COMMAND_REGISTRY[(
    "ngernduangold_weekly", "weekly-runner-v4"
)] = _runtime_launcher_commands(
    TASK_STEP_COMMAND_REGISTRY[("ngernduangold_weekly", "weekly-runner-v3")]
)

# Preserve v4 history. Daily v5 declares rc=2 novelty exhaustion/unknown as a
# queue BLOCK instead of allowing a generic zero/nonzero ambiguity.
_daily_v5_spec = copy.deepcopy(
    TASK_STEP_CONTRACT_REGISTRY[("ngernduangold_daily", "daily-runner-v4")]
)
_daily_v5_spec["version"] = "daily-runner-v5"
_daily_v5_spec["runner_sha256"] = (
    "1180f8684cbd630ffb6656046a7b3bcf32ba00b4759ad15f1cfba970e981fef0"
)
_daily_v5_spec["expected_steps"] = tuple(
    (
        step_id,
        wrapper,
        "queue-agent-v1" if step_id in {"dispatcher", "daily_content"} else contract,
    )
    for step_id, wrapper, contract in _daily_v5_spec["expected_steps"]
)
TASK_STEP_CONTRACT_REGISTRY[(
    "ngernduangold_daily", "daily-runner-v5"
)] = _daily_v5_spec
TASK_STEP_COMMAND_REGISTRY[(
    "ngernduangold_daily", "daily-runner-v5"
)] = copy.deepcopy(
    TASK_STEP_COMMAND_REGISTRY[("ngernduangold_daily", "daily-runner-v4")]
)

# Preserve v5 history. Daily v6 distinguishes proven novelty exhaustion from
# unreadable or otherwise untrusted novelty state without overloading rc=2.
_daily_v6_spec = copy.deepcopy(
    TASK_STEP_CONTRACT_REGISTRY[("ngernduangold_daily", "daily-runner-v5")]
)
_daily_v6_spec["version"] = "daily-runner-v6"
_daily_v6_spec["classifier_version"] = 2
_daily_v6_spec["runner_sha256"] = (
    "0cf03e0033850a644d9a424db0d7b05ddb21c4b0d64e05e080f3d7d27a943157"
)
_daily_v6_spec["expected_steps"] = tuple(
    (
        step_id,
        wrapper,
        "novelty-queue-v1"
        if step_id in {"dispatcher", "daily_content"}
        else contract,
    )
    for step_id, wrapper, contract in _daily_v6_spec["expected_steps"]
)
TASK_STEP_CONTRACT_REGISTRY[(
    "ngernduangold_daily", "daily-runner-v6"
)] = _daily_v6_spec
TASK_STEP_COMMAND_REGISTRY[(
    "ngernduangold_daily", "daily-runner-v6"
)] = copy.deepcopy(
    TASK_STEP_COMMAND_REGISTRY[("ngernduangold_daily", "daily-runner-v5")]
)

ACTIVE_TASK_CONTRACT_VERSION = {
    "ngernduangold_daily": "daily-runner-v6",
    "ngernduangold_weekly": "weekly-runner-v4",
}

# Compatibility/readability view for wiring tests and callers that only need
# the active contract.  Producer and validator logic use the versioned registry
# above so changing an active pointer cannot invalidate historical receipts.
TASK_STEP_CONTRACTS = {
    task_name: TASK_STEP_CONTRACT_REGISTRY[(task_name, version)]
    for task_name, version in ACTIVE_TASK_CONTRACT_VERSION.items()
}


class ReceiptError(RuntimeError):
    """Raised when a receipt transition cannot be trusted."""


class ReceiptArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ReceiptError(f"invalid CLI arguments: {message}")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_value(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _normalize_command(command: list[str] | tuple[str, ...]) -> list[str]:
    if (
        not isinstance(command, (list, tuple))
        or not command
        or any(not isinstance(item, str) or not item for item in command)
    ):
        raise ReceiptError("step command is invalid")
    normalized = []
    for index, item in enumerate(command):
        path_like = (
            index == 0
            or (index == 1 and item.lower().endswith((".py", ".cmd", ".exe")))
            or Path(item).is_absolute()
            or "\\" in item
            or "/" in item
        )
        normalized.append(
            str(Path(item).resolve(strict=False)) if path_like else item
        )
    return normalized


def _command_hash(command: list[str] | tuple[str, ...]) -> str:
    return _hash_value(_normalize_command(command))


def _task_contract_unsigned(contract: dict) -> dict:
    unsigned = copy.deepcopy(contract)
    unsigned.pop("manifest_hash", None)
    return unsigned


def _classifier_hash(classifier_version: int) -> str:
    definition = STEP_CLASSIFIER_REGISTRY.get(classifier_version)
    if not isinstance(definition, dict):
        raise ReceiptError("step classifier version is unsupported")
    return _hash_value(definition)


def _task_contract_spec(task_name: str, version: str | None = None) -> dict | None:
    selected_version = version or ACTIVE_TASK_CONTRACT_VERSION.get(task_name)
    if selected_version is None:
        return None
    spec = TASK_STEP_CONTRACT_REGISTRY.get((task_name, selected_version))
    if not isinstance(spec, dict):
        raise ReceiptError("task contract version is not registered")
    return spec


def _expected_step_rows(spec: dict, command_specs: dict) -> list[dict]:
    rows = []
    for step_id, wrapper, step_contract in spec["expected_steps"]:
        if wrapper == "internal":
            normalized = None
        else:
            normalized = _normalize_command(command_specs[step_id])
        rows.append({
            "step_id": step_id,
            "wrapper": wrapper,
            "contract": step_contract,
            "evidence_mode": "record" if wrapper == "internal" else "exec",
            "command_hash": (
                _hash_value(normalized) if normalized is not None else None
            ),
            "executable": normalized[0] if normalized is not None else None,
            "argument_count": len(normalized) - 1 if normalized is not None else None,
        })
    return rows


def task_contract_registry_hash() -> str:
    registered = [
        {
            "task_name": task_name,
            "version": version,
            "spec": spec,
        }
        for (task_name, version), spec in sorted(
            TASK_STEP_CONTRACT_REGISTRY.items()
        )
    ]
    return _hash_value({
        "active_versions": ACTIVE_TASK_CONTRACT_VERSION,
        "registered_contracts": registered,
        "registered_commands": [
            {
                "task_name": task_name,
                "version": version,
                "commands": commands,
            }
            for (task_name, version), commands in sorted(
                TASK_STEP_COMMAND_REGISTRY.items()
            )
        ],
        "step_classifiers": STEP_CLASSIFIER_REGISTRY,
    })


def build_task_contract(
    task_name: str,
    runner_sha256: str,
    *,
    receipt_producer_sha256: str | None = None,
    version: str | None = None,
) -> dict:
    """Build the canonical task/version-bound ordered-step contract.

    Monitored production tasks are strict and are bound to an exact runner
    version.  Ad-hoc test/helper tasks remain explicitly unscoped and are never
    eligible for the monitored control-health KPI.
    """
    if not isinstance(task_name, str) or not SAFE_ID_RE.fullmatch(task_name):
        raise ReceiptError("task name is unsafe")
    if not isinstance(runner_sha256, str) or not SHA256_RE.fullmatch(runner_sha256):
        raise ReceiptError("runner hash is invalid")
    producer_hash = receipt_producer_sha256 or _file_hash(
        Path(__file__).resolve(strict=False)
    )
    if (
        not isinstance(producer_hash, str)
        or not SHA256_RE.fullmatch(producer_hash)
    ):
        raise ReceiptError("receipt producer hash is invalid")
    is_monitored = task_name in ACTIVE_TASK_CONTRACT_VERSION
    spec = _task_contract_spec(task_name, version) if is_monitored else None
    if spec is None:
        if version not in {None, "unmonitored-v1"}:
            raise ReceiptError("unmonitored task contract version is invalid")
        contract = {
            "schema_version": TASK_CONTRACT_SCHEMA_VERSION,
            "task_name": task_name,
            "version": "unmonitored-v1",
            "classifier_version": STEP_CLASSIFIER_VERSION,
            "classifier_hash": _classifier_hash(STEP_CLASSIFIER_VERSION),
            "enforcement": "UNSCOPED",
            "runner_sha256_start": runner_sha256,
            "receipt_producer_sha256": producer_hash,
            "expected_steps": [],
        }
    else:
        classifier_version = spec.get("classifier_version")
        if runner_sha256 != spec["runner_sha256"]:
            raise ReceiptError(
                "monitored runner hash is not registered for its task contract"
            )
        selected_version = spec["version"]
        command_specs = TASK_STEP_COMMAND_REGISTRY.get(
            (task_name, selected_version)
        )
        if not isinstance(command_specs, dict):
            raise ReceiptError("task command contract is not registered")
        expected_exec_ids = {
            step_id for step_id, wrapper, _ in spec["expected_steps"]
            if wrapper != "internal"
        }
        if set(command_specs) != expected_exec_ids:
            raise ReceiptError("task command contract coverage is incomplete")
        contract = {
            "schema_version": TASK_CONTRACT_SCHEMA_VERSION,
            "task_name": task_name,
            "version": selected_version,
            "classifier_version": classifier_version,
            "classifier_hash": _classifier_hash(classifier_version),
            "enforcement": "STRICT_ORDERED",
            "runner_sha256_start": runner_sha256,
            "receipt_producer_sha256": producer_hash,
            "expected_steps": _expected_step_rows(spec, command_specs),
        }
    contract["manifest_hash"] = _hash_value(contract)
    return contract


def _validate_task_contract_binding(receipt: dict) -> dict:
    contract = receipt.get("task_contract")
    if not isinstance(contract, dict):
        raise ReceiptError("receipt task contract is invalid")
    required = {
        "schema_version", "task_name", "version", "classifier_version",
        "classifier_hash",
        "enforcement", "runner_sha256_start", "receipt_producer_sha256",
        "expected_steps",
        "manifest_hash",
    }
    if set(contract) != required:
        raise ReceiptError("receipt task contract shape is invalid")
    if contract.get("schema_version") != TASK_CONTRACT_SCHEMA_VERSION:
        raise ReceiptError("receipt task contract schema is unsupported")
    task_name = receipt.get("task_name")
    if not isinstance(task_name, str) or not SAFE_ID_RE.fullmatch(task_name):
        raise ReceiptError("receipt task identity is invalid")
    if contract.get("task_name") != task_name:
        raise ReceiptError("receipt task contract identity is mismatched")
    classifier_version = contract.get("classifier_version")
    if (
        not isinstance(classifier_version, int)
        or isinstance(classifier_version, bool)
        or classifier_version not in STEP_CLASSIFIER_REGISTRY
    ):
        raise ReceiptError("receipt step classifier version is unsupported")
    if contract.get("classifier_hash") != _classifier_hash(classifier_version):
        raise ReceiptError("receipt step classifier hash is invalid")
    runner = receipt.get("runner")
    if not isinstance(runner, dict):
        raise ReceiptError("receipt runner binding is invalid")
    runner_hash = runner.get("sha256_start")
    if not isinstance(runner_hash, str) or not SHA256_RE.fullmatch(runner_hash):
        raise ReceiptError("receipt runner start hash is invalid")
    if contract.get("runner_sha256_start") != runner_hash:
        raise ReceiptError("receipt task contract runner binding is mismatched")
    receipt_tool = receipt.get("receipt_tool")
    producer_hash = (
        receipt_tool.get("sha256_start")
        if isinstance(receipt_tool, dict) else None
    )
    if (
        not isinstance(producer_hash, str)
        or not SHA256_RE.fullmatch(producer_hash)
        or contract.get("receipt_producer_sha256") != producer_hash
    ):
        raise ReceiptError("receipt task contract producer binding is mismatched")
    manifest_hash = contract.get("manifest_hash")
    if (
        not isinstance(manifest_hash, str)
        or not SHA256_RE.fullmatch(manifest_hash)
        or manifest_hash != _hash_value(_task_contract_unsigned(contract))
    ):
        raise ReceiptError("receipt task contract hash is invalid")
    version = contract.get("version")
    if not isinstance(version, str) or not version:
        raise ReceiptError("receipt task contract version is invalid")
    if task_name in ACTIVE_TASK_CONTRACT_VERSION:
        if (task_name, version) not in TASK_STEP_CONTRACT_REGISTRY:
            raise ReceiptError("receipt task contract version is not registered")
    elif version != "unmonitored-v1":
        raise ReceiptError("receipt unmonitored task contract version is invalid")
    expected_contract = build_task_contract(
        task_name,
        runner_hash,
        receipt_producer_sha256=producer_hash,
        version=version,
    )
    if contract != expected_contract:
        raise ReceiptError("receipt task contract is not canonical")
    return contract


def _validate_step_manifest_progress(receipt: dict) -> None:
    contract = _validate_task_contract_binding(receipt)
    if contract["enforcement"] != "STRICT_ORDERED":
        return
    expected = contract["expected_steps"]
    observed = receipt.get("steps")
    if not isinstance(observed, list):
        raise ReceiptError("receipt steps are invalid")
    if len(observed) > len(expected):
        raise ReceiptError("receipt contains steps beyond its task contract")
    for index, step in enumerate(observed):
        if not isinstance(step, dict):
            raise ReceiptError("receipt step is invalid")
        actual = {
            "step_id": step.get("step_id"),
            "wrapper": step.get("wrapper"),
            "contract": step.get("contract"),
            "evidence_mode": step.get("evidence_mode"),
            "command_hash": step.get("command_hash"),
            "executable": step.get("executable"),
            "argument_count": step.get("argument_count"),
        }
        if actual != expected[index]:
            raise ReceiptError("receipt steps are not an exact ordered manifest prefix")
    if receipt.get("status") == "FINISHED" and len(observed) != len(expected):
        raise ReceiptError("finished receipt did not complete its task manifest")


def _validate_next_expected_step(
    receipt: dict, *, step_id: str, wrapper: str, contract: str,
    evidence_mode: str, command_hash: str | None,
    executable: str | None, argument_count: int | None
) -> None:
    task_contract = _validate_task_contract_binding(receipt)
    if task_contract["enforcement"] != "STRICT_ORDERED":
        return
    expected = task_contract["expected_steps"]
    index = len(receipt.get("steps", []))
    if index >= len(expected):
        raise ReceiptError("task contract has no remaining step")
    actual = {
        "step_id": step_id,
        "wrapper": wrapper,
        "contract": contract,
        "evidence_mode": evidence_mode,
        "command_hash": command_hash,
        "executable": executable,
        "argument_count": argument_count,
    }
    if actual != expected[index]:
        raise ReceiptError("step does not match the next task-contract entry")


def _validate_step_request(
    *, step_id: str, wrapper: str, contract: str, evidence_mode: str,
    command: list[str] | None = None
) -> str:
    step = _safe_id(step_id, "step id")
    if wrapper not in {"required", "graded", "internal"}:
        raise ReceiptError("step wrapper is invalid")
    if (
        not isinstance(contract, str)
        or not contract
        or len(contract) > 128
        or not SAFE_ID_RE.fullmatch(contract)
    ):
        raise ReceiptError("step contract is invalid")
    if evidence_mode not in {"record", "exec"}:
        raise ReceiptError("step evidence mode is invalid")
    if evidence_mode == "record":
        if command is not None:
            raise ReceiptError("record step cannot contain command evidence")
    else:
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(item, str) or not item for item in command)
        ):
            raise ReceiptError("step command is invalid")
    return step


def _file_hash(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def seal_receipt(receipt: dict) -> dict:
    sealed = copy.deepcopy(receipt)
    sealed.pop("receipt_hash", None)
    sealed["receipt_hash"] = _hash_value(sealed)
    return sealed


def verify_receipt(receipt: object) -> bool:
    if not isinstance(receipt, dict):
        return False
    actual = receipt.get("receipt_hash")
    if not isinstance(actual, str) or not actual:
        return False
    unsigned = copy.deepcopy(receipt)
    unsigned.pop("receipt_hash", None)
    return actual == _hash_value(unsigned)


def _legacy_receipt_summary(receipt: dict) -> dict:
    """Validate only the safe envelope of a historical schema-2 receipt.

    Schema 2 predates ``task_contract`` and per-step command binding.  Its
    self-hash can prove that the local file has not changed since it was sealed,
    but it cannot prove the ordered runner contract now required by schema 3.
    Keep that distinction explicit: callers may inventory the historical run,
    but must never upgrade its claimed execution state to trusted completion.
    """
    required = {
        "schema_version", "run_id", "task_name", "origin", "status",
        "terminal_kind", "terminal_reason", "terminal_step_id", "started_at",
        "finished_at", "execution_state", "publication_state", "final_rc",
        "runner", "receipt_tool", "log_path", "steps", "transition_counter",
        "receipt_hash",
    }
    if set(receipt) != required:
        raise ReceiptError("legacy receipt shape is invalid")
    if receipt.get("schema_version") != LEGACY_RECEIPT_SCHEMA_VERSION:
        raise ReceiptError("legacy receipt schema is unsupported")
    task_name = receipt.get("task_name")
    run_id = receipt.get("run_id")
    if not isinstance(task_name, str) or not SAFE_ID_RE.fullmatch(task_name):
        raise ReceiptError("legacy receipt task identity is invalid")
    if not isinstance(run_id, str) or not SAFE_ID_RE.fullmatch(run_id):
        raise ReceiptError("legacy receipt run identity is invalid")
    if receipt.get("origin") != "RUNNER_INVOCATION_UNVERIFIED":
        raise ReceiptError("legacy receipt origin is invalid")
    status = receipt.get("status")
    if status not in {"RUNNING", *TERMINAL_STATUSES}:
        raise ReceiptError("legacy receipt status is invalid")
    publication_state = receipt.get("publication_state")
    if publication_state not in {
        "BLOCKED_LOCAL_ONLY", "BLOCKED", "NOT_ATTEMPTED",
    }:
        raise ReceiptError("legacy receipt publication state is invalid")
    started_at = _parse_receipt_time(receipt.get("started_at"), "start time")
    now = dt.datetime.now(dt.timezone.utc)
    if started_at > now + RECEIPT_FUTURE_SKEW:
        raise ReceiptError("legacy receipt start time is in the future")
    if not isinstance(receipt.get("log_path"), str) or not receipt["log_path"]:
        raise ReceiptError("legacy receipt log path is invalid")
    for label in ("runner", "receipt_tool"):
        binding = receipt.get(label)
        if not isinstance(binding, dict) or set(binding) != {
            "path", "sha256_start", "sha256_end", "stable_during_run",
        }:
            raise ReceiptError("legacy receipt %s binding is invalid" % label)
        if not isinstance(binding.get("path"), str) or not binding["path"]:
            raise ReceiptError("legacy receipt %s path is invalid" % label)
        start_hash = binding.get("sha256_start")
        end_hash = binding.get("sha256_end")
        if not isinstance(start_hash, str) or not SHA256_RE.fullmatch(start_hash):
            raise ReceiptError("legacy receipt %s start hash is invalid" % label)
        if end_hash is not None and (
            not isinstance(end_hash, str) or not SHA256_RE.fullmatch(end_hash)
        ):
            raise ReceiptError("legacy receipt %s end hash is invalid" % label)
        stability = binding.get("stable_during_run")
        if stability is not None and not isinstance(stability, bool):
            raise ReceiptError("legacy receipt %s stability is invalid" % label)
        if stability is True and end_hash != start_hash:
            raise ReceiptError("legacy receipt %s hash stability is invalid" % label)
    steps = receipt.get("steps")
    if not isinstance(steps, list):
        raise ReceiptError("legacy receipt steps are invalid")
    previous_finished = started_at
    for sequence, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ReceiptError("legacy receipt step is invalid")
        allowed_step_keys = {
            "sequence", "step_id", "wrapper", "contract", "started_at",
            "finished_at", "duration_ms", "raw_rc", "semantic_state",
            "execution_valid", "classification_basis", "launch_error",
            "executable", "argument_count", "command_hash",
        }
        optional_step_keys = {
            "launch_error", "executable", "argument_count", "command_hash",
        }
        required_step_keys = allowed_step_keys - optional_step_keys
        if not required_step_keys.issubset(step) or set(step) - allowed_step_keys:
            raise ReceiptError("legacy receipt step shape is invalid")
        if (
            not isinstance(step.get("sequence"), int)
            or isinstance(step.get("sequence"), bool)
            or step["sequence"] != sequence
        ):
            raise ReceiptError("legacy receipt step sequence is invalid")
        if not isinstance(step.get("step_id"), str) or not SAFE_ID_RE.fullmatch(
            step["step_id"]
        ):
            raise ReceiptError("legacy receipt step identity is invalid")
        if step.get("wrapper") not in {"required", "graded", "internal"}:
            raise ReceiptError("legacy receipt step wrapper is invalid")
        for field in ("contract", "semantic_state", "classification_basis"):
            if not isinstance(step.get(field), str) or not step[field]:
                raise ReceiptError("legacy receipt step %s is invalid" % field)
        if not isinstance(step.get("raw_rc"), int) or isinstance(
            step.get("raw_rc"), bool
        ):
            raise ReceiptError("legacy receipt step exit is invalid")
        validity = step.get("execution_valid")
        if validity is not None and not isinstance(validity, bool):
            raise ReceiptError("legacy receipt step validity is invalid")
        duration = step.get("duration_ms")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise ReceiptError("legacy receipt step duration is invalid")
        step_started = _parse_receipt_time(
            step.get("started_at"), "step start time"
        )
        step_finished = _parse_receipt_time(
            step.get("finished_at"), "step finish time"
        )
        if step_started < previous_finished or step_finished < step_started:
            raise ReceiptError("legacy receipt step chronology is invalid")
        if step_finished > now + RECEIPT_FUTURE_SKEW:
            raise ReceiptError("legacy receipt step time is in the future")
        previous_finished = step_finished
        if "launch_error" in step and (
            not isinstance(step["launch_error"], str) or not step["launch_error"]
        ):
            raise ReceiptError("legacy receipt step launch error is invalid")
        command_keys = {"executable", "argument_count", "command_hash"}
        present_command_keys = command_keys.intersection(step)
        if present_command_keys and present_command_keys != command_keys:
            raise ReceiptError("legacy receipt command evidence is incomplete")
        if present_command_keys:
            if (
                not isinstance(step["executable"], str)
                or not step["executable"]
                or not isinstance(step["argument_count"], int)
                or isinstance(step["argument_count"], bool)
                or step["argument_count"] < 0
                or not isinstance(step["command_hash"], str)
                or not SHA256_RE.fullmatch(step["command_hash"])
            ):
                raise ReceiptError("legacy receipt command evidence is invalid")
    counter = receipt.get("transition_counter")
    if not isinstance(counter, int) or isinstance(counter, bool) or counter < 0:
        raise ReceiptError("legacy receipt transition counter is invalid")
    expected_counter = len(steps) + (1 if status in TERMINAL_STATUSES else 0)
    if counter != expected_counter:
        raise ReceiptError("legacy receipt transition counter is inconsistent")
    state = receipt.get("execution_state")
    known_states = {
        "RUNNING", "PASS", "COMPLETED_WITH_BLOCKERS", "COMPLETED_BLOCKED",
        "UNVERIFIED_NONZERO", "RUNNER_FAILED",
    }
    if state not in known_states:
        raise ReceiptError("legacy receipt execution state is invalid")
    if status == "RUNNING":
        if state != "RUNNING" or any(receipt.get(field) is not None for field in (
            "terminal_kind", "terminal_reason", "terminal_step_id",
            "finished_at", "final_rc",
        )):
            raise ReceiptError("legacy running receipt is inconsistent")
        claimed_finished_at = None
        claimed_final_rc = None
    else:
        if state == "RUNNING":
            raise ReceiptError("legacy terminal receipt is inconsistent")
        claimed_final_rc = receipt.get("final_rc")
        if not isinstance(claimed_final_rc, int) or isinstance(
            claimed_final_rc, bool
        ):
            raise ReceiptError("legacy receipt final exit is invalid")
        claimed_finished_at = _parse_receipt_time(
            receipt.get("finished_at"), "finish time"
        )
        if claimed_finished_at < previous_finished:
            raise ReceiptError("legacy receipt terminal chronology is invalid")
        if claimed_finished_at > now + RECEIPT_FUTURE_SKEW:
            raise ReceiptError("legacy receipt finish time is in the future")
    return {
        "inspection_schema_version": RECEIPT_INSPECTION_SCHEMA_VERSION,
        "evidence_status": "LEGACY_SCHEMA2_HASH_VALID_UNVERIFIED",
        "receipt_schema_version": LEGACY_RECEIPT_SCHEMA_VERSION,
        "task_name": task_name,
        "status": status,
        "execution_state": None,
        "claimed_execution_state": state,
        "publication_state": publication_state,
        "started_at": receipt.get("started_at"),
        "finished_at": receipt.get("finished_at"),
        "final_rc": claimed_final_rc,
        "task_contract_version": None,
        "receipt_hash_prefix": receipt["receipt_hash"][:12],
        "trusted_for_execution": False,
        "trusted_for_completion": False,
        "trusted_for_scheduler_launch": False,
        "reason": "schema 2 has no task_contract or per-step command binding",
    }


def _strict_json_loads(text: str):
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON constant: " + value)

    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )

    def reject_nonfinite(item) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                reject_nonfinite(child)
        elif isinstance(item, list):
            for child in item:
                reject_nonfinite(child)

    reject_nonfinite(value)
    return value


def _parse_receipt_time(value, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ReceiptError("receipt %s is invalid" % label)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReceiptError("receipt %s is invalid" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReceiptError("receipt %s must include a timezone" % label)
    return parsed.astimezone(dt.timezone.utc)


def _validate_receipt_shape(receipt: dict) -> None:
    required = {
        "schema_version", "run_id", "task_name", "origin", "status",
        "terminal_kind", "terminal_reason", "terminal_step_id", "started_at",
        "finished_at", "execution_state", "publication_state", "final_rc",
        "runner", "receipt_tool", "task_contract", "log_path", "steps",
        "transition_counter", "receipt_hash",
    }
    if required.difference(receipt):
        raise ReceiptError("receipt schema is missing required fields")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ReceiptError("receipt schema version is unsupported")
    status = receipt.get("status")
    if not isinstance(status, str) or status not in {"RUNNING", *TERMINAL_STATUSES}:
        raise ReceiptError("receipt status is invalid")
    if receipt.get("origin") != "RUNNER_INVOCATION_UNVERIFIED":
        raise ReceiptError("receipt origin is invalid")
    publication_state = receipt.get("publication_state")
    if not isinstance(publication_state, str) or publication_state not in {
        "BLOCKED_LOCAL_ONLY", "BLOCKED", "NOT_ATTEMPTED",
    }:
        raise ReceiptError("receipt publication state is invalid")
    now = dt.datetime.now(dt.timezone.utc)
    started_at = _parse_receipt_time(receipt.get("started_at"), "start time")
    if started_at > now + RECEIPT_FUTURE_SKEW:
        raise ReceiptError("receipt start time is in the future")
    if not isinstance(receipt.get("log_path"), str) or not receipt["log_path"]:
        raise ReceiptError("receipt log path is invalid")
    for label in ("runner", "receipt_tool"):
        binding = receipt.get(label)
        if not isinstance(binding, dict):
            raise ReceiptError("receipt %s binding is invalid" % label)
        if not isinstance(binding.get("path"), str) or not binding["path"]:
            raise ReceiptError("receipt %s path is invalid" % label)
        if not isinstance(binding.get("sha256_start"), str) or not SHA256_RE.fullmatch(
            binding["sha256_start"]
        ):
            raise ReceiptError("receipt %s start hash is invalid" % label)
        end_hash = binding.get("sha256_end")
        if end_hash is not None and (
            not isinstance(end_hash, str) or not SHA256_RE.fullmatch(end_hash)
        ):
            raise ReceiptError("receipt %s end hash is invalid" % label)
        stability = binding.get("stable_during_run")
        if stability is not None and not isinstance(stability, bool):
            raise ReceiptError("receipt %s stability is invalid" % label)
    task_contract = _validate_task_contract_binding(receipt)
    steps = receipt.get("steps")
    if not isinstance(steps, list):
        raise ReceiptError("receipt steps are invalid")
    previous_finished = started_at
    for sequence, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ReceiptError("receipt step is invalid")
        if (
            not isinstance(step.get("sequence"), int)
            or isinstance(step.get("sequence"), bool)
            or step["sequence"] != sequence
        ):
            raise ReceiptError("receipt step sequence is invalid")
        if not isinstance(step.get("step_id"), str) or not SAFE_ID_RE.fullmatch(
            step["step_id"]
        ):
            raise ReceiptError("receipt step identity is invalid")
        if not isinstance(step.get("raw_rc"), int) or isinstance(
            step.get("raw_rc"), bool
        ):
            raise ReceiptError("receipt step exit is invalid")
        execution_valid = step.get("execution_valid")
        if execution_valid is not None and not isinstance(execution_valid, bool):
            raise ReceiptError("receipt step execution validity is invalid")
        for field in ("wrapper", "contract", "semantic_state", "classification_basis"):
            if not isinstance(step.get(field), str) or not step[field]:
                raise ReceiptError("receipt step %s is invalid" % field)
        if step["wrapper"] not in {"required", "graded", "internal"}:
            raise ReceiptError("receipt step wrapper is invalid")
        evidence_mode = step.get("evidence_mode")
        if not isinstance(evidence_mode, str) or evidence_mode not in {"record", "exec"}:
            raise ReceiptError("receipt step evidence mode is invalid")
        command_fields = {"executable", "argument_count", "command_hash"}
        if evidence_mode == "record":
            if (
                task_contract["enforcement"] == "STRICT_ORDERED"
                and (
                    step["wrapper"] != "internal"
                    or step["contract"] != "internal-v1"
                )
            ):
                raise ReceiptError("receipt record step is not internal evidence")
            if command_fields.intersection(step):
                raise ReceiptError("receipt record step contains command evidence")
        else:
            if (
                not isinstance(step.get("executable"), str)
                or not step["executable"]
                or not isinstance(step.get("argument_count"), int)
                or isinstance(step.get("argument_count"), bool)
                or step["argument_count"] < 0
                or not isinstance(step.get("command_hash"), str)
                or not SHA256_RE.fullmatch(step["command_hash"])
            ):
                raise ReceiptError("receipt exec step command evidence is invalid")
        duration_ms = step.get("duration_ms")
        if (
            not isinstance(duration_ms, int)
            or isinstance(duration_ms, bool)
            or duration_ms < 0
        ):
            raise ReceiptError("receipt step duration is invalid")
        for field in ("started_at", "finished_at"):
            if not isinstance(step.get(field), str) or not step[field]:
                raise ReceiptError("receipt step %s is invalid" % field)
        step_started = _parse_receipt_time(
            step["started_at"], "step start time"
        )
        step_finished = _parse_receipt_time(
            step["finished_at"], "step finish time"
        )
        if step_started < previous_finished or step_finished < step_started:
            raise ReceiptError("receipt step chronology is invalid")
        if step_finished > now + RECEIPT_FUTURE_SKEW:
            raise ReceiptError("receipt step time is in the future")
        previous_finished = step_finished
        launch_error = step.get("launch_error")
        if "launch_error" in step and (
            not isinstance(launch_error, str) or not launch_error
        ):
            raise ReceiptError("receipt step launch error is invalid")
        expected = classify_step(
            step["wrapper"], step["contract"], step["raw_rc"],
            classifier_version=task_contract["classifier_version"],
        )
        if launch_error:
            expected = {
                "semantic_state": "RUNNER_FAILED",
                "execution_valid": False,
                "classification_basis": "child_launch_error",
            }
        if any(step.get(key) != value for key, value in expected.items()):
            raise ReceiptError("receipt step classification is inconsistent")
    _validate_step_manifest_progress(receipt)
    counter = receipt.get("transition_counter")
    if not isinstance(counter, int) or isinstance(counter, bool) or counter < 0:
        raise ReceiptError("receipt transition counter is invalid")
    expected_counter = len(steps) + (1 if status in TERMINAL_STATUSES else 0)
    if counter != expected_counter:
        raise ReceiptError("receipt transition counter is inconsistent")
    if status == "RUNNING":
        if any(receipt.get(field) is not None for field in (
            "terminal_kind", "terminal_reason", "terminal_step_id",
            "finished_at", "final_rc",
        )):
            raise ReceiptError("running receipt has terminal fields")
        if receipt.get("execution_state") != "RUNNING":
            raise ReceiptError("running receipt execution state is invalid")
        for label in ("runner", "receipt_tool"):
            binding = receipt[label]
            if (
                binding.get("sha256_end") is not None
                or binding.get("stable_during_run") is not None
            ):
                raise ReceiptError("running receipt has end-run evidence")
        return

    expected_kind = "end" if status == "FINISHED" else "abort"
    if receipt.get("terminal_kind") != expected_kind:
        raise ReceiptError("terminal receipt kind is invalid")
    reason = receipt.get("terminal_reason")
    if not isinstance(reason, str) or not SAFE_ID_RE.fullmatch(reason):
        raise ReceiptError("terminal receipt reason is invalid")
    terminal_step = receipt.get("terminal_step_id")
    if status == "FINISHED":
        if reason != "normal_end" or terminal_step is not None:
            raise ReceiptError("finished receipt terminal evidence is inconsistent")
    else:
        if reason == "normal_end":
            raise ReceiptError("aborted receipt uses normal-end reason")
        if reason == "step_nonzero":
            last_step = steps[-1] if steps else {}
            if (
                not isinstance(terminal_step, str)
                or terminal_step != last_step.get("step_id")
                or last_step.get("raw_rc") == 0
            ):
                raise ReceiptError("aborted receipt step evidence is inconsistent")
        elif terminal_step is not None:
            raise ReceiptError("non-step abort names a terminal step")
    finished_at = _parse_receipt_time(receipt.get("finished_at"), "finish time")
    if finished_at < previous_finished or finished_at > now + RECEIPT_FUTURE_SKEW:
        raise ReceiptError("terminal receipt chronology is invalid")
    final_rc = receipt.get("final_rc")
    if not isinstance(final_rc, int) or isinstance(final_rc, bool):
        raise ReceiptError("terminal receipt final exit is invalid")
    state = receipt.get("execution_state")
    if not isinstance(state, str) or state not in {
        "PASS", "COMPLETED_WITH_BLOCKERS", "COMPLETED_BLOCKED",
        "UNVERIFIED_NONZERO", "RUNNER_FAILED",
    }:
        raise ReceiptError("terminal receipt execution state is invalid")
    expected_state = _derive_execution_state(
        receipt,
        expected_kind,
        final_rc,
        terminal_reason=reason,
        terminal_step_id=terminal_step,
    )
    for label in ("runner", "receipt_tool"):
        binding = receipt[label]
        stability = binding.get("stable_during_run")
        if not isinstance(stability, bool):
            raise ReceiptError("terminal receipt %s stability is invalid" % label)
        end_hash = binding.get("sha256_end")
        if stability and end_hash != binding.get("sha256_start"):
            raise ReceiptError("terminal receipt %s hash stability is invalid" % label)
        if not stability:
            expected_state = "RUNNER_FAILED"
    if state != expected_state:
        raise ReceiptError("terminal receipt execution state is inconsistent")


def _atomic_write(path: Path, value: dict) -> None:
    """Durably replace one JSON file without exposing a partial document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def receipt_revocation_path(receipt_file: Path) -> Path:
    """Return the durable fail-closed latch paired with one receipt path."""
    selected = Path(receipt_file)
    return selected.with_name(f".{selected.name}.terminal-revoked")


def assert_receipt_not_revoked(receipt_file: Path) -> None:
    """Reject a receipt while its terminal commit latch exists.

    Marker contents are diagnostic only.  Existence is authoritative so a
    partial marker write or malformed marker also fails closed.
    """
    marker = receipt_revocation_path(receipt_file)
    try:
        marker.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ReceiptError("receipt revocation state is unreadable") from exc
    raise ReceiptError("receipt terminal commit is revoked")


def _install_terminal_revocation(path: Path, sealed: dict) -> Path:
    """Atomically create and durably fill the terminal commit latch."""
    marker = receipt_revocation_path(path)
    payload = {
        "schema_version": 1,
        "state": "TERMINAL_COMMIT_REVOKED",
        "task_name": sealed.get("task_name"),
        "run_id": sealed.get("run_id"),
        "candidate_receipt_hash": sealed.get("receipt_hash"),
        "created_at": _utc_now(),
    }
    payload["marker_hash"] = _hash_value(payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"
    marker.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(marker, flags, 0o600)
    except FileExistsError as exc:
        raise ReceiptError("receipt terminal commit is already revoked") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # Never remove a partially written marker: existence alone is the
        # consumer-visible fail-closed latch.
        raise
    return marker


def _clear_terminal_revocation(marker: Path) -> None:
    try:
        marker.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        # Some filesystem wrappers can report an error after the unlink has
        # committed.  Treat an actually absent latch as the successful commit
        # point so process status cannot disagree with the activated receipt.
        try:
            marker.lstat()
        except FileNotFoundError:
            return
        except OSError as stat_exc:
            raise ReceiptError("receipt revocation state is unreadable") from stat_exc
        raise ReceiptError("receipt revocation latch could not be cleared") from exc
    try:
        marker.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ReceiptError("receipt revocation state is unreadable") from exc
    raise ReceiptError("receipt revocation latch remains after clear")


def _read_valid_receipt_file(path: Path) -> dict | None:
    """Return one structurally valid sealed receipt, or ``None``.

    This deliberately does not raise.  It is used only while recovering from a
    failed terminal repair, where an unreadable or absent canonical artifact is
    already the fail-closed outcome.
    """
    try:
        if path.stat().st_size > MAX_RECEIPT_BYTES:
            return None
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
        if not verify_receipt(value):
            return None
        _validate_receipt_shape(value)
        return value
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        ReceiptError,
        RecursionError,
    ):
        return None


def _invalidate_untrusted_terminal(path: Path) -> None:
    """Make a stale positive terminal receipt unusable after repair failure.

    Atomic replacement is the normal evidence path.  If that mechanism has
    just failed, first poison the canonical JSON in place; if the file cannot
    be opened, move it out of the ``*.json`` receipt namespace, then finally
    try removal.  A valid terminal without the exact drift latch must never be
    left at the canonical path after this function reports success.
    """
    try:
        with path.open("r+b") as handle:
            handle.seek(0)
            handle.write(b"!")
            handle.flush()
            os.fsync(handle.fileno())
    except FileNotFoundError:
        return
    except OSError:
        pass

    current = _read_valid_receipt_file(path)
    if current is None or current.get("status") == "RUNNING":
        return

    quarantine = path.with_name(
        f".{path.name}.{secrets.token_hex(6)}.untrusted"
    )
    try:
        os.replace(path, quarantine)
        return
    except FileNotFoundError:
        return
    except OSError:
        pass

    try:
        path.unlink()
        return
    except FileNotFoundError:
        return
    except OSError as exc:
        current = _read_valid_receipt_file(path)
        if (
            current is None
            or current.get("status") == "RUNNING"
        ):
            return
        raise ReceiptError(
            "stale positive terminal receipt could not be invalidated"
        ) from exc


def _repair_drifted_terminal(path: Path, sealed: dict) -> dict:
    """Persist a drift-latched terminal or invalidate the prior positive one."""
    try:
        _atomic_write(path, sealed)
        return sealed
    except OSError as exc:
        # An I/O wrapper can report failure after os.replace completed.  Trust
        # that outcome only when the exact desired fail-closed receipt is now
        # present; otherwise revoke the earlier positive terminal artifact.
        current = _read_valid_receipt_file(path)
        if current == sealed:
            return current
        if current is not None and current.get("status") != "RUNNING":
            _invalidate_untrusted_terminal(path)
        raise ReceiptError(
            "terminal drift repair failed; prior positive receipt was invalidated"
        ) from exc


def _safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise ReceiptError(f"invalid {label}")
    return value


def receipt_path(root: Path, task_name: str, run_id: str) -> Path:
    task = _safe_id(task_name, "task name")
    run = _safe_id(run_id, "run id")
    selected_root = Path(root).resolve(strict=False)
    path = (selected_root / task / f"{run}.json").resolve(strict=False)
    try:
        path.relative_to(selected_root)
    except ValueError as exc:
        raise ReceiptError("receipt path escapes root") from exc
    return path


def receipt_transition_lock_path(receipt_file: Path) -> Path:
    selected = Path(receipt_file)
    return selected.with_name(f".{selected.name}.transition-lock")


def _acquire_transition_byte_lock(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_transition_byte_lock(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _receipt_transition_lease(receipt_file: Path):
    """Serialize load-to-commit transitions in-process and across processes."""
    selected = Path(receipt_file).resolve(strict=False)
    key = str(selected).casefold() if os.name == "nt" else str(selected)
    with _ACTIVE_TRANSITIONS_GUARD:
        if key in _ACTIVE_TRANSITIONS:
            raise ReceiptError("receipt transition is already active")
        _ACTIVE_TRANSITIONS.add(key)

    lock_path = receipt_transition_lock_path(selected)
    handle = None
    os_locked = False
    try:
        deadline = time.monotonic() + TRANSITION_LEASE_WAIT_SECONDS
        last_error: OSError | None = None
        while True:
            candidate = None
            try:
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                candidate = lock_path.open("a+b")
                candidate.seek(0, os.SEEK_END)
                if candidate.tell() == 0:
                    candidate.write(b"\0")
                    candidate.flush()
                    os.fsync(candidate.fileno())
                _acquire_transition_byte_lock(candidate)
                handle = candidate
                os_locked = True
                break
            except OSError as exc:
                last_error = exc
                if candidate is not None:
                    try:
                        candidate.close()
                    except OSError:
                        pass
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ReceiptError(
                        "receipt transition lease is unavailable"
                    ) from last_error
                time.sleep(min(TRANSITION_LEASE_RETRY_SECONDS, remaining))

        yield
    finally:
        if handle is not None:
            if os_locked:
                try:
                    _release_transition_byte_lock(handle)
                except OSError:
                    pass
            try:
                handle.close()
            except OSError:
                pass
        with _ACTIVE_TRANSITIONS_GUARD:
            _ACTIVE_TRANSITIONS.discard(key)


def _serialized_receipt_transition(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            path = receipt_path(
                kwargs["root"], kwargs["task_name"], kwargs["run_id"]
            )
        except KeyError as exc:
            raise ReceiptError("receipt transition identity is missing") from exc
        with _receipt_transition_lease(path):
            return function(*args, **kwargs)

    return wrapped


def _serialized_receipt_start(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            task = _safe_id(kwargs["task_name"], "task name")
            selected_run_id = _safe_id(
                kwargs.get("run_id") or _new_run_id(task), "run id"
            )
            path = receipt_path(kwargs["root"], task, selected_run_id)
        except KeyError as exc:
            raise ReceiptError("receipt transition identity is missing") from exc
        forwarded = dict(kwargs)
        forwarded["run_id"] = selected_run_id
        with _receipt_transition_lease(path):
            return function(*args, **forwarded)

    return wrapped


def _serialized_terminal_transition(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            path = receipt_path(
                kwargs["root"], kwargs["task_name"], kwargs["run_id"]
            )
        except KeyError as exc:
            raise ReceiptError("receipt transition identity is missing") from exc
        with _receipt_transition_lease(path):
            sealed, revocation = function(*args, **kwargs)
        # Activate the terminal artifact only after the serialization lease has
        # been released.  If lease-held work fails, the durable revocation latch
        # remains and every consumer rejects the candidate receipt.
        _clear_terminal_revocation(revocation)
        return sealed

    return wrapped


def _load_receipt(root: Path, task_name: str, run_id: str) -> tuple[Path, dict]:
    path = receipt_path(root, task_name, run_id)
    assert_receipt_not_revoked(path)
    try:
        if path.stat().st_size > MAX_RECEIPT_BYTES:
            raise ReceiptError("receipt exceeds the bounded evidence size")
        receipt = _strict_json_loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReceiptError("receipt does not exist") from exc
    except (
        OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError,
        RecursionError,
    ) as exc:
        raise ReceiptError("receipt is unreadable or malformed") from exc
    if not verify_receipt(receipt):
        raise ReceiptError("receipt hash mismatch")
    _validate_receipt_shape(receipt)
    if receipt.get("task_name") != task_name or receipt.get("run_id") != run_id:
        raise ReceiptError("receipt identity mismatch")
    assert_receipt_not_revoked(path)
    return path, receipt


def inspect_receipt_file(path: Path) -> dict:
    """Read one receipt without granting transition or scheduler authority.

    Current schema-3 receipts receive full task-contract validation. Historical
    schema-2 receipts are exposed only as hash-valid legacy inventory: their
    claimed terminal state is kept separate and is never returned as trusted
    execution or proof that Windows Task Scheduler launched the run.

    The result intentionally omits run ids, filesystem paths, command details,
    raw errors, session identifiers and full hashes so it is safe for status
    surfaces. This function never writes, revokes, repairs or upgrades a receipt.
    """
    selected = Path(path).resolve(strict=False)
    assert_receipt_not_revoked(selected)
    try:
        before = selected.stat()
        if before.st_size <= 0 or before.st_size > MAX_RECEIPT_BYTES:
            raise ReceiptError("receipt size is outside the bounded evidence limit")
        raw = selected.read_bytes()
        after = selected.stat()
    except FileNotFoundError as exc:
        raise ReceiptError("receipt does not exist") from exc
    except OSError as exc:
        raise ReceiptError("receipt is unreadable") from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise ReceiptError("receipt changed while being read")
    try:
        value = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReceiptError("receipt is unreadable or malformed") from exc
    if not verify_receipt(value):
        raise ReceiptError("receipt hash mismatch")
    assert_receipt_not_revoked(selected)
    schema_version = value.get("schema_version") if isinstance(value, dict) else None
    if schema_version == SCHEMA_VERSION:
        _validate_receipt_shape(value)
        task_contract = value["task_contract"]
        return {
            "inspection_schema_version": RECEIPT_INSPECTION_SCHEMA_VERSION,
            "evidence_status": "VALID_SCHEMA3_TASK_CONTRACT",
            "receipt_schema_version": SCHEMA_VERSION,
            "task_name": value["task_name"],
            "status": value["status"],
            "execution_state": value["execution_state"],
            "claimed_execution_state": value["execution_state"],
            "publication_state": value["publication_state"],
            "started_at": value["started_at"],
            "finished_at": value["finished_at"],
            "final_rc": value["final_rc"],
            "task_contract_version": task_contract["version"],
            "receipt_hash_prefix": value["receipt_hash"][:12],
            "trusted_for_execution": True,
            "trusted_for_completion": value["status"] in TERMINAL_STATUSES,
            # The producer records this limitation explicitly in ``origin``.
            # Correlation with Task Scheduler history remains a separate gate.
            "trusted_for_scheduler_launch": False,
            "reason": "execution receipt valid; scheduler launch origin unverified",
        }
    if schema_version == LEGACY_RECEIPT_SCHEMA_VERSION:
        return _legacy_receipt_summary(value)
    raise ReceiptError("receipt schema version is unsupported")


def _new_run_id(task_name: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    suffix = secrets.token_hex(3)
    prefix = re.sub(r"[^A-Za-z0-9_.-]", "-", task_name)[:40]
    return f"{prefix}-{stamp}-{os.getpid()}-{suffix}"


@_serialized_receipt_start
def start_receipt(
    *,
    root: Path,
    task_name: str,
    runner_path: Path,
    log_path: Path,
    run_id: str | None = None,
) -> tuple[Path, dict]:
    task = _safe_id(task_name, "task name")
    selected_run_id = _safe_id(run_id or _new_run_id(task), "run id")
    path = receipt_path(root, task, selected_run_id)
    assert_receipt_not_revoked(path)
    if path.exists():
        raise ReceiptError("receipt already exists")
    runner = Path(runner_path).resolve(strict=False)
    log = Path(log_path).resolve(strict=False)
    tool_path = Path(__file__).resolve(strict=False)
    runner_hash = _file_hash(runner)
    tool_hash = _file_hash(tool_path)
    if runner_hash is None:
        raise ReceiptError("runner is missing or unreadable")
    if tool_hash is None:
        raise ReceiptError("receipt tool is missing or unreadable")
    task_spec = _task_contract_spec(task)
    if task_spec is not None:
        expected_runner = (Path(__file__).resolve().parent / task_spec["runner_name"])
        if runner != expected_runner.resolve(strict=False):
            raise ReceiptError("monitored task is bound to a different runner path")
    task_contract = build_task_contract(
        task, runner_hash, receipt_producer_sha256=tool_hash
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "run_id": selected_run_id,
        "task_name": task,
        "origin": "RUNNER_INVOCATION_UNVERIFIED",
        "status": "RUNNING",
        "terminal_kind": None,
        "terminal_reason": None,
        "terminal_step_id": None,
        "started_at": _utc_now(),
        "finished_at": None,
        "execution_state": "RUNNING",
        "publication_state": "BLOCKED_LOCAL_ONLY",
        "final_rc": None,
        "runner": {
            "path": str(runner),
            "sha256_start": runner_hash,
            "sha256_end": None,
            "stable_during_run": None,
        },
        "receipt_tool": {
            "path": str(tool_path),
            "sha256_start": tool_hash,
            "sha256_end": None,
            "stable_during_run": None,
        },
        "task_contract": task_contract,
        "log_path": str(log),
        "steps": [],
        "transition_counter": 0,
    }
    sealed = seal_receipt(receipt)
    _validate_receipt_shape(sealed)
    _atomic_write(path, sealed)
    return path, sealed


def classify_step(
    wrapper: str,
    contract: str,
    raw_rc: int,
    *,
    classifier_version: int = STEP_CLASSIFIER_VERSION,
) -> dict:
    """Return only the semantics that the named CLI contract proves."""
    definition = STEP_CLASSIFIER_REGISTRY.get(classifier_version)
    if not isinstance(definition, dict):
        raise ReceiptError("step classifier version is unsupported")
    if not isinstance(raw_rc, int) or isinstance(raw_rc, bool):
        raise ReceiptError("raw rc must be an integer")
    if raw_rc < 0:
        return copy.deepcopy(definition["negative_exit"])
    exit_maps = definition["contract_exit_maps"]
    states = exit_maps.get(contract)
    if isinstance(states, dict):
        state = states.get(str(raw_rc))
        if state is not None:
            return {
                "semantic_state": state,
                "execution_valid": True,
                "classification_basis": contract,
            }
        result = copy.deepcopy(definition["known_contract_default"])
        result["classification_basis"] = contract
        return result
    if raw_rc == 0:
        return copy.deepcopy(definition["fallback_zero"])
    fallback = definition["fallback_nonzero"]
    return {
        "semantic_state": (
            fallback["graded_one_state"]
            if wrapper == "graded" and raw_rc == 1
            else fallback["other_state"]
        ),
        "execution_valid": fallback["execution_valid"],
        "classification_basis": fallback["classification_basis"],
    }


def _append_step(
    *,
    root: Path,
    task_name: str,
    run_id: str,
    step_id: str,
    wrapper: str,
    contract: str,
    raw_rc: int,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    evidence_mode: str,
    command: list[str] | None = None,
    launch_error: str | None = None,
) -> dict:
    step = _validate_step_request(
        step_id=step_id,
        wrapper=wrapper,
        contract=contract,
        evidence_mode=evidence_mode,
        command=command,
    )
    normalized_command = (
        _normalize_command(command) if evidence_mode == "exec" else None
    )
    command_hash = (
        _hash_value(normalized_command) if normalized_command is not None else None
    )
    path, receipt = _load_receipt(root, task_name, run_id)
    if receipt.get("status") != "RUNNING":
        raise ReceiptError("cannot append a step to a terminal receipt")
    _validate_next_expected_step(
        receipt, step_id=step, wrapper=wrapper, contract=contract,
        evidence_mode=evidence_mode, command_hash=command_hash,
        executable=(normalized_command[0] if normalized_command else None),
        argument_count=(len(normalized_command) - 1 if normalized_command else None),
    )
    existing = {
        item.get("step_id")
        for item in receipt.get("steps", [])
        if isinstance(item, dict)
    }
    if step in existing:
        raise ReceiptError("duplicate step transition")
    task_contract = _validate_task_contract_binding(receipt)
    classification = classify_step(
        wrapper, contract, raw_rc,
        classifier_version=task_contract["classifier_version"],
    )
    row = {
        "sequence": len(receipt.get("steps", [])) + 1,
        "step_id": step,
        "wrapper": wrapper,
        "contract": contract,
        "evidence_mode": evidence_mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": max(0, int(duration_ms)),
        "raw_rc": raw_rc,
        **classification,
    }
    if launch_error:
        row.update(
            {
                "semantic_state": "RUNNER_FAILED",
                "execution_valid": False,
                "classification_basis": "child_launch_error",
            }
        )
    if evidence_mode == "exec":
        assert normalized_command is not None
        row["executable"] = normalized_command[0]
        row["argument_count"] = max(0, len(normalized_command) - 1)
        row["command_hash"] = command_hash
    if launch_error:
        row["launch_error"] = launch_error
    receipt.setdefault("steps", []).append(row)
    receipt["transition_counter"] = int(receipt.get("transition_counter", 0)) + 1
    sealed = seal_receipt(receipt)
    _validate_receipt_shape(sealed)
    _atomic_write(path, sealed)
    return row


@_serialized_receipt_transition
def record_step(
    *,
    root: Path,
    task_name: str,
    run_id: str,
    step_id: str,
    wrapper: str,
    contract: str,
    raw_rc: int,
) -> dict:
    now = _utc_now()
    return _append_step(
        root=root,
        task_name=task_name,
        run_id=run_id,
        step_id=step_id,
        wrapper=wrapper,
        contract=contract,
        raw_rc=raw_rc,
        started_at=now,
        finished_at=now,
        duration_ms=0,
        evidence_mode="record",
    )


@_serialized_receipt_transition
def execute_step(
    *,
    root: Path,
    task_name: str,
    run_id: str,
    step_id: str,
    wrapper: str,
    contract: str,
    command: list[str],
) -> int:
    step = _validate_step_request(
        step_id=step_id,
        wrapper=wrapper,
        contract=contract,
        evidence_mode="exec",
        command=command,
    )
    normalized_command = _normalize_command(command)
    # Validate the transition before launching the child.  This prevents a
    # malformed or terminal receipt from executing an unrecordable command.
    _, receipt = _load_receipt(root, task_name, run_id)
    if receipt.get("status") != "RUNNING":
        raise ReceiptError("cannot execute a step for a terminal receipt")
    if any(
        isinstance(item, dict) and item.get("step_id") == step_id
        for item in receipt.get("steps", [])
    ):
        raise ReceiptError("duplicate step transition")
    _validate_next_expected_step(
        receipt, step_id=step, wrapper=wrapper, contract=contract,
        evidence_mode="exec", command_hash=_command_hash(command),
        executable=normalized_command[0],
        argument_count=len(normalized_command) - 1,
    )

    # Refuse to launch a child after either executable binding has drifted.
    # Finish-time checks still run independently to catch mid-step changes.
    for label in ("runner", "receipt_tool"):
        binding = receipt.get(label)
        path = Path(binding.get("path", "")) if isinstance(binding, dict) else Path("")
        current_hash = _file_hash(path) if str(path) else None
        if current_hash != binding.get("sha256_start"):
            raise ReceiptError("%s changed before child launch" % label)

    started_wall = _utc_now()
    started_clock = time.monotonic()
    launch_error = None
    try:
        child_environment = os.environ.copy()
        child_environment["NGERNDUANGOLD_TASK_NAME"] = task_name
        child_environment["NGERNDUANGOLD_TASK_RUN_ID"] = run_id
        completed = subprocess.run(
            command, check=False, env=child_environment
        )
        raw_rc = int(completed.returncode)
    except OSError as exc:
        raw_rc = 3
        launch_error = f"{type(exc).__name__}: {exc}"
        print(f"task receipt child launch failed: {launch_error}", file=sys.stderr)
    finished_wall = _utc_now()
    duration_ms = round((time.monotonic() - started_clock) * 1000)
    _append_step(
        root=root,
        task_name=task_name,
        run_id=run_id,
            step_id=step,
        wrapper=wrapper,
        contract=contract,
        raw_rc=raw_rc,
        started_at=started_wall,
        finished_at=finished_wall,
        duration_ms=duration_ms,
        evidence_mode="exec",
        command=command,
        launch_error=launch_error,
    )
    return raw_rc


def _derive_execution_state(
    receipt: dict,
    terminal_kind: str,
    final_rc: int,
    terminal_reason: str | None = None,
    terminal_step_id: str | None = None,
) -> str:
    """Derive execution state without treating a proven block as success.

    An abort is a runner failure unless it is bound to the exact last recorded
    step and that step's declared exit contract proves a fail-closed blocker.
    Unknown non-zero exits remain unverified even when they happened to reach
    the same batch abort label.
    """
    # Only 0/1/2 are valid non-fatal accumulator values.  A runner/evidence
    # failure must dominate any earlier verified blocker so the sealed receipt
    # can never look healthier than the Windows process exit.
    if final_rc not in {0, 1, CLI_COMPLETED_BLOCKED}:
        return "RUNNER_FAILED"
    steps = receipt.get("steps", [])
    if not isinstance(steps, list):
        return "UNVERIFIED_NONZERO"
    if any(
        isinstance(step, dict) and step.get("execution_valid") is False
        for step in steps
    ):
        return "RUNNER_FAILED"
    if any(
        isinstance(step, dict)
        and step.get("raw_rc") != 0
        and step.get("execution_valid") is None
        for step in steps
    ):
        return "UNVERIFIED_NONZERO"
    selected_reason = (
        terminal_reason
        if terminal_reason is not None
        else receipt.get("terminal_reason")
    )
    selected_step = (
        terminal_step_id
        if terminal_step_id is not None
        else receipt.get("terminal_step_id")
    )
    if terminal_kind == "abort":
        last_step = steps[-1] if steps and isinstance(steps[-1], dict) else {}
        verified_block_abort = bool(
            final_rc == CLI_COMPLETED_BLOCKED
            and selected_reason == "step_nonzero"
            and isinstance(selected_step, str)
            and selected_step == last_step.get("step_id")
            and last_step.get("raw_rc") != 0
            and last_step.get("execution_valid") is True
            and last_step.get("semantic_state") in VERIFIED_BLOCKING_STATES
        )
        return "COMPLETED_BLOCKED" if verified_block_abort else "RUNNER_FAILED"
    has_blocker = any(
        isinstance(step, dict) and step.get("semantic_state") in BLOCKING_STATES
        for step in steps
    )
    if has_blocker and final_rc not in {1, CLI_COMPLETED_BLOCKED}:
        return "RUNNER_FAILED"
    if has_blocker:
        return "COMPLETED_WITH_BLOCKERS"
    if final_rc != 0:
        return "UNVERIFIED_NONZERO"
    return "PASS"


@_serialized_terminal_transition
def finish_receipt(
    *,
    root: Path,
    task_name: str,
    run_id: str,
    terminal_kind: str,
    terminal_reason: str,
    terminal_step_id: str | None,
    publication_state: str,
    final_rc: int,
) -> dict:
    if terminal_kind not in {"end", "abort"}:
        raise ReceiptError("invalid terminal kind")
    if not isinstance(final_rc, int) or isinstance(final_rc, bool):
        raise ReceiptError("final rc must be an integer")
    reason = _safe_id(terminal_reason, "terminal reason")
    selected_step = (
        _safe_id(terminal_step_id, "terminal step id")
        if terminal_step_id is not None
        else None
    )
    if terminal_kind == "end":
        if reason != "normal_end" or selected_step is not None:
            raise ReceiptError("normal end has contradictory terminal evidence")
    else:
        if reason == "normal_end":
            raise ReceiptError("abort cannot use normal-end reason")
        if reason == "step_nonzero" and selected_step is None:
            raise ReceiptError("step abort is missing terminal step identity")
        if reason != "step_nonzero" and selected_step is not None:
            raise ReceiptError("non-step abort names a terminal step")
    if publication_state not in {
        "BLOCKED_LOCAL_ONLY",
        "BLOCKED",
        "NOT_ATTEMPTED",
    }:
        raise ReceiptError("invalid publication state")
    path, receipt = _load_receipt(root, task_name, run_id)
    if receipt.get("status") in TERMINAL_STATUSES:
        raise ReceiptError("receipt is already terminal")
    if receipt.get("status") != "RUNNING":
        raise ReceiptError("receipt has invalid transition state")
    _validate_step_manifest_progress(receipt)
    task_contract = _validate_task_contract_binding(receipt)
    if (
        terminal_kind == "end"
        and task_contract["enforcement"] == "STRICT_ORDERED"
        and len(receipt.get("steps", []))
        != len(task_contract["expected_steps"])
    ):
        raise ReceiptError("normal end is missing required task-contract steps")
    if reason == "step_nonzero":
        steps = receipt.get("steps", [])
        last_step = steps[-1] if steps and isinstance(steps[-1], dict) else {}
        if (
            selected_step != last_step.get("step_id")
            or last_step.get("raw_rc") == 0
            or final_rc == 0
        ):
            raise ReceiptError("step abort is not bound to the last non-zero step")
    runner_path = Path(receipt.get("runner", {}).get("path", ""))
    end_hash = _file_hash(runner_path) if str(runner_path) else None
    start_hash = receipt.get("runner", {}).get("sha256_start")
    stable = bool(start_hash and end_hash and start_hash == end_hash)
    receipt["runner"]["sha256_end"] = end_hash
    receipt["runner"]["stable_during_run"] = stable
    tool_path = Path(receipt.get("receipt_tool", {}).get("path", ""))
    tool_end_hash = _file_hash(tool_path) if str(tool_path) else None
    tool_start_hash = receipt.get("receipt_tool", {}).get("sha256_start")
    tool_stable = bool(
        tool_start_hash
        and tool_end_hash
        and tool_start_hash == tool_end_hash
    )
    receipt["receipt_tool"]["sha256_end"] = tool_end_hash
    receipt["receipt_tool"]["stable_during_run"] = tool_stable
    state = _derive_execution_state(
        receipt,
        terminal_kind,
        final_rc,
        terminal_reason=reason,
        terminal_step_id=selected_step,
    )
    if not stable or not tool_stable:
        state = "RUNNER_FAILED"
    receipt.update(
        {
            "status": "FINISHED" if terminal_kind == "end" else "ABORTED",
            "terminal_kind": terminal_kind,
            "terminal_reason": reason,
            "terminal_step_id": selected_step,
            "finished_at": _utc_now(),
            "execution_state": state,
            "publication_state": publication_state,
            "final_rc": int(final_rc),
            "transition_counter": int(receipt.get("transition_counter", 0)) + 1,
        }
    )
    sealed = seal_receipt(receipt)
    _validate_receipt_shape(sealed)

    # Re-read both executable bindings at the commit boundary.  A file can
    # change after the first end hash but before the receipt is persisted; once
    # any such drift is observed it remains a runner failure even if bytes later
    # happen to change back.
    commit_runner_hash = _file_hash(runner_path) if str(runner_path) else None
    commit_tool_hash = _file_hash(tool_path) if str(tool_path) else None
    runner_commit_stable = bool(
        stable and commit_runner_hash and commit_runner_hash == end_hash
    )
    tool_commit_stable = bool(
        tool_stable and commit_tool_hash and commit_tool_hash == tool_end_hash
    )
    if not runner_commit_stable or not tool_commit_stable:
        receipt["runner"]["sha256_end"] = commit_runner_hash
        receipt["runner"]["stable_during_run"] = runner_commit_stable
        receipt["receipt_tool"]["sha256_end"] = commit_tool_hash
        receipt["receipt_tool"]["stable_during_run"] = tool_commit_stable
        receipt["execution_state"] = "RUNNER_FAILED"
        sealed = seal_receipt(receipt)
        _validate_receipt_shape(sealed)
    revocation = _install_terminal_revocation(path, sealed)
    _atomic_write(path, sealed)

    post_runner_hash = _file_hash(runner_path) if str(runner_path) else None
    post_tool_hash = _file_hash(tool_path) if str(tool_path) else None
    runner_post_drift = post_runner_hash != sealed["runner"].get("sha256_end")
    tool_post_drift = post_tool_hash != sealed["receipt_tool"].get("sha256_end")
    if runner_post_drift or tool_post_drift:
        if runner_post_drift:
            receipt["runner"]["sha256_end"] = post_runner_hash
            receipt["runner"]["stable_during_run"] = False
        if tool_post_drift:
            receipt["receipt_tool"]["sha256_end"] = post_tool_hash
            receipt["receipt_tool"]["stable_during_run"] = False
        receipt["execution_state"] = "RUNNER_FAILED"
        sealed = seal_receipt(receipt)
        _validate_receipt_shape(sealed)
        sealed = _repair_drifted_terminal(path, sealed)
    return sealed, revocation


def terminal_process_code(receipt: dict) -> int:
    """Map the sealed execution state to the Windows runner exit contract.

    The batch accumulator is necessarily computed before the receipt is
    sealed.  Hash drift and invalid/unclassified step exits can only be proven
    while sealing, so the finish command must return that stronger terminal
    classification to the parent runner instead of always returning success.
    """
    state = receipt.get("execution_state")
    if state == "PASS":
        return 0
    if state in {"COMPLETED_BLOCKED", "COMPLETED_WITH_BLOCKERS"}:
        return CLI_COMPLETED_BLOCKED
    if state in {"RUNNER_FAILED", "UNVERIFIED_NONZERO"}:
        return CLI_RUNNER_FAILED
    return CLI_RUNNER_FAILED


def rotate_log(path: Path, *, max_bytes: int, keep: int) -> str:
    """Rotate a bounded private text log before the runner opens it."""
    selected = Path(path).resolve(strict=False)
    if max_bytes <= 0 or keep <= 0:
        raise ReceiptError("log rotation limits must be positive")
    try:
        size = selected.stat().st_size
    except FileNotFoundError:
        return "MISSING"
    except OSError as exc:
        raise ReceiptError("log metadata is unreadable") from exc
    if size < max_bytes:
        return "UNCHANGED"
    selected.parent.mkdir(parents=True, exist_ok=True)
    oldest = Path(f"{selected}.{keep}")
    try:
        oldest.unlink()
    except FileNotFoundError:
        pass
    for index in range(keep, 1, -1):
        older = Path(f"{selected}.{index - 1}")
        newer = Path(f"{selected}.{index}")
        if older.exists():
            os.replace(older, newer)
    os.replace(selected, Path(f"{selected}.1"))
    return "ROTATED"


def _base_parser() -> argparse.ArgumentParser:
    parser = ReceiptArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command_name", required=True)

    start = sub.add_parser("start")
    start.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    start.add_argument("--task", required=True)
    start.add_argument("--runner", type=Path, required=True)
    start.add_argument("--log", type=Path, required=True)
    start.add_argument("--run-id")

    execute = sub.add_parser("exec")
    execute.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    execute.add_argument("--task", required=True)
    execute.add_argument("--run-id", required=True)
    execute.add_argument("--step", required=True)
    execute.add_argument("--wrapper", choices=("required", "graded"), required=True)
    execute.add_argument("--contract", default="generic")
    execute.add_argument("child_command", nargs=argparse.REMAINDER)

    record = sub.add_parser("record")
    record.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    record.add_argument("--task", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--step", required=True)
    record.add_argument("--wrapper", default="internal")
    record.add_argument("--contract", default="internal-v1")
    record.add_argument("--raw-rc", type=int, required=True)

    finish = sub.add_parser("finish")
    finish.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    finish.add_argument("--task", required=True)
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--terminal", choices=("end", "abort"), required=True)
    finish.add_argument("--terminal-reason", required=True)
    finish.add_argument("--terminal-step")
    finish.add_argument("--publication-state", required=True)
    finish.add_argument("--final-rc", type=int, required=True)

    rotate = sub.add_parser("rotate-log")
    rotate.add_argument("--path", type=Path, required=True)
    rotate.add_argument("--max-bytes", type=int, default=5 * 1024 * 1024)
    rotate.add_argument("--keep", type=int, default=3)
    rotate.add_argument("--quiet", action="store_true")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--path", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _base_parser().parse_args(argv)
        if args.command_name == "start":
            _, receipt = start_receipt(
                root=args.root,
                task_name=args.task,
                runner_path=args.runner,
                log_path=args.log,
                run_id=args.run_id,
            )
            print(receipt["run_id"])
            return 0
        if args.command_name == "exec":
            command = list(args.child_command)
            if command and command[0] == "--":
                command = command[1:]
            return execute_step(
                root=args.root,
                task_name=args.task,
                run_id=args.run_id,
                step_id=args.step,
                wrapper=args.wrapper,
                contract=args.contract,
                command=command,
            )
        if args.command_name == "record":
            record_step(
                root=args.root,
                task_name=args.task,
                run_id=args.run_id,
                step_id=args.step,
                wrapper=args.wrapper,
                contract=args.contract,
                raw_rc=args.raw_rc,
            )
            return 0
        if args.command_name == "finish":
            sealed = finish_receipt(
                root=args.root,
                task_name=args.task,
                run_id=args.run_id,
                terminal_kind=args.terminal,
                terminal_reason=args.terminal_reason,
                terminal_step_id=args.terminal_step,
                publication_state=args.publication_state,
                final_rc=args.final_rc,
            )
            return terminal_process_code(sealed)
        if args.command_name == "rotate-log":
            state = rotate_log(args.path, max_bytes=args.max_bytes, keep=args.keep)
            if not args.quiet:
                print(state)
            return 0
        if args.command_name == "inspect":
            summary = inspect_receipt_file(args.path)
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            return (
                0
                if summary["evidence_status"] == "VALID_SCHEMA3_TASK_CONTRACT"
                else CLI_LEGACY_UNVERIFIED
            )
    except ReceiptError as exc:
        print(f"task receipt error: {exc}", file=sys.stderr)
        return CLI_EVIDENCE_ERROR
    except (
        OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
        RecursionError,
    ) as exc:
        print(f"task receipt I/O error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return CLI_EVIDENCE_ERROR
    return CLI_EVIDENCE_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
