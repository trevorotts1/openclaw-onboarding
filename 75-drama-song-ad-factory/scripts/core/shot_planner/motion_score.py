"""motion_score.py: F12 clips must move — frame-diff motion score per clip.

Manual Part F F12: "Characters barely moved. Clip prompts ask for motion;
flag clips with almost no frame-to-frame change. Done when: each clip has a
motion score in the receipt and low-motion clips are flagged before
assembly."

The score is a pure function over provided frame stats: tests (and the QC
layer) pass frame_stats in, no real video is ever read here. The optional
default stub samples a real clip with ffmpeg only when frame_stats is None
and a clip_path is given — never in tests; callers that cannot sample pass
frame_stats and keep this module offline.

Threshold: MOTION_SCORE_LOW = 0.02 mean frame-to-frame change (the same
2%-of-scale band fps_conform uses for its duplicated-frames cap
DUP_FRAMES_CAP = 2.0). A clip whose sampled frames differ by less than 2%
of pixel range between neighbours is a near-still clip: flagged
CLIP_LOW_MOTION before assembly. Stdlib only, $0 spend, no network.
"""
from __future__ import annotations

#: Below this mean normalized frame-to-frame change a clip is near-still.
#: Matches fps_conform.DUP_FRAMES_CAP's 2% band (same scale: 0.0-1.0).
MOTION_SCORE_LOW = 0.02

#: Reason code the receipt and the pre-assembly gate carry.
CLIP_LOW_MOTION = "CLIP_LOW_MOTION"

TOOL_NAME = "motion_score"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"


class MotionScoreError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def frame_diff_score(frame_stats):
    """Mean normalized frame-to-frame change from provided frame stats.

    frame_stats: a sequence of length-3-or-more rows [t, mean, min, ...]
    per sampled frame (any extra columns ignored) OR a flat list of mean
    ints/floats (0-255 scale). Pure: nothing is read, nothing is spent.
    raises MotionScoreError BAD_FRAME_STATS on anything unscorable.
    Returns the mean absolute neighbour difference normalized to 0.0-1.0.
    """
    if not isinstance(frame_stats, (list, tuple)) or len(frame_stats) < 2:
        raise MotionScoreError("BAD_FRAME_STATS",
                               "frame_stats needs at least 2 sampled frames")
    means = []
    for row in frame_stats:
        if isinstance(row, (list, tuple)):
            # [t, mean, ...] rows carry the frame mean at index 1; a bare
            # [mean] row (or a flat list of means) carries it at index 0.
            if len(row) >= 2 and _is_num(row[1]):
                means.append(float(row[1]))
            elif len(row) >= 1 and _is_num(row[0]):
                means.append(float(row[0]))
            else:
                raise MotionScoreError("BAD_FRAME_STATS",
                                       "each row needs numeric values")
        elif _is_num(row):
            means.append(float(row))
        else:
            raise MotionScoreError("BAD_FRAME_STATS",
                                   "frame_stats rows must be numeric")
    diffs = [abs(means[i + 1] - means[i]) for i in range(len(means) - 1)]
    if not diffs:
        raise MotionScoreError("BAD_FRAME_STATS", "no differences computed")
    score = sum(diffs) / len(diffs)
    # Sampled luma means live on the 0-255 pixel scale; any mean above 1.0
    # marks that scale (already-normalized input stays 0.0-1.0 untouched).
    scale = 255.0 if max(means) > 1.0 else 1.0
    return score / scale


def motion_score(clip_path=None, frame_stats=None):
    """Pluggable motion score: {'score': float, 'flagged': bool}.

    frame_stats given  -> pure function over the provided stats (the test
                          path; no file is opened, $0, no ffmpeg).
    frame_stats absent -> default frame-diff stub samples the real clip
                          with ffmpeg signalstats (only when a clip_path is
                          supplied); MotionScoreError CLIP_UNREADABLE when
                          the stub cannot answer, never a guessed score.
    flagged is True exactly when score < MOTION_SCORE_LOW (F12 threshold).
    """
    if frame_stats is not None:
        score = frame_diff_score(frame_stats)
    elif clip_path:
        score = frame_diff_score(_sample_clip(clip_path))
    else:
        raise MotionScoreError("CLIP_UNREADABLE",
                               "motion_score needs frame_stats or clip_path")
    return {"score": round(score, 6),
            "flagged": bool(score < MOTION_SCORE_LOW),
            "threshold": MOTION_SCORE_LOW,
            "tool_version": TOOL_VERSION}


