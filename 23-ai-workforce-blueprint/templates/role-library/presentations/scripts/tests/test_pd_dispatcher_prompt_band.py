"""PD-065 -- the prompt band is stated from the shared gate, never a literal.

Acceptance rows (per the consolidation amendments):
  A1  the composed prompt for slide 1 carries the floor and ceiling the gate
      returns (stubbed to 1000/1200) and no stale "9,000";
  (b) parallel_prompt_worker._verify_prompt USES the `constraints` it is given
      (before this unit the argument was ignored);
  (c) dispatcher._verify_single_prompt fails closed, naming the missing module,
      when build_deck cannot be imported -- unless phase_verifiers
      ._degraded_allowed allows a degraded pass in an explicit test/CI context.

No paid call, no network, no live system.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import parallel_prompt_worker as W  # noqa: E402


class _StubGate:
    """The shared gate with the band the test wants to see."""

    def __init__(self, floor: int, ceiling: int):
        self._budget = {"floor": floor, "target_min": (floor + ceiling) // 2,
                        "ceiling": ceiling, "max": ceiling + 5, "pin": 5}

    def length_budget(self) -> dict:
        return dict(self._budget)

    def length_problems(self, text: str):
        return [] if self._budget["floor"] <= len(text.strip()) <= self._budget["ceiling"] else ["length"]


def _dept_root(tmp_path: Path) -> Path:
    root = tmp_path / "presentations"
    root.mkdir(parents=True, exist_ok=True)
    (root / "presentation-manager.md").write_text("role sop", encoding="utf-8")
    return root


def _compose(tmp_path: Path, phase_id: str) -> str:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    order = {"phase_id": phase_id, "_prompt_slide_ordinal": 1,
             "_prompt_slide_total": 25,
             "produces_artifact": ["working/prompts/slide-01.txt"]}
    _system, user = D.compose_prompt(
        phase_id=phase_id, owning_role="presentation-manager",
        dept_root=_dept_root(tmp_path), run_dir=run_dir, order=order,
        attempt=1, prior_reasons=None)
    return user


def test_A1_composed_prompt_states_the_gate_band_and_no_stale_literal(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_shared_prompt_gate", lambda: _StubGate(1000, 1200))
    for phase_id in ("P4-PROMPT", "P-PROMPT-QC"):
        user = _compose(tmp_path, phase_id)
        assert "1,000" in user, phase_id
        assert "1,200" in user, phase_id
        assert "9,000" not in user, phase_id
        assert "18,000" not in user, phase_id


def test_A1_per_slide_instruction_text_uses_the_same_gate_numbers(monkeypatch):
    monkeypatch.setattr(D, "_shared_prompt_gate", lambda: _StubGate(1000, 1200))
    assert D._prompt_band_text() == "1,000-1,200-char"
    monkeypatch.setattr(D, "_shared_prompt_gate", lambda: _StubGate(1000, 1200))
    assert W._prompt_band_text({"min_chars": 700, "max_chars": 900}) == "700 to 900 characters"
    assert W._prompt_band_text({}) == "1,000 to 1,200 characters"


def test_A1_unreadable_budget_refuses_to_author(tmp_path, monkeypatch):
    def _boom():
        raise RuntimeError("prompt_gate.py could not be imported")
    monkeypatch.setattr(D, "_shared_prompt_gate", _boom)
    with pytest.raises(RuntimeError):
        _compose(tmp_path, "P4-PROMPT")


def _prompt_run(tmp_path: Path, text: str) -> Path:
    run_dir = tmp_path / "run"
    prompts = run_dir / "working" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "slide-01.txt").write_text(text, encoding="utf-8")
    return run_dir


def test_c_build_deck_unavailable_fails_closed_naming_the_module(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_bd", None)
    monkeypatch.setattr(D, "_shared_prompt_gate", lambda: _StubGate(10, 100))
    monkeypatch.delenv("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", raising=False)
    run_dir = _prompt_run(tmp_path, "a prompt body well inside the stub band")
    ok, reasons = D._verify_single_prompt(run_dir, 1)
    assert ok is False
    assert any("build_deck" in r for r in reasons), reasons


def test_c_degraded_allowed_still_passes_with_the_note(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_bd", None)
    monkeypatch.setattr(D, "_shared_prompt_gate", lambda: _StubGate(10, 100))
    monkeypatch.setenv("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "1")
    run_dir = _prompt_run(tmp_path, "a prompt body well inside the stub band")
    ok, reasons = D._verify_single_prompt(run_dir, 1)
    assert ok is True
    assert any("degraded to a length-only check" in r for r in reasons), reasons


def test_c_control_missing_prompt_file_still_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_bd", None)
    monkeypatch.setenv("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "1")
    run_dir = tmp_path / "run"
    (run_dir / "working").mkdir(parents=True)
    ok, reasons = D._verify_single_prompt(run_dir, 1)
    assert ok is False
    assert reasons == ["no prompt file"]


def test_b_verify_prompt_uses_the_declared_constraints(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_verify_single_prompt",
                        lambda run_dir, ordinal: (True, []))
    run_dir = tmp_path / "run"
    slide = {"ordinal": 1}
    text = "[ARCHETYPE: A2] Do not add watermarks. " + "x" * 40

    ok, reasons = W._verify_prompt(
        slide, text, run_dir,
        {"min_chars": 10_000, "max_chars": 20_000,
         "required_blocks": ["[ARCHETYPE", "DO-NOT BLOCK", "Do not "]})
    assert ok is False
    joined = " | ".join(reasons)
    assert "under the declared floor 10000" in joined, reasons
    assert "'DO-NOT BLOCK' is missing" in joined, reasons

    ok, reasons = W._verify_prompt(
        slide, text, run_dir,
        {"min_chars": 1, "max_chars": 10_000,
         "required_blocks": ["[ARCHETYPE", "Do not "]})
    assert ok is True, reasons
    assert reasons == []


def test_b_gate_pass_with_an_advisory_note_still_passes(tmp_path, monkeypatch):
    """Amendment (c) end to end: the dispatcher may PASS with the explicit
    test/CI degraded NOTE. Only the ADDED constraint reasons may flip that
    verdict -- judging `not reasons` would fail a check the gate just allowed."""
    note = ("NOTE: build_deck.check_prompt_qc_deterministic unavailable -- "
            "degraded to a length-only check (explicit test/CI context)")
    monkeypatch.setattr(D, "_verify_single_prompt", lambda rd, o: (True, [note]))
    ok, reasons = W._verify_prompt(
        {"ordinal": 1}, "a body", tmp_path / "run",
        {"min_chars": 1, "max_chars": 10_000})
    assert ok is True, reasons
    assert reasons == [note]

    # ...and a real constraint violation on the same advisory pass still fails
    ok, reasons = W._verify_prompt(
        {"ordinal": 1}, "a body", tmp_path / "run",
        {"min_chars": 10_000, "max_chars": 20_000})
    assert ok is False, reasons
