"""Tests for the start-up wiring of probe_ocr (MASTER-SPEC 7.4 / U027 step 1).

MASTER-SPEC 7.4: "The missing OCR dependency fails at minute zero, before any
paid generation, not after 62 images."

Before this unit, presentation_job/preflight_deps.py::probe_ocr existed but had
ZERO callers -- the readback gate (gates.py::Gates._ocr_gate, NON_WAIVABLE_GATES)
only found out the engine was missing at close(), after every slide had already
been downloaded and paid for. This file proves:

  1. probe_ocr() itself is fail-closed: available -> 0, unavailable -> 1.
  2. Engine.run() (phases.py) calls it FIRST, before the phase loop, before the
     ack message, and before any phase (i.e. any paid image generation) runs.
  3. A healthy interpreter passes straight through to the phase loop.
  4. An unhealthy interpreter refuses immediately: non-zero exit, a BLOCKED
     state naming what's missing and how to install it, and -- the concrete
     thing this unit exists to prevent -- ZERO phases/images executed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.state import StateStore, EXIT_OK, EXIT_GATE_BLOCKED
from presentation_job.manifest import Manifest
from presentation_job.phases import Engine
from presentation_job.preflight_deps import probe_ocr
import prompt_gate


# ---------------------------------------------------------------------------
# Helpers (same shape as tests/test_heal.py's _mkmanifest / _mkengine)
# ---------------------------------------------------------------------------
def _mkmanifest(tmp_path, phases=None):
    """A single trivial phase whose script, if it EVER runs, writes a marker
    file -- our stand-in for 'a paid image got generated'."""
    mp = tmp_path / "m.json"
    if phases is None:
        phases = [{
            "id": "P4-RENDER", "order": 1, "owning_role": "renderer",
            "produces_artifact": ["paid.marker"],
            "executor": {"kind": "script", "cmd": "touch paid.marker"},
        }]
    mp.write_text(json.dumps({"manifest_version": 25, "phases": phases}))
    return Manifest(mp)


def _mkengine(tmp_path, manifest=None):
    rd = tmp_path / "r"
    rd.mkdir(exist_ok=True)
    store = StateStore(rd)
    if manifest is None:
        manifest = _mkmanifest(tmp_path)
    s = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd), "created_at": "",
        "manifest_path": str(manifest.path), "manifest_version": 25,
        "manifest_sha256": manifest.sha256, "presentation_type": "from_scratch",
        "requester": {"chat_id": "t"}, "intake": {}, "current_phase": None,
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store.save(s)
    return Engine(rd, manifest, store, s), s


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Board and notify are both env-gated no-ops when unset -- keep tests
    # deterministic regardless of the ambient shell.
    monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
    monkeypatch.delenv("COMMAND_CENTER_URL", raising=False)
    monkeypatch.delenv("MISSION_CONTROL_URL", raising=False)


# ---------------------------------------------------------------------------
# 1. probe_ocr() itself: fail-closed in both directions.
# ---------------------------------------------------------------------------
class TestProbeOcrFailClosed:
    def test_available_returns_0(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            prompt_gate, "_ocr_engine_available",
            lambda: (SimpleNamespace(name="pytesseract"), SimpleNamespace(name="PIL.Image")))
        rd = tmp_path / "r"
        rd.mkdir()
        assert probe_ocr(rd) == EXIT_OK
        rec = json.loads((rd / "state.json").read_text())
        assert rec["runtime_deps"]["ocr"]["available"] is True

    def test_unavailable_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prompt_gate, "_ocr_engine_available", lambda: (None, None))
        rd = tmp_path / "r"
        rd.mkdir()
        assert probe_ocr(rd) == 1
        rec = json.loads((rd / "state.json").read_text())
        assert rec["runtime_deps"]["ocr"]["available"] is False

    def test_prompt_gate_not_importable_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "prompt_gate", None)
        rd = tmp_path / "r"
        rd.mkdir()
        try:
            assert probe_ocr(rd) == 1
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# 2/3/4. Engine.run() wiring: healthy proceeds, unhealthy refuses at minute
#         zero with zero phases executed (zero images "generated").
# ---------------------------------------------------------------------------
class TestEngineStartupWiring:
    def test_healthy_box_proceeds_past_startup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            prompt_gate, "_ocr_engine_available",
            lambda: (SimpleNamespace(name="pytesseract"), SimpleNamespace(name="PIL.Image")))
        engine, state = _mkengine(tmp_path)
        engine.run()

        # Never blocked for the OCR reason.
        assert (state.get("blocked") or {}).get("phase") != "P0-STARTUP-OCR-PROBE"
        # The phase loop was actually entered: our one phase ran and produced
        # its marker (the "paid image").
        assert (engine.run_dir / "paid.marker").exists(), \
            "healthy box must proceed to the phase loop"
        ps = [p for p in state["phases"] if p["id"] == "P4-RENDER"]
        assert ps and ps[0]["status"] == "done"
        # ack was attempted -- proves we got past the preflight into the normal
        # loop (dispatch itself fails in-test since PRESENTATION_NOTIFY_CMD is
        # unset, so it lands in "events"/"undeliverable" rather than "sent").
        assert any(e["kind"] == "report.ack" for e in state.get("events", []))

    def test_missing_engine_refuses_at_minute_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prompt_gate, "_ocr_engine_available", lambda: (None, None))
        engine, state = _mkengine(tmp_path)
        rc = engine.run()

        assert rc == EXIT_GATE_BLOCKED
        assert state["terminal"] == "BLOCKED"
        assert state["blocked"]["phase"] == "P0-STARTUP-OCR-PROBE"
        reason = state["blocked"]["reason"]
        assert "pytesseract" in reason
        assert "pip install" in reason
        assert sys.executable in reason

        # The concrete failure mode this unit exists to prevent: NO phase ran,
        # so NO image was ever "generated" or paid for.
        assert state["phases"] == [], "no phase may run when the OCR probe fails"
        assert not (engine.run_dir / "paid.marker").exists(), \
            "zero images/artifacts may be produced when the start-up probe blocks"
        # The ack ("Got it, building...") must never even be attempted for a
        # run that never starts.
        assert not any(e["kind"] == "report.ack" for e in state.get("events", []))
        assert not state.get("sent", {}).get("ack")

    def test_missing_engine_reports_blocked_to_requester(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prompt_gate, "_ocr_engine_available", lambda: (None, None))
        engine, state = _mkengine(tmp_path)
        engine.run()
        undeliverable = state.get("undeliverable", [])
        assert undeliverable, "a blocked-at-startup run must attempt to notify the requester"
        msg = undeliverable[-1]
        assert msg["kind"] == "blocked"
        assert "cannot start" in msg["message"]
        assert "nothing has been paid for" in msg["message"]
