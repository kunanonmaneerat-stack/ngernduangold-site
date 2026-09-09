#!/usr/bin/env python3
"""Static contract for Netlify's fail-closed build-input trigger."""

from pathlib import Path
import tomllib

import release_contract


ROOT = Path(__file__).resolve().parents[1]


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def main() -> int:
    config = tomllib.loads((ROOT / "netlify.toml").read_text(encoding="utf-8"))
    build = config["build"]
    command = build["command"]
    ignore = build["ignore"]

    check("site build runs merchant, release-manifest, smoke, and readiness gates",
          "build_site.py" in command and
          "tools/write_release_manifest.py" in command and
          "tools/postdeploy_smoke.py" in command and
          "tools/release_funnel_readiness.py" in command and
          "--require-local-ready" in command)
    critical = (
        ".system_control/policy.json",
        ".system_control/merchant_offers.json",
        ".system_control/content_manifest.json",
        "release/funnel_pilot.json",
        "pipeline/ga4_pull.py",
        "pipeline/ga4_schema.py",
        "tools/comply_gate_stitch.py",
        "tools/merchant_offer_gate.py",
        "tools/postdeploy_smoke.py",
        "tools/release_contract.py",
        "tools/release_funnel_readiness.py",
        "tools/write_release_manifest.py",
    )
    first_check = ignore.split(";", 1)[0]
    check("every safety-critical build input bypasses broad exclusions",
          all(path in first_check for path in critical))
    check("unreadable refs or a critical diff force a build",
          "|| exit 1" in first_check)
    check("routine automation files remain excluded from site-only builds",
          "':(exclude)automation-log'" in ignore and
          "':(exclude)pipeline'" in ignore)

    source = (ROOT / "build_site.py").read_text(encoding="utf-8")
    check("site rendering reads the own-product authorization switch",
          "load_own_product_policy" in source and
          'item.get("promotion_authorized")' in source)
    readiness = (ROOT / "tools" / "release_funnel_readiness.py").read_text(
        encoding="utf-8"
    )
    pilot = (ROOT / "release" / "funnel_pilot.json").read_text(encoding="utf-8")
    check("readiness score cannot authorize a pilot or external action",
          "score_is_authorization" in readiness and
          "publication_authority_granted" in readiness and
          'pilot_status = "BLOCKED"' in readiness and
          '"external_action_authorized": false' in pilot)
    check("pilot measurement support is bound to actual producer and schema files",
          '"pipeline/ga4_pull.py"' in pilot and
          '"pipeline/ga4_schema.py"' in pilot and
          "PILOT_MEASUREMENT_CONTRACT" in pilot and
          "PILOT_MEASUREMENT_FIELDS" in pilot)
    check("pilot threshold is provisional, low-confidence, and non-scaling",
          "provisional_planning_assumption" in pilot and
          '"trusted_historical_baseline_available": false' in pilot and
          '"winner_declaration_allowed": false' in pilot and
          '"scale_decision_allowed": false' in pilot)
    check("every build-time gate input is bound into release provenance",
          ".system_control/content_manifest.json" in
          {path.as_posix() for path in release_contract.SOURCE_INPUTS} and
          "tools/comply_gate_stitch.py" in
          {path.as_posix() for path in release_contract.SOURCE_INPUTS})
    print("netlify build trigger: 9/9 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
