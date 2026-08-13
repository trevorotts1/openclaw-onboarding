#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/test_rename_applier.py
# UNIT TESTS for the PIPELINE RENAME APPLIER (scripts/u03_modules/
# rename_applier.py — U03 tooling, PUT /opportunities/pipelines/{id} under
# Version: v3). The one law this file exists to enforce: THE APPLIER NEVER
# WRITES WITHOUT --execute. Every non-execute invocation — run_apply default,
# and the apply CLI path — must be a READ-ONLY DRY-RUN, and the suite proves
# "nothing written" the only way that is provable: a stub client that RECORDS
# every write and fails the test the moment one is attempted.
#
# COVERAGE (offline, hermetic, no network, no credentials, no tokens):
#   * the write gate: dry-run plans, reads, and reports — and never invokes
#     the PUT (by-name and by-id targeting, and the CLI boundary)
#   * --execute performs exactly ONE PUT, targeted by the resolved id, whose
#     body changes ONLY the name — every read-back stage echoed byte-for-byte
#     (complete-replacement semantics: an echo that drops a key, an id, or
#     the order is a fail-closed refusal, never a plan)
#   * the fail-closed refusal ladder: absent target, name-mismatched target,
#     stageless pipeline (a body that could delete stages is never built,
#     not even for the dry-run report), placeholder pipeline id, invalid new
#     name, scope-denied read, edge/transport HELD, validation refusal,
#     read-back name drift, read-back stage-id drift, applied-but-unreadable
#     HELD, idempotent no-op, empty-name STOP
#   * the HTTP layer: a real v3 client with a monkeypatched urlopen proves
#     the browser User-Agent rides on GET and PUT (Cloudflare edge 1010
#     discipline — urllib's default "Python-urllib/x.y" is 403'd before it
#     reaches Convert and Flow), Version: v3 on the write, a 404 read is a
#     STOP (PipelineNotFound), a bare 403 whose body does NOT match the scope
#     signature is UpstreamBlockedError (HELD) — never a scope STOP — and a
#     scope-signature 403 is ScopeDenied
#   * never-a-secret: a real token and a real-looking location id never reach
#     any assertion output or any emitted surface (markers are last-4-char
#     suffixes only)
#
# Run: python3 -m pytest scripts/u03_modules/test_rename_applier.py -q
#  or: python3 scripts/u03_modules/test_rename_applier.py
#
# Note: rename_applier.py's own `self-test` subcommand exercises the same
# runner seams; this file is the INDEPENDENT pytest battery — distinct stubs
# with a hard-fail on any write, hermetic http monkeypatching, and output
# hygiene asserts — so a shared-stub blind spot cannot green both.
# =============================================================================
"""test_rename_applier.py -- the applier's write gate and fail-closed ladder."""

from __future__ import annotations

import http.client
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# Import bootstrap (house convention): the registry lives one directory up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthology_registry as reg  # noqa: E402
import u03_modules.rename_applier as ap  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4

GOLDEN = {
    "id": "pipe_ren",
    "name": "Anthology Engine",
    "stages": [
        {"id": "stg_0", "name": "Intake", "position": 0},
        {"id": "stg_1", "name": "Avatar", "position": 1},
        {"id": "stg_2", "name": "Tone", "position": 2},
    ],
}
OLD_NAME = GOLDEN["name"]
NEW_NAME = "Anthology Engine 2"
LOC_TMPL = "loc_tmpl"


# ---------------------------------------------------------------------------
# Deterministic stubs. A _WriteRecording stub records every write attempt and
# FAILS the test if one ever happens in a dry-run: "nothing written" is
# asserted by the stub itself, not by a report field that could lie.
# ---------------------------------------------------------------------------
class _ListCaf:
    """registry-CafClient-shaped stub: the by-name listing surface."""

    def __init__(self, pipelines=None, behavior="ok"):
        self._pipelines = [dict(p) for p in (pipelines or [])]
        self._behavior = behavior
        self.calls = []

    def list_pipelines(self, location_id):
        self.calls.append(("list", location_id))
        if self._behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        return [dict(p) for p in self._pipelines]


