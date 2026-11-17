#!/usr/bin/env python3
"""test_pd_phase_checks_image_check_vision.py — PD-205b (lane FL17).

01-BUILD-SPEC.md, section PD-205b, "The image-check contract tests something
that can fail", carried-over acceptance row, VERBATIM:

  **Acceptance:** report graded by `deepseek-v4.1-flash` → fail; by `glm-ocr`
  → pass; by an unknown name → fail.

And the binding consolidation amendment (Pass 6) that adds the second rule:

  Add acceptance rows for the second rule: grader equal to author fails;
  `author_model` absent fails.

Rows proven here:

  A1a  graded_by_model == "deepseek-v4.1-flash" (registry: text)  -> FAIL,
       reason is the image-check/cannot-read-images branch
  A1b  graded_by_model == "glm-ocr" (registry: vision)            -> PASS
  A1c  graded_by_model == an unknown id                           -> FAIL
       (unknown never clears the floor)
  A1d  author_model == graded_by_model ("glm-ocr" twice)           -> FAIL
  A1e  no author_model at all                                      -> FAIL
  A1f  CONTROL: the same report as A1a but with graded_by_model swapped to
       glm-ocr passes — so A1a's red comes from CAPABILITY, not from any other
       field in the fixture.

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

VISION = "glm-ocr"                     # registry: modality vision
TEXT_MODEL = "deepseek-v4.1-flash"     # registry: modality text
UNKNOWN = "totally-made-up-model-xyz"  # registry: nothing


def _run_dir(tmp_path: Path, *, graded_by_model: str, author_model=...,
             n_slides: int = 2) -> Path:
    """A run dir whose image_qc_report.json satisfies every OTHER FIX 33 row,
    so only the row under test can turn it red."""
    rd = tmp_path
    qc = rd / "working" / "qc"
    qc.mkdir(parents=True)
    renders = rd / "renders"
    renders.mkdir()
    for n in range(1, n_slides + 1):
        (renders / f"slide-{n:02d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    report = {
        "gate": "AF-IMAGE-QC",
        "graded_by_provider": "ollama-cloud",
        "graded_by_model": graded_by_model,
        "request_id": "req-vision-unit-001",
        "slides": [{"slide": n, "observed_text": f"slide {n:02d} read"}
                   for n in range(1, n_slides + 1)],
    }
    if author_model is not ...:
        report["author_model"] = author_model
    (qc / "image_qc_report.json").write_text(json.dumps(report), encoding="utf-8")
    return rd


def test_A1a_text_model_grader_fails(tmp_path):
    rd = _run_dir(tmp_path, graded_by_model=TEXT_MODEL, author_model="kimi-v4-a")
    ok, reasons = pv._fix33_check_report(rd, degraded=False)
    assert ok is False
    assert any("cannot read images" in r for r in reasons), reasons


def test_A1b_vision_model_grader_passes(tmp_path):
    rd = _run_dir(tmp_path, graded_by_model=VISION, author_model=TEXT_MODEL)
    ok, reasons = pv._fix33_check_report(rd, degraded=False)
    assert (ok, reasons) == (True, [])


def test_A1c_unknown_model_grader_fails(tmp_path):
    rd = _run_dir(tmp_path, graded_by_model=UNKNOWN, author_model=TEXT_MODEL)
    ok, reasons = pv._fix33_check_report(rd, degraded=False)
    assert ok is False
    assert any("cannot read images" in r and "unknown" in r for r in reasons), reasons


def test_A1d_grader_equal_to_author_fails(tmp_path):
    rd = _run_dir(tmp_path, graded_by_model=VISION, author_model=VISION)
    ok, reasons = pv._fix33_check_report(rd, degraded=False)
    assert ok is False
    assert any("equals" in r and "graded its own work" in r for r in reasons), reasons


def test_A1e_missing_author_model_fails(tmp_path):
    rd = _run_dir(tmp_path, graded_by_model=VISION)  # no author_model
    ok, reasons = pv._fix33_check_report(rd, degraded=False)
    assert ok is False
    assert any("no author_model" in r for r in reasons), reasons


def test_A1f_control_same_fixture_vision_grader_passes(tmp_path):
    """A1a's red is the grader's capability: swap only that one field and the
    identical fixture is green."""
    rd = _run_dir(tmp_path, graded_by_model=VISION, author_model="kimi-v4-a")
    ok, reasons = pv._fix33_check_report(rd, degraded=False)
    assert (ok, reasons) == (True, [])
