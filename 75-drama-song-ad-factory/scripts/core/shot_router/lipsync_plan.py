"""lipsync_plan.py: anchors first, then impact, spread across the whole video (N-116).

Section 3.3c. Trevor, November 23: "It needs to decide where we get the most
impact from... spread out the lip sync portions throughout the video so we
maximize our usage of it. We know it gets used in the beginning. We know it
gets used at the end."

The planner runs in the Shot Router, on data from the Story Beats, the
Emotion Track and the Voice Map. It fills the lip-sync share in four steps:

1. **The two fixed anchors, placed before anything is ranked.** The opening
   passage (lip-sync by the lead inside the first 15 seconds) and the ending
   (the call to action on camera plus the closing echo, the last sung line).
   Either missing is ``LIPSYNC_ANCHOR_MISSING``.
2. **Score every other candidate passage for impact.** A candidate is one or
   more whole sentences by one voice in the Voice Map, 5 to 30 seconds long.
   One point table, added up.
3. **Spend the share on the highest scores.** Take from the top of the
   ranking until lip-sync reaches 25 to 30 percent of the film. Whole
   sentences win over the 35 percent top.
4. **Spread it across the whole video.** No more than 20 seconds of sung time
   (or 15 percent of the length, whichever is longer) between one piece and
   the next is ``LIPSYNC_GAP_TOO_LONG``; no quarter of the video holding more
   than 40 percent of the lip-sync seconds is ``LIPSYNC_CLUMPED``.

When spread and impact pull apart, spread wins the place and impact picks the
passage inside the empty stretch. An instrumental stretch never counts toward
a gap: nobody is singing in it.

Writes ``storyboard/lipsync-plan.json``: every candidate with its points and
the reason for each; which were chosen; the two anchors; the share in seconds
and percent; the longest gap; each quarter's share.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

import json

from .common import ShotRouterError

#: The share of the film lip-sync aims for, and the top it never crosses (3.3a).
TARGET_SHARE = (0.25, 0.30)
TOP_SHARE = 0.35
#: Section 3.3c step 4: the spread rules.
MAX_GAP_SECONDS = 20.0
MAX_GAP_SHARE = 0.15
MAX_QUARTER_SHARE = 0.40
#: The opening passage: lip-sync by the lead inside this many seconds (3.2).
OPENING_SECONDS = 15.0
#: One lip-sync piece is whole sentences, 5 to 30 seconds (3.3a, rule H4).
PIECE_MIN_S = 5.0
PIECE_MAX_S = 30.0

#: The one point table of 3.3c step 2. Weights are the plan's proposals;
#: Trevor can change any of them in one line.
IMPACT_POINTS = {
    "emotion_changes": 3.0,     # 0 to 3, direction or intensity inside it
    "hook_or_chorus": 2.0,
    "speaks_to_viewer": 2.0,
    "story_turn": 2.0,
    "face_is_the_point": 1.0,
}


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def score_candidate(candidate):
    """One candidate passage's impact: the five rows of 3.3c, added up."""
    if not isinstance(candidate, dict):
        raise ShotRouterError("CANDIDATE_INVALID", "a candidate must be an object")
    reasons = {}
    emotion = candidate.get("emotion_change_points")
    if emotion is None:
        emotion = 0
    if not _num(emotion) or not 0 <= emotion <= 3:
        raise ShotRouterError(
            "CANDIDATE_INVALID",
            "emotion_change_points is 0 to 3, got %r" % (emotion,))
    reasons["emotion_changes"] = float(emotion)
    for key in ("hook_or_chorus", "speaks_to_viewer", "story_turn",
                "face_is_the_point"):
        reasons[key] = IMPACT_POINTS[key] if candidate.get(key) else 0.0
    return {
        "points": round(sum(reasons.values()), 2),
        "reasons": {k: v for k, v in reasons.items() if v},
    }


def _window(candidate):
    start = candidate.get("start")
    end = candidate.get("end")
    if not _num(start) or not _num(end) or float(end) <= float(start):
        raise ShotRouterError(
            "CANDIDATE_INVALID",
            "candidate %r needs a non-empty window" % candidate.get("id"))
    return float(start), float(end)


def _check_piece(candidate):
    start, end = _window(candidate)
    length = end - start
    if candidate.get("cuts_sentence"):
        raise ShotRouterError(
            "LIPSYNC_CUTS_SENTENCE",
            "candidate %r starts or ends inside a sentence" % candidate.get("id"))
    if not PIECE_MIN_S <= length:
        raise ShotRouterError(
            "LIPSYNC_AUDIO_TOO_SHORT",
            "candidate %r is %.2fs, under the %.1fs whole-sentence floor"
            % (candidate.get("id"), length, PIECE_MIN_S))
    if length > PIECE_MAX_S and not candidate.get("stitched"):
        raise ShotRouterError(
            "LIPSYNC_AUDIO_TOO_LONG",
            "candidate %r is %.2fs, over the %.0fs piece limit and not marked "
            "stitched" % (candidate.get("id"), length, PIECE_MAX_S))
    return length