class _WriteRecording:
    """v3-client-shaped stub whose ONLY invariant is: no write without
    permission. `writes_allowed` flips True for the golden --execute tests;
    while False, any update_pipeline call fails the test outright."""

    def __init__(self, pipeline=None, writes_allowed=False, put_behavior="ok",
                 get_behavior="ok", readback=None):
        self._pipeline = dict(pipeline) if pipeline else None
        self._writes_allowed = writes_allowed
        self._put_behavior = put_behavior
        self._get_behavior = get_behavior
        self._readback = dict(readback) if readback else None
        self.puts = []   # recorded writes — asserted empty in dry-run tests
        self.gets = []

    def get_pipeline(self, pipeline_id):
        self.gets.append(pipeline_id)
        if self._get_behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._get_behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._get_behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        if self._get_behavior == "missing":
            raise ap.PipelineNotFound("pipeline id not found (HTTP 404)")
        if self._readback is not None:
            return dict(self._readback)
        return dict(self._pipeline) if self._pipeline else {}

    def update_pipeline(self, pipeline_id, body):
        self.puts.append((pipeline_id, json.loads(json.dumps(body))))
        assert self._writes_allowed, (
            "WRITE ATTEMPTED WITHOUT --execute: PUT /opportunities/pipelines/"
            "%s with body %s" % (pipeline_id, json.dumps(body, sort_keys=True)))
        if self._put_behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._put_behavior == "validation":
            raise reg.CafValidation("Convert and Flow rejected the PUT (HTTP 422)")
        if self._put_behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._put_behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        return dict(body)


def _run_apply(*, caf=None, v3=None, location_id=LOC_TMPL, pipeline_id="",
               old_name=OLD_NAME, new_name=NEW_NAME, execute=False):
    """Capture stdout (the ONE JSON object) + stderr and return (rc, report)."""
    caf = caf if caf is not None else _ListCaf(pipelines=[GOLDEN])
    v3 = v3 if v3 is not None else _WriteRecording(pipeline=GOLDEN)
    buf = io.StringIO()
    with _capture_stdout(buf):
        rc = ap.run_apply(caf, v3, location_id, pipeline_id, old_name, new_name,
                          execute=execute, out=io.StringIO())
    report = None
    try:
        report = json.loads(buf.getvalue())
    except ValueError:
        report = None
    return rc, report, caf, v3


class _capture_stdout:
    """Context manager capturing sys.stdout (hermetic; nothing leaks)."""

    def __init__(self, buf):
        self._buf = buf
        self._saved = sys.stdout

    def __enter__(self):
        sys.stdout = self._buf
        return self

    def __exit__(self, *exc):
        sys.stdout = self._saved
        return False


def _real_client(token, timeout=15):
    """The module's REAL v3 client for hermetic HTTP-layer tests."""
    return ap._V3Client(token, timeout=timeout)


# ---------------------------------------------------------------------------
# THE WRITE GATE: dry-run never writes.
# ---------------------------------------------------------------------------
def test_dry_run_writes_nothing_and_reports_applied_false():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=False)
    rc, report, caf, _ = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3)
    assert rc == EX_OK, "golden dry-run must exit 0, got %s" % rc
    assert report is not None, "dry-run must emit ONE JSON object on stdout"
    assert report["ok"] is True
    assert report["applied"] is False and report["dry_run"] is True
    assert report["current_name"] == OLD_NAME
    assert report["new_name"] == NEW_NAME
    assert report["delta"] == []
    assert v3.puts == [], "dry-run must NEVER invoke the PUT"
    assert caf.calls == [("list", LOC_TMPL)], (
        "by-name dry-run must read the listing exactly once, got %s" % caf.calls)


