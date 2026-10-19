"""GHL-169 — Skill 06 client routes: routed callers and declared gaps.

MOCK-ONLY. Every HTTP call is an injected ``(Request, timeout) -> response``
opener; the capability gate is a synthetic in-memory gate. No network, no
credential, no live GoHighLevel call.

Covered:
  * ``media.files.list`` routed through the frozen ``PublicGhlAdapter``
    (row-supplied Version ``v3``, browser UA, required ``type``).
  * the required-``type`` gate runs BEFORE any adapter/transport.
  * the default capability gate (no explicit gate) refuses before transport.
  * ``surveys.list`` routed; its path builder still matches the registry row.
  * router operation-ID declaration matches the frozen registry.
  * NEGATIVE CONTROL: a raw REST line added to any of the five caller files
    without a ``ghl_route_gaps`` entry fails; the scanner is proved to
    discriminate (a synthetic raw line is caught).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error

import pytest

_TOOLS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "tools")
)
_SKILL_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_funnels_read as fr  # noqa: E402
import ghl_media as gm  # noqa: E402
import ghl_object_router as router  # noqa: E402
import ghl_public_client as client  # noqa: E402
import ghl_route_gaps as gaps  # noqa: E402
import ghl_survey_rest as sr  # noqa: E402

FAKE_LOC = "LOCATION0000000fake"
FAKE_PIT = "PIT-fixture-not-a-real-token"
GCS_URL = "https://storage.googleapis.com/msgsndr/LOCATION0000000fake/hero.png"


class FakeResponse:
    def __init__(self, payload, code: int = 200):
        self._payload = payload
        self._code = code

    def getcode(self) -> int:
        return self._code

    def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


class RecordingOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        return self.response


def _gate(*operations: str):
    seams = client.engine()
    gate = seams["CapabilityGate"](tenant=FAKE_LOC)
    for operation_id in operations:
        gate.enable(
            seams["Capability"](
                operation_id=operation_id,
                contract_verified=True,
                adapter_built=True,
                offline_tests_passed=True,
                read_verified=True,
            ),
            write=False,
        )
    return gate


def _media_gate():
    return _gate(client.MEDIA_FILES_LIST)


# ── Media LIST ───────────────────────────────────────────────────────────────

class TestMediaListRoute:
    BODY = {"files": [{"id": "FILEID123", "name": "hero.png"}], "count": 1,
            "traceId": "TRACE123"}

    def test_missing_type_fails_before_transport(self):
        opener = RecordingOpener(FakeResponse(self.BODY))
        with pytest.raises(gm.MediaListTypeError, match="explicit type"):
            gm.list_media(FAKE_LOC, FAKE_PIT, opener=opener,
                          capability=_media_gate())
        assert opener.requests == []

    def test_blank_type_fails_before_transport(self):
        opener = RecordingOpener(FakeResponse(self.BODY))
        with pytest.raises(gm.MediaListTypeError, match="explicit type"):
            gm.list_media(FAKE_LOC, FAKE_PIT, media_type="  ", opener=opener,
                          capability=_media_gate())
        assert opener.requests == []

    def test_invalid_type_fails_before_transport(self):
        opener = RecordingOpener(FakeResponse(self.BODY))
        with pytest.raises(gm.MediaListTypeError, match="not supported"):
            gm.list_media(FAKE_LOC, FAKE_PIT, media_type="spreadsheet",
                          opener=opener, capability=_media_gate())
        assert opener.requests == []

    def test_routes_through_adapter_row(self):
        opener = RecordingOpener(FakeResponse(self.BODY))
        result = gm.list_media(
            FAKE_LOC, FAKE_PIT, media_type="  FILE ", opener=opener,
            capability=_media_gate(),
        )
        assert result == {"files": self.BODY["files"], "count": 1,
                          "traceId": "TRACE123", "http": 200}
        assert len(opener.requests) == 1
        request = opener.requests[0]
        assert request.full_url == (
            "https://services.leadconnectorhq.com/medias/files"
            f"?locationId={FAKE_LOC}&type=file"
        )
        assert request.get_method() == "GET"
        # Version comes from the frozen row, not from a Skill 06 constant.
        assert request.get_header("Version") == "v3"
        assert request.get_header("Authorization") == f"Bearer {FAKE_PIT}"
        assert request.get_header("Accept") == "application/json"
        user_agent = request.get_header("User-agent") or ""
        assert user_agent and "Python-urllib" not in user_agent

    def test_default_gate_denies_before_transport(self):
        opener = RecordingOpener(FakeResponse(self.BODY))
        with pytest.raises(gm.MediaListError, match="capability_disabled"):
            gm.list_media(FAKE_LOC, FAKE_PIT, media_type="file", opener=opener)
        assert opener.requests == []

    def test_http_error_is_typed(self):
        def _raise(req, timeout):
            raise urllib.error.HTTPError(
                req.full_url, 429, "rate limited", hdrs=None,
                fp=__import__("io").BytesIO(b"slow down"),
            )

        with pytest.raises(gm.MediaListError) as excinfo:
            gm.list_media(FAKE_LOC, FAKE_PIT, media_type="file",
                          opener=_raise, capability=_media_gate())
        assert "media.files.list" in str(excinfo.value)
        assert FAKE_PIT not in str(excinfo.value)

    def test_malformed_payload_is_typed(self):
        opener = RecordingOpener(FakeResponse({"unexpected": []}))
        with pytest.raises(gm.MediaListError, match="payload_no_files"):
            gm.list_media(FAKE_LOC, FAKE_PIT, media_type="file", opener=opener,
                          capability=_media_gate())


# ── Survey LIST ──────────────────────────────────────────────────────────────

class TestSurveyListRoute:
    def test_list_operation_is_the_frozen_row(self):
        operations = client.engine()["OPERATIONS"]
        row = operations[sr.SURVEY_LIST_OPERATION_ID]
        assert row.method == "GET"
        assert row.path_template == "/surveys/"
        assert row.version == "v3"
        # The builder must still describe the registered route.
        assert sr.survey_list_path(FAKE_LOC, 25) == (
            f"{row.path_template}?locationId={FAKE_LOC}&limit=25"
        )

    def test_routes_through_adapter_row(self):
        opener = RecordingOpener(FakeResponse({"surveys": [{"id": "S1"}]}))
        result = client.list_surveys(
            FAKE_LOC, FAKE_PIT, opener=opener,
            capability=_gate(client.SURVEYS_LIST),
        )
        assert result == {"surveys": [{"id": "S1"}]}
        request = opener.requests[0]
        assert request.full_url == (
            "https://services.leadconnectorhq.com/surveys/"
            f"?locationId={FAKE_LOC}"
        )
        assert request.get_header("Version") == "v3"

    def test_default_gate_denies_before_transport(self):
        opener = RecordingOpener(FakeResponse({"surveys": []}))
        with pytest.raises(client.PublicRouteError, match="capability_disabled"):
            client.list_surveys(FAKE_LOC, FAKE_PIT, opener=opener)
        assert opener.requests == []


# ── Router operation declaration ────────────────────────────────────────────

class TestObjectRouterOperations:
    def test_every_declared_operation_exists_in_the_registry(self):
        operations = client.engine()["OPERATIONS"]
        for object_type, entry in router.PUBLIC_OPERATION_ROUTES.items():
            for bucket in ("routed", "declared"):
                for operation_id in entry[bucket]:
                    assert operation_id in operations, (
                        f"{object_type}.{bucket} names an unknown operation "
                        f"{operation_id!r}"
                    )

    def test_media_routing_is_explicit(self):
        route = router.public_operation_route("media")
        assert route["routed"] == ("media.files.list",)
        assert "media.upload" in route["declared"]
        assert "media.folders.create" in route["declared"]

    def test_unknown_object_type_invents_nothing(self):
        assert router.public_operation_route("no-such-object") == {
            "routed": (), "declared": ()
        }


# ── Declared named gaps ─────────────────────────────────────────────────────

class TestNamedGaps:
    def test_every_gap_anchor_still_exists(self):
        assert gaps.missing_anchors(_SKILL_ROOT) == []

    def test_funnel_routes_are_gaps_against_different_registered_paths(self):
        operations = client.engine()["OPERATIONS"]
        # The called routes have no row; the registered rows are different.
        assert fr.FUNNEL_LIST_PATH not in {
            row.path_template for row in operations.values()
        }
        assert fr.PAGE_LIST_PATH not in {
            row.path_template for row in operations.values()
        }
        assert operations["funnels.list"].path_template == "/funnels/"
        assert operations["funnels.pages.list"].path_template == (
            "/funnels/{funnelId}/pages"
        )
        assert any(
            gap["file"] == "tools/ghl_funnels_read.py" for gap in gaps.NAMED_GAPS
        )

    def test_media_writes_are_declared_gaps(self):
        declared = {
            gap["operation_id"] for gap in gaps.NAMED_GAPS
            if gap["file"] == "tools/ghl_media.py"
        }
        assert declared == {"media.upload", "media.folders.create"}

    def test_routed_operations_are_the_client_paths(self):
        assert set(gaps.ROUTED_OPERATIONS) == {
            client.MEDIA_FILES_LIST, client.SURVEYS_LIST
        }


# ── Negative control ────────────────────────────────────────────────────────

# Every raw-REST marker line that is allowed to remain. Each is either a
# declared gap or documentation/constant text; a NEW raw call has a new line
# text and fails. Occurrence counts below catch a duplicate of an existing line.
ALLOWED_RAW_LINES = {
    '``POST services.leadconnectorhq.com/medias/upload-file`` Bearer-PIT call from',
    '* KIE.ai (``api.kie.ai``) and the GHL MEDIA upload (``services.leadconnectorhq.com``',
    'GHL_SERVICES_ORIGIN = "https://services.leadconnectorhq.com"',
    '``POST services.leadconnectorhq.com/medias/upload-file`` with',
    'req = urllib.request.Request(url, data=body, method="POST")',
    '_opener = opener or (lambda r, t: urllib.request.urlopen(r, timeout=t))',
    '``POST services.leadconnectorhq.com/medias/folder`` with',
    'REST_SERVICES = "rest_services"          # raw HTTPS services.leadconnectorhq.com',
    '"""Identify builder-origin routes (backend.leadconnectorhq.com).',
    '"""Identify services.* routes (services.leadconnectorhq.com).',
    'GHL_BACKEND_ORIGIN = "https://backend.leadconnectorhq.com"',
    'or a ``*.leadconnectorhq.com`` CDN host — see ``is_ghl_media_url``). Any',
    '# (``*.leadconnectorhq.com``). An ``<img src>`` outside this set is an EXTERNAL',
    'GHL_MEDIA_HOST_SUFFIX = ".leadconnectorhq.com"',
    'the GHL media upload returns) and any ``*.leadconnectorhq.com`` host (the GHL',
    'f"(storage.googleapis.com/msgsndr/... or *.leadconnectorhq.com), "',
    'return urllib.request.urlopen(req, timeout=timeout)',
    'req = urllib.request.Request(url, method="GET")',
    '``GET backend.leadconnectorhq.com/surveys/<id>`` with the owner ``token-id``',
    'SURVEY_BACKEND_ORIGIN = "https://backend.leadconnectorhq.com"      # GET <id> (owner token-id) — proven',
    'SURVEY_SERVICES_ORIGIN = "https://services.leadconnectorhq.com"    # list GET (PIT + browser UA) — proven',
    '"""``GET backend.leadconnectorhq.com/surveys/<id>`` — proven with owner token-id.',
    '"""``GET services.leadconnectorhq.com/surveys/?locationId=…&limit=…`` — proven',
    '"url": "https://backend.leadconnectorhq.com/surveys/abc123?locationId=LOC"}',
    'if not (origin == "https://backend.leadconnectorhq.com"',
    '{"method": "POST", "url": "https://backend.leadconnectorhq.com/surveys/abc",',
}


