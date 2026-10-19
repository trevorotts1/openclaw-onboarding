"""Canonical intent fingerprints and write idempotency keys.

Frozen by evidence/W01/GU-004-CONTRACT-FREEZE.md sections 1.3 step 6 and 2.4.

Key format: ``gxo_<op-short>-<32 hex>``.  The canonical intent is
``sha256(canonical_json(operation_id, method, resolved_path, sorted(query),
body, tenant, version))`` and is echoed as ``request_fingerprint``.  Reusing a
key with a different fingerprint is refused.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import ContractViolation
from .result import canonical_json

_KEY_PATTERN = re.compile(r"^gxo_([a-z0-9][a-z0-9_-]{0,31})-([0-9a-f]{32})$")

IDEMPOTENCY_KEY_FORMAT = "gxo_<op-short>-<32 hex>"


def operation_short(operation_id: str) -> str:
    text = str(operation_id or "").strip().lower()
    if not text:
        raise ContractViolation("operation_id_invalid")
    short = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    short = re.sub(r"-{2,}", "-", short)
    short = short[:32].strip("-")
    return short or "op"


def canonical_intent(
    *,
    operation_id: str,
    method: str,
    resolved_path: str,
    query: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
    tenant: str,
    version: str | None,
) -> str:
    """64-hex request fingerprint (section 1.3 step 6)."""

    ordered_query: dict[str, Any] = {}
    if query:
        for key in sorted(query, key=str):
            ordered_query[str(key)] = query[key]
    payload = {
        "operation_id": operation_id,
        "method": str(method).upper(),
        "resolved_path": resolved_path,
        "query": ordered_query,
        "body": dict(body) if body is not None else {},
        "tenant": tenant,
        "version": version,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdempotencyKey:
    operation_id: str
    value: str

    def __post_init__(self) -> None:
        match = _KEY_PATTERN.match(str(self.value))
        if match is None:
            raise ContractViolation(
                "idempotency_key_invalid",
                detail={"format": IDEMPOTENCY_KEY_FORMAT},
            )

    @classmethod
    def issue(cls, operation_id: str) -> "IdempotencyKey":
        return cls(
            operation_id=str(operation_id),
            value="gxo_" + operation_short(operation_id) + "-" + secrets.token_hex(16),
        )

    @classmethod
    def parse(cls, value: str) -> "IdempotencyKey":
        if not isinstance(value, str):
            raise ContractViolation(
                "idempotency_key_invalid",
                detail={"format": IDEMPOTENCY_KEY_FORMAT},
            )
        match = _KEY_PATTERN.match(value)
        if match is None:
            raise ContractViolation(
                "idempotency_key_invalid",
                detail={"format": IDEMPOTENCY_KEY_FORMAT},
            )
        return cls(operation_id=match.group(1), value=value)

    def __str__(self) -> str:
        return self.value


class IdempotencyLedger:
    """Remembers key -> fingerprint and refuses reuse with a different intent.

    Bounded so a long-lived process cannot grow without limit; the oldest entry
    is evicted first.
    """

    def __init__(self, *, max_entries: int = 4096) -> None:
        if int(max_entries) < 1:
            raise ContractViolation("ledger_size_invalid")
        self._entries: dict[str, str] = {}
        self._max_entries = int(max_entries)

    def lookup(self, key: str) -> str | None:
        return self._entries.get(str(key))

    def record(self, key: str, fingerprint: str) -> None:
        text = str(key)
        seen = self._entries.get(text)
        if seen is not None and seen != fingerprint:
            raise ContractViolation(
                "idempotency_key_reuse", detail={"key": text}
            )
        if seen is None and len(self._entries) >= self._max_entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[text] = fingerprint

    def __len__(self) -> int:
        return len(self._entries)
