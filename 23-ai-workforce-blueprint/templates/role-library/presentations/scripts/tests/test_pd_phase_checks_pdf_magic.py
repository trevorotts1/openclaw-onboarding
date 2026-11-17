#!/usr/bin/env python3
"""test_pd208_pdf_magic.py — PD-208 (lane FL17).

01-BUILD-SPEC.md, section PD-208:

  **Change:** add ``_verify_binary_artifact(pattern, min_bytes, magic,
  scale_by_slides, floor_formula)`` beside ``_verify_text_artifact``: size from
  the file's byte length, and the first bytes must equal ``magic``. Register the
  three PDF steps with ``magic=b"%PDF"``.

  **Acceptance:** the PD-208 probe as a test: text named ``.pdf`` -> fail
  "not a PDF"; a file starting ``%PDF`` above the floor -> pass.

Rows proven here:

  A1a  a TEXT file named ``*.pdf``, above the floor  -> FAIL, reason says
       "not a PDF"  (for EACH of the three registered PDF steps)
  A1b  a file starting ``%PDF`` above the floor      -> PASS (same three steps)
  A1c  ``%PDF`` exactly at the floor                 -> PASS   (byte length, not
       decoded-text length, is what the floor compares)
  A1d  ``%PDF`` one byte under the floor             -> FAIL on size
  A1e  the CONTROL that keeps A1a honest: the SAME text fixture still PASSES the
       old ``_verify_text_artifact``. If the fixture ever shrinks below the text
       floor, this assert fails, so A1a can never be satisfied vacuously.

No network, no model call, no live service.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

# (phase id, produces_artifact pattern, floor key) — the three PDF steps the
# spec names. The pattern is the one the MANIFEST declares (test_pd061 A4 keeps
# that parity green; this file proves the registration is the binary one).
PDF_STEPS = (
    ("P8.1-PDF-EXPORT", "working/deliverables/*-FINAL.pdf", "deck_pdf"),
    ("P8.2-GUIDE", "working/deliverables/PRESENTER-GUIDE.pdf", "guide_pdf"),
    ("P9.1-SPEECH-PDF", "working/deliverables/PRESENTERS-SPEECH.pdf", "speech_pdf"),
)

# Comfortably above every floor these steps can compute for an empty run dir:
# pdf_floor(1)=8192, guide_floor(1)=12000, speech_pdf=3000.
_BIG = 200_000


def _write(run_dir: Path, pattern: str, data: bytes) -> Path:
    """Write ``data`` at a concrete path for ``pattern`` (wildcards resolved)."""
    rel = pattern.replace("*", "DECK")
    p = run_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


@pytest.mark.parametrize("phase_id,pattern,key", PDF_STEPS)
def test_a1a_text_named_pdf_fails_not_a_pdf(tmp_path, phase_id, pattern, key):
    """A1a: a long TEXT file named *.pdf is not a PDF — fail, and say so."""
    run_dir = tmp_path / "run"
    _write(run_dir, pattern, b"z" * _BIG)
    ok, reasons = pv.PHASE_VERIFIERS[phase_id](run_dir)
    assert not ok, (
        f"{phase_id}: a {_BIG:,}-byte text file named *.pdf must NOT pass — "
        f"the step is checked for a PDF")
    assert any("not a PDF" in r for r in reasons), (
        f"{phase_id}: the failure must say the file is not a PDF, got {reasons}")


@pytest.mark.parametrize("phase_id,pattern,key", PDF_STEPS)
def test_a1b_pdf_magic_above_floor_passes(tmp_path, phase_id, pattern, key):
    """A1b: a file starting %PDF, above the floor, is accepted."""
    run_dir = tmp_path / "run"
    _write(run_dir, pattern, b"%PDF-1.7\n" + b"x" * _BIG)
    ok, reasons = pv.PHASE_VERIFIERS[phase_id](run_dir)
    assert ok, f"{phase_id}: a real PDF above the floor must pass, got {reasons}"


def test_a1c_pdf_exactly_at_the_floor_passes(tmp_path):
    """A1c: the floor compares BYTES on disk, and is inclusive."""
    floor = pv._MIN_BYTES["speech_pdf"]
    run_dir = tmp_path / "run"
    _write(run_dir, "working/deliverables/PRESENTERS-SPEECH.pdf",
           b"%PDF" + b"z" * (floor - 4))
    p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.pdf"
    assert p.stat().st_size == floor, "fixture is not exactly at the floor"
    ok, reasons = pv.PHASE_VERIFIERS["P9.1-SPEECH-PDF"](run_dir)
    assert ok, f"a {floor:,}-byte PDF (exactly the floor) must pass, got {reasons}"


def test_a1d_pdf_one_byte_under_the_floor_fails_on_size(tmp_path):
    """A1d: %PDF at offset 0 is not enough — the byte-length floor still applies."""
    floor = pv._MIN_BYTES["speech_pdf"]
    run_dir = tmp_path / "run"
    _write(run_dir, "working/deliverables/PRESENTERS-SPEECH.pdf",
           b"%PDF" + b"z" * (floor - 5))
    ok, reasons = pv.PHASE_VERIFIERS["P9.1-SPEECH-PDF"](run_dir)
    assert not ok, "a PDF one byte under the floor must fail"
    assert any("bytes <" in r for r in reasons), (
        f"the failure must be about size, not magic, got {reasons}")


def test_a1e_control_old_text_check_still_passes_the_text_fixture(tmp_path):
    """A1e: the A1a fixture WOULD have passed the old text check.

    This is what makes A1a a real before/after pair rather than a test that
    passes because the fixture is too small. If the fixture ever drops below the
    text floor, this control fails instead of A1a silently going vacuous.
    """
    run_dir = tmp_path / "run"
    _write(run_dir, "working/deliverables/PRESENTERS-SPEECH.pdf", b"z" * _BIG)
    old = pv._verify_text_artifact(
        "working/deliverables/PRESENTERS-SPEECH.pdf",
        pv._MIN_BYTES["speech_pdf"])
    ok_old, reasons_old = old(run_dir)
    assert ok_old, (
        "CONTROL BROKEN: the text fixture must pass the OLD text check, "
        f"otherwise A1a proves nothing; got {reasons_old}")


def test_the_three_pdf_steps_are_registered_with_the_binary_factory():
    """A1: registration, not just the helper — the three steps name the factory.

    The factory stamps ``artifact_pattern`` on every verifier it builds (the
    same stamp test_pd061's parity walk reads). ``_verify_text_artifact`` also
    stamps it, so the pattern alone cannot tell the two factories apart — the
    proof is behavioural: each of the three steps rejects a text *.pdf, which
    only the binary factory does (A1a) — and here we additionally pin that the
    helper exists with the exact signature the spec names.
    """
    assert callable(pv._verify_binary_artifact)
    import inspect
    params = list(inspect.signature(pv._verify_binary_artifact).parameters.items())
    assert [n for n, _ in params] == [
        "pattern", "min_bytes", "magic", "scale_by_slides", "floor_formula"], (
        f"the helper's signature must match the spec, got {[n for n, _ in params]}")
    assert params[2][1].default == b"%PDF", (
        f"magic must default to b'%PDF', got {params[2][1].default!r}")
    for phase_id, pattern, _key in PDF_STEPS:
        assert getattr(pv.PHASE_VERIFIERS[phase_id], "artifact_pattern", None) == pattern, (
            f"{phase_id}: the registered verifier no longer carries its checked path")