def _anchors(song_end, candidates):
    """Step 1: the opening and the ending, placed before any ranking."""
    opening = [c for c in candidates if not c.get("instrumental")
               and _window(c)[0] < OPENING_SECONDS and c.get("role") == "lead"]
    closing = [c for c in candidates if not c.get("instrumental")
               and abs(_window(c)[1] - song_end) <= 1.0]
    call_to_action = [c for c in candidates if not c.get("instrumental")
                      and c.get("call_to_action")]
    if not closing and not call_to_action:
        # The closing echo is the last sung line; a real song's last line often
        # ends a second or more before the final sample of the file.
        sung = [c for c in candidates if not c.get("instrumental")]
        if sung:
            closing = [sorted(sung, key=lambda c: _window(c)[1])[-1]]
    missing = []
    if not opening:
        missing.append("LIPSYNC_ANCHOR_MISSING: no lead lip-sync passage inside "
                       "the first %.0f seconds" % OPENING_SECONDS)
    if not closing and not call_to_action:
        missing.append("LIPSYNC_ANCHOR_MISSING: no ending passage (the call to "
                       "action on camera and the closing echo)")
    chosen = []
    if opening:
        chosen.append(sorted(opening, key=lambda c: _window(c)[0])[0])
    if call_to_action:
        chosen.append(sorted(call_to_action, key=lambda c: _window(c)[0])[0])
    if closing:
        last = sorted(closing, key=lambda c: _window(c)[1])[-1]
        if last not in chosen:
            chosen.append(last)
    return chosen, missing


def _quarters(song_end):
    return [((song_end * i / 4.0), (song_end * (i + 1) / 4.0)) for i in range(4)]


def _overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _sung_windows(candidates, instrumental):
    """The sung time on the song: everything except instrumental stretches."""
    spans = []
    for candidate in sorted(candidates, key=lambda c: _window(c)[0]):
        if candidate.get("instrumental"):
            continue
        spans.append(_window(candidate))
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _sung_spans(candidates, song_end):
    """The song with its instrumental stretches removed: nobody sings there."""
    instrumental = sorted(_window(c) for c in candidates if c.get("instrumental"))
    merged = []
    for start, end in instrumental:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    spans, cursor = [], 0.0
    for start, end in merged:
        if start > cursor:
            spans.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < song_end:
        spans.append((cursor, song_end))
    return spans


def _largest_gap(chosen, candidates, song_end):
    """(gap_seconds, gap_start, gap_end, limit) over SUNG time only.

    An instrumental stretch is not sung, so it never counts toward a gap even
    when no lip-sync piece sits inside it (3.3c step 4).
    """
    selected = sorted(_window(c) for c in chosen)
    limit = max(MAX_GAP_SECONDS, song_end * MAX_GAP_SHARE)
    gaps = []
    for start, end in _sung_spans(candidates, song_end):
        cursor = start
        for left, right in selected:
            if right <= start or left >= end:
                continue
            if left > cursor:
                gaps.append((cursor, min(left, end)))
            cursor = max(cursor, right)
        if cursor < end:
            gaps.append((cursor, end))
    if not gaps:
        return 0.0, 0.0, 0.0, limit
    gap_start, gap_end = max(gaps, key=lambda g: g[1] - g[0])
    return round(gap_end - gap_start, 3), gap_start, gap_end, limit


