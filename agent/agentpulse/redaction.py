"""Recursive secret redaction for logs, payloads, spool files, and audit records.

The redactor is deliberately conservative: secret-looking keys are replaced in
structured values, while URL credentials, token-like query parameters, common
environment assignments, bearer headers, and PEM private keys are scrubbed in
text. It never mutates caller-owned containers.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

_SECRET_KEY_RE = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|authorization|credential|"
    r"private[_-]?key|webhook|cookie|session)",
    re.IGNORECASE,
)
_SECRET_QUERY_RE = re.compile(
    r"(?:token|api[_-]?key|key|secret|password|passwd|authorization|credential|"
    r"signature|sig|access[_-]?token|refresh[_-]?token)",
    re.IGNORECASE,
)
_ENV_RE = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API[_-]?KEY|"
    r"AUTHORIZATION|CREDENTIAL|PRIVATE[_-]?KEY|WEBHOOK|COOKIE|SESSION))"
    r"(?P<sep>\s*=\s*|\s*:\s*)(?P<value>[^\s,;&]+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(\bBearer\s+)[^\s,;]+", re.IGNORECASE)
_BASIC_RE = re.compile(r"(\bBasic\s+)[^\s,;]+", re.IGNORECASE)
_PEM_RE = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_ASSIGNMENT_RE = re.compile(
    r"(?P<name>\b(?:password|passwd|secret|token|api[_-]?key|authorization|"
    r"credential|private[_-]?key|webhook|cookie|session)\b)"
    r"(?P<sep>\s*[:=]\s*)(?P<value>[^\s,;&]+)",
    re.IGNORECASE,
)


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not (parts.scheme and (parts.netloc or parts.query)):
        return value
    netloc = parts.netloc
    if "@" in netloc:
        host = netloc.rsplit("@", 1)[1]
        netloc = f"{REDACTED}@{host}"
    query = []
    changed = False
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        if _SECRET_QUERY_RE.search(key):
            val = REDACTED
            changed = True
        query.append((key, val))
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), parts.fragment)) if changed or netloc != parts.netloc else value


def redact_text(value: str) -> str:
    """Redact secrets from arbitrary text, preserving surrounding diagnostics."""
    value = _PEM_RE.sub(REDACTED, value)
    # Process complete URLs before generic KEY=value matching. Otherwise a
    # query delimiter such as ``&keep=yes`` can be swallowed as one secret.
    value = re.sub(r"https?://[^\s<>\"']+", lambda m: _redact_url(m.group(0)), value)
    value = _BEARER_RE.sub(rf"\1{REDACTED}", value)
    value = _BASIC_RE.sub(rf"\1{REDACTED}", value)
    value = _ENV_RE.sub(rf"\g<name>\g<sep>{REDACTED}", value)
    return _ASSIGNMENT_RE.sub(rf"\g<name>\g<sep>{REDACTED}", value)


def redact(value: Any) -> Any:
    """Return a recursively redacted copy of mappings, sequences, and text."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _SECRET_KEY_RE.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, set):
        return {redact(item) for item in value}
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    """Redact HTTP headers, including bearer and cookie values."""
    return redact(headers)


def redact_json(value: Any) -> str:
    """Redact and serialize JSON for safe output."""
    return json.dumps(redact(value), sort_keys=True, default=str)


# Explicit alias for call sites that read more naturally.
sanitize = redact
sanitize_text = redact_text
__all__ = ["REDACTED", "redact", "redact_headers", "redact_json", "redact_text", "sanitize", "sanitize_text"]
