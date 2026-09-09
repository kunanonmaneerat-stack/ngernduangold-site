#!/usr/bin/env python3
"""Regression tests for policy-aware post queue selection."""
import json
from pathlib import Path
import tempfile
import sys
import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import post_agent  # noqa: E402
import post_timing  # noqa: E402


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def main():
    with tempfile.TemporaryDirectory(prefix="post_queue_policy_") as tmp:
        root = Path(tmp)
        policy_path = root / "policy.json"
        policy_path.write_text(json.dumps({"channels": {
            "facebook": {"state": "manual"},
            "threads": {"state": "active"},
            "tiktok": {"state": "retired"},
            "instagram": {"state": "paused"},
            "pantip": {"state": "limited", "phase_until": "2026-08-14", "weekly_quota": 3},
            "youtube": {"state": "active"},
        }}), encoding="utf-8")

        check("post queue excludes retired channels",
              post_agent.eligible_platforms(str(policy_path)) == ["fb", "threads"])
        check("timing excludes paused, retired, and expired channels",
              post_timing.eligible_platforms(
                  str(policy_path), datetime.date(2026, 8, 16)
              ) == ["fb", "threads", "yt"])
        check("timing excludes limited Pantip without its review and authority gates",
              post_timing.eligible_platforms(
                  str(policy_path), datetime.date(2026, 8, 14)
              ) == ["fb", "threads", "yt"])

        missing = root / "missing.json"
        check("queue fails closed when policy is absent",
              post_agent.eligible_platforms(str(missing)) == [])
        check("timing fails closed when policy is absent",
              post_timing.eligible_platforms(str(missing)) == [])

        malformed = root / "malformed.json"
        malformed.write_text("{not-json", encoding="utf-8")
        check("queue fails closed when policy is malformed",
              post_agent.eligible_platforms(str(malformed)) == [])
        check("timing fails closed when policy is malformed",
              post_timing.eligible_platforms(str(malformed)) == [])

        partial = root / "partial.json"
        partial.write_text(json.dumps({"channels": {
            "facebook": {},
            "threads": {"state": "unknown"},
            "tiktok": {"state": "limited", "phase_until": "2026-08-20", "weekly_quota": 0},
        }}), encoding="utf-8")
        check("queue blocks missing, unknown, and zero-quota states",
              post_agent.eligible_platforms(str(partial), datetime.date(2026, 8, 16)) == [])
        check("timing blocks missing channels and unknown states",
              post_timing.eligible_platforms(str(partial), datetime.date(2026, 8, 16)) == [])

        counts = post_timing.social_counts([
            (8, "(direct)", 82),
            (8, "chatgpt.com", 12),
            (12, "facebook.com", 5),
            (12, "threads.net", 2),
            (20, "pantip.com", 14),
        ])
        check("timing excludes direct and non-social sessions",
              counts == {12: 7, 20: 14})

        package = root / "package.md"
        package.write_text("# Content Package - Current topic\n\n## Facebook\n", encoding="utf-8")
        check("current package title is a topic fallback",
              post_agent.topics_from(str(package)) == ["Current topic"])

        library = root / "KNOWLEDGE-POSTS-C.md"
        library.write_text(
            "| date | id | topic | threads_text | fb_text |\n"
            "|---|---|---|---|---|\n"
            "| 2026-08-16 | kn-29 | Safe topic | body | body |\n",
            encoding="utf-8",
        )
        row, reasons = post_agent.knowledge_row_for_date(str(library), "2026-08-16")
        check("invalid knowledge row fails closed", row is None and bool(reasons))

        calls = []

        class FakeKnowledgeValidator:
            @staticmethod
            def parse_rows(_path):
                return [{"date": "2026-08-16", "id": "kn-29", "topic": "Safe topic"}]

            @staticmethod
            def validate(_path, content_id=None):
                calls.append(content_id)
                return ([{"date": "2026-08-16", "id": "kn-29", "topic": "Safe topic"}], [])

        prior_validator = sys.modules.get("validate_knowledge_posts")
        try:
            sys.modules["validate_knowledge_posts"] = FakeKnowledgeValidator
            row, reasons = post_agent.knowledge_row_for_date(str(library), "2026-08-16")
        finally:
            if prior_validator is None:
                sys.modules.pop("validate_knowledge_posts", None)
            else:
                sys.modules["validate_knowledge_posts"] = prior_validator
        check("queue validates the exact selected content id",
              row and row["id"] == "kn-29" and not reasons and calls == ["kn-29"])

        calls.clear()
        try:
            sys.modules["validate_knowledge_posts"] = FakeKnowledgeValidator
            row, reasons = post_agent.knowledge_row_for_date(str(library), "2026-08-17")
        finally:
            if prior_validator is None:
                sys.modules.pop("validate_knowledge_posts", None)
            else:
                sys.modules["validate_knowledge_posts"] = prior_validator
        check("missing date does not validate a different content id",
              row is None and bool(reasons) and calls == [])

        packages = root / "packages"
        packages.mkdir()
        safe_package = packages / "fallback.md"
        safe_package.write_text("# Content Package - Generic evergreen topic\n", encoding="utf-8")
        old_knowledge, old_packages = post_agent.KNOWLEDGE, post_agent.PKG
        try:
            post_agent.KNOWLEDGE = str(root)
            post_agent.PKG = str(packages)
            selected, topics, kind, blocked = post_agent.select_content(
                datetime.date(2026, 8, 16))
        finally:
            post_agent.KNOWLEDGE, post_agent.PKG = old_knowledge, old_packages
        check("declared but invalid knowledge date cannot fall back",
              selected == str(library) and topics == [] and kind == "blocked" and bool(blocked))
        check("blocked queue returns a failing process code",
              post_agent.queue_exit_code({"blocked_reasons": ["source pending"]}) == 2)
        check("clean prepared queue returns success",
              post_agent.queue_exit_code({"blocked_reasons": []}) == 0)

    print("17 checks, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
