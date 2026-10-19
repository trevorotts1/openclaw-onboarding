"""Capability-gate breadth suite -- GHL-170, re-pinned by GHL-182.

Proves, offline, that the capability gate denies every operation that is not
explicitly enabled for the bound tenant, across the whole ``operations.py``
registry.  The registry is enumerated dynamically: nothing here hardcodes a
row list, and the row count is pinned so a registry change fails loudly until
the suite is updated.

The checked-in record was re-verified by GHL-150 (``920ce3fd4``): it names
tenant ``Mct54Bwi1KlNouGXQcDX`` and enables exactly six read-verified rows.
The earlier premises -- "the record admits nothing" and "the record names a
non-live tenant" -- are therefore stale, and this suite is re-pinned to the
recorded reality without weakening any assertion.

Four proofs:

1. The checked-in record admits exactly its six enabled operations for the
   tenant it names, and denies every other registry row with zero transport
   calls.  Rows the adapter refuses before the gate (unapplicable tenant
   bindings) are named and counted, derived from the registry rather than a
   stale constant.
2. A synthetic record enabling exactly one operation for the live tenant
   admits that row and only that row.
3. A record for another tenant admits nothing when the qualifier is the live
   tenant, including a row that is enabled inside the record, and including a
   row that carries its own mismatched tenant.
4. Mutation controls: bypassing the gate, returning an enabled capability, or
   granting another tenant's enablement makes these assertions fail, so the
   suite has teeth.

No live call is made: ``FakeTransport`` records every request and replays
scripted responses.  No token, PIT, location id or customer value from a real
account appears here beyond the tenant identifiers the unit names.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    ApprovalRef,
    FakeTransport,
    PublicGhlAdapter,
    SYNTHETIC_APPROVAL,
    fake_auth,
    fake_tenant,
    issue_key,
    resp,
)

from cli_anything.gohighlevel.public import adapter as adapter_module  # noqa: E402
from cli_anything.gohighlevel.public import capability as capability_module  # noqa: E402
from cli_anything.gohighlevel.public.auth import AuthKind  # noqa: E402
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    Capability,
    CapabilityGate,
    capability_record_path,
    load_capability_record,
)
from cli_anything.gohighlevel.public.errors import CapabilityDisabled  # noqa: E402
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402
from cli_anything.gohighlevel.public.readback import (  # noqa: E402
    ReadbackRegistry,
    ReadbackSpec,
)
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

#: The tenant the checked-in record names and the unit treats as "live".
LIVE_TENANT = "Mct54Bwi1KlNouGXQcDX"

#: A tenant the checked-in record does not name.  Loading the record for this
#: qualifier must fail closed to an empty gate.
FOREIGN_TENANT = "XCgFTEA1oDvsPnTqqgoB"

#: The six operations the checked-in record enables for ``LIVE_TENANT``,
#: read-verified live on 2026-10-19 (GHL-150).  A change here is a record
#: change the suite must be told about.
EXPECTED_ENABLED = frozenset(
    {
        "locations.get",
        "contacts.list",
        "contacts.search",
        "custom_fields.list",
        "pipelines.list",
        "media.files.list",
    }
)

#: The gate is default-deny, so the only admissible pre-gate refusals are the
#: frozen tenant-binding rules.  A new rule appearing here is a behaviour
#: change the suite must be told about.
PRE_GATE_RULES = frozenset({"unknown_tenant_binding", "tenant_path_missing"})

#: Pinned registry shape.  A change here means operations.py grew or shrank:
#: update this count and the breadth expectations in the same change.  Failing
#: loudly is the point.
EXPECTED_OPERATION_COUNT = 140

_COMPLETE = dict(
    contract_verified=True,
    adapter_built=True,
    offline_tests_passed=True,
    read_verified=True,
    canary_verified=True,
)

#: The single operation the synthetic records enable.  It is a read row on a
#: public route, so admission ends in one transport call and no readback.
ENABLED_OPERATION = "locations.get"

_ROW_COUNT_MESSAGE = (
    "operations.py registry row count changed to {actual} (suite pins "
    "{expected}); update EXPECTED_OPERATION_COUNT and the breadth expectations "
    "in tests/test_capability_breadth.py"
)


# ---------------------------------------------------------------------------
# per-row call construction
# ---------------------------------------------------------------------------


def _path_params(template: str, tenant: str) -> dict[str, str]:
    return {
        name: tenant if name == "locationId" else "synthetic_" + name
        for name in re.findall(r"\{([^{}]+)\}", template or "")
    }


def _query_for(row) -> dict[str, str]:
    """Satisfy a row's declared required query so the gate is actually reached.

    A missing required query is a typed contract violation *before* the gate
    (GHL-150), so the suite must supply a document-valid value or it would
    never test the gate for that row.
    """

    enums = dict(getattr(row, "query_enums", ()) or ())
    return {
        str(name): str(enums[name][0]) if name in enums else "synthetic_value"
        for name in tuple(getattr(row, "required_query", ()) or ())
    }


def _readback_for(row, tenant: str) -> ReadbackSpec:
    target = (
        OPERATIONS[row.readback_plan]
        if row.readback_plan
        else OPERATIONS["contacts.get"]
    )
    return ReadbackSpec(
        operation_id=target.operation_id,
        target_params=_path_params(target.path_template, tenant),
        expect={"id": "synthetic_id"},
    )


def _auth_for(row, tenant: str):
    for kind in row.auth_kinds:
        if kind in (AuthKind.location_pit, AuthKind.oauth):
            return fake_auth(kind=kind, location_id=tenant)
        if kind is AuthKind.firebase_internal:
            return fake_auth(kind=kind)
    # No auth class satisfies the row; the adapter refuses it before the gate
    # and the suite asserts that refusal is still fail-closed.
    return fake_auth(kind=AuthKind.location_pit, location_id=tenant)


def _call_kwargs(row, tenant: str) -> dict:
    kwargs = {
        "operation_id": row.operation_id,
        "tenant": fake_tenant(tenant),
        "path_params": _path_params(row.path_template, tenant),
        "query": _query_for(row),
    }
    if row.write:
        kwargs["idempotency_key"] = issue_key(row.operation_id)
        kwargs["readback"] = _readback_for(row, tenant)
        kwargs["approval"] = ApprovalRef(ref=SYNTHETIC_APPROVAL)
    return kwargs


def _invoke(row, tenant: str, *, gate=None, record=None):
    """Call one row against a fake transport; return (result, transport)."""

    transport = FakeTransport([resp(200)])
    adapter = PublicGhlAdapter(
        auth=_auth_for(row, tenant),
        operations=OPERATIONS,
        transport=transport,
        capability=gate,
        capability_record=record,
        readbacks=ReadbackRegistry(),
    )
    result = adapter.call(**_call_kwargs(row, tenant))
    return result, transport


def _checked_in_record() -> dict:
    path = capability_record_path()
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_record(directory: str, tenant: str, capabilities: dict) -> str:
    document = {
        "record_version": 1,
        "tenant": tenant,
        "recorded_at": "2026-10-19",
        "authority": "synthetic test record (GHL-170 breadth suite)",
        "note": "test-only; never enables a live call",
        "capabilities": capabilities,
    }
    path = os.path.join(directory, "synthetic-capabilities.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    return path


def _enabled_row(**overrides) -> dict:
    row = dict(_COMPLETE, enabled=True, activation="UNVERIFIED", provisional=False)
    row.update(overrides)
    return row


def _assert_gate_reachable_rule(operation_id: str, rule: str, row) -> None:
    if rule == "capability_disabled":
        return
    assert rule in PRE_GATE_RULES, (
        f"{operation_id}: unexpected denial rule {rule!r}; only "
        f"capability_disabled or {sorted(PRE_GATE_RULES)} may deny a row"
    )
    assert row.route_class != "public_direct", (
        f"{operation_id}: a public_direct row must be denied by the capability "
        f"gate, not by {rule!r}"
    )


#: Tenant bindings the frozen table can apply without a path value.  A row
#: declaring anything else is refused before the capability gate.
_APPLICABLE_BINDINGS = frozenset(
    {
        "none",
        "implicit-pit",
        "body.locationId",
        "query.locationId",
        "body.altId+altType=location",
        "query.altId+altType",
        "query.altId+altType=location",
    }
)


def _pre_gate_operation_ids() -> set[str]:
    """Registry rows the adapter refuses before the capability gate.

    Recomputed from the registry's own ``tenant_binding`` and
    ``path_template`` fields, so the suite never carries a stale refusal
    count; if the adapter stops refusing one of these rows the observed set
    diverges and the suite fails.
    """

    pre: set[str] = set()
    for operation_id, row in OPERATIONS.items():
        binding = str(getattr(row, "tenant_binding", "none") or "none")
        params = set(
            re.findall(r"\{([^{}]+)\}", getattr(row, "path_template", "") or "")
        )
        if binding == "path.locationId":
            if "locationId" not in params:
                pre.add(operation_id)
        elif binding.startswith("path."):
            # The identifier rides its own path parameter; nothing to inject.
            continue
        elif binding not in _APPLICABLE_BINDINGS:
            pre.add(operation_id)
    return pre


def _assert_pre_gate_matches_registry(observed: set[str]) -> None:
    expected = _pre_gate_operation_ids()
    assert observed == expected, (
        "pre-gate refusal set changed; registry says "
        f"{sorted(expected)} but the adapter refused {sorted(observed)}"
    )


# ---------------------------------------------------------------------------
# 1. checked-in record: exactly its six enabled rows are admitted
# ---------------------------------------------------------------------------


class CheckedInRecordBreadthTest(unittest.TestCase):
    def test_record_enables_exactly_the_pinned_rows(self) -> None:
        record = _checked_in_record()
        self.assertEqual(str(record["tenant"]), LIVE_TENANT)
        self.assertEqual(record["record_version"], 1)
        self.assertEqual(
            set(record["capabilities"]),
            set(EXPECTED_ENABLED),
            "checked-in record row set changed; update EXPECTED_ENABLED",
        )
        for operation_id, row in record["capabilities"].items():
            with self.subTest(operation_id=operation_id):
                self.assertIs(row["enabled"], True)
                self.assertIs(row["read_verified"], True)
                self.assertEqual(row["activation"], "VERIFIED")
                self.assertIs(row["provisional"], False)

    def test_every_registry_row_is_classified_by_the_checked_in_record(self) -> None:
        record = _checked_in_record()
        record_tenant = str(record["tenant"])

        gate = load_capability_record(tenant=record_tenant)
        self.assertEqual(len(gate), len(EXPECTED_ENABLED))
        for operation_id in OPERATIONS:
            capability = gate.get(operation_id)
            if operation_id in EXPECTED_ENABLED:
                self.assertTrue(capability.enabled, operation_id)
                self.assertEqual(
                    gate.require(operation_id).operation_id, operation_id
                )
            else:
                self.assertFalse(capability.enabled, operation_id)
                with self.assertRaises(CapabilityDisabled) as caught:
                    gate.require(operation_id)
                self.assertEqual(caught.exception.rule, "capability_disabled")

        exercised: list[str] = []
        admitted: list[str] = []
        gate_denials: set[str] = set()
        pre_gate: set[str] = set()
        for operation_id, row in OPERATIONS.items():
            with self.subTest(operation_id=operation_id):
                result, transport = _invoke(
                    row, record_tenant, record=capability_record_path()
                )
                exercised.append(operation_id)

                if operation_id in EXPECTED_ENABLED:
                    self.assertIs(result.status, Status.ok, operation_id)
                    self.assertEqual(transport.call_count, 1, operation_id)
                    self.assertEqual(
                        result.evidence["capability"]["operation_id"],
                        operation_id,
                    )
                    self.assertIs(result.evidence["capability"]["enabled"], True)
                    self.assertEqual(
                        result.evidence["capability"]["observed_http_status"],
                        200,
                    )
                    admitted.append(operation_id)
                    continue

                rule = (result.error or {}).get("rule")
                self.assertIs(result.status, Status.denied)
                self.assertIs(result.evidence.get("refused_before_transport"), True)
                self.assertEqual(result.evidence.get("tenant"), record_tenant)
                self.assertEqual(transport.call_count, 0, operation_id)
                self.assertIsNotNone(result.receipt_id)
                self.assertRegex(result.receipt_id, r"^gxo_res_[0-9a-f]{12}$")
                _assert_gate_reachable_rule(operation_id, rule, row)

                if rule == "capability_disabled":
                    gate_denials.add(operation_id)
                else:
                    pre_gate.add(operation_id)

        self.assertEqual(
            len(exercised),
            len(OPERATIONS),
            f"exercised {len(exercised)} of {len(OPERATIONS)} rows",
        )
        self.assertEqual(set(exercised), set(OPERATIONS))
        self.assertEqual(sorted(admitted), sorted(EXPECTED_ENABLED))
        _assert_pre_gate_matches_registry(pre_gate)
        self.assertEqual(
            gate_denials,
            set(OPERATIONS) - set(EXPECTED_ENABLED) - pre_gate,
            "every other row must be denied by capability_disabled",
        )
        public = {
            operation_id
            for operation_id, row in OPERATIONS.items()
            if row.route_class == "public_direct"
        }
        self.assertTrue(public <= (gate_denials | set(EXPECTED_ENABLED)), (
            "every non-enabled public_direct row must be denied by "
            f"capability_disabled; missing "
            f"{sorted(public - gate_denials - set(EXPECTED_ENABLED))}"
        ))


# ---------------------------------------------------------------------------
# 2. synthetic record: exactly one operation enabled for the live tenant
# ---------------------------------------------------------------------------


class SingleEnablementBreadthTest(unittest.TestCase):
    def test_only_the_enabled_operation_is_admitted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="operator-mac-GHL-182-") as temp:
            path = _write_record(
                temp, LIVE_TENANT, {ENABLED_OPERATION: _enabled_row()}
            )

            # Known-good control on the instrument: the record itself enables
            # exactly the one row.
            control = load_capability_record(tenant=LIVE_TENANT, path=path)
            self.assertTrue(control.get(ENABLED_OPERATION).enabled)
            self.assertEqual(len(control), 1)

            admitted: list[str] = []
            gate_denials: set[str] = set()
            pre_gate: set[str] = set()
            for operation_id, row in OPERATIONS.items():
                with self.subTest(operation_id=operation_id):
                    result, transport = _invoke(row, LIVE_TENANT, record=path)
                    rule = (result.error or {}).get("rule")

                    if operation_id == ENABLED_OPERATION:
                        self.assertIs(result.status, Status.ok)
                        self.assertEqual(transport.call_count, 1)
                        self.assertEqual(
                            result.evidence["capability"]["operation_id"],
                            ENABLED_OPERATION,
                        )
                        self.assertIs(
                            result.evidence["capability"]["enabled"], True
                        )
                        self.assertEqual(
                            result.evidence["capability"]["observed_http_status"],
                            200,
                        )
                        admitted.append(operation_id)
                        continue

                    self.assertIs(result.status, Status.denied)
                    self.assertIs(
                        result.evidence.get("refused_before_transport"), True
                    )
                    self.assertEqual(transport.call_count, 0, operation_id)
                    _assert_gate_reachable_rule(operation_id, rule, row)
                    if rule == "capability_disabled":
                        gate_denials.add(operation_id)
                    else:
                        pre_gate.add(operation_id)

            self.assertEqual(admitted, [ENABLED_OPERATION])
            _assert_pre_gate_matches_registry(pre_gate)
            self.assertEqual(
                gate_denials,
                set(OPERATIONS) - {ENABLED_OPERATION} - pre_gate,
            )
            public = {
                operation_id
                for operation_id, row in OPERATIONS.items()
                if row.route_class == "public_direct"
            } - {ENABLED_OPERATION}
            self.assertTrue(public <= gate_denials, (
                "every non-enabled public_direct row must be denied by "
                f"capability_disabled; missing {sorted(public - gate_denials)}"
            ))


# ---------------------------------------------------------------------------
# 3. tenant binding: a record for another tenant authorizes nothing
# ---------------------------------------------------------------------------


class TenantMismatchBreadthTest(unittest.TestCase):
    def test_record_for_another_tenant_denies_even_its_enabled_row(self) -> None:
        self.assertNotEqual(FOREIGN_TENANT, LIVE_TENANT)

        with tempfile.TemporaryDirectory(prefix="operator-mac-GHL-182-") as temp:
            path = _write_record(
                temp, FOREIGN_TENANT, {ENABLED_OPERATION: _enabled_row()}
            )

            # Control: the same record does enable the row for its own tenant.
            own = load_capability_record(tenant=FOREIGN_TENANT, path=path)
            self.assertTrue(own.get(ENABLED_OPERATION).enabled)

            # The qualifier is the live tenant: the loader fails closed to an
            # empty gate, so nothing is admitted.
            live = load_capability_record(tenant=LIVE_TENANT, path=path)
            self.assertEqual(len(live), 0)
            self.assertFalse(live.get(ENABLED_OPERATION).enabled)

            for operation_id, row in OPERATIONS.items():
                with self.subTest(operation_id=operation_id):
                    result, transport = _invoke(row, LIVE_TENANT, record=path)
                    rule = (result.error or {}).get("rule")
                    self.assertIs(result.status, Status.denied)
                    self.assertEqual(transport.call_count, 0, operation_id)
                    self.assertIs(
                        result.evidence.get("refused_before_transport"), True
                    )
                    _assert_gate_reachable_rule(operation_id, rule, row)

    def test_the_checked_in_record_denies_a_foreign_tenant(self) -> None:
        record = _checked_in_record()
        self.assertEqual(str(record["tenant"]), LIVE_TENANT)
        self.assertNotEqual(FOREIGN_TENANT, LIVE_TENANT)

        foreign = load_capability_record(tenant=FOREIGN_TENANT)
        self.assertEqual(len(foreign), 0)
        for operation_id in OPERATIONS:
            with self.subTest(operation_id=operation_id):
                self.assertFalse(foreign.get(operation_id).enabled)

    def test_a_capability_carrying_another_tenant_is_denied(self) -> None:
        with tempfile.TemporaryDirectory(prefix="operator-mac-GHL-182-") as temp:
            path = _write_record(
                temp,
                LIVE_TENANT,
                {
                    ENABLED_OPERATION: _enabled_row(tenant=FOREIGN_TENANT),
                },
            )
            gate = load_capability_record(tenant=LIVE_TENANT, path=path)
            capability = gate.get(ENABLED_OPERATION)
            self.assertTrue(capability.enabled)
            self.assertEqual(capability.tenant, FOREIGN_TENANT)

            row = OPERATIONS[ENABLED_OPERATION]
            result, transport = _invoke(row, LIVE_TENANT, record=path)

            self.assertIs(result.status, Status.denied)
            self.assertEqual(result.error["rule"], "capability_tenant_mismatch")
            self.assertEqual(
                result.error["operation_id"], ENABLED_OPERATION
            )
            self.assertIs(result.evidence.get("refused_before_transport"), True)
            self.assertEqual(
                result.evidence["capability"],
                {"operation_id": ENABLED_OPERATION, "enabled": True},
            )
            self.assertEqual(transport.call_count, 0)


# ---------------------------------------------------------------------------
# 4. dynamic enumeration and pinned registry shape
# ---------------------------------------------------------------------------


class RegistryEnumerationTest(unittest.TestCase):
    def test_registry_is_enumerated_dynamically_and_count_is_pinned(self) -> None:
        actual = len(OPERATIONS)
        self.assertEqual(
            actual,
            EXPECTED_OPERATION_COUNT,
            _ROW_COUNT_MESSAGE.format(
                actual=actual, expected=EXPECTED_OPERATION_COUNT
            ),
        )

        seen: list[str] = []
        for operation_id, row in OPERATIONS.items():
            seen.append(operation_id)
            self.assertEqual(row.operation_id, operation_id)

        self.assertEqual(len(seen), actual)
        self.assertEqual(len(set(seen)), actual)
        self.assertEqual(set(seen), set(OPERATIONS))
        self.assertEqual(
            len(OPERATIONS),
            len(OPERATIONS.keys()),
            "registry iteration and key enumeration disagree",
        )

    def test_pre_gate_refusals_are_recomputed_from_the_registry(self) -> None:
        # Independent of the call loop in test 1: recompute the classification
        # so a registry change trips one clear message rather than a cascade.
        record = _checked_in_record()
        tenant = str(record["tenant"])
        pre_gate: set[str] = set()
        for operation_id, row in OPERATIONS.items():
            with self.subTest(operation_id=operation_id):
                result, transport = _invoke(
                    row, tenant, record=capability_record_path()
                )
                if operation_id in EXPECTED_ENABLED:
                    self.assertIs(result.status, Status.ok)
                    self.assertEqual(transport.call_count, 1)
                    continue
                self.assertIs(result.status, Status.denied)
                self.assertEqual(transport.call_count, 0)
                rule = (result.error or {}).get("rule")
                _assert_gate_reachable_rule(operation_id, rule, row)
                if rule != "capability_disabled":
                    pre_gate.add(operation_id)
        _assert_pre_gate_matches_registry(pre_gate)
        # The derived set is small enough to name, and every member must be a
        # frozen pre-gate rule, never a gate widening.
        self.assertTrue(pre_gate, "the registry must still contain pre-gate rows")


# ---------------------------------------------------------------------------
# 5. mutation controls -- the suite must FAIL when the branch is bypassed
# ---------------------------------------------------------------------------


def _assert_all_rows_denied(tenant: str, *, gate=None, record=None) -> None:
    """Bare-assert version used only to prove the mutants are caught."""

    for operation_id, row in OPERATIONS.items():
        result, transport = _invoke(row, tenant, gate=gate, record=record)
        assert result.status is Status.denied, (
            f"{operation_id}: mutant admitted the call with status "
            f"{result.status.value!r}"
        )
        assert transport.call_count == 0, (
            f"{operation_id}: mutant reached transport {transport.call_count} "
            "time(s)"
        )


class MutationControlTest(unittest.TestCase):
    def test_bypassing_the_gate_is_caught(self) -> None:
        gate = CapabilityGate(tenant=LIVE_TENANT)
        with mock.patch.object(
            adapter_module, "_gate_skips", lambda route_class: True
        ):
            with self.assertRaises(AssertionError):
                _assert_all_rows_denied(LIVE_TENANT, gate=gate)

    def test_returning_an_enabled_capability_is_caught(self) -> None:
        def enabled(self, operation_id):  # noqa: ANN001 - mutant signature
            return Capability(
                operation_id=str(operation_id), enabled=True, **_COMPLETE
            )

        with mock.patch.object(CapabilityGate, "get", enabled):
            with self.assertRaises(AssertionError):
                _assert_all_rows_denied(
                    LIVE_TENANT, gate=CapabilityGate(tenant=LIVE_TENANT)
                )

    def test_granting_another_tenants_enablement_is_caught(self) -> None:
        self.assertNotEqual(FOREIGN_TENANT, LIVE_TENANT)

        with tempfile.TemporaryDirectory(prefix="operator-mac-GHL-182-") as temp:
            path = _write_record(
                temp, FOREIGN_TENANT, {ENABLED_OPERATION: _enabled_row()}
            )

            def tenant_blind(*, tenant, path=None, environ=None):  # noqa: ANN001
                # A loader that read the other tenant's enablement and bound it
                # to whatever tenant asked: the exact defect case 3 forbids.
                gate = CapabilityGate(tenant=tenant)
                gate.enable(
                    Capability(operation_id=ENABLED_OPERATION, **_COMPLETE),
                    write=False,
                )
                return gate

            with mock.patch.object(
                adapter_module, "load_capability_record", tenant_blind
            ):
                with self.assertRaises(AssertionError):
                    _assert_all_rows_denied(LIVE_TENANT, record=path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
