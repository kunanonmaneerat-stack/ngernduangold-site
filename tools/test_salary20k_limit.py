#!/usr/bin/env python3
"""Regression contract for the BOT salary-20k credit-card limit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "build_site.py").read_text(encoding="utf-8")
PAGE = (ROOT / "site" / "credit-card-salary-20000-2026.html").read_text(
    encoding="utf-8"
)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def main():
    for label, document in (("generator", SOURCE), ("built page", PAGE)):
        check(label + " removes the unsupported 1.5-2x range", "1.5–2" not in document)
        check(label + " removes the unsupported 30k-40k range", "30,000–40,000" not in document)
        check(label + " states the 1.5x cap", "ไม่เกิน 1.5 เท่า" in document)
        check(label + " states the 30k cap at salary 20k", "ไม่เกิน 30,000 บาท" in document)
    check(
        "built page links the primary BOT credit-card source",
        "https://www.bot.or.th/th/satang-story/digital-fin-lit/creditcard.html" in PAGE,
    )
    print("salary20k BOT limit contract: all checks passed")


if __name__ == "__main__":
    main()
