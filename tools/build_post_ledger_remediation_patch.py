#!/usr/bin/env python3
"""Emit an apply_patch payload for deterministic legacy identity remediation.

This helper is intentionally read-only.  It recomputes every source/row/content hash
from the current repository and emits a patch; it never edits the ledger, bindings,
or evidence itself.  Candidates without an exact prefix/source join are omitted.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / "automation-log"
LEDGER = AUTO / "post-ledger.jsonl"
BINDINGS = AUTO / "post-ledger-identity-bindings.jsonl"
EVIDENCE_REL = "automation-log/dedup-evidence/post-ledger-identity-sources-v2.json"
EVIDENCE = ROOT / EVIDENCE_REL

sys.path.insert(0, str(AUTO))
spec = importlib.util.spec_from_file_location("post_ledger_identity", AUTO / "post_ledger_identity.py")
identity = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(identity)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def source_hash(relative: str) -> str:
    return sha256((ROOT / relative).read_bytes())


def table_rows(relative: str, page2: bool = False) -> list[dict]:
    result = []
    for line in (ROOT / relative).read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("| 2026-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if page2:
            if len(cells) != 4:
                raise AssertionError((relative, cells))
            date, content_id, _topic, facebook = cells
            result.append({
                "date": date, "id": content_id, "channel": "facebook-page2",
                "text": html.unescape(facebook.replace("<br>", "\n")),
                "field": f"table[id={content_id}].fb_text",
            })
        else:
            if len(cells) != 5:
                raise AssertionError((relative, cells))
            date, content_id, _topic, threads, facebook = cells
            result.extend([
                {
                    "date": date, "id": content_id, "channel": "threads",
                    "text": html.unescape(threads.replace("<br>", "\n")),
                    "field": f"table[id={content_id}].threads_text",
                },
                {
                    "date": date, "id": content_id, "channel": "facebook",
                    "text": html.unescape(facebook.replace("<br>", "\n")),
                    "field": f"table[id={content_id}].fb_text",
                },
            ])
    return result


def exact_range(relative: str, start: int, end: int) -> str:
    lines = (ROOT / relative).read_text(encoding="utf-8-sig").splitlines()
    return "\n".join(lines[start - 1:end]).strip()


def patch_escape(lines: str) -> str:
    return "\n".join("+" + line for line in lines.splitlines())


def main() -> int:
    if EVIDENCE.exists():
        raise SystemExit(f"refusing to overwrite existing {EVIDENCE_REL}")
    raw_lines = LEDGER.read_bytes().split(b"\n")[:-1]
    rows = [json.loads(raw.decode("utf-8")) for raw in raw_lines]
    row_hashes = {number: sha256(raw.rstrip(b"\r")) for number, raw in enumerate(raw_lines, 1)}
    existing = [json.loads(line) for line in BINDINGS.read_text(encoding="utf-8").splitlines()]
    existing_targets = {
        record["target"]["line"] for record in existing
        if record.get("record_type") == "post_ledger_identity_binding"
    }

    candidates = []
    for relative in (
        "automation-log/KNOWLEDGE-POSTS_20260720-0802.md",
        "automation-log/KNOWLEDGE-POSTS-B_20260802-0815.md",
    ):
        for item in table_rows(relative):
            for line_no, row in enumerate(rows, 1):
                if line_no in existing_targets or row.get("type") != "text":
                    continue
                prefix = str(row.get("text_first80") or "")
                exact = item["text"].startswith(prefix)
                whitespace_equivalent = "".join(item["text"].split()).startswith(
                    "".join(prefix.split())
                )
                if (
                    str(row.get("ts") or "")[:10] == item["date"]
                    and row.get("channel") == item["channel"]
                    and len(prefix) >= 40
                    and (exact or whitespace_equivalent)
                ):
                    candidates.append({
                        "line": line_no, "source": relative, "field": item["field"],
                        "evidence_type": "markdown_table_text_hash", "item": item,
                        "join_mode": "exact_prefix" if exact else "whitespace_equivalent_prefix",
                    })

    page2_relative = "automation-log/PAGE2-POSTS_20260721-0814.md"
    for item in table_rows(page2_relative, page2=True):
        for line_no, row in enumerate(rows, 1):
            prefix = str(row.get("text_first80") or "")
            if (
                line_no not in existing_targets and row.get("type") == "text"
                and row.get("channel") == item["channel"]
                and str(row.get("ts") or "")[:10] == item["date"]
                and item["id"] in str(row.get("note") or "")
                and len(prefix) >= 40 and item["text"].startswith(prefix)
            ):
                candidates.append({
                    "line": line_no, "source": page2_relative,
                    "field": item["field"], "evidence_type": "markdown_table_text_hash",
                    "item": item,
                    "join_mode": "exact_prefix",
                })

    line_ranges = [
        (28, "automation-log/_pantip_LIVE-opportunity_debt-cashflow-loop_20260716.md", 16, 28, "pantip-44163092"),
        (96, "automation-log/_pantip_draft_20260726.md", 24, 32, "pantip-renew-20260726"),
        (97, "automation-log/FBGROUP-LISTEN_20260726.md", 43, 57, "fbgroup-home-debt-20260726"),
    ]
    for line_no, relative, start, end, content_id in line_ranges:
        row = rows[line_no - 1]
        text = exact_range(relative, start, end)
        prefix = str(row.get("text_first80") or "")
        if line_no in existing_targets or len(prefix) < 40 or not text.startswith(prefix):
            raise AssertionError(f"line-range candidate {line_no} is no longer exact")
        candidates.append({
            "line": line_no, "source": relative, "field": f"lines[{start}:{end}]",
            "evidence_type": "markdown_line_range_text_hash",
            "item": {
                "id": content_id, "date": str(row["ts"])[:10],
                "channel": row["channel"], "text": text,
            },
            "join_mode": "exact_prefix",
        })

    manifest_relative = ".system_control/content_manifest.json"
    manifest = json.loads((ROOT / manifest_relative).read_text(encoding="utf-8-sig"))
    by_id = {item["id"]: item for item in manifest["items"]}
    manifest_specs = [
        (25, "2026-07-16_kp05", "exact_caption_prefix"),
        (26, "2026-07-17_eb02", "exact_caption_prefix"),
        (29, "2026-07-18_kp06", "whitespace_equivalent_caption_prefix"),
        (72, "2026-07-23_credit-bureau", "canonical_slug_descriptor"),
    ]
    for line_no, content_id, join_mode in manifest_specs:
        row = rows[line_no - 1]
        item = by_id[content_id]
        channel = row["channel"]
        caption = str((item.get("captions") or {}).get(channel) or "")
        prefix = str(row.get("text_first80") or "")
        if join_mode == "exact_caption_prefix" and not caption.startswith(prefix):
            raise AssertionError(f"manifest candidate {line_no} caption no longer matches")
        if join_mode == "whitespace_equivalent_caption_prefix" and not "".join(
            caption.split()
        ).startswith("".join(prefix.split())):
            raise AssertionError(f"manifest candidate {line_no} caption whitespace join no longer matches")
        if join_mode == "canonical_slug_descriptor" and content_id.split("_", 1)[-1] not in (
            prefix + " " + str(row.get("note") or "")
        ):
            raise AssertionError(f"manifest candidate {line_no} descriptor no longer matches")
        candidates.append({
            "line": line_no, "source": manifest_relative,
            "field": f"items[id={content_id}]",
            "evidence_type": "content_manifest_hash_join",
            "item": {
                "id": content_id, "date": item["date"], "channel": channel,
                "join_mode": join_mode,
                "caption_sha256": sha256(caption.encode("utf-8"))
                if join_mode in {"exact_caption_prefix", "whitespace_equivalent_caption_prefix"}
                else identity.ZERO_SHA256,
            },
        })

    candidates.sort(key=lambda item: item["line"])
    if len(candidates) != 33 or len({item["line"] for item in candidates}) != 33:
        raise AssertionError(f"expected 33 deterministic candidates, got {len(candidates)}")

    evidence_records = []
    for candidate in candidates:
        item = dict(candidate["item"])
        exact_text = item.pop("text", None)
        value = (
            {
                "id": item["id"], "date": item["date"], "channel": item["channel"],
                "text_sha256": sha256(exact_text.encode("utf-8")),
                "join_mode": candidate["join_mode"],
            }
            if exact_text is not None else item
        )
        evidence_records.append({
            "evidence_id": f"legacy-line-{candidate['line']:06d}",
            "source_path": candidate["source"],
            "source_sha256": source_hash(candidate["source"]),
            "source_field": candidate["field"],
            "value": value,
        })
        candidate["evidence_value"] = value
        candidate["exact_text"] = exact_text

    evidence_payload = {
        "schema_version": 1,
        "created_at": "2026-08-23T20:15:00+07:00",
        "purpose": (
            "Immutable deterministic source selectors and hashes for bounded legacy "
            "permanent-dedup identity repair; no post, delivery, or status fact is created."
        ),
        "records": evidence_records,
    }
    evidence_text = json.dumps(evidence_payload, ensure_ascii=False, indent=2) + "\n"
    evidence_sha = sha256(evidence_text.encode("utf-8"))

    previous = existing[-1]["seal_sha256"]
    all_targets = sorted(existing_targets | {item["line"] for item in candidates})
    appended = []
    for candidate in candidates:
        line_no = candidate["line"]
        value = candidate["evidence_value"]
        if candidate["evidence_type"] == "content_manifest_hash_join":
            identity_kind = "clip"
            identity_value = value["id"]
        else:
            identity_kind = "text_hash"
            identity_value = identity._text_hash(candidate["exact_text"])
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
                "path": candidate["source"],
                "sha256": source_hash(candidate["source"]),
                "field": candidate["field"],
                "evidence_path": EVIDENCE_REL,
                "evidence_sha256": evidence_sha,
                "evidence_field": f"records[evidence_id=legacy-line-{line_no:06d}].value",
            },
            "evidence_type": candidate["evidence_type"],
            "identity": {
                "kind": identity_kind,
                "value": identity_value,
                "value_sha256": identity.identity_value_sha256(identity_value),
            },
            "reuse_policy": "PERMANENT_DEDUP",
        }
        record["binding_sha256"] = identity.binding_sha256(record)
        previous = record["binding_sha256"]
        appended.append(record)
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
        f"*** Add File: {EVIDENCE.as_posix()}\n"
        f"{patch_escape(evidence_text.rstrip(chr(10)))}\n"
        f"*** Update File: {BINDINGS.as_posix()}\n"
        "@@\n"
        f" {last_line}\n"
        f"{patch_escape(append_text)}\n"
        "*** End Patch\n"
    )
    sys.stdout.write(patch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