def test_dry_run_by_pipeline_id_reads_by_id_and_still_never_writes():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=False)
    rc, report, caf, v3b = _run_apply(caf=_ListCaf(), v3=v3,
                                      pipeline_id="pipe_ren")
    assert rc == EX_OK and report is not None and report["ok"] is True
    assert report["applied"] is False and report["dry_run"] is True
    assert caf.calls == [], "by-id targeting must not consult the listing"
    assert v3b.gets == ["pipe_ren"], (
        "by-id dry-run must read the pipeline by id once, got %s" % v3b.gets)
    assert v3b.puts == [], "by-id dry-run must NEVER invoke the PUT"


def test_cli_apply_without_execute_is_a_dry_run_that_never_writes(monkeypatch):
    # The CLI (main) resolves credentials through the REAL registry label
    # machinery — a pit- token and a location id in the environment let the
    # resolution run untouched; the client constructors are the only seam
    # monkeypatched, and both are read off `reg` by main (house wiring).
    monkeypatch.setenv("CONVERT_AND_FLOW_PIT", "pit-test-only-token")
    monkeypatch.setenv("CONVERT_AND_FLOW_LOCATION_ID", LOC_TMPL)
    captured = {"v3": None}

    def _caf(token):
        return _ListCaf(pipelines=[GOLDEN])

    def _v3(token):
        captured["v3"] = _WriteRecording(pipeline=GOLDEN, writes_allowed=False)
        return captured["v3"]

    monkeypatch.setattr(reg, "CafClient", _caf)
    monkeypatch.setattr(ap, "_V3Client", _v3)
    buf = io.StringIO()
    with _capture_stdout(buf):
        rc = ap.main(["apply", "--new-name", NEW_NAME])
    assert rc == EX_OK, "CLI apply without --execute must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["dry_run"] is True and report["applied"] is False
    assert captured["v3"].puts == [], (
        "the write gate must hold at the CLI boundary — the PUT was invoked "
        "without --execute")


def test_execute_performs_exactly_one_put_with_stages_echoed_byte_for_byte():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=True,
                         readback=dict(GOLDEN, name=NEW_NAME))
    rc, report, caf, v3b = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3,
                                      execute=True)
    assert rc == EX_OK, "golden execute must exit 0, got %s" % rc
    assert report is not None and report["ok"] is True
    assert report["applied"] is True and report["dry_run"] is False
    assert len(v3b.puts) == 1, "execute must PUT exactly once, got %d" % len(v3b.puts)
    pid, body = v3b.puts[0]
    assert pid == "pipe_ren", "PUT must target the resolved pipeline id"
    assert body["name"] == NEW_NAME, "PUT body must change ONLY the name"
    assert body["stages"] == GOLDEN["stages"], (
        "PUT body must echo the read-back stages byte-for-byte (complete "
        "replacement — every key, every id, order preserved)")


def test_idempotent_noop_passes_and_never_writes():
    # Idempotent: old_name == new_name and the pipeline already carries that
    # name — find-by-name binds it, the identity law passes, and the no-op
    # fires BEFORE any by-id read or write.
    v3 = _WriteRecording(pipeline=dict(GOLDEN, name=NEW_NAME), writes_allowed=False)
    rc, report, caf, v3b = _run_apply(caf=_ListCaf(pipelines=[dict(GOLDEN, name=NEW_NAME)]),
                                      v3=v3, old_name=NEW_NAME, new_name=NEW_NAME,
                                      execute=True)
    assert rc == EX_OK and report is not None and report["ok"] is True
    assert report["applied"] is False, "an already-named pipeline is a no-op"
    assert v3b.puts == [], "idempotent no-op must never invoke the PUT"
    assert caf.calls == [("list", LOC_TMPL)], (
        "the no-op must be proven on the live listing, got %s" % caf.calls)


