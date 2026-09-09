#!/usr/bin/env python3
"""Focused tests for the shared non-public action capability gate."""

import json
from pathlib import Path
import tempfile

from action_authority import (
    ActionBlocked,
    require_actor_capabilities,
    require_actor_capability,
)


def write_roles(repo: Path, actors: dict) -> Path:
    path = repo / ".system_control" / "role_capabilities.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"default": "deny", "actors": actors}), encoding="utf-8"
    )
    return path


def blocked(label, call) -> None:
    try:
        call()
    except ActionBlocked:
        print("PASS", label)
        return
    raise AssertionError(label)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        write_roles(repo, {
            "owner": {
                "git_commit": True,
                "git_push": True,
                "deploy": True,
                "source_acknowledge": True,
            },
            "codex": {
                "git_commit": False,
                "git_push": False,
                "deploy": False,
                "source_acknowledge": False,
            },
        })
        actor = require_actor_capabilities(repo, "owner", ("git_push", "deploy"))
        if actor != "owner":
            raise AssertionError("authorized actor is returned")
        print("PASS owner has both push and deploy capabilities")
        require_actor_capability(repo, "owner", "source_acknowledge")
        print("PASS owner has source acknowledgement capability")
        blocked("missing actor fails closed", lambda: require_actor_capability(
            repo, None, "git_commit"
        ))
        blocked("unknown actor fails closed", lambda: require_actor_capability(
            repo, "unknown", "git_commit"
        ))
        blocked("Codex commit remains blocked", lambda: require_actor_capability(
            repo, "codex", "git_commit"
        ))
        blocked("all requested capabilities are required", lambda: require_actor_capabilities(
            repo, "codex", ("git_push", "deploy")
        ))
        bad = repo / "bad.json"
        bad.write_text(json.dumps({"default": "allow", "actors": {}}), encoding="utf-8")
        blocked("non-deny role file fails closed", lambda: require_actor_capability(
            repo, "owner", "git_commit", role_path=bad
        ))
        for label, raw_value in (
            (
                "duplicate capability key fails closed",
                '{"default":"deny","actors":{"owner":{"git_commit":false,'
                '"git_commit":true}}}',
            ),
            (
                "NaN anywhere in authority evidence fails closed",
                '{"default":"deny","actors":{"owner":{"git_commit":true}},'
                '"unused":NaN}',
            ),
            (
                "overflowed number anywhere in authority evidence fails closed",
                '{"default":"deny","actors":{"owner":{"git_commit":true}},'
                '"unused":1e999}',
            ),
        ):
            bad.write_text(raw_value, encoding="utf-8")
            blocked(label, lambda: require_actor_capability(
                repo, "owner", "git_commit", role_path=bad
            ))
    print("action authority: 10/10 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
