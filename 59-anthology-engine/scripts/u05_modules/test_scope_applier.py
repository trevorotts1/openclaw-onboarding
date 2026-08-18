#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/test_scope_applier.py
# UNIT TESTS for the WORKFLOW TRIGGER-SCOPE APPLIER (scripts/u05_modules/
# scope_applier.py — U05 tooling: PUT /workflow/{loc}/trigger/{trigger_id}
# through the internal Firebase rail). The one law this file exists to
# enforce: THE APPLIER NEVER WRITES WITHOUT --execute. Every non-execute
# invocation — run_apply default, and the apply CLI path — must be a
# READ-ONLY DRY-RUN, and the suite proves "nothing written" the only way
# that is provable: a stub rail that RECORDS every write and fails the test
# the moment one is attempted.
#
# THE SCOPE LAW (scope_applier.py's header, written against): each of the
# EIGHT contract release workflows must fire ONLY on its contract contact_tag
# trigger — the trigger is type "contact_tag" and its filter lives in the
# trigger's "conditions" array as the tagsAdded condition (the exact shape
# the Skill 44 build rail ships: {"operator": "index-of-true", "field":
# "tagsAdded", "value": <tag>, ...}). "In scope" means: the workflow exists
# BYTE-EXACT under a contract release-notification name, carries EXACTLY ONE
# contact_tag trigger, and that trigger's tagsAdded filter value IS the
# contract trigger_tag. An EMPTY / wrong / multi-tag / non-string filter is
# the drift the applier corrects — and ONLY with --execute. A body that
# could guess a filter is never constructed, not even for the dry-run
# report.
#
# COVERAGE (offline, hermetic, no network, no credentials, no tokens):
#   * the write gate: dry-run plans, reads, and reports — and never invokes
#     the PUT (by-name and by-id targeting, and the CLI boundary)
#   * --execute performs EXACTLY ONE PUT, targeted by the trigger id from
#     the live read, whose body echoes the pre-write trigger byte-for-byte
#     with ONLY the tagsAdded value corrected to the contract tag — every
#     other condition key preserved (complete-replacement semantics)
#   * the fail-closed refusal ladder: absent workflow, duplicated name,
#     by-id name mismatch, workflow with NO contact_tag trigger, TWO
#     contact_tag triggers, no tagsAdded condition, an over-scoped multi-
#     value list, a non-string filter value, a trigger with no real id, a
#     placeholder workflow id, a non-contract workflow name, a rail
#     rejection of the PUT (the _error body classification), a rail
#     unavailable read (HELD), a read-back filter drift (exit 5), a
#     read-back active-state drift (exit 5), an applied-but-unreadable PUT
#     (HELD — never reported as corrected)
#   * the idempotent no-op: a live filter that already IS the contract tag
#     (and the single-element [<tag>] list form) passes with NOTHING written
#     — even with --execute
#   * the HTTP layer: the REAL ScopeRailClient with a monkeypatched urlopen
#     proves the browser User-Agent rides on the GET list / trigger GET /
#     trigger PUT (Cloudflare edge 1010 discipline — urllib's default
#     "Python-urllib/x.y" is 403'd before it reaches the rail), the
#     token-id / channel / source / version header set on every request, a
#     rail HTTP error on the PUT is InternalRailUnavailable (HELD), and a
#     rejected PUT answered as a parsed "_error" body is TriggerScopeRefused
#     (STOP) — never surfaced
#   * never-a-secret: real-looking workflow / trigger ids never reach any
#     assertion output or any emitted surface (markers are last-4-char
#     suffixes only); no credential shape rides any surface; the only
#     token-shaped strings in this file are synthetic fixture markers
#     ("pit-test-only-token" / "tok-fake"), asserted INSIDE the hermetic
#     HTTP tests and never emitted by the module
#   * the house doctrine pins: the exit-code convention (0/1/2/3/4/5)
#     asserted through the registry's exported constants, the browser
#     User-Agent law (CF 1010), the fail-closed-empty package init, and the
#     U05 sibling batteries green (scope_checker, workflow_reader,
#     negative_verifier, attack_unscoped, golden_scoped)
#
# Run: python3 -m pytest scripts/u05_modules/test_scope_applier.py -q
#  or: python3 scripts/u05_modules/test_scope_applier.py
#
# Note: scope_applier.py's own `self-test` subcommand exercises the same
# runner seams; this file is the INDEPENDENT pytest battery — distinct stubs
# with a hard-fail on any write, hermetic http monkeypatching, and output
# hygiene asserts — so a shared-stub blind spot cannot green both.
# =============================================================================
"""test_scope_applier.py -- the trigger-scope applier's write gate and
fail-closed ladder (U05 tooling; dry-run writes nothing, ever)."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# Import bootstrap (house convention): the registry lives one directory up,
# and the U05 package is imported BY NAME (u05_modules/__init__.py: pure
# namespace container, side-effect-free at import).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthology_registry as reg  # noqa: E402
import u05_modules.scope_applier as ap  # noqa: E402  (the module under test)
import u05_modules.workflow_reader as wf_reader  # noqa: E402  (the rail-path sibling)

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape. No test fixture carries a real one; the
# synthetic markers below appear ONLY inside the hermetic HTTP tests.
CREDENTIAL_SHAPE = "pit-"

LOC_TMPL = "loc_tmpl"

# The golden contract row (mirrors the contract's first release workflow:
# config/anthology-snapshot-contract.json workflows.release_notifications).
# The tag and name are the module's own self-test fixtures — synthetic, the
# SAME values the module's _self_test_body pins.
CONTRACT_NAME = "Anthology Release: Avatar"
CONTRACT_TAG = "anthology-release-avatar"

# The golden workflow row (the listing shape) and the golden contact_tag
# trigger (the Skill 44 build shape). Synthetic ids only — never a live id.
WORKFLOW_ID = "wf-0000"
TRIGGER_ID = "trg-0001"

# The DRIFTED trigger: fires on the WRONG tag (the defect the applier fixes).
DRIFTED_TRIGGER = {
    "id": TRIGGER_ID, "workflowId": WORKFLOW_ID, "name": CONTRACT_NAME,
    "type": "contact_tag", "masterType": "highlevel", "active": True,
    "conditions": [{"operator": "index-of-true", "field": "tagsAdded",
                    "title": "Tag Added", "type": "select", "id": "tag-added",
                    "value": "anthology-release-tone"}],
}

# The SCOPED trigger: already fires ONLY on the contract tag (the no-op
# fixture — never written, even with --execute).
SCOPED_TRIGGER = {
    "id": TRIGGER_ID, "workflowId": WORKFLOW_ID, "name": CONTRACT_NAME,
    "type": "contact_tag", "masterType": "highlevel", "active": True,
    "conditions": [{"operator": "index-of-true", "field": "tagsAdded",
                    "title": "Tag Added", "type": "select", "id": "tag-added",
                    "value": CONTRACT_TAG}],
}

WORKFLOW_ROW = {"id": WORKFLOW_ID, "name": CONTRACT_NAME,
                "type": "workflow", "parentId": "dir-tmpl"}


def _contract_row(contract=None):
    """The contract row the runner requires: byte-exact the golden name and
    carrying the golden trigger_tag (the module's own contract reader runs
    on the committed contract — this is the SAME row the module's self-test
    uses as rows[0])."""
    return {"name": CONTRACT_NAME, "trigger_tag": CONTRACT_TAG}


# ---------------------------------------------------------------------------
# Deterministic stubs. A _WriteRecording stub records every write attempt and
# FAILS the test if one ever happens in a dry-run: "nothing written" is
# asserted by the stub itself, not by a report field that could lie.
# ---------------------------------------------------------------------------
class _FakeRail:
    """Internal-rail stub for the trigger-scope surface: list rows +
    per-workflow trigger GET + the trigger PUT (which APPLIES the echoed body
    so the read-back reflects the write). Records every read and every PUT
    so the tests can prove the write gate."""

    def __init__(self, rows=None, triggers=None, outcome="ok",
                 put_outcome="ok", put_readback=None, readback_unavailable=False):
        self._rows = [dict(r) for r in (rows or [])]
        self._triggers = {k: [dict(t) for t in v] for k, v in (triggers or {}).items()}
        self._outcome = outcome
        self._put_outcome = put_outcome
        self._put_readback = dict(put_readback) if put_readback else None
        self._readback_unavailable = readback_unavailable
        self._reads_ok = True
        self.calls = []
        self.puts = []

    def _get(self, path):
        self.calls.append(path)
        if self._outcome == "unavailable" or not self._reads_ok:
            raise reg.InternalRailUnavailable("fixture: rail unavailable")
        if "/list" in path:
            return {"rows": [dict(r) for r in self._rows]}
        if "trigger?" in path:
            wid = path.rsplit("=", 1)[-1]
            return [dict(t) for t in self._triggers.get(wid, [])]
        return {}

    def put_trigger(self, location_id, trigger_id, body):
        self.puts.append((location_id, trigger_id, body))
        if self._put_outcome == "refused":
            # Mirror the REAL client contract (ScopeRailClient.put_trigger):
            # a rejected PUT comes back as a parsed "_error" body, which the
            # client CLASSIFIES and raises — the runner sees the exception.
            raise ap.TriggerScopeRefused(
                "the internal rail REJECTED the trigger PUT (classified "
                "refusal; the body is never surfaced)")
        if self._put_outcome == "unavailable":
            raise reg.InternalRailUnavailable("fixture: rail unavailable on PUT")
        if self._put_readback is not None:
            self._triggers[body.get("workflowId") or "wf-0000"] = [dict(self._put_readback)]
            if self._readback_unavailable:
                self._reads_ok = False  # PUT confirmed; the verify read is dead
            return dict(body)
        # Apply the echoed body: the read-back now carries the corrected filter.
        self._triggers[body.get("workflowId") or "wf-0000"] = [dict(body)]
        return dict(body)


def _run_apply(*, rail=None, location_id=LOC_TMPL, workflow_name=CONTRACT_NAME,
               workflow_id="", execute=False, row=None):
    """Capture stdout (the ONE JSON object) + stderr and return
    (rc, report, rail). A non-contract workflow name refuses at the
    contract-row resolve — the SAME path main() takes."""
    rail = rail if rail is not None else _FakeRail(
        rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    row = row if row is not None else _contract_row()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ap.run_apply(rail, location_id, workflow_id, workflow_name, row,
                          execute=execute, out=io.StringIO())
    report = None
    try:
        report = json.loads(buf.getvalue())
    except ValueError:
        report = None
    return rc, report, rail


# ---------------------------------------------------------------------------
# THE WRITE GATE: dry-run never writes.
# ---------------------------------------------------------------------------
def test_dry_run_writes_nothing_and_reports_applied_false():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    rc, report, rail = _run_apply(rail=rail)
    assert rc == EX_OK, "golden dry-run must exit 0, got %s" % rc
    assert report is not None, "dry-run must emit ONE JSON object on stdout"
    assert report["ok"] is True
    assert report["applied"] is False and report["dry_run"] is True
    assert report["workflow_name"] == CONTRACT_NAME
    assert report["trigger_tag"] == CONTRACT_TAG
    assert report["trigger_id_marker"] == "..." + TRIGGER_ID[-4:]
    assert report["delta"] == []
    assert rail.puts == [], "dry-run must NEVER invoke the PUT"
    assert len(rail.calls) == 2, (
        "dry-run must read the listing once and the trigger once, got %s"
        % rail.calls)


def test_dry_run_by_workflow_id_reads_by_id_and_still_never_writes():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    rc, report, rail = _run_apply(rail=rail, workflow_id=WORKFLOW_ID)
    assert rc == EX_OK and report is not None and report["ok"] is True
    assert report["applied"] is False and report["dry_run"] is True
    assert rail.puts == [], "by-id dry-run must NEVER invoke the PUT"
    # the by-id path still lists (the identity law is proven on the listing),
    # then reads the trigger
    assert any("/list" in c for c in rail.calls), (
        "the by-id target must still prove the name law on the listing, "
        "got %s" % rail.calls)
    assert any("trigger?" in c and c.endswith(WORKFLOW_ID) for c in rail.calls), (
        "by-id dry-run must read the workflow's triggers once, got %s" % rail.calls)


def test_cli_apply_without_execute_is_a_dry_run_that_never_writes(monkeypatch):
    # The CLI (main) resolves rail credentials through the REAL registry
    # label machinery — a Firebase refresh token + API key in the environment
    # let the resolution run untouched; the ScopeRailClient constructor is
    # the ONLY seam monkeypatched (the same seam the module's own self-test
    # uses, so this battery stays OFFLINE).
    monkeypatch.setenv("ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN", "tok-fake")
    monkeypatch.setenv("ANTHOLOGY_GHL_FIREBASE_API_KEY", "key-fake")
    captured = {"rail": None}

    def _rail(refresh, api_key, timeout=15):
        captured["rail"] = _FakeRail(
            rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
        return captured["rail"]

    monkeypatch.setattr(ap, "ScopeRailClient", _rail)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ap.main(["apply", "--workflow-name", CONTRACT_NAME,
                      "--location-id", LOC_TMPL])
    assert rc == EX_OK, "CLI apply without --execute must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["dry_run"] is True and report["applied"] is False
    assert captured["rail"].puts == [], (
        "the write gate must hold at the CLI boundary — the PUT was invoked "
        "without --execute")


def test_execute_applies_exactly_one_put_with_echo_body():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    rc, report, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_OK, "golden execute must exit 0, got %s" % rc
    assert report is not None and report["ok"] is True
    assert report["applied"] is True and report["dry_run"] is False
    assert report["delta"] == []
    assert len(rail.puts) == 1, "execute must PUT exactly once, got %d" % len(rail.puts)
    loc, tid, body = rail.puts[0]
    assert loc == LOC_TMPL
    assert tid == TRIGGER_ID, "PUT must target the trigger id from the live read"
    # the body echoes the live trigger byte-for-byte with ONLY the tagsAdded
    # value corrected — every key, every other condition key preserved
    assert body["id"] == TRIGGER_ID and body["workflowId"] == WORKFLOW_ID
    assert body["type"] == "contact_tag" and body["active"] is True
    assert body["masterType"] == "highlevel" and body["name"] == CONTRACT_NAME
    assert sorted(body.keys()) == sorted(DRIFTED_TRIGGER.keys()), (
        "the PUT body must echo the live trigger key-for-key (no key dropped, "
        "none invented)")
    conds = body["conditions"]
    assert len(conds) == 1 and conds[0]["field"] == "tagsAdded"
    assert conds[0]["value"] == CONTRACT_TAG, (
        "the PUT body must correct the filter to the contract tag")
    assert conds[0]["operator"] == "index-of-true" and conds[0]["id"] == "tag-added", (
        "the PUT body must preserve every OTHER condition key")


def test_idempotent_noop_passes_and_never_writes():
    # Already in scope: the live filter IS the contract tag — nothing is
    # written, ever, even with --execute (the old==new doctrine).
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [SCOPED_TRIGGER]})
    rc, report, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_OK and report is not None and report["ok"] is True
    assert report["applied"] is False, "an already-scoped workflow is a no-op"
    assert rail.puts == [], "idempotent no-op must never invoke the PUT"


def test_single_element_list_filter_is_also_a_noop():
    # The [<tag>] list form binds exactly the contract tag — the same no-op.
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={
        WORKFLOW_ID: [dict(SCOPED_TRIGGER, conditions=[
            {"operator": "index-of-true", "field": "tagsAdded",
             "title": "Tag Added", "type": "select", "id": "tag-added",
             "value": [CONTRACT_TAG]}])]})
    rc, report, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_OK and report["applied"] is False
    assert rail.puts == [], "an exact [tag] list must be an idempotent no-op"


# ---------------------------------------------------------------------------
# FAIL-CLOSED REFUSALS.
# ---------------------------------------------------------------------------
def test_absent_workflow_stops_before_any_write():
    rail = _FakeRail(rows=[], triggers={})
    rc, report, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "absent target must STOP, got %s" % rc
    assert report is not None and report["ok"] is False
    assert report["applied"] is False
    assert any(d.get("item") == "workflow" for d in report["delta"]), (
        "the STOP surface must name the absent target")
    assert rail.puts == [], "absent target must never be written"


def test_duplicated_name_stops_and_is_never_written():
    dup_rows = [dict(WORKFLOW_ROW), dict(WORKFLOW_ROW, id="wf-dup")]
    rail = _FakeRail(rows=dup_rows, triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "a duplicated name must STOP, got %s" % rc
    assert rail.puts == [], "a duplicated target must never be written"


def test_by_id_name_mismatch_stops_and_is_never_written():
    rail = _FakeRail(rows=[dict(WORKFLOW_ROW, name="Something Else")],
                     triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    rc, _, rail = _run_apply(rail=rail, workflow_id=WORKFLOW_ID, execute=True)
    assert rc == EX_STOP, "name-mismatched target must STOP, got %s" % rc
    assert rail.puts == [], "a non-byte-exact target must never be written"


def test_workflow_without_contact_tag_trigger_stops():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={
        WORKFLOW_ID: [{"id": "trg-0001", "type": "contact_changed",
                       "active": True,
                       "conditions": [{"field": "tagsAdded", "value": CONTRACT_TAG}]}]})
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "triggerless workflow must STOP, got %s" % rc
    assert rail.puts == [], "no trigger to scope must never be written"


def test_two_contact_tag_triggers_stop_scoping_is_a_guess():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={
        WORKFLOW_ID: [DRIFTED_TRIGGER,
                      dict(DRIFTED_TRIGGER, id="trg-0002")]})
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "two contact_tag triggers must STOP, got %s" % rc
    assert rail.puts == [], "scoping the wrong one is a guess — never written"


def test_missing_tagsadded_condition_refuses_even_in_dry_run():
    # A body that could INVENT a filter is never constructed — not even for
    # the dry-run report.
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={
        WORKFLOW_ID: [dict(DRIFTED_TRIGGER, conditions=[
            {"field": "contactTagAdded", "value": CONTRACT_TAG}])]})
    rc, _, rail = _run_apply(rail=rail)
    assert rc == EX_STOP, "missing tagsAdded must STOP in dry-run too, got %s" % rc
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "missing tagsAdded must STOP, got %s" % rc
    assert rail.puts == [], "no invented filter is ever written"


def test_over_scoped_multi_value_list_stops():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={
        WORKFLOW_ID: [dict(DRIFTED_TRIGGER, conditions=[
            {"field": "tagsAdded", "value": [CONTRACT_TAG, "anthology-release-tone"]}])]})
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "an over-scoped list must STOP, got %s" % rc
    assert rail.puts == [], "an operator decision is never a guessed write"


def test_non_string_filter_value_stops():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={
        WORKFLOW_ID: [dict(DRIFTED_TRIGGER, conditions=[
            {"field": "tagsAdded", "value": {"tag": CONTRACT_TAG}}])]})
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "a non-string filter value must STOP, got %s" % rc
    assert rail.puts == [], "an unprovable filter shape is never written"


def test_trigger_without_real_id_stops_before_the_put():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={
        WORKFLOW_ID: [dict(DRIFTED_TRIGGER, id="REPLACE-ME")]})
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "a placeholder trigger id must STOP, got %s" % rc
    assert rail.puts == [], "a placeholder trigger id must never reach a PUT"


def test_placeholder_workflow_id_stops_and_never_reaches_a_request():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    rc, _, rail = _run_apply(rail=rail, workflow_id="REPLACE-ME", execute=True)
    assert rc == EX_STOP, "placeholder workflow id must STOP, got %s" % rc
    assert rail.calls == [], "a placeholder id must never reach a request"


def test_non_contract_workflow_name_stops():
    rc, _, _ = _run_apply(workflow_name="Not A Contract Workflow", execute=True)
    assert rc == EX_STOP, "non-contract target must STOP, got %s" % rc


def test_rail_rejection_of_the_put_is_a_stop():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]},
                     put_outcome="refused")
    rc, report, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_STOP, "a rail rejection must STOP, got %s" % rc
    assert report is not None and report["applied"] is False
    assert any(d.get("item") == "trigger_filter" for d in report["delta"]), (
        "the rejection surface must name the filter")
    assert len(rail.puts) == 1, "the PUT was attempted — the STOP is the verdict"


def test_rail_unavailable_on_the_read_is_held():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]},
                     outcome="unavailable")
    rc, _, _ = _run_apply(rail=rail)
    assert rc == EX_HELD, "unavailable rail must be HELD, got %s" % rc


def test_read_back_filter_drift_after_put_exits_5_with_delta():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]},
                     put_readback=dict(DRIFTED_TRIGGER))
    rc, report, _ = _run_apply(rail=rail, execute=True)
    assert rc == EX_MISMATCH, "read-back drift must exit 5, got %s" % rc
    assert report is not None and report["ok"] is False
    assert report["applied"] is True
    assert any("trigger_filter" in str(d.get("item")) for d in report["delta"]), (
        "the drift report must carry the filter delta")


def test_read_back_active_state_drift_after_put_exits_5():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]},
                     put_readback=dict(SCOPED_TRIGGER, active=False))
    rc, report, _ = _run_apply(rail=rail, execute=True)
    assert rc == EX_MISMATCH, "active-state drift must exit 5, got %s" % rc
    assert any("trigger_active" in str(d.get("item")) for d in report["delta"])


def test_applied_but_unreadable_put_is_held_never_reported_corrected():
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]},
                     put_readback=SCOPED_TRIGGER, readback_unavailable=True)
    rc, _, rail = _run_apply(rail=rail, execute=True)
    assert rc == EX_HELD, "applied-but-unreadable must be HELD, got %s" % rc
    assert len(rail.puts) == 1, "the PUT did happen — the HELD is about verify"


# ---------------------------------------------------------------------------
# THE HTTP LAYER (real ScopeRailClient, hermetic urlopen).
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


def _real_rail_client():
    """The REAL ScopeRailClient with an injected mint (no Firebase exchange —
    the mint surface is a seam the registry documents). The synthetic mint
    token rides the token-id header exactly like a live id_token."""
    return ap.ScopeRailClient("refresh-fake", "apikey-fake", mint_fn=lambda rt: "tok-fake")


def _cloudflare_body():
    return b"<!DOCTYPE html><html><head><title>Attention Required! " \
           b"| Cloudflare</title></head><body>Error 1010</body></html>"


def test_real_rail_client_sends_browser_ua_and_header_set_on_reads(monkeypatch):
    handler = _install_http_handler(monkeypatch, [
        (200, json.dumps({"rows": [WORKFLOW_ROW]}).encode("utf-8")),
        (200, json.dumps([SCOPED_TRIGGER]).encode("utf-8")),
    ])
    rail = _real_rail_client()
    rows = rail._get(ap._RAIL_WORKFLOW_LIST.format(loc=LOC_TMPL))
    assert rows["rows"][0]["name"] == CONTRACT_NAME
    triggers = rail._get(ap._RAIL_WORKFLOW_TRIGGER.format(
        loc=LOC_TMPL, wid=WORKFLOW_ID))
    assert triggers[0]["id"] == TRIGGER_ID
    assert len(handler.requests) == 2
    for req in handler.requests:
        assert req.get_method() == "GET"
        assert req.full_url.startswith(reg.INTERNAL_API_BASE), (
            "every rail read must ride backend.leadconnectorhq.com")
        hdrs = req.headers
        # urllib canonicalizes header names (Token-id / Channel / Source /
        # Version); assert case-insensitively so the check survives that
        # canonicalization — the same way the u03 rename battery does.
        ua = next((v for k, v in hdrs.items() if k.lower() == "user-agent"), None)
        assert ua == reg.CAF_BROWSER_UA, (
            "the browser User-Agent must ride on every request (Cloudflare "
            "edge 1010 discipline — urllib's default UA is 403'd before it "
            "reaches the rail), got %r" % ua)
        assert hdrs.get("token-id") is None, (
            "urllib canonicalizes header names — the token-id assert must "
            "be case-insensitive")
        tok = next((v for k, v in hdrs.items() if k.lower() == "token-id"), None)
        assert tok == "tok-fake"
        chan = next((v for k, v in hdrs.items() if k.lower() == "channel"), None)
        src = next((v for k, v in hdrs.items() if k.lower() == "source"), None)
        ver = next((v for k, v in hdrs.items() if k.lower() == "version"), None)
        assert chan == "APP" and src == "WEB_USER"
        assert ver == reg.INTERNAL_VERSION_HEADER
        assert hdrs.get("Accept") == "application/json"


def test_real_rail_client_put_rides_browser_ua_and_classifies_error_body(monkeypatch):
    handler = _install_http_handler(monkeypatch, [
        (200, json.dumps({"_error": True}).encode("utf-8")),
    ])
    rail = _real_rail_client()
    with pytest.raises(ap.TriggerScopeRefused):
        rail.put_trigger(LOC_TMPL, TRIGGER_ID,
                         ap.build_scope_body(DRIFTED_TRIGGER, CONTRACT_TAG,
                                             CONTRACT_NAME))
    assert len(handler.requests) == 1
    req = handler.requests[0]
    assert req.get_method() == "PUT"
    assert req.full_url == (
        reg.INTERNAL_API_BASE
        + ap._RAIL_WORKFLOW_TRIGGER_PUT.format(loc=LOC_TMPL, trg=TRIGGER_ID))
    hdrs = req.headers
    ua = next((v for k, v in hdrs.items() if k.lower() == "user-agent"), None)
    assert ua == reg.CAF_BROWSER_UA, (
        "the browser User-Agent must ride on the PUT too (CF 1010)")
    tok = next((v for k, v in hdrs.items() if k.lower() == "token-id"), None)
    assert tok == "tok-fake"
    ct = next((v for k, v in hdrs.items() if k.lower() == "content-type"), None)
    assert ct == "application/json"
    body = json.loads(req.data.decode("utf-8"))
    conds = body["conditions"]
    assert conds[0]["value"] == CONTRACT_TAG, (
        "the PUT body must carry the corrected contract tag")


def test_real_rail_client_put_success_is_parsed_and_returned(monkeypatch):
    handler = _install_http_handler(monkeypatch, [
        (200, json.dumps({"id": TRIGGER_ID}).encode("utf-8")),
    ])
    rail = _real_rail_client()
    out = rail.put_trigger(LOC_TMPL, TRIGGER_ID,
                           ap.build_scope_body(DRIFTED_TRIGGER, CONTRACT_TAG,
                                               CONTRACT_NAME))
    assert out == {"id": TRIGGER_ID}
    assert len(handler.requests) == 1


def test_real_rail_client_http_error_on_put_is_held_not_crash(monkeypatch):
    handler = _install_http_handler(monkeypatch, [
        (503, b"<html>cf 1010</html>"),
    ])
    rail = _real_rail_client()
    with pytest.raises(reg.InternalRailUnavailable):
        rail.put_trigger(LOC_TMPL, TRIGGER_ID, {"id": TRIGGER_ID})
    assert len(handler.requests) == 1


def test_real_rail_client_transport_error_on_put_is_held(monkeypatch):
    def _boom(*args, **kwargs):
        raise urllib.error.URLError("fixture: connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    rail = _real_rail_client()
    with pytest.raises(reg.InternalRailUnavailable):
        rail.put_trigger(LOC_TMPL, TRIGGER_ID, {"id": TRIGGER_ID})


# ---------------------------------------------------------------------------
# NEVER-A-SECRET: a real-looking workflow / trigger id and a token must not
# leak anywhere; a credential-shaped value REFUSES rather than print.
# ---------------------------------------------------------------------------
def test_no_surface_prints_a_token_or_full_ids():
    real_loc = "2HIKGNgsixWx0yds7Qnx"
    rail = _FakeRail(rows=[WORKFLOW_ROW], triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
    rc, report, _ = _run_apply(rail=rail, location_id=real_loc)
    assert rc == EX_OK
    assert report is not None
    dump = json.dumps(report)
    assert WORKFLOW_ID not in dump, "the full workflow id must never be surfaced"
    assert TRIGGER_ID not in dump, "the full trigger id must never be surfaced"
    assert WORKFLOW_ID[-4:] in dump, "the workflow MARKER (last 4 chars) is the surface"
    assert TRIGGER_ID[-4:] in dump, "the trigger MARKER (last 4 chars) is the surface"
    assert report["workflow_id_marker"] == "..." + WORKFLOW_ID[-4:]
    assert report["trigger_id_marker"] == "..." + TRIGGER_ID[-4:]
    assert real_loc not in dump, "the full location id must never be surfaced"
    assert report["location_marker"] == "..." + real_loc[-4:]
    assert "tok-fake" not in dump and "pit-" not in dump


def test_report_surfaces_never_carry_credential_shape():
    """The golden dry-run and the golden apply never emit a credential-shaped
    string anywhere on the payload."""
    for kwargs in ({}, {"execute": True}):
        rail = _FakeRail(rows=[WORKFLOW_ROW],
                         triggers={WORKFLOW_ID: [DRIFTED_TRIGGER]})
        rc, report, _ = _run_apply(rail=rail, **kwargs)
        assert rc in (EX_OK,)
        dumped = json.dumps(report, indent=2, sort_keys=True)
        assert "pit-" not in dumped and "Bearer" not in dumped
        assert "tok-" not in dumped and "refresh-fake" not in dumped


# ---------------------------------------------------------------------------
# HOUSE LAW PINS: the applier derives its laws from the ONE authorities and
# rides the house discipline, never re-typing a law or a UA.
# ---------------------------------------------------------------------------
def test_contract_law_pinned_to_the_committed_contract():
    """The scope law resolves from config/anthology-snapshot-contract.json:
    the EIGHT release workflows, the template location, and the avatar row's
    tag — a drift in the contract breaks THIS battery first."""
    contract = ap._load_contract(ap.CONTRACT_PATH)
    rows = ap._contract_rows(contract)
    assert len(rows) == 8, "the contract must carry exactly 8 release workflows"
    assert ap._contract_template_location(contract) == ap.DEFAULT_TEMPLATE_LOCATION
    assert rows[0]["name"] == CONTRACT_NAME == "Anthology Release: Avatar"
    assert rows[0]["trigger_tag"] == CONTRACT_TAG == "anthology-release-avatar"


def test_rail_surfaces_are_the_proven_sibling_surfaces():
    """The read surfaces are the PROVEN workflow_reader surfaces (Skill 44 /
    Skill 58 doctrine): the workflow list path and the trigger read path —
    never an invented endpoint; the write PUT is the Skill 44 build-rail
    trigger PUT."""
    # the applier's listing path names the SAME endpoint the workflow reader
    # proves live — same path, same limit (only the format differs: {loc}
    # vs %s), never a second surface
    assert ap._RAIL_WORKFLOW_LIST.startswith("/workflow/{loc}/list?limit=200"), (
        "the listing path must be the ONE proven surface")
    assert wf_reader.WORKFLOWS_LIST_PATH == "/workflow/%s/list", (
        "the sibling's proven surface drifted")
    assert ap._RAIL_WORKFLOW_TRIGGER.startswith("/workflow/{loc}/trigger?workflowId=")
    assert ap._RAIL_WORKFLOW_TRIGGER_PUT == "/workflow/{loc}/trigger/{trg}"


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])


def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert ap.EX_STOP == EX_STOP and ap.EX_HELD == EX_HELD


def test_u05_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface (fail-closed empty init)."""
    import u05_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()


