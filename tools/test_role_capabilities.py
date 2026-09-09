#!/usr/bin/env python3
"""One current boolean per actor/action; stale policy docs must carry an amendment banner."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIONS = {
    "local_write", "web_research", "social_publish", "git_commit",
    "git_push", "deploy", "financial_transaction", "source_acknowledge",
    "external_notify", "external_storage_write", "package_install",
    "scheduler_mutation",
}


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def main():
    data = json.loads((ROOT / ".system_control" / "role_capabilities.json").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / ".system_control" / "policy.json").read_text(encoding="utf-8"))
    check("role schema records the internal delegation", data.get("schema_version") == 2)
    check("authority defaults to deny", data.get("default") == "deny")
    check("superseded policy audit is not an authority",
          "automation-log/POLICY-AUDIT_20260816.md" not in data.get("authority", []))
    for actor, caps in data["actors"].items():
        check(actor + " has exactly the canonical actions", set(caps) == ACTIONS)
        check(actor + " capabilities are booleans", all(type(value) is bool for value in caps.values()))
    delegation = data.get("delegations", {}).get("codex", {})
    check("Codex is the dated internal page operator",
          delegation.get("authorized_by") == "owner" and
          delegation.get("authorized_on") == "2026-08-16" and
          delegation.get("role") == "internal_page_operator")
    check("internal operator references the page-only identity",
          delegation.get("public_identity_ref") ==
          ".system_control/policy.json#/public_identity" and
          delegation.get("public_speaker") is False and
          policy.get("public_identity", {}).get("page_only") is True)
    check("Codex can improve the local project",
          data["actors"]["codex"]["local_write"] is True and
          data["actors"]["codex"]["web_research"] is True)
    check("non-owner automation cannot mutate remote state",
          all(not data["actors"][actor][action]
              for actor in ("codex", "cowork", "claude_code", "github_actions")
              for action in ("social_publish", "git_commit", "git_push", "deploy",
                             "financial_transaction", "source_acknowledge",
                             "external_notify", "external_storage_write",
                             "package_install", "scheduler_mutation")))
    check("only owner can acknowledge official-source review",
          data["actors"]["owner"]["source_acknowledge"] is True and
          all(data["actors"][actor]["source_acknowledge"] is False
              for actor in ("codex", "cowork", "claude_code", "github_actions")))
    banners = {
        "STANDING-RULE_autopost.md": "PARTIALLY SUPERSEDED 2026-08-16",
        "automation-log/OWNER-MANDATE_20260702.md": "AMENDED 2026-08-16",
        "OPERATING-NOTES.md": "AUTHORITY NOTICE 2026-08-16",
    }
    for rel, marker in banners.items():
        head = "\n".join((ROOT / rel).read_text(encoding="utf-8").splitlines()[:8])
        check(rel + " identifies stale authority", marker in head)
    print("role capability contract: all checks passed")


if __name__ == "__main__":
    main()
