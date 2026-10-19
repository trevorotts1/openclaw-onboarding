"""GHL-168: the V4 route/enable probe is bound to the call tenant.

Independent W18 QC reproduced two MAJOR defects with a fake transport:

* F1 -- ``WorkflowV4Adapter._enabled`` probed ``PublicGhlAdapter.capability``
  with no tenant.  A fresh adapter denied every V4 surface even when the
  capability record admitted all five for the call tenant.
* F2 -- ``workflow_route`` made the same unbound probe, so every surface
  routed ``skill44_private_fallback`` until some other call happened to load
  a tenant gate.  After ONE tenant-scoped read the verdict flipped: capability
  depended on call order.

These tests pin the fix.  Every call is offline: ``FakeTransport`` replays a
scripted 200, the capability record is a temporary JSON file, and no live
tenant, token or network is touched.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FakeTransport,
    fake_auth,
    fake_tenant,
    resp,
)

from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter  # noqa: E402
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402
from cli_anything.gohighlevel.public.workflow_v4 import (  # noqa: E402
    CREATE_OPERATION,
    DELETE_OPERATION,
    READ_OPERATION,
    STATUS_OPERATION,
    UPDATE_OPERATION,
    WorkflowV4Adapter,
)
from cli_anything.gohighlevel.utils.workflow_builder import (  # noqa: E402
    WORKFLOW_ROUTE_PRIVATE,
    WORKFLOW_ROUTE_PUBLIC,
    workflow_route,
)

#: The tenant the W18 QC used, as recorded by the live ledger for BlackCEO LLC.
LIVE_TENANT = "Mct54Bwi1KlNouGXQcDX"
#: A record that admits nothing for the live tenant must never widen it.
OTHER_TENANT = "XCgFTEA1oDvsPnTqqgoB"

V4_OPERATIONS = (
    READ_OPERATION,
    CREATE_OPERATION,
    UPDATE_OPERATION,
    STATUS_OPERATION,
    DELETE_OPERATION,
)
SURFACES = ("definition.read", "create", "update", "status.change", "delete")

_DEFINITION_BODY = json.dumps(
    {
        "workflow": {
            "id": "wf_synthetic_0001",
            "name": "Synthetic Flow",
            "version": 1,
            "actions": [],
            "triggers": [],
            "status": "draft",
        },
        "revision": 1,
    }
).encode()


def _record(path: Path, tenant: str) -> Path:
    """An admitting record: all five V4 operations enabled for ``tenant``."""

    rows = {
        operation_id: {
            "contract_verified": True,
            "adapter_built": True,
            "offline_tests_passed": True,
            "read_verified": True,
            "canary_verified": True,
            "enabled": True,
            "tenant": tenant,
        }
        for operation_id in V4_OPERATIONS
    }
    path.write_text(
        json.dumps(
            {"record_version": 1, "tenant": tenant, "capabilities": rows}
        ),
        encoding="utf-8",
    )
    return path


def _v4(record_path: Path, transport: FakeTransport) -> WorkflowV4Adapter:
    public = PublicGhlAdapter(
        auth=fake_auth(location_id=LIVE_TENANT),
        transport=transport,
        capability=None,
        capability_record=record_path,
    )
    return WorkflowV4Adapter(public=public)


class TenantBoundProbe(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ghl168-test-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.record = _record(self.tmp / "live.json", LIVE_TENANT)
        self.tenant = fake_tenant(LIVE_TENANT)
        self.other = fake_tenant(OTHER_TENANT)

    # -- (a) admitting record for the call tenant is live from call one ----

    def test_fresh_adapter_is_enabled_from_the_first_call(self) -> None:
        v4 = _v4(self.record, FakeTransport())

        for key in SURFACES:
            capability = v4.capability(key, tenant=self.tenant)
            self.assertTrue(capability.enabled, key)

        self.assertTrue(v4._enabled(UPDATE_OPERATION, self.tenant))
        route = workflow_route(v4, "update", tenant=LIVE_TENANT)
        self.assertEqual(route.route, WORKFLOW_ROUTE_PUBLIC, route.reason)

    def test_every_surface_routes_public_with_an_admitting_record(self) -> None:
        v4 = _v4(self.record, FakeTransport())

        for key in SURFACES:
            route = workflow_route(v4, key, tenant=LIVE_TENANT)
            self.assertEqual(route.route, WORKFLOW_ROUTE_PUBLIC, key)

    # -- (b) a record for another tenant stays denied ---------------------

    def test_record_for_a_different_tenant_stays_denied(self) -> None:
        foreign = _record(self.tmp / "foreign.json", OTHER_TENANT)
        v4 = _v4(foreign, FakeTransport())

        for key in SURFACES:
            capability = v4.capability(key, tenant=self.tenant)
            self.assertFalse(capability.enabled, key)
            self.assertIsNotNone(capability.activation_blocked, key)
            route = workflow_route(v4, key, tenant=LIVE_TENANT)
            self.assertEqual(route.route, WORKFLOW_ROUTE_PRIVATE, key)

        self.assertFalse(v4._enabled(UPDATE_OPERATION, self.tenant))

    def test_unbound_probe_denies_even_after_a_tenant_scoped_read(self) -> None:
        """The F1 shape: no tenant means deny, never "whichever loaded last"."""

        transport = FakeTransport([resp(200, _DEFINITION_BODY)])
        v4 = _v4(self.record, transport)
        result = v4.read_definition(tenant=self.tenant, workflow_id="wf_synthetic_0001")
        self.assertEqual(result.status.value, "ok")

        capability = v4.capability("update")
        self.assertFalse(capability.enabled)
        self.assertIsNotNone(capability.activation_blocked)
        route = workflow_route(v4, "update")
        self.assertEqual(route.route, WORKFLOW_ROUTE_PRIVATE, route.reason)

    # -- (c) ordering never changes the verdict ---------------------------

    def test_ordering_does_not_change_the_verdict(self) -> None:
        before = _v4(self.record, FakeTransport())
        baseline = {key: workflow_route(before, key, tenant=LIVE_TENANT).route
                    for key in SURFACES}
        self.assertTrue(all(route == WORKFLOW_ROUTE_PUBLIC for route in baseline.values()))

        after = _v4(self.record, FakeTransport([resp(200, _DEFINITION_BODY)]))
        read = after.read_definition(tenant=self.tenant, workflow_id="wf_synthetic_0001")
        self.assertEqual(read.status.value, "ok")
        followed = {key: workflow_route(after, key, tenant=LIVE_TENANT).route
                    for key in SURFACES}
        self.assertEqual(baseline, followed)

    def test_a_foreign_read_cannot_enable_the_live_tenant(self) -> None:
        foreign = _record(self.tmp / "foreign.json", OTHER_TENANT)
        transport = FakeTransport([resp(200, _DEFINITION_BODY)])
        v4 = _v4(foreign, transport)

        # A denied read never reaches transport, so no gate is even loaded.
        denied = v4.read_definition(tenant=self.tenant, workflow_id="wf_synthetic_0001")
        self.assertNotEqual(denied.status.value, "ok")
        self.assertFalse(v4._enabled(UPDATE_OPERATION, self.tenant))
        self.assertFalse(v4._enabled(READ_OPERATION, self.tenant))

    def test_disabled_receipt_is_bound_to_the_call_tenant(self) -> None:
        foreign = _record(self.tmp / "foreign.json", OTHER_TENANT)
        v4 = _v4(foreign, FakeTransport())

        result = v4.update_definition(
            tenant=self.tenant,
            workflow_id="wf_synthetic_0001",
            intent={"set_fields": {"name": "Synthetic Flow"}},
            approval={"ref": "approval-synthetic-0001"},
            expected_revision=1,
        )
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertEqual(result.evidence["operation_id"], UPDATE_OPERATION)


class F6WorkflowListVersion(unittest.TestCase):
    """F6: the registry claims v3; the recorded live 200 used 2021-07-28.

    The discrepancy is recorded, the row is left untouched, and the blocker is
    named.  A new live call is the only thing that can settle which Version the
    endpoint accepts -- this unit never makes one.
    """

    def setUp(self) -> None:
        self.repo = Path(__file__).resolve().parents[4]
        self.evidence = self.repo / "evidence" / "W23" / "f6-workflows-list-version.md"

    def test_registry_row_is_unchanged(self) -> None:
        row = OPERATIONS["workflows.list"]
        self.assertEqual(row.version, "v3")
        self.assertEqual(row.blocker, "A-UNVERIFIED")

    def test_discrepancy_is_recorded_with_a_named_blocker(self) -> None:
        self.assertTrue(self.evidence.is_file(), f"missing {self.evidence}")
        text = self.evidence.read_text(encoding="utf-8")
        for fragment in (
            "B-WORKFLOWS-LIST-VERSION",
            "2021-07-28",
            "v3",
            "workflows.list",
            "GHL_UPDATES_live-ledger.md",
            "line 759",
        ):
            self.assertIn(fragment, text, fragment)

    def test_registry_points_at_the_blocker(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "cli_anything"
            / "gohighlevel"
            / "public"
            / "operations.py"
        ).read_text(encoding="utf-8")
        self.assertIn("B-WORKFLOWS-LIST-VERSION", source)


if __name__ == "__main__":
    unittest.main()
