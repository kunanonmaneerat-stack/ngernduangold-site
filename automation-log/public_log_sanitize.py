"""Remove private values before a record enters the public repository.

This is a write-boundary control, not a scanner exception.  The privacy guard
continues to scan the resulting files unchanged and fail closed if a producer
finds another way to emit protected data.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any


EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)
PHONE_RE = re.compile(r"(?<!\d)(?:\+66|66|0)\d{8,9}(?!\d)")
IPV4_RE = re.compile(r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])")
TELEGRAM_ID_RE = re.compile(
    r"(?i)(\btelegram\b[^\r\n]{0,80}?)(?<!\d)-?\d{7,}(?!\d)"
)
SLACK_ROUTE_RE = re.compile(r"(?i)https?://app\.slack\.com/client/[^\s\"'<>]+")
KNOWN_CREDENTIAL_RE = re.compile(
    r"(?i)(?:\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"
    r"|\bAIza[0-9A-Za-z_-]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\bsk-[A-Za-z0-9_-]{20,})"
)

PRIVATE_KEYS = {
    "access_token", "refresh_token", "auth_token", "api_key", "client_secret",
    "private_key", "password", "passwd", "authorization", "cookie",
    "session_cookie", "webhook", "webhook_url", "email", "email_address",
    "buyer_email", "phone", "phone_number", "mobile", "mobile_number",
    "full_name", "customer_name", "customer_id", "account_number",
    "bank_account", "postal_address", "ip", "ip_address", "public_ip",
    "host_ip", "ipv4", "ipv6", "chat_id", "telegram_chat_id",
    "slack_channel_id", "slack_workspace_id", "workspace_id", "revenue",
    "revenue_thb", "gross_revenue", "net_revenue", "payout",
    "commission_earned", "transaction_id", "order_id",
}


def _normalise_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _redact_ipv4(match: re.Match[str]) -> str:
    try:
        address = ipaddress.ip_address(match.group(0))
    except ValueError:
        return match.group(0)
    if address.is_unspecified or address.is_loopback:
        return match.group(0)
    return "[redacted-network-address]"


def sanitize_text(value: Any) -> str:
    text = str(value)
    text = EMAIL_RE.sub("[redacted-email]", text)
    text = PHONE_RE.sub("[redacted-phone]", text)
    text = IPV4_RE.sub(_redact_ipv4, text)
    text = TELEGRAM_ID_RE.sub(r"\1[redacted-operational-id]", text)
    text = SLACK_ROUTE_RE.sub("[redacted-operational-route]", text)
    text = KNOWN_CREDENTIAL_RE.sub("[redacted-credential]", text)
    return text


def sanitize_public_value(value: Any, redacted_fields: set[str] | None = None) -> Any:
    found = redacted_fields if redacted_fields is not None else set()
    if isinstance(value, dict):
        clean = {}
        for key, child in value.items():
            normal = _normalise_key(key)
            if normal in PRIVATE_KEYS or normal.endswith(
                ("_access_token", "_refresh_token", "_api_key", "_client_secret",
                 "_password", "_private_key")
            ):
                found.add(normal)
                continue
            clean[str(key)] = sanitize_public_value(child, found)
        return clean
    if isinstance(value, list):
        return [sanitize_public_value(child, found) for child in value]
    if isinstance(value, tuple):
        return [sanitize_public_value(child, found) for child in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def sanitize_public_record(record: dict[str, Any]) -> dict[str, Any]:
    redacted: set[str] = set()
    clean = sanitize_public_value(record, redacted)
    if redacted:
        clean["redacted_private_fields"] = sorted(redacted)
    return clean

