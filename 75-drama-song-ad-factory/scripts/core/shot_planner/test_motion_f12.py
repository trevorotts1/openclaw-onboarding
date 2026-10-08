#!/usr/bin/env python3
"""F12 tests: clips must move (manual Part F F12).

stdlib only, $0, mocked providers only — no video is ever read; motion
scores are pure functions over provided frame stats.

Covers (acceptance):
  prompt builders  - bible.compile_visual_prompt and every style-bible
                     compile_prompt carry the F12 motion line ("The subject
                     moves naturally through the frame").
  motion_score     - {'score', 'flagged'} pluggable: pure over frame_stats;
                     still-clip fixture (near-zero diffs) flags
                     CLIP_LOW_MOTION below MOTION_SCORE_LOW = 0.02; moving
                     fixture passes; malformed stats fail closed.
  receipt + gate   - gate_clips flags the still clip (CLIP_LOW_MOTION) and
                     passes the moving one; to_motion_qc_record verdicts;
                     assembler dry-run receipt carries per-clip
                     motion_score and blocks a flagged clip before render.

Run: python3 core/shot_planner/test_motion_f12.py
"""
import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import shot_planner.motion_score as MS            # noqa: E402
from shot_planner.motion_score import (           # noqa: E402
    MOTION_SCORE_LOW, CLIP_LOW_MOTION, MotionScoreError,
    motion_score, frame_diff_score, gate_clips, to_motion_qc_record,
)

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

# ---------------------------------------------------------------- fixtures --

#: Near-still clip: 8 sampled frames, mean luma barely changes (1/255 step).
STILL_STATS = [[i, 128.0 + (0.25 if i % 2 else 0.0)] for i in range(8)]

#: Moving clip: mean luma sweeps ~90/255 across the samples.
MOVING_STATS = [[i, 40.0 + i * 12.0] for i in range(8)]

#: Prompt-builder fixtures (bible shapes: minimal valid records).
STYLE = {
    "schema_version": "1.0.0", "style_id": "resilia-animated-01",
    "aspect_ratio": "9:16",
    "aesthetic": "animated drama look",
    "rendering_style": "hand-painted 2D animation",
    "camera_language": "intimate eye-level medium shots",
    "lens_tendencies": "35mm-equivalent framing",
    "lighting_doctrine": "warm golden key with soft teal fill",
    "contrast_architecture": "lifted shadows",
    "environment_texture": "lived-in painterly sets",
    "grain_sharpness": "fine animation grain",
    "color_palette": ["warm amber", "deep teal"],
    "visual_continuity_constraints": ["fixed proportions"],
    "banned_visual_cliches": ["photoreal deepfake skin"],
}
PRODUCT = {
    "schema_version": "1.0.0", "product_id": "p-01",
    "packaging_reference": "amber jar", "logo_mark": "wordmark",
    "color": "amber", "geometry": "cylinder", "label_placement": "front",
    "cap_lid": "screw cap",
    "prohibited_invented_text": ["miracle"],
    "required_product_reference_images": ["img-1"],
}
CHARS = [{"character_id": "c1", "approved_reference_asset_ids": ["ref-1"]}]
SHOT = {"shot_id": "s1", "base_prompt": "close-up in the kitchen",
        "character_ids": ["c1"]}

MOTION_LINE = "The subject moves naturally through the frame"


def test_bible_prompt_carries_motion():
    """bible.compile_visual_prompt: the clip prompt asks for motion."""
    from product_style_bible import bible
    out = bible.compile_visual_prompt(STYLE, CHARS, PRODUCT, SHOT)
    check("bible prompt carries the F12 motion line",
          MOTION_LINE in out["prompt"], out["prompt"][-160:])
    check("bible prompt still carries the compiled mark",
          bible.assert_compiled(out["prompt"]))
    # Flare/text checks unchanged by the motion line.
    bad = copy.deepcopy(SHOT)
    bad["base_prompt"] = "lens flare over the jar"
    try:
        bible.compile_visual_prompt(STYLE, CHARS, PRODUCT, bad)
        check("flare still prohibited", False, "no raise")
    except bible.CompilerError as e:
        check("flare still prohibited", e.code == "FLARE_PROHIBITED",
              e.code)


def _c3_shot():
    return {"shot_id": "s1", "base_prompt": "wake-up close-up"}


def test_style_bible_prompts_carry_motion():
    """canvas_to_3d / canvas_to_life / hybrid compile_prompt all ask for motion."""
    from style_bibles.canvas_to_3d import canvas_3d_bible as c3
    from style_bibles.canvas_to_life import canvas_to_life_bible as c2l
    from style_bibles.hybrid import hybrid_bible as hb
    ident = {"character": "K", "face": "round", "hair": "black bob",
             "glasses": "none", "accessories": "watch", "wardrobe": "jeans"}
    out = c3.compile_prompt(_c3_shot(), c3.MODE_3D, ident)
    check("canvas_to_3d prompt carries the motion line",
          MOTION_LINE in out["prompt"], out["prompt"][-160:])
    lock = c2l.identity_lock("K", ["ref-1"], ["brave"])
    out2 = c2l.compile_prompt(_c3_shot(), c2l.MODE_PAINTED, lock)
    check("canvas_to_life prompt carries the motion line",
          MOTION_LINE in out2["prompt"], out2["prompt"][-160:])
    out3 = hb.compile_prompt(_c3_shot(), hb.MODE_SKETCH)
    check("hybrid prompt carries the motion line",
          MOTION_LINE in out3["prompt"], out3["prompt"][-160:])


