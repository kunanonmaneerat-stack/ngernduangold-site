#!/usr/bin/env python3
"""Fail closed when public content is not authored solely as the page.

Output intentionally contains only paths/task slugs and finding categories.  It
never echoes matched copy, account names, or other values from public/private
files.  The canonical identity and the prohibited personal-voice patterns live
in .system_control/policy.json, not in this script.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
from typing import Iterable
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / ".system_control" / "policy.json"
SITE = ROOT / "site"
MANIFEST = ROOT / ".system_control" / "content_manifest.json"
KNOWLEDGE_GLOB = "KNOWLEDGE-POSTS*.md"
PROMPT_ROOTS = (
    ("primary", Path(r"C:\Users\nL_ku\Claude\Scheduled")),
    ("mirror", Path(r"C:\Users\nL_ku\.claude\scheduled-tasks")),
)

_JSONLD = re.compile(
    r'<script\s+[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>", re.S)
_VERIFY_FILE = re.compile(r"^google[0-9a-z_-]*\.html$", re.I)
_KNOWLEDGE_ROW = re.compile(r"^\|\s*20\d\d-\d\d-\d\d\s*\|")
_CSS_GENERATED_ATTRIBUTE_ALLOWLIST = frozenset({"data-l"})
_OUTWARD_HINTS = (
    "draft pack",
    "draft suggestion",
    "soft-cta",
    "threads_text",
    "fb_text",
    "\u0e23\u0e48\u0e32\u0e07\u0e42\u0e1e\u0e2a\u0e15\u0e4c",  # draft post
    "\u0e23\u0e48\u0e32\u0e07\u0e04\u0e33\u0e15\u0e2d\u0e1a",  # draft answer
    "\u0e23\u0e48\u0e32\u0e07\u0e2a\u0e32\u0e18\u0e32\u0e23\u0e13\u0e30",  # public draft
)


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    category: str


@dataclass(frozen=True)
class _JSToken:
    kind: str
    value: str


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _strict_json_loads(text: str):
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON constant: " + value)

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        parse_float=finite_float,
        object_pairs_hook=unique_object,
    )


def _load_json(path: Path):
    text = _read(path)
    if text is None:
        return None
    try:
        return _strict_json_loads(text)
    except (TypeError, ValueError):
        return None


def _visible_text(document: str) -> str:
    without_code = _SCRIPT_STYLE.sub(" ", document)
    return html.unescape(_TAGS.sub(" ", without_code))


class _PublicMetadataParser(HTMLParser):
    """Collect text-bearing HTML metadata without treating it as body copy."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []
        self.meta_tags: list[list[tuple[str, str | None]]] = []
        self.element_attributes: list[list[tuple[str, str | None]]] = []
        self.style_attributes: list[str] = []
        self.style_blocks: list[str] = []
        self.link_tags: list[list[tuple[str, str | None]]] = []
        self.script_blocks: list[tuple[list[tuple[str, str | None]], str]] = []
        self._title_depth = 0
        self._style_stack: list[list[str]] = []
        self._script_stack: list[tuple[list[tuple[str, str | None]], list[str]]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        lowered = tag.casefold()
        self.element_attributes.append(list(attrs))
        if lowered == "meta":
            self.meta_tags.append(list(attrs))
            for name, value in attrs:
                if (
                    isinstance(name, str)
                    and name.casefold() == "content"
                    and isinstance(value, str)
                ):
                    self.values.append(value)
        elif lowered == "link":
            self.link_tags.append(list(attrs))
        for name, value in attrs:
            if (
                isinstance(name, str)
                and name.casefold() == "style"
                and isinstance(value, str)
            ):
                self.style_attributes.append(value)
        if lowered == "title":
            self._title_depth += 1
        elif lowered == "style":
            self._style_stack.append([])
        elif lowered == "script":
            self._script_stack.append((list(attrs), []))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "title" and self._title_depth:
            self._title_depth -= 1
        elif lowered == "style" and self._style_stack:
            self.style_blocks.append("".join(self._style_stack.pop()))
        elif lowered == "script" and self._script_stack:
            attrs, parts = self._script_stack.pop()
            self.script_blocks.append((attrs, "".join(parts)))

    def handle_data(self, data: str) -> None:
        if self._title_depth and data:
            self.values.append(data)
        if self._style_stack and data:
            self._style_stack[-1].append(data)
        if self._script_stack and data:
            self._script_stack[-1][1].append(data)


def _parse_public_metadata(document: str) -> _PublicMetadataParser:
    parser = _PublicMetadataParser()
    try:
        parser.feed(document)
        parser.close()
    except (ValueError, TypeError):
        # Identity structure has separate fail-closed checks. Return every value
        # parsed before malformed trailing markup rather than dropping evidence.
        pass
    while parser._style_stack:
        parser.style_blocks.append("".join(parser._style_stack.pop()))
    while parser._script_stack:
        attrs, parts = parser._script_stack.pop()
        parser.script_blocks.append((attrs, "".join(parts)))
    return parser


def _attribute_values(attrs, key: str) -> list[str | None]:
    return [
        value
        for name, value in attrs
        if isinstance(name, str) and name.casefold() == key
    ]


def _matching_meta_tags(
    metadata: _PublicMetadataParser,
    selector: str,
    expected: str,
) -> list[list[tuple[str, str | None]]]:
    matches = []
    for attrs in metadata.meta_tags:
        values = _attribute_values(attrs, selector)
        if any(
            isinstance(value, str) and value.strip().casefold() == expected
            for value in values
        ):
            matches.append(attrs)
    return matches


def _meta_identity_findings(
    metadata: _PublicMetadataParser,
    path: str,
    brand: str,
    selector: str,
    expected: str,
    category: str,
    required: bool,
) -> list[Finding]:
    tags = _matching_meta_tags(metadata, selector, expected)
    if not tags:
        return [Finding(path, 1, "PAGE_%s_MISSING" % category)] if required else []

    contents = [_attribute_values(attrs, "content") for attrs in tags]
    selector_counts = [len(_attribute_values(attrs, selector)) for attrs in tags]
    findings = []
    if (
        len(tags) != 1
        or any(count != 1 for count in selector_counts)
        or any(len(values) != 1 for values in contents)
    ):
        findings.append(Finding(path, 1, "PAGE_%s_AMBIGUOUS" % category))

    values = [value for group in contents for value in group]
    if not values or any(
        not isinstance(value, str) or not value.strip() or value.strip() != brand
        for value in values
    ):
        findings.append(Finding(path, 1, "PAGE_%s_WRONG" % category))
    return findings


def _has_meta_refresh(metadata: _PublicMetadataParser) -> bool:
    for attrs in metadata.meta_tags:
        if any(
            isinstance(value, str) and value.strip().casefold() == "refresh"
            for value in _attribute_values(attrs, "http-equiv")
        ):
            return True
    return False


def _strip_css_comments(value: str) -> tuple[str, bool]:
    """Remove CSS comments while preserving quoted strings."""

    result: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(value):
        char = value[index]
        if quote is not None:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            result.append(char)
            index += 1
            continue
        if value.startswith("/*", index):
            end = value.find("*/", index + 2)
            if end < 0:
                return "".join(result), False
            result.append(" ")
            index = end + 2
            continue
        result.append(char)
        index += 1
    return "".join(result), True


def _decode_css_string(value: str, start: int) -> tuple[str, int, bool]:
    quote = value[start]
    decoded: list[str] = []
    index = start + 1
    while index < len(value):
        char = value[index]
        if char == quote:
            return "".join(decoded), index + 1, True
        if char in "\r\n\f":
            return "", index, False
        if char != "\\":
            decoded.append(char)
            index += 1
            continue

        index += 1
        if index >= len(value):
            return "", index, False
        if value[index] == "\r":
            index += 1
            if index < len(value) and value[index] == "\n":
                index += 1
            continue
        if value[index] in "\n\f":
            index += 1
            continue
        if value[index] in "0123456789abcdefABCDEF":
            end = index
            while (
                end < len(value)
                and end - index < 6
                and value[end] in "0123456789abcdefABCDEF"
            ):
                end += 1
            codepoint = int(value[index:end], 16)
            if codepoint == 0 or codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                return "", end, False
            decoded.append(chr(codepoint))
            index = end
            if index < len(value) and value[index].isspace():
                if value[index] == "\r" and index + 1 < len(value) and value[index + 1] == "\n":
                    index += 2
                else:
                    index += 1
            continue
        decoded.append(value[index])
        index += 1
    return "", index, False


def _css_has_unresolved_import(value: str) -> bool:
    """Recognize CSS-escaped @import outside comments and quoted strings."""
    source, valid = _strip_css_comments(value)
    if not valid:
        return True
    index = 0
    while index < len(source):
        if source[index] in {'"', "'"}:
            _decoded, index, quoted = _decode_css_string(source, index)
            if not quoted:
                return True
            continue
        if source[index] != "@":
            index += 1
            continue
        index += 1
        decoded: list[str] = []
        while index < len(source):
            char = source[index]
            if char.isalnum() or char in "_-" or ord(char) > 127:
                decoded.append(char)
                index += 1
                continue
            if char != "\\":
                break
            index += 1
            if index >= len(source) or source[index] in "\r\n\f":
                return True
            if source[index] in "0123456789abcdefABCDEF":
                end = index
                while (
                    end < len(source)
                    and end - index < 6
                    and source[end] in "0123456789abcdefABCDEF"
                ):
                    end += 1
                codepoint = int(source[index:end], 16)
                if (
                    codepoint == 0
                    or codepoint > 0x10FFFF
                    or 0xD800 <= codepoint <= 0xDFFF
                ):
                    return True
                decoded.append(chr(codepoint))
                index = end
                if index < len(source) and source[index].isspace():
                    if (
                        source[index] == "\r"
                        and index + 1 < len(source)
                        and source[index + 1] == "\n"
                    ):
                        index += 2
                    else:
                        index += 1
                continue
            decoded.append(source[index])
            index += 1
        if "".join(decoded).casefold() == "import":
            return True
    return False


def _decode_css_generated_value(
    value: str,
) -> tuple[list[str], list[str], bool]:
    value = value.strip()
    important = re.search(r"!\s*important\s*$", value, re.I)
    if important:
        value = value[: important.start()].rstrip()
    if value.casefold() in {"none", "normal"}:
        return [], [], True
    if not value:
        return [], [], False

    attribute = re.fullmatch(
        r"attr\(\s*([A-Za-z][A-Za-z0-9_-]*)\s*\)", value, re.I
    )
    if attribute:
        name = attribute.group(1).casefold()
        if name in _CSS_GENERATED_ATTRIBUTE_ALLOWLIST:
            return [], [name], True
        return [], [], False

    decoded: list[str] = []
    index = 0
    while index < len(value):
        while index < len(value) and value[index].isspace():
            index += 1
        if index == len(value):
            break
        if value[index] not in {'"', "'"}:
            return [], [], False
        text, index, valid = _decode_css_string(value, index)
        if not valid:
            return [], [], False
        decoded.append(text)
    return decoded, [], True


def _css_declaration_segments(source: str, inline: bool) -> list[str]:
    """Return declaration-sized segments, never selector or comment text."""

    segments: list[str] = []
    buffer: list[str] = []
    depth = 1 if inline else 0
    quote: str | None = None
    escaped = False
    comment = False
    index = 0
    while index < len(source):
        char = source[index]
        if comment:
            if source.startswith("*/", index):
                if depth:
                    buffer.append("*/")
                comment = False
                index += 2
            else:
                if depth:
                    buffer.append(char)
                index += 1
            continue
        if quote is not None:
            if depth:
                buffer.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if source.startswith("/*", index):
            if depth:
                buffer.append("/*")
            comment = True
            index += 2
            continue
        if char in {'"', "'"}:
            quote = char
            if depth:
                buffer.append(char)
            index += 1
            continue
        if not inline and char == "{":
            depth += 1
            buffer.clear()
            index += 1
            continue
        if not inline and char == "}":
            if depth and buffer:
                segments.append("".join(buffer))
            buffer.clear()
            depth = max(0, depth - 1)
            index += 1
            continue
        if char == ";" and depth:
            segments.append("".join(buffer))
            buffer.clear()
            index += 1
            continue
        if depth:
            buffer.append(char)
        index += 1
    if depth and buffer:
        segments.append("".join(buffer))
    return segments


def _css_generated_text(
    source: str,
    inline: bool,
) -> tuple[list[str], list[str], bool]:
    values: list[str] = []
    attributes: list[str] = []
    valid = True
    for raw_segment in _css_declaration_segments(source, inline):
        segment, comments_valid = _strip_css_comments(raw_segment)
        match = re.match(r"^\s*content\s*:\s*(.*)$", segment, re.I | re.S)
        if match is None:
            continue
        if not comments_valid:
            valid = False
            continue
        decoded, referenced, declaration_valid = _decode_css_generated_value(
            match.group(1)
        )
        if not declaration_valid:
            valid = False
            continue
        values.extend(decoded)
        attributes.extend(referenced)
    return values, attributes, valid


def _generated_attribute_values(
    metadata: _PublicMetadataParser,
    name: str,
) -> Iterable[str]:
    for attrs in metadata.element_attributes:
        for value in _attribute_values(attrs, name):
            if isinstance(value, str):
                yield value


_JS_ASSIGNMENT_OPERATORS = {
    "=", "+=", "-=", "*=", "/=", "%=", "**=", "&&=", "||=", "??=",
    "++", "--",
}
_JS_ATTRIBUTE_MUTATORS = {
    "setAttribute": 0,
    "toggleAttribute": 0,
    "setAttributeNS": 1,
}
_JS_EXECUTABLE_SCRIPT_TYPES = {
    "application/ecmascript",
    "application/javascript",
    "application/x-ecmascript",
    "application/x-javascript",
    "module",
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
}


def _decode_js_escape(source: str, index: int) -> tuple[str, int, bool]:
    if index >= len(source):
        return "", index, False
    char = source[index]
    escapes = {
        "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
        "0": "\0",
    }
    if char in escapes:
        return escapes[char], index + 1, True
    if char in "\r\n":
        if char == "\r" and index + 1 < len(source) and source[index + 1] == "\n":
            return "", index + 2, True
        return "", index + 1, True
    if char == "x":
        raw = source[index + 1:index + 3]
        if len(raw) != 2 or any(value not in "0123456789abcdefABCDEF" for value in raw):
            return "", index, False
        return chr(int(raw, 16)), index + 3, True
    if char == "u":
        if index + 1 < len(source) and source[index + 1] == "{":
            end = source.find("}", index + 2)
            raw = source[index + 2:end] if end >= 0 else ""
            next_index = end + 1
        else:
            raw = source[index + 1:index + 5]
            next_index = index + 5
        if (
            not raw
            or len(raw) > 6
            or any(value not in "0123456789abcdefABCDEF" for value in raw)
        ):
            return "", index, False
        codepoint = int(raw, 16)
        if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            return "", index, False
        return chr(codepoint), next_index, True
    if char in "1234567":
        # Legacy octal escapes are context-sensitive. Treat the value as dynamic.
        return "", index, False
    return char, index + 1, True


def _read_js_quoted(
    source: str,
    start: int,
    quote: str,
) -> tuple[str, int, bool, bool, list[str]]:
    decoded: list[str] = []
    expressions: list[str] = []
    dynamic = False
    index = start + 1
    while index < len(source):
        char = source[index]
        if char == quote:
            return "".join(decoded), index + 1, True, dynamic, expressions
        if quote == "`" and source.startswith("${", index):
            dynamic = True
            index += 2
            expression_start = index
            depth = 1
            nested_quote: str | None = None
            escaped = False
            while index < len(source) and depth:
                current = source[index]
                if nested_quote is not None:
                    if escaped:
                        escaped = False
                    elif current == "\\":
                        escaped = True
                    elif current == nested_quote:
                        nested_quote = None
                elif current in {'"', "'", "`"}:
                    nested_quote = current
                elif current == "{":
                    depth += 1
                elif current == "}":
                    depth -= 1
                index += 1
            if depth:
                return "", index, False, True, expressions
            expressions.append(source[expression_start:index - 1])
            continue
        if char == "\\":
            value, index, valid = _decode_js_escape(source, index + 1)
            if not valid:
                return "", index, False, dynamic, expressions
            decoded.append(value)
            continue
        if quote != "`" and char in "\r\n":
            return "", index, False, dynamic, expressions
        decoded.append(char)
        index += 1
    return "", index, False, dynamic, expressions


def _slash_starts_regex(tokens: list[_JSToken]) -> bool:
    if not tokens:
        return True
    previous = tokens[-1]
    if previous.kind == "punct":
        return previous.value not in {")", "]", "}", "++", "--"}
    return previous.kind == "ident" and previous.value in {
        "return", "throw", "case", "delete", "void", "typeof", "new", "in",
        "of", "yield", "await", "else", "do",
    }


def _js_tokens(source: str) -> list[_JSToken]:
    tokens: list[_JSToken] = []
    index = 0
    punctuators = (
        ">>>=", "===", "!==", "**=", "&&=", "||=", "??=", "=>", "==", "!=",
        "<=", ">=", "++", "--", "+=", "-=", "*=", "/=", "%=", "&&", "||",
        "??", "?.", "**", "<<", ">>",
    )
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = len(source) if end < 0 else end + 2
            continue
        if char in {'"', "'", "`"}:
            value, index, valid, dynamic, expressions = _read_js_quoted(
                source, index, char
            )
            tokens.append(
                _JSToken("dynamic" if dynamic or not valid else "string", value)
            )
            for expression in expressions:
                tokens.extend(_js_tokens(expression))
            continue
        if char == "/" and _slash_starts_regex(tokens):
            index += 1
            escaped = False
            character_class = False
            while index < len(source):
                current = source[index]
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == "[":
                    character_class = True
                elif current == "]":
                    character_class = False
                elif current == "/" and not character_class:
                    index += 1
                    while index < len(source) and source[index].isalpha():
                        index += 1
                    break
                index += 1
            tokens.append(_JSToken("regex", ""))
            continue
        if char.isalpha() or char in "_$" or ord(char) > 127 or (
            char == "\\" and source.startswith("\\u", index)
        ):
            decoded: list[str] = []
            valid = True
            while index < len(source):
                current = source[index]
                if current.isalnum() or current in "_$" or ord(current) > 127:
                    decoded.append(current)
                    index += 1
                elif current == "\\" and source.startswith("\\u", index):
                    value, next_index, escape_valid = _decode_js_escape(source, index + 1)
                    if not escape_valid:
                        valid = False
                        index += 2
                        break
                    decoded.append(value)
                    index = next_index
                else:
                    break
            tokens.append(_JSToken("ident" if valid else "dynamic", "".join(decoded)))
            continue
        matched = next((value for value in punctuators if source.startswith(value, index)), None)
        if matched:
            tokens.append(_JSToken("punct", matched))
            index += len(matched)
        else:
            tokens.append(_JSToken("punct", char))
            index += 1
    return tokens


def _matching_js_token(
    tokens: list[_JSToken],
    start: int,
    opener: str,
    closer: str,
) -> int | None:
    depth = 0
    for index in range(start, len(tokens)):
        if tokens[index].kind != "punct":
            continue
        if tokens[index].value == opener:
            depth += 1
        elif tokens[index].value == closer:
            depth -= 1
            if depth == 0:
                return index
    return None


def _js_for_each_domains(
    tokens: list[_JSToken],
) -> list[tuple[str, int, int, frozenset[str]]]:
    domains = []
    for start, token in enumerate(tokens):
        if token.kind != "punct" or token.value != "[":
            continue
        end = _matching_js_token(tokens, start, "[", "]")
        if end is None:
            continue
        items = tokens[start + 1:end]
        if not items or any(
            item.kind != "string" if index % 2 == 0 else item.value != ","
            for index, item in enumerate(items)
        ):
            continue
        values = frozenset(item.value for item in items[::2])
        tail = tokens[end + 1:end + 9]
        if not (
            len(tail) == 8
            and tail[0].value == "."
            and tail[1] == _JSToken("ident", "forEach")
            and tail[2].value == "("
            and tail[3] == _JSToken("ident", "function")
            and tail[4].value == "("
            and tail[5].kind == "ident"
            and tail[6].value == ")"
            and tail[7].value == "{"
        ):
            continue
        body_start = end + 8
        body_end = _matching_js_token(tokens, body_start, "{", "}")
        if body_end is not None:
            domains.append((tail[5].value, body_start, body_end, values))
    return domains


def _js_argument_domain(
    argument: list[_JSToken],
    position: int,
    scopes: list[tuple[str, int, int, frozenset[str]]],
) -> frozenset[str] | None:
    if len(argument) == 1 and argument[0].kind == "string":
        return frozenset({argument[0].value})
    if (
        argument
        and len(argument) % 2 == 1
        and all(argument[index].kind == "string" for index in range(0, len(argument), 2))
        and all(argument[index].value == "+" for index in range(1, len(argument), 2))
    ):
        return frozenset({"".join(argument[index].value for index in range(0, len(argument), 2))})
    if len(argument) == 1 and argument[0].kind == "ident":
        for name, start, end, values in reversed(scopes):
            if name == argument[0].value and start < position < end:
                return values
    return None


def _js_call_arguments(
    tokens: list[_JSToken],
    opener: int,
) -> tuple[list[list[_JSToken]], int | None]:
    end = _matching_js_token(tokens, opener, "(", ")")
    if end is None:
        return [], None
    arguments: list[list[_JSToken]] = []
    current: list[_JSToken] = []
    nesting = 0
    for token in tokens[opener + 1:end]:
        if token.kind == "punct" and token.value in {"(", "[", "{"}:
            nesting += 1
        elif token.kind == "punct" and token.value in {")", "]", "}"}:
            nesting -= 1
        if token.kind == "punct" and token.value == "," and nesting == 0:
            arguments.append(current)
            current = []
        else:
            current.append(token)
    if current or arguments:
        arguments.append(current)
    return arguments, end


def _js_method_call_mutates(
    method: str,
    arguments: list[list[_JSToken]],
    position: int,
    scopes: list[tuple[str, int, int, frozenset[str]]],
    attribute: str,
) -> bool:
    if method == "setAttributeNode":
        return bool(arguments)
    argument_index = _JS_ATTRIBUTE_MUTATORS.get(method)
    if argument_index is None or argument_index >= len(arguments):
        return False
    domain = _js_argument_domain(arguments[argument_index], position, scopes)
    if domain is None:
        return True
    return attribute.casefold() in {value.casefold() for value in domain}


def _js_may_mutate_generated_attribute(source: str, attribute: str) -> bool:
    tokens = _js_tokens(source)
    scopes = _js_for_each_domains(tokens)

    # Module graphs and string-to-code execution cross the boundary of this
    # local static analysis. A generated public attribute must therefore fail
    # closed instead of assuming an imported/evaluated body is benign.
    for index, token in enumerate(tokens):
        if token == _JSToken("ident", "import"):
            return True
        if token.kind == "ident" and token.value in {"eval", "Function"}:
            return True
        if (
            token.kind == "string"
            and token.value in {"eval", "Function"}
            and index
            and tokens[index - 1].value == "["
            and index + 2 < len(tokens)
            and tokens[index + 1].value == "]"
            and tokens[index + 2].value in {"(", "?."}
        ):
            return True
        if (
            token.kind == "ident"
            and token.value in {"setTimeout", "setInterval"}
            and index + 1 < len(tokens)
            and tokens[index + 1].value == "("
        ):
            arguments, _end = _js_call_arguments(tokens, index + 1)
            if arguments and arguments[0] and arguments[0][0].kind in {
                "string", "dynamic"
            }:
                return True

        # HTML parsing sinks can create or replace a generated attribute
        # without calling setAttribute/dataset.
        if (
            token.kind == "ident"
            and token.value == "outerHTML"
            and index
            and tokens[index - 1].value in {".", "?."}
            and index + 1 < len(tokens)
            and tokens[index + 1].value in _JS_ASSIGNMENT_OPERATORS
        ):
            return True
        if (
            token.kind == "string"
            and token.value == "outerHTML"
            and index
            and tokens[index - 1].value == "["
            and index + 2 < len(tokens)
            and tokens[index + 1].value == "]"
            and tokens[index + 2].value in _JS_ASSIGNMENT_OPERATORS
        ):
            return True
        if (
            token.kind in {"ident", "string"}
            and token.value == "innerHTML"
        ):
            if token.kind == "ident":
                member = bool(index and tokens[index - 1].value in {".", "?."})
                assignment = index + 1
            else:
                member = bool(
                    index
                    and tokens[index - 1].value == "["
                    and index + 1 < len(tokens)
                    and tokens[index + 1].value == "]"
                )
                assignment = index + 2
            if (
                member
                and assignment < len(tokens)
                and tokens[assignment].value in _JS_ASSIGNMENT_OPERATORS
            ):
                # Keep unrelated, statically bounded UI fragments out of the
                # generated-attribute gate. Block when the HTML source itself
                # can spell the identity-bearing attribute, or when a template
                # expression makes the source text unprovable.
                for rhs in tokens[assignment + 1:]:
                    if rhs.value == ";":
                        break
                    if rhs.kind == "dynamic" or (
                        rhs.kind == "string"
                        and attribute.casefold() in rhs.value.casefold()
                    ):
                        return True
        if (
            token.kind == "ident"
            and token.value in {"insertAdjacentHTML", "write", "writeln"}
            and index
            and tokens[index - 1].value in {".", "?."}
            and index + 1 < len(tokens)
            and tokens[index + 1].value == "("
        ):
            return True

    for index, token in enumerate(tokens):
        if token.kind == "ident" and token.value in {
            *set(_JS_ATTRIBUTE_MUTATORS), "setAttributeNode"
        }:
            member = bool(index and tokens[index - 1].value in {".", "?."})
            bare_call = bool(
                index + 1 < len(tokens)
                and tokens[index + 1].value == "("
                and not (
                    index
                    and tokens[index - 1] == _JSToken("ident", "function")
                )
            )
            if not member and not bare_call:
                continue
            if index + 1 >= len(tokens) or tokens[index + 1].value != "(":
                return True
            arguments, call_end = _js_call_arguments(tokens, index + 1)
            if (
                not member
                and call_end is not None
                and call_end + 1 < len(tokens)
                and tokens[call_end + 1].value == "{"
            ):
                # Object/class method definition, not a call site.
                continue
            if _js_method_call_mutates(
                token.value, arguments, index, scopes, attribute
            ):
                return True

        if token.kind == "string" and token.value in {
            *set(_JS_ATTRIBUTE_MUTATORS), "setAttributeNode"
        } and index and tokens[index - 1].value == "[":
            if index + 2 >= len(tokens) or tokens[index + 1].value != "]":
                return True
            if tokens[index + 2].value != "(":
                return True
            arguments, _end = _js_call_arguments(tokens, index + 2)
            if _js_method_call_mutates(
                token.value, arguments, index, scopes, attribute
            ):
                return True

        dataset_end: int | None = None
        if token == _JSToken("ident", "dataset") and index and tokens[index - 1].value in {".", "?."}:
            dataset_end = index + 1
        elif (
            token == _JSToken("string", "dataset")
            and index
            and tokens[index - 1].value == "["
            and index + 1 < len(tokens)
            and tokens[index + 1].value == "]"
        ):
            dataset_end = index + 2
        if dataset_end is None or dataset_end >= len(tokens):
            continue
        if tokens[dataset_end].value in _JS_ASSIGNMENT_OPERATORS:
            return True
        if (
            tokens[dataset_end].value in {".", "?."}
            and dataset_end + 1 < len(tokens)
            and tokens[dataset_end + 1].kind == "ident"
        ):
            key_domain = frozenset({tokens[dataset_end + 1].value})
            after_key = dataset_end + 2
        elif tokens[dataset_end].value == "[":
            close = _matching_js_token(tokens, dataset_end, "[", "]")
            if close is None:
                return True
            key_domain = _js_argument_domain(
                tokens[dataset_end + 1:close], index, scopes
            )
            after_key = close + 1
        else:
            # Passing or aliasing the whole DOMStringMap leaves future writes
            # unprovable; a direct property read continues through the branches
            # above and remains allowed.
            return True
        if (
            after_key < len(tokens)
            and tokens[after_key].value in _JS_ASSIGNMENT_OPERATORS
            and (
                key_domain is None
                or "l" in {value.casefold() for value in key_domain}
            )
        ):
            return True

    # A computed member call with an unprovable method name could resolve to an
    # attribute mutator. Only inspect executable tokens and only block when one
    # of its attribute-name positions is itself unprovable or data-l.
    for close, token in enumerate(tokens):
        if token.value != "]" or close + 1 >= len(tokens) or tokens[close + 1].value != "(":
            continue
        open_index = close - 1
        depth = 1
        while open_index >= 0:
            if tokens[open_index].value == "]":
                depth += 1
            elif tokens[open_index].value == "[":
                depth -= 1
                if depth == 0:
                    break
            open_index -= 1
        if open_index < 0:
            continue
        property_tokens = tokens[open_index + 1:close]
        if len(property_tokens) == 1 and property_tokens[0].kind == "string":
            continue
        arguments, _end = _js_call_arguments(tokens, close + 1)
        for argument in arguments[:2]:
            domain = _js_argument_domain(argument, close, scopes)
            if domain is None or attribute.casefold() in {
                value.casefold() for value in domain
            }:
                return True
    return False


def _script_is_executable(attrs) -> bool:
    types = _attribute_values(attrs, "type")
    if not types:
        return True
    if len(types) != 1 or not isinstance(types[0], str):
        return True
    script_type = types[0].split(";", 1)[0].strip().casefold()
    return not script_type or script_type in _JS_EXECUTABLE_SCRIPT_TYPES


def _javascript_sources(
    metadata: _PublicMetadataParser,
    page: Path,
    site: Path,
    trusted_remote_scripts: frozenset[str],
) -> tuple[list[str], bool]:
    sources: list[str] = []
    unverified = False
    site_root = site.resolve()
    for attrs, body in metadata.script_blocks:
        if not _script_is_executable(attrs):
            continue
        raw_sources = _attribute_values(attrs, "src")
        # Browsers ignore a script element's body when src is present.
        if not raw_sources and body.strip():
            sources.append(body)
        for raw_source in raw_sources:
            if not isinstance(raw_source, str) or not raw_source.strip():
                unverified = True
                continue
            parsed = urlsplit(raw_source.strip())
            if parsed.scheme in {"http", "https"} or parsed.netloc:
                # Do not fetch or invent remote contents. Only an exact URL tied
                # to an existing local policy contract may cross this boundary.
                if raw_source.strip() not in trusted_remote_scripts:
                    unverified = True
                continue
            if parsed.scheme:
                unverified = True
                continue
            raw_path = unquote(parsed.path)
            candidate = site / raw_path.lstrip("/") if raw_path.startswith("/") else page.parent / raw_path
            try:
                resolved = candidate.resolve()
                resolved.relative_to(site_root)
            except (OSError, ValueError):
                unverified = True
                continue
            if resolved.is_symlink() or not resolved.is_file():
                unverified = True
                continue
            script = _read(resolved)
            if script is None:
                unverified = True
            else:
                sources.append(script)

    for attrs in metadata.element_attributes:
        for name, value in attrs:
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            lowered = name.casefold()
            if lowered.startswith("on") and len(lowered) > 2:
                sources.append(value)
            elif lowered in {"href", "src", "action", "formaction"} and value.lstrip().casefold().startswith("javascript:"):
                sources.append(value.lstrip()[11:])
    return sources, unverified


def _stylesheet_sources(
    metadata: _PublicMetadataParser,
    page: Path,
    site: Path,
    trusted_remote_stylesheets: frozenset[str],
) -> tuple[list[str], bool]:
    """Load local linked stylesheets without crossing the built-site root."""
    sources: list[str] = []
    unverified = False
    site_root = site.resolve()
    for attrs in metadata.link_tags:
        rel_values = _attribute_values(attrs, "rel")
        is_stylesheet = any(
            isinstance(value, str)
            and "stylesheet" in {part.casefold() for part in value.split()}
            for value in rel_values
        )
        if not is_stylesheet:
            continue
        hrefs = _attribute_values(attrs, "href")
        if len(hrefs) != 1:
            unverified = True
            continue
        raw_source = hrefs[0]
        if not isinstance(raw_source, str) or not raw_source.strip():
            unverified = True
            continue
        parsed = urlsplit(raw_source.strip())
        if parsed.scheme in {"http", "https"} or parsed.netloc:
            if raw_source.strip() not in trusted_remote_stylesheets:
                unverified = True
            continue
        if parsed.scheme:
            unverified = True
            continue
        raw_path = unquote(parsed.path)
        candidate = (
            site / raw_path.lstrip("/")
            if raw_path.startswith("/")
            else page.parent / raw_path
        )
        try:
            if candidate.is_symlink():
                raise ValueError("stylesheet symlink")
            resolved = candidate.resolve()
            resolved.relative_to(site_root)
        except (OSError, ValueError):
            unverified = True
            continue
        if not resolved.is_file():
            unverified = True
            continue
        stylesheet = _read(resolved)
        if stylesheet is None:
            unverified = True
            continue
        # Imported CSS is an unresolved rendering graph. Do not silently accept
        # a linked sheet whose rendered source is only partially inspected.
        if _css_has_unresolved_import(stylesheet):
            unverified = True
        sources.append(stylesheet)
    return sources, unverified


def _compile_patterns(identity: dict) -> tuple[list[re.Pattern[str]], list[Finding]]:
    patterns: list[re.Pattern[str]] = []
    findings: list[Finding] = []
    raw_patterns = identity.get("forbidden_personal_claim_patterns")
    if not isinstance(raw_patterns, list) or not raw_patterns:
        return [], [Finding(".system_control/policy.json", 1, "IDENTITY_PATTERNS_MISSING")]
    for value in raw_patterns:
        if not isinstance(value, str) or not value:
            findings.append(Finding(".system_control/policy.json", 1, "IDENTITY_PATTERN_INVALID"))
            continue
        try:
            patterns.append(re.compile(value, re.I))
        except re.error:
            findings.append(Finding(".system_control/policy.json", 1, "IDENTITY_PATTERN_INVALID"))
    return patterns, findings


def _speaker_pattern(identity: dict) -> tuple[re.Pattern[str] | None, list[Finding]]:
    speakers = identity.get("forbidden_public_speakers")
    if not isinstance(speakers, list) or not speakers or not all(
        isinstance(value, str) and value.strip() for value in speakers
    ):
        return None, [Finding(".system_control/policy.json", 1, "FORBIDDEN_SPEAKERS_INVALID")]
    body = "|".join(re.escape(value.strip()) for value in speakers)
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + body + r")(?![A-Za-z0-9_])", re.I), []


