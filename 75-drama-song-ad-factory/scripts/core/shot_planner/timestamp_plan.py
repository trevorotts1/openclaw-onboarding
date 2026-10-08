"""timestamp_plan.py: Part H H5 - pictures are planned from the REAL song timing.

Kiesett's Stop Stale ad: pictures were made at 4-5 s each BEFORE the song
existed, then slowed 1.26-1.8x to fill it; 8 of 17 shots did not match the
line being heard. Fixes here (stdlib only):

  * plan_from_timestamps(): one shot window per sung/spoken line, taken from
    measured timestamps (Suno timestamped lyrics / aligned words / a local
    transcription of the finished track). Planned or packet timings are
    refused (PLANNED_TIMINGS_REFUSED): the song must exist first.
  * every shot names the line it SHOWS (shows_line_ids) and gets a
    gen_duration_s equal to its window, so no stretching is needed.
  * match_table()/pictures_match_gate(): shot / time / line / match rows;
    a shot whose named line is not the line heard in its window fails
    (PICTURE_LINE_MISMATCH).
  * check_stretch(): no slow motion above MAX_SLOWMO (1.15x)
    (SLOWMO_OVER_LIMIT).
"""
from __future__ import annotations

try:
    from .shot_planner import PlanError
except ImportError:                      # imported as a top-level module
    from shot_planner import PlanError   # type: ignore

MAX_SLOWMO = 1.15
# receipt `source` values that mean "measured from the finished song"
# (audio_c3/lyric_timing.py tiers + its payload source)
REAL_TIMING_SOURCES = frozenset({
    "suno-timestamped-lyrics", "suno-alignedWords",
    "faster-whisper-local", "cloud-stt"})
MISMATCH = "PICTURE_LINE_MISMATCH"
SLOWMO = "SLOWMO_OVER_LIMIT"
MIN_HEARD_S = 0.3        # overlap below this is not "the line heard"
MAX_CLIP_S = 6.0         # longest single generated picture (windows split above)
# the delivery checklist question H11 adds as Q10
CHECKLIST_Q10 = ("Q10 Do the pictures match the words? Measured: "
                 "{matched} of {total} shots show the line heard in their window.")


def _lines(timing):
    """[{line_id,start,end,text}] from a raw list or a load_timing_map dict."""
    if isinstance(timing, dict) and isinstance(timing.get("lines"), dict):
        out = [dict(v, line_id=k) for k, v in timing["lines"].items()]
    elif isinstance(timing, list):
        out = [dict(v) for v in timing]
    else:
        raise PlanError("BAD_TIMING_SHAPE", "timing must be a line list or timing map")
    for ln in out:
        if not isinstance(ln.get("line_id"), str) or not ln["line_id"]:
            raise PlanError("BAD_TIMING_SHAPE", "every line needs a line_id")
        if not all(isinstance(ln.get(k), (int, float)) for k in ("start", "end")) \
                or not ln["start"] < ln["end"]:
            raise PlanError("BAD_LINE_WINDOW", "line %s window unordered" % ln["line_id"])
    return sorted(out, key=lambda l: l["start"])


