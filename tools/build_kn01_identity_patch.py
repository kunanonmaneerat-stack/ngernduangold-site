#!/usr/bin/env python3
"""Emit an apply_patch payload for the two deterministic kn-01 manual rows.

The helper is read-only and idempotent.  It refuses to overwrite evidence or
append duplicate target lines; the caller must apply the emitted patch through
the normal reviewed file-edit path.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / "automation-log"
LEDGER = AUTO / "post-ledger.jsonl"
BINDINGS = AUTO / "post-ledger-identity-bindings.jsonl"
SOURCE_REL = "automation-log/KNOWLEDGE-POSTS_20260720-0802.md"
SOURCE = ROOT / SOURCE_REL
EVIDENCE_REL = (
    "automation-log/dedup-evidence/"
    "post-ledger-identity-sources-kn01-v1.json"
)
EVIDENCE = ROOT / EVIDENCE_REL

spec = importlib.util.spec_from_file_location(
    "post_ledger_identity", AUTO / "post_ledger_identity.py"
)
identity = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(identity)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def table_value(field: str) -> str:
    matches = []
    for line in SOURCE.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("| 2026-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[1] == "kn-01":
            matches.append(cells)
    if len(matches) != 1:
        raise AssertionError("kn-01 source row is missing or ambiguous")
    cell = matches[0][3 if field == "threads_text" else 4]
    return cell.replace("<br>", "\n")


def patch_escape(value: str) -> str:
    return "\n".join("+" + line for line in value.splitlines())


def main() -> int:
    if EVIDENCE.exists():
        raise SystemExit(f"refusing to overwrite existing {EVIDENCE_REL}")
    raw_lines = LEDGER.read_bytes().split(b"\n")[:-1]
    rows = [json.loads(raw.decode("utf-8")) for raw in raw_lines]
    row_hashes = {
        number: sha256(raw.rstrip(b"\r"))
        for number, raw in enumerate(raw_lines, 1)
    }
    existing = [
        json.loads(line)
        for line in BINDINGS.read_text(encoding="utf-8").splitlines()
    ]
    targets = {
        record["target"]["line"]
        for record in existing
        if record.get("record_type") == "post_ledger_identity_binding"
    }
    if targets & {41, 48}:
        raise SystemExit("kn-01 target binding already exists")
    if not existing or existing[-1].get("record_type") != "post_ledger_identity_binding_seal":
        raise AssertionError("identity binding ledger lacks a terminal seal")

    specs = [
        (41, "threads", "threads_text"),
        (48, "facebook", "fb_text"),
    ]
    source_hash = sha256(SOURCE.read_bytes())
    evidence_records = []
    prepared = []
    for line_no, channel, field in specs:
        row = rows[line_no - 1]
        if row.get("type") != "text" or row.get("channel") != channel:
            raise AssertionError(f"ledger line {line_no} no longer matches kn-01")
        exact_text = table_value(field)
        value = {
            "id": "kn-01",
            "date": "2026-07-19",
            "channel": channel,
            "text_sha256": sha256(exact_text.encode("utf-8")),
            "join_mode": "kn01_manual_descriptor",
        }
        evidence_id = f"legacy-line-{line_no:06d}"
        evidence_records.append({
            "evidence_id": evidence_id,
            "source_path": SOURCE_REL,
            "source_sha256": source_hash,
            "source_field": f"table[id=kn-01].{field}",
            "value": value,
        })
        prepared.append((line_no, channel, field, exact_text, value, evidence_id))

    evidence_payload = {
        "schema_version": 1,
        "created_at": "2026-08-24T19:20:00+07:00",
        "purpose": (
            "Exact hash-bound repair for the two kn-01 manual publication "
            "descriptors; no publication or delivery fact is created."
        ),
        "records": evidence_records,
    }
    evidence_text = json.dumps(
        evidence_payload, ensure_ascii=False, indent=2
    ) + "\n"
    evidence_hash = sha256(evidence_text.encode("utf-8"))

    previous = existing[-1]["seal_sha256"]
    appended = []
    for line_no, channel, field, exact_text, value, evidence_id in prepared:
        identity_value = identity._text_hash(exact_text)
        record = {
            "schema_version": 1,
            "record_type": "post_ledger_identity_binding",
            "binding_id": f"plid-v1-{line_no:06d}",
            "previous_binding_sha256": previous,
            "target": {
                "ledger_path": "automation-log/post-ledger.jsonl",
                "line": line_no,
                "row_sha256": row_hashes[line_no],
            },
            "source": {
                "path": SOURCE_REL,
                "sha256": source_hash,
                "field": f"table[id=kn-01].{field}",
                "evidence_path": EVIDENCE_REL,
                "evidence_sha256": evidence_hash,
                "evidence_field": f"records[evidence_id={evidence_id}].value",
            },
            "evidence_type": "knowledge_manual_descriptor_join",
            "identity": {
                "kind": "text_hash",
                "value": identity_value,
                "value_sha256": identity.identity_value_sha256(identity_value),
            },
            "reuse_policy": "PERMANENT_DEDUP",
        }
        record["binding_sha256"] = identity.binding_sha256(record)
        previous = record["binding_sha256"]
        appended.append(record)

    all_targets = sorted(targets | {41, 48})
    seal = {
        "schema_version": 1,
        "record_type": "post_ledger_identity_binding_seal",
        "binding_count": len(all_targets),
        "sealed_target_lines": all_targets,
        "previous_record_sha256": previous,
    }
    seal["seal_sha256"] = identity.seal_sha256(seal)
    appended.append(seal)

    last_line = BINDINGS.read_text(encoding="utf-8").splitlines()[-1]
    append_text = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in appended
    )
    patch = (
        "*** Begin Patch\n"
        f"*** Add File: {EVIDENCE_REL}\n"
        f"{patch_escape(evidence_text.rstrip(chr(10)))}\n"
        "*** Update File: automation-log/post-ledger-identity-bindings.jsonl\n"
        "@@\n"
        f" {last_line}\n"
        f"{patch_escape(append_text)}\n"
        "*** End Patch\n"
    )
    sys.stdout.write(patch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
