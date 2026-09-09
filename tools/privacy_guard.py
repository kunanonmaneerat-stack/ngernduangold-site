#!/usr/bin/env python3
"""Fail-closed privacy scan for public records, sources and generated pages.

The scanner covers structured/log-like control records plus the site builder,
public source components and generated ``site`` text assets.  Git-ignored build
output is enumerated explicitly so a local release cannot bypass the guard.
Findings never echo matching content; output is limited to path, line number,
and data class.
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import io
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Iterable, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    category: str


JSON_KEY_RE = re.compile(r'"(?P<key>(?:[^"\\]|\\.)+)"\s*:')
HEX_DIGEST_RE = re.compile(r"[0-9A-Fa-f]+\Z")
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)
PHONE_RE = re.compile(
    r"(?<![\d+])(?:"
    # Keep the historical broad 0-prefix detector: malformed tracker tokens
    # and digest-like prose must not become a hiding place merely because the
    # second digit is zero.  Valid digest/tracker spans are masked separately.
    r"0\d(?:[ .-]?\d){7,8}"
    r"|(?:\+66|66)[ .-]?[1-9](?:[ .-]?\d){7,8}"
    r")(?!\d)"
)
# Candidate extraction stays deliberately narrower than a general URL parser.
# AccessTrade exposes either a 12-character campaign token ending in ``002a0x``
# or an eight-character ``/go/`` token.  The parsed URL is validated again below
# before any characters are hidden from the phone-number detector.
AFFILIATE_TRACKER_CANDIDATE_RE = re.compile(
    r"https://atth\.me/(?:[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*)",
    re.IGNORECASE,
)
AFFILIATE_TRACKER_DIRECT_PATH_RE = re.compile(
    r"/[0-9a-z]{6}002a0x\Z", re.IGNORECASE
)
AFFILIATE_TRACKER_GO_PATH_RE = re.compile(r"/go/[A-Za-z0-9]{8}\Z")
IPV4_RE = re.compile(r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])")
# Broad candidate matching plus ipaddress validation below catches both full and
# compressed IPv6 without mistaking ordinary timestamps for an address.
# Use identifier-aware boundaries so CSS pseudo-elements such as
# ``body::before`` cannot be parsed as the valid compressed address ``::bef``.
IPV6_RE = re.compile(
    r"(?<![A-Za-z0-9_:])[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?![A-Za-z0-9_:])"
)
URL_CREDENTIAL_RE = re.compile(
    r"(?i)(?:[?&](?:access_?token|api_?key|secret|password|signature|auth)="
    r"|https?://[^\s/@:]+:[^\s/@]+@)"
)
KNOWN_CREDENTIAL_RE = re.compile(
    r"(?i)(?:\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"
    r"|\bAIza[0-9A-Za-z_-]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\bsk-[A-Za-z0-9_-]{20,})"
)
SLACK_ROUTE_RE = re.compile(r"(?i)https?://app\.slack\.com/client/")
TELEGRAM_ID_RE = re.compile(r"(?i)\btelegram\b[^\r\n]{0,80}(?<!\d)-?\d{7,}(?!\d)")

PUBLIC_TEXT_SUFFIXES = frozenset({
    ".css", ".html", ".js", ".json", ".jsonl", ".md", ".svg", ".txt", ".xml",
})
PUBLIC_SOURCE_ROOTS = frozenset({"components", "release", "site"})
PUBLIC_ROOT_FILES = frozenset({"_redirects", "build_site.py", "robots.txt", "sitemap.xml"})


DIGEST_ALGORITHM_LENGTHS = {
    "md5": 32,
    "sha1": 40,
    "sha224": 56,
    "sha256": 64,
    "sha384": 96,
    "sha512": 128,
}
# Generic digest fields are accepted only at standard cryptographic hex
# lengths.  Short numeric checksums therefore cannot hide phone numbers.
GENERIC_DIGEST_LENGTHS = frozenset(DIGEST_ALGORITHM_LENGTHS.values())
GENERIC_DIGEST_FIELD_NAMES = frozenset({"hash", "digest", "fingerprint", "checksum"})


SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "auth_token",
    "api_key",
    "client_secret",
    "private_key",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "session_cookie",
    "webhook",
    "webhook_url",
}
PII_KEYS = {
    "email",
    "email_address",
    "buyer_email",
    "phone",
    "phone_number",
    "mobile",
    "mobile_number",
    "full_name",
    "customer_name",
    "customer_id",
    "account_number",
    "bank_account",
    "postal_address",
}
NETWORK_KEYS = {
    "ip",
    "ip_address",
    "public_ip",
    "host_ip",
    "ipv4",
    "ipv6",
}
OPERATIONAL_ID_KEYS = {
    "chat_id",
    "telegram_chat_id",
    "slack_channel_id",
    "slack_workspace_id",
    "workspace_id",
}
FINANCIAL_KEYS = {
    "revenue",
    "revenue_thb",
    "gross_revenue",
    "net_revenue",
    "payout",
    "commission_earned",
    "transaction_id",
    "order_id",
}


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _key_category(key: str) -> str | None:
    normal = _normalise_key(key)
    if normal in SECRET_KEYS or normal.endswith(("_access_token", "_refresh_token", "_api_key", "_client_secret", "_password", "_private_key")):
        return "CREDENTIAL_FIELD"
    if normal in PII_KEYS:
        return "PII_FIELD"
    if normal in NETWORK_KEYS:
        return "NETWORK_FIELD"
    if normal in OPERATIONAL_ID_KEYS:
        return "OPERATIONAL_IDENTIFIER_FIELD"
    if normal in FINANCIAL_KEYS:
        return "PRIVATE_FINANCIAL_FIELD"
    return None


def _digest_lengths_for_key(key: str) -> frozenset[int]:
    """Return permitted hex lengths only for an explicit digest-like field."""
    normal = _normalise_key(key)
    final_component = normal.rsplit("_", 1)[-1]
    algorithm_length = DIGEST_ALGORITHM_LENGTHS.get(final_component)
    if algorithm_length is not None:
        return frozenset({algorithm_length})
    if normal in GENERIC_DIGEST_FIELD_NAMES or any(
        normal.endswith("_" + field_name)
        for field_name in GENERIC_DIGEST_FIELD_NAMES
    ):
        return GENERIC_DIGEST_LENGTHS
    return frozenset()


def _is_validated_digest_field(key: str, value: str) -> bool:
    lengths = _digest_lengths_for_key(key)
    return bool(lengths and len(value) in lengths and HEX_DIGEST_RE.fullmatch(value))


@dataclass(frozen=True)
class _JsonNode:
    kind: str
    start: int
    end: int
    scalar: object | None = None
    content_span: tuple[int, int] | None = None
    members: tuple[tuple[str, "_JsonNode"], ...] = ()
    elements: tuple["_JsonNode", ...] = ()


class _JsonSpanParser:
    """Parse already-valid JSON while retaining exact string-value spans."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.decoder = json.JSONDecoder()

    def _skip_whitespace(self, index: int) -> int:
        while index < len(self.text) and self.text[index] in " \t\r\n":
            index += 1
        return index

    def parse(self) -> _JsonNode:
        start = self._skip_whitespace(0)
        node, end = self._parse_value(start)
        if self._skip_whitespace(end) != len(self.text):
            raise ValueError("trailing JSON content")
        return node

    def _parse_value(self, index: int) -> tuple[_JsonNode, int]:
        index = self._skip_whitespace(index)
        if index >= len(self.text):
            raise ValueError("missing JSON value")
        if self.text[index] == "{":
            return self._parse_object(index)
        if self.text[index] == "[":
            return self._parse_array(index)

        scalar, end = self.decoder.raw_decode(self.text, index)
        if isinstance(scalar, str):
            return (
                _JsonNode(
                    kind="string",
                    start=index,
                    end=end,
                    scalar=scalar,
                    content_span=(index + 1, end - 1),
                ),
                end,
            )
        return _JsonNode(kind="scalar", start=index, end=end, scalar=scalar), end

    def _parse_object(self, start: int) -> tuple[_JsonNode, int]:
        index = self._skip_whitespace(start + 1)
        members: list[tuple[str, _JsonNode]] = []
        if index < len(self.text) and self.text[index] == "}":
            end = index + 1
            return _JsonNode(kind="object", start=start, end=end), end

        while True:
            if index >= len(self.text) or self.text[index] != '"':
                raise ValueError("JSON object key is not a string")
            key_node, index = self._parse_value(index)
            if key_node.kind != "string" or not isinstance(key_node.scalar, str):
                raise ValueError("JSON object key is not a string")
            index = self._skip_whitespace(index)
            if index >= len(self.text) or self.text[index] != ":":
                raise ValueError("missing JSON object colon")
            value_node, index = self._parse_value(index + 1)
            members.append((key_node.scalar, value_node))
            index = self._skip_whitespace(index)
            if index >= len(self.text):
                raise ValueError("unterminated JSON object")
            if self.text[index] == "}":
                end = index + 1
                return (
                    _JsonNode(
                        kind="object",
                        start=start,
                        end=end,
                        members=tuple(members),
                    ),
                    end,
                )
            if self.text[index] != ",":
                raise ValueError("missing JSON object comma")
            index = self._skip_whitespace(index + 1)

    def _parse_array(self, start: int) -> tuple[_JsonNode, int]:
        index = self._skip_whitespace(start + 1)
        elements: list[_JsonNode] = []
        if index < len(self.text) and self.text[index] == "]":
            end = index + 1
            return _JsonNode(kind="array", start=start, end=end), end

        while True:
            element, index = self._parse_value(index)
            elements.append(element)
            index = self._skip_whitespace(index)
            if index >= len(self.text):
                raise ValueError("unterminated JSON array")
            if self.text[index] == "]":
                end = index + 1
                return (
                    _JsonNode(
                        kind="array",
                        start=start,
                        end=end,
                        elements=tuple(elements),
                    ),
                    end,
                )
            if self.text[index] != ",":
                raise ValueError("missing JSON array comma")
            index = self._skip_whitespace(index + 1)