# ---------------------------------------------------------------------------
# FAIL-CLOSED REFUSALS.
# ---------------------------------------------------------------------------
def test_absent_pipeline_stops_before_any_write():
    v3 = _WriteRecording(writes_allowed=False)
    rc, report, _, v3b = _run_apply(caf=_ListCaf(pipelines=[]), v3=v3,
                                    execute=True)
    assert rc == EX_STOP, "absent target must STOP, got %s" % rc
    assert report is not None and report["ok"] is False
    assert report["applied"] is False
    assert v3b.puts == [] and v3b.gets == [], "absent target must never be written"


def test_name_mismatched_target_stops_and_is_never_written():
    v3 = _WriteRecording(pipeline=dict(GOLDEN, name="Something Else"),
                         writes_allowed=False)
    rc, report, _, v3b = _run_apply(caf=_ListCaf(pipelines=[dict(GOLDEN, name="Something Else")]),
                                    v3=v3, execute=True)
    assert rc == EX_STOP, "name-mismatched target must STOP, got %s" % rc
    assert report is not None and report["ok"] is False
    assert report["applied"] is False
    assert v3b.puts == [], "a non-byte-exact target must never be written"


def test_stageless_pipeline_refuses_the_plan_even_in_dry_run():
    stageless = dict(GOLDEN, stages=[])
    v3 = _WriteRecording(pipeline=stageless, writes_allowed=False)
    rc, report, _, v3b = _run_apply(caf=_ListCaf(pipelines=[stageless]), v3=v3)
    assert rc == EX_STOP, "stageless target must STOP in dry-run too, got %s" % rc
    assert v3b.puts == [], "no body that could delete stages is ever constructed"


def test_stage_record_without_id_refuses_the_plan():
    bad = dict(GOLDEN, stages=[{"name": "Intake", "position": 0}])
    v3 = _WriteRecording(pipeline=bad, writes_allowed=False)
    rc, _, _, v3b = _run_apply(caf=_ListCaf(pipelines=[bad]), v3=v3, execute=True)
    assert rc == EX_STOP, "id-less stage must refuse the plan, got %s" % rc
    assert v3b.puts == [], "an unkeepable stage must never be written"


def test_invalid_new_name_stops_before_any_read_or_write():
    v3 = _WriteRecording(writes_allowed=False)
    rc, _, caf, v3b = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3,
                                 new_name="")
    assert rc == EX_STOP, "empty new name must STOP, got %s" % rc
    rc2, _, _, _ = _run_apply(v3=_WriteRecording(writes_allowed=False),
                              new_name="Bad\x00Name")
    assert rc2 == EX_STOP, "control-char new name must STOP, got %s" % rc2
    assert caf.calls == [], "invalid names must be refused BEFORE any read"
    assert v3b.puts == [], "invalid names must never be written"


def test_placeholder_pipeline_id_stops_and_never_reaches_a_request():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=False)
    rc, _, _, v3b = _run_apply(v3=v3, pipeline_id="REPLACE-ME", execute=True)
    assert rc == EX_STOP, "placeholder pipeline id must STOP, got %s" % rc
    assert v3b.gets == [] and v3b.puts == [], (
        "a placeholder id must never reach a request")


def test_read_scope_denied_is_a_stop_never_a_plan():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=False)
    rc, report, _, v3b = _run_apply(caf=_ListCaf(behavior="scope"), v3=v3)
    assert rc == EX_STOP, "scope-denied read must STOP, got %s" % rc
    assert v3b.puts == [], "a scope-denied read must never be written"


def test_read_edge_block_and_transport_are_held():
    for behavior in ("edge", "transport"):
        v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=False)
        rc, _, _, v3b = _run_apply(caf=_ListCaf(behavior=behavior), v3=v3)
        assert rc == EX_HELD, "%s read must be HELD, got %s" % (behavior, rc)
        assert v3b.puts == [], "%s read must never be written" % behavior


def test_validation_refusal_on_the_put_is_a_stop():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=True,
                         put_behavior="validation")
    rc, report, _, _ = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3,
                                  execute=True)
    assert rc == EX_STOP, "validation refusal must STOP, got %s" % rc
    assert report is not None and report["applied"] is False


