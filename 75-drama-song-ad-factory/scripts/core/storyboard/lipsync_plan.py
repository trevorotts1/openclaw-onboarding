"""lipsync_plan.py: where lip-sync goes (row N-116, plan section 3.3c). Stdlib only.

The planner fills the lip-sync share in this order, on data from the Story
Beats, the Emotion Track and the Voice Map:

1. Two fixed anchors are placed first: the opening passage (a lead piece inside
   the first 15 seconds, section 3.2) and the ending (the spoken call to action
   by the character who says it, plus the last sung line). A missing anchor is
   refused ``LIPSYNC_ANCHOR_MISSING``.
2. Every other candidate passage is scored for impact (the point table below);
   the share is spent on the highest scores until it reaches the 25 to 30
   percent target.
3. The result is spread across the whole video: no more than 20 seconds of sung
   time (or 15 percent of the video, if longer) between one piece and the next
   (``LIPSYNC_GAP_TOO_LONG``), and no quarter of the video holding more than 40
   percent of the lip-sync seconds (``LIPSYNC_CLUMPED``).

Writes ``storyboard/lipsync-plan.json``. Whole sentences win over the top
(section 3.3a rule 5): the plan reports the seconds and percent so the run
owner sees an overrun before any spend. No provider call, no spend.
"""
from __future__ import annotations

import json
import os

SCHEMA_VERSION = "blackceo.lipsync-plan/v1"
PLAN_NAME = "lipsync-plan.json"

LIPSYNC_ANCHOR_MISSING = "LIPSYNC_ANCHOR_MISSING"
LIPSYNC_GAP_TOO_LONG = "LIPSYNC_GAP_TOO_LONG"
LIPSYNC_CLUMPED = "LIPSYNC_CLUMPED"
LIPSYNC_AUDIO_TOO_LONG = "LIPSYNC_AUDIO_TOO_LONG"

#: One piece is 5 to 30 seconds; only a passage longer than this is stitched
#: (3.3a rule 4). A candidate that long is refused, never planned whole.
MAX_PIECE_S = 30.0

#: Defaults the plan may change in one line (3.3c says so explicitly).
TARGET_LO = 0.25
TARGET_HI = 0.30
HARD_TOP = 0.35
GAP_SECONDS = 20.0
GAP_FRACTION = 0.15
CLUMP_FRACTION = 0.40
OPENING_WINDOW_S = 15.0
OPENING_FIRST_BY_S = 3.0

#: Impact points (3.3c step 2). The weights are the plan's proposed defaults.
IMPACT_POINTS = (
    ("emotion_change", 3),    # direction or intensity changes inside the piece
    ("hook", 2),              # the hook or the chorus
    ("speaks_to_viewer", 2),  # "you", a promise, an ask
    ("story_turn", 2),        # a decision, discovery or reversal
    ("face_is_point", 1),     # nothing else has to be shown in the moment
)


def _num(value):
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _candidate(raw):
    c = {
        "candidate_id": raw.get("candidate_id") or raw.get("line_id"),
        "role": (raw.get("role") or "").strip().lower(),
        "start_s": _num(raw.get("start_s")),
        "end_s": _num(raw.get("end_s")),
        "score_components": dict(raw.get("score_components") or {}),
        "is_anchor": bool(raw.get("is_anchor")),
        "anchor": (raw.get("anchor") or "").strip().lower(),
        "instrumental": bool(raw.get("instrumental")),
    }
    if c["candidate_id"] is None or c["start_s"] is None or c["end_s"] is None \
            or c["end_s"] <= c["start_s"]:
        return None
    return c


def impact_score(candidate):
    """The 3.3c impact score: one point table, added up and capped per row."""
    comps = candidate.get("score_components") or {}
    score = 0
    reasons = {}
    for key, cap in IMPACT_POINTS:
        raw = comps.get(key)
        if isinstance(raw, bool):
            value = cap if raw else 0
        elif isinstance(raw, (int, float)):
            value = max(0, min(int(raw), cap))
        else:
            value = 0
        if value:
            score += value
            reasons[key] = value
    return score, reasons


