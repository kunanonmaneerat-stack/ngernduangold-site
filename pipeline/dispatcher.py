"""Local-only semantic-family reservation and draft-fulfilment queue.

This is an auditable request state machine, not a rotating topic list:

* an active family is first RESERVED;
* a hash-chained REVIEW_REFRESHED transition can replace a stale provisional
  review without changing the reserved family/request identity;
* the same outstanding request is reissued or referenced until an exact,
  hash-bound local draft fulfilment receipt exists;
* mechanical draft evidence ends at DRAFTED_BLOCKED; legacy mechanical-only
  CONSUMED rows gain a hash-anchored LEGACY_CONSUMPTION_RECLASSIFIED cutover.

The ledger is hash chained and guarded by an independently persisted checkpoint
plus an explicit activation sentinel. Scheduled runs never create a missing
state implicitly. This module has no network, model, notification, publication,
deployment, or scheduler mutation path.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import types
import unicodedata

import content_pack_audit

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - production host is Windows
    import fcntl

try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ORDERS = ROOT / "automation-log" / "orders.txt"
DEFAULT_INBOX = ROOT / "automation-log" / "cowork-inbox"
DEFAULT_LEDGER = (
    ROOT / ".local-private" / "runtime" / "content-novelty"
    / "topic-lifecycle-ledger.jsonl"
)
ORDERS = str(DEFAULT_ORDERS)
INBOX = str(DEFAULT_INBOX)

SCHEMA_VERSION = 2
STATE_SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64
FAMILY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
REQUEST_ID_RE = re.compile(r"^(dispatcher|daily):(\d{4}-\d{2}-\d{2})$")
HISTORICAL_REQUEST_ID = "historical-orders-bootstrap-v2"
HISTORICAL_PREFIX = "# HISTORICAL_CONSUMED\t"
LOCK_TIMEOUT_SECONDS = 2.0
CORPUS_REVIEW_RECEIPT_TYPE = "PROVISIONAL_LOCAL_CORPUS_REVIEW"
FULFILMENT_RECEIPT_TYPE = "LOCAL_DRAFT_FULFILMENT"
CORPUS_REVIEW_SCHEMA_VERSION = 2
FULFILMENT_SCHEMA_VERSION = 2
CORPUS_REVIEW_PRODUCER = "ngernduangold.local-deterministic-corpus-audit"
CORPUS_REVIEW_METHOD = "normalized-exact-near-sequence-trigram-v2"
FULFILMENT_PRODUCER = "ngernduangold.local-draft-fulfilment"
STRICT_REVALIDATION_SCHEMA_VERSION = 2
STRICT_REVALIDATION_RECEIPT_TYPE = "LEGACY_DRAFT_FULFILMENT_STRICT_REVALIDATION"
STRICT_REVALIDATION_PRODUCER = "ngernduangold.local-deterministic-content-pack-audit"
AUDIT_ENGINE_RELATIVE = "pipeline/content_pack_audit.py"
EXPECTED_AUDIT_ENGINE_VERSION = "content-pack-audit-v2"
STRICT_REVALIDATION_RELATIVE = (
    "automation-log/dedup-evidence/"
    "LOCAL-CONTENT-PACK_20260825_V2-STRICT-REVALIDATION.json"
)
STRICT_REVALIDATION = (
    ROOT / "automation-log" / "dedup-evidence"
    / "LOCAL-CONTENT-PACK_20260825_V2-STRICT-REVALIDATION.json"
)
REVALIDATION_EVENT_KEYS = {
    "revalidation_receipt", "revalidation_sha256", "snapshot_manifest_sha256",
}


class NoveltyError(RuntimeError):
    """Base class for fail-closed novelty state errors."""


class NoveltyIntegrityError(NoveltyError):
    """Registry, ledger, checkpoint, request, or receipt cannot be trusted."""


class NoveltyLockError(NoveltyError):
    """The crash-releasing OS lock was not acquired within the bounded wait."""


class NoveltyStateUninitialized(NoveltyError):
    """The explicit activation sentinel/checkpoint has not been bootstrapped."""


def _strict_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: " + str(key))
        out[key] = value
    return out


def _reject_json_constant(value):
    raise ValueError("non-finite JSON: " + value)


def _canonical_json(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _audit_engine_path() -> Path:
    path = (ROOT / AUDIT_ENGINE_RELATIVE).resolve()
    pipeline_root = (ROOT / "pipeline").resolve()
    try:
        pipeline_root.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise NoveltyIntegrityError("audit-engine directory escapes repo root") from exc
    if path.parent != pipeline_root:
        raise NoveltyIntegrityError("audit-engine path escapes repo root")
    return path


def _load_bound_audit_engine(
    *, expected_sha256: str | None = None,
    label: str = "live content-pack audit engine",
) -> dict:
    """Compile and execute the exact pre-read, hash-bound source bytes.

    Python timestamp pyc validation can otherwise execute stale bytecode after
    a same-size/same-mtime source edit.  Admission deliberately does not call
    functions on the ordinarily imported module.
    """
    path = _audit_engine_path()
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise NoveltyIntegrityError(label + " is unreadable") from exc
    disk_sha = _sha256_bytes(payload)
    if expected_sha256 is not None and (
        not SHA256_RE.fullmatch(str(expected_sha256 or "").upper())
        or disk_sha != str(expected_sha256).upper()
    ):
        raise NoveltyIntegrityError(label + " receipt binding is mismatched")
    module = types.ModuleType("_ngernduangold_bound_content_pack_audit_" + disk_sha)
    module.__file__ = str(path)
    module.__package__ = ""
    try:
        code = compile(payload, str(path), "exec", dont_inherit=True)
        exec(code, module.__dict__)
    except Exception as exc:
        raise NoveltyIntegrityError(
            label + " exact source cannot be compiled/executed"
        ) from exc
    if (
        str(getattr(module, "AUDIT_ENGINE_VERSION", "") or "")
        != EXPECTED_AUDIT_ENGINE_VERSION
        or str(getattr(module, "AUDIT_ENGINE_SOURCE_SHA256", "") or "").upper()
        != disk_sha
        or "comply_gate" in module.__dict__
    ):
        raise NoveltyIntegrityError(
            label + " exact-source identity/dependency contract is invalid"
        )
    try:
        after_exec = path.read_bytes()
    except OSError as exc:
        raise NoveltyIntegrityError(label + " became unreadable during load") from exc
    if after_exec != payload:
        raise NoveltyIntegrityError(label + " changed during exact-source load")
    return {
        "bytes": payload,
        "sha256": disk_sha,
        "version": EXPECTED_AUDIT_ENGINE_VERSION,
        "module": module,
    }


def _recheck_bound_audit_engine(
    binding: dict, *, expected_sha256: str | None = None,
    label: str = "live content-pack audit engine",
) -> None:
    """Recheck the exact disk bytes immediately after a bound live audit."""
    if not isinstance(binding, dict) or set(binding) != {
        "bytes", "sha256", "version", "module",
    }:
        raise NoveltyIntegrityError(label + " runtime binding is invalid")
    if (
        binding.get("version") != EXPECTED_AUDIT_ENGINE_VERSION
        or _sha256_bytes(binding.get("bytes", b"")) != binding.get("sha256")
        or (
            expected_sha256 is not None
            and str(expected_sha256 or "").upper() != binding.get("sha256")
        )
    ):
        raise NoveltyIntegrityError(label + " runtime binding drifted")
    path = _audit_engine_path()
    try:
        live_bytes = path.read_bytes()
    except OSError as exc:
        raise NoveltyIntegrityError(label + " is unreadable after audit") from exc
    if live_bytes != binding["bytes"]:
        raise NoveltyIntegrityError(label + " changed during audit")


def normalize_topic(value: str) -> str:
    """NFKC/casefold while retaining letters, numbers, and Unicode marks.

    Thai tone/vowel marks carry identity. Dropping category M would make
    distinct words such as หนี้ and หนี collide.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(
        char for char in text
        if char.isalnum() or unicodedata.category(char).startswith("M")
    )


def topic_sha256(value: str) -> str:
    normalized = normalize_topic(value)
    if not normalized:
        raise NoveltyIntegrityError("topic identity is empty")
    return _sha256_bytes(normalized.encode("utf-8"))


def _legacy_family_id(topic: str) -> str:
    return "legacy-" + topic_sha256(topic)[:16].lower()


def _resolve_bound_path(value: str) -> Path:
    raw = Path(str(value or ""))
    return (raw if raw.is_absolute() else ROOT / raw).resolve()


def _resolve_repo_evidence_path(value: str) -> tuple[str, Path]:
    """Resolve one direct, repo-relative dedup-evidence JSON path."""
    raw_value = str(value or "").replace("\\", "/")
    raw = Path(raw_value)
    if raw.is_absolute() or ".." in raw.parts:
        raise NoveltyIntegrityError("evidence path must be repo-relative")
    relative = raw.as_posix()
    if not re.fullmatch(r"automation-log/dedup-evidence/[A-Za-z0-9_.-]+\.json", relative):
        raise NoveltyIntegrityError("evidence path is outside the allowed repo root")
    resolved = (ROOT / raw).resolve()
    root_resolved = ROOT.resolve()
    expected = (ROOT / "automation-log" / "dedup-evidence").resolve()
    try:
        expected.relative_to(root_resolved)
    except ValueError as exc:
        raise NoveltyIntegrityError("allowed evidence directory escapes repo root") from exc
    if resolved.parent != expected:
        raise NoveltyIntegrityError("evidence path escaped the allowed repo root")
    return relative, resolved


def _resolve_repo_candidate_path(value: str) -> tuple[str, Path]:
    """Resolve one direct, repo-relative blocked content-pack Markdown path."""
    raw_value = str(value or "").replace("\\", "/")
    raw = Path(raw_value)
    if raw.is_absolute() or ".." in raw.parts:
        raise NoveltyIntegrityError("candidate pack path must be repo-relative")
    relative = raw.as_posix()
    if not re.fullmatch(
        r"automation-log/cc-outbox/LOCAL-CONTENT-PACK_[A-Za-z0-9_-]+\.md",
        relative,
    ):
        raise NoveltyIntegrityError("candidate pack path is outside the allowed repo root")
    resolved = (ROOT / raw).resolve()
    root_resolved = ROOT.resolve()
    expected = (ROOT / "automation-log" / "cc-outbox").resolve()
    try:
        expected.relative_to(root_resolved)
    except ValueError as exc:
        raise NoveltyIntegrityError("allowed candidate directory escapes repo root") from exc
    if resolved.parent != expected:
        raise NoveltyIntegrityError("candidate pack path escaped the allowed repo root")
    return relative, resolved


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise NoveltyIntegrityError("JSON evidence is unreadable: " + str(path)) from exc
    if not isinstance(value, dict):
        raise NoveltyIntegrityError("JSON evidence root is not an object: " + str(path))
    return value


def _load_json_bytes(payload: bytes, path: Path) -> dict:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, TypeError, ValueError) as exc:
        raise NoveltyIntegrityError("JSON evidence is unreadable: " + str(path)) from exc
    if not isinstance(value, dict):
        raise NoveltyIntegrityError("JSON evidence root is not an object: " + str(path))
    return value


def _read_hash_bound_bytes(path: Path, expected_sha256: str, label: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise NoveltyIntegrityError(label + " is unreadable") from exc
    if _sha256_bytes(payload) != str(expected_sha256 or "").upper():
        raise NoveltyIntegrityError(label + " hash mismatch")
    return payload


def _prior_pack_inventory(candidate_path: str) -> dict:
    paths = list((ROOT / "automation-log" / "content-packages").glob("*.md"))
    paths.extend(
        (ROOT / "automation-log" / "cc-outbox").glob("LOCAL-CONTENT-PACK_*.md")
    )
    entries = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix().casefold()):
        relative = path.relative_to(ROOT).as_posix()
        if path.is_file() and relative != candidate_path:
            entries.append({"path": relative, "sha256": _sha256_file(path)})
    return {
        "file_count": len(entries),
        "files": entries,
        "canonical_path_sha256_inventory": _sha256_bytes(
            _canonical_json(entries).encode("utf-8")
        ),
    }


def _capture_corpus_bytes(candidate_path: str) -> tuple[dict[str, bytes], dict]:
    """Read every allowlisted audit input once and derive its exact inventory."""
    candidate_path, _candidate = _resolve_repo_candidate_path(candidate_path)
    root_resolved = ROOT.resolve()
    corpus: dict[str, bytes] = {}
    for relative in (
        ".system_control/content_manifest.json",
        ".system_control/content_calendar.json",
        "automation-log/post-ledger.jsonl",
    ):
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise NoveltyIntegrityError("corpus input escaped repo root: " + relative) from exc
        if not path.is_file():
            raise NoveltyIntegrityError("required corpus input is missing: " + relative)
        try:
            corpus[relative] = path.read_bytes()
        except OSError as exc:
            raise NoveltyIntegrityError("required corpus input is unreadable: " + relative) from exc
    paths = list((ROOT / "automation-log" / "content-packages").glob("*.md"))
    paths.extend(
        (ROOT / "automation-log" / "cc-outbox").glob("LOCAL-CONTENT-PACK_*.md")
    )
    entries = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix().casefold()):
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file() or relative == candidate_path:
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise NoveltyIntegrityError("prior-pack corpus escaped repo root") from exc
        try:
            payload = resolved.read_bytes()
        except OSError as exc:
            raise NoveltyIntegrityError("prior-pack corpus is unreadable") from exc
        corpus[relative] = payload
        entries.append({"path": relative, "sha256": _sha256_bytes(payload)})
    inputs = {
        relative: _sha256_bytes(corpus[relative]) for relative in (
            ".system_control/content_manifest.json",
            ".system_control/content_calendar.json",
            "automation-log/post-ledger.jsonl",
        )
    }
    inputs["prior_generated_fulfilled_withdrawn_pack_inventory"] = {
        "file_count": len(entries),
        "files": entries,
        "canonical_path_sha256_inventory": _sha256_bytes(
            _canonical_json(entries).encode("utf-8")
        ),
    }
    return corpus, inputs


def current_corpus_inputs(candidate_path: str) -> dict:
    """Exact, allowlisted local corpus inputs required by review schema v2."""
    paths = (
        ".system_control/content_manifest.json",
        ".system_control/content_calendar.json",
        "automation-log/post-ledger.jsonl",
    )
    values = {}
    for relative in paths:
        path = ROOT / relative
        if not path.is_file():
            raise NoveltyIntegrityError("required corpus input is missing: " + relative)
        values[relative] = _sha256_file(path)
    values["prior_generated_fulfilled_withdrawn_pack_inventory"] = (
        _prior_pack_inventory(candidate_path)
    )
    return values


def _snapshot_relative(receipt_sha256: str) -> str:
    return (
        ".local-private/runtime/content-novelty/evidence/"
        + receipt_sha256.upper() + "/manifest.json"
    )


def _strict_receipt_snapshot_path(receipt_sha256: str) -> Path:
    sha = str(receipt_sha256 or "").upper()
    if not SHA256_RE.fullmatch(sha):
        raise NoveltyIntegrityError("strict receipt snapshot SHA is invalid")
    target = (
        ROOT / ".local-private" / "runtime" / "content-novelty"
        / "strict-revalidation-receipts" / sha / "receipt.json"
    ).resolve()
    base = (
        ROOT / ".local-private" / "runtime" / "content-novelty"
        / "strict-revalidation-receipts"
    ).resolve()
    try:
        base.relative_to(ROOT.resolve())
        target.relative_to(base)
    except ValueError as exc:
        raise NoveltyIntegrityError("strict receipt snapshot escapes repo root") from exc
    return target


def _write_strict_receipt_snapshot(payload: bytes, receipt_sha256: str) -> Path:
    target = _strict_receipt_snapshot_path(receipt_sha256)
    if _sha256_bytes(payload) != str(receipt_sha256).upper():
        raise NoveltyIntegrityError("strict receipt snapshot bytes are mismatched")
    if target.exists():
        if target.read_bytes() != payload:
            raise NoveltyIntegrityError("strict receipt snapshot drifted")
    else:
        _atomic_write(target, payload)
    return target


def _load_strict_receipt_snapshot(receipt_sha256: str) -> bytes:
    target = _strict_receipt_snapshot_path(receipt_sha256)
    return _read_hash_bound_bytes(
        target, str(receipt_sha256).upper(), "strict receipt snapshot"
    )


