"""Public capability gate -- GU-004 sections 3.1-3.3.

Default-deny proof: an operation with no recorded capability is refused with a
receipt and never reaches transport.  ``enabled=True`` together with a non-null
``activation_blocked`` is impossible for every row, and enablement requires the
frozen evidence (plus the canary for a write).
"""

from __future__ import annotations

import os
import re
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FROZEN_OPERATIONS,
    REGISTRY_PRESENT,
    REGISTRY_REASON,
    SYNTHETIC_CONTACT,
    SYNTHETIC_TENANT,
    FakeTransport,
    Row,
    enabled_gate,
    fake_tenant,
    issue_key,
    make_adapter,
    readback_spec,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    DEFAULT_BLOCK,
    ActivationBlock,
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.errors import (  # noqa: E402
    CapabilityDisabled,
    ContractViolation,
)
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

_V4_WRITES = (
    "workflows.definition.create",
    "workflows.definition.update",
    "workflows.status.publish",
    "workflows.definition.delete",
)

_READ_ROW = row(
    "contacts.get",
    method="GET",
    path_template="/contacts/{contactId}",
    tenant_binding="path.contactId",
)
_WRITE_ROW = row(
    "contacts.upsert",
    method="POST",
    path_template="/contacts/upsert",
    write=True,
    tenant_binding="body.locationId",
)

_COMPLETE = dict(
    contract_verified=True,
    adapter_built=True,
    offline_tests_passed=True,
    read_verified=True,
    canary_verified=True,
)


class DefaultDenyTest(unittest.TestCase):
    def test_gate_returns_a_disabled_capability_for_an_unknown_operation(self) -> None:
        capability = CapabilityGate().get("contacts.get")
        self.assertFalse(capability.enabled)
        self.assertIsNotNone(capability.activation_blocked)
        self.assertEqual(capability.activation_blocked.reason, DEFAULT_BLOCK.reason)

    def test_gate_refuses_through_require(self) -> None:
        with self.assertRaises(CapabilityDisabled) as caught:
            CapabilityGate().require("contacts.get")
        self.assertEqual(caught.exception.rule, "capability_disabled")
        self.assertIn("owner", caught.exception.detail)
        self.assertIn("unblock", caught.exception.detail)

    def test_a_disabled_row_still_explains_itself(self) -> None:
        gate = CapabilityGate(
            {"contacts.get": Capability(operation_id="contacts.get", enabled=False)}
        )
        capability = gate.get("contacts.get")
        self.assertFalse(capability.enabled)
        self.assertIsNotNone(capability.activation_blocked)

    def test_every_supplied_capability_defaults_to_disabled_state(self) -> None:
        capability = Capability(operation_id="contacts.get")
        for field_name in (
            "contract_verified",
            "adapter_built",
            "offline_tests_passed",
            "read_verified",
            "canary_verified",
            "enabled",
        ):
            self.assertFalse(getattr(capability, field_name), field_name)

    def test_disabled_call_produces_a_receipt_and_never_reaches_transport(self) -> None:
        operations = registry(_READ_ROW)
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(transport, operations, gate=CapabilityGate())

        result = adapter.call(
            operation_id="contacts.get",
            tenant=fake_tenant(),
            path_params={"contactId": SYNTHETIC_CONTACT},
        )

        self.assertIs(result.status, Status.denied)
        self.assertRegex(result.receipt_id, re.compile(r"^gxo_res_[0-9a-f]{12}$"))
        self.assertEqual(result.evidence["receipt_id"], result.receipt_id)
        self.assertEqual(result.evidence["tenant"], SYNTHETIC_TENANT)
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertIn("owner", result.error)
        self.assertIn("unblock", result.error)
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertEqual(result.evidence["capability"], {
            "operation_id": "contacts.get",
            "enabled": False,
        })
        self.assertEqual(transport.call_count, 0)

    def test_disabled_write_is_refused_before_transport_and_does_not_burn_the_key(self) -> None:
        operations = registry(_WRITE_ROW, _READ_ROW)
        readbacks = ReadbackRegistry()
        readbacks.register(readback_spec())
        transport = FakeTransport([resp(200), resp(200)])
        adapter = make_adapter(
            transport, operations, gate=CapabilityGate(), readbacks=readbacks
        )
        key = issue_key("contacts.upsert")

        first = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=key,
            readback=readback_spec(),
        )
        second = adapter.call(
            operation_id="contacts.upsert",
            tenant=fake_tenant(),
            body={"email": "a@example.invalid"},
            idempotency_key=key,
            readback=readback_spec(),
        )

        self.assertIs(first.status, Status.denied)
        self.assertEqual(first.error["rule"], "capability_disabled")
        self.assertIs(second.status, Status.denied)
        self.assertEqual(transport.call_count, 0)


