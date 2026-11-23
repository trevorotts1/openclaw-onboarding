#!/usr/bin/env python3
"""F12 motion-gate waiver tests (NEVER-AGAIN lock 4: gate change via repo fix).

The waiver is a Trevor-signed receipt read by ONE reader
(shot_planner.motion_score.motion_gate_waiver) and honoured by the gate
(gate_clips) only for the shot ids it names. Everything else keeps the full
floor: an unsigned record, a missing file, a half-written file, an unnamed
shot, an unmeasurable row, or a caller-supplied stricter verdict.

Run: python3 core/shot_planner/test_motion_waiver_f12.py
     python3 -m pytest -q core/shot_planner/test_motion_waiver_f12.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from shot_planner.motion_score import (           # noqa: E402
    CLIP_LOW_MOTION, CLIP_MOTION_UNMEASURABLE, MOTION_STRUCTURE_MIN,
    MOTION_SUBJECT_LOW, TOOL_VERSION, gate_clips, motion_gate_waiver,
)

#: Spatial row that FAILS on measured subject motion (below 0.012) with a
#: strong structure score, so the finding is low motion, not weak structure.
LOW_ROW = {"motion_score": {"score": 0.001, "evidence": "spatial",
                            "subject_motion_score": 0.001,
                            "motion_structure": 20.0}}
#: Spatial row that PASSES on both magnitude and structure.
MOVE_ROW = {"motion_score": {"score": 0.030, "evidence": "spatial",
                             "subject_motion_score": 0.030,
                             "motion_structure": 20.0}}
#: Every sampled pair degenerate: no measurement exists, so nothing to waive.
UNMEAS_ROW = {"motion_score": {"score": 0.0, "evidence": "spatial",
                               "subject_motion_score": 0.0,
                               "motion_structure": 0.0,
                               "unmeasurable": True}}

#: The row motion_score() actually EMITS for a measured low-motion clip:
#: spatial evidence, subject_motion_score below MOTION_SUBJECT_LOW,
#: structure above the floor, and flagged=True (its own echo of that same
#: measurement). This is what a real run stores, so it must be waivable.
SCORED_LOW_ROW = {"motion_score": {"score": 0.002, "flagged": True,
                                   "threshold": MOTION_SUBJECT_LOW,
                                   "structure_threshold": MOTION_STRUCTURE_MIN,
                                   "evidence": "spatial",
                                   "tool_version": TOOL_VERSION,
                                   "subject_motion_score": 0.002,
                                   "motion_structure": 7.8}}

SIGNED = {"signed_by": "Trevor", "signature": "sig-abc",
          "who": "Trevor", "at": "2026-11-21T10:00:00-05:00",
          "shots": ["s-low"]}


def _run_dir(record):
    """A run dir holding control/motion-gate-waiver.json (or no file)."""
    root = tempfile.mkdtemp(prefix="motion-waiver-")
    os.makedirs(os.path.join(root, "control"))
    if record is not None:
        with open(os.path.join(root, "control", "motion-gate-waiver.json"),
                  "w", encoding="utf-8") as fh:
            if isinstance(record, str):
                fh.write(record)
            else:
                json.dump(record, fh)
    return root


def test_signed_waiver_lets_named_low_shot_pass():
    run = _run_dir(SIGNED)
    w = motion_gate_waiver(run)
    assert w == {"who": "Trevor", "at": SIGNED["at"], "shots": ["s-low"]}, w
    res = gate_clips([{"shot_id": "s-low", **LOW_ROW}], waiver=w)
    assert res["outcome"] == "ok", res
    assert res["flagged"] == [], res
    assert res["waived"] == ["s-low"], res
    assert res["waiver"] == {"who": "Trevor", "at": SIGNED["at"]}, res
    assert res["reason_code"] == "CLIPS_MOTION_WAIVED", res


def test_unsigned_waiver_is_ignored():
    run = _run_dir(dict(SIGNED, signed_by="owner"))
    assert motion_gate_waiver(run) is None
    res = gate_clips([{"shot_id": "s-low", **LOW_ROW}],
                     waiver=motion_gate_waiver(run))
    assert res["outcome"] == "rejected", res
    assert res["flagged"] == ["s-low"] and res["waived"] == [], res
    assert res["reason_code"] == CLIP_LOW_MOTION, res


def test_missing_file_fails_closed():
    run = _run_dir(None)
    assert motion_gate_waiver(run) is None
    # Half-written JSON and a record with no shots list read as no waiver.
    assert motion_gate_waiver(_run_dir('{"signed_by": "Trevor"')) is None
    assert motion_gate_waiver(_run_dir(dict(SIGNED, shots=[]))) is None
    assert motion_gate_waiver(_run_dir(dict(SIGNED, who="  "))) is None
    # A whitespace-only signature is no signature (QC finding, fail closed).
    assert motion_gate_waiver(_run_dir(dict(SIGNED, signature="   "))) is None
    assert motion_gate_waiver(None) is None
    res = gate_clips([{"shot_id": "s-low", **LOW_ROW}], waiver=None)
    assert res["outcome"] == "rejected" and res["flagged"] == ["s-low"], res


def test_unnamed_low_motion_shot_still_flagged():
    w = motion_gate_waiver(_run_dir(SIGNED))
    res = gate_clips([{"shot_id": "s-low", **LOW_ROW},
                      {"shot_id": "s-other", **LOW_ROW}], waiver=w)
    assert res["outcome"] == "rejected", res
    assert res["flagged"] == ["s-other"], res
    assert res["waived"] == ["s-low"], res


def test_unmeasurable_never_waived():
    w = motion_gate_waiver(_run_dir(SIGNED))
    res = gate_clips([{"shot_id": "s-low", **UNMEAS_ROW}], waiver=w)
    assert res["outcome"] == "rejected", res
    assert res["flagged"] == ["s-low"], res
    assert res["waived"] == [], res
    assert res["reason_code"] == CLIP_MOTION_UNMEASURABLE, res


def test_scored_low_shot_flagged_by_scorer_is_waived():
    # BUG (measured on a real run): motion_score() stamps flagged=True on every
    # low clip, so the old guard refused to waive EVERY real low shot. The
    # flag here is the scorer's own echo of the failing measurement, not a
    # stricter caller verdict -- a signed waiver naming the shot applies.
    w = motion_gate_waiver(_run_dir(SIGNED))
    res = gate_clips([{"shot_id": "s-low", **SCORED_LOW_ROW}], waiver=w)
    assert res["outcome"] == "ok", res
    assert res["flagged"] == [], res
    assert res["waived"] == ["s-low"], res
    assert res["reason_code"] == "CLIPS_MOTION_WAIVED", res

def test_caller_flagged_verdict_not_loosened_by_waiver():
    w = motion_gate_waiver(_run_dir(SIGNED))
    row = {"shot_id": "s-low",
           "motion_score": dict(MOVE_ROW["motion_score"], flagged=True)}
    res = gate_clips([row], waiver=w)
    assert res["outcome"] == "rejected" and res["flagged"] == ["s-low"], res
    assert res["waived"] == [], res


def main():
    fns = (test_signed_waiver_lets_named_low_shot_pass,
           test_unsigned_waiver_is_ignored,
           test_missing_file_fails_closed,
           test_unnamed_low_motion_shot_still_flagged,
           test_unmeasurable_never_waived,
           test_scored_low_shot_flagged_by_scorer_is_waived,
           test_caller_flagged_verdict_not_loosened_by_waiver)
    failed = 0
    for fn in fns:
        try:
            fn()
            print("ok:", fn.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL:", fn.__name__, exc)
    print("\n%d of %d failed" % (failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
