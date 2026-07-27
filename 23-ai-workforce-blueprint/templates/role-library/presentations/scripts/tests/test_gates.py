"""Tests for U013 -- fail-closed gates: key fix, warn-mode, fail-open closure."""
from __future__ import annotations

import ast
import json
import pathlib
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, SCRIPTS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_GOOD_MEDIA():
    """Extract GOOD_MEDIA fixture from ghl_media_push.py source via ast."""
    src = Path(SCRIPTS) / "ghl_media_push.py"
    if not src.is_file():
        # Fallback: the producer module may not exist in all test environments
        return {
            "ghl_folder_id": "fld_123",
            "slides": [
                {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
                {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "complete"},
            ],
            "pptx_ghl_media_id": "pptx_9",
        }
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", None) == "GOOD_MEDIA":
                    return ast.literal_eval(node.value)
    return {
        "ghl_folder_id": "fld_123",
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "complete"},
        ],
        "pptx_ghl_media_id": "pptx_9",
    }


GOOD_MEDIA = _load_GOOD_MEDIA()


def _make_run_dir(base: Path, media=None):
    ck = base / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    if media is not None:
        (ck / "media_library.json").write_text(json.dumps(media))
    return base


# ---------------------------------------------------------------------------
# Test 1: _ghl_gate on GOOD_MEDIA -> pass
# ---------------------------------------------------------------------------
def test_ghl_gate_passes_on_good_media():
    from presentation_job.gates import Gates
    with tempfile.TemporaryDirectory() as tmp:
        base = _make_run_dir(Path(tmp), GOOD_MEDIA)
        g = Gates(base, {})._ghl_gate()
        assert g["state"] == "pass", f"GOOD_MEDIA should pass, got {g}"
        assert "ghl_folder_id" in g
        assert "pptx_ghl_media_id" in g
        assert "slide_uploads_complete" in g
        assert "media_ids" not in g
        assert "folder_id" not in g


# ---------------------------------------------------------------------------
# Test 2: old media_ids key -> fail
# ---------------------------------------------------------------------------
def test_ghl_gate_fails_on_old_media_ids_key():
    from presentation_job.gates import Gates
    with tempfile.TemporaryDirectory() as tmp:
        base = _make_run_dir(Path(tmp), {"media_ids": ["a", "b"]})
        g = Gates(base, {})._ghl_gate()
        assert g["state"] == "fail", f"old media_ids key should fail, got {g}"
        reason = g.get("reason", "")
        assert "ghl_folder_id" in reason


# ---------------------------------------------------------------------------
# Test 3: no pptx_ghl_media_id -> fail
# ---------------------------------------------------------------------------
def test_ghl_gate_fails_on_missing_pptx():
    from presentation_job.gates import Gates
    m = dict(GOOD_MEDIA)
    m.pop("pptx_ghl_media_id")
    with tempfile.TemporaryDirectory() as tmp:
        base = _make_run_dir(Path(tmp), m)
        g = Gates(base, {})._ghl_gate()
        assert g["state"] == "fail"
        assert "pptx_ghl_media_id" in g.get("reason", "")


# ---------------------------------------------------------------------------
# Test 4: pending slide -> fail with count
# ---------------------------------------------------------------------------
def test_ghl_gate_fails_on_pending_slide():
    from presentation_job.gates import Gates
    m = {
        "ghl_folder_id": "fld_123",
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "pending"},
            {"slide_number": 3, "ghl_media_id": "m3", "ghl_upload_status": "complete"},
        ],
        "pptx_ghl_media_id": "pptx_9",
    }
    with tempfile.TemporaryDirectory() as tmp:
        base = _make_run_dir(Path(tmp), m)
        g = Gates(base, {})._ghl_gate()
        assert g["state"] == "fail"
        assert "1 of 3" in g.get("reason", "")


