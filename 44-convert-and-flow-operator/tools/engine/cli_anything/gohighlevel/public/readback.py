"""Mandatory read-back / reconciliation plans.

Frozen by the GHL modernization contract ledger, 2026-10-18 (GU-004 sections 1.3 step 8
and 2.4). Operation scope and Version come from the official operation page
https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/.

A write is never fire-and-forget: the API requires a ``ReadbackSpec`` for every
write.  The registry may be sparse per operation; a caller-supplied spec stands
in until a frozen plan lands.  ``ReadbackResult.result`` is never defaulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .errors import ContractViolation


class ReadbackStatus(str, Enum):
    verified = "verified"
    mismatch = "mismatch"
    absent = "absent"
    unreadable = "unreadable"


@dataclass(frozen=True)
class ReadbackSpec:
    """Where and how to prove that a write landed."""

    operation_id: str
    target_params: Mapping[str, str] | None = None
    query: Mapping[str, Any] | None = None
    expect: Mapping[str, Any] | None = None
    description: str | None = None
    #: Opt-in: also match ``expect`` one level into a NAMED collection envelope
    #: (GHL's ``{"conversations":[…]}`` / ``{"messages":{…}}``). Default False
    #: keeps every existing plan's shallow semantics unchanged.
    scan_nested: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ContractViolation("readback_operation_missing")


@dataclass(frozen=True)
class ReadbackResult:
    result: ReadbackStatus
    operation_id: str | None
    attempt: int
    detail: Mapping[str, Any]
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", ReadbackStatus(self.result))
        if not isinstance(self.attempt, int) or self.attempt < 1:
            raise ContractViolation("readback_attempt_invalid")
        if not isinstance(self.detail, Mapping):
            raise ContractViolation("readback_detail_invalid")

    @property
    def verified(self) -> bool:
        return self.result is ReadbackStatus.verified


class ReadbackRegistry:
    """operation_id -> one or more frozen plans."""

    def __init__(
        self,
        plans: Mapping[str, "ReadbackSpec | Sequence[ReadbackSpec]"] | None = None,
    ) -> None:
        self._plans: dict[str, tuple[ReadbackSpec, ...]] = {}
        for operation_id, value in dict(plans or {}).items():
            entries = value if isinstance(value, (list, tuple)) else (value,)
            for spec in entries:
                self.register(spec, operation_id=str(operation_id))

    def register(
        self, spec: ReadbackSpec, *, operation_id: str | None = None
    ) -> None:
        if not isinstance(spec, ReadbackSpec):
            raise ContractViolation("readback_invalid")
        key = str(operation_id or spec.operation_id)
        existing = self._plans.get(key, ())
        self._plans[key] = existing + (spec,)

    def get(self, operation_id: str) -> ReadbackSpec | None:
        entries = self._plans.get(str(operation_id))
        if not entries:
            return None
        return entries[0]

    def all(self, operation_id: str) -> tuple[ReadbackSpec, ...]:
        return self._plans.get(str(operation_id), ())

    def require(self, operation_id: str) -> ReadbackSpec:
        spec = self.get(operation_id)
        if spec is None:
            raise ContractViolation(
                "readback_required", detail={"operation_id": str(operation_id)}
            )
        return spec

    def __contains__(self, operation_id: object) -> bool:
        return str(operation_id) in self._plans

    def __len__(self) -> int:
        return len(self._plans)


# Frozen registry.  Plans land per operation family; an empty plan list is
# legal, but a write still cannot run without a spec.
READBACKS = ReadbackRegistry()


def evaluate_readback(
    spec: ReadbackSpec,
    *,
    http_status: int | None,
    parsed_body: Any,
    transport_error: str = "none",
) -> ReadbackStatus:
    """Judge one read-back response without ever defaulting the result."""

    if transport_error and transport_error != "none":
        return ReadbackStatus.unreadable
    if http_status is None:
        return ReadbackStatus.unreadable
    if http_status in (401, 403):
        return ReadbackStatus.unreadable
    if http_status == 404:
        return ReadbackStatus.absent
    if not (200 <= http_status < 300):
        return ReadbackStatus.unreadable
    if parsed_body is None:
        return ReadbackStatus.unreadable
    if not spec.expect:
        return ReadbackStatus.verified
    return (
        ReadbackStatus.mismatch
        if _mismatch(spec.expect, parsed_body, scan_nested=spec.scan_nested)
        else ReadbackStatus.verified
    )


def _mismatch(expect: Mapping[str, Any], parsed: Any, *,
              scan_nested: bool = False) -> bool:
    # ponytail: shallow subset match at root and one level under "data"; add a
    # path expression when a real plan needs deeper nesting. ``scan_nested`` is
    # the documented upgrade for GHL conversation envelopes, whose collections
    # live under a NAMED key ({"conversations":[…]} / {"messages":{…}}).
    for key, wanted in expect.items():
        found, value = _lookup(parsed, str(key), scan_nested=scan_nested)
        if not found or value != wanted:
            return True
    return False


def _lookup(parsed: Any, key: str, *, scan_nested: bool = False) -> tuple[bool, Any]:
    if isinstance(parsed, Mapping):
        if key in parsed:
            return True, parsed[key]
        data = parsed.get("data")
        if isinstance(data, Mapping) and key in data:
            return True, data[key]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, Mapping) and key in item:
                    return True, item[key]
        if scan_nested:
            for value in parsed.values():
                if isinstance(value, Mapping):
                    if key in value:
                        return True, value[key]
                    inner = value.get("messages")
                    if isinstance(inner, list):
                        for item in inner:
                            if isinstance(item, Mapping) and key in item:
                                return True, item[key]
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, Mapping) and key in item:
                            return True, item[key]
    return False, None