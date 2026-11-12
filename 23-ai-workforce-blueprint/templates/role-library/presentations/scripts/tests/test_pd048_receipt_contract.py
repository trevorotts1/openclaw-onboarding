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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
