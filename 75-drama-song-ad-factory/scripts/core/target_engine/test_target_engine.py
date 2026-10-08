#!/usr/bin/env python3
"""G4 target-engine suite (unit W-G-004, band fix + call-path wire G4-WIRE).

Proves, stdlib only and with zero paid calls:
  1. Trevor's 5/10 band (G11, order 1240): <= 5 points off = ACCEPT;
     past 5 up to 10 = ACCEPT_WITH_FLAG with the flag in the receipt;
     past 10 after the bounded rounds = REDO (never keep-the-closest).
  2. The band numbers come from core/spoken_share -- one constants module,
     no second 5/10 anywhere in this package.
  3. Singing chosen + all-spoken take -> candidate rejected as far outside
     target, round REGENERATES; exhaustion hands back REDO with the
     measurements, never a raise.
  4. Closest-of-N: the candidate closest to EVERY target wins, including
     length.
  5. Call path: music_director.select_best and retake_manager.plan both
     judge through the engine -- accept / flag / redo within 5/10.
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
    """1a. Every axis inside 5 points -> ACCEPT on round 1."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    out = TE.steer(
        lambda i, adj: [cand("c1", 0.44, 0.56, 88.0),
                        cand("c2", 0.50, 0.50, 91.0)],
        tg, singing_chosen=True)
    check("within-5 ACCEPT verdict", out["verdict"] == TE.VERDICT_ACCEPT)
    check("within-5 band is ACCEPT", out["band"] == TE.BAND_ACCEPT)
    check("within-5 winner is closest", out["candidate"]["id"] == "c2")
    check("within-5 grace is the module constant",
          out["grace_pct"] == GRA and out["grace_pct"] == 5)
    check("within-5 used round 1", out["rounds_used"] == 1)
    check("within-5 no warnings", out["warnings"] == [])
    check("within-5 no flags", out["flags"] == [])
    check("within-5 all_spoken_final False", out["all_spoken_final"] is False)


def test_five_point_boundary_accepts():
    """1b. Exactly 5 points off is still the accept band (<= 5)."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    out = TE.steer(lambda i, adj: [cand("edge", 0.55, 0.45, 90.0)],
                   tg, singing_chosen=True)
    check("5.0 points ACCEPT", out["verdict"] == TE.VERDICT_ACCEPT)
    check("5.0 points band ACCEPT", out["band"] == TE.BAND_ACCEPT)
    check("5.0 points no flag", out["flags"] == [])


def test_six_off_flags_and_accepts():
    """1c. 6 points off = past 5 up to 10 -> accept WITH the flag (G11)."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    rounds_seen = []

    def gen(i, adj):
        rounds_seen.append(i)
        # 56% spoken = 6 points off the 50% target; length exact.
        return [cand("far-%d" % i, 0.56, 0.44, 90.0)]

    out = TE.steer(gen, tg, max_rounds=TE.MAX_ROUNDS)
    check("6-off ACCEPT_WITH_FLAG", out["verdict"] == TE.VERDICT_FLAG)
    check("6-off band is FLAG", out["band"] == TE.BAND_FLAG)
    check("6-off stops on round 1", rounds_seen == [1])
    check("6-off receipt carries the flag",
          len(out["flags"]) == 1 and out["flags"][0].startswith("FLAG:"))
    check("6-off flag text names the band",
          "accept with a flag" in out["flags"][0])
    check("6-off keeps the take", out["candidate"]["id"] == "far-1")
    check("6-off never raises", True)  # reaching here IS the proof


def test_ten_point_boundary_flags():
    """1d. Exactly 10 points off is still the flag band (<= 10)."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    out = TE.steer(lambda i, adj: [cand("edge", 0.60, 0.40, 90.0)],
                   tg, singing_chosen=True)
    check("10.0 points is FLAG not REDO",
          out["verdict"] == TE.VERDICT_FLAG and out["band"] == TE.BAND_FLAG)
    check("10.0 points carries flag", len(out["flags"]) == 1)


def test_past_10_redoes_after_rounds():
    """1e. Past 10 points -> adjust each bounded round, then REDO.
    G11 REPLACES the old keep-the-closest-with-a-warning endgame."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    rounds_seen = []

    def gen(i, adj):
        rounds_seen.append(i)
        # 64% spoken = 14 points off (the LeAnne T21 shape); length off too.
        return [cand("far-%d" % i, 0.64, 0.36, 110.0)]

    out = TE.steer(gen, tg, max_rounds=TE.MAX_ROUNDS)
    check("14-off verdict REDO", out["verdict"] == TE.VERDICT_REDO)
    check("14-off band REDO", out["band"] == TE.BAND_REDO)
    check("14-off burned the bounded rounds", rounds_seen == [1, 2, 3])
    check("14-off keeps measurements for the handback",
          out["metrics"] is not None
          and out["candidate"]["id"] == "far-3")
    check("14-off warning says REDO not keep-closest",
          any("REDO (regenerate)" in w for w in out["warnings"])
          and not any("keep the closest take" in w for w in out["warnings"]))
    check("14-off never cancels",
          any("never cancel" in w for w in out["warnings"]))
    check("14-off adjust instructions carried",
          any(r.get("verdict") == TE.VERDICT_ADJUST
              for r in out["history"]))
    check("14-off never raises", True)


