"""Fail-closed consistency guard for analytics/revenue report prose.

The human-readable report may summarize raw observations, but it may not label
GA4, GSC, or affiliate revenue more trustworthy than the canonical local
readiness view.  The generated marker also prevents an old/raw CSV from being
silently promoted after the report producer has selected it.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from types import SimpleNamespace

try:
    import decision_readiness
except ImportError:  # pragma: no cover - package import path
    from pipeline import decision_readiness


SCHEMA = "canonical-evidence-state:v1"
_MARKER_PATTERN = re.compile(
    r"<!-- canonical-evidence-state:v1 "
    r"GA4=([A-Z0-9_]+)\|(READY|BLOCKED) "
    r"GSC=([A-Z0-9_]+)\|(READY|BLOCKED) "
    r"REVENUE=([A-Z0-9_]+)\|(READY|BLOCKED) -->"
)


def _state(value) -> str:
    selected = str(getattr(value, "state", "UNAVAILABLE") or "UNAVAILABLE")
    return selected.replace(" ", "_").upper()


def _gate(value) -> str:
    return "READY" if getattr(value, "trusted", False) is True else "BLOCKED"


def canonical_marker(readiness) -> str:
    """Return the exact machine-readable marker required in every report."""
    return (
        "<!-- %s GA4=%s|%s GSC=%s|%s REVENUE=%s|%s -->"
        % (
            SCHEMA,
            _state(readiness.ga4), _gate(readiness.ga4),
            _state(readiness.gsc), _gate(readiness.gsc),
            _state(readiness.revenue), _gate(readiness.revenue),
        )
    )


def canonical_block(readiness) -> list[str]:
    """Return a prose-safe block whose state tokens must be copied verbatim."""
    return [
        "## Canonical evidence states — ห้ามเขียนยกระดับ",
        "",
        "- GA4: `%s / %s`" % (_state(readiness.ga4), _gate(readiness.ga4)),
        "- GSC: `%s / %s`" % (_state(readiness.gsc), _gate(readiness.gsc)),
        "- verified affiliate revenue: `%s / %s`" % (
            _state(readiness.revenue), _gate(readiness.revenue)
        ),
        canonical_marker(readiness),
        "",
    ]


def readiness_from_marker(text: str):
    """Recover one exact canonical state envelope from a producer report."""
    matches = _MARKER_PATTERN.findall(text)
    if len(matches) != 1:
        raise ValueError("source report must contain exactly one canonical marker")
    values = matches[0]

    def selected(state: str, gate: str) -> SimpleNamespace:
        return SimpleNamespace(
            state=state,
            trusted=gate == "READY",
            label="CURRENT" if gate == "READY" else "UNTRUSTED",
            reason="bound to source report canonical marker",
            schema=SCHEMA,
            expires_at=None,
        )

    return SimpleNamespace(
        ga4=selected(values[0], values[1]),
        gsc=selected(values[2], values[3]),
        revenue=selected(values[4], values[5]),
        observation=None,
    )


_SOURCE_TOKENS = {
    "GA4": (re.compile(r"\bGA4\b", re.I),),
    "GSC": (re.compile(r"\bGSC\b", re.I),),
    "REVENUE": (
        re.compile(r"\b(?:VERIFIED[_ ]?)?(?:AFFILIATE[_ ]?)?REVENUE\b", re.I),
        re.compile(r"(?:รายได้|ยอดขาย)"),
    ),
}
_PROMOTION = re.compile(
    r"(?<!UN)\b(?:CURRENT|TRUSTED|READY|VERIFIED)\b|เชื่อได้|ยืนยันแล้ว|พิสูจน์แล้ว",
    re.I,
)
_BLOCKING_CONTEXT = re.compile(
    r"\b(?:UNTRUSTED|STALE(?:_\w+)?|INVALID(?:_\w+)?|UNAVAILABLE|BLOCKED|"
    r"UNRECONCILED|UNKNOWN)\b|ห้าม|ไม่ใช่\s*0|วัดไม่ได้|ยังไม่ยืนยัน|ไม่มีหลักฐาน",
    re.I,
)
_ZERO_VALUE = re.compile(r"(?:=|:)\s*0(?:\.0+)?(?:\D|$)")
_NUMERIC_EVIDENCE = re.compile(r"\d")
_OWN_PRODUCT_SALES = re.compile(
    r"(?:ยอดขาย|รายได้).{0,60}(?:199\s*฿|letter[- ]?kit|ชุดจดหมาย)",
    re.I,
)
_DECISION_CANDIDATE = re.compile(
    r"\b(?:ACTION|WINNER|SCALE|CADENCE)\b|คำตัดสิน|ทำต่อ\s*:|"
    r"โฟกัส(?:สัปดาห์)?|หน้ารั่ว|striking[ -]?distance|เลือกคีย์|"
    r"ปรับ\s*(?:title|H2)|เพิ่มความถี่|ดันซ้ำ|internal\s+link",
    re.I,
)
_DECISION_BASIS = re.compile(
    r"\[basis=(GA4|GSC|REVENUE|LOCAL_POLICY)\]", re.I
)


def validate_report(text: str, readiness) -> list[str]:
    """Return contradictions between report prose and canonical readiness."""
    errors: list[str] = []
    marker = canonical_marker(readiness)
    if marker not in text:
        errors.append("canonical evidence marker is missing or mismatched")

    sources = {
        "GA4": readiness.ga4,
        "GSC": readiness.gsc,
        "REVENUE": readiness.revenue,
    }
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("<!--"):
            continue
        blocked_context = _BLOCKING_CONTEXT.search(line) is not None
        if (
            _OWN_PRODUCT_SALES.search(line)
            and _NUMERIC_EVIDENCE.search(line)
            and not blocked_context
        ):
            errors.append(
                "line %d reports numeric own-product sales without a bound paid-and-fulfilled ledger"
                % number
            )
        if _DECISION_CANDIDATE.search(line) and not blocked_context:
            basis_match = _DECISION_BASIS.search(line)
            if basis_match is None:
                errors.append(
                    "line %d has an actionable finding without an explicit evidence basis"
                    % number
                )
            else:
                basis = basis_match.group(1).upper()
                if basis != "LOCAL_POLICY":
                    selected = sources[basis]
                    if getattr(selected, "trusted", False) is not True:
                        errors.append(
                            "line %d uses blocked %s as an action basis"
                            % (number, basis)
                        )
        for name, source in sources.items():
            if getattr(source, "trusted", False) is True:
                continue
            if not any(pattern.search(line) for pattern in _SOURCE_TOKENS[name]):
                continue
            if _PROMOTION.search(line) and not blocked_context:
                errors.append(
                    "line %d promotes %s while canonical state is %s"
                    % (number, name, _state(source))
                )
            if name == "REVENUE" and _ZERO_VALUE.search(line) and not blocked_context:
                errors.append(
                    "line %d turns unavailable revenue into zero" % number
                )
            elif (
                name == "REVENUE"
                and _NUMERIC_EVIDENCE.search(line)
                and not blocked_context
            ):
                errors.append(
                    "line %d reports numeric revenue while canonical revenue is unavailable"
                    % number
                )
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate report prose against canonical local evidence states"
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--source-report", type=Path,
        help="producer report whose canonical marker is the immutable authority",
    )
    args = parser.parse_args(argv)
    try:
        text = args.report.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print("report trust guard: FAIL (report unreadable: %s)" % type(exc).__name__)
        return 2
    if args.source_report is not None:
        try:
            source_text = args.source_report.read_text(encoding="utf-8")
            readiness_from_marker(source_text)
        except (OSError, UnicodeError, ValueError) as exc:
            print("report trust guard: FAIL (source report: %s)" % str(exc))
            return 2
        current_readiness = decision_readiness.read()
        source_errors = validate_report(source_text, current_readiness)
        if source_errors:
            print("report trust guard: FAIL (source report is not current canonical evidence)")
            for error in source_errors:
                print("- " + error)
            return 2
        # Parsing above proves there is exactly one marker; validating against
        # the current readiness proves that marker was not forged, copied from
        # an older report, or allowed to outlive a source downgrade.
        readiness = current_readiness
    else:
        readiness = decision_readiness.read()
    errors = validate_report(text, readiness)
    if errors:
        print("report trust guard: FAIL")
        for error in errors:
            print("- " + error)
        return 2
    print("report trust guard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