def _copy_findings(
    text: str,
    path: str,
    line: int,
    patterns: Iterable[re.Pattern[str]],
    speakers: re.Pattern[str] | None,
) -> list[Finding]:
    findings: list[Finding] = []
    if any(pattern.search(text) for pattern in patterns):
        findings.append(Finding(path, line, "PERSONAL_PUBLIC_VOICE"))
    if speakers is not None and speakers.search(text):
        findings.append(Finding(path, line, "AGENT_AS_PUBLIC_SPEAKER"))
    return findings


def _identity_entity_ok(value, brand: str, entity_type: str) -> bool:
    return (
        isinstance(value, dict)
        and value.get("@type") == entity_type
        and value.get("name") == brand
    )


def _jsonld_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _jsonld_nodes(item)
    elif isinstance(value, dict):
        yield value
        for key, item in value.items():
            # A JSON-LD context describes term mappings, not public entities.
            if key != "@context":
                yield from _jsonld_nodes(item)


def _jsonld_string_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _jsonld_string_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _jsonld_string_values(item)


def _scan_site(
    site: Path,
    brand: str,
    entity_type: str,
    patterns: list[re.Pattern[str]],
    speakers: re.Pattern[str] | None,
    trusted_remote_scripts: frozenset[str],
    trusted_remote_stylesheets: frozenset[str],
) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    checked = 0
    if not site.is_dir():
        return [Finding("site", 1, "BUILT_SITE_MISSING")], 0
    for path in sorted(site.rglob("*.html")):
        if _VERIFY_FILE.match(path.name):
            continue
        try:
            rel = "site/" + path.relative_to(site).as_posix()
        except ValueError:
            findings.append(Finding("site", 1, "PUBLIC_PAGE_PATH_UNSAFE"))
            continue
        if path.is_symlink():
            findings.append(Finding(rel, 1, "PUBLIC_PAGE_SYMLINK"))
            continue
        document = _read(path)
        if document is None:
            findings.append(Finding(rel, 1, "PUBLIC_PAGE_UNREADABLE"))
            continue
        checked += 1
        metadata = _parse_public_metadata(document)
        for metadata_value in metadata.values:
            findings.extend(
                _copy_findings(metadata_value, rel, 1, patterns, speakers)
            )

        redirect = _has_meta_refresh(metadata)
        findings.extend(
            _meta_identity_findings(
                metadata, rel, brand, "name", "author", "AUTHOR", not redirect
            )
        )
        findings.extend(
            _meta_identity_findings(
                metadata,
                rel,
                brand,
                "property",
                "og:site_name",
                "SITE_NAME",
                not redirect,
            )
        )

        generated_attributes: set[str] = set()
        linked_styles, stylesheet_unverified = _stylesheet_sources(
            metadata, path, site, trusted_remote_stylesheets
        )
        if stylesheet_unverified:
            findings.append(
                Finding(rel, 1, "CSS_EXTERNAL_STYLESHEET_UNVERIFIED")
            )
        for css, inline in [
            *((value, False) for value in metadata.style_blocks),
            *((value, True) for value in metadata.style_attributes),
            *((value, False) for value in linked_styles),
        ]:
            generated, referenced, css_valid = _css_generated_text(css, inline)
            if not css_valid:
                findings.append(Finding(rel, 1, "CSS_GENERATED_TEXT_INVALID"))
            for value in generated:
                findings.extend(_copy_findings(value, rel, 1, patterns, speakers))
            generated_attributes.update(referenced)
        for name in sorted(generated_attributes):
            for value in _generated_attribute_values(metadata, name):
                findings.extend(_copy_findings(value, rel, 1, patterns, speakers))
        if generated_attributes:
            javascript, script_unverified = _javascript_sources(
                metadata, path, site, trusted_remote_scripts
            )
            if script_unverified:
                findings.append(
                    Finding(rel, 1, "CSS_GENERATED_ATTRIBUTE_SCRIPT_UNVERIFIED")
                )
            if any(
                _js_may_mutate_generated_attribute(source, name)
                for source in javascript
                for name in generated_attributes
            ):
                findings.append(
                    Finding(rel, 1, "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION")
                )

        visible = _visible_text(document)
        if not redirect and brand not in visible:
            findings.append(Finding(rel, 1, "PAGE_VISIBLE_IDENTITY_MISSING"))
        # Redirect shells may omit article identity metadata, but their rendered
        # copy remains public and must not bypass personal/agent voice checks.
        findings.extend(_copy_findings(visible, rel, 1, patterns, speakers))

        for match in _JSONLD.finditer(document):
            try:
                payload = _strict_json_loads(html.unescape(match.group(1)))
            except (TypeError, ValueError):
                findings.append(Finding(rel, 1, "JSONLD_INVALID"))
                continue
            for metadata_value in _jsonld_string_values(payload):
                findings.extend(
                    _copy_findings(metadata_value, rel, 1, patterns, speakers)
                )
            for node in _jsonld_nodes(payload):
                for field in ("author", "publisher"):
                    if field in node and not _identity_entity_ok(
                        node[field], brand, entity_type
                    ):
                        findings.append(
                            Finding(rel, 1, "JSONLD_%s_NOT_PAGE" % field.upper())
                        )
                raw_type = node.get("@type")
                types = {raw_type} if isinstance(raw_type, str) else set(raw_type or [])
                if types.intersection({"Article", "BlogPosting", "NewsArticle"}):
                    for field in ("author", "publisher"):
                        if field not in node:
                            findings.append(
                                Finding(rel, 1, "JSONLD_%s_MISSING" % field.upper())
                            )
    return sorted(set(findings)), checked


