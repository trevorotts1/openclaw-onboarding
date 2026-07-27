"""Tests for waivers (U013).  Covers non-waivable enforcement, quote minimum,
duplicate detection, valid waiver application, and import-time assertion."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.gates import (
    Gates, GATE_KEYS, NON_WAIVABLE_GATES, WARN_ONLY_GATES, ALL_GATE_KEYS,
)
from presentation_job.waivers import WaiverError, load_waivers, validate_waiver
from presentation_job.state import StateStore, EXIT_OK, EXIT_GATE_BLOCKED, EXIT_WAIVER_INVALID
import ghl_media_push as gmp

_GOOD_MEDIA_SOURCE = Path(gmp.__file__).read_text()


# ---------------------------------------------------------------------------
# Test 9 — ocr_readback waiver exits 9 regardless of quote quality
# ---------------------------------------------------------------------------
def test_ocr_readback_cannot_be_waived(tmp_path: Path):
    """A well-sourced waiver naming ocr_readback must be rejected."""
    waiver = {
        "rule": "ocr_readback",
        "source": "intake_field",
        "intake_field": "client_ok_no_ocr",
        "client_request_quote": "we do not need the readback",
        "captured_at": "2026-07-25T00:00:00Z",
    }
    with pytest.raises(WaiverError, match="not a waivable gate"):
        validate_waiver(waiver, tmp_path)


# ---------------------------------------------------------------------------
# Test 10 — 2-character quote exits 9
# ---------------------------------------------------------------------------
def test_two_char_quote_exits_9(tmp_path: Path):
    """A waiver with a client_request_quote shorter than 3 chars must be rejected."""
    waiver = {
        "rule": "qc",
        "source": "intake_field",
        "intake_field": "skip_qc",
        "client_request_quote": "ok",
        "captured_at": "2026-07-25T00:00:00Z",
    }
    with pytest.raises(WaiverError, match="no client_request_quote"):
        validate_waiver(waiver, tmp_path)


# ---------------------------------------------------------------------------
# Test 11 — two waivers naming the same gate exit 9
# ---------------------------------------------------------------------------
def test_duplicate_waivers_exit_9(tmp_path: Path):
    """load_waivers must reject two waivers naming the same gate."""
    waivers_file = tmp_path / "waivers.json"
    waivers_file.write_text(json.dumps([
        {"rule": "qc", "source": "intake_field", "intake_field": "skip_qc",
         "client_request_quote": "skip the QC on this one", "captured_at": "2026-07-25T00:00:00Z"},
        {"rule": "qc", "source": "intake_field", "intake_field": "skip_qc_2",
         "client_request_quote": "I also want to skip QC", "captured_at": "2026-07-25T00:00:01Z"},
    ]))
    with pytest.raises(WaiverError, match="two waivers name the same gate"):
        load_waivers(tmp_path)


# ---------------------------------------------------------------------------
# Test 12 — valid intake_field waiver for qc lets qc-failing job close
# ---------------------------------------------------------------------------
def test_valid_waiver_lets_qc_failing_job_close(tmp_path: Path, capsys):
    """A valid intake_field waiver for qc must mark the gate waived, not failed."""
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
    src = ast.parse(_GOOD_MEDIA_SOURCE)
    good = next(ast.literal_eval(n.value) for n in ast.walk(src)
                if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == "GOOD_MEDIA" for t in n.targets))
    (ck / "media_library.json").write_text(json.dumps(good))

    # Set up intake.json for the waiver field
    cpy = run_dir / "working" / "copy"
    cpy.mkdir(parents=True)
    (cpy / "intake.json").write_text(json.dumps({"skip_qc": True}))

    # Write a valid waiver for qc
    (run_dir / "waivers.json").write_text(json.dumps([{
        "rule": "qc",
        "source": "intake_field",
        "intake_field": "skip_qc",
        "client_request_quote": "I want to skip QC on this deck",
        "captured_at": "2026-07-25T00:00:00Z",
    }]))

    store = StateStore(run_dir)
    state = {"job_id": "t12", "schema_version": 1, "phases": [],
             "gates": {}, "presentation_type": "from_scratch"}
    store.save(state)

    from presentation_job.phases import Engine
    from presentation_job.manifest import Manifest
    man_path = _scripts_dir.parent.parent.parent.parent.parent / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
    manifest = Manifest(man_path)
    engine = Engine(run_dir, manifest, store, store.load(), dry_run=False)

    rc = engine.close()
    assert rc == EXIT_OK, f"waived qc should allow close with exit 0, got {rc}"
    state2 = store.load()
    qc_gate = state2.get("gates", {}).get("qc", {})
    assert qc_gate.get("state") == "waived", \
        f"qc gate must be waived, got {qc_gate.get('state')}"


# ---------------------------------------------------------------------------
# Test 13 — import-time assertion: GATE_KEYS and NON_WAIVABLE_GATES are disjoint
# ---------------------------------------------------------------------------
def test_gate_keys_non_waivable_disjoint():
    """The import-time assertion in gates.py guarantees no overlap."""
    overlap = set(GATE_KEYS) & set(NON_WAIVABLE_GATES)
    assert not overlap, \
        f"GATE_KEYS and NON_WAIVABLE_GATES must be disjoint; overlap: {overlap}"


# ---------------------------------------------------------------------------
# Test — broken waiver (no client quote) exits 9 via close()
# ---------------------------------------------------------------------------
def test_broken_waiver_exits_9_on_close(tmp_path: Path, capsys):
    """A waiver with a 2-character quote must produce exit 9 when processed by close()."""
    run_dir = tmp_path

    # Satisfy the hard gates
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
    src = ast.parse(_GOOD_MEDIA_SOURCE)
    good = next(ast.literal_eval(n.value) for n in ast.walk(src)
                if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == "GOOD_MEDIA" for t in n.targets))
    (ck / "media_library.json").write_text(json.dumps(good))

    # Broken waiver — 2-char quote and missing captured_at
    (run_dir / "waivers.json").write_text(json.dumps([{
        "rule": "teleprompter",
        "source": "transcript",
        "client_request_quote": "ok",
        "captured_at": "2026-07-25T00:00:00Z",
    }]))

    store = StateStore(run_dir)
    state = {"job_id": "t_brk", "schema_version": 1, "phases": [],
             "gates": {}, "presentation_type": "from_scratch"}
    store.save(state)

    from presentation_job.phases import Engine
    from presentation_job.manifest import Manifest
    man_path = _scripts_dir.parent.parent.parent.parent.parent / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
    manifest = Manifest(man_path)
    engine = Engine(run_dir, manifest, store, store.load(), dry_run=False)

    rc = engine.close()
    assert rc == EXIT_WAIVER_INVALID, f"broken waiver must exit 9, got {rc}"
