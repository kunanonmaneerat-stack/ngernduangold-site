#!/usr/bin/env python3
"""Hash-bound, fail-closed media gate for social publication.

An automated Veo-sparkle scan cannot prove that every possible provider mark or
logo is absent.  Publication therefore requires both layers:

* a visual-review receipt bound to the exact SHA-256 of every image/video; and
* a fresh automated frame scan for video files.

Only canonical social assets are accepted. Raw/generated/staging footage is never
publishable even when somebody writes a receipt for it.  For video, automated
audio measurements are technical evidence only: a final receipt must also carry
an explicit human-listening review bound to the exact final asset SHA-256.

``media_origin`` is treated as an allow-listed declaration, not independent
proof of how bytes were created.  The result therefore calls it an attestation
and never reports the origin as verified.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sys

try:
    from tools import generative_media_origin_gate
except ImportError:  # Direct ``py tools/media_publish_guard.py`` execution.
    import generative_media_origin_gate


ROOT = Path(__file__).resolve().parents[1]
APPROVED_ROOTS = ("reels", "media/pins", "media/quotes")
REPORT_ROOT = Path("automation-log/media-qa")
DUPLICATE_REGISTRY = REPORT_ROOT / "published-media.json"
MANIFEST = Path(".system_control/content_manifest.json")
GENERATIVE_MEDIA_POLICY = Path(".system_control/generative_media_policy.json")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
HUMAN_REVIEWER_TYPES = {"HUMAN", "OWNER"}
SHA256_HEX = set("0123456789ABCDEF")
MAX_REVIEW_FUTURE_SKEW = timedelta(minutes=5)
CORPUS_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
CORPUS_CLAIM_LOCK = Path(
    ".local-private/runtime/media-publication-corpus.lock"
)
CORPUS_BINDING_FIELDS = {
    "schema_version",
    "corpus_fingerprint",
    "content_id",
    "asset",
    "asset_sha256",
}


class MediaPublicationBlocked(RuntimeError):
    """The local media corpus cannot authorize this mutation boundary."""


def _is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_json(path):
    def reject_constant(token):
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicate_keys(pairs):
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
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
        require_finite(value)
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None


def _path_is_linklike(path):
    """Treat symlinks and Windows junctions as mutable corpus indirection."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction is not None and is_junction())
    except OSError:
        # Unreadable link metadata cannot be publication evidence.
        return True


def _strict_json_object(raw, label):
    """Decode one corpus object without non-finite values or duplicate keys."""
    def reject_constant(token):
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is unreadable or malformed") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
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
        require_finite(value)
    except ValueError as exc:
        raise ValueError(f"{label} is unreadable or malformed") from exc
    return value


def _assert_no_link_components(repo, relative, label):
    current = repo
    for part in relative.parts:
        current = current / part
        if _path_is_linklike(current):
            raise ValueError(f"{label} must not use a symlink or junction")


def _canonical_corpus_file(repo, raw, label):
    """Return one readable, canonical, repository-contained corpus asset."""
    if not isinstance(raw, str) or not raw.strip() or raw != raw.strip():
        raise ValueError(f"{label} path is missing or non-canonical")
    relative = Path(raw)
    if (
        relative.is_absolute()
        or relative.as_posix() != raw
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(":" in part for part in relative.parts)
    ):
        raise ValueError(f"{label} path is not canonical repository-relative POSIX")
    _assert_no_link_components(repo, relative, label)
    try:
        resolved = (repo / relative).resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} path is missing or escapes the repository") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} path is not a regular file")
    if resolved.suffix.casefold() not in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS:
        raise ValueError(f"{label} path is not a supported media file")
    try:
        actual_hash = _sha256(resolved)
    except OSError as exc:
        raise ValueError(f"{label} path is unreadable") from exc
    return resolved, actual_hash


