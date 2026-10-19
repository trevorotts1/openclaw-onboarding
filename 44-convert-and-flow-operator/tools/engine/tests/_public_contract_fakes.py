"""Shared fakes for the frozen public-contract tests.

Every test in this package runs offline: ``FakeTransport`` records each request
and replays scripted ``TransportResponse`` objects, and the one header-level
test injects an opener stub into ``RequestsTransport`` so urllib never opens a
socket.  No token, PIT, location id or customer value from a real account ever
appears here -- the fixtures are synthetic strings only.
"""

from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# ---------------------------------------------------------------------------
# real registry probe (GU-004 section 5).  Row conformance tests stay BLOCKED
# until this module imports cleanly and exposes a non-empty OPERATIONS.
# ---------------------------------------------------------------------------

FROZEN_OPERATIONS: Mapping[str, Any] = {}
REGISTRY_ERROR: str | None = None

try:  # pragma: no cover - depends on the W04 registry lane
    from cli_anything.gohighlevel.public.operations import (
        OPERATIONS as _FROZEN_OPERATIONS,
    )

    FROZEN_OPERATIONS = _FROZEN_OPERATIONS
except Exception as exc:  # noqa: BLE001 - absence and a raising module both block
    REGISTRY_ERROR = f"{type(exc).__name__}: {exc}"

REGISTRY_PRESENT = bool(FROZEN_OPERATIONS)
REGISTRY_REASON = (
    "BLOCKED: public/operations.py registry not usable at import time "
    f"({REGISTRY_ERROR or 'OPERATIONS is empty'}); assertions are frozen as written"
)


def _load_adapter():
    """Import the frozen adapter surface.

    The adapter carries a pre-merge bridge for an *absent* registry.  When the
    registry module exists but raises at import, neutralise it (empty stub) so
    the contract tests still exercise the frozen adapter interface; the stub
    never satisfies a registry conformance assertion, which stays BLOCKED on
    the real module per ``REGISTRY_REASON``.
    """

    try:
        from cli_anything.gohighlevel.public.adapter import (
            ApprovalRef,
            PublicGhlAdapter,
        )

        return ApprovalRef, PublicGhlAdapter
    except Exception:
        if REGISTRY_ERROR is None:
            raise
        stub = types.ModuleType("cli_anything.gohighlevel.public.operations")
        stub.OPERATIONS = {}
        stub.OperationRegistry = dict
        sys.modules["cli_anything.gohighlevel.public.operations"] = stub
        for name in list(sys.modules):
            if name.startswith("cli_anything.gohighlevel.public."):
                if name == "cli_anything.gohighlevel.public.operations":
                    continue
                del sys.modules[name]
            elif name == "cli_anything.gohighlevel.public":
                del sys.modules[name]
        parent = sys.modules.get("cli_anything.gohighlevel")
        if parent is not None and hasattr(parent, "public"):
            delattr(parent, "public")
        from cli_anything.gohighlevel.public.adapter import (
            ApprovalRef,
            PublicGhlAdapter,
        )

        return ApprovalRef, PublicGhlAdapter


ApprovalRef, PublicGhlAdapter = _load_adapter()

from cli_anything.gohighlevel.public.auth import AuthContext, AuthKind, TenantBinding
from cli_anything.gohighlevel.public.capability import Capability, CapabilityGate
from cli_anything.gohighlevel.public.idempotency import IdempotencyKey
from cli_anything.gohighlevel.public.readback import ReadbackRegistry, ReadbackSpec
from cli_anything.gohighlevel.public.transport import TransportResponse

SYNTHETIC_TENANT = "loc_synthetic_0001"
SYNTHETIC_OTHER_TENANT = "loc_synthetic_0002"
SYNTHETIC_TOKEN = "synthetic-token-value"
SYNTHETIC_APPROVAL = "approval-synthetic-0001"
SYNTHETIC_CONTACT = "contact_synthetic_0001"

#: Frozen per-operation row shape (GU-004 section 1.4).  Tests construct rows
#: with this so the adapter is exercised through the frozen interface even
#: before ``public/operations.py`` lands.
@dataclass(frozen=True)
class Row:
    operation_id: str
    method: str
    path_template: str
    version: str | None = "v3"
    version_alternates: tuple[str, ...] = ()
    documented_level: str = "D"
    route_class: str = "public_direct"
    auth_kinds: tuple[AuthKind, ...] = (AuthKind.location_pit,)
    tenant_binding: str = "none"
    write: bool = False
    approval_required: bool = False
    scopes_candidate: tuple[str, ...] = ()
    doc_url: str | None = "https://example.invalid/doc"
    doc_fetch_date: str | None = "2026-10-18"
    blocker: str | None = None


