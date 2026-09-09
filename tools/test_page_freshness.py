#!/usr/bin/env python3
"""Prove a rebuild cannot impersonate a factual content review."""
from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def article(path):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                        path.read_text(encoding="utf-8"), re.S)
    return next(json.loads(block) for block in blocks
                if json.loads(block).get("@type") == "Article")


def main():
    source = (ROOT / "build_site.py").read_text(encoding="utf-8")
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    salary = article(SITE / "credit-card-salary-30000-2026.html")
    legacy = article(SITE / "kept-savings-2026.html")

    check("build timestamp is not a content freshness variable", "BUILD_DATE" not in source)
    check("reviewed page carries its explicit modification date",
          salary.get("dateModified") == "2026-08-16")
    check("unreviewed page omits fabricated modification date",
          "dateModified" not in legacy)
    check("sitemap does not restamp every URL",
          0 < sitemap.count("<lastmod>") < sitemap.count("<url>"))

    selected = {
        "pay-off-credit-card-debt-2026.html": "25680245.pdf",
        "loan-online-legal-2026.html": "BOTLicenseCheck",
        "car-still-installment-loan-2026.html": "auto-loan-restructuring",
        "refinance-home-2026.html": "news-20260514",
    }
    for filename, source_token in selected.items():
        text = (SITE / filename).read_text(encoding="utf-8")
        check(filename + " exposes bound official sources",
              'class="official-sources"' in text and source_token in text)
    print("page freshness/source binding: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