def test_all_spoken_reject_and_regenerate():
    """3. Singing chosen + no real singing -> rejected, REGENERATE."""
    verdicts = []

    def gen(i, adj):
        if i == 1:
            return [cand("spoken-only", 1.00, 0.00, 90.0)]
        return [cand("real-%d" % i, 0.22, 0.78, 90.0)]

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
    check("all-spoken exhaustion is REDO (never keep-the-closest)",
          out2["verdict"] == TE.VERDICT_REDO)
    check("all-spoken exhaustion never raises", True)
    check("all-spoken carries the flag-free redo receipt",
          out2["all_spoken_final"] is True and out2["flags"] == [])


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


def test_score_worst_and_unmeasured():
    """4b. Scoring: worst axis governs; unmeasured axis can never pass."""
    tg = TE.targets(spoken_target=0.50, length_target_s=90.0)
    near = TE.score(TE.normalize_metrics({"spoken_share": 0.53}), tg)
    check("unmeasured axis scores worst(inf)",
          near["unmeasured"] == ["length_s"] and not near["within_grace"])
    check("unmeasured axis is the REDO band", near["band"] == TE.BAND_REDO)
    full = TE.score(TE.normalize_metrics({"spoken_share": 0.53,
                                          "length_s": 91.0}), tg)
    check("both measured within grace", full["within_grace"])
    check("3-point miss bands ACCEPT", full["band"] == TE.BAND_ACCEPT)
    flag = TE.score(TE.normalize_metrics({"spoken_share": 0.56,
                                          "length_s": 90.0}), tg)
    check("6-point miss bands FLAG", flag["band"] == TE.BAND_FLAG)
    check("6-point miss worst_pts", flag["worst_pts"] == 6.0)
    redo = TE.score(TE.normalize_metrics({"spoken_share": 0.50,
                                          "length_s": 110.0}), tg)
    check("length miss past 10 bands REDO",
          not redo["within_grace"] and redo["band"] == TE.BAND_REDO)


def test_band_single_source():
    """2. One constants module: the 5/10 band comes from spoken_share."""
    check("GRACE_PCT re-exported not redefined", TE.GRACE_PCT == GRA == 5)
    check("ACCEPT_PTS from spoken_share",
          TE.ACCEPT_PTS == _SS.ACCEPT_PTS == 5)
    check("FLAG_PTS from spoken_share", TE.FLAG_PTS == _SS.FLAG_PTS == 10)
    check("band labels from spoken_share",
          (TE.BAND_ACCEPT, TE.BAND_FLAG, TE.BAND_REDO)
          == (_SS.BAND_ACCEPT, _SS.BAND_FLAG, _SS.BAND_REDO))
    check("band numbers re-exported",
          (TE.SPOKEN_TARGET_PCT, TE.SPOKEN_MIN_PCT, TE.SPOKEN_MAX_PCT)
          == (_SS.SPOKEN_TARGET_PCT, _SS.SPOKEN_MIN_PCT,
              _SS.SPOKEN_MAX_PCT))
    check("band_for_gap agrees with spoken_share judge_gap",
          [TE.band_for_gap(g) for g in (0, 5, 6, 10, 10.01, 14)]
          == [_SS.BAND_ACCEPT, _SS.BAND_ACCEPT, _SS.BAND_FLAG,
              _SS.BAND_FLAG, _SS.BAND_REDO, _SS.BAND_REDO])
    src = os.path.join(HERE, "target_engine.py")
    text = open(src, encoding="utf-8").read()
    tree = ast.parse(text)
    literal_grace = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Assign)
                     and any(getattr(t, "id", None) == "GRACE_PCT"
                             for t in n.targets)
                     and isinstance(n.value, ast.Constant)]
    check("no literal GRACE_PCT assignment in this module",
          not literal_grace)
    literal_band = [n for n in ast.walk(tree)
                    if isinstance(n, ast.Assign)
                    and any(getattr(t, "id", None) in ("ACCEPT_PTS",
                                                       "FLAG_PTS")
                            for t in n.targets)
                    and isinstance(n.value, ast.Constant)]
    check("no literal ACCEPT_PTS/FLAG_PTS assignment (read from spoken_share)",
          not literal_band)
    check("grace fallback is getattr, not a second constant",
          "getattr(_SS, \"GRACE_PCT\", 5)" in text)


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
          out["verdict"] in (TE.VERDICT_ACCEPT, TE.VERDICT_FLAG,
                             TE.VERDICT_REDO, TE.VERDICT_REGENERATE))
    check("empty round regenerates without raising", True)
    out2 = TE.steer(lambda i, adj: [], TE.targets(), max_rounds=2)
    check("empty rounds end in REDO (nothing to keep)",
          out2["verdict"] == TE.VERDICT_REDO)


