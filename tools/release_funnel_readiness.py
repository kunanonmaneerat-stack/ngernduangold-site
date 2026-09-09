#!/usr/bin/env python3
"""Describe release/funnel readiness without authorizing deploys or traffic.

The score is explanatory only.  Exact-release, attribution, and offer-safety
failures are hard blockers regardless of the aggregate number.  The bounded
pilot contract is deliberately non-authorizing and cannot publish or click.
"""

from __future__ import annotations

import argparse
import ast
from datetime import date, datetime, timezone
from html import unescape
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlsplit

try:
    import merchant_offer_gate as merchant_gate
    import postdeploy_smoke as smoke
    from release_contract import load_pilot
except ModuleNotFoundError:  # package import used by focused tests
    from tools import merchant_offer_gate as merchant_gate
    from tools import postdeploy_smoke as smoke
    from tools.release_contract import load_pilot


ROOT = Path(__file__).resolve().parents[1]
PREDEPLOY_ACCEPTANCE_PATH = Path("release/PREDEPLOY-ACCEPTANCE.md")
FUNNEL_REPORT_PATH = Path("release/RELEASE-FUNNEL-READINESS.json")
CATEGORY_ORDER = (
    "inventory",
    "exact_release",
    "attribution",
    "offer_safety",
    "bounded_pilot",
)
CATEGORY_WEIGHT = 20
HARD_BLOCKER_CATEGORIES = {
    "inventory",
    "exact_release",
    "attribution",
    "offer_safety",
}
ATTRIBUTION_PREFIXES = (
    "\u0e44\u0e21\u0e48\u0e1e\u0e1a GA4",
    "event taxonomy missing:",
    "affiliate disclosure",
    "own-product CTA is classified as affiliate:",
    "\u0e1b\u0e38\u0e48\u0e21 ",
    "sub_id",
)
TRANSACTION_RE = re.compile(
    r"(?:\u0e2a\u0e31\u0e48\u0e07|\u0e0b\u0e37\u0e49\u0e2d|\u0e42\u0e2d\u0e19|"
    r"\u0e1e\u0e23\u0e49\u0e2d\u0e21\u0e40\u0e1e\u0e22\u0e4c|"
    r"\u0e2a\u0e48\u0e07\u0e2a\u0e25\u0e34\u0e1b|(?:59|199)\s*\u0e3f)",
    re.I,
)
CHECKOUT_HOST_SUFFIXES = ("gumroad.com",)
REQUIRED_ATTRIBUTION_DIMENSIONS = {
    "provider",
    "cta_id",
    "position",
    "content_id",
    "acquisition_content_id",
    "sub_id",
    "channel",
    "campaign",
}
REQUIRED_PILOT_STOPS = {
    "exact_release_drift",
    "attribution_contract_failure",
    "offer_safety_failure",
    "merchant_inactive_or_content_mismatch",
    "official_source_review_required",
    "analytics_trust_not_trusted",
    "page_offer_or_cta_changed",
}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key: " + key)
            value[key] = item
        return value

    def require_finite(item: Any) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    try:
        if path.is_symlink():
            raise ValueError(label + " must not be a symlink")
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or len(raw) != after.st_size:
            raise ValueError(label + " changed while being read")
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
        require_finite(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(label + " is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(label + " must be an object")
    return payload


def _literal_mapping(path: Path, symbol: str) -> tuple[dict[str, Any] | None, str | None]:
    """Read a literal contract declaration without importing operational code."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return None, "unreadable: " + str(exc)
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == symbol
                   for target in node.targets):
                value = node.value
        elif (isinstance(node, ast.AnnAssign)
              and isinstance(node.target, ast.Name)
              and node.target.id == symbol):
            value = node.value
        if value is None:
            continue
        try:
            payload = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError):
            return None, "is not a literal mapping"
        if not isinstance(payload, dict):
            return None, "is not a literal mapping"
        return payload, None
    return None, "is absent"


def _markup(html: str) -> str:
    return re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.I | re.S)


def inventory_findings(pages: dict[str, str], live: bool) -> list[str]:
    findings: list[str] = []
    if not pages:
        return ["published inventory is empty"]
    owners: dict[str, str] = {}
    for name, html in pages.items():
        if html.startswith("__FETCH_FAIL__"):
            findings.append(str(name) + ": page fetch failed")
            continue
        canonical = smoke._canonical(html)
        if not canonical:
            findings.append(str(name) + ": canonical is missing")
            continue
        try:
            parsed = urlsplit(canonical)
        except ValueError:
            parsed = None
        if (
            parsed is None
            or parsed.scheme != "https"
            or parsed.hostname != "ngernduangold.com"
            or parsed.query
            or parsed.fragment
        ):
            findings.append(str(name) + ": canonical host/shape is invalid")
        if live and canonical.rstrip("/") != str(name).rstrip("/"):
            findings.append(str(name) + ": canonical is not the fetched URL")
        if canonical in owners:
            findings.append(str(name) + ": duplicate canonical also used by " + owners[canonical])
        else:
            owners[canonical] = str(name)
    return findings


def attribution_findings(
    pages: dict[str, str], products: dict[str, Any], live: bool
) -> list[str]:
    findings: list[str] = []
    for name, html in pages.items():
        if html.startswith("__FETCH_FAIL__"):
            findings.append(str(name) + ": cannot verify attribution on an unfetched page")
            continue
        expected = str(name) if live else smoke._canonical(html)
        _buttons, page_findings = smoke.check_page(
            html, products=products, expected_url=expected
        )
        for finding in page_findings:
            if finding.startswith(ATTRIBUTION_PREFIXES):
                findings.append(str(name) + ": " + finding)
    return findings


def _own_offer_findings(
    pages: dict[str, str], policy: dict[str, Any], repo: Path
) -> list[str]:
    findings: list[str] = []
    raw_items = ((policy.get("products") or {}).get("items"))
    if not isinstance(raw_items, list) or not raw_items:
        return ["own-product policy has no product items"]
    products: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            findings.append("own-product row %d is not an object" % index)
            continue
        product_id = item.get("id")
        if not isinstance(product_id, str) or not product_id.strip():
            findings.append("own-product row %d has no id" % index)
            continue
        if product_id in products:
            findings.append("duplicate own-product id: " + product_id)
            continue
        if not isinstance(item.get("promotion_authorized"), bool):
            findings.append(product_id + ": promotion_authorized is not boolean")
        products[product_id] = item

    seen_intents: dict[str, list[str]] = {}
    for name, html in pages.items():
        if html.startswith("__FETCH_FAIL__"):
            continue
        markup = _markup(html)
        for tag in re.findall(r"<[^>]+\bdata-buy\s*=\s*[\"'][^\"']+[\"'][^>]*>", markup, re.I):
            attrs = smoke._attrs(tag)
            product_id = attrs.get("data-buy", "")
            seen_intents.setdefault(product_id, []).append(str(name))
            item = products.get(product_id)
            if item is None:
                findings.append(str(name) + ": undeclared data-buy " + product_id)
            elif item.get("promotion_authorized") is not True:
                findings.append(str(name) + ": unauthorized data-buy " + product_id)

        for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", markup, re.I | re.S):
            tag = "<a" + match.group(1) + ">"
            attrs = smoke._attrs(tag)
            href = unescape(attrs.get("href", ""))
            product_id = attrs.get("data-buy", "")
            if "data-note" in attrs:
                findings.append(str(name) + ": unbound data-note purchase intent")
            try:
                host = (urlsplit(href).hostname or "").lower()
            except ValueError:
                host = ""
            checkout = any(host == suffix or host.endswith("." + suffix)
                           for suffix in CHECKOUT_HOST_SUFFIXES)
            if checkout and not product_id:
                findings.append(str(name) + ": checkout link has no stable data-buy id")
            text = re.sub(r"<[^>]+>", " ", unescape(match.group(2)))
            combined = " ".join((text, " ".join(attrs.values())))
            if host == "line.me" and TRANSACTION_RE.search(combined) and not product_id:
                findings.append(str(name) + ": transactional LINE CTA has no data-buy id")

    for product_id, item in products.items():
        if item.get("promotion_authorized") is not True:
            continue
        deliverable = item.get("deliverable")
        if not isinstance(deliverable, str) or not deliverable.strip():
            findings.append(product_id + ": authorized product has no deliverable")
        elif not deliverable.startswith(("gumroad:", "https://")):
            path = repo / deliverable
            if not path.is_file() or path.stat().st_size < 10 * 1024:
                findings.append(product_id + ": authorized deliverable is absent or placeholder-sized")
        if product_id not in seen_intents:
            findings.append(product_id + ": authorized product has no bound public CTA")
    return findings


def offer_findings(
    pages: dict[str, str], repo: Path, checked_on: date
) -> tuple[list[str], dict[str, Any]]:
    registry_path = repo / ".system_control" / "merchant_offers.json"
    policy_path = repo / ".system_control" / "policy.json"
    try:
        registry = merchant_gate.load_registry(registry_path)
        policy = _read_json(policy_path, "own-product policy")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return ["offer controls unavailable: " + str(exc)], {}
    findings = merchant_gate.evaluate(registry, pages, checked_on)
    findings.extend(_own_offer_findings(pages, policy, repo))
    return findings, registry.get("products", {})


def measurement_contract_definition_findings(pilot: dict[str, Any]) -> list[str]:
    """Validate the requested measurement shape, not whether it exists yet."""
    findings: list[str] = []
    contract = pilot.get("measurement_contract")
    if not isinstance(contract, dict):
        return ["pilot measurement_contract is missing"]
    expected_strings = {
        "producer_path": "pipeline/ga4_pull.py",
        "schema_adapter_path": "pipeline/ga4_schema.py",
        "producer_contract_symbol": "PILOT_MEASUREMENT_CONTRACT",
        "schema_fields_symbol": "PILOT_MEASUREMENT_FIELDS",
        "primary_metric": "affiliate_click_sessions / qualified_landing_sessions",
    }
    if contract.get("contract_version") != 1:
        findings.append("pilot measurement contract_version must be 1")
    for field, expected in expected_strings.items():
        if contract.get(field) != expected:
            findings.append("pilot measurement_contract.%s must be %s" % (field, expected))
    required_fields = set(contract.get("required_fields") or [])
    if required_fields != {"affiliate_click_sessions", "qualified_landing_sessions"}:
        findings.append("pilot measurement fields must be the two session-scoped operands")
    dimensions = set(contract.get("required_dimensions") or [])
    if not REQUIRED_ATTRIBUTION_DIMENSIONS.issubset(dimensions):
        findings.append("pilot measurement dimensions are incomplete")
    scopes = contract.get("required_scopes")
    if scopes != {
        "affiliate_click_sessions": "session",
        "qualified_landing_sessions": "session",
    }:
        findings.append("pilot measurement operands must both be session scoped")
    definition = contract.get("qualified_landing_session_definition")
    if not isinstance(definition, str) or not definition.strip():
        findings.append("qualified_landing_session definition is missing")
    return findings


def _materialized_pilot_target(
    pilot: dict[str, Any], pages: dict[str, str] | None
) -> tuple[dict[str, str] | None, str | None]:
    target = pilot.get("target")
    if not isinstance(target, dict) or not isinstance(pages, dict):
        return None, "audited pilot target page is unavailable"
    canonical = target.get("canonical_url")
    html = next(
        (value for value in pages.values() if smoke._canonical(value) == canonical),
        None,
    )
    if not isinstance(html, str):
        return None, "audited pilot target page is unavailable"
    matches = []
    for tag in re.findall(r"<a\b[^>]*>", _markup(html), re.I):
        attrs = smoke._attrs(tag)
        if attrs.get("data-cta-id") == target.get("cta_id"):
            matches.append(attrs)
    if len(matches) != 1:
        return None, "audited pilot CTA must occur exactly once"
    attrs = matches[0]
    try:
        parsed = urlsplit(unescape(attrs.get("href", "")))
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None, "audited pilot CTA URL is invalid"

    def one(name: str) -> str | None:
        values = query.get(name)
        if not isinstance(values, list) or len(values) != 1 or not values[0]:
            return None
        return values[0]

    derived = {
        "canonical_url": str(canonical or ""),
        "page_file": str(target.get("page_file") or ""),
        "primary_event": str(target.get("primary_event") or ""),
        "provider": str(attrs.get("data-provider") or ""),
        "cta_id": str(attrs.get("data-cta-id") or ""),
        "position": str(attrs.get("data-pos") or ""),
        "content_id": str(attrs.get("data-content-id") or ""),
        "sub_id": str(one("utm_content") or ""),
        "channel": str(one("utm_source") or ""),
        "campaign": str(one("utm_campaign") or ""),
    }
    if any(not value for value in derived.values()):
        return None, "audited pilot CTA dimensions are incomplete"
    return derived, None


def measurement_support_findings(
    pilot: dict[str, Any], repo: Path, pages: dict[str, str] | None = None
) -> list[str]:
    """Fail closed until the actual producer and schema expose literal support."""
    contract = pilot.get("measurement_contract")
    if not isinstance(contract, dict):
        return ["measurement support cannot be evaluated without a valid contract"]
    producer_path = repo / str(contract.get("producer_path", ""))
    schema_path = repo / str(contract.get("schema_adapter_path", ""))
    producer_symbol = str(contract.get("producer_contract_symbol", ""))
    schema_symbol = str(contract.get("schema_fields_symbol", ""))
    producer, producer_error = _literal_mapping(producer_path, producer_symbol)
    schema, schema_error = _literal_mapping(schema_path, schema_symbol)
    findings: list[str] = []
    if producer_error:
        findings.append(
            "measurement producer %s %s; session-scoped pilot numerator/denominator are unsupported"
            % (producer_symbol or "contract", producer_error)
        )
    if schema_error:
        findings.append(
            "measurement schema %s %s; pilot fields/dimensions are not materialized"
            % (schema_symbol or "contract", schema_error)
        )
    if producer_error or schema_error:
        return findings

    required_fields = set(contract.get("required_fields") or [])
    required_dimensions = set(contract.get("required_dimensions") or [])
    required_scopes = contract.get("required_scopes")
    expected_version = contract.get("contract_version")
    expected_metric = contract.get("primary_metric")
    if producer.get("contract_version") != expected_version:
        findings.append("measurement producer contract version does not match the pilot")
    if producer.get("primary_metric") != expected_metric:
        findings.append("measurement producer primary metric does not match the pilot")
    if set(producer.get("fields") or []) != required_fields:
        findings.append("measurement producer is missing required session fields")
    if set(producer.get("dimensions") or []) != required_dimensions:
        findings.append("measurement producer is missing required attribution dimensions")
    if producer.get("scopes") != required_scopes:
        findings.append("measurement producer does not declare both operands as session scoped")
    if schema.get("contract_version") != expected_version:
        findings.append("measurement schema contract version does not match the pilot")
    if schema.get("primary_metric") != expected_metric:
        findings.append("measurement schema primary metric does not match the pilot")
    if set(schema.get("fields") or []) != required_fields:
        findings.append("measurement schema does not expose required session fields")
    if set(schema.get("dimensions") or []) != required_dimensions:
        findings.append("measurement schema does not expose required attribution dimensions")
    if schema.get("scopes") != required_scopes:
        findings.append("measurement schema does not preserve session operand scopes")

    snapshot = producer.get("snapshot")
    expected_coverage = {
        "pilot_affiliate_sessions", "pilot_qualified_landings"
    }
    if producer.get("output_file") != "automation-log/ga4-pilot-sessions.csv":
        findings.append("measurement producer output is not the canonical pilot table")
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema_version") != 3
        or snapshot.get("file_key") != "pilot_sessions"
        or set(snapshot.get("query_coverage_keys") or []) != expected_coverage
        or snapshot.get("hash_binding_required") is not True
        or snapshot.get("pagination_completeness_required") is not True
    ):
        findings.append("measurement producer lacks schema-3 hash/coverage binding")
    queries = producer.get("queries")
    affiliate_query = queries.get("affiliate_click_sessions") if isinstance(queries, dict) else None
    landing_query = queries.get("qualified_landing_sessions") if isinstance(queries, dict) else None
    expected_event_dimensions = {
        "eventName", "pagePath", "landingPagePlusQueryString",
        "sessionManualAdContent",
        *("customEvent:" + name for name in required_dimensions),
    }
    if (
        not isinstance(affiliate_query, dict)
        or affiliate_query.get("metric") != "sessions"
        or set(affiliate_query.get("dimensions") or []) != expected_event_dimensions
        or not isinstance(landing_query, dict)
        or landing_query.get("metric") != "sessions"
        or set(landing_query.get("dimensions") or [])
        != {"landingPagePlusQueryString", "sessionManualAdContent"}
    ):
        findings.append("measurement producer queries are not exact session-scoped operands")
    expected_order = [
        *contract.get("required_dimensions", []),
        *contract.get("required_fields", []),
        "measurement_scope",
    ]
    constraints = schema.get("constraints")
    if (
        schema.get("field_order") != expected_order
        or schema.get("measurement_scope") != "session"
        or not isinstance(constraints, dict)
        or constraints.get("unique_dimension_tuple") is not True
        or constraints.get(
            "affiliate_click_sessions_lte_qualified_landing_sessions"
        ) is not True
        or constraints.get("nonnegative_integer_operands") is not True
        or constraints.get("canonical_dimensions") is not True
    ):
        findings.append("measurement schema lacks fail-closed row constraints")
    materialized_target, target_error = _materialized_pilot_target(pilot, pages)
    if target_error:
        findings.append(target_error)
    elif producer.get("target") != materialized_target:
        findings.append("measurement producer target does not match the audited CTA")
    return findings


def pilot_findings(
    pilot: dict[str, Any], pages: dict[str, str], products: dict[str, Any]
) -> list[str]:
    findings: list[str] = []
    if pilot.get("schema_version") != 2:
        findings.append("pilot schema_version must be 2")
    if pilot.get("state") != "planned_blocked":
        findings.append("pilot state must remain planned_blocked")
    if pilot.get("external_action_authorized") is not False:
        findings.append("pilot must not authorize external action")
    pilot_id = pilot.get("pilot_id")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        findings.append("pilot_id is missing")

    target = pilot.get("target")
    if not isinstance(target, dict):
        return findings + ["pilot target is missing"]
    required_target = (
        "canonical_url",
        "page_file",
        "content_id",
        "provider",
        "cta_id",
        "position",
        "primary_event",
    )
    for field in required_target:
        if not isinstance(target.get(field), str) or not target[field].strip():
            findings.append("pilot target.%s is missing" % field)
    if target.get("primary_event") != "affiliate_click":
        findings.append("pilot primary event must be affiliate_click")
    provider = products.get(target.get("provider"))
    if not isinstance(provider, dict) or provider.get("availability") != "active":
        findings.append("pilot provider is not active in the merchant registry")
    elif target.get("content_id") not in provider.get("allowed_content_ids", []):
        findings.append("pilot provider is not approved for the target content")

    selected_html = None
    for name, html in pages.items():
        if str(name) == target.get("page_file") or smoke._canonical(html) == target.get("canonical_url"):
            if selected_html is not None:
                findings.append("pilot target resolves to more than one page")
            selected_html = html
    if selected_html is None:
        findings.append("pilot target page is absent")
    else:
        tags = []
        for tag in re.findall(r"<a\b[^>]*>", _markup(selected_html), re.I):
            attrs = smoke._attrs(tag)
            if attrs.get("data-cta-id") == target.get("cta_id"):
                tags.append((attrs, unescape(attrs.get("href", ""))))
        if len(tags) != 1:
            findings.append("pilot must bind exactly one target CTA")
        else:
            attrs, href = tags[0]
            for attr, field in (
                ("data-provider", "provider"),
                ("data-content-id", "content_id"),
                ("data-pos", "position"),
            ):
                if attrs.get(attr) != target.get(field):
                    findings.append("pilot CTA %s does not match target.%s" % (attr, field))
            tracked, _atth, _go = smoke._affiliate_traits(
                href, set(attrs.get("rel", "").lower().split())
            )
            if not tracked:
                findings.append("pilot CTA is not classified as an affiliate path")

    design = pilot.get("design")
    if not isinstance(design, dict):
        findings.append("pilot design is missing")
    else:
        minimum = design.get("minimum_qualified_sessions")
        maximum = design.get("maximum_qualified_sessions")
        duration = design.get("maximum_duration_days")
        threshold = design.get("success_threshold")
        if not isinstance(minimum, int) or minimum < 50:
            findings.append("pilot minimum sample must be at least 50 qualified sessions")
        if not isinstance(maximum, int) or not isinstance(minimum, int) or maximum < minimum:
            findings.append("pilot maximum sample must not be below its minimum")
        if not isinstance(duration, int) or not 1 <= duration <= 30:
            findings.append("pilot duration must be from 1 to 30 days")
        if not isinstance(threshold, dict):
            findings.append("pilot success_threshold must be a qualified provisional assumption")
        else:
            value = threshold.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < value <= 1:
                findings.append("pilot provisional threshold value must be a rate from 0 to 1")
            if threshold.get("status") != "provisional_planning_assumption":
                findings.append("pilot threshold must be labeled provisional_planning_assumption")
            if threshold.get("confidence") != "low":
                findings.append("pilot threshold confidence must remain low before a trusted baseline")
            if threshold.get("trusted_historical_baseline_available") is not False:
                findings.append("pilot must not claim a trusted historical baseline")
            if threshold.get("reset_after_first_trusted_baseline") is not True:
                findings.append("pilot threshold must reset after the first trusted baseline")
            rationale = threshold.get("rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                findings.append("pilot provisional threshold rationale is missing")
        if design.get("maximum_cta_variants") != 1:
            findings.append("pilot must hold exactly one CTA variant")
        if design.get("freeze_page_offer_and_cta_during_window") is not True:
            findings.append("pilot must freeze its page, offer, and CTA")
        if design.get("clicks_do_not_prove_revenue") is not True:
            findings.append("pilot must state that clicks do not prove revenue")
        if design.get("outcome_classification") != "directional_only":
            findings.append("pilot outcomes must remain directional_only")
        if design.get("winner_declaration_allowed") is not False:
            findings.append("pilot must not allow a winner declaration")
        if design.get("scale_decision_allowed") is not False:
            findings.append("pilot must not allow a scale decision")
        if not isinstance(design.get("decision_rule"), str) or not design["decision_rule"].strip():
            findings.append("pilot decision_rule is missing")
        if design.get("primary_metric") != "affiliate_click_sessions / qualified_landing_sessions":
            findings.append("pilot primary metric must use session-scoped numerator and denominator")

    prerequisites = pilot.get("prerequisites")
    if not isinstance(prerequisites, dict):
        findings.append("pilot prerequisites are missing")
    else:
        required = set(prerequisites.get("required_categories") or [])
        if required != {"inventory", "exact_release", "attribution", "offer_safety"}:
            findings.append("pilot required_categories are incomplete")
        if prerequisites.get("minimum_live_readiness_score") != 80:
            findings.append("pilot minimum live readiness score must be 80")
        if prerequisites.get("analytics_trust") != "TRUSTED":
            findings.append("pilot analytics trust prerequisite must be TRUSTED")
        if prerequisites.get("measurement_contract_support") != "REQUIRED":
            findings.append("pilot must require measurement contract support")
        if prerequisites.get("publishable_placement_receipt") != "REQUIRED":
            findings.append("pilot must require a publishable placement receipt")
        if prerequisites.get("owner_execution_authority") != "REQUIRED_SEPARATELY":
            findings.append("pilot must require separate owner execution authority")
        if prerequisites.get("exact_release_lock") is not True:
            findings.append("pilot must require an exact release lock")

    dimensions = set(pilot.get("attribution_dimensions") or [])
    if not REQUIRED_ATTRIBUTION_DIMENSIONS.issubset(dimensions):
        findings.append("pilot attribution dimensions are incomplete")
    stops = set(pilot.get("stop_conditions") or [])
    if not REQUIRED_PILOT_STOPS.issubset(stops):
        findings.append("pilot stop conditions are incomplete")
    findings.extend(measurement_contract_definition_findings(pilot))
    return findings


def evaluate(
    src: Path | str,
    *,
    repo: Path | str = ROOT,
    live_pages: dict[str, str] | None = None,
    live_manifest: object = None,
    checked_on: date | None = None,
) -> dict[str, Any]:
    selected_repo = Path(repo).resolve()
    selected_src = Path(src).resolve()
    checked_on = checked_on or date.today()
    local_pages = smoke.pages_local(str(selected_src))
    is_live = live_pages is not None
    pages = live_pages if is_live else local_pages

    categories: dict[str, dict[str, Any]] = {}
    inventory = inventory_findings(pages, is_live)
    categories["inventory"] = {"status": "FAIL" if inventory else "PASS", "findings": inventory}

    try:
        local_manifest = _read_json(
            selected_src / "release-manifest.json", "local release manifest"
        )
    except ValueError as exc:
        local_manifest = None
        local_manifest_findings = [str(exc)]
    else:
        local_manifest_findings = smoke.compare_release_manifest(
            local_manifest, str(selected_src), str(selected_repo)
        )
    release = list(local_manifest_findings)
    release.extend(smoke.local_build_freshness(str(selected_src), str(selected_repo)))
    if is_live:
        drift = smoke.compare_release_pages(pages, local_pages)
        for name, values in drift.items():
            release.extend(str(name) + ": " + value for value in values)
        release.extend(
            smoke.compare_release_manifest(
                live_manifest, str(selected_src), str(selected_repo)
            )
        )
    categories["exact_release"] = {
        "status": "FAIL" if release else "PASS",
        "findings": release,
    }

    offer, products = offer_findings(pages, selected_repo, checked_on)
    attribution = attribution_findings(pages, products, is_live)
    categories["attribution"] = {
        "status": "FAIL" if attribution else "PASS",
        "findings": attribution,
    }
    categories["offer_safety"] = {
        "status": "FAIL" if offer else "PASS",
        "findings": offer,
    }

    try:
        pilot = load_pilot(selected_repo)
    except ValueError as exc:
        pilot = {}
        pilot_contract = [str(exc)]
    else:
        # The pilot design binds to the audited local candidate. Production
        # mismatch belongs to exact_release, not to the JSON contract itself.
        pilot_contract = pilot_findings(pilot, local_pages, products)
    prerequisite_failures = [
        name
        for name in ("inventory", "exact_release", "attribution", "offer_safety")
        if categories[name]["status"] != "PASS"
    ]
    measurement_findings = (
        [] if pilot_contract else measurement_support_findings(
            pilot, selected_repo, local_pages
        )
    )
    operational_reasons = [
        *("blocked by release prerequisite: " + name for name in prerequisite_failures),
        *measurement_findings,
        "analytics TRUSTED evidence is not verified by this release-only guard",
        "publishable placement receipt is not supplied or verified",
        "separate owner execution authority is not granted by this report",
    ]
    if pilot_contract:
        pilot_status = "FAIL"
        pilot_reasons = pilot_contract
    else:
        # A valid pilot plan is deliberately still non-operational. This tool
        # has no calendar/receipt/owner-authority inputs and therefore cannot
        # emit PASS/GO for execution.
        pilot_status = "BLOCKED"
        pilot_reasons = operational_reasons
    categories["bounded_pilot"] = {
        "status": pilot_status,
        "findings": pilot_reasons,
        "contract_valid": not pilot_contract,
        "measurement_contract_supported": not pilot_contract and not measurement_findings,
        "semantics": "design_contract_only_not_operational_authority",
    }

    for name in CATEGORY_ORDER:
        categories[name]["weight"] = CATEGORY_WEIGHT
    score = sum(
        value["weight"] for value in categories.values() if value["status"] == "PASS"
    )
    hard_blockers = [
        name
        for name in CATEGORY_ORDER
        if name in HARD_BLOCKER_CATEGORIES and categories[name]["status"] != "PASS"
    ]
    external_requested = pilot.get("external_action_authorized") is True
    release_contract_blocked = bool(hard_blockers or pilot_contract)
    return {
        "schema_version": 1,
        "mode": "live" if is_live else "local",
        "assessment_scope": "release_funnel_contract_only",
        "score_descriptive": score,
        "score_max": 100,
        "score_is_authorization": False,
        "external_action_authorization_requested": external_requested,
        "external_action_authorized": False,
        "publication_authority_granted": False,
        "release_contract_status": "BLOCKED" if release_contract_blocked else "PASS",
        "hard_blocked": bool(hard_blockers),
        "hard_blockers": hard_blockers,
        "categories": categories,
        "publication": {
            "status": "NOT_AUTHORIZED",
            "calendar_publishable_count_evaluated": False,
            "publishable_placement_receipt_verified": False,
            "authority_granted": False,
        },
        "operational_pilot_eligibility": {
            "status": "BLOCKED",
            "reasons": pilot_reasons,
            "eligibility_is_authorization": False,
        },
        "release": {
            "local_manifest_schema": (
                local_manifest.get("schema_version") if isinstance(local_manifest, dict) else None
            ),
            "local_release_id": (
                local_manifest.get("release_id") if isinstance(local_manifest, dict) else None
            ),
            "live_release_id": (
                live_manifest.get("release_id") if isinstance(live_manifest, dict) else None
            ),
        },
        "pilot": {
            "pilot_id": pilot.get("pilot_id"),
            "state": pilot.get("state"),
            "design_contract_valid": not pilot_contract,
            "release_category_prerequisites_met": not prerequisite_failures,
            "measurement_contract_supported": not pilot_contract and not measurement_findings,
            "operational_eligibility": "BLOCKED",
            "external_action_authorization_requested": external_requested,
            "external_action_authorized": False,
        },
        "conditions_for_80_plus": [
            "80 points requires all four hard-blocker categories to pass; no aggregate score can waive any one",
            "inventory: every sitemap page fetches and has one unique self-canonical HTTPS URL",
            "exact_release: production canonical set, normalized HTML, aggregate tree, source/gate hashes, and pilot hash exactly match the audited local release",
            "attribution: every live page carries the scoped event taxonomy and every affiliate CTA has exact rel, provider, content, position, and sub-id metadata",
            "offer_safety: merchant/content fit passes and no unauthorized, unbound, or undeliverable own-product purchase path is live",
            "bounded_pilot remains BLOCKED until the producer/schema support session-scoped operands and trusted analytics, placement receipt, and separate owner authority are verified",
        ],
    }


def _print_human(report: dict[str, Any]) -> None:
    print(
        "release/funnel readiness [%s]: %d/%d (DESCRIPTIVE ONLY)"
        % (report["mode"].upper(), report["score_descriptive"], report["score_max"])
    )
    for name in CATEGORY_ORDER:
        row = report["categories"][name]
        print("  %-16s %s (%d)" % (name, row["status"], row["weight"]))
        for finding in row["findings"][:3]:
            print("    - " + finding)
        if len(row["findings"]) > 3:
            print("    - ... %d more" % (len(row["findings"]) - 3))
    print("hard blockers: " + (", ".join(report["hard_blockers"]) or "none"))
    print("assessment scope: RELEASE/FUNNEL CONTRACT ONLY")
    print("publication authority: NOT AUTHORIZED")
    print("operational pilot eligibility: BLOCKED")


def _json_report_path(raw: str, repo: Path) -> Path:
    """Resolve a JSON output without allowing it to clobber acceptance evidence."""
    selected = Path(raw)
    if not selected.is_absolute():
        selected = repo / selected
    selected = selected.resolve()
    reserved = (repo / PREDEPLOY_ACCEPTANCE_PATH).resolve()
    if selected == reserved:
        raise ValueError(
            "release/funnel JSON must not overwrite the candidate-bound "
            "PREDEPLOY-ACCEPTANCE.md"
        )
    if selected.suffix.casefold() != ".json":
        raise ValueError("release/funnel report output must use a .json path")
    return selected


def _atomic_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--require-local-ready", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if args.require_local_ready and args.live:
        print("--require-local-ready cannot be combined with --live", file=sys.stderr)
        return 2
    report_path = None
    if args.report:
        try:
            report_path = _json_report_path(args.report, repo)
        except ValueError as exc:
            print("release/funnel report unavailable: " + str(exc), file=sys.stderr)
            return 2
    try:
        pages = smoke.pages_live() if args.live else None
        manifest = smoke.fetch_release_manifest() if args.live else None
        report = evaluate(
            args.src,
            repo=args.repo,
            live_pages=pages,
            live_manifest=manifest,
        )
    except Exception as exc:
        print("release/funnel readiness unavailable: " + str(exc), file=sys.stderr)
        return 2
    report["evaluated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if report_path is not None:
        try:
            _atomic_text(report_path, payload)
        except OSError as exc:
            print("release/funnel report unavailable: " + str(exc), file=sys.stderr)
            return 2
    if args.json:
        print(payload, end="")
    else:
        _print_human(report)
    if args.require_local_ready:
        # Score is never sufficient. Every release hard-blocker category must
        # pass, while the pilot must be structurally valid, explicitly blocked,
        # and non-authorizing. Missing measurement/receipt evidence must never
        # prevent a safe artifact build or become an execution GO signal.
        release_pass = all(
            report["categories"][name]["status"] == "PASS"
            for name in HARD_BLOCKER_CATEGORIES
        )
        pilot = report["categories"]["bounded_pilot"]
        pilot_safe = pilot["contract_valid"] and pilot["status"] == "BLOCKED"
        return 0 if (
            release_pass
            and pilot_safe
            and report["external_action_authorized"] is False
            and report["publication_authority_granted"] is False
        ) else 1
    return 1 if (
        report["hard_blocked"]
        or report["categories"]["bounded_pilot"]["status"] == "FAIL"
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
