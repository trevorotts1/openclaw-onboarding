"""motion_score.py: F12 clips must move — spatial subject-motion score per clip.

Manual Part F F12: "Characters barely moved. Clip prompts ask for motion;
flag clips with almost no frame-to-frame change. Done when: each clip has a
motion score in the receipt and low-motion clips are flagged before
assembly."

Two measures, one gate:

* SUBJECT MOTION (the gate's decision) — frame differencing on a 48x27
  grayscale grid sampled at 15 fps. For each consecutive pair the global
  luminance offset+gain is fitted away (so a flash/exposure change scores
  zero) and the best global translation is searched on a stride-2 lattice
  with quarter-pixel refinement (so a pan/global camera move scores zero).
  What remains is local, non-translational change: subject motion.
  MOTION_SUBJECT_LOW = 0.012 normalized residual was calibrated on real
  ffmpeg fixtures (see test_motion_d3_spatial.py): static 0.000, coded
  noise 0.002, flash 0.003, pan 0.004, handheld shake 0.009, moving
  subject 0.026.
* LEGACY MEAN LUMA (kept for callers that still consume it) —
  MOTION_SCORE_LOW = 0.02 mean frame-to-frame change of per-frame mean
  luma, unchanged from 1.0.0. A flash or a pan scores HIGH on this one,
  which is exactly why the gate no longer decides on it.

Scores are pure functions over provided data: tests pass frame_stats
(legacy rows) or frame_grids (spatial frames), no video is read. The
default stub samples a real clip with ffmpeg only when neither is given
and a clip_path is supplied; MotionScoreError CLIP_UNREADABLE when it
cannot answer, never a guessed score. Stdlib only, $0 spend, no network.
"""
from __future__ import annotations

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

#: Legacy threshold: below this mean normalized frame-to-frame change of
#: per-frame mean luma a clip is near-still. Matches
#: fps_conform.DUP_FRAMES_CAP's 2% band (same scale: 0.0-1.0).
MOTION_SCORE_LOW = 0.02

#: Gate threshold on the spatial subject-motion score. Calibrated on ffmpeg
#: fixtures (test_motion_d3_spatial.py): non-subject cases 0.000-0.009,
#: genuine local motion 0.026.
MOTION_SUBJECT_LOW = 0.012

#: Spatial evidence sampler: grayscale grid per frame, sampled frames/second.
SPATIAL_GRID = (48, 27)
SPATIAL_FPS = 15

#: Reason code the receipt and the pre-assembly gate carry.
CLIP_LOW_MOTION = "CLIP_LOW_MOTION"

TOOL_NAME = "motion_score"
TOOL_VERSION = "2.0.0"
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


def _check_grids(grids, width, height):
    """Validate frame grids; MotionScoreError BAD_FRAME_STATS on anything
    unscorable (fail closed, never a guessed score)."""
    if not isinstance(grids, (list, tuple)) or len(grids) < 2:
        raise MotionScoreError("BAD_FRAME_STATS",
                               "frame_grids needs at least 2 frames")
    size = width * height
    if width < 8 or height < 8:
        raise MotionScoreError("BAD_FRAME_STATS",
                               "grid %dx%d cannot carry spatial evidence"
                               % (width, height))
    for g in grids:
        if not isinstance(g, (list, tuple)) or len(g) != size:
            raise MotionScoreError("BAD_FRAME_STATS",
                                   "each frame grid needs %d values" % size)
        for v in g:
            if not _is_num(v):
                raise MotionScoreError("BAD_FRAME_STATS",
                                       "frame grid values must be numeric")


def _shift_limit(width):
    """Search radius and interior margin for one grid width."""
    shift = max(1, int(round(width * 0.17)))
    return shift, shift + 2


def _dc(grid):
    mean = sum(grid) / len(grid)
    return [v - mean for v in grid], mean