def _scan_manifest(
    manifest: Path,
    patterns: list[re.Pattern[str]],
    speakers: re.Pattern[str] | None,
) -> tuple[list[Finding], int]:
    data = _load_json(manifest)
    rel = ".system_control/content_manifest.json"
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return [Finding(rel, 1, "CONTENT_MANIFEST_INVALID")], 0
    findings: list[Finding] = []
    checked = 0
    for index, item in enumerate(data["items"], 1):
        if not isinstance(item, dict):
            findings.append(Finding(rel, index, "CONTENT_ITEM_INVALID"))
            continue
        values = []
        for field in ("topic_th", "disclosure"):
            if isinstance(item.get(field), str):
                values.append(item[field])
        captions = item.get("captions")
        if isinstance(captions, dict):
            values.extend(value for value in captions.values() if isinstance(value, str))
        checked += len(values)
        for text in values:
            findings.extend(_copy_findings(text, rel, index, patterns, speakers))
    return sorted(set(findings)), checked


def _scan_knowledge(
    repo: Path,
    patterns: list[re.Pattern[str]],
    speakers: re.Pattern[str] | None,
) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    checked = 0
    log_dir = repo / "automation-log"
    for path in sorted(log_dir.glob(KNOWLEDGE_GLOB)) if log_dir.is_dir() else []:
        text = _read(path)
        rel = "automation-log/" + path.name
        if text is None:
            findings.append(Finding(rel, 1, "KNOWLEDGE_LIBRARY_UNREADABLE"))
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if not _KNOWLEDGE_ROW.match(line):
                continue
            checked += 1
            public_copy = html.unescape(line.replace("<br>", "\n"))
            findings.extend(
                _copy_findings(public_copy, rel, line_number, patterns, speakers)
            )
    return sorted(set(findings)), checked


