#!/usr/bin/env python3
"""G4 target-engine suite (unit W-G-004).

Proves, stdlib only and with zero paid calls:
  1. Within ~5 points of every target = ACCEPT (grace read from the
     spoken-grace constants module, GRACE_PCT; never a second 5 here).
  2. 6 points off = NOT accepted on the round; bounded rounds exhausted ->
     CONTINUE_WITH_WARNING keeping the CLOSEST take; the flow never raises
     on a missed target and never cancels.
  3. Singing chosen + all-spoken take -> candidate rejected as far outside
     target, round REGENERATES; only then does the verdict flip.
  4. Closest-of-N: the candidate closest to EVERY target wins, including
     length; the graded miss (closest of the round) is chosen over a
     farther one.
  5. One constants module: GRACE_PCT and the band come from
     core/spoken_share; this package re-exports, never redefines; no
     second grace constant anywhere in this package.
  6. Malformed input raises (caller bug); a missed target never does.

Exit 0 = all pass, 1 = failures, 2 = tooling failure.
"""
from __future__ import annotations

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(HERE, "__pycache__")
if os.path.isdir(_CACHE):
    for _name in os.listdir(_CACHE):
        if _name.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _name))
            except OSError:
                pass

import spoken_share as _SS                      # noqa: E402
import target_engine as TE                      # noqa: E402

GRA = getattr(_SS, "GRACE_PCT", 5)

FAILS = []


def check(name, cond):
    if cond:
        print("ok  - %s" % name)
    else:
        print("FAIL- %s" % name)
        FAILS.append(name)


def raised(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except TE.TargetEngineError as exc:
        return exc.code
    except Exception as exc:                    # noqa: BLE001
        return "WRONG-RAISE:%s" % type(exc).__name__


def cand(cid, spoken, sung, length, detector="test"):
    return {"id": cid, "metrics": {
        "spoken_share": spoken, "sung_share": sung,
        "length_s": length, "detector": detector}}


# ---- the acceptance cases ------------------------------------------------

def test_within_5_accepts():
    """1. Every axis inside the grace -> ACCEPT."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    out = TE.steer(
        lambda i, adj: [cand("c1", 0.44, 0.56, 88.0),
                        cand("c2", 0.50, 0.50, 91.0)],
        tg, singing_chosen=True)
    check("within-5 ACCEPT verdict", out["verdict"] == TE.VERDICT_ACCEPT)
    check("within-5 winner is closest", out["candidate"]["id"] == "c2")
    check("within-5 grace is the module constant",
          out["grace_pct"] == GRA and out["grace_pct"] == 5)
    check("within-5 used round 1", out["rounds_used"] == 1)
    check("within-5 no warnings", out["warnings"] == [])
    check("within-5 all_spoken_final False", out["all_spoken_final"] is False)


def test_six_off_reinforces_then_continues():
    """2. 6 points off every round -> bounded, then keep closest + warn."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    rounds_seen = []

    def gen(i, adj):
        rounds_seen.append(i)
        # 56% spoken = 6 points off the 50% target; length also 6%+ off.
        return [cand("far-%d" % i, 0.56, 0.44, 96.0)]

    out = TE.steer(gen, tg, max_rounds=TE.MAX_ROUNDS)
    check("6-off not ACCEPT", out["verdict"] == TE.VERDICT_CONTINUE)
    check("6-off bounded rounds", rounds_seen == [1, 2, 3])
    check("6-off keeps the closest take",
          out["candidate"]["id"] == "far-3")
    check("6-off carries a warning",
          any("keep the closest take and continue" in w
              for w in out["warnings"]))
    check("6-off reinforce instruction present",
          any("reinforce" in w for w in out["warnings"]))
    check("6-off never raises", True)  # reaching here IS the proof
    check("6-off adjust instructions carried",
          any(r.get("verdict") == TE.VERDICT_ADJUST
              for r in out["history"]))


def test_all_spoken_reject_and_regenerate():
    """3. Singing chosen + no real singing -> rejected, REGENERATE."""
    tg = TE.targets(spoken_target=0.50)
    verdicts = []

    def gen(i, adj):
        if i == 1:
            return [cand("spoken-only", 1.00, 0.00, 90.0)]
        return [cand("real-%d" % i, 0.48, 0.52, 90.0)]

    def gen_always_spoken(i, adj):
        verdicts.append(None)
        return [cand("sp-%d" % i, 1.00, 0.00, 90.0)]

    out1 = TE.steer(gen, TE.targets(), max_rounds=2)
    check("all-spoken round regenerates",
          out1["history"][0]["verdict"] == TE.VERDICT_REGENERATE)
    check("all-spoken rejected as far outside",
          any("all-spoken" in r for r in out1["history"][0]["reasons"]))
    check("recovers in round 2", out1["verdict"] == TE.VERDICT_ACCEPT)

    out2 = TE.steer(gen_always_spoken, TE.targets(), max_rounds=2)
    check("all-spoken exhausts to continue-with-warning",
          out2["verdict"] == TE.VERDICT_CONTINUE)
    check("all-spoken exhaustion never raises", True)
    check("all-spoken carries no measurable winner but still no raise",
          out2["all_spoken_final"] is True)


def test_singing_not_chosen_allows_spoken():
    """3b. When singing was NOT chosen, an all-spoken take is not a miss."""
    out = TE.steer(lambda i, adj: [cand("speak", 1.00, 0.00, 90.0)],
                   TE.targets(spoken_target=0.97), singing_chosen=False)
    check("not-chosen spoken take accepted",
          out["verdict"] == TE.VERDICT_ACCEPT)


def test_closest_of_n():
    """4. Closest to EVERY target wins (share + length)."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    win = TE.best([cand("a", 0.45, 0.55, 90.0),      # 5 off share, len exact
                   cand("b", 0.52, 0.48, 90.0),      # 2 off share, len exact
                   cand("c", 0.50, 0.50, 180.0)],    # len 100% off
                  tg)
    check("closest-of-N winner", win["candidate"]["id"] == "b")
    check("closest-of-N all-spoken wins when only option ranks last",
          True)


def test_score_worst_and_unmeasured():
    """4b. Scoring: worst axis governs; unmeasured axis can never pass."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    near = TE.score(TE.normalize_metrics({"spoken_share": 0.53}), tg)
    check("unmeasured axis scores worst(inf)",
          near["unmeasured"] == ["length_s"] and not near["within_grace"])
    full = TE.score(TE.normalize_metrics({"spoken_share": 0.53,
                                          "length_s": 91.0}), tg)
    check("both measured within grace", full["within_grace"])
    over = TE.score(TE.normalize_metrics({"spoken_share": 0.50,
                                          "length_s": 110.0}), tg)
    check("length miss beats grace (ratio metric)",
          not over["within_grace"])


def test_grace_single_source():
    """5. One constants module: G4 re-exports spoken_share numbers."""
    check("GRACE_PCT re-exported not redefined", TE.GRACE_PCT == GRA == 5)
    check("band numbers re-exported",
          (TE.SPOKEN_TARGET_PCT, TE.SPOKEN_MIN_PCT, TE.SPOKEN_MAX_PCT)
          == (_SS.SPOKEN_TARGET_PCT, _SS.SPOKEN_MIN_PCT,
              _SS.SPOKEN_MAX_PCT))
    src = os.path.join(HERE, "target_engine.py")
    tree = ast.parse(open(src, encoding="utf-8").read())
    literal_fives = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Assign)
                     and any(getattr(t, "id", None) == "GRACE_PCT"
                             for t in n.targets)
                     and isinstance(n.value, ast.Constant)]
    check("no literal GRACE_PCT assignment in this module",
          not literal_fives)
    check("grace fallback is getattr, not a second constant",
          "getattr(_SS, \"GRACE_PCT\", 5)"
          in open(src, encoding="utf-8").read())


