#!/usr/bin/env python3
"""Generate exact-window, local-only media revalidation evidence.

The generator reads the current calendar and the already-declared canonical
media receipts, then re-runs ``media_publish_guard`` locally.  It never creates
human-review evidence and never grants publication authority.  A missing human
audio review is preserved as a blocker bound to the exact asset hash.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import media_publish_guard
import next48_owner_decision_packet as packet


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_KIND = "LOCAL_ONLY_NEXT48_MEDIA_REVALIDATION"
MEDIA_QA_ROOT = Path("automation-log/media-qa")


class RevalidationError(RuntimeError):
    pass


def _media_placements(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("media") not in (None, "")]


def _source_binding(repo: Path, placement: dict) -> dict:
    source = placement.get("source")
    if not isinstance(source, dict):
        raise RevalidationError("media placement source is malformed")
    relative = str(source.get("file") or "")
    path = packet._repo_path(repo, relative)
    return {
        "path": relative,
        "sha256": packet._sha256(path),
        "row_id": source.get("row_id"),
        "field": source.get("field"),
    }


def _sanitized_fresh_scan(result: dict, asset: str) -> dict | None:
    """Keep only decision metrics and a repository-relative asset identity."""
    scan = result.get("fresh_scan")
    if scan is None:
        return None
    if not isinstance(scan, dict):
        raise RevalidationError("fresh media scan is malformed")
    allowed = ("verdict", "frames", "track_frames", "track_frac")
    sanitized = {"asset": asset}
    for key in allowed:
        value = scan.get(key)
        if value is not None:
            sanitized[key] = value
    if sanitized.get("verdict") not in {"PASS", "FAIL", "ERROR"}:
        raise RevalidationError("fresh media scan verdict is invalid")
    return sanitized


def build_receipt(
    repo: Path,
    as_of: datetime,
    hours: int = 48,
    *,
    guard_runner=None,
) -> dict:
    repo = Path(repo).resolve()
    if not isinstance(hours, int) or isinstance(hours, bool) or hours != 48:
        raise RevalidationError("this contract requires an exact 48-hour window")
    anchor = packet._aware_bangkok(as_of)
    end = anchor + timedelta(hours=hours)
    calendar_path = packet._repo_path(repo, packet.CALENDAR.as_posix())
    calendar = packet._load_object(calendar_path)
    selected = packet._select_window_placements(
        calendar.get("placements"), anchor, end
    )
    media_rows = _media_placements(selected)
    run_guard = guard_runner or media_publish_guard.evaluate
    rows: list[dict] = []
    human_blocked = 0
    other_blocked = 0

    for placement in media_rows:
        placement_id = str(placement.get("placement_id") or "")
        asset = placement.get("media")
        canonical_receipt = placement.get("media_receipt")
        if not placement_id or not isinstance(asset, str) or not isinstance(canonical_receipt, str):
            raise RevalidationError("media placement binding is incomplete")
        asset_path = packet._repo_path(repo, asset)
        receipt_path = packet._repo_path(repo, canonical_receipt)
        try:
            result = run_guard(asset_path, receipt_path, repo=repo, now=anchor)
        except Exception as exc:
            raise RevalidationError(
                f"media guard failed to run for {placement_id}: {type(exc).__name__}"
            ) from exc
        if not isinstance(result, dict) or result.get("verdict") not in {"PASS", "FAIL"}:
            raise RevalidationError(f"media guard returned an invalid verdict for {placement_id}")
        verdict = str(result["verdict"])
        findings = result.get("findings")
        if not isinstance(findings, list) or any(not isinstance(item, str) for item in findings):
            raise RevalidationError(f"media guard findings are malformed for {placement_id}")
        media_type = str(result.get("media_type") or "")
        if media_type != str(placement.get("format") or ""):
            raise RevalidationError(f"calendar/media type mismatch for {placement_id}")
        authority = result.get("publication_authority_granted")
        if authority is not False:
            raise RevalidationError("media guard attempted to grant publication authority")
        is_human_blocked = verdict == "FAIL" and findings == ["human audio review is missing"]
        if is_human_blocked:
            human_blocked += 1
        elif verdict != "PASS":
            other_blocked += 1
        rows.append({
            "placement_id": placement_id,
            "scheduled_at": packet._slot(placement).isoformat(timespec="seconds"),
            "calendar_placement_sha256": packet._canonical_sha256(placement),
            "asset": asset,
            "asset_sha256": packet._sha256(asset_path),
            "asset_size_bytes": asset_path.stat().st_size,
            "canonical_receipt": canonical_receipt,
            "canonical_receipt_sha256": packet._sha256(receipt_path),
            "source_binding": _source_binding(repo, placement),
            "fresh_automated_qa": _sanitized_fresh_scan(result, asset),
            "media_publish_guard": {
                "verdict": verdict,
                "findings": findings,
                "finding": findings[0] if len(findings) == 1 else None,
                "publication_authority_granted": False,
            },
            "state": (
                "MEDIA_GATE_PASS_AUTHORITY_STILL_BLOCKED"
                if verdict == "PASS"
                else "AUTOMATED_MEDIA_PASS_HUMAN_LISTENING_BLOCKED"
                if is_human_blocked
                else "MEDIA_EVIDENCE_BLOCKED"
            ),
        })

    if other_blocked:
        summary_verdict = "COMPLETED_WITH_MEDIA_BLOCKERS"
    elif human_blocked:
        summary_verdict = "COMPLETED_WITH_HUMAN_LISTENING_BLOCKERS"
    else:
        summary_verdict = "COMPLETED_MEDIA_PASS_AUTHORITY_BLOCKED"
    payload = {
        "schema_version": 2,
        "receipt_kind": RECEIPT_KIND,
        "receipt_id": "next48-media-revalidation-" + anchor.strftime("%Y%m%dT%H%M%S%z"),
        "evaluated_at": anchor.isoformat(timespec="seconds"),
        "timezone": "Asia/Bangkok",
        "window": {
            "start_inclusive": anchor.isoformat(timespec="seconds"),
            "end_inclusive": end.isoformat(timespec="seconds"),
            "hours": hours,
            "calendar": packet.CALENDAR.as_posix(),
            "calendar_sha256": packet._sha256(calendar_path),
            "selection_rule": (
                "Every and only media-bearing placement whose exact Bangkok "
                "scheduled_at is inside the inclusive 48-hour window."
            ),
        },
        "guard_implementation": {
            name: {
                "path": relative,
                "sha256": packet._sha256(packet._repo_path(repo, relative)),
            }
            for name, relative in packet.MEDIA_REVALIDATION_IMPLEMENTATIONS.items()
        },
        "summary": {
            "calendar_placements_in_window": len(selected),
            "media_placements_in_window": len(rows),
            "media_publish_guard_pass": sum(
                row["media_publish_guard"]["verdict"] == "PASS" for row in rows
            ),
            "media_publish_guard_blocked": sum(
                row["media_publish_guard"]["verdict"] != "PASS" for row in rows
            ),
            "human_audio_reviews_outstanding": human_blocked,
            "publication_authority_granted": False,
            "calendar_or_authority_mutated": False,
            "verdict": summary_verdict,
        },
        "placements": rows,
        "limitations": [
            "Automated media checks are not a substitute for human listening.",
            "This receipt grants no publication authority and does not change PLANNED_BLOCKED.",
            "No network, platform, scheduler, tracker, deployment or external action was performed.",
        ],
    }
    payload["receipt_payload_sha256"] = packet._canonical_sha256(payload)
    return payload


def write_receipt(path: Path, payload: dict, repo: Path) -> None:
    repo = Path(repo).resolve()
    path = Path(path).resolve()
    qa_root = (repo / MEDIA_QA_ROOT).resolve()
    try:
        path.relative_to(qa_root)
    except ValueError as exc:
        raise RevalidationError("output must stay under automation-log/media-qa") from exc
    if not path.name.startswith("NEXT48-MEDIA-REVALIDATION-RECEIPT_") or path.suffix != ".json":
        raise RevalidationError("output filename is outside the receipt namespace")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RevalidationError("refusing to overwrite a different receipt")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--as-of", required=True, help="timezone-aware ISO-8601 instant")
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = build_receipt(
            args.repo, packet._aware_bangkok(args.as_of), args.hours
        )
        write_receipt(args.output, payload, args.repo)
        print(json.dumps({
            "verdict": "PASS",
            "output": str(args.output),
            "receipt_payload_sha256": payload["receipt_payload_sha256"],
            "summary": payload["summary"],
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "verdict": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
