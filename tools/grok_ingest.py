#!/usr/bin/env python3
"""Local claim/result bridge. Mutations: ledger + ack (and ledger lock) only.

The caller must deliver JSON through an authenticated, owner-approved channel.
This CLI is not an authenticated network endpoint and never publishes.
On Windows the ISO job_id in ack filenames is percent-encoded reversibly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit

import grok_gate as gate
import grok_jobcards as cards

CLAIM_KEYS = {"kind", "job_id", "at", "text_sha256_seen"}
RESULT_KEYS = {"kind", "job_id", "at", "result", "post_url", "verified", "error", "could_not_see"}
VERIFIED = {"url_opened", "text_matches", "account_matches"}


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    kind = payload.get("kind")
    if kind == "claim":
        if set(payload) != CLAIM_KEYS:
            raise ValueError("claim schema fields are not exact")
        if not isinstance(payload["text_sha256_seen"], str) or not re.fullmatch(r"[0-9a-f]{64}", payload["text_sha256_seen"]):
            raise ValueError("text_sha256_seen invalid")
    elif kind == "result":
        if set(payload) - RESULT_KEYS or not {"kind", "job_id", "at", "result"} <= set(payload):
            raise ValueError("result schema fields invalid")
        if payload["result"] not in {"posted", "failed", "unknown"}:
            raise ValueError("unsupported result")
        for field in ("post_url", "error", "could_not_see"):
            if field in payload and not isinstance(payload[field], str):
                raise ValueError(field + " must be a string")
        if "verified" in payload and (not isinstance(payload["verified"], dict) or
                set(payload["verified"]) != VERIFIED or
                any(type(x) is not bool for x in payload["verified"].values())):
            raise ValueError("verified requires exactly three booleans")
        if payload["result"] == "posted":
            parsed = urlsplit(payload.get("post_url", ""))
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or not parsed.path.strip("/"):
                raise ValueError("posted requires an HTTPS post permalink")
            if payload.get("verified") != {key: True for key in VERIFIED}:
                raise ValueError("posted requires all three verified values true")
        elif payload["result"] == "unknown" and not payload.get("could_not_see", "").strip():
            raise ValueError("unknown requires could_not_see")
        elif payload["result"] == "failed" and not payload.get("error", "").strip():
            raise ValueError("failed requires error")
    else:
        raise ValueError("kind must be claim or result")
    if not isinstance(payload.get("job_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*@[^/\\\s]+", payload["job_id"]):
        raise ValueError("job_id invalid")
    gate.timestamp(payload["job_id"].split("@", 1)[1])
    gate.timestamp(payload["at"])
    return payload


def load_card(job_id, root):
    slot = gate.timestamp(job_id.split("@", 1)[1])
    path = root / cards.HANDOFF / ("jobcards_" + slot.date().isoformat() + ".json")
    document = gate.read_json(path)
    if not isinstance(document, list):
        raise ValueError("jobcard export must be an array")
    matches = [card for card in document if card.get("job_id") == job_id]
    if len(matches) != 1:
        raise ValueError("job_id not in exactly one READY export")
    card = matches[0]
    if card["gate"]["verdict"] != "READY" or card["approval"]["owner_approved"] is not True:
        raise ValueError("jobcard is held")
    if gate.digest(card["content"]["text"]) != card["content"]["text_sha256"]:
        raise ValueError("jobcard text hash mismatch")
    if gate.timestamp(card["scheduled_at"]) != slot:
        raise ValueError("job_id slot mismatch")
    return card


def ack_path(job_id, root):
    directory = (root / cards.HANDOFF).resolve()
    path = directory / (quote(job_id, safe="@._-") + ".ack.json")
    if path.is_symlink() or path.resolve().parent != directory:
        raise ValueError("ack path escaped handoff directory")
    return path


def write_ack(payload, root):
    path = ack_path(payload["job_id"], root)
    # Directory is created only by exporter; ingest cannot create other paths.
    open(path, "w", encoding="utf-8", newline="\n").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def claim(payload, card, root, now):
    validate(payload)
    def reject(reason, verdict="BLOCKED"):
        ack = dict(kind="claim_rejected", job_id=payload["job_id"], verdict=verdict,
                   reason=reason, at=now.isoformat())
        # Never overwrite a prior positive ack with contradictory evidence.
        path = ack_path(payload["job_id"], root)
        if not path.exists():
            write_ack(ack, root)
        return ack

    if ack_path(payload["job_id"], root).exists():
        return reject("job already has acknowledgement; reconcile, do not retry")
    if payload["text_sha256_seen"] != card["content"]["text_sha256"]:
        return reject("text_sha256_seen mismatch")
    if not gate.timestamp(card["window"]["not_before"]) <= now <= gate.timestamp(card["window"]["not_after"]):
        return reject("outside window at receiver clock")
    if abs((now - gate.timestamp(payload["at"])).total_seconds()) > 120:
        return reject("claim at differs from receiver clock by more than 120 seconds")
    pid = payload["job_id"].split("@", 1)[0]
    result = gate.assess(pid, root=root, now=now)
    if result["verdict"] != "READY":
        return reject(result["blocking_field"] or result["could_not_check"], result["verdict"])
    job = gate.resolve_job(pid, root)
    if (job["job_id"] != card["job_id"] or job["text"] != card["content"]["text"] or
            job["channel"] != card["channel"] or job["placement"]["format"] != card["leg"] or
            job["action"]["target_identity"] != card["account"] or
            job["placement"].get("media") != card["content"]["media_ref"]):
        return reject("jobcard canonical binding drift")
    media = job["placement"].get("media")
    actual_media = gate.hashlib.sha256(gate.safe_path(media, root).read_bytes()).hexdigest() if media else None
    if actual_media != card["content"]["media_sha256"]:
        return reject("media hash drift")
    # Existing writer takes the cross-operator ledger lock and rechecks quota,
    # minimum gap, permanent text identity and coverage INSIDE that lock.
    previous = gate.ledger.LEDGER
    try:
        gate.ledger.LEDGER = str(root / gate.LEDGER)
        ok, key, reason = gate.ledger.claim_text_publication(card["channel"], job["text"], now.isoformat(),
            content_id=job["placement"]["content_id"], placement_id=pid,
            source="grok:" + gate.digest(gate.canonical(card)))
    finally:
        gate.ledger.LEDGER = previous
    if not ok:
        return reject(reason)
    ack = dict(kind="claim_ack", job_id=payload["job_id"], at=now.isoformat(),
               dedup_key=key, job_sha256=gate.digest(gate.canonical(card)),
               text_sha256=card["content"]["text_sha256"], account=card["account"],
               window=card["window"], media_sha256=actual_media)
    write_ack(ack, root)
    return ack


def result(payload, card, root, now):
    validate(payload)
    path = str(root / gate.LEDGER)
    if not gate.ledger.acquire_lock(path=path):
        raise RuntimeError("ledger lock unavailable; result UNKNOWN, retry only after reconciliation")
    try:
        rows, integrity = gate.ledger._read_ledger_snapshot(path)
        if integrity["state"] != "OK":
            raise ValueError("ledger integrity UNKNOWN")
        source = "grok:" + gate.digest(gate.canonical(card))
        claims = [r for r in rows if r.get("status") == "claimed" and r.get("source") == source]
        if len(claims) != 1:
            raise ValueError("result has no unique prior claim bound to exact jobcard")
        original = claims[0]
        if (original.get("placement_id") != payload["job_id"].split("@", 1)[0] or
                original.get("text_hash") != gate.ledger.text_hash(card["content"]["text"])):
            raise ValueError("claim text/placement binding mismatch")
        key = original["dedup_key"]
        fingerprint = gate.digest(gate.canonical(payload))
        existing = [r for r in rows if r.get("type") == "status" and r.get("dedup_key") == key]
        if existing:
            if len(existing) == 1 and existing[0].get("grok_result_sha256") == fingerprint:
                return dict(kind="result_ack", job_id=payload["job_id"], appended=False, idempotent=True)
            raise ValueError("claim already has terminal or conflicting evidence; reconciliation required")
        at = gate.timestamp(payload["at"])
        if at > now + dt.timedelta(seconds=120) or at < gate.timestamp(original["ts"]):
            raise ValueError("result time outside claim chronology")
        if payload["result"] == "posted":
            if not gate.timestamp(card["window"]["not_before"]) <= at <= gate.timestamp(card["window"]["not_after"]):
                raise ValueError("reported publication outside window")
            domains = {"facebook": {"facebook.com", "www.facebook.com"},
                       "youtube": {"youtube.com", "www.youtube.com", "youtu.be"},
                       "threads": {"threads.net", "www.threads.net", "threads.com", "www.threads.com"},
                       "instagram": {"instagram.com", "www.instagram.com"},
                       "tiktok": {"tiktok.com", "www.tiktok.com"}}
            if urlsplit(payload["post_url"]).hostname not in domains.get(card["channel"], set()):
                raise ValueError("post_url platform differs from channel")
        row = dict(type="status", status=payload["result"], dedup_key=key,
                   job_id=payload["job_id"], grok_result_sha256=fingerprint,
                   post_id=payload.get("post_url", ""), posted_at=at.isoformat(),
                   received_at=now.isoformat(), verified=payload.get("verified", {}),
                   error=payload.get("error", ""), could_not_see=payload.get("could_not_see", ""))
        gate.ledger._public_safe(row)
        gate.ledger._append(row, path=path)
        return dict(kind="result_ack", job_id=payload["job_id"], appended=True, idempotent=False)
    finally:
        gate.ledger.release_lock(path=path)


def ingest(payload, *, root=gate.ROOT, now=None):
    root = Path(root).resolve()
    now = (now or dt.datetime.now(gate.TZ)).astimezone(gate.TZ)
    validate(payload)
    try:
        card = load_card(payload["job_id"], root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if payload["kind"] != "claim":
            raise ValueError("result jobcard unavailable or invalid; retain claim for reconciliation") from exc
        ack = dict(kind="claim_rejected", job_id=payload["job_id"], at=now.isoformat(),
                   verdict="UNKNOWN" if isinstance(exc, OSError) else "BLOCKED",
                   reason="jobcard unavailable or invalid: " + type(exc).__name__)
        if (root / cards.HANDOFF).is_dir() and not ack_path(payload["job_id"], root).exists():
            write_ack(ack, root)
        return ack
    return claim(payload, card, root, now) if payload["kind"] == "claim" else result(payload, card, root, now)


def selftest():
    import unittest
    from unittest.mock import patch
    import tempfile

    class IngestTests(unittest.TestCase):
        def setUp(self):
            self.now = gate.timestamp("2026-09-13T12:30:00+07:00")
            self.pid = "sample__facebook_main"
            self.jid = self.pid + "@" + self.now.isoformat()
            self.payload = dict(kind="result", job_id=self.jid, at=self.now.isoformat(),
                result="posted", post_url="https://www.facebook.com/page/posts/123",
                verified={k: True for k in VERIFIED})

        def test_posted_reverse_each_verification(self):
            validate(self.payload)
            for key in VERIFIED:
                for bad in (False, 1, "true", None):
                    candidate = {**self.payload, "verified": {**self.payload["verified"], key: bad}}
                    with self.assertRaises(ValueError):
                        validate(candidate)
            for missing in ("post_url", "verified"):
                candidate = dict(self.payload)
                del candidate[missing]
                with self.assertRaises(ValueError):
                    validate(candidate)

        def test_unknown_and_failed_require_evidence(self):
            for status, field in (("unknown", "could_not_see"), ("failed", "error")):
                candidate = dict(kind="result", job_id=self.jid, at=self.now.isoformat(), result=status)
                with self.assertRaises(ValueError):
                    validate(candidate)
                validate({**candidate, field: "Observed fixture evidence"})

        def test_claim_real_lock_ack_duplicates_hash_window_and_gate(self):
            from contextlib import ExitStack
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                (root / cards.HANDOFF).mkdir(parents=True)
                path = root / gate.LEDGER
                open(path, "w", encoding="utf-8", newline="\n").write("")
                text = "A unique synthetic publication checklist"
                card = dict(job_id=self.jid, channel="facebook", leg="text", account="page-fixture",
                    content=dict(text=text, text_sha256=gate.digest(text), media_ref=None, media_sha256=None),
                    window=dict(not_before=self.now.isoformat(), not_after=(self.now + dt.timedelta(minutes=10)).isoformat()))
                job = dict(job_id=self.jid, channel="facebook", text=text,
                    placement=dict(placement_id=self.pid, content_id="sample", format="text"),
                    action=dict(target_identity="page-fixture"))
                payload = dict(kind="claim", job_id=self.jid, at=self.now.isoformat(), text_sha256_seen=gate.digest(text))
                with ExitStack() as stack:
                    stack.enter_context(patch.object(gate, "assess", return_value=dict(verdict="READY")))
                    stack.enter_context(patch.object(gate, "resolve_job", return_value=job))
                    stack.enter_context(patch.object(gate.ledger, "is_duplicate_text", return_value=(False, "", None)))
                    stack.enter_context(patch.object(gate.ledger, "load_index", return_value={"integrity": {"state": "OK"}}))
                    stack.enter_context(patch.object(gate.ledger, "day_capacity", return_value=1))
                    stack.enter_context(patch.object(gate.ledger, "minimum_gap", return_value=(True, "")))
                    actual = gate.ledger.claim_text_publication
                    with patch.object(gate.ledger, "claim_text_publication", wraps=actual) as writer:
                        response = claim(payload, card, root, self.now)
                        self.assertEqual(response["kind"], "claim_ack")
                        writer.assert_called_once()
                    self.assertEqual(gate.read_json(ack_path(self.jid, root)), response)
                    before = path.read_bytes()
                    self.assertEqual(claim(payload, card, root, self.now)["kind"], "claim_rejected")
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)
                    # Different ids leave independent rejected acknowledgements.
                    for i, mode in enumerate(("hash", "window", "gate", "reservation")):
                        candidate = {**payload, "job_id": "test%d__facebook_main@%s" % (i, self.now.isoformat())}
                        candidate_card = {**card, "job_id": candidate["job_id"]}
                        if mode == "hash":
                            candidate["text_sha256_seen"] = "0" * 64
                        elif mode == "window":
                            candidate_card["window"] = dict(not_before=(self.now + dt.timedelta(hours=1)).isoformat(), not_after=(self.now + dt.timedelta(hours=2)).isoformat())
                        with patch.object(gate, "assess", return_value=dict(verdict="UNKNOWN" if mode == "gate" else "READY", blocking_field="", could_not_check="ledger")), patch.object(gate, "resolve_job", return_value={**job, "job_id": candidate["job_id"]}), patch.object(gate.ledger, "claim_text_publication", return_value=(False, "", "already reserved")):
                            rejected = claim(candidate, candidate_card, root, self.now)
                        self.assertEqual(rejected["kind"], "claim_rejected")
                        self.assertEqual(rejected["verdict"], "UNKNOWN" if mode == "gate" else "BLOCKED")
                        self.assertEqual(path.read_bytes(), before)
                rows, integrity = gate.ledger._read_ledger_snapshot(str(path))
                self.assertEqual(integrity["state"], "OK")
                unknown = dict(kind="result", job_id=self.jid, at=self.now.isoformat(),
                               result="unknown", could_not_see="Platform outcome not visible")
                self.assertTrue(result(unknown, card, root, self.now)["appended"])
                after = path.read_bytes()
                self.assertTrue(result(unknown, card, root, self.now)["idempotent"])
                self.assertEqual(path.read_bytes(), after)
                rows, integrity = gate.ledger._read_ledger_snapshot(str(path))
                self.assertEqual(integrity["state"], "OK")
                self.assertEqual(rows[-1]["status"], "unknown")
                self.assertFalse(any(r.get("status") == "posted" for r in rows))
                self.assertFalse(Path(gate.ledger._lock_path(str(path))).exists())

        def test_malformed_or_unknown_result_never_writes_posted(self):
            from unittest.mock import Mock
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                (root / "automation-log").mkdir()
                path = root / gate.LEDGER
                open(path, "w", encoding="utf-8", newline="\n").write("")
                with patch.object(gate.ledger, "_append") as append:
                    with self.assertRaises(ValueError):
                        result({**self.payload, "verified": {}}, {}, root, self.now)
                    append.assert_not_called()
                self.assertEqual(path.read_bytes(), b"")

        def test_result_is_atomic_idempotent_and_claim_bound(self):
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                (root / "automation-log").mkdir()
                path = root / gate.LEDGER
                card = dict(content={"text": "fixture publication"}, channel="facebook",
                    window={"not_before": self.now.isoformat(), "not_after": (self.now + dt.timedelta(minutes=10)).isoformat()})
                original = dict(type="text", status="claimed", source="grok:" + gate.digest(gate.canonical(card)),
                    placement_id=self.pid, text_hash=gate.ledger.text_hash(card["content"]["text"]),
                    dedup_key="text:fb:fixture", ts=self.now.isoformat())
                open(path, "w", encoding="utf-8", newline="\n").write(json.dumps(original) + "\n")
                # Integrity parser is tested separately; use the real lock/append.
                def snapshot(p):
                    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines()], {"state": "OK"}
                with patch.object(gate.ledger, "_read_ledger_snapshot", side_effect=snapshot):
                    self.assertTrue(result(self.payload, card, root, self.now)["appended"])
                    before = path.read_bytes()
                    self.assertTrue(result(self.payload, card, root, self.now)["idempotent"])
                    self.assertEqual(before, path.read_bytes())
                    with self.assertRaises(ValueError):
                        result({**self.payload, "post_url": "https://www.facebook.com/page/posts/999"}, card, root, self.now)
                    self.assertEqual(before, path.read_bytes())

        def test_ack_filename_cannot_escape_and_is_windows_safe(self):
            path = ack_path(self.jid, gate.ROOT)
            self.assertNotIn(":", path.name)
            self.assertIn("%3A", path.name)
            with self.assertRaises(ValueError):
                validate({**self.payload, "job_id": "../bad@" + self.now.isoformat()})

    return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IngestTests)).wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON file, literal JSON, or - for stdin")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.input:
        parser.error("input required")
    try:
        raw = sys.stdin.read() if args.input == "-" else args.input if args.input.lstrip().startswith("{") else Path(args.input).read_text(encoding="utf-8")
        response = ingest(gate.identity_guard._strict_json_loads(raw))
        code = 3 if response.get("verdict") == "UNKNOWN" else 2 if response["kind"] == "claim_rejected" else 0
    except ValueError as exc:
        response, code = dict(kind="rejected", reason=str(exc)), 2
    except Exception as exc:
        response, code = dict(kind="RUNNER_FAILED", could_not_check=type(exc).__name__), 4
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
