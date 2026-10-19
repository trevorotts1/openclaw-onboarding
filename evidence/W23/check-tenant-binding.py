#!/usr/bin/env python3
"""GHL-168 machine check: the V4 route/enable probe is tenant-bound.

Read-only. No network, no credential read, no live call. Exits 0 only when the
F1/F2 fix still holds and the F6 discrepancy is still recorded as a named
blocker rather than a guess.

Run from the repo root:
    python3 -I evidence/W23/check-tenant-binding.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "44-convert-and-flow-operator" / "tools" / "engine"
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel.public.adapter import (  # noqa: E402
    PublicGhlAdapter,
)
from cli_anything.gohighlevel.public.auth import (  # noqa: E402
    AuthContext,
    AuthKind,
    TenantBinding,
)
from cli_anything.gohighlevel.public.operations import OPERATIONS  # noqa: E402
from cli_anything.gohighlevel.public.transport import (  # noqa: E402
    TransportResponse,
)
from cli_anything.gohighlevel.public.workflow_v4 import (  # noqa: E402
    CREATE_OPERATION,
    DELETE_OPERATION,
    READ_OPERATION,
    STATUS_OPERATION,
    UPDATE_OPERATION,
    WorkflowV4Adapter,
)
from cli_anything.gohighlevel.utils.workflow_builder import (  # noqa: E402
    workflow_route,
)

FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILURES.append(message)


def source(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


V4_SOURCE = "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/workflow_v4.py"
BUILDER = "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py"
CLI = "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py"
OPS = "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py"

LIVE_TENANT = "Mct54Bwi1KlNouGXQcDX"
OTHER_TENANT = "XCgFTEA1oDvsPnTqqgoB"
V4_OPERATIONS = (
    READ_OPERATION,
    CREATE_OPERATION,
    UPDATE_OPERATION,
    STATUS_OPERATION,
    DELETE_OPERATION,
)
SURFACES = ("definition.read", "create", "update", "status.change", "delete")

DEFINITION_BODY = json.dumps(
    {
        "workflow": {
            "id": "wf_check_0001",
            "name": "Check Flow",
            "version": 1,
            "actions": [],
            "triggers": [],
            "status": "draft",
        },
        "revision": 1,
    }
).encode()


# ---------------------------------------------------------------------------
# 1. Source: every probe passes a tenant.
# ---------------------------------------------------------------------------

v4_source = source(V4_SOURCE)
check(
    "def _enabled(\n        self, operation_id: str, tenant: TenantBinding | str | None\n    ) -> bool:"
    in v4_source,
    "workflow_v4.py: _enabled must take the call tenant",
)
check(
    "self._public.capability(operation_id, tenant=location_id).enabled"
    in v4_source,
    "workflow_v4.py: the enable probe must pass the tenant to the adapter",
)
check(
    v4_source.count("if not self._enabled(operation_id, tenant):") == 4,
    "workflow_v4.py: all four write surfaces must bind _enabled to the tenant",
)
check(
    "self._public.capability(operation_id).enabled" not in v4_source,
    "workflow_v4.py: an unbound enable probe reappeared",
)
check(
    "return CapabilityGate().get(operation_id)" in v4_source,
    "workflow_v4.py: an unbound capability probe must answer default-deny",
)
check(
    "operation_id, tenant=tenant.location_id" in v4_source,
    "workflow_v4.py: the disabled receipt must read the call tenant's record",
)

builder_source = source(BUILDER)
check(
    "def workflow_route(v4: Any, operation: str, *, tenant: Any = None) -> WorkflowRoute:"
    in builder_source,
    "workflow_builder.py: workflow_route must accept the tenant",
)
check(
    "capability = v4.capability(key, tenant=tenant)" in builder_source,
    "workflow_builder.py: the route probe must pass the tenant",
)
check(
    "v4.capability(key)\n" not in builder_source,
    "workflow_builder.py: an unbound route probe reappeared",
)
check(
    "workflow_route(self.public_v4, operation, tenant=self.loc)" in builder_source,
    "workflow_builder.py: CampaignBuilder.route_for must pass its location",
)

cli_source = source(CLI)
check(
    cli_source.count('workflow_route(v4, "definition.read", tenant=_loc(ctx))') == 2,
    "gohighlevel_cli.py: both definition.read routes must pass the tenant",
)
check(
    'workflow_route(v4, "update", tenant=location_id)' in cli_source,
    "gohighlevel_cli.py: the update route must pass the tenant",
)

# ---------------------------------------------------------------------------
# 2. Behaviour: fresh adapter, foreign tenant, ordering.
# ---------------------------------------------------------------------------


def _record(path: Path, tenant: str) -> Path:
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
        json.dumps({"record_version": 1, "tenant": tenant, "capabilities": rows}),
        encoding="utf-8",
    )
    return path


class _Transport:
    def __init__(self, response: TransportResponse | None = None) -> None:
        self.response = response or TransportResponse(
            status=200,
            headers={},
            body=DEFINITION_BODY,
            error_kind="none",
            elapsed_s=0.01,
        )
        self.requests: list[dict] = []

    def request(self, **kwargs) -> TransportResponse:
        self.requests.append(kwargs)
        return self.response


def _auth() -> AuthContext:
    return AuthContext(
        kind=AuthKind.location_pit,
        location_id=LIVE_TENANT,
        resolve_secret=lambda name: "synthetic-token-value",
        source="env:GHL_API_KEY",
    )


def _v4(record: Path, transport: _Transport) -> WorkflowV4Adapter:
    public = PublicGhlAdapter(
        auth=_auth(),
        transport=transport,
        capability=None,
        capability_record=record,
    )
    return WorkflowV4Adapter(public=public)


with tempfile.TemporaryDirectory(prefix="ghl168-check-") as tmp:
    root = Path(tmp)
    live_record = _record(root / "live.json", LIVE_TENANT)
    foreign_record = _record(root / "foreign.json", OTHER_TENANT)
    tenant = TenantBinding(location_id=LIVE_TENANT, source="check")

    fresh = _v4(live_record, _Transport())
    for key in SURFACES:
        check(
            fresh.capability(key, tenant=tenant).enabled,
            f"{key}: admitting record for the call tenant must be enabled from the first call",
        )
        check(
            workflow_route(fresh, key, tenant=LIVE_TENANT).route == "public_v4",
            f"{key}: admitting record must route public_v4 from the first call",
        )
    check(
        fresh._enabled(UPDATE_OPERATION, tenant),
        "fresh adapter: update must be enabled before any read",
    )

    foreign = _v4(foreign_record, _Transport())
    for key in SURFACES:
        check(
            not foreign.capability(key, tenant=tenant).enabled,
            f"{key}: a record for another tenant must stay denied",
        )
        check(
            workflow_route(foreign, key, tenant=LIVE_TENANT).route
            == "skill44_private_fallback",
            f"{key}: a record for another tenant must keep the private fallback",
        )

    ordered = _v4(live_record, _Transport())
    read = ordered.read_definition(tenant=tenant, workflow_id="wf_check_0001")
    check(read.status.value == "ok", "ordering control: the tenant read must succeed")
    for key in SURFACES:
        check(
            workflow_route(ordered, key, tenant=LIVE_TENANT).route == "public_v4",
            f"{key}: route verdict must not change after a tenant-scoped read",
        )
    check(
        ordered.capability("update").enabled is False,
        "an unbound probe must still deny after a tenant-scoped read",
    )

# ---------------------------------------------------------------------------
# 3. F6: the discrepancy is recorded, the row is untouched.
# ---------------------------------------------------------------------------

row = OPERATIONS["workflows.list"]
check(row.version == "v3", "workflows.list Version must stay v3 until a live call settles it")
check(row.blocker == "A-UNVERIFIED", "workflows.list blocker must stay A-UNVERIFIED")

f6 = REPO / "evidence" / "W23" / "f6-workflows-list-version.md"
check(f6.is_file(), "evidence/W23/f6-workflows-list-version.md is missing")
if f6.is_file():
    text = f6.read_text(encoding="utf-8")
    for fragment in (
        "B-WORKFLOWS-LIST-VERSION",
        "2021-07-28",
        "GHL_UPDATES_live-ledger.md",
        "line 759",
    ):
        check(fragment in text, f"F6 evidence lost {fragment!r}")
check(
    "B-WORKFLOWS-LIST-VERSION" in source(OPS),
    "operations.py no longer names the F6 blocker",
)

# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------

if FAILURES:
    print(f"RESULT: FAIL - {len(FAILURES)} of {CHECKS} checks failed")
    for failure in FAILURES:
        print(f"  - {failure}")
    raise SystemExit(1)

print(f"RESULT: PASS - {CHECKS} of {CHECKS} checks passed")
raise SystemExit(0)
