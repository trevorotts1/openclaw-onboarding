#!/usr/bin/env python3
"""test_pd048_receipt_contract.py -- PD-048a: the page-install receipt carries
the fields the phase check reads.

THE DEFECT (finding PD-048, Critical): the installer proved its own work with
NESTED fields (execution.execution_id, input_hashes{}, scope.location_id,
remote.funnel_id/page_ids), while the phase's own check runs
`phase_verifiers._make_pu_verifier` -> `_pu_check_receipt_identity` FIRST and
reads TOP-LEVEL text fields only (execution_id, input_sha256, location_id and a
remote id). So a completed, adapter-proven install (`validate_receipt` -> True)
still failed `phase_verifiers.verify(...)` and the engine re-ran the install
forever, sending raw check text to the client.

This file pins the ADDITIVE contract:
  * a completed MemoryPageAdapter install passes the real phase check for
    P-U-GHL-SALES (A1) and P-U-GHL-VSL (A2);
  * the completed gate pair passes the real phase check for P-U-FORM-GATE (A3);
  * a pending receipt still fails (A4) and the hand-made "perfect fake" receipt
    from test_pres011_ghl_external.py still fails (A5);
  * every written receipt (pending, blocked, complete) carries the flat fields,
    computed from the nested ones (the change itself).

Offline and deterministic: Memory adapters only, and the GHL media read-back
transport is stubbed (the check only uses it for media receipts, which these are
not, so no request is ever made).

Flat file inside tests/, manages its own import path -- matching every sibling
in this directory.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import pytest  # noqa: E402

import ghl_external_installer as gx  # noqa: E402
import phase_verifiers as pv  # noqa: E402

try:  # the read-back transport the strict receipt check probes (never called
    import ghl_media as _ghl_media  # noqa: E402  here: these receipts carry no media id)
except Exception:  # pragma: no cover -- box without the Skill-48 sibling
    _ghl_media = None
# A5 reuses the hand-made "perfect fake" from the PRES-011 suite verbatim --
# one definition, never a second copy that could drift.
from test_pres011_ghl_external import _perfect_fake_receipt  # noqa: E402

# A location id that is NOT placeholder-shaped (the strict receipt check refuses
# any value containing test/example/placeholder/changeme/todo).
LOC = "locPD048ACLIENT"
ENV = {"GOHIGHLEVEL_LOCATION_ID": LOC}
SALES_PRE = {"WANT_SALES_CHECKOUT": "yes"}
VSL_PRE = {"WANT_VSL_PAGE": "yes"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture(autouse=True)
def _box_has_ghl(monkeypatch):
    """Simulate a box where GHL is configured, so the phase check's read-only
    media list-back does not NOTE-skip every receipt (phase_verifiers fails on
    any reason, NOTE included). No request is made: these receipts carry no
    file_id/media_id, which is the only thing that path ever lists."""
    monkeypatch.setenv("GOHIGHLEVEL_LOCATION_ID", LOC)
    if _ghl_media is not None:
        monkeypatch.setattr(_ghl_media, "resolve_location_pit",
                            lambda: "pit-pd048a-test-double", raising=False)
        monkeypatch.setattr(_ghl_media, "resolve_location_id", lambda: LOC,
                            raising=False)


def _intake(tmp_path: Path, pre: dict) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({
        "deck_slug": "acme-widget",
        "company": "Acme Co",
        "pre_presentation_capture": pre,
        "deck_brief": {"OFFER_NAME": "Acme Widget Mastery"},
    }))
    return rd


def _seed_pages(rd: Path) -> None:
    (rd / "working" / "sales-checkout" / "html").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "vsl" / "html").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "sales-checkout" / "html" / "sales.html").write_text(
        "<h1>Sales</h1>" + "x" * 300)
    (rd / "working" / "sales-checkout" / "html" / "checkout.html").write_text(
        "<h1>Checkout</h1>" + "x" * 300)
    (rd / "working" / "vsl" / "html" / "vsl.html").write_text(
        "<h1>VSL</h1><video src='m.mp4'></video>" + "x" * 300)


# ---------------------------------------------------------------------------
# A1 / A2 -- a COMPLETED install passes the phase's own check
# ---------------------------------------------------------------------------
def test_a1_completed_sales_install_passes_the_phase_check(tmp_path):
    rd = _intake(tmp_path, SALES_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                   page_adapter=gx.MemoryPageAdapter(LOC),
                                   env=ENV)
    assert rc == gx.EXIT_OK, receipt
    assert receipt["status"] == gx.STATUS_COMPLETE
    # The installer's own proof still holds ...
    ok, detail, _d = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
    assert ok is True, detail
    # ... and the phase's own check now accepts the same receipt.
    ok, reasons = pv.verify(gx.PHASE_GHL_SALES, rd)
    assert ok is True, reasons
    assert not [r for r in reasons if not r.startswith("NOTE")], reasons


def test_a2_completed_vsl_install_passes_the_phase_check(tmp_path):
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_VSL,
                                   page_adapter=gx.MemoryPageAdapter(LOC),
                                   env=ENV)
    assert rc == gx.EXIT_OK, receipt
    assert receipt["status"] == gx.STATUS_COMPLETE
    ok, reasons = pv.verify(gx.PHASE_GHL_VSL, rd)
    assert ok is True, reasons


# ---------------------------------------------------------------------------
# A3 -- the completed gate pair passes the phase check
# ---------------------------------------------------------------------------
def test_a3_completed_gate_pair_passes_the_phase_check(tmp_path):
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE,
                                   gate_adapter=gx.MemoryGateAdapter(LOC),
                                   env=ENV)
    assert rc == gx.EXIT_OK, receipt
    ok, detail, _d = gx.validate_receipt(rd, gx.PHASE_FORM_GATE, env=ENV)
    assert ok is True, detail
    ok, reasons = pv.verify(gx.PHASE_FORM_GATE, rd)
    assert ok is True, reasons
    # `_pu_check_form_gate` reads a top-level name plus fields/steps: the plan's
    # own contract is carried there, one definition per artifact.
    form = json.loads((rd / "ecosystem" / "gate-form.json").read_text())
    flow = json.loads((rd / "workflows" / "gate-workflow.json").read_text())
    assert form["name"] and form["fields"]
    assert flow["name"] and flow["steps"]


# ---------------------------------------------------------------------------
# A4 -- a pending receipt is still not a completed install
# ---------------------------------------------------------------------------
def test_a4_pending_receipt_still_fails_the_phase_check(tmp_path):
    rd = _intake(tmp_path, SALES_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES, env=ENV)
    assert rc == gx.EXIT_OK
    assert receipt["status"] == gx.STATUS_PENDING
    ok, reasons = pv.verify(gx.PHASE_GHL_SALES, rd)
    assert ok is False, reasons
    assert reasons


def test_a4_pending_gate_receipts_still_fail_the_phase_check(tmp_path):
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE, env=ENV)
    assert rc == gx.EXIT_OK
    assert receipt["status"] == gx.STATUS_PENDING
    ok, reasons = pv.verify(gx.PHASE_FORM_GATE, rd)
    assert ok is False, reasons
    assert any("pending" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# A5 -- the hand-made perfect fake is still refused
# ---------------------------------------------------------------------------
def test_a5_hand_made_fake_receipt_still_fails(tmp_path):
    rd = _intake(tmp_path, SALES_PRE)
    _seed_pages(rd)
    fake = _perfect_fake_receipt(rd, gx.PHASE_GHL_SALES)
    for p in gx.receipt_paths(rd, gx.PHASE_GHL_SALES):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(fake), encoding="utf-8")
    ok, detail, _d = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
    assert ok is False, detail
    ok, reasons = pv.verify(gx.PHASE_GHL_SALES, rd)
    assert ok is False, reasons


# ---------------------------------------------------------------------------
# The change itself -- flat fields on every receipt the installer writes,
# computed from the nested values (never a second source of truth).
# ---------------------------------------------------------------------------
def test_completed_receipt_carries_flat_fields_equal_to_nested(tmp_path):
    rd = _intake(tmp_path, SALES_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                   page_adapter=gx.MemoryPageAdapter(LOC),
                                   env=ENV)
    assert rc == gx.EXIT_OK
    data = gx.load_receipt(rd, gx.PHASE_GHL_SALES)
    # nested blocks are untouched
    assert data["remote"]["funnel_id"]
    assert data["execution"]["execution_id"]
    # and the flat fields mirror them
    assert data["execution_id"] == data["execution"]["execution_id"]
    assert data["location_id"] == data["scope"]["location_id"] == LOC
    assert data["funnel_id"] == data["remote"]["funnel_id"]
    assert data["page_id"] == data["remote"]["sales_page_id"]
    # input_sha256 is the sha256 of the canonical JSON of the nested hashes.
    assert data["input_sha256"] == gx._canonical_json_sha256(data["input_hashes"])
    assert SHA256_RE.match(data["input_sha256"]), data["input_sha256"]


def test_blocked_receipt_carries_the_flat_fields_and_no_invented_ids(tmp_path):
    rd = _intake(tmp_path, SALES_PRE)  # no page HTML on disk
    rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                   page_adapter=gx.MemoryPageAdapter(LOC),
                                   env=ENV)
    assert rc == gx.EXIT_BLOCKED, receipt
    data = gx.load_receipt(rd, gx.PHASE_GHL_SALES)
    assert data["status"] == gx.STATUS_BLOCKED
    assert data["execution_id"] == data["execution"]["execution_id"]
    assert SHA256_RE.match(data["input_sha256"])
    # No adapter ran, so no remote id is invented.
    assert data["funnel_id"] == ""
    assert data["page_id"] == ""


# ---------------------------------------------------------------------------
# PD-069 A1 -- the check the ENGINE runs. The acceptance names
# `phase_verifiers.PHASE_VERIFIERS[...]` itself, not the `verify()` wrapper
# whose SIMULATED/provenance guards sit in front of it, so these rows call the
# registered function directly on the run dir.
#
# A1.1 / A1.2: a COMPLETED in-memory install for P-U-GHL-VSL and
# P-U-FORM-GATE passes the registered check -- i.e. the receipt carries the
# flat fields that check reads (execution_id, input_sha256, location_id, a
# remote id; name/fields/steps for the gate pair).
# A1.3: a PENDING plan fails with the installer's own "pending" reason, not
# with a shape complaint -- so the engine reports an honest pause, never
# "the artifact is malformed".
# A1.4 / A1.5 are the NEGATIVE CONTROLS: delete the flat fields the receipt
# carries and the same check turns RED with a shape reason. Without them the
# pass rows would prove nothing.
# ---------------------------------------------------------------------------
SHAPE_MARKERS = (
    "no operation name",
    "no fields list",
    "no actions/steps list",
    "carries no schema_version",
    "carries no run scope",
    "carries no execution_id",
    "carries no revision/input hash",
    "carries no remote artifact id",
    "carries no location_id",
    "reads as a placeholder",
    "file not found",
    "file is zero bytes",
    "not valid JSON",
)

def _shape_reasons(reasons):
    return [r for r in reasons if any(m in r for m in SHAPE_MARKERS)]

def test_pd069_a1_completed_vsl_install_passes_the_registered_check(tmp_path):
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_VSL,
                                   page_adapter=gx.MemoryPageAdapter(LOC),
                                   env=ENV)
    assert rc == gx.EXIT_OK, receipt
    assert receipt["status"] == gx.STATUS_COMPLETE
    ok, reasons = pv.PHASE_VERIFIERS["P-U-GHL-VSL"](rd)
    assert ok is True, reasons
    assert not _shape_reasons(reasons), reasons

def test_pd069_a1_completed_gate_pair_passes_the_registered_check(tmp_path):
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE,
                                   gate_adapter=gx.MemoryGateAdapter(LOC),
                                   env=ENV)
    assert rc == gx.EXIT_OK, receipt
    assert receipt["status"] == gx.STATUS_COMPLETE
    ok, reasons = pv.PHASE_VERIFIERS["P-U-FORM-GATE"](rd)
    assert ok is True, reasons
    assert not _shape_reasons(reasons), reasons

def test_pd069_a1_pending_gate_plan_fails_as_pending_not_shape(tmp_path):
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE, env=ENV)
    assert rc == gx.EXIT_OK, receipt
    assert receipt["status"] == gx.STATUS_PENDING
    ok, reasons = pv.PHASE_VERIFIERS["P-U-FORM-GATE"](rd)
    assert ok is False, reasons
    joined = " | ".join(reasons)
    assert "pending_external_execution" in joined, reasons
    assert not _shape_reasons(reasons), reasons

def test_pd069_a1_control_stripping_gate_flat_fields_turns_the_check_red(tmp_path):
    """Same pending pair, flat name/fields/steps deleted (the pre-PD-048a
    receipt): the check must fall back to a SHAPE reason and lose the pending
    reason -- proving the pass/fail split above is caused by the fields."""
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, _receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE, env=ENV)
    assert rc == gx.EXIT_OK
    for p in gx.receipt_paths(rd, gx.PHASE_FORM_GATE):
        data = json.loads(p.read_text(encoding="utf-8"))
        for key in ("name", "fields", "steps"):
            data.pop(key, None)
        p.write_text(json.dumps(data), encoding="utf-8")
    ok, reasons = pv.PHASE_VERIFIERS["P-U-FORM-GATE"](rd)
    assert ok is False, reasons
    assert _shape_reasons(reasons), reasons
    assert not any("pending_external_execution" in r for r in reasons), reasons

def test_pd069_a1_control_stripping_vsl_flat_fields_turns_the_check_red(tmp_path):
    """The completed VSL receipt with its flat fields deleted: the registered
    check must fail naming the identity fields -- proving it really reads the
    file on disk, not the installer's return value."""
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    rc, _receipt = gx.execute_phase(rd, gx.PHASE_GHL_VSL,
                                    page_adapter=gx.MemoryPageAdapter(LOC),
                                    env=ENV)
    assert rc == gx.EXIT_OK
    p = gx.receipt_paths(rd, gx.PHASE_GHL_VSL)[0]
    data = json.loads(p.read_text(encoding="utf-8"))
    for key in ("execution_id", "input_sha256", "location_id", "funnel_id",
                "page_id"):
        data.pop(key, None)
    p.write_text(json.dumps(data), encoding="utf-8")
    ok, reasons = pv.PHASE_VERIFIERS["P-U-GHL-VSL"](rd)
    assert ok is False, reasons
    assert _shape_reasons(reasons), reasons