def test_timing_map_fallback_measurement():
    """6b. No detector yet (W-G-003 not on main): the spoken_share timing
    map measures, tagged as planner-side."""
    timing = [{"delivery": "spoken", "seconds": 45.0},
              {"delivery": "sung", "seconds": 45.0}]
    m = TE.measure_candidate({"id": "t", "timing": timing})
    check("timing map measures spoken share", m["spoken_share"] == 0.5)
    check("timing map tagged as source",
          m["detector"] == "spoken_share.timing")


def test_music_director_call_path():
    """5a. music_director.select_best judges the take through the engine:
    accept / flag / redo within 5/10."""
    import music_director as MD
    scored = [
        {"candidate_id": "take-1", "axes": {}, "total": 0.9,
         "verdict": "PASS", "reasons": [], "lyric_diff": {}},
        {"candidate_id": "take-2", "axes": {}, "total": 0.8,
         "verdict": "PASS", "reasons": [], "lyric_diff": {}},
    ]
    tg = {"spoken_share": 0.225, "length_s": 90.0}
    sel = MD.select_best(scored,
                         target_metrics={"spoken_share": 0.26,
                                         "length_s": 90.0},
                         targets=tg)
    check("MD winner still the highest total",
          sel["winner"]["candidate_id"] == "take-1")
    check("MD within-5 -> ACCEPT", sel["target"]["verdict"] == "ACCEPT"
          and sel["target"]["band"] == TE.BAND_ACCEPT)
    check("MD within-5 no flag", sel["target"]["flags"] == [])

    sel = MD.select_best(scored,
                         target_metrics={"spoken_share": 0.285,
                                         "length_s": 90.0},
                         targets=tg)
    check("MD 6-off -> ACCEPT_WITH_FLAG",
          sel["target"]["verdict"] == "ACCEPT_WITH_FLAG"
          and sel["target"]["band"] == TE.BAND_FLAG)
    check("MD 6-off flag in the receipt",
          len(sel["target"]["flags"]) == 1
          and sel["target"]["flags"][0].startswith("FLAG:"))

    sel = MD.select_best(scored,
                         target_metrics={"spoken_share": 0.365,
                                         "length_s": 90.0},
                         targets=tg)
    check("MD 14-off -> REDO", sel["target"]["verdict"] == "REDO"
          and sel["target"]["band"] == TE.BAND_REDO)
    check("MD 14-off note says regenerate, never cancel",
          "REDO" in sel["note"] and "regenerate" in sel["note"]
          and "cancel" not in sel["note"].replace("never cancel", ""))

    sel = MD.select_best(scored)   # no metrics -> unchanged legacy shape
    check("MD without target_metrics unchanged",
          "target" not in sel and sel["winner"]["candidate_id"] == "take-1")


def test_retake_manager_call_path():
    """5b. retake_manager.plan gates a target-miss retake on the band:
    within 5 no retake, 5-10 no retake (flag), past 10 retakes."""
    import retake_manager as RM

    def req(gap):
        return {"failed_artifact_id": "take-1", "check": "target band",
                "shots": ["take-1"], "target_gap_pts": gap}

    out = RM.plan(req(4.0), profile_path="/nonexistent-profile.json")
    check("RM 4-off rejected as in-band",
          out["outcome"] == "rejected" and out["code"] == "TARGET_IN_BAND"
          and out["band"] == TE.BAND_ACCEPT)
    out = RM.plan(req(6.0), profile_path="/nonexistent-profile.json")
    check("RM 6-off rejected as in-band (flag, not redone)",
          out["outcome"] == "rejected" and out["code"] == "TARGET_IN_BAND"
          and out["band"] == TE.BAND_FLAG)
    out = RM.plan(req(14.0))
    check("RM 14-off plans the retake",
          out["outcome"] == "ok" and out["targets"] == ["take-1"])
    check("RM without target_gap_pts unchanged (needs profile)",
          RM.plan({"failed_artifact_id": "x"})["outcome"] == "rejected")


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
    test_five_point_boundary_accepts()
    test_six_off_flags_and_accepts()
    test_ten_point_boundary_flags()
    test_past_10_redoes_after_rounds()
    test_all_spoken_reject_and_regenerate()
    test_singing_not_chosen_allows_spoken()
    test_closest_of_n()
    test_score_worst_and_unmeasured()
    test_band_single_source()
    test_caller_bugs_raise_misses_never()
    test_timing_map_fallback_measurement()
    test_music_director_call_path()
    test_retake_manager_call_path()
    test_hygiene()
    print("")
    if FAILS:
        print("FAILED %d: %s" % (len(FAILS), FAILS))
        return 1
    print("all target-engine checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
