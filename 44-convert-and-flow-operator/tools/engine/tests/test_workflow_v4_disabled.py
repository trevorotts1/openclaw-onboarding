"""V4 workflow surface is DISABLED by default -- GU-004 3.2 rules 1, 4, 7.

Frozen expectations (section 6.2):

* every V4 write refuses without a canary and without an approval;
* a disabled call still produces a receipt and makes zero transport calls;
* there is no V4 sweep anywhere in the package: no module iterates the
  operation map (or the registry) and turns V4 writes on or fires them.

Every test is offline.  ``FakeTransport`` records requests and replays scripted
responses; no live account, token or network is involved.  Enabling a write is
never global: a gate is bound to one synthetic tenant and to one operation id.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    enabled_gate,
    fake_auth,
    fake_tenant,
)

from cli_anything.gohighlevel.public.adapter import (  # noqa: E402
    ApprovalRef,
    PublicGhlAdapter,
)
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402
from cli_anything.gohighlevel.public.result import (  # noqa: E402
    REQUIRED_EVIDENCE_KEYS,
    Status,
)
from cli_anything.gohighlevel.public.workflow_v4 import (  # noqa: E402
    GAP_RULES,
    OPERATION_MAP,
    WorkflowV4Adapter,
)

TENANT = fake_tenant()
APPROVAL = ApprovalRef(ref="approval-synthetic-v4")

#: The four frozen V4 write keys (section 5.7).  ``restore`` is a named gap,
#: not a row, so it is asserted separately.
WRITE_KEYS: tuple[str, ...] = ("create", "update", "status.change", "delete")
WRITE_IDS: tuple[str, ...] = tuple(OPERATION_MAP[key] for key in WRITE_KEYS)

_WRITE_SURFACE_CALLS: tuple[str, ...] = (
    "update_definition(",
    "create_workflow(",
    "delete_workflow(",
    "set_status(",
    "publish_workflow(",
    "unpublish_workflow(",
    "_write(",
    "enable(",
)


def _package_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "cli_anything"
        / "gohighlevel"
        / "public"
    )


def _public_adapter(
    transport: FakeTransport, gate: CapabilityGate | None = None
) -> PublicGhlAdapter:
    return PublicGhlAdapter(
        auth=fake_auth(),
        operations=OPERATIONS,
        transport=transport,
        capability=gate,
        readbacks=ReadbackRegistry(),
    )


def _v4(
    transport: FakeTransport, gate: CapabilityGate | None = None
) -> WorkflowV4Adapter:
    return WorkflowV4Adapter(public=_public_adapter(transport, gate))


def _loop_bodies(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, body_text)`` for every ``for`` block."""

    lines = text.splitlines()
    bodies: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)for\s+.+:\s*$", lines[index])
        if match is None:
            index += 1
            continue
        indent = len(match.group(1))
        body: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            if candidate.strip():
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate_indent <= indent:
                    break
            body.append(candidate)
            cursor += 1
        bodies.append((index + 1, "\n".join(body)))
        index = cursor
    return bodies


