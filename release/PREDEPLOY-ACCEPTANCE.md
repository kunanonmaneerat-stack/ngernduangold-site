# Candidate-bound predeploy acceptance

This file is local evidence only. It does not authorize deployment,
publication, scheduling, traffic generation, or any external action.

- schema_version: `2`
- report_kind: `candidate-bound-predeploy-acceptance-v2`
- evaluated_at: `2026-08-25T08:08:31+00:00`
- expires_at: `2026-08-25T10:08:31+00:00`
- acceptance_contract_schema: `1`
- acceptance_policy_path: `.system_control/policy.json`
- acceptance_policy_sha256: `2bb5caa8653fcb8f2e13c676a143af3783f5d3eafa1bf5af48ef3dda228bd6c7`
- acceptance_max_age_hours: `2`
- acceptance_max_funnel_report_age_hours: `2`
- acceptance_future_skew_seconds: `300`
- acceptance_exclusive_expiry: `true`
- evidence_only: `true`
- external_action_authorized: `false`
- deployment_authorized: `false`
- publication_authority: `NOT_AUTHORIZED`
- final_verdict: `BLOCKED`
- candidate_artifact_integrity: `PASS`
- candidate_id: `sha256:245c6626f4db45d54e7823322bce4262ff93880f6415a679eb8b59f026a3f178`
- candidate_receipt_sha256: `7ebb89fb5542d03b3a9c6dcc65e7bca7272a0df9f2628647137ac7e9529d986f`
- candidate_archive_sha256: `245c6626f4db45d54e7823322bce4262ff93880f6415a679eb8b59f026a3f178`
- candidate_archive_member_count: `139`
- candidate_archive_bytes: `168233209`
- candidate_source_revision_scope: `git-worktree-excluding-candidate-and-declared-downstream-outputs-v1`
- candidate_source_revision_clean: `false`
- candidate_source_revision_working_tree_sha256: `96394835d7b3edb8fdfec93eb1f24e66fb75e6e49c97506a4ddc99e25f33f8be`
- candidate_excluded_generated_outputs: `["release/PREDEPLOY-ACCEPTANCE.md","release/RELEASE-FUNNEL-READINESS.json"]`
- release_id: `sha256:c84f4d10be940850979fca5622b5c6544371fadb0f0c36362f31d6289c1a7f59`
- manifest_schema: `2`
- manifest_file_count: `138`
- manifest_source_input_count: `14`
- official_snapshot_checked_at: `2026-08-25T02:05:06+00:00`
- official_snapshot_sha256: `d90a623d9cdafa0d36249c553de930a299e901372a40a4fdce93ad880823a995`
- source_registry_sha256: `f965ce081ca99b1df8446e007398e6ac011db5c9f2d1cc8aad9ee027c37b3ba1`
- official_source_decisions_sha256: `ed9f9b9fb38eb2c45f73383e20c79fd3778ebaab97cfae5f5a09f0713e35dea6`
- official_sources_configured: `31`
- official_sources_successful: `31`
- official_source_current_errors: `0`
- official_source_pending_reviews: `31`
- owner_review_packet_items: `31`
- affected_content_items: `16`
- affected_content_items_allowed: `0`
- affected_content_items_blocked: `16`
- calendar_process_state: `BLOCKED`
- calendar_sha256: `1ddaf076374c34469998bb4d15c373ec8d3617469775e1145c602d621ae8f203`
- calendar_decision_sha256: `43a2134099a52b1bf866b522d740fcab97e96f8874a46802aac2e9f79011d4f0`
- calendar_publishable_count: `0`
- calendar_structural_findings: `0`
- ga4_decision_trust: `UNTRUSTED`
- ga4_decision_evidence_sha256: `7e86bf87bbce340bc85a3ee84c8feaebb5e48f576115ae1535ede0ed113edb18`
- workspace_state: `DIRTY`
- workspace_clean: `false`
- funnel_report_path: `release/RELEASE-FUNNEL-READINESS.json`
- funnel_report_sha256: `94da9225a463d67a3fd8b17b60eb4b3d7e853e072c612eda3a3ceb3bb84caca9`
- funnel_report_evaluated_at: `2026-08-25T08:08:24+00:00`
- funnel_report_expires_at: `2026-08-25T10:08:24+00:00`
- funnel_release_contract_status: `PASS`
- funnel_score_descriptive: `80`
- funnel_publication_status: `NOT_AUTHORIZED`

Final decision: **BLOCKED** until separate authority and all live gates pass.
