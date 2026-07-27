"""Tests for gates (U013).  Covers the upload gate key fix, warn-mode staging,
fail-closed enforcement, and phase_verifier fail-closed returns."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import ghl_media_push as gmp
from presentation_job.gates import (
    Gates, GATE_KEYS, NON_WAIVABLE_GATES, WARN_ONLY_GATES, ALL_GATE_KEYS,
)
from presentation_job.waivers import WaiverError, load_waivers, validate_waiver
from presentation_job.state import StateStore, EXIT_OK, EXIT_GATE_BLOCKED, EXIT_WAIVER_INVALID


# ---------------------------------------------------------------------------
# Helper — read GOOD_MEDIA from source (never copy the literal)
# ---------------------------------------------------------------------------
_GOOD_MEDIA_SOURCE = Path(gmp.__file__).read_text()


def _good_media() -> dict:
    """Extract the GOOD_MEDIA fixture from ghl_media_push.py via AST.
    GOOD_MEDIA is a local inside _selftest (line 460, col_offset 4), so it is
    NOT importable — this extraction guarantees the test never drifts from the
    producer's own self-test fixture."""
    src = ast.parse(_GOOD_MEDIA_SOURCE)
    for n in ast.walk(src):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if getattr(t, "id", None) == "GOOD_MEDIA":
                    return ast.literal_eval(n.value)
    raise AssertionError("GOOD_MEDIA not found in ghl_media_push.py")


# ---------------------------------------------------------------------------
# Test 1 — _ghl_gate on GOOD_MEDIA returns pass (the key fix)
# ---------------------------------------------------------------------------
def test_ghl_gate_passes_on_good_media(tmp_path: Path):
    """The upload gate must pass when given the producer's own GOOD_MEDIA fixture."""
    run_dir = tmp_path
    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True)
    (ck / "media_library.json").write_text(json.dumps(_good_media()))

    g = Gates(run_dir, {})
    result = g._ghl_gate()
    assert result["state"] == "pass", f"expected pass, got {result}"
    assert result["ghl_folder_id"] == "fld_123"
    assert result["slide_uploads_complete"] == 2
    assert result["slide_uploads_total"] == 2
    assert result["pptx_ghl_media_id"] == "pptx_9"


# ---------------------------------------------------------------------------
# Test 2 — _ghl_gate on old key media_ids returns fail
# ---------------------------------------------------------------------------
def test_ghl_gate_fails_on_old_key(tmp_path: Path):
    """media_ids is a phantom key — no producer writes it.  The gate must fail."""
    run_dir = tmp_path
    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True)
    (ck / "media_library.json").write_text(json.dumps({"media_ids": ["a", "b"]}))

    g = Gates(run_dir, {})
    result = g._ghl_gate()
    assert result["state"] == "fail", f"expected fail for old-key payload, got {result}"
    assert "ghl_folder_id" in result["reason"]


# ---------------------------------------------------------------------------
# Test 3 — _ghl_gate fails when pptx_ghl_media_id is absent
# ---------------------------------------------------------------------------
def test_ghl_gate_fails_on_missing_pptx_id(tmp_path: Path):
    """A complete upload record without pptx_ghl_media_id must fail."""
    run_dir = tmp_path
    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True)
    payload = {
        "ghl_folder_id": "fld_123",
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "complete"},
        ],
        # pptx_ghl_media_id deliberately absent
    }
    (ck / "media_library.json").write_text(json.dumps(payload))

    g = Gates(run_dir, {})
    result = g._ghl_gate()
    assert result["state"] == "fail", f"expected fail, got {result}"
    assert "pptx_ghl_media_id" in result["reason"]


# ---------------------------------------------------------------------------
# Test 4 — _ghl_gate reports incomplete slide counts
# ---------------------------------------------------------------------------
def test_ghl_gate_reports_incomplete_slide_count(tmp_path: Path):
    """One pending slide out of two must produce a counted reason."""
    run_dir = tmp_path
    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True)
    payload = {
        "ghl_folder_id": "fld_123",
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "pending"},
        ],
        "pptx_ghl_media_id": "pptx_9",
    }
    (ck / "media_library.json").write_text(json.dumps(payload))

    g = Gates(run_dir, {})
    result = g._ghl_gate()
    assert result["state"] == "fail", f"expected fail for partial, got {result}"
    reason = result["reason"]
    assert "1" in reason, f"reason must name the count of incomplete slides: {reason}"
    assert "2" in reason, f"reason must name total: {reason}"