def _write_consumption_snapshot(
    receipt_sha256: str, artifacts: list[dict],
) -> dict:
    """Persist content-addressed pre-consumption bytes without overwriting drift."""
    sha = str(receipt_sha256 or "").upper()
    if not SHA256_RE.fullmatch(sha):
        raise NoveltyIntegrityError("snapshot receipt SHA is invalid")
    directory = (
        ROOT / ".local-private" / "runtime" / "content-novelty"
        / "evidence" / sha
    )
    root_resolved = ROOT.resolve()
    evidence_root = directory.parent.resolve()
    try:
        evidence_root.relative_to(root_resolved)
        directory.resolve().relative_to(evidence_root)
    except ValueError as exc:
        raise NoveltyIntegrityError("consumption evidence root escapes repo root") from exc
    records = []
    seen_paths = set()
    for artifact in artifacts:
        relative = str(artifact["path"])
        payload = artifact["bytes"]
        if relative in seen_paths or not isinstance(payload, bytes):
            raise NoveltyIntegrityError("snapshot artifact set is duplicated or invalid")
        seen_paths.add(relative)
        artifact_sha = _sha256_bytes(payload)
        blob_relative = "blobs/" + artifact_sha + ".bin"
        blob_path = directory / blob_relative
        if blob_path.exists():
            if blob_path.read_bytes() != payload:
                raise NoveltyIntegrityError("content-addressed snapshot blob drifted")
        else:
            _atomic_write(blob_path, payload)
        records.append({
            "role": str(artifact["role"]),
            "path": relative,
            "sha256": artifact_sha,
            "blob": blob_relative,
        })
    records.sort(key=lambda item: (item["role"], item["path"]))
    manifest = {
        "schema_version": 1,
        "state": "IMMUTABLE_PRECONSUMPTION_EVIDENCE",
        "receipt_sha256": sha,
        "artifacts": records,
        "bundle_sha256": _sha256_bytes(_canonical_json(records).encode("utf-8")),
        "publication_authority": "NONE",
    }
    manifest_bytes = (_canonical_json(manifest) + "\n").encode("utf-8")
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        if manifest_path.read_bytes() != manifest_bytes:
            raise NoveltyIntegrityError("consumption evidence manifest drifted")
    else:
        _atomic_write(manifest_path, manifest_bytes)
    return {
        "path": _snapshot_relative(sha),
        "sha256": _sha256_bytes(manifest_bytes),
        "bundle_sha256": manifest["bundle_sha256"],
    }


def _load_consumption_snapshot(receipt_sha256: str) -> tuple[dict, dict[str, bytes]]:
    sha = str(receipt_sha256 or "").upper()
    relative = _snapshot_relative(sha)
    manifest_path = (ROOT / relative).resolve()
    evidence_root = (
        ROOT / ".local-private" / "runtime" / "content-novelty" / "evidence"
    ).resolve()
    try:
        evidence_root.relative_to(ROOT.resolve())
        manifest_path.relative_to(evidence_root)
    except ValueError as exc:
        raise NoveltyIntegrityError("consumption snapshot escaped evidence root") from exc
    if not manifest_path.is_file():
        raise NoveltyIntegrityError("consumed fulfilment snapshot is missing")
    manifest_bytes = manifest_path.read_bytes()
    manifest = _load_json_bytes(manifest_bytes, manifest_path)
    if (
        set(manifest) != {
            "schema_version", "state", "receipt_sha256", "artifacts",
            "bundle_sha256", "publication_authority",
        }
        or manifest.get("schema_version") != 1
        or manifest.get("state") != "IMMUTABLE_PRECONSUMPTION_EVIDENCE"
        or manifest.get("receipt_sha256") != sha
        or manifest.get("publication_authority") != "NONE"
        or not isinstance(manifest.get("artifacts"), list)
        or manifest.get("bundle_sha256") != _sha256_bytes(
            _canonical_json(manifest.get("artifacts")).encode("utf-8")
        )
    ):
        raise NoveltyIntegrityError("consumption snapshot manifest is invalid")
    if manifest_bytes != (_canonical_json(manifest) + "\n").encode("utf-8"):
        raise NoveltyIntegrityError("consumption snapshot manifest is non-canonical")
    if any(not isinstance(item, dict) for item in manifest["artifacts"]):
        raise NoveltyIntegrityError("consumption snapshot artifact is not an object")
    if manifest["artifacts"] != sorted(
        manifest["artifacts"], key=lambda item: (item.get("role", ""), item.get("path", ""))
    ):
        raise NoveltyIntegrityError("consumption snapshot artifact order is non-canonical")
    payloads = {}
    for record in manifest["artifacts"]:
        if not isinstance(record, dict) or set(record) != {
            "role", "path", "sha256", "blob",
        }:
            raise NoveltyIntegrityError("consumption snapshot record is invalid")
        if record.get("blob") != "blobs/" + str(record.get("sha256")) + ".bin":
            raise NoveltyIntegrityError("consumption snapshot blob identity is invalid")
        blob = (manifest_path.parent / str(record["blob"])).resolve()
        try:
            blob.relative_to(manifest_path.parent.resolve())
        except ValueError as exc:
            raise NoveltyIntegrityError("consumption snapshot blob escaped bundle") from exc
        data = _read_hash_bound_bytes(
            blob, str(record["sha256"]), "consumption snapshot blob"
        )
        key = str(record["path"])
        if key in payloads:
            raise NoveltyIntegrityError("consumption snapshot paths are duplicated")
        payloads[key] = data
    return manifest, payloads


def _review_corpus_bindings(review_payload: dict) -> dict[str, str]:
    """Return the exact allowlisted corpus path/hash map declared by a v2 review."""
    inputs = review_payload.get("corpus_inputs")
    core_paths = (
        ".system_control/content_manifest.json",
        ".system_control/content_calendar.json",
        "automation-log/post-ledger.jsonl",
    )
    if not isinstance(inputs, dict) or set(inputs) != {
        *core_paths, "prior_generated_fulfilled_withdrawn_pack_inventory",
    }:
        raise NoveltyIntegrityError("corpus-review input schema is invalid")
    bindings = {}
    for path in core_paths:
        sha = str(inputs.get(path) or "").upper()
        if not SHA256_RE.fullmatch(sha):
            raise NoveltyIntegrityError("corpus-review core input hash is invalid")
        bindings[path] = sha
    inventory = inputs.get("prior_generated_fulfilled_withdrawn_pack_inventory")
    if not isinstance(inventory, dict) or set(inventory) != {
        "file_count", "files", "canonical_path_sha256_inventory",
    }:
        raise NoveltyIntegrityError("corpus-review prior-pack inventory schema is invalid")
    files = inventory.get("files")
    if not isinstance(files, list) or any(
        not isinstance(item, dict) or set(item) != {"path", "sha256"}
        for item in files
    ):
        raise NoveltyIntegrityError("corpus-review prior-pack record is invalid")
    if (
        inventory.get("file_count") != len(files)
        or files != sorted(files, key=lambda item: str(item.get("path", "")).casefold())
        or inventory.get("canonical_path_sha256_inventory")
        != _sha256_bytes(_canonical_json(files).encode("utf-8"))
    ):
        raise NoveltyIntegrityError("corpus-review prior-pack inventory is non-canonical")
    for item in files:
        path = str(item.get("path") or "")
        sha = str(item.get("sha256") or "").upper()
        if not (
            SHA256_RE.fullmatch(sha)
            and path not in bindings
            and (
                re.fullmatch(r"automation-log/content-packages/[^/]+\.md", path)
                or re.fullmatch(
                    r"automation-log/cc-outbox/LOCAL-CONTENT-PACK_[A-Za-z0-9_-]+\.md",
                    path,
                )
            )
        ):
            raise NoveltyIntegrityError("corpus-review prior-pack path/hash is invalid")
        bindings[path] = sha
    return bindings


def _validate_snapshot_artifact_contract(
    manifest: dict, snapshot: dict[str, bytes], *, receipt_path: str,
    receipt_sha256: str, receipt_payload: dict, review_payload: dict,
) -> dict[str, bytes]:
    """Reject any dropped, added, or role-rewritten immutable artifact."""
    review = receipt_payload.get("corpus_review")
    pack = receipt_payload.get("pack")
    engine = receipt_payload.get("audit_engine")
    if (
        not isinstance(review, dict) or set(review) != {"path", "sha256"}
        or not isinstance(pack, dict) or "path" not in pack or "sha256" not in pack
        or not isinstance(engine, dict) or set(engine) != {"path", "sha256"}
        or engine.get("path") != "pipeline/content_pack_audit.py"
    ):
        raise NoveltyIntegrityError("snapshot receipt nested bindings are invalid")
    expected = {
        ("fulfilment_receipt", receipt_path, str(receipt_sha256).upper()),
        (
            "corpus_review_receipt", str(review["path"]),
            str(review["sha256"]).upper(),
        ),
        ("candidate_pack", str(pack["path"]), str(pack["sha256"]).upper()),
        ("audit_engine", str(engine["path"]), str(engine["sha256"]).upper()),
    }
    corpus_bindings = _review_corpus_bindings(review_payload)
    expected.update(
        ("corpus_input", path, sha) for path, sha in corpus_bindings.items()
    )
    actual = {
        (str(item["role"]), str(item["path"]), str(item["sha256"]).upper())
        for item in manifest["artifacts"]
    }
    if len(actual) != len(manifest["artifacts"]) or actual != expected:
        raise NoveltyIntegrityError(
            "consumption snapshot artifact set/roles differ from immutable bindings"
        )
    for _role, path, sha in expected:
        data = snapshot.get(path)
        if data is None or _sha256_bytes(data) != sha:
            raise NoveltyIntegrityError("consumption snapshot bound artifact is missing")
    return {path: snapshot[path] for path in corpus_bindings}


def _validate_review_receipt(
    rows: list[dict], *, allow_bound_subset: bool = False,
    recompute_current_audit: bool = True,
    preloaded_receipts: dict[tuple[str, str], bytes] | None = None,
    corpus_bytes: dict[str, bytes] | None = None,
    audit_engine_runtime: dict | None = None,
) -> dict:
    """Require exact schema-v2 method, current corpus hashes, and family/topic map."""
    if recompute_current_audit:
        if audit_engine_runtime is None:
            audit_engine_runtime = _load_bound_audit_engine(
                label="corpus-review audit engine"
            )
        else:
            _recheck_bound_audit_engine(
                audit_engine_runtime, label="corpus-review audit engine"
            )
    elif audit_engine_runtime is not None:
        raise NoveltyIntegrityError(
            "historical corpus-review validation cannot accept a live audit runtime"
        )
    groups = {}
    for row in rows:
        supplied_hash = str(row.get("corpus_review_sha256") or "").upper()
        supplied_path = str(row.get("corpus_review_receipt") or "")
        if not supplied_path or not SHA256_RE.fullmatch(supplied_hash):
            raise NoveltyIntegrityError(
                "active family lacks a provisional corpus-review receipt binding"
            )
        groups.setdefault((supplied_path, supplied_hash), []).append(row)

    top_keys = {
        "schema_version", "receipt_type", "producer", "method", "review_state",
        "semantic_universality_claimed", "publication_authority", "created_at",
        "method_limit", "candidate_path", "families", "corpus_inputs",
        "corpus_audit", "explicit_non_authority",
    }
    audit_keys = {
        "topic_candidates", "topic_baseline_records",
        "historical_exact_collisions", "historical_near_collisions",
        "cross_family_exact_collisions", "cross_family_near_collisions",
    }
    collision_keys = audit_keys - {"topic_candidates", "topic_baseline_records"}
    validated = {}
    for (supplied_path, supplied_hash), bound_rows in groups.items():
        canonical_path, resolved = _resolve_repo_evidence_path(supplied_path)
        if supplied_path != canonical_path:
            raise NoveltyIntegrityError("corpus-review receipt path is not canonical")
        preloaded = (preloaded_receipts or {}).get((supplied_path, supplied_hash))
        if preloaded is None and not resolved.is_file():
            raise NoveltyIntegrityError(
                "provisional corpus-review receipt hash is missing or mismatched"
            )
        receipt_bytes = (
            preloaded if preloaded is not None else _read_hash_bound_bytes(
                resolved, supplied_hash, "provisional corpus-review receipt"
            )
        )
        if _sha256_bytes(receipt_bytes) != supplied_hash:
            raise NoveltyIntegrityError("preloaded corpus-review receipt hash mismatch")
        payload = _load_json_bytes(receipt_bytes, resolved)
        if set(payload) != top_keys or (
            payload.get("schema_version") != CORPUS_REVIEW_SCHEMA_VERSION
            or payload.get("receipt_type") != CORPUS_REVIEW_RECEIPT_TYPE
            or payload.get("producer") != CORPUS_REVIEW_PRODUCER
            or payload.get("method") != CORPUS_REVIEW_METHOD
            or payload.get("review_state") != "PROVISIONAL_LOCAL_REVIEW"
            or payload.get("semantic_universality_claimed") is not False
            or payload.get("publication_authority") != "NONE"
            or not isinstance(payload.get("created_at"), str)
            or not payload.get("created_at")
            or not isinstance(payload.get("method_limit"), str)
            or "not prove" not in payload.get("method_limit", "").casefold()
            or not isinstance(payload.get("explicit_non_authority"), str)
            or not payload.get("explicit_non_authority")
        ):
            raise NoveltyIntegrityError(
                "provisional corpus-review receipt schema/method/producer is invalid"
            )
        candidate_path, _candidate_resolved = _resolve_repo_candidate_path(
            str(payload.get("candidate_path") or "")
        )
        if payload.get("candidate_path") != candidate_path:
            raise NoveltyIntegrityError("corpus-review candidate path is not canonical")
        if not isinstance(payload.get("corpus_inputs"), dict):
            raise NoveltyIntegrityError(
                "provisional corpus-review receipt has no corpus input binding"
            )
        current_inputs = (
            _capture_corpus_bytes(candidate_path)[1]
            if recompute_current_audit and corpus_bytes is None
            else None
        )
        if corpus_bytes is not None:
            inventory_entries = [
                {"path": path, "sha256": _sha256_bytes(data)}
                for path, data in sorted(corpus_bytes.items())
                if path != candidate_path and (
                    path.startswith("automation-log/content-packages/")
                    or path.startswith("automation-log/cc-outbox/LOCAL-CONTENT-PACK_")
                )
            ]
            current_inputs = {
                relative: _sha256_bytes(corpus_bytes[relative]) for relative in (
                    ".system_control/content_manifest.json",
                    ".system_control/content_calendar.json",
                    "automation-log/post-ledger.jsonl",
                )
            }
            current_inputs["prior_generated_fulfilled_withdrawn_pack_inventory"] = {
                "file_count": len(inventory_entries),
                "files": inventory_entries,
                "canonical_path_sha256_inventory": _sha256_bytes(
                    _canonical_json(inventory_entries).encode("utf-8")
                ),
            }
        if recompute_current_audit and payload.get("corpus_inputs") != current_inputs:
            raise NoveltyIntegrityError(
                "provisional corpus-review receipt is stale or has a fabricated input set"
            )
        families = payload.get("families")
        if not isinstance(families, list) or any(
            not isinstance(item, dict)
            or set(item) != {"family_id", "topic", "topic_sha256"}
            or topic_sha256(item.get("topic")) != item.get("topic_sha256")
            for item in families
        ):
            raise NoveltyIntegrityError("corpus-review receipt family schema is invalid")
        supplied_map = {
            item["family_id"]: (item["topic"], item["topic_sha256"])
            for item in families
        }
        expected_map = {
            row["family_id"]: (row["topic"], row["topic_sha256"])
            for row in bound_rows
        }
        if (
            len(supplied_map) != len(families)
            or any(supplied_map.get(key) != value for key, value in expected_map.items())
            or (not allow_bound_subset and supplied_map != expected_map)
        ):
            raise NoveltyIntegrityError(
                "corpus-review receipt does not bind the exact family/topic map"
            )
        audit = payload.get("corpus_audit")
        computed_receipt_audit = None
        if recompute_current_audit:
            engine_module = audit_engine_runtime["module"]
            try:
                computed_audit = engine_module.audit_topics(
                    ROOT, candidate_path, families, corpus_bytes
                )
            except engine_module.ContentPackAuditError as exc:
                raise NoveltyIntegrityError("topic corpus audit cannot be recomputed: " + str(exc)) from exc
            computed_receipt_audit = {
                key: computed_audit[key] for key in audit_keys
            }
            _recheck_bound_audit_engine(
                audit_engine_runtime,
                label="corpus-review audit engine",
            )
        if (
            not isinstance(audit, dict)
            or set(audit) != audit_keys
            or audit.get("topic_candidates") != len(families)
            or not isinstance(audit.get("topic_baseline_records"), int)
            or audit.get("topic_baseline_records") < 1
            or any(audit.get(name) != 0 for name in collision_keys)
            or (
                recompute_current_audit
                and audit != computed_receipt_audit
            )
        ):
            raise NoveltyIntegrityError(
                "provisional corpus-review receipt does not bind a clean local audit"
            )
        if (
            recompute_current_audit
            and corpus_bytes is None
            and payload.get("corpus_inputs") != current_corpus_inputs(candidate_path)
        ):
            raise NoveltyIntegrityError(
                "provisional corpus-review corpus changed during audit"
            )
        validated[(supplied_path, supplied_hash)] = payload
    if recompute_current_audit:
        _recheck_bound_audit_engine(
            audit_engine_runtime,
            label="corpus-review audit engine",
        )
    return validated