def plan_from_timestamps(lines, source, duration_s, subjects=None,
                         lipsync_line_ids=(), max_clip_s=MAX_CLIP_S):
    """Shots from real line timestamps. Windows are contiguous (0 to
    duration_s); a gap before a line is absorbed by the shot before it, so
    the picture never outlasts its own length by more than the gap.

    subjects: {line_id: what the picture shows}. Lines in lipsync_line_ids
    stay one whole shot (E5); longer windows are split in clips <= max_clip_s,
    each still naming the same line.
    """
    if source not in REAL_TIMING_SOURCES:
        raise PlanError("PLANNED_TIMINGS_REFUSED",
                        "source %r is not a measured timing of the finished song; "
                        "make the song first, then plan the pictures" % (source,))
    ls = _lines(lines)
    if not ls:
        raise PlanError("EMPTY_PLAN", "no timed lines")
    if not isinstance(duration_s, (int, float)) or duration_s < ls[-1]["end"]:
        raise PlanError("BAD_DURATION", "duration_s must cover the last line")
    subjects = subjects or {}
    shots = []
    for i, ln in enumerate(ls):
        lo = 0.0 if i == 0 else ln["start"]
        hi = ls[i + 1]["start"] if i + 1 < len(ls) else float(duration_s)
        n = 1 if ln["line_id"] in lipsync_line_ids else max(1, -(-(hi - lo) // max_clip_s))
        step = (hi - lo) / n
        for k in range(int(n)):
            a, b = lo + k * step, lo + (k + 1) * step
            shots.append({
                "shot_id": "S%02d" % (len(shots) + 1),
                "song_start": round(a, 3), "song_end": round(b, 3),
                "lyric_line_ids": [ln["line_id"]],
                "shows_line_ids": [ln["line_id"]],
                "line_text": ln.get("text", ""),
                "visual_objective": subjects.get(ln["line_id"], ""),
                "gen_duration_s": round(b - a, 3),
                "max_stretch": MAX_SLOWMO, "status": "planned"})
    return shots


def _heard(lines, a, b):
    """Line with the most overlap with [a,b], or None when below MIN_HEARD_S."""
    best, best_ov = None, 0.0
    for ln in lines:
        ov = min(b, ln["end"]) - max(a, ln["start"])
        if ov > best_ov:
            best, best_ov = ln, ov
    return best if best_ov >= MIN_HEARD_S else None


def match_table(shots, timing):
    """Rows {shot_id, start, end, heard_line_id, heard_text, shows_line_ids,
    match, reason}. A shot matches when the line heard in its window is one
    it names; a window with no line heard matches (silence/instrumental)."""
    ls = _lines(timing)
    rows = []
    for sh in shots:
        a, b = sh["song_start"], sh["song_end"]
        h = _heard(ls, a, b)
        shows = list(sh.get("shows_line_ids") or [])
        if h is None:
            ok, why = True, "no-line-heard"
        elif not shows:
            ok, why = False, "NO_LINE_NAMED"
        elif h["line_id"] in shows:
            ok, why = True, "match"
        else:
            ok, why = False, "shows %s, line heard is %s" % (",".join(shows), h["line_id"])
        rows.append({"shot_id": sh["shot_id"], "start": a, "end": b,
                     "heard_line_id": h["line_id"] if h else None,
                     "heard_text": h.get("text", "") if h else "",
                     "shows_line_ids": shows, "match": ok, "reason": why})
    return rows


def pictures_match_gate(shots, timing):
    """QC record: the table plus the Q10 line with measured numbers."""
    rows = match_table(shots, timing)
    bad = [r for r in rows if not r["match"]]
    return {"outcome": "rejected" if bad else "ok",
            "reason_code": MISMATCH if bad else "PICTURES_MATCH",
            "rows": rows, "mismatches": [r["shot_id"] for r in bad],
            "q10": CHECKLIST_Q10.format(matched=len(rows) - len(bad), total=len(rows))}


def stretch_of(seg):
    """Slow-motion factor of a segment: shown seconds / source seconds
    (or 1/speed). 1.0 when neither is declared."""
    if isinstance(seg.get("stretch"), (int, float)):
        return float(seg["stretch"])
    sp = seg.get("speed")
    if isinstance(sp, (int, float)) and sp > 0:
        return 1.0 / sp
    sd, d = seg.get("source_dur"), seg.get("dur", seg.get("snapped_dur"))
    if isinstance(sd, (int, float)) and sd > 0 and isinstance(d, (int, float)):
        return d / sd
    return 1.0


def check_stretch(segments, limit=MAX_SLOWMO):
    """Rows {index, src, stretch, ok}; ok is False above `limit` (lip-sync
    clips are held on a frame, never stretched, so they are checked too)."""
    return [{"index": i, "src": s.get("src"), "stretch": round(stretch_of(s), 3),
             "ok": stretch_of(s) <= limit + 1e-9} for i, s in enumerate(segments)]