# ---------------------------------------------------------------------------
# Test 5: script gate accepts either path
# ---------------------------------------------------------------------------
def test_script_gate_accepts_either_path():
    from presentation_job.gates import Gates
    # Path 1: working/deliverables
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "working" / "deliverables").mkdir(parents=True)
        (base / "working" / "deliverables" / "PRESENTERS-SPEECH.md").write_text("X" * 3000)
        g = Gates(base, {}).evaluate_all()["script"]
        assert g["state"] == "pass"

    # Path 2: working/presenter-speech (fallback)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "working" / "presenter-speech").mkdir(parents=True)
        (base / "working" / "presenter-speech" / "PRESENTERS-SPEECH.md").write_text("X" * 3000)
        g = Gates(base, {}).evaluate_all()["script"]
        assert g["state"] == "pass"

    # Neither -> fail
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        g = Gates(base, {}).evaluate_all()["script"]
        assert g["state"] == "fail"


# ---------------------------------------------------------------------------
# Test 6: prompt_floor fails on 8999-char prompt
# ---------------------------------------------------------------------------
def test_prompt_floor_fails_short_prompt():
    from presentation_job.gates import Gates
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "working" / "prompts").mkdir(parents=True)
        (base / "working" / "prompts" / "slide-01.txt").write_text("X" * 8999)
        g = Gates(base, {}).evaluate_all()["prompt_floor"]
        assert g["state"] == "fail"
        reason = g.get("reason", "")
        assert "slide-01" in reason
        assert "8999" in reason


# ---------------------------------------------------------------------------
# Test 7: close() with everything failing exits 3, sets BLOCKED
# ---------------------------------------------------------------------------
def test_close_all_failing_exits_blocked():
    from presentation_job.phases import Engine
    from presentation_job.manifest import Manifest
    from presentation_job.state import StateStore
    import presentation_job.state as st

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        store = StateStore(base)
        state = {"job_id": "test-7", "schema_version": 1, "phases": [], "heartbeat": {}}
        store.save(state)
        state = store.load()

        mp = base / "manifest.json"
        mp.write_text(json.dumps({"manifest_version": 25, "phases": [],
                                   "deliverables_required": [], "client_package_files": [],
                                   "autofails": []}))
        manifest = Manifest(mp)
        engine = Engine(base, manifest, store, state)
        rc = engine.close()
        assert rc == st.EXIT_GATE_BLOCKED, f"expected 3, got {rc}"
        assert state.get("terminal") == "BLOCKED"


# ---------------------------------------------------------------------------
# Test 8: warn-mode gates don't block close
# ---------------------------------------------------------------------------
def test_close_warn_mode_exits_ok():
    from presentation_job.phases import Engine
    from presentation_job.manifest import Manifest
    from presentation_job.state import StateStore
    import presentation_job.state as st

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        store = StateStore(base)

        # Set up 4 passing gates
        (base / "working" / "deliverables").mkdir(parents=True)
        (base / "working" / "deliverables" / "PRESENTERS-SPEECH.md").write_text("X" * 3000)
        (base / "working" / "deliverables" / "presenter-teleprompter.html").write_text("Y" * 11000)
        (base / "working" / "prompts").mkdir(parents=True)
        (base / "working" / "prompts" / "slide-01.txt").write_text("Z" * 9500)
        ck = base / "working" / "checkpoints"
        ck.mkdir(parents=True)
        (ck / "media_library.json").write_text(json.dumps(GOOD_MEDIA))

        state = {"job_id": "test-8", "schema_version": 1, "phases": [], "heartbeat": {}}
        store.save(state)
        state = store.load()

        mp = base / "manifest.json"
        mp.write_text(json.dumps({"manifest_version": 25, "phases": [],
                                   "deliverables_required": [], "client_package_files": [],
                                   "autofails": []}))
        manifest = Manifest(mp)
        engine = Engine(base, manifest, store, state)
        rc = engine.close()
        assert rc == st.EXIT_OK, f"warn-mode should exit 0, got {rc}"
        gate_warnings = state.get("gate_warnings", [])
        assert len(gate_warnings) == 2
        warned_gates = {w["gate"] for w in gate_warnings}
        assert warned_gates == {"qc", "ocr_readback"}