def _parse_order_line(raw: str, line_number: int, *, historical: bool) -> dict:
    fields = [field.strip() for field in raw.split("\t")]
    if historical:
        if len(fields) == 1:
            topic = fields[0]
            family_id = _legacy_family_id(topic)
            explicit_family = False
        elif len(fields) == 2:
            family_id, topic = fields
            explicit_family = True
        else:
            raise NoveltyIntegrityError(
                "historical orders line %d has invalid field count" % line_number
            )
        receipt_path = receipt_hash = ""
    else:
        if len(fields) != 4:
            raise NoveltyIntegrityError(
                "active orders line %d must bind family, topic, review receipt, and hash"
                % line_number
            )
        family_id, topic, receipt_path, receipt_hash = fields
        explicit_family = True
    if not FAMILY_RE.fullmatch(family_id):
        raise NoveltyIntegrityError(
            "orders line %d has invalid semantic family id" % line_number
        )
    if not topic:
        raise NoveltyIntegrityError("orders line %d has empty topic" % line_number)
    return {
        "family_id": family_id,
        "topic": topic,
        "topic_sha256": topic_sha256(topic),
        "line_number": line_number,
        "historical": bool(historical),
        "explicit_family": explicit_family,
        "corpus_review_receipt": receipt_path,
        "corpus_review_sha256": receipt_hash.upper(),
    }


