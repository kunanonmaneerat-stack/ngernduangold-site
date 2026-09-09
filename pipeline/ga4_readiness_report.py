#!/usr/bin/env python3
"""Emit a privacy-safe, local-only GA4 repair/readiness report.

The report never contacts GA4, discovers an egress address, changes CIDRs, or
promotes legacy CSVs.  It explains why the existing local evidence cannot be
used for decisions and what externally verified evidence is still required.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import platform
from pathlib import Path
import sys

try:
    import ga4_decision_trust
    import ga4_pull
    import observation_snapshot
except ImportError:  # pragma: no cover - package import path
    from pipeline import ga4_decision_trust, ga4_pull, observation_snapshot


BANGKOK = dt.timezone(dt.timedelta(hours=7))
EXPECTED_METADATA_FIELDS = {
    "schema_version",
    "captured_at",
    "window_start",
    "window_end",
    "window_days",
    "property_id",
    "producer_sha256",
    "event_contract",
    "pilot_measurement_contract",
    "pilot_schema_contract",
    "pilot_binding",
    "query_coverage",
    "ga4_decision_trust",
    "capture_time_trust",
    "files",
}


def _fingerprint(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _strict_json(path: Path):
    try:
        return observation_snapshot._strict_json_loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None


def _safe_runtime_details(policy_path: Path, host_path: Path, now: dt.datetime):
    trust = ga4_decision_trust.evaluate_ga4_decision_trust(
        policy_path, host_path, now=now
    )
    egress = getattr(trust, "egress_ip", None)
    cidrs = tuple(getattr(trust, "cidrs", ()) or ())
    covered = None
    if egress and cidrs:
        try:
            address = ipaddress.ip_address(egress)
            networks = [ipaddress.ip_network(value, strict=False) for value in cidrs]
            covered = any(
                address.version == network.version and address in network
                for network in networks
            )
        except ValueError:
            covered = False

    verified_at = None
    date_window_complete = None
    attestation_bound = None
    try:
        policy, error = ga4_decision_trust._read_json(
            policy_path, "policy trust config"
        )
        block, _schema = ga4_decision_trust._internal_block(policy)
        if error or block is None:
            raise ValueError("unavailable policy block")
        (
            block,
            error,
            _private_schema,
            block_owner_path,
        ) = ga4_decision_trust._private_internal_block(block, policy_path)
        if error or block is None:
            raise ValueError("unavailable private block")
        raw_verified = block.get("verified_at")
        if isinstance(raw_verified, str) and raw_verified.strip():
            verified_at = raw_verified.strip()
        date_window_complete = (
            ga4_decision_trust._coverage_window_error(
                block, today=now.astimezone(BANGKOK).date()
            )
            is None
        )
        raw_cidrs, cidr_error = ga4_decision_trust._configured_cidrs(block)
        if cidr_error:
            raise ValueError("unavailable CIDR set")
        if isinstance(raw_cidrs, str):
            raw_cidrs = [raw_cidrs]
        if not isinstance(raw_cidrs, list) or not raw_cidrs:
            raise ValueError("unavailable CIDR set")
        networks = [
            ipaddress.ip_network(str(value).strip(), strict=False)
            for value in raw_cidrs
        ]
        attestation_bound = (
            ga4_decision_trust._coverage_attestation_error(
                block,
                networks,
                owner_path=block_owner_path,
                today=now.astimezone(BANGKOK).date(),
            )
            is None
        )
    except (AttributeError, TypeError, ValueError):
        pass

    return {
        "trusted": trust.trusted is True and trust.label == "TRUSTED",
        "label": "TRUSTED" if trust.trusted is True and trust.label == "TRUSTED"
        else "UNTRUSTED",
        "reason": str(trust.reason),
        "schema": str(trust.schema),
        "expires_at": getattr(trust, "expires_at", None),
        "host_record_present": bool(egress),
        "host_record_fingerprint": _fingerprint(egress),
        "configured_cidr_count": len(cidrs),
        "configured_cidr_fingerprints": sorted(
            value for value in (_fingerprint(item) for item in cidrs) if value
        ),
        "current_egress_covered": covered,
        "coverage_verified_at": verified_at,
        "date_window_complete": date_window_complete,
        "coverage_attestation_bound": attestation_bound,
        "full_28_day_coverage": (
            date_window_complete is True and attestation_bound is True
        ),
        "raw_network_values_redacted": True,
    }


def _bundle_details(root: Path, now: dt.datetime):
    log = root / "automation-log"
    meta_path = log / "ga4-snapshot.json"
    files = {
        "metrics": log / "ga4-metrics.csv",
        "pages": log / "ga4-pages.csv",
        "funnel": log / "ga4-funnel.csv",
        "pilot_sessions": log / "ga4-pilot-sessions.csv",
    }
    metadata = _strict_json(meta_path)
    declared = metadata.get("files") if isinstance(metadata, dict) else None
    coverage = metadata.get("query_coverage") if isinstance(metadata, dict) else None
    declared = declared if isinstance(declared, dict) else {}
    coverage = coverage if isinstance(coverage, dict) else {}

    file_details = {}
    for name, path in files.items():
        exists = path.is_file()
        actual_hash = None
        if exists:
            try:
                actual_hash = observation_snapshot.sha256_file(path)
            except (OSError, UnicodeError):
                pass
        declared_hash = declared.get(name)
        file_details[name] = {
            "exists": exists,
            "declared": name in declared,
            "hash_matches": (
                isinstance(declared_hash, str)
                and actual_hash is not None
                and declared_hash == actual_hash
            ),
        }

    base = observation_snapshot.validate_bundle(
        meta_path,
        files,
        now=now,
        csv_contracts=observation_snapshot.GA4_CSV_CONTRACTS,
        producer_path=Path(ga4_pull.__file__).resolve(),
        expected_schema_version=3,
    )
    validated = observation_snapshot.require_ga4_pilot_provenance(
        observation_snapshot.require_source_identity(
            observation_snapshot.require_ga4_coverage(base), "ga4"
        )
    )
    local_day = now.astimezone(BANGKOK).date()
    expected_end = local_day
    expected_start = local_day - dt.timedelta(days=27)
    metadata_keys = set(metadata) if isinstance(metadata, dict) else set()
    return {
        "metadata_path": str(meta_path),
        "metadata_readable": isinstance(metadata, dict),
        "validator_state": validated.get("state", "UNKNOWN"),
        "validator_decisionable_before_runtime_trust": (
            validated.get("decisionable") is True
        ),
        "schema_version": {
            "expected": 3,
            "actual": metadata.get("schema_version") if isinstance(metadata, dict) else None,
            "exact_integer_match": (
                isinstance(metadata, dict)
                and type(metadata.get("schema_version")) is int
                and metadata.get("schema_version") == 3
            ),
        },
        "metadata_fields": {
            "required": sorted(EXPECTED_METADATA_FIELDS),
            "missing": sorted(EXPECTED_METADATA_FIELDS - metadata_keys),
        },
        "window": {
            "expected_start": expected_start.isoformat(),
            "expected_end": expected_end.isoformat(),
            "actual_start": metadata.get("window_start") if isinstance(metadata, dict) else None,
            "actual_end": metadata.get("window_end") if isinstance(metadata, dict) else None,
            "current": (
                isinstance(metadata, dict)
                and metadata.get("window_start") == expected_start.isoformat()
                and metadata.get("window_end") == expected_end.isoformat()
                and type(metadata.get("window_days")) is int
                and metadata.get("window_days") == 28
            ),
        },
        "files": {
            "required_keys": sorted(files),
            "declared_keys": sorted(declared),
            "missing_declared_keys": sorted(set(files) - set(declared)),
            "unexpected_declared_keys": sorted(set(declared) - set(files)),
            "details": file_details,
        },
        "query_coverage": {
            "required_keys": sorted(ga4_pull.GA4_QUERY_NAMES),
            "present_keys": sorted(coverage),
            "missing_keys": sorted(set(ga4_pull.GA4_QUERY_NAMES) - set(coverage)),
            "unexpected_keys": sorted(set(coverage) - set(ga4_pull.GA4_QUERY_NAMES)),
        },
        "capture_trust": (
            metadata.get("ga4_decision_trust") if isinstance(metadata, dict) else None
        ),
    }


def _blockers(runtime: dict, bundle: dict):
    blockers = []

    def add(code, field, expected, actual, repair):
        blockers.append({
            "code": code,
            "field": field,
            "expected": expected,
            "actual": actual,
            "repair": repair,
        })

    if runtime["current_egress_covered"] is not True:
        add(
            "CURRENT_EGRESS_NOT_COVERED",
            "runtime.current_egress_covered",
            True,
            runtime["current_egress_covered"],
            "Verify the current egress externally, add only its exact CIDR in GA4 and the private policy, then record fresh local evidence.",
        )
    if runtime["coverage_attestation_bound"] is not True:
        add(
            "COVERAGE_ATTESTATION_NOT_BOUND",
            "runtime.coverage_attestation_bound",
            True,
            runtime["coverage_attestation_bound"],
            "Create authenticated read-only GA4 Admin activation evidence bound to the exact normalized CIDR set and reset verified_at to that activation date.",
        )
    if runtime["date_window_complete"] is not True:
        add(
            "FILTER_COVERAGE_NOT_28_DAYS",
            "runtime.date_window_complete",
            True,
            runtime["date_window_complete"],
            "After the externally verified exclusion is active, wait until it spans the complete rolling 28-day decision window.",
        )
    if runtime["trusted"] is not True:
        add(
            "RUNTIME_TRUST_NOT_TRUSTED",
            "runtime.trusted",
            True,
            {"trusted": False, "reason": runtime["reason"]},
            "Resolve every fail-closed runtime trust reason before pulling or using GA4 decision evidence.",
        )
    schema = bundle["schema_version"]
    if schema["exact_integer_match"] is not True:
        add(
            "SNAPSHOT_SCHEMA_NOT_V3",
            "bundle.schema_version",
            3,
            schema["actual"],
            "Repull all four tables atomically with the schema-v3 producer; do not edit or migrate legacy metadata by hand.",
        )
    missing_fields = bundle["metadata_fields"]["missing"]
    if missing_fields:
        add(
            "SNAPSHOT_REQUIRED_FIELDS_MISSING",
            "bundle.metadata_fields",
            [],
            missing_fields,
            "Regenerate metadata from one complete trusted producer run.",
        )
    missing_files = bundle["files"]["missing_declared_keys"]
    nonexistent_files = sorted(
        key for key, value in bundle["files"]["details"].items()
        if value["exists"] is not True
    )
    if missing_files or nonexistent_files:
        add(
            "SNAPSHOT_FILE_SET_INCOMPLETE",
            "bundle.files",
            {"declared": [], "not_materialized": []},
            {"missing_declared": missing_files, "not_materialized": nonexistent_files},
            "Repull metrics, pages, funnel, and pilot_sessions as one atomic bundle.",
        )
    missing_queries = bundle["query_coverage"]["missing_keys"]
    if missing_queries:
        add(
            "QUERY_COVERAGE_MISSING",
            "bundle.query_coverage",
            [],
            missing_queries,
            "Use the schema-v3 producer so every paginated query records exact row coverage.",
        )
    if bundle["window"]["current"] is not True:
        add(
            "SNAPSHOT_WINDOW_NOT_CURRENT",
            "bundle.window",
            {
                "start": bundle["window"]["expected_start"],
                "end": bundle["window"]["expected_end"],
            },
            {
                "start": bundle["window"]["actual_start"],
                "end": bundle["window"]["actual_end"],
            },
            "Repull only after runtime trust is valid; historical files remain observations, not decision evidence.",
        )
    if bundle["capture_trust"] != "TRUSTED":
        add(
            "CAPTURE_TRUST_NOT_TRUSTED",
            "bundle.capture_trust",
            "TRUSTED",
            bundle["capture_trust"],
            "A new bundle must be captured while runtime trust is valid; capture trust cannot be backfilled.",
        )
    return sorted(blockers, key=lambda item: item["code"])


def build_report(root: Path, *, now: dt.datetime | None = None):
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    selected = Path(root).resolve()
    runtime = _safe_runtime_details(
        selected / ".system_control" / "policy.json",
        selected / ".system_control" / "host_ip.json",
        current,
    )
    bundle = _bundle_details(selected, current)
    blockers = _blockers(runtime, bundle)
    return {
        "schema_version": 1,
        "generated_at": current.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode": "LOCAL_ONLY_NO_NETWORK",
        "host_fingerprint": _fingerprint(platform.node()),
        "decision_state": "READY" if not blockers else "BLOCKED",
        "ready_to_pull": runtime["trusted"] is True,
        "ready_for_decisions": (
            not blockers
            and bundle["validator_decisionable_before_runtime_trust"] is True
            and runtime["trusted"] is True
        ),
        "runtime": runtime,
        "bundle": bundle,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "safety": {
            "network_called": False,
            "ga4_called": False,
            "tracker_opened": False,
            "test_traffic_created": False,
            "configuration_mutated": False,
            "legacy_snapshot_promoted": False,
        },
    }


def _parse_now(value: str | None):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--now must include a UTC offset")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--now", type=_parse_now)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.repo_root, now=args.now)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    sys.stdout.write(rendered)
    return 0 if report["ready_for_decisions"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