# ---------------------------------------------------------------------------
# Test 9: ocr_readback is never waivable
# ---------------------------------------------------------------------------
def test_waiver_ocr_readback_is_never_waivable():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "ocr_readback", "source": "transcript",
         "client_request_quote": "yes",
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="not a waivable gate"):
        validate_waiver(w, Path("/nonexistent"))


# ---------------------------------------------------------------------------
# Test 10: short quote rejected
# ---------------------------------------------------------------------------
def test_waiver_short_quote_rejected():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "script", "source": "intake_field",
         "intake_field": "ok_field",
         "client_request_quote": "ab",
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="no client_request_quote"):
        validate_waiver(w, Path("/nonexistent"))


# ---------------------------------------------------------------------------
# Test 11: duplicate waivers rejected
# ---------------------------------------------------------------------------
def test_duplicate_waiver_rejected():
    from presentation_job.waivers import load_waivers, WaiverError
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        waivers = [
            {"rule": "qc", "source": "intake_field", "intake_field": "ok_field",
             "client_request_quote": "skip qc please",
             "captured_at": "2026-01-01T00:00:00Z"},
            {"rule": "qc", "source": "intake_field", "intake_field": "ok_field",
             "client_request_quote": "skip qc please again",
             "captured_at": "2026-01-02T00:00:00Z"},
        ]
        (base / "waivers.json").write_text(json.dumps(waivers))
        with pytest.raises(WaiverError, match="two waivers name the same gate"):
            load_waivers(base)


# ---------------------------------------------------------------------------
# Test 12: valid intake waiver for qc lets close pass
# ---------------------------------------------------------------------------
def test_valid_intake_waiver_for_qc():
    from presentation_job.phases import Engine
    from presentation_job.manifest import Manifest
    from presentation_job.state import StateStore
    import presentation_job.state as st

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        store = StateStore(base)

        # 4 passing gates
        (base / "working" / "deliverables").mkdir(parents=True)
        (base / "working" / "deliverables" / "PRESENTERS-SPEECH.md").write_text("X" * 3000)
        (base / "working" / "deliverables" / "presenter-teleprompter.html").write_text("Y" * 11000)
        (base / "working" / "prompts").mkdir(parents=True)
        (base / "working" / "prompts" / "slide-01.txt").write_text("Z" * 9500)
        ck = base / "working" / "checkpoints"
        ck.mkdir(parents=True)
        (ck / "media_library.json").write_text(json.dumps(GOOD_MEDIA))
        (base / "working" / "copy").mkdir(parents=True)
        (base / "working" / "copy" / "intake.json").write_text(
            json.dumps({"client_ok_qc": True}))

        # Valid waiver for qc
        (base / "waivers.json").write_text(json.dumps([{
            "rule": "qc", "source": "intake_field",
            "intake_field": "client_ok_qc",
            "client_request_quote": "skip qc please",
            "captured_at": "2026-01-01T00:00:00Z",
        }]))

        state = {"job_id": "test-12", "schema_version": 1, "phases": [], "heartbeat": {}}
        store.save(state)
        state = store.load()

        mp = base / "manifest.json"
        mp.write_text(json.dumps({"manifest_version": 25, "phases": [],
                                   "deliverables_required": [], "client_package_files": [],
                                   "autofails": []}))
        manifest = Manifest(mp)
        engine = Engine(base, manifest, store, state)
        rc = engine.close()
        assert rc == st.EXIT_OK, f"qc-waived should exit 0, got {rc}"
        gates = state.get("gates", {})
        assert gates.get("qc", {}).get("state") == "waived"


