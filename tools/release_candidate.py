#!/usr/bin/env python3
"""Create and verify a deterministic, non-authorizing release candidate archive.

The Git-connected Netlify path rebuilds ``site/`` and ``site/`` is ignored by
Git.  A content-addressed archive therefore preserves the exact audited bytes
without pretending that a dirty working tree is an immutable source revision.
This tool never deploys, uploads, commits, or grants action authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import zipfile

try:
    import release_contract
except ModuleNotFoundError:  # package import used by focused tests
    from tools import release_contract


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
ARCHIVE_FORMAT = "zip-store-fixed-metadata-v1"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
ZIP_CREATE_SYSTEM = 3
ZIP_CREATE_VERSION = 20
ZIP_EXTRACT_VERSION = 20
ZIP_EXTERNAL_ATTR = (0o100644 & 0xFFFF) << 16
ZIP_UTF8_FLAG = 0x800

# Exact downstream artifacts that consume the candidate receipt/manifest but
# are not release inputs.  Binding one of these files into ``source_revision``
# creates a self-invalidating cycle: writing the report after ``pack`` makes
# the receipt stale even though neither the audited site nor its source changed.
# Keep this allow-list deliberately narrow and record it in every receipt so an
# exclusion can never be implicit.
SOURCE_REVISION_OUTPUT_EXCLUSIONS = (
    "release/PREDEPLOY-ACCEPTANCE.md",
    "release/RELEASE-FUNNEL-READINESS.json",
)
SOURCE_REVISION_SCOPE = (
    "git-worktree-excluding-candidate-and-declared-downstream-outputs-v1"
)


class CandidateError(RuntimeError):
    """Raised before a candidate can be mislabeled as verified."""


def _strict_json_loads(value: str | bytes) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    parsed = json.loads(
        value,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def require_finite(item: object) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    require_finite(parsed)
    return parsed


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _inside(path: Path, root: Path, label: str) -> Path:
    selected = path.resolve()
    try:
        selected.relative_to(root.resolve())
    except ValueError as exc:
        raise CandidateError(label + " must stay inside the repository") from exc
    return selected


def _site_files(src: Path) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for path in sorted(src.rglob("*")):
        if path.is_symlink():
            raise CandidateError("candidate site contains a symlink: " + str(path))
        if not path.is_file():
            continue
        name = path.relative_to(src).as_posix()
        parsed = PurePosixPath(name)
        if parsed.is_absolute() or ".." in parsed.parts or not name:
            raise CandidateError("candidate site contains an unsafe path")
        rows.append((name, path))
    if not rows:
        raise CandidateError("candidate site is empty")
    return rows


def _canonical_manifest(src: Path, repo: Path) -> tuple[dict, bytes]:
    path = src / release_contract.MANIFEST_NAME
    try:
        raw = path.read_bytes()
        payload = _strict_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateError("release manifest is missing or unreadable") from exc
    findings = release_contract.manifest_findings(payload, src, repo)
    if findings:
        raise CandidateError("; ".join(findings))
    canonical = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise CandidateError("release manifest is valid but not canonical bytes")
    return payload, raw


def _write_archive(src: Path, destination: Path) -> int:
    rows = _site_files(src)
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        archive.comment = b""
        for name, path in rows:
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = ZIP_CREATE_SYSTEM
            info.create_version = ZIP_CREATE_VERSION
            info.extract_version = ZIP_EXTRACT_VERSION
            info.reserved = 0
            info.flag_bits = ZIP_UTF8_FLAG if not name.isascii() else 0
            info.volume = 0
            info.internal_attr = 0
            info.external_attr = ZIP_EXTERNAL_ATTR
            info.extra = b""
            info.comment = b""
            with path.open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    return len(rows)


def _git_output(repo: Path, args: list[str]) -> bytes | None:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def _validated_output_exclusions(repo: Path) -> tuple[str, ...]:
    values: list[str] = []
    for name in SOURCE_REVISION_OUTPUT_EXCLUSIONS:
        parsed = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or parsed.is_absolute()
            or ".." in parsed.parts
            or any(character in name for character in "*?[]")
            or not parsed.parts
            or parsed.parts[0] != "release"
            or Path(name) in release_contract.SOURCE_INPUTS
        ):
            raise CandidateError(
                "source-revision output exclusion must be one exact downstream release path"
            )
        selected = (repo / Path(*parsed.parts)).resolve()
        try:
            selected.relative_to(repo.resolve())
        except ValueError as exc:
            raise CandidateError(
                "source-revision output exclusion escapes the repository"
            ) from exc
        values.append(name)
    if len(values) != len(set(values)):
        raise CandidateError("source-revision output exclusions contain duplicates")
    return tuple(values)


def _git_snapshot(repo: Path, receipt: Path, out_dir: Path) -> dict:
    head_raw = _git_output(repo, ["rev-parse", "HEAD"])
    branch_raw = _git_output(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    head = head_raw.decode("ascii", "replace").strip() if head_raw else "UNAVAILABLE"
    branch = branch_raw.decode("utf-8", "replace").strip() if branch_raw else "UNAVAILABLE"

    excluded_receipt = receipt.resolve().relative_to(repo).as_posix()
    excluded_archive_prefix = out_dir.resolve().relative_to(repo).as_posix().rstrip("/") + "/"
    excluded_generated_outputs = _validated_output_exclusions(repo)

    exclusions = [
        ".",
        ":(exclude)" + excluded_receipt,
        ":(exclude)" + excluded_archive_prefix + "**",
        *(
            ":(exclude)" + name
            for name in excluded_generated_outputs
        ),
    ]
    tracked_names_raw = _git_output(
        repo, ["diff", "--name-only", "-z", "HEAD", "--", *exclusions]
    )
    tracked_state_raw = _git_output(
        repo, ["diff", "--raw", "--full-index", "-z", "HEAD", "--", *exclusions]
    )
    if tracked_names_raw is None or tracked_state_raw is None:
        tracked_names = {"GIT_STATUS_UNAVAILABLE"}
        tracked_state_hash = "UNAVAILABLE"
    else:
        tracked_names = {
            item.decode("utf-8", "replace")
            for item in tracked_names_raw.split(b"\0") if item
        }
        tracked_state_hash = sha256_bytes(tracked_state_raw)

    # ``git diff --raw`` uses an all-zero destination object id for ordinary
    # unstaged worktree edits.  It therefore binds the dirty path and mode, but
    # not the bytes currently under that path.  Hash those bytes separately so
    # changing one already-dirty tracked file cannot replay an older receipt.
    tracked_content_rows: list[dict[str, str]] = []
    for name in sorted(tracked_names):
        if name == "GIT_STATUS_UNAVAILABLE":
            tracked_content_rows.append({"path": name, "state": "UNAVAILABLE"})
            continue
        unresolved = repo / name
        if unresolved.is_symlink():
            raise CandidateError("tracked source path is a symlink: " + name)
        try:
            path = unresolved.resolve(strict=True)
        except FileNotFoundError:
            tracked_content_rows.append({"path": name, "state": "MISSING"})
            continue
        try:
            path.relative_to(repo.resolve())
        except ValueError as exc:
            raise CandidateError("tracked source path escapes the repository") from exc
        if not path.is_file():
            raise CandidateError("tracked source path is not a regular file: " + name)
        tracked_content_rows.append({
            "path": name,
            "sha256": sha256_file(path),
            "state": "FILE",
        })
    tracked_content_hash = sha256_bytes(json.dumps(
        tracked_content_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8"))

    untracked_raw = _git_output(
        repo, ["ls-files", "--others", "--exclude-standard", "-z"]
    )
    if untracked_raw is None:
        untracked_names = {"GIT_STATUS_UNAVAILABLE"}
    else:
        untracked_names = {
            item.decode("utf-8", "replace")
            for item in untracked_raw.split(b"\0") if item
        }
    untracked_names = {
        name for name in untracked_names
        if (
            name != excluded_receipt
            and not name.startswith(excluded_archive_prefix)
            and name not in excluded_generated_outputs
        )
    }
    untracked_content_lines: list[str] = []
    for name in sorted(untracked_names):
        if name == "GIT_STATUS_UNAVAILABLE":
            untracked_content_lines.append(name)
            continue
        unresolved = repo / name
        if unresolved.is_symlink():
            raise CandidateError("untracked source path is not a regular file: " + name)
        path = unresolved.resolve()
        try:
            path.relative_to(repo.resolve())
        except ValueError as exc:
            raise CandidateError("untracked source path escapes the repository") from exc
        if path.is_symlink() or not path.is_file():
            raise CandidateError("untracked source path is not a regular file: " + name)
        untracked_content_lines.append(name + "\0" + sha256_file(path))
    untracked_content = ("\n".join(untracked_content_lines) + "\n").encode("utf-8")
    untracked_content_hash = sha256_bytes(untracked_content)
    fingerprint_lines = (
        ["T:" + name for name in sorted(tracked_names)]
        + ["U:" + name for name in sorted(untracked_names)]
    )
    working_state_hash = sha256_bytes(
        b"tracked\0" + tracked_state_hash.encode("ascii", "replace")
        + b"\ntracked-content\0" + tracked_content_hash.encode("ascii")
        + b"\nuntracked\0" + untracked_content_hash.encode("ascii") + b"\n"
    )
    clean = not tracked_names and not untracked_names and head != "UNAVAILABLE"
    return {
        "head": head,
        "branch": branch,
        "clean": clean,
        "tracked_changes_count": len(tracked_names),
        "untracked_paths_count": len(untracked_names),
        "dirty_path_fingerprint_sha256": sha256_bytes(
            ("\n".join(fingerprint_lines) + "\n").encode("utf-8")
        ),
        "tracked_state_sha256": tracked_state_hash,
        "tracked_content_sha256": tracked_content_hash,
        "untracked_content_sha256": untracked_content_hash,
        "working_tree_content_sha256": working_state_hash,
        "clean_rebuild_verified": False,
        "scope": SOURCE_REVISION_SCOPE,
        "excluded_generated_outputs": list(excluded_generated_outputs),
    }


def _archive_relative(archive: Path, repo: Path) -> str:
    return archive.resolve().relative_to(repo.resolve()).as_posix()


def build_receipt(
    *,
    src: Path,
    repo: Path,
    archive: Path,
    receipt: Path,
    out_dir: Path,
    manifest: dict,
    manifest_raw: bytes,
    member_count: int,
) -> dict:
    archive_hash = sha256_file(archive)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": "local-release-candidate-v1",
        "candidate_id": "sha256:" + archive_hash,
        "release_id": manifest["release_id"],
        "manifest_schema": manifest["schema_version"],
        "manifest_sha256": sha256_bytes(manifest_raw),
        "manifest_source_input_count": len(manifest.get("source_sha256") or {}),
        "archive": {
            "path": _archive_relative(archive, repo),
            "sha256": archive_hash,
            "bytes": archive.stat().st_size,
            "member_count": member_count,
            "format": ARCHIVE_FORMAT,
        },
        "artifact": {
            "archive_verified": True,
            "content_addressed": True,
            "reproducible_from_archive": True,
        },
        "source_revision": _git_snapshot(repo, receipt, out_dir),
        "deployment": {
            "authorized": False,
            "authority_source": ".system_control/role_capabilities.json",
            "path": "netlify_git_connected",
            "action_receipt": None,
        },
        "postdeploy": {
            "state": "NOT_CREATED",
            "required_zero_finding_families": [
                "exact_release", "attribution", "offer_safety"
            ],
            "receipt": None,
        },
        "rollback": {
            "artifact_location": "LOCAL_ONLY",
            "previous_deploy_id": None,
            "previous_release_id": None,
            "restore_path_verified": False,
            "ready": False,
        },
        "external_action_authorized": False,
    }


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def pack(src: Path, repo: Path, out_dir: Path, receipt: Path) -> tuple[Path, dict]:
    repo = repo.resolve()
    src = _inside(src, repo, "candidate source")
    out_dir = _inside(out_dir, repo, "candidate archive directory")
    receipt = _inside(receipt, repo, "candidate receipt")
    if not src.is_dir():
        raise CandidateError("candidate source directory does not exist")
    manifest, manifest_raw = _canonical_manifest(src, repo)
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".candidate-", suffix=".zip.tmp", dir=out_dir
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        member_count = _write_archive(src, temporary)
        archive_hash = sha256_file(temporary)
        archive = out_dir / ("candidate-" + archive_hash + ".zip")
        if archive.exists():
            if sha256_file(archive) != archive_hash:
                raise CandidateError("existing content-addressed archive is corrupt")
            temporary.unlink()
        else:
            os.replace(temporary, archive)
        payload = build_receipt(
            src=src,
            repo=repo,
            archive=archive,
            receipt=receipt,
            out_dir=out_dir,
            manifest=manifest,
            manifest_raw=manifest_raw,
            member_count=member_count,
        )
        _atomic_json(receipt, payload)
        verify(src, repo, archive, receipt)
        return archive, payload
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateError(message)


def verify(src: Path, repo: Path, archive: Path, receipt: Path) -> dict:
    repo = repo.resolve()
    src = _inside(src, repo, "candidate source")
    archive = _inside(archive, repo, "candidate archive")
    receipt = _inside(receipt, repo, "candidate receipt")
    try:
        payload = _strict_json_loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateError("candidate receipt is missing or unreadable") from exc
    _require(isinstance(payload, dict), "candidate receipt must be an object")
    _require(payload.get("schema_version") == SCHEMA_VERSION,
             "candidate receipt schema is unsupported")
    _require(payload.get("contract") == "local-release-candidate-v1",
             "candidate receipt contract is unsupported")
    _require(payload.get("external_action_authorized") is False,
             "candidate receipt must never authorize external action")
    deployment = payload.get("deployment") or {}
    artifact = payload.get("artifact") or {}
    rollback = payload.get("rollback") or {}
    postdeploy = payload.get("postdeploy") or {}
    _require(deployment.get("authorized") is False and
             deployment.get("action_receipt") is None,
             "candidate receipt must not authorize deployment")
    _require(artifact.get("archive_verified") is True and
             artifact.get("content_addressed") is True and
             artifact.get("reproducible_from_archive") is True,
             "candidate artifact claims are incomplete")
    _require(rollback.get("ready") is False and
             rollback.get("artifact_location") == "LOCAL_ONLY" and
             rollback.get("restore_path_verified") is False,
             "local archive must not overclaim rollback readiness")
    _require(postdeploy.get("state") == "NOT_CREATED" and
             postdeploy.get("receipt") is None,
             "predeploy candidate must not contain a postdeploy receipt")

    manifest, manifest_raw = _canonical_manifest(src, repo)
    _require(payload.get("release_id") == manifest.get("release_id"),
             "candidate receipt release id differs from local manifest")
    _require(payload.get("manifest_schema") == manifest.get("schema_version"),
             "candidate receipt manifest schema differs")
    _require(payload.get("manifest_sha256") == sha256_bytes(manifest_raw),
             "candidate receipt manifest hash differs")
    _require(payload.get("manifest_source_input_count") ==
             len(manifest.get("source_sha256") or {}),
             "candidate receipt source-input count differs")

    archive_row = payload.get("archive") or {}
    actual_hash = sha256_file(archive)
    _require(archive_row.get("path") == _archive_relative(archive, repo),
             "candidate archive path differs from receipt")
    _require(archive_row.get("sha256") == actual_hash and
             payload.get("candidate_id") == "sha256:" + actual_hash,
             "candidate archive is not content-addressed correctly")
    _require(archive_row.get("bytes") == archive.stat().st_size,
             "candidate archive byte count differs")
    _require(archive_row.get("format") == ARCHIVE_FORMAT,
             "candidate archive format differs")

    expected = {name: path for name, path in _site_files(src)}
    try:
        with zipfile.ZipFile(archive, "r") as zipped:
            _require(zipped.comment == b"",
                     "candidate archive comment is not deterministic")
            infos = zipped.infolist()
            names = [info.filename for info in infos]
            _require(len(names) == len(set(names)),
                     "candidate archive contains duplicate members")
            _require(set(names) == set(expected),
                     "candidate archive membership differs from local site")
            for info in infos:
                expected_flags = ZIP_UTF8_FLAG if not info.filename.isascii() else 0
                _require(
                    info.date_time == FIXED_ZIP_TIME
                    and info.compress_type == zipfile.ZIP_STORED
                    and info.create_system == ZIP_CREATE_SYSTEM
                    and info.create_version == ZIP_CREATE_VERSION
                    and info.extract_version == ZIP_EXTRACT_VERSION
                    and info.reserved == 0
                    and info.flag_bits == expected_flags
                    and info.volume == 0
                    and info.internal_attr == 0
                    and info.external_attr == ZIP_EXTERNAL_ATTR
                    and info.extra == b""
                    and info.comment == b""
                    and info.compress_size == info.file_size,
                    "candidate archive metadata is not deterministic",
                )
                parsed = PurePosixPath(info.filename)
                _require(not parsed.is_absolute() and ".." not in parsed.parts,
                         "candidate archive contains an unsafe member")
                _require(zipped.read(info) == expected[info.filename].read_bytes(),
                         "candidate archive member differs: " + info.filename)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CandidateError("candidate archive is unreadable") from exc
    _require(archive_row.get("member_count") == len(expected),
             "candidate archive member count differs")

    snapshot = _git_snapshot(repo, receipt, archive.parent)
    _require(payload.get("source_revision") == snapshot,
             "candidate receipt no longer describes the current source revision state")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("pack", "verify"):
        selected = subparsers.add_parser(name)
        selected.add_argument("--src", default="site")
        selected.add_argument("--repo", default=str(ROOT))
        selected.add_argument("--receipt", default="release/candidate-receipt.json")
        if name == "pack":
            selected.add_argument("--out-dir", default="release/candidates")
        else:
            selected.add_argument("--archive")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    src = Path(args.src)
    if not src.is_absolute():
        src = repo / src
    receipt = Path(args.receipt)
    if not receipt.is_absolute():
        receipt = repo / receipt
    try:
        if args.command == "pack":
            out_dir = Path(args.out_dir)
            if not out_dir.is_absolute():
                out_dir = repo / out_dir
            archive, payload = pack(src, repo, out_dir, receipt)
            print("candidate archive: %s (%d members, %d bytes)" % (
                payload["candidate_id"], payload["archive"]["member_count"],
                payload["archive"]["bytes"],
            ))
            print("archive -> " + str(archive))
            print("receipt -> " + str(receipt))
        else:
            try:
                payload = _strict_json_loads(receipt.read_text(encoding="utf-8"))
            except Exception as exc:
                raise CandidateError("candidate receipt is missing or unreadable") from exc
            archive_arg = args.archive or (payload.get("archive") or {}).get("path")
            if not isinstance(archive_arg, str) or not archive_arg:
                raise CandidateError("candidate archive path is missing")
            archive = Path(archive_arg)
            if not archive.is_absolute():
                archive = repo / archive
            verified = verify(src, repo, archive, receipt)
            print("candidate verify: PASS " + verified["candidate_id"])
    except CandidateError as exc:
        print("candidate verify: FAIL " + str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
