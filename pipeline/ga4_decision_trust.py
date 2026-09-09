"""Fail-closed trust check for GA4 decisions based on internal-IP coverage."""

from __future__ import annotations

import ipaddress
import hashlib
import json
import math
import os
import datetime
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


HOST_STATE_MAX_AGE_DAYS = 7
DECISION_WINDOW_DAYS = 28
BANGKOK = datetime.timezone(datetime.timedelta(hours=7))
COVERAGE_ATTESTATION_SCHEMA_VERSION = 1
COVERAGE_ATTESTATION_SOURCE = "authenticated_ga4_admin_read_only"


@dataclass(frozen=True)
class TrustResult:
    trusted: bool
    label: str
    reason: str
    # Exclusive UTC boundary for a cached consumer.  Missing/invalid runtime
    # freshness evidence must never be interpreted as indefinitely trusted.
    expires_at: str | None = None
    # Kept for local compatibility with older callers, but deliberately hidden
    # from repr/logging.  Public consumers must use only trusted/label/reason.
    egress_ip: str | None = field(default=None, repr=False)
    cidrs: tuple[str, ...] = field(default_factory=tuple, repr=False)
    schema: str = "unknown"


def _untrusted(reason: str, *, schema: str = "unknown") -> TrustResult:
    return TrustResult(False, "UNTRUSTED", reason, schema=schema)


def _strict_json_loads(text: str):
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON constant: " + value)

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        parse_float=finite_float,
        object_pairs_hook=unique_object,
    )


