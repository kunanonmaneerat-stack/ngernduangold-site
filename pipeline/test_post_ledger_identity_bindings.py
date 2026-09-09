#!/usr/bin/env python3
"""Adversarial tests for append-only legacy identity bindings."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / "automation-log"
sys.path.insert(0, str(AUTO))
import post_ledger as ledger  # noqa: E402
import post_ledger_identity as identity  # noqa: E402


PRODUCTION_LEDGER = AUTO / "post-ledger.jsonl"
PRODUCTION_BINDINGS = AUTO / "post-ledger-identity-bindings.jsonl"
PRODUCTION_EVIDENCE = (
    AUTO / "dedup-evidence" / "post-ledger-identity-sources-v1.json"
)
PRODUCTION_EVIDENCE_V2 = (
    AUTO / "dedup-evidence" / "post-ledger-identity-sources-v2.json"
)
PRODUCTION_TOMBSTONES = AUTO / "post-ledger-collision-tombstones.json"
PRODUCTION_PRIVATE_COMMITMENT = (
    AUTO / "dedup-evidence" / "private-session-tool-input-commitments-v1.json"
)
PRODUCTION_PRIVATE_EVIDENCE = (
    AUTO / "dedup-evidence" /
    "post-ledger-identity-sources-private-session-v1.json"
)
PRODUCTION_PUBLIC_WEB_EVIDENCE = (
    AUTO / "dedup-evidence" /
    "post-ledger-identity-sources-public-web-v1.json"
)
PUBLIC_WEB_LINES = [45, 53, 109]
PRIVATE_LINES = [
    27, 30, 31, 32, 47, 49, 55, 56, 62, 63, 70, 71, 78, 79, 87, 88,
    89, 94, 95, 103, 113, 114, 120, 121, 129, 137, 155, 175,
]
EXPECTED_LINES = sorted([
    25, 26, 28, 29, 33, 41, 45, 48, 51, 52, 53, 57, 58, 59, 60, 64, 65, 66, 67, 68,
    72, 74, 75, 76, 81, 82, 83, 84, 85, 90, 91, 96, 97, 101, 106,
    108, 109, 117, 118, 126, 127, 132, 133, 141, 142, 150, 151, 160, 161,
    165, 166, 176,
] + PRIVATE_LINES)


def read_ledger(path: Path):
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    physical = raw.split(b"\n")[:-1]
    rows = [json.loads(line.rstrip(b"\r").decode("utf-8")) for line in physical]
    hashes = {
        number: hashlib.sha256(line.rstrip(b"\r")).hexdigest().upper()
        for number, line in enumerate(physical, 1)
    }
    return rows, hashes


def read_bindings(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def reseal(records):
    previous = identity.ZERO_SHA256
    targets = []
    for record in records:
        if record.get("record_type") == "post_ledger_identity_binding":
            record["previous_binding_sha256"] = previous
            record["binding_sha256"] = identity.binding_sha256(record)
            previous = record["binding_sha256"]
            targets.append(record["target"]["line"])
        elif record.get("record_type") == "post_ledger_identity_binding_seal":
            record["binding_count"] = len(targets)
            record["sealed_target_lines"] = sorted(targets)
            record["previous_record_sha256"] = previous
            record["seal_sha256"] = identity.seal_sha256(record)
            previous = record["seal_sha256"]
        else:
            raise AssertionError("unknown binding fixture record")


def write_jsonl(path: Path, records, final_newline=True):
    body = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    )
    path.write_text(body + ("\n" if final_newline else ""), encoding="utf-8")


def normalize(text):
    cleaned = re.sub(r"https?://\S+|www\.\S+|atth\.me/\S+", "", str(text))
    return "".join(char for char in cleaned.casefold() if char.isalnum())


class BindingSandbox:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dedup-binding-")
        self.root = Path(self.temp.name)
        self.auto = self.root / "automation-log"
        self.evidence = (
            self.auto / "dedup-evidence" / PRODUCTION_EVIDENCE.name
        )
        self.ledger = self.auto / PRODUCTION_LEDGER.name
        self.bindings = self.auto / PRODUCTION_BINDINGS.name
        self.evidence.parent.mkdir(parents=True)
        shutil.copyfile(PRODUCTION_LEDGER, self.ledger)
        shutil.copyfile(PRODUCTION_BINDINGS, self.bindings)
        records = read_bindings(PRODUCTION_BINDINGS)
        relative_files = set()
        for record in records:
            if record.get("record_type") != "post_ledger_identity_binding":
                continue
            relative_files.add(record["source"]["path"])
            relative_files.add(record["source"]["evidence_path"])
        for relative in relative_files:
            source = ROOT / relative
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def close(self):
        self.temp.cleanup()

    def load(self):
        rows, hashes = read_ledger(self.ledger)
        return identity.load_identity_bindings(
            ledger_path=self.ledger,
            rows=rows,
            row_sha256=hashes,
            bindings_path=self.bindings,
            repo_root=self.root,
        )

    def records(self):
        return read_bindings(self.bindings)

    def save_records(self, records, final_newline=True):
        write_jsonl(self.bindings, records, final_newline=final_newline)

    def sync_evidence_hash(self, records):
        digest = hashlib.sha256(self.evidence.read_bytes()).hexdigest().upper()
        for record in records:
            if (
                record.get("record_type") == "post_ledger_identity_binding"
                and record["source"]["evidence_path"].endswith(
                    PRODUCTION_EVIDENCE.name
                )
            ):
                record["source"]["evidence_sha256"] = digest
        reseal(records)


class IdentityBindingTests(unittest.TestCase):
    def setUp(self):
        self.box = BindingSandbox()

    def tearDown(self):
        self.box.close()

    def assert_invalid_atomic(self):
        bindings, report = self.box.load()
        self.assertEqual({}, bindings)
        self.assertEqual("INVALID", report["state"])
        self.assertEqual(0, report["binding_count"])
        self.assertTrue(report["errors"])

    def assert_invalid_box(self, box):
        bindings, report = box.load()
        self.assertEqual({}, bindings)
        self.assertEqual("INVALID", report["state"])
        self.assertEqual(0, report["binding_count"])
        self.assertTrue(report["errors"])

    def rewrite_public_observation(
        self, box, line, mutate, *, recompute_text_identity=False,
        retarget_line=None,
    ):
        records = box.records()
        binding = next(
            item for item in records
            if item.get("record_type") == "post_ledger_identity_binding"
            and item["target"]["line"] == line
        )
        source_path = box.root / binding["source"]["path"]
        source_payload = json.loads(source_path.read_text(encoding="utf-8"))
        selected = source_payload["observations"][0]
        mutate(selected)

        if retarget_line is not None:
            physical = box.ledger.read_text(encoding="utf-8").splitlines()
            target_hash = hashlib.sha256(
                physical[retarget_line - 1].encode("utf-8")
            ).hexdigest().upper()
            selected["ledger_line"] = retarget_line
            selected["ledger_row_sha256"] = target_hash
            binding["target"]["line"] = retarget_line
            binding["target"]["row_sha256"] = target_hash

        source_path.write_text(
            json.dumps(source_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest().upper()
        binding["source"]["sha256"] = source_sha

        evidence_path = box.root / binding["source"]["evidence_path"]
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence_id = binding["source"]["evidence_field"].split("=", 1)[1].split("]", 1)[0]
        evidence_record = next(
            item for item in evidence_payload["records"]
            if item["evidence_id"] == evidence_id
        )
        evidence_record["source_sha256"] = source_sha
        evidence_record["value"]["observation_id"] = selected["observation_id"]
        evidence_record["value"]["observation_sha256"] = hashlib.sha256(
            identity._canonical_json(selected)
        ).hexdigest().upper()
        evidence_path.write_text(
            json.dumps(evidence_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest().upper()
        for record in records:
            if (
                record.get("record_type") == "post_ledger_identity_binding"
                and record["source"]["evidence_path"] == binding["source"]["evidence_path"]
            ):
                record["source"]["evidence_sha256"] = evidence_sha

        if recompute_text_identity:
            exact_text = selected.get("observed_text", selected.get("rendered_text"))
            text_hash = hashlib.sha1(normalize(exact_text).encode("utf-8")).hexdigest()
            binding["identity"]["value"] = text_hash
            binding["identity"]["value_sha256"] = identity.identity_value_sha256(
                text_hash
            )
        reseal(records)
        box.save_records(records)

    def test_01_production_overlay_applies_only_proven_rows(self):
        before = hashlib.sha256(PRODUCTION_LEDGER.read_bytes()).hexdigest()
        rows, hashes = read_ledger(PRODUCTION_LEDGER)
        bindings, report = identity.load_identity_bindings(
            ledger_path=PRODUCTION_LEDGER,
            rows=rows,
            row_sha256=hashes,
            bindings_path=PRODUCTION_BINDINGS,
            repo_root=ROOT,
        )
        after = hashlib.sha256(PRODUCTION_LEDGER.read_bytes()).hexdigest()
        self.assertEqual(before, after, "reader must never rewrite historical rows")
        self.assertEqual("PASS", report["state"])
        self.assertEqual(EXPECTED_LINES, report["applied_lines"])
        self.assertEqual(80, len(bindings))
        self.assertEqual(6, report["seal_count"])
        self.assertEqual(["qt-02"], report["quarantined_non_reusable"])

    def test_02_payload_tampering_is_rejected_without_partial_apply(self):
        records = self.box.records()
        records[0]["identity"]["value"] += "-tampered"
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_03_target_row_tampering_is_rejected_even_after_reseal(self):
        records = self.box.records()
        records[0]["target"]["row_sha256"] = "A" * 64
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_04_duplicate_target_line_is_ambiguous_and_rejected(self):
        records = self.box.records()
        records[1]["target"] = copy.deepcopy(records[0]["target"])
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_05_reordering_breaks_the_append_only_hash_chain(self):
        records = self.box.records()
        records[0], records[1] = records[1], records[0]
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_06_evidence_file_tampering_is_rejected(self):
        payload = json.loads(self.box.evidence.read_text(encoding="utf-8"))
        payload["purpose"] += " tampered"
        self.box.evidence.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.assert_invalid_atomic()

    def test_07_source_provenance_change_is_rejected_after_reseal(self):
        records = self.box.records()
        records[0]["source"]["field"] = "items[id=another-item]"
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_08_ambiguous_source_evidence_id_is_rejected(self):
        payload = json.loads(self.box.evidence.read_text(encoding="utf-8"))
        payload["records"].append(copy.deepcopy(payload["records"][0]))
        self.box.evidence.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        records = self.box.records()
        self.box.sync_evidence_hash(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_09_exact_text_cannot_be_swapped_with_another_caption(self):
        payload = json.loads(self.box.evidence.read_text(encoding="utf-8"))
        evidence = next(
            item for item in payload["records"]
            if item["evidence_id"] == "knowledge-kn-21-threads"
        )
        evidence["value"]["exact_text"] = "ข้อความอื่นที่ยาวพอแต่ไม่ตรงกับโพสต์เดิม " * 3
        self.box.evidence.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        records = self.box.records()
        binding = next(
            item for item in records
            if item.get("record_type") == "post_ledger_identity_binding"
            and item["target"]["line"] == 141
        )
        value = evidence["value"]["exact_text"]
        new_hash = hashlib.sha1(normalize(value).encode("utf-8")).hexdigest()
        binding["identity"]["value"] = new_hash
        binding["identity"]["value_sha256"] = identity.identity_value_sha256(new_hash)
        self.box.sync_evidence_hash(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_10_qt02_quarantine_cannot_be_relaxed(self):
        records = self.box.records()
        for record in records:
            if (
                record.get("record_type") == "post_ledger_identity_binding"
                and record["identity"]["value"] == "qt-02"
            ):
                record["reuse_policy"] = "PERMANENT_DEDUP"
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_11_native_identity_cannot_be_overwritten(self):
        physical = self.box.ledger.read_text(encoding="utf-8").splitlines()
        row = json.loads(physical[56])
        row["clip_key"] = "save"
        physical[56] = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        self.box.ledger.write_text("\n".join(physical) + "\n", encoding="utf-8")
        records = self.box.records()
        records[0]["target"]["row_sha256"] = hashlib.sha256(
            physical[56].encode("utf-8")
        ).hexdigest().upper()
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_12_missing_commit_newline_is_rejected(self):
        records = self.box.records()
        self.box.save_records(records, final_newline=False)
        self.assert_invalid_atomic()

    def test_13_integration_improves_coverage_and_tombstones_all_known_collisions(self):
        self.box.bindings.unlink()
        baseline = ledger.permanent_dedup_completeness(self.box.ledger)
        self.assertEqual((44, 81, 35.2), (
            baseline["complete_rows"], baseline["incomplete_rows"],
            baseline["coverage_percent"],
        ))
        metric = ledger.permanent_dedup_completeness(PRODUCTION_LEDGER)
        self.assertEqual("BLOCKED", metric["state"])
        self.assertEqual((124, 1, 125, 99.2), (
            metric["complete_rows"], metric["incomplete_rows"],
            metric["identity_rows"], metric["coverage_percent"],
        ))
        self.assertEqual(80, metric["applied_identity_bindings"])
        self.assertEqual("PASS", metric["collision_tombstone_state"])
        self.assertEqual(0, metric["duplicate_identity_groups"])
        self.assertEqual(3, metric["historical_duplicate_identity_groups"])
        self.assertEqual(3, metric["tombstoned_duplicate_identity_groups"])
        self.assertEqual([], metric["duplicate_identities"])
        tombstoned_duplicates = {
            (item["channel"], item["identity"]): [
                occurrence["line"] for occurrence in item["occurrences"]
            ]
            for item in metric["tombstoned_duplicate_identities"]
        }
        self.assertEqual({
            ("tiktok", "titleloan"): [1, 19],
            ("ig", "aed0406157eb7257c3bf86c7906a6822f8b86e79"): [63, 89],
            ("yt", "90e43a4ddc4d3da3f72e17d10fd38f153e0741bc"): [
                31, 47, 55, 62, 70, 78, 87, 94, 103, 113, 120, 129,
                137, 155,
            ],
        }, tombstoned_duplicates)

    def test_14_text_binding_participates_in_exact_permanent_dedup(self):
        # Reduce the fixture to the one proven text publication so coverage is complete.
        production_rows = PRODUCTION_LEDGER.read_text(encoding="utf-8").splitlines()
        target_row = production_rows[140]
        self.box.ledger.write_text(target_row + "\n", encoding="utf-8")
        fixture_records = self.box.records()
        records = [
            copy.deepcopy(item) for item in self.box.records()
            if item.get("record_type") == "post_ledger_identity_binding"
            and item["target"]["line"] == 141
        ]
        records.append(copy.deepcopy(fixture_records[-1]))
        records[0]["target"]["line"] = 1
        records[0]["target"]["row_sha256"] = hashlib.sha256(
            target_row.encode("utf-8")
        ).hexdigest().upper()
        reseal(records)
        self.box.save_records(records)
        evidence = json.loads(self.box.evidence.read_text(encoding="utf-8"))
        exact = next(
            item["value"]["exact_text"] for item in evidence["records"]
            if item["evidence_id"] == "knowledge-kn-21-threads"
        )
        allowed, _, metric = ledger.permanent_dedup_gate(self.box.ledger)
        self.assertTrue(allowed, metric)
        duplicate, reason, _ = ledger.is_duplicate_text(
            "threads", exact + " https://example.com", path=self.box.ledger
        )
        self.assertTrue(duplicate)
        self.assertIn("exact duplicate (permanent)", reason)

    def test_15_qt02_binding_enforces_global_non_reuse(self):
        production_rows = PRODUCTION_LEDGER.read_text(encoding="utf-8").splitlines()
        target_row = production_rows[80]
        self.box.ledger.write_text(target_row + "\n", encoding="utf-8")
        fixture_records = self.box.records()
        records = [
            copy.deepcopy(item) for item in self.box.records()
            if item.get("record_type") == "post_ledger_identity_binding"
            and item["target"]["line"] == 81
        ]
        records.append(copy.deepcopy(fixture_records[-1]))
        records[0]["target"]["line"] = 1
        records[0]["target"]["row_sha256"] = hashlib.sha256(
            target_row.encode("utf-8")
        ).hexdigest().upper()
        reseal(records)
        self.box.save_records(records)
        index = ledger.load_index(self.box.ledger)
        duplicate, reason, finding = ledger.is_twin(
            index, "pinterest", "qt-02", "2027-01-01"
        )
        self.assertTrue(duplicate)
        self.assertIn("quarantined and non-reusable", reason)
        self.assertEqual(["QUARANTINED_NON_REUSABLE"], finding)

    def test_16_snapshot_matches_every_cited_source_hash_and_field(self):
        payload = json.loads(PRODUCTION_EVIDENCE.read_text(encoding="utf-8"))
        json_cache = {}
        table_cache = {}
        for evidence in payload["records"]:
            source_path = ROOT / evidence["source_path"]
            self.assertEqual(
                evidence["source_sha256"],
                hashlib.sha256(source_path.read_bytes()).hexdigest().upper(),
            )
            field = evidence["source_field"]
            if field.startswith("items[id="):
                data = json_cache.setdefault(
                    source_path, json.loads(source_path.read_text(encoding="utf-8-sig"))
                )
                content_id = field[len("items[id="):-1]
                item = next(row for row in data["items"] if row["id"] == content_id)
                expected = {
                    "id": item["id"], "date": item["date"], "reel": item["reel"],
                    "posted": item["posted"],
                }
            elif field.startswith("items[content_id="):
                data = json_cache.setdefault(
                    source_path, json.loads(source_path.read_text(encoding="utf-8-sig"))
                )
                content_id = field[len("items[content_id="):-1]
                item = next(
                    row for row in data["items"] if row["content_id"] == content_id
                )
                expected = {
                    key: item[key] for key in (
                        "content_id", "asset", "sha256", "status", "channels",
                        "published_date",
                    )
                }
            else:
                match = identity.KNOWLEDGE_FIELD_RE.fullmatch(field)
                self.assertIsNotNone(match, field)
                if source_path not in table_cache:
                    table = {}
                    for line in source_path.read_text(encoding="utf-8-sig").splitlines():
                        if not line.startswith("| 2026-"):
                            continue
                        parts = [
                            value.strip()
                            for value in line.strip().strip("|").split("|")
                        ]
                        self.assertEqual(5, len(parts))
                        date, content_id, _topic, threads, facebook = parts
                        table[content_id] = {
                            "date": date,
                            "threads": threads.replace("<br>", "\n"),
                            "facebook": facebook.replace("<br>", "\n"),
                        }
                    table_cache[source_path] = table
                content_id, field_name = match.groups()
                channel = "threads" if field_name == "threads_text" else "facebook"
                row = table_cache[source_path][content_id]
                expected = {
                    "id": content_id, "date": row["date"], "channel": channel,
                    "exact_text": row[channel],
                }
            self.assertEqual(expected, evidence["value"], evidence["evidence_id"])

    def test_17_missing_bound_ledger_is_not_treated_as_empty_initialization(self):
        self.box.ledger.unlink()
        metric = ledger.permanent_dedup_completeness(self.box.ledger)
        self.assertEqual("BLOCKED", metric["state"])
        self.assertEqual("UNKNOWN", metric["integrity_state"])
        self.assertTrue(any("overlay still exists" in item for item in metric["failures"]))

    def test_18_clean_tail_truncation_is_rejected_by_final_seal_requirement(self):
        records = self.box.records()
        # Keep the final appended binding but remove its closing seal.  Removing
        # both would merely expose the previous valid seal and is not truncation
        # evidence after a later append-only recovery.
        self.box.save_records(records[:-1], final_newline=True)
        self.assert_invalid_atomic()

    def test_19_duplicate_key_in_sealed_binding_jsonl_is_rejected(self):
        lines = self.box.bindings.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace(
            "{", '{"schema_version":999,', 1
        )
        self.box.bindings.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assert_invalid_atomic()

    def test_20_duplicate_key_in_hash_bound_evidence_is_rejected(self):
        raw = self.box.evidence.read_text(encoding="utf-8")
        ambiguous = raw.replace(
            '"evidence_id":',
            '"evidence_id": "shadow-evidence",\n      "evidence_id":',
            1,
        )
        self.assertNotEqual(raw, ambiguous)
        self.box.evidence.write_text(ambiguous, encoding="utf-8")
        records = self.box.records()
        self.box.sync_evidence_hash(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_21_nested_overflow_number_is_rejected_by_strict_parser(self):
        with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
            identity._strict_json_loads('{"nested":[{"value":1e999}]}')

    def test_22_kn01_descriptor_cannot_be_changed_after_rebinding(self):
        records = self.box.records()
        target = next(
            item for item in records
            if item.get("record_type") == "post_ledger_identity_binding"
            and item["target"]["line"] == 41
        )
        lines = self.box.ledger.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[40])
        row["text_first80"] = row["text_first80"].replace("kn-01", "kn-99", 1)
        lines[40] = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        self.box.ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
        target["target"]["row_sha256"] = hashlib.sha256(
            lines[40].encode("utf-8")
        ).hexdigest().upper()
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_23_kn01_manual_publication_proof_is_mandatory(self):
        records = self.box.records()
        target_records = [
            item for item in records
            if item.get("record_type") == "post_ledger_identity_binding"
            and item["target"]["line"] in {41, 48}
        ]
        self.assertEqual(2, len(target_records))
        source = self.box.root / target_records[0]["source"]["path"]
        raw = source.read_text(encoding="utf-8-sig")
        proof = (
            "kn-01 ถูกโพสต์จริงไปแล้ววันที่ 19 ก.ค. "
            "(Threads 17:30 + FB 21:28)"
        )
        self.assertIn(proof, raw)
        source.write_text(raw.replace(proof, "kn-01 manual proof removed"), encoding="utf-8")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest().upper()
        evidence_path = self.box.root / target_records[0]["source"]["evidence_path"]
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        for item in evidence["records"]:
            item["source_sha256"] = source_hash
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        evidence_hash = hashlib.sha256(evidence_path.read_bytes()).hexdigest().upper()
        for record in target_records:
            record["source"]["sha256"] = source_hash
            record["source"]["evidence_sha256"] = evidence_hash
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_24_private_commitments_are_complete_and_privacy_sanitized(self):
        commitment_raw = PRODUCTION_PRIVATE_COMMITMENT.read_text(encoding="utf-8")
        evidence_raw = PRODUCTION_PRIVATE_EVIDENCE.read_text(encoding="utf-8")
        leak = re.compile(
            r"(?i)(?:[A-Z]:[\\/]|/Users/|\\\\Users\\\\|"
            r"local_[0-9a-f]{8}-)"
        )
        self.assertIsNone(leak.search(commitment_raw))
        self.assertIsNone(leak.search(evidence_raw))
        payload = identity._strict_json_loads(commitment_raw)
        self.assertEqual(PRIVATE_LINES, [x["ledger_line"] for x in payload["records"]])
        for item in payload["records"]:
            self.assertEqual(identity.PRIVATE_COMMITMENT_VALUE_KEYS, set(item))
            self.assertEqual(
                identity.PRIVATE_COMMITMENT_PRIVACY_STATUS,
                item["privacy_status"],
            )
        time_join_lines = [
            item["ledger_line"] for item in payload["records"]
            if item["join_mode"] == "exact_task_date_time_tool_input_set"
        ]
        self.assertEqual(
            sorted(identity.PRIVATE_SESSION_ZERO_PREFIX_LINES), time_join_lines
        )

    def test_25_private_identity_cannot_be_redirected_after_full_rehash(self):
        commitment_path = self.box.root / identity.PRIVATE_COMMITMENT_SOURCE
        commitment = json.loads(commitment_path.read_text(encoding="utf-8"))
        item = next(x for x in commitment["records"] if x["ledger_line"] == 27)
        item["text_identity_sha1"] = "0" * 40
        commitment_path.write_text(
            json.dumps(commitment, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        source_sha = hashlib.sha256(commitment_path.read_bytes()).hexdigest().upper()

        evidence_path = self.box.root / (
            "automation-log/dedup-evidence/"
            "post-ledger-identity-sources-private-session-v1.json"
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        for evidence_item in evidence["records"]:
            evidence_item["source_sha256"] = source_sha
            if evidence_item["evidence_id"] == "private-session-line-000027":
                evidence_item["value"] = copy.deepcopy(item)
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest().upper()

        records = self.box.records()
        for record in records:
            if (
                record.get("record_type") == "post_ledger_identity_binding"
                and record["source"]["path"] == identity.PRIVATE_COMMITMENT_SOURCE
            ):
                record["source"]["sha256"] = source_sha
                record["source"]["evidence_sha256"] = evidence_sha
                if record["target"]["line"] == 27:
                    record["identity"]["value"] = "0" * 40
                    record["identity"]["value_sha256"] = (
                        identity.identity_value_sha256("0" * 40)
                    )
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()

    def test_26_public_web_observations_are_exact_and_privacy_safe(self):
        evidence = json.loads(
            PRODUCTION_PUBLIC_WEB_EVIDENCE.read_text(encoding="utf-8")
        )
        self.assertEqual(3, len(evidence["records"]))
        by_id = {item["evidence_id"]: item for item in evidence["records"]}
        self.assertEqual(3, len(by_id))
        source_paths = {
            ROOT / item["source_path"] for item in evidence["records"]
        }
        leak = re.compile(
            r"(?i)(?:(?<![A-Z])[A-Z]:[\\/]|/Users/|\\\\Users\\\\|"
            r"local_[0-9a-f]{8}-|"
            r'"(?:session_?id|browser_?session|cookie|authorization)"\s*:)'
        )
        combined = PRODUCTION_PUBLIC_WEB_EVIDENCE.read_text(encoding="utf-8")
        for path in source_paths:
            raw = path.read_text(encoding="utf-8")
            combined += raw
            payload = json.loads(raw)
            self.assertEqual(1, len(payload["observations"]))
            observation = payload["observations"][0]
            evidence_record = by_id[observation["observation_id"]]
            self.assertEqual(
                evidence_record["source_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            )
            self.assertEqual(
                evidence_record["value"]["observation_sha256"],
                hashlib.sha256(identity._canonical_json(observation)).hexdigest().upper(),
            )
            exact_text = observation.get(
                "observed_text", observation.get("rendered_text")
            )
            declared_length = observation.get(
                "observed_text_length", observation.get("rendered_text_length")
            )
            declared_hash = observation.get(
                "observed_text_sha256", observation.get("rendered_text_sha256")
            )
            self.assertEqual(declared_length, len(exact_text))
            self.assertEqual(
                declared_hash,
                hashlib.sha256(exact_text.encode("utf-8")).hexdigest().upper(),
            )
        self.assertIsNone(leak.search(combined))
        self.assertNotIn("fbclid=", combined.casefold())

    def test_27_public_observation_url_redirection_is_rejected_after_full_rehash(self):
        cases = [
            (45, "target_post_url", "https://www.facebook.com/groups/1/posts/2/"),
            (53, "canonical_url", "https://pantip.com/topic/44168590/comment4"),
            (109, "resolved_parent_url", "https://www.facebook.com/1/posts/2/"),
        ]
        for line, field, replacement in cases:
            with self.subTest(line=line, field=field):
                box = BindingSandbox()
                try:
                    self.rewrite_public_observation(
                        box, line,
                        lambda item, f=field, v=replacement: item.__setitem__(f, v),
                    )
                    self.assert_invalid_box(box)
                finally:
                    box.close()

    def test_28_wrong_comment_id_or_author_is_rejected_after_full_rehash(self):
        cases = [
            (45, "comment_id", "2410314352797819"),
            (45, "actor_display", "another actor"),
            (53, "comment_id", "119809717"),
            (53, "author_display", "สมาชิกหมายเลข 1"),
            (109, "comment_id", "1028158030069587"),
            (109, "page_actor", "another page"),
        ]
        for line, field, replacement in cases:
            with self.subTest(line=line, field=field):
                box = BindingSandbox()
                try:
                    self.rewrite_public_observation(
                        box, line,
                        lambda item, f=field, v=replacement: item.__setitem__(f, v),
                    )
                    self.assert_invalid_box(box)
                finally:
                    box.close()

    def test_29_wrong_display_time_is_rejected_after_full_rehash(self):
        for line in PUBLIC_WEB_LINES:
            with self.subTest(line=line):
                box = BindingSandbox()
                try:
                    self.rewrite_public_observation(
                        box, line,
                        lambda item: item.__setitem__("displayed_time", "เวลาอื่น"),
                    )
                    self.assert_invalid_box(box)
                finally:
                    box.close()

    def test_30_public_observation_cannot_be_retargeted_to_another_ledger_row(self):
        for line in PUBLIC_WEB_LINES:
            with self.subTest(line=line):
                box = BindingSandbox()
                try:
                    self.rewrite_public_observation(
                        box, line, lambda _item: None, retarget_line=33,
                    )
                    self.assert_invalid_box(box)
                finally:
                    box.close()

    def test_31_public_text_and_hash_tampering_fail_after_full_rehash(self):
        for line in PUBLIC_WEB_LINES:
            with self.subTest(line=line, mutation="text"):
                box = BindingSandbox()
                try:
                    def change_text(item):
                        text_key = (
                            "observed_text" if "observed_text" in item
                            else "rendered_text"
                        )
                        length_key = text_key.replace("text", "text_length")
                        hash_key = text_key.replace("text", "text_sha256")
                        item[text_key] = item[text_key][:-1] + "X"
                        item[length_key] = len(item[text_key])
                        item[hash_key] = hashlib.sha256(
                            item[text_key].encode("utf-8")
                        ).hexdigest().upper()

                    self.rewrite_public_observation(
                        box, line, change_text, recompute_text_identity=True,
                    )
                    self.assert_invalid_box(box)
                finally:
                    box.close()
            with self.subTest(line=line, mutation="declared_hash"):
                box = BindingSandbox()
                try:
                    self.rewrite_public_observation(
                        box, line,
                        lambda item: item.__setitem__(
                            "observed_text_sha256"
                            if "observed_text_sha256" in item
                            else "rendered_text_sha256",
                            "0" * 64,
                        ),
                    )
                    self.assert_invalid_box(box)
                finally:
                    box.close()

    def test_32_tracking_redirect_or_fbclid_cannot_replace_normalized_merchant_link(self):
        for replacement in (
            "https://l.facebook.com/l.php?u=https%3A%2F%2Fngernduangold.com",
            "https://ngernduangold.com/debt-calculator?utm_source=fb&"
            "utm_medium=comment&fbclid=transient",
        ):
            with self.subTest(replacement=replacement):
                box = BindingSandbox()
                try:
                    self.rewrite_public_observation(
                        box, 109,
                        lambda item, v=replacement: item.__setitem__(
                            "normalized_merchant_link", v
                        ),
                    )
                    self.assert_invalid_box(box)
                finally:
                    box.close()

    def test_33_only_one_unproven_legacy_row_remains_blocked(self):
        report = ledger.inspect_ledger(PRODUCTION_LEDGER)
        coverage = report["identity_coverage"]
        self.assertEqual("PASS", report["identity_binding_report"]["state"])
        self.assertEqual((124, 1), (
            coverage["complete_rows"], coverage["incomplete_rows"]
        ))
        self.assertEqual(
            [39], [item["line"] for item in coverage["legacy_incomplete"]]
        )

    def test_34_line_broadcast_source_copy_cannot_drift_after_full_reseal(self):
        records = self.box.records()
        binding = next(
            item for item in records
            if item.get("record_type") == "post_ledger_identity_binding"
            and item["target"]["line"] == 33
        )
        source_path = self.box.root / binding["source"]["path"]
        source_text = source_path.read_text(encoding="utf-8")
        self.assertIn("\n## เวอร์ชัน B", source_text)
        source_path.write_text(
            source_text.replace(
                "\n## เวอร์ชัน B", "\nchanged\n\n## เวอร์ชัน B", 1
            ),
            encoding="utf-8",
        )

        evidence_path = self.box.root / binding["source"]["evidence_path"]
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        body = identity._line_broadcast_section_value(
            source_path.read_bytes(), binding["source"]
        )
        evidence_record = evidence["records"][0]
        evidence_record["source_sha256"] = hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest().upper()
        evidence_record["value"]["text_sha256"] = hashlib.sha256(
            body.encode("utf-8")
        ).hexdigest().upper()
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        new_identity = hashlib.sha1(normalize(body).encode("utf-8")).hexdigest()
        binding["source"]["sha256"] = evidence_record["source_sha256"]
        binding["source"]["evidence_sha256"] = hashlib.sha256(
            evidence_path.read_bytes()
        ).hexdigest().upper()
        binding["identity"]["value"] = new_identity
        binding["identity"]["value_sha256"] = identity.identity_value_sha256(
            new_identity
        )
        reseal(records)
        self.box.save_records(records)
        self.assert_invalid_atomic()


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
