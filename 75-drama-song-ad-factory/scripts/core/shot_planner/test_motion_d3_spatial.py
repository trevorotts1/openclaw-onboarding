#!/usr/bin/env python3
"""D3 tests: spatial subject motion, not whole-frame mean-brightness change.

Gap-map item D3: motion_score.frame_diff_score was the mean absolute change
of per-frame mean luma, so a flash or a global pan scored high and passed
as "motion". This suite proves the replacement discriminates, with the
measured numbers printed per case:

  real ffmpeg fixtures   flash (global luminance change)      -> refused
                         pan over a still (global translation) -> refused
                         static                            -> refused
                         genuine local motion               -> allowed
  pure frame grids       the same three cases with exact expected geometry
  gate                   missing evidence, malformed evidence, and measured
                         sub-threshold scores still refuse (F12 fail-closed
                         semantics preserved)

Run: python3 core/shot_planner/test_motion_d3_spatial.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from shot_planner.motion_score import (           # noqa: E402
    MOTION_SCORE_LOW, MOTION_SUBJECT_LOW, SPATIAL_GRID, CLIP_LOW_MOTION,
    MotionScoreError, frame_diff_score, gate_clips, motion_score,
    subject_motion_evidence,
)

FAILS = []
W, H = SPATIAL_GRID


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ------------------------------------------------------- pure grid fixtures --

def _pattern():
    """Non-periodic luma texture: real frames are not self-similar under
    translation, and a periodic synthetic grid can out-correlate its own
    true shift."""
    import math
    return [90.0 + 70.0 * math.sin(0.23 * x + 0.11 * y)
            + 40.0 * math.cos(0.31 * y + 0.05 * x)
            for y in range(H) for x in range(W)]


def _flash_grid(base):
    """Uniform luminance offset AND gain: nothing moves, everything brightens."""
    return [0.4 * v + 120.0 for v in base]


def _shifted(base, dx):
    out = []
    for y in range(H):
        for x in range(W):
            out.append(base[y * W + min(W - 1, max(0, x - dx))])
    return out


def _moving_block(base, x0):
    out = list(base)
    for y in range(H // 2, H // 2 + 6):
        for x in range(x0, x0 + 6):
            out[y * W + x] = 255.0
    return out


def test_pure_grids_discriminate():
    base = _pattern()
    flash = subject_motion_evidence([base, _flash_grid(base)])
    pan = subject_motion_evidence([base, _shifted(base, 5)])
    local = subject_motion_evidence([_moving_block(base, 12),
                                     _moving_block(base, 24)])
    for name, ev in (("flash", flash), ("pan", pan), ("local", local)):
        print("  grid %-5s subject_motion=%.6f legacy_frame_diff=%.6f "
              "global_luma_change=%.6f displacement=%.6f"
              % (name, ev["subject_motion_score"], ev["frame_diff_score"],
                 ev["global_luma_change"], ev["global_displacement"]))
    check("pure flash scores below the subject threshold",
          flash["subject_motion_score"] < MOTION_SUBJECT_LOW,
          repr(flash["subject_motion_score"]))
    check("pure flash is a large global luminance change (legacy trap)",
          flash["global_luma_change"] > MOTION_SCORE_LOW,
          repr(flash["global_luma_change"]))
    check("pure pan scores below the subject threshold",
          pan["subject_motion_score"] < MOTION_SUBJECT_LOW,
          repr(pan["subject_motion_score"]))
    check("pure local motion scores above the subject threshold",
          local["subject_motion_score"] > MOTION_SUBJECT_LOW,
          repr(local["subject_motion_score"]))
    check("pure local motion is invisible to the legacy mean-luma score",
          local["frame_diff_score"] < MOTION_SCORE_LOW,
          repr(local["frame_diff_score"]))
    check("local motion separates from pan by at least 5x",
          local["subject_motion_score"] > 5 * max(1e-6, pan["subject_motion_score"]),
          "%r vs %r" % (local["subject_motion_score"],
                        pan["subject_motion_score"]))
    # motion_score() over grids exposes the numbers and decides on them.
    out = motion_score(frame_grids=[_moving_block(base, 12),
                                    _moving_block(base, 24)])
    check("grid motion_score is spatial evidence",
          out["evidence"] == "spatial"
          and out["threshold"] == MOTION_SUBJECT_LOW
          and out["score"] == out["subject_motion_score"]
          and out["flagged"] is False, json.dumps(out, sort_keys=True)[:160])
    snap = motion_score(frame_grids=[base, _flash_grid(base)])
    check("flash grid is flagged with the legacy score still reported",
          snap["flagged"] is True and "frame_diff_score" in snap,
          json.dumps(snap, sort_keys=True)[:160])
    # Malformed grids fail closed; a zero-variance frame is degenerate but
    # valid input and must score zero, not raise.
    for bad in ([base], [base, base[:-1]], [base, [None] * (W * H)],
                "nope"):
        try:
            motion_score(frame_grids=bad)
            check("malformed grid %r fails closed" % (str(bad)[:24],),
                  False, "no raise")
        except MotionScoreError as e:
            check("malformed grid %r fails closed" % (str(bad)[:24],),
                  e.code == "BAD_FRAME_STATS", e.code)
    flat = motion_score(frame_grids=[[0.0] * (W * H), [0.0] * (W * H)])
    check("zero-variance frames score zero and are flagged",
          flat["subject_motion_score"] == 0.0 and flat["flagged"] is True,
          json.dumps(flat, sort_keys=True)[:120])


# ---------------------------------------------------------- ffmpeg fixtures --

def _run(argv):
    proc = subprocess.run(argv, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg fixture failed: %r\n%s"
                           % (argv[:3], proc.stderr.decode("utf-8",
                                                           "replace")[-400:]))


def _build_clips(tmp):
    """Flash, pan-over-still, local-motion and static fixtures, 2 s each."""
    big = os.path.join(tmp, "big.png")
    still = os.path.join(tmp, "still.png")
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "testsrc2=size=1280x720:rate=1", "-frames:v", "1", big])
    _run(["ffmpeg", "-y", "-v", "error", "-i", big,
          "-vf", "crop=320:180:0:0", "-frames:v", "1", still])
    clips = {"flash": os.path.join(tmp, "flash.mp4"),
             "pan": os.path.join(tmp, "pan.mp4"),
             "local": os.path.join(tmp, "local.mp4"),
             "static": os.path.join(tmp, "static.mp4")}
    # Global luminance flash: white blended over the whole still.
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
          "-i", still, "-f", "lavfi", "-i", "color=c=white:s=320x180:r=24",
          "-filter_complex",
          "[0:v][1:v]blend=all_expr='A*(1-0.65*gt(mod(N\\,12)\\,7))"
          "+B*(0.65*gt(mod(N\\,12)\\,7))'", "-t", "2",
          "-pix_fmt", "yuv420p", clips["flash"]])
    # Global pan over a still image: pure translation, no subject motion.
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
          "-i", big, "-vf", "crop=320:180:x='(iw-320)*(t/2)':y=0",
          "-t", "2", "-pix_fmt", "yuv420p", clips["pan"]])
    # Genuine local motion: a bright block travels across a static frame.
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
          "-i", still, "-f", "lavfi", "-i", "color=c=white:s=48x48:r=24",
          "-filter_complex",
          "[0:v][1:v]overlay=x='20+240*t/2':y=66", "-t", "2",
          "-pix_fmt", "yuv420p", clips["local"]])
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
          "-i", still, "-t", "2", "-pix_fmt", "yuv420p", clips["static"]])
    return clips


def test_real_clips_move_the_decision():
    tmp = tempfile.mkdtemp(prefix="motion_d3_")
    try:
        clips = _build_clips(tmp)
        scores = {}
        for name in ("flash", "pan", "local", "static"):
            scores[name] = motion_score(clip_path=clips[name])
            s = scores[name]
            print("  clip %-6s subject_motion=%.6f legacy_frame_diff=%.6f "
                  "global_luma_change=%.6f displacement=%.6f samples=%d "
                  "flagged=%s"
                  % (name, s["subject_motion_score"], s["frame_diff_score"],
                     s["global_luma_change"], s["global_displacement"],
                     s["samples"], s["flagged"]))
        check("clip sampling produced spatial evidence",
              all(s["evidence"] == "spatial" and s["samples"] >= 2
                  for s in scores.values()),
              json.dumps({k: v.get("samples") for k, v in scores.items()}))
        check("flash refused by the subject-motion gate",
              scores["flash"]["flagged"] is True
              and scores["flash"]["subject_motion_score"] < MOTION_SUBJECT_LOW,
              repr(scores["flash"]["subject_motion_score"]))
        check("flash would have PASSED the legacy mean-luma score",
              scores["flash"]["frame_diff_score"] >= MOTION_SCORE_LOW,
              repr(scores["flash"]["frame_diff_score"]))
        check("pan-over-still refused by the subject-motion gate",
              scores["pan"]["flagged"] is True
              and scores["pan"]["subject_motion_score"] < MOTION_SUBJECT_LOW,
              repr(scores["pan"]["subject_motion_score"]))
        check("pan would have PASSED the legacy mean-luma score",
              scores["pan"]["frame_diff_score"] >= MOTION_SCORE_LOW,
              repr(scores["pan"]["frame_diff_score"]))
        check("genuine local motion allowed",
              scores["local"]["flagged"] is False
              and scores["local"]["subject_motion_score"] > MOTION_SUBJECT_LOW,
              repr(scores["local"]["subject_motion_score"]))
        check("genuine local motion would have been REFUSED by the legacy score",
              scores["local"]["frame_diff_score"] < MOTION_SCORE_LOW,
              repr(scores["local"]["frame_diff_score"]))
        check("static clip refused", scores["static"]["flagged"] is True,
              repr(scores["static"]["subject_motion_score"]))

        rows = [{"clip_id": k, "motion_score": scores[k]}
                for k in ("flash", "pan", "local", "static")]
        res = gate_clips(rows)
        check("gate rejects flash and pan before assembly",
              res["outcome"] == "rejected"
              and res["reason_code"] == CLIP_LOW_MOTION
              and res["flagged"] == ["flash", "pan", "static"],
              json.dumps(res)[:200])
        ok = gate_clips([{"clip_id": "local",
                          "motion_score": scores["local"]}])
        check("gate passes genuine motion", ok["outcome"] == "ok",
              json.dumps(ok)[:160])
        check("gate reports the spatial threshold it decided on",
              res["threshold"] == MOTION_SUBJECT_LOW
              and res["legacy_threshold"] == MOTION_SCORE_LOW,
              repr((res["threshold"], res["legacy_threshold"])))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------- gate semantics --

def test_fail_closed_semantics_preserved():
    local = motion_score(frame_grids=[
        _moving_block(_pattern(), 12), _moving_block(_pattern(), 24)])
    flash = motion_score(frame_grids=[_pattern(), _flash_grid(_pattern())])

    # Missing evidence: unchanged — listed as unscored, never guessed.
    res = gate_clips([{"src": "no-score"}])
    check("missing evidence is listed unscored (unchanged)",
          res["unscored"] == ["no-score"] and res["flagged"] == [],
          json.dumps(res)[:160])

    # Malformed evidence: unchanged — raises fail-closed.
    for label, ms in (
            ("legacy string score", "high"),
            ("spatial without subject score",
             {"score": 0.5, "evidence": "spatial"}),
            ("spatial subject out of range",
             {"score": 0.5, "evidence": "spatial",
              "subject_motion_score": 1.5}),
            ("spatial subject not numeric",
             {"score": 0.5, "evidence": "spatial",
              "subject_motion_score": "moving"}),
            ("unknown evidence tag",
             {"score": 0.5, "evidence": "vibes"}),
            ("non-dict score", 0.5)):
        try:
            gate_clips([{"src": "bad", "motion_score": ms}])
            check("%s fails closed" % label, False, "no raise")
        except MotionScoreError as e:
            check("%s fails closed" % label, e.code == "CLIP_UNSCORED", e.code)

    # Measured sub-threshold still refuses even when the row claims flagged:false.
    spoof = dict(flash)
    spoof["flagged"] = False
    res2 = gate_clips([{"src": "spoof", "motion_score": spoof}])
    check("measured sub-threshold spatial score overrides flagged:false",
          res2["flagged"] == ["spoof"], json.dumps(res2)[:160])
    legacy = {"score": 0.001, "flagged": False}
    res3 = gate_clips([{"src": "legacy-low", "motion_score": legacy}])
    check("measured sub-threshold legacy score still refuses (F12 repair)",
          res3["flagged"] == ["legacy-low"], json.dumps(res3)[:160])
    # A stricter supplied verdict is never loosened.
    stricter = dict(local)
    stricter["flagged"] = True
    res4 = gate_clips([{"src": "stricter", "motion_score": stricter}])
    check("flagged:true is still honoured", res4["flagged"] == ["stricter"],
          json.dumps(res4)[:160])
    # 1.0.0 receipts (no evidence tag) keep the legacy decision.
    res5 = gate_clips([{"src": "old-pass", "motion_score": {"score": 0.5}},
                       {"src": "old-fail",
                        "motion_score": {"score": 0.001}}])
    check("legacy receipts keep the legacy decision",
          res5["flagged"] == ["old-fail"], json.dumps(res5)[:160])
    # frame_diff_score alone must never gate a spatial row.
    check("legacy helper still scores flat mean-luma rows",
          frame_diff_score([40.0, 52.0]) > MOTION_SCORE_LOW,
          repr(frame_diff_score([40.0, 52.0])))


def test_thresholds_and_version():
    check("subject threshold is 0.012", MOTION_SUBJECT_LOW == 0.012,
          repr(MOTION_SUBJECT_LOW))
    check("legacy threshold is unchanged at 0.02", MOTION_SCORE_LOW == 0.02,
          repr(MOTION_SCORE_LOW))
    check("spatial grid is 48x27", SPATIAL_GRID == (48, 27),
          repr(SPATIAL_GRID))


def main():
    for fn in (test_thresholds_and_version,
               test_pure_grids_discriminate,
               test_real_clips_move_the_decision,
               test_fail_closed_semantics_preserved):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        print("D3 FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all D3 spatial motion tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