def plan_lipsync(candidates, *, song_end, instrumental_windows=None):
    """Fill the lip-sync share. Returns the `storyboard/lipsync-plan.json` body."""
    if not _num(song_end) or float(song_end) <= 0:
        raise ShotRouterError("PLAN_INVALID", "song_end must be a positive number")
    song_end = float(song_end)
    if not isinstance(candidates, list) or not candidates:
        raise ShotRouterError("PLAN_INVALID", "at least one candidate is required")
    scored = []
    seen = set()
    for candidate in candidates:
        cid = candidate.get("id")
        if not cid:
            raise ShotRouterError("CANDIDATE_INVALID", "every candidate needs an id")
        if cid in seen:
            raise ShotRouterError("CANDIDATE_INVALID",
                                  "candidate id %r repeats" % cid)
        seen.add(cid)
        if candidate.get("instrumental"):
            # Not a lip-sync candidate: it only tells the spread that nobody
            # is singing there. It is never chosen and never scored.
            start, end = _window(candidate)
            if end > song_end:
                raise ShotRouterError(
                    "CANDIDATE_INVALID",
                    "instrumental window %r ends past the song at %.2fs"
                    % (cid, end))
            scored.append(dict(candidate, length=round(end - start, 3),
                               score={"points": 0.0, "reasons": {}}))
            continue
        length = _check_piece(candidate)
        start, end = _window(candidate)
        if end > song_end:
            raise ShotRouterError(
                "CANDIDATE_INVALID",
                "candidate %r ends past the song at %.2fs" % (cid, end))
        scored.append(dict(candidate, length=round(length, 3),
                           score=score_candidate(candidate)))

    anchors, missing = _anchors(song_end, scored)
    chosen_ids = [c["id"] for c in anchors]
    share_seconds = sum(c["length"] for c in anchors)

    # Step 3: highest scores first, inside the target band.
    for candidate in sorted(scored, key=lambda c: (-c["score"]["points"],
                                                   _window(c)[0])):
        if candidate.get("instrumental") or candidate["id"] in chosen_ids:
            continue
        proposed = share_seconds + candidate["length"]
        if proposed / song_end > TARGET_SHARE[1]:
            continue
        chosen_ids.append(candidate["id"])
        share_seconds = proposed

    # Step 4: spread. A gap is filled by the highest-scoring candidate that
    # sits inside it; spread wins the place, impact picks the passage.
    chosen = [c for c in scored if c["id"] in chosen_ids]
    fills = []
    while True:
        gap, gap_start, gap_end, limit = _largest_gap(chosen, scored, song_end)
        if gap <= limit:
            break
        options = [c for c in scored
                   if c["id"] not in chosen_ids
                   and not c.get("instrumental")
                   and _window(c)[0] >= gap_start
                   and _window(c)[1] <= gap_end]
        if not options:
            break
        fill = max(options, key=lambda c: (c["score"]["points"],
                                           -_window(c)[0]))
        chosen_ids.append(fill["id"])
        chosen.append(fill)
        share_seconds += fill["length"]
        fills.append(fill["id"])

    gap, gap_start, gap_end, limit = _largest_gap(chosen, scored, song_end)

    quarters = _quarters(song_end)
    quarter_rows = []
    clumped = False
    for index, (start, end) in enumerate(quarters, start=1):
        seconds = sum(_overlap(_window(c), (start, end)) for c in chosen)
        share = seconds / share_seconds if share_seconds else 0.0
        if share > MAX_QUARTER_SHARE:
            clumped = True
        quarter_rows.append({
            "quarter": index,
            "window_seconds": [round(start, 3), round(end, 3)],
            "lipsync_seconds": round(seconds, 3),
            "share_of_lipsync": round(share, 4),
        })

    share_percent = round(100.0 * share_seconds / song_end, 2) if song_end else 0
    codes = list(missing)
    if gap > limit:
        codes.append(
            "LIPSYNC_GAP_TOO_LONG: %.2fs with no lip-sync between %.2fs and "
            "%.2fs, limit %.2fs" % (gap, gap_start, gap_end, limit))
    if clumped:
        codes.append("LIPSYNC_CLUMPED: one quarter holds more than %.0f%% of the "
                     "lip-sync seconds" % (MAX_QUARTER_SHARE * 100))

    plan = {
        "schema": "blackceo.lipsync-plan/v1",
        "song_end_seconds": song_end,
        "candidates": [{
            "id": c["id"],
            "start": c["start"], "end": c["end"],
            "role": c.get("role"),
            "length_seconds": c["length"],
            "points": c["score"]["points"],
            "points_by_row": c["score"]["reasons"],
            "chosen": c["id"] in chosen_ids,
        } for c in sorted(scored, key=lambda c: _window(c)[0])],
        "anchors": {
            "opening": chosen_ids[:1] if anchors else [],
            "ending": [c["id"] for c in anchors[1:]] if len(anchors) > 1 else [],
            "opening_seconds": OPENING_SECONDS,
        },
        "chosen_ids": [c["id"] for c in sorted(chosen, key=lambda c: _window(c)[0])],
        "share": {
            "seconds": round(share_seconds, 3),
            "percent": share_percent,
            "target_percent": [TARGET_SHARE[0] * 100, TARGET_SHARE[1] * 100],
            "top_percent": TOP_SHARE * 100,
            "whole_sentences_win_over_top": True,
        },
        "longest_gap": {
            "seconds": gap,
            "window_seconds": [round(gap_start, 3), round(gap_end, 3)],
            "limit_seconds": round(limit, 3),
            "instrumental_never_counts": True,
        },
        "quarters": quarter_rows,
        "spread_fills": fills,
        "codes": codes,
        "approved": not codes,
        "tool": "lipsync_planner",
    }
    return plan


def write_plan(path, plan):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return path


def require_plan(plan):
    """The plan is checked before any spend; a code refuses the spend."""
    if plan.get("codes"):
        raise ShotRouterError(plan["codes"][0].split(":", 1)[0],
                              "; ".join(plan["codes"]))
    return plan
