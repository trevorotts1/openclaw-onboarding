"""Focused WF24 tests: reconciled funnel reads across every surface.

Covers the acceptance IDs this lane owns:
  B01  registry/inventory/router/Skill 6 client agree for the funnel family
  B02  funnel list/page/count paths and query placement, unresolved fields labeled
  B03  wrapper side: an unsupported media type is refused before transport
  IG-ROUTE-06  registry/capability/shared router/CLI/dispatcher describe one route
  IG-ROUTE-09  no mixed old/new funnel request shape

Offline only: every HTTP call uses an injected fake opener; no credentials, no
network, no live GoHighLevel.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_ROOT = os.path.dirname(_TESTS_DIR)
_REPO_ROOT = os.path.dirname(_SKILL_ROOT)
_TOOLS = os.path.join(_SKILL_ROOT, "tools")
_SHARED_GHL = os.path.join(_REPO_ROOT, "shared-utils", "ghl")
_ENGINE = os.path.join(_REPO_ROOT, "44-convert-and-flow-operator", "tools", "engine")
for _p in (_TOOLS, _SHARED_GHL, _ENGINE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import funnel_read_contract as contract  # noqa: E402
import capability_inventory as inv  # noqa: E402
import object_router as router  # noqa: E402
import ghl_funnels_read as fr  # noqa: E402
import ghl_public_client as client  # noqa: E402

_FIXTURE_PATH = os.path.join(
    _REPO_ROOT, "tests", "fixtures", "ghl_compat", "funnel_read_contracts.json"
)
FIXTURE = json.load(open(_FIXTURE_PATH, encoding="utf-8"))
FIXTURE_OPS = {o["operation_id"]: o for o in FIXTURE["operations"]}
OPS = ("funnels.list", "funnels.pages.list", "funnels.pages.count")

_FIXTURE_PIT = "pit-fixture-for-wf24-tests-only"


class _FakeResponse:
    def __init__(self, payload, code=200):
        self._payload = payload
        self._code = code

    def getcode(self):
        return self._code

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class _RecordingOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        return _FakeResponse(self.payload)


def _query(req):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)


def _path(req):
    return urllib.parse.urlsplit(req.full_url).path


def _frozen_row(operation_id):
    return router.frozen_row(operation_id)


# ---------------------------------------------------------------------------
# B01 / IG-ROUTE-06 - one operation, one route, every surface
# ---------------------------------------------------------------------------
def test_b01_inventory_router_client_agree_on_funnel_operations():
    inventory_routes = {
        c.capability_id: c.route for c in inv.OPERATIONS if c.resource == "funnels"
    }
    client_routes = {
        op: "%s %s" % (spec["method"], spec["path"])
        for op, spec in client.RECONCILED_FUNNEL_READS.items()
    }
    router_routes = {
        op: "GET %s" % path for op, path in router.RECONCILED_FUNNEL_PATHS.items()
    }
    fixture_routes = {
        op: "%s %s" % (body["method"], body["path"])
        for op, body in FIXTURE_OPS.items()
    }
    expected = {
        "funnels.list": "GET /funnels/funnel/list",
        "funnels.pages_list": "GET /funnels/page",
        "funnels.pages_count": "GET /funnels/page/count",
    }
    assert inventory_routes == expected, inventory_routes
    assert {k: v for k, v in client_routes.items()} == {
        "funnels.list": "GET /funnels/funnel/list",
        "funnels.pages.list": "GET /funnels/page",
        "funnels.pages.count": "GET /funnels/page/count",
    }
    assert router_routes == {
        "funnels.list": "GET /funnels/funnel/list",
        "funnels.pages.list": "GET /funnels/page",
        "funnels.pages.count": "GET /funnels/page/count",
    }
    assert fixture_routes == router_routes


def test_ig_route_06_registry_capability_router_client_agree():
    for op in OPS:
        spec = contract.contract(op)
        cap = next(c for c in inv.OPERATIONS if c.capability_id == spec.capability_id)
        assert "%s %s" % (spec.method, spec.path) == cap.route, op

        reg = router.registration(op)
        assert reg.capability_id == spec.capability_id, op
        row = _frozen_row(reg.public_operation_id)
        assert row is not None, op
        # WF00-CP01 landed the corrected rows: registry, inventory, router and
        # the Skill 6 client must now describe one route, with no pending change
        # request. A regression to the old shape fails here instead of passing.
        assert (str(row.method).upper(), str(row.path_template)) == (
            spec.method, spec.path,
        ), (op, row.method, row.path_template)
        assert reg.status == router.ROUTABLE, (op, reg.status, reg.reason)

        mirror = client.RECONCILED_FUNNEL_READS[op]
        assert mirror["method"] == spec.method and mirror["path"] == spec.path, op
        assert tuple(mirror["required_query"]) == spec.required_query(), op


# ---------------------------------------------------------------------------
# B02 - paths, query placement, explicit unresolved fields
# ---------------------------------------------------------------------------
def test_b02_funnel_paths_and_query_placement_match_contract_fixture():
    module_dict = contract.as_dict()
    fixture_body = dict(FIXTURE)
    fixture_body.pop("fixture_purpose", None)
    assert module_dict == fixture_body, "contract module and fixture drifted"

    for op in OPS:
        spec = contract.contract(op)
        body = FIXTURE_OPS[op]
        assert body["path"] == spec.path
        assert body["method"] == "GET"
        assert body["version_state"] == "unverified"
        assert body["scope_state"] == "unverified"
        assert body["required_query"] == list(spec.required_query())
        for param in body["query"]:
            assert param["placement"] == "query", (op, param)
        assert body["version_header"] == "2023-02-21"
        assert any("Version" in u for u in body["unresolved"])
        assert any("scope" in u for u in body["unresolved"])

    # The old frozen shapes are audit anchors only and never equal a new path.
    for op, old in contract.OBSOLETE_FROZEN_SHAPES.items():
        assert contract.contract(op).path != old.split(" ", 1)[1], op

    # The query builder refuses a mixed/old shape before any transport.
    assert contract.build_query(
        "funnels.pages.count", locationId="loc-1", funnelId="fun-1"
    ) == {"locationId": "loc-1", "funnelId": "fun-1"}
    with pytest.raises(ValueError, match="funnelId"):
        contract.build_query("funnels.pages.list", locationId="loc-1", offset=0, limit=10)
    with pytest.raises(ValueError, match="unknown query parameter"):
        contract.build_query(
            "funnels.list", locationId="loc-1", offset=0, limit=10, funnelId="fun-1"
        )


# ---------------------------------------------------------------------------
# IG-ROUTE-09 - exact requests, no mixed old/new shape
# ---------------------------------------------------------------------------
def test_ig_route_09_no_mixed_old_new_funnel_shape():
    # Funnel list: exact path + exact query names.
    opener = _RecordingOpener({"funnels": [], "count": 0, "traceId": "t"})
    fr.list_funnels("loc-1", pit=_FIXTURE_PIT, opener=opener, limit=25)
    req = opener.requests[0]
    assert _path(req) == "/funnels/funnel/list"
    assert set(_query(req)) == {"locationId", "offset", "limit"}

    # Page list: exact path + exact query names.
    opener = _RecordingOpener({"pages": []})
    fr.list_pages("fun-1", "loc-1", pit=_FIXTURE_PIT, opener=opener, limit=25)
    req = opener.requests[0]
    assert _path(req) == "/funnels/page"
    assert set(_query(req)) == {"locationId", "funnelId", "limit", "offset"}

    # Page count: exact path + exactly the two required identifiers.
    opener = _RecordingOpener({"count": 4})
    got = fr.count_pages("fun-1", "loc-1", pit=_FIXTURE_PIT, opener=opener)
    req = opener.requests[0]
    assert _path(req) == "/funnels/page/count"
    assert set(_query(req)) == {"locationId", "funnelId"}
    assert got["count"] == 4

    # No emitted URL carries an old shape.
    for old in contract.OBSOLETE_FROZEN_SHAPES.values():
        old_path = old.split(" ", 1)[1]
        assert _path(req) != old_path


def test_count_pages_raises_on_unknown_envelope():
    opener = _RecordingOpener({"pages": []})
    with pytest.raises(fr.FunnelsReadError, match="no recognized count field|unrecognized response envelope"):
        fr.count_pages("fun-1", "loc-1", pit=_FIXTURE_PIT, opener=opener)


# ---------------------------------------------------------------------------
# Skill 6 bridge: refuses a stale frozen row before transport
# ---------------------------------------------------------------------------
def test_public_client_refuses_stale_frozen_row_before_transport(monkeypatch):
    spec = contract.contract("funnels.list")
    row = _frozen_row("funnels.list")
    assert (str(row.method).upper(), str(row.path_template)) == (
        spec.method, spec.path,
    ), (row.method, row.path_template)

    # The WF00-CP01 row correction landed, so the live guard is a no-op.
    client.assert_reconciled_funnel_row("funnels.list")

    # Negative control on the same instrument: a stale row still refuses, and
    # it refuses before any transport call.
    class _StaleRow:
        method = "GET"
        path_template = "/funnels/"

    registry = client.engine()["OPERATIONS"]

    class _StaleRegistry:
        def get(self, operation_id):
            if operation_id == "funnels.list":
                return _StaleRow()
            return registry.get(operation_id)

    monkeypatch.setitem(client.engine(), "OPERATIONS", _StaleRegistry())

    class _NoCall:
        def __call__(self, req, timeout):  # pragma: no cover
            raise AssertionError("stale-row refusal must happen before transport")

    with pytest.raises(client.PublicRouteError) as excinfo:
        client.list_funnels(
            "loc-1", _FIXTURE_PIT, opener=_NoCall(), capability=object()
        )
    assert excinfo.value.rule == "reconciled_path_mismatch"


# ---------------------------------------------------------------------------
# B03 wrapper side - unsupported media type refused before transport
# ---------------------------------------------------------------------------
def test_b03_wrapper_refuses_unsupported_media_type_before_transport():
    class _NoCall:
        def __call__(self, req, timeout):  # pragma: no cover
            raise AssertionError("media-type refusal must happen before transport")

    with pytest.raises(client.MediaTypeRequired):
        client.list_media_files(
            "loc-1", _FIXTURE_PIT, None, opener=_NoCall(), capability=object()
        )
    with pytest.raises(client.MediaTypeRequired):
        client.list_media_files(
            "loc-1", _FIXTURE_PIT, "spreadsheet", opener=_NoCall(), capability=object()
        )


# ---------------------------------------------------------------------------
# Capability dimensions stay independent and explicit
# ---------------------------------------------------------------------------
def test_capability_dimensions_are_separate_facts():
    facts = inv.describe_capability("funnels.list")
    assert facts.documented is True
    assert facts.implemented == "yes"
    assert facts.routable is True
    assert facts.account_available == "unknown"
    assert facts.functionally_verified == "not_run"
    assert facts.version_header == "2023-02-21"
    assert facts.version_state == "unverified"
    assert facts.scope_state == "unverified"


def test_read_module_constants_match_the_shared_contract():
    assert fr.FUNNEL_LIST_PATH == contract.contract("funnels.list").path
    assert fr.PAGE_LIST_PATH == contract.contract("funnels.pages.list").path
    assert fr.PAGE_COUNT_PATH == contract.contract("funnels.pages.count").path
    assert fr.GHL_FUNNELS_VERSION == contract.contract("funnels.list").version_header


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
