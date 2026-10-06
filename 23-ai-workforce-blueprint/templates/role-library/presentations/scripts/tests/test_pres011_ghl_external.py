#!/usr/bin/env python3
"""test_pres011_ghl_external.py -- PRES-011: external GHL operations leave the
text-only artifact writer.

THE DEFECT: P-U-FORM-GATE, P-U-GHL-SALES and P-U-GHL-VSL declared
executor.kind=agent, so dispatcher.dispatch_one authored their "completion"
by writing model text to one artifact file. A JSON-looking receipt with no
GHL form/workflow/page behind it passed the generic presence verifier.
The fix (ghl_external_installer.py, same wave): explicit executor
capabilities (text_artifact vs ghl_page_install/ghl_workflow_install),
preflight refusal of text-routed external phases, client-scoped Skill 06/44
adapters whose tool results alone write execution receipts, company/run/
location-bound receipts with input hashes + execution_id + remote readback,
and durable dispatched/running/remote-created/verified states with resumable
next actions.

Maps to QC-PRES-011 checks 1-3 (check 4 is future live acceptance, recorded
in run/evidence, not performed here):

  1. Fake model returns a perfect-looking receipt; no external phase can
     complete from that output.
  2. Mock Skill 06/44 adapters returning real IDs; remote readback required
     before completion; tool calls carry the correct client location.
  3. Kill after remote creation but before final receipt: resume reuses the
     recorded remote ID, creates no duplicate, continues.

Plus the TODO step-1 preflight gate, the manifest wiring pins, and the gate
defer/waived/fail_closed mechanic (delegated to the page builders' own
resolvers, never re-derived).

Offline only: MemoryPageAdapter/MemoryGateAdapter stand in for Skill 06/44.
No network, no GHL call, no real credentials (env dicts are passed
explicitly, never the process environment).

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import ghl_external_installer as gx  # noqa: E402
import phase_verifiers as pv  # noqa: E402

ENV = {"GOHIGHLEVEL_LOCATION_ID": "locPRES011TEST"}
LOC = "locPRES011TEST"

SALES_PRE = {"WANT_SALES_CHECKOUT": "yes"}
VSL_PRE = {"WANT_VSL_PAGE": "yes"}


def _intake(tmp_path: Path, pre: dict, deck_slug: str = "acme-widget") -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({
        "deck_slug": deck_slug,
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


def _perfect_fake_receipt(rd: Path, phase_id: str) -> dict:
    """A model-fabricated receipt: schema-correct, IDs present, readback
    shaped correctly -- but never produced by an adapter run (no ops-ledger
    entry, no input hashes)."""
    scope = {"deck_slug": "acme-widget", "run_id": "run",
             "company": "Acme Co", "location_id": LOC}
    if phase_id == gx.PHASE_FORM_GATE:
        return {
            "schema_version": gx.RECEIPT_SCHEMA, "phase": phase_id,
            "artifact": "ecosystem/gate-form.json",
            "deck_slug": "acme-widget", "run_id": "run", "scope": scope,
            "input_hashes": {},
            "execution": {"execution_id": "gx_fakefakefake",
                          "started_at": "2026-09-09T00:00:00Z",
                          "adapter": "model-text"},
            "form": {"name": "ZHC acme-widget VSL Gate",
                     "form_id": "form_COUNTERFEIT"},
            "remote": {"form_id": "form_COUNTERFEIT",
                       "workflow_id": "wf_COUNTERFEIT"},
            "readback": {"ok": True, "checked_at": "2026-09-09T00:00:00Z",
                         "form": {"form_id": "form_COUNTERFEIT",
                                  "location_id": LOC, "workflow_ids": ["wf_COUNTERFEIT"],
                                  "http": 200},
                         "workflow": {"workflow_id": "wf_COUNTERFEIT",
                                      "form_id": "form_COUNTERFEIT",
                                      "location_id": LOC, "draft": True,
                                      "http": 200}},
            "status": gx.STATUS_COMPLETE, "blocker": None,
            "built_at": "2026-09-09T00:00:00Z",
        }
    key = "sales" if phase_id == gx.PHASE_GHL_SALES else "vsl"
    pages = (["sales", "checkout"] if phase_id == gx.PHASE_GHL_SALES
             else ["vsl"])
    remote = {"funnel_id": "funnel_COUNTERFEIT"}
    rb_pages = {}
    for pg in pages:
        pid = f"page_COUNTERFEIT_{pg}"
        remote[f"{pg}_page_id"] = pid
        rb_pages[pid] = {"page_id": pid, "funnel_id": "funnel_COUNTERFEIT",
                         "location_id": LOC, "version": 1, "draft": True,
                         "slug": f"acme-widget-{pg}"}
    _ = key
    return {
        "schema_version": gx.RECEIPT_SCHEMA, "phase": phase_id,
        "deck_slug": "acme-widget", "run_id": "run", "scope": scope,
        "input_hashes": {},
        "execution": {"execution_id": "gx_fakefakefake",
                      "started_at": "2026-09-09T00:00:00Z",
                      "adapter": "model-text"},
        "remote": remote,
        "readback": {"ok": True, "checked_at": "2026-09-09T00:00:00Z",
                     "pages": rb_pages},
        "status": gx.STATUS_COMPLETE, "blocker": None,
        "built_at": "2026-09-09T00:00:00Z",
    }


def _write_fake(rd: Path, phase_id: str) -> dict:
    fake = _perfect_fake_receipt(rd, phase_id)
    for p in gx.receipt_paths(rd, phase_id):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(fake), encoding="utf-8")
    return fake


# ---------------------------------------------------------------------------
# TODO step 1 -- preflight refuses text-routed external phases.
# ---------------------------------------------------------------------------
class TestPreflight:
    def test_agent_routed_external_refused_with_code(self):
        for pid in gx.EXTERNAL_PHASES:
            ok, detail = gx.preflight_check_phase(
                pid, {"executor": {"kind": "agent"}})
            assert ok is False, f"{pid} text routing must refuse"
            assert "AF-EXTERNAL-TEXT-ROUTING" in detail, detail

    def test_script_with_install_capability_passes(self):
        ok, _d = gx.preflight_check_phase(
            gx.PHASE_GHL_SALES,
            {"executor": {"kind": "script",
                          "capability": gx.CAP_GHL_PAGE_INSTALL}})
        assert ok is True
        ok, _d = gx.preflight_check_phase(
            gx.PHASE_FORM_GATE,
            {"executor": {"kind": "script",
                          "capability": gx.CAP_GHL_WORKFLOW_INSTALL}})
        assert ok is True

    def test_plain_text_phase_unaffected(self):
        ok, _d = gx.preflight_check_phase(
            "P4-COPY", {"executor": {"kind": "agent"}})
        assert ok is True


# ---------------------------------------------------------------------------
# QC check 1 -- fake-model receipts can never complete.
# ---------------------------------------------------------------------------
class TestFakeReceiptCannotComplete:
    @pytest.mark.parametrize("phase_id", list(gx.EXTERNAL_PHASES))
    def test_perfect_fake_fails(self, tmp_path, phase_id):
        pre = SALES_PRE if phase_id == gx.PHASE_GHL_SALES else VSL_PRE
        rd = _intake(tmp_path, pre)
        _seed_pages(rd)
        _write_fake(rd, phase_id)
        ok, detail, _data = gx.validate_receipt(rd, phase_id, env=ENV)
        assert ok is False, f"fake receipt must not validate: {detail}"

    def test_pending_plan_is_not_complete(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        rc, _r = gx.execute_phase(rd, gx.PHASE_GHL_SALES, env=ENV)
        assert rc == gx.EXIT_OK
        ok, detail, _data = gx.validate_receipt(rd, gx.PHASE_GHL_SALES,
                                                env=ENV)
        assert ok is False
        assert "pending_external_execution" in detail

    def test_wrong_location_receipt_fails(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        fake = _write_fake(rd, gx.PHASE_GHL_SALES)
        fake["scope"]["location_id"] = "locFOREIGN"
        for p in gx.receipt_paths(rd, gx.PHASE_GHL_SALES):
            p.write_text(json.dumps(fake), encoding="utf-8")
        ok, detail, _d = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
        assert ok is False
        assert "WRONG_LOCATION" in detail

    def test_stale_run_receipt_fails(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        fake = _write_fake(rd, gx.PHASE_GHL_SALES)
        fake["scope"]["run_id"] = "some-other-run"
        for p in gx.receipt_paths(rd, gx.PHASE_GHL_SALES):
            p.write_text(json.dumps(fake), encoding="utf-8")
        ok, detail, _d = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
        assert ok is False
        assert "stale/foreign" in detail


# ---------------------------------------------------------------------------
# QC check 2 -- mock adapters: IDs + readback prove completion; the client
# location travels on every tool call.
# ---------------------------------------------------------------------------
class TestMockAdapters:
    def test_sales_adapter_completes_with_readback(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        mem = gx.MemoryPageAdapter(LOC)
        rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                       page_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK, receipt
        assert receipt["status"] == gx.STATUS_COMPLETE
        assert receipt["remote"]["funnel_id"]
        assert receipt["remote"]["sales_page_id"]
        assert receipt["remote"]["checkout_page_id"]
        assert receipt["readback"]["ok"] is True
        ok, _d, _dd = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
        assert ok is True, _d

    def test_readback_required(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        mem = gx.MemoryPageAdapter(LOC)
        rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                       page_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK
        receipt["readback"] = {"ok": False}
        for p in gx.receipt_paths(rd, gx.PHASE_GHL_SALES):
            p.write_text(json.dumps(receipt), encoding="utf-8")
        ok, detail, _d = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
        assert ok is False
        assert "readback" in detail

    def test_tool_calls_carry_client_location(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        evil = gx.MemoryPageAdapter("locFOREIGN9999")
        rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                       page_adapter=evil, env=ENV)
        assert rc != gx.EXIT_OK, receipt
        ok, _d, _dd = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
        assert ok is False

    def test_vsl_reuses_sales_funnel(self, tmp_path):
        rd = _intake(tmp_path, {**SALES_PRE, **VSL_PRE})
        _seed_pages(rd)
        mem = gx.MemoryPageAdapter(LOC)
        rc, _r = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                  page_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK
        rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_VSL,
                                       page_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK, receipt
        assert mem.calls.count("create_funnel") == 1, mem.calls
        ok, _d, _dd = gx.validate_receipt(rd, gx.PHASE_GHL_VSL, env=ENV)
        assert ok is True, _d

    def test_gate_pair_completes_with_readback(self, tmp_path):
        rd = _intake(tmp_path, VSL_PRE)
        _seed_pages(rd)
        mem = gx.MemoryGateAdapter(LOC)
        rc, receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE,
                                       gate_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK, receipt
        assert receipt["remote"]["form_id"]
        assert receipt["remote"]["workflow_id"]
        ok, _d, _dd = gx.validate_receipt(rd, gx.PHASE_FORM_GATE, env=ENV)
        assert ok is True, _d
        # BOTH artifacts exist with IDs.
        for p in gx.receipt_paths(rd, gx.PHASE_FORM_GATE):
            assert p.is_file()
            d = json.loads(p.read_text())
            assert d["remote"]["form_id"]
            assert d["remote"]["workflow_id"]

    def test_gate_wrong_location_refused(self, tmp_path):
        rd = _intake(tmp_path, VSL_PRE)
        _seed_pages(rd)
        evil = gx.MemoryGateAdapter("locFOREIGN9999")
        rc, receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE,
                                       gate_adapter=evil, env=ENV)
        assert rc != gx.EXIT_OK, receipt


# ---------------------------------------------------------------------------
# QC check 3 -- kill-resume reuses recorded remote IDs, no duplicates.
# ---------------------------------------------------------------------------
class TestKillResume:
    def test_page_kill_after_funnel_reuses_id(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        mem = gx.MemoryPageAdapter(LOC)
        # Simulate the kill: funnel created (ops persisted), receipt gone.
        funnel_id = mem.create_funnel(
            gx.build_page_install_plan(
                phase_id=gx.PHASE_GHL_SALES,
                scope={"deck_slug": "acme-widget", "run_id": "run",
                       "company": "Acme Co", "location_id": LOC},
                pages=[{"key": "sales", "name": "n", "slug": "s",
                        "source": "x"},
                       {"key": "checkout", "name": "n", "slug": "c",
                        "source": "x"}],
                funnel_name="Acme Co -- Sales/Checkout"))
        exec_id = "gx_resumeprobe01"
        gx.record_ops(rd, gx.PHASE_GHL_SALES,
                      {"status": gx.STATUS_REMOTE_CREATED,
                       "execution_id": exec_id,
                       "remote": {"funnel_id": funnel_id},
                       "next_action": "install pages, then read back"})
        creates_before = mem.calls.count("create_funnel")
        rc, receipt = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                       page_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK, receipt
        assert mem.calls.count("create_funnel") == creates_before, mem.calls
        assert receipt["remote"]["funnel_id"] == funnel_id
        ok, _d, _dd = gx.validate_receipt(rd, gx.PHASE_GHL_SALES, env=ENV)
        assert ok is True, _d

    def test_page_receipt_loss_resumes_without_dup(self, tmp_path):
        rd = _intake(tmp_path, SALES_PRE)
        _seed_pages(rd)
        mem = gx.MemoryPageAdapter(LOC)
        rc, first = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                     page_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK
        first_remote = dict(first["remote"])
        for p in gx.receipt_paths(rd, gx.PHASE_GHL_SALES):
            p.unlink()
        n_before = (mem.calls.count("create_funnel")
                    + mem.calls.count("install_page"))
        rc, second = gx.execute_phase(rd, gx.PHASE_GHL_SALES,
                                      page_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK, second
        n_after = (mem.calls.count("create_funnel")
                   + mem.calls.count("install_page"))
        assert n_after == n_before, mem.calls
        assert second["remote"] == first_remote

    def test_gate_partial_form_only_resumes(self, tmp_path):
        rd = _intake(tmp_path, VSL_PRE)
        _seed_pages(rd)
        mem = gx.MemoryGateAdapter(LOC)
        plan = gx.build_gate_form_plan(
            scope={"deck_slug": "acme-widget", "run_id": "run",
                   "company": "Acme Co", "location_id": LOC})
        form_id = mem.create_form({"scope": plan["scope"],
                                   "form": plan["form"]})
        gx.record_ops(rd, gx.PHASE_FORM_GATE,
                      {"status": gx.STATUS_REMOTE_CREATED,
                       "execution_id": "gx_gatepartial1",
                       "remote": {"form_id": form_id},
                       "next_action": "create workflow, then read back"})
        forms_before = mem.calls.count("create_form")
        rc, receipt = gx.execute_phase(rd, gx.PHASE_FORM_GATE,
                                       gate_adapter=mem, env=ENV)
        assert rc == gx.EXIT_OK, receipt
        assert mem.calls.count("create_form") == forms_before, mem.calls
        assert receipt["remote"]["form_id"] == form_id
        assert receipt["remote"]["workflow_id"]
        ok, _d, _dd = gx.validate_receipt(rd, gx.PHASE_FORM_GATE, env=ENV)
        assert ok is True, _d


# ---------------------------------------------------------------------------
# Manifest wiring + registry + gate mechanic.
# ---------------------------------------------------------------------------
class TestManifestWiring:
    @staticmethod
    def _manifest() -> dict:
        cur = SCRIPTS
        for _ in range(12):
            cand = (cur / "universal-sops" / "presentation-slide-craft"
                    / "PIPELINE-MANIFEST.json")
            if cand.is_file():
                return json.loads(cand.read_text())
            if cur.parent == cur:
                break
            cur = cur.parent
        raise FileNotFoundError("PIPELINE-MANIFEST.json not found")

    def test_external_phases_are_script_with_capability(self):
        m = self._manifest()
        ph = {p["id"]: p for p in m["phases"]}
        assert ph[gx.PHASE_GHL_SALES]["executor"]["kind"] == "script"
        assert ph[gx.PHASE_GHL_VSL]["executor"]["kind"] == "script"
        assert ph[gx.PHASE_FORM_GATE]["executor"]["kind"] == "script"
        assert (ph[gx.PHASE_GHL_SALES]["executor"]["capability"]
                == gx.CAP_GHL_PAGE_INSTALL)
        assert (ph[gx.PHASE_GHL_VSL]["executor"]["capability"]
                == gx.CAP_GHL_PAGE_INSTALL)
        assert (ph[gx.PHASE_FORM_GATE]["executor"]["capability"]
                == gx.CAP_GHL_WORKFLOW_INSTALL)
        for pid in gx.EXTERNAL_PHASES:
            assert "ghl_external_installer.py" in ph[pid]["executor"]["cmd"], pid

    def test_verifiers_cover_external_phases(self):
        for pid in gx.EXTERNAL_PHASES:
            assert pid in pv.PHASE_VERIFIERS, f"{pid} has no verifier"

    def test_preflight_passes_on_shipped_manifest(self):
        m = self._manifest()
        ph = {p["id"]: p for p in m["phases"]}
        for pid in gx.EXTERNAL_PHASES:
            ok, detail = gx.preflight_check_phase(pid, ph[pid])
            assert ok is True, detail


class TestGateMechanic:
    def test_absent_flag_defers(self, tmp_path):
        rd = _intake(tmp_path, {})
        for pid in gx.EXTERNAL_PHASES:
            ok, reasons = pv.verify(pid, rd)
            assert ok is True, (pid, reasons)
            assert any("defer" in r for r in reasons), (pid, reasons)

    def test_decline_with_quote_waives(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "no",
                                "SALES_CHECKOUT_DECLINED_REASON":
                                "We already have a funnel we like."})
        ok, reasons = pv.verify(gx.PHASE_GHL_SALES, rd)
        assert ok is True
        assert any("waived" in r for r in reasons)
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "no",
                                "VSL_PAGE_DECLINED_REASON":
                                "We have no video and want none."})
        for pid in (gx.PHASE_GHL_VSL, gx.PHASE_FORM_GATE):
            ok, reasons = pv.verify(pid, rd)
            assert ok is True, (pid, reasons)
            assert any("waived" in r for r in reasons), (pid, reasons)

    def test_decline_without_reason_fails_closed(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "no"})
        ok, reasons = pv.verify(gx.PHASE_GHL_SALES, rd)
        assert ok is False
        assert any("fail_closed" in r or "AF-" in r for r in reasons)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