def test_read_back_name_drift_after_put_exits_5_with_delta():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=True,
                         readback=dict(GOLDEN, name=NEW_NAME + " TYPO"))
    rc, report, _, _ = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3,
                                  execute=True)
    assert rc == EX_MISMATCH, "read-back name drift must exit 5, got %s" % rc
    assert report is not None and report["ok"] is False
    assert report["applied"] is True
    assert any("pipeline_name" in str(d.get("item")) for d in report["delta"]), (
        "drift report must carry the name delta")


def test_read_back_stage_id_drift_after_put_exits_5_with_delta():
    drifted = dict(GOLDEN, name=NEW_NAME)
    drifted["stages"] = [dict(st) for st in GOLDEN["stages"][:2]]
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=True, readback=drifted)
    rc, report, _, _ = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3,
                                  execute=True)
    assert rc == EX_MISMATCH, "stage drift must exit 5, got %s" % rc
    assert any("pipeline_stages" in str(d.get("item")) for d in report["delta"])


def test_applied_but_unreadable_put_is_held_never_reported_renamed():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=True,
                         get_behavior="transport")
    rc, _, _, v3b = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3,
                               execute=True)
    assert rc == EX_HELD, "applied-but-unreadable must be HELD, got %s" % rc
    assert len(v3b.puts) == 1, "the PUT did happen — the HELD is about verify"


# ---------------------------------------------------------------------------
# THE HTTP LAYER (real client, hermetic urlopen).
# ---------------------------------------------------------------------------
class _FakeResponse:
    """A 2xx body holder (context-managed, like a real urlopen response)."""

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


class _RecordingHTTPHandler(urllib.request.BaseHandler):
    """Records every outbound request and serves canned responses. No socket
    is ever opened. Error statuses are raised as HTTPError with a readable
    body — the same shape urllib gives the registry's classification code.
    The OpenerDirector contains ONLY this handler, so no default processor
    can ever open a real connection."""

    def __init__(self, responses):
        self.requests = []
        self.responses = list(responses)

    def https_open(self, req):
        self.requests.append(req)
        if not self.responses:
            raise AssertionError(
                "unexpected outbound request: %s %s" % (req.get_method(), req.full_url))
        status, body = self.responses.pop(0)
        if 200 <= status < 300:
            return _FakeResponse(body)
        raise urllib.error.HTTPError(
            req.full_url, status, "fixture", http.client.HTTPMessage(),
            io.BytesIO(body))


def _install_http_handler(monkeypatch, responses):
    """Patch urlopen with a director containing ONLY the recording handler —
    hermetic: any connection attempt is impossible by construction."""
    handler = _RecordingHTTPHandler(responses)
    director = urllib.request.OpenerDirector()
    director.add_handler(handler)
    monkeypatch.setattr(urllib.request, "urlopen", director.open)
    return handler


def _scope_denial_body():
    return b'{"message": "The token is not authorized for this scope."}'


def _cloudflare_body():
    return b"<!DOCTYPE html><html><head><title>Attention Required! " \
           b"| Cloudflare</title></head><body>Error 1010</body></html>"


