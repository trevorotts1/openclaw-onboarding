"""Shared helpers for the Agent Studio (WF29) tests.

Every transport response is scripted and every identifier is synthetic.  No
live tenant, token, contact or customer value appears here.

The operation rows below are built from ``DOCUMENTED_ROW_REQUESTS`` -- the
transcription of ``29-ghl-convert-and-flow/references/agent-studio.md``
(verified 2026-08-03) -- because WF00's ``public/operations.py`` does not carry
the studio family yet.  They are SHAPE DOUBLES for the frozen interface, not a
wire contract: production refuses without the real frozen rows
(``StudioOperationRowMissing``).  The source records the Version for these
operations as UNVERIFIED, so every row carries ``VERSION_BLOCKER``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Mapping, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    approval,
    fake_auth,
    fake_tenant,
    resp,
)

from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter  # noqa: E402
from cli_anything.gohighlevel.public.agent_studio import (  # noqa: E402
    DOCUMENTED_ROW_REQUESTS,
    DOC_URL,
    OPERATION_IDS,
    VERSION_BLOCKER,
    AgentStudioAdapter,
)
from cli_anything.gohighlevel.public.auth import AuthKind  # noqa: E402
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.operations import OperationRow  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402

OTHER_TENANT = "loc_synthetic_0002"
#: The Version literal the source reference's cURL templates use for this app.
#: It lives HERE, not in the package: the package may carry no global version
#: default, and the source records the value as UNVERIFIED per operation.
STUDIO_DOCUMENTED_VERSION = "2021-04-15"
FIXTURES = os.path.join(_HERE, "fixtures", "agent_studio")
ALLOWED_TOOLS = ("conversation.greet", "conversation.greet.warm", "crm.contact.lookup")


def studio_rows() -> dict[str, OperationRow]:
    """The documented shape of the seven rows WF00 still has to freeze."""

    rows: dict[str, OperationRow] = {}
    for logical, request in DOCUMENTED_ROW_REQUESTS.items():
        operation_id = OPERATION_IDS[logical]
        rows[operation_id] = OperationRow(
            operation_id=operation_id,
            method=request["method"],
            path_template=request["path_template"],
            version=STUDIO_DOCUMENTED_VERSION,
            version_alternates=(),
            documented_level="D",
            route_class="public_direct",
            auth_kinds=(AuthKind.location_pit,),
            tenant_binding=request["tenant_binding"],
            write=bool(request["write"]),
            approval_required=bool(request["approval_required"]),
            scopes_candidate=tuple(request["scopes_candidate"]),
            doc_url=DOC_URL,
            doc_fetch_date="2026-08-03",
            blocker=VERSION_BLOCKER,
            readback_plan=None,
            required_query=tuple(request.get("required_query", ())),
        )
    return rows


def gate_for(
    rows: Mapping[str, OperationRow],
    tenant: str = SYNTHETIC_TENANT,
    *,
    enabled: Sequence[str] | None = None,
) -> CapabilityGate:
    """A tenant-bound gate; ``enabled`` names operation ids (None means all)."""

    gate = CapabilityGate(tenant=tenant)
    wanted = None if enabled is None else set(enabled)
    for operation_id, row in rows.items():
        if wanted is not None and operation_id not in wanted:
            continue
        capability = Capability(
            operation_id=operation_id,
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            canary_verified=True,
        )
        gate.enable(capability, write=bool(row.write))
    return gate


def studio_adapter(
    transport: FakeTransport,
    *,
    tenant: str = SYNTHETIC_TENANT,
    rows: Mapping[str, OperationRow] | None = None,
    enabled: Sequence[str] | None = None,
    deny_all: bool = False,
) -> tuple[AgentStudioAdapter, PublicGhlAdapter]:
    rows = rows if rows is not None else studio_rows()
    gate = CapabilityGate(tenant=tenant) if deny_all else gate_for(
        rows, tenant, enabled=enabled
    )
    public = PublicGhlAdapter(
        auth=fake_auth(location_id=tenant),
        operations=rows,
        transport=transport,
        capability=gate,
        readbacks=ReadbackRegistry(),
    )
    return AgentStudioAdapter(public=public), public


def public_tenant(location_id: str = SYNTHETIC_TENANT):
    return fake_tenant(location_id)


def approval_ref():
    return approval()


def fixture(name: str) -> Any:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


def agent_document(
    *,
    name: str = "Synthetic Flow Agent",
    staging_id: str | None = "ver_synthetic_staging_0001",
    production_id: str | None = "ver_synthetic_production_0001",
    tenant: str = SYNTHETIC_TENANT,
    graph: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """An agent payload with the requested staging/production identities."""

    document: dict[str, Any] = {
        "id": "agent_synthetic_0001",
        "locationId": tenant,
        "name": name,
        "status": "active",
        "versions": [],
    }
    base_graph = dict(graph or _base_graph())
    if production_id is not None:
        document["versions"].append(
            {"id": production_id, "status": "production", **_base_graph()}
        )
    if staging_id is not None:
        document["versions"].append(
            {"id": staging_id, "status": "staging", **dict(base_graph)}
        )
    return document


def _base_graph() -> dict[str, Any]:
    return {
        "entryNodeId": "node_start",
        "nodes": [
            {"id": "node_start", "type": "start", "tool": "conversation.greet"},
            {"id": "node_lookup", "type": "tool", "tool": "crm.contact.lookup"},
        ],
        "edges": [{"source": "node_start", "target": "node_lookup"}],
        "variables": [{"name": "topic"}],
        "configuration": {"locale": "en-US"},
    }


def json_body(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def ok(payload: Any) -> Any:
    return resp(200, json_body(payload))


def paged(*agents: Mapping[str, Any], tenant: str = SYNTHETIC_TENANT) -> Any:
    return resp(200, json_body({"agents": list(agents), "locationId": tenant}))


def execution_response(
    *,
    execution_id: str = "exec_synthetic_0001",
    status: str = "completed",
    output: Mapping[str, Any] | None = None,
) -> Any:
    return resp(
        200,
        json_body(
            {
                "executionId": execution_id,
                "status": status,
                "output": dict(output or {"text": "synthetic answer"}),
            }
        ),
    )
