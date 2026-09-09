#!/usr/bin/env python3
"""Fail closed when public copy uses an unreviewed merchant or promotion.

Product availability and promotion validity are deliberately separate.  An
expired rate/speed campaign must not remove a still-available product CTA, but
its dated claims must disappear from public copy on the expiry date.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import date
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import parse_qsl, unquote, unquote_to_bytes, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / ".system_control" / "merchant_offers.json"
DEFAULT_OWN_PRODUCT_POLICY = ROOT / ".system_control" / "policy.json"
_PUBLIC_ROOT_HTML = (
    "budget-503020-infographic.html",
    "car-insurance-infographic.html",
    "car-pawn-not-paid-off.html",
    "car-refinance-infographic.html",
    "debt-calculator.html",
    "debt-freedom-clock.html",
    "debt-health-check.html",
    "debt-letter-kit.html",
    "debt-payoff-infographic.html",
    "home-land-for-cash-infographic.html",
    "loan-approval-compare.html",
    "motorcycle-title-loan-infographic.html",
    "old-car-financing-20years.html",
    "refinance-savings-calculator.html",
    "workshop-hr.html",
)
# Explicit allow-list: these are live build inputs, not archive/quarantine/report
# material.  The legacy credit-card-salary-30000.html alias is intentionally not
# scanned because it is never published and redirects to the canonical 2026 page.
DEFAULT_SOURCES = (
    ROOT / "build_site.py",
    ROOT / ".system_control" / "content_manifest.json",
    *(ROOT / name for name in _PUBLIC_ROOT_HTML),
)

_ANCHOR_RE = re.compile(r"<a\b[^>]*>", re.I | re.S)
_CRITICAL_ANCHOR_ATTRS = {
    "href", "rel", "data-provider", "data-content-id",
}
_UNQUOTED_CRITICAL_ATTR_RE = re.compile(
    r"\b(?:href|rel|data-provider|data-content-id)\s*=\s*(?![\"'])",
    re.I,
)
_TRACKER_LITERAL_RE = re.compile(
    r"https://atth\.me/((?:go/)?[0-9A-Za-z]+)", re.I)
_ATTH_URL_CANDIDATE_RE = re.compile(
    r"https://atth\.me/[^\s\"'<>`]*", re.I)
_JS_CONCAT_GAP_RE = re.compile(
    r"(?:\s|[()]|/\*.*?\*/|//[^\r\n]*(?:\r?\n|$))*"
    r"\+"
    r"(?:\s|[()]|/\*.*?\*/|//[^\r\n]*(?:\r?\n|$))*",
    re.S,
)
_RUNTIME_TRACKER_RE = re.compile(
    r"(?<![a-z0-9+.-])(?:https?:)?//"
    r"(?:[a-z0-9-]+\.)*atth\.me(?=$|[/:?#])"
    r"[^\s\"'<>`]*",
    re.I,
)
_IDNA_DOT_TRANSLATION = str.maketrans({"\u3002": ".", "\uff0e": ".", "\uff61": "."})
_IDNA_IGNORED_RE = re.compile(
    "[\u00ad\u034f\u1806\u180b-\u180f\u200b\u2060\u2064\ufe00-\ufe0f\ufeff"
    "\U000e0100-\U000e01ef]"
)
_TEMPLATE_EXPRESSION_RE = re.compile(r"\$\{([^{}]*)\}", re.S)
_JS_EXPRESSION_WRAPPER_RE = re.compile(
    r"(?:\s|[()]|/\*.*?\*/|//[^\r\n]*(?:\r?\n|$))*",
    re.S,
)
_JS_TEMPLATE_CHAIN_GAP_RE = re.compile(
    r"(?:\s|[()+${}]|/\*.*?\*/|//[^\r\n]*(?:\r?\n|$))*",
    re.S,
)
MAX_EXECUTABLE_SURFACE_CHARS = 1_000_000
MAX_EXECUTABLE_HTML_TOTAL_CHARS = 2_000_000
MAX_EXECUTABLE_LITERAL_COUNT = 4096
MAX_NESTED_EXECUTABLE_DEPTH = 4
MAX_NESTED_EXECUTABLE_DOCUMENTS = 64
MAX_PERCENT_DECODE_LAYERS = 4
_EXECUTABLE_SCRIPT_TYPES = frozenset({
    "module",
    "application/ecmascript",
    "application/javascript",
    "application/x-ecmascript",
    "application/x-javascript",
    "text/ecmascript",
    "text/javascript",
    "text/javascript1.0",
    "text/javascript1.1",
    "text/javascript1.2",
    "text/javascript1.3",
    "text/javascript1.4",
    "text/javascript1.5",
    "text/jscript",
    "text/livescript",
    "text/x-ecmascript",
    "text/x-javascript",
})
_ATTRIBUTION_QUERY_KEYS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content",
})
_ATTRIBUTION_VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,159}")
_NETWORK_FIELDS = (
    "affiliate_network",
    "network_campaign_id",
    "network_status",
    "network_verified_on",
    "tracking_urls",
)
_EXPECTED_NETWORK_STATUS = {
    "active": "approved",
    "paused": "paused",
    "retired": "retired",
}
_PAUSED_OFFER_MARKER = 'data-offer-status="paused"'
_PAUSED_PURCHASE_TOKENS = {
    "data-buy=": "buy-intent attribute",
    'rel="sponsored': "sponsored link",
    "atth.me/": "affiliate endpoint",
    "line.me/": "LINE order endpoint",
    "gumroad.com/": "checkout endpoint",
    "promptpay": "PromptPay instruction",
    "\u0e1e\u0e23\u0e49\u0e2d\u0e21\u0e40\u0e1e\u0e22\u0e4c": "PromptPay instruction",
    "\u0e2a\u0e48\u0e07\u0e2a\u0e25\u0e34\u0e1b": "slip-delivery instruction",
    "199\u0e3f": "paused-product price",
}


def _strict_json_loads(value: str) -> object:
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    document = json.loads(
        value,
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


def _stable_text(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"source must not be a symlink: {path}")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if ((before.st_size, before.st_mtime_ns) !=
            (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size):
        raise ValueError(f"source changed while being read: {path}")
    return raw.decode("utf-8-sig")


def default_sources(root: Path = ROOT) -> tuple[Path, ...]:
    fixed = tuple(root / path.relative_to(ROOT) for path in DEFAULT_SOURCES)
    knowledge = tuple(sorted((root / "automation-log").glob("KNOWLEDGE-POSTS*.md")))
    return fixed + knowledge


def select_sources(paths: list[Path] | tuple[Path, ...], *,
                   generated_site: Path | None = None,
                   root: Path = ROOT) -> tuple[Path, ...]:
    """Select source-copy inputs and, only when requested, generated HTML.

    ``build_site.py`` runs the default source-copy gate before generating its
    output and then calls this gate again with ``site`` after generation.  An
    implicit site/ dependency would make a clean build fail or validate stale
    output from a prior build.  Runtime control callers that need placement
    coverage must therefore opt in explicitly and fail closed if that directory
    is missing or empty.
    """
    selected = list(paths) if paths else list(default_sources(root))
    if generated_site is not None:
        selected.append(generated_site)
    return tuple(selected)


def resolve_sources(paths: list[Path] | tuple[Path, ...]) -> tuple[Path, ...]:
    """Expand generated output to public HTML plus its redirect surface.

    ``site/_redirects`` can expose an affiliate tracker even when no HTML anchor
    does.  Treat a generated directory without that file as incomplete rather
    than silently claiming full placement coverage.
    """
    resolved: list[Path] = []
    for path in paths:
        if path.is_dir():
            pages = sorted(path.glob("*.html"))
            if not pages:
                raise ValueError(f"source directory has no HTML: {path}")
            scripts = sorted(path.glob("*.js"))
            redirects = path / "_redirects"
            if not redirects.is_file():
                raise ValueError(f"source directory has no _redirects: {path}")
            resolved.extend(pages)
            resolved.extend(scripts)
            resolved.append(redirects)
        else:
            resolved.append(path)
    return tuple(dict.fromkeys(path.resolve() for path in resolved))


def _publishable_text(path: Path, today: date) -> str:
    """Read current/future outward copy while excluding immutable history rows."""
    text = _stable_text(path)
    if path.name == "content_manifest.json":
        payload = _strict_json_loads(text)
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError("content manifest has no items list")
        future = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"content manifest item {index} is not an object")
            try:
                item_date = date.fromisoformat(str(item.get("date", "")))
            except ValueError as exc:
                raise ValueError(
                    f"content manifest item {index} has invalid date") from exc
            if item_date >= today:
                future.append(item)
        return json.dumps(future, ensure_ascii=False, sort_keys=True)
    if path.name.startswith("KNOWLEDGE-POSTS") and path.suffix.lower() == ".md":
        rows = []
        for line in text.splitlines():
            match = re.match(r"^\|\s*(20\d\d-\d\d-\d\d)\s*\|", line)
            if not match:
                continue
            try:
                row_date = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if row_date >= today:
                rows.append(line)
        return "\n".join(rows)
    return text


def load_documents(paths: list[Path] | tuple[Path, ...], today: date) -> dict[str, str]:
    return {str(path): _publishable_text(path, today)
            for path in resolve_sources(paths)}


def load_registry(path: Path) -> dict:
    payload = _strict_json_loads(_stable_text(path))
    if not isinstance(payload, dict):
        raise ValueError("registry must be a JSON object")
    return payload


def _tracker_base(value: object) -> str:
    """Return one exact tracker path with only bounded UTM attribution."""
    text = _browser_url_text(value)
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if (
        parsed.scheme.casefold() != "https"
        or parsed.netloc.casefold() != "atth.me"
        or bool(parsed.fragment)
        or re.fullmatch(r"/(?:go/)?[0-9A-Za-z]+", parsed.path or "") is None
    ):
        return ""
    if "?" in text and not parsed.query:
        return ""
    if parsed.query:
        try:
            pairs = parse_qsl(
                parsed.query, keep_blank_values=True, strict_parsing=True,
            )
        except ValueError:
            return ""
        keys = [key for key, _value in pairs]
        if (
            not pairs
            or len(keys) != len(set(keys))
            or any(key not in _ATTRIBUTION_QUERY_KEYS for key in keys)
            or any(_ATTRIBUTION_VALUE_RE.fullmatch(value) is None
                   for _key, value in pairs)
        ):
            return ""
    return "https://atth.me" + parsed.path


class _AnchorAttributeParser(HTMLParser):
    """Parse one opening anchor while preserving duplicate attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[list[tuple[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.casefold() == "a":
            self.anchors.append(list(attrs))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)


def _anchor_attributes(tag: str) -> tuple[dict[str, str], list[str]]:
    """Return normalized critical attributes and conservative parse errors."""
    errors: list[str] = []
    if _UNQUOTED_CRITICAL_ATTR_RE.search(tag):
        errors.append("anchor critical attributes must be quoted")
    parser = _AnchorAttributeParser()
    try:
        parser.feed(tag)
        parser.close()
    except (AssertionError, ValueError) as exc:
        return {}, [f"anchor cannot be parsed safely: {type(exc).__name__}"]
    if len(parser.anchors) != 1:
        return {}, ["anchor cannot be parsed unambiguously"]
    values: dict[str, str] = {}
    seen: set[str] = set()
    for raw_name, raw_value in parser.anchors[0]:
        name = str(raw_name or "").casefold()
        if name not in _CRITICAL_ANCHOR_ATTRS:
            continue
        if name in seen:
            errors.append(f"anchor attribute {name} is duplicated")
            continue
        seen.add(name)
        if raw_value is None:
            errors.append(f"anchor attribute {name} has no value")
            continue
        values[name] = html.unescape(str(raw_value)).strip()
    return values, errors


def _placements(
    documents: dict[str, str],
) -> tuple[list[tuple[str, str, str, str, str]], list[str]]:
    """Return parsed placements plus fail-closed anchor syntax findings."""
    rows: list[tuple[str, str, str, str, str]] = []
    failures: list[str] = []
    for name, text in documents.items():
        # Python generators contain deliberately unreachable/fallback templates.
        # Placement eligibility is checked against the generated HTML at the end
        # of build_site.py; promotional claim tokens are still scanned in source.
        if str(name).lower().endswith(".py"):
            continue
        for tag in _ANCHOR_RE.findall(text):
            attrs, parse_errors = _anchor_attributes(tag)
            if parse_errors:
                failures.extend(f"{name}: {message}" for message in parse_errors)
                continue
            href_value = attrs.get("href", "")
            normalized_href = _browser_url_text(href_value)
            rel_tokens = set(attrs.get("rel", "").casefold().split())
            # The interstitial template has an inert href="" placeholder that is
            # populated from an already-reviewed source anchor at runtime. It is
            # not itself a public placement. Every non-inert affiliate link is.
            inert = (not href_value or href_value.startswith("#") or
                     _javascript_payload(href_value) is not None)
            is_affiliate = (not inert and ("sponsored" in rel_tokens or
                            re.match(r"https://(?:[^/]+\.)?atth\.me(?:/|$)",
                                     normalized_href, re.I) is not None or
                            re.match(r"/go(?:/|$)", href_value) is not None))
            if not is_affiliate:
                continue
            provider = attrs.get("data-provider", "").casefold()
            content = attrs.get("data-content-id", "")
            if re.fullmatch(r"[a-z0-9_-]+", provider) is None:
                provider = ""
            if re.fullmatch(r"[a-z0-9._-]+", content) is None:
                content = ""
            rows.append((name, provider, content,
                         _tracker_base(href_value), href_value))
    return rows, list(dict.fromkeys(failures))


def _internal_go_path(value: object) -> str:
    """Return one canonical own-site /go route path, or an empty string."""
    try:
        parsed = urlsplit(str(value or ""))
    except ValueError:
        return ""
    netloc = parsed.netloc.casefold()
    own_host = not netloc or netloc in {
        "ngernduangold.com", "www.ngernduangold.com",
    }
    path = parsed.path or ""
    if (
        not own_host
        or parsed.scheme.casefold() not in {"", "https"}
        or bool(parsed.query)
        or bool(parsed.fragment)
        or re.fullmatch(r"/go/[a-z0-9._-]+", path, re.I) is None
    ):
        return ""
    return path.casefold()


def _redirect_routes(
    documents: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    """Parse exact /go source routes from generated Netlify redirect files."""
    routes: dict[str, str] = {}
    failures: list[str] = []
    for name, text in documents.items():
        if Path(name).name != "_redirects":
            continue
        for line_number, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            source = _internal_go_path(fields[0]) if fields else ""
            if not source:
                continue
            if len(fields) < 2:
                failures.append(
                    f"{name}:{line_number}: internal affiliate redirect has no target")
                continue
            target = fields[1]
            if len(fields) != 3 or fields[2] != "301!":
                failures.append(
                    f"{name}:{line_number}: internal /go redirect must be one forced 301 route")
            previous = routes.get(source)
            if previous is not None:
                failures.append(
                    f"{name}:{line_number}: internal affiliate redirect {source} is duplicated")
                continue
            routes[source] = target
    return routes, failures


_CLAIM_BLOCK_BREAK_RE = re.compile(
    r"(?:\r?\n\s*\r?\n|</(?:p|li|div|section|article|h[1-6]|tr)>\s*)",
    re.I,
)


def _claim_blocks(text: str) -> list[str]:
    """Return conservative copy blocks used for occurrence-scoped qualifiers."""
    return [block for block in _CLAIM_BLOCK_BREAK_RE.split(text) if block.strip()]


def _decode_script_escapes(value: str) -> str:
    """Decode bounded, deterministic escapes that can conceal a tracker URL."""
    # Script elements are raw-text nodes: HTML character references in their
    # bodies stay literal. Inline event attributes have already been decoded by
    # HTMLParser before reaching this function.
    text = value

    def codepoint(match: re.Match[str]) -> str:
        number = int(match.group(1), 16)
        if number > 0x10FFFF or 0xD800 <= number <= 0xDFFF:
            return match.group(0)
        return chr(number)

    def octal_codepoint(match: re.Match[str]) -> str:
        number = int(match.group(1), 8)
        return chr(number) if number <= 0xFF else match.group(0)

    for _ in range(4):
        previous = text
        text = re.sub(r"\\(?:\r\n|[\r\n])", "", text)
        # A JSON string embedded in JavaScript can carry one extra escaping
        # layer before a later JSON.parse/decode step exposes the URL.
        text = re.sub(r"\\\\(?=(?:u\{|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|/))",
                      r"\\", text)
        text = re.sub(r"\\u\{([0-9a-fA-F]{1,6})\}", codepoint, text)
        text = re.sub(r"\\u([0-9a-fA-F]{4})", codepoint, text)
        text = re.sub(r"\\x([0-9a-fA-F]{2})", codepoint, text)
        # Classic non-module JavaScript still accepts legacy octal escapes.
        text = re.sub(r"\\([0-7]{1,3})", octal_codepoint, text)
        text = text.replace(r"\/", "/")
        text = text.replace(r"\t", "\t").replace(r"\r", "\r").replace(r"\n", "\n")
        text = text.replace("\\\\", "\\")
        if text == previous:
            break
    # WHATWG URL host parsing applies Unicode compatibility/IDNA mappings.  The
    # bounded normalization covers full-width ASCII and the three IDNA dot
    # aliases without attempting arbitrary visual-confusable folding.
    text = text.translate(_IDNA_DOT_TRANSLATION)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_IDNA_DOT_TRANSLATION)
    text = _IDNA_IGNORED_RE.sub("", text)
    # WHATWG special-scheme parsing treats slash/backslash runs after http(s)
    # as authority separators and strips ASCII tab/newline/CR from URLs.
    text = text.replace("\t", "").replace("\r", "").replace("\n", "")
    text = re.sub(r"(?i)\b(https?):[\\/]+", r"\1://", text)
    return text.replace("\\", "/")


_URL_AUTHORITY_RE = re.compile(
    r"^((?:[a-z][a-z0-9+.-]*:)?//)([^/?#]*)(.*)$", re.I | re.S,
)


def _browser_url_text(value: object, *, decode_html_entities: bool = True) -> str:
    """Return a bounded browser-like spelling for URL security comparisons.

    Browser URL parsing strips ASCII tab/newline controls, applies Unicode/IDNA
    mappings, percent-decodes special-scheme hosts and accepts backslashes as
    authority separators.  Normalizing those deterministic aliases before any
    allow-list comparison prevents a visually different host from bypassing the
    merchant registry.
    """
    text = str(value or "")
    if decode_html_entities:
        text = html.unescape(text)
    text = _decode_script_escapes(text)
    text = text.replace("\t", "").replace("\r", "").replace("\n", "")
    text = text.strip("\x00\x0b\x0c \u0085\u00a0")
    match = _URL_AUTHORITY_RE.match(text)
    if match is None:
        return text
    prefix, authority, suffix = match.groups()
    userinfo = ""
    host_port = authority
    if "@" in host_port:
        userinfo, host_port = host_port.rsplit("@", 1)
        userinfo += "@"
    port = ""
    host = host_port
    if host.startswith("["):
        closing = host.find("]")
        if closing >= 0:
            port = host[closing + 1:]
            host = host[:closing + 1]
    elif ":" in host:
        possible_host, separator, possible_port = host.rpartition(":")
        if separator and (not possible_port or possible_port.isdigit()):
            host, port = possible_host, separator + possible_port
    try:
        host = unquote(host, errors="strict")
    except UnicodeDecodeError:
        return text
    host = _decode_script_escapes(host).rstrip(".")
    if host and not host.startswith("["):
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return text
    return prefix + userinfo + host.casefold() + port + suffix


def _javascript_payload(value: object) -> str | None:
    """Return code carried by a browser-recognized javascript: URL."""
    text = html.unescape(str(value or "")).strip()
    compact = text.replace("\t", "").replace("\r", "").replace("\n", "")
    if not compact.casefold().startswith("javascript:"):
        return None
    return compact.split(":", 1)[1]


def _percent_decoded_variants(value: str) -> list[str]:
    """Project bounded decodeURIComponent-style constant transformations."""
    variants = [value]
    current = value
    for _ in range(MAX_PERCENT_DECODE_LAYERS):
        try:
            decoded = unquote(current, errors="strict")
        except UnicodeDecodeError:
            break
        if decoded == current:
            break
        variants.append(decoded)
        current = decoded
    return variants


def _data_url_payload(value: object) -> tuple[str, str] | None:
    """Decode a bounded constant data: URL for nested code/document scanning."""
    text = html.unescape(str(value or "")).strip()
    compact = text.replace("\t", "").replace("\r", "").replace("\n", "")
    if not compact.casefold().startswith("data:"):
        return None
    if len(compact) > MAX_EXECUTABLE_SURFACE_CHARS * 2:
        raise ValueError("data URL exceeds bounded encoded size")
    try:
        header, payload = compact[5:].split(",", 1)
    except ValueError as exc:
        raise ValueError("data URL has no payload separator") from exc
    fields = [field.strip() for field in header.split(";")]
    mime = fields[0].casefold() if fields and "/" in fields[0] else "text/plain"
    is_base64 = any(field.casefold() == "base64" for field in fields[1:])
    raw = unquote_to_bytes(payload)
    if is_base64:
        try:
            raw = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("data URL has invalid base64 payload") from exc
    if len(raw) > MAX_EXECUTABLE_SURFACE_CHARS:
        raise ValueError("data URL decoded payload exceeds bounded size")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("data URL executable payload is not UTF-8") from exc
    return mime, decoded


def _js_string_literals(script: str) -> list[tuple[int, int, str, str]]:
    """Tokenize quoted JS strings while ignoring line and block comments."""
    literals: list[tuple[int, int, str, str]] = []
    index = 0
    length = len(script)
    while index < length:
        char = script[index]
        following = script[index + 1] if index + 1 < length else ""
        if char == "/" and following == "/":
            newline = script.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if char == "/" and following == "*":
            closing = script.find("*/", index + 2)
            index = length if closing < 0 else closing + 2
            continue
        if char not in {'"', "'", "`"}:
            index += 1
            continue
        quote = char
        start = index
        index += 1
        raw: list[str] = []
        while index < length:
            char = script[index]
            if char == "\\" and index + 1 < length:
                raw.extend((char, script[index + 1]))
                index += 2
                continue
            if char == quote:
                index += 1
                literals.append((
                    start,
                    index,
                    _decode_script_escapes("".join(raw)),
                    quote,
                ))
                break
            raw.append(char)
            index += 1
    return literals


def _constant_string_expression(expression: str) -> str | None:
    """Evaluate only a bounded expression of quoted constants, ``+`` and parens."""
    literals = _js_string_literals(expression)
    if not literals:
        return None
    if _JS_EXPRESSION_WRAPPER_RE.fullmatch(expression[:literals[0][0]]) is None:
        return None
    for left, right in zip(literals, literals[1:]):
        if _JS_CONCAT_GAP_RE.fullmatch(expression[left[1]:right[0]]) is None:
            return None
    if _JS_EXPRESSION_WRAPPER_RE.fullmatch(expression[literals[-1][1]:]) is None:
        return None
    values = [
        _fold_template_literal(literal[2]) if literal[3] == "`" else literal[2]
        for literal in literals
    ]
    return "".join(values)


def _fold_template_literal(value: str) -> str:
    """Fold only static ``${...}`` string expressions inside one template."""
    text = value
    for _ in range(8):
        changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            folded = _constant_string_expression(match.group(1))
            if folded is None:
                return match.group(0)
            changed = True
            return folded

        text = _TEMPLATE_EXPRESSION_RE.sub(replace, text)
        if not changed:
            break
    return text


def _literal_static_value(literal: tuple[int, int, str, str]) -> str:
    value = literal[2]
    if literal[3] != "`":
        return value
    # The recursive fold handles intact templates.  Removing only template
    # delimiters also projects nested constant templates that the bounded lexer
    # splits at an inner backtick; identifiers/operators remain and therefore
    # cannot be mistaken for a constant URL.
    value = _fold_template_literal(value)
    # A complete unresolved interpolation is dynamic.  Keep a hard separator
    # in its place so an identifier such as ``atth`` cannot be projected into
    # a host that the program never constructs.  Unbalanced ${ / } fragments
    # are still removed below because the lexer uses them only at boundaries of
    # a nested template literal; adjacent static literals remain inspectable.
    value = _TEMPLATE_EXPRESSION_RE.sub("\x00", value)
    return value.replace("${", "").replace("$", "").replace("{", "").replace("}", "")


def _static_string_chain_gap(value: str) -> bool:
    if _JS_CONCAT_GAP_RE.fullmatch(value) is not None:
        return True
    return (
        _JS_TEMPLATE_CHAIN_GAP_RE.fullmatch(value) is not None
        and any(marker in value for marker in ("${", "}"))
    )


def _script_constant_strings(script: str) -> list[str]:
    """Return decoded JS literals and adjacent ``literal + literal`` chains."""
    if len(script) > MAX_EXECUTABLE_SURFACE_CHARS:
        raise ValueError("executable JavaScript surface exceeds bounded size")
    literals = _js_string_literals(script)
    if len(literals) > MAX_EXECUTABLE_LITERAL_COUNT:
        raise ValueError("executable JavaScript literal count exceeds bound")
    values: list[str] = []
    for index, literal in enumerate(literals):
        first = _literal_static_value(literal)
        values.append(first)
        joined = first
        cursor = literal[1]
        next_index = index + 1
        joined_count = 1
        while next_index < len(literals):
            gap = script[cursor:literals[next_index][0]]
            if not _static_string_chain_gap(gap):
                break
            next_literal = literals[next_index]
            joined += _literal_static_value(next_literal)
            joined_count += 1
            cursor = literals[next_index][1]
            next_index += 1
        if joined_count > 1:
            values.append(joined)
    projected: list[str] = []
    for value in values:
        projected.extend(_percent_decoded_variants(value))
    return list(dict.fromkeys(projected))


_URL_BEARING_ATTRIBUTES = frozenset({
    "action", "data", "formaction", "href", "ping", "poster", "src", "xlink:href",
})
_NESTED_DOCUMENT_TAGS = frozenset({"embed", "frame", "iframe", "object"})
_JAVASCRIPT_DATA_MIME_TYPES = frozenset({
    "application/ecmascript", "application/javascript", "text/ecmascript",
    "text/javascript",
})
_HTML_DATA_MIME_TYPES = frozenset({
    "application/xhtml+xml", "image/svg+xml", "text/html",
})


class _ExecutableSurfaceParser(HTMLParser):
    """Collect browser code and URL sinks while excluding visible prose."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.code: list[str] = []
        self.destinations: list[tuple[str, str, str]] = []
        self.nested_documents: list[str] = []
        self._script_execution: list[bool] = []

    @staticmethod
    def _script_is_executable(attrs) -> bool:
        declared = [
            str(value or "").strip().casefold()
            for name, value in attrs
            if str(name or "").casefold() == "type"
        ]
        if not declared:
            return True
        if len(declared) != 1:
            # Ambiguous duplicate type attributes must not create a bypass.
            return True
        essence = declared[0].split(";", 1)[0].strip()
        return not essence or essence in _EXECUTABLE_SCRIPT_TYPES

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized_tag = tag.casefold()
        executable_script = False
        if normalized_tag == "script":
            executable_script = self._script_is_executable(attrs)
            self._script_execution.append(executable_script)
        normalized_attrs = [
            (str(raw_name or "").casefold(), str(raw_value or "").strip())
            for raw_name, raw_value in attrs
        ]
        for name, value in normalized_attrs:
            if not value:
                continue
            if name == "srcdoc":
                self.nested_documents.append(value)
            elif name.startswith("on"):
                self.code.append(value)
            elif name in _URL_BEARING_ATTRIBUTES:
                javascript = _javascript_payload(value)
                if javascript is not None:
                    self.code.append(javascript)
                elif normalized_tag == "a" and name == "href":
                    # Ordinary anchors are bound to provider/content identity by
                    # _placements. Their browser-canonical host is checked there.
                    continue
                elif normalized_tag == "script" and name == "src" and not executable_script:
                    continue
                elif name == "ping":
                    self.destinations.extend(
                        (normalized_tag, name, item) for item in value.split()
                    )
                else:
                    self.destinations.append((normalized_tag, name, value))
        if normalized_tag == "meta":
            attr_values: dict[str, list[str]] = {}
            for name, value in normalized_attrs:
                attr_values.setdefault(name, []).append(value)
            if any(value.casefold() == "refresh"
                   for value in attr_values.get("http-equiv", [])):
                for content in attr_values.get("content", []):
                    match = re.search(r"(?:^|;)\s*url\s*=\s*(.+)\s*$", content, re.I)
                    if match is not None:
                        self.destinations.append((
                            normalized_tag, "content",
                            match.group(1).strip().strip("\"'"),
                        ))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() == "script" and self._script_execution:
            self._script_execution.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._script_execution:
            self._script_execution.pop()

    def handle_data(self, data: str) -> None:
        if self._script_execution and self._script_execution[-1]:
            self.code.append(data)


def _runtime_tracker_candidates(path: Path, text: str) -> list[str]:
    """Find executable tracker destinations without scanning explanatory HTML."""
    if path.suffix.lower() == ".js":
        try:
            surfaces = _script_constant_strings(text)
        except ValueError:
            return ["unsafe-oversized-executable-javascript"]
        return list(dict.fromkeys(
            match.group(0)
            for surface in surfaces
            for match in _RUNTIME_TRACKER_RE.finditer(
                _browser_url_text(surface, decode_html_entities=False)
            )
        ))
    if path.suffix.lower() != ".html":
        return []

    candidates: list[str] = []
    executable_chars = 0
    document_count = 0

    def charge(size: int) -> None:
        nonlocal executable_chars
        executable_chars += size
        if executable_chars > MAX_EXECUTABLE_HTML_TOTAL_CHARS:
            raise ValueError("executable HTML surfaces exceed bounded size")

    def collect_surface(surface: str, *, decode_html_entities: bool = True) -> None:
        normalized = _browser_url_text(
            surface, decode_html_entities=decode_html_entities,
        )
        candidates.extend(
            match.group(0)
            for match in _RUNTIME_TRACKER_RE.finditer(normalized)
        )

    def inspect_script(script: str) -> None:
        charge(len(script))
        for surface in _script_constant_strings(script):
            collect_surface(surface, decode_html_entities=False)

    def inspect_destination(tag: str, attribute: str, destination: str,
                            depth: int) -> None:
        charge(len(destination))
        javascript = _javascript_payload(destination)
        if javascript is not None:
            inspect_script(javascript)
            return
        data_payload = _data_url_payload(destination)
        if data_payload is not None:
            mime, payload = data_payload
            if tag == "script" or mime in _JAVASCRIPT_DATA_MIME_TYPES:
                inspect_script(payload)
            elif tag in _NESTED_DOCUMENT_TAGS or mime in _HTML_DATA_MIME_TYPES:
                inspect_html(payload, depth + 1)
            return
        collect_surface(destination)

    def inspect_html(document: str, depth: int) -> None:
        nonlocal document_count
        document_count += 1
        if (
            depth > MAX_NESTED_EXECUTABLE_DEPTH
            or document_count > MAX_NESTED_EXECUTABLE_DOCUMENTS
        ):
            raise ValueError("nested executable HTML exceeds bounded inspection")
        parser = _ExecutableSurfaceParser()
        parser.feed(document)
        parser.close()
        for tag, attribute, destination in parser.destinations:
            inspect_destination(tag, attribute, destination, depth)
        for script in parser.code:
            inspect_script(script)
        for nested_document in parser.nested_documents:
            charge(len(nested_document))
            inspect_html(nested_document, depth + 1)

    try:
        inspect_html(text, 0)
    except (AssertionError, ValueError):
        return ["unsafe-unparseable-or-oversized-executable-html"]
    return list(dict.fromkeys(candidates))


def _tracker_literals(documents: dict[str, str]) -> list[tuple[str, str, str]]:
    """Return all potential generated tracker destinations, including JS.

    Anchors are only one surface: the quiz creates links at runtime and Netlify
    routes live in ``_redirects``.  Source generators are deliberately excluded
    because they may retain unreachable fail-closed candidates; their generated
    output is the authoritative outward surface.
    """
    rows: list[tuple[str, str, str]] = []
    for name, text in documents.items():
        path = Path(name)
        # Static anchors are validated by ``_placements``.  For HTML, inspect
        # executable script blocks only so explanatory prose that mentions an
        # affiliate URL is not misclassified as a runtime destination.
        for candidate in _runtime_tracker_candidates(path, text):
            rows.append((name, _tracker_base(candidate), candidate))
    return list(dict.fromkeys(rows))


def _valid_official_url(value: object) -> bool:
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return False
    return (parsed.scheme == "https" and bool(parsed.hostname) and
            parsed.username is None and parsed.password is None and
            not parsed.fragment and
            not re.fullmatch(r"(?:[^.]+\.)?atth\.me", parsed.hostname, re.I))


def _valid_tracking_url(value: object) -> bool:
    text = str(value or "")
    return bool(_TRACKER_LITERAL_RE.fullmatch(text))


def evaluate_own_product_offers(
    policy: dict, documents: dict[str, str]
) -> list[str]:
    """Fail closed when a missing own product is not visibly payment-paused.

    The affiliate registry cannot prove that an own-product deliverable exists.
    Bind the owner-controlled product state to the exact public offer page so a
    missing product cannot pass merely because its old purchase anchor lost a
    ``data-buy`` attribute.  This check is intentionally static/local and grants
    no publication or promotion authority.
    """
    failures: list[str] = []
    raw_products = policy.get("products")
    items = raw_products.get("items") if isinstance(raw_products, dict) else None
    if not isinstance(items, list) or not items:
        return ["own-product policy has no product items"]

    products: dict[str, dict] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            failures.append(f"own-product row {index} must be an object")
            continue
        product_id = item.get("id")
        if (not isinstance(product_id, str) or
                re.fullmatch(r"[a-z0-9][a-z0-9._-]*", product_id) is None):
            failures.append(f"own-product row {index} has invalid id")
            continue
        if product_id in products:
            failures.append(f"duplicate own-product id: {product_id}")
            continue
        if not isinstance(item.get("promotion_authorized"), bool):
            failures.append(
                f"own product {product_id} has no boolean promotion_authorized")
        products[product_id] = item

    html_documents = {
        name: text for name, text in documents.items()
        if Path(name).suffix.casefold() == ".html"
    }
    for name, text in html_documents.items():
        for match in re.finditer(
            r"\bdata-buy\s*=\s*([\"'])([^\"']+)\1", text, re.I
        ):
            product_id = html.unescape(match.group(2)).strip()
            item = products.get(product_id)
            if item is None:
                failures.append(f"{name}: undeclared own-product data-buy {product_id}")
            elif item.get("promotion_authorized") is not True:
                failures.append(f"{name}: unauthorized own-product data-buy {product_id}")

    for product_id, item in products.items():
        if item.get("status") != "PROMISED-BUT-MISSING":
            continue
        if item.get("deliverable") not in (None, ""):
            failures.append(
                f"own product {product_id} is PROMISED-BUT-MISSING but has a deliverable")
        if item.get("promotion_authorized") is not False:
            failures.append(
                f"own product {product_id} is PROMISED-BUT-MISSING but promotion is not disabled")
        sold_on = item.get("sold_on")
        normalized = str(sold_on or "").replace("\\", "/")
        if re.fullmatch(r"site/[a-z0-9][a-z0-9._-]*\.html", normalized) is None:
            failures.append(f"own product {product_id} has invalid sold_on page")
            continue
        page_name = normalized.rsplit("/", 1)[-1]
        matches = [
            (name, text) for name, text in html_documents.items()
            if Path(name).name.casefold() == page_name.casefold()
        ]
        if not matches:
            failures.append(
                f"own product {product_id} offer page is absent from the audited scope")
            continue
        for name, text in matches:
            folded = text.casefold()
            if _PAUSED_OFFER_MARKER not in folded:
                failures.append(
                    f"{name}: missing product {product_id} has no explicit paused marker")
            risks = sorted({
                label for token, label in _PAUSED_PURCHASE_TOKENS.items()
                if token.casefold() in folded
            })
            if risks:
                failures.append(
                    f"{name}: missing product {product_id} still exposes purchase mechanics "
                    f"({', '.join(risks)})")
    return failures


def evaluate(registry: dict, documents: dict[str, str], today: date) -> list[str]:
    failures: list[str] = []
    redirect_routes, redirect_failures = _redirect_routes(documents)
    failures.extend(redirect_failures)
    if registry.get("schema_version") != 2:
        failures.append("unsupported or missing schema_version")

    review_valid_days = registry.get("review_valid_days")
    if not isinstance(review_valid_days, int) or not 1 <= review_valid_days <= 90:
        failures.append("review_valid_days must be an integer from 1 to 90")
        review_valid_days = 0

    as_of: date | None = None
    try:
        as_of = date.fromisoformat(str(registry["as_of"]))
    except (KeyError, TypeError, ValueError):
        failures.append("registry has invalid as_of")
    else:
        if as_of > today:
            failures.append("registry as_of is in the future")

    products = registry.get("products")
    if not isinstance(products, dict) or not products:
        failures.append("products must be a non-empty object")
        products = {}
    tracker_owners: dict[str, str] = {}
    campaign_owners: dict[int, str] = {}
    for provider, product in products.items():
        if not re.fullmatch(r"[a-z0-9_]+", str(provider)):
            failures.append(f"product key {provider} is invalid")
        if not isinstance(product, dict):
            failures.append(f"product {provider} must be an object")
            continue
        availability = product.get("availability")
        if availability not in {"active", "paused", "retired"}:
            failures.append(f"product {provider} has invalid availability")
        official_url = str(product.get("official_url", ""))
        if not _valid_official_url(official_url):
            failures.append(f"product {provider} has no HTTPS official_url")
        if not re.fullmatch(r"[a-z0-9_]+", str(product.get("product_type", ""))):
            failures.append(f"product {provider} has invalid product_type")
        allowed = product.get("allowed_content_ids")
        if (not isinstance(allowed, list) or not allowed or
                any(not isinstance(item, str) or not re.fullmatch(r"[a-z0-9._-]+", item)
                    for item in allowed) or len(set(allowed)) != len(allowed)):
            failures.append(f"product {provider} has invalid allowed_content_ids")
        try:
            reviewed_on = date.fromisoformat(str(product["reviewed_on"]))
        except (KeyError, TypeError, ValueError):
            failures.append(f"product {provider} has invalid reviewed_on")
        else:
            age = (today - reviewed_on).days
            if age < 0:
                failures.append(f"product {provider} reviewed_on is in the future")
            elif review_valid_days and age > review_valid_days:
                failures.append(
                    f"product {provider} review is stale ({age}d > {review_valid_days}d)")

        present_network_fields = {field for field in _NETWORK_FIELDS if field in product}
        if present_network_fields != set(_NETWORK_FIELDS):
            missing = sorted(set(_NETWORK_FIELDS) - present_network_fields)
            failures.append(
                f"product {provider} has incomplete affiliate network evidence"
                + (" (missing %s)" % ", ".join(missing) if missing else ""))
            continue
        if product.get("affiliate_network") != "AccessTrade":
            failures.append(f"product {provider} has invalid affiliate_network")
        campaign_id = product.get("network_campaign_id")
        if (isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or
                campaign_id <= 0):
            failures.append(f"product {provider} has invalid network_campaign_id")
        else:
            previous = campaign_owners.get(campaign_id)
            if previous is not None and previous != provider:
                failures.append(
                    f"network campaign {campaign_id} is duplicated by {previous} and {provider}")
            else:
                campaign_owners[campaign_id] = str(provider)
        network_status = product.get("network_status")
        if network_status not in set(_EXPECTED_NETWORK_STATUS.values()):
            failures.append(f"product {provider} has invalid network_status")
        elif _EXPECTED_NETWORK_STATUS.get(availability) != network_status:
            failures.append(
                f"product {provider} availability {availability} conflicts with "
                f"network_status {network_status}")
        try:
            network_verified_on = date.fromisoformat(
                str(product["network_verified_on"]))
        except (KeyError, TypeError, ValueError):
            failures.append(f"product {provider} has invalid network_verified_on")
        else:
            network_age = (today - network_verified_on).days
            if network_age < 0:
                failures.append(
                    f"product {provider} network_verified_on is in the future")
            elif review_valid_days and network_age > review_valid_days:
                failures.append(
                    f"product {provider} network verification is stale "
                    f"({network_age}d > {review_valid_days}d)")
            if as_of is not None and network_verified_on > as_of:
                failures.append(
                    f"product {provider} network verification is newer than registry as_of")
        tracking_urls = product.get("tracking_urls")
        if (not isinstance(tracking_urls, list) or not tracking_urls or
                any(not isinstance(url, str) or not _valid_tracking_url(url)
                    for url in tracking_urls) or
                len(set(tracking_urls)) != len(tracking_urls)):
            failures.append(f"product {provider} has invalid tracking_urls")
        else:
            for tracker in tracking_urls:
                previous = tracker_owners.get(tracker)
                if previous is not None and previous != provider:
                    failures.append(
                        f"tracker {tracker} is registered to both {previous} and {provider}")
                else:
                    tracker_owners[tracker] = str(provider)

    placements, placement_parse_failures = _placements(documents)
    failures.extend(placement_parse_failures)
    for name, provider, content_id, tracker, href in placements:
        if not provider:
            failures.append(f"{name}: affiliate placement has no data-provider")
            continue
        product = products.get(provider)
        if not isinstance(product, dict):
            failures.append(f"{name}: affiliate provider {provider} is not registered")
            continue
        if product.get("availability") != "active":
            failures.append(
                f"{name}: affiliate provider {provider} is {product.get('availability')}")
        internal_route = _internal_go_path(href)
        if not tracker and not internal_route:
            failures.append(
                f"{name}: affiliate destination is not an exact registered "
                "tracker or /go route")
        if tracker:
            tracker_owner = tracker_owners.get(tracker)
            if tracker_owner is None:
                failures.append(f"{name}: tracker {tracker} is not registered")
            elif tracker_owner != provider:
                failures.append(
                    f"{name}: tracker {tracker} belongs to {tracker_owner}, not {provider}")
        if internal_route:
            redirect_target = redirect_routes.get(internal_route)
            if redirect_target is None:
                failures.append(
                    f"{name}: internal affiliate redirect {internal_route} is missing")
            elif not _valid_tracking_url(redirect_target):
                failures.append(
                    f"{name}: internal affiliate redirect {internal_route} "
                    "does not resolve to one exact registered tracker URL")
            else:
                redirect_owner = tracker_owners.get(redirect_target)
                if redirect_owner is None:
                    failures.append(
                        f"{name}: internal affiliate redirect {internal_route} "
                        f"targets unregistered tracker {redirect_target}")
                elif redirect_owner != provider:
                    failures.append(
                        f"{name}: internal affiliate redirect {internal_route} "
                        f"targets {redirect_owner}, not {provider}")
        if not content_id:
            failures.append(f"{name}: affiliate provider {provider} has no data-content-id")
            continue
        allowed = product.get("allowed_content_ids")
        if isinstance(allowed, list) and content_id not in allowed:
            failures.append(
                f"{name}: provider {provider} is not reviewed for content {content_id}")

    for route, target in redirect_routes.items():
        try:
            parsed_target = urlsplit(html.unescape(str(target or "")))
        except ValueError:
            parsed_target = None
        if parsed_target is None or not parsed_target.scheme:
            continue
        tracker = _tracker_base(target)
        if not tracker:
            failures.append(
                f"redirect {route} has an unsupported or malformed external target")
            continue
        tracker_owner = tracker_owners.get(tracker)
        if tracker_owner is None:
            failures.append(f"redirect {route} targets unregistered tracker {tracker}")
            continue
        product = products.get(tracker_owner)
        if not isinstance(product, dict) or product.get("availability") != "active":
            failures.append(
                f"redirect {route} targets inactive provider {tracker_owner}")

    for name, tracker, candidate in _tracker_literals(documents):
        # Runtime-created affiliate destinations do not expose the exact
        # provider + content identity carried by a reviewed static anchor.  A
        # registered tracker alone is therefore insufficient evidence: a JS
        # object can pair one provider's label with another provider's URL.
        # Keep this surface closed until a dedicated hash-bound runtime
        # placement manifest is implemented and consumed by the renderer.
        failures.append(
            f"{name}: runtime tracker literal is not bound to a reviewed "
            f"static provider/content placement ({candidate})"
        )

    promotions = registry.get("promotions")
    if not isinstance(promotions, list):
        failures.append("promotions must be a list")
        promotions = []
    seen: set[str] = set()
    for promo in promotions:
        if not isinstance(promo, dict):
            failures.append("promotion row must be an object")
            continue
        promo_id = str(promo.get("id", "")).strip()
        if not promo_id or promo_id in seen:
            failures.append("promotion id missing or duplicated")
            continue
        seen.add(promo_id)
        provider = str(promo.get("provider", "")).strip()
        if provider not in products:
            failures.append(f"{promo_id}: provider has no product record")
        if promo.get("state") not in {"active", "expired", "paused"}:
            failures.append(f"{promo_id}: invalid state")
        if not _valid_official_url(promo.get("official_url")):
            failures.append(f"{promo_id}: invalid official_url")
        try:
            valid_until = date.fromisoformat(str(promo["valid_until"]))
        except (KeyError, TypeError, ValueError):
            failures.append(f"{promo_id}: invalid valid_until")
            continue
        valid_from = date.min
        if "valid_from" in promo:
            try:
                valid_from = date.fromisoformat(str(promo["valid_from"]))
            except (TypeError, ValueError):
                failures.append(f"{promo_id}: invalid valid_from")
                continue
            if valid_from > valid_until:
                failures.append(f"{promo_id}: valid_from is after valid_until")
                continue
        try:
            verified_on = date.fromisoformat(str(promo["verified_on"]))
        except (KeyError, TypeError, ValueError):
            failures.append(f"{promo_id}: invalid verified_on")
            verified_on = None
        if verified_on is not None:
            verification_age = (today - verified_on).days
            if verification_age < 0:
                failures.append(f"{promo_id}: verified_on is in the future")
            elif (promo.get("state") == "active" and review_valid_days
                  and verification_age > review_valid_days):
                failures.append(
                    f"{promo_id}: promotion verification is stale "
                    f"({verification_age}d > {review_valid_days}d)")
            if as_of is not None and verified_on > as_of:
                failures.append(
                    f"{promo_id}: promotion verification is newer than registry as_of")
        tokens = promo.get("claim_tokens")
        if (not isinstance(tokens, list) or not tokens or
                any(not isinstance(token, str) or not token.strip() for token in tokens)):
            failures.append(f"{promo_id}: claim_tokens missing or malformed")
            continue
        requirements = promo.get("claim_requirements", {})
        if not isinstance(requirements, dict):
            failures.append(f"{promo_id}: claim_requirements must be an object")
            requirements = {}
        else:
            valid_requirements: dict[str, list[str]] = {}
            for claim_token, context_tokens in requirements.items():
                if claim_token not in tokens:
                    failures.append(
                        f"{promo_id}: claim requirement key {claim_token!r} is not a claim token")
                    continue
                if (not isinstance(context_tokens, list) or not context_tokens or
                        any(not isinstance(context, str) or not context.strip()
                            for context in context_tokens) or
                        len(set(context_tokens)) != len(context_tokens)):
                    failures.append(
                        f"{promo_id}: claim requirement {claim_token!r} is malformed")
                    continue
                valid_requirements[claim_token] = context_tokens
            requirements = valid_requirements
        hits = [(name, token) for name, text in documents.items()
                for token in tokens if token in text]
        for name, token in hits:
            for block_number, block in enumerate(_claim_blocks(documents[name]), 1):
                occurrence_count = block.count(token)
                if occurrence_count == 0:
                    continue
                required_contexts = requirements.get(token, [])
                if required_contexts and occurrence_count > 1:
                    failures.append(
                        f"{promo_id}: {name} claim {token!r} block "
                        f"{block_number} repeats {occurrence_count} times; "
                        "each qualified promotional claim must use a separate structural block")
                    continue
                for required_context in required_contexts:
                    context_count = block.count(required_context)
                    if context_count < occurrence_count:
                        failures.append(
                            f"{promo_id}: {name} claim {token!r} block "
                            f"{block_number} has {occurrence_count} occurrence(s) but "
                            f"local context {required_context!r} appears "
                            f"{context_count} time(s)")
        in_window = valid_from <= today <= valid_until
        available = promo.get("state") == "active" and in_window
        if promo.get("state") == "active" and today > valid_until:
            failures.append(
                f"{promo_id}: registry still says active after {valid_until.isoformat()}")
        if hits and not available:
            examples = ", ".join(f"{name}:{token}" for name, token in hits[:3])
            failures.append(
                f"{promo_id}: inactive outside {valid_from.isoformat()}.."
                f"{valid_until.isoformat()} but claim remains ({examples})")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--own-product-policy", type=Path, default=DEFAULT_OWN_PRODUCT_POLICY,
    )
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--generated-site",
        type=Path,
        help="also inspect this generated HTML directory (missing/empty fails closed)",
    )
    args = parser.parse_args()
    paths = select_sources(args.paths, generated_site=args.generated_site)
    scope = (
        "explicit+generated" if args.paths and args.generated_site is not None
        else "explicit" if args.paths
        else "source-inputs+generated" if args.generated_site is not None
        else "source-inputs"
    )
    try:
        registry = load_registry(args.registry)
        own_product_policy = load_registry(args.own_product_policy)
        documents = load_documents(paths, args.today)
        failures = evaluate(registry, documents, args.today)
        failures.extend(evaluate_own_product_offers(own_product_policy, documents))
    except Exception as exc:
        print("FAIL merchant offer gate unavailable: %s" % exc)
        return 2
    for failure in failures:
        print("FAIL " + failure)
    if failures:
        print("merchant offer gate: %d failure(s)" % len(failures))
        return 1
    print("merchant offer gate: PASS scope=%s (%d product(s), %d promotion(s), "
          "%d placement(s), %d document(s))" %
          (scope, len(registry["products"]), len(registry["promotions"]),
           len(_placements(documents)[0]), len(documents)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