# ---------------------------------------------------------------------------
# Test 5 — script gate accepts speech file at either path
# ---------------------------------------------------------------------------
def test_script_gate_either_path(tmp_path: Path):
    """The script gate must pass when the speech file is at either accepted path."""
    run_dir = tmp_path
    # Test primary path (working/deliverables)
    d1 = run_dir / "working" / "deliverables"
    d1.mkdir(parents=True)
    (d1 / "PRESENTERS-SPEECH.md").write_text("x" * 3000)
    g = Gates(run_dir, {})
    r = g._artifact_gate_any(
        ["working/deliverables/PRESENTERS-SPEECH.md",
         "working/presenter-speech/PRESENTERS-SPEECH.md"], 2048)
    assert r["state"] == "pass", f"primary path must pass: {r}"
    assert "PRESENTERS-SPEECH.md" in r["evidence"]

    # Remove primary; test fallback path
    (d1 / "PRESENTERS-SPEECH.md").unlink()
    d2 = run_dir / "working" / "presenter-speech"
    d2.mkdir(parents=True)
    (d2 / "PRESENTERS-SPEECH.md").write_text("x" * 3000)
    r2 = g._artifact_gate_any(
        ["working/deliverables/PRESENTERS-SPEECH.md",
         "working/presenter-speech/PRESENTERS-SPEECH.md"], 2048)
    assert r2["state"] == "pass", f"fallback path must pass: {r2}"

    # Neither — must fail
    (d2 / "PRESENTERS-SPEECH.md").unlink()
    r3 = g._artifact_gate_any(
        ["working/deliverables/PRESENTERS-SPEECH.md",
         "working/presenter-speech/PRESENTERS-SPEECH.md"], 2048)
    assert r3["state"] == "fail", f"neither path must fail: {r3}"


# ---------------------------------------------------------------------------
# Test 6 — prompt_floor fails on one short prompt, naming file and length
# ---------------------------------------------------------------------------
def test_prompt_floor_fails_on_short_prompt(tmp_path: Path):
    """One prompt below the 9000-char floor must fail and name the file + length."""
    run_dir = tmp_path
    d = run_dir / "working" / "prompts"
    d.mkdir(parents=True)
    (d / "slide-01.txt").write_text("x" * 8999)
    (d / "slide-02.txt").write_text("y" * 9500)

    g = Gates(run_dir, {})
    result = g._prompt_floor_gate()
    assert result["state"] == "fail", f"expected fail, got {result}"
    reason = result["reason"]
    assert "slide-01.txt" in reason, f"reason must name the short file: {reason}"
    assert "8999" in reason or "below" in reason, f"reason must name the short length: {reason}"


# ---------------------------------------------------------------------------
# Test 7 — close() with everything failing exits 3
# ---------------------------------------------------------------------------
def test_close_all_failing_exits_blocked(tmp_path: Path, capsys):
    """When every gate fails, close() must exit 3 with terminal BLOCKED."""
    run_dir = tmp_path
    store = StateStore(run_dir)
    # Write a minimal state so the engine can work
    state = {"job_id": "t7", "schema_version": 1, "phases": [],
             "gates": {}, "presentation_type": "from_scratch"}
    store.save(state)

    from presentation_job.phases import Engine
    from presentation_job.manifest import Manifest
    man_path = _scripts_dir.parent.parent.parent.parent.parent / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
    manifest = Manifest(man_path)
    engine = Engine(run_dir, manifest, store, store.load(), dry_run=False)

    rc = engine.close()
    assert rc == EXIT_GATE_BLOCKED, f"expected exit 3, got {rc}"
    state2 = store.load()
    assert state2.get("terminal") == "BLOCKED", f"terminal must be BLOCKED, got {state2.get('terminal')}"
    captured = capsys.readouterr()
    for gate_name in ("script", "teleprompter", "prompt_floor", "ghl_upload"):
        assert gate_name in captured.err, f"stderr must name {gate_name}: {captured.err}"