class TestNoReintroducedRawREST:
    def test_no_undeclared_raw_rest_in_caller_files(self):
        hits = gaps.undeclared_raw_lines(_SKILL_ROOT, ALLOWED_RAW_LINES)
        assert hits == [], (
            "raw REST call added without a named-gap declaration: "
            f"{hits}. Route it through ghl_public_client or declare it in "
            "ghl_route_gaps.NAMED_GAPS."
        )

    def test_scanner_discriminates(self):
        # A control proves the check can fail: with no lines allowed, the same
        # files report raw hits. If this returns [] the scanner is broken.
        hits = gaps.undeclared_raw_lines(_SKILL_ROOT, None)
        assert hits, "the raw-REST scanner did not detect a known raw line"

    def test_gap_functions_keep_exactly_one_raw_transport(self):
        # Scoped to the functions that ARE the declared gaps, so an unrelated
        # future change to another function cannot mask a reintroduction here.
        import inspect

        for function in (gm.upload_media, gm.create_media_folder):
            source = inspect.getsource(function)
            assert source.count("urllib.request.Request(") == 1, function.__name__
            assert source.count("urlopen(") == 1, function.__name__
        source = inspect.getsource(fr._get_json)
        assert source.count("urllib.request.Request(") == 1
        assert inspect.getsource(fr._default_opener).count("urlopen(") == 1

    def test_routed_media_list_owns_no_raw_transport(self):
        import inspect
        source = inspect.getsource(gm.list_media)
        assert "urllib.request.Request(" not in source
        assert "urlopen(" not in source
        assert "client.list_media_files" in source

    def test_the_client_is_the_only_transport_owner(self):
        import inspect
        source = inspect.getsource(client)
        assert "urllib.request.Request(" in source
        assert "urlopen" in source
