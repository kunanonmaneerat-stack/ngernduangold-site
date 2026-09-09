#!/usr/bin/env python3
"""Build a deterministic, local-only 48-hour publication decision packet.

The packet is evidence, not authority.  It never edits the content calendar,
policy, ledger, source registries, media receipts, or any external system.  A
``READY_FOR_OWNER_DECISION`` result means only that non-owner blockers are
clear; publication remains blocked until the separately controlled, exact
one-time owner-authority contract passes at the mutation boundary.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
LOG = ROOT / "automation-log"
for import_root in (str(TOOLS), str(LOG)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import content_source_gate
import live_domain_observation
import media_publish_guard
import post_ledger
import privacy_guard
import public_identity_guard


BANGKOK = ZoneInfo("Asia/Bangkok")
CALENDAR = Path(".system_control/content_calendar.json")
POLICY = Path(".system_control/policy.json")
CAPABILITIES = Path(".system_control/role_capabilities.json")
LEDGER = Path("automation-log/post-ledger.jsonl")
IDENTITY_BINDINGS = Path("automation-log/post-ledger-identity-bindings.jsonl")
COLLISION_TOMBSTONES = Path("automation-log/post-ledger-collision-tombstones.json")
OFFICIAL_SNAPSHOT = Path("automation-log/knowledge-base/official-news-snapshot.json")
SOURCE_REGISTRIES = (
    Path("automation-log/knowledge-base/content-source-registry.json"),
    Path("automation-log/knowledge-base/page2-source-registry.json"),
    Path("automation-log/knowledge-base/social-source-registry.json"),
)
MEDIA_REVALIDATION_DIR = Path("automation-log/media-qa")
MEDIA_REVALIDATION_GLOB = "NEXT48-MEDIA-REVALIDATION-RECEIPT_*.json"
MEDIA_REVALIDATION_IMPLEMENTATIONS = {
    "generator": "tools/next48_media_revalidation.py",
    "media_publish_guard": "tools/media_publish_guard.py",
    "watermark_scanner": "tiktok-pipeline/src/qa_watermark.py",
    "generative_media_origin_gate": "tools/generative_media_origin_gate.py",
}
LIVE_DOMAIN_OBSERVATION_GLOB = "LIVE-DOMAIN-OBSERVATION_*.json"
LIVE_DOMAIN_OBSERVATION_DIR = Path(
    ".local-private/runtime/live-domain-observations"
)
GENERATOR_PATH = Path("tools/next48_owner_decision_packet.py")
PACKET_KIND = "LOCAL_ONLY_NEXT48_EXACT_READINESS"
BLOCKED_CALENDAR_STATE = "PLANNED_BLOCKED"

OWNER_BLOCKERS = {
    "publication_authority",
    "channel_review",
    "per_piece_owner_confirmation",
    "official_source_review",
    "human_listening_not_run",
}

# The calendar's publication channel is intentionally shared by the two
# Facebook pages, while permanent dedup is explicitly same-account.  The
# historical ledger already represents Page 2 as ``facebook-page2``; folding
# it into ``fb`` would let one incomplete main-page Story deadlock Page 2.
ACCOUNT_DEDUP_CHANNELS = {
    "facebook_page2": "facebook-page2",
}


class PacketError(RuntimeError):
    pass


def _strict_loads(raw: str) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    result = json.loads(
        raw,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def finite(value: object) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        if isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)

    finite(result)
    return result


def _stable_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise PacketError(f"symlink evidence is not allowed: {path}")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise PacketError(f"evidence changed while being read: {path}")
    return raw


def _load_object(path: Path) -> dict:
    try:
        value = _strict_loads(_stable_bytes(path).decode("utf-8"))
    except Exception as exc:
        raise PacketError(f"missing/unreadable JSON evidence: {path}") from exc
    if not isinstance(value, dict):
        raise PacketError(f"JSON evidence must be an object: {path}")
    return value


def _repo_path(repo: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise PacketError("repository evidence path is missing")
    selected = (repo / relative).resolve()
    try:
        selected.relative_to(repo.resolve())
    except ValueError as exc:
        raise PacketError("repository evidence path escapes the repository") from exc
    return selected


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _sha256(path: Path) -> str:
    return _sha256_bytes(_stable_bytes(path))


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _file_binding(repo: Path, relative: Path) -> dict:
    path = _repo_path(repo, relative.as_posix())
    return {
        "path": relative.as_posix(),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _aware_bangkok(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PacketError("as-of must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PacketError("as-of must include an explicit timezone")
    return parsed.astimezone(BANGKOK)


def _slot(placement: dict) -> datetime:
    return _aware_bangkok(
        f"{placement.get('date')}T{placement.get('time')}:00+07:00"
    )


def _table_rows(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    header: list[str] | None = None
    for raw_line in _stable_bytes(path).decode("utf-8").splitlines():
        if not raw_line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        lowered = [cell.casefold() for cell in cells]
        if "date" in lowered and "id" in lowered:
            if len(lowered) != len(set(lowered)):
                raise PacketError(f"duplicate Markdown header: {path}")
            header = lowered
            continue
        if header is None or len(cells) != len(header):
            continue
        if all(re.fullmatch(r"[-: ]+", cell or "-") for cell in cells):
            continue
        row = dict(zip(header, cells))
        content_id = row.get("id", "").strip()
        if content_id:
            if content_id in rows:
                raise PacketError(f"duplicate content_id {content_id}: {path}")
            rows[content_id] = row
    return rows


def _weekly_rows(path: Path) -> dict[str, dict]:
    payload = _load_object(path)
    days = payload.get("days")
    if payload.get("schema_version") != 1 or not isinstance(days, list):
        raise PacketError("weekly pack contract is invalid")
    rows: dict[str, dict] = {}
    for row in days:
        if not isinstance(row, dict):
            raise PacketError("weekly pack row is malformed")
        content_id = str(row.get("candidate_id") or "").strip()
        if not content_id or content_id in rows:
            raise PacketError("weekly pack identity is missing or duplicated")
        rows[content_id] = row
    return rows


def _markdown_section(path: Path, row_id: str, field: str) -> str:
    headings = {
        "youtube_package": "## YouTube package",
        "social_caption": "## Social caption",
    }
    heading = headings.get(field)
    if heading is None:
        return ""
    text = _stable_bytes(path).decode("utf-8")
    asset_ids = re.findall(r"\*\*Asset ID:\*\*\s*`([^`\r\n]+)`", text)
    if not row_id or asset_ids != [row_id]:
        return ""
    heading_pattern = re.compile(
        r"(?m)^" + re.escape(heading) + r"[ \t]*\r?$"
    )
    matches = list(heading_pattern.finditer(text))
    if len(matches) != 1:
        return ""
    tail = text[matches[0].end():]
    next_heading = re.search(r"(?m)^## [^\r\n]+[ \t]*\r?$", tail)
    if next_heading:
        tail = tail[:next_heading.start()]
    return tail.strip()


def _caption(repo: Path, placement: dict, cache: dict[str, object]) -> tuple[str, dict]:
    source = placement.get("source")
    if not isinstance(source, dict):
        raise PacketError("placement source is malformed")
    relative = str(source.get("file") or "")
    row_id = str(source.get("row_id") or "")
    field = str(source.get("field") or "").casefold()
    path = _repo_path(repo, relative)
    section_key = "#".join((relative, row_id, field))
    if path.suffix.casefold() == ".md" and field in {"youtube_package", "social_caption"}:
        if section_key not in cache:
            cache[section_key] = _markdown_section(path, row_id, field)
        value = cache[section_key]
    else:
        if relative not in cache:
            cache[relative] = (
                _weekly_rows(path)
                if path.suffix.casefold() == ".json"
                else _table_rows(path)
            )
        rows = cache[relative]
        row = rows.get(row_id) if isinstance(rows, dict) else None
        if not isinstance(row, dict):
            raise PacketError(f"caption row is missing: {row_id}")
        value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PacketError(f"caption field is missing: {row_id}.{field}")
    if path.suffix.casefold() != ".json":
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    return value, {
        "path": relative,
        "file_sha256": _sha256(path),
        "row_id": row_id,
        "field": field,
        "caption_sha256": _sha256_bytes(value.encode("utf-8")),
        "caption_utf8_bytes": len(value.encode("utf-8")),
    }


def _media_index(
    repo: Path,
    calendar_hash: str,
    anchor: datetime,
    end: datetime,
    placements: list[dict],
    *,
    guard_runner=None,
) -> tuple[dict[str, dict], dict]:
    """Select one schema-v2 receipt bound to the exact calendar and window.

    Dated filenames are archival evidence, not configuration.  Selecting one
    hard-coded historical receipt made every later calendar look corrupt.  A
    usable receipt must instead match the current calendar bytes, both window
    boundaries, and every media-bearing placement in that window.
    """
    root = _repo_path(repo, MEDIA_REVALIDATION_DIR.as_posix())
    candidates: list[tuple[Path, dict]] = []
    for path in sorted(root.glob(MEDIA_REVALIDATION_GLOB)):
        payload = _load_object(path)
        if (
            payload.get("schema_version") != 2
            or payload.get("receipt_kind") != "LOCAL_ONLY_NEXT48_MEDIA_REVALIDATION"
        ):
            continue
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        if str(window.get("calendar_sha256") or "").upper() != calendar_hash:
            continue
        try:
            start_value = _aware_bangkok(window.get("start_inclusive"))
            end_value = _aware_bangkok(window.get("end_inclusive"))
        except PacketError:
            continue
        if start_value == anchor and end_value == end and window.get("hours") == 48:
            candidates.append((path, payload))
    if not candidates:
        raise PacketError(
            "no media revalidation receipt matches the exact calendar and 48-hour window"
        )
    if len(candidates) != 1:
        raise PacketError("media revalidation receipt selection is ambiguous")
    path, payload = candidates[0]
    if payload.get("timezone") != "Asia/Bangkok":
        raise PacketError("media revalidation timezone is not canonical")
    if _aware_bangkok(payload.get("evaluated_at")) != anchor:
        raise PacketError("media revalidation evaluation time differs from the window")
    expected_receipt_id = (
        "next48-media-revalidation-" + anchor.strftime("%Y%m%dT%H%M%S%z")
    )
    if payload.get("receipt_id") != expected_receipt_id:
        raise PacketError("media revalidation receipt identity differs from the window")
    supplied_hash = payload.get("receipt_payload_sha256")
    unsigned = dict(payload)
    unsigned.pop("receipt_payload_sha256", None)
    if supplied_hash != _canonical_sha256(unsigned):
        raise PacketError("media revalidation receipt payload hash is invalid")
    window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    if window.get("calendar") != CALENDAR.as_posix():
        raise PacketError("media revalidation receipt calendar path is not canonical")
    implementation_bindings = payload.get("guard_implementation")
    implementation_bindings = (
        implementation_bindings if isinstance(implementation_bindings, dict) else {}
    )
    if set(implementation_bindings) != set(MEDIA_REVALIDATION_IMPLEMENTATIONS):
        raise PacketError("media revalidation implementation binding set is incomplete")
    for name, expected_path in MEDIA_REVALIDATION_IMPLEMENTATIONS.items():
        binding = implementation_bindings.get(name)
        if not isinstance(binding, dict) or binding.get("path") != expected_path:
            raise PacketError(f"media revalidation implementation path differs: {name}")
        if str(binding.get("sha256") or "").upper() != _sha256(
            _repo_path(repo, expected_path)
        ):
            raise PacketError(f"media revalidation implementation has changed: {name}")
    rows = payload.get("placements")
    if not isinstance(rows, list):
        raise PacketError("media revalidation placement inventory is malformed")
    index: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise PacketError("media revalidation row is malformed")
        placement_id = str(row.get("placement_id") or "")
        if not placement_id or placement_id in index:
            raise PacketError("media revalidation identity is missing or duplicated")
        index[placement_id] = row
    expected = {
        str(row.get("placement_id") or ""): row
        for row in placements
        if row.get("media") not in (None, "")
    }
    if not expected or "" in expected:
        raise PacketError("exact window has no valid media placement identity")
    if set(index) != set(expected):
        raise PacketError("media revalidation inventory differs from the exact window")
    media_pass = 0
    media_blocked = 0
    human_blocked = 0
    other_blocked = 0
    for placement_id, placement in expected.items():
        row = index[placement_id]
        if (
            row.get("scheduled_at") != _slot(placement).isoformat(timespec="seconds")
            or row.get("calendar_placement_sha256") != _canonical_sha256(placement)
            or row.get("asset") != placement.get("media")
            or row.get("canonical_receipt") != placement.get("media_receipt")
        ):
            raise PacketError(
                f"media revalidation placement binding differs: {placement_id}"
            )
        gate = row.get("media_publish_guard")
        if not isinstance(gate, dict) or gate.get("publication_authority_granted") is not False:
            raise PacketError("media revalidation attempted to grant authority")
        verdict = gate.get("verdict")
        findings = gate.get("findings")
        finding = gate.get("finding")
        if (
            verdict not in {"PASS", "FAIL"}
            or not isinstance(findings, list)
            or any(not isinstance(item, str) for item in findings)
            or finding != (findings[0] if len(findings) == 1 else None)
        ):
            raise PacketError(
                f"media revalidation gate evidence is inconsistent: {placement_id}"
            )
        human_only = verdict == "FAIL" and findings == ["human audio review is missing"]
        expected_state = (
            "MEDIA_GATE_PASS_AUTHORITY_STILL_BLOCKED"
            if verdict == "PASS" and findings == []
            else "AUTOMATED_MEDIA_PASS_HUMAN_LISTENING_BLOCKED"
            if human_only
            else "MEDIA_EVIDENCE_BLOCKED"
        )
        if row.get("state") != expected_state:
            raise PacketError(
                f"media revalidation row state differs from evidence: {placement_id}"
            )
        if verdict == "PASS":
            if findings:
                raise PacketError(
                    f"media revalidation PASS carries findings: {placement_id}"
                )
            media_pass += 1
        else:
            media_blocked += 1
            if human_only:
                human_blocked += 1
            else:
                other_blocked += 1
        source = placement.get("source")
        source = source if isinstance(source, dict) else {}
        source_binding = row.get("source_binding")
        source_binding = source_binding if isinstance(source_binding, dict) else {}
        source_path = str(source.get("file") or "")
        if (
            source_binding.get("path") != source_path
            or source_binding.get("row_id") != source.get("row_id")
            or source_binding.get("field") != source.get("field")
            or str(source_binding.get("sha256") or "").upper()
            != _sha256(_repo_path(repo, source_path))
        ):
            raise PacketError(
                f"media revalidation source binding differs: {placement_id}"
            )
        fresh = row.get("fresh_automated_qa")
        if placement.get("format") == "video":
            if (
                not isinstance(fresh, dict)
                or set(fresh) - {"asset", "verdict", "frames", "track_frames", "track_frac"}
                or fresh.get("asset") != placement.get("media")
                or fresh.get("verdict") != "PASS"
                or not isinstance(fresh.get("frames"), int)
                or isinstance(fresh.get("frames"), bool)
                or fresh.get("frames") <= 0
                or fresh.get("track_frames") != 0
            ):
                raise PacketError(
                    f"media revalidation fresh video scan differs: {placement_id}"
                )
        elif fresh is not None:
            raise PacketError(
                f"still-image revalidation carries a video scan: {placement_id}"
            )
        asset_path = _repo_path(repo, str(placement.get("media") or ""))
        receipt_path = _repo_path(repo, str(placement.get("media_receipt") or ""))
        if (
            str(row.get("asset_sha256") or "").upper() != _sha256(asset_path)
            or str(row.get("canonical_receipt_sha256") or "").upper()
            != _sha256(receipt_path)
        ):
            raise PacketError(
                f"media revalidation asset or receipt hash differs: {placement_id}"
            )

        # A canonical JSON digest detects accidental byte drift but is not an
        # execution proof: a coordinated edit could change verdict, state and
        # summary, then compute a new digest. Replay the bound guard semantics
        # at the exact evaluation instant against the current asset, canonical
        # receipt and corpus. For video, the receipt's already validated fresh
        # scan metrics are replayed so packet construction stays deterministic;
        # the scanner implementation hash above still invalidates stale scans.
        recorded_scan = None
        if isinstance(fresh, dict):
            recorded_scan = {
                key: fresh[key]
                for key in ("verdict", "frames", "track_frames", "track_frac")
                if key in fresh
            }

        def replay_scanner(_asset: Path, _fps: float) -> dict:
            if recorded_scan is None:
                raise PacketError("recorded fresh scan is missing")
            return dict(recorded_scan)

        try:
            replay_guard = guard_runner or media_publish_guard.evaluate
            replay = replay_guard(
                asset_path,
                receipt_path,
                repo=repo,
                scanner=replay_scanner if recorded_scan is not None else None,
                now=anchor,
            )
        except Exception as exc:
            raise PacketError(
                f"media revalidation guard replay failed: {placement_id}"
            ) from exc
        if (
            not isinstance(replay, dict)
            or replay.get("media_type") != placement.get("format")
            or replay.get("publication_authority_granted") is not False
            or replay.get("verdict") != verdict
            or replay.get("findings") != findings
        ):
            raise PacketError(
                f"media revalidation guard replay differs: {placement_id}"
            )
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    expected_summary_verdict = (
        "COMPLETED_WITH_MEDIA_BLOCKERS"
        if other_blocked
        else "COMPLETED_WITH_HUMAN_LISTENING_BLOCKERS"
        if human_blocked
        else "COMPLETED_MEDIA_PASS_AUTHORITY_BLOCKED"
    )
    if (
        summary.get("media_placements_in_window") != len(expected)
        or summary.get("calendar_placements_in_window") != len(placements)
        or summary.get("media_publish_guard_pass") != media_pass
        or summary.get("media_publish_guard_blocked") != media_blocked
        or summary.get("human_audio_reviews_outstanding") != human_blocked
        or summary.get("verdict") != expected_summary_verdict
        or summary.get("publication_authority_granted") is not False
        or summary.get("calendar_or_authority_mutated") is not False
    ):
        raise PacketError("media revalidation summary is inconsistent")
    return index, {
        "path": path.relative_to(repo).as_posix(),
        "sha256": _sha256(path),
        "receipt_id": payload.get("receipt_id"),
        "evaluated_at": payload.get("evaluated_at"),
    }


def _media_state(
    repo: Path, placement: dict, media_index: dict[str, dict]
) -> dict:
    asset = placement.get("media")
    receipt = placement.get("media_receipt")
    if placement.get("format") == "text":
        if asset is not None or receipt is not None:
            raise PacketError("text placement carries media")
        return {"state": "NOT_REQUIRED", "asset": None, "receipt": None}
    if not isinstance(asset, str) or not isinstance(receipt, str):
        return {"state": "BLOCKED_MISSING", "asset": asset, "receipt": receipt}
    row = media_index.get(str(placement.get("placement_id") or ""))
    asset_path = _repo_path(repo, asset)
    receipt_path = _repo_path(repo, receipt)
    asset_hash = _sha256(asset_path)
    receipt_hash = _sha256(receipt_path)
    if not isinstance(row, dict):
        state = "BLOCKED_REVALIDATION_MISSING"
        revalidation = None
    else:
        matches = (
            row.get("asset") == asset
            and str(row.get("asset_sha256") or "").upper() == asset_hash
            and row.get("canonical_receipt") == receipt
            and str(row.get("canonical_receipt_sha256") or "").upper() == receipt_hash
        )
        publish_gate = row.get("media_publish_guard")
        publish_gate = publish_gate if isinstance(publish_gate, dict) else {}
        state = (
            "PASS"
            if matches and publish_gate.get("verdict") == "PASS"
            else "BLOCKED_HUMAN_LISTENING"
            if matches and publish_gate.get("finding") == "human audio review is missing"
            else "BLOCKED_EVIDENCE_MISMATCH"
        )
        revalidation = {
            "state": row.get("state"),
            "fresh_automated_verdict": (
                row.get("fresh_automated_qa") or {}
            ).get("verdict") if isinstance(row.get("fresh_automated_qa"), dict) else None,
            "media_publish_guard_verdict": publish_gate.get("verdict"),
            "media_publish_guard_finding": publish_gate.get("finding"),
        }
    return {
        "state": state,
        "asset": asset,
        "asset_sha256": asset_hash,
        "asset_size_bytes": asset_path.stat().st_size,
        "receipt": receipt,
        "receipt_sha256": receipt_hash,
        "revalidation": revalidation,
    }


def _latest_live_domain_observation(repo: Path) -> Path:
    root = _repo_path(repo, LIVE_DOMAIN_OBSERVATION_DIR.as_posix())
    candidates = sorted(root.glob(LIVE_DOMAIN_OBSERVATION_GLOB))
    if not candidates:
        raise PacketError("live-domain observation is missing")
    selected = candidates[-1]
    if selected.is_symlink() or not selected.is_file():
        raise PacketError("live-domain observation is not a regular file")
    return selected


def _live_domain_state(repo: Path, as_of: datetime) -> tuple[dict, Path]:
    """Validate a local read-only live observation against exact local files.

    A network observation is not a repair attestation. Even a 200 root/sitemap
    remains BLOCKED until the live release manifest exists and exact release
    parity was proven by the observer.
    """
    path = _latest_live_domain_observation(repo)
    payload = _load_object(path)
    failures: list[str] = []
    failures.extend(
        "live-domain observation: " + error
        for error in live_domain_observation.validate_observation(
            repo, payload, as_of=as_of
        )
    )
    if payload.get("observation_kind") != "LIVE_BRANDED_DOMAIN_RELEASE_PARITY":
        failures.append("live-domain observation kind is invalid")
    boundary = payload.get("boundary")
    boundary = boundary if isinstance(boundary, dict) else {}
    if (
        boundary.get("repairs_dns") is not False
        or boundary.get("deploys_site") is not False
        or boundary.get("grants_publication_authority") is not False
        or boundary.get("follows_affiliate_redirects") is not False
    ):
        failures.append("live-domain observation boundary is unsafe or incomplete")
    try:
        observed = _aware_bangkok(payload.get("observed_at"))
    except PacketError:
        observed = None
        failures.append("live-domain observed_at is invalid")

    expected_paths = {
        "site/index.html",
        "site/sitemap.xml",
        "site/release-manifest.json",
        "release/candidate-receipt.json",
    }
    bindings = payload.get("local_candidate_bindings")
    bindings = bindings if isinstance(bindings, list) else []
    actual_paths: set[str] = set()
    current_bindings: dict[str, dict] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            failures.append("live-domain local binding row is malformed")
            continue
        relative = binding.get("path")
        if not isinstance(relative, str) or not relative.strip():
            failures.append("live-domain local binding path is missing")
            continue
        relative = Path(relative).as_posix()
        if relative in actual_paths:
            failures.append("live-domain local binding path is duplicated")
            continue
        actual_paths.add(relative)
        try:
            current = _file_binding(repo, Path(relative))
        except Exception as exc:
            failures.append(
                "live-domain local binding is unreadable: " + type(exc).__name__
            )
            continue
        current_bindings[relative] = current
        if (
            str(binding.get("sha256") or "").upper() != current["sha256"]
            or binding.get("size_bytes") != current["size_bytes"]
        ):
            failures.append("live-domain local binding changed: " + relative)
    if actual_paths != expected_paths:
        failures.append("live-domain local binding inventory is incomplete or extra")

    http = payload.get("http_observations")
    http = http if isinstance(http, dict) else {}
    root = http.get("branded_root") if isinstance(http.get("branded_root"), dict) else {}
    sitemap = (
        http.get("branded_sitemap")
        if isinstance(http.get("branded_sitemap"), dict)
        else {}
    )
    manifest = (
        http.get("branded_release_manifest")
        if isinstance(http.get("branded_release_manifest"), dict)
        else {}
    )
    conclusion = payload.get("conclusion")
    conclusion = conclusion if isinstance(conclusion, dict) else {}
    exact_remote_hash_parity = (
        str(root.get("body_sha256") or "").upper()
        == (current_bindings.get("site/index.html") or {}).get("sha256")
        and str(sitemap.get("body_sha256") or "").upper()
        == (current_bindings.get("site/sitemap.xml") or {}).get("sha256")
        and str(manifest.get("body_sha256") or "").upper()
        == (current_bindings.get("site/release-manifest.json") or {}).get("sha256")
    )
    release_parity_pass = (
        root.get("http_status") == 200
        and sitemap.get("http_status") == 200
        and manifest.get("http_status") == 200
        and exact_remote_hash_parity
        and conclusion.get("live_local_release_parity") == "PASS"
        and conclusion.get("release_attestation_state") == "PASS"
        and conclusion.get("repair_claimed") is False
    )
    if not release_parity_pass:
        failures.append("live branded release parity is not proven")
    if not exact_remote_hash_parity:
        failures.append("live response body hashes do not match the local candidate")
    state = "PASS" if not failures else "BLOCKED"
    return ({
        "state": state,
        "observed_at": observed.isoformat(timespec="seconds") if observed else None,
        "observation_id": payload.get("observation_id"),
        "dns_state": (payload.get("dns") or {}).get("state")
        if isinstance(payload.get("dns"), dict) else "UNKNOWN",
        "release_attestation_state": conclusion.get("release_attestation_state"),
        "live_local_release_parity": conclusion.get("live_local_release_parity"),
        "live_deploy_state": conclusion.get("live_deploy_state"),
        "failures": failures,
    }, path)


def _live_domain_dependency(calendar: dict, placement: dict) -> dict:
    """Classify whether the exact CTA/profile/bio route needs the branded site."""
    reasons: list[str] = []
    cta_id = str(placement.get("cta_id") or "")
    catalog = calendar.get("cta_catalog")
    catalog = catalog if isinstance(catalog, dict) else {}
    cta = catalog.get(cta_id)
    if not isinstance(cta, dict):
        return {
            "depends_on_branded_site": True,
            "reasons": ["CTA registry entry is missing or malformed"],
        }
    landing = cta.get("landing")
    if isinstance(landing, str) and landing.strip():
        target = landing.strip()
        if target.startswith("/"):
            reasons.append("CTA landing is a branded-site relative path")
        else:
            try:
                host = (urlsplit(target).hostname or "").casefold()
            except ValueError:
                host = ""
            if host == "ngernduangold.com" or host.endswith(".ngernduangold.com"):
                reasons.append("CTA landing host is the branded domain")
            elif not host:
                reasons.append("CTA landing host is not provable")
    elif cta.get("until_gate") == "LIVE_LANDING_PARITY":
        reasons.append("CTA is explicitly disabled until live landing parity")
    blockers = {
        str(value) for value in placement.get("blockers", [])
        if isinstance(value, str)
    }
    if blockers & {"live_landing_parity", "landing_parity", "bio_route_parity"}:
        reasons.append("calendar requires live landing or bio-route parity")
    return {
        "depends_on_branded_site": bool(reasons),
        "cta_id": cta_id,
        "cta_kind": cta.get("kind"),
        "landing": landing,
        "reasons": reasons,
    }


def _source_state(repo: Path, placement: dict, caption: str, scheduled: datetime) -> dict:
    gates = placement.get("gates") if isinstance(placement.get("gates"), dict) else {}
    gate = gates.get("source_review")
    content_id = str(placement.get("content_id") or "")
    if gate == "NOT_REQUIRED":
        return {
            "state": "NOT_REQUIRED_EXACT_COPY_HASH_BOUND",
            "allowed": True,
            "source_ids": [],
            "caption_sha256": _sha256_bytes(caption.encode("utf-8")),
            "failures": [],
        }
    if content_id.startswith(("kn-", "p2-", "b3-", "b4-", "tt-r14-")):
        result = content_source_gate.evaluate_repo_content_source_gate(
            content_id,
            repo,
            now=scheduled.astimezone(timezone.utc),
        )
        return {
            "state": "PASS" if result.allowed else "BLOCKED",
            "allowed": bool(result.allowed),
            "source_ids": list(result.source_ids),
            "evaluated_for_slot_at": scheduled.isoformat(timespec="seconds"),
            "failures": list(result.failures),
        }
    return {
        "state": "BLOCKED_TIKTOK_LAUNCH_REVIEW",
        "allowed": False,
        "source_ids": list(placement.get("source_ids") or []),
        "failures": ["calendar requires per-piece TikTok source review"],
    }


def _text_dedup(
    caption: str,
    channel: str,
    scheduled: datetime,
    rows: list[dict],
    report: dict,
    channel_metric: dict,
) -> dict:
    if channel_metric.get("state") != "PASS":
        return {
            "state": "BLOCKED_CHANNEL_COVERAGE",
            "collision": None,
            "reason": "; ".join(channel_metric.get("failures") or []),
        }
    normalized = post_ledger.normalize_text(caption)
    if not normalized:
        return {
            "state": "BLOCKED_EMPTY_IDENTITY",
            "collision": None,
            "reason": "normalized caption identity is empty",
        }
    bindings = report.get("identity_bindings") or {}
    target_hash = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    cutoff = scheduled - timedelta(days=post_ledger.TEXT_DUP_DAYS)
    for line, row in enumerate(rows, 1):
        if str(row.get("type") or "").strip().casefold() not in post_ledger._TEXT_IDENTITY_TYPES:
            continue
        if post_ledger.norm_channel(row.get("channel")) != channel:
            continue
        prior_hash = post_ledger._row_text_identity(row, bindings.get(line))
        if prior_hash == target_hash:
            return {
                "state": "BLOCKED_EXACT_COLLISION",
                "collision": {"ledger_line": line, "type": "PERMANENT_EXACT"},
                "reason": "exact normalized caption already exists on the channel",
            }
        try:
            stamp = datetime.fromisoformat(str(row.get("ts") or "").replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=BANGKOK)
            stamp = stamp.astimezone(BANGKOK)
        except (TypeError, ValueError):
            continue
        prior = row.get("text_norm") or str((bindings.get(line) or {}).get("text_norm") or "")
        if stamp >= cutoff and prior:
            ratio = difflib.SequenceMatcher(None, normalized, prior).ratio()
            if ratio >= post_ledger.TEXT_SIM_THRESHOLD:
                return {
                    "state": "BLOCKED_NEAR_COLLISION",
                    "collision": {
                        "ledger_line": line,
                        "type": "ROLLING_NEAR",
                        "similarity_percent": round(ratio * 100.0, 1),
                    },
                    "reason": "caption is within the rolling near-duplicate threshold",
                }
    return {"state": "PASS", "collision": None, "reason": ""}


def _dedup_state(
    placement: dict,
    caption: str,
    scheduled: datetime,
    global_metric: dict,
    channel_metrics: dict[str, dict],
    rows: list[dict],
    report: dict,
    index: dict,
    channel: str,
) -> dict:
    channel_metric = channel_metrics[channel]
    if placement.get("format") == "video":
        twin, reason, _ = post_ledger.is_twin(
            index,
            channel,
            str(placement.get("content_id") or ""),
            scheduled,
        )
        exact = {
            "state": "BLOCKED_COLLISION_OR_UNKNOWN" if twin else "PASS",
            "collision": bool(twin),
            "reason": reason,
        }
    else:
        exact = _text_dedup(
            caption, channel, scheduled, rows, report, channel_metric
        )
    return {
        "global_state": global_metric.get("state"),
        "global_coverage": {
            "complete_rows": global_metric.get("complete_rows"),
            "incomplete_rows": global_metric.get("incomplete_rows"),
            "identity_rows": global_metric.get("identity_rows"),
            "coverage_percent": global_metric.get("coverage_percent"),
            "duplicate_identity_groups": global_metric.get("duplicate_identity_groups"),
        },
        "channel_state": channel_metric.get("state"),
        "channel_coverage": {
            "channel": channel_metric.get("channel"),
            "complete_rows": channel_metric.get("complete_rows"),
            "incomplete_rows": channel_metric.get("incomplete_rows"),
            "identity_rows": channel_metric.get("identity_rows"),
            "coverage_percent": channel_metric.get("coverage_percent"),
        },
        "exact_candidate_state": exact,
    }


def _effective_blockers(
    placement: dict,
    source: dict,
    media: dict,
    dedup: dict,
    quota_gap: dict,
    live_domain: dict,
    identity_pass: bool,
) -> tuple[list[str], list[str]]:
    blockers = {
        str(value) for value in placement.get("blockers", [])
        if isinstance(value, str) and value.strip()
    }
    # The calendar alias predates the action-scoped channel gate. Publication
    # identity is explicitly same-channel (cross-channel adaptation is allowed),
    # so an incomplete Facebook Story must remain visible in the global audit
    # metric without deadlocking an otherwise complete Threads identity space.
    # The mutation path independently rechecks the same channel-scoped claim;
    # this local packet grants no authority.
    if "permanent_dedup_coverage" in blockers:
        blockers.remove("permanent_dedup_coverage")
    if dedup.get("channel_state") != "PASS":
        blockers.add("channel_permanent_dedup_incomplete")
    exact_state = (dedup.get("exact_candidate_state") or {}).get("state")
    # When exact checking stopped only because channel history is incomplete,
    # the channel-coverage blocker is the root cause; do not double-count the
    # unevaluated candidate as a separate collision.
    if exact_state not in {"PASS", "BLOCKED_CHANNEL_COVERAGE"}:
        blockers.add("exact_dedup_collision_or_unknown")
    if source.get("state") == "BLOCKED":
        failures = " ".join(source.get("failures") or []).casefold()
        if "stale" in failures:
            blockers.add("source_freshness_at_slot")
        if not any(token in failures for token in (
            "human review", "owner review", "review is pending", "manual source evidence", "source changed"
        )):
            blockers.add("source_integrity")
    elif str(source.get("state") or "").startswith("BLOCKED"):
        blockers.add("official_source_review")
    if not str(media.get("state") or "").startswith(("PASS", "NOT_REQUIRED")):
        if media.get("state") == "BLOCKED_HUMAN_LISTENING":
            blockers.add("human_listening_not_run")
        else:
            blockers.add("media_evidence")
    if not identity_pass:
        blockers.add("privacy_public_identity")
    # Capacity/gap intentionally fail closed when the channel history is
    # incomplete. Keep the channel-coverage defect as the single root blocker
    # instead of reporting two derivative failures as independent incidents.
    if dedup.get("channel_state") == "PASS":
        if int(quota_gap.get("remaining_capacity_before_claim") or 0) <= 0:
            blockers.add("daily_quota_exhausted_or_unknown")
        if quota_gap.get("gap_allowed") is not True:
            blockers.add("minimum_gap_failed_or_unknown")
    if (
        live_domain.get("depends_on_branded_site") is True
        and live_domain.get("observation_state") != "PASS"
    ):
        blockers.add("live_branded_release_parity_failed_or_unknown")
    owner = sorted(blockers & OWNER_BLOCKERS)
    non_owner = sorted(blockers - OWNER_BLOCKERS)
    return owner, non_owner


def _quota_gap_state(index: dict, channel: str, scheduled: datetime) -> dict:
    """Return the exact pre-claim policy capacity/gap state, fail closed."""
    try:
        capacity = post_ledger.day_capacity(index, channel, scheduled)
        gap_allowed, gap_reason = post_ledger.minimum_gap(
            index, channel, scheduled
        )
    except Exception as exc:
        return {
            "state": "BLOCKED",
            "remaining_capacity_before_claim": 0,
            "gap_allowed": False,
            "gap_reason": "quota/gap evaluation failed: " + type(exc).__name__,
        }
    allowed = capacity > 0 and gap_allowed is True
    return {
        "state": "PASS" if allowed else "BLOCKED",
        "remaining_capacity_before_claim": capacity,
        "gap_allowed": gap_allowed is True,
        "gap_reason": str(gap_reason or ""),
    }


def _dedup_channel(account_id: str, account: dict) -> str:
    selected = ACCOUNT_DEDUP_CHANNELS.get(account_id, account.get("channel"))
    channel = post_ledger.norm_channel(selected)
    if not channel:
        raise PacketError("calendar account has no canonical dedup channel")
    return channel


def _select_window_placements(
    raw_placements: object,
    anchor: datetime,
    end: datetime,
) -> list[dict]:
    """Select the actual exact-window inventory without a fixture-sized claim.

    The number of calendar rows is evidence, not policy.  A previous version
    hard-coded the eight rows present in the first packet fixture, which made a
    later valid five-row window look malformed before its evidence bindings
    could be checked.  An empty window remains a fail-closed runway gap.
    """
    if not isinstance(raw_placements, list):
        raise PacketError("calendar placements are malformed")
    placements = [
        row for row in raw_placements
        if isinstance(row, dict) and anchor <= _slot(row) <= end
    ]
    placements.sort(key=lambda row: (_slot(row), str(row.get("placement_id") or "")))
    if not placements:
        raise PacketError("exact 48-hour window has no calendar placements")
    return placements


def build_packet(repo: Path, as_of: datetime, hours: int = 48) -> dict:
    repo = repo.resolve()
    if not isinstance(hours, int) or isinstance(hours, bool) or hours != 48:
        raise PacketError("this contract requires an exact 48-hour window")
    anchor = _aware_bangkok(as_of)
    end = anchor + timedelta(hours=hours)
    calendar_path = _repo_path(repo, CALENDAR.as_posix())
    calendar = _load_object(calendar_path)
    policy = _load_object(_repo_path(repo, POLICY.as_posix()))
    capabilities = _load_object(_repo_path(repo, CAPABILITIES.as_posix()))
    calendar_hash = _sha256(calendar_path)

    placements = _select_window_placements(
        calendar.get("placements"), anchor, end
    )
    if any(row.get("status") != BLOCKED_CALENDAR_STATE for row in placements):
        raise PacketError("48-hour placement was promoted from PLANNED_BLOCKED")

    media_index, media_binding = _media_index(
        repo, calendar_hash, anchor, end, placements
    )
    live_domain_control, live_domain_path = _live_domain_state(repo, anchor)
    caption_cache: dict[str, object] = {}
    privacy_findings, _privacy_count, privacy_operational = privacy_guard.scan_repository(repo)
    identity_findings, identity_counts = public_identity_guard.scan(repo=repo)
    global_metric = post_ledger.permanent_dedup_completeness(repo / LEDGER)
    ledger_rows, ledger_report = post_ledger._read_ledger_snapshot(repo / LEDGER)
    if ledger_report.get("state") != "OK":
        raise PacketError("post ledger integrity is not OK")
    ledger_index = post_ledger.load_index(repo / LEDGER, since_days=None)

    accounts = calendar.get("accounts") if isinstance(calendar.get("accounts"), dict) else {}
    channels = {
        _dedup_channel(
            str(row.get("account") or ""),
            accounts.get(str(row.get("account") or "")) or {},
        )
        for row in placements
    }
    if "" in channels:
        raise PacketError("calendar account has no canonical channel")
    channel_metrics = {
        channel: post_ledger.permanent_dedup_channel_completeness(
            channel, repo / LEDGER
        )
        for channel in sorted(channels)
    }

    policy_channels = policy.get("channels") if isinstance(policy.get("channels"), dict) else {}
    actors = capabilities.get("actors") if isinstance(capabilities.get("actors"), dict) else {}
    codex = actors.get("codex") if isinstance(actors.get("codex"), dict) else {}
    identity_global_pass = (
        not privacy_findings
        and not privacy_operational
        and not identity_findings
    )
    packet_rows: list[dict] = []
    for placement in placements:
        scheduled = _slot(placement)
        account_id = str(placement.get("account") or "")
        account = accounts.get(account_id)
        if not isinstance(account, dict):
            raise PacketError(f"calendar account is missing: {account_id}")
        channel = post_ledger.norm_channel(account.get("channel"))
        dedup_channel = _dedup_channel(account_id, account)
        caption, caption_binding = _caption(repo, placement, caption_cache)
        source = _source_state(repo, placement, caption, scheduled)
        media = _media_state(repo, placement, media_index)
        dedup = _dedup_state(
            placement,
            caption,
            scheduled,
            global_metric,
            channel_metrics,
            ledger_rows,
            ledger_report,
            ledger_index,
            dedup_channel,
        )
        dedup["decision_scope"] = "CHANNEL_AND_EXACT_CANDIDATE"
        dedup["global_state_role"] = "AUDIT_ONLY_NOT_ACTION_GATE"
        quota_gap = _quota_gap_state(ledger_index, dedup_channel, scheduled)
        live_domain = _live_domain_dependency(calendar, placement)
        live_domain.update({
            "observation_state": live_domain_control.get("state"),
            "observation_id": live_domain_control.get("observation_id"),
            "observed_at": live_domain_control.get("observed_at"),
            "release_attestation_state": live_domain_control.get(
                "release_attestation_state"
            ),
            "live_local_release_parity": live_domain_control.get(
                "live_local_release_parity"
            ),
        })
        page_identity_pass = (
            identity_global_pass
            and account.get("page_only") is True
            and account.get("entity_type") == "Organization"
            and isinstance(account.get("public_speaker"), str)
            and bool(account.get("public_speaker").strip())
            and (placement.get("gates") or {}).get("page_identity") == "PASS"
        )
        owner_blockers, non_owner_blockers = _effective_blockers(
            placement,
            source,
            media,
            dedup,
            quota_gap,
            live_domain,
            page_identity_pass,
        )
        if non_owner_blockers:
            decision_state = "BLOCKED_NOT_READY_FOR_OWNER_DECISION"
        elif owner_blockers:
            decision_state = "READY_FOR_OWNER_DECISION"
        else:
            decision_state = "READY_ALL_GATES"
        policy_channel = str(account.get("policy_channel") or channel)
        channel_policy = policy_channels.get(policy_channel)
        channel_policy = channel_policy if isinstance(channel_policy, dict) else {}
        packet_rows.append({
            "placement_id": placement.get("placement_id"),
            "content_id": placement.get("content_id"),
            "scheduled_at": scheduled.isoformat(timespec="seconds"),
            "target": {
                "account_id": account_id,
                "channel": channel,
                "dedup_channel": dedup_channel,
                "public_speaker": account.get("public_speaker"),
                "entity_type": account.get("entity_type"),
                "page_only": account.get("page_only"),
                "account_handle": account.get("account_handle"),
                "profile_url": account.get("profile_url"),
            },
            "calendar_state": {
                "status": placement.get("status"),
                "slot_state": placement.get("slot_state"),
                "publication_authorized": False,
                "placement_canonical_sha256": _canonical_sha256(placement),
            },
            "caption_binding": caption_binding,
            "media": media,
            "source": source,
            "dedup": dedup,
            "quota_gap": quota_gap,
            "live_domain": live_domain,
            "privacy_public_identity": {
                "state": "PASS" if page_identity_pass else "BLOCKED",
                "repo_privacy_guard": "PASS" if not privacy_findings and not privacy_operational else "BLOCKED",
                "repo_public_identity_guard": "PASS" if not identity_findings else "BLOCKED",
                "page_identity_gate": (placement.get("gates") or {}).get("page_identity"),
            },
            "authority": {
                "calendar_default_publication_authorized": (
                    calendar.get("defaults") or {}
                ).get("publication_authorized"),
                "policy_channel_publication_authorized": channel_policy.get("publication_authorized"),
                "codex_social_publish_capability": codex.get("social_publish"),
                "exact_private_owner_receipt_present": False,
            },
            "owner_blockers": owner_blockers,
            "non_owner_blockers": non_owner_blockers,
            "decision_state": decision_state,
            "publication_state": "BLOCKED",
        })

    ranked = sorted(
        packet_rows,
        key=lambda row: (
            len(row["non_owner_blockers"]),
            len(row["owner_blockers"]),
            row["scheduled_at"],
            row["placement_id"],
        ),
    )
    closest = ranked[0]
    ready_count = sum(
        row["decision_state"] == "READY_FOR_OWNER_DECISION" for row in packet_rows
    )
    all_ready = sum(row["decision_state"] == "READY_ALL_GATES" for row in packet_rows)
    bound_inputs = {
        "calendar": _file_binding(repo, CALENDAR),
        "policy": _file_binding(repo, POLICY),
        "role_capabilities": _file_binding(repo, CAPABILITIES),
        "post_ledger": _file_binding(repo, LEDGER),
        "post_ledger_identity_bindings": _file_binding(repo, IDENTITY_BINDINGS),
        "post_ledger_collision_tombstones": _file_binding(repo, COLLISION_TOMBSTONES),
        "official_news_snapshot": _file_binding(repo, OFFICIAL_SNAPSHOT),
        "source_registries": [_file_binding(repo, path) for path in SOURCE_REGISTRIES],
        "media_revalidation": media_binding,
        "live_domain_observation": _file_binding(
            repo, live_domain_path.relative_to(repo)
        ),
        "generator": _file_binding(repo, GENERATOR_PATH),
        "privacy_guard": _file_binding(repo, Path("tools/privacy_guard.py")),
        "public_identity_guard": _file_binding(repo, Path("tools/public_identity_guard.py")),
    }
    packet = {
        "schema_version": 1,
        "packet_kind": PACKET_KIND,
        "as_of": anchor.isoformat(timespec="seconds"),
        "timezone": "Asia/Bangkok",
        "window": {
            "start_inclusive": anchor.isoformat(timespec="seconds"),
            "end_inclusive": end.isoformat(timespec="seconds"),
            "hours": 48,
            "selection": "calendar scheduled_at within the exact inclusive window",
        },
        "boundary": {
            "scope": "LOCAL_ONLY_READINESS_EVIDENCE",
            "is_approval_receipt": False,
            "grants_publication_authority": False,
            "calendar_or_policy_mutated": False,
            "external_actions_performed": False,
            "publication_requires_mutation_boundary_recheck": True,
        },
        "bound_inputs": bound_inputs,
        "quality_controls": {
            "privacy_guard": {
                "state": "PASS" if not privacy_findings and not privacy_operational else "BLOCKED",
                "finding_count": len(privacy_findings),
                "operational_error": privacy_operational,
            },
            "public_identity_guard": {
                "state": "PASS" if not identity_findings else "BLOCKED",
                "counts": identity_counts,
                "finding_count": len(identity_findings),
            },
            "live_domain": live_domain_control,
        },
        "summary": {
            "placement_count": len(packet_rows),
            "ready_for_owner_decision": ready_count,
            "blocked_not_ready_for_owner_decision": len(packet_rows) - ready_count - all_ready,
            "ready_all_gates": all_ready,
            "publishable": 0,
            "closest_placement_id": closest["placement_id"],
            "closest_decision_state": closest["decision_state"],
            "closest_owner_blockers": closest["owner_blockers"],
            "closest_non_owner_blockers": closest["non_owner_blockers"],
        },
        "placements": packet_rows,
    }
    if any(row["publication_state"] != "BLOCKED" for row in packet_rows):
        raise PacketError("packet attempted to authorize publication")
    packet["packet_payload_sha256"] = _canonical_sha256(packet)
    return packet


def validate_packet(packet: dict, repo: Path) -> list[str]:
    failures: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be a JSON object"]
    supplied_hash = packet.get("packet_payload_sha256")
    unsigned = dict(packet)
    unsigned.pop("packet_payload_sha256", None)
    if supplied_hash != _canonical_sha256(unsigned):
        failures.append("packet payload SHA-256 mismatch")
    try:
        as_of = _aware_bangkok(packet.get("as_of"))
        expected = build_packet(repo, as_of, int((packet.get("window") or {}).get("hours")))
    except Exception as exc:
        failures.append(f"packet recomputation failed: {type(exc).__name__}: {exc}")
        return failures
    if packet != expected:
        failures.append("packet does not equal deterministic recomputation")
    return failures


def _write_packet(path: Path, packet: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--as-of", help="timezone-aware ISO-8601 evaluation instant")
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.validate is not None:
            packet = _load_object(args.validate.resolve())
            failures = validate_packet(packet, args.repo)
            if failures:
                print(json.dumps({"verdict": "FAIL", "failures": failures}, ensure_ascii=False))
                return 2
            print(json.dumps({
                "verdict": "PASS",
                "packet": str(args.validate),
                "packet_payload_sha256": packet.get("packet_payload_sha256"),
                "summary": packet.get("summary"),
            }, ensure_ascii=False))
            return 0
        if not args.as_of:
            raise PacketError("--as-of is required for deterministic generation")
        packet = build_packet(args.repo, _aware_bangkok(args.as_of), args.hours)
        if args.output is not None:
            _write_packet(args.output.resolve(), packet)
        print(json.dumps({
            "verdict": "PASS",
            "output": str(args.output) if args.output else None,
            "packet_payload_sha256": packet.get("packet_payload_sha256"),
            "summary": packet.get("summary"),
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