# ---------------------------------------------------------------------------
# PD-217 -- the install receipt must match RECORDED ids.
#
# THE DEFECT: the ledger-agreement loop only failed when the receipt's id and
# the ops ledger's id were BOTH present and DIFFERENT. A receipt naming an id
# this run's ledger never recorded (ledger value absent) sailed through, so a
# fabricated id was accepted as proof of an install. The rule now fails on an
# absent ledger value exactly as on a mismatch, with one named message.
#
# Each row is its own BEFORE/AFTER pair on the same run dir: the completed
# install validates with the ledger intact, then the ledger loses the id (or
# records a different one) and the SAME receipt stops validating, naming it.
# ---------------------------------------------------------------------------
PD217_MSG = "receipt id not recorded in this run's operations ledger"


def _edit_ledger_remote(rd: Path, phase_id: str, key: str, value) -> None:
    """Rewrite ONE id in this run's ops ledger: value=None deletes it."""
    ops = gx.load_ops(rd)
    remote = ops[phase_id].setdefault("remote", {})
    if value is None:
        remote.pop(key, None)
    else:
        remote[key] = value
    gx._write_json_atomic(rd / gx.OPS_LEDGER_REL, ops)


def _complete_install(rd: Path, phase_id: str) -> None:
    if phase_id == gx.PHASE_FORM_GATE:
        rc, receipt = gx.execute_phase(rd, phase_id,
                                       gate_adapter=gx.MemoryGateAdapter(LOC),
                                       env=ENV)
    else:
        rc, receipt = gx.execute_phase(rd, phase_id,
                                       page_adapter=gx.MemoryPageAdapter(LOC),
                                       env=ENV)
    assert rc == gx.EXIT_OK, receipt
    assert receipt["status"] == gx.STATUS_COMPLETE
    ok, detail, _d = gx.validate_receipt(rd, phase_id, env=ENV)
    assert ok is True, detail