# ---------------------------------------------------------------------------
# Test 13: import-time assertion holds
# ---------------------------------------------------------------------------
def test_assert_no_overlap():
    from presentation_job.gates import GATE_KEYS, NON_WAIVABLE_GATES
    assert not (set(GATE_KEYS) & set(NON_WAIVABLE_GATES))


# ---------------------------------------------------------------------------
# Test 14: unknown phase fails closed (step 9)
# ---------------------------------------------------------------------------
def test_phase_verifier_fail_closed_unknown_phase():
    import phase_verifiers
    with tempfile.TemporaryDirectory() as tmp:
        ok, reasons = phase_verifiers.verify("P-NOT-A-PHASE", Path(tmp))
        assert ok is False, f"unknown phase should fail-closed, got ok={ok}"
        assert "P-NOT-A-PHASE" in reasons[0]


# ---------------------------------------------------------------------------
# Test 15: raising verifier fails closed (step 9)
# ---------------------------------------------------------------------------
def test_phase_verifier_fail_closed_verifier_raises(monkeypatch):
    import phase_verifiers

    def _raising(run_dir):
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(phase_verifiers.PHASE_VERIFIERS, "P3-ARC", _raising)
    with tempfile.TemporaryDirectory() as tmp:
        ok, reasons = phase_verifiers.verify("P3-ARC", Path(tmp))
        assert ok is False, f"raising verifier should fail-closed, got ok={ok}"
        assert any("RuntimeError" in r for r in reasons)


# ---------------------------------------------------------------------------
# Test 16: qc gate carries warn_only
# ---------------------------------------------------------------------------
def test_qc_gate_has_warn_only():
    from presentation_job.gates import Gates
    with tempfile.TemporaryDirectory() as tmp:
        g = Gates(Path(tmp), {})._qc_gate()
        assert g.get("warn_only") is True


# ---------------------------------------------------------------------------
# Test 17: ocr gate carries warn_only
# ---------------------------------------------------------------------------
def test_ocr_gate_has_warn_only():
    from presentation_job.gates import Gates
    with tempfile.TemporaryDirectory() as tmp:
        g = Gates(Path(tmp), {})._ocr_gate()
        assert g.get("warn_only") is True
        assert g["state"] == "fail"


# ---------------------------------------------------------------------------
# Test 18: WARN_ONLY_GATES value
# ---------------------------------------------------------------------------
def test_warn_only_gates_value():
    from presentation_job.gates import WARN_ONLY_GATES
    assert WARN_ONLY_GATES == ("qc", "ocr_readback")


# ---------------------------------------------------------------------------
# Test 19: TRANSCRIPT_WAIVERS_ACCEPTED defaults False
# ---------------------------------------------------------------------------
def test_transcript_waivers_defaults_false():
    from presentation_job.waivers import TRANSCRIPT_WAIVERS_ACCEPTED
    assert TRANSCRIPT_WAIVERS_ACCEPTED is False


# ---------------------------------------------------------------------------
# Test 20: transcript waiver rejected with message
# ---------------------------------------------------------------------------
def test_transcript_waiver_rejected_with_message():
    from presentation_job.waivers import validate_waiver, WaiverError
    w = {"rule": "script", "source": "transcript",
         "client_request_quote": "yes please",
         "captured_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(WaiverError, match="transcript-sourced waivers are not yet accepted"):
        validate_waiver(w, Path("/nonexistent"))


# ---------------------------------------------------------------------------
# Test 21: prompt_floor passes on good prompts
# ---------------------------------------------------------------------------
def test_prompt_floor_passes_good_prompts():
    from presentation_job.gates import Gates
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "working" / "prompts").mkdir(parents=True)
        (base / "working" / "prompts" / "slide-01.txt").write_text("A" * 9200)
        (base / "working" / "prompts" / "slide-02.txt").write_text("B" * 9500)
        g = Gates(base, {}).evaluate_all()["prompt_floor"]
        assert g["state"] == "pass"
