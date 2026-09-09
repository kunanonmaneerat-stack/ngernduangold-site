#!/usr/bin/env python3
"""Focused deterministic tests for descriptive release/funnel readiness."""

from __future__ import annotations

import copy
from datetime import date
import json
import os
from pathlib import Path
import tempfile

import postdeploy_smoke as smoke
import release_contract
import release_funnel_readiness as readiness


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def _report_path_fails(raw: str, repo: Path, contains: str) -> bool:
    try:
        readiness._json_report_path(raw, repo)
    except ValueError as exc:
        return contains in str(exc)
    return False


def page(canonical: str, *, target: bool = False, unsafe: bool = False) -> str:
    markers = smoke.GA_ID + "".join(smoke.EVENT_TAXONOMY_MARKERS.values())
    body = "<p>ordinary sourced page</p>"
    if target:
        body += (
            '<div>\u0e21\u0e35\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e1e\u0e31\u0e19\u0e18\u0e21\u0e34\u0e15\u0e23</div>'
            '<a rel="sponsored nofollow noopener" data-provider="ktccard" '
            'data-content-id="salary30k-2026" data-cta-id="salary30000-ktc-lower" '
            'data-pos="after-faq" href="https://atth.me/go/ABC123?utm_source=website&amp;'
            'utm_medium=article&amp;utm_campaign=ktccard&amp;'
            'utm_content=website_salary30k-lower_ktccard">details</a>'
        )
    if unsafe:
        body += (
            '<a data-note="\u0e2a\u0e31\u0e48\u0e07 \u0e42\u0e2d\u0e19\u0e1e\u0e23\u0e49\u0e2d\u0e21\u0e40\u0e1e\u0e22\u0e4c 59\u0e3f" '
            'href="https://line.me/example">\u0e2a\u0e31\u0e48\u0e07 59\u0e3f</a>'
            '<a href="https://shop.gumroad.com/l/kit">checkout</a>'
        )
    return (
        '<!doctype html><html><head><link rel="canonical" href="%s">'
        '<meta property="og:title" content="title"><meta property="og:image" content="image">'
        '<script>%s</script></head><body>%s</body></html>' % (canonical, markers, body)
    )


def pilot() -> dict:
    return {
        "schema_version": 2,
        "pilot_id": "salary30k-ktccard-context-v1",
        "state": "planned_blocked",
        "external_action_authorized": False,
        "hypothesis": "fixture",
        "target": {
            "canonical_url": "https://ngernduangold.com/credit-card-salary-30000-2026",
            "page_file": "credit-card-salary-30000-2026.html",
            "content_id": "salary30k-2026",
            "provider": "ktccard",
            "cta_id": "salary30000-ktc-lower",
            "position": "after-faq",
            "primary_event": "affiliate_click",
        },
        "design": {
            "unit": "qualified_landing_session",
            "primary_metric": "affiliate_click_sessions / qualified_landing_sessions",
            "minimum_qualified_sessions": 100,
            "maximum_qualified_sessions": 300,
            "maximum_duration_days": 14,
            "success_threshold": {
                "value": 0.08,
                "status": "provisional_planning_assumption",
                "confidence": "low",
                "trusted_historical_baseline_available": False,
                "reset_after_first_trusted_baseline": True,
                "rationale": "fixture has no trusted historical baseline",
            },
            "maximum_cta_variants": 1,
            "freeze_page_offer_and_cta_during_window": True,
            "clicks_do_not_prove_revenue": True,
            "outcome_classification": "directional_only",
            "winner_declaration_allowed": False,
            "scale_decision_allowed": False,
            "decision_rule": "directional only; never declare a winner or scale",
        },
        "prerequisites": {
            "minimum_live_readiness_score": 80,
            "required_categories": [
                "inventory", "exact_release", "attribution", "offer_safety"
            ],
            "analytics_trust": "TRUSTED",
            "measurement_contract_support": "REQUIRED",
            "publishable_placement_receipt": "REQUIRED",
            "owner_execution_authority": "REQUIRED_SEPARATELY",
            "exact_release_lock": True,
        },
        "measurement_contract": {
            "contract_version": 1,
            "producer_path": "pipeline/ga4_pull.py",
            "schema_adapter_path": "pipeline/ga4_schema.py",
            "producer_contract_symbol": "PILOT_MEASUREMENT_CONTRACT",
            "schema_fields_symbol": "PILOT_MEASUREMENT_FIELDS",
            "primary_metric": "affiliate_click_sessions / qualified_landing_sessions",
            "required_fields": [
                "affiliate_click_sessions", "qualified_landing_sessions"
            ],
            "required_dimensions": sorted(readiness.REQUIRED_ATTRIBUTION_DIMENSIONS),
            "required_scopes": {
                "affiliate_click_sessions": "session",
                "qualified_landing_sessions": "session",
            },
            "qualified_landing_session_definition": "exact target landing session excluding synthetic traffic",
        },
        "attribution_dimensions": sorted(readiness.REQUIRED_ATTRIBUTION_DIMENSIONS),
        "stop_conditions": sorted(readiness.REQUIRED_PILOT_STOPS),
    }