def _read_json(path: str | Path, label: str) -> tuple[Any | None, str | None]:
    try:
        return _strict_json_loads(Path(path).read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{label} is missing"
    except (json.JSONDecodeError, ValueError) as exc:
        detail = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
        return None, f"{label} is invalid JSON ({detail})"
    except OSError as exc:
        return None, f"{label} cannot be read ({type(exc).__name__})"


def _internal_block(policy: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Return current or explicitly supported legacy internal-traffic schema."""
    ga4 = policy.get("ga4")
    if isinstance(ga4, dict) and isinstance(ga4.get("internal_traffic"), dict):
        return ga4["internal_traffic"], "ga4.internal_traffic"
    # Legacy exports placed the block at the document root.
    if isinstance(policy.get("ga4_internal_traffic"), dict):
        return policy["ga4_internal_traffic"], "ga4_internal_traffic (legacy)"
    if isinstance(policy.get("internal_traffic"), dict):
        return policy["internal_traffic"], "internal_traffic (legacy)"
    return None, "unknown"


def _single_alias(
    value: Any, keys: tuple[str, ...], label: str
) -> tuple[Any, str | None]:
    """Read one supported alias and reject documents with two sources of truth."""
    if not isinstance(value, dict):
        return None, None
    present = [key for key in keys if key in value]
    if len(present) > 1:
        return None, f"{label} has ambiguous aliases"
    return (value.get(present[0]) if present else None), None


def _configured_cidrs(block: dict[str, Any]) -> tuple[Any, str | None]:
    return _single_alias(
        block,
        ("ips", "cidrs", "internal_cidrs", "ip_ranges", "addresses"),
        "configured internal CIDRs",
    )


def _contract_path(
    contract: dict[str, Any], owner_path: str | Path, label: str
) -> tuple[Path | None, str | None]:
    env_name = contract.get("environment")
    if env_name is not None and not isinstance(env_name, str):
        return None, f"{label} contract environment must be a string"
    raw = os.environ.get(env_name, "").strip() if env_name else ""
    if not raw:
        raw = str(contract.get("default") or "").strip()
    if not raw:
        return None, f"{label} contract has no private path"
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        owner = Path(owner_path).resolve()
        base = owner.parent.parent if owner.parent.name == ".system_control" else owner.parent
        candidate = base / candidate
    return candidate.resolve(), None


def _private_internal_block(
    block: dict[str, Any], policy_path: str | Path
) -> tuple[dict[str, Any] | None, str | None, str, Path]:
    owner_path = Path(policy_path).resolve()
    contract = block.get("private_config_contract")
    if contract is None:
        return block, None, "", owner_path
    if not isinstance(contract, dict):
        return None, "GA4 private config contract must be an object", "", owner_path
    expected_schema = contract.get("schema_version")
    if (
        not isinstance(expected_schema, int)
        or isinstance(expected_schema, bool)
        or expected_schema < 1
    ):
        return (
            None,
            "GA4 private config contract schema_version is missing or invalid",
            "",
            owner_path,
        )
    path, error = _contract_path(contract, policy_path, "GA4 private config")
    if error:
        return None, error, "", owner_path
    private, error = _read_json(path, "GA4 private config")
    if error:
        return None, error, "", path or owner_path
    if not isinstance(private, dict):
        return None, "GA4 private config must be a JSON object", "", path
    private_schema = private.get("schema_version")
    if type(private_schema) is not int or private_schema != expected_schema:
        return (
            None,
            "GA4 private config schema_version does not match its contract",
            "",
            path,
        )
    private_block, private_schema = _internal_block(private)
    if private_block is None:
        # A minimal private file may itself be the internal-traffic block.
        if any(key in private for key in ("ips", "cidrs", "internal_cidrs")):
            private_block, private_schema = private, "private internal_traffic"
        else:
            return (
                None,
                "GA4 private config has no supported internal-traffic block",
                "",
                path,
            )
    return private_block, None, " -> private " + private_schema, path


def _private_host_state(
    host: Any, host_path: str | Path
) -> tuple[Any | None, str | None]:
    if not isinstance(host, dict) or "private_state_contract" not in host:
        return host, None
    contract = host.get("private_state_contract")
    if not isinstance(contract, dict):
        return None, "egress state private contract must be an object"
    path, error = _contract_path(contract, host_path, "egress state")
    if error:
        return None, error
    return _read_json(path, "private egress state")


def _egress_value(host: Any) -> tuple[Any, str | None]:
    if isinstance(host, str):
        return host, None
    return _single_alias(
        host, ("ip", "egress_ip", "public_ip", "address"),
        "private egress state address",
    )


def _host_state_timestamp(host: Any) -> datetime.datetime | None:
    if not isinstance(host, dict):
        return None
    try:
        stamp = datetime.datetime.fromisoformat(
            str(host.get("checked_at") or "").replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return None
    return stamp


def _host_state_freshness_error(
    host: Any, *, now: datetime.datetime | None = None
) -> str | None:
    """Return a privacy-safe reason when host state cannot support a decision."""
    if not isinstance(host, dict):
        return "private egress state is not a JSON object"
    stamp = _host_state_timestamp(host)
    if stamp is None:
        return "private egress state checked_at is missing, invalid, or timezone-naive"
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        return "GA4 trust evaluation time is timezone-naive"
    age_seconds = (
        current.astimezone(datetime.timezone.utc)
        - stamp.astimezone(datetime.timezone.utc)
    ).total_seconds()
    if age_seconds < -300:
        return "private egress state checked_at is unexpectedly in the future"
    if age_seconds >= HOST_STATE_MAX_AGE_DAYS * 86400:
        return "private egress state is stale"
    return None


def _host_state_origin_error(host: Any) -> str | None:
    """Bind private egress evidence to this host and its supported producer.

    A fresh address copied from another machine is not evidence about the
    machine that runs the GA4 producer.  Reasons intentionally omit hostnames,
    addresses, and network ranges so callers may log them safely.
    """
    if not isinstance(host, dict):
        return "private egress state is not a JSON object"
    recorded_host = host.get("host")
    try:
        current_host = platform.node()
    except Exception:
        current_host = ""
    if not isinstance(recorded_host, str) or not recorded_host.strip():
        return "private egress state host identity is missing"
    if not isinstance(current_host, str) or not current_host.strip():
        return "current host identity is unavailable"
    if recorded_host.strip().casefold() != current_host.strip().casefold():
        return "private egress state was captured on a different host"
    if host.get("source") != "api.ipify.org":
        return "private egress state source is missing or unsupported"
    return None


def _coverage_window_error(
    block: dict[str, Any], *, today: datetime.date | None = None
) -> str | None:
    """Require the current exclusion coverage to span the whole decision window."""
    raw = block.get("verified_at", block.get("activated_at"))
    if not isinstance(raw, str) or not raw.strip():
        return "GA4 internal-traffic verified_at is missing"
    try:
        text = raw.strip().replace("Z", "+00:00")
        if "T" in text:
            verified_at = datetime.datetime.fromisoformat(text)
            if verified_at.tzinfo is None or verified_at.utcoffset() is None:
                raise ValueError("verified_at timestamp must include a timezone")
            verified = verified_at.astimezone(BANGKOK).date()
        else:
            verified = datetime.date.fromisoformat(text)
    except ValueError:
        return "GA4 internal-traffic verified_at is invalid"
    current_day = today or datetime.datetime.now(BANGKOK).date()
    window_start = current_day - datetime.timedelta(days=DECISION_WINDOW_DAYS - 1)
    if verified > current_day:
        return "GA4 internal-traffic verified_at is in the future"
    if verified > window_start:
        return "GA4 internal-traffic coverage has not spanned the full 28-day decision window"
    return None


def _cidr_set_sha256(networks: list[Any] | tuple[Any, ...]) -> str:
    """Fingerprint one normalized CIDR set without exposing network values.

    Sorting and de-duplicating makes the binding independent of UI ordering,
    while any material range change invalidates the saved attestation.
    """
    normalized = sorted({str(network) for network in networks})
    canonical = json.dumps(
        normalized, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _verified_business_date(block: dict[str, Any]) -> tuple[datetime.date | None, str | None]:
    raw = block.get("verified_at", block.get("activated_at"))
    if not isinstance(raw, str) or not raw.strip():
        return None, "GA4 internal-traffic verified_at is missing"
    try:
        text = raw.strip().replace("Z", "+00:00")
        if "T" in text:
            value = datetime.datetime.fromisoformat(text)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("verified_at timestamp must include a timezone")
            return value.astimezone(BANGKOK).date(), None
        return datetime.date.fromisoformat(text), None
    except ValueError:
        return None, "GA4 internal-traffic verified_at is invalid"


def _coverage_attestation_error(
    block: dict[str, Any],
    networks: list[Any] | tuple[Any, ...],
    *,
    owner_path: str | Path,
    today: datetime.date | None = None,
) -> str | None:
    """Bind the clean-window start to the exact Admin-observed CIDR set.

    The attestation is deliberately immutable evidence from the activation
    observation.  A CIDR change must create a new authenticated observation
    and reset ``verified_at``; retaining an old date therefore fails closed.
    """
    attestation = block.get("coverage_attestation")
    if not isinstance(attestation, dict):
        return "GA4 coverage attestation is missing"
    schema_version = attestation.get("schema_version")
    if type(schema_version) is not int or schema_version != COVERAGE_ATTESTATION_SCHEMA_VERSION:
        return "GA4 coverage attestation schema_version is missing or unsupported"
    if attestation.get("source") != COVERAGE_ATTESTATION_SOURCE:
        return "GA4 coverage attestation source is missing or unsupported"

    raw_verified = block.get("verified_at", block.get("activated_at"))
    attested_verified = attestation.get("verified_at")
    if (
        not isinstance(raw_verified, str)
        or not isinstance(attested_verified, str)
        or attested_verified.strip() != raw_verified.strip()
    ):
        return "GA4 coverage attestation does not bind the current verified_at"

    verified_day, error = _verified_business_date(block)
    if error or verified_day is None:
        return error or "GA4 internal-traffic verified_at is invalid"
    raw_attested_at = attestation.get("attested_at")
    try:
        attested_at = datetime.datetime.fromisoformat(
            str(raw_attested_at or "").replace("Z", "+00:00")
        )
        if attested_at.tzinfo is None or attested_at.utcoffset() is None:
            raise ValueError("attested_at must include a timezone")
    except (TypeError, ValueError):
        return "GA4 coverage attestation attested_at is missing, invalid, or timezone-naive"
    attested_day = attested_at.astimezone(BANGKOK).date()
    current_day = today or datetime.datetime.now(BANGKOK).date()
    if attested_day > current_day:
        return "GA4 coverage attestation attested_at is in the future"
    if attested_day != verified_day:
        return "GA4 coverage attestation does not bind the clean-window start date"

    fingerprint = attestation.get("cidr_set_sha256")
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(char not in "0123456789abcdef" for char in fingerprint)
    ):
        return "GA4 coverage attestation CIDR-set fingerprint is missing or invalid"
    expected_fingerprint = _cidr_set_sha256(networks)
    if fingerprint != expected_fingerprint:
        return "GA4 coverage attestation does not match the configured CIDR set"

    observation_contract = attestation.get("admin_observation_contract")
    if not isinstance(observation_contract, dict):
        return "GA4 Admin observation contract is missing"
    observation_schema = observation_contract.get("schema_version")
    if type(observation_schema) is not int or observation_schema != 1:
        return "GA4 Admin observation contract schema_version is missing or unsupported"
    raw_name = observation_contract.get("default")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return "GA4 Admin observation contract has no evidence file"
    evidence_name = Path(raw_name.strip())
    if (
        evidence_name.is_absolute()
        or evidence_name.name != raw_name.strip()
        or str(evidence_name) in {".", ".."}
    ):
        return "GA4 Admin observation contract evidence path is not a safe sibling file"
    expected_observation_hash = observation_contract.get("sha256")
    if (
        not isinstance(expected_observation_hash, str)
        or len(expected_observation_hash) != 64
        or any(
            char not in "0123456789abcdef"
            for char in expected_observation_hash
        )
    ):
        return "GA4 Admin observation contract SHA-256 is missing or invalid"
    evidence_path = Path(owner_path).resolve().parent / evidence_name
    try:
        evidence_bytes = evidence_path.read_bytes()
    except FileNotFoundError:
        return "GA4 Admin observation evidence is missing"
    except OSError as exc:
        return "GA4 Admin observation evidence cannot be read (%s)" % type(exc).__name__
    if hashlib.sha256(evidence_bytes).hexdigest() != expected_observation_hash:
        return "GA4 Admin observation evidence SHA-256 does not match its contract"
    try:
        observation = _strict_json_loads(evidence_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, ValueError):
        return "GA4 Admin observation evidence is invalid JSON"
    if not isinstance(observation, dict):
        return "GA4 Admin observation evidence must be a JSON object"
    if type(observation.get("schema_version")) is not int or observation.get("schema_version") != 1:
        return "GA4 Admin observation schema_version is missing or unsupported"
    if observation.get("mode") != "authenticated_browser_read_only":
        return "GA4 Admin observation mode is missing or unsupported"
    if observation.get("external_mutations") != []:
        return "GA4 Admin observation does not prove a read-only capture"
    observed = observation.get("internal_traffic")
    if not isinstance(observed, dict):
        return "GA4 Admin observation internal-traffic evidence is missing"
    if str(observed.get("filter_state") or "").strip().casefold() != "active":
        return "GA4 Admin observation filter is not Active"
    if str(observed.get("filter_operation") or "").strip().casefold() != "exclude":
        return "GA4 Admin observation operation is not Exclude"
    if observed.get("exact_normalized_set_match") is not True:
        return "GA4 Admin observation does not prove an exact normalized-set match"
    if observed.get("raw_network_values_emitted") is not False:
        return "GA4 Admin observation network-value redaction is not proven"
    normalized_count = len({str(network) for network in networks})
    for count_key in ("condition_count", "private_contract_condition_count"):
        count = observed.get(count_key)
        if type(count) is not int or count != normalized_count:
            return "GA4 Admin observation condition count does not match the CIDR set"
    if observed.get("cidr_set_sha256") != expected_fingerprint:
        return "GA4 Admin observation CIDR-set fingerprint does not match"
    try:
        observed_at = datetime.datetime.fromisoformat(
            str(observation.get("observed_at") or "").replace("Z", "+00:00")
        )
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
    except (TypeError, ValueError):
        return "GA4 Admin observation observed_at is missing, invalid, or timezone-naive"
    if observed_at.astimezone(datetime.timezone.utc) != attested_at.astimezone(
        datetime.timezone.utc
    ):
        return "GA4 coverage attestation time does not match the Admin observation"
    return None


def evaluate_ga4_decision_trust(
    policy_path: str | Path,
    host_ip_path: str | Path,
    *,
    now: datetime.datetime | None = None,
) -> TrustResult:
    """Trust GA4 decisions only when the recorded egress IP is excluded.

    This function performs local file reads only. Every missing, malformed, or
    ambiguous input returns ``UNTRUSTED`` instead of guessing.
    """
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        return _untrusted("GA4 trust evaluation time must be timezone-aware")
    policy, error = _read_json(policy_path, "policy trust config")
    if error:
        return _untrusted(error)
    if not isinstance(policy, dict):
        return _untrusted("policy trust config must be a JSON object")

    block, schema = _internal_block(policy)
    if block is None:
        return _untrusted(
            "policy trust config has no supported GA4 internal-traffic block",
            schema=schema,
        )
    block, error, private_schema, block_owner_path = _private_internal_block(
        block, policy_path
    )
    if error or block is None:
        return _untrusted(error or "GA4 private config is unavailable", schema=schema)
    schema += private_schema
    raw_state, error = _single_alias(
        block, ("filter_state", "state"), "GA4 internal-traffic filter state"
    )
    if error:
        return _untrusted(error, schema=schema)
    state = str(raw_state or "").strip().casefold()
    if state != "active":
        return _untrusted(
            f"GA4 internal-traffic filter is not active (found {raw_state or 'missing'})",
            schema=schema,
        )
    raw_operation, error = _single_alias(
        block, ("filter_operation", "operation"),
        "GA4 internal-traffic operation",
    )
    if error:
        return _untrusted(error, schema=schema)
    if raw_operation is None:
        return _untrusted(
            "GA4 internal-traffic operation is missing; Exclude is required",
            schema=schema,
        )
    if str(raw_operation).strip().casefold() != "exclude":
        return _untrusted(
            f"GA4 internal-traffic operation is not Exclude (found {raw_operation})",
            schema=schema,
        )
    # Keep evaluating privacy-safe, independently actionable blockers.  A
    # newly activated filter and an uncovered current egress can coexist; if
    # we return on the age gate first, the operator may wait 28 days only to
    # discover that the clean window never started for this host.
    coverage_error = _coverage_window_error(
        block, today=current.astimezone(BANGKOK).date()
    )

    raw_cidrs, error = _configured_cidrs(block)
    if error:
        return _untrusted(error, schema=schema)
    if isinstance(raw_cidrs, str):
        raw_cidrs = [raw_cidrs]
    if not isinstance(raw_cidrs, list) or not raw_cidrs:
        return _untrusted("configured internal CIDRs are missing or empty", schema=schema)
    networks = []
    try:
        for raw in raw_cidrs:
            networks.append(ipaddress.ip_network(str(raw).strip(), strict=False))
    except ValueError:
        return _untrusted("configured internal CIDR is invalid", schema=schema)
    if any(
        (network.version == 4 and network.prefixlen < 24)
        or (network.version == 6 and network.prefixlen < 64)
        for network in networks
    ):
        return _untrusted(
            "configured internal CIDR is broader than the supported exclusion range",
            schema=schema,
        )
    attestation_error = _coverage_attestation_error(
        block,
        networks,
        owner_path=block_owner_path,
        today=current.astimezone(BANGKOK).date(),
    )

    host, error = _read_json(host_ip_path, "egress IP record")
    if error:
        return _untrusted(error, schema=schema)
    host, error = _private_host_state(host, host_ip_path)
    if error:
        return _untrusted(error, schema=schema)
    origin_error = _host_state_origin_error(host)
    if origin_error:
        return _untrusted(origin_error, schema=schema)
    freshness_error = _host_state_freshness_error(host, now=current)
    if freshness_error:
        return _untrusted(freshness_error, schema=schema)
    raw_ip, error = _egress_value(host)
    if error:
        return _untrusted(error, schema=schema)
    try:
        egress = ipaddress.ip_address(str(raw_ip).strip())
    except ValueError:
        return _untrusted(
            "private egress state address is missing or invalid",
            schema=schema,
        )

    same_family = [network for network in networks if network.version == egress.version]
    rendered = tuple(str(network) for network in networks)
    if not any(egress in network for network in same_family):
        reason = "private egress state is outside configured internal CIDRs"
        if coverage_error:
            reason += "; " + coverage_error
        if attestation_error:
            reason += "; " + attestation_error
        return TrustResult(
            False,
            "UNTRUSTED",
            reason,
            egress_ip=str(egress),
            cidrs=rendered,
            schema=schema,
        )
    if coverage_error or attestation_error:
        return TrustResult(
            False,
            "UNTRUSTED",
            "; ".join(
                reason
                for reason in (coverage_error, attestation_error)
                if reason
            ),
            egress_ip=str(egress),
            cidrs=rendered,
            schema=schema,
        )
    host_stamp = _host_state_timestamp(host)
    if host_stamp is None:  # Defensive: the freshness gate above must own this.
        return _untrusted(
            "private egress state checked_at is missing, invalid, or timezone-naive",
            schema=schema,
        )
    expires_at = (
        host_stamp.astimezone(datetime.timezone.utc)
        + datetime.timedelta(days=HOST_STATE_MAX_AGE_DAYS)
    ).isoformat(timespec="seconds")
    return TrustResult(
        True,
        "TRUSTED",
        "private egress state is covered by configured internal CIDRs",
        expires_at=expires_at,
        egress_ip=str(egress),
        cidrs=rendered,
        schema=schema,
    )