class IllegalCombinationTest(unittest.TestCase):
    def test_enabled_with_an_activation_block_is_impossible(self) -> None:
        block = ActivationBlock(
            reason="synthetic blocker",
            owner="W04",
            unblock="synthetic evidence",
        )
        with self.assertRaises(ContractViolation) as caught:
            Capability(operation_id="contacts.get", enabled=True, activation_blocked=block)
        self.assertEqual(caught.exception.rule, "enabled_with_activation_block")

    def test_enabled_without_evidence_is_impossible(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            Capability(operation_id="contacts.get", enabled=True)
        self.assertEqual(caught.exception.rule, "enabled_without_evidence")

    def test_partial_evidence_cannot_enable(self) -> None:
        partial_sets = (
            dict(contract_verified=True),
            dict(contract_verified=True, adapter_built=True),
            dict(contract_verified=True, adapter_built=True, offline_tests_passed=True),
        )
        for evidence in partial_sets:
            with self.subTest(evidence=evidence):
                with self.assertRaises(ContractViolation):
                    Capability(operation_id="contacts.upsert", enabled=True, **evidence)

    def test_read_ready_evidence_cannot_enable_a_write(self) -> None:
        # Read evidence is complete but the canary is missing: the gate refuses
        # exactly here (section 3.2 rule 3), before any transport.
        read_ready = Capability(
            operation_id="contacts.upsert",
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
        )
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        with self.assertRaises(ContractViolation) as caught:
            gate.enable(read_ready, write=True)
        self.assertEqual(caught.exception.rule, "capability_canary_missing")
        self.assertFalse(gate.get("contacts.upsert").enabled)

    def test_an_unbound_gate_cannot_hold_an_enabled_capability(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            CapabilityGate({"contacts.get": Capability(operation_id="contacts.get", enabled=True, **_COMPLETE)})
        self.assertEqual(caught.exception.rule, "capability_requires_tenant")

    def test_gate_enable_requires_a_tenant(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            CapabilityGate().enable(
                Capability(operation_id="contacts.get", **_COMPLETE), write=False
            )
        self.assertEqual(caught.exception.rule, "capability_requires_tenant")

    def test_partial_activation_block_is_refused(self) -> None:
        for kwargs in (
            dict(reason="", owner="W04", unblock="x"),
            dict(reason="x", owner="", unblock="x"),
            dict(reason="x", owner="W04", unblock=""),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ContractViolation) as caught:
                    ActivationBlock(**kwargs)  # type: ignore[arg-type]
                self.assertEqual(caught.exception.rule, "activation_block_incomplete")


class EnablementRuleTest(unittest.TestCase):
    def test_read_enable_requires_contract_adapter_tests_and_read(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        missing_read = Capability(
            operation_id="contacts.get",
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
        )
        with self.assertRaises(ContractViolation) as caught:
            gate.enable(missing_read, write=False)
        self.assertEqual(caught.exception.rule, "capability_evidence_insufficient")

    def test_write_enable_requires_the_canary(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        no_canary = Capability(
            operation_id="contacts.upsert",
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
        )
        with self.assertRaises(ContractViolation) as caught:
            gate.enable(no_canary, write=True)
        self.assertEqual(caught.exception.rule, "capability_canary_missing")

    def test_complete_evidence_enables_and_clears_the_block(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        enabled = gate.enable(
            Capability(operation_id="contacts.upsert", **_COMPLETE), write=True
        )
        self.assertTrue(enabled.enabled)
        self.assertIsNone(enabled.activation_blocked)
        self.assertTrue(gate.require("contacts.upsert").enabled)

    def test_a_blocked_capability_cannot_be_enabled(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        blocked = Capability(
            operation_id="contacts.get",
            **_COMPLETE,
            activation_blocked=ActivationBlock(
                reason="x", owner="W04", unblock="y"
            ),
        )
        with self.assertRaises(ContractViolation):
            gate.enable(blocked, write=False)


@unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
class FrozenRegistryCapabilityTest(unittest.TestCase):
    def test_no_frozen_row_is_enabled_by_default(self) -> None:
        gate = CapabilityGate()
        for operation_id, frozen in FROZEN_OPERATIONS.items():
            if frozen.route_class == "skill44_private":
                continue  # not governed by this gate (section 3.2 rule 8)
            with self.subTest(operation_id=operation_id):
                capability = gate.get(operation_id)
                self.assertFalse(capability.enabled)
                self.assertIsNotNone(capability.activation_blocked)

    def test_enabled_and_activation_blocked_never_coexist_for_a_frozen_row(self) -> None:
        for operation_id in FROZEN_OPERATIONS:
            row_capability = CapabilityGate().get(operation_id)
            with self.subTest(operation_id=operation_id):
                self.assertFalse(
                    row_capability.enabled and row_capability.activation_blocked is not None
                )

    def test_skill44_private_rows_are_not_governed_by_this_gate(self) -> None:
        private = [
            frozen
            for frozen in FROZEN_OPERATIONS.values()
            if frozen.route_class == "skill44_private"
        ]
        self.assertTrue(private, "registry must carry the skill44_private rows")
        transport = FakeTransport()
        adapter = make_adapter(transport, FROZEN_OPERATIONS)
        for frozen in private:
            with self.subTest(operation_id=frozen.operation_id):
                descriptor = adapter.capability(frozen.operation_id)
                self.assertFalse(descriptor.enabled)
                self.assertIsNotNone(descriptor.activation_blocked)

    def test_every_v4_write_is_disabled(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        for operation_id in _V4_WRITES:
            with self.subTest(operation_id=operation_id):
                self.assertIn(operation_id, FROZEN_OPERATIONS)
                frozen = FROZEN_OPERATIONS[operation_id]
                self.assertEqual(frozen.version, "v4")
                self.assertTrue(frozen.write)
                self.assertTrue(frozen.approval_required)
                self.assertFalse(gate.get(operation_id).enabled)


if __name__ == "__main__":
    unittest.main(verbosity=2)
