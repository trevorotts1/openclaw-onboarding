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
                         8 Hz full-black exposure strobe    -> refused
                         gain/contrast strobe               -> refused
                         coded noise c0s 8/48/64/80         -> refused
                         pan + local motion                 -> allowed
  pure frame grids       the same cases with exact expected geometry,
                         including a uniform-noise field that clears the
                         magnitude threshold and is refused on structure
  gate                   missing evidence, malformed evidence, degenerate
                         (unmeasurable) evidence, and measured sub-threshold
                         scores still refuse (F12 fail-closed preserved)

Run: python3 core/shot_planner/test_motion_d3_spatial.py
"""
import json
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from shot_planner.motion_score import (           # noqa: E402
    MOTION_SCORE_LOW, MOTION_SUBJECT_LOW, MOTION_STRUCTURE_MIN,
    CLIP_LOW_MOTION, CLIP_MOTION_UNMEASURABLE, SPATIAL_GRID,
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
    # Grid fixtures are pure arithmetic over a fixed formula: no encoder, no
    # sampling, so their bytes and their scores are identical on every box.
    # Measured identically on macOS (ffmpeg 9.0.2, Python 3.14.7) and on the
    # CI runner: flash legacy 0.273265 / 0.273265, pan 0.037398 / 0.037398,
    # local legacy 0.014446 / 0.014446, local subject 0.067247 / 0.067247.
    # Grids are the only class pinned exactly; encoded-clip numbers below use
    # the subject/legacy tolerances that their measured spread justifies.
    grid_calibration = (("flash", flash, 0.0, 0.273265),
                        ("pan", pan, 0.0, 0.037398),
                        ("local", local, 0.067247, 0.014446))
    for name, ev, subject, legacy in grid_calibration:
        check("%s grid reproduces its calibrated numbers" % name,
              abs(ev["subject_motion_score"] - subject) < 1e-6
              and abs(ev["frame_diff_score"] - legacy) < 1e-6,
              "%r/%r vs %r/%r" % (ev["subject_motion_score"],
                                  ev["frame_diff_score"], subject, legacy))
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


def test_pure_degenerate_and_noise():
    """Degenerate exposure frames and uniform grain must never score as motion.

    Pure grids, no ffmpeg: a zero-variance frame has no gain fit, and a
    noise field raises every tile by the same amount.
    """
    base = _pattern()
    black = [0.0] * (W * H)
    rnd = random.Random(7)
    noise = [[128.0 + rnd.gauss(0.0, 9.0) for _ in range(W * H)]
             for _ in range(8)]

    ev = subject_motion_evidence(noise)
    print("  grid noise   subject=%.6f struct=%7.2f (magnitude gate %.3f, "
          "structure gate %.1f)"
          % (ev["subject_motion_score"], ev["motion_structure"],
             MOTION_SUBJECT_LOW, MOTION_STRUCTURE_MIN))
    check("pure noise clears the magnitude threshold",
          ev["subject_motion_score"] >= MOTION_SUBJECT_LOW,
          repr(ev["subject_motion_score"]))
    check("pure noise fails the structure test",
          ev["motion_structure"] < MOTION_STRUCTURE_MIN,
          repr(ev["motion_structure"]))
    check("pure noise is flagged as a whole",
          motion_score(frame_grids=noise)["flagged"] is True,
          json.dumps(motion_score(frame_grids=noise), sort_keys=True)[:160])

    mixed = subject_motion_evidence([base, base, black, black, base, base])
    print("  grid black   subject=%.6f struct=%7.2f degen=%d valid=%d"
          % (mixed["subject_motion_score"], mixed["motion_structure"],
             mixed["degenerate_pairs"], mixed["valid_pairs"]))
    check("degenerate pairs are counted, not scored",
          mixed["degenerate_pairs"] == 3 and mixed["valid_pairs"] == 2,
          repr((mixed["degenerate_pairs"], mixed["valid_pairs"])))
    check("a black frame does not become subject motion",
          mixed["subject_motion_score"] < MOTION_SUBJECT_LOW,
          repr(mixed["subject_motion_score"]))
    check("the legacy score still reports the exposure event",
          mixed["frame_diff_score"] > MOTION_SCORE_LOW,
          repr(mixed["frame_diff_score"]))

    dark = motion_score(frame_grids=[black, black, black])
    check("an all-degenerate clip is unmeasurable, not low-motion",
          dark["unmeasurable"] is True and dark["flagged"] is True
          and dark["reason_code"] == CLIP_MOTION_UNMEASURABLE,
          json.dumps(dark, sort_keys=True)[:200])
    res = gate_clips([{"clip_id": "all-black", "motion_score": dark}])
    check("gate refuses an unmeasurable clip with its own typed reason",
          res["outcome"] == "rejected"
          and res["reason_code"] == CLIP_MOTION_UNMEASURABLE
          and res["unmeasurable"] == ["all-black"]
          and res["flagged"] == ["all-black"],
          json.dumps(res)[:200])


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
             "static": os.path.join(tmp, "static.mp4"),
             "black_strobe": os.path.join(tmp, "black_strobe.mp4"),
             "gain_strobe": os.path.join(tmp, "gain_strobe.mp4"),
             "pan_local": os.path.join(tmp, "pan_local.mp4")}
    for c in (8, 48, 64, 80):
        clips["noise%d" % c] = os.path.join(tmp, "noise%d.mp4" % c)
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
    # 8 Hz full-black exposure strobe: one frame in three collapses to black.
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
          "-i", still, "-f", "lavfi", "-i", "color=c=black:s=320x180:r=24",
          "-filter_complex",
          "[0:v][1:v]blend=all_expr='A*(1-gt(mod(N\\,3)\\,1))"
          "+B*(gt(mod(N\\,3)\\,1))'", "-t", "2",
          "-pix_fmt", "yuv420p", clips["black_strobe"]])
    # Gain-only exposure strobe (contrast, no offset).
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
          "-i", still, "-vf",
          "eq=contrast=1.6:enable='lt(mod(t\\,0.35)\\,0.12)'", "-t", "2",
          "-pix_fmt", "yuv420p", clips["gain_strobe"]])
    # Pan plus a small local subject: compensation must keep the subject.
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
          "-i", big, "-f", "lavfi", "-i", "color=c=white:s=24x24:r=24",
          "-filter_complex",
          "[0:v]crop=320:180:x='(iw-320)*(t/4)':y=0[p];"
          "[p][1:v]overlay=x='100+80*t/2':y=80", "-t", "2",
          "-pix_fmt", "yuv420p", clips["pan_local"]])
    # Coded noise sweep: grain is spatially uniform and can reach the
    # magnitude threshold; the structure test must refuse it.
    for c in (8, 48, 64, 80):
        _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24",
              "-i", still, "-vf", "noise=c0s=%d:c0f=t" % c, "-t", "2",
              "-pix_fmt", "yuv420p", clips["noise%d" % c]])
    return clips


def test_real_clips_move_the_decision():
    tmp = tempfile.mkdtemp(prefix="motion_d3_")
    try:
        clips = _build_clips(tmp)
        names = ("flash", "pan", "local", "static", "black_strobe",
                 "gain_strobe", "pan_local", "noise8", "noise48",
                 "noise64", "noise80")
        scores = {}
        for name in names:
            scores[name] = motion_score(clip_path=clips[name])
            s = scores[name]
            print("  clip %-12s subject=%.6f struct=%7.2f degen=%2d valid=%2d "
                  "legacy=%.6f flagged=%s"
                  % (name, s["subject_motion_score"], s["motion_structure"],
                     s["degenerate_pairs"], s["valid_pairs"],
                     s["frame_diff_score"], s["flagged"]))
        check("clip sampling produced spatial evidence",
              all(s["evidence"] == "spatial" and s["samples"] >= 2
                  for s in scores.values()),
              json.dumps({k: v.get("samples") for k, v in scores.items()}))
        # Clip numbers split into two classes, measured on macOS (ffmpeg 9.0.2,
        # Python 3.14.7) and on the Ubuntu CI runner:
        #
        # Subject term is stable across environments; keep it exact.
        #   flash 0.000369 / 0.000439 (+7.0e-5)
        #   pan   0.000190 / 0.000190 (  0    )
        #   local 0.026011 / 0.025899 (-1.1e-4)   <- widest, 4.5x inside 5e-4
        #
        # Legacy mean-luma term moves with the encoder build and is not
        # exact-pinnable. This is the drift that failed CI:
        #   flash 0.106209 / 0.107116 (+9.1e-4 = 0.86% of value)
        #   pan   0.044635 / 0.044655 (+2.0e-5)
        #   local 0.000549 / 0.000544 (-5.0e-6)
        # So the legacy number is asserted on a 5% band, 5.8x the widest
        # measured spread (plus a 1e-5 floor over the 1e-6 rounding step),
        # which still goes red on any semantic change.
        for name, subject, legacy in (
                ("flash", 0.000369, 0.106209),
                ("pan", 0.000190, 0.044635),
                ("local", 0.026011, 0.000549)):
            s = scores[name]
            check("%s reproduces its calibrated subject score" % name,
                  abs(s["subject_motion_score"] - subject) < 5e-4,
                  "%r vs %r" % (s["subject_motion_score"], subject))
            check("%s keeps its calibrated legacy score" % name,
                  abs(s["frame_diff_score"] - legacy)
                  <= max(1e-5, 0.05 * abs(legacy)),
                  "%r vs %r (measured spread 9.1e-4 worst case)"
                  % (s["frame_diff_score"], legacy))
        for name in ("flash", "pan"):
            s = scores[name]
            check("%s is refused with a 2x margin, not merely below the gate"
                  % name,
                  s["flagged"] is True
                  and s["subject_motion_score"] <= MOTION_SUBJECT_LOW / 2,
                  "%r (gate %r)" % (s["subject_motion_score"],
                                    MOTION_SUBJECT_LOW))
        # A still loop encodes identical frames, so zero is structural, not
        # calibrated: both environments measured exactly 0.0.
        for name in ("static",):
            s = scores[name]
            check("%s is exactly zero for both scores" % name,
                  s["subject_motion_score"] == 0.0
                  and s["frame_diff_score"] == 0.0,
                  "%r/%r" % (s["subject_motion_score"],
                             s["frame_diff_score"]))
        check("local is allowed with a 2x margin above the gate",
              scores["local"]["flagged"] is False
              and scores["local"]["subject_motion_score"]
              >= MOTION_SUBJECT_LOW * 2,
              repr(scores["local"]["subject_motion_score"]))
        check("genuine local motion clears the structure test",
              scores["local"]["motion_structure"] > MOTION_STRUCTURE_MIN,
              repr(scores["local"]["motion_structure"]))
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
        check("pan compensation still saw its flat frames (degenerate count)",
              scores["pan"]["degenerate_pairs"] >= 1,
              repr(scores["pan"]["degenerate_pairs"]))
        check("genuine local motion allowed",
              scores["local"]["flagged"] is False
              and scores["local"]["subject_motion_score"] > MOTION_SUBJECT_LOW,
              repr(scores["local"]["subject_motion_score"]))
        check("genuine local motion would have been REFUSED by the legacy score",
              scores["local"]["frame_diff_score"] < MOTION_SCORE_LOW,
              repr(scores["local"]["frame_diff_score"]))
        check("static clip refused", scores["static"]["flagged"] is True,
              repr(scores["static"]["subject_motion_score"]))
        # Pan + small subject: compensation removes the pan, keeps the subject.
        check("pan + local motion is allowed",
              scores["pan_local"]["flagged"] is False
              and scores["pan_local"]["subject_motion_score"]
              > MOTION_SUBJECT_LOW,
              repr(scores["pan_local"]["subject_motion_score"]))
        check("pan + local motion is not the pure-pan number",
              scores["pan_local"]["subject_motion_score"]
              > 10 * max(1e-6, scores["pan"]["subject_motion_score"]),
              "%r vs %r" % (scores["pan_local"]["subject_motion_score"],
                            scores["pan"]["subject_motion_score"]))
        # Whole-frame black strobe: an exposure event, never subject motion.
        bs = scores["black_strobe"]
        check("8 Hz black strobe is refused",
              bs["flagged"] is True
              and bs["subject_motion_score"] < MOTION_SUBJECT_LOW,
              repr(bs["subject_motion_score"]))
        check("black strobe counts its degenerate pairs",
              bs["degenerate_pairs"] >= 10 and bs["valid_pairs"] >= 1,
              repr((bs["degenerate_pairs"], bs["valid_pairs"])))
        check("black strobe still carries the legacy exposure signature",
              bs["frame_diff_score"] >= MOTION_SCORE_LOW,
              repr(bs["frame_diff_score"]))
        check("gain strobe is refused", scores["gain_strobe"]["flagged"] is True,
              repr(scores["gain_strobe"]["subject_motion_score"]))
        # Noise sweep: the heavier fields clear the magnitude threshold and
        # must be refused on structure.
        for name in ("noise8", "noise48", "noise64", "noise80"):
            s = scores[name]
            check("%s refused (magnitude or structure)" % name,
                  s["flagged"] is True,
                  json.dumps({k: s[k] for k in ("subject_motion_score",
                                                "motion_structure")}))
        for name in ("noise48", "noise64", "noise80"):
            s = scores[name]
            check("%s clears the magnitude threshold but fails structure"
                  % name,
                  s["subject_motion_score"] >= MOTION_SUBJECT_LOW
                  and s["motion_structure"] < MOTION_STRUCTURE_MIN,
                  json.dumps({k: s[k] for k in ("subject_motion_score",
                                                "motion_structure")}))

        rows = [{"clip_id": k, "motion_score": scores[k]}
                for k in ("flash", "pan", "local", "static", "black_strobe",
                          "noise64")]
        res = gate_clips(rows)
        check("gate rejects flash, pan, static, black strobe and noise",
              res["outcome"] == "rejected"
              and res["reason_code"] == CLIP_LOW_MOTION
              and res["flagged"] == ["flash", "pan", "static",
                                     "black_strobe", "noise64"],
              json.dumps(res)[:220])
        ok = gate_clips([{"clip_id": "local",
                          "motion_score": scores["local"]},
                         {"clip_id": "pan_local",
                          "motion_score": scores["pan_local"]}])
        check("gate passes genuine motion and pan+local", ok["outcome"] == "ok",
              json.dumps(ok)[:160])
        check("gate reports the thresholds it decided on",
              res["threshold"] == MOTION_SUBJECT_LOW
              and res["structure_threshold"] == MOTION_STRUCTURE_MIN
              and res["legacy_threshold"] == MOTION_SCORE_LOW,
              repr((res["threshold"], res["structure_threshold"],
                    res["legacy_threshold"])))
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
            ("spatial without structure score",
             {"score": 0.5, "evidence": "spatial",
              "subject_motion_score": 0.5}),
            ("spatial structure not numeric",
             {"score": 0.5, "evidence": "spatial",
              "subject_motion_score": 0.5, "motion_structure": "wide"}),
            ("spatial subject out of range",
             {"score": 0.5, "evidence": "spatial",
              "subject_motion_score": 1.5, "motion_structure": 9.0}),
            ("spatial subject not numeric",
             {"score": 0.5, "evidence": "spatial",
              "subject_motion_score": "moving", "motion_structure": 9.0}),
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

    # A structure failure is a measured refusal too, and flagged:false
    # cannot override it.
    weak = {"score": 0.03, "evidence": "spatial",
            "subject_motion_score": 0.03, "motion_structure": 1.5,
            "flagged": False}
    res6 = gate_clips([{"src": "grain", "motion_score": weak}])
    check("a noise-like residual is refused even with flagged:false",
          res6["flagged"] == ["grain"], json.dumps(res6)[:160])

    # The magnitude gate flips exactly once, strictly below the threshold.
    boundary = []
    for subj in (0.011999, MOTION_SUBJECT_LOW, 0.012001):
        row = {"score": subj, "evidence": "spatial",
               "subject_motion_score": subj, "motion_structure": 9.0}
        boundary.append(gate_clips([{"src": "b", "motion_score": row}])
                        ["flagged"] == ["b"])
    check("near-threshold flips exactly at MOTION_SUBJECT_LOW",
          boundary == [True, False, False], repr(boundary))


def test_thresholds_and_version():
    check("subject threshold is 0.012", MOTION_SUBJECT_LOW == 0.012,
          repr(MOTION_SUBJECT_LOW))
    check("structure threshold is 4.0", MOTION_STRUCTURE_MIN == 4.0,
          repr(MOTION_STRUCTURE_MIN))
    check("legacy threshold is unchanged at 0.02", MOTION_SCORE_LOW == 0.02,
          repr(MOTION_SCORE_LOW))
    check("spatial grid is 48x27", SPATIAL_GRID == (48, 27),
          repr(SPATIAL_GRID))


def main():
    for fn in (test_thresholds_and_version,
               test_pure_grids_discriminate,
               test_pure_degenerate_and_noise,
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
