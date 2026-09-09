#!/usr/bin/env python3
"""Capture a read-only, hash-bound live/local release-parity observation.

This tool may read the branded domain, its Netlify alias and Netlify's public
site metadata.  It never follows redirects, affiliate links, writes DNS,
deploys, grants publication authority, or creates analytics traffic beyond the
direct evidence requests named in the receipt.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
BANGKOK = ZoneInfo("Asia/Bangkok")
OUTPUT_DIR = Path(".local-private/runtime/live-domain-observations")
PRODUCER_PATH = Path("tools/live_domain_observation.py")
POLICY_PATH = Path(".system_control/policy.json")
OBSERVATION_SCHEMA_VERSION = 2
VALIDITY_CONTRACT_SCHEMA_VERSION = 1
LOCAL_BINDING_PATHS = (
    Path("site/index.html"),
    Path("site/sitemap.xml"),
    Path("site/release-manifest.json"),
    Path("release/candidate-receipt.json"),
)
MAX_BODY_BYTES = 16 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


class ObservationError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _canonical_hash(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _aware(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(BANGKOK)
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservationError("observation time must be timezone-aware")
    return parsed.astimezone(BANGKOK)


def _repo_path(repo: Path, relative: Path) -> Path:
    root = repo.resolve(strict=True)
    selected = (root / relative).resolve(strict=False)
    try:
        selected.relative_to(root)
    except ValueError as exc:
        raise ObservationError("path escapes repository") from exc
    return selected


def _stable_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ObservationError(f"binding is not a regular file: {path}")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise ObservationError(f"binding changed while being read: {path}")
    return raw


def _strict_json_bytes(raw: bytes, label: str) -> object:
    def reject_duplicates(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ObservationError(f"duplicate JSON key in {label}: {key}")
            value[key] = child
        return value

    def reject_constant(token):
        raise ObservationError(f"non-finite JSON value in {label}: {token}")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except ObservationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservationError(f"{label} is malformed") from exc


def _policy_contract(repo: Path) -> dict:
    raw = _stable_bytes(_repo_path(repo, POLICY_PATH))
    document = _strict_json_bytes(raw, "release policy")
    if not isinstance(document, dict):
        raise ObservationError("release policy is not an object")
    release = document.get("release_attestation")
    contract = (
        release.get("live_domain_observation")
        if isinstance(release, dict)
        else None
    )
    required = {
        "schema_version",
        "max_age_hours",
        "max_capture_duration_seconds",
        "future_skew_seconds",
        "exclusive_expiry",
    }
    if not isinstance(contract, dict) or set(contract) != required:
        raise ObservationError("live-domain validity policy contract is invalid")
    for field, minimum, maximum in (
        ("max_age_hours", 1, 168),
        ("max_capture_duration_seconds", 1, 600),
        ("future_skew_seconds", 0, 3600),
    ):
        value = contract.get(field)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < minimum
            or value > maximum
        ):
            raise ObservationError(
                "live-domain validity policy %s is invalid" % field
            )
    if contract.get("schema_version") != VALIDITY_CONTRACT_SCHEMA_VERSION:
        raise ObservationError("live-domain validity policy schema is invalid")
    if contract.get("exclusive_expiry") is not True:
        raise ObservationError("live-domain validity policy expiry is invalid")
    return {
        "schema_version": VALIDITY_CONTRACT_SCHEMA_VERSION,
        "policy_path": POLICY_PATH.as_posix(),
        "policy_sha256": hashlib.sha256(raw).hexdigest().upper(),
        "max_age_hours": contract["max_age_hours"],
        "max_capture_duration_seconds": contract[
            "max_capture_duration_seconds"
        ],
        "future_skew_seconds": contract["future_skew_seconds"],
        "exclusive_expiry": True,
    }


def _binding(repo: Path, relative: Path) -> dict:
    raw = _stable_bytes(_repo_path(repo, relative))
    return {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
        "size_bytes": len(raw),
    }


def _header(headers, name: str) -> str | None:
    value = headers.get(name)
    return str(value) if value is not None else None


def _http_get(url: str, timeout: float) -> tuple[dict, bytes]:
    request = Request(
        url,
        headers={"User-Agent": "ngernduangold-readonly-observer/1.0"},
        method="GET",
    )
    opener = build_opener(_NoRedirect())
    response = None
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        status = int(getattr(response, "status", response.getcode()))
        raw = response.read(MAX_BODY_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES:
            raise ObservationError(f"response exceeds size limit: {url}")
        headers = response.headers
        evidence = {
            "url": url,
            "http_status": status,
            "content_length": len(raw),
            "body_sha256": hashlib.sha256(raw).hexdigest().upper(),
            "etag": _header(headers, "ETag"),
            "request_id": _header(headers, "x-nf-request-id"),
            "content_type": _header(headers, "Content-Type"),
        }
        redirect = _header(headers, "Location")
        if redirect is not None:
            evidence["redirect_location"] = redirect
        return evidence, raw
    except (OSError, ValueError) as exc:
        if isinstance(exc, ObservationError):
            raise
        raise ObservationError(f"HTTP observation failed for {url}: {exc}") from exc
    finally:
        if response is not None:
            response.close()


def _sitemap_metadata(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="strict")
    lastmods = re.findall(r"<lastmod>([^<]+)</lastmod>", text)
    return {
        "url_count": len(re.findall(r"<loc>", text)),
        "min_lastmod": min(lastmods) if lastmods else None,
        "max_lastmod": max(lastmods) if lastmods else None,
    }


def _client_addresses(domain: str) -> list[str]:
    try:
        values = {
            row[4][0]
            for row in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
            if row and row[4]
        }
    except OSError:
        return []
    return sorted(values)


def _authoritative_addresses(domain: str, server_ip: str) -> list[str]:
    try:
        completed = subprocess.run(
            ["nslookup", "-type=A", domain, server_ip],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    addresses: set[str] = set()
    for candidate in re.findall(r"(?<![:\d])(?:\d{1,3}\.){3}\d{1,3}(?![:\d])", completed.stdout):
        try:
            parsed = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if parsed.version == 4 and candidate != server_ip:
            addresses.add(candidate)
    return sorted(addresses)


def _public_metadata(raw: bytes, status: int) -> dict:
    if status != 200:
        return {"http_status": status, "state": "UNAVAILABLE"}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservationError("Netlify public metadata is malformed") from exc
    if not isinstance(value, dict):
        raise ObservationError("Netlify public metadata is not an object")
    deploy = value.get("published_deploy")
    deploy = deploy if isinstance(deploy, dict) else {}
    return {
        "http_status": status,
        "request_id": None,
        "site_id": value.get("id"),
        "site_name": value.get("name"),
        "custom_domain": value.get("custom_domain"),
        "published_deploy_id": deploy.get("id"),
        "published_deploy_state": deploy.get("state"),
        "published_at": deploy.get("published_at"),
        "branch": deploy.get("branch"),
        "commit_ref": deploy.get("commit_ref"),
        "build_settings": value.get("build_settings")
        if isinstance(value.get("build_settings"), dict)
        else {},
    }


def build_observation(
    repo: Path,
    *,
    domain: str,
    alias_domain: str,
    netlify_site: str,
    authoritative_server: str,
    authoritative_server_ip: str,
    timeout: float,
    now: str | datetime | None = None,
) -> dict:
    started = _aware(now)
    validity = _policy_contract(repo)
    root, root_raw = _http_get(f"https://{domain}/", timeout)
    sitemap, sitemap_raw = _http_get(f"https://{domain}/sitemap.xml", timeout)
    manifest, manifest_raw = _http_get(
        f"https://{domain}/release-manifest.json", timeout
    )
    alias, _ = _http_get(f"https://{alias_domain}/", timeout)
    metadata_http, metadata_raw = _http_get(
        f"https://api.netlify.com/api/v1/sites/{netlify_site}", timeout
    )
    finished = datetime.now(BANGKOK) if now is None else started

    bindings = [_binding(repo, relative) for relative in LOCAL_BINDING_PATHS]
    binding_by_path = {row["path"]: row for row in bindings}
    sitemap.update(_sitemap_metadata(sitemap_raw))

    client = _client_addresses(domain)
    authoritative = _authoritative_addresses(domain, authoritative_server_ip)
    exact_remote_hash_parity = (
        root["body_sha256"] == binding_by_path["site/index.html"]["sha256"]
        and sitemap["body_sha256"]
        == binding_by_path["site/sitemap.xml"]["sha256"]
        and manifest["body_sha256"]
        == binding_by_path["site/release-manifest.json"]["sha256"]
    )
    parity = bool(
        root["http_status"] == 200
        and sitemap["http_status"] == 200
        and manifest["http_status"] == 200
        and exact_remote_hash_parity
    )

    reasons: list[str] = []
    if root["http_status"] != 200:
        reasons.append(f"the branded root returned HTTP {root['http_status']}")
    if sitemap["http_status"] != 200:
        reasons.append(f"the branded sitemap returned HTTP {sitemap['http_status']}")
    if manifest["http_status"] != 200:
        reasons.append(
            "the branded release-manifest endpoint returns "
            + str(manifest["http_status"])
        )
    for relative, remote in (
        ("site/index.html", root),
        ("site/sitemap.xml", sitemap),
        ("site/release-manifest.json", manifest),
    ):
        if remote["body_sha256"] != binding_by_path[relative]["sha256"]:
            reasons.append(f"the live body hash differs from {relative}")
    if not client:
        reasons.append("client DNS resolution was unavailable")
    if not authoritative:
        reasons.append("authoritative DNS resolution was unavailable")

    expires_at = finished + timedelta(hours=validity["max_age_hours"])
    observation = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "observation_kind": "LIVE_BRANDED_DOMAIN_RELEASE_PARITY",
        "observation_id": "live-domain-" + finished.strftime("%Y%m%dT%H%M%S%z"),
        "observed_at": finished.isoformat(timespec="seconds"),
        "observation_window": {
            "start": started.isoformat(timespec="seconds"),
            "end": finished.isoformat(timespec="seconds"),
        },
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "validity_contract": validity,
        "boundary": {
            "scope": "READ_ONLY_EXTERNAL_OBSERVATION_PLUS_LOCAL_FILE_BINDINGS",
            "repairs_dns": False,
            "deploys_site": False,
            "grants_publication_authority": False,
            "follows_affiliate_redirects": False,
        },
        "producer": _binding(repo, PRODUCER_PATH),
        "branded_domain": domain,
        "dns": {
            "state": "DNS_RESOLUTION_RECOVERED_CURRENT"
            if client and authoritative
            else "UNKNOWN",
            "authoritative_server": authoritative_server,
            "authoritative_server_ip": authoritative_server_ip,
            "apex_a": {
                "state": "PRESENT" if authoritative else "UNKNOWN",
                "addresses": authoritative,
            },
            "client_resolution": {
                "state": "PASS_CURRENT" if client else "UNKNOWN",
                "addresses": client,
            },
        },
        "netlify_public_metadata": _public_metadata(
            metadata_raw, metadata_http["http_status"]
        ),
        "http_observations": {
            "branded_root": root,
            "branded_sitemap": sitemap,
            "branded_release_manifest": manifest,
            "default_alias_root": alias,
        },
        "local_candidate_bindings": bindings,
        "conclusion": {
            "dns_state": "DNS_RESOLUTION_RECOVERED_CURRENT"
            if client and authoritative
            else "UNKNOWN",
            "release_attestation_state": "PASS" if parity else "MISSING",
            "live_local_release_parity": "PASS" if parity else "FAILED",
            "live_deploy_state": "PARITY_CONFIRMED"
            if parity
            else "MISMATCH_OR_OLD_DEPLOY",
            "reasons": reasons,
            "repair_claimed": False,
        },
    }
    observation["observation_payload_sha256"] = _canonical_hash(observation)
    return observation


def _timestamp(value: object, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(label + " is invalid")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(label + " is invalid")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(label + " must be timezone-aware")
        return None
    return parsed


def validate_observation_integrity(repo: Path, payload: object) -> list[str]:
    """Validate immutable evidence and its policy-bound validity envelope."""
    if not isinstance(payload, dict):
        return ["observation is not an object"]
    errors: list[str] = []
    claimed = payload.get("observation_payload_sha256")
    unsigned = {k: v for k, v in payload.items() if k != "observation_payload_sha256"}
    if not isinstance(claimed, str) or not SHA256_RE.fullmatch(claimed):
        errors.append("observation payload hash is invalid")
    elif claimed != _canonical_hash(unsigned):
        errors.append("observation payload hash mismatch")
    if payload.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
        errors.append("observation schema is unsupported")
    if payload.get("observation_kind") != "LIVE_BRANDED_DOMAIN_RELEASE_PARITY":
        errors.append("observation kind is invalid")
    boundary = payload.get("boundary")
    boundary = boundary if isinstance(boundary, dict) else {}
    for field in (
        "repairs_dns",
        "deploys_site",
        "grants_publication_authority",
        "follows_affiliate_redirects",
    ):
        if boundary.get(field) is not False:
            errors.append("unsafe observation boundary: " + field)
    producer = payload.get("producer")
    try:
        current_producer = _binding(repo, PRODUCER_PATH)
    except ObservationError as exc:
        errors.append(str(exc))
    else:
        if producer != current_producer:
            errors.append("observation producer binding is invalid or stale")

    try:
        current_validity = _policy_contract(repo)
    except ObservationError as exc:
        current_validity = None
        errors.append(str(exc))
    validity = payload.get("validity_contract")
    if not isinstance(validity, dict):
        errors.append("observation validity contract is missing")
    elif current_validity is not None and validity != current_validity:
        errors.append("observation validity contract is invalid or stale")

    observed = _timestamp(payload.get("observed_at"), "observed_at", errors)
    window = payload.get("observation_window")
    if not isinstance(window, dict) or set(window) != {"start", "end"}:
        errors.append("observation window is invalid")
        window_start = None
        window_end = None
    else:
        window_start = _timestamp(
            window.get("start"), "observation window start", errors
        )
        window_end = _timestamp(
            window.get("end"), "observation window end", errors
        )
    expires = _timestamp(payload.get("expires_at"), "expires_at", errors)
    if window_start is not None and window_end is not None:
        if window_start > window_end:
            errors.append("observation window starts after it ends")
        if observed is not None and observed != window_end:
            errors.append("observed_at does not equal observation window end")
        duration = (window_end - window_start).total_seconds()
        capture_limit = (
            current_validity.get("max_capture_duration_seconds")
            if isinstance(current_validity, dict)
            else None
        )
        if (
            isinstance(capture_limit, int)
            and (duration < 0 or duration > capture_limit)
        ):
            errors.append("observation capture duration exceeds policy")
    if observed is not None and expires is not None and isinstance(
        current_validity, dict
    ):
        expected_expiry = observed + timedelta(
            hours=current_validity["max_age_hours"]
        )
        expected_text = expected_expiry.isoformat(timespec="seconds")
        if payload.get("expires_at") != expected_text:
            errors.append("observation expiry does not match policy")

    rows = payload.get("local_candidate_bindings")
    rows = rows if isinstance(rows, list) else []
    if [row.get("path") for row in rows if isinstance(row, dict)] != [
        path.as_posix() for path in LOCAL_BINDING_PATHS
    ]:
        errors.append("local binding inventory is invalid")
    else:
        for row, relative in zip(rows, LOCAL_BINDING_PATHS):
            try:
                current = _binding(repo, relative)
            except ObservationError as exc:
                errors.append(str(exc))
            else:
                if row != current:
                    errors.append("local binding changed: " + relative.as_posix())
    return list(dict.fromkeys(errors))


def validate_observation(
    repo: Path,
    payload: object,
    *,
    as_of: str | datetime | None = None,
) -> list[str]:
    """Validate one observation for a decision at ``as_of`` (now by default)."""
    errors = validate_observation_integrity(repo, payload)
    if not isinstance(payload, dict):
        return errors
    try:
        decision_time = _aware(as_of)
    except (ObservationError, ValueError):
        errors.append("decision time must be timezone-aware")
        return list(dict.fromkeys(errors))
    time_errors: list[str] = []
    observed = _timestamp(payload.get("observed_at"), "observed_at", time_errors)
    expires = _timestamp(payload.get("expires_at"), "expires_at", time_errors)
    validity = payload.get("validity_contract")
    skew = (
        validity.get("future_skew_seconds")
        if isinstance(validity, dict)
        else None
    )
    if observed is not None:
        if observed > decision_time:
            errors.append("observation is not yet valid")
        if (
            isinstance(skew, int)
            and not isinstance(skew, bool)
            and observed > decision_time + timedelta(seconds=skew)
        ):
            errors.append("observation time exceeds allowed future skew")
    if expires is not None and decision_time >= expires:
        errors.append("observation is stale at the decision time")
    return list(dict.fromkeys(errors))


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(raw)
        handle.flush()
    temporary.replace(path)


def _load(path: Path) -> object:
    try:
        return _strict_json_bytes(_stable_bytes(path), "observation")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ObservationError(f"observation is unreadable: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--repo", default=str(ROOT))
    capture.add_argument("--domain", default="ngernduangold.com")
    capture.add_argument("--alias-domain", default="ngernduangold.netlify.app")
    capture.add_argument("--netlify-site", default="ngernduangold.netlify.app")
    capture.add_argument("--authoritative-server", default="dns1.p09.nsone.net")
    capture.add_argument("--authoritative-server-ip", default="198.51.44.9")
    capture.add_argument("--timeout", type=float, default=20.0)
    capture.add_argument("--now")
    capture.add_argument("--output")
    validate = sub.add_parser("validate")
    validate.add_argument("path")
    validate.add_argument("--repo", default=str(ROOT))
    validate.add_argument(
        "--as-of",
        help="timezone-aware decision time; defaults to the current time",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repo = Path(args.repo).resolve(strict=True)
        if args.command == "validate":
            path = Path(args.path).resolve(strict=True)
            errors = validate_observation(repo, _load(path), as_of=args.as_of)
            print(json.dumps({"verdict": "FAIL" if errors else "PASS", "errors": errors}))
            return 1 if errors else 0
        payload = build_observation(
            repo,
            domain=args.domain,
            alias_domain=args.alias_domain,
            netlify_site=args.netlify_site,
            authoritative_server=args.authoritative_server,
            authoritative_server_ip=args.authoritative_server_ip,
            timeout=args.timeout,
            now=args.now,
        )
        if args.output:
            output = _repo_path(repo, Path(args.output))
        else:
            stamp = payload["observed_at"].replace("-", "").replace(":", "")
            output = _repo_path(repo, OUTPUT_DIR / f"LIVE-DOMAIN-OBSERVATION_{stamp}.json")
        _atomic_write(output, payload)
        errors = validate_observation(repo, payload)
        print(json.dumps({
            "verdict": "FAIL" if errors else "PASS",
            "output": str(output),
            "observation_payload_sha256": payload["observation_payload_sha256"],
            "live_local_release_parity": payload["conclusion"]["live_local_release_parity"],
            "errors": errors,
        }))
        return 1 if errors else 0
    except (ObservationError, OSError, ValueError) as exc:
        print("live-domain observation FAIL: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
