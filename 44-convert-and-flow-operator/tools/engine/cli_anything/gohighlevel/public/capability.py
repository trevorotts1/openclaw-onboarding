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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

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
        """Frozen GU-004 section 3.2 rule 2, taken literally.

        A read operation is enabled only when contract_verified AND
        adapter_built AND offline_tests_passed AND read_verified.  There is no
        offline-only escape: until a real 200 is observed for the tenant, the
        operation stays denied.  ``provisional`` remains a receipt field only
        and no longer admits anything.
        """

        return (
            self.contract_verified
            and self.adapter_built
            and self.offline_tests_passed
            and self.read_verified
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


# ---------------------------------------------------------------------------
# Additive capability record v2 (Document 1 section 5.2)
#
# v1 is a single gate row per (operation_id, tenant).  v2 keeps the SAME
# authorization surface but splits the facts v1 collapsed: availability,
# scope/authorization, read evidence, write-canary evidence and functional
# readiness are independent.  A v1 record is TRANSLATED into v2 without ever
# widening a grant: an unproven dimension stays unknown, never "available".
# ---------------------------------------------------------------------------

CAPABILITY_RECORD_VERSION_V2 = 2
SUPPORTED_RECORD_VERSIONS: tuple[int, ...] = (CAPABILITY_RECORD_VERSION, CAPABILITY_RECORD_VERSION_V2)

AVAILABILITY_STATES: frozenset[str] = frozenset(
    {"unknown", "available", "beta_not_enabled", "unavailable"}
)
SCOPE_STATES: frozenset[str] = frozenset(
    {"unverified", "granted", "missing_scope", "wrong_role", "denied"}
)
PROBE_STATES: frozenset[str] = frozenset({"not_run", "passed", "failed", "inconclusive"})
#: Which fallback a rejected public operation may use.  The policy never
#: overrides an account-permission denial: that is not an availability gap.
FALLBACK_POLICIES: frozenset[str] = frozenset(
    {
        "authorized_private_then_managed_browser",
        "authorized_private",
        "managed_browser",
        "none",
    }
)
DEFAULT_FALLBACK_POLICY = "authorized_private_then_managed_browser"
#: The beta flag is per sub-account and is the ONLY source of this decision.
WORKFLOW_BETA_ERROR_CODE = "WORKFLOW_API_NOT_ENABLED_FOR_LOCATION"

def _probe_not_run() -> dict[str, Any]:
    return {"state": "not_run", "receipt_id": None}


def _probe_state(value: object, field: str, operation_id: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractViolation(
            "capability_probe_invalid",
            operation_id=operation_id,
            detail={"field": field},
        )
    state = str(value.get("state", ""))
    if state not in PROBE_STATES:
        raise ContractViolation(
            "capability_probe_invalid",
            operation_id=operation_id,
            detail={"field": field, "state": state},
        )
    return {"state": state, "receipt_id": value.get("receipt_id")}


@dataclass(frozen=True)
class CapabilityRecordV2:
    """Document 1 section 5.2, with the fields section 5.2 adds by prose.

    ``enabled`` means "the record authorizes a dispatch for a READ of this
    operation".  It never implies the tenant returned a 200, and it never
    admits a write: ``write_admitted`` additionally demands canary evidence.
    """

    location_id: str
    operation_id: str
    contract_revision: str
    record_version: int = CAPABILITY_RECORD_VERSION_V2
    credential_ref: str | None = None
    credential_fingerprint: str | None = None
    documented: bool = False
    adapter_built: bool = False
    offline_tests_passed: bool = False
    availability: str = "unknown"
    scope_state: str = "unverified"
    read_probe: Mapping[str, Any] = field(default_factory=_probe_not_run)
    write_canary: Mapping[str, Any] = field(default_factory=_probe_not_run)
    enabled: bool = False
    checked_at: str | None = None
    expires_at: str | None = None
    fallback_policy: str = DEFAULT_FALLBACK_POLICY
    # Added by section 5.2 prose: principal/effective-grant binding and the
    # request media type this row actually carries.
    principal: str | None = None
    effective_grant_fingerprint: str | None = None
    request_media_type: str = "application/json"
    invalidation_reason: str | None = None

    def __post_init__(self) -> None:
        for field in ("location_id", "operation_id", "contract_revision"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "capability_v2_incomplete",
                    operation_id=str(self.operation_id),
                    detail={"field": field},
                )
        if self.record_version != CAPABILITY_RECORD_VERSION_V2:
            raise ContractViolation(
                "capability_v2_version_invalid", operation_id=self.operation_id
            )
        if self.availability not in AVAILABILITY_STATES:
            raise ContractViolation(
                "capability_v2_availability_invalid", operation_id=self.operation_id
            )
        if self.scope_state not in SCOPE_STATES:
            raise ContractViolation(
                "capability_v2_scope_state_invalid", operation_id=self.operation_id
            )
        if self.fallback_policy not in FALLBACK_POLICIES:
            raise ContractViolation(
                "capability_v2_fallback_invalid", operation_id=self.operation_id
            )
        object.__setattr__(
            self, "read_probe", _probe_state(self.read_probe, "read_probe", self.operation_id)
        )
        object.__setattr__(
            self,
            "write_canary",
            _probe_state(self.write_canary, "write_canary", self.operation_id),
        )
        if self.enabled:
            # Enable-by-record still demands the frozen offline evidence AND a
            # contradicting availability/scope fact must be resolved first.
            if not (self.documented and self.adapter_built and self.offline_tests_passed):
                raise ContractViolation(
                    "capability_v2_enabled_without_evidence",
                    operation_id=self.operation_id,
                )
            if self.availability in ("beta_not_enabled", "unavailable"):
                raise ContractViolation(
                    "capability_v2_enabled_when_unavailable",
                    operation_id=self.operation_id,
                    detail={"availability": self.availability},
                )
            if self.scope_state in ("missing_scope", "wrong_role", "denied"):
                raise ContractViolation(
                    "capability_v2_enabled_when_denied",
                    operation_id=self.operation_id,
                    detail={"scope_state": self.scope_state},
                )
            if self.invalidation_reason:
                raise ContractViolation(
                    "capability_v2_enabled_while_invalidated",
                    operation_id=self.operation_id,
                    detail={"invalidation_reason": self.invalidation_reason},
                )

    # -- derived facts -----------------------------------------------------

    @property
    def read_proven(self) -> bool:
        """Only an observed probe proves the read.  A record is never proof."""

        return self.read_probe.get("state") == "passed"

    @property
    def canary_proven(self) -> bool:
        return self.write_canary.get("state") == "passed"

    def read_admitted(self) -> bool:
        """A read needs enablement AND observed read evidence (IG-AUTH-03)."""

        return bool(self.enabled and self.read_proven)

    def write_admitted(self) -> bool:
        """A successful read NEVER enables create/update/publish (IG-AUTH-03)."""

        return bool(self.read_admitted() and self.canary_proven)

    def binding(self) -> tuple[str | None, str | None, str]:
        """(credential fingerprint, grant fingerprint, contract revision)."""

        return (
            self.credential_fingerprint,
            self.effective_grant_fingerprint,
            self.contract_revision,
        )

    def with_canary(self, *, state: str, receipt_id: str | None) -> "CapabilityRecordV2":
        """Record canary evidence.  Evidence only: enablement is separate."""

        return replace(
            self,
            write_canary=_probe_state({"state": state, "receipt_id": receipt_id}, "write_canary", self.operation_id),
        )

    def with_read_probe(self, *, state: str, receipt_id: str | None) -> "CapabilityRecordV2":
        return replace(
            self,
            read_probe=_probe_state({"state": state, "receipt_id": receipt_id}, "read_probe", self.operation_id),
        )

    def invalidated(self, reason: str) -> "CapabilityRecordV2":
        """A rotation/schema change invalidates its OWN evidence, not the world."""

        return replace(self, enabled=False, invalidation_reason=str(reason))

    def as_document(self) -> dict[str, Any]:
        """Exactly the section 5.2 shape (plus the additive binding fields)."""

        return {
            "record_version": int(self.record_version),
            "location_id": self.location_id,
            "operation_id": self.operation_id,
            "contract_revision": self.contract_revision,
            "credential_ref": self.credential_ref,
            "credential_fingerprint": self.credential_fingerprint,
            "documented": bool(self.documented),
            "adapter_built": bool(self.adapter_built),
            "offline_tests_passed": bool(self.offline_tests_passed),
            "availability": self.availability,
            "scope_state": self.scope_state,
            "read_probe": dict(self.read_probe),
            "write_canary": dict(self.write_canary),
            "enabled": bool(self.enabled),
            "checked_at": self.checked_at,
            "expires_at": self.expires_at,
            "fallback_policy": self.fallback_policy,
            "principal": self.principal,
            "effective_grant_fingerprint": self.effective_grant_fingerprint,
            "request_media_type": self.request_media_type,
            "invalidation_reason": self.invalidation_reason,
        }

    def to_gate_capability(self, *, tenant: str | None = None) -> Capability:
        """Translate to the v1 gate row WITHOUT widening it.

        The gate only ever admits a read whose evidence is complete, and it
        demands canary evidence for a write.  ``availability``/``scope_state``
        stay visible in the v2 record; the gate never reinterprets them.
        """

        bound = tenant if tenant is not None else self.location_id
        return Capability(
            operation_id=self.operation_id,
            contract_verified=bool(self.documented and self.adapter_built),
            adapter_built=bool(self.adapter_built),
            offline_tests_passed=bool(self.offline_tests_passed),
            read_verified=self.read_proven,
            canary_verified=self.canary_proven,
            enabled=bool(self.enabled and self.read_proven),
            activation=(
                ACTIVATION_VERIFIED if self.read_proven else ACTIVATION_UNVERIFIED
            ),
            tenant=bound,
            activation_blocked=None,
        )


def capability_record_v2_from_v1(
    operation_id: str,
    row: Mapping[str, Any],
    *,
    location_id: str,
    contract_revision: str,
) -> CapabilityRecordV2:
    """Translate one v1 row into v2 without inventing a single fact.

    * ``read_verified``/``canary_verified`` become probe states;
    * ``availability`` stays ``unknown``: v1 never measured it;
    * ``scope_state`` stays ``unverified``: v1 never measured it;
    * ``enabled`` is kept only when v1's own four-part evidence holds and no
      activation block was recorded.  A translation can only ever narrow.
    """

    raw = dict(row)
    blocked = raw.get("activation_blocked")
    if isinstance(blocked, Mapping):
        # A checked-in record may carry the block as a plain object.
        raw["activation_blocked"] = ActivationBlock(**dict(blocked))
    try:
        v1 = Capability(operation_id=str(operation_id), **raw)
    except (ContractViolation, TypeError):
        # A v1 row that cannot even be constructed never granted anything.
        # Translate it as a DISABLED v2 row instead of dropping the record:
        # monotone in the only direction that matters (no widening).
        return CapabilityRecordV2(
            location_id=str(location_id),
            operation_id=str(operation_id),
            contract_revision=str(contract_revision),
            documented=bool(raw.get("contract_verified")),
            adapter_built=bool(raw.get("adapter_built")),
            offline_tests_passed=bool(raw.get("offline_tests_passed")),
            read_probe={
                "state": "passed" if raw.get("read_verified") is True else "not_run",
                "receipt_id": None,
            },
            write_canary={
                "state": "passed" if raw.get("canary_verified") is True else "not_run",
                "receipt_id": None,
            },
            enabled=False,
            invalidation_reason="v1_row_inconsistent",
        )
    enabled = bool(
        v1.enabled
        and v1.evidence_ok()
        and v1.activation_blocked is None
        and v1.activation == ACTIVATION_VERIFIED
    )
    return CapabilityRecordV2(
        location_id=str(location_id),
        operation_id=str(operation_id),
        contract_revision=str(contract_revision),
        credential_ref=None,
        credential_fingerprint=None,
        documented=bool(v1.contract_verified),
        adapter_built=bool(v1.adapter_built),
        offline_tests_passed=bool(v1.offline_tests_passed),
        availability="unknown",
        scope_state="unverified",
        read_probe={
            "state": "passed" if v1.read_verified else "not_run",
            "receipt_id": None,
        },
        write_canary={
            "state": "passed" if v1.canary_verified else "not_run",
            "receipt_id": None,
        },
        enabled=enabled,
        fallback_policy=DEFAULT_FALLBACK_POLICY,
        request_media_type="application/json",
    )


def translate_capability_document(
    document: Mapping[str, Any],
    *,
    tenant: str,
    contract_revision: str | None = None,
) -> dict[str, CapabilityRecordV2]:
    """Translate a whole v1 document to v2.  Never widens; never guesses."""

    rows = document.get("capabilities")
    if not isinstance(rows, Mapping):
        return {}
    revision = str(contract_revision or document.get("contract_revision") or "unknown")
    translated: dict[str, CapabilityRecordV2] = {}
    for operation_id, row in rows.items():
        if not isinstance(operation_id, str) or not isinstance(row, Mapping):
            return {}
        translated[operation_id] = capability_record_v2_from_v1(
            operation_id, row, location_id=tenant, contract_revision=revision
        )
    return translated


def load_capability_records_v2(
    *,
    tenant: str,
    path: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    contract_revision: str | None = None,
) -> dict[str, CapabilityRecordV2]:
    """Load a checked-in record as typed v2 rows (v1 or v2 on disk).

    Same fail-closed posture as ``load_capability_record``: one bad row empties
    the whole result rather than widening it.
    """

    if not isinstance(tenant, str) or not tenant.strip():
        return {}
    record_path = capability_record_path(path, environ=environ)
    try:
        with open(record_path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(document, Mapping):
        return {}
    version = document.get("record_version")
    if version not in SUPPORTED_RECORD_VERSIONS:
        return {}
    if str(document.get("tenant", document.get("location_id", ""))) != tenant:
        return {}
    rows = document.get("capabilities")
    if not isinstance(rows, Mapping) or not rows:
        return {}
    if version == CAPABILITY_RECORD_VERSION:
        return translate_capability_document(
            document,
            tenant=tenant,
            contract_revision=contract_revision
            or str(document.get("contract_revision") or "v1-record"),
        )
    revision = str(contract_revision or document.get("contract_revision") or "unknown")
    records: dict[str, CapabilityRecordV2] = {}
    for operation_id, row in rows.items():
        if not isinstance(operation_id, str) or not isinstance(row, Mapping):
            return {}
        payload = dict(row)
        payload.setdefault("location_id", tenant)
        payload.setdefault("operation_id", operation_id)
        payload.setdefault("contract_revision", revision)
        try:
            records[operation_id] = CapabilityRecordV2(**payload)
        except (ContractViolation, TypeError):
            return {}
    return records


# ---------------------------------------------------------------------------
# Configurable bounded capability cache
# ---------------------------------------------------------------------------

class CapabilityCache:
    """Bounded, expiring, binding-aware cache for capability evidence.

    An entry is usable only for the exact (credential fingerprint, effective
    grant fingerprint, contract revision) that produced it: a token rotation,
    a grant change or a docs/schema hash change invalidates its own evidence
    and nothing else.  The cache is an optimization; a miss is always safe.
    """

    def __init__(self, *, ttl_s: float = 300.0, max_entries: int = 512) -> None:
        if float(ttl_s) < 0:
            raise ContractViolation("capability_cache_ttl_invalid")
        if int(max_entries) < 1:
            raise ContractViolation("capability_cache_size_invalid")
        self._ttl_s = float(ttl_s)
        self._max_entries = int(max_entries)
        self._entries: dict[tuple[str, str], tuple[CapabilityRecordV2, float]] = {}

    @property
    def ttl_s(self) -> float:
        return self._ttl_s

    def get(
        self,
        tenant: str,
        operation_id: str,
        *,
        now: float,
        credential_fingerprint: str | None = None,
        grant_fingerprint: str | None = None,
        contract_revision: str | None = None,
    ) -> CapabilityRecordV2 | None:
        key = (str(tenant), str(operation_id))
        entry = self._entries.get(key)
        if entry is None:
            return None
        record, stored_at = entry
        if now - stored_at > self._ttl_s or record.invalidation_reason:
            del self._entries[key]
            return None
        expected = self._binding(
            credential_fingerprint, grant_fingerprint, contract_revision
        )
        if expected is not None and record.binding() != expected:
            # Rotation/schema change: this entry is evidence for another binding.
            del self._entries[key]
            return None
        return record

    def put(self, record: CapabilityRecordV2, *, now: float) -> None:
        if not isinstance(record, CapabilityRecordV2):
            raise ContractViolation("capability_cache_record_invalid")
        key = (record.location_id, record.operation_id)
        if key not in self._entries and len(self._entries) >= self._max_entries:
            oldest_key = min(self._entries, key=lambda k: self._entries[k][1])
            del self._entries[oldest_key]
        self._entries[key] = (record, float(now))

    def invalidate(self, *, tenant: str, operation_id: str, reason: str) -> None:
        """Invalidate ONE entry with a reason; never a blanket flush."""

        key = (str(tenant), str(operation_id))
        entry = self._entries.get(key)
        if entry is None:
            return
        record, stored_at = entry
        self._entries[key] = (record.invalidated(reason), stored_at)

    def invalidate_credential(self, *, tenant: str, credential_fingerprint: str) -> int:
        """A rotated credential drops every entry bound to it, for that tenant."""

        dropped = 0
        for key in list(self._entries):
            record, _ = self._entries[key]
            if (
                key[0] == str(tenant)
                and record.credential_fingerprint == credential_fingerprint
            ):
                del self._entries[key]
                dropped += 1
        return dropped

    def invalidate_contract(self, *, tenant: str, contract_revision: str) -> int:
        """A schema/docs hash change drops only rows pinned to that revision."""

        dropped = 0
        for key in list(self._entries):
            record, _ = self._entries[key]
            if key[0] == str(tenant) and record.contract_revision == str(contract_revision):
                del self._entries[key]
                dropped += 1
        return dropped

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _binding(
        credential_fingerprint: str | None,
        grant_fingerprint: str | None,
        contract_revision: str | None,
    ) -> tuple[str | None, str | None, str] | None:
        if credential_fingerprint is None and grant_fingerprint is None and contract_revision is None:
            return None
        return (
            credential_fingerprint,
            grant_fingerprint,
            str(contract_revision if contract_revision is not None else "unknown"),
        )


# ---------------------------------------------------------------------------
# Exact failure classification (Document 1 section 5.4)
#
# A generic 403 is never a fallback bypass (IG-ROUTE-03), and a beta flag is
# never a bad token.  These classes are disjoint and the order of the checks is
# the contract: provider code first, then credential, then scope/role, then a
# bare forbidden.
# ---------------------------------------------------------------------------

FAILURE_CLASSES: frozenset[str] = frozenset(
    {
        "ok",
        "beta_not_enabled",
        "unauthorized",
        "missing_scope",
        "wrong_role",
        "forbidden",
        "not_found",
        "conflict",
        "validation_error",
        "rate_limited",
        "unknown_outcome",
        "unavailable",
    }
)

#: Only these classes permit an FALLBACK route.  A permission denial never does.
FALLBACK_CLASSES: frozenset[str] = frozenset({"beta_not_enabled"})

_SCOPE_MARKERS = (
    "scope",
    "insufficient_scope",
    "missing scope",
    "not authorized for this scope",
)
_ROLE_MARKERS = ("role", "user type", "user_type", "permission denied for user")
_BETA_MARKERS = (WORKFLOW_BETA_ERROR_CODE, "not enabled for location")


@dataclass(frozen=True)
class FailureClassification:
    kind: str
    http_status: int | None
    provider_code: str | None
    retryable: bool
    fallback_allowed: bool
    detail: str

    def __post_init__(self) -> None:
        if self.kind not in FAILURE_CLASSES:
            raise ContractViolation(
                "failure_class_unknown", detail={"kind": str(self.kind)}
            )

    def as_evidence(self) -> dict[str, Any]:
        return {
            "classification": self.kind,
            "http_status": self.http_status,
            "provider_code": self.provider_code,
            "retryable": bool(self.retryable),
            "fallback_allowed": bool(self.fallback_allowed),
        }


def _provider_payload(body: bytes | str | Mapping[str, Any] | None) -> Mapping[str, Any]:
    if body is None:
        return {}
    if isinstance(body, Mapping):
        return dict(body)
    raw = body if isinstance(body, bytes) else str(body).encode("utf-8", "replace")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return {"message": raw.decode("utf-8", "replace")[:400]}
    return dict(parsed) if isinstance(parsed, Mapping) else {"message": str(parsed)[:400]}


def _provider_code(payload: Mapping[str, Any]) -> str | None:
    for key in ("code", "errorCode", "error_code", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            inner = value.get("code") or value.get("message")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def _searchable_text(payload: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("message", "msg", "error", "error_description", "detail", "code"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Mapping):
            parts.extend(str(v) for v in value.values() if isinstance(v, str))
    return " ".join(parts).lower()


def classify_failure(
    *,
    http_status: int | None,
    body: bytes | str | Mapping[str, Any] | None = None,
    transport_error: str = "none",
    write: bool = False,
) -> FailureClassification:
    """Classify one completed attempt.  Exact, disjoint, secret-free."""

    if transport_error and transport_error != "none":
        kind = "unknown_outcome" if write else "unavailable"
        return FailureClassification(
            kind=kind,
            http_status=None,
            provider_code=None,
            retryable=False,
            fallback_allowed=False,
            detail="transport_" + str(transport_error),
        )
    if http_status is None:
        kind = "unknown_outcome" if write else "unavailable"
        return FailureClassification(kind, None, None, False, False, "no_response")

    payload = _provider_payload(body)
    code = _provider_code(payload)
    text = _searchable_text(payload)
    if code and text and code.lower() not in text:
        text = text + " " + code.lower()

    if 200 <= http_status <= 299:
        return FailureClassification("ok", http_status, code, False, False, "2xx")
    if http_status == 401:
        return FailureClassification(
            "unauthorized", http_status, code, False, False,
            "credential expired, revoked or absent; never a beta flag",
        )
    if http_status == 403:
        if any(marker.lower() in text for marker in _BETA_MARKERS):
            return FailureClassification(
                "beta_not_enabled", http_status, code or WORKFLOW_BETA_ERROR_CODE,
                False,
                True,
                "per-location private-beta flag; select the authorized private fallback",
            )
        if any(marker in text for marker in _SCOPE_MARKERS):
            return FailureClassification(
                "missing_scope", http_status, code, False, False,
                "token lacks one operation scope; repair authorization",
            )
        if any(marker in text for marker in _ROLE_MARKERS):
            return FailureClassification(
                "wrong_role", http_status, code, False, False,
                "the authenticated user role cannot perform this operation",
            )
        return FailureClassification(
            "forbidden", http_status, code, False, False,
            "generic 403; never laundered into a browser/internal write",
        )
    if http_status == 404:
        return FailureClassification("not_found", http_status, code, False, False, "not_found")
    if http_status == 409:
        return FailureClassification("conflict", http_status, code, False, False, "conflict")
    if http_status in (400, 422):
        return FailureClassification("validation_error", http_status, code, False, False, "validation")
    if http_status == 429:
        return FailureClassification("rate_limited", http_status, code, True, False, "honor provider backoff")
    if 500 <= http_status <= 599:
        return FailureClassification(
            "unknown_outcome" if write else "unavailable",
            http_status, code, False, False, "upstream_error",
        )
    return FailureClassification(
        "unknown_outcome" if write else "unavailable",
        http_status, code, False, False, "unexpected_http_status",
    )


# ---------------------------------------------------------------------------
# WF01-CP01: resolve_capability + route decision
#
# This is the frozen interface other lanes consume.  It answers two questions
# and nothing else:
#   1. may this (tenant, operation, credential) run at all?
#   2. if so, on which ONE route?
# ---------------------------------------------------------------------------

ROUTES: frozenset[str] = frozenset(
    {
        "public_rest",
        "official_mcp",
        "private_fallback",
        "managed_browser",
        "reconcile_only",
        "dry_run",
        "none",
    }
)
DECISIONS: frozenset[str] = frozenset({"allow", "deny", "probe_required", "canary_required"})


@dataclass(frozen=True)
class CapabilityResolution:
    tenant: str
    operation_id: str
    decision: str
    reason: str
    route_class: str | None
    write: bool
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ContractViolation(
                "resolution_decision_invalid", operation_id=self.operation_id
            )

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


@dataclass(frozen=True)
class RouteDecision:
    tenant: str
    operation_id: str
    route: str
    reason: str
    write: bool
    must_reconcile: bool
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.route not in ROUTES:
            raise ContractViolation("route_invalid", operation_id=self.operation_id)


def resolve_capability(
    *,
    record: CapabilityRecordV2 | None,
    tenant: str,
    operation_id: str,
    write: bool = False,
    route_class: str | None = None,
    fallback_policy: str | None = None,
) -> CapabilityResolution:
    """Resolve ONE capability.  Default deny, and a read never admits a write."""

    if not isinstance(tenant, str) or not tenant.strip():
        raise ContractViolation("tenant_required", operation_id=str(operation_id))
    policy = str(fallback_policy or DEFAULT_FALLBACK_POLICY)
    if policy not in FALLBACK_POLICIES:
        raise ContractViolation("fallback_policy_invalid", operation_id=str(operation_id))
    if record is None:
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="deny",
            reason="capability_record_absent",
            route_class=route_class,
            write=bool(write),
            evidence={"policy": policy},
        )
    if record.operation_id != operation_id:
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="deny",
            reason="operation_mismatch",
            route_class=route_class,
            write=bool(write),
            evidence={"record_operation_id": record.operation_id},
        )
    if record.location_id != tenant:
        # IG-AUTH-01: a location/principal mismatch is refused before network.
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="deny",
            reason="location_principal_mismatch",
            route_class=route_class,
            write=bool(write),
            evidence={"record_location_id": record.location_id},
        )
    if record.invalidation_reason:
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="deny",
            reason="evidence_invalidated",
            route_class=route_class,
            write=bool(write),
            evidence={"invalidation_reason": record.invalidation_reason},
        )
    if record.availability == "beta_not_enabled":
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="deny",
            reason="beta_not_enabled",
            route_class=route_class,
            write=bool(write),
            evidence={"fallback_policy": policy},
        )
    if record.scope_state in ("missing_scope", "wrong_role", "denied"):
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="deny",
            reason=record.scope_state,
            route_class=route_class,
            write=bool(write),
            evidence={"fallback_policy": policy},
        )
    if not record.enabled:
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="deny",
            reason="not_enabled",
            route_class=route_class,
            write=bool(write),
            evidence={"fallback_policy": policy},
        )
    if not record.read_proven:
        # A bounded canary may run BEFORE the read is proven; production
        # dispatch may not (section 5.2 canary-deadlock paragraph).
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="canary_required" if write else "probe_required",
            reason="read_evidence_absent",
            route_class=route_class,
            write=bool(write),
            evidence={"fallback_policy": policy},
        )
    if write and not record.canary_proven:
        return CapabilityResolution(
            tenant=tenant,
            operation_id=str(operation_id),
            decision="canary_required",
            reason="write_canary_absent",
            route_class=route_class,
            write=True,
            evidence={"fallback_policy": policy},
        )
    return CapabilityResolution(
        tenant=tenant,
        operation_id=str(operation_id),
        decision="allow",
        reason="evidence_complete",
        route_class=route_class,
        write=bool(write),
        evidence={
            "fallback_policy": policy,
            "credential_fingerprint": record.credential_fingerprint,
            "effective_grant_fingerprint": record.effective_grant_fingerprint,
            "contract_revision": record.contract_revision,
            "request_media_type": record.request_media_type,
            "expires_at": record.expires_at,
        },
    )