def _read_corpus_document(repo, relative, label):
    _assert_no_link_components(repo, relative, label)
    path = repo / relative
    if not path.is_file():
        raise ValueError(f"{label} is missing or not a regular file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} is unreadable") from exc
    return raw, _strict_json_object(raw, label)


def _corpus_identity(value, label):
    if (
        not isinstance(value, str)
        or value != value.strip()
        or CORPUS_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(f"{label} identity is missing or non-canonical")
    return value


def _validated_publication_corpus(repo):
    """Load the exact novelty corpus, rejecting every ambiguous shape.

    The returned records are snapshots of the same validated documents used to
    build the fingerprint, so malformed registry data cannot be fingerprinted
    and then silently disappear from permanent duplicate comparison.
    """
    repo = Path(repo).resolve()
    manifest_raw, manifest = _read_corpus_document(
        repo, MANIFEST, "content manifest"
    )
    registry_raw, registry = _read_corpus_document(
        repo, DUPLICATE_REGISTRY, "published media registry"
    )
    if registry.get("schema_version") != 1:
        raise ValueError("published media registry schema_version is unsupported")

    manifest_items = manifest.get("items")
    registry_items = registry.get("items")
    if not isinstance(manifest_items, list):
        raise ValueError("content manifest items must be an exact list")
    if not isinstance(registry_items, list):
        raise ValueError("published media registry items must be an exact list")

    seen_identities = set()
    seen_paths = set()
    records = []

    def add_record(source, index, item, identity_field, path_field):
        if not isinstance(item, dict):
            raise ValueError(f"{source} item {index} must be an object")
        identity = _corpus_identity(
            item.get(identity_field), f"{source} item {index}"
        )
        path, actual_hash = _canonical_corpus_file(
            repo, item.get(path_field), f"{source} item {index}"
        )
        identity_key = identity.casefold()
        path_key = str(path).casefold()
        if identity_key in seen_identities:
            raise ValueError("publication corpus contains a duplicate identity")
        if path_key in seen_paths:
            raise ValueError("publication corpus contains a duplicate asset path")
        seen_identities.add(identity_key)
        seen_paths.add(path_key)
        records.append((source, identity, path, actual_hash))

    for index, item in enumerate(manifest_items):
        add_record("content manifest", index, item, "id", "reel")
    for index, item in enumerate(registry_items):
        add_record(
            "published media registry", index, item, "content_id", "asset"
        )
        declared_hash = _exact_sha256(item.get("sha256"))
        if declared_hash is None or declared_hash != records[-1][3]:
            raise ValueError(
                f"published media registry item {index} SHA-256 is missing or stale"
            )
        if not isinstance(item.get("status"), str) or not item["status"].strip():
            raise ValueError(
                f"published media registry item {index} status is missing"
            )

    return (
        ((MANIFEST, manifest_raw), (DUPLICATE_REGISTRY, registry_raw)),
        tuple(records),
    )


def _corpus_fingerprint(documents):
    digest = hashlib.sha256()
    for relative, raw in documents:
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")
    return digest.hexdigest().upper()


def _exact_sha256(value):
    normalized = str(value or "").strip().upper()
    return normalized if len(normalized) == 64 and set(normalized) <= SHA256_HEX else None


def _aware_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (
            parsed.astimezone(timezone.utc)
            if parsed.tzinfo is not None and parsed.utcoffset() is not None
            else None
        )
    except (TypeError, ValueError):
        return None


def _review_clock(now):
    current = now or datetime.now(timezone.utc)
    if (
        not isinstance(current, datetime)
        or current.tzinfo is None
        or current.utcoffset() is None
    ):
        return None
    return current.astimezone(timezone.utc)


def _evidence_path(repo, raw):
    """Resolve one canonical repository-relative evidence path, fail closed."""
    if not isinstance(raw, str) or not raw.strip() or raw != raw.strip():
        return None
    relative = Path(raw)
    if relative.is_absolute() or relative.as_posix() != raw or ".." in relative.parts:
        return None
    resolved = (repo / relative).resolve()
    return resolved if _is_within(resolved, repo) else None


def final_review_findings(
    asset,
    payload,
    *,
    repo=ROOT,
    actual_hash=None,
    media_type=None,
    origin_policy=None,
    now=None,
):
    """Validate exact visual/human review evidence without a fresh video scan.

    This validates repository evidence and a declared allow-listed origin, but
    does not authenticate a reviewer or independently prove media provenance.
    """
    repo = Path(repo).resolve()
    asset = Path(asset).resolve()
    payload = payload if isinstance(payload, dict) else {}
    findings = []
    current = _review_clock(now)
    if current is None:
        findings.append("media review clock is invalid or lacks a timezone")

    if not _is_within(asset, repo):
        findings.append("asset is outside the repository")
        return findings
    rel_asset = asset.relative_to(repo).as_posix()
    if not any(_is_within(asset, repo / root) for root in APPROVED_ROOTS):
        findings.append("asset is not under an approved canonical media root")
    if asset.is_symlink():
        findings.append("symlink assets are not publishable")
    if not asset.is_file():
        findings.append("asset is missing or not a regular file")
    expected_hash = _exact_sha256(actual_hash) if actual_hash is not None else None
    current_hash = _sha256(asset) if asset.is_file() else None
    if actual_hash is not None and expected_hash is None:
        findings.append("expected asset SHA-256 is malformed")
    elif expected_hash is not None and current_hash != expected_hash:
        findings.append("expected asset SHA-256 does not match current asset bytes")
    actual_hash = current_hash
    suffix = asset.suffix.casefold()
    inferred_type = (
        "video" if suffix in VIDEO_EXTENSIONS
        else "image" if suffix in IMAGE_EXTENSIONS
        else "unknown"
    )
    media_type = media_type or inferred_type
    if inferred_type == "unknown" or media_type != inferred_type:
        findings.append("unsupported media extension or media_type mismatch")
    if payload.get("asset") != rel_asset:
        findings.append("QA receipt is bound to a different asset path")
    if actual_hash is None or _exact_sha256(payload.get("sha256")) != actual_hash:
        findings.append("QA receipt SHA-256 does not match current asset bytes")
    if payload.get("media_type") != media_type:
        findings.append("QA receipt media_type does not match asset")

    if origin_policy is None:
        origin_policy = _load_json(repo / GENERATIVE_MEDIA_POLICY)
    if origin_policy is None:
        findings.append("generative media policy is missing or unreadable")
    else:
        findings.extend(generative_media_origin_gate.policy_problems(origin_policy))
        findings.extend(generative_media_origin_gate.origin_problems(
            origin_policy,
            payload.get("media_origin"),
            label="QA receipt declared origin",
        ))

    watermark = payload.get("watermark") if isinstance(payload.get("watermark"), dict) else {}
    visual = watermark.get("visual_review") if isinstance(watermark.get("visual_review"), dict) else {}
    if visual.get("status") != "PASS":
        findings.append("visual watermark review is not PASS")
    if not str(visual.get("reviewer", "")).strip():
        findings.append("visual watermark reviewer is missing")
    evidence = visual.get("evidence") if isinstance(visual.get("evidence"), list) else []
    if not evidence:
        findings.append("visual watermark evidence is missing")
    if len(evidence) != len(set(str(item) for item in evidence)):
        findings.append("visual watermark evidence paths are duplicated")

    declared_hashes = visual.get("evidence_sha256")
    if declared_hashes is None:
        source_binding = payload.get("source_binding")
        declared_hashes = (
            source_binding.get("scene_evidence_sha256")
            if isinstance(source_binding, dict) else None
        )
    # A one-file still-image review may use the exact final asset itself. Its
    # top-level asset binding is already the explicit receipt hash declaration.
    if (
        declared_hashes is None
        and media_type == "image"
        and evidence == [rel_asset]
        and actual_hash is not None
    ):
        declared_hashes = {rel_asset: payload.get("sha256")}
    if not isinstance(declared_hashes, dict) or not declared_hashes:
        findings.append("visual evidence SHA-256 bindings are missing")
        declared_hashes = {}
    evidence_strings = [item for item in evidence if isinstance(item, str)]
    if set(declared_hashes) != set(evidence_strings) or len(evidence_strings) != len(evidence):
        findings.append("visual evidence path set does not exactly match SHA-256 bindings")
    for raw in evidence_strings:
        evidence_path = _evidence_path(repo, raw)
        if evidence_path is None or evidence_path.is_symlink() or not evidence_path.is_file():
            findings.append("visual evidence is missing, unsafe, or outside the repository: %s" % raw)
            continue
        declared_hash = _exact_sha256(declared_hashes.get(raw))
        if declared_hash is None:
            findings.append("visual evidence SHA-256 is missing or malformed: %s" % raw)
        elif _sha256(evidence_path) != declared_hash:
            findings.append("visual evidence SHA-256 does not match current bytes: %s" % raw)

    if media_type == "video":
        human = payload.get("human_audio_review")
        if not isinstance(human, dict):
            findings.append("human audio review is missing")
        else:
            if human.get("status") != "PASS":
                findings.append("human audio review is not PASS")
            if human.get("reviewer_is_human") is not True:
                findings.append("human audio review must explicitly assert reviewer_is_human=true")
            if str(human.get("reviewer_type") or "").strip().upper() not in HUMAN_REVIEWER_TYPES:
                findings.append("human audio reviewer_type must be HUMAN or OWNER")
            if not str(human.get("reviewer") or "").strip():
                findings.append("human audio reviewer is missing")
            if _exact_sha256(human.get("asset_sha256")) != actual_hash:
                findings.append("human audio review is not bound to the exact asset SHA-256")
            human_reviewed_at = _aware_timestamp(human.get("reviewed_at"))
            if human_reviewed_at is None:
                findings.append("human audio reviewed_at is missing, invalid, or lacks a timezone")
            elif (
                current is not None
                and human_reviewed_at > current + MAX_REVIEW_FUTURE_SKEW
            ):
                findings.append(
                    "human audio reviewed_at is in the future beyond allowed clock skew"
                )

    return findings


def publication_corpus_fingerprint(repo=ROOT):
    """Fingerprint the exact manifest/legacy-media corpus used for novelty review."""
    try:
        documents, _records = _validated_publication_corpus(repo)
    except (OSError, ValueError):
        return None
    return _corpus_fingerprint(documents)


def _prior_media(repo):
    """Yield (content_id, absolute_path) from manifest and legacy image registry."""
    _documents, records = _validated_publication_corpus(repo)
    for _source, content_id, path, _actual_hash in records:
        yield content_id, path


def _exact_duplicate_finding(prior_media, asset, content_id, actual_hash):
    """Return the canonical duplicate finding for one validated corpus snapshot."""
    if actual_hash is None:
        return None
    for source, prior_id, prior_path, prior_hash in prior_media:
        # The manifest is also the current production inventory. Only its exact
        # id/path pair represents this candidate rather than publication history.
        if (
            source == "content manifest"
            and prior_path == asset
            and content_id == prior_id
        ):
            continue
        if prior_hash == actual_hash:
            return "exact media duplicate of prior content %s" % (
                prior_id or prior_path.name
            )
    return None


def _default_video_scan(path, fps):
    scanner_path = ROOT / "tiktok-pipeline" / "src" / "qa_watermark.py"
    spec = importlib.util.spec_from_file_location("publish_qa_watermark", scanner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("watermark scanner cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scan(str(path), fps=fps)


def evaluate(asset, report, *, repo=ROOT, scanner=None, now=None):
    """Return a structured PASS/FAIL verdict without mutating either input."""
    repo = Path(repo).resolve()
    asset = Path(asset)
    report = Path(report)
    asset = (repo / asset).resolve() if not asset.is_absolute() else asset.resolve()
    report = (repo / report).resolve() if not report.is_absolute() else report.resolve()
    findings = []
    current = _review_clock(now)
    if current is None:
        findings.append("media review clock is invalid or lacks a timezone")

    if not _is_within(asset, repo):
        findings.append("asset is outside the repository")

    expected_report_root = (repo / REPORT_ROOT).resolve()
    if not _is_within(report, expected_report_root):
        findings.append("QA receipt is outside automation-log/media-qa")
    payload = _load_json(report)
    if payload is None:
        findings.append("QA receipt is missing or unreadable")
        payload = {}

    suffix = asset.suffix.casefold()
    if suffix in VIDEO_EXTENSIONS:
        media_type = "video"
    elif suffix in IMAGE_EXTENSIONS:
        media_type = "image"
    else:
        media_type = "unknown"
        findings.append("unsupported media extension")

    actual_hash = _sha256(asset) if asset.is_file() else None
    if payload.get("schema_version") != 1:
        findings.append("unsupported or missing QA receipt schema_version")
    origin_policy = _load_json(repo / GENERATIVE_MEDIA_POLICY)
    findings.extend(final_review_findings(
        asset,
        payload,
        repo=repo,
        actual_hash=actual_hash,
        media_type=media_type,
        origin_policy=origin_policy,
        now=current,
    ))

    novelty = payload.get("novelty_review") if isinstance(payload.get("novelty_review"), dict) else {}
    content_id = str(novelty.get("content_id", "")).strip()
    if novelty.get("status") != "PASS":
        findings.append("creative novelty review is not PASS")
    if not content_id:
        findings.append("creative novelty content_id is missing")
    if not str(novelty.get("reviewer", "")).strip():
        findings.append("creative novelty reviewer is missing")
    try:
        corpus_documents, prior_media = _validated_publication_corpus(repo)
        corpus_fingerprint = _corpus_fingerprint(corpus_documents)
    except (OSError, ValueError):
        corpus_fingerprint = None
        prior_media = ()
    if corpus_fingerprint is None:
        findings.append("publication comparison corpus is missing or unreadable")
    elif str(novelty.get("corpus_fingerprint", "")).upper() != corpus_fingerprint:
        findings.append("creative novelty review is stale for the current publication corpus")
    if corpus_fingerprint is not None:
        duplicate_finding = _exact_duplicate_finding(
            prior_media, asset, content_id, actual_hash
        )
        if duplicate_finding:
            findings.append(duplicate_finding)

    reviewed_at = _aware_timestamp(payload.get("reviewed_at"))
    if reviewed_at is None:
        findings.append("reviewed_at is missing, invalid, or lacks a timezone")
    elif current is not None and reviewed_at > current + MAX_REVIEW_FUTURE_SKEW:
        findings.append("reviewed_at is in the future beyond allowed clock skew")

    scan_result = None
    scan_diagnostics = []
    if media_type == "video":
        watermark = payload.get("watermark") if isinstance(payload.get("watermark"), dict) else {}
        automated = (watermark.get("automated_scan")
                     if isinstance(watermark.get("automated_scan"), dict) else {})
        if automated.get("status") != "PASS":
            findings.append("recorded automated watermark scan is not PASS")
        try:
            fps = float(automated.get("fps", 3.0))
            if fps < 1.0 or fps > 5.0:
                raise ValueError("fps outside review range")
        except (TypeError, ValueError):
            fps = 3.0
            findings.append("automated scan fps is invalid")
        scan_safe = (
            asset.is_file()
            and not asset.is_symlink()
            and _is_within(asset, repo)
            and any(
                _is_within(asset, (repo / root).resolve())
                for root in APPROVED_ROOTS
            )
        )
        if scan_safe:
            findings_before_scan = bool(findings)
            try:
                scan_result = (scanner or _default_video_scan)(asset, fps)
                if not isinstance(scan_result, dict) or scan_result.get("verdict") != "PASS":
                    target = scan_diagnostics if findings_before_scan else findings
                    target.append("fresh automated watermark scan did not PASS")
            except Exception as exc:
                target = scan_diagnostics if findings_before_scan else findings
                target.append("fresh automated watermark scan unavailable: %s" % str(exc)[:120])
            try:
                post_scan_hash = _sha256(asset) if asset.is_file() else None
            except OSError:
                post_scan_hash = None
            if post_scan_hash != actual_hash:
                findings.append("asset bytes changed during fresh watermark scan")

    corpus_binding = None
    if (
        corpus_fingerprint is not None
        and actual_hash is not None
        and content_id
        and _is_within(asset, repo)
    ):
        corpus_binding = {
            "schema_version": 1,
            "corpus_fingerprint": corpus_fingerprint,
            "content_id": content_id,
            "asset": asset.relative_to(repo).as_posix(),
            "asset_sha256": actual_hash,
        }

    return {
        "verdict": "PASS" if not findings else "FAIL",
        "asset": str(asset),
        "sha256": actual_hash,
        "media_type": media_type,
        "corpus_binding": corpus_binding,
        "findings": findings,
        "diagnostic_findings": scan_diagnostics,
        "fresh_scan": scan_result,
        "origin_attestation": (
            "DECLARED_ALLOWED_NOT_INDEPENDENTLY_VERIFIED"
            if origin_policy is not None and not generative_media_origin_gate.origin_problems(
                origin_policy,
                payload.get("media_origin"),
                label="QA receipt declared origin",
            )
            else "BLOCKED_OR_UNKNOWN"
        ),
        "publication_authority_granted": False,
    }


def _validated_corpus_binding(value):
    if (
        not isinstance(value, dict)
        or set(value) != CORPUS_BINDING_FIELDS
        or value.get("schema_version") != 1
    ):
        raise MediaPublicationBlocked(
            "media publication corpus binding is missing or not exact"
        )
    fingerprint = _exact_sha256(value.get("corpus_fingerprint"))
    asset_hash = _exact_sha256(value.get("asset_sha256"))
    try:
        content_id = _corpus_identity(
            value.get("content_id"), "media publication corpus binding"
        )
    except ValueError as exc:
        raise MediaPublicationBlocked(str(exc)) from exc
    raw_asset = value.get("asset")
    if (
        not isinstance(raw_asset, str)
        or not raw_asset
        or raw_asset != raw_asset.strip()
        or Path(raw_asset).is_absolute()
        or Path(raw_asset).as_posix() != raw_asset
        or any(part in {"", ".", ".."} for part in Path(raw_asset).parts)
    ):
        raise MediaPublicationBlocked(
            "media publication corpus binding asset path is non-canonical"
        )
    if fingerprint is None or asset_hash is None:
        raise MediaPublicationBlocked(
            "media publication corpus binding hash is missing or malformed"
        )
    return {
        "schema_version": 1,
        "corpus_fingerprint": fingerprint,
        "content_id": content_id,
        "asset": raw_asset,
        "asset_sha256": asset_hash,
    }


@contextmanager
def _exclusive_corpus_claim_lock(repo):
    """Hold the shared local corpus lock through one remote mutation boundary."""
    repo = Path(repo).resolve()
    lock_path = repo / CORPUS_CLAIM_LOCK
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        _assert_no_link_components(
            repo, CORPUS_CLAIM_LOCK.parent, "media publication corpus lock"
        )
        if _path_is_linklike(lock_path):
            raise MediaPublicationBlocked(
                "media publication corpus lock must not be a symlink or junction"
            )
        handle = lock_path.open("a+b", buffering=0)
    except MediaPublicationBlocked:
        raise
    except OSError as exc:
        raise MediaPublicationBlocked(
            "media publication corpus lock is unavailable"
        ) from exc

    acquired = False
    try:
        if lock_path.stat().st_size == 0:
            handle.write(b"\0")
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(
                    handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                )
        except (OSError, BlockingIOError) as exc:
            raise MediaPublicationBlocked(
                "another media publication corpus claim is active"
            ) from exc
        acquired = True
        yield
    finally:
        if acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                # Closing the process-owned handle still releases the OS lock.
                pass
        handle.close()


@contextmanager
def publication_corpus_claim(
    asset,
    report,
    *,
    expected_asset_sha256,
    expected_content_id,
    repo=ROOT,
    scanner=None,
    now=None,
):
    """Revalidate and hold the exact novelty corpus at a mutation boundary.

    The QA receipt is already hash-bound by ``publication_authority``. This
    boundary additionally proves that its reviewed corpus generation is still
    current, while the shared OS lock prevents another cooperating publisher or
    corpus writer from advancing that generation until the remote call returns.
    """
    repo = Path(repo).resolve()
    expected_hash = _exact_sha256(expected_asset_sha256)
    if expected_hash is None:
        raise MediaPublicationBlocked(
            "media publication corpus claim expected asset SHA-256 is malformed"
        )
    try:
        expected_id = _corpus_identity(
            expected_content_id, "media publication corpus claim"
        )
    except ValueError as exc:
        raise MediaPublicationBlocked(str(exc)) from exc

    selected_asset = Path(asset)
    selected_asset = (
        (repo / selected_asset).resolve()
        if not selected_asset.is_absolute()
        else selected_asset.resolve()
    )
    with _exclusive_corpus_claim_lock(repo):
        try:
            result = evaluate(
                selected_asset,
                report,
                repo=repo,
                scanner=scanner,
                now=now,
            )
        except Exception as exc:
            raise MediaPublicationBlocked(
                "media publication corpus boundary recheck is unavailable"
            ) from exc
        if not isinstance(result, dict) or result.get("verdict") != "PASS":
            findings = result.get("findings") if isinstance(result, dict) else None
            detail = (
                "; ".join(str(item) for item in findings[:3])
                if isinstance(findings, list) and findings
                else "no PASS verdict"
            )
            raise MediaPublicationBlocked(
                "media publication corpus boundary blocked: " + detail
            )
        binding = _validated_corpus_binding(result.get("corpus_binding"))
        try:
            expected_asset = selected_asset.relative_to(repo).as_posix()
        except ValueError as exc:
            raise MediaPublicationBlocked(
                "media publication corpus claim asset is outside the repository"
            ) from exc
        if (
            binding["content_id"] != expected_id
            or binding["asset"] != expected_asset
            or binding["asset_sha256"] != expected_hash
        ):
            raise MediaPublicationBlocked(
                "media publication corpus claim does not match the authorized action"
            )

        # Re-read after the complete guard. This closes a mutation scheduled
        # after evaluate() took its snapshot; the surrounding lock then remains
        # held across the caller's remote mutation rather than merely narrowing
        # the race with one final comparison.
        try:
            documents, records = _validated_publication_corpus(repo)
            current_fingerprint = _corpus_fingerprint(documents)
            current_asset_hash = _sha256(selected_asset)
        except (OSError, ValueError) as exc:
            raise MediaPublicationBlocked(
                "media publication corpus changed or became unreadable at the boundary"
            ) from exc
        if current_fingerprint != binding["corpus_fingerprint"]:
            raise MediaPublicationBlocked(
                "media publication corpus generation changed at the mutation boundary"
            )
        if current_asset_hash != expected_hash:
            raise MediaPublicationBlocked(
                "media publication asset changed at the mutation boundary"
            )
        duplicate_finding = _exact_duplicate_finding(
            records, selected_asset, expected_id, current_asset_hash
        )
        if duplicate_finding:
            raise MediaPublicationBlocked(duplicate_finding)
        yield result


def main(argv=None):
    parser = argparse.ArgumentParser(description="fail-closed social media publication guard")
    parser.add_argument("asset")
    parser.add_argument("--report", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(args.asset, args.report)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["verdict"], result["asset"])
        for finding in result["findings"]:
            print("- " + finding)
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