# ---------------------------------------------------------------------------
# Test 8 — close() with warn-mode gates failing exits 0
# ---------------------------------------------------------------------------
def test_close_warn_mode_exits_ok(tmp_path: Path, capsys):
    """When the four hard gates pass and only qc+ocr fail, close exits 0 with 2 warnings."""
    run_dir = tmp_path

    # Satisfy the four hard gates
    d = run_dir / "working" / "deliverables"
    d.mkdir(parents=True)
    (d / "PRESENTERS-SPEECH.md").write_text("x" * 3000)
    (d / "presenter-teleprompter.html").write_text("y" * 11000)

    prompts = run_dir / "working" / "prompts"
    prompts.mkdir(parents=True)
    for i in range(1, 3):
        (prompts / f"slide-{i:02d}.txt").write_text("p" * 9500)

    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True)
    (ck / "media_library.json").write_text(json.dumps(_good_media()))

    store = StateStore(run_dir)
    state = {"job_id": "t8", "schema_version": 1, "phases": [],
             "gates": {}, "presentation_type": "from_scratch"}
    store.save(state)

    from presentation_job.phases import Engine
    from presentation_job.manifest import Manifest
    man_path = _scripts_dir.parent.parent.parent.parent.parent / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
    manifest = Manifest(man_path)
    engine = Engine(run_dir, manifest, store, store.load(), dry_run=False)

    rc = engine.close()
    assert rc == EXIT_OK, f"warn-mode should exit 0, got {rc}"
    state2 = store.load()
    assert state2.get("terminal") == "DONE"
    warnings = state2.get("gate_warnings", [])
    warn_keys = {w[0] for w in warnings}
    assert warn_keys == {"qc", "ocr_readback"}, \
        f"expected qc+ocr in warnings, got {warn_keys}"
    assert len(warnings) == 2, f"expected 2 warnings, got {len(warnings)}"


# ---------------------------------------------------------------------------
# Test 14 — verify() on unregistered phase returns (False, ...)
# ---------------------------------------------------------------------------
def test_verify_unregistered_phase_returns_false(tmp_path: Path):
    """A phase not in PHASE_VERIFIERS must return (False, ...) per fail-closed doctrine."""
    import phase_verifiers
    ok, reasons = phase_verifiers.verify("P-NOT-A-PHASE", tmp_path)
    assert ok is False, f"unregistered phase must return False, got {ok}"
    assert any("P-NOT-A-PHASE" in r for r in reasons), \
        f"reasons must name the phase id: {reasons}"


# ---------------------------------------------------------------------------
# Test 15 — verify() on a raising verifier returns (False, ...)
# ---------------------------------------------------------------------------
def test_verify_raising_verifier_returns_false(tmp_path: Path):
    """A verifier that raises must return (False, ...) whose reason names the exception."""
    import phase_verifiers
    import phase_verifiers as pv

    # Monkeypatch a phase that always raises
    def _raise(*args, **kwargs):
        raise RuntimeError("simulated checker crash")

    original = pv.PHASE_VERIFIERS.get("P0A-INTAKE")
    pv.PHASE_VERIFIERS["P0A-INTAKE"] = _raise
    try:
        # Set up a valid intake.json so _raise gets called
        cpy = tmp_path / "working" / "copy"
        cpy.mkdir(parents=True)
        (cpy / "intake.json").write_text("{}")
        ok, reasons = phase_verifiers.verify("P0A-INTAKE", tmp_path)
        assert ok is False, f"raising verifier must return False, got {ok}"
        assert any("RuntimeError" in r for r in reasons), \
            f"reasons must name RuntimeError: {reasons}"
    finally:
        if original is not None:
            pv.PHASE_VERIFIERS["P0A-INTAKE"] = original
        else:
            pv.PHASE_VERIFIERS.pop("P0A-INTAKE", None)
