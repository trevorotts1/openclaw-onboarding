#!/usr/bin/env python3
"""test_pd_phase_checks_png_signature.py — PD-105 (lane FL17).

01-BUILD-SPEC.md, section PD-105:

  **Build unit PD-105 (Moderate, Sonnet; lane FL17).** In
  ``_verify_infographic_checklist`` require the PNG signature (first 8 bytes)
  before the size test. [...] (b) From PD-215: the builder's status file will
  carry ``render_verified`` in place of ``qc_passed``; this check accepts either
  key during the change-over.

  **Acceptance:** a 102,400-byte file of letters fails; a real PNG of that size
  passes.

Rows proven here:

  A1a  a 102,400-byte file of letters at infographic.png  -> FAIL, reason says
       "not a PNG"
  A1b  a real PNG (signature + filler) of 102,400 bytes    -> PASS
  A1c  the signature test comes BEFORE the size test: a letters file UNDER the
       floor reports "not a PNG" ahead of "bytes <"
  A1d  status carries ``render_verified`` (no ``qc_passed``) -> PASS  (PD-215)
  A1e  the CONTROL that keeps A1a honest: the letters fixture is EXACTLY at the
       floor, so the size test alone would pass it — only the signature can
       fail it.

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

PHASE = "P8.3-INFOGRAPHIC"
FLOOR = 102_400
PNG_SIG = b"\x89PNG\r\n\x1a\n"
LETTERS = b"x"


def _run_dir(tmp_path: Path, png: bytes, status: dict | None = None) -> Path:
    """A run dir that satisfies every OTHER requirement of the phase, so the
    only variable under test is the PNG bytes (and, for A1d, the status keys)."""
    run_dir = tmp_path / "run"
    for rel in ("working/qc", "working/deliverables", "working/checkpoints",
                "working/prompts"):
        (run_dir / rel).mkdir(parents=True)
    (run_dir / "working" / "prompts" / "infographic-prompt.txt").write_text("P" * 9000)
    (run_dir / "working" / "deliverables" / "infographic.png").write_bytes(png)
    (run_dir / "working" / "checkpoints" / "infographic_status.json").write_text(
        json.dumps(status if status is not None else {
            "infographic_format": "checklist", "status": "ready", "qc_passed": True,
            "prompt_path": "working/prompts/infographic-prompt.txt",
            "render_path": "working/deliverables/infographic.png",
            "deliverable_path": "working/deliverables/infographic.png"}))
    (run_dir / "working" / "qc" / "infographic_checklist_verdict.json").write_text(
        json.dumps({
            "phase_id": PHASE, "verdict": "pass",
            "checked": ["all prompt checklist items visible", "no clipping",
                        "correct 9:16 format"],
            "prompt_path": "working/prompts/infographic-prompt.txt",
            "render_path": "working/deliverables/infographic.png",
            "status_path": "working/checkpoints/infographic_status.json",
            "render_status_ok": True, "reasons": []}))
    return run_dir


def _letters(n: int = FLOOR) -> bytes:
    return LETTERS * n


def _real_png(n: int = FLOOR) -> bytes:
    return PNG_SIG + LETTERS * (n - len(PNG_SIG))


def test_a1a_102400_bytes_of_letters_fails_not_a_png(tmp_path):
    """A1a: the spec's exact failing fixture — 102,400 bytes of letters."""
    png = _letters()
    assert len(png) == FLOOR, "fixture is not 102,400 bytes"
    run_dir = _run_dir(tmp_path, png)
    ok, reasons = pv.verify(PHASE, run_dir)
    assert not ok, (
        f"a {FLOOR:,}-byte file of letters must NOT pass the infographic check")
    assert any("not a PNG" in r for r in reasons), (
        f"the failure must say the file is not a PNG, got {reasons}")


def test_a1b_real_png_of_that_size_passes(tmp_path):
    """A1b: the spec's exact passing fixture — a real PNG of 102,400 bytes."""
    png = _real_png()
    assert len(png) == FLOOR and png.startswith(PNG_SIG)
    run_dir = _run_dir(tmp_path, png)
    ok, reasons = pv.verify(PHASE, run_dir)
    assert ok, f"a real {FLOOR:,}-byte PNG must pass, got {reasons}"


def test_a1c_signature_is_checked_before_the_size_test(tmp_path):
    """A1c: order — a small letters file reports 'not a PNG' first."""
    run_dir = _run_dir(tmp_path, _letters(1000))
    ok, reasons = pv.verify(PHASE, run_dir)
    assert not ok
    sig_at = next((i for i, r in enumerate(reasons) if "not a PNG" in r), None)
    size_at = next((i for i, r in enumerate(reasons) if "bytes <" in r), None)
    assert sig_at is not None, f"no signature failure reported, got {reasons}"
    assert size_at is not None, f"the size test must still run, got {reasons}"
    assert sig_at < size_at, (
        f"the signature test must come BEFORE the size test, got {reasons}")


def test_a1d_render_verified_is_accepted_in_place_of_qc_passed(tmp_path):
    """A1d (PD-215 change-over): render_verified alone passes the status check."""
    run_dir = _run_dir(tmp_path, _real_png(), status={
        "infographic_format": "checklist", "status": "ready", "render_verified": True,
        "prompt_path": "working/prompts/infographic-prompt.txt",
        "render_path": "working/deliverables/infographic.png",
        "deliverable_path": "working/deliverables/infographic.png"})
    ok, reasons = pv.verify(PHASE, run_dir)
    assert ok, f"render_verified must be accepted as qc_passed, got {reasons}"

    # Negative control: neither key present is still a failure.
    run_dir2 = _run_dir(tmp_path / "neither", _real_png(), status={
        "infographic_format": "checklist", "status": "ready"})
    ok2, reasons2 = pv.verify(PHASE, run_dir2)
    assert not ok2 and any("render_verified" in r for r in reasons2), (
        f"a status with neither key must fail, got {reasons2}")


def test_a1e_control_the_letters_fixture_is_exactly_at_the_floor(tmp_path):
    """A1e: A1a cannot be satisfied by the size test — the fixture is AT the
    floor, so before PD-105 it passed. This control pins that."""
    png = _letters()
    run_dir = _run_dir(tmp_path, png)
    p = run_dir / "working" / "deliverables" / "infographic.png"
    assert p.stat().st_size == FLOOR, (
        "CONTROL BROKEN: fixture must sit exactly at the floor, otherwise A1a "
        "could be failing on size and prove nothing about the signature")
    ok, reasons = pv.verify(PHASE, run_dir)
    assert not any("bytes <" in r for r in reasons), (
        f"the fixture must NOT trip the size test, got {reasons}")
