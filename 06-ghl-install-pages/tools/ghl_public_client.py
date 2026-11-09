#!/usr/bin/env python3
"""ghl_public_client.py — Skill 06's single route into the frozen public adapter.

WHY THIS EXISTS
---------------
W18 (``evidence/W18/v4-and-client-path-verification.md`` §4.4/§5) found Skill 06
calling ``services.leadconnectorhq.com`` with its own hardcoded paths and Version
constants, bypassing ``cli_anything.gohighlevel.public.PublicGhlAdapter``.  A raw
call cannot be capability-gated, cannot be tenant-checked and carries whatever
Version the caller typed.

This module is the one call path for the operations whose *called route* matches
a frozen registry row.  Method, path, Version, auth class and tenant binding come
from the row inside ``PublicGhlAdapter.call``; this module owns only the transport
seam (the ``(Request, timeout)`` opener the Skill 06 tests already inject) and the
browser User-Agent that ``services.*`` requires (Cloudflare 1010 otherwise).

NOT A GATE BYPASS
-----------------
``make_adapter`` never supplies a capability gate unless the caller passes one.
With no gate the adapter loads the checked-in capability record, which is
default-deny (and, on the base revision, bound to a different tenant), so a call
is refused *before transport*.  Tests inject an explicit ``CapabilityGate``; the
production default stays default-deny.

NAMED GAPS AND RECONCILED FUNNEL READS
-------------------------------------
Routes whose called path has no registry row, or whose shape the adapter cannot
carry (multipart upload; internal SPA authoring), are NOT invented here.  They
are recorded in ``ghl_route_gaps.py`` with file:line and reason.

The three funnel reads are reconciled (WF24-CP01): GET /funnels/funnel/list,
GET /funnels/page and GET /funnels/page/count. The helpers below call them
through the central adapter, but refuse BEFORE transport while the current
frozen row still declares an older path. That refusal is the honest state, not
a fallback: the central row is WF00-owned and the correction request travels
with the registration row. Once the row matches, the same helpers route with no
code change.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping, Optional

# ── Frozen operation ids (no method/path/Version literals live here) ─────────

MEDIA_FILES_LIST = "media.files.list"
SURVEYS_LIST = "surveys.list"

FUNNEL_LIST = "funnels.list"
FUNNEL_PAGES_LIST = "funnels.pages.list"
FUNNEL_PAGES_COUNT = "funnels.pages.count"

#: Reconciled funnel read contract (WF24-CP01), mirrored here because Skill 06
#: ships standalone. The focused test asserts this mirror equals
#: tests/fixtures/ghl_compat/funnel_read_contracts.json, so drift fails loudly.
RECONCILED_FUNNEL_READS = {
    FUNNEL_LIST: {
        "method": "GET",
        "path": "/funnels/funnel/list",
        "required_query": ("locationId", "offset", "limit"),
        "optional_query": ("type", "category", "parentId", "name"),
    },
    FUNNEL_PAGES_LIST: {
        "method": "GET",
        "path": "/funnels/page",
        "required_query": ("locationId", "funnelId", "limit", "offset"),
        "optional_query": ("name",),
    },
    FUNNEL_PAGES_COUNT: {
        "method": "GET",
        "path": "/funnels/page/count",
        "required_query": ("locationId", "funnelId"),
        "optional_query": (),
    },
}

DEFAULT_BASE_URL = "https://services.leadconnectorhq.com"

# services.* 403s (Cloudflare 1010) the bare-Python default UA. The proven
# browser UA is a transport concern, not an operation contract.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

ENGINE_ROOT_ENV = "GHL_PUBLIC_ENGINE_ROOT"


class PublicRouteError(RuntimeError):
    """A routed public call failed. Never carries a credential value.

    ``rule`` is the adapter's refusal rule (e.g. ``capability_disabled``) when
    the call was refused before transport; ``http_status`` is set otherwise.
    """

    def __init__(
        self,
        operation_id: str,
        *,
        status: str,
        rule: Optional[str] = None,
        http_status: Optional[int] = None,
    ) -> None:
        self.operation_id = operation_id
        self.status = status
        self.rule = rule
        self.http_status = http_status
        detail = rule or ("HTTP %s" % http_status if http_status else status)
        super().__init__(
            "public route %s failed: %s" % (operation_id, detail)
        )


# ── Engine discovery (lazy; Skill 06 ships standalone) ───────────────────────

_ENGINE: Optional[dict] = None


def _engine_root() -> str:
    env = os.environ.get(ENGINE_ROOT_ENV)
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    walk = here
    for _ in range(6):
        candidate = os.path.join(
            walk, "44-convert-and-flow-operator", "tools", "engine"
        )
        if os.path.isdir(os.path.join(candidate, "cli_anything", "gohighlevel")):
            return candidate
        parent = os.path.dirname(walk)
        if parent == walk:
            break
        walk = parent
    raise PublicRouteError(
        "engine", status="unavailable", rule="public_engine_not_found"
    )


def engine():
    """Import the frozen public package once. Returns a dict of seams."""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    root = _engine_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from cli_anything.gohighlevel.public import PublicGhlAdapter  # noqa: E402
        from cli_anything.gohighlevel.public.auth import (  # noqa: E402
            AuthContext,
            AuthKind,
            TenantBinding,
        )
        from cli_anything.gohighlevel.public.capability import (  # noqa: E402
            Capability,
            CapabilityGate,
        )
        from cli_anything.gohighlevel.public.errors import (  # noqa: E402
            ContractViolation,
        )
        from cli_anything.gohighlevel.public.operations import (  # noqa: E402
            OPERATIONS,
        )
        from cli_anything.gohighlevel.public.result import Status  # noqa: E402
        from cli_anything.gohighlevel.public.transport import (  # noqa: E402
            TransportResponse,
            encode_query,
        )
    except Exception as exc:  # noqa: BLE001 - typed at the route boundary
        raise PublicRouteError(
            "engine", status="unavailable", rule="public_engine_import_failed"
        ) from exc

    _ENGINE = {
        "PublicGhlAdapter": PublicGhlAdapter,
        "AuthContext": AuthContext,
        "AuthKind": AuthKind,
        "TenantBinding": TenantBinding,
        "Capability": Capability,
        "CapabilityGate": CapabilityGate,
        "ContractViolation": ContractViolation,
        "OPERATIONS": OPERATIONS,
        "Status": Status,
        "TransportResponse": TransportResponse,
        "encode_query": encode_query,
    }
    return _ENGINE


# ── Transport seam ───────────────────────────────────────────────────────────

class OpenerTransport:
    """Adapter ``Transport`` over the ``(Request, timeout) -> response`` opener.

    Tests already inject this opener shape, so routing does not add a second
    mocking seam. The response body of the last request is retained for the
    caller to parse (``OperationResult`` carries a receipt, not the body).
    """

    def __init__(
        self,
        opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = BROWSER_UA,
    ) -> None:
        self._opener = opener
        self._base_url = str(base_url).rstrip("/")
        self._user_agent = user_agent
        self.last_response: Any = None

    def request(
        self,
        *,
        method: str,
        url: str,
        version: Optional[str],
        headers: Mapping[str, str],
        query: Optional[Mapping[str, object]],
        body: Optional[Mapping[str, object]],
        timeout_s: float,
    ) -> Any:
        seams = engine()
        TransportResponse = seams["TransportResponse"]

        target = self._base_url + url
        encoded = seams["encode_query"](query)
        if encoded:
            target += ("&" if "?" in target else "?") + encoded

        data = None
        if body is not None:
            data = json.dumps(
                body, sort_keys=True, separators=(",", ":"), default=str
            ).encode("utf-8")

        req = urllib.request.Request(target, data=data, method=method.upper())
        for name, value in dict(headers or {}).items():
            if name.lower() in ("version", "cookie", "proxy-authorization"):
                continue
            req.add_header(str(name), str(value))
        if version is not None:
            req.add_header("Version", str(version))
        if data is not None:
            req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", self._user_agent)

        opener = self._opener or urllib.request.urlopen
        try:
            response = opener(req, timeout_s)
            status = int(response.getcode())
            raw = response.read()
            response_headers = {}
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            response_headers = {}
        except (TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            return TransportResponse(
                status=None,
                headers={},
                body=b"",
                error_kind=(
                    "timeout" if isinstance(reason, TimeoutError) else "connection"
                ),
            )
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        result = TransportResponse(
            status=status, headers=response_headers, body=raw
        )
        self.last_response = result
        return result


def parse_body(transport: OpenerTransport) -> Any:
    """Parse the body of the last transport response; None when empty/bad JSON."""
    response = getattr(transport, "last_response", None)
    if response is None or not response.body:
        return None
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


# ── Adapter construction ─────────────────────────────────────────────────────

def make_adapter(
    location_id: str,
    pit: str,
    *,
    opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
    transport: Any = None,
    capability: Any = None,
    capability_record: Optional[str] = None,
    timeout: float = 60.0,
):
    """Build a tenant-bound adapter. No gate shipped here means default-deny."""
    if not location_id or not str(location_id).strip():
        raise ValueError("location_id is required and must be non-empty")
    if not pit or not str(pit).strip():
        raise ValueError("pit is required and must be non-empty")
    seams = engine()
    if transport is None:
        transport = OpenerTransport(opener)
    auth = seams["AuthContext"](
        kind=seams["AuthKind"].location_pit,
        location_id=str(location_id),
        resolve_secret=lambda name: str(pit),
        # The frozen auth seam parses ``<label>:<NAME>``; the value is supplied
        # by the caller's argument, never read or recorded here.
        source="env:GHL_LOCATION_PIT",
    )
    adapter = seams["PublicGhlAdapter"](
        auth=auth,
        transport=transport,
        capability=capability,
        capability_record=capability_record,
        default_timeout_s=float(timeout),
    )
    return adapter, transport


def call_public(
    adapter: Any,
    transport: OpenerTransport,
    operation_id: str,
    location_id: str,
    *,
    path_params: Optional[Mapping[str, str]] = None,
    query: Optional[Mapping[str, object]] = None,
    timeout: Optional[float] = None,
) -> Any:
    """One read through the adapter; returns the parsed JSON body.

    Raises ``PublicRouteError`` for any non-ok status, including a
    pre-transport capability refusal (``rule=capability_disabled``).
    """
    seams = engine()
    tenant = seams["TenantBinding"](
        location_id=str(location_id), source="skill06:call"
    )
    kwargs: dict[str, Any] = {
        "operation_id": operation_id,
        "tenant": tenant,
    }
    if path_params:
        kwargs["path_params"] = dict(path_params)
    if query:
        kwargs["query"] = dict(query)
    if timeout is not None:
        kwargs["timeout_s"] = float(timeout)
    try:
        result = adapter.call(**kwargs)
    except seams["ContractViolation"] as exc:
        # A frozen-contract refusal (bad path params, missing readback, ...) is
        # still a typed route refusal at this boundary, never a raw exception
        # leaking past the caller's named error class.
        raise PublicRouteError(
            operation_id,
            status="contract_violation",
            rule=getattr(exc, "rule", "contract_violation"),
        ) from exc
    status = getattr(result.status, "value", str(result.status))
    if status != "ok":
        error = dict(result.error or {})
        raise PublicRouteError(
            operation_id,
            status=status,
            rule=error.get("rule"),
            http_status=result.http_status,
        )
    return parse_body(transport)


# ── Routed operation helpers ─────────────────────────────────────────────────

MEDIA_LIST_TYPES = ("file", "image", "video", "audio", "document")


class MediaTypeRequired(ValueError):
    """``type`` is required by GET /medias/files; raised before any transport."""


def normalize_media_type(media_type: Optional[str]) -> str:
    normalized = str(media_type).strip().lower() if media_type is not None else ""
    if not normalized:
        raise MediaTypeRequired(
            "media LIST requires an explicit type: one of "
            + ", ".join(MEDIA_LIST_TYPES)
        )
    if normalized not in MEDIA_LIST_TYPES:
        raise MediaTypeRequired(
            "media LIST type %r is not supported; use one of %s"
            % (media_type, ", ".join(MEDIA_LIST_TYPES))
        )
    return normalized


def list_media_files(
    location_id: str,
    pit: str,
    media_type: Optional[str],
    *,
    opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
    capability: Any = None,
    capability_record: Optional[str] = None,
    timeout: float = 60.0,
) -> dict:
    """GET /medias/files through ``media.files.list`` (required ``type``).

    The type gate runs before the adapter is built, so a missing/out-of-set
    value never reaches a transport.
    """
    normalized = normalize_media_type(media_type)
    if not location_id or not str(location_id).strip():
        raise ValueError("location_id is required and must be non-empty")
    if not pit or not str(pit).strip():
        raise ValueError("pit is required and must be non-empty")
    adapter, transport = make_adapter(
        location_id,
        pit,
        opener=opener,
        capability=capability,
        capability_record=capability_record,
        timeout=timeout,
    )
    body = call_public(
        adapter,
        transport,
        MEDIA_FILES_LIST,
        location_id,
        query={"type": normalized, "locationId": str(location_id)},
        timeout=timeout,
    )
    if not isinstance(body, dict) or not isinstance(body.get("files"), list):
        raise PublicRouteError(
            MEDIA_FILES_LIST, status="validation_error", rule="payload_no_files"
        )
    return {
        "files": body["files"],
        "count": body.get("count"),
        "traceId": body.get("traceId"),
        "http": 200,
    }


def _funnel_query(operation_id: str, *, location_id: str, **values: object) -> dict:
    """Exact query mapping for one reconciled funnel read (contract order)."""
    spec = RECONCILED_FUNNEL_READS[operation_id]
    declared = set(spec["required_query"]) | set(spec["optional_query"])
    unknown = sorted(set(values) - declared)
    if unknown:
        raise PublicRouteError(
            operation_id, status="validation_error", rule="unknown_query_parameter"
        )
    query = {
        "locationId": str(location_id),
        "offset": int(values.get("offset", 0)),
        "limit": int(values.get("limit", 100)),
    }
    if "funnelId" in spec["required_query"]:
        funnel_id = values.get("funnelId")
        if not funnel_id or not str(funnel_id).strip():
            raise PublicRouteError(
                operation_id, status="validation_error", rule="funnel_id_required"
            )
        query["funnelId"] = str(funnel_id)
    for name in spec["optional_query"]:
        value = values.get(name)
        if value is not None and str(value).strip():
            query[name] = str(value)
    return query


def assert_reconciled_funnel_row(operation_id: str) -> None:
    """Refuse before transport while the frozen registry row is stale.

    The central row is WF00-owned. Emitting the old shape would be a mixed
    old/new request (IG-ROUTE-09), so the call fails loudly instead.
    """
    spec = RECONCILED_FUNNEL_READS[operation_id]
    registry = engine()["OPERATIONS"]
    row = registry.get(operation_id)
    if row is None:
        raise PublicRouteError(
            operation_id, status="contract_mismatch", rule="frozen_row_missing"
        )
    if (
        str(row.method).upper() != spec["method"]
        or str(row.path_template) != spec["path"]
    ):
        raise PublicRouteError(
            operation_id,
            status="contract_mismatch",
            rule="reconciled_path_mismatch",
        )


def list_funnels(
    location_id: str,
    pit: str,
    *,
    offset: int = 0,
    limit: int = 100,
    opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
    capability: Any = None,
    capability_record: Optional[str] = None,
    timeout: float = 60.0,
    **optional: object,
) -> dict:
    """One PUBLIC page of GET /funnels/funnel/list through the adapter."""
    query = _funnel_query(
        FUNNEL_LIST, location_id=location_id, offset=offset, limit=limit, **optional
    )
    assert_reconciled_funnel_row(FUNNEL_LIST)
    adapter, transport = make_adapter(
        location_id, pit, opener=opener, capability=capability,
        capability_record=capability_record, timeout=timeout,
    )
    body = call_public(
        adapter, transport, FUNNEL_LIST, location_id, query=query, timeout=timeout
    )
    if not isinstance(body, dict) or not isinstance(body.get("funnels"), list):
        raise PublicRouteError(
            FUNNEL_LIST, status="validation_error", rule="payload_no_funnels"
        )
    return {
        "funnels": body["funnels"],
        "count": body.get("count"),
        "traceId": body.get("traceId"),
        "http": 200,
    }


def list_funnel_pages(
    location_id: str,
    pit: str,
    funnel_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
    opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
    capability: Any = None,
    capability_record: Optional[str] = None,
    timeout: float = 60.0,
    **optional: object,
) -> Any:
    """One PUBLIC page of GET /funnels/page through the adapter."""
    query = _funnel_query(
        FUNNEL_PAGES_LIST,
        location_id=location_id,
        funnelId=funnel_id,
        offset=offset,
        limit=limit,
        **optional,
    )
    assert_reconciled_funnel_row(FUNNEL_PAGES_LIST)
    adapter, transport = make_adapter(
        location_id, pit, opener=opener, capability=capability,
        capability_record=capability_record, timeout=timeout,
    )
    return call_public(
        adapter, transport, FUNNEL_PAGES_LIST, location_id,
        query=query, timeout=timeout,
    )


def count_funnel_pages(
    location_id: str,
    pit: str,
    funnel_id: str,
    *,
    opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
    capability: Any = None,
    capability_record: Optional[str] = None,
    timeout: float = 60.0,
) -> dict:
    """GET /funnels/page/count through the adapter; returns the numeric total."""
    query = _funnel_query(
        FUNNEL_PAGES_COUNT, location_id=location_id, funnelId=funnel_id
    )
    assert_reconciled_funnel_row(FUNNEL_PAGES_COUNT)
    adapter, transport = make_adapter(
        location_id, pit, opener=opener, capability=capability,
        capability_record=capability_record, timeout=timeout,
    )
    body = call_public(
        adapter, transport, FUNNEL_PAGES_COUNT, location_id,
        query=query, timeout=timeout,
    )
    source_key = ""
    value = None
    if isinstance(body, bool):
        value = None
    elif isinstance(body, int):
        source_key, value = "<bare integer>", body
    elif isinstance(body, dict):
        for key in ("count", "total", "totalCount"):
            if body.get(key) is not None:
                source_key, value = key, body[key]
                break
    if value is None or isinstance(value, bool):
        raise PublicRouteError(
            FUNNEL_PAGES_COUNT, status="validation_error", rule="payload_no_count"
        )
    try:
        total = int(value)
    except (TypeError, ValueError) as exc:
        raise PublicRouteError(
            FUNNEL_PAGES_COUNT, status="validation_error", rule="count_not_numeric"
        ) from exc
    if total < 0:
        raise PublicRouteError(
            FUNNEL_PAGES_COUNT, status="validation_error", rule="count_negative"
        )
    return {
        "count": total,
        "source_key": source_key,
        "traceId": body.get("traceId") if isinstance(body, dict) else None,
    }


def list_surveys(
    location_id: str,
    pit: str,
    *,
    opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
    capability: Any = None,
    capability_record: Optional[str] = None,
    timeout: float = 60.0,
) -> Any:
    """GET /surveys/ through ``surveys.list`` (public read)."""
    adapter, transport = make_adapter(
        location_id,
        pit,
        opener=opener,
        capability=capability,
        capability_record=capability_record,
        timeout=timeout,
    )
    return call_public(
        adapter,
        transport,
        SURVEYS_LIST,
        location_id,
        query={"locationId": str(location_id)},
        timeout=timeout,
    )


__all__ = [
    "BROWSER_UA",
    "FUNNEL_LIST",
    "FUNNEL_PAGES_COUNT",
    "FUNNEL_PAGES_LIST",
    "MEDIA_FILES_LIST",
    "MEDIA_LIST_TYPES",
    "MediaTypeRequired",
    "OpenerTransport",
    "PublicRouteError",
    "SURVEYS_LIST",
    "RECONCILED_FUNNEL_READS",
    "assert_reconciled_funnel_row",
    "call_public",
    "count_funnel_pages",
    "engine",
    "list_funnel_pages",
    "list_funnels",
    "list_media_files",
    "list_surveys",
    "make_adapter",
    "normalize_media_type",
    "parse_body",
]
