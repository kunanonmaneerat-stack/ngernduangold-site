#!/usr/bin/env python3
"""Regression tests for product-vs-promotion expiry semantics."""
from datetime import date
import html
import json
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from .merchant_offer_gate import (
        ROOT,
        default_sources,
        evaluate,
        evaluate_own_product_offers,
        load_documents,
        load_registry,
        select_sources,
    )
except ImportError:
    from merchant_offer_gate import (
        ROOT,
        default_sources,
        evaluate,
        evaluate_own_product_offers,
        load_documents,
        load_registry,
        select_sources,
    )


CHECKS = 0


def registry():
    return {
        "schema_version": 2,
        "as_of": "2026-08-16",
        "review_valid_days": 30,
        "products": {
            "provider": {
                "availability": "active",
                "official_url": "https://example.test/product",
                "reviewed_on": "2026-08-16",
                "product_type": "term_personal_loan",
                "affiliate_network": "AccessTrade",
                "network_campaign_id": 123,
                "network_status": "approved",
                "network_verified_on": "2026-08-16",
                "tracking_urls": ["https://atth.me/test"],
                "allowed_content_ids": ["page"],
            }
        },
        "promotions": [{
            "id": "promo",
            "provider": "provider",
            "state": "expired",
            "valid_until": "2026-06-30",
            "official_url": "https://example.test/product",
            "verified_on": "2026-08-16",
            "claim_tokens": ["special 19.99%", "approved in 30 minutes"],
        }],
    }


def own_product_policy():
    return {
        "products": {"items": [{
            "id": "letter-kit-199",
            "sold_on": "site/debt-letter-kit.html",
            "deliverable": None,
            "status": "PROMISED-BUT-MISSING",
            "promotion_authorized": False,
        }]}
    }


def check(label, condition):
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print("PASS", label)


