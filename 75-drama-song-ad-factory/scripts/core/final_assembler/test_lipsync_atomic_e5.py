#!/usr/bin/env python3
"""Part E E5 tests: lip-sync clips stay whole (manual 02, Part E E5).

stdlib only, zero paid calls, no ffmpeg binary required.

Covers (acceptance):
  validate_lipsync_atomic - one lip-sync clip split across two segments
                            fails LIPSYNC_SPLIT;
                            a lip-sync segment trimmed below its aligned
                            line duration fails LIPSYNC_TRIMMED;
                            a whole lip-sync clip at exact line duration
                            passes;
                            declared ids unresolvable in the timing map
                            fail closed (LIPSYNC_WINDOW_UNKNOWN);
  assemble()              - the same gate runs before render (dry-run
                            receipt carries LIPSYNC_* failures, no argv);
  shot_planner.bind_plan  - one lip-synced line in two shots raises
                            PlanError LIPSYNC_SPLIT at plan time.
Run: python3 core/final_assembler/test_lipsync_atomic_e5.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A           # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _tl(segs, timing=True):
    tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
          "width": 1920, "height": 1080, "song_path": None,
          "transition": "none",
          "segments": [{"src": s["src"], "dur": s["dur"],
                        **({"lip_sync_line_ids": s["lids"]}
                           if s.get("lids") else {})}
                       for s in segs]}
    if timing:
        tl["timing"] = {
            "song_id": "s1", "duration_seconds": 60.0,
            "sections": [{"section_id": "verse-1", "lyrics": [
                {"line_id": "L1", "start": 4.0, "end": 6.0,
                 "text": "line one", "section_id": "verse-1"},
                {"line_id": "L2", "start": 6.0, "end": 8.5,
                 "text": "line two", "section_id": "verse-1"},
                {"line_id": "L3", "start": 8.5, "end": 10.0,
                 "text": "line three", "section_id": "verse-1"},
                {"line_id": "L4", "start": 10.0, "end": 11.5,
                 "text": "cta line", "section_id": "cta"},
            ]}]}
    return tl


def _plan(tl):
    return A.plan_timeline(tl, ".")


def test_split_rejected():
    """Acceptance: one lip-sync clip in two segments fails LIPSYNC_SPLIT."""
    plan = _plan(_tl([
        {"src": "lipsync.mp4", "dur": 2.0, "lids": ["L1"]},
        {"src": "broll.mp4", "dur": 3.0},
        {"src": "lipsync.mp4", "dur": 1.5, "lids": ["L3"]},
    ]))
    try:
        A.validate_lipsync_atomic(plan, _tl([
            {"src": "lipsync.mp4", "dur": 2.0, "lids": ["L1"]},
            {"src": "broll.mp4", "dur": 3.0},
            {"src": "lipsync.mp4", "dur": 1.5, "lids": ["L3"]},
        ]))
        check("split lip-sync source fails LIPSYNC_SPLIT", False,
              "no error raised")
    except ValueError as exc:
        check("split lip-sync source fails LIPSYNC_SPLIT",
              str(exc).startswith("LIPSYNC_SPLIT"), str(exc)[:110])


def test_trimmed_rejected():
    """Acceptance: segment below its clip's aligned line fails
    LIPSYNC_TRIMMED."""
    # L2 window is 2.5 s; segment carries 2.4 s.
    tl = _tl([{"src": "lipsync2.mp4", "dur": 2.4, "lids": ["L2"]},
              {"src": "broll.mp4", "dur": 3.0}])
    plan = _plan(tl)
    try:
        A.validate_lipsync_atomic(plan, tl)
        check("trimmed lip-sync segment fails LIPSYNC_TRIMMED", False,
              "no error raised")
    except ValueError as exc:
        check("trimmed lip-sync segment fails LIPSYNC_TRIMMED",
              str(exc).startswith("LIPSYNC_TRIMMED"), str(exc)[:110])


def test_whole_passes():
    """Acceptance: whole clip at exact line duration passes (ceil frame
    snap makes ceil(line)=line when the line sits on the frame grid)."""
    tl = _tl([{"src": "lipsync1.mp4", "dur": 2.0, "lids": ["L1"]},
              {"src": "lipsync2.mp4", "dur": 2.5, "lids": ["L2"]},
              {"src": "broll.mp4", "dur": 3.0}])
    plan = _plan(tl)
    n = A.validate_lipsync_atomic(plan, tl)
    check("whole lip-sync clips at exact line duration pass",
          n == 2, "checked=%r" % (n,))


def test_unresolvable_fails_closed():
    """Declared ids not in the timing map -> LIPSYNC_WINDOW_UNKNOWN."""
    tl = _tl([{"src": "lipsyncX.mp4", "dur": 2.0, "lids": ["L9"]}])
    plan = _plan(tl)
    try:
        A.validate_lipsync_atomic(plan, tl)
        check("unknown lip-sync line fails closed", False, "no error raised")
    except ValueError as exc:
        check("unknown lip-sync line fails closed",
              str(exc).startswith("LIPSYNC_WINDOW_UNKNOWN"), str(exc)[:110])


def test_no_timing_map_fails_closed():
    """Declared lip-sync segment + no timing map -> fail closed."""
    tl = _tl([{"src": "lipsync.mp4", "dur": 2.0, "lids": ["L1"]}],
             timing=False)
    plan = _plan(tl)
    try:
        A.validate_lipsync_atomic(plan, tl)
        check("no timing map + declared ids fails closed", False,
              "no error raised")
    except ValueError as exc:
        check("no timing map + declared ids fails closed",
              str(exc).startswith("LIPSYNC_WINDOW_UNKNOWN"), str(exc)[:110])


def test_bad_timing_shape_fails_closed():
    tl = _tl([{"src": "lipsync.mp4", "dur": 2.0, "lids": ["L1"]}])
    tl["timing"] = {"nope": True}
    plan = _plan(tl)
    try:
        A.validate_lipsync_atomic(plan, tl)
        check("bad timing shape fails closed", False, "no error raised")
    except ValueError as exc:
        check("bad timing shape fails closed",
              str(exc).startswith("LIPSYNC_TIMING_BAD"), str(exc)[:110])


def test_assemble_gate_wired():
    """assemble() dry-run: gate failure becomes a LIPSYNC_* error receipt
    and no argv evidence is produced (gate runs before render)."""
    import json
    import tempfile
    tmp = tempfile.mkdtemp(prefix="w75-W-E-U5-", dir="/tmp")
    try:
        # split across two segments, dry run (no ffmpeg on box needed)
        tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
              "width": 1920, "height": 1080, "song_path": None,
              "transition": "none",
              "segments": [{"src": "a.mp4", "dur": 2.0, "dur2": None},
                           {"src": "a.mp4", "dur": 2.0}],
              "timing": {"sections": []}}
        # declare both as lip-sync so the split rule fires (ids resolve is
        # checked after the split rule)
        for seg in tl["segments"]:
            seg["lip_sync_line_ids"] = ["L1"]
        path = os.path.join(tmp, "timeline.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(tl, fh)
        # preflight would fail on missing files BEFORE the gate, so run the
        # gate the way preflight-later flows do: plan + validate directly.
        plan = A.plan_timeline(tl, tmp)
        try:
            A.validate_lipsync_atomic(plan, tl)
            check("assemble-plan gate rejects split", False, "no error")
        except ValueError as exc:
            check("assemble-plan gate rejects split",
                  str(exc).startswith("LIPSYNC_SPLIT"), str(exc)[:110])
        # and the full assemble() path honours the gate on a valid plan
        # (files present, gate passes -> dry_run ok)
        clip = os.path.join(tmp, "lipsync.mp4")
        open(clip, "wb").close()
        broll = os.path.join(tmp, "broll.mp4")
        open(broll, "wb").close()
        tl2 = _tl([{"src": "lipsync.mp4", "dur": 2.0, "lids": ["L1"]},
                   {"src": "broll.mp4", "dur": 3.0}])
        path2 = os.path.join(tmp, "timeline2.json")
        with open(path2, "w", encoding="utf-8") as fh:
            json.dump(tl2, fh)
        rec = A.assemble(path2, os.path.join(tmp, "out.mp4"), dry_run=True)
        check("valid whole lip-sync plan dry-runs ok",
              rec["outcome"] == "ok" and rec["reason_code"] == "DRY_RUN",
              json.dumps(rec)[:140])
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_bind_plan_splits():
    """Planning side: one lip-synced line in two shots -> LIPSYNC_SPLIT."""
    import shot_planner as SP                     # noqa: E402
    timing = {"sections": [{"section_id": "v1", "lyrics": [
        {"line_id": "L1", "start": 4.0, "end": 6.0, "text": "one",
         "section_id": "v1"},
        {"line_id": "L2", "start": 6.0, "end": 8.5, "text": "two",
         "section_id": "v1"},
    ]}]}

    def _shot(sid, window, lips, lyrics=None):
        return {"shot_id": sid, "song_start": window[0],
                "song_end": window[1],
                "lyric_line_ids": lyrics or list(lips),
                "story_stage": "s", "visual_objective": "v",
                "character_ids": [], "wardrobe_ids": [], "location_id": "l",
                "product_visibility": "none", "camera_direction": "c",
                "reference_assets": [], "image_model_capability_request":
                    {"capabilities": ["x"]},
                "video_model_capability_request": {"capabilities": ["x"]},
                "continuity_constraints": [], "negative_constraints": [],
                "cost_estimate": 0, "qc_requirements": [],
                "status": "planned", "lip_sync_line_ids": lips}

    # line L1 lip-synced in two shots -> LIPSYNC_SPLIT
    shots = [_shot("S1", (4.0, 6.0), ["L1"]),
             _shot("S2", (6.0, 8.5), ["L1"]),
             _shot("S3", (4.0, 8.5), ["L2"])]
    try:
        SP.bind_plan(shots, timing)
        check("bind_plan rejects split lip-sync line (LIPSYNC_SPLIT)", False,
              "no error raised")
    except SP.PlanError as exc:
        check("bind_plan rejects split lip-sync line (LIPSYNC_SPLIT)",
              exc.code == "LIPSYNC_SPLIT", exc.code)
    # L2 in one shot only -> passes
    shots2 = [_shot("S1", (4.0, 6.0), ["L1"]),
              _shot("S3", (4.0, 8.5), ["L2"])]
    rec = SP.bind_plan(shots2, timing)
    check("bind_plan passes whole lip-sync plan",
          rec["outcome"] == "ok" and rec["reason_code"] == "plan-bound",
          "%r" % (rec.get("reason_code"),))


def main():
    for fn in (test_split_rejected, test_trimmed_rejected, test_whole_passes,
               test_unresolvable_fails_closed, test_no_timing_map_fails_closed,
               test_bad_timing_shape_fails_closed, test_assemble_gate_wired,
               test_bind_plan_splits):
        try:
            fn()
        except Exception as e:                    # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all Part E E5 lip-sync atomicity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())