def _validated_digest_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return valid digest leaf spans reached through explicit digest fields."""
    try:
        root = _JsonSpanParser(text).parse()
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
        # Any structural uncertainty leaves the text untouched for fail-closed
        # pattern scanning by the caller.
        return ()

    spans: list[tuple[int, int]] = []

    def visit(node: _JsonNode, inherited_lengths: frozenset[int]) -> None:
        if node.kind == "string":
            value = node.scalar
            if (
                inherited_lengths
                and isinstance(value, str)
                and len(value) in inherited_lengths
                and HEX_DIGEST_RE.fullmatch(value)
                and node.content_span is not None
            ):
                spans.append(node.content_span)
            return
        if node.kind == "object":
            for key, child in node.members:
                explicit_lengths = _digest_lengths_for_key(key)
                visit(child, explicit_lengths or inherited_lengths)
            return
        if node.kind == "array":
            for child in node.elements:
                visit(child, inherited_lengths)

    visit(root, frozenset())
    return tuple(spans)


def _mask_validated_digest_values(text: str) -> str:
    """Mask structurally validated digest leaves, preserving offsets and lines."""
    masked = list(text)
    for start, end in _validated_digest_spans(text):
        for index in range(start, end):
            if masked[index] not in "\r\n":
                masked[index] = " "
    return "".join(masked)


def _is_validated_affiliate_tracker_url(value: str) -> bool:
    """Recognise only exact, credential-free AccessTrade tracker URLs.

    Query strings and fragments are rejected so a real phone number cannot be
    concealed in tracker parameters.  A strict path grammar also prevents an
    attacker from appending a phone number to an otherwise valid campaign URL.
    """
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != "atth.me"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        return False
    return bool(
        AFFILIATE_TRACKER_DIRECT_PATH_RE.fullmatch(parsed.path)
        or AFFILIATE_TRACKER_GO_PATH_RE.fullmatch(parsed.path)
    )


def _mask_validated_affiliate_tracker_urls(text: str) -> str:
    """Mask only validated tracker substrings, preserving offsets and lines."""
    masked = list(text)
    for match in AFFILIATE_TRACKER_CANDIDATE_RE.finditer(text):
        if not _is_validated_affiliate_tracker_url(match.group(0)):
            continue
        for index in range(match.start(), match.end()):
            if masked[index] not in "\r\n":
                masked[index] = " "
    return "".join(masked)


def is_scoped_path(relative_path: str) -> bool:
    """Return whether a path can feed public controls, source or build output."""
    path = PurePosixPath(relative_path.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return False
    suffix = path.suffix.lower()
    if path.parts[0] == ".system_control":
        return suffix in {".json", ".jsonl"}
    if path.parts[0] == "automation-log":
        if suffix in {".json", ".jsonl", ".csv", ".log"}:
            return True
        name_upper = path.name.upper()
        return suffix == ".md" and (name_upper.startswith("FACTS") or path.name.lower() == "latest.md")
    if len(path.parts) == 1:
        return path.name in PUBLIC_ROOT_FILES or suffix == ".html"
    return path.parts[0] in PUBLIC_SOURCE_ROOTS and (
        suffix in PUBLIC_TEXT_SUFFIXES or path.name in PUBLIC_ROOT_FILES
    )


def _generated_public_paths(repo_root: Path) -> set[str]:
    """Enumerate ignored public build/source text without following symlinks."""
    paths: set[str] = set()
    for root_name in PUBLIC_SOURCE_ROOTS:
        top = repo_root / root_name
        if not top.is_dir():
            continue
        for current, directories, filenames in os.walk(top, followlinks=False):
            # A symlinked directory must not become an unbounded traversal root.
            directories[:] = [
                name for name in directories
                if not (Path(current) / name).is_symlink()
            ]
            for filename in filenames:
                candidate = Path(current) / filename
                try:
                    relative = candidate.relative_to(repo_root).as_posix()
                except ValueError:
                    continue
                if is_scoped_path(relative):
                    paths.add(relative)
    return paths


def _candidate_paths(repo_root: Path) -> tuple[list[str], list[Finding]]:
    """Return tracked plus untracked/non-ignored files in the public scope."""
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo_root), "ls-files", "-z",
                "--cached", "--others", "--exclude-standard",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, ValueError):
        return [], [Finding(".", 1, "GIT_INDEX_UNAVAILABLE")]
    if result.returncode != 0:
        return [], [Finding(".", 1, "GIT_INDEX_UNAVAILABLE")]
    try:
        raw_paths = result.stdout.decode("utf-8", errors="strict").split("\0")
    except UnicodeDecodeError:
        return [], [Finding(".", 1, "GIT_INDEX_UNREADABLE")]
    for raw_path in raw_paths:
        if raw_path and any(ord(character) < 32 for character in raw_path):
            return [], [Finding(".", 1, "UNSAFE_TRACKED_PATH")]
    paths = {
        p.replace("\\", "/")
        for p in raw_paths
        if p and is_scoped_path(p)
    }
    paths.update(_generated_public_paths(repo_root))
    paths = sorted(paths)
    return paths, []


def _network_findings(line: str) -> set[str]:
    categories: set[str] = set()
    for candidate in IPV4_RE.findall(line):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not address.is_unspecified and not address.is_loopback:
            categories.add("NETWORK_ADDRESS")
    for candidate in IPV6_RE.findall(line):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not address.is_unspecified and not address.is_loopback:
            categories.add("NETWORK_ADDRESS")
    return categories


def _line_categories(line: str, pattern_scan_line: str | None = None) -> set[str]:
    categories: set[str] = set()
    for match in JSON_KEY_RE.finditer(line):
        category = _key_category(match.group("key"))
        if category:
            categories.add(category)
    scan_line = line if pattern_scan_line is None else pattern_scan_line
    if EMAIL_RE.search(scan_line):
        categories.add("EMAIL_ADDRESS")
    if PHONE_RE.search(scan_line):
        categories.add("PHONE_NUMBER")
    categories.update(_network_findings(scan_line))
    if URL_CREDENTIAL_RE.search(scan_line) or KNOWN_CREDENTIAL_RE.search(scan_line):
        categories.add("CREDENTIAL_VALUE")
    if SLACK_ROUTE_RE.search(scan_line) or TELEGRAM_ID_RE.search(scan_line):
        categories.add("OPERATIONAL_IDENTIFIER")
    return categories


def _strict_json_loads(text: str) -> object:
    """Parse standards-compliant JSON; Python's NaN/Infinity extension is unsafe."""
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON constant: " + value)

    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    document = json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for nested in item.values():
                require_finite(nested)
        elif isinstance(item, list):
            for nested in item:
                require_finite(nested)

    require_finite(document)
    return document


