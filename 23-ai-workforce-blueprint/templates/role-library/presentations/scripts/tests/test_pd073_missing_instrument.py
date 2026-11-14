"""PD-073 — the renderer must not pass by not running.

Acceptance (spec, PD-073): with the prompt_gate import forced to fail and no test
marker -> a failure naming the missing module; with the marker -> the current
(no-op / empty) behaviour.

The trigger used here is build_deck._import_prompt_gate() returning None — the
function's own documented seam for "the shared module is not importable" — so the
tests exercise the real production branch, not a stub of the callers.
"""
import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402


def _rd(tmp_path):
    (tmp_path / "working" / "prompts").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _no_markers(monkeypatch):
    """A REAL production run has none of these. Without clearing them the negative
    case would silently degrade and the test would prove nothing."""
    for var in ("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "CI", "OPENCLAW_TEST"):
        monkeypatch.delenv(var, raising=False)


def _marker(rd):
    p = rd / "working" / "checkpoints" / ".test-context"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("test context", encoding="utf-8")


def _force_prompt_gate_away(monkeypatch):
    monkeypatch.setattr(bd, "_import_prompt_gate", lambda: None)


# --- _canonical_prompt_dir_problems -----------------------------------------

def test_canonical_prompt_dir_problems_names_missing_prompt_gate(tmp_path, monkeypatch):
    """Import forced to fail, no marker -> a named problem, never []."""
    rd = _rd(tmp_path)
    _no_markers(monkeypatch)
    _force_prompt_gate_away(monkeypatch)

    problems = bd._canonical_prompt_dir_problems(rd)

    assert problems, "an unimportable prompt_gate must not read as 'no problems'"
    assert any("prompt_gate" in p for p in problems), problems
    assert any("unavailable" in p for p in problems), problems


def test_canonical_prompt_dir_problems_marker_keeps_current_behaviour(tmp_path, monkeypatch):
    """Same failure, but the .test-context marker is present -> [] as today."""
    rd = _rd(tmp_path)
    _no_markers(monkeypatch)
    _marker(rd)
    _force_prompt_gate_away(monkeypatch)

    assert bd._canonical_prompt_dir_problems(rd) == []


def test_control_prompt_gate_present_clean_dir_is_empty(tmp_path, monkeypatch):
    """CONTROL on the instrument: with the real module importable a clean prompt dir
    is still [] — this change did not turn the detector into an always-fail."""
    rd = _rd(tmp_path)
    _no_markers(monkeypatch)
    assert bd._import_prompt_gate() is not None, "prompt_gate must ship beside build_deck"

    assert bd._canonical_prompt_dir_problems(rd) == []


# --- _verify_aspect_and_readback --------------------------------------------

def test_verify_aspect_and_readback_raises_when_prompt_gate_missing(tmp_path, monkeypatch):
    """Import forced to fail, no marker -> raises, naming the missing module."""
    rd = _rd(tmp_path)
    _no_markers(monkeypatch)
    _force_prompt_gate_away(monkeypatch)
    out_path = rd / "renders" / "slide-01.png"  # canonical: run_dir/renders/

    with pytest.raises(RuntimeError) as exc:
        bd._verify_aspect_and_readback(out_path, {"copy": ["x"]}, 1)

    assert "prompt_gate" in str(exc.value), exc.value
    assert "slide 1" in str(exc.value), exc.value


def test_verify_aspect_and_readback_marker_keeps_current_noop(tmp_path, monkeypatch):
    """Same failure, marker present -> returns None (the pre-change no-op)."""
    rd = _rd(tmp_path)
    _no_markers(monkeypatch)
    _marker(rd)
    _force_prompt_gate_away(monkeypatch)
    out_path = rd / "renders" / "slide-01.png"  # canonical: run_dir/renders/

    assert bd._verify_aspect_and_readback(out_path, {"copy": ["x"]}, 1) is None


# --- the gate the renderer actually reads ------------------------------------

def test_rich_prompt_gate_fails_closed_when_prompt_gate_missing(tmp_path, monkeypatch):
    """PD-073 end to end: the rich-prompt preflight gate no longer skips the
    directory detector when prompt_gate is missing — it fails naming the module."""
    rd = _rd(tmp_path)
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"slide": 1}]}), encoding="utf-8")
    _no_markers(monkeypatch)
    _force_prompt_gate_away(monkeypatch)

    reason = bd._chk_rich_prompts(rd)

    assert reason.startswith("AF-P1:"), reason
    assert "prompt_gate" in reason, reason
