#!/usr/bin/env python3
"""test_pd_phase_checks_pd310b.py — PD-310b (lane FL17).

The two human-only craft rules (AF-OBI-4, AF-OBI) and the six warning holds
were applied by the OLDER runner only — ``run_signature_deck.attest_phase``
calls ``craft_judgement.attestation_blocker`` / ``warning_hold_blocker`` before
it appends an attestation. The phase-verifier engine path (``phase_verifiers``)
did not, so a QC phase could attest there with no independent human verdict and
no acknowledgement on record.

This unit calls ``craft_judgement.engine_attestation_reasons(run_dir, phase_id)``
from the engine's two step checks, behind a switch that is OFF by default.

Rows (01-BUILD-SPEC.md, section PD-310b):

  A1  variable unset: both step checks return exactly what they returned
      before (same fixture, compare the outputs).
  A2  variable set and a human verdict missing: a reason that starts
      ``OPERATOR-REVIEW:``.
  A3  variable set and every verdict present: pass.

Dependency: PD-310 supplies ``craft_judgement.engine_attestation_reasons``.
On a tree without it A2/A3 SKIP with an explicit reason — a skip is NOT a pass
— and they are proven in an integration tree that carries PD-310; this unit's
build report names the command.

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

SWITCH = "PRESENTATION_CRAFT_ENGINE_HOLDS"
# The two step ids PD-310's report names (craft_judgement.HUMAN_VERDICT_PHASES).
STEPS = ("P1Q-COPY-QC", "P-PROMPT-QC")
# A third phase that is NOT one of the two — it must never be touched.
UNRELATED = "P4-COPY"
SENTINEL = (True, ["SENTINEL-NOTE"])


def _hook_available() -> bool:
    """True only when PD-310's module and its engine hook are on this tree."""
    try:
        import craft_judgement
    except Exception:  # noqa: BLE001 — absent or unimportable = not available
        return False
    return callable(getattr(craft_judgement, "engine_attestation_reasons", None))


needs_pd310 = pytest.mark.skipif(
    not _hook_available(),
    reason="PD-310's craft_judgement.engine_attestation_reasons is not on this "
           "branch yet (depends_on PD-310, still IN_BATCH) — A2/A3 are proven in "
           "an integration tree that carries it; this skip is NOT a pass",
)


@pytest.fixture()
def run_dir(tmp_path):
    rd = tmp_path / "run-310b"
    rd.mkdir()
    return rd


@pytest.fixture()
def sentinel(monkeypatch):
    """Both step checks answer a known pair, so the switch is what is measured.

    A1 is 'returns exactly what it returned before': with the switch off the
    observed pair must be byte-for-byte the sentinel's pair, for both ids."""
    def fake(rd):
        return SENTINEL

    for sid in STEPS:
        monkeypatch.setitem(pv.PHASE_VERIFIERS, sid, fake)
    return fake


def _write_verdicts(run_dir: Path) -> Path:
    """Two independent 'pass' verdicts, shaped as craft_judgement.human_verdicts
    accepts: rule_code in the human bucket, run_id == the run folder's name,
    a reviewer that is not a builder identity, and a rationale."""
    p = run_dir / "working" / "qc" / "human_craft_verdicts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"verdicts": [
        {"rule_code": "AF-OBI-4", "verdict": "pass", "run_id": run_dir.name,
         "reviewer": "Opus QC lane", "rationale": "independent read of the deck",
         "captured_at": "2026-11-13T20:00:00Z"},
        {"rule_code": "AF-OBI", "verdict": "pass", "run_id": run_dir.name,
         "reviewer": "Opus QC lane", "rationale": "independent read of the deck",
         "captured_at": "2026-11-13T20:00:00Z"},
    ]}), encoding="utf-8")
    return p


# ---------------------------------------------------------------- A1 ----

def test_a1_switch_unset_both_step_checks_unchanged(monkeypatch, run_dir, sentinel):
    """A1: variable unset -> both step checks return exactly what they did."""
    monkeypatch.delenv(SWITCH, raising=False)
    for sid in STEPS:
        assert pv.verify(sid, run_dir) == SENTINEL, sid


def test_a1_switch_only_literal_one_turns_it_on(monkeypatch, run_dir, sentinel):
    """A1: any value but the literal "1" is off — same outputs as unset."""
    for value in ("", "0", "2", "true", "yes"):
        monkeypatch.setenv(SWITCH, value)
        for sid in STEPS:
            assert pv.verify(sid, run_dir) == SENTINEL, (value, sid)


def test_a1_unrelated_phase_never_touched(monkeypatch, run_dir, sentinel):
    """A1: even switched on, a phase outside the two ids is unchanged."""
    monkeypatch.setenv(SWITCH, "1")
    monkeypatch.setitem(pv.PHASE_VERIFIERS, UNRELATED, sentinel)
    assert pv.verify(UNRELATED, run_dir) == SENTINEL


# ---------------------------------------------------------------- A2 ----

@needs_pd310
def test_a2_switch_on_missing_verdict_is_operator_review(monkeypatch, run_dir, sentinel):
    """A2: switched on with no human verdict file -> OPERATOR-REVIEW reason."""
    monkeypatch.setenv(SWITCH, "1")
    for sid in STEPS:
        ok, reasons = pv.verify(sid, run_dir)
        assert ok is False, sid
        assert any(r.startswith("OPERATOR-REVIEW:") for r in reasons), (sid, reasons)
        joined = " | ".join(reasons)
        # Not vacuous: the reason is the human-verdict hold, not a module that
        # failed to import.
        assert "AF-OBI-HUMAN-VERDICT" in joined, (sid, reasons)


# ---------------------------------------------------------------- A3 ----

@needs_pd310
def test_a3_switch_on_every_verdict_present_passes(monkeypatch, run_dir, sentinel):
    """A3: switched on with both verdicts recorded -> the step passes."""
    monkeypatch.setenv(SWITCH, "1")
    _write_verdicts(run_dir)
    for sid in STEPS:
        assert pv.verify(sid, run_dir) == SENTINEL, sid


@needs_pd310
def test_parity_the_two_step_ids_are_pd310s_human_verdict_phases():
    """The local gate tuple and PD-310's own set must stay equal — a copy that
    drifts would hold the wrong step (or miss one)."""
    import craft_judgement

    assert set(STEPS) == set(craft_judgement.HUMAN_VERDICT_PHASES)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