def fixture(root: Path) -> Path:
    src = root / "site"
    src.mkdir(parents=True)
    for relative in release_contract.SOURCE_INPUTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == release_contract.PILOT_PATH:
            path.write_text(json.dumps(pilot()), encoding="utf-8")
        elif relative == Path(".system_control/policy.json"):
            path.write_text(json.dumps({
                "products": {"items": [{
                    "id": "ebook-59",
                    "sold_on": "site/links.html",
                    "deliverable": None,
                    "promotion_authorized": False,
                }]}
            }), encoding="utf-8")
        elif relative == Path(".system_control/merchant_offers.json"):
            path.write_text(json.dumps({
                "schema_version": 2,
                "as_of": "2026-08-16",
                "review_valid_days": 30,
                "products": {
                    "ktccard": {
                        "availability": "active",
                        "reviewed_on": "2026-08-16",
                        "official_url": "https://example.test/official",
                        "product_type": "credit_card",
                        "affiliate_network": "AccessTrade",
                        "network_campaign_id": 100,
                        "network_status": "approved",
                        "network_verified_on": "2026-08-16",
                        "tracking_urls": ["https://atth.me/go/ABC123"],
                        "allowed_content_ids": ["salary30k-2026"],
                    }
                },
                "promotions": [],
            }), encoding="utf-8")
        else:
            path.write_text("fixture", encoding="utf-8")
        os.utime(path, (100, 100))

    index = src / "index.html"
    target = src / "credit-card-salary-30000-2026.html"
    index.write_text(page("https://ngernduangold.com/"), encoding="utf-8")
    target.write_text(
        page("https://ngernduangold.com/credit-card-salary-30000-2026", target=True),
        encoding="utf-8",
    )
    os.utime(index, (200, 200))
    os.utime(target, (200, 200))
    manifest = release_contract.manifest_for(src, root)
    (src / release_contract.MANIFEST_NAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return src


def run() -> None:
    with tempfile.TemporaryDirectory() as strict_raw:
        strict_path = Path(strict_raw) / "evidence.json"
        for malformed in (
            '{"schema_version":1,"schema_version":2}',
            '{"schema_version":1,"probe":1e999}',
        ):
            strict_path.write_text(malformed, encoding="utf-8")
            try:
                readiness._read_json(strict_path, "fixture evidence")
            except ValueError:
                pass
            else:
                raise AssertionError("ambiguous/non-finite readiness evidence must fail closed")
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        src = fixture(root)
        local = readiness.evaluate(src, repo=root, checked_on=date(2026, 8, 16))
        check("audited local release contract scores 80, not a false pilot 100",
              local["score_descriptive"] == 80)
        check("all four release categories pass",
              all(local["categories"][name]["status"] == "PASS"
                  for name in readiness.HARD_BLOCKER_CATEGORIES))
        check("pilot is blocked while producer/schema support is absent",
              local["categories"]["bounded_pilot"]["status"] == "BLOCKED" and
              local["categories"]["bounded_pilot"]["measurement_contract_supported"] is False)
        check("score never grants external authority",
              local["score_is_authorization"] is False and
              local["external_action_authorized"] is False and
              local["publication_authority_granted"] is False)
        check("contract score is separated from publication and operational eligibility",
              local["assessment_scope"] == "release_funnel_contract_only" and
              local["publication"]["status"] == "NOT_AUTHORIZED" and
              local["operational_pilot_eligibility"]["status"] == "BLOCKED" and
              "ready" not in local)

        live_pages = {
            "https://ngernduangold.com/": page("https://ngernduangold.com/").replace(
                "<script>", "<script>legacy-"
            ).replace(smoke.GA_ID, ""),
            "https://ngernduangold.com/credit-card-salary-30000-2026": page(
                "https://ngernduangold.com/credit-card-salary-30000-2026",
                unsafe=True,
            ).replace("<script>", "<script>legacy-").replace(smoke.GA_ID, ""),
        }
        low = readiness.evaluate(
            src,
            repo=root,
            live_pages=live_pages,
            live_manifest=None,
            checked_on=date(2026, 8, 16),
        )
        check("reachable but stale unsafe live fixture scores exactly 20",
              low["score_descriptive"] == 20)
        check("exact release remains a hard blocker", "exact_release" in low["hard_blockers"])
        check("attribution remains a hard blocker", "attribution" in low["hard_blockers"])
        check("offer safety remains a hard blocker", "offer_safety" in low["hard_blockers"])
        check("pilot cannot earn points before prerequisites pass",
              low["categories"]["bounded_pilot"]["status"] != "PASS")

        manifest = json.loads((src / release_contract.MANIFEST_NAME).read_text())
        check("fresh schema-v2 manifest matches", not release_contract.manifest_findings(
            manifest, src, root
        ))
        source = root / "tools" / "postdeploy_smoke.py"
        source.write_text("changed", encoding="utf-8")
        check("changed gate invalidates source provenance",
              "provenance differs" in release_contract.manifest_findings(
                  manifest, src, root
              )[0])

        local_pages = smoke.pages_local(str(src))
        missing_measurement = readiness.measurement_support_findings(
            pilot(), root, local_pages
        )
        check("missing session operands and dimensions block measurement support",
              any("session-scoped" in value for value in missing_measurement) and
              any("not materialized" in value for value in missing_measurement))
        measurement = pilot()["measurement_contract"]
        producer_contract = {
            "contract_version": 1,
            "primary_metric": measurement["primary_metric"],
            "fields": measurement["required_fields"],
            "dimensions": measurement["required_dimensions"],
            "scopes": measurement["required_scopes"],
            "output_file": "automation-log/ga4-pilot-sessions.csv",
            "snapshot": {
                "schema_version": 3,
                "file_key": "pilot_sessions",
                "query_coverage_keys": [
                    "pilot_affiliate_sessions", "pilot_qualified_landings"
                ],
                "hash_binding_required": True,
                "pagination_completeness_required": True,
            },
            "queries": {
                "affiliate_click_sessions": {
                    "metric": "sessions",
                    "dimensions": [
                        "eventName", "pagePath", "landingPagePlusQueryString",
                        "sessionManualAdContent",
                        *("customEvent:" + name
                          for name in measurement["required_dimensions"]),
                    ],
                },
                "qualified_landing_sessions": {
                    "metric": "sessions",
                    "dimensions": [
                        "landingPagePlusQueryString", "sessionManualAdContent"
                    ],
                },
            },
            "target": {
                **pilot()["target"],
                "sub_id": "website_salary30k-lower_ktccard",
                "channel": "website",
                "campaign": "ktccard",
            },
        }
        schema_contract = {
            "contract_version": 1,
            "primary_metric": measurement["primary_metric"],
            "fields": measurement["required_fields"],
            "dimensions": measurement["required_dimensions"],
            "scopes": measurement["required_scopes"],
            "field_order": [
                *measurement["required_dimensions"],
                *measurement["required_fields"],
                "measurement_scope",
            ],
            "measurement_scope": "session",
            "constraints": {
                "unique_dimension_tuple": True,
                "affiliate_click_sessions_lte_qualified_landing_sessions": True,
                "nonnegative_integer_operands": True,
                "canonical_dimensions": True,
            },
        }
        (root / "pipeline" / "ga4_pull.py").write_text(
            "PILOT_MEASUREMENT_CONTRACT = " + repr(producer_contract), encoding="utf-8"
        )
        (root / "pipeline" / "ga4_schema.py").write_text(
            "PILOT_MEASUREMENT_FIELDS = " + repr(schema_contract), encoding="utf-8"
        )
        check("literal producer and schema contracts can satisfy measurement support",
              not readiness.measurement_support_findings(
                  pilot(), root, local_pages
              ))
        producer_contract["snapshot"]["hash_binding_required"] = False
        (root / "pipeline" / "ga4_pull.py").write_text(
            "PILOT_MEASUREMENT_CONTRACT = " + repr(producer_contract), encoding="utf-8"
        )
        check("missing hash binding fails measurement support closed",
              any("hash/coverage" in value for value in
                  readiness.measurement_support_findings(
                      pilot(), root, local_pages
                  )))
        producer_contract["snapshot"]["hash_binding_required"] = True
        (root / "pipeline" / "ga4_pull.py").write_text(
            "PILOT_MEASUREMENT_CONTRACT = " + repr(producer_contract), encoding="utf-8"
        )
        (src / release_contract.MANIFEST_NAME).write_text(
            json.dumps(release_contract.manifest_for(src, root)), encoding="utf-8"
        )
        supported = readiness.evaluate(
            src, repo=root, checked_on=date(2026, 8, 16)
        )
        check("supported measurement is recognized",
              supported["pilot"]["measurement_contract_supported"] is True)
        check("supported measurement remains blocked",
              supported["categories"]["bounded_pilot"]["status"] == "BLOCKED")
        check("supported measurement cannot increase the descriptive score",
              supported["score_descriptive"] <= 80)
        blocked_findings = supported["categories"]["bounded_pilot"]["findings"]
        check("supported measurement still requires trusted analytics",
              any("TRUSTED" in value for value in blocked_findings))
        check("supported measurement still requires placement receipt",
              any("receipt" in value for value in blocked_findings))
        check("supported measurement still requires separate authority",
              any("authority" in value for value in blocked_findings))

        unsafe_pages = {
            "credit-card-salary-30000-2026.html": page(
                "https://ngernduangold.com/credit-card-salary-30000-2026",
                target=True,
                unsafe=True,
            )
        }
        policy = json.loads((root / ".system_control" / "policy.json").read_text())
        unsafe = readiness._own_offer_findings(unsafe_pages, policy, root)
        check("unbound LINE and checkout paths fail offer safety",
              any("data-note" in value for value in unsafe) and
              any("checkout" in value for value in unsafe))

        bad_pilot = copy.deepcopy(pilot())
        bad_pilot["external_action_authorized"] = True
        products = json.loads(
            (root / ".system_control" / "merchant_offers.json").read_text()
        )["products"]
        bad = readiness.pilot_findings(bad_pilot, smoke.pages_local(str(src)), products)
        check("pilot contract cannot authorize external action",
              any("must not authorize" in value for value in bad))
        hard_target = copy.deepcopy(pilot())
        hard_target["design"]["success_threshold"] = 0.08
        hard_target_findings = readiness.pilot_findings(
            hard_target, smoke.pages_local(str(src)), products
        )
        check("unqualified 8 percent hard target is rejected",
              any("qualified provisional" in value for value in hard_target_findings))
        winner = copy.deepcopy(pilot())
        winner["design"]["winner_declaration_allowed"] = True
        winner_findings = readiness.pilot_findings(
            winner, smoke.pages_local(str(src)), products
        )
        check("pilot cannot declare a winner or authorize scale",
              any("winner declaration" in value for value in winner_findings))
        check("funnel JSON cannot overwrite candidate-bound acceptance evidence",
              _report_path_fails(
                  "release/PREDEPLOY-ACCEPTANCE.md", root, "must not overwrite"
              ))
        check("funnel report rejects a misleading non-JSON extension",
              _report_path_fails(
                  "release/another-report.md", root, "must use a .json"
              ))
        check("funnel JSON uses a separate canonical path",
              readiness._json_report_path(
                  str(readiness.FUNNEL_REPORT_PATH), root
              ) == (root / readiness.FUNNEL_REPORT_PATH).resolve())
    print("release/funnel readiness: 28/28 PASS")


if __name__ == "__main__":
    run()
