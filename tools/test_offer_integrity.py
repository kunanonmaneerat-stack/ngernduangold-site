#!/usr/bin/env python3
"""Static revenue-integrity checks for generated pages; no network or tracked clicks."""
from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def read(path):
    return path.read_text(encoding="utf-8")


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def main():
    pages = list(SITE.glob("*.html"))
    check("generated HTML exists", len(pages) >= 1)
    all_html = "\n".join(read(path) for path in pages)

    affiliate_tags = re.findall(r'<a\b[^>]*atth\.me/[^>]*>', all_html, re.I)
    check("affiliate anchors exist", bool(affiliate_tags))
    check("every affiliate anchor has stable page content identity",
          all('data-content-id="' in tag for tag in affiliate_tags))
    check("every affiliate anchor has stable placement class",
          all('data-pos="' in tag for tag in affiliate_tags))
    check("every affiliate anchor identifies its provider",
          all('data-provider="' in tag for tag in affiliate_tags))
    check("every affiliate anchor carries the complete UTM/sub-id contract",
          all(all(field in tag for field in
                  ("utm_source=", "utm_medium=", "utm_campaign=", "utm_content="))
              for tag in affiliate_tags))
    build_source = read(ROOT / "build_site.py")
    check("CTA id fallback is semantic rather than a DOM ordinal",
          "function _ctaId(a)" in build_source and
          'return s?p+"-"+s:p+"-"+_pageContent(a)' in build_source)
    check("page identity is separated from incoming acquisition creative",
          "acquisition_content_id:_acqContent()" in build_source)
    check("interstitial continue link preserves the original CTA dimensions",
          "['data-cta-id','data-pos','data-content-id'].forEach" in build_source)
    affiliate_blocks = re.findall(r'<a\b[^>]*atth\.me/[^>]*>.*?</a>', all_html,
                                  re.I | re.S)
    unsupported = ("ลิงก์ทางการของผู้ให้บริการ", "สมัครออนไลน์ตรงกับผู้ให้บริการ",
                   "สมัครตรงกับผู้ให้บริการ", "· ปลอดภัย")
    check("affiliate redirects make no direct-official or safety guarantee",
          all(not any(claim in block for claim in unsupported)
              for block in affiliate_blocks))

    check("mismatched generic Krungsri tracker removed", "00dayn002a0x" not in all_html)

    car = read(SITE / "car-still-installment-loan-2026.html")
    check("car-refinance page does not use home-refinance tracker", "00eeac002a0x" not in car)
    check("car-refinance fallback is an internal guide", 'href="/car-refinance-2026' in car)

    interest = read(SITE / "credit-card-interest-2026.html")
    check("current card minimum is present", "8%" in interest)
    check("current temporary period is present", "1 \u0e21.\u0e04." in interest and "31 \u0e18.\u0e04. 2569" in interest)
    check("stale 5-10 percent range removed", "5\u201310%" not in interest and "5-10%" not in interest)

    risky = (
        'data-buy=', 'rel="sponsored', 'atth.me/', 'line.me/', 'gumroad.com/',
        'promptpay', '\u0e1e\u0e23\u0e49\u0e2d\u0e21\u0e40\u0e1e\u0e22\u0e4c',
        '\u0e2a\u0e48\u0e07\u0e2a\u0e25\u0e34\u0e1b', '199\u0e3f',
    )
    for path in (ROOT / "debt-letter-kit.html", SITE / "debt-letter-kit.html"):
        text = read(path).casefold()
        check(path.name + " carries paused status", 'data-offer-status="paused"' in text)
        check(path.name + " exposes no purchase mechanism",
              not any(token.casefold() in text for token in risky))

    links = read(SITE / "links.html")
    policy = json.loads(read(ROOT / ".system_control" / "policy.json"))
    products = {item["id"]: item for item in policy["products"]["items"]}
    check("own-product intents never use unbound data-note", "data-note=" not in all_html)
    if products["ebook-59"]["promotion_authorized"]:
        check("authorized ebook intent has stable product id",
              'data-buy="ebook-59"' in links)
    else:
        check("unauthorized ebook has no purchase or promotion path",
              'data-buy="ebook-59"' not in all_html and
              "guide59" not in all_html and
              "คู่มือปลดหนี้ 59฿" not in all_html and
              "คู่มือ + Worksheet 59฿" not in all_html)
    if products["debt-toolkit-gumroad"]["promotion_authorized"]:
        check("authorized toolkit intent has stable product id",
              'data-buy="debt-toolkit-gumroad"' in links)
    else:
        check("unauthorized toolkit has no purchase or promotion path",
              'data-buy="debt-toolkit-gumroad"' not in all_html and
              "toolkit199" not in all_html and "kit199" not in all_html and
              "ชุดเครื่องมือ 199฿" not in all_html and
              "สั่งชุดเครื่องมือ 199฿" not in all_html)
    if not any(products[pid]["promotion_authorized"]
               for pid in ("ebook-59", "debt-toolkit-gumroad")):
        check("links hub explains the own-product pause",
              'data-offer-status="paused"' in links)

    quiz = read(SITE / "quiz.html")
    check("quiz Krungsri recommendation is internal", 'krungsri:"/credit-card-easy-approval-2026"' in quiz)
    check("KTC PROUD is labeled as a revolving cash card",
          "บัตรกดเงินสด KTC PROUD" in all_html and "วงเงินหมุนเวียน" in all_html)
    check("KTC PROUD is not mislabeled as fixed-installment personal loan",
          "สินเชื่อบุคคล KTC Proud" not in all_html and
          "สินเชื่อส่วนบุคคล KTC PROUD" not in all_html and
          "สินเชื่อบุคคล KTC PROUD" not in all_html and
          "วงเงินก้อน ไม่ต้องค้ำ · ผ่อนรายเดือน" not in all_html)
    cash_card = read(SITE / "cash-card-easy-2026.html")
    check("cash-card page routes to KTC PROUD rather than vehicle finance",
          'data-provider="ktcproud"' in cash_card and
          'data-provider="ktcphboom"' not in cash_card)
    pberm_blocks = re.findall(
        r'<a\b[^>]*data-provider="ktcphboom"[^>]*>.*?</a>', all_html,
        re.I | re.S)
    check("KTC P BERM placements are never labeled as a generic cash card",
          pberm_blocks and all("บัตรกดเงินสด" not in block for block in pberm_blocks))
    print("offer integrity: all checks passed")


if __name__ == "__main__":
    main()