def row(operation_id: str, **overrides: Any) -> Row:
    return Row(operation_id=operation_id, **overrides)


def registry(*rows: Row) -> dict[str, Row]:
    return {item.operation_id: item for item in rows}


def fake_auth(
    *,
    kind: AuthKind = AuthKind.location_pit,
    location_id: str | None = SYNTHETIC_TENANT,
    name: str = "GHL_API_KEY",
    value: str = SYNTHETIC_TOKEN,
) -> AuthContext:
    if kind in (AuthKind.agency_pit, AuthKind.firebase_internal):
        location_id = None
    label = "oauth" if kind is AuthKind.oauth else "env"

    def resolve(secret_name: str) -> str:
        assert secret_name == name, secret_name
        return value

    return AuthContext(
        kind=kind,
        location_id=location_id,
        resolve_secret=resolve,
        source=f"{label}:{name}",
    )


def fake_tenant(location_id: str = SYNTHETIC_TENANT) -> TenantBinding:
    return TenantBinding(location_id=location_id, source="request")


def resp(
    status: int | None = 200,
    body: bytes = b'{"ok":true}',
    headers: Mapping[str, str] | None = None,
    error_kind: str = "none",
) -> TransportResponse:
    return TransportResponse(
        status=status,
        headers=dict(headers or {}),
        body=body,
        error_kind=error_kind,  # type: ignore[arg-type]
        elapsed_s=0.01,
    )


class FakeTransport:
    """Records every request; replays scripted responses in order."""

    def __init__(self, responses: Sequence[TransportResponse] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: Mapping[str, str],
        query: Mapping[str, object] | None,
        body: Mapping[str, object] | None,
        timeout_s: float,
    ) -> TransportResponse:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "version": version,
                "headers": dict(headers or {}),
                "query": None if query is None else dict(query),
                "body": None if body is None else dict(body),
                "timeout_s": timeout_s,
            }
        )
        if self.responses:
            return self.responses.pop(0)
        return resp()

    @property
    def call_count(self) -> int:
        return len(self.requests)

    @property
    def last(self) -> dict[str, Any]:
        assert self.requests, "no transport call was recorded"
        return self.requests[-1]


class StubResponse:
    """Minimal ``urlopen`` return value for the injected-opener test."""

    def __init__(
        self,
        status: int = 200,
        body: bytes = b'{"ok":true}',
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._status = status
        self._body = body
        self.headers = dict(headers or {"Content-Type": "application/json"})

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self._status

    def __enter__(self) -> "StubResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class RecordingOpener:
    """Callable opener: captures the built urllib Request, never opens a socket."""

    def __init__(self, response: StubResponse | None = None) -> None:
        self.requests: list[Any] = []
        self._response = response or StubResponse()

    def __call__(self, request: Any, timeout: float | None = None) -> StubResponse:
        self.requests.append(request)
        return self._response

    @property
    def last(self) -> Any:
        assert self.requests, "no request was built"
        return self.requests[-1]


def enabled_gate(
    rows: Sequence[Row], *, tenant: str = SYNTHETIC_TENANT
) -> CapabilityGate:
    """A gate where every supplied row has cleared the frozen evidence rules."""

    gate = CapabilityGate(tenant=tenant)
    for item in rows:
        capability = Capability(
            operation_id=item.operation_id,
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            canary_verified=True,
        )
        gate.enable(capability, write=bool(item.write))
    return gate


def make_adapter(
    transport: FakeTransport,
    operations: Mapping[str, Row],
    *,
    auth: AuthContext | None = None,
    gate: CapabilityGate | None = None,
    readbacks: ReadbackRegistry | None = None,
    max_attempts: int = 1,
) -> PublicGhlAdapter:
    return PublicGhlAdapter(
        auth=auth or fake_auth(),
        operations=operations,  # type: ignore[arg-type]
        transport=transport,
        capability=gate,
        readbacks=readbacks if readbacks is not None else ReadbackRegistry(),
        max_attempts=max_attempts,
    )


def issue_key(operation_id: str) -> str:
    return IdempotencyKey.issue(operation_id).value


def approval() -> ApprovalRef:
    return ApprovalRef(ref=SYNTHETIC_APPROVAL)


def readback_spec(
    *,
    operation_id: str = "contacts.get",
    contact_id: str = SYNTHETIC_CONTACT,
    expect: Mapping[str, Any] | None = None,
) -> ReadbackSpec:
    return ReadbackSpec(
        operation_id=operation_id,
        target_params={"contactId": contact_id},
        expect=dict(expect if expect is not None else {"id": contact_id}),
    )