def _bilinear(g, w, x, y):
    x0 = int(x // 1)
    y0 = int(y // 1)
    fx = x - x0
    fy = y - y0
    i = y0 * w + x0
    return (g[i] * (1 - fx) * (1 - fy) + g[i + 1] * fx * (1 - fy)
            + g[i + w] * (1 - fx) * fy + g[i + w + 1] * fx * fy)


def _corr(a, b, w, x0, x1, y0, y1, dx, dy, sb, sbb, n):
    """Pearson correlation of the interior at one candidate shift.

    Correlation, not raw L1: it is invariant to the per-frame offset AND
    gain, so a flash cannot offer the search a spurious translation and a
    pan still peaks at its true shift.
    """
    sa = saa = sab = 0.0
    for y in range(y0, y1 + 1):
        row = y * w
        for x in range(x0, x1 + 1):
            av = _bilinear(a, w, x - dx, y - dy)
            bv = b[row + x]
            sa += av
            saa += av * av
            sab += av * bv
    num = n * sab - sa * sb
    va = max(0.0, n * saa - sa * sa)
    vb = max(0.0, n * sbb - sb * sb)
    den = (va * vb) ** 0.5
    return num / den if den > 1e-9 else 0.0


def _best_shift(a, b, w, h):
    """Best global translation between two DC-removed grids.

    Stride-2 correlation lattice over the full search radius, then +/-1 and
    half/quarter-pixel refinement of the four best cells: a global pan must
    compensate or it would be read as subject motion.
    """
    shift, margin = _shift_limit(w)
    x0, x1 = margin, w - margin - 1
    y0, y1 = margin, h - margin - 1
    n = float((x1 - x0 + 1) * (y1 - y0 + 1))
    sb = sbb = 0.0
    for y in range(y0, y1 + 1):
        row = y * w
        for x in range(x0, x1 + 1):
            bv = b[row + x]
            sb += bv
            sbb += bv * bv
    cands = []
    for dy in range(-shift, shift + 1, 2):
        for dx in range(-shift, shift + 1, 2):
            c = _corr(a, b, w, x0, x1, y0, y1, dx, dy, sb, sbb, n)
            cands.append((c, float(dx), float(dy)))
    cands.sort(reverse=True)
    # Refine around the K best lattice cells, not just the top one: a
    # near-periodic frame can score a spurious cell between lattice points
    # and the true shift has to stay reachable.
    for c0, bx0, by0 in cands[:4]:
        best = (c0, bx0, by0)
        bx, by = int(bx0), int(by0)
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                c = _corr(a, b, w, x0, x1, y0, y1, bx + dx, by + dy,
                          sb, sbb, n)
                if c > best[0]:
                    best = (c, float(bx + dx), float(by + dy))
        for step in (0.5, 0.25):
            bx, by = best[1], best[2]
            for sdy in (-step, 0.0, step):
                for sdx in (-step, 0.0, step):
                    c = _corr(a, b, w, x0, x1, y0, y1, bx + sdx, by + sdy,
                              sb, sbb, n)
                    if c > best[0]:
                        best = (c, bx + sdx, by + sdy)
        if best[0] > cands[0][0]:
            cands[0] = best
    return cands[0]


def _affine_residual(a, b, w, h, dx, dy):
    """Mean |b - (g*a + o)| over the interior after the best global shift.

    g/o are fitted per pair, so a global luminance offset (additive flash)
    or gain (exposure/contrast flash) is absorbed instead of counted as
    motion.
    """
    _, margin = _shift_limit(w)
    av, bv = [], []
    for y in range(margin, h - margin):
        row = y * w
        for x in range(margin, w - margin):
            av.append(_bilinear(a, w, x - dx, y - dy))
            bv.append(b[row + x])
    n = len(av)
    ma = sum(av) / n
    mb = sum(bv) / n
    cov = sum((av[k] - ma) * (bv[k] - mb) for k in range(n)) / n
    var = sum((av[k] - ma) ** 2 for k in range(n)) / n
    gain = cov / var if var > 1e-9 else 1.0
    off = mb - gain * ma
    return sum(abs(bv[k] - (gain * av[k] + off)) for k in range(n)) / n


def subject_motion_evidence(frame_grids, grid_size=None):
    """Pure spatial evidence over per-frame grayscale grids.

    frame_grids: >=2 frames, each a flat w*h sequence of 0-255 values, in
    time order. Returns the measured numbers as data (0.0-1.0 scale):
      subject_motion_score - local change left after removing global
                             luminance offset+gain and best global
                             translation; the value the gate decides on.
      frame_diff_score     - legacy mean |delta per-frame mean luma|, kept
                             for callers still consuming the old score.
      global_luma_change   - same signal named for what it is: a flash or
                             exposure change, not motion.
      global_displacement  - mean best global shift, frame widths per pair.
      samples, grid        - what was measured.
    raises MotionScoreError BAD_FRAME_STATS on any unscorable input.
    """
    w, h = grid_size or SPATIAL_GRID
    _check_grids(frame_grids, w, h)
    prev, prev_mean = _dc(frame_grids[0])
    subjects, lumas, disps = [], [], []
    for raw in frame_grids[1:]:
        cur, cur_mean = _dc(raw)
        _, dx, dy = _best_shift(prev, cur, w, h)
        resid = _affine_residual(prev, cur, w, h, dx, dy)
        subjects.append(resid / 255.0)
        lumas.append(abs(cur_mean - prev_mean) / 255.0)
        disps.append(((dx * dx + dy * dy) ** 0.5) / w)
        prev, prev_mean = cur, cur_mean
    pairs = float(len(subjects))
    return {
        "subject_motion_score": round(sum(subjects) / pairs, 6),
        "frame_diff_score": round(sum(lumas) / pairs, 6),
        "global_luma_change": round(sum(lumas) / pairs, 6),
        "global_displacement": round(sum(disps) / pairs, 6),
        "samples": len(frame_grids),
        "grid": [w, h],
    }

def motion_score(clip_path=None, frame_stats=None, frame_grids=None,
                 grid_size=None):
    """Pluggable motion score: {'score': float, 'flagged': bool, ...}.

    frame_grids given  -> SPATIAL evidence (the gate's decision path):
                          score is subject_motion_score, threshold is
                          MOTION_SUBJECT_LOW, and the legacy frame_diff_score
                          rides along as data.
    frame_stats given  -> LEGACY pure function over per-frame mean luma
                          (no file opened, $0, no ffmpeg).
    neither given, clip_path given -> spatial sampling of the real clip
                          with ffmpeg; MotionScoreError CLIP_UNREADABLE when
                          it cannot answer, never a guessed score.
    flagged is True exactly when the measured score on the evidence path
    used is below its threshold.
    """
    if frame_grids is not None:
        ev = subject_motion_evidence(frame_grids, grid_size=grid_size)
        return {"score": ev["subject_motion_score"],
                "flagged": bool(ev["subject_motion_score"]
                                < MOTION_SUBJECT_LOW),
                "threshold": MOTION_SUBJECT_LOW,
                "evidence": "spatial",
                **ev,
                "tool_version": TOOL_VERSION}
    if frame_stats is not None:
        score = frame_diff_score(frame_stats)
        return {"score": round(score, 6),
                "flagged": bool(score < MOTION_SCORE_LOW),
                "threshold": MOTION_SCORE_LOW,
                "evidence": "luma_only",
                "tool_version": TOOL_VERSION}
    if clip_path:
        return motion_score(frame_grids=_sample_clip_grids(clip_path))
    raise MotionScoreError("CLIP_UNREADABLE",
                           "motion_score needs frame_stats, frame_grids or "
                           "clip_path")


def _sample_clip_grids(clip_path):
    """Sample per-frame grayscale grids from a real clip with ffmpeg.

    One decode: fps -> 48x27 area downscale -> gray rawvideo on stdout.
    Subprocess argv arrays only (never a shell string); raises
    MotionScoreError CLIP_UNREADABLE on any failure — callers who cannot
    run ffmpeg pass frame_grids/frame_stats instead and never reach this.
    """
    import subprocess
    w, h = SPATIAL_GRID
    cmd = ["ffmpeg", "-v", "error", "-i", str(clip_path),
           "-vf", "fps=%d,scale=%d:%d:flags=area,format=gray"
           % (SPATIAL_FPS, w, h),
           "-an", "-f", "rawvideo", "-"]
    try:
        proc = _LG.run_ffmpeg(cmd, "motion-score-spatial",
                              capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MotionScoreError("CLIP_UNREADABLE", str(exc)) from exc
    if proc.returncode != 0:
        raise MotionScoreError("CLIP_UNREADABLE",
                               (proc.stderr or b"")[-200:].decode(
                                   "utf-8", "replace"))
    raw = proc.stdout or b""
    size = w * h
    frames = len(raw) // size
    if frames < 2:
        raise MotionScoreError("CLIP_UNREADABLE",
                               "sampled fewer than 2 frames from the clip")
    return [list(raw[i:i + size]) for i in range(0, frames * size, size)]


def gate_clips(clips):
    """F12 pre-assembly gate over clip rows (plan segments or receipt rows).

    clips: [{clip_id|shot_id|src, motion_score: {'score', 'flagged'...}}].
    The gate decides on the SPATIAL evidence when the row carries it —
    motion_score['subject_motion_score'] with evidence 'spatial' (written
    by motion_score() 2.0.0) — and flags a clip below MOTION_SUBJECT_LOW,
    so a flash or a global pan no longer passes as motion. Rows without
    spatial evidence (receipts written by 1.0.0) keep the legacy decision
    on 'score' < MOTION_SCORE_LOW, unchanged. Rows carrying neither a
    motion_score key are listed in 'unscored' and reported in the receipt
    — the QC review layer reads a non-empty unscored list as FAIL (same
    seam E6 uses: the assembler never scores video itself; the scoring
    step does). MALFORMED evidence — non-dict row, non-numeric score, a
    spatial tag without a numeric in-range subject_motion_score, or an
    unknown evidence tag — raises MotionScoreError CLIP_UNSCORED
    fail-closed. Returns
    {'outcome', 'reason_code', 'flagged': [ids], 'unscored': [ids],
    'scores': {id: gate score}, 'threshold', 'legacy_threshold'}.
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
        evidence = ms.get("evidence")
        if evidence is not None and evidence not in ("spatial", "luma_only"):
            raise MotionScoreError(
                "CLIP_UNSCORED",
                "%s carries an unknown motion evidence tag" % cid)
        subject = ms.get("subject_motion_score")
        if evidence == "spatial" or subject is not None:
            # Malformed spatial evidence refuses: a tagged row must carry a
            # numeric score on the same 0.0-1.0 scale as its threshold.
            if not _is_num(subject) or not 0.0 <= subject <= 1.0:
                raise MotionScoreError(
                    "CLIP_UNSCORED",
                    "%s carries malformed spatial motion evidence" % cid)
            measured, threshold = subject, MOTION_SUBJECT_LOW
        else:
            measured, threshold = ms["score"], MOTION_SCORE_LOW
        scores[cid] = measured
        # Fail closed on the MEASURED score: a supplied flagged:false can
        # never override a measured sub-threshold score. A supplied
        # flagged:true is still honoured, so a stricter verdict is never
        # loosened into a pass.
        if measured < threshold or ms.get("flagged") is True:
            flagged.append(cid)
    return {"outcome": "ok" if not flagged else "rejected",
            "reason_code": "CLIPS_MOTION_PASS" if not flagged
            else CLIP_LOW_MOTION,
            "flagged": flagged, "unscored": unscored, "scores": scores,
            "threshold": MOTION_SUBJECT_LOW,
            "legacy_threshold": MOTION_SCORE_LOW}


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