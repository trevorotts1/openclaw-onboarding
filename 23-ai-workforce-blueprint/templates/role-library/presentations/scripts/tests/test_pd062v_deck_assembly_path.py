#!/usr/bin/env python3
"""test_pd062v_deck_assembly_path.py — PD-062v (Critical, lane FL17).

Critical finding PD-062: the engine looks for the deck where nothing writes it.
The render writes the assembled deck to ``working/deliverables/`` while the
assembly step accepted any ``**/*.pptx`` anywhere in the run folder — so a stray
file could stand in for the deck, and the declared path was never resolved.

After the fix:

  * ``artifact_path`` resolves a folder-carrying pattern
    (``working/deliverables/*-FINAL.pptx``) AS WRITTEN relative to the run
    folder; patterns with no folder keep the run-top / working/upsell lookups.
  * ``P8-ASSEMBLE`` requires exactly one deck matching
    ``working/deliverables/*-FINAL.pptx`` that is a ZIP holding
    ``ppt/presentation.xml``. While the manifest still declares the run-top
    ``*-FINAL.pptx``, a run-top deck is accepted too (safe before or after
    PD-062).

Rows (01-BUILD-SPEC.md, section PD-062v):

  A1  a deck only at working/deliverables/out-FINAL.pptx is found
  A2  control: a deck only at the run top is found
  A3  a stray .pptx in another folder and no -FINAL deck -> assembly fails and
      names the expected path
  A4  a text file named x-FINAL.pptx fails as "not a deck"

No network, no model call, no live service; every fixture is a stubbed file.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

EXPECTED = "working/deliverables/*-FINAL.pptx"


def _deck(path: Path) -> Path:
    """A real assembled deck: a ZIP holding ppt/presentation.xml, above 1 KB."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/presentation.xml", "<p:presentation/>" + "x" * 2048)
        zf.writestr("[Content_Types].xml", "<Types/>")
    return path


def _harmony_pass(monkeypatch):
    """Harmony is a separate proof; stub it to PASS so the deck check decides."""
    monkeypatch.setattr(pv, "_bd_fn", lambda name: (lambda run_dir: ""))


# ---------------------------------------------------------------------------
# A1 — the deck at the render's own output dir is found
# ---------------------------------------------------------------------------

def test_a1_deck_under_working_deliverables_is_found(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    deck = _deck(run_dir / "working" / "deliverables" / "out-FINAL.pptx")

    assert pv.artifact_path(run_dir, EXPECTED) == deck, \
        "the folder-carrying pattern must resolve as written"

    _harmony_pass(monkeypatch)
    ok, reasons = pv.verify("P8-ASSEMBLE", run_dir)
    assert ok, f"a deck at {EXPECTED} must pass assembly, got {reasons}"


# ---------------------------------------------------------------------------
# A2 — control: the manifest's run-top pattern is still accepted
# ---------------------------------------------------------------------------

def test_a2_run_top_deck_is_found(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    deck = _deck(run_dir / "out-FINAL.pptx")

    assert pv.artifact_path(run_dir, "*-FINAL.pptx") == deck

    _harmony_pass(monkeypatch)
    ok, reasons = pv.verify("P8-ASSEMBLE", run_dir)
    assert ok, f"a run-top deck must pass assembly, got {reasons}"


# ---------------------------------------------------------------------------
# A3 — a stray .pptx elsewhere is not the deck, and the miss names the path
# ---------------------------------------------------------------------------

def test_a3_stray_pptx_is_not_the_deck_and_expected_path_is_named(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    _deck(run_dir / "working" / "renders" / "stray.pptx")  # a real ZIP, wrong place

    _harmony_pass(monkeypatch)
    ok, reasons = pv.verify("P8-ASSEMBLE", run_dir)
    assert not ok, "a stray .pptx must not satisfy assembly"
    joined = "; ".join(reasons)
    assert EXPECTED in joined, f"the failure must name the expected path, got {reasons}"
    assert "stray.pptx" in joined, f"the failure must name what it found, got {reasons}"


# ---------------------------------------------------------------------------
# A4 — a text file named like a deck is not a deck
# ---------------------------------------------------------------------------

def test_a4_text_file_named_final_pptx_fails_as_not_a_deck(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    fake = run_dir / "x-FINAL.pptx"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_text("this is not a pptx\n" * 200, encoding="utf-8")

    _harmony_pass(monkeypatch)
    ok, reasons = pv.verify("P8-ASSEMBLE", run_dir)
    assert not ok, "a renamed text file must not pass assembly"
    joined = "; ".join(reasons)
    assert "not a deck" in joined, f"must fail as 'not a deck', got {reasons}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