def test_real_v3_client_sends_browser_ua_and_v3_on_get_and_put(monkeypatch):
    handler = _install_http_handler(monkeypatch, [
        (200, b'{"pipeline": {"id": "pipe_ren", "name": "Anthology Engine", '
              b'"stages": [{"id": "stg_0", "name": "Intake", "position": 0}]}}'),
        (200, b'{"pipeline": {"id": "pipe_ren", "name": "Anthology Engine 2", '
              b'"stages": [{"id": "stg_0", "name": "Intake", "position": 0}]}}'),
    ])
    client = _real_client("pit-test-only-token")
    pipeline = client.get_pipeline("pipe_ren")
    assert pipeline["name"] == "Anthology Engine"
    client.update_pipeline("pipe_ren", {"name": "Anthology Engine 2", "stages": pipeline["stages"]})
    assert len(handler.requests) == 2
    get_req, put_req = handler.requests
    assert get_req.get_method() == "GET"
    assert get_req.full_url == (
        "https://services.leadconnectorhq.com/opportunities/pipelines/pipe_ren")
    assert put_req.get_method() == "PUT"
    assert put_req.full_url == (
        "https://services.leadconnectorhq.com/opportunities/pipelines/pipe_ren")
    for req in (get_req, put_req):
        hdrs = req.headers
        # urllib normalizes header names to lowercase ("User-agent"); assert
        # case-insensitively so the check survives that canonicalization.
        ua = next((v for k, v in hdrs.items() if k.lower() == "user-agent"), None)
        assert ua == reg.CAF_BROWSER_UA, (
            "the browser User-Agent must ride on every request (Cloudflare "
            "edge 1010 discipline — urllib's default UA is 403'd before it "
            "reaches Convert and Flow), got %r" % ua)
        assert hdrs.get("Accept") == "application/json"
        assert hdrs.get("Authorization") == "Bearer pit-test-only-token"
    assert put_req.headers.get("Version") == ap.CAF_VERSION_V3, (
        "the rename write must ride Version: v3")
    body = json.loads(put_req.data.decode("utf-8"))
    assert body == {"name": "Anthology Engine 2", "stages": pipeline["stages"]}


def test_v3_client_404_read_is_pipeline_not_found_stop_family(monkeypatch):
    handler = _install_http_handler(monkeypatch, [(404, b"not found")])
    client = _real_client("pit-test-only-token")
    with pytest.raises(ap.PipelineNotFound):
        client.get_pipeline("pipe_missing")
    assert len(handler.requests) == 1


def test_v3_client_scope_signature_403_is_scope_denied(monkeypatch):
    handler = _install_http_handler(monkeypatch, [(403, _scope_denial_body())])
    client = _real_client("pit-test-only-token")
    with pytest.raises(reg.ScopeDenied):
        client.get_pipeline("pipe_ren")
    assert len(handler.requests) == 1


def test_v3_client_bare_403_is_upstream_blocked_held_not_scope(monkeypatch):
    handler = _install_http_handler(monkeypatch, [(403, _cloudflare_body())])
    client = _real_client("pit-test-only-token")
    with pytest.raises(reg.UpstreamBlockedError):
        client.get_pipeline("pipe_ren")
    assert len(handler.requests) == 1


