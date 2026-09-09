"""Paths for local runtime state that must never enter the public repository.

The tracked tree contains contracts and aggregate public summaries only.  Live
network state, full execution logs, and sale records live below the ignored
``.local-private/runtime`` directory by default.  Environment variables allow
an operator to relocate individual files without putting a private path or
value into tracked configuration.
"""

from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _private_root() -> Path:
    raw = os.environ.get("NGERNDUANGOLD_PRIVATE_ROOT", "").strip()
    path = Path(raw).expanduser() if raw else REPO_ROOT / ".local-private" / "runtime"
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _private_file(env_name: str, default_name: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    path = Path(raw).expanduser() if raw else _private_root() / default_name
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


PRIVATE_ROOT = _private_root()
HOST_STATE_FILE = _private_file("NGERNDUANGOLD_HOST_STATE", "host-state.json")
GA4_PRIVATE_POLICY_FILE = _private_file(
    "NGERNDUANGOLD_GA4_PRIVATE_POLICY", "ga4-policy-private.json"
)
SALES_LOG_FILE = _private_file("NGERNDUANGOLD_SALES_LOG", "sales-log.jsonl")
SALES_INTAKE_FILE = _private_file(
    "NGERNDUANGOLD_SALES_INTAKE", "sales-intake.jsonl"
)
DISPATCHER_LOG_FILE = _private_file(
    "NGERNDUANGOLD_DISPATCHER_LOG", "dispatcher.log"
)
WEEKLY_LOG_FILE = _private_file("NGERNDUANGOLD_WEEKLY_LOG", "weekly.log")
IMPROVEMENT_RUNS_DIR = _private_file(
    "NGERNDUANGOLD_IMPROVEMENT_RUNS", "improvement-runs"
)


def ensure_private_parent(path: str | os.PathLike[str]) -> Path:
    """Create only the parent directory for an explicitly selected private file."""
    selected = Path(path).resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    return selected
