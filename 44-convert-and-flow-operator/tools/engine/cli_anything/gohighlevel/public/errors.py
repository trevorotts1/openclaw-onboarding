"""Pre-transport refusal errors for the public adapter.

Frozen by evidence/W01/GU-004-CONTRACT-FREEZE.md section 1.1.

Every error carries a machine-readable ``rule`` and a ``detail`` mapping of
names/keys only.  A secret value, token, PIT, location id or customer payload
is never placed in an error, in ``detail`` or in the exception message.
"""

from __future__ import annotations

from typing import Any, Mapping


class _AdapterError(Exception):
    """Common behaviour: rule code plus safe detail."""

    rule = "contract_violation"

    def __init__(
        self,
        rule: str | None = None,
        *,
        operation_id: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        self.rule = rule or type(self).rule
        self.operation_id = operation_id
        self.detail = dict(detail or {})
        parts = [self.rule]
        if operation_id:
            parts.append("operation_id=" + str(operation_id))
        for key in sorted(self.detail):
            parts.append(f"{key}={self.detail[key]}")
        super().__init__(type(self).__name__ + ": " + " ".join(parts))

    def to_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"rule": self.rule}
        payload.update(self.detail)
        return payload


class ContractViolation(_AdapterError):
    """The caller broke the frozen contract.  Refused before transport."""

    rule = "contract_violation"


class ReconciliationRequired(_AdapterError):
    """An unreconciled unknown_outcome blocks this retry (section 2.4)."""

    rule = "reconciliation_required"


class CapabilityDisabled(_AdapterError):
    """The capability gate refuses this operation (section 3.2 rule 7)."""

    rule = "capability_disabled"


class CredentialMissing(_AdapterError):
    """No usable credential was found.  Only variable names are recorded."""

    rule = "credential_missing"
