#!/usr/bin/env python3
"""Write/check candidate-bound predeploy acceptance evidence.

This report is a downstream consumer of the local candidate receipt.  It never
authorizes deployment or publication, and it is written only after the exact
candidate, manifest, source review, calendar, and analytics trust inputs can be
read.  Missing or ambiguous evidence fails closed and leaves an existing report
untouched.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import content_calendar_guard
import content_source_gate
import ga4_decision_trust
import release_candidate
import release_contract


REPORT_PATH = Path("release/PREDEPLOY-ACCEPTANCE.md")
FUNNEL_REPORT_PATH = Path("release/RELEASE-FUNNEL-READINESS.json")
CANDIDATE_RECEIPT_PATH = Path("release/candidate-receipt.json")
SNAPSHOT_PATH = Path("automation-log/knowledge-base/official-news-snapshot.json")
SOURCE_REGISTRY_PATH = Path(
    "automation-log/knowledge-base/content-source-registry.json"
)
OWNER_PACKET_PATH = Path("automation-log/cowork-inbox/OFFICIAL-NEWS-REVIEW.md")
POLICY_PATH = Path(".system_control/policy.json")
HOST_IP_PATH = Path(".system_control/host_ip.json")
CALENDAR_PATH = Path(".system_control/content_calendar.json")
SCHEMA_VERSION = 2
REPORT_KIND = "candidate-bound-predeploy-acceptance-v2"
POLICY_CONTRACT_PATH = "release_attestation.predeploy_acceptance"
POLICY_CONTRACT_FIELDS = {
    "schema_version",
    "max_age_hours",
    "max_funnel_report_age_hours",
    "future_skew_seconds",
    "exclusive_expiry",
}


class AcceptanceError(RuntimeError):
    """Raised before incomplete evidence can be written as an attestation."""


def _read_text(path: Path, label: str) -> str:
    if path.is_symlink():
        raise AcceptanceError(label + " must not be a symlink")
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise AcceptanceError(label + " is missing or unreadable") from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise AcceptanceError(label + " changed while it was read")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise AcceptanceError(label + " is not UTF-8") from exc


def _read_json(path: Path, label: str):
    try:
        return release_candidate._strict_json_loads(_read_text(path, label))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AcceptanceError(label + " is invalid JSON") from exc


def _integer(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AcceptanceError(label + " must be a non-negative integer")
    return value


def _positive_integer(value, label: str) -> int:
    parsed = _integer(value, label)
    if parsed < 1:
        raise AcceptanceError(label + " must be a positive integer")
    return parsed


def _add_hours(moment: datetime, hours: int, label: str) -> datetime:
    try:
        return moment + timedelta(hours=hours)
    except (OverflowError, TypeError) as exc:
        raise AcceptanceError(label + " is out of range") from exc


def _require_aware_datetime(value, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AcceptanceError(label + " must include a UTC offset")
    return value


def _policy_contract(repo: Path) -> dict:
    policy_path = repo.resolve() / POLICY_PATH
    policy_text = _read_text(policy_path, "release policy")
    try:
        policy = release_candidate._strict_json_loads(policy_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AcceptanceError("release policy is invalid JSON") from exc
    if not isinstance(policy, dict):
        raise AcceptanceError("release policy must be an object")
    release_attestation = policy.get("release_attestation")
    if not isinstance(release_attestation, dict):
        raise AcceptanceError("release-attestation policy is missing")
    contract = release_attestation.get("predeploy_acceptance")
    if not isinstance(contract, dict) or set(contract) != POLICY_CONTRACT_FIELDS:
        raise AcceptanceError("predeploy-acceptance policy contract differs")
    schema = contract.get("schema_version")
    max_age = contract.get("max_age_hours")
    max_funnel_age = contract.get("max_funnel_report_age_hours")
    future_skew = contract.get("future_skew_seconds")
    if type(schema) is not int or schema != 1:
        raise AcceptanceError("predeploy-acceptance policy schema is unsupported")
    max_age = _positive_integer(max_age, "predeploy max age")
    max_funnel_age = _positive_integer(
        max_funnel_age, "predeploy funnel-report max age"
    )
    future_skew = _integer(future_skew, "predeploy future skew")
    if contract.get("exclusive_expiry") is not True:
        raise AcceptanceError("predeploy expiry must be exclusive")
    return {
        "schema_version": schema,
        "max_age_hours": max_age,
        "max_funnel_report_age_hours": max_funnel_age,
        "future_skew_seconds": future_skew,
        "exclusive_expiry": True,
        "policy_sha256": release_candidate.sha256_bytes(
            policy_text.encode("utf-8")
        ),
    }


def _render_value(value) -> str:
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, int) and not isinstance(value, bool):
        rendered = str(value)
    elif isinstance(value, str):
        rendered = value
    else:
        raise AcceptanceError("predeploy field has an unsupported value type")
    if not rendered or "`" in rendered or "\n" in rendered or "\r" in rendered:
        raise AcceptanceError("predeploy field contains unsafe Markdown text")
    return rendered


def _canonical_sha256(value) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AcceptanceError("predeploy fingerprint input is invalid") from exc
    return release_candidate.sha256_bytes(encoded)


FIELD_ORDER = (
    "schema_version",
    "report_kind",
    "evaluated_at",
    "expires_at",
    "acceptance_contract_schema",
    "acceptance_policy_path",
    "acceptance_policy_sha256",
    "acceptance_max_age_hours",
    "acceptance_max_funnel_report_age_hours",
    "acceptance_future_skew_seconds",
    "acceptance_exclusive_expiry",
    "evidence_only",
    "external_action_authorized",
    "deployment_authorized",
    "publication_authority",
    "final_verdict",
    "candidate_artifact_integrity",
    "candidate_id",
    "candidate_receipt_sha256",
    "candidate_archive_sha256",
    "candidate_archive_member_count",
    "candidate_archive_bytes",
    "candidate_source_revision_scope",
    "candidate_source_revision_clean",
    "candidate_source_revision_working_tree_sha256",
    "candidate_excluded_generated_outputs",
    "release_id",
    "manifest_schema",
    "manifest_file_count",
    "manifest_source_input_count",
    "official_snapshot_checked_at",
    "official_snapshot_sha256",
    "source_registry_sha256",
    "official_source_decisions_sha256",
    "official_sources_configured",
    "official_sources_successful",
    "official_source_current_errors",
    "official_source_pending_reviews",
    "owner_review_packet_items",
    "affected_content_items",
    "affected_content_items_allowed",
    "affected_content_items_blocked",
    "calendar_process_state",
    "calendar_sha256",
    "calendar_decision_sha256",
    "calendar_publishable_count",
    "calendar_structural_findings",
    "ga4_decision_trust",
    "ga4_decision_evidence_sha256",
    "workspace_state",
    "workspace_clean",
    "funnel_report_path",
    "funnel_report_sha256",
    "funnel_report_evaluated_at",
    "funnel_report_expires_at",
    "funnel_release_contract_status",
    "funnel_score_descriptive",
    "funnel_publication_status",
)
SHA256_FIELDS = {
    "acceptance_policy_sha256",
    "candidate_receipt_sha256",
    "candidate_archive_sha256",
    "candidate_source_revision_working_tree_sha256",
    "official_snapshot_sha256",
    "source_registry_sha256",
    "official_source_decisions_sha256",
    "calendar_sha256",
    "calendar_decision_sha256",
    "ga4_decision_evidence_sha256",
    "funnel_report_sha256",
}


def render_document(evidence: dict) -> str:
    if set(evidence) != set(FIELD_ORDER):
        missing = sorted(set(FIELD_ORDER) - set(evidence))
        extra = sorted(set(evidence) - set(FIELD_ORDER))
        raise AcceptanceError(
            "predeploy evidence fields differ (missing=%s extra=%s)"
            % (missing, extra)
        )
    if (
        evidence["schema_version"] != SCHEMA_VERSION
        or evidence["report_kind"] != REPORT_KIND
        or evidence["evidence_only"] is not True
        or evidence["external_action_authorized"] is not False
        or evidence["deployment_authorized"] is not False
        or evidence["publication_authority"] != "NOT_AUTHORIZED"
        or evidence["final_verdict"] != "BLOCKED"
        or evidence["candidate_artifact_integrity"] != "PASS"
    ):
        raise AcceptanceError("predeploy evidence overclaims authority or integrity")
    if any(
        not isinstance(evidence.get(name), str)
        or re.fullmatch(r"[0-9a-f]{64}", evidence[name]) is None
        for name in SHA256_FIELDS
    ):
        raise AcceptanceError("predeploy evidence contains an invalid SHA-256 binding")
    lines = [
        "# Candidate-bound predeploy acceptance",
        "",
        "This file is local evidence only. It does not authorize deployment,",
        "publication, scheduling, traffic generation, or any external action.",
        "",
    ]
    lines.extend(
        "- %s: `%s`" % (name, _render_value(evidence[name]))
        for name in FIELD_ORDER
    )
    lines.extend(("", "Final decision: **BLOCKED** until separate authority and all live gates pass.", ""))
    return "\n".join(lines)


def _funnel_currentness(funnel: dict, *, now: datetime, contract: dict):
    funnel_evaluated_at = _parse_time(
        funnel.get("evaluated_at"), "release/funnel evaluation time"
    )
    funnel_expires_at = _add_hours(
        funnel_evaluated_at,
        contract["max_funnel_report_age_hours"],
        "release/funnel expiry",
    )
    _validate_decision_window(
        evaluated_at=funnel_evaluated_at,
        expires_at=funnel_expires_at,
        as_of=now,
        future_skew_seconds=contract["future_skew_seconds"],
        label="release/funnel readiness report",
    )
    return funnel_evaluated_at, funnel_expires_at


def collect_evidence(repo: Path, *, now: datetime) -> dict:
    repo = repo.resolve()
    _require_aware_datetime(now, "evaluation time")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    acceptance_contract = _policy_contract(repo)
    expires_at = _add_hours(
        now, acceptance_contract["max_age_hours"], "predeploy expiry"
    )

    receipt_path = repo / CANDIDATE_RECEIPT_PATH
    candidate_receipt_text = _read_text(receipt_path, "candidate receipt")
    try:
        raw_candidate = release_candidate._strict_json_loads(candidate_receipt_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AcceptanceError("candidate receipt is invalid JSON") from exc
    if not isinstance(raw_candidate, dict):
        raise AcceptanceError("candidate receipt must be an object")
    archive_value = (raw_candidate.get("archive") or {}).get("path")
    if not isinstance(archive_value, str) or not archive_value:
        raise AcceptanceError("candidate archive path is missing")
    archive = (repo / archive_value).resolve()
    candidate = release_candidate.verify(
        repo / "site", repo, archive, receipt_path
    )
    if _read_text(receipt_path, "candidate receipt") != candidate_receipt_text:
        raise AcceptanceError("candidate receipt changed during verification")
    source_revision = candidate.get("source_revision") or {}
    expected_exclusions = list(release_candidate.SOURCE_REVISION_OUTPUT_EXCLUSIONS)
    source_hash = source_revision.get("working_tree_content_sha256")
    if (
        source_revision.get("scope") != release_candidate.SOURCE_REVISION_SCOPE
        or source_revision.get("excluded_generated_outputs") != expected_exclusions
        or not isinstance(source_revision.get("clean"), bool)
        or not isinstance(source_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source_hash)
    ):
        raise AcceptanceError("candidate source-revision contract differs")

    manifest = _read_json(
        repo / "site" / release_contract.MANIFEST_NAME, "release manifest"
    )
    if not isinstance(manifest, dict):
        raise AcceptanceError("release manifest must be an object")

    funnel_path = repo / FUNNEL_REPORT_PATH
    funnel_text = _read_text(funnel_path, "release/funnel readiness report")
    try:
        funnel = release_candidate._strict_json_loads(funnel_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AcceptanceError("release/funnel readiness report is invalid JSON") from exc
    if not isinstance(funnel, dict):
        raise AcceptanceError("release/funnel readiness report must be an object")
    funnel_evaluated_at, funnel_expires_at = _funnel_currentness(
        funnel, now=now, contract=acceptance_contract
    )
    funnel_release = funnel.get("release") or {}
    funnel_publication = funnel.get("publication") or {}
    if (
        funnel.get("schema_version") != 1
        or funnel.get("mode") != "local"
        or funnel.get("assessment_scope") != "release_funnel_contract_only"
        or funnel.get("score_is_authorization") is not False
        or funnel.get("external_action_authorized") is not False
        or funnel.get("publication_authority_granted") is not False
        or funnel.get("release_contract_status") not in {"PASS", "BLOCKED"}
        or funnel_release.get("local_release_id") != candidate.get("release_id")
        or funnel_publication.get("status") != "NOT_AUTHORIZED"
        or funnel_publication.get("authority_granted") is not False
    ):
        raise AcceptanceError(
            "release/funnel readiness report is stale, unsupported, or over-authorizing"
        )

    snapshot_text = _read_text(repo / SNAPSHOT_PATH, "official-source snapshot")
    registry_text = _read_text(repo / SOURCE_REGISTRY_PATH, "source registry")
    try:
        snapshot = release_candidate._strict_json_loads(snapshot_text)
        registry = release_candidate._strict_json_loads(registry_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AcceptanceError("official-source evidence is invalid JSON") from exc
    if not isinstance(snapshot, dict) or not isinstance(registry, dict):
        raise AcceptanceError("official-source evidence must be JSON objects")
    summary = snapshot.get("summary")
    pending = snapshot.get("review_required")
    items = registry.get("items")
    if not isinstance(summary, dict) or not isinstance(pending, list):
        raise AcceptanceError("official-source snapshot shape is unsupported")
    if not isinstance(items, dict) or not items:
        raise AcceptanceError("source registry has no content items")
    content_results = [
        content_source_gate.evaluate_content_source_gate(
            content_id,
            repo / SOURCE_REGISTRY_PATH,
            repo / SNAPSHOT_PATH,
            library_name=registry.get("library"),
            now=now,
            _registry_document=registry,
            _snapshot_document=snapshot,
        )
        for content_id in sorted(items)
    ]
    content_allowed = sum(1 for result in content_results if result.allowed)
    source_decisions_sha256 = _canonical_sha256([
        {
            "content_id": result.content_id,
            "allowed": result.allowed,
            "source_ids": list(result.source_ids),
            "failures": list(result.failures),
        }
        for result in content_results
    ])

    packet = _read_text(repo / OWNER_PACKET_PATH, "official-source owner packet")
    packet_items = len(re.findall(r"^- \[ \] `", packet, re.M))

    calendar_text = _read_text(repo / CALENDAR_PATH, "content calendar")
    calendar = content_calendar_guard.evaluate(
        repo / CALENDAR_PATH, repo=repo, now=now
    )
    calendar_counts = calendar.get("counts") or {}
    calendar_findings = calendar.get("findings") or []
    structural = sum(
        1
        for finding in calendar_findings
        if isinstance(finding, dict)
        and finding.get("classification") not in {
            content_calendar_guard.PUBLICATION_BLOCKER,
            content_calendar_guard.REPORT_ONLY,
        }
    )
    calendar_decision_sha256 = _canonical_sha256({
        "process_state": calendar.get("process_state"),
        "counts": calendar_counts,
        "findings": calendar_findings,
    })

    try:
        ga4 = ga4_decision_trust.evaluate_ga4_decision_trust(
            repo / POLICY_PATH, repo / HOST_IP_PATH, now=now
        )
        ga4_label = ga4.label if ga4.label in {"TRUSTED", "UNTRUSTED"} else "UNKNOWN"
        ga4_fingerprint = _canonical_sha256({
            "trusted": ga4.trusted is True,
            "label": ga4_label,
            "expires_at": ga4.expires_at,
            "schema": ga4.schema,
            "reason_sha256": release_candidate.sha256_bytes(
                str(ga4.reason).encode("utf-8")
            ),
        })
    except Exception:
        ga4_label = "UNKNOWN"
        ga4_fingerprint = _canonical_sha256({
            "trusted": False,
            "label": "UNKNOWN",
            "expires_at": None,
            "schema": "unknown",
            "reason_sha256": "0" * 64,
        })

    workspace_clean = source_revision.get("clean") is True
    workspace_state = "CLEAN" if workspace_clean else "DIRTY"
    exclusions_text = json.dumps(
        expected_exclusions, ensure_ascii=False, separators=(",", ":")
    )
    if _read_text(funnel_path, "release/funnel readiness report") != funnel_text:
        raise AcceptanceError("release/funnel readiness report changed during evaluation")
    if _read_text(repo / SNAPSHOT_PATH, "official-source snapshot") != snapshot_text:
        raise AcceptanceError("official-source snapshot changed during evaluation")
    if _read_text(repo / SOURCE_REGISTRY_PATH, "source registry") != registry_text:
        raise AcceptanceError("source registry changed during evaluation")
    if _read_text(repo / CALENDAR_PATH, "content calendar") != calendar_text:
        raise AcceptanceError("content calendar changed during evaluation")
    if _policy_contract(repo) != acceptance_contract:
        raise AcceptanceError("predeploy-acceptance policy changed during evaluation")
    candidate_after = release_candidate.verify(
        repo / "site", repo, archive, receipt_path
    )
    if (
        candidate_after != candidate
        or _read_text(receipt_path, "candidate receipt") != candidate_receipt_text
    ):
        raise AcceptanceError("candidate evidence changed during evaluation")
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "evaluated_at": now.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "acceptance_contract_schema": acceptance_contract["schema_version"],
        "acceptance_policy_path": POLICY_PATH.as_posix(),
        "acceptance_policy_sha256": acceptance_contract["policy_sha256"],
        "acceptance_max_age_hours": acceptance_contract["max_age_hours"],
        "acceptance_max_funnel_report_age_hours": acceptance_contract[
            "max_funnel_report_age_hours"
        ],
        "acceptance_future_skew_seconds": acceptance_contract[
            "future_skew_seconds"
        ],
        "acceptance_exclusive_expiry": acceptance_contract["exclusive_expiry"],
        "evidence_only": True,
        "external_action_authorized": False,
        "deployment_authorized": False,
        "publication_authority": "NOT_AUTHORIZED",
        "final_verdict": "BLOCKED",
        "candidate_artifact_integrity": "PASS",
        "candidate_id": candidate["candidate_id"],
        "candidate_receipt_sha256": release_candidate.sha256_bytes(
            candidate_receipt_text.encode("utf-8")
        ),
        "candidate_archive_sha256": candidate["archive"]["sha256"],
        "candidate_archive_member_count": _integer(
            candidate["archive"].get("member_count"), "candidate member count"
        ),
        "candidate_archive_bytes": _integer(
            candidate["archive"].get("bytes"), "candidate byte count"
        ),
        "candidate_source_revision_scope": str(source_revision.get("scope") or "UNKNOWN"),
        "candidate_source_revision_clean": source_revision.get("clean") is True,
        "candidate_source_revision_working_tree_sha256": str(
            source_revision.get("working_tree_content_sha256") or "UNKNOWN"
        ),
        "candidate_excluded_generated_outputs": exclusions_text,
        "release_id": candidate["release_id"],
        "manifest_schema": _integer(manifest.get("schema_version"), "manifest schema"),
        "manifest_file_count": _integer(manifest.get("file_count"), "manifest file count"),
        "manifest_source_input_count": _integer(
            candidate.get("manifest_source_input_count"), "manifest source-input count"
        ),
        "official_snapshot_checked_at": str(snapshot.get("checked_at") or "UNKNOWN"),
        "official_snapshot_sha256": release_candidate.sha256_bytes(
            snapshot_text.encode("utf-8")
        ),
        "source_registry_sha256": release_candidate.sha256_bytes(
            registry_text.encode("utf-8")
        ),
        "official_source_decisions_sha256": source_decisions_sha256,
        "official_sources_configured": _integer(
            summary.get("configured_sources"), "configured source count"
        ),
        "official_sources_successful": _integer(
            summary.get("successful_sources"), "successful source count"
        ),
        "official_source_current_errors": _integer(
            summary.get("current_errors"), "source error count"
        ),
        "official_source_pending_reviews": len(pending),
        "owner_review_packet_items": packet_items,
        "affected_content_items": len(content_results),
        "affected_content_items_allowed": content_allowed,
        "affected_content_items_blocked": len(content_results) - content_allowed,
        "calendar_process_state": str(calendar.get("process_state") or "UNKNOWN"),
        "calendar_sha256": release_candidate.sha256_bytes(
            calendar_text.encode("utf-8")
        ),
        "calendar_decision_sha256": calendar_decision_sha256,
        "calendar_publishable_count": _integer(
            calendar_counts.get("publishable", 0), "calendar publishable count"
        ),
        "calendar_structural_findings": structural,
        "ga4_decision_trust": ga4_label,
        "ga4_decision_evidence_sha256": ga4_fingerprint,
        "workspace_state": workspace_state,
        "workspace_clean": workspace_clean,
        "funnel_report_path": FUNNEL_REPORT_PATH.as_posix(),
        "funnel_report_sha256": release_candidate.sha256_bytes(
            funnel_text.encode("utf-8")
        ),
        "funnel_report_evaluated_at": str(funnel.get("evaluated_at")),
        "funnel_report_expires_at": funnel_expires_at.astimezone(
            timezone.utc
        ).isoformat(timespec="seconds"),
        "funnel_release_contract_status": str(
            funnel.get("release_contract_status") or "UNKNOWN"
        ),
        "funnel_score_descriptive": _integer(
            funnel.get("score_descriptive"), "funnel descriptive score"
        ),
        "funnel_publication_status": str(
            funnel_publication.get("status") or "UNKNOWN"
        ),
    }


def _atomic_write(path: Path, document: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _parse_time(raw, label: str = "evaluation time") -> datetime:
    if not isinstance(raw, str) or not raw:
        raise AcceptanceError(label + " is invalid")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AcceptanceError(label + " is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AcceptanceError(label + " must include a UTC offset")
    return parsed


def _validate_decision_window(
    *,
    evaluated_at: datetime,
    expires_at: datetime,
    as_of: datetime,
    future_skew_seconds: int,
    label: str,
) -> None:
    for value, value_label in (
        (evaluated_at, label + " evaluation time"),
        (expires_at, label + " expiry time"),
        (as_of, label + " decision time"),
    ):
        _require_aware_datetime(value, value_label)
    evaluated_utc = evaluated_at.astimezone(timezone.utc)
    expires_utc = expires_at.astimezone(timezone.utc)
    as_of_utc = as_of.astimezone(timezone.utc)
    if evaluated_utc > as_of_utc:
        if (evaluated_utc - as_of_utc).total_seconds() > future_skew_seconds:
            raise AcceptanceError(label + " evaluation time exceeds future skew")
        raise AcceptanceError(label + " is not yet valid")
    if as_of_utc >= expires_utc:
        raise AcceptanceError(label + " is stale")


def _validated_report_contract(repo: Path, document: str):
    contract = _policy_contract(repo)
    expected_fields = {
        "schema_version": str(SCHEMA_VERSION),
        "report_kind": REPORT_KIND,
        "acceptance_contract_schema": str(contract["schema_version"]),
        "acceptance_policy_path": POLICY_PATH.as_posix(),
        "acceptance_policy_sha256": contract["policy_sha256"],
        "acceptance_max_age_hours": str(contract["max_age_hours"]),
        "acceptance_max_funnel_report_age_hours": str(
            contract["max_funnel_report_age_hours"]
        ),
        "acceptance_future_skew_seconds": str(contract["future_skew_seconds"]),
        "acceptance_exclusive_expiry": "true",
    }
    for name, expected in expected_fields.items():
        if field(document, name) != expected:
            raise AcceptanceError(
                "predeploy acceptance policy binding is stale: " + name
            )
    evaluated_at = _parse_time(
        field(document, "evaluated_at"), "predeploy evaluation time"
    )
    expires_at = _parse_time(
        field(document, "expires_at"), "predeploy expiry time"
    )
    expected_expiry = _add_hours(
        evaluated_at, contract["max_age_hours"], "predeploy expiry"
    )
    if expires_at != expected_expiry:
        raise AcceptanceError("predeploy expiry does not match the policy TTL")
    return evaluated_at, expires_at, contract


def field(document: str, name: str) -> str:
    match = re.search(r"^- " + re.escape(name) + r": `([^`]*)`\s*$", document, re.M)
    if not match:
        raise AcceptanceError("missing predeploy field: " + name)
    return match.group(1)


def write_report(repo: Path, *, now: datetime) -> Path:
    document = render_document(collect_evidence(repo, now=now))
    destination = repo.resolve() / REPORT_PATH
    _atomic_write(destination, document)
    return destination


def _check_integrity_document(repo: Path, document: str, evaluated_at: datetime) -> None:
    expected = render_document(collect_evidence(repo, now=evaluated_at))
    if document != expected:
        raise AcceptanceError(
            "predeploy acceptance report is non-canonical or its evidence drifted"
        )


def check_integrity(repo: Path) -> None:
    repo = repo.resolve()
    destination = repo / REPORT_PATH
    current = _read_text(destination, "predeploy acceptance report")
    evaluated_at, _, _ = _validated_report_contract(repo, current)
    _check_integrity_document(repo, current, evaluated_at)
    if _read_text(destination, "predeploy acceptance report") != current:
        raise AcceptanceError("predeploy acceptance report changed during validation")


def check_report(repo: Path, *, as_of: datetime | None = None) -> None:
    repo = repo.resolve()
    destination = repo / REPORT_PATH
    current = _read_text(destination, "predeploy acceptance report")
    evaluated_at, expires_at, contract = _validated_report_contract(repo, current)
    decision_time = as_of if as_of is not None else datetime.now(timezone.utc)
    _require_aware_datetime(decision_time, "predeploy decision time")
    _validate_decision_window(
        evaluated_at=evaluated_at,
        expires_at=expires_at,
        as_of=decision_time,
        future_skew_seconds=contract["future_skew_seconds"],
        label="predeploy acceptance report",
    )
    _check_integrity_document(repo, current, evaluated_at)
    current_evidence = collect_evidence(repo, now=decision_time)
    drifted = [
        name
        for name in FIELD_ORDER
        if name not in {"evaluated_at", "expires_at"}
        and field(current, name) != _render_value(current_evidence[name])
    ]
    if drifted:
        raise AcceptanceError(
            "predeploy acceptance current evidence drifted: "
            + ", ".join(drifted)
        )
    if _read_text(destination, "predeploy acceptance report") != current:
        raise AcceptanceError("predeploy acceptance report changed during validation")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("write", "check", "check-integrity"))
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--now", help="timezone-aware ISO-8601 instant")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    try:
        if args.command == "write":
            now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
            path = write_report(repo, now=now)
            print("predeploy acceptance: BLOCKED evidence -> " + str(path))
        elif args.command == "check":
            as_of = (
                _parse_time(args.now, "predeploy decision time")
                if args.now else None
            )
            check_report(repo, as_of=as_of)
            print(
                "predeploy acceptance: PASS "
                "(current canonical evidence; decision BLOCKED)"
            )
        else:
            if args.now:
                raise AcceptanceError("--now is not valid with check-integrity")
            check_integrity(repo)
            print(
                "predeploy acceptance: PASS "
                "(historical integrity only; decision BLOCKED)"
            )
    except (AcceptanceError, release_candidate.CandidateError) as exc:
        print("predeploy acceptance: FAIL " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
