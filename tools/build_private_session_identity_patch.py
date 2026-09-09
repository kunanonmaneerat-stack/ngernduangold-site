#!/usr/bin/env python3
"""Build a privacy-safe apply_patch for exact legacy comment identities.

The private Claude/Cowork transcripts are read-only inputs.  This program never
copies transcript paths, session ids, or raw text into its output.  It verifies a
narrow allowlist of structured tool-input events and emits only cryptographic
commitments plus append-only identity bindings.  The historical post ledger is
never edited.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / "automation-log"
sys.path.insert(0, str(AUTO))
import post_ledger  # noqa: E402
import post_ledger_identity as identity  # noqa: E402


LEDGER = AUTO / "post-ledger.jsonl"
BINDINGS = AUTO / "post-ledger-identity-bindings.jsonl"
COMMITMENT_REL = identity.PRIVATE_COMMITMENT_SOURCE
EVIDENCE_REL = (
    "automation-log/dedup-evidence/"
    "post-ledger-identity-sources-private-session-v1.json"
)
COMMITMENT = ROOT / COMMITMENT_REL
EVIDENCE = ROOT / EVIDENCE_REL
CREATED_AT = "2026-08-24T20:30:00+07:00"
EXPECTED_CURRENT_INCOMPLETE = {
    27, 30, 31, 32, 33, 39, 45, 47, 49, 53, 55, 56, 62, 63, 70, 71,
    78, 79, 87, 88, 89, 94, 95, 103, 109, 113, 114, 120, 121, 129,
    137, 155, 175,
}
EXPECTED_REMAINING = {
    33, 39, 45, 53, 109,
}
MAX_TRANSCRIPTS = 512
MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024


class BuildError(RuntimeError):
    pass


def _stable_bytes(path: Path) -> bytes:
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise BuildError("a private transcript changed while being read")
    return raw


def _ledger_snapshot():
    raw = _stable_bytes(LEDGER)
    if not raw.endswith(b"\n"):
        raise BuildError("post ledger lacks a final newline")
    physical = raw.split(b"\n")[:-1]
    rows = [identity._strict_json_loads(line.rstrip(b"\r").decode("utf-8"))
            for line in physical]
    hashes = {
        number: identity.sha256_bytes(line.rstrip(b"\r"))
        for number, line in enumerate(physical, 1)
    }
    return rows, hashes


def _task_name(skill: Path) -> str | None:
    try:
        head = _stable_bytes(skill).decode("utf-8-sig").splitlines()[:12]
    except (OSError, UnicodeDecodeError):
        return None
    for line in head:
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def _private_session_spaces():
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    if not local.is_absolute():
        raise BuildError("LOCALAPPDATA is unavailable")
    pattern = (
        "Packages/Claude_*/LocalCache/Roaming/Claude/"
        "local-agent-mode-sessions/*/*"
    )
    spaces = sorted(path for path in local.glob(pattern) if path.is_dir())
    if not spaces:
        raise BuildError("Claude local session store is unavailable")
    return spaces


def _parse_timestamp(value: str) -> datetime.datetime:
    try:
        stamp = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise BuildError("a private event timestamp is invalid") from exc
    if stamp.tzinfo is None:
        raise BuildError("a private event timestamp lacks timezone")
    return stamp


def _tool_text_events(obj: dict):
    message = obj.get("message") or {}
    content = message.get("content") or []
    if not isinstance(content, list):
        return
    for content_index, item in enumerate(content):
        if not isinstance(item, dict) or item.get("type") != "tool_use":
            continue
        name = item.get("name")
        payload = item.get("input") or {}
        if (
            name == "mcp__claude-in-chrome__computer"
            and payload.get("action") == "type"
            and isinstance(payload.get("text"), str)
        ):
            yield {
                "json_field": f"message.content[{content_index}].input.text",
                "tool_name": name, "input_mode": "type", "text": payload["text"],
            }
        elif name == "mcp__claude-in-chrome__browser_batch":
            actions = payload.get("actions") or []
            if not isinstance(actions, list):
                continue
            for action_index, action in enumerate(actions):
                if not isinstance(action, dict):
                    continue
                action_input = action.get("input") or {}
                if (
                    action.get("name") == "computer"
                    and action_input.get("action") == "type"
                    and isinstance(action_input.get("text"), str)
                ):
                    yield {
                        "json_field": (
                            f"message.content[{content_index}].input.actions"
                            f"[{action_index}].input.text"
                        ),
                        "tool_name": name, "input_mode": "type",
                        "text": action_input["text"],
                    }
        elif (
            name == "mcp__Windows-MCP__Clipboard"
            and payload.get("mode") == "set"
            and isinstance(payload.get("text"), str)
        ):
            yield {
                "json_field": f"message.content[{content_index}].input.text",
                "tool_name": name, "input_mode": "clipboard_set",
                "text": payload["text"],
            }


def _read_private_events():
    expected_tasks = {
        contract["task_id"]
        for contract in identity.PRIVATE_SESSION_LINE_CONTRACT.values()
    }
    expected_hashes = {
        contract["transcript_sha256"]
        for contract in identity.PRIVATE_SESSION_LINE_CONTRACT.values()
    }
    transcripts = {}
    processed_hashes = set()
    events = []
    scanned = 0
    total_bytes = 0
    for space in _private_session_spaces():
        for skill in sorted(space.glob("local_*/uploads/SKILL.md")):
            task = _task_name(skill)
            if task not in expected_tasks:
                continue
            session_root = skill.parent.parent
            for transcript in sorted((session_root / ".claude" / "projects").rglob("*.jsonl")):
                scanned += 1
                if scanned > MAX_TRANSCRIPTS:
                    raise BuildError("private transcript scan exceeded file bound")
                raw = _stable_bytes(transcript)
                if len(raw) > MAX_TRANSCRIPT_BYTES:
                    raise BuildError("a private transcript exceeds the per-file bound")
                total_bytes += len(raw)
                if total_bytes > MAX_TOTAL_BYTES:
                    raise BuildError("private transcript scan exceeded byte bound")
                transcript_sha = identity.sha256_bytes(raw)
                if transcript_sha in processed_hashes:
                    continue
                processed_hashes.add(transcript_sha)
                if transcript_sha in expected_hashes:
                    transcripts[transcript_sha] = raw
                try:
                    lines = raw.decode("utf-8-sig").splitlines()
                except UnicodeDecodeError as exc:
                    raise BuildError("a relevant private transcript is not UTF-8") from exc
                for physical_line, line in enumerate(lines, 1):
                    try:
                        obj = identity._strict_json_loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    timestamp = str(obj.get("timestamp") or "")
                    try:
                        local_date = _parse_timestamp(timestamp).astimezone(
                            datetime.timezone(datetime.timedelta(hours=7))
                        ).date().isoformat()
                    except BuildError:
                        continue
                    for item in _tool_text_events(obj) or []:
                        events.append({
                            "task_id": task,
                            "target_date": local_date,
                            "transcript_sha256": transcript_sha,
                            "transcript_size_bytes": len(raw),
                            "event_physical_line": physical_line,
                            "event_sha256": identity.sha256_bytes(line.encode("utf-8")),
                            "event_timestamp": timestamp,
                            **item,
                        })
    if set(transcripts) != expected_hashes:
        raise BuildError("one or more pinned private transcripts are unavailable")
    return events


def _safe_records(rows: list[dict], events: list[dict]):
    records = []
    for line, contract in sorted(identity.PRIVATE_SESSION_LINE_CONTRACT.items()):
        row = rows[line - 1]
        prefix = str(row.get("text_first80") or "")
        matches = [
            event for event in events
            if event["task_id"] == contract["task_id"]
            and event["target_date"] == contract["target_date"]
            and event["text"].startswith(prefix)
        ]
        expected_count = identity.PRIVATE_SESSION_MATCH_COUNTS.get(line, 1)
        if len(matches) != expected_count:
            raise BuildError("a private tool-input match is missing or ambiguous")
        if len({event["text"] for event in matches}) != 1:
            raise BuildError("matching private events disagree on exact text")
        text = matches[0]["text"]
        if (
            identity.sha256_bytes(text.encode("utf-8")) != contract["text_sha256"]
            or identity._text_hash(text) != contract["text_identity_sha1"]
        ):
            raise BuildError("matching private text differs from pinned commitment")
        representatives = []
        for event in matches:
            observed = {
                key: event[key] for key in (
                "task_id", "target_date", "transcript_sha256",
                "transcript_size_bytes", "event_physical_line", "event_sha256",
                "json_field", "tool_name", "input_mode", "event_timestamp",
                )
            }
            observed.update({
                "row_source": str(row.get("source") or ""),
                "channel": identity._full_channel(row.get("channel")),
                "text_length": len(event["text"]),
                "text_sha256": identity.sha256_bytes(
                    event["text"].encode("utf-8")
                ),
                "text_identity_sha1": identity._text_hash(event["text"]),
            })
            if observed == contract:
                representatives.append(event)
        if len(representatives) != 1:
            raise BuildError("a private event differs from the pinned contract")
        ledger_at = datetime.datetime.fromisoformat(str(row.get("ts") or ""))
        if ledger_at.tzinfo is None:
            raise BuildError("a ledger timestamp lacks timezone")
        for event in matches:
            event_at = _parse_timestamp(event["event_timestamp"])
            lag = (ledger_at.astimezone(datetime.timezone.utc) - event_at.astimezone(
                datetime.timezone.utc
            )).total_seconds()
            if lag < 0 or lag > identity.PRIVATE_SESSION_MAX_LAG_SECONDS.get(
                line, 30 * 60
            ):
                raise BuildError(
                    f"private event for ledger line {line} is outside its time window"
                )
        records.append({
            "commitment_id": "private-session-line-%06d" % line,
            "ledger_line": line,
            **contract,
            "ledger_prefix_length": len(prefix),
            "ledger_prefix_sha256": identity.sha256_bytes(prefix.encode("utf-8")),
            "matching_event_count": expected_count,
            "join_mode": (
                "exact_task_date_time_tool_input_set"
                if line in identity.PRIVATE_SESSION_ZERO_PREFIX_LINES
                else "exact_structured_tool_input_prefix"
            ),
            "privacy_status": identity.PRIVATE_COMMITMENT_PRIVACY_STATUS,
        })
    return records


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _append_binding_records(rows, row_hashes, source_hash, evidence_hash):
    existing = [
        identity._strict_json_loads(line)
        for line in BINDINGS.read_text(encoding="utf-8").splitlines()
    ]
    if not existing or existing[-1].get("record_type") != "post_ledger_identity_binding_seal":
        raise BuildError("identity binding ledger lacks a final seal")
    old_lines = {
        record["target"]["line"]
        for record in existing
        if record.get("record_type") == "post_ledger_identity_binding"
    }
    target_lines = set(identity.PRIVATE_SESSION_LINE_CONTRACT)
    if old_lines & target_lines:
        raise BuildError("one or more private targets are already bound")
    previous = existing[-1]["seal_sha256"]
    additions = []
    current_keys = post_ledger.load_index(LEDGER)["keys"]
    proposed_groups = {}
    for line, contract in sorted(identity.PRIVATE_SESSION_LINE_CONTRACT.items()):
        group = (contract["channel"], contract["text_identity_sha1"])
        proposed_groups.setdefault(group, []).append(line)
        dedup_key = post_ledger.make_text_dedup_key(*group)
        if dedup_key in current_keys:
            raise BuildError("a proposed private identity is already present")
    actual_collisions = {
        group: lines for group, lines in proposed_groups.items() if len(lines) > 1
    }
    expected_collisions = {
        ("instagram", "aed0406157eb7257c3bf86c7906a6822f8b86e79"): [63, 89],
        ("youtube", "90e43a4ddc4d3da3f72e17d10fd38f153e0741bc"): [
            31, 47, 55, 62, 70, 78, 87, 94, 103, 113, 120, 129, 137, 155,
        ],
    }
    if actual_collisions != expected_collisions:
        raise BuildError("proposed private identity collision set drifted")
    for line, contract in sorted(identity.PRIVATE_SESSION_LINE_CONTRACT.items()):
        evidence_id = "private-session-line-%06d" % line
        record = {
            "schema_version": 1,
            "record_type": "post_ledger_identity_binding",
            "binding_id": "plid-v1-%06d" % line,
            "previous_binding_sha256": previous,
            "target": {
                "ledger_path": "automation-log/post-ledger.jsonl",
                "line": line,
                "row_sha256": row_hashes[line],
            },
            "source": {
                "path": COMMITMENT_REL,
                "sha256": source_hash,
                "field": f"records[commitment_id={evidence_id}]",
                "evidence_path": EVIDENCE_REL,
                "evidence_sha256": evidence_hash,
                "evidence_field": f"records[evidence_id={evidence_id}].value",
            },
            "evidence_type": "privacy_sanitized_tool_input_commitment",
            "identity": {
                "kind": "text_hash",
                "value": contract["text_identity_sha1"],
                "value_sha256": identity.identity_value_sha256(
                    contract["text_identity_sha1"]
                ),
            },
            "reuse_policy": "PERMANENT_DEDUP",
        }
        record["binding_sha256"] = identity.binding_sha256(record)
        previous = record["binding_sha256"]
        additions.append(record)
    all_lines = sorted(old_lines | target_lines)
    seal = {
        "schema_version": 1,
        "record_type": "post_ledger_identity_binding_seal",
        "binding_count": len(all_lines),
        "sealed_target_lines": all_lines,
        "previous_record_sha256": previous,
    }
    seal["seal_sha256"] = identity.seal_sha256(seal)
    additions.append(seal)
    return existing[-1], additions


def _patch_add_file(relative: str, raw: bytes) -> list[str]:
    text = raw.decode("utf-8")
    return [f"*** Add File: {relative}"] + ["+" + line for line in text.splitlines()]


def build_patch(created_at: str):
    if COMMITMENT.exists() or EVIDENCE.exists():
        raise BuildError("private commitment output already exists")
    rows, row_hashes = _ledger_snapshot()
    metric = post_ledger.load_index(LEDGER)["identity_coverage"]
    incomplete = {item["line"] for item in metric["legacy_incomplete"]}
    if incomplete != EXPECTED_CURRENT_INCOMPLETE:
        raise BuildError("current incomplete target set drifted")
    if incomplete - set(identity.PRIVATE_SESSION_LINE_CONTRACT) != EXPECTED_REMAINING:
        raise BuildError("expected remaining blocker set is inconsistent")
    events = _read_private_events()
    commitments = _safe_records(rows, events)
    commitment_payload = {
        "schema_version": 1,
        "created_at": created_at,
        "purpose": (
            "Privacy-preserving exact tool-input commitments for bounded legacy "
            "permanent-dedup repair; contains no path, session id, or raw text."
        ),
        "extraction_contract": identity.PRIVATE_COMMITMENT_EXTRACTION_CONTRACT,
        "records": commitments,
    }
    commitment_raw = _json_bytes(commitment_payload)
    if re.search(
        rb"(?i)(?:[A-Z]:[\\/]|/Users/|\\\\Users\\\\|local_[0-9a-f]{8}-)",
        commitment_raw,
    ):
        raise BuildError("private identifier leaked into sanitized commitment")
    commitment_sha = identity.sha256_bytes(commitment_raw)
    evidence_payload = {
        "schema_version": 1,
        "created_at": created_at,
        "purpose": (
            "Immutable sanitized selectors for private-session identity commitments; "
            "no external delivery or publication status is inferred."
        ),
        "records": [
            {
                "evidence_id": item["commitment_id"],
                "source_path": COMMITMENT_REL,
                "source_sha256": commitment_sha,
                "source_field": (
                    f"records[commitment_id={item['commitment_id']}]"
                ),
                "value": item,
            }
            for item in commitments
        ],
    }
    evidence_raw = _json_bytes(evidence_payload)
    evidence_sha = identity.sha256_bytes(evidence_raw)
    old_seal, additions = _append_binding_records(
        rows, row_hashes, commitment_sha, evidence_sha
    )
    compact = lambda value: json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    )
    patch = ["*** Begin Patch"]
    patch += _patch_add_file(COMMITMENT_REL, commitment_raw)
    patch += _patch_add_file(EVIDENCE_REL, evidence_raw)
    patch += [
        "*** Update File: automation-log/post-ledger-identity-bindings.jsonl",
        "@@",
        " " + compact(old_seal),
    ]
    patch += ["+" + compact(record) for record in additions]
    patch += ["*** End Patch"]
    return "\n".join(patch) + "\n", {
        "state": "VERIFIED_PATCH_READY",
        "repaired_lines": sorted(identity.PRIVATE_SESSION_LINE_CONTRACT),
        "remaining_lines": sorted(EXPECTED_REMAINING),
        "private_artifacts_modified": False,
        "raw_text_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-patch", action="store_true")
    parser.add_argument("--created-at", default=CREATED_AT)
    args = parser.parse_args()
    patch, summary = build_patch(args.created_at)
    if args.emit_patch:
        sys.stdout.write(patch)
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
