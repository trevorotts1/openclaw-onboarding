"""The single result envelope, fingerprinting and redaction helpers.

Frozen by evidence/W01/GU-004-CONTRACT-FREEZE.md sections 2.1-2.3.

No secret, token, PIT value, full payload or customer identifier beyond the
tenant is ever written into an envelope.  ``redaction="ids-only"`` replaces
non-tenant identifier values.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Mapping

from .errors import ContractViolation

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .readback import ReadbackResult

ADAPTER_VERSION = "ghl-public-adapter-0.1"

REDACTED = "[REDACTED]"
ID_PLACEHOLDER = "<id>"


class Status(str, Enum):
    ok = "ok"
    unknown_outcome = "unknown_outcome"
    denied = "denied"
    not_found = "not_found"
    conflict = "conflict"
    validation_error = "validation_error"
    rate_limited = "rate_limited"
    unavailable = "unavailable"


# Required evidence keys, always present.  None is allowed only where
# section 2.2 says so (http_status / response_fingerprint / readback).
REQUIRED_EVIDENCE_KEYS: tuple[str, ...] = (
    "operation_id",
    "request_fingerprint",
    "http_status",
    "response_fingerprint",
    "tenant",
    "attempt",
    "readback",
    "receipt_id",
    "version_header",
    "timeout_s",
    "adapter_version",
    "transport",
    "auth_kind",
    "auth_source",
    "doc_url",
    "doc_fetch_date",
    "request_bytes",
    "started_at",
    "finished_at",
)

# Response headers that may be echoed.  Everything else (authorization,
# cookies, raw tokens) is dropped at the seam.
ECHOED_RESPONSE_HEADERS: frozenset[str] = frozenset(
    {
        "content-type",
        "content-length",
        "date",
        "retry-after",
        "server",
        "version",
        "x-request-id",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
    }
)

_SENSITIVE_TOKENS = frozenset(
    {
        "authorization",
        "bearer",
        "cookie",
        "key",
        "apikey",
        "password",
        "pit",
        "secret",
        "secrets",
        "token",
        "tokens",
    }
)
_SENSITIVE_SUBSTRINGS = ("api_key", "private_integration", "refresh_token", "approval_token")
_SAFE_ID_KEYS = frozenset({"locationid", "location_id", "altid", "tenant"})


@dataclass(frozen=True)
class OperationResult:
    """Section 2.1, verbatim."""

    status: Status
    operation_id: str
    receipt_id: str
    request_fingerprint: str
    http_status: int | None
    response_fingerprint: str | None
    tenant: str
    attempt: int
    version_header: str | None
    readback: "ReadbackResult | None"
    adapter_version: str
    transport: Literal["http", "caf-cli"]
    doc_url: str | None
    evidence: Mapping[str, Any]
    error: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", Status(self.status))
        if not isinstance(self.evidence, Mapping):
            raise ContractViolation(
                "evidence_not_mapping", operation_id=self.operation_id
            )
        missing = [key for key in REQUIRED_EVIDENCE_KEYS if key not in self.evidence]
        if missing:
            raise ContractViolation(
                "evidence_keys_missing",
                operation_id=self.operation_id,
                detail={"missing": missing},
            )
        if not isinstance(self.attempt, int) or self.attempt < 1:
            raise ContractViolation(
                "attempt_invalid", operation_id=self.operation_id
            )
        if not _is_hex64(self.request_fingerprint):
            raise ContractViolation(
                "request_fingerprint_invalid", operation_id=self.operation_id
            )
        if self.response_fingerprint is not None and not _is_hex64(
            self.response_fingerprint
        ):
            raise ContractViolation(
                "response_fingerprint_invalid", operation_id=self.operation_id
            )
        if self.error is not None and not isinstance(self.error, Mapping):
            raise ContractViolation("error_not_mapping", operation_id=self.operation_id)


# ---------------------------------------------------------------------------
# fingerprinting
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Deterministic JSON used for every fingerprint."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def fingerprint_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def request_fingerprint_of(payload: Mapping[str, Any]) -> str:
    return fingerprint_bytes(canonical_json(dict(payload)).encode("utf-8"))


def response_fingerprint(payload: bytes | None) -> str | None:
    """64-hex of the received body.  None when no body was received."""

    if not payload:
        return None
    return fingerprint_bytes(payload)


def _is_hex64(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value)


# ---------------------------------------------------------------------------
# redaction
# ---------------------------------------------------------------------------


def _tokens(name: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", name.lower()) if part}


def is_sensitive_key(name: str) -> bool:
    if not isinstance(name, str):
        return False
    if _tokens(name) & _SENSITIVE_TOKENS:
        return True
    joined = name.lower().replace("-", "_")
    return any(marker in joined for marker in _SENSITIVE_SUBSTRINGS)


def redact_value(_value: Any) -> str:
    return REDACTED


def redact_mapping(
    value: Any,
    *,
    redaction: Literal["none", "ids-only"] = "none",
    _depth: int = 0,
) -> Any:
    """Deep copy with secret-shaped keys removed.

    ``redaction="ids-only"`` also replaces identifier values other than the
    tenant's own location id.
    """

    if _depth > 8:
        return "<depth-limited>"
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if is_sensitive_key(key_text):
                out[key_text] = REDACTED
                continue
            if redaction == "ids-only" and _looks_like_id_key(key_text):
                out[key_text] = ID_PLACEHOLDER
                continue
            out[key_text] = redact_mapping(item, redaction=redaction, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [
            redact_mapping(item, redaction=redaction, _depth=_depth + 1)
            for item in value
        ]
    return value


def _looks_like_id_key(name: str) -> bool:
    lowered = name.lower()
    if lowered in _SAFE_ID_KEYS:
        return False
    return lowered.endswith("id") or lowered.endswith("ids")


def redact_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Allowlist only.  Authorization/cookies never survive the seam."""

    out: dict[str, str] = {}
    for key, value in dict(headers or {}).items():
        if str(key).lower() in ECHOED_RESPONSE_HEADERS:
            out[str(key)] = str(value)
    return out
