#!/usr/bin/env python3
"""PD-076 / PD-201 — the process certificate counts what it claims.

The certificate's integrity_pass must mean what it says:

  * every key in ALL_GATE_KEYS is PRESENT and pass or waived (a gate key the
    state never recorded was never evaluated, and an unevaluated gate is not
    a pass — PD-076);
  * no step sits outside done / deferred / obsolete (PD-076);
  * no row of working/checkpoints/gate_log.jsonl records result
    degraded_pass or test_seam_used (PD-201: an empty `.test-context` file in
    the run folder switches checks into test mode, and that pass cannot be
    minted as an integrity pass).

Each failure case asserts the reason NAMES what is wrong, and the clean case
is the control proving the check is not vacuous.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.gates import ALL_GATE_KEYS  # noqa: E402


def _clean_gates():
    return {k: {"state": "pass"} for k in ALL_GATE_KEYS}


def _make_engine(tmp_path, phases, gates):
    from presentation_job.manifest import Manifest
    from presentation_job.phases import Engine
    from presentation_job.state import StateStore

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"manifest_version": 25, "phases": []}))
    manifest = Manifest(manifest_path)
    state = {
        "schema_version": 1, "job_id": "pd076_cert_test",
        "run_dir": str(run_dir), "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": str(manifest_path), "manifest_version": 25,
        "manifest_sha256": manifest.sha256, "presentation_type": "from_scratch",
        "requester": {"chat_id": "test"}, "current_phase": None,
        "phases": phases, "gates": gates, "waivers": [], "events": [],
        "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store = StateStore(run_dir)
    store.save(state)
    return Engine(run_dir, manifest, store, state, dry_run=False)


def _write_gate_log(run_dir: Path, rows):
    ckpt = run_dir / "working" / "checkpoints"
    ckpt.mkdir(parents=True, exist_ok=True)
    (ckpt / "gate_log.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Control: an otherwise-clean state still mints integrity_pass True
# ---------------------------------------------------------------------------
def test_clean_state_passes(tmp_path):
    engine = _make_engine(
        tmp_path,
        phases=[{"id": "P1", "status": "done", "verifier_ok": True},
                {"id": "P2", "status": "deferred"},
                {"id": "P3", "status": "obsolete"}],
        gates=_clean_gates(),
    )
    cert = engine._mint_process_certificate()
    assert cert["integrity_pass"] is True, cert["integrity_fail_reasons"]
    assert cert["gate_results"]["missing_gate_keys"] == []
    assert cert["gate_results"]["degraded_or_test_seam_rows"] == []


# ---------------------------------------------------------------------------
# PD-076: one gate key missing from the state
# ---------------------------------------------------------------------------
def test_missing_gate_key_fails_and_names_it(tmp_path):
    gates = _clean_gates()
    del gates["qc"]
    engine = _make_engine(tmp_path, phases=[], gates=gates)
    cert = engine._mint_process_certificate()
    assert cert["integrity_pass"] is False
    assert cert["gate_results"]["missing_gate_keys"] == ["qc"]
    reasons = " | ".join(cert["integrity_fail_reasons"])
    assert "qc" in reasons and "never evaluated" in reasons, reasons


# ---------------------------------------------------------------------------
# PD-076: a step outside done / deferred / obsolete
# ---------------------------------------------------------------------------
def test_unfinished_step_fails_and_names_it(tmp_path):
    engine = _make_engine(
        tmp_path,
        phases=[{"id": "P4-RENDER", "status": "running"}],
        gates=_clean_gates(),
    )
    cert = engine._mint_process_certificate()
    assert cert["integrity_pass"] is False
    reasons = " | ".join(cert["integrity_fail_reasons"])
    assert "P4-RENDER" in reasons, reasons
    assert "not done, deferred or obsolete" in reasons, reasons


def test_blocked_step_is_not_a_settled_step(tmp_path):
    engine = _make_engine(
        tmp_path,
        phases=[{"id": "P9-UPLOAD", "status": "blocked"}],
        gates=_clean_gates(),
    )
    cert = engine._mint_process_certificate()
    assert cert["integrity_pass"] is False, "a blocked step is not a finished step"
    assert "P9-UPLOAD" in " | ".join(cert["integrity_fail_reasons"])


# ---------------------------------------------------------------------------
# PD-201: a degraded or test-seam row in the gate log
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("result", ["degraded_pass", "test_seam_used"])
def test_gate_log_degraded_row_fails_and_names_it(tmp_path, result):
    engine = _make_engine(tmp_path, phases=[], gates=_clean_gates())
    _write_gate_log(engine.run_dir, [
        {"phase_id": "P1Q-COPY-QC", "result": "pass"},
        {"phase_id": "P-IMAGE-QC", "result": result},
    ])
    cert = engine._mint_process_certificate()
    assert cert["integrity_pass"] is False
    rows = cert["gate_results"]["degraded_or_test_seam_rows"]
    assert len(rows) == 1, rows
    reasons = " | ".join(cert["integrity_fail_reasons"])
    assert "line 2" in reasons and result in reasons and "P-IMAGE-QC" in reasons, reasons


def test_gate_log_clean_rows_do_not_fail(tmp_path):
    engine = _make_engine(tmp_path, phases=[], gates=_clean_gates())
    _write_gate_log(engine.run_dir, [{"phase_id": "P1Q-COPY-QC", "result": "pass"}])
    cert = engine._mint_process_certificate()
    assert cert["integrity_pass"] is True, cert["integrity_fail_reasons"]