def main():
    today = date(2026, 8, 16)
    with TemporaryDirectory() as raw:
        strict_path = Path(raw) / "registry.json"
        strict_rejected = 0
        for value in (
            '{"schema_version":1,"schema_version":2}',
            '{"schema_version":2,"unused":NaN}',
            '{"schema_version":2,"unused":1e999}',
        ):
            strict_path.write_text(value, encoding="utf-8")
            try:
                load_registry(strict_path)
            except ValueError:
                strict_rejected += 1
        check("merchant registry rejects duplicate and non-finite JSON",
              strict_rejected == 3)
    check("clean-build source scope does not depend on generated site",
          ROOT / "site" not in default_sources())
    check("runtime mode explicitly adds generated site placements",
          ROOT / "site" in select_sources([], generated_site=ROOT / "site"))
    build_source = (ROOT / "build_site.py").read_text(encoding="utf-8")
    pre_gate = build_source.index("\ngate_merchant_offers()\n")
    first_generated_write = build_source.index('open(f"{OUT}/')
    post_gate = build_source.rindex("\ngate_merchant_offers(OUT)\n")
    check("build validates sources before output and generated placements after output",
          pre_gate < first_generated_write < post_gate)
    check("active product remains allowed after its promo expires",
          not evaluate(registry(), {"page": "provider product is available"}, today))
    paused_letter_page = {
        "debt-letter-kit.html": (
            '<section data-offer-status="paused">free sample only</section>'
        )
    }
    check("missing own product passes only with an explicit payment pause",
          not evaluate_own_product_offers(own_product_policy(), paused_letter_page))
    check("missing own product without a paused marker is blocked",
          bool(evaluate_own_product_offers(
              own_product_policy(),
              {"debt-letter-kit.html": "free sample only"},
          )))
    check("paused missing product cannot retain a payment endpoint",
          bool(evaluate_own_product_offers(
              own_product_policy(),
              {"debt-letter-kit.html": (
                  '<section data-offer-status="paused">free</section>'
                  '<a href="https://line.me/example">order</a>'
              )},
          )))
    unauthorized_buy = {
        "debt-letter-kit.html": (
            '<section data-offer-status="paused">free</section>'
            '<a data-buy="letter-kit-199" href="/pay">order</a>'
        )
    }
    check("promotion-disabled own product cannot expose data-buy",
          bool(evaluate_own_product_offers(
              own_product_policy(), unauthorized_buy,
          )))
    failures = evaluate(registry(), {"page": "special 19.99%"}, today)
    check("expired promotional claim is blocked", bool(failures))

    current = registry()
    current["promotions"][0]["state"] = "active"
    current["promotions"][0]["valid_from"] = "2026-07-01"
    current["promotions"][0]["valid_until"] = "2026-08-31"
    check("current promotional claim passes before its end date",
          not evaluate(current, {"page": "special 19.99%"}, today))
    qualified = registry()
    qualified["promotions"][0]["state"] = "active"
    qualified["promotions"][0]["valid_from"] = "2026-07-01"
    qualified["promotions"][0]["valid_until"] = "2026-08-31"
    qualified["promotions"][0]["claim_requirements"] = {
        "special 19.99%": ["first transfer >=50,000", "other draws 25%"],
    }
    qualified_copy = "special 19.99% first transfer >=50,000; other draws 25%"
    check("qualified promotional claim passes with same-document context",
          not evaluate(qualified, {"page": qualified_copy}, today))
    check("qualified promotional claim without all context is blocked",
          bool(evaluate(qualified,
                        {"page": "special 19.99% first transfer >=50,000"}, today)))
    check("qualifier in a different document cannot satisfy a claim",
          bool(evaluate(qualified, {
              "claim-page": "special 19.99%",
              "other-page": "first transfer >=50,000; other draws 25%",
          }, today)))
    repeated_claim = qualified_copy + "\n\nUNQUALIFIED special 19.99%"
    check("every promotional claim occurrence needs local qualifiers",
          bool(evaluate(qualified, {"page": repeated_claim}, today)))
    repeated_same_block = qualified_copy + "; special 19.99% repeated without qualifiers"
    check("repeated claim in one block needs repeated local qualifiers",
          bool(evaluate(qualified, {"page": repeated_same_block}, today)))
    duplicated_qualifiers_same_block = (
        "special 19.99% first transfer >=50,000 first transfer >=50,000; "
        "other draws 25% other draws 25%; UNQUALIFIED special 19.99%"
    )
    check("duplicated qualifiers cannot be borrowed by another claim in one block",
          bool(evaluate(qualified,
                        {"page": duplicated_qualifiers_same_block}, today)))
    check("separately qualified promotional claims pass in separate blocks",
          not evaluate(qualified,
                       {"page": qualified_copy + "\n\n" + qualified_copy}, today))
    malformed_requirements = registry()
    malformed_requirements["promotions"][0]["claim_requirements"] = {
        "unknown claim": ["qualifier"],
    }
    check("claim requirement keys must be registered claim tokens",
          bool(evaluate(malformed_requirements, {"page": "evergreen"}, today)))
    malformed_requirements = registry()
    malformed_requirements["promotions"][0]["claim_requirements"] = {
        "special 19.99%": [],
    }
    check("claim requirement context must be a non-empty token list",
          bool(evaluate(malformed_requirements, {"page": "evergreen"}, today)))
    check("promotional claim fails before its start date",
          bool(evaluate(current, {"page": "special 19.99%"}, date(2026, 6, 30))))
    check("same promotional claim fails after its end date",
          bool(evaluate(current, {"page": "special 19.99%"}, date(2026, 9, 1))))
    check("expired window cannot remain active even when public copy is clean",
          bool(evaluate(current, {"page": "evergreen product copy"}, date(2026, 9, 1))))
    current["promotions"][0]["state"] = "paused"
    check("paused promotional claim is blocked inside its date window",
          bool(evaluate(current, {"page": "special 19.99%"}, today)))
    anchor = ('<a data-provider="provider" data-content-id="page" '
              'href="https://atth.me/test">apply</a>')
    check("registered active placement passes", not evaluate(registry(), {"page": anchor}, today))
    for malformed_anchor in (
        ('<a href=https://atth.me/unknown data-provider=provider '
         'data-content-id=page rel=sponsored>x</a>'),
        ('<a data-provider="provider" data-content-id="page" '
         'href="https&#58;//atth.me/unknown">x</a>'),
        ('<a data-provider="provider" data-content-id="page" '
         'href="https://atth&#46;me/unknown">x</a>'),
        ('<a data-provider="provider" data-content-id="page" '
         'href="&#x2f;go/unknown">x</a>'),
    ):
        check("encoded or unquoted affiliate anchor fails closed: " + malformed_anchor,
              bool(evaluate(registry(), {"page": malformed_anchor}, today)))
    duplicate_href = (
        '<a data-provider="provider" data-content-id="page" '
        'href="https://example.test/benign" '
        'href="https://atth.me/unknown">x</a>'
    )
    check("duplicate critical anchor attributes fail closed",
          bool(evaluate(registry(), {"page": duplicate_href}, today)))
    check("unknown provider placement is blocked",
          bool(evaluate(registry(), {"page": anchor.replace('data-provider="provider"',
                                                            'data-provider="unknown"')}, today)))
    check("placement without content identity is blocked",
          bool(evaluate(registry(), {"page": anchor.replace(' data-content-id="page"', '')}, today)))
    check("placement without provider identity is blocked",
          bool(evaluate(registry(), {"page": anchor.replace(' data-provider="provider"', '')}, today)))
    go_anchor = ('<a rel="sponsored nofollow noopener" data-content-id="page" '
                 'href="/go/offer">apply</a>')
    check("internal affiliate redirect without provider is blocked",
          bool(evaluate(registry(), {"page": go_anchor}, today)))
    check("inert interstitial placeholder is not a placement",
          not evaluate(registry(), {"page": '<a rel="sponsored" href="">continue</a>'}, today))
    check("unreviewed page intent is blocked",
          bool(evaluate(registry(), {"page": anchor.replace('data-content-id="page"',
                                                            'data-content-id="wrong"')}, today)))
    paused = registry()
    paused["products"]["provider"]["availability"] = "paused"
    paused["products"]["provider"]["network_status"] = "paused"
    check("paused provider placement is blocked", bool(evaluate(paused, {"page": anchor}, today)))
    stale = registry()
    stale["products"]["provider"]["reviewed_on"] = "2026-07-01"
    check("stale merchant review is blocked", bool(evaluate(stale, {"page": anchor}, today)))
    malformed = registry()
    del malformed["products"]["provider"]["product_type"]
    check("missing product taxonomy is blocked", bool(evaluate(malformed, {"page": anchor}, today)))
    malformed = registry()
    del malformed["products"]["provider"]["network_verified_on"]
    check("partial affiliate network evidence is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["affiliate_network"] = "OtherNetwork"
    check("unexpected affiliate network is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["network_campaign_id"] = 0
    check("non-positive campaign id is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["network_campaign_id"] = True
    check("boolean campaign id is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["network_verified_on"] = "not-a-date"
    check("malformed network verification date is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["network_verified_on"] = "2026-08-17"
    check("future network verification date is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["network_verified_on"] = "2026-07-01"
    check("stale network verification is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["network_status"] = "paused"
    check("network status and availability conflict is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["tracking_urls"] = ["http://atth.me/test"]
    check("non-HTTPS tracking URL is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    malformed["products"]["provider"]["tracking_urls"] = [
        "https://atth.me/test", "https://atth.me/test"]
    check("duplicate tracking URL in one product is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    duplicate = registry()
    duplicate["products"]["other"] = {
        "availability": "active",
        "official_url": "https://example.test/other",
        "reviewed_on": "2026-08-16",
        "product_type": "term_personal_loan",
        "affiliate_network": "AccessTrade",
        "network_campaign_id": 124,
        "network_status": "approved",
        "network_verified_on": "2026-08-16",
        "tracking_urls": ["https://atth.me/test"],
        "allowed_content_ids": ["page"],
    }
    check("one tracker cannot belong to two products",
          bool(evaluate(duplicate, {"page": "evergreen"}, today)))
    duplicate = registry()
    duplicate["products"]["other"] = {
        "availability": "active",
        "official_url": "https://example.test/other",
        "reviewed_on": "2026-08-16",
        "product_type": "term_personal_loan",
        "affiliate_network": "AccessTrade",
        "network_campaign_id": 123,
        "network_status": "approved",
        "network_verified_on": "2026-08-16",
        "tracking_urls": ["https://atth.me/other"],
        "allowed_content_ids": ["page"],
    }
    check("one campaign id cannot belong to two products",
          bool(evaluate(duplicate, {"page": "evergreen"}, today)))
    check("runtime tracker without provider-content binding is blocked",
          bool(evaluate(registry(), {
              "quiz.html": '<script>var u="https://atth.me/test"</script>',
          }, today)))
    check("unregistered runtime tracker literal is blocked",
          bool(evaluate(registry(), {
              "quiz.html": '<script>var u="https://atth.me/unknown"</script>',
          }, today)))
    check("runtime tracker suffix cannot hide behind a registered prefix",
          bool(evaluate(registry(), {
              "quiz.html": '<script>var u="https://atth.me/test.evil"</script>',
          }, today)))
    check("runtime tracker query must use reviewed attribution keys",
          bool(evaluate(registry(), {
              "quiz.html": '<script>var u="https://atth.me/test?redirect=evil"</script>',
          }, today)))
    for obfuscated_runtime in (
        '<script>var u="https:"+"//atth.me/test"</script>',
        '<script>var u="https:\\/\\/atth.me\\/test"</script>',
        '<script>var u="https:\\u002f\\u002f\\u0061tth\\u002eme/test"</script>',
        '<script>var u="ht" + "tps://at" + "th.me/test"</script>',
        '<script>const u="https://at" + ("th.me/test")</script>',
        '<script>const u="https:\\057\\057atth.me/test"</script>',
        '<script>const u="https://atth\\u3002me/test"</script>',
        '<script>const u="https://\\uff41tth.me/test"</script>',
        '<script>const u=`https://${"at" + "th.me"}/test`</script>',
        '<script>const u=`https://${`${"at"+"th.me"}`}/test`</script>',
        '<script>const u="https://at\\u00adth.me/test"</script>',
        '<script>const u="https://at\\u200bth.me/test"</script>',
        '<script>const u="https://at\\tth.me/test"</script>',
        '<script>const u="https:\\\\atth.me/test"</script>',
        '<script>const u="https://at\\u180fth.me/test"</script>',
        '<script>const u="https://at\\u2064th.me/test"</script>',
    ):
        check("constant or escaped runtime tracker is blocked: " + obfuscated_runtime,
              bool(evaluate(registry(), {"quiz.html": obfuscated_runtime}, today)))
    check("tracker in executable iframe srcdoc is blocked",
          bool(evaluate(registry(), {
              "quiz.html": (
                  '<iframe srcdoc="&lt;script&gt;location=&quot;https://atth.me/test&quot;'
                  '&lt;/script&gt;"></iframe>'
              ),
          }, today)))
    for canonical_anchor in (
        '<a href="https://atth&#x3002;me/test">go</a>',
        '<a href="https://%61tth.me/test">go</a>',
    ):
        check("browser-canonical affiliate anchor is blocked: " + canonical_anchor,
              bool(evaluate(registry(), {"quiz.html": canonical_anchor}, today)))
    for browser_sink in (
        '<iframe src="https://atth.me/test"></iframe>',
        '<meta http-equiv="refresh" content="0;url=https://atth.me/test">',
        '<form action="https://atth.me/test"><button>go</button></form>',
        '<object data="https://atth.me/test"></object>',
        '<embed src="https://atth.me/test">',
        '<button formaction="https://atth.me/test">go</button>',
        '<script src="https://%61tth.me/test"></script>',
        (
            '<script src="data:text/javascript,location%3D%22https%3A%2F%2F'
            'atth.me%2Ftest%22"></script>'
        ),
        (
            '<iframe src="data:text/html,%3Cscript%3Elocation%3D%22https%3A%2F%2F'
            'atth.me%2Ftest%22%3C%2Fscript%3E"></iframe>'
        ),
        (
            '<button onclick="location=decodeURIComponent(&quot;https%3A%2F%2F'
            'atth.me%2Ftest&quot;)">go</button>'
        ),
        (
            '<a href="java&#x09;script:location=&quot;https://atth.me/test&quot;">'
            'go</a>'
        ),
    ):
        check("browser URL-bearing sink is blocked: " + browser_sink,
              bool(evaluate(registry(), {"quiz.html": browser_sink}, today)))
    nested_document = '<script>const value="reviewed-static-copy"</script>'
    for _ in range(6):
        nested_document = (
            '<iframe srcdoc="' + html.escape(nested_document, quote=True) + '"></iframe>'
        )
    check("nested executable document depth fails closed",
          bool(evaluate(registry(), {"quiz.html": nested_document}, today)))
    check("oversized executable script surface fails closed",
          bool(evaluate(registry(), {
              "quiz.html": "<script>" + ("x" * 1_000_001) + "</script>",
          }, today)))
    check("dynamic template identifier is not projected into a tracker host",
          not evaluate(registry(), {
              "quiz.html": (
                  '<script>const atth="example";'
                  'const u=`https://${atth}.me/test`;</script>'
              ),
          }, today))
    check("large inert prose does not consume the executable surface budget",
          not evaluate(registry(), {
              "quiz.html": "<p>" + ("x" * 2_000_001) + "</p>",
          }, today))
    check("plain explanatory HTML tracker text is not runtime code",
          not evaluate(registry(), {
              "quiz.html": "<p>ตัวอย่างข้อความ https://atth.me/test สำหรับอธิบายระบบ</p>",
          }, today))
    check("runtime tracker in javascript href is blocked",
          bool(evaluate(registry(), {
              "quiz.html": (
                  '<a href="javascript:location=&apos;https://atth.me/test&apos;">go</a>'
              ),
          }, today)))
    check("script comments and classifier patterns are not destinations",
          not evaluate(registry(), {
              "quiz.html": (
                  '<script>// example "https://atth.me/test"\n'
                  'var classifier=/https:\\/\\/atth\\.me\\//;'
                  'var host="atth.me";</script>'
              ),
          }, today))
    check("inert JSON script data is not executable runtime code",
          not evaluate(registry(), {
              "quiz.html": (
                  '<script type="application/json">'
                  '{"example":"https://atth.me/test"}</script>'
              ),
          }, today))
    check("HTML entities remain literal inside JavaScript raw-text",
          not evaluate(registry(), {
              "quiz.html": (
                  '<script>var example="https&#58;&#47;&#47;atth&#46;me/test";</script>'
              ),
          }, today))
    external_anchor = anchor.replace(
        '<a ', '<a rel="sponsored nofollow noopener" ').replace(
            'href="https://atth.me/test"',
            'href="https://evil.example/phish"')
    check("sponsored external destination cannot bypass tracker registry",
          bool(evaluate(registry(), {"page": external_anchor}, today)))
    check("registered active redirect tracker passes",
          not evaluate(registry(), {"_redirects": "/go/x https://atth.me/test 301!"}, today))
    check("unreferenced /go route cannot expose an arbitrary external target",
          bool(evaluate(registry(), {
              "_redirects": "/go/x https://evil.example/phish 301!",
          }, today)))
    check("/go route must be an exact forced permanent redirect",
          bool(evaluate(registry(), {
              "_redirects": "/go/x https://atth.me/test 200!",
          }, today)))
    routed_anchor = anchor.replace(
        'href="https://atth.me/test"', 'href="/go/x"')
    check("internal redirect target belongs to anchor provider",
          not evaluate(registry(), {
              "page": routed_anchor,
              "_redirects": "/go/x https://atth.me/test 301!",
          }, today))
    check("unregistered redirect tracker is blocked",
          bool(evaluate(registry(), {"_redirects": "/go/x https://atth.me/unknown 301!"}, today)))
    paused_runtime = registry()
    paused_runtime["products"]["provider"]["availability"] = "paused"
    paused_runtime["products"]["provider"]["network_status"] = "paused"
    check("paused tracker literal in runtime JS is blocked",
          bool(evaluate(paused_runtime,
                        {"quiz.html": '<script>var u="https://atth.me/test"</script>'}, today)))
    other_provider = registry()
    other_provider["products"]["other"] = {
        "availability": "active",
        "official_url": "https://example.test/other",
        "reviewed_on": "2026-08-16",
        "product_type": "term_personal_loan",
        "affiliate_network": "AccessTrade",
        "network_campaign_id": 124,
        "network_status": "approved",
        "network_verified_on": "2026-08-16",
        "tracking_urls": ["https://atth.me/other"],
        "allowed_content_ids": ["page"],
    }
    mismatched_anchor = anchor.replace(
        'href="https://atth.me/test"', 'href="https://atth.me/other"')
    check("tracker-to-provider mismatch is blocked",
          bool(evaluate(other_provider, {"page": mismatched_anchor}, today)))
    check("internal redirect cannot cross provider ownership",
          bool(evaluate(other_provider, {
              "page": routed_anchor,
              "_redirects": "/go/x https://atth.me/other 301!",
          }, today)))
    attributed_url = (
        "https://atth.me/test?utm_source=website&utm_medium=article"
        "&utm_campaign=provider&utm_content=website_page_provider"
    )
    check("direct tracker keeps reviewed path while allowing attribution query",
          not evaluate(registry(), {
              "page": (
                  '<a data-provider="provider" data-content-id="page" '
                  'rel="sponsored" href="%s">x</a>' % attributed_url
              ),
          }, today))
    check("redirect tracker keeps reviewed path with bounded attribution query",
          not evaluate(registry(), {
              "_redirects": "/go/x %s 301!" % attributed_url,
          }, today))
    for adversarial_url in (
        "https://atth.me:444/test",
        "https://atth.me/test?redirect=https%3A%2F%2Fevil.example",
        "https://atth.me/test?utm_source=website&utm_source=duplicate",
        "https://atth.me/test?utm_source=website&utm_medium=bad%20value",
    ):
        check("direct tracker authority/query is exact: " + adversarial_url,
              bool(evaluate(registry(), {
                  "page": (
                      '<a data-provider="provider" data-content-id="page" '
                      'rel="sponsored" href="%s">x</a>' % adversarial_url
                  ),
              }, today)))
    for suffix in ("/extra", "#frag", ".evil", "%2Fevil"):
        adversarial_url = "https://atth.me/test" + suffix
        check("direct tracker suffix is not an exact registered URL: " + suffix,
              bool(evaluate(registry(), {
                  "page": (
                      '<a data-provider="provider" data-content-id="page" '
                      'rel="sponsored" href="%s">x</a>' % adversarial_url
                  ),
              }, today)))
        check("redirect tracker suffix is not an exact registered URL: " + suffix,
              bool(evaluate(registry(), {
                  "page": routed_anchor,
                  "_redirects": "/go/x %s 301!" % adversarial_url,
              }, today)))
    check("redirect tracker query is not an exact registered URL",
          bool(evaluate(registry(), {
              "page": routed_anchor,
              "_redirects": "/go/x https://atth.me/test?x=1 301!",
          }, today)))
    malformed = registry()
    del malformed["promotions"][0]["official_url"]
    check("promotion without official evidence URL is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    malformed = registry()
    del malformed["promotions"][0]["verified_on"]
    check("promotion without verification date is blocked",
          bool(evaluate(malformed, {"page": "evergreen"}, today)))
    stale_promotion = registry()
    stale_promotion["promotions"][0].update({
        "state": "active",
        "valid_from": "2026-07-01",
        "valid_until": "2026-08-31",
        "verified_on": "2026-07-01",
    })
    check("active promotion with stale verification is blocked",
          bool(evaluate(stale_promotion, {"page": "evergreen"}, today)))
    with TemporaryDirectory() as raw:
        root = Path(raw)
        canonical = root / "canonical.html"
        canonical.write_text("special 19.99%", encoding="utf-8")
        docs = load_documents([canonical], today)
        check("canonical root HTML is evaluated",
              bool(evaluate(registry(), docs, today)))

        site = root / "site"
        site.mkdir()
        (site / "quiz.html").write_text("approved in 30 minutes", encoding="utf-8")
        (site / "_redirects").write_text("", encoding="utf-8")
        docs = load_documents([site], today)
        check("generated site and quiz HTML are evaluated",
              bool(evaluate(registry(), docs, today)))
        check("generated redirect surface is loaded",
              any(Path(name).name == "_redirects" for name in docs))

        js_site = root / "js-site"
        js_site.mkdir()
        (js_site / "index.html").write_text("clean", encoding="utf-8")
        (js_site / "runtime.js").write_text(
            'var u="https://atth.me/unknown"', encoding="utf-8")
        (js_site / "_redirects").write_text("", encoding="utf-8")
        js_docs = load_documents([js_site], today)
        check("standalone generated JavaScript tracker is evaluated",
              bool(evaluate(registry(), js_docs, today)))

        missing_redirects = root / "missing-redirects"
        missing_redirects.mkdir()
        (missing_redirects / "index.html").write_text("clean", encoding="utf-8")
        try:
            load_documents([missing_redirects], today)
        except ValueError:
            missing_redirects_blocked = True
        else:
            missing_redirects_blocked = False
        check("generated output without _redirects fails closed",
              missing_redirects_blocked)

        empty_site = root / "empty-site"
        empty_site.mkdir()
        try:
            load_documents([empty_site], today)
        except ValueError:
            empty_generated_site_blocked = True
        else:
            empty_generated_site_blocked = False
        check("explicit generated-site mode fails closed on empty output",
              empty_generated_site_blocked)

        manifest = root / "content_manifest.json"
        manifest.write_text(json.dumps({"items": [
            {"date": "2026-08-15", "caption": "special 19.99%"},
            {"date": "2026-08-17", "caption": "evergreen clean copy"},
        ]}), encoding="utf-8")
        docs = load_documents([manifest], today)
        check("past manifest history is excluded from the publishable gate",
              not evaluate(registry(), docs, today))
        manifest.write_text(json.dumps({"items": [
            {"date": "not-a-date", "caption": "special 19.99%"},
        ]}), encoding="utf-8")
        try:
            load_documents([manifest], today)
        except ValueError:
            malformed_manifest_blocked = True
        else:
            malformed_manifest_blocked = False
        check("malformed future manifest cannot evade the offer gate",
              malformed_manifest_blocked)

        knowledge = root / "KNOWLEDGE-POSTS-test.md"
        knowledge.write_text(
            "| 2026-08-15 | old | special 19.99% |\n"
            "| 2026-08-17 | next | approved in 30 minutes |\n",
            encoding="utf-8")
        docs = load_documents([knowledge], today)
        check("future knowledge-library claim is evaluated but past rows are excluded",
              bool(evaluate(registry(), docs, today)))
    print("merchant offer gate: %d checks passed" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
