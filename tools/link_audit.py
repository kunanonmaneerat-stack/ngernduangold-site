"""Internal-link audit for the built site — finds orphan / near-orphan pages.

WHY
    Index coverage is the current SEO bottleneck (GSC: many pages discovered-not-indexed).
    A page that no other page links to in its body is hard for Google to justify crawling
    and indexing. Target set by Cowork (24 Jul 2026): every indexable content page should
    have >= 3 CONTEXTUAL inbound links from topically related pages.

HOW TO RUN  (from repo root, after a build so site/ is fresh)
    set SITE_GA=G-17PPE0M1B8
    python build_site.py
    python tools/link_audit.py                 # list pages under the threshold
    python tools/link_audit.py --min 5         # stricter threshold
    python tools/link_audit.py --json out.json # full per-page data for diffing before/after

HOW TO READ THE OUTPUT
    in       contextual inbound = unique pages linking here from BODY content.
             The footer and the generic "read next" nav block are excluded on purpose:
             they link the same targets from every page and say nothing about topical
             relevance. The "other in this category" sibling block IS counted (topical).
    all      every internal inbound link including footer/nav boilerplate. A page with a
             low `in` but a high `all` (e.g. workshop-hr, linked site-wide from the footer)
             is NOT an orphan in Google's eyes — do not force body links into it.
    out      outbound contextual links from this page.
    cluster  rough topic bucket (debt / card / loan / save / insure / tax / tool) used to
             pick sensible link sources: prefer a source in the same cluster.
    sources  which pages currently link here — check before adding, never duplicate a pair.

WHAT IS NOT MEASURED
    Pages marked <meta name="robots" content="noindex"> (the infographic pages) and the
    Google Search Console ownership stub are excluded as targets: adding inbound links to
    a noindex page buys nothing. index.html is excluded as a target (the home page needs
    no inbound help) but still counts as a link SOURCE.

WHEN ADDING LINKS (rules from the 24 Jul order)
    <= 2 new contextual links per source page per wave; anchor text describes the target
    topic naturally (no keyword stuffing, no interest figures/percentages, none of the
    banned approval-claim words); edit build_site.py only; never duplicate an existing pair.
"""
import argparse
import io
import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")

# excluded as TARGETS only (still counted as link sources)
SKIP = {"index.html", "404.html"}

CLUSTERS = [
    ("debt", ("debt-", "close-debt", "pay-off", "move-informal", "credit-card-debt-lawsuit",
              "debt-collection", "rebuild-credit", "informal-debt")),
    ("card", ("credit-card", "first-credit-card", "cash-card", "lifestyle-credit", "krungsri-credit",
              "credit-bureau", "bureau-blacklist")),
    ("loan", ("loan-", "title-loan", "car-", "home-land", "motorcycle-", "refinance-", "personal-loan",
              "freelance-loan")),
    ("save", ("kept-", "save", "saving", "emergency-fund", "park-money", "high-yield", "salary-budget")),
    ("insure", ("insurance", "critical-illness", "health-insurance", "life-insurance")),
    ("tax", ("tax-", "retirement", "mutual-fund")),
    ("tool", ("debt-calculator", "debt-health-check", "refinance-savings", "debt-freedom-clock",
              "workshop-hr", "debt-letter-kit", "quiz", "links")),
]


def cluster_of(slug):
    s = slug.lower()
    for name, keys in CLUSTERS:
        for k in keys:
            if k in s:
                return name
    return "other"


def canon(slug):
    """Canonical form of a page slug: extensionless, matching the site's URL convention."""
    return slug[:-5] if slug.endswith(".html") else slug


def audit():
    if not os.path.isdir(SITE):
        raise SystemExit("BUILD FIRST: %s not found (run python build_site.py)" % SITE)
    files = sorted(f for f in os.listdir(SITE) if f.endswith(".html"))
    raw = {f: io.open(os.path.join(SITE, f), encoding="utf-8", errors="replace").read() for f in files}
    indexable = {f for f in files
                 if f not in SKIP and 'content="noindex"' not in raw[f] and not f.startswith("google")}
    pages = {canon(f): f for f in indexable}

    inbound = defaultdict(set)      # body-only (contextual)
    inbound_all = defaultdict(set)  # including footer / read-next nav
    outbound = defaultdict(set)

    href_re = re.compile(r'href="/([^"#?]*)[^"]*"')
    for f in files:
        src = canon(f)
        html = raw[f]
        body = html
        for marker in ("<footer", '<div class="related"><h2>อ่านต่อ'):
            i = body.find(marker)
            if i > 0:
                body = body[:i]
        for scope, bucket in ((body, inbound), (html, inbound_all)):
            for m in href_re.finditer(scope):
                tgt = canon(m.group(1))
                if not tgt or tgt == src or tgt not in pages:
                    continue
                bucket[tgt].add(src)
                if scope is body and f in indexable:
                    outbound[src].add(tgt)

    rows = [{
        "slug": slug,
        "inbound": len(inbound[slug]),
        "inbound_all": len(inbound_all[slug]),
        "outbound": len(outbound[slug]),
        "cluster": cluster_of(slug),
        "sources": sorted(inbound[slug]),
    } for slug in sorted(pages)]
    rows.sort(key=lambda r: (r["inbound"], r["slug"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description="Audit contextual inbound internal links per page.")
    ap.add_argument("--min", type=int, default=3, help="inbound threshold to flag (default 3)")
    ap.add_argument("--json", default=None, help="write full per-page rows to this JSON file")
    a = ap.parse_args()

    rows = audit()
    low = [r for r in rows if r["inbound"] < a.min]
    print("indexable pages=%d | contextual inbound<%d = %d" % (len(rows), a.min, len(low)))
    print("%-40s %3s %4s %3s  %-7s %s" % ("slug", "in", "all", "out", "cluster", "sources"))
    for r in low:
        print("%-40s %3d %4d %3d  %-7s %s" % (r["slug"][:40], r["inbound"], r["inbound_all"],
                                              r["outbound"], r["cluster"],
                                              ",".join(s[:20] for s in r["sources"])))
    if a.json:
        import json
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(rows, ensure_ascii=False, indent=1))
        print("json ->", a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
