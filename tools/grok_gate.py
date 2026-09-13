#!/usr/bin/env python3
"""Read-only Grok gate. 0 READY, 2 BLOCKED, 3 UNKNOWN, 4 runner failure.

READY requires a real, already consumed owner receipt rechecked by the existing
read-only execution verifier. This module NEVER provisions/consumes receipts.
Pending approval cannot authorize a claim. Run --selftest for isolated reversals.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation-log"))
sys.path.insert(0, str(ROOT / "tools"))
import channel_readiness as readiness
import content_compliance_gate as compliance
import post_ledger as ledger
import public_identity_guard as identity_guard
import publication_authority as authority

TZ = dt.timezone(dt.timedelta(hours=7))
CALENDAR = ".system_control/content_calendar.json"
POLICY = ".system_control/policy.json"
ROLES = ".system_control/role_capabilities.json"
LEDGER = "automation-log/post-ledger.jsonl"
RULES = "tiktok-pipeline/compliance_rules.json"
CHECKLIST = ".system_control/compliance_checklist.md"
EXIT = {"READY": 0, "BLOCKED": 2, "UNKNOWN": 3, "RUNNER_FAILED": 4}


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def read_json(path):
    return identity_guard._strict_json_loads(Path(path).read_text(encoding="utf-8"))


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return result.astimezone(TZ)


def safe_path(value, root=ROOT):
    if not isinstance(value, str) or not value:
        raise ValueError("file path missing")
    path = (root / value).resolve()
    path.relative_to(root.resolve())
    return path


def resolve_job(request, root=ROOT):
    calendar = read_json(root / CALENDAR)
    draft = request if isinstance(request, dict) else None
    if isinstance(request, str) and request.lower().endswith(".json"):
        draft = read_json(safe_path(request, root))
    pid = draft.get("placement_id") if draft is not None else request
    if not pid and isinstance(draft, dict):
        pid = str(draft.get("job_id", "")).split("@", 1)[0]
    rows = [p for p in calendar["placements"] if p.get("placement_id") == pid]
    if len(rows) != 1:
        raise ValueError("placement_id must match exactly one canonical placement")
    placement = rows[0]
    account = calendar["accounts"][placement["account"]]
    channel = readiness.ALIASES.get(account["channel"], account["channel"])
    slot = timestamp(placement.get("scheduled_at") or
                     placement["date"] + "T" + placement["time"] + ":00+07:00")
    text, error = compliance.load_source_copy(placement, repo=root)
    if error:
        raise ValueError(error)
    if draft is not None:
        supplied = draft.get("content", {}).get("text", text)
        if supplied != text:
            raise ValueError("draft content.text differs from canonical source")
        for field, expected in (("channel", channel), ("account", placement["account"]),
                                ("scheduled_at", slot.isoformat()),
                                ("leg", placement["format"])):
            if field in draft and draft[field] != expected:
                raise ValueError("draft " + field + " differs from calendar")
        if "text_sha256" in draft.get("content", {}) and draft["content"]["text_sha256"] != digest(text):
            raise ValueError("draft content.text_sha256 mismatch")
    action = (draft or {}).get("execution_action", placement.get("execution_action"))
    # A separate owner workflow may persist the return value of
    # authorize_live_publication here. Never put it into the hash-bound calendar
    # after consumption (that would invalidate the receipt), or export its nonce.
    action_path = root / ".local-private/runtime/publication-actions" / (digest(pid + "@" + slot.isoformat()) + ".json")
    if action is None and action_path.exists():
        if action_path.is_symlink():
            raise ValueError("private execution action must not be a symlink")
        action = read_json(action_path)
    return dict(placement=placement, account=account, channel=channel,
                slot=slot, text=text, action=action,
                job_id=pid + "@" + slot.isoformat())


def finish(checks):
    blocked = [c for c in checks if c["verdict"] == "BLOCKED"]
    unknown = [c for c in checks if c["verdict"] == "UNKNOWN"]
    return {"verdict": "BLOCKED" if blocked else "UNKNOWN" if unknown else "READY",
            "checks": checks, "blocking_field": blocked[0]["field"] if blocked else "",
            "could_not_check": "; ".join(c["field"] + ": " + c["detail"] for c in unknown)}


def assess(request, *, root=ROOT, now=None):
    root = Path(root).resolve()
    now = now or dt.datetime.now(TZ)
    checks = []

    def add(field, verdict, paths, detail):
        checks.append(dict(field=field, verdict=verdict, paths=paths, detail=detail))

    try:
        job = resolve_job(request, root)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        add("placement.source", "UNKNOWN", [CALENDAR], str(exc))
        # Absence of an owner action is a known denial even if source is unreadable.
        try:
            calendar = read_json(root / CALENDAR)
            pid = request.get("placement_id") if isinstance(request, dict) else request
            rows = [p for p in calendar["placements"] if p.get("placement_id") == pid]
            if len(rows) == 1 and not rows[0].get("execution_action") and not (
                isinstance(request, dict) and request.get("execution_action")
            ):
                add("approval.owner_evidence", "BLOCKED", [CALENDAR],
                    "No private owner receipt/action; editable approval booleans are insufficient")
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            pass
        return finish(checks)
    p, text, channel = job["placement"], job["text"], job["channel"]
    source_path = p["source"]["file"]
    action = job["action"]
    add("content.privacy", "READY" if ledger.sanitize_public_record({"text": text}) == {"text": text} else "BLOCKED",
        [source_path, "automation-log/public_log_sanitize.py"], "Final public copy must survive privacy sanitizer unchanged")
    if not isinstance(action, dict):
        add("approval.owner_evidence", "BLOCKED", [CALENDAR,
            ".local-private/runtime/publication-receipts"],
            "Missing owner-controlled one-time receipt and consumed action; owner_approved is not evidence")
        add("publication_authority.execution", "UNKNOWN", ["tools/publication_authority.py"],
            "No preview mode for pending receipts. Owner workflow must authorize once; this gate only rechecks consumed actions")
    try:
        policy, roles = read_json(root / POLICY), read_json(root / ROLES)
        entry = policy["channels"][channel]
        # Existing assessor owns all six layers; no copied readiness logic.
        original = readiness.LEDGER
        try:
            readiness.LEDGER = str(root / LEDGER)
            rows = readiness.assess(policy, roles, channel, entry, "grok",
                                    now.astimezone(TZ).date().isoformat(), now)
        finally:
            readiness.LEDGER = original
        selected = [r for r in rows if r["leg"] == p["format"]]
        row = selected[0] if len(selected) == 1 else {"verdict": "BLOCKED", "why": "unsupported channel leg"}
        add("channel_readiness.layers_1_6", row["verdict"], [POLICY, ROLES, LEDGER], row["why"])
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        policy = None
        add("channel_readiness.layers_1_6", "UNKNOWN", [POLICY, ROLES, LEDGER], str(exc))
    add("placement.publication_authorized", "READY" if p.get("publication_authorized") is True else "BLOCKED",
        [CALENDAR], "Canonical placement permission (necessary, never owner approval)")
    add("channel.handoff_scope", "BLOCKED" if channel == "pantip" or
        (channel == "facebook" and p["format"] == "video") else "READY", [CALENDAR],
        "Pantip and Facebook Reel excluded by handover")
    try:
        authority._enforce_slot_window(channel, job["slot"], now)
        add("window", "READY", [CALENDAR, "tools/publication_authority.py"], "Inside existing authority window")
    except authority.PublicationBlocked as exc:
        add("window", "BLOCKED", [CALENDAR, "tools/publication_authority.py"], str(exc))
    try:
        rules = read_json(root / RULES)
        forbidden = rules["forbidden"]
        if not isinstance(forbidden, list) or not forbidden or not all(isinstance(x, str) and x for x in forbidden):
            raise ValueError("forbidden policy is malformed")
        ok, issues = compliance.comply_gate.check(text)
        hit = any(word.casefold() in text.casefold() for word in forbidden)
        add("content.forbidden", "READY" if ok and not hit else "BLOCKED",
            [source_path, RULES, "pipeline/comply_gate.py"], "Policy forbidden list and existing compliance checker")
        checklist = (root / CHECKLIST).read_text(encoding="utf-8")
        educational = re.findall(r'^- \[ \] \u0e21\u0e35 "([^"]+)"', checklist, re.M)
        if len(educational) != 1:
            raise ValueError("required educational disclosure policy unavailable")
        required = educational[:]
        if p.get("affiliate") is True:
            required.append(rules["required_disclosure"].split(" \u00b7 ")[2])
        if p["format"] == "video":
            required.append(rules["required_disclosure"].split(" \u00b7 ")[-1])
        add("content.disclosure", "READY" if all(x in text for x in required) else "BLOCKED",
            [source_path, CHECKLIST, RULES], "Required policy disclosure must occur in exact final copy")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError) as exc:
        add("content.compliance_policy", "UNKNOWN", [RULES, CHECKLIST], str(exc))
    add("content.cta_199", "BLOCKED" if re.search(r"(?<!\d)199(?!\d)", text) or
        p.get("cta_id") == "letter-kit-199" else "READY", [source_path, CALENDAR],
        "199 offer withheld by handover; numeric token comparison")
    if policy is not None:
        try:
            identity = policy["public_identity"]
            patterns, errors = identity_guard._compile_patterns(identity)
            speakers, more = identity_guard._speaker_pattern(identity)
            findings = identity_guard._copy_findings(text, source_path, 1, patterns, speakers)
            add("content.public_identity", "UNKNOWN" if errors or more else "BLOCKED" if findings else "READY",
                [POLICY, source_path], "Existing public_identity_guard pattern and speaker checks")
        except (KeyError, TypeError, ValueError) as exc:
            add("content.public_identity", "UNKNOWN", [POLICY], str(exc))
    try:
        dup, reason, finding = ledger.is_duplicate_text(channel, text, path=str(root / LEDGER))
        unknown = isinstance(finding, dict) and finding.get("type") in {
            "ledger_integrity", "text_identity", "dedup_completeness"}
        add("content.text_hash", "UNKNOWN" if unknown else "BLOCKED" if dup else "READY",
            [LEDGER, "automation-log/post_ledger.py", "automation-log/dedup-evidence"],
            "Identity coverage unknown" if unknown else "Duplicate exact hash or existing near-duplicate rule" if dup else "Permanent ledger identity checked; no substring comparison")
    except (OSError, ValueError, TypeError) as exc:
        add("content.text_hash", "UNKNOWN", [LEDGER], str(exc))
    media_hash = None
    try:
        media = p.get("media")
        if media:
            media_hash = hashlib.sha256(safe_path(media, root).read_bytes()).hexdigest()
        if p["format"] in {"video", "image"} and not media:
            raise ValueError("media required for this leg")
        add("content.media", "READY", [media] if media else [CALENDAR], "Exact asset SHA-256 read; QA rechecked by authority")
    except (OSError, ValueError, TypeError) as exc:
        add("content.media", "UNKNOWN", [CALENDAR], str(exc))
    if isinstance(action, dict):
        try:
            target_fields = ("page_id", "account_id", "ig_user_id", "channel_id", "account_handle")
            target = next((job["account"].get(f) for f in target_fields if job["account"].get(f)), None)
            if target is None and p["account"] == channel + "_main" and policy is not None:
                target = next((policy["channels"][channel].get(f) for f in target_fields if policy["channels"][channel].get(f)), None)
            if not target or target != action.get("target_identity"):
                raise authority.PublicationBlocked("calendar account has no exact authorized target binding")
            for field, expected in (("placement_id", p["placement_id"]), ("content_id", p["content_id"]),
                                    ("channel", channel), ("actor", "grok")):
                if action.get(field) != expected:
                    raise authority.PublicationBlocked("action " + field + " mismatch")
            if timestamp(action.get("scheduled_slot")) != job["slot"]:
                raise authority.PublicationBlocked("action scheduled_slot mismatch")
            authority.verify_execution_authorization(repo=root, action=action, caption=text,
                asset_sha256=media_hash, media_qa_path=p.get("media_receipt"), now=now)
            add("approval.owner_evidence", "READY", [".local-private/runtime/publication-receipts/consumed"],
                "Private one-time receipt verified; repository boolean did not grant approval")
            add("publication_authority.execution", "READY", [POLICY, ROLES, CALENDAR, source_path,
                "tools/publication_authority.py", ".local-private/runtime/publication-receipts/consumed"],
                "Existing read-only verifier passed exact receipt, source, target, media and window bindings")
        except authority.PublicationBlocked as exc:
            # Do not echo nonce/receipt contents into public handoff files.
            add("approval.owner_evidence", "BLOCKED", ["tools/publication_authority.py"],
                "Existing execution verifier rejected owner receipt or evidence binding")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            add("publication_authority.execution", "UNKNOWN", ["tools/publication_authority.py"],
                "Execution evidence could not be inspected: " + type(exc).__name__)
    return finish(checks)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("placement_or_draft", nargs="?")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.placement_or_draft:
        parser.error("placement_id or draft JSON required")
    try:
        result = assess(args.placement_or_draft)
    except Exception as exc:
        result = dict(verdict="RUNNER_FAILED", checks=[], blocking_field="runner",
                      could_not_check=type(exc).__name__)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT[result["verdict"]]


def selftest():
    import copy
    import unittest
    from unittest.mock import patch

    class GateTests(unittest.TestCase):
        def setUp(self):
            self.now = timestamp("2026-09-13T12:30:00+07:00")
            self.policy = copy.deepcopy(read_json(ROOT / POLICY))
            self.policy["gates"] = []
            self.policy["channels"]["facebook"].update(state="active", auto=True, kind="text", publication_authorized=True)
            self.policy["publication_control"]["default_publication_authorized"] = True
            self.roles = {"actors": {"grok": {"social_publish": True}}, "default": "deny"}
            education = re.findall(r'^- \[ \] \u0e21\u0e35 "([^"]+)"', (ROOT / CHECKLIST).read_text(encoding="utf-8"), re.M)[0]
            self.text = "A useful planning checklist.\n" + education
            self.job = dict(placement=dict(placement_id="sample__facebook_main", content_id="sample",
                account="facebook_main", format="text", publication_authorized=True,
                source={"file": "fixture.txt"}), account={"page_id": self.policy["channels"]["facebook"]["page_id"]}, channel="facebook", slot=self.now,
                text=self.text, job_id="sample__facebook_main@" + self.now.isoformat(),
                action=dict(placement_id="sample__facebook_main", content_id="sample", channel="facebook",
                    actor="grok", target_identity=self.policy["channels"]["facebook"]["page_id"], scheduled_slot=self.now.isoformat()))

        def run_fixture(self, *, policy=None, roles=None, job=None, activity=None, duplicate=None, authority_error=None):
            real_json = read_json
            def read(path):
                if str(path).replace("\\", "/").endswith(POLICY):
                    return self.policy if policy is None else policy
                if str(path).replace("\\", "/").endswith(ROLES):
                    return self.roles if roles is None else roles
                return real_json(path)
            with patch(__name__ + ".read_json", side_effect=read), patch(__name__ + ".resolve_job", return_value=job or self.job), patch.object(readiness, "ledger_activity", return_value=activity or (0, None, set())), patch.object(ledger, "is_duplicate_text", return_value=duplicate or (False, "", None)), patch.object(authority, "verify_execution_authorization", side_effect=authority_error, return_value={}) as verifier:
                result = assess("sample__facebook_main", now=self.now)
            return result

        def test_real_content_checks_fire_and_stay_quiet(self):
            self.assertEqual(self.run_fixture()["verdict"], "READY")
            cases = (("content.forbidden", self.text + " " + read_json(ROOT / RULES)["forbidden"][0]),
                     ("content.disclosure", "A useful planning checklist."),
                     ("content.cta_199", self.text + " 199"),
                     ("content.public_identity", self.text + " grok"),
                     ("content.privacy", self.text + " fixture@example.com"))
            for field, text in cases:
                with self.subTest(field=field):
                    result = self.run_fixture(job={**self.job, "text": text})
                    self.assertTrue(any(c["field"] == field and c["verdict"] == "BLOCKED" for c in result["checks"]))

        def test_all_six_readiness_layers_reverse(self):
            for layer in range(1, 7):
                policy, roles = copy.deepcopy(self.policy), copy.deepcopy(self.roles)
                activity = (0, None, set())
                if layer == 1:
                    policy["publication_control"]["default_publication_authorized"] = False
                elif layer == 2:
                    policy["channels"]["facebook"]["state"] = "paused"
                elif layer == 3:
                    policy["channels"]["facebook"].update(auto=False, auto_legs=[])
                elif layer == 4:
                    policy["gates"] = [dict(date="2026-09-01", decides=["facebook"], status="OPEN")]
                elif layer == 5:
                    roles["actors"]["grok"]["social_publish"] = False
                else:
                    activity = (999, None, set())
                with self.subTest(layer=layer):
                    result = self.run_fixture(policy=policy, roles=roles, activity=activity)
                    self.assertTrue(any(c["field"] == "channel_readiness.layers_1_6" and c["verdict"] == "BLOCKED" for c in result["checks"]))
            result = self.run_fixture(activity=(0, self.now - dt.timedelta(minutes=5), set()))
            self.assertEqual(result["verdict"], "BLOCKED")

        def test_owner_window_dedup_and_media_reversals(self):
            self.assertEqual(self.run_fixture(authority_error=authority.PublicationBlocked("fixture expired"))["verdict"], "BLOCKED")
            self.assertEqual(self.run_fixture(job={**self.job, "action": None})["verdict"], "BLOCKED")
            result = self.run_fixture(job={**self.job, "slot": self.now - dt.timedelta(hours=1)})
            self.assertTrue(any(c["field"] == "window" and c["verdict"] == "BLOCKED" for c in result["checks"]))
            self.assertEqual(self.run_fixture(duplicate=(True, "exact", {"type": "text"}))["verdict"], "BLOCKED")
            self.assertEqual(self.run_fixture(duplicate=(True, "unreadable", {"type": "ledger_integrity"}))["verdict"], "UNKNOWN")
            job = copy.deepcopy(self.job)
            job["placement"]["media"] = "missing-fixture-asset.mp4"
            result = self.run_fixture(job=job)
            self.assertEqual(result["verdict"], "UNKNOWN")

        def test_missing_policy_is_unknown_without_any_known_denial(self):
            with patch.object(readiness, "assess", side_effect=ValueError("unreadable policy")):
                self.assertEqual(self.run_fixture()["verdict"], "UNKNOWN")

        def test_unknown_is_not_blocked(self):
            self.assertEqual(finish([dict(field="ledger", verdict="UNKNOWN", detail="unreadable")])["verdict"], "UNKNOWN")
            self.assertEqual(EXIT["UNKNOWN"], 3)
            self.assertEqual(EXIT["RUNNER_FAILED"], 4)

        def test_each_check_reverse_and_aggregate(self):
            fields = ["channel_readiness.layers_1_6", "approval.owner_evidence", "content.forbidden",
                      "content.disclosure", "content.cta_199", "content.public_identity", "content.text_hash",
                      "publication_authority.execution", "window", "content.media"]
            for field in fields:
                with self.subTest(field=field):
                    checks = [dict(field=f, verdict="READY", detail="fixture") for f in fields]
                    self.assertEqual(finish(checks)["verdict"], "READY")
                    checks[fields.index(field)]["verdict"] = "BLOCKED"
                    self.assertEqual(finish(checks)["blocking_field"], field)
                    checks[fields.index(field)]["verdict"] = "UNKNOWN"
                    self.assertEqual(finish(checks)["verdict"], "UNKNOWN")

        def test_live_calendar_has_no_approval(self):
            rows = read_json(ROOT / CALENDAR)["placements"]
            self.assertTrue(rows)
            for p in rows:
                if p.get("execution_action"):
                    continue
                result = assess(p["placement_id"])
                self.assertEqual(result["verdict"], "BLOCKED", p["placement_id"])
                self.assertTrue(any(c["field"] == "approval.owner_evidence" and c["verdict"] == "BLOCKED" for c in result["checks"]))

    return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GateTests)).wasSuccessful() else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
