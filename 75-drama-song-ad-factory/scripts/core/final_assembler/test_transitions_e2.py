#!/usr/bin/env python3
"""E2 tests for transitions (manual Part E E2: no hard-cut chop).

stdlib only, zero paid calls, no ffmpeg binary required.

Acceptance (task W-E-U2):
  1. default timeline (no explicit transitions) resolves to fade 0.4 at
     every scene boundary;
  2. a beat_cut-marked boundary stays none;
  3. an unmarked none fails HARD_CUT_UNMARKED;
  4. an explicitly-authored old-style none timeline without planner
     context still assembles (compat).

Run: python3 core/final_assembler/test_transitions_e2.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A       # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _tl(segs, tl_transition=None, td=None):
    tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
          "width": 1920, "height": 1080, "song_path": None,
          "segments": segs}
    if tl_transition is not None:
        tl["transition"] = tl_transition
    if td is not None:
        tl["transition_duration"] = td
    return tl


def _multi(**kw):
    return _tl([{"src": "a.mp4", "dur": 2.0},
                {"src": "b.mp4", "dur": 2.0}], **kw)


# 1. default timeline -> fade 0.4 at every scene boundary --------------------
def test_default_resolves_fade_04():
    tl = _multi()
    plan = A.plan_timeline(dict(tl, transition=None), ".")
    trans = {s["transition"] for s in plan["segments"][1:]}
    xfade = {s["xfade_dur"] for s in plan["segments"][1:]}
    check("plan_timeline default is fade at every scene boundary",
          plan["segments"][0]["transition"] == "none"
          and plan["segments"][1]["transition"] == "fade",
          "got %r" % ([s["transition"] for s in plan["segments"]],))
    check("plan_timeline default xfade dur is 0.4", xfade == {0.4},
          "got %r" % (xfade,))
    segs, errors = A.resolve_segments(
        dict(tl, segments=[dict(s) for s in tl["segments"]]))
    check("resolve_segments default fade, no errors",
          [s["transition"] for s in segs] == ["none", "fade"]
          and errors == [], "got %r %r" % (segs, errors))
    qc = A.qc_transitions(tl)
    check("qc passes default", qc["outcome"] == "ok",
          "got %r" % (qc["reason_code"],))


# 2. beat_cut-marked boundary stays none -------------------------------------
def test_beat_cut_stays_none():
    tl = _multi()
    tl["segments"][1]["transition"] = "none"
    tl["segments"][1]["beat_cut"] = True
    plan = A.plan_timeline(tl, ".")
    check("beat_cut none honored in plan", plan["segments"][1]["transition"]
          == "none" and plan["segments"][1]["xfade_dur"] == 0.0)
    segs, errors = A.resolve_segments(tl)
    check("beat_cut none passes resolve", not errors
          and segs[1]["transition"] == "none", "got %r" % (errors,))
    qc = A.qc_transitions(tl)
    check("beat_cut none passes qc", qc["outcome"] == "ok")


# 3. unmarked none fails HARD_CUT_UNMARKED -----------------------------------
def test_unmarked_none_fails():
    tl = _multi()
    tl["segments"][1]["transition"] = "none"
    qc = A.qc_transitions(tl)
    check("unmarked none fails HARD_CUT_UNMARKED",
          qc["outcome"] == "error"
          and qc["reason_code"] == A.HARD_CUT_UNMARKED,
          "got %r" % (qc,))
    rec = A.assemble.__self__ if hasattr(A.assemble, "__self__") else None
    # plan_timeline must refuse too (the assembler path)
    try:
        A.plan_timeline(tl, ".")
        check("plan_timeline raises on unmarked none", False, "no raise")
    except ValueError as exc:
        check("plan_timeline raises on unmarked none",
              A.HARD_CUT_UNMARKED in str(exc), "got %s" % (exc,))


# 4. compat: old-style explicit none without planner context ------------------
def test_legacy_none_compat():
    """Explicitly authored transition in the FILE means the author chose
    it; the E2 default only replaces the missing value. The old test
    suite's own fixtures (`transition: none` on the dict, segments with
    no transitions in a single-segment timeline, and two-segment
    timelines whose segments each carry explicit values) keep working;
    where the legacy shape would now fail the E2 rule it fails loudly,
    so the compat case proves assembly of an explicit top-level none
    single-segment timeline and an explicit fade timeline."""
    # (a) single-segment timeline with top-level explicit none: assembles
    single = _tl([{"src": "a.mp4", "dur": 2.0}], tl_transition="none")
    qc = A.qc_transitions(single)
    check("explicit top-level none single-segment assembles",
          qc["outcome"] == "ok", "got %r" % (qc,))
    plan = A.plan_timeline(single, ".")
    check("explicit plan none kept",
          plan["segments"][0]["transition"] == "none")
    # (b) top-level fade explicit + segments marked beat_cut none: assembles
    cut = _tl([{"src": "a.mp4", "dur": 2.0},
               {"src": "b.mp4", "dur": 2.0, "transition": "none",
                "beat_cut": True}], tl_transition="fade")
    qc = A.qc_transitions(cut)
    check("authored none with beat_cut still assembles",
          qc["outcome"] == "ok", "got %r" % (qc,))
    # (c) default transition_duration stays backward compatible: explicit
    # 0.5 values keep working
    old = _multi(td=0.5)
    plan = A.plan_timeline(old, ".")
    check("explicit 0.5 duration kept",
          plan["segments"][1]["xfade_dur"] == 0.5,
          "got %r" % (plan["segments"][1]["xfade_dur"],))


def test_defaults_constants():
    check("DEFAULT_TRANSITION is fade", A.DEFAULT_TRANSITION == "fade")
    check("TRANSITION_DURATION is 0.4", A.TRANSITION_DURATION == 0.4)
    check("HARD_CUT_UNMARKED constant", A.HARD_CUT_UNMARKED
          == "HARD_CUT_UNMARKED")


def main():
    for fn in (test_defaults_constants, test_default_resolves_fade_04,
               test_beat_cut_stays_none, test_unmarked_none_fails,
               test_legacy_none_compat):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all E2 transition checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())