def _scan_prompts(
    prompt_roots: tuple[tuple[str, Path], ...],
    identity: dict,
    brand: str,
    patterns: list[re.Pattern[str]],
) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    checked = 0
    marker = identity.get("required_prompt_marker")
    tasks = identity.get("outward_copy_tasks")
    if not isinstance(marker, str) or not marker:
        findings.append(Finding(".system_control/policy.json", 1, "PROMPT_MARKER_INVALID"))
        return findings, checked
    if not isinstance(tasks, list) or not tasks or not all(
        isinstance(task, str) and task for task in tasks
    ):
        findings.append(Finding(".system_control/policy.json", 1, "OUTWARD_TASKS_INVALID"))
        return findings, checked

    # Future-proof the explicit SSOT list: a newly added live ngernduangold task
    # that drafts public copy may not silently bypass the page-identity contract.
    declared = set(tasks)
    discovered: set[str] = set()
    disabled_markers = (
        "retired \u2014 no-op",
        "retired - no-op",
        "description: [done",
        "description: [disabled",
        "description: [paused",
        "description: [\u0e1b\u0e34\u0e14",  # closed
        "description: [\u0e1e\u0e31\u0e01",  # paused
    )
    body_disabled_markers = (
        "\n[\u0e1b\u0e34\u0e14",  # closed
        "\n[\u0e1e\u0e31\u0e01",  # paused
    )
    for _label, root in prompt_roots:
        if not root.is_dir():
            continue
        for directory in sorted(root.glob("ngernduangold-*")):
            path = directory / "SKILL.md"
            if not path.is_file():
                continue
            text = _read(path)
            if text is None:
                continue
            head = "\n".join(text.splitlines()[:25]).casefold()
            if any(value in head for value in disabled_markers) or any(
                value in head for value in body_disabled_markers
            ):
                continue
            low = text.casefold()
            if any(hint in low for hint in _OUTWARD_HINTS):
                discovered.add(directory.name)
    for task in sorted(discovered - declared):
        findings.append(Finding("scheduled/" + task, 1, "OUTWARD_TASK_UNDECLARED"))

    for task in tasks:
        copies = []
        for label, root in prompt_roots:
            candidate = root / task / "SKILL.md"
            if candidate.exists():
                copies.append((label, candidate))
        if not copies:
            findings.append(Finding("scheduled/" + task, 1, "OUTWARD_TASK_PROMPT_MISSING"))
            continue
        for label, path in copies:
            checked += 1
            text = _read(path)
            rel = "scheduled-%s/%s/SKILL.md" % (label, task)
            if text is None:
                findings.append(Finding(rel, 1, "OUTWARD_TASK_PROMPT_UNREADABLE"))
                continue
            if marker not in text:
                findings.append(Finding(rel, 1, "PAGE_IDENTITY_MARKER_MISSING"))
            if brand not in text:
                findings.append(Finding(rel, 1, "PAGE_IDENTITY_NAME_MISSING"))
            # Selected tasks generate copy intended for publication.  A singular
            # personal voice anywhere in their live prompt is unsafe because agents
            # routinely copy examples verbatim.  Agent names are allowed only in the
            # internal rule line, so those are enforced by the marker rather than a
            # blind full-prompt name ban.
            if any(pattern.search(text) for pattern in patterns):
                findings.append(Finding(rel, 1, "PERSONAL_VOICE_IN_OUTWARD_PROMPT"))
    return sorted(set(findings)), checked