@pytest.mark.parametrize("phase,key,pre", [
    (gx.PHASE_GHL_SALES, "funnel_id", SALES_PRE),
    (gx.PHASE_GHL_SALES, "sales_page_id", SALES_PRE),
    (gx.PHASE_GHL_SALES, "checkout_page_id", SALES_PRE),
    (gx.PHASE_GHL_VSL, "funnel_id", VSL_PRE),
    (gx.PHASE_GHL_VSL, "vsl_page_id", VSL_PRE),
])
def test_pd217_a1_page_receipt_id_absent_from_the_ledger_fails(
        tmp_path, phase, key, pre):
    rd = _intake(tmp_path, pre)
    _seed_pages(rd)
    _complete_install(rd, phase)
    _edit_ledger_remote(rd, phase, key, None)
    ok, detail, _d = gx.validate_receipt(rd, phase, env=ENV)
    assert ok is False, detail
    assert PD217_MSG in detail, detail
    assert key in detail, detail


@pytest.mark.parametrize("key", ["form_id", "workflow_id"])
def test_pd217_a1_gate_receipt_id_absent_from_the_ledger_fails(tmp_path, key):
    rd = _intake(tmp_path, VSL_PRE)
    _seed_pages(rd)
    _complete_install(rd, gx.PHASE_FORM_GATE)
    _edit_ledger_remote(rd, gx.PHASE_FORM_GATE, key, None)
    ok, detail, _d = gx.validate_receipt(rd, gx.PHASE_FORM_GATE, env=ENV)
    assert ok is False, detail
    assert PD217_MSG in detail, detail
    assert key in detail, detail


@pytest.mark.parametrize("phase,key,pre", [
    (gx.PHASE_GHL_SALES, "sales_page_id", SALES_PRE),
    (gx.PHASE_FORM_GATE, "workflow_id", VSL_PRE),
])
def test_pd217_a1_a_different_ledger_id_fails_with_the_same_message(
        tmp_path, phase, key, pre):
    """The old mismatch branch keeps its teeth, now under one message."""
    rd = _intake(tmp_path, pre)
    _seed_pages(rd)
    _complete_install(rd, phase)
    _edit_ledger_remote(rd, phase, key, "page_someone_elses")
    ok, detail, _d = gx.validate_receipt(rd, phase, env=ENV)
    assert ok is False, detail
    assert PD217_MSG in detail, detail


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
