#!/usr/bin/env python3
"""Regression tests for official Responsible Lending copy rules."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import comply_gate  # noqa: E402


def u(value):
    return value.encode("ascii").decode("unicode_escape")


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def main():
    prohibited = u(r"\u0e15\u0e34\u0e14\u0e1a\u0e39\u0e42\u0e23\u0e01\u0e47\u0e01\u0e39\u0e49\u0e44\u0e14\u0e49")
    ok, issues = comply_gate.check(prohibited + " " + comply_gate.RESPONSIBLE_LINE)
    check("official prohibited phrase is blocked", not ok and any("official" in x for x in issues))

    loan_copy = u(r"\u0e40\u0e1b\u0e23\u0e35\u0e22\u0e1a\u0e40\u0e17\u0e35\u0e22\u0e1a\u0e2a\u0e34\u0e19\u0e40\u0e0a\u0e37\u0e48\u0e2d\u0e08\u0e32\u0e01\u0e15\u0e49\u0e19\u0e17\u0e38\u0e19\u0e23\u0e27\u0e21")
    ok, issues = comply_gate.check(loan_copy)
    check("lending copy requires the current warning", not ok and "missing Responsible Lending warning" in issues)

    ok, issues = comply_gate.check(loan_copy + " " + comply_gate.RESPONSIBLE_LINE)
    check("neutral lending copy with warning passes", ok)

    neutral = u(r"\u0e08\u0e14\u0e23\u0e32\u0e22\u0e08\u0e48\u0e32\u0e22\u0e17\u0e38\u0e01\u0e27\u0e31\u0e19\u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e40\u0e2b\u0e47\u0e19\u0e01\u0e23\u0e30\u0e41\u0e2a\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e14")
    ok, issues = comply_gate.check(neutral)
    check("non-lending education does not need loan warning", ok)

    harmless = u(r"\u0e2d\u0e22\u0e48\u0e32\u0e15\u0e31\u0e14\u0e2a\u0e34\u0e19\u0e43\u0e08\u0e42\u0e14\u0e22\u0e44\u0e21\u0e48\u0e14\u0e39\u0e23\u0e32\u0e22\u0e08\u0e48\u0e32\u0e22")
    ok, issues = comply_gate.check(harmless)
    check("ordinary do-not-ignore wording is not overblocked", ok)

    print("5 checks, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