def scan(
    repo: Path = ROOT,
    policy_path: Path | None = None,
    site: Path | None = None,
    manifest: Path | None = None,
    prompt_roots: tuple[tuple[str, Path], ...] | None = None,
) -> tuple[list[Finding], dict[str, int]]:
    policy_path = policy_path or (repo / ".system_control" / "policy.json")
    site = site or (repo / "site")
    manifest = manifest or (repo / ".system_control" / "content_manifest.json")
    prompt_roots = prompt_roots or PROMPT_ROOTS
    policy = _load_json(policy_path)
    if not isinstance(policy, dict):
        return [Finding(".system_control/policy.json", 1, "POLICY_INVALID")], {}
    identity = policy.get("public_identity")
    if not isinstance(identity, dict):
        return [Finding(".system_control/policy.json", 1, "PUBLIC_IDENTITY_MISSING")], {}

    findings: list[Finding] = []
    brand = identity.get("canonical_name")
    entity_type = identity.get("entity_type")
    if not isinstance(brand, str) or not brand.strip():
        findings.append(Finding(".system_control/policy.json", 1, "CANONICAL_NAME_INVALID"))
        brand = ""
    if entity_type != "Organization":
        findings.append(Finding(".system_control/policy.json", 1, "ENTITY_TYPE_NOT_ORGANIZATION"))
        entity_type = "Organization"
    if identity.get("page_only") is not True:
        findings.append(Finding(".system_control/policy.json", 1, "PAGE_ONLY_NOT_TRUE"))

    patterns, pattern_findings = _compile_patterns(identity)
    speakers, speaker_findings = _speaker_pattern(identity)
    findings.extend(pattern_findings)
    findings.extend(speaker_findings)

    trusted_remote_scripts: frozenset[str] = frozenset()
    ga4 = policy.get("ga4")
    measurement_id = ga4.get("measurement_id") if isinstance(ga4, dict) else None
    if isinstance(measurement_id, str) and re.fullmatch(
        r"G-[A-Z0-9]+", measurement_id
    ):
        trusted_remote_scripts = frozenset({
            "https://www.googletagmanager.com/gtag/js?id=" + measurement_id
        })

    trusted_remote_stylesheets: frozenset[str] = frozenset()
    raw_stylesheets = identity.get("trusted_remote_stylesheets", [])
    if not isinstance(raw_stylesheets, list) or any(
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or urlsplit(value).scheme != "https"
        or not urlsplit(value).netloc
        for value in raw_stylesheets
    ) or len(raw_stylesheets) != len(set(raw_stylesheets)):
        findings.append(
            Finding(
                ".system_control/policy.json",
                1,
                "TRUSTED_REMOTE_STYLESHEETS_INVALID",
            )
        )
    else:
        trusted_remote_stylesheets = frozenset(raw_stylesheets)

    site_findings, pages = _scan_site(
        site,
        brand,
        entity_type,
        patterns,
        speakers,
        trusted_remote_scripts,
        trusted_remote_stylesheets,
    )
    manifest_findings, captions = _scan_manifest(manifest, patterns, speakers)
    knowledge_findings, knowledge_rows = _scan_knowledge(repo, patterns, speakers)
    prompt_findings, prompts = _scan_prompts(prompt_roots, identity, brand, patterns)
    findings.extend(site_findings)
    findings.extend(manifest_findings)
    findings.extend(knowledge_findings)
    findings.extend(prompt_findings)
    counts = {
        "pages": pages,
        "caption_fields": captions,
        "knowledge_rows": knowledge_rows,
        "outward_prompts": prompts,
    }
    return sorted(set(findings)), counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings, counts = scan()
    if args.json:
        print(
            json.dumps(
                {
                    "verdict": "FAIL" if findings else "PASS",
                    "counts": counts,
                    "findings": [finding.__dict__ for finding in findings],
                },
                ensure_ascii=True,
            )
        )
    elif findings:
        for finding in findings:
            print("FAIL %s:%d %s" % (finding.path, finding.line, finding.category))
    else:
        print(
            "PASS public identity guard: page-only identity across "
            "%d pages, %d caption fields, %d knowledge rows, %d outward prompts"
            % (
                counts.get("pages", 0),
                counts.get("caption_fields", 0),
                counts.get("knowledge_rows", 0),
                counts.get("outward_prompts", 0),
            )
        )
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