def load_order_registry(
    path: str | os.PathLike[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Read the candidate registry exactly once and validate review bindings."""
    target = Path(path or ORDERS)
    if not target.is_file():
        raise NoveltyIntegrityError("orders registry is missing")
    try:
        lines = target.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise NoveltyIntegrityError("orders registry is unreadable") from exc
    active, historical = [], []
    seen_families, seen_topics = {}, {}
    for line_number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(HISTORICAL_PREFIX):
            row = _parse_order_line(
                stripped[len(HISTORICAL_PREFIX):], line_number, historical=True
            )
            historical.append(row)
        elif stripped.startswith("#"):
            continue
        else:
            row = _parse_order_line(stripped, line_number, historical=False)
            active.append(row)
        family_id, identity = row["family_id"], row["topic_sha256"]
        if family_id in seen_families:
            raise NoveltyIntegrityError(
                "semantic family %s is duplicated on orders lines %d and %d"
                % (family_id, seen_families[family_id], line_number)
            )
        if identity in seen_topics:
            raise NoveltyIntegrityError(
                "normalized topic is duplicated on orders lines %d and %d"
                % (seen_topics[identity], line_number)
            )
        seen_families[family_id] = line_number
        seen_topics[identity] = line_number
    _validate_review_receipt(active, recompute_current_audit=False)
    return active, historical


def load_orders():
    """Compatibility seam returning one complete registry read."""
    return load_order_registry()


def _coerce_loaded_registry(value) -> tuple[list[dict], list[dict]]:
    if (
        isinstance(value, tuple) and len(value) == 2
        and isinstance(value[0], list) and isinstance(value[1], list)
    ):
        return value
    raise NoveltyIntegrityError("load_orders must return one active/historical registry pair")


def ledger_path_for(inbox: str | os.PathLike[str] | None = None) -> Path:
    selected = Path(inbox or INBOX).resolve()
    if selected == DEFAULT_INBOX.resolve():
        return DEFAULT_LEDGER
    return selected.parent / ".content-novelty" / "topic-lifecycle-ledger.jsonl"


def _state_paths(ledger_path: Path) -> tuple[Path, Path]:
    return (
        ledger_path.with_suffix(ledger_path.suffix + ".activated.json"),
        ledger_path.with_suffix(ledger_path.suffix + ".checkpoint.json"),
    )


def _append_journal_path(ledger_path: Path) -> Path:
    return ledger_path.with_suffix(ledger_path.suffix + ".append-journal.json")


def _state_id(ledger_path: Path) -> str:
    return _sha256_bytes(str(ledger_path.resolve()).encode("utf-8"))


def _record_hash(record_without_hash: dict) -> str:
    return _sha256_bytes(_canonical_json(record_without_hash).encode("utf-8"))


def _ledger_bytes(rows: list[dict]) -> bytes:
    return "".join(_canonical_json(row) + "\n" for row in rows).encode("utf-8")


def _lock_byte(handle, *, unlock: bool = False) -> None:
    handle.seek(0)
    if os.name == "nt":
        mode = msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK
        msvcrt.locking(handle.fileno(), mode, 1)
    else:  # pragma: no cover
        mode = fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB
        fcntl.flock(handle.fileno(), mode)


@contextlib.contextmanager
def _claim_lock(ledger_path: Path):
    """Acquire a process-crash-releasing OS lock; file existence is inert."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    handle = lock_path.open("a+b", buffering=0)
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        os.fsync(handle.fileno())
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    acquired = False
    try:
        while not acquired:
            try:
                _lock_byte(handle)
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise NoveltyLockError(
                        "novelty state lock is busy; state is BLOCKED/UNKNOWN"
                    )
                time.sleep(0.02)
        _recover_append_journal(ledger_path)
        yield
    finally:
        if acquired:
            try:
                _lock_byte(handle, unlock=True)
            except OSError:
                pass
        handle.close()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _journal_bytes(payload: dict) -> bytes:
    body = dict(payload)
    body.pop("journal_sha256", None)
    canonical_hash = _sha256_bytes(_canonical_json(body).encode("utf-8"))
    return (_canonical_json(dict(body, journal_sha256=canonical_hash)) + "\n").encode(
        "utf-8"
    )


def _state_binding(ledger_payload: bytes, checkpoint: dict) -> dict:
    if not isinstance(checkpoint, dict) or set(checkpoint) != {
        "schema_version", "state_id", "sequence", "head_hash", "ledger_sha256",
    }:
        raise NoveltyIntegrityError("novelty checkpoint schema is invalid")
    if (
        checkpoint.get("schema_version") != STATE_SCHEMA_VERSION
        or type(checkpoint.get("sequence")) is not int
        or checkpoint["sequence"] < 0
        or not SHA256_RE.fullmatch(str(checkpoint.get("head_hash") or ""))
        or not SHA256_RE.fullmatch(str(checkpoint.get("ledger_sha256") or ""))
    ):
        raise NoveltyIntegrityError("novelty checkpoint binding is invalid")
    return {
        "sequence": checkpoint["sequence"],
        "head_hash": checkpoint["head_hash"],
        "ledger_sha256": _sha256_bytes(ledger_payload),
    }


def _recover_append_journal(ledger_path: Path) -> None:
    """Complete an interrupted ledger/checkpoint pair while the OS lock is held."""
    journal_path = _append_journal_path(ledger_path)
    if not journal_path.is_file():
        return
    payload = _load_json(journal_path)
    if set(payload) != {
        "schema_version", "state", "state_id", "previous", "next",
        "ledger_utf8", "checkpoint", "journal_sha256",
    }:
        raise NoveltyIntegrityError("append journal schema is invalid")
    supplied_hash = payload.get("journal_sha256")
    if journal_path.read_bytes() != _journal_bytes(payload):
        raise NoveltyIntegrityError("append journal bytes/hash are invalid")
    if (
        payload.get("schema_version") != 1
        or payload.get("state") not in {"PENDING", "APPLIED"}
        or payload.get("state_id") != _state_id(ledger_path)
        or not isinstance(payload.get("ledger_utf8"), str)
        or not isinstance(payload.get("checkpoint"), dict)
        or not isinstance(supplied_hash, str)
    ):
        raise NoveltyIntegrityError("append journal identity is invalid")
    try:
        next_ledger = payload["ledger_utf8"].encode("utf-8")
    except UnicodeError as exc:
        raise NoveltyIntegrityError("append journal ledger bytes are invalid") from exc
    checkpoint = payload["checkpoint"]
    expected_next = _state_binding(next_ledger, checkpoint)
    if payload.get("next") != expected_next or set(checkpoint) != {
        "schema_version", "state_id", "sequence", "head_hash", "ledger_sha256",
    } or (
        checkpoint.get("schema_version") != STATE_SCHEMA_VERSION
        or checkpoint.get("state_id") != _state_id(ledger_path)
        or checkpoint.get("ledger_sha256") != expected_next["ledger_sha256"]
    ):
        raise NoveltyIntegrityError("append journal next state is invalid")
    checkpoint_path = _state_paths(ledger_path)[1]
    try:
        current_ledger = ledger_path.read_bytes()
        current_checkpoint = _load_json(checkpoint_path)
    except (OSError, NoveltyIntegrityError) as exc:
        raise NoveltyIntegrityError("append journal cannot inspect current state") from exc
    current_binding = _state_binding(current_ledger, current_checkpoint)
    current_ledger_sha = _sha256_bytes(current_ledger)
    current_checkpoint_binding = {
        "sequence": current_checkpoint["sequence"],
        "head_hash": current_checkpoint["head_hash"],
        "ledger_sha256": current_checkpoint["ledger_sha256"],
    }
    previous = payload.get("previous")
    next_binding = payload.get("next")
    if (
        not isinstance(previous, dict)
        or not isinstance(next_binding, dict)
        or current_ledger_sha not in {
            previous.get("ledger_sha256"), next_binding.get("ledger_sha256")
        }
        or current_checkpoint_binding not in (previous, next_binding)
    ):
        raise NoveltyIntegrityError(
            "append journal current ledger/checkpoint are outside old/new transaction"
        )
    if payload["state"] == "APPLIED":
        if current_binding != next_binding or current_checkpoint_binding != next_binding:
            raise NoveltyIntegrityError("applied append journal points to an older state")
        return
    _atomic_write(ledger_path, next_ledger)
    _atomic_write(
        checkpoint_path, (_canonical_json(checkpoint) + "\n").encode("utf-8")
    )
    applied = dict(payload, state="APPLIED")
    _atomic_write(journal_path, _journal_bytes(applied))


def bootstrap_novelty_state(ledger_path: str | os.PathLike[str]) -> dict:
    """Explicitly activate empty state; never called implicitly by scheduled main."""
    target = Path(ledger_path)
    sentinel_path, checkpoint_path = _state_paths(target)
    with _claim_lock(target):
        present = [path.exists() for path in (target, sentinel_path, checkpoint_path)]
        if all(present):
            read_consumed_ledger(target)
            return _load_json(sentinel_path)
        if any(present):
            raise NoveltyIntegrityError(
                "partial novelty activation exists; explicit repair is required"
            )
        state_id = _state_id(target)
        ledger_payload = b""
        sentinel = {
            "schema_version": STATE_SCHEMA_VERSION,
            "state": "ACTIVATED_EMPTY",
            "state_id": state_id,
            "ledger_name": target.name,
            "checkpoint_name": checkpoint_path.name,
            "activated_at": _datetime.datetime.now(
                _datetime.timezone.utc
            ).isoformat(timespec="seconds"),
        }
        checkpoint = {
            "schema_version": STATE_SCHEMA_VERSION,
            "state_id": state_id,
            "sequence": 0,
            "head_hash": GENESIS_HASH,
            "ledger_sha256": _sha256_bytes(ledger_payload),
        }
        _atomic_write(target, ledger_payload)
        _atomic_write(
            checkpoint_path, (_canonical_json(checkpoint) + "\n").encode("utf-8")
        )
        _atomic_write(
            sentinel_path, (_canonical_json(sentinel) + "\n").encode("utf-8")
        )
        return sentinel


def _valid_request_id(request_id: str) -> bool:
    match = REQUEST_ID_RE.fullmatch(str(request_id or ""))
    if not match:
        return False
    try:
        return _datetime.date.fromisoformat(match.group(2)).isoformat() == match.group(2)
    except ValueError:
        return False


def _read_ledger_rows_raw(target: Path) -> tuple[list[dict], bytes]:
    try:
        payload = target.read_bytes()
        raw_lines = payload.decode("utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise NoveltyIntegrityError("topic lifecycle ledger is unreadable") from exc
    rows, expected_previous = [], GENESIS_HASH
    state_by_family, family_by_topic = {}, {}
    required = {
        "schema_version", "sequence", "event_at", "event", "family_id", "topic",
        "topic_sha256", "consumer", "request_id", "orders_line", "historical",
        "corpus_review_receipt", "corpus_review_sha256",
        "fulfilment_receipt", "fulfilment_sha256",
        "previous_hash", "record_hash",
    }
    for line_number, raw in enumerate(raw_lines, 1):
        if not raw.strip():
            raise NoveltyIntegrityError(
                "topic lifecycle ledger has blank line %d" % line_number
            )
        try:
            row = json.loads(
                raw, object_pairs_hook=_strict_object,
                parse_constant=_reject_json_constant,
            )
        except (TypeError, ValueError) as exc:
            raise NoveltyIntegrityError(
                "topic lifecycle ledger line %d is invalid JSON" % line_number
            ) from exc
        expected_keys = required
        if isinstance(row, dict) and row.get("event") == "LEGACY_CONSUMPTION_RECLASSIFIED":
            expected_keys = required | REVALIDATION_EVENT_KEYS
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise NoveltyIntegrityError(
                "topic lifecycle ledger line %d has invalid schema" % line_number
            )
        if row["schema_version"] != SCHEMA_VERSION or row["sequence"] != line_number:
            raise NoveltyIntegrityError(
                "topic lifecycle ledger line %d has invalid sequence/schema" % line_number
            )
        if row["previous_hash"] != expected_previous:
            raise NoveltyIntegrityError(
                "topic lifecycle ledger hash chain breaks at line %d" % line_number
            )
        if (
            not FAMILY_RE.fullmatch(str(row["family_id"]))
            or topic_sha256(row["topic"]) != row["topic_sha256"]
        ):
            raise NoveltyIntegrityError(
                "topic lifecycle identity mismatch at line %d" % line_number
            )
        body = dict(row)
        supplied_hash = body.pop("record_hash")
        if _record_hash(body) != supplied_hash:
            raise NoveltyIntegrityError(
                "topic lifecycle record hash mismatch at line %d" % line_number
            )
        if not row["historical"] and not _valid_request_id(row["request_id"]):
            raise NoveltyIntegrityError(
                "topic lifecycle request id invalid at line %d" % line_number
            )
        prior_family = family_by_topic.get(row["topic_sha256"])
        if prior_family is not None and prior_family != row["family_id"]:
            raise NoveltyIntegrityError(
                "topic identity is reused across families at line %d" % line_number
            )
        family_by_topic[row["topic_sha256"]] = row["family_id"]
        prior = state_by_family.get(row["family_id"])
        if row["historical"]:
            valid_transition = (
                prior is None
                and row["event"] == "CONSUMED"
                and row["request_id"] == HISTORICAL_REQUEST_ID
                and not row["corpus_review_receipt"]
                and not row["corpus_review_sha256"]
            )
        elif prior is None:
            valid_transition = (
                row["event"] == "RESERVED"
                and bool(row["corpus_review_receipt"])
                and bool(SHA256_RE.fullmatch(row["corpus_review_sha256"]))
                and not row["fulfilment_receipt"]
                and not row["fulfilment_sha256"]
            )
        elif row["event"] == "REVIEW_REFRESHED":
            valid_transition = (
                prior is not None
                and prior["event"] in {"RESERVED", "REVIEW_REFRESHED"}
                and not prior["historical"]
                and not row["historical"]
                and all(row[key] == prior[key] for key in (
                    "family_id", "topic", "topic_sha256", "request_id",
                ))
                and bool(row["corpus_review_receipt"])
                and bool(SHA256_RE.fullmatch(row["corpus_review_sha256"]))
                and (
                    row["corpus_review_receipt"], row["corpus_review_sha256"]
                ) != (
                    prior["corpus_review_receipt"], prior["corpus_review_sha256"]
                )
                and not row["fulfilment_receipt"]
                and not row["fulfilment_sha256"]
            )
        elif row["event"] == "LEGACY_CONSUMPTION_RECLASSIFIED":
            valid_transition = (
                prior is not None
                and prior["event"] == "CONSUMED"
                and not prior["historical"]
                and not row["historical"]
                and all(row[key] == prior[key] for key in (
                    "family_id", "topic", "topic_sha256", "request_id",
                    "orders_line", "corpus_review_receipt",
                    "corpus_review_sha256", "fulfilment_receipt",
                    "fulfilment_sha256",
                ))
                and row["consumer"] == "strict-legacy-reclassification"
                and row["revalidation_receipt"] == STRICT_REVALIDATION_RELATIVE
                and bool(SHA256_RE.fullmatch(row["revalidation_sha256"]))
                and bool(SHA256_RE.fullmatch(row["snapshot_manifest_sha256"]))
            )
        elif row["event"] == "DRAFTED_BLOCKED":
            valid_transition = (
                prior is not None
                and prior["event"] in {"RESERVED", "REVIEW_REFRESHED"}
                and not prior["historical"]
                and not row["historical"]
                and all(row[key] == prior[key] for key in (
                    "family_id", "topic", "topic_sha256", "request_id",
                    "orders_line", "corpus_review_receipt",
                    "corpus_review_sha256",
                ))
                and bool(row["fulfilment_receipt"])
                and bool(SHA256_RE.fullmatch(row["fulfilment_sha256"]))
            )
        else:
            valid_transition = (
                prior["event"] in {"RESERVED", "REVIEW_REFRESHED"}
                and row["event"] == "CONSUMED"
                and not prior["historical"]
                and not row["historical"]
                and all(row[key] == prior[key] for key in (
                    "family_id", "topic", "topic_sha256", "request_id",
                    "orders_line", "corpus_review_receipt",
                    "corpus_review_sha256",
                ))
                and bool(row["fulfilment_receipt"])
                and bool(SHA256_RE.fullmatch(row["fulfilment_sha256"]))
            )
        if not valid_transition:
            raise NoveltyIntegrityError(
                "topic lifecycle transition invalid at line %d" % line_number
            )
        state_by_family[row["family_id"]] = row
        rows.append(row)
        expected_previous = supplied_hash
    if payload != _ledger_bytes(rows):
        raise NoveltyIntegrityError("topic lifecycle ledger bytes are non-canonical")
    return rows, payload


def read_consumed_ledger(path: str | os.PathLike[str]) -> list[dict]:
    """Validate activation, event chain, and independent checkpoint."""
    target = Path(path)
    sentinel_path, checkpoint_path = _state_paths(target)
    if not sentinel_path.exists():
        raise NoveltyStateUninitialized(
            "novelty activation sentinel is missing; explicit bootstrap required"
        )
    if not target.is_file() or not checkpoint_path.is_file():
        raise NoveltyIntegrityError(
            "activated novelty state is missing ledger or checkpoint"
        )
    sentinel = _load_json(sentinel_path)
    checkpoint = _load_json(checkpoint_path)
    state_id = _state_id(target)
    if (
        sentinel.get("schema_version") != STATE_SCHEMA_VERSION
        or sentinel.get("state") != "ACTIVATED_EMPTY"
        or sentinel.get("state_id") != state_id
        or sentinel.get("ledger_name") != target.name
        or sentinel.get("checkpoint_name") != checkpoint_path.name
    ):
        raise NoveltyIntegrityError("novelty activation sentinel is mismatched")
    rows, payload = _read_ledger_rows_raw(target)
    head = rows[-1]["record_hash"] if rows else GENESIS_HASH
    expected_checkpoint = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_id": state_id,
        "sequence": len(rows),
        "head_hash": head,
        "ledger_sha256": _sha256_bytes(payload),
    }
    if checkpoint != expected_checkpoint:
        raise NoveltyIntegrityError(
            "novelty checkpoint does not bind exact ledger sequence/head/bytes"
        )
    return rows


def _validate_candidates(active: list[dict], historical: list[dict], request_id: str) -> None:
    if not _valid_request_id(request_id):
        raise NoveltyIntegrityError("request_id is invalid before reservation")
    families, topics = set(), set()
    for row in [*active, *historical]:
        if topic_sha256(row.get("topic")) != row.get("topic_sha256"):
            raise NoveltyIntegrityError("supplied candidate topic hash is mismatched")
        if row.get("family_id") in families or row.get("topic_sha256") in topics:
            raise NoveltyIntegrityError("supplied candidate identities are duplicated")
        families.add(row.get("family_id"))
        topics.add(row.get("topic_sha256"))
    if any(row.get("historical") for row in active):
        raise NoveltyIntegrityError("active candidates are marked historical")
    if any(not row.get("historical") for row in historical):
        raise NoveltyIntegrityError("historical candidates are not marked historical")
    _validate_review_receipt(active, recompute_current_audit=False)


def _append_events_atomic(
    path: Path, existing: list[dict], events: list[dict],
) -> list[dict]:
    sentinel_path, checkpoint_path = _state_paths(path)
    sentinel = _load_json(sentinel_path)
    rows = list(existing)
    previous_hash = rows[-1]["record_hash"] if rows else GENESIS_HASH
    for event in events:
        body = {
            "schema_version": SCHEMA_VERSION,
            "sequence": len(rows) + 1,
            "event_at": _datetime.datetime.now(
                _datetime.timezone.utc
            ).isoformat(timespec="seconds"),
            "event": event["event"],
            "family_id": event["family_id"],
            "topic": event["topic"],
            "topic_sha256": event["topic_sha256"],
            "consumer": event["consumer"],
            "request_id": event["request_id"],
            "orders_line": int(event.get("line_number") or event.get("orders_line") or 0),
            "historical": bool(event.get("historical")),
            "corpus_review_receipt": str(event.get("corpus_review_receipt") or ""),
            "corpus_review_sha256": str(event.get("corpus_review_sha256") or "").upper(),
            "fulfilment_receipt": str(event.get("fulfilment_receipt") or ""),
            "fulfilment_sha256": str(event.get("fulfilment_sha256") or "").upper(),
            "previous_hash": previous_hash,
        }
        if event["event"] == "LEGACY_CONSUMPTION_RECLASSIFIED":
            body.update({
                "revalidation_receipt": str(event.get("revalidation_receipt") or ""),
                "revalidation_sha256": str(
                    event.get("revalidation_sha256") or ""
                ).upper(),
                "snapshot_manifest_sha256": str(
                    event.get("snapshot_manifest_sha256") or ""
                ).upper(),
            })
        row = dict(body, record_hash=_record_hash(body))
        rows.append(row)
        previous_hash = row["record_hash"]
    ledger_payload = _ledger_bytes(rows)
    checkpoint = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_id": sentinel["state_id"],
        "sequence": len(rows),
        "head_hash": previous_hash,
        "ledger_sha256": _sha256_bytes(ledger_payload),
    }
    try:
        previous_ledger = path.read_bytes()
    except OSError as exc:
        raise NoveltyIntegrityError("ledger disappeared before append journal") from exc
    previous_checkpoint = _load_json(checkpoint_path)
    if previous_ledger != _ledger_bytes(existing):
        raise NoveltyIntegrityError("ledger changed before append journal")
    journal = {
        "schema_version": 1,
        "state": "PENDING",
        "state_id": sentinel["state_id"],
        "previous": _state_binding(previous_ledger, previous_checkpoint),
        "next": _state_binding(ledger_payload, checkpoint),
        "ledger_utf8": ledger_payload.decode("utf-8"),
        "checkpoint": checkpoint,
    }
    journal_path = _append_journal_path(path)
    _atomic_write(journal_path, _journal_bytes(journal))
    _atomic_write(path, ledger_payload)
    _atomic_write(
        checkpoint_path, (_canonical_json(checkpoint) + "\n").encode("utf-8")
    )
    _atomic_write(journal_path, _journal_bytes(dict(journal, state="APPLIED")))
    # Every integrity check that could depend on mutable external evidence ran
    # before the append.  Returning the exact in-memory rows avoids a
    # post-commit read/validation failure being mistaken for a rolled-back
    # transaction; the next locked reader independently verifies journal,
    # ledger, sentinel, and checkpoint.
    return rows


def _lifecycle(rows: list[dict]):
    reserved, drafted, consumed = {}, {}, {}
    for row in rows:
        if row["historical"]:
            consumed[row["family_id"]] = row
        elif row["event"] in {"RESERVED", "REVIEW_REFRESHED"}:
            reserved[row["family_id"]] = row
        elif row["event"] == "DRAFTED_BLOCKED":
            drafted[row["family_id"]] = row
        elif row["event"] == "CONSUMED":
            consumed[row["family_id"]] = row
            drafted.pop(row["family_id"], None)
        elif row["event"] == "LEGACY_CONSUMPTION_RECLASSIFIED":
            # Legacy mechanical-only CONSUMED rows are corrected to a blocked
            # drafted state once their strict immutable evidence is anchored.
            consumed.pop(row["family_id"], None)
            drafted[row["family_id"]] = row
    outstanding = {
        family: row for family, row in reserved.items()
        if family not in drafted and family not in consumed
    }
    return reserved, consumed, outstanding


def _drafted_map(rows: list[dict]) -> dict[str, dict]:
    drafted = {}
    for row in rows:
        if row["historical"]:
            continue
        if row["event"] == "DRAFTED_BLOCKED":
            drafted[row["family_id"]] = row
        elif row["event"] == "CONSUMED":
            drafted.pop(row["family_id"], None)
        elif row["event"] == "LEGACY_CONSUMPTION_RECLASSIFIED":
            drafted[row["family_id"]] = row
    return drafted


def _consumed_event_map(rows: list[dict]) -> dict[str, dict]:
    return {
        row["family_id"]: row for row in rows
        if not row["historical"] and row["event"] == "CONSUMED"
    }


def _revalidation_map(rows: list[dict]) -> dict[str, dict]:
    return {
        row["family_id"]: row for row in rows
        if not row["historical"] and row["event"] == "LEGACY_CONSUMPTION_RECLASSIFIED"
    }


def _reserve_locked(
    target: Path, rows: list[dict], active: list[dict], historical: list[dict],
    *, consumer: str, request_id: str, max_count: int | None,
) -> tuple[list[dict], str]:
    reserved, consumed, outstanding = _lifecycle(rows)
    changed = []
    if outstanding:
        active_by_family = {row["family_id"]: row for row in active}
        changed = [
            family for family, row in outstanding.items()
            if family in active_by_family and (
                active_by_family[family]["corpus_review_receipt"],
                active_by_family[family]["corpus_review_sha256"],
            ) != (
                row["corpus_review_receipt"], row["corpus_review_sha256"],
            )
        ]
        if changed:
            if (
                not set(outstanding).issubset(active_by_family)
                or set(changed) != set(outstanding)
            ):
                raise NoveltyIntegrityError(
                    "outstanding request review refresh is partial or missing families"
                )
            rebound = []
            for family, prior in sorted(
                outstanding.items(), key=lambda item: item[1]["sequence"]
            ):
                current = active_by_family[family]
                if (
                    current["topic"] != prior["topic"]
                    or current["topic_sha256"] != prior["topic_sha256"]
                ):
                    raise NoveltyIntegrityError(
                        "review refresh cannot change reserved family/topic identity"
                    )
                rebound.append(dict(
                    current,
                    event="REVIEW_REFRESHED",
                    consumer="review-refresh:" + consumer,
                    request_id=prior["request_id"],
                    fulfilment_receipt="",
                    fulfilment_sha256="",
                ))
            review_bindings = {
                (row["corpus_review_receipt"], row["corpus_review_sha256"])
                for row in rebound
            }
            if len(review_bindings) != 1:
                raise NoveltyIntegrityError(
                    "one outstanding request cannot refresh across review groups"
                )
            _validate_review_receipt(
                rebound, allow_bound_subset=True, recompute_current_audit=True
            )
            rows = _append_events_atomic(target, rows, rebound)
            reserved, consumed, outstanding = _lifecycle(rows)
    same_request = sorted(
        (row for row in outstanding.values() if row["request_id"] == request_id),
        key=lambda row: row["sequence"],
    )
    if same_request:
        return same_request, "REVIEW_REFRESHED" if changed else "SAME_REQUEST_RESERVED"
    if outstanding:
        return (
            sorted(outstanding.values(), key=lambda row: row["sequence"]),
            "REVIEW_REFRESHED_REFERENCE" if changed else "OUTSTANDING_REFERENCE",
        )
    request_date = request_id.split(":", 1)[1]
    if any(
        not row.get("historical")
        and row.get("event") in {
            "DRAFTED_BLOCKED", "CONSUMED", "LEGACY_CONSUMPTION_RECLASSIFIED",
        }
        and str(row.get("request_id") or "").endswith(":" + request_date)
        for row in rows
    ):
        return [], "ALREADY_TERMINAL_FOR_DATE"
    events = []
    known_families = set(reserved) | set(consumed)
    known_topics = {row["topic_sha256"] for row in rows}
    for row in historical:
        if row["family_id"] in known_families or row["topic_sha256"] in known_topics:
            continue
        events.append(dict(
            row, event="CONSUMED", consumer="historical-bootstrap",
            request_id=HISTORICAL_REQUEST_ID,
            fulfilment_receipt="orders.txt#historical",
            fulfilment_sha256=topic_sha256(row["topic"]),
        ))
        known_families.add(row["family_id"])
        known_topics.add(row["topic_sha256"])
    selected = []
    selected_review = None
    for row in active:
        if row["family_id"] in known_families or row["topic_sha256"] in known_topics:
            continue
        row_review = (
            row["corpus_review_receipt"], row["corpus_review_sha256"]
        )
        if selected_review is None:
            selected_review = row_review
        elif row_review != selected_review:
            # One request/pack can bind exactly one pre-generation review.
            # Leave other valid groups unreserved for the next lifecycle run.
            continue
        if max_count is not None and len(selected) >= max_count:
            break
        selected.append(row)
        known_families.add(row["family_id"])
        known_topics.add(row["topic_sha256"])
    if selected:
        _validate_review_receipt(
            selected,
            allow_bound_subset=True,
            recompute_current_audit=True,
        )
    events.extend(dict(
        row, event="RESERVED", consumer=consumer, request_id=request_id,
        fulfilment_receipt="", fulfilment_sha256="",
    ) for row in selected)
    if events:
        committed = _append_events_atomic(target, rows, events)
        return (
            [row for row in committed if row["event"] == "RESERVED"
             and row["request_id"] == request_id],
            "NEW_RESERVED" if selected else "NOVELTY_EXHAUSTED",
        )
    return [], "NOVELTY_EXHAUSTED"


def claim_novel_orders(
    active: list[dict], historical: list[dict], *, consumer: str,
    request_id: str, ledger_path: str | os.PathLike[str],
    max_count: int | None = None, return_mode: bool = False,
) -> list[dict] | tuple[list[dict], str]:
    """Compatibility name: atomically reserve, never consume, active families."""
    _validate_candidates(active, historical, request_id)
    target = Path(ledger_path)
    with _claim_lock(target):
        rows = read_consumed_ledger(target)
        selected, mode = _reserve_locked(
            target, rows, active, historical, consumer=consumer,
            request_id=request_id, max_count=max_count,
        )
        return (selected, mode) if return_mode else selected


def select_daily_order_atomic(
    active: list[dict], historical: list[dict], *, request_id: str,
    ledger_path: str | os.PathLike[str],
) -> tuple[str, list[dict]]:
    """Choose reuse/reference/reservation under one lock with no read-claim gap."""
    _validate_candidates(active, historical, request_id)
    target = Path(ledger_path)
    with _claim_lock(target):
        rows = read_consumed_ledger(target)
        selected, mode = _reserve_locked(
            target, rows, active, historical,
            consumer="daily-content-local-request", request_id=request_id,
            max_count=1,
        )
        own = [row for row in selected if row["request_id"] == request_id]
        if own:
            return "DAILY_RESERVED", own[:1]
        dispatcher_request = "dispatcher:" + request_id.split(":", 1)[1]
        dispatch = [
            row for row in selected if row["request_id"] == dispatcher_request
        ]
        if dispatch:
            return "DISPATCHER_REFERENCE", dispatch
        return ("OUTSTANDING_REFERENCE" if selected else mode), selected


def _validate_fulfilment_receipt(
    receipt_path: str, receipt_sha256: str, reservations: list[dict],
    *, receipt_bytes: bytes | None = None,
    snapshot_for_consumption: bool = False,
) -> tuple[dict, dict]:
    supplied = str(receipt_sha256 or "").upper()
    canonical_receipt_path, resolved = _resolve_repo_evidence_path(receipt_path)
    if receipt_path != canonical_receipt_path:
        raise NoveltyIntegrityError("draft fulfilment receipt path is not canonical")
    if not SHA256_RE.fullmatch(supplied) or not resolved.is_file():
        raise NoveltyIntegrityError("draft fulfilment receipt is missing")
    if receipt_bytes is None:
        receipt_bytes = _read_hash_bound_bytes(
            resolved, supplied, "draft fulfilment receipt"
        )
    elif _sha256_bytes(receipt_bytes) != supplied:
        raise NoveltyIntegrityError("draft fulfilment receipt hash mismatch")
    payload = _load_json_bytes(receipt_bytes, resolved)
    top_keys = {
        "schema_version", "receipt_type", "producer", "fulfilment_state",
        "semantic_universality_claimed", "publication_authority", "release_state",
        "request_id", "created_at", "corpus_review", "pack", "families",
        "safety_audit", "copy_corpus_audit", "relevance_audit",
        "audit_engine", "explicit_non_authority",
    }
    request_ids = {row["request_id"] for row in reservations}
    if set(payload) != top_keys or (
        payload.get("schema_version") != FULFILMENT_SCHEMA_VERSION
        or payload.get("receipt_type") != FULFILMENT_RECEIPT_TYPE
        or payload.get("producer") != FULFILMENT_PRODUCER
        or payload.get("fulfilment_state") != "DRAFT_FULFILLED_BLOCKED"
        or payload.get("semantic_universality_claimed") is not False
        or payload.get("publication_authority") != "NONE"
        or payload.get("release_state") != "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW"
        or len(request_ids) != 1
        or payload.get("request_id") not in request_ids
        or not isinstance(payload.get("created_at"), str)
        or not payload.get("created_at")
        or not isinstance(payload.get("explicit_non_authority"), str)
        or not payload.get("explicit_non_authority")
    ):
        raise NoveltyIntegrityError("draft fulfilment receipt exact schema is invalid")
    audit_engine = payload.get("audit_engine")
    if (
        not isinstance(audit_engine, dict)
        or set(audit_engine) != {"path", "sha256"}
        or audit_engine.get("path") != AUDIT_ENGINE_RELATIVE
    ):
        raise NoveltyIntegrityError("draft fulfilment audit-engine binding is invalid")
    audit_engine_runtime = _load_bound_audit_engine(
        expected_sha256=str(audit_engine.get("sha256") or ""),
        label="draft fulfilment audit engine",
    )
    preliminary_corpus = payload.get("corpus_review")
    if not isinstance(preliminary_corpus, dict) or set(preliminary_corpus) != {
        "path", "sha256",
    }:
        raise NoveltyIntegrityError("draft fulfilment has no corpus-review binding")
    preliminary_corpus_path = str(preliminary_corpus.get("path") or "")
    preliminary_corpus_sha = str(preliminary_corpus.get("sha256") or "").upper()
    canonical_preliminary, preliminary_resolved = _resolve_repo_evidence_path(
        preliminary_corpus_path
    )
    if preliminary_corpus_path != canonical_preliminary:
        raise NoveltyIntegrityError("draft fulfilment corpus-review path is not canonical")
    review_bytes = _read_hash_bound_bytes(
        preliminary_resolved, preliminary_corpus_sha, "corpus-review receipt"
    )
    review_preview = _load_json_bytes(review_bytes, preliminary_resolved)
    preview_candidate, _preview_path = _resolve_repo_candidate_path(
        str(review_preview.get("candidate_path") or "")
    )
    captured_corpus, _captured_inputs = _capture_corpus_bytes(preview_candidate)
    review_groups = _validate_review_receipt(
        reservations,
        allow_bound_subset=True,
        recompute_current_audit=True,
        preloaded_receipts={
            (preliminary_corpus_path, preliminary_corpus_sha): review_bytes
        },
        corpus_bytes=captured_corpus,
        audit_engine_runtime=audit_engine_runtime,
    )
    _recheck_bound_audit_engine(
        audit_engine_runtime,
        expected_sha256=str(audit_engine["sha256"]),
        label="draft fulfilment audit engine",
    )
    if len(review_groups) != 1:
        raise NoveltyIntegrityError(
            "one draft fulfilment cannot span multiple corpus-review receipts"
        )
    review_payload = next(iter(review_groups.values()))
    pack = payload.get("pack")
    if not isinstance(pack, dict) or set(pack) != {
        "path", "sha256", "status", "platform_variants",
        "semantic_family_ids", "request_id",
    }:
        raise NoveltyIntegrityError("draft fulfilment receipt has no exact pack binding")
    canonical_pack_path, pack_path = _resolve_repo_candidate_path(
        str(pack.get("path") or "")
    )
    pack_sha = str(pack.get("sha256") or "").upper()
    if (
        pack.get("path") != canonical_pack_path
        or canonical_pack_path != review_payload.get("candidate_path")
        or not pack_path.is_file()
        or not SHA256_RE.fullmatch(pack_sha)
        or pack.get("status") != "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW"
        or pack.get("request_id") != payload["request_id"]
    ):
        raise NoveltyIntegrityError("draft fulfilment pack binding is mismatched")
    try:
        pack_bytes = _read_hash_bound_bytes(
            pack_path, pack_sha, "draft fulfilment pack"
        )
        pack_text = pack_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise NoveltyIntegrityError("draft fulfilment pack is unreadable") from exc
    family_ids = [row["family_id"] for row in reservations]
    if (
        len(pack_bytes) < 1000
        or pack.get("platform_variants") != len(reservations) * 3
        or pack.get("semantic_family_ids") != family_ids
        or ("- `request_id`: `" + payload["request_id"] + "`") not in pack_text
        or "- `status`: `DRAFT_ONLY_BLOCKED_SOURCE_REVIEW`" not in pack_text
        or "- `publication_authority`: `NONE`" not in pack_text
        or "- `novelty_review_state`: `PROVISIONAL_LOCAL_REVIEW`" not in pack_text
        or "- `semantic_universality_claimed`: `FALSE`" not in pack_text
        or pack_text.count("### Threads") != len(reservations)
        or pack_text.count("### Facebook") != len(reservations)
        or pack_text.count("### TikTok") != len(reservations)
        or any(
            pack_text.count("- `family_id`: `" + family + "`") != 1
            for family in family_ids
        )
    ):
        raise NoveltyIntegrityError(
            "draft fulfilment pack lacks exact request/family/platform semantics"
        )
    corpus_binding = payload.get("corpus_review")
    if not isinstance(corpus_binding, dict) or set(corpus_binding) != {"path", "sha256"}:
        raise NoveltyIntegrityError("draft fulfilment has no corpus-review binding")
    corpus_path = str(corpus_binding.get("path") or "")
    corpus_sha = str(corpus_binding.get("sha256") or "").upper()
    canonical_corpus_path, resolved_corpus_path = _resolve_repo_evidence_path(corpus_path)
    if (
        corpus_path != canonical_corpus_path
        or not SHA256_RE.fullmatch(corpus_sha)
        or not resolved_corpus_path.is_file()
        or (corpus_path, corpus_sha) not in review_groups
    ):
        raise NoveltyIntegrityError("draft fulfilment corpus-review binding is mismatched")
    family_items = payload.get("families")
    if not isinstance(family_items, list) or any(
        not isinstance(item, dict) or set(item) != {"family_id", "topic_sha256"}
        for item in family_items
    ):
        raise NoveltyIntegrityError("draft fulfilment family schema is invalid")
    families = {
        str(item["family_id"]): str(item["topic_sha256"]).upper()
        for item in family_items
    }
    expected_families = {
        row["family_id"]: row["topic_sha256"] for row in reservations
    }
    if len(families) != len(family_items) or families != expected_families or any(
        row["corpus_review_receipt"] != corpus_path
        or row["corpus_review_sha256"] != corpus_sha
        for row in reservations
    ):
        raise NoveltyIntegrityError(
            "draft fulfilment does not bind exact reserved family/topic/review set"
        )
    engine_module = audit_engine_runtime["module"]
    try:
        computed_pack_audit = engine_module.audit_pack_text(
            ROOT, canonical_pack_path, reservations, pack_text, captured_corpus
        )
    except engine_module.ContentPackAuditError as exc:
        raise NoveltyIntegrityError(
            "draft fulfilment pack audit cannot be recomputed: " + str(exc)
        ) from exc
    safety = payload.get("safety_audit")
    safety_keys = {
        "first_person_hits", "url_hits", "commercial_or_tracking_hits",
        "guarantee_hits", "live_link_dependency_hits", "comply_gate_failures",
    }
    if (
        not isinstance(safety, dict)
        or set(safety) != safety_keys
        or any(type(safety[name]) is not int or safety[name] != 0 for name in safety_keys)
        or safety != computed_pack_audit["safety_audit"]
    ):
        raise NoveltyIntegrityError("draft fulfilment safety audit is incomplete or failing")
    copy_audit = payload.get("copy_corpus_audit")
    copy_keys = {
        "candidate_variants", "historical_records", "unique_historical_normal_forms",
        "historical_exact_collisions", "historical_near_collisions",
        "cross_family_exact_collisions", "cross_family_near_collisions",
    }
    collision_keys = copy_keys - {
        "candidate_variants", "historical_records", "unique_historical_normal_forms",
    }
    if (
        not isinstance(copy_audit, dict)
        or set(copy_audit) != copy_keys
        or copy_audit.get("candidate_variants") != len(reservations) * 3
        or type(copy_audit.get("historical_records")) is not int
        or copy_audit.get("historical_records") < 1
        or type(copy_audit.get("unique_historical_normal_forms")) is not int
        or copy_audit.get("unique_historical_normal_forms") < 1
        or any(copy_audit.get(name) != 0 for name in collision_keys)
        or copy_audit != computed_pack_audit["copy_corpus_audit"]
    ):
        raise NoveltyIntegrityError("draft fulfilment copy-corpus audit is incomplete or failing")
    relevance = payload.get("relevance_audit")
    if (
        not isinstance(relevance, dict)
        or relevance != computed_pack_audit["relevance_audit"]
        or relevance.get("mechanical_relevance_only") is not True
        or relevance.get("family_count") != len(reservations)
        or relevance.get("candidate_variants") != len(reservations) * 3
        or relevance.get("families_below_threshold") != 0
    ):
        raise NoveltyIntegrityError(
            "draft fulfilment copy is not mechanically bound to reserved topics"
        )
    _recheck_bound_audit_engine(
        audit_engine_runtime,
        expected_sha256=str(audit_engine["sha256"]),
        label="draft fulfilment audit engine",
    )
    if snapshot_for_consumption:
        artifacts = [
            {"role": "fulfilment_receipt", "path": receipt_path, "bytes": receipt_bytes},
            {
                "role": "corpus_review_receipt",
                "path": preliminary_corpus_path,
                "bytes": review_bytes,
            },
            {"role": "candidate_pack", "path": canonical_pack_path, "bytes": pack_bytes},
            {
                "role": "audit_engine", "path": AUDIT_ENGINE_RELATIVE,
                "bytes": audit_engine_runtime["bytes"],
            },
        ]
        artifacts.extend(
            {"role": "corpus_input", "path": path, "bytes": data}
            for path, data in captured_corpus.items()
        )
        _write_consumption_snapshot(supplied, artifacts)
    return payload, audit_engine_runtime


def fulfil_reservations(
    family_ids: list[str], *, receipt_path: str, receipt_sha256: str,
    ledger_path: str | os.PathLike[str],
) -> list[dict]:
    """Append draft fulfilment transitions; never grants publication readiness."""
    target = Path(ledger_path)
    wanted = list(dict.fromkeys(family_ids))
    if not wanted or len(wanted) != len(family_ids):
        raise NoveltyIntegrityError("fulfilment family set is empty or duplicated")
    with _claim_lock(target):
        rows = read_consumed_ledger(target)
        _reserved, consumed, outstanding = _lifecycle(rows)
        drafted = _drafted_map(rows)
        terminal = dict(drafted, **consumed)
        if all(family in terminal for family in wanted):
            existing = [terminal[family] for family in wanted]
            if any(
                row["fulfilment_receipt"] != receipt_path
                or row["fulfilment_sha256"] != receipt_sha256.upper()
                for row in existing
            ):
                raise NoveltyIntegrityError("existing fulfilment binding differs")
            return existing
        if any(family not in outstanding for family in wanted):
            raise NoveltyIntegrityError("fulfilment targets are not outstanding reservations")
        reservations = [outstanding[family] for family in wanted]
        payload, audit_engine_runtime = _validate_fulfilment_receipt(
            receipt_path, receipt_sha256, reservations,
            snapshot_for_consumption=True,
        )
        _recheck_bound_audit_engine(
            audit_engine_runtime,
            expected_sha256=str(payload["audit_engine"]["sha256"]),
            label="draft fulfilment audit engine",
        )
        events = [dict(
            row, event="DRAFTED_BLOCKED", consumer="local-draft-fulfilment",
            fulfilment_receipt=receipt_path,
            fulfilment_sha256=receipt_sha256.upper(),
        ) for row in reservations]
        committed = _append_events_atomic(target, rows, events)
        return [
            row for row in committed
            if row["event"] == "DRAFTED_BLOCKED" and row["family_id"] in wanted
            and not row["historical"]
        ]


def fulfil_outstanding_from_receipt(
    *, receipt_path: str, receipt_sha256: str,
    ledger_path: str | os.PathLike[str],
) -> list[dict]:
    """Fulfil exactly one outstanding request declared by a strict receipt."""
    target = Path(ledger_path)
    supplied = str(receipt_sha256 or "").upper()
    canonical_receipt, resolved = _resolve_repo_evidence_path(receipt_path)
    if receipt_path != canonical_receipt:
        raise NoveltyIntegrityError("draft fulfilment receipt path is not canonical")
    if not SHA256_RE.fullmatch(supplied) or not resolved.is_file():
        raise NoveltyIntegrityError("draft fulfilment receipt is missing")
    receipt_bytes = _read_hash_bound_bytes(
        resolved, supplied, "draft fulfilment receipt"
    )
    receipt_payload = _load_json_bytes(receipt_bytes, resolved)
    with _claim_lock(target):
        rows = read_consumed_ledger(target)
        request_id = str(receipt_payload.get("request_id") or "")
        family_items = receipt_payload.get("families")
        if not _valid_request_id(request_id) or not isinstance(family_items, list):
            raise NoveltyIntegrityError(
                "strict fulfilment receipt lacks a valid request/family declaration"
            )
        wanted = [
            str(item.get("family_id") or "")
            for item in family_items if isinstance(item, dict)
        ]
        if (
            not wanted
            or len(wanted) != len(family_items)
            or len(set(wanted)) != len(wanted)
        ):
            raise NoveltyIntegrityError("strict fulfilment receipt family set is invalid")
        _reserved, consumed, outstanding = _lifecycle(rows)
        drafted = _drafted_map(rows)
        reservations = sorted(
            (
                row for row in outstanding.values()
                if row["request_id"] == request_id
            ),
            key=lambda row: row["sequence"],
        )
        if not reservations:
            terminal = dict(drafted, **consumed)
            if all(family in terminal for family in wanted):
                existing = [terminal[family] for family in wanted]
                if any(
                    row["request_id"] != request_id
                    or row["fulfilment_receipt"] != receipt_path
                    or row["fulfilment_sha256"] != supplied
                    for row in existing
                ):
                    raise NoveltyIntegrityError("existing fulfilment binding differs")
                return existing
            raise NoveltyIntegrityError("receipt request has no outstanding reservation")
        if {row["family_id"] for row in reservations} != set(wanted):
            raise NoveltyIntegrityError(
                "receipt families do not exactly match its outstanding request"
            )
        payload, audit_engine_runtime = _validate_fulfilment_receipt(
            receipt_path, supplied, reservations, receipt_bytes=receipt_bytes,
            snapshot_for_consumption=True,
        )
        _recheck_bound_audit_engine(
            audit_engine_runtime,
            expected_sha256=str(payload["audit_engine"]["sha256"]),
            label="draft fulfilment audit engine",
        )
        events = [dict(
            row, event="DRAFTED_BLOCKED", consumer="local-draft-fulfilment",
            fulfilment_receipt=receipt_path, fulfilment_sha256=supplied,
        ) for row in reservations]
        committed = _append_events_atomic(target, rows, events)
        return [
            row for row in committed
            if row["event"] == "DRAFTED_BLOCKED"
            and row["request_id"] == request_id
            and row["family_id"] in set(wanted)
            and not row["historical"]
        ]


def _strict_revalidation_payload_locked(
    consumed_rows: list[dict], *, ledger_path: str | os.PathLike[str],
    strict_corpus_review_path: str, strict_corpus_review_sha256: str,
) -> dict:
    """Build deterministic v2 evidence while the lifecycle lock is held.

    The caller may serialize this value as a new immutable receipt.  This
    function never edits the legacy receipt or lifecycle ledger.
    """
    target = Path(ledger_path).resolve()
    try:
        ledger_relative = target.relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise NoveltyIntegrityError("revalidation ledger is outside repo root") from exc
    ordered = sorted(consumed_rows, key=lambda row: row["sequence"])
    if not ordered or any(row.get("historical") for row in ordered):
        raise NoveltyIntegrityError("strict revalidation requires nonhistorical consumed rows")
    legacy_bindings = {
        (row.get("fulfilment_receipt"), row.get("fulfilment_sha256"))
        for row in ordered
    }
    if len(legacy_bindings) != 1:
        raise NoveltyIntegrityError("legacy consumed rows do not share one fulfilment binding")
    legacy_path, legacy_sha = next(iter(legacy_bindings))
    canonical_legacy, legacy_resolved = _resolve_repo_evidence_path(str(legacy_path))
    if (
        legacy_path != canonical_legacy
        or not SHA256_RE.fullmatch(str(legacy_sha or "").upper())
        or not legacy_resolved.is_file()
    ):
        raise NoveltyIntegrityError("legacy fulfilment binding is missing or mismatched")
    legacy_bytes = _read_hash_bound_bytes(
        legacy_resolved, str(legacy_sha).upper(), "legacy fulfilment receipt"
    )
    legacy_payload = _load_json_bytes(legacy_bytes, legacy_resolved)
    if (
        legacy_payload.get("schema_version") != 1
        or legacy_payload.get("receipt_type") != FULFILMENT_RECEIPT_TYPE
        or legacy_payload.get("publication_authority") != "NONE"
        or legacy_payload.get("release_state") != "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW"
    ):
        raise NoveltyIntegrityError("legacy fulfilment is not the expected blocked v1 receipt")
    strict_path, strict_resolved = _resolve_repo_evidence_path(strict_corpus_review_path)
    strict_sha = str(strict_corpus_review_sha256 or "").upper()
    if (
        strict_corpus_review_path != strict_path
        or not SHA256_RE.fullmatch(strict_sha)
        or not strict_resolved.is_file()
    ):
        raise NoveltyIntegrityError("strict corpus-review binding is missing or mismatched")
    strict_bytes = _read_hash_bound_bytes(
        strict_resolved, strict_sha, "strict corpus-review receipt"
    )
    strict_preview = _load_json_bytes(strict_bytes, strict_resolved)
    candidate_path, _candidate_resolved = _resolve_repo_candidate_path(
        str(strict_preview.get("candidate_path") or "")
    )
    audit_engine_runtime = _load_bound_audit_engine(
        label="legacy strict audit engine"
    )
    captured_corpus, _captured_inputs = _capture_corpus_bytes(candidate_path)
    rebound = [dict(
        row,
        corpus_review_receipt=strict_path,
        corpus_review_sha256=strict_sha,
    ) for row in ordered]
    review_groups = _validate_review_receipt(
        rebound,
        preloaded_receipts={(strict_path, strict_sha): strict_bytes},
        corpus_bytes=captured_corpus,
        audit_engine_runtime=audit_engine_runtime,
    )
    _recheck_bound_audit_engine(
        audit_engine_runtime, label="legacy strict audit engine"
    )
    if len(review_groups) != 1:
        raise NoveltyIntegrityError("strict revalidation needs one corpus-review receipt")
    review_payload = next(iter(review_groups.values()))
    pack = legacy_payload.get("pack")
    if not isinstance(pack, dict):
        raise NoveltyIntegrityError("legacy fulfilment has no pack binding")
    pack_relative, pack_path = _resolve_repo_candidate_path(str(pack.get("path") or ""))
    pack_sha = str(pack.get("sha256") or "").upper()
    if (
        pack.get("path") != pack_relative
        or pack_relative != review_payload.get("candidate_path")
        or not pack_path.is_file()
        or not SHA256_RE.fullmatch(pack_sha)
    ):
        raise NoveltyIntegrityError("legacy pack cannot be strictly rebound")
    engine_module = audit_engine_runtime["module"]
    try:
        pack_bytes = _read_hash_bound_bytes(
            pack_path, pack_sha, "legacy strict pack"
        )
        pack_text = pack_bytes.decode("utf-8")
        computed_pack = engine_module.audit_pack_text(
            ROOT, pack_relative, rebound, pack_text, captured_corpus
        )
    except (UnicodeError, engine_module.ContentPackAuditError) as exc:
        raise NoveltyIntegrityError("legacy pack strict audit failed: " + str(exc)) from exc
    _recheck_bound_audit_engine(
        audit_engine_runtime,
        label="legacy strict audit engine",
    )
    snapshot_artifacts = [
        {"role": "fulfilment_receipt", "path": canonical_legacy, "bytes": legacy_bytes},
        {"role": "corpus_review_receipt", "path": strict_path, "bytes": strict_bytes},
        {"role": "candidate_pack", "path": pack_relative, "bytes": pack_bytes},
        {
            "role": "audit_engine", "path": AUDIT_ENGINE_RELATIVE,
            "bytes": audit_engine_runtime["bytes"],
        },
    ]
    snapshot_artifacts.extend(
        {"role": "corpus_input", "path": path, "bytes": data}
        for path, data in captured_corpus.items()
    )
    _recheck_bound_audit_engine(
        audit_engine_runtime,
        label="legacy strict audit engine",
    )
    snapshot_binding = _write_consumption_snapshot(
        str(legacy_sha).upper(), snapshot_artifacts
    )
    _recheck_bound_audit_engine(
        audit_engine_runtime,
        label="legacy strict audit engine",
    )
    review_audit = review_payload["corpus_audit"]
    ledger_rows = read_consumed_ledger(target)
    checkpoint_sequence = max(row["sequence"] for row in ordered)
    prefix_rows = ledger_rows[:checkpoint_sequence]
    if (
        len(prefix_rows) != checkpoint_sequence
        or prefix_rows[-1]["sequence"] != checkpoint_sequence
    ):
        raise NoveltyIntegrityError("legacy consumed rows do not bind a complete ledger prefix")
    checkpoint_head = prefix_rows[-1]["record_hash"]
    return {
        "schema_version": STRICT_REVALIDATION_SCHEMA_VERSION,
        "receipt_type": STRICT_REVALIDATION_RECEIPT_TYPE,
        "producer": STRICT_REVALIDATION_PRODUCER,
        "revalidation_state": "STRICT_REVALIDATED_BLOCKED",
        "semantic_universality_claimed": False,
        "publication_authority": "NONE",
        "release_state": "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW",
        "created_at": "2026-08-25T00:00:00+07:00",
        "ledger": {
            "path": ledger_relative,
            "prefix_sequence": checkpoint_sequence,
            "prefix_head": checkpoint_head,
            "ledger_prefix_sha256": _sha256_bytes(_ledger_bytes(prefix_rows)),
        },
        "legacy_fulfilment": {
            "path": canonical_legacy,
            "sha256": str(legacy_sha).upper(),
        },
        "pack": {
            "path": pack_relative,
            "sha256": pack_sha,
            "status": "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW",
            "request_id": ordered[0]["request_id"],
            "platform_variants": len(ordered) * 3,
        },
        "strict_corpus_review": {"path": strict_path, "sha256": strict_sha},
        "evidence_snapshot": snapshot_binding,
        "audit_engine": {
            "path": AUDIT_ENGINE_RELATIVE,
            "sha256": audit_engine_runtime["sha256"],
        },
        "families": [{
            "family_id": row["family_id"],
            "topic": row["topic"],
            "topic_sha256": row["topic_sha256"],
            "consumed_record_hash": row["record_hash"],
        } for row in ordered],
        "recomputed": {
            "corpus_audit": review_audit,
            "safety_audit": computed_pack["safety_audit"],
            "copy_corpus_audit": computed_pack["copy_corpus_audit"],
            "relevance_audit": computed_pack["relevance_audit"],
        },
        "explicit_non_authority": (
            "Strict local revalidation of legacy consumed draft evidence only; "
            "no source, claim, media, schedule, release, or publication authority."
        ),
    }


def strict_revalidation_payload(
    consumed_rows: list[dict], *, ledger_path: str | os.PathLike[str],
    strict_corpus_review_path: str, strict_corpus_review_sha256: str,
) -> dict:
    """Recover/read one coherent ledger view and build a strict cutover receipt."""
    target = Path(ledger_path).resolve()
    with _claim_lock(target):
        # The internal builder re-reads under this same lock to bind the exact
        # current prefix and rejects supplied rows that are not in that prefix.
        return _strict_revalidation_payload_locked(
            consumed_rows, ledger_path=target,
            strict_corpus_review_path=strict_corpus_review_path,
            strict_corpus_review_sha256=strict_corpus_review_sha256,
        )


def _validate_archived_pack_audits(payload: dict, ordered: list[dict]) -> None:
    """Validate the immutable v1 audit result schema without running live code.

    Admission re-executes the then-current, hash-bound engine before appending
    DRAFTED_BLOCKED.  Historical verification instead validates the archived
    engine blob and the exact result contract so a harmless live engine upgrade
    cannot rewrite or invalidate earlier evidence.
    """
    safety = payload.get("safety_audit")
    safety_keys = {
        "first_person_hits", "url_hits", "commercial_or_tracking_hits",
        "guarantee_hits", "live_link_dependency_hits", "comply_gate_failures",
    }
    if (
        not isinstance(safety, dict) or set(safety) != safety_keys
        or any(type(safety[key]) is not int or safety[key] != 0 for key in safety_keys)
    ):
        raise NoveltyIntegrityError("archived draft safety audit is invalid")

    copy_audit = payload.get("copy_corpus_audit")
    copy_keys = {
        "candidate_variants", "historical_records", "unique_historical_normal_forms",
        "historical_exact_collisions", "historical_near_collisions",
        "cross_family_exact_collisions", "cross_family_near_collisions",
    }
    collision_keys = copy_keys - {
        "candidate_variants", "historical_records", "unique_historical_normal_forms",
    }
    if (
        not isinstance(copy_audit, dict) or set(copy_audit) != copy_keys
        or copy_audit.get("candidate_variants") != len(ordered) * 3
        or type(copy_audit.get("historical_records")) is not int
        or copy_audit["historical_records"] < 1
        or type(copy_audit.get("unique_historical_normal_forms")) is not int
        or copy_audit["unique_historical_normal_forms"] < 1
        or any(copy_audit.get(key) != 0 for key in collision_keys)
    ):
        raise NoveltyIntegrityError("archived draft copy audit is invalid")

    relevance = payload.get("relevance_audit")
    relevance_keys = {
        "method", "mechanical_relevance_only",
        "minimum_platform_coverage_required",
        "minimum_combined_coverage_required", "family_count",
        "candidate_variants", "families_below_threshold", "families",
    }
    expected_rows = [{
        "family_id": row["family_id"],
        "topic_sha256": row["topic_sha256"],
    } for row in ordered]
    if (
        not isinstance(relevance, dict) or set(relevance) != relevance_keys
        or relevance.get("method")
        != "normalized-topic-character-trigram-containment-v1"
        or relevance.get("mechanical_relevance_only") is not True
        or relevance.get("minimum_platform_coverage_required") != 0.12
        or relevance.get("minimum_combined_coverage_required") != 0.30
        or relevance.get("family_count") != len(ordered)
        or relevance.get("candidate_variants") != len(ordered) * 3
        or relevance.get("families_below_threshold") != 0
        or not isinstance(relevance.get("families"), list)
        or len(relevance["families"]) != len(ordered)
    ):
        raise NoveltyIntegrityError("archived draft relevance audit is invalid")
    actual_rows = []
    for item in relevance["families"]:
        if not isinstance(item, dict) or set(item) != {
            "family_id", "topic_sha256", "minimum_platform_coverage",
            "combined_coverage", "passed",
        }:
            raise NoveltyIntegrityError("archived relevance family schema is invalid")
        if (
            item.get("passed") is not True
            or not isinstance(item.get("minimum_platform_coverage"), (int, float))
            or isinstance(item.get("minimum_platform_coverage"), bool)
            or not isinstance(item.get("combined_coverage"), (int, float))
            or isinstance(item.get("combined_coverage"), bool)
            or item["minimum_platform_coverage"] < 0.12
            or item["combined_coverage"] < 0.30
        ):
            raise NoveltyIntegrityError("archived relevance family result is failing")
        actual_rows.append({
            "family_id": item.get("family_id"),
            "topic_sha256": item.get("topic_sha256"),
        })
    if actual_rows != expected_rows:
        raise NoveltyIntegrityError("archived relevance family binding is invalid")


def _validate_terminal_v2_snapshot(
    group: list[dict], *, receipt_path: str, receipt_sha256: str,
    receipt_payload: dict, manifest: dict, snapshot: dict[str, bytes],
) -> None:
    """Validate exact immutable v2 admission evidence without live-engine replay."""
    top_keys = {
        "schema_version", "receipt_type", "producer", "fulfilment_state",
        "semantic_universality_claimed", "publication_authority", "release_state",
        "request_id", "created_at", "corpus_review", "pack", "families",
        "safety_audit", "copy_corpus_audit", "relevance_audit",
        "audit_engine", "explicit_non_authority",
    }
    ordered = sorted(group, key=lambda row: row["sequence"])
    request_ids = {row["request_id"] for row in ordered}
    if set(receipt_payload) != top_keys or (
        receipt_payload.get("schema_version") != FULFILMENT_SCHEMA_VERSION
        or receipt_payload.get("receipt_type") != FULFILMENT_RECEIPT_TYPE
        or receipt_payload.get("producer") != FULFILMENT_PRODUCER
        or receipt_payload.get("fulfilment_state") != "DRAFT_FULFILLED_BLOCKED"
        or receipt_payload.get("semantic_universality_claimed") is not False
        or receipt_payload.get("publication_authority") != "NONE"
        or receipt_payload.get("release_state") != "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW"
        or len(request_ids) != 1
        or receipt_payload.get("request_id") != next(iter(request_ids))
        or not isinstance(receipt_payload.get("created_at"), str)
        or not receipt_payload.get("created_at")
        or not isinstance(receipt_payload.get("explicit_non_authority"), str)
        or not receipt_payload.get("explicit_non_authority")
    ):
        raise NoveltyIntegrityError("terminal v2 fulfilment exact schema is invalid")
    review = receipt_payload.get("corpus_review")
    pack = receipt_payload.get("pack")
    engine = receipt_payload.get("audit_engine")
    if (
        not isinstance(review, dict) or set(review) != {"path", "sha256"}
        or not isinstance(pack, dict) or set(pack) != {
            "path", "sha256", "status", "platform_variants",
            "semantic_family_ids", "request_id",
        }
        or not isinstance(engine, dict) or set(engine) != {"path", "sha256"}
    ):
        raise NoveltyIntegrityError("terminal v2 nested binding schema is invalid")
    review_bytes = snapshot.get(str(review["path"]))
    if review_bytes is None:
        raise NoveltyIntegrityError("terminal v2 snapshot lacks its corpus review")
    review_payload = _load_json_bytes(
        review_bytes, ROOT / _snapshot_relative(receipt_sha256)
    )
    _validate_snapshot_artifact_contract(
        manifest, snapshot, receipt_path=receipt_path,
        receipt_sha256=receipt_sha256, receipt_payload=receipt_payload,
        review_payload=review_payload,
    )
    if (
        engine.get("path") != "pipeline/content_pack_audit.py"
        or snapshot.get("pipeline/content_pack_audit.py") is None
        or _sha256_bytes(snapshot["pipeline/content_pack_audit.py"])
        != str(engine.get("sha256") or "").upper()
    ):
        raise NoveltyIntegrityError("terminal v2 audit-engine evidence is mismatched")
    family_items = receipt_payload.get("families")
    expected_family_items = [{
        "family_id": row["family_id"], "topic_sha256": row["topic_sha256"],
    } for row in ordered]
    family_ids = [row["family_id"] for row in ordered]
    if (
        family_items != expected_family_items
        or pack.get("status") != "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW"
        or pack.get("platform_variants") != len(ordered) * 3
        or pack.get("semantic_family_ids") != family_ids
        or pack.get("request_id") != receipt_payload["request_id"]
        or any(
            row["corpus_review_receipt"] != review["path"]
            or row["corpus_review_sha256"] != str(review["sha256"]).upper()
            for row in ordered
        )
    ):
        raise NoveltyIntegrityError("terminal v2 family/review/pack binding is invalid")
    _validate_review_receipt(
        ordered, allow_bound_subset=True, recompute_current_audit=False,
        preloaded_receipts={
            (str(review["path"]), str(review["sha256"]).upper()): review_bytes
        },
    )
    pack_bytes = snapshot.get(str(pack["path"]))
    if len(pack_bytes or b"") < 1000:
        raise NoveltyIntegrityError("terminal v2 immutable pack evidence is incomplete")
    _validate_archived_pack_audits(receipt_payload, ordered)


def _validate_legacy_strict_revalidation(
    consumed_rows: list[dict], ledger_path: str | os.PathLike[str],
    *, require_anchor: bool = True,
    revalidation_bytes: bytes | None = None,
    revalidation_sha256: str | None = None,
    ledger_rows: list[dict] | None = None,
    replay_current_engine: bool = False,
) -> dict:
    canonical, resolved = _resolve_repo_evidence_path(STRICT_REVALIDATION_RELATIVE)
    if canonical != STRICT_REVALIDATION_RELATIVE:
        raise NoveltyIntegrityError("strict legacy revalidation path is invalid")
    if ledger_rows is None:
        ledger_rows = read_consumed_ledger(ledger_path)
    ordered = sorted(consumed_rows, key=lambda row: row["sequence"])
    expected_anchor_families = {row["family_id"] for row in ordered}
    anchors = _revalidation_map(ledger_rows)
    present_anchor_families = expected_anchor_families & set(anchors)
    if require_anchor and present_anchor_families != expected_anchor_families:
        raise NoveltyIntegrityError("legacy strict revalidation is not ledger-anchored")
    if revalidation_bytes is None:
        if not require_anchor:
            raise NoveltyIntegrityError("strict revalidation immutable bytes were not supplied")
        anchored_hashes = {
            anchors[family]["revalidation_sha256"] for family in expected_anchor_families
        }
        anchored_paths = {
            anchors[family]["revalidation_receipt"] for family in expected_anchor_families
        }
        if len(anchored_hashes) != 1 or anchored_paths != {STRICT_REVALIDATION_RELATIVE}:
            raise NoveltyIntegrityError("legacy revalidation anchors disagree")
        revalidation_sha256 = next(iter(anchored_hashes))
        revalidation_bytes = _load_strict_receipt_snapshot(revalidation_sha256)
    revalidation_sha = _sha256_bytes(revalidation_bytes)
    if (
        not SHA256_RE.fullmatch(str(revalidation_sha256 or "").upper())
        or revalidation_sha != str(revalidation_sha256).upper()
    ):
        raise NoveltyIntegrityError("strict revalidation immutable bytes/hash differ")
    payload = _load_json_bytes(revalidation_bytes, resolved)
    top_keys = {
        "schema_version", "receipt_type", "producer", "revalidation_state",
        "semantic_universality_claimed", "publication_authority", "release_state",
        "created_at", "ledger", "legacy_fulfilment", "pack",
        "strict_corpus_review", "evidence_snapshot", "audit_engine",
        "families", "recomputed",
        "explicit_non_authority",
    }
    if set(payload) != top_keys or (
        payload.get("schema_version") != STRICT_REVALIDATION_SCHEMA_VERSION
        or payload.get("receipt_type") != STRICT_REVALIDATION_RECEIPT_TYPE
        or payload.get("producer") != STRICT_REVALIDATION_PRODUCER
        or payload.get("revalidation_state") != "STRICT_REVALIDATED_BLOCKED"
        or payload.get("semantic_universality_claimed") is not False
        or payload.get("publication_authority") != "NONE"
        or payload.get("release_state") != "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW"
        or not isinstance(payload.get("created_at"), str)
        or not payload.get("created_at")
        or not isinstance(payload.get("explicit_non_authority"), str)
        or not payload.get("explicit_non_authority")
    ):
        raise NoveltyIntegrityError("strict legacy revalidation schema is invalid")
    strict_binding = payload.get("strict_corpus_review")
    if not isinstance(strict_binding, dict) or set(strict_binding) != {"path", "sha256"}:
        raise NoveltyIntegrityError("strict legacy revalidation corpus binding is invalid")
    snapshot_binding = payload.get("evidence_snapshot")
    if not isinstance(snapshot_binding, dict) or set(snapshot_binding) != {
        "path", "sha256", "bundle_sha256",
    }:
        raise NoveltyIntegrityError("strict legacy evidence-snapshot binding is invalid")
    ledger_binding = payload.get("ledger")
    target = Path(ledger_path).resolve()
    try:
        ledger_relative = target.relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise NoveltyIntegrityError("revalidation ledger is outside repo root") from exc
    if not isinstance(ledger_binding, dict) or set(ledger_binding) != {
        "path", "prefix_sequence", "prefix_head", "ledger_prefix_sha256",
    }:
        raise NoveltyIntegrityError("strict legacy revalidation ledger prefix is invalid")
    prefix_sequence = ledger_binding.get("prefix_sequence")
    if (
        ledger_binding.get("path") != ledger_relative
        or type(prefix_sequence) is not int
        or prefix_sequence < 1
        or prefix_sequence > len(ledger_rows)
    ):
        raise NoveltyIntegrityError("strict legacy revalidation ledger prefix is mismatched")
    prefix_rows = ledger_rows[:prefix_sequence]
    if (
        ledger_binding.get("prefix_head") != prefix_rows[-1]["record_hash"]
        or ledger_binding.get("ledger_prefix_sha256")
        != _sha256_bytes(_ledger_bytes(prefix_rows))
    ):
        raise NoveltyIntegrityError("strict legacy revalidation ledger prefix was tampered")
    expected_families = [{
        "family_id": row["family_id"], "topic": row["topic"],
        "topic_sha256": row["topic_sha256"],
        "consumed_record_hash": row["record_hash"],
    } for row in ordered]
    if payload.get("families") != expected_families or any(
        row["sequence"] > prefix_sequence for row in ordered
    ):
        raise NoveltyIntegrityError("strict legacy revalidation family records are mismatched")
    legacy_binding = payload.get("legacy_fulfilment")
    if not isinstance(legacy_binding, dict) or set(legacy_binding) != {"path", "sha256"}:
        raise NoveltyIntegrityError("strict legacy fulfilment binding is invalid")
    expected_legacy = {
        (row["fulfilment_receipt"], row["fulfilment_sha256"]) for row in ordered
    }
    if len(expected_legacy) != 1 or (
        legacy_binding.get("path"), legacy_binding.get("sha256")
    ) != next(iter(expected_legacy)):
        raise NoveltyIntegrityError("strict legacy fulfilment binding differs from ledger")
    snapshot_manifest, snapshot = _load_consumption_snapshot(
        legacy_binding["sha256"]
    )
    snapshot_path = (ROOT / _snapshot_relative(legacy_binding["sha256"])).resolve()
    if (
        snapshot_binding.get("path") != _snapshot_relative(legacy_binding["sha256"])
        or snapshot_binding.get("sha256") != _sha256_file(snapshot_path)
        or snapshot_binding.get("bundle_sha256")
        != snapshot_manifest.get("bundle_sha256")
    ):
        raise NoveltyIntegrityError("strict legacy evidence snapshot is mismatched")
    legacy_bytes = snapshot.get(legacy_binding["path"])
    strict_bytes = snapshot.get(strict_binding["path"])
    if (
        legacy_bytes is None
        or _sha256_bytes(legacy_bytes) != legacy_binding["sha256"]
        or strict_bytes is None
        or _sha256_bytes(strict_bytes) != strict_binding["sha256"]
    ):
        raise NoveltyIntegrityError("strict legacy snapshot lacks receipt evidence")
    legacy_payload = _load_json_bytes(legacy_bytes, resolved)
    strict_payload = _load_json_bytes(strict_bytes, resolved)
    pack_binding = payload.get("pack")
    if not isinstance(pack_binding, dict) or set(pack_binding) != {
        "path", "sha256", "status", "request_id", "platform_variants",
    }:
        raise NoveltyIntegrityError("strict legacy pack binding is invalid")
    legacy_pack = legacy_payload.get("pack")
    if (
        not isinstance(legacy_pack, dict)
        or pack_binding.get("path") != legacy_pack.get("path")
        or pack_binding.get("sha256") != legacy_pack.get("sha256")
        or pack_binding.get("status") != "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW"
        or pack_binding.get("request_id") != ordered[0]["request_id"]
        or pack_binding.get("platform_variants") != len(ordered) * 3
        or strict_payload.get("candidate_path") != pack_binding.get("path")
    ):
        raise NoveltyIntegrityError("strict legacy pack binding differs from immutable evidence")
    pack_bytes = snapshot.get(pack_binding["path"])
    if pack_bytes is None or _sha256_bytes(pack_bytes) != pack_binding["sha256"]:
        raise NoveltyIntegrityError("strict legacy snapshot lacks pack evidence")
    strict_family_map = {
        item.get("family_id"): (item.get("topic"), item.get("topic_sha256"))
        for item in strict_payload.get("families", []) if isinstance(item, dict)
    }
    if strict_family_map != {
        row["family_id"]: (row["topic"], row["topic_sha256"]) for row in ordered
    }:
        raise NoveltyIntegrityError("strict corpus-review family map differs from ledger")
    engine = payload.get("audit_engine")
    if (
        not isinstance(engine, dict)
        or set(engine) != {"path", "sha256"}
        or engine.get("path") != AUDIT_ENGINE_RELATIVE
        or not SHA256_RE.fullmatch(str(engine.get("sha256") or ""))
        or snapshot.get(AUDIT_ENGINE_RELATIVE) is None
        or _sha256_bytes(snapshot[AUDIT_ENGINE_RELATIVE])
        != str(engine.get("sha256") or "").upper()
    ):
        raise NoveltyIntegrityError("strict legacy audit-engine binding is invalid")
    live_engine_runtime = None
    if replay_current_engine:
        live_engine_runtime = _load_bound_audit_engine(
            expected_sha256=str(engine.get("sha256") or ""),
            label="strict legacy audit engine",
        )
    snapshot_corpus = _validate_snapshot_artifact_contract(
        snapshot_manifest, snapshot,
        receipt_path=str(legacy_binding["path"]),
        receipt_sha256=str(legacy_binding["sha256"]),
        receipt_payload={
            "corpus_review": strict_binding,
            "pack": pack_binding,
            "audit_engine": engine,
        },
        review_payload=strict_payload,
    )
    rebound = [dict(
        row,
        corpus_review_receipt=str(strict_binding["path"]),
        corpus_review_sha256=str(strict_binding["sha256"]).upper(),
    ) for row in ordered]
    _validate_review_receipt(
        rebound, allow_bound_subset=False,
        recompute_current_audit=replay_current_engine,
        preloaded_receipts={
            (str(strict_binding["path"]), str(strict_binding["sha256"]).upper()): strict_bytes
        },
        corpus_bytes=snapshot_corpus if replay_current_engine else None,
        audit_engine_runtime=live_engine_runtime,
    )
    if replay_current_engine:
        _recheck_bound_audit_engine(
            live_engine_runtime,
            expected_sha256=str(engine.get("sha256") or ""),
            label="strict legacy audit engine",
        )
    recomputed = payload.get("recomputed")
    if not isinstance(recomputed, dict) or set(recomputed) != {
        "corpus_audit", "safety_audit", "copy_corpus_audit", "relevance_audit",
    }:
        raise NoveltyIntegrityError("strict legacy audit snapshot is invalid")
    if recomputed.get("corpus_audit") != strict_payload.get("corpus_audit"):
        raise NoveltyIntegrityError("strict legacy topic-audit snapshot is mismatched")
    archived_result = {
        "safety_audit": recomputed.get("safety_audit"),
        "copy_corpus_audit": recomputed.get("copy_corpus_audit"),
        "relevance_audit": recomputed.get("relevance_audit"),
    }
    _validate_archived_pack_audits(archived_result, ordered)
    if replay_current_engine:
        engine_module = live_engine_runtime["module"]
        try:
            strict_pack_audit = engine_module.audit_pack_text(
                ROOT, str(pack_binding["path"]), rebound,
                pack_bytes.decode("utf-8"), snapshot_corpus,
            )
        except (UnicodeError, engine_module.ContentPackAuditError) as exc:
            raise NoveltyIntegrityError("strict legacy pack replay failed") from exc
        if any(
            recomputed.get(key) != strict_pack_audit[key]
            for key in ("safety_audit", "copy_corpus_audit", "relevance_audit")
        ):
            raise NoveltyIntegrityError("strict legacy live admission replay differs")
        _recheck_bound_audit_engine(
            live_engine_runtime,
            expected_sha256=str(engine.get("sha256") or ""),
            label="strict legacy audit engine",
        )
    for family in present_anchor_families:
        anchor = anchors[family]
        if (
            anchor["revalidation_receipt"] != STRICT_REVALIDATION_RELATIVE
            or anchor["revalidation_sha256"] != revalidation_sha
            or anchor["snapshot_manifest_sha256"] != snapshot_binding["sha256"]
        ):
            raise NoveltyIntegrityError("legacy revalidation ledger anchor is mismatched")
    return payload


def record_strict_revalidation(
    *, receipt_path: str, receipt_sha256: str,
    ledger_path: str | os.PathLike[str],
) -> list[dict]:
    """Atomically reclassify legacy mechanical consumption to DRAFTED_BLOCKED."""
    supplied = str(receipt_sha256 or "").upper()
    canonical, resolved = _resolve_repo_evidence_path(receipt_path)
    if (
        canonical != STRICT_REVALIDATION_RELATIVE
        or receipt_path != canonical
        or not SHA256_RE.fullmatch(supplied)
    ):
        raise NoveltyIntegrityError("strict revalidation receipt binding is invalid")
    target = Path(ledger_path)
    with _claim_lock(target):
        rows = read_consumed_ledger(target)
        existing = _revalidation_map(rows)
        snapshot_path = _strict_receipt_snapshot_path(supplied)
        if snapshot_path.is_file():
            receipt_bytes = _load_strict_receipt_snapshot(supplied)
        else:
            receipt_bytes = _read_hash_bound_bytes(
                resolved, supplied, "strict revalidation receipt"
            )
        receipt_payload = _load_json_bytes(receipt_bytes, resolved)
        family_items = receipt_payload.get("families")
        if not isinstance(family_items, list) or not family_items:
            raise NoveltyIntegrityError("strict revalidation receipt has no family records")
        family_ids = [
            str(item.get("family_id") or "")
            for item in family_items if isinstance(item, dict)
        ]
        if (
            len(family_ids) != len(family_items)
            or len(set(family_ids)) != len(family_ids)
        ):
            raise NoveltyIntegrityError("strict revalidation family identity is invalid")
        consumed = _consumed_event_map(rows)
        selected = [consumed[family] for family in family_ids if family in consumed]
        if len(selected) != len(family_ids) or any(row["historical"] for row in selected):
            raise NoveltyIntegrityError("strict revalidation families are not consumed drafts")
        selected.sort(key=lambda row: row["sequence"])
        if all(family in existing for family in family_ids):
            _validate_legacy_strict_revalidation(
                selected, target, require_anchor=True,
                revalidation_bytes=receipt_bytes,
                revalidation_sha256=supplied,
                ledger_rows=rows,
                replay_current_engine=False,
            )
            return [existing[family] for family in family_ids]
        if any(family in existing for family in family_ids):
            raise NoveltyIntegrityError("strict revalidation anchor set is partial")
        # A new cutover must bind the current canonical receipt.  Read once for
        # validation, then compare the exact live bytes immediately before the
        # append.  Historical reruns above use the immutable snapshot instead.
        live_bytes = _read_hash_bound_bytes(
            resolved, supplied, "strict revalidation receipt"
        )
        if live_bytes != receipt_bytes:
            raise NoveltyIntegrityError("strict revalidation receipt snapshot/live differ")
        _validate_legacy_strict_revalidation(
            selected, target, require_anchor=False,
            revalidation_bytes=receipt_bytes,
            revalidation_sha256=supplied,
            ledger_rows=rows,
            replay_current_engine=True,
        )
        engine_binding = receipt_payload.get("audit_engine")
        if not isinstance(engine_binding, dict):
            raise NoveltyIntegrityError("strict revalidation audit engine is missing")
        live_engine_runtime = _load_bound_audit_engine(
            expected_sha256=str(engine_binding.get("sha256") or ""),
            label="strict revalidation audit engine",
        )
        if _read_hash_bound_bytes(
            resolved, supplied, "strict revalidation receipt"
        ) != receipt_bytes:
            raise NoveltyIntegrityError(
                "strict revalidation receipt changed before lifecycle commit"
            )
        _write_strict_receipt_snapshot(receipt_bytes, supplied)
        snapshot = receipt_payload.get("evidence_snapshot")
        if not isinstance(snapshot, dict) or not SHA256_RE.fullmatch(
            str(snapshot.get("sha256") or "")
        ):
            raise NoveltyIntegrityError("strict revalidation snapshot hash is invalid")
        _recheck_bound_audit_engine(
            live_engine_runtime,
            expected_sha256=str(engine_binding.get("sha256") or ""),
            label="strict revalidation audit engine",
        )
        events = [dict(
            row,
            event="LEGACY_CONSUMPTION_RECLASSIFIED",
            consumer="strict-legacy-reclassification",
            revalidation_receipt=canonical,
            revalidation_sha256=supplied,
            snapshot_manifest_sha256=str(snapshot["sha256"]).upper(),
        ) for row in selected]
        committed = _append_events_atomic(target, rows, events)
        anchors = _revalidation_map(committed)
        return [anchors[family] for family in family_ids]


def _validate_consumed_evidence_locked(
    rows: list[dict], ledger_path: str | os.PathLike[str],
) -> dict:
    """Validate terminal draft evidence from one coherent locked ledger view."""
    drafted = _drafted_map(rows)
    raw_consumed = _consumed_event_map(rows)
    reclassified = _revalidation_map(rows)
    unclassified = set(raw_consumed) - set(reclassified)
    if unclassified:
        raise NoveltyIntegrityError(
            "mechanical CONSUMED rows lack LEGACY_CONSUMPTION_RECLASSIFIED cutover"
        )
    terminal = sorted(
        (
            row for row in drafted.values()
            if row.get("event") == "DRAFTED_BLOCKED" and not row.get("historical")
        ),
        key=lambda row: row["sequence"],
    )
    groups = {}
    for row in terminal:
        groups.setdefault(
            (row["fulfilment_receipt"], row["fulfilment_sha256"]), []
        ).append(row)
    legacy_rows = []
    for (receipt_path, receipt_sha), group in groups.items():
        manifest, snapshot = _load_consumption_snapshot(receipt_sha)
        receipt_bytes = snapshot.get(receipt_path)
        if receipt_bytes is None or _sha256_bytes(receipt_bytes) != receipt_sha:
            raise NoveltyIntegrityError("draft snapshot lacks its fulfilment receipt")
        payload = _load_json_bytes(
            receipt_bytes, ROOT / _snapshot_relative(receipt_sha)
        )
        if payload.get("schema_version") == FULFILMENT_SCHEMA_VERSION:
            _validate_terminal_v2_snapshot(
                group, receipt_path=receipt_path, receipt_sha256=receipt_sha,
                receipt_payload=payload, manifest=manifest, snapshot=snapshot,
            )
        else:
            raise NoveltyIntegrityError("draft fulfilment has unknown schema")
    legacy_rows = sorted(
        (raw_consumed[family] for family in reclassified),
        key=lambda row: row["sequence"],
    )
    if legacy_rows:
        _validate_legacy_strict_revalidation(
            legacy_rows, ledger_path, ledger_rows=rows,
            require_anchor=True, replay_current_engine=False,
        )
    return {
        "state": "PASS" if terminal or legacy_rows else "PASS_EMPTY",
        "consumed": 0,
        "drafted_blocked": len(terminal) + len(legacy_rows),
        "legacy_reclassified": len(legacy_rows),
    }


def validate_consumed_evidence(
    ledger_path: str | os.PathLike[str],
) -> dict:
    """Lock, recover any torn append, then validate immutable terminal drafts."""
    target = Path(ledger_path)
    with _claim_lock(target):
        rows = read_consumed_ledger(target)
        return _validate_consumed_evidence_locked(rows, target)


def request_path(
    prefix: str, date: str, inbox: str | os.PathLike[str] | None = None,
) -> Path:
    return Path(inbox or INBOX) / (prefix + "-" + date + "-novelty-v3.md")


def _request_bytes(
    *, date: str, request_id: str, rows: list[dict], title: str,
    state: str = "QUEUED_NOVEL",
) -> bytes:
    ordered = sorted(rows, key=lambda row: row.get("sequence", 0))
    if ordered:
        hashes = [row["record_hash"] for row in ordered]
        binding = _sha256_bytes(_canonical_json(hashes).encode("utf-8"))
        lines = [
            "# " + title + " — " + date,
            "",
            "- state: " + state,
            "- request_id: " + request_id,
            "- lifecycle: RESERVED_NOT_CONSUMED",
            "- claim_record_head_hash: " + hashes[-1],
            "- claim_record_hashes_sha256: " + binding,
            "- generation: LOCAL_ONLY_NO_NETWORK_NO_PAID_LLM",
            "- publication_authority: NONE",
            "",
            "## Reserved semantic families",
        ]
        lines.extend(
            "- " + row["family_id"] + " — " + row["topic"]
            + "  record_hash=" + row["record_hash"]
            for row in ordered
        )
    else:
        lines = [
            "# " + title + " — " + date,
            "",
            "- state: NOVELTY_EXHAUSTED",
            "- request_id: " + request_id,
            "- action: DO_NOT_GENERATE_DO_NOT_CYCLE",
            "- generation: LOCAL_ONLY_NO_NETWORK_NO_PAID_LLM",
            "- publication_authority: NONE",
            "",
            "No unreserved semantic family exists in automation-log/orders.txt.",
            "Add a reviewed, receipt-bound family before generating again.",
        ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_request(
    path: Path, *, date: str, request_id: str, rows: list[dict], title: str,
    state: str = "QUEUED_NOVEL",
) -> None:
    _atomic_write(path, _request_bytes(
        date=date, request_id=request_id, rows=rows, title=title, state=state
    ))


def _reference_bytes(
    *, date: str, request_id: str, rows: list[dict], referenced_path: Path,
    title: str,
) -> bytes:
    ordered = sorted(rows, key=lambda row: row["sequence"])
    hashes = [row["record_hash"] for row in ordered]
    lines = [
        "# " + title + " — " + date,
        "",
        "- state: REFERENCE_DO_NOT_GENERATE_DUPLICATE",
        "- request_id: " + request_id,
        "- referenced_request_id: " + ordered[0]["request_id"],
        "- referenced_request_path: " + str(referenced_path),
        "- claim_record_head_hash: " + hashes[-1],
        "- claim_record_hashes_sha256: "
        + _sha256_bytes(_canonical_json(hashes).encode("utf-8")),
        "- action: REFERENCE_ONLY_DO_NOT_GENERATE_DUPLICATE",
        "- publication_authority: NONE",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_reference(
    path: Path, *, date: str, request_id: str, rows: list[dict],
    referenced_path: Path, title: str,
) -> None:
    _atomic_write(path, _reference_bytes(
        date=date, request_id=request_id, rows=rows,
        referenced_path=referenced_path, title=title,
    ))


def _request_contract(request_id: str) -> tuple[str, str, str]:
    match = REQUEST_ID_RE.fullmatch(str(request_id or ""))
    if not match or not _valid_request_id(request_id):
        raise NoveltyIntegrityError("reserved event has no recoverable request contract")
    if match.group(1) == "dispatcher":
        return (
            match.group(2), "generation-request",
            "LOCAL NOVELTY-GATED GENERATION REQUEST",
        )
    return (
        match.group(2), "daily-generation-request",
        "DAILY LOCAL NOVELTY-GATED GENERATION REQUEST",
    )


def _reconcile_requests_locked(
    ledger_path: str | os.PathLike[str],
    inbox: str | os.PathLike[str] | None = None,
    *, ledger_rows: list[dict] | None = None,
) -> list[str]:
    """Locked implementation: rebuild requests from one ledger snapshot."""
    grouped = {}
    if ledger_rows is None:
        ledger_rows = read_consumed_ledger(ledger_path)
    _reserved, _consumed, outstanding = _lifecycle(ledger_rows)
    for row in outstanding.values():
        grouped.setdefault(row["request_id"], []).append(row)
    recovered = []

    def prior_row_versions(request_id: str) -> list[list[dict]]:
        versions = []
        seen = set()
        for event in ledger_rows:
            if (
                event["request_id"] != request_id
                or event["event"] not in {"RESERVED", "REVIEW_REFRESHED"}
            ):
                continue
            _prior_reserved, _prior_consumed, prior_outstanding = _lifecycle(
                ledger_rows[:event["sequence"]]
            )
            prior_rows = sorted(
                (
                    item for item in prior_outstanding.values()
                    if item["request_id"] == request_id
                ),
                key=lambda item: item["sequence"],
            )
            identity = tuple(row["record_hash"] for row in prior_rows)
            if prior_rows and identity not in seen:
                seen.add(identity)
                versions.append(prior_rows)
        return versions

    for request_id in sorted(grouped):
        date, prefix, title = _request_contract(request_id)
        path = request_path(prefix, date, inbox=inbox)
        request_rows = sorted(grouped[request_id], key=lambda row: row["sequence"])
        expected = _request_bytes(
            date=date, request_id=request_id, rows=request_rows, title=title
        )
        if path.exists():
            try:
                actual = path.read_bytes()
            except OSError as exc:
                raise NoveltyIntegrityError("reserved request is unreadable") from exc
            if actual != expected:
                prior_versions = {
                    _request_bytes(
                        date=date, request_id=request_id,
                        rows=prior_rows, title=title,
                    )
                    for prior_rows in prior_row_versions(request_id)
                }
                if actual not in prior_versions:
                    raise NoveltyIntegrityError(
                        "reserved request bytes do not match current or prior hash-bound records"
                    )
                _atomic_write(path, expected)
                recovered.append(str(path))
            continue
        _atomic_write(path, expected)
        recovered.append(str(path))

    current_by_request = {
        request_id: sorted(items, key=lambda row: row["sequence"])
        for request_id, items in grouped.items()
    }
    inbox_path = Path(inbox or INBOX)
    reference_specs = (
        (
            "daily-reference-*-novelty-v3.md",
            re.compile(r"^daily-reference-(\d{4}-\d{2}-\d{2})-novelty-v3\.md$"),
            "daily", "DAILY LOCAL NOVELTY REFERENCE",
        ),
        (
            "generation-reference-*-novelty-v3.md",
            re.compile(r"^generation-reference-(\d{4}-\d{2}-\d{2})-novelty-v3\.md$"),
            "dispatcher", "LOCAL NOVELTY OUTSTANDING REFERENCE",
        ),
    )
    for pattern, name_re, owner, title in reference_specs:
        for path in sorted(inbox_path.glob(pattern), key=lambda item: item.name.casefold()):
            match = name_re.fullmatch(path.name)
            if not match or not path.is_file():
                continue
            try:
                actual = path.read_bytes()
                text = actual.decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise NoveltyIntegrityError("reserved reference is unreadable") from exc
            if actual.startswith(b"# FULFILLED_OR_HISTORICAL_DO_NOT_GENERATE\n"):
                continue
            referenced = re.search(
                r"(?m)^- referenced_request_id: ((?:dispatcher|daily):\d{4}-\d{2}-\d{2})$",
                text,
            )
            referenced_id = referenced.group(1) if referenced else ""
            current_rows = current_by_request.get(referenced_id)
            if not current_rows:
                continue
            date = match.group(1)
            own_request_id = owner + ":" + date
            origin = _origin_request_path(current_rows, inbox_path)
            expected = _reference_bytes(
                date=date, request_id=own_request_id, rows=current_rows,
                referenced_path=origin, title=title,
            )
            if actual == expected:
                continue
            prior_versions = {
                _reference_bytes(
                    date=date, request_id=own_request_id, rows=prior_rows,
                    referenced_path=_origin_request_path(prior_rows, inbox_path),
                    title=title,
                )
                for prior_rows in prior_row_versions(referenced_id)
            }
            if actual not in prior_versions:
                raise NoveltyIntegrityError(
                    "reserved reference bytes do not match current or prior hash-bound records"
                )
            _atomic_write(path, expected)
            recovered.append(str(path))
    return recovered


def reconcile_requests(
    ledger_path: str | os.PathLike[str],
    inbox: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Recover journal, read ledger, and reconcile requests under one OS lock."""
    target = Path(ledger_path)
    with _claim_lock(target):
        rows = read_consumed_ledger(target)
        return _reconcile_requests_locked(target, inbox, ledger_rows=rows)


def _origin_request_path(rows: list[dict], inbox) -> Path:
    date, prefix, _title = _request_contract(rows[0]["request_id"])
    return request_path(prefix, date, inbox=inbox)


def retire_request_inventory(
    ledger_path: str | os.PathLike[str],
    inbox: str | os.PathLike[str] | None = None,
) -> dict:
    """Archive proven terminal requests and validate the root inbox fail closed."""
    import request_retirement
    import sys

    inbox_path = Path(inbox or INBOX).resolve()
    archive_path = inbox_path.parent / "_retired-generation"
    try:
        inbox_path.relative_to(ROOT.resolve())
        scope_root = ROOT
    except ValueError:
        # Test/embedded runtimes stay fully contained beside their patched inbox.
        scope_root = inbox_path.parent
    target = Path(ledger_path)
    try:
        with _claim_lock(target):
            rows = read_consumed_ledger(target)
            consumed_evidence = _validate_consumed_evidence_locked(rows, target)
            inbox_path.mkdir(parents=True, exist_ok=True)
            archive_path.mkdir(parents=True, exist_ok=True)
            result = request_retirement._retire_and_validate_locked(
                ledger=target, inbox_path=inbox_path, archive_path=archive_path,
                scope_root=scope_root, rows=rows, engine=sys.modules[__name__],
            )
            result["consumed_evidence"] = consumed_evidence
            return result
    except request_retirement.RequestRetirementError as exc:
        raise NoveltyIntegrityError(str(exc)) from exc


def main():
    active, historical = _coerce_loaded_registry(load_orders())
    date = _datetime.date.today().isoformat()
    request_id = "dispatcher:" + date
    ledger_path = ledger_path_for(INBOX)
    reconciled = reconcile_requests(ledger_path, INBOX)
    rows, claim_mode = claim_novel_orders(
        active, historical, consumer="dispatcher-local-request",
        request_id=request_id, ledger_path=ledger_path, return_mode=True,
    )
    if rows and rows[0]["request_id"] == request_id:
        state = "QUEUED_NOVEL"
        path = request_path("generation-request", date)
        write_request(
            path, date=date, request_id=request_id, rows=rows,
            title="LOCAL NOVELTY-GATED GENERATION REQUEST",
        )
    elif rows:
        state = "REFERENCE_OUTSTANDING_RESERVED"
        path = request_path("generation-reference", date)
        write_reference(
            path, date=date, request_id=request_id, rows=rows,
            referenced_path=_origin_request_path(rows, INBOX),
            title="LOCAL NOVELTY OUTSTANDING REFERENCE",
        )
    elif claim_mode == "ALREADY_TERMINAL_FOR_DATE":
        state = "NOVELTY_EXHAUSTED"
        path = request_path("generation-request", date)
    else:
        state = "NOVELTY_EXHAUSTED"
        path = request_path("generation-status", date)
        write_request(
            path, date=date, request_id=request_id, rows=[],
            title="LOCAL NOVELTY-GATED STATUS",
        )
    for recovered_path in reconcile_requests(ledger_path, INBOX):
        if recovered_path not in reconciled:
            reconciled.append(recovered_path)
    retirement = retire_request_inventory(ledger_path, INBOX)
    try:
        display_path = str(path.relative_to(ROOT))
    except ValueError:
        display_path = str(path)
    message = (
        "ngernduangold local novelty request: " + state + "; "
        + str(len(rows)) + " families -> " + display_path
    )
    print("---")
    print(message)
    print("generation: local-only (no network LLM/paid API)")
    print("publication_authority: NONE")
    return {
        "state": state,
        "queued": 0,
        "total": len(rows),
        "families": [row["family_id"] for row in rows],
        "message": message,
        "request": str(path),
        "ledger": str(ledger_path),
        "reconciled_requests": reconciled,
        "request_retirement": retirement,
        "generated": False,
        "notified": False,
    }


def cli_main() -> int:
    try:
        result = main()
    except NoveltyError as exc:
        print("BLOCKED_UNKNOWN: " + str(exc))
        return 20
    return 10 if result["state"] == "NOVELTY_EXHAUSTED" else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--bootstrap-novelty-state", action="store_true")
    parser.add_argument("--record-draft-fulfilment", metavar="RECEIPT")
    parser.add_argument("--retire-consumed-requests", action="store_true")
    args = parser.parse_args()
    if args.bootstrap_novelty_state:
        try:
            bootstrap_novelty_state(ledger_path_for(INBOX))
            print("ACTIVATED_EMPTY: explicit novelty state bootstrap complete")
            raise SystemExit(0)
        except NoveltyError as exc:
            print("BLOCKED_UNKNOWN: " + str(exc))
            raise SystemExit(20)
    if args.record_draft_fulfilment:
        try:
            receipt = str(args.record_draft_fulfilment)
            receipt_hash = _sha256_file(_resolve_bound_path(receipt))
            rows = fulfil_outstanding_from_receipt(
                receipt_path=receipt, receipt_sha256=receipt_hash,
                ledger_path=ledger_path_for(INBOX),
            )
            retirement = retire_request_inventory(ledger_path_for(INBOX), INBOX)
            print(
                "DRAFT_FULFILLED_NOT_PUBLICATION_READY: "
                + str(len(rows)) + " families"
            )
            print(
                "REQUEST_INVENTORY: " + retirement["state"] + "; retired="
                + str(retirement["retired"])
            )
            raise SystemExit(0)
        except (NoveltyError, OSError) as exc:
            print("BLOCKED_UNKNOWN: " + str(exc))
            raise SystemExit(20)
    if args.retire_consumed_requests:
        try:
            result = retire_request_inventory(ledger_path_for(INBOX), INBOX)
            print(
                "REQUEST_INVENTORY: " + result["state"] + "; retired="
                + str(result["retired"]) + "; newly_retired="
                + str(len(result["newly_retired"]))
            )
            raise SystemExit(0)
        except NoveltyError as exc:
            print("BLOCKED_UNKNOWN: " + str(exc))
            raise SystemExit(20)
    raise SystemExit(cli_main())
