#!/usr/bin/env python3
"""Read-only, fail-closed daily coverage for publishable media.

The old batch command scanned two staging globs and could miss the canonical
``reels/`` file that an operator would actually publish.  It also treated the
Veo sparkle detector as though it could assess still images.  This gate keeps
those responsibilities separate:

* every canonical video physically present under ``reels/`` (plus every reel
  referenced by the content manifest) gets a fresh Veo frame scan; and
* every media asset whose exact Bangkok slot has not passed must carry a
  hash-bound visual QA receipt and pass ``media_publish_guard``.  Images are
  never sent to the video detector.  Legacy date-only reel routes remain in
  scope for their whole Bangkok day because they do not contain enough
  evidence to infer an earlier cutoff.

The gate never walks quarantine and never writes to media, manifests, receipts,
or schedules.  The video detector uses only a temporary frame directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import media_publish_guard as publish_guard


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(".system_control/content_manifest.json")
CALENDAR = Path(".system_control/content_calendar.json")
SCHEDULE = Path("reels/schedule.json")
REPORT_ROOT = Path("automation-log/media-qa")
REELS_ROOT = Path("reels")
VIDEO_EXTENSIONS = set(publish_guard.VIDEO_EXTENSIONS)
IMAGE_EXTENSIONS = set(publish_guard.IMAGE_EXTENSIONS)
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
APPROVED_ROOTS = tuple(Path(value) for value in publish_guard.APPROVED_ROOTS)
BANGKOK = dt.timezone(dt.timedelta(hours=7), name="Asia/Bangkok")


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _thai_now() -> dt.datetime:
    # Thailand has no daylight-saving changes; a fixed UTC+07:00 avoids relying
    # on an optional Windows tzdata package in the scheduled-task interpreter.
    return dt.datetime.now(BANGKOK)


def _evaluation_clock(
    *, now: dt.datetime | None, today: dt.date | None, findings: list[str]
) -> dt.datetime:
    """Return one aware Bangkok instant without silently accepting ambiguity.

    ``today`` is retained only as a deterministic compatibility override and
    means the start of that Bangkok day.  Runtime callers should omit both (or
    supply ``now``) so a same-day slot that has already passed is not counted as
    future media merely because its calendar date equals today's date.
    """
    if now is not None and today is not None:
        findings.append("provide now or today, not both")
    if now is not None:
        if now.tzinfo is None or now.utcoffset() is None:
            findings.append("evaluation now must include a timezone")
            return now.replace(tzinfo=BANGKOK)
        return now.astimezone(BANGKOK)
    if today is not None:
        return dt.datetime.combine(today, dt.time.min, tzinfo=BANGKOK)
    return _thai_now()


def _parse_clock(value: object) -> dt.time | None:
    try:
        return dt.datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError):
        return None


def _load_object(path: Path, label: str, findings: list[str]) -> dict:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    try:
        if path.is_symlink():
            raise ValueError("symlink")
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or len(raw) != after.st_size:
            raise ValueError("changed while being read")
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
        require_finite(value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        findings.append(f"{label} is missing or unreadable: {str(exc)[:120]}")
        return {}
    if not isinstance(value, dict):
        findings.append(f"{label} must contain a JSON object")
        return {}
    return value


def _repo_relative_path(repo: Path, raw: object, *, default_reels: bool) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip().replace("\\", "/")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    if default_reels:
        # Bare schedule filenames historically mean ``reels/<file>``.  An
        # explicit ``media/...`` path must remain explicit so that the approved
        # root check can reject ``media/quarantine`` instead of accidentally
        # rewriting it to ``reels/media/quarantine``.
        top_level = relative.parts[0].casefold() if relative.parts else ""
        known_media_top_levels = {root.parts[0].casefold() for root in APPROVED_ROOTS}
        if top_level not in known_media_top_levels:
            relative = REELS_ROOT / relative
    return (repo / relative).resolve()


def _approved_asset(repo: Path, path: Path) -> bool:
    if not _within(path, repo):
        return False
    return any(_within(path, (repo / root).resolve()) for root in APPROVED_ROOTS)


def _report_path(repo: Path, raw: object) -> Path | None:
    path = _repo_relative_path(repo, raw, default_reels=False)
    if path is None or not _within(path, (repo / REPORT_ROOT).resolve()):
        return None
    return path


def _receipt_index(repo: Path) -> dict[Path, list[Path]]:
    """Index receipts by their declared asset without trusting the declaration.

    ``media_publish_guard`` performs the authoritative path/hash/schema checks.
    This index only lets an unscheduled canonical poster find its receipt.
    """
    root = (repo / REPORT_ROOT).resolve()
    index: dict[Path, list[Path]] = {}
    if not root.is_dir():
        return index
    for report in sorted(root.rglob("*.json")):
        findings: list[str] = []
        payload = _load_object(report, "media QA receipt", findings)
        if findings:
            continue
        asset = _repo_relative_path(repo, payload.get("asset"), default_reels=False)
        if asset is None or not _approved_asset(repo, asset):
            continue
        index.setdefault(asset, []).append(report.resolve())
    return index


def _route_entries(row: dict) -> list[dict]:
    """Support the current one-asset row and an optional multi-media row."""
    if "media" not in row:
        return [row]
    media = row.get("media")
    if not isinstance(media, list) or not media or any(not isinstance(item, dict) for item in media):
        return []
    return list(media)


def _default_scan(path: Path, fps: float) -> dict:
    return publish_guard._default_video_scan(path, fps)


def _default_guard(path: Path, report: Path, *, repo: Path, scanner) -> dict:
    return publish_guard.evaluate(path, report, repo=repo, scanner=scanner)


def evaluate(
    *,
    repo: Path = ROOT,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
    fps: float = 3.0,
    scanner=None,
    guard_runner=None,
) -> dict:
    """Return a structured daily verdict without changing repository state."""
    repo = Path(repo).resolve()
    scanner = scanner or _default_scan
    guard_runner = guard_runner or _default_guard
    findings: list[str] = []
    evaluation_now = _evaluation_clock(now=now, today=today, findings=findings)
    current_day = evaluation_now.date()
    checked: list[dict] = []
    coverage = {
        "manifest_references": 0,
        "canonical_video_files": 0,
        "canonical_video_scans": 0,
        "canonical_videos_guarded_as_future": 0,
        "future_video_diagnostic_scans": 0,
        "canonical_image_files": 0,
        "canonical_image_guards": 0,
        "future_routes": 0,
        "legacy_schedule_routes": 0,
        "content_calendar_routes": 0,
        "deduplicated_guard_bindings": 0,
        "future_video_guards": 0,
        "future_image_guards": 0,
        "quarantine_files_scanned": 0,
    }

    manifest = _load_object(repo / MANIFEST, "content manifest", findings)
    schedule = _load_object(repo / SCHEDULE, "reels schedule", findings)
    calendar = _load_object(repo / CALENDAR, "content calendar", findings)

    canonical_videos: set[Path] = set()
    canonical_images: set[Path] = set()
    manifest_image_reports: dict[Path, tuple[object, str]] = {}
    items = manifest.get("items", [])
    if not isinstance(items, list):
        findings.append("content manifest items must be a list")
        items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            findings.append(f"manifest item {index} is not an object")
            continue
        raw = item.get("reel")
        if not isinstance(raw, str) or not raw.strip():
            findings.append(f"manifest item {index} has no reel path")
            continue
        coverage["manifest_references"] += 1
        path = _repo_relative_path(repo, raw, default_reels=False)
        label = str(item.get("id") or index)
        if path is None or not _within(path, (repo / REELS_ROOT).resolve()):
            findings.append(f"manifest {label}: reel path is outside reels/")
            continue
        if path.is_symlink():
            findings.append(f"manifest {label}: symlink media is not allowed")
            continue
        if not path.is_file():
            findings.append(f"manifest {label}: {raw} is missing")
            continue
        suffix = path.suffix.casefold()
        if suffix in VIDEO_EXTENSIONS:
            canonical_videos.add(path)
        elif suffix in IMAGE_EXTENSIONS:
            canonical_images.add(path)
            manifest_image_reports[path] = (item.get("qa_report"), f"manifest {label}")
        else:
            findings.append(f"manifest {label}: unsupported media extension {suffix or '<none>'}")

    reels_root = (repo / REELS_ROOT).resolve()
    if not reels_root.is_dir():
        findings.append("canonical reels directory is missing")
    else:
        for candidate in sorted(reels_root.rglob("*")):
            suffix = candidate.suffix.casefold()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue
            if candidate.is_symlink():
                findings.append(f"canonical media is a symlink: {candidate.relative_to(repo).as_posix()}")
                continue
            resolved = candidate.resolve()
            if not _within(resolved, reels_root):
                findings.append(f"canonical media escapes reels/: {candidate}")
                continue
            if candidate.is_file():
                if suffix in VIDEO_EXTENSIONS:
                    canonical_videos.add(resolved)
                else:
                    canonical_images.add(resolved)

    future_paths: set[Path] = set()
    guard_routes: list[tuple[str, Path, Path, str]] = []
    guard_route_keys: set[tuple[Path, Path]] = set()

    def register_future_route(
        route_label: str,
        raw_asset: object,
        raw_report: object,
        *,
        default_reels: bool,
        route_counter: str,
    ) -> None:
        """Bind one future route to exact media and receipt evidence.

        The legacy reels schedule accepts bare filenames as ``reels/<file>``.
        The canonical content calendar must use explicit repository-relative
        paths.  During migration the same asset/receipt pair can occur in both
        inputs; guard that exact pair once while retaining both route counts.
        """
        coverage["future_routes"] += 1
        coverage[route_counter] += 1
        path = _repo_relative_path(repo, raw_asset, default_reels=default_reels)
        if path is None:
            findings.append(
                f"{route_label}: asset path is missing, absolute, or traverses upward")
            return
        if not _approved_asset(repo, path):
            findings.append(f"{route_label}: asset is outside approved canonical media roots")
            return
        future_paths.add(path)
        if path.is_symlink():
            findings.append(f"{route_label}: symlink media is not allowed")
            return
        if not path.is_file():
            findings.append(
                f"{route_label}: asset is missing: {path.relative_to(repo).as_posix()}")
            return
        if path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            findings.append(
                f"{route_label}: unsupported media extension {path.suffix or '<none>'}")
            return
        report = _report_path(repo, raw_report)
        if report is None:
            findings.append(
                f"{route_label}: hash-bound qa_report is missing or outside "
                f"{REPORT_ROOT.as_posix()}")
            return
        if not report.is_file():
            findings.append(
                f"{route_label}: QA receipt is missing: {report.relative_to(repo).as_posix()}")
            return
        key = (path, report)
        if key in guard_route_keys:
            coverage["deduplicated_guard_bindings"] += 1
            return
        guard_route_keys.add(key)
        guard_routes.append((route_label, path, report, "future"))

    for raw_day, row in sorted(schedule.items(), key=lambda pair: str(pair[0])):
        try:
            day = dt.date.fromisoformat(str(raw_day))
        except ValueError:
            findings.append(f"schedule has invalid date key: {raw_day}")
            continue
        # A legacy schedule key has only day precision.  Keep all routes on the
        # current Bangkok day in scope rather than inventing a time-of-day that
        # could suppress a still-upcoming route.
        if day < current_day:
            continue
        if not isinstance(row, dict):
            findings.append(f"schedule {raw_day}: row is not an object")
            continue
        entries = _route_entries(row)
        if not entries:
            findings.append(f"schedule {raw_day}: media routes are missing or invalid")
            continue
        for position, entry in enumerate(entries, start=1):
            route_label = f"schedule {raw_day} media {position}"
            register_future_route(
                route_label,
                entry.get("asset") or entry.get("file"),
                entry.get("qa_report"),
                default_reels=True,
                route_counter="legacy_schedule_routes",
            )

    placements = calendar.get("placements", [])
    if not isinstance(placements, list):
        findings.append("content calendar placements must be a list")
        placements = []
    for index, row in enumerate(placements):
        if not isinstance(row, dict):
            findings.append(f"content calendar placement {index}: row is not an object")
            continue
        raw_day = row.get("date")
        try:
            day = dt.date.fromisoformat(str(raw_day))
        except ValueError:
            findings.append(f"content calendar placement {index}: invalid date {raw_day}")
            continue
        if day < current_day:
            continue
        clock = _parse_clock(row.get("time"))
        if clock is None:
            findings.append(
                f"content calendar placement {index}: invalid time {row.get('time')}")
            continue
        slot_at = dt.datetime.combine(day, clock, tzinfo=BANGKOK)
        if slot_at < evaluation_now:
            continue
        placement_id = row.get("placement_id")
        if not isinstance(placement_id, str) or not placement_id.strip():
            placement_id = str(index)
        media = row.get("media")
        media_format = str(row.get("format") or "").strip().casefold()
        if media in (None, ""):
            if media_format in {"image", "video"}:
                findings.append(
                    f"content calendar {placement_id}: {media_format} placement has no media")
            continue
        if not isinstance(media, str):
            findings.append(
                f"content calendar {placement_id}: media must be one explicit path")
            continue
        register_future_route(
            f"content calendar {placement_id}",
            media,
            row.get("media_receipt"),
            default_reels=False,
            route_counter="content_calendar_routes",
        )

    # Every image in the canonical reels root is a still-media route. It must
    # never be passed to the Veo scanner. An explicit manifest receipt wins;
    # otherwise discover the one receipt whose declared asset matches.
    receipt_index = _receipt_index(repo)
    coverage["canonical_image_files"] = len(canonical_images)
    for path in sorted(canonical_images):
        if path in future_paths:
            continue
        explicit = manifest_image_reports.get(path)
        if explicit:
            raw_report, label = explicit
            report = _report_path(repo, raw_report)
            candidates = [report] if report is not None else []
        else:
            label = f"canonical image {path.relative_to(repo).as_posix()}"
            candidates = receipt_index.get(path, [])
        if len(candidates) != 1 or not candidates[0].is_file():
            reason = "missing" if not candidates else "ambiguous or unreadable"
            findings.append(f"{label}: hash-bound QA receipt is {reason}")
            continue
        guard_routes.append((label, path, candidates[0], "canonical-image"))

    guarded_paths: set[Path] = set()
    for label, path, report, route_type in guard_routes:
        try:
            result = guard_runner(path, report, repo=repo, scanner=scanner)
        except Exception as exc:
            result = {"verdict": "ERROR", "findings": [str(exc)[:160]]}
        verdict = result.get("verdict") if isinstance(result, dict) else "ERROR"
        media_type = "video" if path.suffix.casefold() in VIDEO_EXTENSIONS else "image"
        if route_type == "canonical-image":
            coverage["canonical_image_guards"] += 1
        elif media_type == "video":
            coverage["future_video_guards"] += 1
        else:
            coverage["future_image_guards"] += 1
        guarded_paths.add(path)
        checked.append({
            "asset": path.relative_to(repo).as_posix(),
            "source": label,
            "method": "hash-bound-media-guard",
            "media_type": media_type,
            "verdict": verdict,
            "diagnostic_findings": (
                result.get("diagnostic_findings", [])
                if isinstance(result, dict)
                else []
            ),
        })
        if verdict != "PASS":
            detail = result.get("findings", []) if isinstance(result, dict) else []
            findings.append(f"{label}: media guard {verdict}: {'; '.join(map(str, detail))[:240]}")

    coverage["canonical_video_files"] = len(canonical_videos)
    for path in sorted(canonical_videos):
        if path in future_paths:
            if path in guarded_paths:
                coverage["canonical_videos_guarded_as_future"] += 1
                continue
            # A missing/bad future receipt remains a hard blocker, but that
            # must not suppress independent watermark diagnostics.  The bare
            # scan is recorded as untrusted route evidence and can never turn
            # the already-failed route into an apparent publication pass.
            coverage["future_video_diagnostic_scans"] += 1
        try:
            result = scanner(path, fps)
        except Exception as exc:
            result = {"verdict": "ERROR", "error": str(exc)[:160]}
        verdict = result.get("verdict") if isinstance(result, dict) else "ERROR"
        coverage["canonical_video_scans"] += 1
        checked.append({
            "asset": path.relative_to(repo).as_posix(),
            "source": (
                "future-route-without-valid-receipt"
                if path in future_paths
                else "canonical-reels"
            ),
            "method": "veo-frame-scan",
            "media_type": "video",
            "verdict": verdict,
            "frames": result.get("frames") if isinstance(result, dict) else None,
            "track_frames": result.get("track_frames") if isinstance(result, dict) else None,
        })
        if verdict != "PASS":
            detail = result.get("error") if isinstance(result, dict) else "invalid scanner result"
            findings.append(
                f"canonical reel {path.relative_to(repo).as_posix()}: frame scan {verdict}"
                + (f" ({detail})" if detail else "")
            )

    return {
        "verdict": "PASS" if not findings else "FAIL",
        "today": current_day.isoformat(),
        "evaluated_at": evaluation_now.isoformat(),
        "coverage": coverage,
        "findings": findings,
        "checked": checked,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="fail-closed daily canonical media coverage gate")
    parser.add_argument("--fps", type=float, default=3.0)
    clock_group = parser.add_mutually_exclusive_group()
    clock_group.add_argument(
        "--now",
        help="timezone-aware ISO-8601 evaluation instant; converted to Asia/Bangkok",
    )
    clock_group.add_argument(
        "--today",
        help="Asia/Bangkok date override at 00:00 for deterministic compatibility tests",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        today = dt.date.fromisoformat(args.today) if args.today else None
    except ValueError:
        parser.error("--today must be YYYY-MM-DD")
    evaluation_now = None
    if args.now:
        try:
            evaluation_now = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            parser.error("--now must be an ISO-8601 timestamp")
        if evaluation_now.tzinfo is None or evaluation_now.utcoffset() is None:
            parser.error("--now must include a UTC offset or Z")
    result = evaluate(today=today, now=evaluation_now, fps=args.fps)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        coverage = result["coverage"]
        print(
            f"{result['verdict']} canonical={coverage['canonical_video_files']} "
            f"scanned={coverage['canonical_video_scans']} "
            f"future={coverage['future_routes']} guarded="
            f"{coverage['future_video_guards'] + coverage['future_image_guards']}"
        )
        for finding in result["findings"]:
            print("- " + finding)
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