class DisabledByDefault(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.adapter = _v4(self.transport)

    # -- capability rows -------------------------------------------------

    def test_every_v4_operation_row_is_disabled_by_default(self) -> None:
        for key in WRITE_KEYS + ("definition.read", "status.read"):
            capability = self.adapter.capability(key)
            self.assertFalse(capability.enabled, key)
            self.assertIsNotNone(capability.activation_blocked, key)
            self.assertFalse(capability.write_ready() if key in WRITE_KEYS else False)

    def test_v4_write_rows_are_v4_and_approval_guarded(self) -> None:
        for operation_id in WRITE_IDS:
            row = OPERATIONS[operation_id]
            self.assertEqual(row.version, "v4", operation_id)
            self.assertTrue(row.write, operation_id)
            self.assertTrue(row.approval_required, operation_id)
            self.assertEqual(row.route_class, "public_direct", operation_id)

    # -- each write refuses with a receipt and zero transport ------------

    def _assert_denied_receipt(self, result, operation_id: str, calls: int) -> None:
        self.assertIs(result.status, Status.denied)
        self.assertEqual(result.operation_id, operation_id)
        self.assertRegex(result.receipt_id, r"^gxo_res_[0-9a-f]{12}$")
        for key in REQUIRED_EVIDENCE_KEYS:
            self.assertIn(key, result.evidence)
        self.assertIsNone(result.http_status)
        self.assertIsNone(result.response_fingerprint)
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertTrue(result.evidence["refused_before_transport"])
        self.assertFalse(result.evidence["workflow_v4"]["reconcilable"])
        self.assertEqual(self.transport.call_count, calls)

    def test_create_refuses_without_canary(self) -> None:
        result = self.adapter.create_workflow(
            tenant=TENANT,
            definition={"name": "Synthetic Flow", "source": "synthetic", "actions": []},
            approval=APPROVAL,
        )
        self._assert_denied_receipt(result, "workflows.definition.create", 0)

    def test_update_refuses_without_canary(self) -> None:
        result = self.adapter.update_definition(
            tenant=TENANT,
            workflow_id="wf_synthetic_0001",
            intent={"set_fields": {"name": "Synthetic Flow"}},
            approval=APPROVAL,
        )
        self._assert_denied_receipt(result, "workflows.definition.update", 0)

    def test_publish_refuses_without_canary(self) -> None:
        result = self.adapter.publish_workflow(
            tenant=TENANT, workflow_id="wf_synthetic_0001", approval=APPROVAL
        )
        self._assert_denied_receipt(result, "workflows.status.publish", 0)

    def test_delete_refuses_without_canary(self) -> None:
        result = self.adapter.delete_workflow(
            tenant=TENANT, workflow_id="wf_synthetic_0001", approval=APPROVAL
        )
        self._assert_denied_receipt(result, "workflows.definition.delete", 0)

    # -- reads enabled is not canary -------------------------------------

    def test_reads_enabled_do_not_enable_any_v4_write(self) -> None:
        gate = enabled_gate(
            [OPERATIONS["workflows.definition.read"], OPERATIONS["workflows.list"]],
            tenant=SYNTHETIC_TENANT,
        )
        adapter = _v4(self.transport, gate)

        read = adapter.read_definition(
            tenant=TENANT, workflow_id="wf_synthetic_0001"
        )
        self.assertIs(read.status, Status.ok)
        self.assertEqual(self.transport.call_count, 1)

        for call in (
            lambda: adapter.create_workflow(
                tenant=TENANT,
                definition={"name": "Synthetic Flow", "actions": []},
                approval=APPROVAL,
            ),
            lambda: adapter.update_definition(
                tenant=TENANT,
                workflow_id="wf_synthetic_0001",
                intent={"set_fields": {"name": "Synthetic Flow"}},
                approval=APPROVAL,
            ),
            lambda: adapter.publish_workflow(
                tenant=TENANT, workflow_id="wf_synthetic_0001", approval=APPROVAL
            ),
            lambda: adapter.delete_workflow(
                tenant=TENANT, workflow_id="wf_synthetic_0001", approval=APPROVAL
            ),
        ):
            result = call()
            self.assertIs(result.status, Status.denied)
            self.assertEqual(result.error["rule"], "capability_disabled")

        self.assertEqual(self.transport.call_count, 1)

    # -- canary and approval --------------------------------------------

    def test_enablement_refuses_a_write_without_canary(self) -> None:
        gate = CapabilityGate(tenant=SYNTHETIC_TENANT)
        capability = Capability(
            operation_id="workflows.definition.update",
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            canary_verified=False,
        )
        self.assertFalse(capability.write_ready())
        with self.assertRaises(ContractViolation) as caught:
            gate.enable(capability, write=True)
        self.assertEqual(caught.exception.rule, "capability_canary_missing")
        self.assertFalse(gate.get("workflows.definition.update").enabled)

    def test_enabled_write_without_approval_never_reaches_transport(self) -> None:
        gate = enabled_gate([OPERATIONS["workflows.definition.create"]])
        adapter = _v4(self.transport, gate)
        with self.assertRaises(ContractViolation) as caught:
            adapter.create_workflow(
                tenant=TENANT,
                definition={"name": "Synthetic Flow", "actions": []},
                approval=None,
            )
        self.assertEqual(caught.exception.rule, "approval_required")
        self.assertEqual(self.transport.call_count, 0)
        self.assertEqual(self.transport.requests, [])

    def test_restore_is_a_named_gap_not_a_row(self) -> None:
        self.assertIn("restore", GAP_RULES)
        self.assertNotIn("workflows.restore", WRITE_IDS)
        with self.assertRaises(ContractViolation) as caught:
            self.adapter.restore_workflow(
                tenant=TENANT, workflow_id="wf_synthetic_0001"
            )
        self.assertEqual(
            caught.exception.rule, "workflow_restore_has_no_documented_operation"
        )
        self.assertEqual(self.transport.call_count, 0)

    # -- no V4 sweep -----------------------------------------------------

    def test_no_module_iterates_the_operation_map_into_a_write(self) -> None:
        package = _package_dir()
        self.assertTrue(package.is_dir(), package)
        for path in sorted(package.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line_number, body in _loop_bodies(text):
                for surface in _WRITE_SURFACE_CALLS:
                    self.assertNotIn(
                        surface,
                        body,
                        f"{path.name}:{line_number} loops into {surface}",
                    )

    def test_v4_operation_ids_appear_only_in_registry_v4_and_alias_modules(self) -> None:
        # ``operations.py`` is the frozen row table and ``aliases.py`` is the
        # frozen alias table; both are data.  V4 module names are the adapter.
        allowed = {
            "operations.py",
            "aliases.py",
            "workflow_v4.py",
            "workflow_v4_intent.py",
        }
        for path in sorted(_package_dir().glob("*.py")):
            if path.name in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            for operation_id in WRITE_IDS:
                self.assertNotIn(operation_id, text, f"{path.name}: {operation_id}")

    def test_v4_version_is_confined_to_the_frozen_rows(self) -> None:
        v4_rows = {
            operation_id
            for operation_id, row in OPERATIONS.items()
            if row.version == "v4"
        }
        expected = {value for value in OPERATION_MAP.values() if value is not None}
        self.assertEqual(v4_rows, expected)

    def test_operation_map_writes_are_exactly_the_four_frozen_keys(self) -> None:
        mapped_writes = {
            key
            for key, operation_id in OPERATION_MAP.items()
            if operation_id is not None and OPERATIONS[operation_id].write
        }
        self.assertEqual(mapped_writes, set(WRITE_KEYS))
        self.assertEqual(set(GAP_RULES), {"validation.read", "restore"})


if __name__ == "__main__":
    unittest.main()