def _validate_json(text: str, relative_path: str) -> list[Finding]:
    try:
        _strict_json_loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        line = exc.lineno if isinstance(exc, json.JSONDecodeError) else 1
        return [Finding(relative_path, max(1, line), "MALFORMED_JSON")]
    return []


def _validate_jsonl(lines: Sequence[str], relative_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            _strict_json_loads(line)
        except (json.JSONDecodeError, ValueError):
            findings.append(Finding(relative_path, line_number, "MALFORMED_JSONL"))
    return findings


def _scan_csv(text: str, relative_path: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        reader = csv.reader(io.StringIO(text), strict=True)
        rows = list(reader)
    except csv.Error:
        return [Finding(relative_path, 1, "MALFORMED_CSV")]
    if not rows:
        return findings

    sensitive_columns: list[int] = []
    for index, header in enumerate(rows[0]):
        category = _key_category(header)
        if category:
            sensitive_columns.append(index)
            findings.append(Finding(relative_path, 1, category))

    sales_file = "sales" in PurePosixPath(relative_path).stem.lower()
    for line_number, row in enumerate(rows[1:], 2):
        if not any(cell.strip() for cell in row):
            continue
        if sales_file:
            findings.append(Finding(relative_path, line_number, "SALES_RECORD"))
        if any(index < len(row) and row[index].strip() for index in sensitive_columns):
            findings.append(Finding(relative_path, line_number, "SENSITIVE_RECORD"))
    return findings


def scan_file(repo_root: Path, relative_path: str) -> list[Finding]:
    root = repo_root.resolve()
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        if candidate.is_symlink():
            return [Finding(relative_path, 1, "UNSAFE_TRACKED_SYMLINK")]
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        return [Finding(relative_path, 1, "UNREADABLE_TRACKED_FILE")]
    if not resolved.is_file():
        return [Finding(relative_path, 1, "UNREADABLE_TRACKED_FILE")]
    try:
        size = resolved.stat().st_size
    except OSError:
        return [Finding(relative_path, 1, "UNREADABLE_TRACKED_FILE")]
    if size > MAX_FILE_BYTES:
        return [Finding(relative_path, 1, "OVERSIZE_TRACKED_FILE")]
    try:
        text = resolved.read_bytes().decode("utf-8-sig", errors="strict")
    except (OSError, UnicodeDecodeError):
        return [Finding(relative_path, 1, "UNREADABLE_TRACKED_FILE")]

    lines = text.splitlines()
    findings: list[Finding] = []
    suffix = resolved.suffix.lower()
    validation_findings: list[Finding] = []
    # Plain structured/log-like text can contain an exact affiliate tracker.
    # Mask only its validated URL span; nearby numbers remain fully scannable.
    pattern_scan_lines = _mask_validated_affiliate_tracker_urls(text).splitlines()
    if suffix == ".json":
        validation_findings = _validate_json(text, relative_path)
        if not validation_findings:
            masked_text = _mask_validated_digest_values(text)
            masked_text = _mask_validated_affiliate_tracker_urls(masked_text)
            masked_lines = masked_text.splitlines()
            if len(masked_lines) == len(lines):
                pattern_scan_lines = masked_lines
        else:
            # Structural uncertainty keeps the original fail-closed scan.
            pattern_scan_lines = lines
    elif suffix == ".jsonl":
        validation_findings = _validate_jsonl(lines, relative_path)
        pattern_scan_lines = []
        for line in lines:
            if not line.strip():
                pattern_scan_lines.append(line)
                continue
            try:
                _strict_json_loads(line)
            except (json.JSONDecodeError, ValueError):
                # Malformed records receive the original fail-closed scan.
                pattern_scan_lines.append(line)
            else:
                masked_line = _mask_validated_digest_values(line)
                pattern_scan_lines.append(
                    _mask_validated_affiliate_tracker_urls(masked_line)
                )

    for line_number, (line, pattern_scan_line) in enumerate(
        zip(lines, pattern_scan_lines), 1
    ):
        for category in _line_categories(line, pattern_scan_line):
            findings.append(Finding(relative_path, line_number, category))

    findings.extend(validation_findings)
    if suffix == ".jsonl":
        if "sales" in resolved.stem.lower():
            for line_number, line in enumerate(lines, 1):
                if line.strip():
                    findings.append(Finding(relative_path, line_number, "SALES_RECORD"))
    elif suffix == ".csv":
        findings.extend(_scan_csv(text, relative_path))
    return sorted(set(findings))


def scan_repository(repo_root: Path | str = REPO_ROOT) -> tuple[list[Finding], int, bool]:
    root = Path(repo_root)
    candidates, index_findings = _candidate_paths(root)
    if index_findings:
        return index_findings, 0, True
    findings: list[Finding] = []
    for relative_path in candidates:
        findings.extend(scan_file(root, relative_path))
    return sorted(set(findings)), len(candidates), False


def render_findings(findings: Iterable[Finding]) -> str:
    return "\n".join(
        "%s:%d [%s]" % (finding.path, finding.line, finding.category)
        for finding in sorted(set(findings))
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan public-repo candidate logs without echoing values."
    )
    parser.add_argument("--repo", default=str(REPO_ROOT), help="Repository root (default: this repository)")
    args = parser.parse_args(argv)

    findings, scanned_count, operational_error = scan_repository(args.repo)
    rendered = render_findings(findings)
    if rendered:
        print(rendered)
    if findings:
        print(
            "privacy-guard: FAIL (%d finding(s), %d candidate file(s) scanned)"
            % (len(findings), scanned_count)
        )
        return 2 if operational_error else 1
    print("privacy-guard: PASS (%d candidate file(s) scanned)" % scanned_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
