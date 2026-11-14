"""PD-211 — the copy teeth name a slide with no copy, and the typography teeth say
what they actually measure.

Pinned here (PASS5-GATES.md, PD-211 acceptance):

  A1  slides.json with slide 2's copy empty and a passing report -> the copy teeth
      fail naming slide 2; the phrase "RE-MEASURES the ACTUAL design-system" is gone
      from the typography check (read the function; the report lists the lines).

No network, no credentials. Stdlib + pytest/tmp_path only.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402


def _indep(reviewer="qc-specialist-presentations", builder="slide-copywriter"):
    return {"graded_by": reviewer, "independent": True,
            "builder": builder, "self_graded": False}


def _copy_run(tmp_path, copy_map, report_slides):
    """A run dir with slides.json carrying copy_map {slide: [copy[]]} and a
    shape-valid passing copy-QC report."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    slides = [{"slide": s, "scene": "x", "copy": c} for s, c in sorted(copy_map.items())]
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    report = {
        "gate": "Phase 1Q",
        "average": 9.1,
        "triggered_autofails": [],
        "pass": True,
        "qc_independence": _indep(),
        "per_slide_scores": [
            {"slide": s, "average": 9.0, "pass": True, "notes": "clean"}
            for s in report_slides
        ],
    }
    path = rd / "working" / "qc" / "copy_qc_report.json"
    path.write_text(json.dumps(report))
    return path


def test_a1_slide_with_no_copy_fails_naming_the_slide(tmp_path):
    """Slide 2's copy is empty over a passing report -> AF-COPY-QC names slide 02."""
    path = _copy_run(
        tmp_path,
        {
            1: ["Northwind Co", "Converting beat one into repeatable revenue"],
            2: [],
        },
        report_slides=[1, 2],
    )
    reason = bd._chk_copy_qc(path)
    assert reason, "a passing report over a slide with no copy must FAIL"
    assert "AF-COPY-QC" in reason, reason
    assert "slide 02 has no copy" in reason, reason


def test_a1_blank_copy_fields_fail_naming_the_slide(tmp_path):
    """A slide whose copy fields are all empty strings is equally 'no copy'."""
    path = _copy_run(
        tmp_path,
        {
            1: ["Northwind Co", "Converting beat one into repeatable revenue"],
            2: ["", "", ""],
        },
        report_slides=[1, 2],
    )
    reason = bd._chk_copy_qc(path)
    assert reason, "a passing report over blank copy must FAIL"
    assert "slide 02 has no copy" in reason, reason


def test_a1_typography_check_says_what_it_measures():
    """The overclaim is gone; the docstring and failure text say the declared values."""
    src = inspect.getsource(bd.check_typography_qc_teeth)
    flat = " ".join(src.split())  # the phrase wraps across source lines
    assert "RE-MEASURES the ACTUAL design-system" not in flat, (
        "the typography teeth must not claim to re-measure the actual design system")
    assert "the type sizes and contrast the design file DECLARES" in flat, src
