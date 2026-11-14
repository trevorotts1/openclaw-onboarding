"""PD-067 -- the per-slide quality merge fails closed.

Finding PD-067 (Severe, reproduced): `_validate_qc_slide` accepted a slide
verdict under any of nine keys while `_reduce_qc_union` only ever read `pass`.
A slide the grader failed under another key name therefore merged into a
report stamped `pass: true`, and the same merge stamped
`qc_independence: {..., independent: True}` by code.

The four probe cases from the finding, run here against the real functions:

  1. slide 2 says ``"verdict": "FAIL"``      -> invalid unit (was merged pass)
  2. slide 2 says ``"passed": false``        -> invalid unit (was merged pass)
  3. slide 2 says ``"pass": 0``, no score    -> invalid unit (was merged pass)
  4. CONTROL, slide 2 says ``"pass": false`` -> valid unit, merges to
     ``pass: false``

Case 4 is the positive control: a validator that refused everything would
satisfy 1-3 and is not a fix. No paid call, no network, no manifest load.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402


def _qc(n: int, total: int = 2) -> dict:
    return {"scope": "slide", "ordinal": n, "slide_id": f"slide-{n:02d}",
            "unit_count": total, "phase_id": "P-PROMPT-QC",
            "reviewer_role": "qc-specialist-x"}


def _passing_slide_1() -> str:
    return json.dumps({"slide": 1, "slide_id": "slide-01",
                       "pass": True, "score": 9.0})


def _slide_2(payload: dict) -> str:
    doc = {"slide": 2, "slide_id": "slide-02"}
    doc.update(payload)
    return json.dumps(doc)


# The three failing shapes the finding proved merged to `pass: true`.
FAILING_SHAPES = [
    {"verdict": "FAIL"},      # probe 1
    {"passed": False},        # probe 2
    {"pass": 0},              # probe 3 -- a number is not a boolean
]


def test_probe_failing_shapes_are_invalid_units():
    for shape in FAILING_SHAPES:
        ok, reasons = D._validate_qc_slide(_qc(2), _slide_2(shape))
        assert not ok, f"shape {shape!r} was accepted as a valid unit"
        assert reasons and "pass" in reasons[0], \
            f"shape {shape!r} refused without naming the `pass` key: {reasons!r}"


def test_probe_failing_shapes_refuse_the_merge():
    for shape in FAILING_SHAPES:
        rows = [(_qc(1), _passing_slide_1()), (_qc(2), _slide_2(shape))]
        assert D._reduce_qc_union(rows) is None, \
            f"shape {shape!r} merged instead of being refused"


def test_probe_control_still_merges_to_pass_false():
    # The control: a row that honestly says pass:false is a VALID unit and the
    # union still forms -- and it forms with pass false, not true.
    control = _slide_2({"pass": False})
    ok, reasons = D._validate_qc_slide(_qc(2), control)
    assert ok, f"the pass:false control was refused: {reasons!r}"
    rows = [(_qc(1), _passing_slide_1()), (_qc(2), control)]
    out = D._reduce_qc_union(rows)
    assert out is not None, "the pass:false control refused the merge"
    rep = json.loads(out)
    assert rep["pass"] is False
    assert len(rep["slides"]) == 2  # both rows preserved, nothing dropped


def test_merge_does_not_stamp_independence():
    rows = [(_qc(1), _passing_slide_1()),
            (_qc(2), _slide_2({"pass": True, "score": 9.0}))]
    rep = json.loads(D._reduce_qc_union(rows))
    assert rep["pass"] is True
    # PD-067: `graded_by` only. The merge never claims independence it has not
    # proven; the report gate compares author_model against graded_by_model.
    assert rep["qc_independence"] == {"graded_by": "qc-specialist-x"}
    assert "independent" not in rep["qc_independence"]
