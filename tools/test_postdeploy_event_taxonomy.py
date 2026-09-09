#!/usr/bin/env python3
"""Regression tests for click-event semantics in the deploy smoke gate."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("postdeploy_smoke", HERE / "postdeploy_smoke.py")
SMOKE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(SMOKE)


def page(script: str, anchor: str = "") -> str:
    return (
        '<html><head><meta property="og:image" content="x">'
        '<meta property="og:title" content="x">'
        '<link rel="canonical" href="https://ngernduangold.com/test">'
        '</head><body>'
        + anchor
        + '<script>G-17PPE0M1B8;'
        + script
        + '</script></body></html>'
    )


GOOD_TAXONOMY = "".join(SMOKE.EVENT_TAXONOMY_MARKERS.values())
PRODUCTS = {
    "provider": {
        "availability": "active",
        "allowed_content_ids": ["test"],
    }
}


def affiliate_anchor(rel: str = "sponsored nofollow noopener",
                     provider: str = "provider",
                     content_id: str = "test",
                     sub_provider: str = "provider",
                     href: str | None = None) -> str:
    href = href or (
        "https://atth.me/test?utm_source=website&utm_medium=article&"
        f"utm_campaign=provider&utm_content=website_test_{sub_provider}")
    return (
        "มีลิงก์พันธมิตร"
        f'<a rel="{rel}" data-provider="{provider}" '
        f'data-content-id="{content_id}" href="{href}">apply</a>'
    )


class EventTaxonomyTests(unittest.TestCase):
    def test_scoped_taxonomy_passes(self) -> None:
        _, failures = SMOKE.check_page(page(GOOD_TAXONOMY))
        self.assertEqual(failures, [])

    def test_legacy_listener_with_only_affiliate_event_fails_closed(self) -> None:
        _, failures = SMOKE.check_page(
            page('gtag("event","affiliate_click",{page:location.pathname})')
        )
        self.assertTrue(any("event taxonomy missing" in item for item in failures))
        self.assertTrue(any("buy_intent_click" in item for item in failures))
        self.assertTrue(any("internal_cta_click" in item for item in failures))

    def test_own_product_must_not_be_sponsored_tracker(self) -> None:
        anchor = (
            '<a data-buy="letter-kit" rel="sponsored" '
            'href="https://atth.me/unsafe">buy</a>'
        )
        _, failures = SMOKE.check_page(page(GOOD_TAXONOMY, anchor))
        self.assertTrue(any("own-product CTA is classified as affiliate" in item for item in failures))

    def test_internal_own_product_is_allowed(self) -> None:
        anchor = '<a data-buy="free-tool" class="cta" href="/debt-health-check">open</a>'
        _, failures = SMOKE.check_page(page(GOOD_TAXONOMY, anchor))
        self.assertEqual(failures, [])

    def test_rel_values_must_be_exact_tokens(self) -> None:
        _, failures = SMOKE.check_page(
            page(GOOD_TAXONOMY, affiliate_anchor(
                rel="unsponsored notnofollow notnoopener")), products=PRODUCTS)
        self.assertTrue(any("ขาด rel 'sponsored'" in item for item in failures))
        self.assertTrue(any("ขาด rel 'nofollow'" in item for item in failures))
        self.assertTrue(any("ขาด rel 'noopener'" in item for item in failures))

    def test_internal_go_link_uses_the_same_merchant_contract(self) -> None:
        _, failures = SMOKE.check_page(
            page(GOOD_TAXONOMY, affiliate_anchor(href="/go/offer")),
            products=PRODUCTS)
        self.assertEqual(failures, [])

    def test_unregistered_or_wrong_content_fit_fails_closed(self) -> None:
        _, unknown = SMOKE.check_page(
            page(GOOD_TAXONOMY, affiliate_anchor(provider="unknown")),
            products=PRODUCTS)
        self.assertTrue(any("ไม่อยู่ใน registry" in item for item in unknown))
        _, wrong = SMOKE.check_page(
            page(GOOD_TAXONOMY, affiliate_anchor(content_id="wrong")),
            products=PRODUCTS)
        self.assertTrue(any("content fit" in item for item in wrong))

    def test_sub_id_provider_must_match_anchor_provider(self) -> None:
        _, failures = SMOKE.check_page(
            page(GOOD_TAXONOMY, affiliate_anchor(sub_provider="other")),
            products={**PRODUCTS, "other": {
                "availability": "active", "allowed_content_ids": ["test"]}})
        self.assertTrue(any("provider ไม่ตรง" in item for item in failures))

    def test_html_string_inside_script_is_not_a_literal_anchor(self) -> None:
        runtime_template = (
            "<script>var row='<a rel=\"sponsored nofollow noopener\" "
            "data-provider=\"'+provider+'\" href=\"'+url+'\">go</a>';</script>")
        count, failures = SMOKE.check_page(page(GOOD_TAXONOMY, runtime_template),
                                           products=PRODUCTS)
        self.assertEqual(count, 0)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