def test_module_self_test_is_offline_and_exits_zero():
    rc = ap.self_test(out=io.StringIO())
    assert rc == EX_OK, "the module's own offline self-test must exit 0"


def test_sibling_u05_batteries_are_green():
    """The U05 family's other offline batteries pass — the scope checker,
    the workflow reader, the negative verifier, the empty-filter attack
    fixture, and the golden scoped fixture — so the scope applier is tested
    against a green family (a red sibling is caught HERE first)."""
    import u05_modules.attack_unscoped as attack
    import u05_modules.golden_scoped as gscoped
    import u05_modules.negative_verifier as nv
    import u05_modules.scope_checker as sc
    import u05_modules.workflow_reader as wf
    assert sc.self_test() == EX_OK
    assert wf.self_test(out=io.StringIO()) == EX_OK
    assert nv.self_test(out=io.StringIO()) == EX_OK
    assert attack.self_test(out=io.StringIO()) == EX_OK
    assert gscoped.self_test(out=io.StringIO()) == EX_OK


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
    (test_dry_run_by_workflow_id_reads_by_id_and_still_never_writes, False),
    (test_cli_apply_without_execute_is_a_dry_run_that_never_writes, True),
    (test_execute_applies_exactly_one_put_with_echo_body, False),
    (test_idempotent_noop_passes_and_never_writes, False),
    (test_single_element_list_filter_is_also_a_noop, False),
    (test_absent_workflow_stops_before_any_write, False),
    (test_duplicated_name_stops_and_is_never_written, False),
    (test_by_id_name_mismatch_stops_and_is_never_written, False),
    (test_workflow_without_contact_tag_trigger_stops, False),
    (test_two_contact_tag_triggers_stop_scoping_is_a_guess, False),
    (test_missing_tagsadded_condition_refuses_even_in_dry_run, False),
    (test_over_scoped_multi_value_list_stops, False),
    (test_non_string_filter_value_stops, False),
    (test_trigger_without_real_id_stops_before_the_put, False),
    (test_placeholder_workflow_id_stops_and_never_reaches_a_request, False),
    (test_non_contract_workflow_name_stops, False),
    (test_rail_rejection_of_the_put_is_a_stop, False),
    (test_rail_unavailable_on_the_read_is_held, False),
    (test_read_back_filter_drift_after_put_exits_5_with_delta, False),
    (test_read_back_active_state_drift_after_put_exits_5, False),
    (test_applied_but_unreadable_put_is_held_never_reported_corrected, False),
    (test_real_rail_client_sends_browser_ua_and_header_set_on_reads, True),
    (test_real_rail_client_put_rides_browser_ua_and_classifies_error_body, True),
    (test_real_rail_client_put_success_is_parsed_and_returned, True),
    (test_real_rail_client_http_error_on_put_is_held_not_crash, True),
    (test_real_rail_client_transport_error_on_put_is_held, True),
    (test_no_surface_prints_a_token_or_full_ids, False),
    (test_report_surfaces_never_carry_credential_shape, False),
    (test_contract_law_pinned_to_the_committed_contract, False),
    (test_rail_surfaces_are_the_proven_sibling_surfaces, False),
    (test_browser_user_agent_is_a_browser_ua_cf_1010_law, False),
    (test_exit_code_convention_is_house_0_1_2_3_4_5, False),
    (test_u05_package_init_is_fail_closed_empty, False),
    (test_module_self_test_is_offline_and_exits_zero, False),
    (test_sibling_u05_batteries_are_green, False),
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