def _sample_clip(clip_path, samples=6):
    """Default stub: sample N frames' mean luma via ffmpeg signalstats.

    Subprocess argv arrays only (never a shell string); raises
    MotionScoreError CLIP_UNREADABLE on any failure — callers who cannot
    run ffmpeg pass frame_stats instead and never reach this.
    """
    import subprocess
    cmd = ["ffmpeg", "-v", "info", "-i", str(clip_path),
           "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
           "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MotionScoreError("CLIP_UNREADABLE", str(exc)) from exc
    if proc.returncode != 0:
        raise MotionScoreError("CLIP_UNREADABLE",
                               (proc.stderr or "")[-200:])
    import re
    yavg = []
    for m in re.finditer(r"YAVG=([0-9.]+)", proc.stderr or ""):
        yavg.append(float(m.group(1)))
    if len(yavg) < 2:
        raise MotionScoreError("CLIP_UNREADABLE",
                               "sampled fewer than 2 frames from the clip")
    step = max(1, len(yavg) // samples)
    return [[i, y] for i, y in enumerate(yavg[::step])]


def gate_clips(clips):
    """F12 pre-assembly gate over clip rows (plan segments or receipt rows).

    clips: [{clip_id|shot_id|src, motion_score: {'score', 'flagged'...}}].
    Rows carrying a score below MOTION_SCORE_LOW are flagged -> outcome
    'rejected' with reason CLIP_LOW_MOTION (blocks before any render
    spend). Rows without a motion_score key are listed in 'unscored' and
    reported in the receipt — the QC review layer reads a non-empty
    unscored list as FAIL (same seam E6 uses: the assembler never scores
    video itself; the scoring step does), while a MALFORMED score row
    (non-dict, or a non-numeric score) raises MotionScoreError
    CLIP_UNSCORED fail-closed. Returns
    {'outcome', 'reason_code', 'flagged': [ids], 'unscored': [ids],
    'scores': {id: score}, 'threshold'}.
    """
    if not isinstance(clips, list) or not clips:
        raise MotionScoreError("CLIPS_EMPTY", "clips must be a non-empty list")
    flagged, unscored, scores = [], [], {}
    for c in clips:
        if not isinstance(c, dict):
            raise MotionScoreError("CLIP_UNSCORED", "clip row not a record")
        cid = c.get("clip_id") or c.get("shot_id") or c.get("src") or ""
        cid = str(cid)
        ms = c.get("motion_score")
        if ms is None:
            unscored.append(cid)
            continue
        if not isinstance(ms, dict) or not _is_num(ms.get("score")):
            raise MotionScoreError("CLIP_UNSCORED",
                                   "%s carries a malformed motion score" % cid)
        scores[cid] = ms["score"]
        # Trust the row's own flagged verdict when present; recompute when
        # absent, so receipts written by motion_score() stay authoritative.
        if ms.get("flagged") is True or (
                not isinstance(ms.get("flagged"), bool)
                and ms["score"] < MOTION_SCORE_LOW):
            flagged.append(cid)
    return {"outcome": "ok" if not flagged else "rejected",
            "reason_code": "CLIPS_MOTION_PASS" if not flagged
            else CLIP_LOW_MOTION,
            "flagged": flagged, "unscored": unscored, "scores": scores,
            "threshold": MOTION_SCORE_LOW}


def to_motion_qc_record(clips, reviewer, run_id, stage="final_edit",
                        check_id="f12-clip-motion", checker_version=TOOL_VERSION):
    """qc-schema verdict record over gate_clips (17.6: reviewer differs).

    reviewer must carry identity/session/authority. Returns the record the
    delivery gate reads; FAIL exactly when any clip is flagged.
    """
    if not isinstance(reviewer, dict):
        raise MotionScoreError("BAD_INPUT", "reviewer must be an object")
    result = gate_clips(clips)
    fail = result["flagged"] or result["unscored"]
    return {
        "schema_version": SCHEMA_VERSION, "check_id": check_id,
        "run_id": run_id, "stage": stage, "check": "clip_motion",
        "verdict": "PASS" if not fail else "FAIL",
        "evidence": {
            "summary": "clip-motion %s: %d clip(s)%s%s" % (
                result["outcome"], len(result["scores"]),
                "" if not result["flagged"] else
                " flagged=%s" % ",".join(result["flagged"]),
                "" if not result["unscored"] else
                " unscored=%s" % ",".join(result["unscored"])),
            "refs": []},
        "reason_code": result["reason_code"] if not result["unscored"]
        else CLIP_LOW_MOTION,
        "checker_version": checker_version, "reviewer": reviewer,
    }


def attach_motion_scores(plan_or_clips, scores):
    """Attach motion scores to plan segments (or clip rows) in place.

    scores: {clip_id_or_src: {'score', 'flagged', ...}} — the motion_score()
    output keyed by clip id or src. Rows matching neither key stay unscored
    (gate_clips fails closed on them). Returns the input for chaining.
    """
    if not isinstance(scores, dict):
        raise MotionScoreError("BAD_INPUT", "scores must be a dict")
    for row in plan_or_clips:
        if not isinstance(row, dict):
            continue
        key = row.get("source_clip_id") or row.get("clip_id") \
            or row.get("src")
        if key is not None and key in scores:
            row["motion_score"] = scores[key]
    return plan_or_clips