"""Capability descriptor and default-deny gate.

Frozen by evidence/W01/GU-004-CONTRACT-FREEZE.md sections 3.1-3.3.

Every operation is disabled at the freeze.  ``enabled=True`` together with a
non-null ``activation_blocked`` is impossible by construction.  Enablement is
per ``(operation_id, tenant)``: a gate instance is bound to one tenant, and an
enabled capability cannot be stored in an unbound gate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .errors import CapabilityDisabled, ContractViolation


@dataclass(frozen=True)
class ActivationBlock:
    reason: str
    owner: str
    unblock: str

    def __post_init__(self) -> None:
        for field in ("reason", "owner", "unblock"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "activation_block_incomplete", detail={"field": field}
                )

    def as_evidence(self) -> dict[str, str]:
        return {
            "reason": self.reason,
            "owner": self.owner,
            "unblock": self.unblock,
        }


@dataclass(frozen=True)
class Capability:
    operation_id: str
    contract_verified: bool = False
    adapter_built: bool = False
    offline_tests_passed: bool = False
    read_verified: bool = False
    canary_verified: bool = False
    enabled: bool = False
    activation_blocked: ActivationBlock | None = None
    #: MAJOR 4: the tenant this record is authorized for.  ``None`` records no
    #: assertion; a non-null value must equal the call tenant (GU-004 3.3).
    tenant: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ContractViolation("capability_operation_missing")
        if self.tenant is not None and (
            not isinstance(self.tenant, str) or not self.tenant.strip()
        ):
            raise ContractViolation(
                "capability_tenant_invalid",
                operation_id=self.operation_id,
            )
        if self.enabled and self.activation_blocked is not None:
            raise ContractViolation(
                "enabled_with_activation_block",
                operation_id=self.operation_id,
            )
        if self.enabled and not self.evidence_ok():
            raise ContractViolation(
                "enabled_without_evidence",
                operation_id=self.operation_id,
            )

    def evidence_ok(self) -> bool:
        """Rules 2-3 evidence minus the write-only canary flag."""

        return (
            self.contract_verified
            and self.adapter_built
            and self.offline_tests_passed
            and self.read_verified
        )

    def write_ready(self) -> bool:
        return self.evidence_ok() and self.canary_verified


DEFAULT_BLOCK = ActivationBlock(
    reason="capability record absent for this operation; the gate is default-deny",
    owner="operator (account authority) + W04",
    unblock=(
        "recorded capability evidence for (operation_id, tenant) in "
        "state/ghl-public-capabilities.json"
    ),
)


class CapabilityGate:
    """Default-deny gate.  Unbound gates may hold no enabled capability.

    A gate is bound to one tenant, so a row that carries its own tenant is
    authorized for that tenant and for no other (GU-004 section 3.3).
    """

    def __init__(
        self,
        capabilities: Mapping[str, Capability] | None = None,
        *,
        tenant: str | None = None,
    ) -> None:
        self._tenant = tenant
        self._capabilities: dict[str, Capability] = {}
        for operation_id, capability in dict(capabilities or {}).items():
            self.put(capability, operation_id=str(operation_id))

    @property
    def tenant(self) -> str | None:
        return self._tenant

    def get(self, operation_id: str) -> Capability:
        capability = self._capabilities.get(str(operation_id))
        if capability is None:
            return Capability(
                operation_id=str(operation_id),
                enabled=False,
                activation_blocked=DEFAULT_BLOCK,
            )
        if not capability.enabled and capability.activation_blocked is None:
            # A disabled row must still explain itself: silence is not an
            # outcome.
            return replace(capability, activation_blocked=DEFAULT_BLOCK)
        return capability

    def require(self, operation_id: str) -> Capability:
        capability = self.get(operation_id)
        if not capability.enabled:
            raise CapabilityDisabled(
                operation_id=str(operation_id),
                detail=(
                    capability.activation_blocked.as_evidence()
                    if capability.activation_blocked
                    else DEFAULT_BLOCK.as_evidence()
                ),
            )
        return capability

    def put(
        self,
        capability: Capability,
        *,
        operation_id: str | None = None,
        write: bool = False,
    ) -> None:
        if not isinstance(capability, Capability):
            raise ContractViolation("capability_invalid")
        if capability.enabled and self._tenant is None:
            raise ContractViolation(
                "capability_requires_tenant",
                operation_id=capability.operation_id,
            )
        # BLOCKER 3: ``enable()`` already demands the canary for a write; a
        # row registered directly as write-capable must clear the same rule,
        # or a row without canary evidence would sit in the gate as a write
        # candidate.  (Evidence itself is already pinned by the constructor:
        # ``enabled`` without evidence cannot be built.)
        if write and not capability.canary_verified:
            raise ContractViolation(
                "capability_canary_missing",
                operation_id=capability.operation_id,
            )
        self._capabilities[str(operation_id or capability.operation_id)] = capability

    def enable(self, capability: Capability, *, write: bool) -> Capability:
        """Record enablement only when the frozen evidence rules hold."""

        if not isinstance(capability, Capability):
            raise ContractViolation("capability_invalid")
        if capability.activation_blocked is not None:
            raise ContractViolation(
                "capability_blocked", operation_id=capability.operation_id
            )
        if not capability.evidence_ok():
            raise ContractViolation(
                "capability_evidence_insufficient",
                operation_id=capability.operation_id,
            )
        if write and not capability.canary_verified:
            raise ContractViolation(
                "capability_canary_missing", operation_id=capability.operation_id
            )
        if self._tenant is None:
            raise ContractViolation(
                "capability_requires_tenant", operation_id=capability.operation_id
            )
        enabled = replace(capability, enabled=True, activation_blocked=None)
        self._capabilities[capability.operation_id] = enabled
        return enabled

    def __len__(self) -> int:
        return len(self._capabilities)
