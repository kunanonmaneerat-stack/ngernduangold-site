#!/usr/bin/env python3
"""Verify exact owner-signed, content-scoped source-review receipts.

This module is intentionally verifier-only.  It contains no key generation,
signing, receipt-writing, or global source-queue acknowledgement path.  The
owner public key is supplied out of band through
``NGERNDUANGOLD_OWNER_SOURCE_REVIEW_ED25519_PUBKEY_B64``; the corresponding
private key must never enter this repository or its runtime environment.

A valid ``UNCHANGED`` receipt binds one content ID to the current registry
binding and to the stable evidence fields of its exact official-source rows.
Fetch timestamps and the monitor's transient ``change`` marker are deliberately
excluded from the stable source hash, while freshness, errors, and manual
evidence remain independent publication gates.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Mapping


RECEIPT_SCHEMA_VERSION = 1
RECEIPT_KIND = "OWNER_CONTENT_SOURCE_REVIEW"
SIGNATURE_ALGORITHM = "ed25519"
PUBLIC_KEY_ENV = "NGERNDUANGOLD_OWNER_SOURCE_REVIEW_ED25519_PUBKEY_B64"
ACCEPTED_VERDICT = "UNCHANGED"
MAX_RECEIPT_BYTES = 65536
KNOWN_VERDICTS = frozenset({"UNCHANGED", "UPDATE_REQUIRED", "BLOCK"})
CONTENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
RECEIPT_FIELDS = frozenset({
    "schema_version",
    "receipt_kind",
    "content_id",
    "verdict",
    "reviewed_at",
    "registry_binding_sha256",
    "source_ids",
    "source_state_sha256",
    "nonce",
    "owner_key_sha256",
    "signature_algorithm",
    "signature_b64",
})
SIGNED_FIELDS = RECEIPT_FIELDS - {"signature_b64"}
SOURCE_STATE_FIELDS = (
    "id",
    "url",
    "final_url",
    "kind",
    "http_status",
    "content_type",
    "bytes",
    "fingerprint_method",
    "raw_sha256",
    "sha256",
)


class ReceiptBlocked(RuntimeError):
    """Raised internally when receipt evidence cannot be trusted."""


@dataclass(frozen=True)
class SourceReviewReceiptResult:
    accepted: bool
    found: bool
    receipt_id: str | None
    receipt_sha256: str | None
    path: str | None
    failures: tuple[str, ...]
    source_state_sha256: str | None


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except Exception as exc:
        raise ReceiptBlocked("source-review receipt is not canonical JSON") from exc


def canonical_signed_payload(receipt: object) -> bytes:
    """Return the exact bytes covered by an Ed25519 receipt signature.

    This serialization helper does not sign or write anything.  It accepts only
    the exact signed field set, optionally accompanied by ``signature_b64``.
    """
    if not isinstance(receipt, dict):
        raise ReceiptBlocked("source-review receipt must be a JSON object")
    keys = set(receipt)
    if keys not in (set(SIGNED_FIELDS), set(RECEIPT_FIELDS)):
        raise ReceiptBlocked("source-review receipt signed fields are not exact")
    return _canonical_json({key: receipt[key] for key in SIGNED_FIELDS})


def _strict_json_loads(raw: bytes) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def require_finite(value: object) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        if isinstance(value, dict):
            for child in value.values():
                require_finite(child)
        elif isinstance(value, list):
            for child in value:
                require_finite(child)

    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
        require_finite(value)
        return value
    except Exception as exc:
        raise ReceiptBlocked("source-review receipt is unreadable or invalid JSON") from exc


def _strict_ids(source_ids: object) -> list[str]:
    if (
        not isinstance(source_ids, (list, tuple))
        or not source_ids
        or any(not isinstance(value, str) or not value.strip() for value in source_ids)
    ):
        raise ReceiptBlocked("source-review source IDs are missing or malformed")
    normalized = [value.strip() for value in source_ids]
    if len(normalized) != len(set(normalized)):
        raise ReceiptBlocked("source-review source IDs contain duplicates")
    if normalized != sorted(normalized):
        raise ReceiptBlocked("source-review source IDs must use canonical sorted order")
    return normalized


def source_state_sha256(source_rows: object, source_ids: object) -> str:
    """Hash the stable evidence fields for the exact selected source IDs."""
    required = _strict_ids(source_ids)
    if not isinstance(source_rows, list) or not source_rows:
        raise ReceiptBlocked("official source rows are missing or malformed")

    by_id: dict[str, dict] = {}
    for row in source_rows:
        if not isinstance(row, dict):
            raise ReceiptBlocked("official source row is malformed")
        source_id = row.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ReceiptBlocked("official source row has no source ID")
        normalized_id = source_id.strip()
        if normalized_id in by_id:
            raise ReceiptBlocked("official source rows contain duplicate source IDs")
        by_id[normalized_id] = row

    selected = []
    for source_id in required:
        row = by_id.get(source_id)
        if row is None:
            raise ReceiptBlocked("required official source row is missing: " + source_id)
        stable: dict[str, object] = {}
        for field in SOURCE_STATE_FIELDS:
            if field not in row:
                raise ReceiptBlocked(
                    "official source row stable evidence is incomplete: " + source_id
                )
            stable[field] = row[field]
        if stable["id"] != source_id:
            raise ReceiptBlocked("official source row ID is not canonical: " + source_id)
        for field in (
            "url", "final_url", "kind", "content_type", "fingerprint_method"
        ):
            if not isinstance(stable[field], str):
                raise ReceiptBlocked(
                    "official source row stable evidence is malformed: " + source_id
                )
        for field in ("http_status", "bytes"):
            if not isinstance(stable[field], int) or isinstance(stable[field], bool):
                raise ReceiptBlocked(
                    "official source row stable evidence is malformed: " + source_id
                )
        for field in ("raw_sha256", "sha256"):
            if (
                not isinstance(stable[field], str)
                or SHA256_PATTERN.fullmatch(stable[field]) is None
            ):
                raise ReceiptBlocked(
                    "official source row stable fingerprints are malformed: " + source_id
                )
        selected.append(stable)
    return hashlib.sha256(_canonical_json(selected)).hexdigest()


def _repo_root(repo: Path | str) -> Path:
    try:
        root = Path(repo).resolve(strict=True)
    except OSError as exc:
        raise ReceiptBlocked("source-review repository root is missing or unreadable") from exc
    if not root.is_dir():
        raise ReceiptBlocked("source-review repository root is not a directory")
    return root


def expected_receipt_path(
    repo: Path | str,
    content_id: object,
    registry_binding_sha256: object,
    expected_source_state_sha256: object,
) -> Path:
    """Resolve the only accepted local path for one exact receipt binding."""
    if (
        not isinstance(content_id, str)
        or CONTENT_ID_PATTERN.fullmatch(content_id) is None
    ):
        raise ReceiptBlocked("source-review content ID is not path-safe")
    for value, label in (
        (registry_binding_sha256, "registry binding SHA-256"),
        (expected_source_state_sha256, "source-state SHA-256"),
    ):
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            raise ReceiptBlocked("source-review " + label + " is malformed")
    root = _repo_root(repo)
    receipt_root = root / ".local-private" / "runtime" / "source-review-receipts" / "accepted"
    path = receipt_root / content_id / (
        registry_binding_sha256 + "-" + expected_source_state_sha256 + ".json"
    )
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ReceiptBlocked("source-review receipt path escaped its repository") from exc
    return path


def _existing_components_have_no_symlink(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ReceiptBlocked("source-review receipt path escaped its repository") from exc
    current = root
    for component in relative.parts:
        current = current / component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ReceiptBlocked("source-review receipt path is unreadable") from exc
        windows_reparse = (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        if stat.S_ISLNK(metadata.st_mode) or windows_reparse:
            raise ReceiptBlocked("source-review receipt path must not contain symlinks")


def _file_stamp(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
    )


def _read_stable_regular_file(root: Path, path: Path) -> tuple[bytes, tuple[int, int, int, int]]:
    _existing_components_have_no_symlink(root, path)
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ReceiptBlocked("source-review receipt is missing") from exc
    except OSError as exc:
        raise ReceiptBlocked("source-review receipt is unreadable") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ReceiptBlocked("source-review receipt must be a regular file")
    if before.st_size > MAX_RECEIPT_BYTES:
        raise ReceiptBlocked("source-review receipt exceeds the maximum size")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReceiptBlocked("source-review receipt cannot be opened safely") from exc
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or _file_stamp(opened) != _file_stamp(before):
                raise ReceiptBlocked("source-review receipt changed before it was opened")
            raw = handle.read(MAX_RECEIPT_BYTES + 1)
            if len(raw) > MAX_RECEIPT_BYTES:
                raise ReceiptBlocked("source-review receipt exceeds the maximum size")
            after_read = os.fstat(handle.fileno())
            if _file_stamp(after_read) != _file_stamp(opened):
                raise ReceiptBlocked("source-review receipt changed while it was read")
    except ReceiptBlocked:
        raise
    except OSError as exc:
        raise ReceiptBlocked("source-review receipt cannot be read safely") from exc

    _existing_components_have_no_symlink(root, path)
    try:
        after_path = path.lstat()
    except OSError as exc:
        raise ReceiptBlocked("source-review receipt disappeared while it was read") from exc
    if _file_stamp(after_path) != _file_stamp(before):
        raise ReceiptBlocked("source-review receipt changed while it was read")
    return raw, _file_stamp(before)


def _strict_b64(value: object, *, label: str, expected_bytes: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise ReceiptBlocked(label + " is missing or malformed")
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ReceiptBlocked(label + " is missing or malformed") from exc
    if len(decoded) != expected_bytes:
        raise ReceiptBlocked(label + " has an invalid length")
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ReceiptBlocked(label + " is not canonical base64")
    return decoded


def _reviewed_at(value: object, current: datetime) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReceiptBlocked("source-review receipt reviewed_at is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptBlocked("source-review receipt reviewed_at is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReceiptBlocked("source-review receipt reviewed_at must include a timezone")
    if parsed.astimezone(timezone.utc) > current.astimezone(timezone.utc):
        raise ReceiptBlocked("source-review receipt reviewed_at is in the future")
    return parsed


def _failure_result(
    *,
    found: bool,
    path: Path | None,
    failure: str,
    source_hash: str | None,
    receipt_id: str | None = None,
    receipt_sha256: str | None = None,
) -> SourceReviewReceiptResult:
    return SourceReviewReceiptResult(
        False,
        found,
        receipt_id,
        receipt_sha256,
        str(path) if path is not None else None,
        (failure,),
        source_hash,
    )


def verify_content_source_review_receipt(
    *,
    repo: Path | str,
    content_id: object,
    registry_binding_sha256: object,
    source_ids: object,
    source_rows: object,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> SourceReviewReceiptResult:
    """Verify one exact owner receipt without mutating any local or global state."""
    current = now or datetime.now(timezone.utc)
    if (
        not isinstance(current, datetime)
        or current.tzinfo is None
        or current.utcoffset() is None
    ):
        return _failure_result(
            found=False,
            path=None,
            failure="source-review verification time must include a timezone",
            source_hash=None,
        )

    try:
        normalized_ids = _strict_ids(source_ids)
        source_hash = source_state_sha256(source_rows, normalized_ids)
        path = expected_receipt_path(
            repo, content_id, registry_binding_sha256, source_hash
        )
        root = _repo_root(repo)
    except ReceiptBlocked as exc:
        return _failure_result(
            found=False, path=None, failure=str(exc), source_hash=None
        )

    try:
        raw, first_stamp = _read_stable_regular_file(root, path)
    except ReceiptBlocked as exc:
        is_missing = str(exc) == "source-review receipt is missing"
        return _failure_result(
            found=not is_missing,
            path=path,
            failure=str(exc),
            source_hash=source_hash,
        )
    raw_sha256 = hashlib.sha256(raw).hexdigest()

    try:
        receipt = _strict_json_loads(raw)
        if not isinstance(receipt, dict):
            raise ReceiptBlocked("source-review receipt must be a JSON object")
        if set(receipt) != set(RECEIPT_FIELDS):
            missing = sorted(RECEIPT_FIELDS - set(receipt))
            extra = sorted(set(receipt) - RECEIPT_FIELDS)
            detail = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if extra:
                detail.append("extra=" + ",".join(extra))
            raise ReceiptBlocked(
                "source-review receipt fields are not exact (" + "; ".join(detail) + ")"
            )
        if (
            not isinstance(receipt.get("schema_version"), int)
            or isinstance(receipt.get("schema_version"), bool)
            or receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION
        ):
            raise ReceiptBlocked("source-review receipt schema_version is unsupported")
        if receipt.get("receipt_kind") != RECEIPT_KIND:
            raise ReceiptBlocked("source-review receipt kind is unsupported")
        if receipt.get("content_id") != content_id:
            raise ReceiptBlocked("source-review receipt content ID does not match")
        verdict = receipt.get("verdict")
        if verdict not in KNOWN_VERDICTS:
            raise ReceiptBlocked("source-review receipt verdict is unsupported")
        _reviewed_at(receipt.get("reviewed_at"), current)
        if receipt.get("registry_binding_sha256") != registry_binding_sha256:
            raise ReceiptBlocked("source-review receipt registry binding does not match")
        if not isinstance(receipt.get("source_ids"), list):
            raise ReceiptBlocked("source-review receipt source IDs must be a JSON list")
        receipt_ids = _strict_ids(receipt.get("source_ids"))
        if receipt_ids != normalized_ids:
            raise ReceiptBlocked("source-review receipt source IDs do not exactly match")
        if receipt.get("source_state_sha256") != source_hash:
            raise ReceiptBlocked("source-review receipt source state does not match")
        nonce = receipt.get("nonce")
        if not isinstance(nonce, str) or NONCE_PATTERN.fullmatch(nonce) is None:
            raise ReceiptBlocked(
                "source-review receipt nonce must be 32-128 URL-safe characters"
            )
        if receipt.get("signature_algorithm") != SIGNATURE_ALGORITHM:
            raise ReceiptBlocked("source-review receipt signature algorithm is unsupported")

        selected_environ = os.environ if environ is None else environ
        public_key_raw = _strict_b64(
            selected_environ.get(PUBLIC_KEY_ENV),
            label="source-review owner Ed25519 public key",
            expected_bytes=32,
        )
        owner_key_sha256 = hashlib.sha256(public_key_raw).hexdigest()
        if receipt.get("owner_key_sha256") != owner_key_sha256:
            raise ReceiptBlocked("source-review receipt owner key fingerprint does not match")
        signature = _strict_b64(
            receipt.get("signature_b64"),
            label="source-review receipt Ed25519 signature",
            expected_bytes=64,
        )
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError as exc:
            raise ReceiptBlocked("source-review Ed25519 verifier dependency is unavailable") from exc
        try:
            Ed25519PublicKey.from_public_bytes(public_key_raw).verify(
                signature, canonical_signed_payload(receipt)
            )
        except InvalidSignature as exc:
            raise ReceiptBlocked("source-review receipt Ed25519 signature is invalid") from exc
        except ValueError as exc:
            raise ReceiptBlocked("source-review owner Ed25519 public key is invalid") from exc

        second_raw, second_stamp = _read_stable_regular_file(root, path)
        if second_raw != raw or second_stamp != first_stamp:
            raise ReceiptBlocked("source-review receipt changed during verification")
        if verdict != ACCEPTED_VERDICT:
            raise ReceiptBlocked(
                "source-review receipt verdict requires owner update: " + str(verdict)
            )
    except ReceiptBlocked as exc:
        receipt_id = None
        if isinstance(locals().get("receipt"), dict):
            candidate = receipt.get("nonce")
            if isinstance(candidate, str) and NONCE_PATTERN.fullmatch(candidate):
                receipt_id = candidate
        return _failure_result(
            found=True,
            path=path,
            failure=str(exc),
            source_hash=source_hash,
            receipt_id=receipt_id,
            receipt_sha256=raw_sha256,
        )

    return SourceReviewReceiptResult(
        True,
        True,
        receipt["nonce"],
        raw_sha256,
        str(path),
        (),
        source_hash,
    )


__all__ = (
    "PUBLIC_KEY_ENV",
    "ReceiptBlocked",
    "SourceReviewReceiptResult",
    "canonical_signed_payload",
    "expected_receipt_path",
    "source_state_sha256",
    "verify_content_source_review_receipt",
)
