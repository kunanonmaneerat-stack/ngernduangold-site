#!/usr/bin/env python3
"""Evidence contract for candidate-bound, non-authorizing predeploy acceptance."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PIPELINE = ROOT / "pipeline"
for directory in (TOOLS, PIPELINE):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import content_calendar_guard
import content_source_gate
import ga4_decision_trust
import release_candidate
import release_contract
import write_predeploy_acceptance as acceptance


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def load_json(relative: Path):
    return release_candidate._strict_json_loads(
        (ROOT / relative).read_text(encoding="utf-8")
    )


def main() -> int:
    document = (ROOT / acceptance.REPORT_PATH).read_text(encoding="utf-8")
    acceptance.check_report(ROOT)
    field = lambda name: acceptance.field(document, name)
    evaluated_at = acceptance._parse_time(field("evaluated_at"))
    expires_at = acceptance._parse_time(
        field("expires_at"), "predeploy expiry time"
    )
    policy_text = (ROOT / acceptance.POLICY_PATH).read_text(encoding="utf-8")
    policy = release_candidate._strict_json_loads(policy_text)
    acceptance_contract = policy["release_attestation"]["predeploy_acceptance"]

    candidate_raw = load_json(acceptance.CANDIDATE_RECEIPT_PATH)
    archive = ROOT / candidate_raw["archive"]["path"]
    candidate = release_candidate.verify(
        ROOT / "site", ROOT, archive, ROOT / acceptance.CANDIDATE_RECEIPT_PATH
    )
    manifest = load_json(Path("site") / release_contract.MANIFEST_NAME)
    snapshot = load_json(acceptance.SNAPSHOT_PATH)
    registry = load_json(acceptance.SOURCE_REGISTRY_PATH)
    funnel = load_json(acceptance.FUNNEL_REPORT_PATH)

    check(
        "report is canonical evidence and never action authority",
        field("schema_version") == str(acceptance.SCHEMA_VERSION)
        and field("report_kind") == acceptance.REPORT_KIND
        and field("evidence_only") == "true"
        and field("external_action_authorized") == "false"
        and field("deployment_authorized") == "false"
        and field("publication_authority") == "NOT_AUTHORIZED"
        and field("final_verdict") == "BLOCKED",
    )
    check(
        "report binds the exact release-attestation TTL policy",
        field("acceptance_contract_schema")
        == str(acceptance_contract["schema_version"])
        and field("acceptance_policy_path") == acceptance.POLICY_PATH.as_posix()
        and field("acceptance_policy_sha256")
        == release_candidate.sha256_bytes(policy_text.encode("utf-8"))
        and int(field("acceptance_max_age_hours"))
        == acceptance_contract["max_age_hours"]
        and int(field("acceptance_max_funnel_report_age_hours"))
        == acceptance_contract["max_funnel_report_age_hours"]
        and int(field("acceptance_future_skew_seconds"))
        == acceptance_contract["future_skew_seconds"]
        and field("acceptance_exclusive_expiry") == "true"
        and expires_at
        == evaluated_at + timedelta(hours=acceptance_contract["max_age_hours"]),
    )
    check(
        "report binds the exact verified local candidate",
        field("candidate_artifact_integrity") == "PASS"
        and field("candidate_id") == candidate["candidate_id"]
        and field("candidate_receipt_sha256")
        == release_candidate.sha256_file(ROOT / acceptance.CANDIDATE_RECEIPT_PATH)
        and field("candidate_archive_sha256") == candidate["archive"]["sha256"]
        and int(field("candidate_archive_member_count"))
        == candidate["archive"]["member_count"]
        and int(field("candidate_archive_bytes")) == candidate["archive"]["bytes"],
    )
    source_revision = candidate["source_revision"]
    check(
        "report binds the explicit source-revision scope",
        field("candidate_source_revision_scope") == source_revision["scope"]
        and field("candidate_source_revision_working_tree_sha256")
        == source_revision["working_tree_content_sha256"]
        and field("candidate_source_revision_clean")
        == str(source_revision["clean"]).lower()
        and json.loads(field("candidate_excluded_generated_outputs"))
        == list(release_candidate.SOURCE_REVISION_OUTPUT_EXCLUSIONS)
        and field("workspace_clean") == str(source_revision["clean"]).lower(),
    )
    check(
        "report binds the exact local release manifest",
        field("release_id") == manifest["release_id"] == candidate["release_id"]
        and int(field("manifest_schema")) == manifest["schema_version"]
        and int(field("manifest_file_count")) == manifest["file_count"]
        and int(field("manifest_source_input_count"))
        == len(manifest.get("source_sha256") or {})
        and not release_contract.manifest_findings(manifest, ROOT / "site", ROOT),
    )
    check(
        "release-funnel JSON is separate, canonical, and candidate-bound",
        field("funnel_report_path") == acceptance.FUNNEL_REPORT_PATH.as_posix()
        and field("funnel_report_sha256")
        == release_candidate.sha256_file(ROOT / acceptance.FUNNEL_REPORT_PATH)
        and field("funnel_report_evaluated_at") == funnel["evaluated_at"]
        and acceptance._parse_time(field("funnel_report_expires_at"))
        == acceptance._parse_time(funnel["evaluated_at"])
        + timedelta(hours=acceptance_contract["max_funnel_report_age_hours"])
        and field("funnel_release_contract_status")
        == funnel["release_contract_status"]
        and int(field("funnel_score_descriptive")) == funnel["score_descriptive"]
        and field("funnel_publication_status") == funnel["publication"]["status"]
        and funnel["release"]["local_release_id"] == candidate["release_id"]
        and funnel["external_action_authorized"] is False,
    )
    summary = snapshot["summary"]
    pending = snapshot["review_required"]
    check(
        "report binds the official-source snapshot",
        field("official_snapshot_checked_at") == snapshot["checked_at"]
        and field("official_snapshot_sha256")
        == release_candidate.sha256_file(ROOT / acceptance.SNAPSHOT_PATH)
        and field("source_registry_sha256")
        == release_candidate.sha256_file(ROOT / acceptance.SOURCE_REGISTRY_PATH)
        and int(field("official_sources_configured")) == summary["configured_sources"]
        and int(field("official_sources_successful")) == summary["successful_sources"]
        and int(field("official_source_current_errors")) == summary["current_errors"]
        and int(field("official_source_pending_reviews")) == len(pending),
    )
    packet = (ROOT / acceptance.OWNER_PACKET_PATH).read_text(encoding="utf-8")
    check(
        "report binds the owner review queue without acknowledging it",
        int(field("owner_review_packet_items"))
        == len(re.findall(r"^- \[ \] `", packet, re.M))
        and "acknowledged_this_run: `0`" in packet,
    )
    content_results = [
        content_source_gate.evaluate_content_source_gate(
            content_id,
            ROOT / acceptance.SOURCE_REGISTRY_PATH,
            ROOT / acceptance.SNAPSHOT_PATH,
            library_name=registry.get("library"),
            now=evaluated_at,
        )
        for content_id in sorted(registry["items"])
    ]
    allowed = sum(1 for result in content_results if result.allowed)
    check(
        "report binds content-scoped source decisions",
        int(field("affected_content_items")) == len(content_results)
        and field("official_source_decisions_sha256")
        == acceptance._canonical_sha256([
            {
                "content_id": result.content_id,
                "allowed": result.allowed,
                "source_ids": list(result.source_ids),
                "failures": list(result.failures),
            }
            for result in content_results
        ])
        and int(field("affected_content_items_allowed")) == allowed
        and int(field("affected_content_items_blocked"))
        == len(content_results) - allowed,
    )
    calendar = content_calendar_guard.evaluate(
        ROOT / acceptance.CALENDAR_PATH, repo=ROOT, now=evaluated_at
    )
    structural = sum(
        1
        for finding in calendar["findings"]
        if finding.get("classification")
        not in {
            content_calendar_guard.PUBLICATION_BLOCKER,
            content_calendar_guard.REPORT_ONLY,
        }
    )
    check(
        "report binds the calendar decision without promoting a placement",
        field("calendar_sha256")
        == release_candidate.sha256_file(ROOT / acceptance.CALENDAR_PATH)
        and field("calendar_decision_sha256")
        == acceptance._canonical_sha256({
            "process_state": calendar.get("process_state"),
            "counts": calendar["counts"],
            "findings": calendar["findings"],
        })
        and field("calendar_process_state") == calendar["process_state"]
        and int(field("calendar_publishable_count"))
        == calendar["counts"]["publishable"]
        and int(field("calendar_structural_findings")) == structural
        and calendar["counts"]["publishable"] == 0,
    )
    ga4 = ga4_decision_trust.evaluate_ga4_decision_trust(
        ROOT / acceptance.POLICY_PATH,
        ROOT / acceptance.HOST_IP_PATH,
        now=evaluated_at,
    )
    check(
        "report binds privacy-safe GA4 trust only",
        field("ga4_decision_trust") == ga4.label
        and re.fullmatch(
            r"[0-9a-f]{64}", field("ga4_decision_evidence_sha256")
        )
        and field("ga4_decision_trust") in {"TRUSTED", "UNTRUSTED"}
        and "egress" not in document.casefold()
        and "cidr" not in document.casefold(),
    )
    check(
        "essential package members exist",
        all(
            (ROOT / "site" / name).is_file()
            for name in (
                "index.html",
                "sitemap.xml",
                "robots.txt",
                "_headers",
                "_redirects",
                release_contract.MANIFEST_NAME,
            )
        ),
    )
    check(
        "BLOCKED is independent of the descriptive funnel score",
        field("final_verdict") == "BLOCKED"
        and field("publication_authority") == "NOT_AUTHORIZED"
        and funnel["publication"]["authority_granted"] is False,
    )
    print("predeploy acceptance: 13/13 PASS (decision remains BLOCKED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
