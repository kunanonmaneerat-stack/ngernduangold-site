#!/usr/bin/env python3
"""Regression checks for same-channel near-duplicate knowledge posts."""
import validate_knowledge_posts as validator


def row(content_id, line, threads, facebook):
    return {
        "id": content_id,
        "line": line,
        "threads": threads,
        "facebook": facebook,
    }


def main():
    base = "Start a monthly budget by listing fixed bills, flexible spending, and savings first."
    near = "Start a monthly budget by listing fixed bills, flexible spending and savings first!"
    different = "Before choosing a card, compare annual fees and how you actually spend."

    failures = validator.validate_same_channel_uniqueness([
        row("kn-1", 10, base, different),
        row("kn-2", 11, near, base),
    ])
    assert any("kn-2" in item and "threads" in item for item in failures), \
        "near duplicate in the same channel must fail"
    assert not any("facebook" in item for item in failures), \
        "cross-channel reuse must remain allowed"

    clean = validator.validate_same_channel_uniqueness([
        row("kn-1", 10, base, base),
        row("kn-2", 11, different, different),
    ])
    assert clean == [], "genuinely different rows must pass"
    print("knowledge post uniqueness: 3/3 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