def decide_route(
    *,
    resolution: CapabilityResolution,
    caller: str = "cli_worker",
    route_class: str | None = None,
    failure: FailureClassification | None = None,
    dry_run: bool = False,
    fallback_policy: str | None = None,
) -> RouteDecision:
    """One route for one operation.  Never two public implementations.

    Order follows Document 1 section 5.3.  ``unknown_outcome`` (or a live
    failure class that means the commit is ambiguous) selects ONLY
    reconciliation: no retry and no rail switch (IG-ROUTE-04, A07).
    """

    policy = str(
        fallback_policy
        or resolution.evidence.get("fallback_policy")
        or DEFAULT_FALLBACK_POLICY
    )
    klass = str(route_class or resolution.route_class or "")
    write = bool(resolution.write)

    def decided(route: str, reason: str, *, must_reconcile: bool = False) -> RouteDecision:
        return RouteDecision(
            tenant=resolution.tenant,
            operation_id=resolution.operation_id,
            route=route,
            reason=reason,
            write=write,
            must_reconcile=must_reconcile,
            evidence={
                "caller": str(caller),
                "policy": policy,
                "decision": resolution.decision,
                "resolution_reason": resolution.reason,
                "failure_classification": (
                    failure.as_evidence() if failure is not None else None
                ),
            },
        )

    if dry_run:
        return decided("dry_run", "dry_run_performs_no_mutating_call")
    if failure is not None and failure.kind == "unknown_outcome":
        return decided(
            "reconcile_only",
            "ambiguous_commit_reconcile_on_the_same_rail",
            must_reconcile=True,
        )
    if failure is not None and failure.kind == "rate_limited":
        return decided("none", "rate_limited_backoff_no_transport_rotation")
    if failure is not None and failure.kind in (
        "unauthorized",
        "missing_scope",
        "wrong_role",
        "forbidden",
    ):
        # IG-ROUTE-03: a permission denial is never laundered anywhere.
        return decided("none", "permission_denial_not_a_fallback")
    if failure is not None and failure.kind == "beta_not_enabled":
        return _fallback_route(decided, policy, "beta_not_enabled", klass)
    if resolution.decision == "deny":
        if resolution.reason in ("missing_scope", "wrong_role", "denied"):
            return decided("none", "permission_denial_not_a_fallback")
        if resolution.reason == "beta_not_enabled":
            return _fallback_route(decided, policy, "beta_not_enabled", klass)
        if resolution.reason in ("evidence_invalidated", "operation_mismatch", "location_principal_mismatch"):
            return decided("none", "evidence_invalid_or_mismatched")
        if klass in ("skill06_authoring", "capability_gap"):
            return _fallback_route(decided, policy, "no_api_route", klass)
        return decided("none", "capability_not_admitted")
    if resolution.decision in ("probe_required", "canary_required"):
        return decided("public_rest", resolution.reason)
    if caller == "mcp_session":
        # The MCP-capable session keeps its established official-MCP
        # preference; a missing MCP operation is not proof the API is absent.
        return decided("official_mcp", "mcp_capable_session_exact_operation")
    return decided("public_rest", "verified_shared_public_rest")


