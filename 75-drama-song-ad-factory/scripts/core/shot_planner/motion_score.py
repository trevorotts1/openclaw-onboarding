"""motion_score.py: F12 clips must move — spatial subject-motion score per clip.

Manual Part F F12: "Characters barely moved. Clip prompts ask for motion;
flag clips with almost no frame-to-frame change. Done when: each clip has a
motion score in the receipt and low-motion clips are flagged before
assembly."

Two measures, one gate:

* SUBJECT MOTION (the gate's decision) — frame differencing on a 48x27
  grayscale grid sampled at 15 fps. For each consecutive pair a global
  luminance offset+gain is fitted and subtracted, and the best global
  translation is searched on a stride-2 correlation lattice with
  quarter-pixel refinement. What remains is local, non-translational
  change: subject motion. Two things this does and does NOT absorb:
    - Absorbs an additive flash and a gain/contrast flash, PROVIDED both
      frames carry measurable contrast (a gain fit cannot exist otherwise).
    - Absorbs a pure camera pan/translation.
    - Does NOT absorb a frame collapsed to near-uniform luma (black,
      white, blank): there is no contrast to fit, so that pair is an
      exposure event and contributes ZERO motion evidence — never the
      content amplitude. Every degenerate pair is counted; a clip whose
      every pair is degenerate is `unmeasurable` and is refused with the
      typed reason CLIP_MOTION_UNMEASURABLE.
    - Does NOT absorb global zoom or rotation: those are read as motion.
  MOTION_SUBJECT_LOW = 0.012 normalized residual was calibrated on real
  ffmpeg fixtures (see test_motion_d3_spatial.py): static 0.000, coded
  noise 0.002-0.031 (see the structure test), flash 0.003, pan 0.004,
  handheld shake 0.009, moving subject 0.026-0.036.
* RESIDUAL STRUCTURE — p90/p20 of 4x3 tile means over the residual map.
  Coded grain raises every tile by about the same amount, so a noise field
  can reach the magnitude threshold; MOTION_STRUCTURE_MIN = 4.0 refuses
  it because grain is not concentrated (measured 1.7-2.4) while moving
  content is (measured 9.5-338). The gate requires magnitude AND
  structure, so grain cannot pass as motion. A non-rigid motion whose
  residual genuinely fills every tile is refused (fail-closed).
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

import math

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

#: Minimum spatial concentration of the residual: p90/p20 of 4x3 tile
#: means over the overlap. Coded grain spreads evenly (measured 1.7-2.4)
#: while moving content concentrates (measured 9.5-338), so grain of
#: gate-crossing magnitude is refused on structure, not on mean brightness.
MOTION_STRUCTURE_MIN = 4.0

#: A frame whose interior contrast falls below this many luma units is an
#: exposure collapse (black/white/blank): the per-pair gain fit does not
#: exist and the pair carries no motion evidence.
DEGENERATE_CONTRAST = 2.0

#: Spatial evidence sampler: grayscale grid per frame, sampled frames/second.
SPATIAL_GRID = (48, 27)
SPATIAL_FPS = 15

#: Reason code the receipt and the pre-assembly gate carry.
CLIP_LOW_MOTION = "CLIP_LOW_MOTION"

#: Typed refusal for a clip whose every sampled pair is a degenerate
#: exposure frame: there is no measurable motion evidence, which is NOT the
#: same finding as "the subject barely moved".
CLIP_MOTION_UNMEASURABLE = "CLIP_MOTION_UNMEASURABLE"

TOOL_NAME = "motion_score"
TOOL_VERSION = "2.0.1"
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


def _interior_values(grid, w, h):
    _, margin = _shift_limit(w)
    return [grid[y * w + x]
            for y in range(margin, h - margin)
            for x in range(margin, w - margin)]


def _contrast(values):
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def _affine_residual(a, b, w, h, dx, dy):
    """Mean |b - (g*a + o)| over the interior after the best global shift,
    plus the residual map over the whole overlap as a row-list.

    g/o are fitted per pair, so a global luminance offset (additive flash)
    or gain (contrast/exposure flash) is absorbed instead of counted as
    motion — but only while `a` carries measurable contrast. A frame
    collapsed to near-uniform luma has zero variance and no fit exists;
    callers must exclude that pair (see DEGENERATE_CONTRAST).

    The mean stays on the interior (the region every shift covers) so the
    calibrated magnitude is stable; the row-list spans the larger overlap
    because the structure test needs enough tiles to see untouched
    background.

    raises MotionScoreError CLIP_MOTION_UNMEASURABLE when the shift cannot
    be sampled inside the grid.
    """
    _, margin = _shift_limit(w)
    # Every sample reads the two cells at (x-dx, y-dy) and their +1
    # neighbours, so floor(coord) must land in 0..size-2 on BOTH axes. That
    # holds only while -margin < shift <= margin: an unclamped negative y0
    # makes i = y0*w + x0 resolve to the far end of the flat grid, silently
    # reading the wrong pixels, and a shift past the last row raises
    # IndexError. Validate before the interior loop so the typed refusal
    # pre-empts both.
    if not (-margin < dx <= margin and -margin < dy <= margin):
        raise MotionScoreError(
            CLIP_MOTION_UNMEASURABLE,
            "global shift dx=%r dy=%r cannot be sampled inside the %dx%d "
            "grid" % (dx, dy, w, h))
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
    res = [abs(bv[k] - (gain * av[k] + off)) for k in range(n)]
    iw = w - 2 * margin
    rows = [res[i:i + iw] for i in range(0, n, iw)]
    bx = min(int(math.floor(abs(dx))) + 1, w // 4)
    by = min(int(math.floor(abs(dy))) + 1, h // 4)
    # The map window is inset by bx/by so the structure test sees untouched
    # background. The shift itself was validated above, so this window is
    # never empty.
    x_lo = max(bx, int(math.ceil(dx)))
    x_hi = min(w - bx - 1, w - 2 + int(math.ceil(dx)))
    y_lo = max(by, int(math.ceil(dy)))
    y_hi = min(h - by - 1, h - 2 + int(math.ceil(dy)))
    full = []
    for y in range(y_lo, y_hi + 1):
        row = y * w
        full.append([abs(b[row + x] - (gain * _bilinear(a, w, x - dx, y - dy)
                                       + off))
                     for x in range(x_lo, x_hi + 1)])
    return sum(res) / n, full


#: Tile shape for the concentration test over the residual overlap map.
_STRUCT_TILE = (4, 3)


def _structure(rows):
    """Spatial concentration of the residual map: p90/p20 of tile means.

    The map is the whole shift-compensated overlap (~46x25 at the default
    grid), so untouched background shows up as low tiles. Coded grain raises
    every tile by about the same amount, so the ratio collapses toward 1
    however strong the grain is. Moving content raises a few tiles far above
    the rest, so the ratio stays high. This is what stops a noise field of
    gate-crossing magnitude from passing as motion.
    """
    tw, th = _STRUCT_TILE
    h = len(rows)
    w = len(rows[0]) if h else 0
    tiles = []
    for ty in range(0, h - th + 1, th):
        for tx in range(0, w - tw + 1, tw):
            total = 0.0
            for y in range(ty, ty + th):
                for x in range(tx, tx + tw):
                    total += rows[y][x]
            tiles.append(total / (tw * th))
    if len(tiles) < 5:
        return 0.0
    tiles.sort()
    p20 = tiles[int(0.2 * (len(tiles) - 1))]
    p90 = tiles[int(0.9 * (len(tiles) - 1))]
    if p20 > 1e-6:
        return p90 / p20
    return 99.0 if p90 > 0.5 else 0.0


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
    prev_std = _contrast(_interior_values(prev, w, h))
    subjects, structs, lumas, disps = [], [], [], []
    degenerate = 0
    for raw in frame_grids[1:]:
        cur, cur_mean = _dc(raw)
        cur_std = _contrast(_interior_values(cur, w, h))
        # The legacy field is measured on EVERY pair: an exposure collapse
        # is exactly what it is supposed to see.
        lumas.append(abs(cur_mean - prev_mean) / 255.0)
        if prev_std < DEGENERATE_CONTRAST or cur_std < DEGENERATE_CONTRAST:
            # Exposure event (frame collapsed to near-uniform luma): no
            # gain fit exists, so this pair carries NO motion evidence.
            # It contributes zero -- never the content amplitude -- and is
            # counted, so one black frame cannot scale the mean up.
            degenerate += 1
            subjects.append(0.0)
            disps.append(0.0)
            prev, prev_mean, prev_std = cur, cur_mean, cur_std
            continue
        _, dx, dy = _best_shift(prev, cur, w, h)
        resid, rows = _affine_residual(prev, cur, w, h, dx, dy)
        subjects.append(resid / 255.0)
        structs.append(_structure(rows))
        disps.append(((dx * dx + dy * dy) ** 0.5) / w)
        prev, prev_mean, prev_std = cur, cur_mean, cur_std
    pairs = float(len(subjects))
    measured = float(len(structs))
    return {
        "subject_motion_score": round(sum(subjects) / pairs, 6) if pairs
        else 0.0,
        "motion_structure": round(sum(structs) / measured, 6) if measured
        else 0.0,
        "frame_diff_score": round(sum(lumas) / pairs, 6) if pairs else 0.0,
        "global_luma_change": round(sum(lumas) / pairs, 6) if pairs else 0.0,
        "global_displacement": round(sum(disps) / pairs, 6) if pairs else 0.0,
        "samples": len(frame_grids),
        "valid_pairs": len(structs),
        "degenerate_pairs": degenerate,
        "unmeasurable": not structs,
        "grid": [w, h],
    }

def motion_score(clip_path=None, frame_stats=None, frame_grids=None,
                 grid_size=None):
    """Pluggable motion score: {'score': float, 'flagged': bool, ...}.

    frame_grids given  -> SPATIAL evidence (the gate's decision path):
                          score is subject_motion_score, threshold is
                          MOTION_SUBJECT_LOW, motion_structure carries the
                          concentration test, and the legacy frame_diff_score
                          rides along as data.
    frame_stats given  -> LEGACY pure function over per-frame mean luma
                          (no file opened, $0, no ffmpeg).
    neither given, clip_path given -> spatial sampling of the real clip
                          with ffmpeg; MotionScoreError CLIP_UNREADABLE when
                          it cannot answer, never a guessed score.
    flagged is True when the measured score on the evidence path used is
    below its threshold, or when the spatial structure test fails, or when
    the clip carries no measurable pair at all (unmeasurable: its
    reason_code is then CLIP_MOTION_UNMEASURABLE, not CLIP_LOW_MOTION).
    """
    if frame_grids is not None:
        ev = subject_motion_evidence(frame_grids, grid_size=grid_size)
        flagged = bool(ev["unmeasurable"]
                       or ev["subject_motion_score"] < MOTION_SUBJECT_LOW
                       or ev["motion_structure"] < MOTION_STRUCTURE_MIN)
        out = {"score": ev["subject_motion_score"],
               "flagged": flagged,
               "threshold": MOTION_SUBJECT_LOW,
               "structure_threshold": MOTION_STRUCTURE_MIN,
               "evidence": "spatial",
               "tool_version": TOOL_VERSION,
               **ev}
        if ev["unmeasurable"]:
            out["reason_code"] = CLIP_MOTION_UNMEASURABLE
        return out
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
    by motion_score() 2.0.0). A clip is flagged when the subject-motion
    score is below MOTION_SUBJECT_LOW, when the residual is not spatially
    concentrated (motion_structure below MOTION_STRUCTURE_MIN, e.g. a
    coded-noise field), or when the row is unmeasurable (every sampled pair
    was a degenerate exposure frame — reason_code
    CLIP_MOTION_UNMEASURABLE). A flash or a global pan therefore no longer
    passes as motion, and grain cannot either. Rows without spatial
    evidence (receipts written by 1.0.0) keep the legacy decision on
    'score' < MOTION_SCORE_LOW, unchanged. Rows carrying no motion_score
    key are listed in 'unscored' and reported in the receipt — the QC
    review layer reads a non-empty unscored list as FAIL (same seam E6
    uses: the assembler never scores video itself; the scoring step does).
    MALFORMED evidence — non-dict row, non-numeric score, a spatial tag
    without a numeric in-range subject_motion_score or motion_structure, or
    an unknown evidence tag — raises MotionScoreError CLIP_UNSCORED
    fail-closed. Returns
    {'outcome', 'reason_code', 'flagged': [ids], 'unscored': [ids],
    'unmeasurable': [ids], 'scores': {id: gate score}, 'threshold',
    'structure_threshold', 'legacy_threshold'}.
    """
    if not isinstance(clips, list) or not clips:
        raise MotionScoreError("CLIPS_EMPTY", "clips must be a non-empty list")
    flagged, unscored, unmeasurable, scores = [], [], [], {}
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
            # Malformed spatial evidence refuses: a tagged row must carry
            # numeric scores on the same scales as their thresholds.
            structure = ms.get("motion_structure")
            if (not _is_num(subject) or not 0.0 <= subject <= 1.0
                    or not _is_num(structure) or structure < 0.0):
                raise MotionScoreError(
                    "CLIP_UNSCORED",
                    "%s carries malformed spatial motion evidence" % cid)
            if ms.get("unmeasurable") is True:
                # No valid measurement exists. Refuse, and say so with the
                # typed code rather than a low-motion verdict.
                scores[cid] = subject
                flagged.append(cid)
                unmeasurable.append(cid)
                continue
            measured, threshold = subject, MOTION_SUBJECT_LOW
            weak = structure < MOTION_STRUCTURE_MIN
        else:
            measured, threshold = ms["score"], MOTION_SCORE_LOW
            weak = False
        scores[cid] = measured
        # Fail closed on the MEASURED scores: a supplied flagged:false can
        # never override a measured sub-threshold score or an inconclusive
        # structure test. A supplied flagged:true is still honoured, so a
        # stricter verdict is never loosened into a pass.
        if measured < threshold or weak or ms.get("flagged") is True:
            flagged.append(cid)
    if not flagged:
        reason = "CLIPS_MOTION_PASS"
    elif unmeasurable and len(unmeasurable) == len(flagged):
        reason = CLIP_MOTION_UNMEASURABLE
    else:
        reason = CLIP_LOW_MOTION
    return {"outcome": "ok" if not flagged else "rejected",
            "reason_code": reason,
            "flagged": flagged, "unscored": unscored,
            "unmeasurable": unmeasurable, "scores": scores,
            "threshold": MOTION_SUBJECT_LOW,
            "structure_threshold": MOTION_STRUCTURE_MIN,
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