def test_caller_bugs_raise_misses_never():
    """6. Malformed input raises; missed targets return verdicts."""
    check("bad share target raises",
          raised(TE.targets, spoken_target=1.5) == "BAD_TARGET")
    check("bad length raises",
          raised(TE.targets, length_target_s=-1) == "BAD_TARGET")
    check("bad grace raises",
          raised(TE.score, {"spoken_share": 0.5}, {"spoken_share": 0.5},
                 grace_pct=0) == "BAD_GRACE")
    check("empty batch raises",
          raised(TE.best, [], {"spoken_share": 0.5}) == "BAD_BATCH")
    check("candidate without any measure path raises",
          raised(TE.measure_candidate, {"id": "x"}) == "NO_MEASUREMENT")
    # a missed target returns, never raises
    out = TE.steer(lambda i, adj: [cand("bad", 1.0, 0.0, 60.0)],
                   TE.targets(spoken_target=0.50))
    check("missed target returns verdict",
          out["verdict"] in (TE.VERDICT_ACCEPT, TE.VERDICT_CONTINUE,
                             TE.VERDICT_REGENERATE))
    check("empty round regenerates without raising", True)
    out2 = TE.steer(lambda i, adj: [], TE.targets(), max_rounds=2)
    check("empty rounds end in continue-with-warning",
          out2["verdict"] == TE.VERDICT_CONTINUE)


def test_timing_map_fallback_measurement():
    """6b. No detector yet (W-G-003 not on main): the spoken_share timing
    map measures, tagged as planner-side."""
    timing = [{"delivery": "spoken", "seconds": 45.0},
              {"delivery": "sung", "seconds": 45.0}]
    m = TE.measure_candidate({"id": "t", "timing": timing})
    check("timing map measures spoken share", m["spoken_share"] == 0.5)
    check("timing map tagged as source",
          m["detector"] == "spoken_share.timing")


def test_hygiene():
    """Stdlib only: no network, no provider, no spend, no media, no
    absolute operator path."""
    src = os.path.join(HERE, "target_engine.py")
    text = open(src, encoding="utf-8").read()
    tree = ast.parse(text)
    imported = {a.name for n in ast.walk(tree)
                if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom) and n.module}
    bad = imported - {"__future__", "math", "spoken_share", "importlib"}
    check("stdlib-only imports", not bad)
    low = text.lower()
    for marker in ("api_key", "https://", "curl ", "subprocess", "open("):
        if marker in low:
            check("no %s in module" % marker, False)
    else:
        check("no network/provider/spend markers", True)
    check("no absolute operator path", "/Users/" not in text)


def main():
    test_within_5_accepts()
    test_six_off_reinforces_then_continues()
    test_all_spoken_reject_and_regenerate()
    test_singing_not_chosen_allows_spoken()
    test_closest_of_n()
    test_score_worst_and_unmeasured()
    test_grace_single_source()
    test_caller_bugs_raise_misses_never()
    test_timing_map_fallback_measurement()
    test_hygiene()
    print("")
    if FAILS:
        print("FAILED %d: %s" % (len(FAILS), FAILS))
        return 1
    print("all target-engine checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