def test_motion_score_pure_over_stats():
    """Pluggable core: pure over frame_stats, threshold 0.02."""
    check("threshold is 0.02", MOTION_SCORE_LOW == 0.02,
          repr(MOTION_SCORE_LOW))
    still = motion_score(frame_stats=STILL_STATS)
    moving = motion_score(frame_stats=MOVING_STATS)
    check("still fixture scores near zero", still["score"] < 0.001,
          repr(still["score"]))
    check("still fixture flagged", still["flagged"] is True, repr(still))
    check("moving fixture scores above threshold",
          moving["score"] >= MOTION_SCORE_LOW, repr(moving["score"]))
    check("moving fixture not flagged", moving["flagged"] is False,
          repr(moving))
    check("score shape", isinstance(still["score"], float)
          and isinstance(still["flagged"], bool)
          and still["threshold"] == MOTION_SCORE_LOW)
    # Flat means list works too.
    flat = motion_score(frame_stats=[100, 100.2, 100.1, 100.0])
    check("flat mean list scores like rows", flat["flagged"] is True,
          repr(flat["score"]))
    # Malformed stats fail closed.
    for bad in ([], [128.0], [[None, "x"]], "nope"):
        try:
            motion_score(frame_stats=bad)
            check("bad stats %r fail closed" % (bad,), False, "no raise")
        except MotionScoreError as e:
            check("bad stats %r fail closed" % (bad,),
                  e.code == "BAD_FRAME_STATS", e.code)
    # No inputs at all -> refused, never a guessed score.
    try:
        motion_score()
        check("no inputs refused", False, "no raise")
    except MotionScoreError as e:
        check("no inputs refused", e.code == "CLIP_UNREADABLE", e.code)


def test_gate_flags_before_assembly():
    """gate_clips: still clip -> CLIP_LOW_MOTION; moving -> pass."""
    still = motion_score(frame_stats=STILL_STATS)
    moving = motion_score(frame_stats=MOVING_STATS)
    rows = [{"clip_id": "clip-still", "motion_score": still},
            {"clip_id": "clip-move", "motion_score": moving}]
    res = gate_clips(rows)
    check("gate rejects when the still clip is flagged",
          res["outcome"] == "rejected" and res["reason_code"] == CLIP_LOW_MOTION,
          json.dumps(res)[:120])
    check("gate names the flagged clip", res["flagged"] == ["clip-still"],
          repr(res["flagged"]))
    check("gate carries scores", res["scores"]["clip-move"] >= 0.02,
          repr(res["scores"]))
    res2 = gate_clips([{"src": "clip-move", "motion_score": moving},
                       {"src": "clip-move-b", "motion_score": moving}])
    check("gate passes moving-only receipts",
          res2["outcome"] == "ok" and res2["reason_code"] == "CLIPS_MOTION_PASS",
          json.dumps(res2)[:120])
    # Unscored rows ride the receipt as FAIL for the QC review layer.
    res3 = gate_clips([{"src": "clip-x"}])
    check("unscored rows listed, not raised",
          res3["unscored"] == ["clip-x"] and res3["flagged"] == [],
          json.dumps(res3)[:120])
    # Malformed score -> fail closed.
    try:
        gate_clips([{"src": "clip-x", "motion_score": "high"}])
        check("malformed score fails closed", False, "no raise")
    except MotionScoreError as e:
        check("malformed score fails closed", e.code == "CLIP_UNSCORED",
              e.code)


def test_qc_record_verdicts():
    """to_motion_qc_record: FAIL on flagged/unscored, PASS on moving."""
    reviewer = {"identity": "qc/f12", "session": "unit-test",
                "authority": "manual Part F F12"}
    still = motion_score(frame_stats=STILL_STATS)
    moving = motion_score(frame_stats=MOVING_STATS)
    rec = to_motion_qc_record(
        [{"clip_id": "c1", "motion_score": still}], reviewer, "run-1")
    check("flagged clip -> FAIL record",
          rec["verdict"] == "FAIL" and rec["reason_code"] == CLIP_LOW_MOTION,
          json.dumps(rec)[:140])
    rec2 = to_motion_qc_record(
        [{"clip_id": "c1", "motion_score": moving}], reviewer, "run-1")
    check("moving clip -> PASS record", rec2["verdict"] == "PASS",
          rec2["reason_code"])
    rec3 = to_motion_qc_record([{"clip_id": "c1"}], reviewer, "run-1")
    check("unscored -> FAIL record (completeness rides QC)",
          rec3["verdict"] == "FAIL", json.dumps(rec3)[:140])


