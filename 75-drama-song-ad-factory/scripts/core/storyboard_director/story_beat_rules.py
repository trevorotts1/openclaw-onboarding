"""story_beat_rules.py: G-STORY-03 beat density and lyric-picture coverage.

Two review-time refusals, stdlib only:

* ``review_beat_density`` refuses more than 3 action beats per 5-second shot
  (the T10 beach-phone case: seven beats in 5.0 seconds).
* ``review_lyric_picture_coverage`` refuses a lyric-named picture that does
  not stay on screen for the full word-timing window of its line (the trip
  line sung while the beach phone has already left the frame).

Neither touches the render path; both are read-only over the storyboard plan.
"""
from __future__ import annotations

BEATS_PER_FIVE_SECONDS = 3
BEAT_DENSITY_EXCEEDED = "BEAT_DENSITY_EXCEEDED"
LYRIC_PICTURE_SHORT = "LYRIC_PICTURE_SHORT"


def _shot_span(shot):
    start = shot.get("song_start")
    end = shot.get("song_end")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) \
            and not isinstance(start, bool) and not isinstance(end, bool):
        return float(start), float(end)
    return None, None


def _beat_count(shot):
    """Action beats the shot declares: ``motion_beats`` or a list of beats."""
    n = shot.get("motion_beats")
    if isinstance(n, int) and not isinstance(n, bool):
        return n
    for key in ("action_beats", "beats"):
        value = shot.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


def _fail(code, shot_id, detail):
    return {"criterion": "pacing_mismatch", "code": code,
            "shot_id": shot_id, "detail": detail}


def review_beat_density(shots):
    """Refuse more than 3 action beats per 5-second shot.

    A shot of 5.0 seconds or less may carry at most 3 beats; a longer shot is
    allowed 3 beats for each started 5-second block. Returns
    {"outcome", "findings", "codes"}.
    """
    findings = []
    for shot in shots or []:
        if not isinstance(shot, dict):
            continue
        start, end = _shot_span(shot)
        if start is None:
            continue
        duration = end - start
        beats = _beat_count(shot)
        blocks = max(1, int(duration // 5.0) + (1 if duration % 5.0 else 0))
        cap = BEATS_PER_FIVE_SECONDS * blocks
        if beats > cap:
            findings.append(_fail(
                BEAT_DENSITY_EXCEEDED, shot.get("shot_id"),
                "%d action beats in %.1fs (cap %d per %d x 5s block)"
                % (beats, duration, cap, blocks)))
    return {"outcome": "pass" if not findings else "fail",
            "findings": findings,
            "codes": sorted({f["code"] for f in findings})}


def _normalise_windows(word_timings):
    """{line_id: (start, end)} from a mapping or a list of timed rows."""
    out = {}
    if isinstance(word_timings, dict):
        for line_id, span in word_timings.items():
            if isinstance(span, (list, tuple)) and len(span) == 2:
                out[line_id] = (float(span[0]), float(span[1]))
            elif isinstance(span, dict):
                out[line_id] = (float(span["start"]), float(span["end"]))
    elif isinstance(word_timings, list):
        for row in word_timings:
            if isinstance(row, dict) and row.get("line_id") is not None:
                out[row["line_id"]] = (float(row["start"]), float(row["end"]))
    return out


def review_lyric_picture_coverage(shots, word_timings):
    """Refuse a lyric-named picture that leaves before its line finishes.

    For every shot that names ``lyric_line_ids``, the shot's own on-screen
    window must cover each line's full word-timing window. A shot may widen
    it with ``picture_holds``: {line_id: [start, end]}. Returns
    {"outcome", "findings", "codes"}.
    """
    windows = _normalise_windows(word_timings)
    findings = []
    for shot in shots or []:
        if not isinstance(shot, dict):
            continue
        start, end = _shot_span(shot)
        if start is None:
            continue
        holds = shot.get("picture_holds") if isinstance(
            shot.get("picture_holds"), dict) else {}
        for line_id in shot.get("lyric_line_ids") or []:
            window = windows.get(line_id)
            if window is None:
                continue
            covered = holds.get(line_id)
            lo, hi = start, end
            if isinstance(covered, (list, tuple)) and len(covered) == 2:
                lo, hi = min(lo, float(covered[0])), max(hi, float(covered[1]))
            if lo > window[0] + 1e-6 or hi < window[1] - 1e-6:
                findings.append(_fail(
                    LYRIC_PICTURE_SHORT, shot.get("shot_id"),
                    "picture covers %.2f-%.2fs but line %r runs %.2f-%.2fs; "
                    "the named picture leaves mid-line"
                    % (lo, hi, line_id, window[0], window[1])))
    return {"outcome": "pass" if not findings else "fail",
            "findings": findings,
            "codes": sorted({f["code"] for f in findings})}