def plan_lipsync(candidates, duration_s, *, target_lo=TARGET_LO,
                 target_hi=TARGET_HI, gap_seconds=GAP_SECONDS,
                 gap_fraction=GAP_FRACTION, clump_fraction=CLUMP_FRACTION):
    """Plan the lip-sync pieces. Returns the plan dict with its findings.

    candidates: passage dicts ``{candidate_id, role, start_s, end_s,
    score_components{}, instrumental, anchor}``. ``anchor`` is "opening",
    "ending" or empty. A passage by one voice, 5 to 30 seconds, is the caller's
    contract (section 3.3a); this planner places, it does not re-cut.
    """
    duration = _num(duration_s)
    if not duration or duration <= 0:
        raise ValueError("duration_s must be a positive number")
    parsed = [c for c in (_candidate(r) for r in candidates or []) if c]
    by_id = {c["candidate_id"]: c for c in parsed}

    def opening(c):
        return (c["role"] == "lead" and c["start_s"] <= OPENING_FIRST_BY_S
                and c["start_s"] < OPENING_WINDOW_S)

    opening_pick = next((c for c in parsed if c["anchor"] == "opening" or
                         (not c["anchor"] and opening(c))), None)
    ending_pick = next((c for c in parsed if c["anchor"] == "ending"), None)
    if ending_pick is None:
        if any(c["role"] in ("cta", "call", "spoken") for c in parsed):
            ending_pick = next(c for c in parsed
                               if c["role"] in ("cta", "call", "spoken"))
        else:
            sung = [c for c in parsed if not c["instrumental"]]
            ending_pick = max(sung, key=lambda c: c["end_s"], default=None)

    findings = []
    if opening_pick is None:
        findings.append({"code": LIPSYNC_ANCHOR_MISSING, "candidate_id": None,
                         "detail": "no lead lip-sync passage inside the first "
                                   "15 seconds (section 3.2 opening)"})
    if ending_pick is None:
        findings.append({"code": LIPSYNC_ANCHOR_MISSING, "candidate_id": None,
                         "detail": "no ending lip-sync passage (call to action "
                                   "or last sung line)"})

    chosen = []
    for pick in (opening_pick, ending_pick):
        if pick is not None and pick["candidate_id"] not in \
                {c["candidate_id"] for c in chosen} \
                and pick["end_s"] - pick["start_s"] <= MAX_PIECE_S:
            chosen.append(pick)

    # 3.3a rule 4: one piece over 30 seconds is refused and the stitch named
    # as the fix. It is never planned whole.
    too_long = {c["candidate_id"] for c in parsed
                if c["end_s"] - c["start_s"] > MAX_PIECE_S}
    for c in parsed:
        if c["candidate_id"] not in too_long:
            continue
        findings.append({
            "code": LIPSYNC_AUDIO_TOO_LONG, "candidate_id": c["candidate_id"],
            "detail": "passage runs %.1fs (max %.0fs per piece); split it at a "
                      "breath or a line boundary into consecutive pieces of 5s "
                      "or more and stitch them (section 3.3a rule 4)"
                      % (c["end_s"] - c["start_s"], MAX_PIECE_S)})

    scored = []
    for c in parsed:
        score, reasons = impact_score(c)
        scored.append((score, c, reasons))
    scored.sort(key=lambda row: (-row[0], row[1]["start_s"]))

    def lipsync_seconds(rows):
        return sum(r["end_s"] - r["start_s"] for r in rows)

    target_s = duration * target_lo
    for score, c, _ in scored:
        if lipsync_seconds(chosen) >= target_s:
            break
        if c["candidate_id"] in {x["candidate_id"] for x in chosen}:
            continue
        if c["candidate_id"] in too_long:
            continue
        chosen.append(c)
    chosen.sort(key=lambda c: c["start_s"])

    share = lipsync_seconds(chosen)
    share_pct = share / duration if duration else 0.0

    # Spread: gaps and clumping (3.3c step 4).
    pairings = [c for c in chosen if not c["instrumental"]]
    max_gap = gap_seconds if gap_seconds >= gap_fraction * duration \
        else gap_fraction * duration
    longest_gap = 0.0
    for a, b in zip(pairings, pairings[1:]):
        stretch = [c for c in parsed
                   if c["start_s"] >= a["end_s"] and c["end_s"] <= b["start_s"]
                   and not c["instrumental"]]
        # An instrumental stretch does not count toward a gap: only sung or
        # spoken time between the two chosen pieces does.
        gap = (b["start_s"] - a["end_s"]) - sum(
            x["end_s"] - x["start_s"] for x in stretch)
        gap = max(0.0, gap)
        longest_gap = max(longest_gap, gap)
        if gap > max_gap:
            findings.append({
                "code": LIPSYNC_GAP_TOO_LONG, "candidate_id": b["candidate_id"],
                "detail": "%.1fs of sung time with no lip-sync between %r and %r "
                          "(max %.1fs)" % (gap, a["candidate_id"],
                                           b["candidate_id"], max_gap)})
    quarters = [0.0, 0.0, 0.0, 0.0]
    for c in chosen:
        q = min(3, int((c["start_s"] / duration) * 4))
        quarters[q] += c["end_s"] - c["start_s"]
    for i, secs in enumerate(quarters):
        if share > 0 and secs / share > clump_fraction:
            findings.append({
                "code": LIPSYNC_CLUMPED, "candidate_id": None,
                "detail": "quarter %d holds %.0f%% of the lip-sync seconds "
                          "(max %.0f%%)" % (i + 1, 100 * secs / share,
                                            100 * clump_fraction)})

    pieces = []
    for c in chosen:
        score, reasons = impact_score(c)
        pieces.append({
            "candidate_id": c["candidate_id"],
            "role": c["role"],
            "start_s": round(c["start_s"], 3),
            "end_s": round(c["end_s"], 3),
            "seconds": round(c["end_s"] - c["start_s"], 3),
            "anchor": ("opening" if c is opening_pick else
                       "ending" if c is ending_pick else ""),
            "impact_score": score,
            "points": reasons,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "duration_s": round(duration, 3),
        "pieces": pieces,
        "anchors": {
            "opening": opening_pick["candidate_id"] if opening_pick else None,
            "ending": ending_pick["candidate_id"] if ending_pick else None,
        },
        "share_seconds": round(share, 3),
        "share_percent": round(100 * share_pct, 1),
        "target_percent": [100 * target_lo, 100 * target_hi],
        "over_hard_top": share_pct > HARD_TOP,
        "longest_gap_s": round(longest_gap, 3),
        "quarters": [round(q, 3) for q in quarters],
        "candidates": [{"candidate_id": c["candidate_id"],
                        "impact_score": s, "points": r}
                       for s, c, r in scored],
        "findings": findings,
        "outcome": "fail" if findings else "pass",
    }


def write_plan(run_dir, plan):
    """Write ``storyboard/lipsync-plan.json`` under a run folder.

    3.3c "What it writes": every candidate with its points and the reason for
    each point, the two anchors, the share in seconds and percent, the longest
    gap and each quarter's share. Returns the path written.
    """
    folder = os.path.join(run_dir, "storyboard")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, PLAN_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1, sort_keys=True)
    return path