def test_assembler_receipt_and_gate():
    """assemble() dry-run: per-clip motion_score rides the receipt; a
    flagged clip is refused before render (CLIP_LOW_MOTION).

    Fixture follows the shared assembler shape (E5/E6 tests): 3 lip-sync
    lines over >=12% of runtime so the shared E6 coverage gate passes too;
    only the F12 gate varies between the two receipts."""
    import final_assembler.assembler as A
    tmp = tempfile.mkdtemp(prefix="f12_motion_test_")
    moving = motion_score(frame_stats=MOVING_STATS)
    still = motion_score(frame_stats=STILL_STATS)
    try:
        for e in ("lipsync.mp4", "lip2.mp4", "lip3.mp4", "broll.mp4"):
            open(os.path.join(tmp, e), "wb").close()

        def _tl(segments):
            tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                  "width": 1920, "height": 1080, "song_path": None,
                  "transition": "none",
                  "segments": [
                      {"src": s["src"], "dur": s["dur"],
                       "motion_score": s["ms"],
                       **({"lip_sync_line_ids": s["lids"]}
                          if s.get("lids") else {})}
                      for s in segments],
                  "timing": {"song_id": "s1", "duration_seconds": 60.0,
                             "sections": [{"section_id": "verse-1",
                                           "lyrics": [
                     {"line_id": "L1", "start": 4.0, "end": 6.0,
                      "text": "line one", "section_id": "verse-1"},
                     {"line_id": "L2", "start": 6.0, "end": 8.5,
                      "text": "line two", "section_id": "verse-1"},
                     {"line_id": "L3", "start": 8.5, "end": 10.0,
                      "text": "line three", "section_id": "verse-1"},
                     {"line_id": "L4", "start": 10.0, "end": 11.5,
                      "text": "cta line", "section_id": "cta"},
                 ]}]}}
            path = os.path.join(tmp, "timeline.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(tl, fh)
            return path

        # Moving clips: gate passes, receipt carries per-clip scores.
        ok_tl = _tl([
            {"src": "lipsync.mp4", "dur": 16.0, "lids": ["L1"], "ms": moving},
            {"src": "lip2.mp4", "dur": 2.5, "lids": ["L2"], "ms": moving},
            {"src": "lip3.mp4", "dur": 1.5, "lids": ["L3"], "ms": moving},
            {"src": "broll.mp4", "dur": 3.0, "ms": moving}])
        rec = A.assemble(ok_tl, os.path.join(tmp, "out.mp4"), dry_run=True)
        check("moving plan dry-runs ok",
              rec["outcome"] == "ok" and rec["reason_code"] == "DRY_RUN",
              json.dumps(rec)[:160])
        scores = rec["evidence"]["motion"]["scores"]
        # plan segments carry absolute src paths after preflight; the
        # receipt keys scores by that src, one row per planned clip.
        check("receipt carries the motion gate result",
              rec["evidence"]["motion"]["outcome"] == "ok"
              and len(scores) == 4
              and all(v >= 0.02 for v in scores.values()),
              json.dumps(rec["evidence"]["motion"])[:160])
        check("plan segment keeps its motion_score",
              rec["evidence"]["plan"]["segments"][0]["motion_score"]
              ["flagged"] is False)

        # One near-still clip: refused before any render spend.
        low_tl = _tl([
            {"src": "lipsync.mp4", "dur": 16.0, "lids": ["L1"], "ms": moving},
            {"src": "lip2.mp4", "dur": 2.5, "lids": ["L2"], "ms": still},
            {"src": "lip3.mp4", "dur": 1.5, "lids": ["L3"], "ms": moving},
            {"src": "broll.mp4", "dur": 3.0, "ms": moving}])
        rec2 = A.assemble(low_tl, os.path.join(tmp, "out.mp4"), dry_run=True)
        check("still clip refused before render",
              rec2["outcome"] == "error"
              and rec2["reason_code"] == CLIP_LOW_MOTION,
              json.dumps(rec2)[:160])
        check("refusal names exactly the still clip",
              rec2["evidence"]["flagged"]
              == [os.path.join(tmp, "lip2.mp4")],
              repr(rec2.get("evidence", {}).get("flagged")))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for fn in (test_bible_prompt_carries_motion,
               test_style_bible_prompts_carry_motion,
               test_motion_score_pure_over_stats,
               test_gate_flags_before_assembly,
               test_qc_record_verdicts,
               test_assembler_receipt_and_gate):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        print("F12 FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all F12 motion tests passed (%s)" % (
        ", ".join(fn.__name__ for fn in (
            test_bible_prompt_carries_motion,
            test_style_bible_prompts_carry_motion,
            test_motion_score_pure_over_stats,
            test_gate_flags_before_assembly,
            test_qc_record_verdicts,
            test_assembler_receipt_and_gate))))
    return 0


if __name__ == "__main__":
    sys.exit(main())