"""Shared GA4 CSV schema adapters.

The canonical click field is ``affiliate_click``.  ``conversion`` remains a
read-only fallback for CSV files produced before 2026-08-01.

The bounded-pilot table deliberately uses *session* operands.  Event counts
cannot be substituted for either operand, and every row is bound to one exact
content/placement/CTA identity.  The literal mapping is also read by the
release-only readiness guard without importing this operational module.
"""

from __future__ import annotations

import re


PILOT_MEASUREMENT_FIELDS = {
    "contract_version": 1,
    "primary_metric": "affiliate_click_sessions / qualified_landing_sessions",
    "fields": [
        "affiliate_click_sessions",
        "qualified_landing_sessions",
    ],
    "dimensions": [
        "provider",
        "cta_id",
        "position",
        "content_id",
        "acquisition_content_id",
        "sub_id",
        "channel",
        "campaign",
    ],
    "scopes": {
        "affiliate_click_sessions": "session",
        "qualified_landing_sessions": "session",
    },
    "field_order": [
        "provider",
        "cta_id",
        "position",
        "content_id",
        "acquisition_content_id",
        "sub_id",
        "channel",
        "campaign",
        "affiliate_click_sessions",
        "qualified_landing_sessions",
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

_PILOT_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_GA4_MISSING_DIMENSIONS = {"", "(not set)", "(data not available)"}


def metric_int(row, *names):
    """Return the first present metric as an int, tolerating CSV number text."""
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    return 0


def affiliate_click(row):
    """Read the canonical field first, then the legacy pre-August field."""
    return metric_int(row, "affiliate_click", "conversion")


def canonical_pilot_dimension(value, field):
    """Return one unambiguous pilot dimension or raise instead of guessing.

    GA4 represents a missing custom/session dimension as ``(not set)``.  Only
    acquisition content may be genuinely absent, and it receives one explicit
    sentinel so direct sessions do not collapse into malformed blank keys.
    """
    if not isinstance(field, str) or field not in PILOT_MEASUREMENT_FIELDS["dimensions"]:
        raise ValueError("unknown pilot dimension")
    if value is None:
        selected = ""
    elif isinstance(value, str):
        selected = value.strip()
    else:
        raise ValueError("pilot %s must be text" % field)
    if selected.lower() in _GA4_MISSING_DIMENSIONS:
        if field == "acquisition_content_id":
            return "unattributed"
        raise ValueError("pilot %s is missing" % field)
    if selected != selected.lower() or not _PILOT_TOKEN_RE.fullmatch(selected):
        raise ValueError("pilot %s is not canonical" % field)
    return selected


def _pilot_operand(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError("pilot %s must be a non-negative integer" % field)
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value.strip()):
        number = int(value)
    else:
        raise ValueError("pilot %s must be a non-negative integer" % field)
    if number < 0:
        raise ValueError("pilot %s must be a non-negative integer" % field)
    return number


def pilot_row_errors(row):
    """Validate one materialized session row without coercing bad evidence."""
    if not isinstance(row, dict):
        return ["pilot row must be an object"]
    errors = []
    for field in PILOT_MEASUREMENT_FIELDS["dimensions"]:
        try:
            canonical_pilot_dimension(row.get(field), field)
        except ValueError as exc:
            errors.append(str(exc))
    operands = {}
    for field in PILOT_MEASUREMENT_FIELDS["fields"]:
        try:
            operands[field] = _pilot_operand(row.get(field), field)
        except ValueError as exc:
            errors.append(str(exc))
    if row.get("measurement_scope") != "session":
        errors.append("pilot measurement_scope must be session")
    if (
        set(operands) == set(PILOT_MEASUREMENT_FIELDS["fields"])
        and operands["affiliate_click_sessions"]
        > operands["qualified_landing_sessions"]
    ):
        errors.append("affiliate_click_sessions exceeds qualified_landing_sessions")
    return errors


def pilot_table_errors(rows, fields=None):
    """Validate exact schema, row semantics, and composite uniqueness."""
    expected_fields = PILOT_MEASUREMENT_FIELDS["field_order"]
    errors = []
    if fields is not None and list(fields) != expected_fields:
        errors.append("pilot fields do not match canonical order")
    if not isinstance(rows, (list, tuple)):
        return errors + ["pilot rows must be a sequence"]
    seen = set()
    dimensions = PILOT_MEASUREMENT_FIELDS["dimensions"]
    for index, row in enumerate(rows, 2):
        row_errors = pilot_row_errors(row)
        errors.extend("row %d: %s" % (index, error) for error in row_errors)
        if row_errors:
            continue
        identity = tuple(canonical_pilot_dimension(row[field], field)
                         for field in dimensions)
        if identity in seen:
            errors.append("row %d: duplicate pilot dimension tuple" % index)
        seen.add(identity)
    return errors
