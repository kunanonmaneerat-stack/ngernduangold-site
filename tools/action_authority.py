#!/usr/bin/env python3
"""Fail-closed actor capability checks for non-public project mutations.

This is intentionally smaller than the publication gate.  It answers only one
question: does the named actor currently have every requested capability in the
role SSOT?  Callers must still apply their action-specific gates and approvals.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


ROLE_PATH = Path(".system_control") / "role_capabilities.json"


class ActionBlocked(RuntimeError):
    """Raised before an action when its actor/capability is not explicit."""


def _strict_json_loads(value: str) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    document = json.loads(
        value,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for nested in item.values():
                require_finite(nested)
        elif isinstance(item, list):
            for nested in item:
                require_finite(nested)

    require_finite(document)
    return document


def _load_roles(repo: Path, role_path: Path | None = None) -> dict:
    path = Path(role_path) if role_path is not None else Path(repo) / ROLE_PATH
    try:
        if path.is_symlink():
            raise ValueError("role capabilities must not be a symlink")
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if ((before.st_size, before.st_mtime_ns) !=
                (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size):
            raise ValueError("role capabilities changed while being read")
        value = _strict_json_loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise ActionBlocked("role capabilities are missing or unreadable") from exc
    if not isinstance(value, dict) or value.get("default") != "deny":
        raise ActionBlocked("role capabilities must be a deny-by-default object")
    return value


def require_actor_capabilities(
    repo: Path,
    actor: str | None,
    actions: tuple[str, ...] | list[str],
    *,
    role_path: Path | None = None,
) -> str:
    """Return the normalized actor or raise before any protected mutation."""
    normalized_actor = actor.strip() if isinstance(actor, str) else ""
    if not normalized_actor:
        raise ActionBlocked("protected action requires an explicit actor")
    required = tuple(actions)
    if not required or any(not isinstance(action, str) or not action for action in required):
        raise ActionBlocked("protected action requires explicit capability names")

    roles = _load_roles(Path(repo).resolve(), role_path=role_path)
    actors = roles.get("actors")
    capabilities = actors.get(normalized_actor) if isinstance(actors, dict) else None
    if not isinstance(capabilities, dict):
        raise ActionBlocked("actor is not present in role capabilities")
    denied = [action for action in required if capabilities.get(action) is not True]
    if denied:
        raise ActionBlocked(
            "actor %r lacks current capability: %s"
            % (normalized_actor, ", ".join(denied))
        )
    return normalized_actor


def require_actor_capability(
    repo: Path,
    actor: str | None,
    action: str,
    *,
    role_path: Path | None = None,
) -> str:
    return require_actor_capabilities(
        repo, actor, (action,), role_path=role_path
    )