def test_v3_client_transport_error_is_caf_unreachable_held(monkeypatch):
    def _boom(*args, **kwargs):
        raise urllib.error.URLError("fixture: connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    client = _real_client("pit-test-only-token")
    with pytest.raises(reg.CafUnreachable):
        client.get_pipeline("pipe_ren")


def test_v3_client_validation_4xx_is_caf_validation_stop_family(monkeypatch):
    handler = _install_http_handler(monkeypatch, [(422, b'{"message": "name already exists"}')])
    client = _real_client("pit-test-only-token")
    with pytest.raises(reg.CafValidation):
        client.update_pipeline("pipe_ren", {"name": NEW_NAME, "stages": GOLDEN["stages"]})
    assert len(handler.requests) == 1


# ---------------------------------------------------------------------------
# NEVER-A-SECRET: a real token and a real location id must not leak anywhere.
# ---------------------------------------------------------------------------
def test_no_surface_prints_a_token_or_full_location_id():
    v3 = _WriteRecording(pipeline=GOLDEN, writes_allowed=False)
    real_loc = "2HIKGNgsixWx0yds7Qnx"
    rc, report, _, _ = _run_apply(caf=_ListCaf(pipelines=[GOLDEN]), v3=v3,
                                  location_id=real_loc)
    assert rc == EX_OK
    assert report is not None
    dump = json.dumps(report)
    assert real_loc not in dump, "the full location id must never be surfaced"
    assert real_loc[-4:] in dump, "the location MARKER (last 4 chars) is the surface"
    assert "pit-test-only-token" not in dump
    assert report["location_marker"] == "..." + real_loc[-4:]
    assert report["pipeline_id_marker"] == "..._ren", (
        "pipeline ids surface as last-4-char markers only")


def test_self_test_subcommand_is_offline_and_exits_zero():
    rc = ap.main(["self-test"])
    assert rc == EX_OK, "the module's own offline self-test must exit 0"


# ---------------------------------------------------------------------------
# Plain-python runner (no pytest required) — house style.
# ---------------------------------------------------------------------------
class _MP:
    """Minimal monkeypatch stand-in for the plain runner (mirrors pytest's
    monkeypatch fixture surface for the tests that take it)."""

    def __init__(self):
        self._saved = []

    def setenv(self, k, v):
        self._saved.append((os.environ.get(k), k))
        os.environ[k] = v

    def delenv(self, k, raising=False):
        self._saved.append((os.environ.get(k), k))
        if raising and k not in os.environ:
            raise KeyError(k)
        os.environ.pop(k, None)

    def setattr(self, obj, name, value):
        self._saved.append((getattr(obj, name, None), obj, name))
        setattr(obj, name, value)

    def undo(self):
        for item in reversed(self._saved):
            if len(item) == 3:
                obj, name = item[1], item[2]
                if item[0] is not None:
                    setattr(obj, name, item[0])
                else:
                    try:
                        delattr(obj, name)
                    except AttributeError:
                        pass
            else:
                val, key = item
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val


TESTS = [
    (test_dry_run_writes_nothing_and_reports_applied_false, False),
    (test_dry_run_by_pipeline_id_reads_by_id_and_still_never_writes, False),
    (test_cli_apply_without_execute_is_a_dry_run_that_never_writes, True),
    (test_execute_performs_exactly_one_put_with_stages_echoed_byte_for_byte, False),
    (test_idempotent_noop_passes_and_never_writes, False),
    (test_absent_pipeline_stops_before_any_write, False),
    (test_name_mismatched_target_stops_and_is_never_written, False),
    (test_stageless_pipeline_refuses_the_plan_even_in_dry_run, False),
    (test_stage_record_without_id_refuses_the_plan, False),
    (test_invalid_new_name_stops_before_any_read_or_write, False),
    (test_placeholder_pipeline_id_stops_and_never_reaches_a_request, False),
    (test_read_scope_denied_is_a_stop_never_a_plan, False),
    (test_read_edge_block_and_transport_are_held, False),
    (test_validation_refusal_on_the_put_is_a_stop, False),
    (test_read_back_name_drift_after_put_exits_5_with_delta, False),
    (test_read_back_stage_id_drift_after_put_exits_5_with_delta, False),
    (test_applied_but_unreadable_put_is_held_never_reported_renamed, False),
    (test_real_v3_client_sends_browser_ua_and_v3_on_get_and_put, True),
    (test_v3_client_404_read_is_pipeline_not_found_stop_family, True),
    (test_v3_client_scope_signature_403_is_scope_denied, True),
    (test_v3_client_bare_403_is_upstream_blocked_held_not_scope, True),
    (test_v3_client_transport_error_is_caf_unreachable_held, True),
    (test_v3_client_validation_4xx_is_caf_validation_stop_family, True),
    (test_no_surface_prints_a_token_or_full_location_id, False),
    (test_self_test_subcommand_is_offline_and_exits_zero, False),
]


def main():
    failed = 0
    for t, needs_mp in TESTS:
        mp = _MP() if needs_mp else None
        try:
            t(mp) if needs_mp else t()
            print("  PASS: %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL: %s\n        %s" % (t.__name__, exc))
        except Exception as exc:  # noqa: BLE001 — a crash is a failure, reported as one
            failed += 1
            print("  ERROR: %s\n        %r" % (t.__name__, exc))
        finally:
            if mp is not None:
                mp.undo()
    print("\n=== %d passed, %d failed ===" % (len(TESTS) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
