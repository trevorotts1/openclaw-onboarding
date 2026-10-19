"""Capability descriptor and default-deny gate.

Frozen by the GHL modernization contract ledger, 2026-10-18 (GU-004 sections 3.1-3.3).
Every capability row covers one operation whose scope and Version are documented at
https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/.

Every operation is disabled at the freeze.  ``enabled=True`` together with a
non-null ``activation_blocked`` is impossible by construction.  Enablement is
per ``(operation_id, tenant)``: a gate instance is bound to one tenant, and an
enabled capability cannot be stored in an unbound gate.

The gate stays in memory; ``load_capability_record`` is the only file reader.
It loads the versioned, checked-in record for one tenant and fails closed to
default-deny on any defect.  A record may authorize a dispatch on offline
evidence (``provisional``) while ``activation`` stays ``UNVERIFIED``: enabled
by record is never a claim that the tenant returned a 200.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from .errors import CapabilityDisabled, ContractViolation

#: A record may authorize a dispatch, but only a real 200 observed for the
#: target tenant proves tenant capability.  ``UNVERIFIED`` is the honest state
#: for every operation the 403 has not yet cleared.
ACTIVATION_UNVERIFIED = "UNVERIFIED"
ACTIVATION_VERIFIED = "VERIFIED"
ACTIVATIONS: frozenset[str] = frozenset(
    {ACTIVATION_UNVERIFIED, ACTIVATION_VERIFIED}
)

#: The checked-in capability record is versioned so an older reader refuses a
#: newer shape instead of silently accepting it.
CAPABILITY_RECORD_VERSION = 1
CAPABILITY_RECORD_ENV = "GHL_PUBLIC_CAPABILITIES_FILE"
CAPABILITY_RECORD_NAME = ("state", "ghl-public-capabilities.json")
#: ``.../tools/engine/cli_anything/gohighlevel/public/capability.py`` -> engine
_ENGINE_ROOT = Path(__file__).resolve().parents[3]


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
    #: Tenant-verification state.  ``UNVERIFIED`` means a record authorized the
    #: dispatch on offline evidence only; no real 200 has been observed for the
    #: target tenant.  ``VERIFIED`` demands ``read_verified``.
    activation: str = ACTIVATION_UNVERIFIED
    #: Explicit record declaration that enablement rests on offline evidence
    #: (contract, adapter, tests) and the tenant read is still unproven.  It can
    #: never be combined with ``read_verified``, a canary, or ``VERIFIED``.
    provisional: bool = False

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
        if self.activation not in ACTIVATIONS:
            raise ContractViolation(
                "capability_activation_invalid",
                operation_id=self.operation_id,
            )
        if self.activation == ACTIVATION_VERIFIED and not self.read_verified:
            raise ContractViolation(
                "capability_verified_without_read",
                operation_id=self.operation_id,
            )
        if self.provisional and self.read_verified:
            raise ContractViolation(
                "provisional_with_read_verified",
                operation_id=self.operation_id,
            )
        if self.provisional and self.activation != ACTIVATION_UNVERIFIED:
            raise ContractViolation(
                "provisional_with_verified_activation",
                operation_id=self.operation_id,
            )
        if self.provisional and self.canary_verified:
            raise ContractViolation(
                "provisional_with_canary",
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
        """Rules 2-3 evidence minus the write-only canary flag.

        ``read_verified`` remains the tenant proof.  A record may instead
        declare ``provisional``: offline evidence is complete, the tenant read
        is explicitly unproven, and activation stays ``UNVERIFIED``.  Default
        deny is untouched: an enabled row still needs every offline flag.
        """

        tenant_read = self.read_verified or (
            self.provisional and self.activation == ACTIVATION_UNVERIFIED
        )
        return (
            self.contract_verified
            and self.adapter_built
            and self.offline_tests_passed
            and tenant_read
        )

    def tenant_verified(self) -> bool:
        return self.activation == ACTIVATION_VERIFIED

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


# ---------------------------------------------------------------------------
# checked-in capability record
# ---------------------------------------------------------------------------

def capability_record_path(
    path: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the record: explicit path, then env, then the engine state file."""

    if path is not None:
        return Path(path).expanduser()
    env = (environ if environ is not None else os.environ).get(
        CAPABILITY_RECORD_ENV
    )
    if env:
        return Path(str(env)).expanduser()
    return _ENGINE_ROOT.joinpath(*CAPABILITY_RECORD_NAME)


def load_capability_record(
    *,
    tenant: str,
    path: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> CapabilityGate:
    """Load the checked-in record into a tenant-bound gate.

    Fail-closed in every direction: a missing file, an unreadable or malformed
    document, a different ``record_version``, a tenant mismatch, an empty
    capability table, or one invalid row all yield an empty gate (default
    deny).  A record can therefore never widen the gate by accident.
    """

    gate = CapabilityGate(tenant=tenant)
    if not isinstance(tenant, str) or not tenant.strip():
        return gate
    record_path = capability_record_path(path, environ=environ)
    try:
        with open(record_path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, TypeError, ValueError):
        return gate
    if not isinstance(document, Mapping):
        return gate
    if document.get("record_version") != CAPABILITY_RECORD_VERSION:
        return gate
    if str(document.get("tenant", "")) != tenant:
        return gate
    rows = document.get("capabilities")
    if not isinstance(rows, Mapping) or not rows:
        return gate

    capabilities: dict[str, Capability] = {}
    for operation_id, row in rows.items():
        if not isinstance(operation_id, str) or not isinstance(row, Mapping):
            return CapabilityGate(tenant=tenant)
        try:
            capabilities[operation_id] = Capability(
                operation_id=operation_id, **dict(row)
            )
        except (ContractViolation, TypeError):
            # One bad row fails the whole record: never a partially wider gate.
            return CapabilityGate(tenant=tenant)
    return CapabilityGate(capabilities, tenant=tenant)
