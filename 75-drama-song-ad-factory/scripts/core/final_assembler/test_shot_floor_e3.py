#!/usr/bin/env python3
"""E3 tests for the minimum-shot-length floor (manual 02 Part E E3, High).

stdlib only, zero paid calls, no ffmpeg binary required.

Covers:
  validate_timeline_min_shot - the 0.39 s plan carries SEGMENT_TOO_SHORT;
                a 1.2 s beat_cut segment passes; a custom floor
                overrides; bad shape is named, not silently passed.
  plan_shot_floor - a 1.2 s non-beat-cut plan is merged/extended at
                planning time; a 1.2 s beat_cut segment is merged only
                when a non-lip-sync neighbour shares its boundary, else
                extended; scene order is preserved after a merge; an
                E5 lip-sync atomic clip is extended, never merged; the
                merged plan passes the QC check afterwards.
  assembler wiring - load_timeline fails closed (SEGMENT_TOO_SHORT) on a
                timeline containing the 0.39 s segment, and accepts a
                compliant one (assembler check_timeline_min_shot).
  regression - bind_plan on the original 14.2 shot shape still binds
                after floor remediation (no field lost).

Run: python3 core/final_assembler/test_shot_floor_e3.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import shot_planner as SP                 # noqa: E402
import final_assembler.assembler as A     # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def seg(dur, beat_cut=False, **kw):
    s = {"src": "clip_%s.mp4" % str(abs(hash((dur, beat_cut))))[:6],
         "dur": dur}
    if beat_cut:
        s["beat_cut"] = True
    s.update(kw)
    return s


# ---- 1. QC check: the 0.39 s case must fail SEGMENT_TOO_SHORT (explicit) --
tl_039 = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
          "segments": [seg(2.0), seg(0.39)]}
errs = SP.validate_timeline_min_shot(tl_039)
check("0.39s segment fails with SEGMENT_TOO_SHORT",
      any("SEGMENT_TOO_SHORT" in e and "0.39" in e for e in errs),
      repr(errs))
check("0.39s error names the index + floor",
      len(errs) == 1 and "segments[1]" in errs[0] and "1.50" in errs[0],
      repr(errs))

# ---- 2. QC check: 1.2 s beat_cut passes, 1.2 s plain fails (explicit) ----
tl_beat = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
           "segments": [seg(2.0), seg(1.2, beat_cut=True)]}
check("1.2s beat_cut segment passes the 1.0s boundary floor",
      SP.validate_timeline_min_shot(tl_beat) == [], "returned errors")
tl_plain = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
            "segments": [seg(1.2)]}
check("1.2s non-beat-cut segment fails the 1.5s floor",
      any("SEGMENT_TOO_SHORT" in e for e in
          SP.validate_timeline_min_shot(tl_plain)))

# ---- 3. custom floor override --------------------------------------------
tl_13 = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
         "segments": [seg(2.0), seg(1.3, beat_cut=True)]}
tl_16 = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
         "segments": [seg(2.0), seg(1.6, beat_cut=True)]}
check("custom floor override honored",
      SP.validate_timeline_min_shot(tl_plain, floor=1.0) == [])
check("custom beat_cut_floor override honored (1.6 >= 1.5 passes, "
      "beats 2.0 plain floor)", SP.validate_timeline_min_shot(
          tl_16, floor=2.0, beat_cut_floor=1.5) == [])
errs_13 = SP.validate_timeline_min_shot(tl_13, floor=2.0, beat_cut_floor=1.4)
check("1.3s beat_cut segment fails when beat_cut_floor overridden to 1.4",
      any("SEGMENT_TOO_SHORT" in e and "1.30" in e for e in errs_13),
      repr(errs_13))

# ---- 4. bad shape named ---------------------------------------------------
check("timeline dict without segments named",
      any("TIMELINE_BAD_SHAPE" in e for e in
          SP.validate_timeline_min_shot({"schema_version": A.TIMELINE_SCHEMA})))
check("segment without usable duration named",
      any("TIMELINE_BAD_SEGMENT" in e for e in
          SP.validate_timeline_min_shot([{"src": "c.mp4"}])))

# ---- 5. planning: 1.2 s non-beat-cut merged/extended, order preserved ---
shot = {"shot_id": "S2", "song_start": 2.0, "song_end": 3.2,
        "lyric_line_ids": ["L2"], "src": "b.mp4"}
plan = [{"shot_id": "S1", "song_start": 0.0, "song_end": 2.0,
         "lyric_line_ids": ["L1"], "src": "a.mp4"},
        shot,
        {"shot_id": "S3", "song_start": 3.2, "song_end": 5.0,
         "lyric_line_ids": ["L3"], "src": "c.mp4"}]
out, report = SP.plan_shot_floor(plan)
check("short non-beat-cut shot merged at planning time", len(report) == 1
      and report[0]["action"] == "merged", repr(report))
check("merge happened into next neighbour",
      [s["shot_id"] for s in out] == ["S1", "S2"], repr(out))
check("merged shot meets floor",
      out[1]["song_end"] - out[1]["song_start"] >= SP.MIN_SHOT_S,
      repr(out[1]))
check("scene order preserved after merge",
      [s["shot_id"] for s in out] == sorted(
          s["shot_id"] for s in out)
      and out[0]["song_start"] <= out[1]["song_start"]
      and out[0]["song_end"] <= out[1]["song_start"],
      repr(out))
# merged plan must now pass the gate check (durations roundtrip to dur)
check("post-merge plan passes validate_timeline_min_shot",
      all("SEGMENT_TOO_SHORT" not in e for e in SP.validate_timeline_min_shot(
          {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
           "segments": [{"src": s["src"], "dur": s.get("song_end", 0)
                         - s.get("song_start", 0)} for s in out]})))

# ---- 6. planning: sub-floor beat_cut with no mergeable neighbour extends -
# 1.2 s beat_cut already meets its 1.0 s boundary floor (no action), so the
# extension case uses a 0.9 s beat_cut segment.
bc = [{"shot_id": "B1", "song_start": 0.0, "song_end": 4.0,
       "lyric_line_ids": ["L1"], "src": "a.mp4"},
      {"shot_id": "B2", "song_start": 4.0, "song_end": 4.9,
       "lyric_line_ids": ["L2"], "src": "b.mp4", "beat_cut": True}]
out_b, rep_b = SP.plan_shot_floor(bc)
check("0.9s beat_cut shot extended to its 1.0s boundary floor",
      len(rep_b) == 1 and rep_b[0]["action"] == "extended"
      and rep_b[0]["floor_s"] == SP.BEAT_CUT_MIN_SHOT_S
      and abs((out_b[1]["song_end"] - out_b[1]["song_start"])
              - SP.BEAT_CUT_MIN_SHOT_S) < 1e-9,
      repr((out_b, rep_b)))
check("beat_cut neighbour not consumed for merge",
      [s["shot_id"] for s in out_b] == ["B1", "B2"], repr(out_b))

# ---- 7. planning: E5 lip-sync atomic clip extended, never merged ---------
# Atomicity rides the explicit lip_sync field (never a src-name guess),
# matching E5's data contract.
lsy = [{"shot_id": "L1", "song_start": 0.0, "song_end": 2.0,
        "lyric_line_ids": ["l1"], "src": "lsync.mp4", "lip_sync": True},
       {"shot_id": "L2", "song_start": 2.0, "song_end": 2.6,
        "lyric_line_ids": ["l2"], "src": "b-roll.mp4"},
       {"shot_id": "L3", "song_start": 2.6, "song_end": 3.0,
        "lyric_line_ids": ["l3"], "src": "lsync.mp4", "lip_sync": True}]
out_l, rep_l = SP.plan_shot_floor(lsy)
check("lip-sync short shot merged-or-extended refused merge",
      not any(r["action"] == "merged" for r in rep_l), repr(rep_l))
check("lip-sync clip srcs preserved (atomic windows intact)",
      [(c["src"], c["shot_id"]) for c in out_l]
      == [("lsync.mp4", "L1"), ("b-roll.mp4", "L2"),
          ("lsync.mp4", "L3")],
      repr(out_l))
check("all lip-sync-case shots >= floor after extend",
      all(c["song_end"] - c["song_start"] >= SP.MIN_SHOT_S - 1e-9
          for c in out_l),
      repr([(c["shot_id"], round(c["song_end"] - c["song_start"], 6))
            for c in out_l]))
check("lip-sync L3 window not split across neighbours",
      out_l[2]["song_start"] == 2.6, repr(out_l[2]))  # start unchanged

# ---- 8. lip_sync_atomic=True refuses every merge (song_start shape) ------
out_a, rep_a = SP.plan_shot_floor(
    [{"shot_id": "A1", "song_start": 0.0, "song_end": 1.0,
      "lyric_line_ids": ["x1"]},
     {"shot_id": "A2", "song_start": 1.0, "song_end": 3.0,
      "lyric_line_ids": ["x2"]}], lip_sync_atomic=True)
check("lip_sync_atomic forces extension only",
      all(r["action"] == "extended" for r in rep_a) and len(out_a) == 2,
      repr((out_a, rep_a)))

# ---- 9. QC-path wiring: assembler load_timeline fails closed on 0.39 s ---
tmp = tempfile.mkdtemp(prefix="/tmp/w75-W-E-U3-")
bad = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
       "segments": [seg(2.0), {"src": "short.mp4", "dur": 0.39},
                    seg(2.0)]}
bad_path = os.path.join(tmp, "bad_timeline.json")
with open(bad_path, "w", encoding="utf-8") as fh:
    json.dump(bad, fh)
try:
    A.load_timeline(bad_path)
    check("load_timeline rejects 0.39s timeline", False, "no raise")
except ValueError as exc:
    check("load_timeline rejects 0.39s timeline",
          "SEGMENT_TOO_SHORT" in str(exc) and "0.39" in str(exc),
          repr(str(exc)))
    check("rejection reason cites the check source",
          "minimum shot length" in str(exc), repr(str(exc)))

good = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
        "segments": [seg(2.0), seg(1.2, beat_cut=True), seg(2.0)]}
good_path = os.path.join(tmp, "good_timeline.json")
with open(good_path, "w", encoding="utf-8") as fh:
    json.dump(good, fh)
try:
    tl = A.load_timeline(good_path)
    check("load_timeline accepts compliant timeline", tl == good)
except ValueError as exc:
    check("load_timeline accepts compliant timeline", False, str(exc))

check("assembler check helper returns [] on good timeline",
      A.check_timeline_min_shot(good) == [])
check("assembler check helper returns SEGMENT_TOO_SHORT on 0.39s",
      any("SEGMENT_TOO_SHORT" in e for e in A.check_timeline_min_shot(tl_039)))

# ---- 10. regression: bind_plan still works on the full 14.2 shape --------
timing = {"song_id": "s1", "duration_seconds": 10.0, "sections": [
    {"section_id": "sec1", "lyrics": [
        {"line_id": "L1", "start": 0.0, "end": 2.0, "text": "one"},
        {"line_id": "L2", "start": 2.0, "end": 4.0, "text": "two"}]}]}
shots14 = [
    {"shot_id": "S1", "song_start": 0.0, "song_end": 2.0,
     "lyric_line_ids": ["L1"], "story_stage": "hook",
     "visual_objective": "hook", "character_ids": [], "wardrobe_ids": [],
     "location_id": "L", "product_visibility": "featured",
     "camera_direction": "wide", "reference_assets": [],
     "image_model_capability_request": {"capabilities": ["text-to-image"]},
     "video_model_capability_request": {"capabilities": ["text-to-video"]},
     "continuity_constraints": [], "negative_constraints": [],
     "cost_estimate": 1, "qc_requirements": [], "status": "planned"},
    {"shot_id": "S2", "song_start": 2.0, "song_end": 4.0,
     "lyric_line_ids": ["L2"], "story_stage": "demo",
     "visual_objective": "demo", "character_ids": [], "wardrobe_ids": [],
     "location_id": "L", "product_visibility": "hero",
     "camera_direction": "close", "reference_assets": [],
     "image_model_capability_request": {"capabilities": ["text-to-image"]},
     "video_model_capability_request": {"capabilities": ["text-to-video"]},
     "continuity_constraints": [], "negative_constraints": [],
     "cost_estimate": 1, "qc_requirements": [], "status": "planned"},
]
floor_out, floor_rep = SP.plan_shot_floor(shots14)
bound = SP.bind_plan(floor_out, timing)
check("bind_plan still binds after floor remediation",
      bound["outcome"] == "ok" and bound["shots"] == ["S1", "S2"],
      repr(bound))
check("no plan_shot_floor report row for compliant 14.2 shots",
      floor_rep == [])

print()
if FAILS:
    print("FAILURES: %d -> %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("ALL PASS (test_shot_floor_e3)")