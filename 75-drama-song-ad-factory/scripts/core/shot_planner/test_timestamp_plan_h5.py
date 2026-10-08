#!/usr/bin/env python3
"""Part H H5 tests: pictures planned from real song timestamps.

Done when: a mismatched shot fails QC (PICTURE_LINE_MISMATCH), slow motion
above 1.15x fails (SLOWMO_OVER_LIMIT), planned timings are refused, and the
assembler dry run enforces both. stdlib only, $0, no ffmpeg needed.

Run: python3 core/shot_planner/test_timestamp_plan_h5.py
"""
import json
import os
import sys
import tempfile

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import shot_planner.timestamp_plan as TP          # noqa: E402
from shot_planner.shot_planner import PlanError   # noqa: E402
import final_assembler.assembler as A             # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# Real Suno-style timings (Kiesett's Stale ad, abbreviated).
LINES = [
    {"line_id": "L1", "start": 11.45, "end": 15.8, "text": "The sign came down, the house went Stale"},
    {"line_id": "L2", "start": 30.6, "end": 33.83, "text": "Mortgage takes a bite, taxes take a bite"},
    {"line_id": "L3", "start": 43.5, "end": 47.95, "text": "Stop feeding Stale, take back the wheel"},
]
REAL = "suno-timestamped-lyrics"


def test_plan():
    try:
        TP.plan_from_timestamps(LINES, "packet-plan", 60)
        check("planned timings refused", False)
    except PlanError as e:
        check("planned timings refused", e.code == "PLANNED_TIMINGS_REFUSED", e.code)
    shots = TP.plan_from_timestamps(LINES, REAL, 60.0, {"L2": "Stale at the bills table"})
    check("windows contiguous 0..60", shots[0]["song_start"] == 0
          and shots[-1]["song_end"] == 60.0
          and all(a["song_end"] == b["song_start"] for a, b in zip(shots, shots[1:])))
    check("every shot names its line and requests its own length",
          all(s["shows_line_ids"] and abs(s["gen_duration_s"] - (s["song_end"] - s["song_start"])) < 1e-6
              and s["gen_duration_s"] <= TP.MAX_CLIP_S + 1e-6 for s in shots))
    check("planned shots match their own words",
          TP.pictures_match_gate(shots, LINES)["outcome"] == "ok")
    ls = TP.plan_from_timestamps(LINES, REAL, 60.0, lipsync_line_ids=("L3",))
    check("lip-sync line stays one shot", sum("L3" in s["lyric_line_ids"] for s in ls) == 1)


def test_mismatch_fails():
    shots = TP.plan_from_timestamps(LINES, REAL, 60.0)
    fridge = next(s for s in shots if "L2" in s["lyric_line_ids"])
    fridge["shows_line_ids"] = ["L1"]           # fridge picture over the Mortgage line
    g = TP.pictures_match_gate(shots, LINES)
    check("mismatched shot fails QC", g["outcome"] == "rejected"
          and g["reason_code"] == TP.MISMATCH and g["mismatches"] == [fridge["shot_id"]], g["mismatches"])
    row = next(r for r in g["rows"] if r["shot_id"] == fridge["shot_id"])
    check("table row lists shot/time/line/match",
          row["heard_line_id"] == "L2" and row["match"] is False and row["start"] < row["end"])
    fridge["shows_line_ids"] = []
    check("unnamed line fails", TP.match_table(shots, LINES)[shots.index(fridge)]["reason"] == "NO_LINE_NAMED")
    check("Q10 line carries numbers", "of" in g["q10"] and str(len(shots) - 1) in g["q10"])


def test_stretch():
    r = TP.check_stretch([{"src": "a", "dur": 8.0, "source_dur": 4.4},      # 1.8x (Kiesett S01)
                          {"src": "b", "dur": 4.6, "source_dur": 4.0},      # 1.15x
                          {"src": "c", "dur": 5.0, "speed": 0.7}])          # 1.43x
    check("1.8x fails, 1.15x passes, speed 0.7 fails",
          [x["ok"] for x in r] == [False, True, False], r)


def _tl(tmp, segs, lines=None):
    p = os.path.join(tmp, "tl.json")
    d = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30, "width": 1920, "height": 1080,
         "song_path": None, "transition": "none", "segments": segs}
    if lines:
        d["lines"] = lines
    json.dump(d, open(p, "w"))
    return p


def test_assembler():
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "c.mp4"), "wb").close()
    out = os.path.join(tmp, "o.mp4")
    slow = _tl(tmp, [{"src": "c.mp4", "dur": 8.0, "source_dur": 4.4}])
    r = A.assemble(slow, out, dry_run=True)
    check("assembler blocks 1.8x slow motion", r["reason_code"] == TP.SLOWMO, r.get("reason_code"))
    ok = _tl(tmp, [{"src": "c.mp4", "dur": 4.5, "source_dur": 4.0}])
    r = A.assemble(ok, out, dry_run=True)
    # (a short ad still trips the unrelated E6 coverage gate; H5 must not)
    check("assembler passes 1.125x", r["reason_code"] not in (TP.SLOWMO, TP.MISMATCH)
          and r["evidence"]["h5"]["stretch"][0]["ok"], r.get("reason_code"))
    ln = [{"line_id": "L1", "start_s": 0.0, "end_s": 4.0, "text": "Mortgage takes a bite"},
          {"line_id": "L2", "start_s": 4.0, "end_s": 8.0, "text": "Take back the wheel"}]
    bad = _tl(tmp, [{"src": "c.mp4", "dur": 4.0, "shows_line_ids": ["L2"]},
                    {"src": "c.mp4", "dur": 4.0, "shows_line_ids": ["L2"]}], ln)
    r = A.assemble(bad, out, dry_run=True)
    check("assembler blocks picture/line mismatch", r["reason_code"] == TP.MISMATCH, r.get("reason_code"))
    good = _tl(tmp, [{"src": "c.mp4", "dur": 4.0, "shows_line_ids": ["L1"]},
                     {"src": "c.mp4", "dur": 4.0, "shows_line_ids": ["L2"]}], ln)
    r = A.assemble(good, out, dry_run=True)
    check("assembler passes matching pictures", r["reason_code"] != TP.MISMATCH
          and r["evidence"]["h5"]["pictures_match"]["outcome"] == "ok", r.get("reason_code"))


if __name__ == "__main__":
    test_plan()
    test_mismatch_fails()
    test_stretch()
    test_assembler()
    print("%d check(s) failed" % len(FAILS) if FAILS else "all H5 checks passed")
    sys.exit(1 if FAILS else 0)
