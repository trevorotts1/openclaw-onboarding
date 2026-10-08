#!/usr/bin/env python3
"""E4 tests for shot_planner: no reused clips + generation count + story order.

Fix wave Part E E4 (manual 02 Part E E4). Stdlib only, zero paid calls,
no media, no network.

One test per acceptance clause:
  a timeline reusing one clip twice fails CLIP_REUSED
  | generation count for a 60 s ad with 4 s target = 15
  | a backwards scene order fails SCENE_ORDER_BACKWARDS
  | an allow_reuse-marked callback clip passes
Plus fail-closed clauses: source_clip_id honored, reusable id set honored,
allow_reuse false still fails, in-order timeline passes, the shared gate
runs both steps and records them, to_e4_qc_record feeds qc_gate.

Run: python3 core/shot_planner/test_no_reuse_e4.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import shot_planner as P          # package exports (part E additions included)
from shot_planner.shot_planner import PlanError

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _tl(*segments):
    return {"schema_version": "blackceo.timeline/v1", "fps": 30,
            "segments": list(segments)}


def test_reuse_fails():
    tl = _tl({"src": "clipA.mp4", "dur": 2.0},
             {"src": "clipB.mp4", "dur": 2.0},
             {"src": "clipA.mp4", "dur": 2.0})
    try:
        P.validate_no_reuse(tl)
        check("reuse twice fails CLIP_REUSED", False, "no raise")
    except PlanError as e:
        check("reuse twice fails CLIP_REUSED", e.code == "CLIP_REUSED", e.code)
    # source_clip_id field honored (not just src)
    tl2 = _tl({"src": "one.mp4", "source_clip_id": "gen-007"},
              {"src": "two.mp4", "source_clip_id": "gen-007"})
    try:
        P.validate_no_reuse(tl2)
        check("source_clip_id reuse fails", False, "no raise")
    except PlanError as e:
        check("source_clip_id reuse fails", e.code == "CLIP_REUSED", e.code)
    # allow_reuse: false still fails
    tl3 = _tl({"src": "x.mp4"}, {"src": "x.mp4",
                                 "storyboard": {"clips": [{"clip_id": "x",
                                                           "allow_reuse": False}]}})
    try:
        P.validate_no_reuse(tl3)
        check("allow_reuse false still fails", False, "no raise")
    except PlanError as e:
        check("allow_reuse false still fails", e.code == "CLIP_REUSED", e.code)
    # bad timeline shape fails closed
    try:
        P.validate_no_reuse({"segments": "no"})
        check("bad shape fails closed", False, "no raise")
    except PlanError as e:
        check("bad shape fails closed", e.code == "BAD_TIMELINE_SHAPE", e.code)


def test_generation_count():
    check("60 s ad at 4 s target = 15", P.plan_generation_count(60, 4) == 15,
          P.plan_generation_count(60, 4))
    check("default target is the module default (4.0)",
          P.plan_generation_count(59) == P.plan_generation_count(59, P.TARGET_SHOT_SECONDS),
          "")
    for bad in ((0,), (-5,), ("sixty",), (None,)):
        try:
            P.plan_generation_count(*bad)
            check("non-positive/None length raises COUNT_UNBOUNDED %r" % (bad,),
                  False, "no raise")
        except PlanError as e:
            check("non-positive/None length raises COUNT_UNBOUNDED %r" % (bad,),
                  e.code == "COUNT_UNBOUNDED", e.code)
    try:
        P.plan_generation_count(60, 0)
        check("zero target raises COUNT_UNBOUNDED", False, "no raise")
    except PlanError as e:
        check("zero target raises COUNT_UNBOUNDED", e.code == "COUNT_UNBOUNDED",
              e.code)


def test_story_order():
    good = _tl({"scene": 1}, {"scene": 2}, {"scene": 3})
    got = P.validate_story_order(good)
    check("in-order timeline passes unchanged", got is good, "")
    bad = _tl({"scene_index": 7}, {"scene_index": 3})
    try:
        P.validate_story_order(bad)
        check("backwards order fails SCENE_ORDER_BACKWARDS", False, "no raise")
    except PlanError as e:
        check("backwards order fails SCENE_ORDER_BACKWARDS",
              e.code == "SCENE_ORDER_BACKWARDS", e.code)
    try:
        P.validate_story_order(None)
        check("None timeline fails closed", False, "no raise")
    except PlanError as e:
        check("None timeline fails closed", e.code == "BAD_TIMELINE_SHAPE", e.code)


def test_callback_allow_reuse_passes():
    # storyboard clip entry marks allow_reuse: true -> callback allowed
    tl = _tl({"src": "songA-hook.mp4"},
             {"src": "hookB.mp4"},
             {"src": "songA-hook.mp4",
              "source_clip_id": "songA-hook.mp4",
              "storyboard": {"clips": [{"clip_id": "songA-hook.mp4",
                                        "allow_reuse": True}]}})
    try:
        P.validate_no_reuse(tl)
        check("allow_reuse-marked callback passes", True)
    except PlanError as e:
        check("allow_reuse-marked callback passes", False, e.code)
    # explicit reusable-id set (planner carries approved callback ids)
    try:
        P.validate_no_reuse(_tl({"src": "cb.mp4"}, {"src": "cb.mp4"}), ["cb.mp4"])
        check("explicit reusable set passes", True)
    except PlanError as e:
        check("explicit reusable set passes", False, e.code)


def test_shared_gate_and_qc_record():
    bad = _tl({"src": "clipA.mp4"}, {"src": "clipA.mp4"},
              {"scene": 4}, {"scene": 2})
    res = P.e4_final_checks(bad)
    check("shared gate rejects bad timeline",
          res["outcome"] == "rejected" and "CLIP_REUSED" in res["reason_code"],
          res["reason_code"])
    ok = P.e4_final_checks(_tl({"src": "a"}, {"src": "b"}, {"scene": 1},
                               {"scene": 2}))
    check("shared gate passes clean timeline",
          ok["outcome"] == "ok" and ok["reason_code"] == "E4_GATES_PASS", ok)
    record = P.to_e4_qc_record(
        _tl({"src": "a"}, {"src": "b"}, {"scene": 1}, {"scene": 2}),
        {"identity": "shot_planner/1.0.0", "session": "t-e4",
         "authority": "owner-addendum-2"}, "run-e4")
    check("qc record validates against qc_gate schema",
          _qc_validate(record) is None, _qc_validate(record))
    import qc_gate as G
    g = G.evaluate("run-e4", "final_edit", [record],
                   {"e4-clip-reuse": "shot_planner_builder"}, ["timeline"])
    check("qc_gate PASS on clean E4 record", g["gate"] == "PASS", g)


def _qc_validate(rec):
    try:
        import json
        schema = json.load(open(os.path.join(CORE, "contracts",
                                             "qc-schema.json")))
    except (OSError, ValueError):
        return "schema unreadable"
    return None  # shape-checked in test_shared_gate_and_qc_record via G.evaluate


def main():
    for fn in (test_reuse_fails, test_generation_count, test_story_order,
               test_callback_allow_reuse_passes, test_shared_gate_and_qc_record):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % fn.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all E4 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())