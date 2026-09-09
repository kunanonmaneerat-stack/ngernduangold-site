# GA4 coverage attestation contract

This contract prevents an old 28-day clean-window start from surviving a
change to the internal-traffic CIDR set. It is local-only, fail-closed, and
must not contain raw IP addresses or CIDR values in public output.

## Activation evidence

At the instant an authenticated, read-only GA4 Admin inspection confirms an
`Active` + `Exclude` filter and an exact normalized-set match:

1. Record an immutable sibling Admin-observation JSON file beside the private
   GA4 policy.
2. Set `observed_at` to the real timezone-aware inspection instant.
3. Set the private policy `verified_at` to the same Asia/Bangkok business date.
   Never backdate it.
4. Record only the SHA-256 fingerprint of the sorted, unique, normalized CIDR
   set. Do not put raw network values in the observation.
5. Bind the private policy to the exact observation bytes with
   `admin_observation_contract.sha256`.

The private `ga4.internal_traffic.coverage_attestation` object must contain:

```json
{
  "schema_version": 1,
  "source": "authenticated_ga4_admin_read_only",
  "verified_at": "YYYY-MM-DD",
  "attested_at": "YYYY-MM-DDTHH:MM:SS+07:00",
  "cidr_set_sha256": "64 lowercase hex characters",
  "admin_observation_contract": {
    "schema_version": 1,
    "default": "one-safe-sibling-filename.json",
    "sha256": "64 lowercase hex characters"
  }
}
```

The Admin observation must be strict JSON schema 1 with:

- `mode: authenticated_browser_read_only`
- `external_mutations: []`
- timezone-aware `observed_at` equal to `attested_at`
- `internal_traffic.filter_state: Active`
- `internal_traffic.filter_operation: Exclude`
- `internal_traffic.exact_normalized_set_match: true`
- `internal_traffic.raw_network_values_emitted: false`
- both condition counts equal to the normalized CIDR-set cardinality
- `internal_traffic.cidr_set_sha256` equal to the policy fingerprint

Any CIDR addition, removal, or material range change invalidates the old
attestation. Capture a new authenticated observation, reset `verified_at` to
that activation date, and start a new 28-day clean window. Do not edit,
backfill, or promote an older observation.

The existing 2026-08-24 observation is historical diagnostic evidence only;
it does not prove the clean-window activation date and must not be upgraded in
place.

Local verification:

```powershell
.venv\Scripts\python.exe pipeline\ga4_readiness_report.py --repo-root .
```

`READY` is valid only when the runtime trust, attestation binding, full 28-day
window, and atomic schema-v3 GA4 bundle all pass together.
