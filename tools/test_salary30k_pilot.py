#!/usr/bin/env python3
"""Fail-closed contract for the b4-p01 landing-page pilot. Network-free."""
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "site" / "credit-card-salary-30000-2026.html"
LEGACY_PAGE = ROOT / "site" / "credit-card-salary-30000.html"
LEGACY_SOURCE = ROOT / "credit-card-salary-30000.html"
REDIRECTS = ROOT / "site" / "_redirects"
SITEMAP = ROOT / "site" / "sitemap.xml"
BUILD_SOURCE = ROOT / "build_site.py"
VIDEO = ROOT / "reels" / "2026-08-16_b4-p01.mp4"
SITE_VIDEO = ROOT / "site" / "reels" / VIDEO.name
CAPTIONS = ROOT / "reels" / "2026-08-16_b4-p01.th.vtt"
SITE_CAPTIONS = ROOT / "site" / "reels" / CAPTIONS.name
POSTER = ROOT / "reels" / "2026-08-16_b4-p01-poster.png"
SITE_POSTER = ROOT / "site" / "reels" / POSTER.name
QA = ROOT / "automation-log" / "video-production" / "b4-p01_qa.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main():
    missing = [p for p in (PAGE, LEGACY_SOURCE, REDIRECTS, SITEMAP, BUILD_SOURCE,
                            VIDEO, SITE_VIDEO, CAPTIONS, SITE_CAPTIONS, POSTER,
                            SITE_POSTER, QA)
               if not p.is_file()]
    if missing:
        raise AssertionError("missing pilot artifact(s): " + ", ".join(str(p) for p in missing))

    html = PAGE.read_text(encoding="utf-8")
    redirects = REDIRECTS.read_text(encoding="utf-8")
    sitemap = SITEMAP.read_text(encoding="utf-8")
    build_source = BUILD_SOURCE.read_text(encoding="utf-8")
    legacy_source = LEGACY_SOURCE.read_text(encoding="utf-8")
    qa = json.loads(QA.read_text(encoding="utf-8"))

    canonical_url = "https://ngernduangold.com/credit-card-salary-30000-2026"
    assert re.findall(r'<link rel="canonical" href="([^"]+)">', html) == [canonical_url]
    assert f'<meta property="og:url" content="{canonical_url}">' in html
    assert re.findall(r'<link rel="canonical" href="([^"]+)">', legacy_source) == [canonical_url]
    assert f'<meta property="og:url" content="{canonical_url}">' in legacy_source
    assert '<meta name="robots" content="noindex,follow">' in legacy_source
    assert not LEGACY_PAGE.exists()
    for source in ("/credit-card-salary-30000", "/credit-card-salary-30000.html"):
        assert re.search(
            rf"^{re.escape(source)}\s+/credit-card-salary-30000-2026\s+301!$",
            redirects,
            re.M,
        )
    assert re.search(
        r"^/credit-card-salary-30000-2026\.html\s+"
        r"/credit-card-salary-30000-2026\s+301!$",
        redirects,
        re.M,
    )
    assert sitemap.count(f"<loc>{canonical_url}</loc>") == 1
    assert "<loc>https://ngernduangold.com/credit-card-salary-30000</loc>" not in sitemap
    legacy_href = re.compile(r'href=["\']/credit-card-salary-30000(?:["\'?#])')
    assert not [
        path.name for path in (ROOT / "site").glob("*.html")
        if legacy_href.search(path.read_text(encoding="utf-8"))
    ]

    assert len(re.findall(r"<h1(?:\s|>)", html, re.I)) == 1
    assert html.index("<h1") < html.index('data-cta-id="salary30000-compare"')
    assert "90,000" in html and "3 \u0e40\u0e17\u0e48\u0e32" in html
    for obsolete in ("1.5\u20132", "1.5-2", "45,000", "60,000",
                     "\u0e27\u0e07\u0e40\u0e07\u0e34\u0e19\u0e23\u0e27\u0e21"):
        assert obsolete not in html

    assert 'NO_TOP_OFFER_SLUGS = {"credit-card-salary-30000-2026"}' in build_source
    faq_position = html.index('<h2 id="faq">')
    offer = re.search(
        r'<a\b[^>]*data-cta-id="salary30000-ktc-lower"[^>]*>',
        html,
        re.I,
    )
    assert offer and offer.start() > faq_position
    assert "https://atth.me/go/PeCbnOcY" not in html[:faq_position]
    assert not re.search(r'<a\b[^>]*rel="[^"]*sponsored', html[:faq_position], re.I)
    offer_tag = offer.group(0).replace("&amp;", "&")
    for expected in (
        'rel="sponsored noopener nofollow"',
        'data-provider="ktccard"',
        'data-cta-id="salary30000-ktc-lower"',
        'data-pos="after-faq"',
        'data-content-id="salary30k-2026"',
        "https://atth.me/go/PeCbnOcY?utm_source=website",
        "utm_medium=article",
        "utm_campaign=ktccard",
        "utm_content=website_salary30k-lower_ktccard",
    ):
        assert expected in offer_tag
    assert html.count("utm_content=website_salary30k-lower_ktccard") == 1
    disclosure_position = html.rfind("มีลิงก์พันธมิตร", faq_position, offer.start())
    assert disclosure_position > faq_position
    assert 'data-offer-reviewed="2026-08-16"' in html
    assert "https://www.ktc.co.th/credit-card" in html
    assert ('data-cta-id="salary30000-compare" data-pos="after-options" '
            'data-content-id="salary30k-2026"') in html
    assert "content_id=salary30k-2026&amp;entry=salary30000" in html
    assert 'data-answer-id="salary30k-credit-limit" data-content-id="salary30k-2026"' in html
    assert 'data-content-id="b4-p01"' in html  # video creative stays independently attributable
    assert "acquisition_content_id" in html
    internal_event = re.search(r'internal_cta_click.{0,550}', html)
    assert internal_event and all(k in internal_event.group(0)
                                  for k in ("cta_id", "position", "content_id"))

    assert ('width="1080" height="1920"' in html and 'aspect-ratio:9/16' in html
            and f'poster="/reels/{POSTER.name}"' in html
            and f'src="/reels/{VIDEO.name}"' in html
            and f'src="/reels/{CAPTIONS.name}"' in html)
    assert html.count("https://www.bot.or.th/") >= 1
    assert "https://app.bot.or.th/1213/MCPD/ProductApp/Credit/" in html

    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert len(blocks) == 3
    parsed = [json.loads(block) for block in blocks]
    breadcrumb = next(x for x in parsed if x.get("@type") == "BreadcrumbList")
    assert not breadcrumb["itemListElement"][-1]["item"].endswith(".html")

    vtt = CAPTIONS.read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and vtt.count(" --> ") == 5
    assert "00:00:21.500" in vtt
    assert CAPTIONS.read_bytes() == SITE_CAPTIONS.read_bytes()
    assert POSTER.read_bytes() == SITE_POSTER.read_bytes()

    expected = qa["sha256"].upper()
    assert digest(VIDEO) == expected == digest(SITE_VIDEO)
    assert qa["full_decode"] == "PASS"
    assert qa["faststart"]["status"] == "PASS"
    assert qa["loudness"]["status"] == "PASS"
    assert qa["watermark"]["verdict"] == "PASS"
    print("test_salary30k_pilot: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("test_salary30k_pilot: FAIL - %s" % exc, file=sys.stderr)
        sys.exit(1)