def _fallback_route(decided, policy: str, reason: str, route_class: str) -> RouteDecision:
    if policy in ("authorized_private_then_managed_browser", "authorized_private"):
        return decided("private_fallback", reason)
    if policy == "managed_browser":
        return decided("managed_browser", reason)
    if route_class in ("skill06_authoring", "capability_gap") and policy == "none":
        return decided("none", reason)
    return decided("none", reason)


# ---------------------------------------------------------------------------
# Bounded canary admission
#
# A canary is the ONLY way past "no prior write proves the write".  It is
# bounded to one explicitly authorized operation, one tenant, one attempt, and
# it never enables anything globally.
# ---------------------------------------------------------------------------

CANARY_MAX_ATTEMPTS = 1


@dataclass(frozen=True)
class CanaryAdmission:
    operation_id: str
    tenant: str
    authorized_by: str
    contract_revision: str
    credential_fingerprint: str | None = None
    purpose: str = "capability_canary"
    max_attempts: int = CANARY_MAX_ATTEMPTS

    def __post_init__(self) -> None:
        for field in ("operation_id", "tenant", "authorized_by", "contract_revision"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "canary_admission_incomplete", detail={"field": field}
                )
        if not isinstance(self.max_attempts, int) or not (
            1 <= self.max_attempts <= CANARY_MAX_ATTEMPTS
        ):
            raise ContractViolation(
                "canary_attempts_invalid", operation_id=self.operation_id
            )

    def admit(
        self, record: CapabilityRecordV2 | None
    ) -> tuple[bool, str]:
        """Admit the FIRST canary without demanding a prior successful write."""

        if record is None:
            return False, "capability_record_absent"
        if record.operation_id != self.operation_id:
            return False, "operation_mismatch"
        if record.location_id != self.tenant:
            return False, "location_principal_mismatch"
        if record.contract_revision != self.contract_revision:
            return False, "contract_revision_mismatch"
        if self.credential_fingerprint is not None and (
            record.credential_fingerprint
            and record.credential_fingerprint != self.credential_fingerprint
        ):
            return False, "credential_mismatch"
        if not (record.documented and record.adapter_built and record.offline_tests_passed):
            return False, "offline_evidence_incomplete"
        if record.availability == "beta_not_enabled":
            return False, "beta_not_enabled"
        if record.scope_state in ("missing_scope", "wrong_role", "denied"):
            return False, record.scope_state
        if record.canary_proven:
            return False, "canary_already_recorded"
        return True, "bounded_canary_admitted"
