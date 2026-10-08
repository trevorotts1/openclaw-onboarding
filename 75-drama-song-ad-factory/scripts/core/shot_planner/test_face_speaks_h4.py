#!/usr/bin/env python3
"""Part H H4 tests: every speaking face is a lip-sync clip + coverage target.

Done-when clauses, one test each (Kiesett "Stop Stale" ad, measured lines
from audio/final-r3/r43_1.line-timings.json; shot ranges from the report):
  * a plan with the homeowner's face in an H3 clip over her line fails
    FACE_SPEAKS_NO_LIPSYNC; the Kiesett S01 / S02 / S08 shots are flagged;
  * QC lists the speaking-face shots (shot / time / line / lip-sync);
  * the planner output for Kiesett's script reaches the 15-20 s target;
  * the coverage band measures (9.6 s of 60 s fails, 15-20 s passes, the
    5-point grace is honoured);
  * the same rule rides the final assembler gate (dry run, no media).

stdlib only, zero paid calls, no ffmpeg needed.
Run: python3 core/shot_planner/test_face_speaks_h4.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from shot_planner import face_speaks as F          # noqa: E402
import final_assembler.assembler as A              # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def L(lid, speaker, start, end, text=""):
    return {"line_id": lid, "speaker": speaker, "start": start, "end": end,
            "text": text}


# Kiesett's measured lines (spoken, whole-line spans) + the sung verses,
# which are the low narrator voice (not the woman's).
KIESETT = [
    L("HO1", "homeowner", 2.85, 7.9, "No. We're just going to take a break"),
    L("SUNG1", "narrator", 11.45, 15.8, "The sign came down"),
    L("PARTNER", "partner", 15.9, 16.55, "So what now?"),
    L("HO2", "homeowner", 17.25, 20.3, "Nothing. I'm tired."),
    L("SUNG2", "narrator", 22.5, 27.6, "Later is a door"),
    L("STALE1", "stale", 27.75, 29.05, "Heard we're taking a break."),
    L("SUNG3", "narrator", 30.6, 33.83, "Mortgage takes a bite"),
    L("SUNG4", "narrator", 43.5, 47.95, "Stop feeding Stale"),
    L("HO3", "homeowner", 51.95, 54.6, "How long are you planning to stay?"),
    L("STALE2", "stale", 55.45, 59.1, "How long you planning to wait?"),
]


def S(sid, start, end, faces, lip=None, speaking=None):
    return {"shot_id": sid, "start": start, "end": end,
            "faces_on_screen": faces, "lip_sync_line_ids": lip or [],
            "speaking_faces": speaking or []}


# The delivered ad: S01, S02, S08 are H3 pictures with a talking face.
DELIVERED = [
    S("S01", 0, 7.7, ["homeowner"]),
    S("S02", 7.7, 15.2, ["homeowner", "partner"], speaking=["homeowner"]),
    S("S03", 15.2, 21.5, ["stale"]),
    S("S04", 21.5, 27.5, ["stale", "homeowner"]),
    S("LS1", 27.5, 29.33, ["stale"], lip=["STALE1"]),
    S("S08", 43.4, 47.6, ["homeowner"], speaking=["homeowner"]),
    S("LS3", 51.7, 55.2, ["homeowner"], lip=["HO3"]),
    S("LS2", 55.2, 59.17, ["stale"], lip=["STALE2"]),
]


def test_homeowner_h3_over_her_line_fails():
    plan = [S("K1", 12, 18, ["homeowner"])]
    lines = [L("HO", "homeowner", 12.5, 17.5)]
    res = F.check_face_speaks(plan, lines)
    check("homeowner face in an H3 clip over her line fails",
          not res["pass"] and res["reason_code"] == "FACE_SPEAKS_NO_LIPSYNC",
          res["reason_code"])
    plan[0]["lip_sync_line_ids"] = ["HO"]
    check("same shot as her lip-sync clip passes",
          F.check_face_speaks(plan, lines)["pass"])


def test_kiesett_flags_s01_s02_s08():
    res = F.check_face_speaks(DELIVERED, KIESETT)
    flagged = sorted({r["shot_id"] for r in res["failed"]})
    check("Kiesett ad fails FACE_SPEAKS_NO_LIPSYNC",
          res["reason_code"] == "FACE_SPEAKS_NO_LIPSYNC", res["reason_code"])
    check("S01, S02 and S08 are flagged (and nothing else)",
          flagged == ["S01", "S02", "S08"], flagged)
    check("QC list names shot / time / line / lip-sync for every speaking "
          "face", all(set(("shot_id", "start", "end", "line_id", "lip_sync"))
                      <= set(r) for r in res["rows"]) and len(res["rows"]) >= 6)
    check("the three real lip-sync shots are listed as ok",
          {r["shot_id"] for r in res["rows"] if r["ok"]}
          == {"LS1", "LS2", "LS3"})


def test_non_speaking_alternatives_pass():
    lines = [L("HO", "homeowner", 10, 14), L("NAR", "narrator", 14, 20)]
    shots = [S("back", 10, 14, []),                       # back of head / hands
             S("other", 10, 14, ["stale"]),               # another character
             S("voiceover", 14, 20, ["homeowner"])]       # narrator over a face
    check("back of head, another character, narrator over a face all pass",
          F.check_face_speaks(shots, lines)["pass"])
    wrong = F.check_face_speaks([S("w", 10, 14, ["stale"], lip=["HO"])], lines)
    check("lip-sync clip whose speaker is not on screen fails "
          "LIPSYNC_WRONG_FACE", wrong["reason_code"] == "LIPSYNC_WRONG_FACE",
          wrong["reason_code"])


def test_planner_reaches_target_for_kiesett():
    plan = F.plan_lipsync_lines(KIESETT, 63.17)
    check("planner reaches the target for Kiesett's script",
          plan["pass"] and plan["total_s"] >= plan["target_min_s"] - 1e-6
          and plan["total_s"] <= plan["target_max_s"] + 1e-6, plan)
    check("planner never picks the narrator's sung verses",
          not any(s.startswith("SUNG") for s in plan["selected"]),
          plan["selected"])
    check("planner picks at least 3 lines",
          len(plan["selected"]) >= 3)
    thin = F.plan_lipsync_lines([KIESETT[3], KIESETT[5], KIESETT[8]], 63.17)
    check("a script with too few own-face lines is reported unreachable",
          not thin["pass"] and thin["reason_code"] == F.TARGET_UNREACHABLE)


def test_coverage_band_measures():
    lo, hi, grace = F.target_band_s(60)
    check("60 s ad: 15-20 s band with 3 s (5 points) grace",
          (lo, hi, round(grace, 6)) == (15.0, 20.0, 3.0), (lo, hi, grace))
    bad = F.check_coverage_band(63.17, 9.6, 3)
    check("Kiesett's delivered 9.6 s fails the band",
          not bad["pass"] and bad["reason_code"] == F.BELOW_BAND, bad)
    check("12.5 s of 60 s sits inside the grace band",
          F.check_coverage_band(60, 12.5, 3)["pass"])
    check("16 s passes and 25 s is reported over, not failed",
          F.check_coverage_band(60, 16, 4)["pass"]
          and F.check_coverage_band(60, 25, 4)["pass"]
          and not F.check_coverage_band(60, 25, 4)["evidence"]["in_band"])
    check("a 30 s ad scales the band to 7.5-10 s",
          F.target_band_s(30)[:2] == (7.5, 10.0))
    try:
        F.target_band_s(0)
        check("zero length raises", False)
    except F.FaceRuleError:
        check("zero length raises", True)


def _tl(tmp, shots_bad=False, no_faces=False):
    # 60 s master, no transitions: seg0 0-12 ... seg7 52-60.
    spec = [(12, [], None, None), (5, ["homeowner"], ["L1"], None),
            (8, [], None, None), (5, ["stale"], ["L2"], None),
            (12, ["homeowner"], None, ["homeowner"] if shots_bad else None),
            (5, ["homeowner"], ["L3"], None), (5, ["stale"], ["L4"], None),
            (8, [], None, None)]
    segs = []
    for i, (d, faces, lip, spk) in enumerate(spec):
        s = {"src": "clip%d.mp4" % i, "dur": float(d), "shot_id": "seg%d" % i}
        if not no_faces:
            s["faces_on_screen"] = faces
        if lip:
            s["lip_sync"] = True
            s["lip_sync_line_ids"] = lip
        if spk:
            s["speaking_faces"] = spk
        segs.append(s)
    rows = [("L1", "homeowner", 12, 17), ("L2", "stale", 25, 30),
            ("L3", "homeowner", 42, 47), ("L4", "stale", 47, 52)]
    tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30, "width": 1920,
          "height": 1080, "song_path": None, "transition": "none",
          "segments": segs,
          "lines": [{"line_id": i, "speaker": sp, "start_s": a, "end_s": b}
                    for i, sp, a, b in rows],
          "timing": {"sections": [{"lyrics": [
              {"line_id": i, "start": a, "end": b} for i, _, a, b in rows]}]}}
    path = os.path.join(tmp, "tl-%d%d.json" % (shots_bad, no_faces))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(tl, fh)
    return path


def test_assembler_gate():
    tmp = tempfile.mkdtemp()
    for i in range(8):
        open(os.path.join(tmp, "clip%d.mp4" % i), "wb").close()
    ok = A.assemble(_tl(tmp), os.path.join(tmp, "o.mp4"), dry_run=True)
    check("assembler dry run passes when every speaking face is lip-synced",
          ok["outcome"] == "ok", ok.get("reason_code"))
    bad = A.assemble(_tl(tmp, shots_bad=True), os.path.join(tmp, "o2.mp4"),
                     dry_run=True)
    check("assembler blocks a talking face with no lip-sync clip",
          bad["outcome"] == "error"
          and bad["reason_code"] == "FACE_SPEAKS_NO_LIPSYNC",
          bad.get("reason_code"))
    miss = A.assemble(_tl(tmp, no_faces=True), os.path.join(tmp, "o3.mp4"),
                      dry_run=True)
    check("missing faces_on_screen fails closed FACE_DATA_MISSING",
          miss["reason_code"] == "FACE_DATA_MISSING", miss.get("reason_code"))


def main():
    for fn in (test_homeowner_h3_over_her_line_fails,
               test_kiesett_flags_s01_s02_s08,
               test_non_speaking_alternatives_pass,
               test_planner_reaches_target_for_kiesett,
               test_coverage_band_measures, test_assembler_gate):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % fn.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
