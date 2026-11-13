#!/usr/bin/env python3
"""U-V03 / S75-055: the assembler's planning step writes edit/timeline.json.

The finding: edit/timeline.json (read by the assembler, the clip cutter and
the trailer cutter) was written only by the proof script -- no production
module wrote it. ``assembler.plan_run_timeline(run_dir)`` is that writer: it
composes the timeline from the run's own records and writes it atomically.

This test builds ONE offline run fixture (records only -- no ffmpeg, no
network, no paid call) and checks:

  1. after the planning step, edit/timeline.json exists and parses;
  2. it holds every key the assembler's own checks demand: schema, 30 fps,
     song, run id, segments each carrying motion_score / faces_on_screen /
     lip-sync line ids / speaker / the materialized clip's artifact record,
     lines carrying speaker and their measured windows, and a directive-12.4
     timing map holding every lip-sync line;
  3. load_timeline() accepts the written file, and plan_timeline() builds the
     frame plan from it;
  4. a value NO record holds is the named refusal TIMELINE_INPUT_MISSING:<what>
     -- never a default (missing clip index, unmeasured timings, no motion
     score anywhere), and a refusal writes no timeline;
  5. the write is atomic: no temporary file is left beside it.

Run: python3 -B scripts/core/final_assembler/test_timeline_written_s75_055.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A       # noqa: E402

FAILS = []
RUN_ID = "run-s75-055"
PEOPLE = "lead"

SHOTS = [
    {"shot_id": "S01", "song_start": 0.0, "song_end": 2.0,
     "lyric_line_ids": ["l01"], "lip_sync": True, "lip_sync_line_ids": ["l01"],
     "speaker": PEOPLE, "character_ids": [PEOPLE]},
    {"shot_id": "S02", "song_start": 2.0, "song_end": 4.0,
     "lyric_line_ids": ["l02"], "lip_sync": True, "lip_sync_line_ids": ["l02"],
     "speaker": PEOPLE, "character_ids": [PEOPLE]},
    {"shot_id": "S03", "song_start": 4.0, "song_end": 6.0,
     "lyric_line_ids": ["l03"], "lip_sync": True, "lip_sync_line_ids": ["l03"],
     "speaker": PEOPLE, "character_ids": [PEOPLE]},
]

WORDS = [
    {"word": "my", "start": 0.2, "end": 0.6},
    {"word": "ritual", "start": 0.6, "end": 1.4},
    {"word": "i", "start": 2.3, "end": 2.5},
    {"word": "grabbed", "start": 2.5, "end": 3.2},
    {"word": "tap", "start": 4.4, "end": 4.8},
    {"word": "today", "start": 4.8, "end": 5.4},
]


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _write(path, doc):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def build_run(tmp, *, clips=True, timing_source="suno-timestamped-lyrics",
              clip_motion=True):
    """One offline run folder holding only records (no media, no provider)."""
    run = os.path.join(tmp, "run")
    _write(os.path.join(run, "storyboard", "shot-list.json"),
           {"shots": [dict(s) for s in SHOTS]})
    _write(os.path.join(run, "storyboard", "approval.json"),
           {"state": "approved", "choice": "yes",
            "shots": {s["shot_id"]: {"status": "approved", "revision": "r1",
                                     "still_sha256": "still-" + s["shot_id"]}
                      for s in SHOTS}})
    _write(os.path.join(run, "music", "word-timings.json"),
           {"ok": True,
            "timings": {"source": timing_source,
                        "words": [dict(w) for w in WORDS]}})
    _write(os.path.join(run, "control", "intake-session.json"),
           {"run_id": RUN_ID})
    _write(os.path.join(run, "control", "method.json"),
           {"chosen_length_s": 30})
    open(os.path.join(run, "music", "picked-song.mp3"), "w").close()
    if clips:
        rows = []
        for i, s in enumerate(SHOTS):
            row = {"shot_id": s["shot_id"],
                   "path": "video/clip%02d.mp4" % (i + 1),
                   "sha256": "sha-%s" % s["shot_id"],
                   "receipt_path": "video/clip%02d.receipt.json" % (i + 1),
                   "task_id": "task-%s" % s["shot_id"]}
            if clip_motion:
                row["motion_score"] = {"score": 0.9, "flagged": False,
                                       "evidence": "spatial"}
            rows.append(row)
        _write(os.path.join(run, "video", "clips.json"), {"clips": rows})
    return run


def test_planning_step_writes_the_timeline(tmp):
    run = build_run(tmp)
    path = A.plan_run_timeline(run)
    expected = os.path.join(run, "edit", "timeline.json")
    check("timeline path is edit/timeline.json", path == expected, path)
    check("edit/timeline.json exists", os.path.isfile(expected))
    with open(expected, encoding="utf-8") as fh:
        text = fh.read()
    tl = json.loads(text)

    # 2. every key the assembler's own checks demand.
    check("schema version", tl.get("schema_version") == A.TIMELINE_SCHEMA,
          tl.get("schema_version"))
    check("30 fps master", tl.get("fps") == 30, tl.get("fps"))
    check("frame size recorded",
          isinstance(tl.get("width"), int) and isinstance(tl.get("height"), int))
    check("soundtrack is the picked song",
          tl.get("song_path") == "music/picked-song.mp3", tl.get("song_path"))
    check("run id comes from the session record",
          tl.get("run_id") == RUN_ID, tl.get("run_id"))
    check("run dir is the edit folder's parent", tl.get("run_dir") == "..",
          tl.get("run_dir"))
    check("chosen length carried from control/method.json",
          tl.get("chosen_length_s") == 30, tl.get("chosen_length_s"))
    check("three segments", len(tl.get("segments") or []) == 3)
    for i, seg in enumerate(tl.get("segments") or []):
        ms = seg.get("motion_score")
        check("segments[%d] carries a numeric motion score" % i,
              isinstance(ms, dict) and isinstance(ms.get("score"), (int, float)))
        check("segments[%d] declares faces_on_screen" % i,
              seg.get("faces_on_screen") == [PEOPLE])
        check("segments[%d] names its lip-sync line and speaker" % i,
              seg.get("lip_sync_line_ids") == [SHOTS[i]["lyric_line_ids"][0]]
              and seg.get("speaker") == PEOPLE and seg.get("lip_sync") is True)
        art = seg.get("artifact")
        check("segments[%d] carries the clip's artifact record" % i,
              isinstance(art, dict) and art.get("kind") == "video"
              and art.get("run_id") == RUN_ID
              and art.get("sha256") == "sha-%s" % SHOTS[i]["shot_id"]
              and isinstance(art.get("provenance"), dict)
              and art["provenance"].get("task_id"))
        check("segments[%d] keeps storyboard scene order" % i,
              seg.get("scene_index") == i)

    lines = tl.get("lines") or []
    check("three lines", len(lines) == 3)
    check("every line carries speaker + a measured window",
          all(l.get("speaker") == PEOPLE
              and isinstance(l.get("start_s"), (int, float))
              and isinstance(l.get("end_s"), (int, float))
              and l["start_s"] < l["end_s"] for l in lines))
    # The line window is the measured word run, not the shot window.
    check("line window comes from the measured words",
          abs(lines[0]["start_s"] - 0.2) < 1e-9
          and abs(lines[0]["end_s"] - 1.4) < 1e-9, lines[0])
    lipsync_ids = {lid for s in tl["segments"]
                   for lid in s.get("lip_sync_line_ids") or []}
    timing_ids = {ln["line_id"]
                  for sec in (tl.get("timing") or {}).get("sections") or []
                  for ln in sec.get("lyrics") or []}
    check("timing map holds every lip-sync line",
          timing_ids == lipsync_ids == {"l01", "l02", "l03"},
          sorted(timing_ids))

    # 3. the assembler's own readers accept what the step wrote.
    loaded = A.load_timeline(expected)
    check("load_timeline accepts the written file", len(loaded["segments"]) == 3)
    plan = A.plan_timeline(tl, os.path.dirname(expected))
    check("plan_timeline builds the frame plan",
          plan["total_frames"] > 0 and len(plan["segments"]) == 3,
          plan.get("total_frames"))
    check("the plan carries the scores and lines the gates read",
          all(isinstance(s.get("motion_score"), dict) for s in plan["segments"])
          and len(plan.get("lines") or []) == 3)

    # 4. atomic + repository-safe: no temp file left, no absolute path baked in.
    check("no temporary file left beside the timeline",
          os.listdir(os.path.dirname(expected)) == ["timeline.json"],
          os.listdir(os.path.dirname(expected)))
    check("no operator path baked into the timeline", tmp not in text)

    # Re-planning replaces the file and still validates.
    again = A.plan_run_timeline(run)
    check("a second planning pass rewrites the same file", again == expected
          and A.load_timeline(again)["run_id"] == RUN_ID)


def test_missing_record_is_a_named_refusal(tmp):
    run = build_run(os.path.join(tmp, "noclipindex"), clips=False)
    try:
        A.plan_run_timeline(run)
        code, msg = None, ""
    except A.TimelineInputMissing as exc:
        code, msg = exc.code, str(exc)
    check("missing video/clips.json is TIMELINE_INPUT_MISSING",
          code == A.TIMELINE_INPUT_MISSING and "video/clips.json" in msg,
          msg)
    check("the refusal wrote no timeline",
          not os.path.exists(os.path.join(run, "edit", "timeline.json")))


def test_planned_timings_are_refused(tmp):
    run = build_run(os.path.join(tmp, "planned"), timing_source="planned")
    try:
        A.plan_run_timeline(run)
        msg = ""
    except A.TimelineInputMissing as exc:
        msg = str(exc)
    check("a planned (not measured) timing source is refused",
          "measured word timings" in msg, msg)


def test_absent_motion_score_is_never_defaulted(tmp):
    run = build_run(os.path.join(tmp, "noscore"), clip_motion=False)

    def no_reader(clip_path):
        raise RuntimeError("no clip reader on this box")

    try:
        A.plan_run_timeline(run, motion_scorer=no_reader)
        msg = ""
    except A.TimelineInputMissing as exc:
        msg = str(exc)
    check("an unreadable motion score is TIMELINE_INPUT_MISSING:motion_score",
          "motion_score" in msg and "TIMELINE_INPUT_MISSING" in msg, msg)


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="s75-055-")
    try:
        test_planning_step_writes_the_timeline(tmp)
        test_missing_record_is_a_named_refusal(tmp)
        test_planned_timings_are_refused(tmp)
        test_absent_motion_score_is_never_defaulted(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAILS:
        print("FAILED: %s" % ", ".join(FAILS))
        sys.exit(1)
    print("all ok")
