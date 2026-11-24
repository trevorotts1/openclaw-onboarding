#!/usr/bin/env python3
"""choir_lipsync.py -- N-07 (section 3.4): choir energy, then the close piece.

Stdlib only, no IO, no provider call. One lip-sync job carries 1 to 3 faces,
large in frame. Choir energy comes in two pieces, in this order: first a wide
choir shot made with H3 nine-picture and a camera move, then the close
lip-sync piece of 1 to 3 singers. A choir lip-sync piece with no wider lead-in
shot before it is refused ``CHOIR_LEAD_IN_MISSING``.

Face count itself is ``story_checks.check_face_count`` (max 3). This module
adds the lead-in rule that face count alone cannot see.
"""
from __future__ import annotations

CHOIR_LEAD_IN_MISSING = "CHOIR_LEAD_IN_MISSING"

CHOIR_LABELS = frozenset(("choir", "lead inside the choir", "lead_inside_the_choir",
                          "ensemble"))

#: Routes that count as the wide nine-picture choir-energy shot.
NINE_PICTURE_ROUTES = frozenset(("minimax-h3/reference-to-video", "reference-to-video",
                                 "nine_picture", "nine-picture", "nine picture",
                                 "ninepicture", "h3_nine_picture"))

WIDE_SIZES = frozenset(("wide", "establishing", "extreme wide", "medium wide",
                        "full", "wide shot", "long shot"))


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _rows(shots):
    return [s for s in shots if isinstance(s, dict)] if isinstance(shots, list) else []


def _ordered(rows):
    return sorted(rows, key=lambda s: (_num(s.get("song_start")),
                                       _num(s.get("song_end"))))


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _kind(row):
    for key in ("speaker", "lipsync_label", "lip_sync_label", "label"):
        v = _text(row.get(key)).lower()
        if v:
            return v
    return ""


def _route(row):
    for key in ("route", "video_route", "clip_route", "model_route"):
        v = _text(row.get(key)).lower()
        if v:
            return v
    return ""


def _is_lipsync(row):
    v = row.get("lip_sync")
    if v is True:
        return True
    return _text(v).lower() in ("true", "yes", "1") or _route(row) in (
        "kling_lipsync", "omnihuman_lipsync", "lip_sync", "lipsync", "lip-sync")


def _is_wide(row):
    size = _text(row.get("shot_size")).lower()
    if size:
        return size in WIDE_SIZES or "wide" in size
    return True  # a shot with no declared size is not proven close


def _has_move(row):
    return bool(_text(row.get("camera_move"))
                or _text(row.get("camera_move_reason"))
                or _text(row.get("camera_direction")))


def check_choir_lead_in(shots):
    """A choir lip-sync piece needs a wider nine-picture lead-in (N-07).

    Returns findings ``[{code, shot_id, detail}]``. Empty means every choir
    lip-sync row in the plan is led in correctly.
    """
    ordered = _ordered(_rows(shots))
    findings = []
    for i, row in enumerate(ordered):
        if _kind(row) not in CHOIR_LABELS or not _is_lipsync(row):
            continue
        sid = row.get("shot_id")
        prev = ordered[i - 1] if i > 0 else None
        if prev is None:
            findings.append({"code": CHOIR_LEAD_IN_MISSING, "shot_id": sid,
                             "detail": "choir lip-sync piece has no shot before it; "
                                       "widen first"})
            continue
        location = _text(row.get("location_id"))
        prev_location = _text(prev.get("location_id"))
        same_place = not location or not prev_location or location == prev_location
        lead_in = (_route(prev) in NINE_PICTURE_ROUTES and _is_wide(prev)
                   and _has_move(prev) and not _is_lipsync(prev) and same_place)
        if not lead_in:
            findings.append({
                "code": CHOIR_LEAD_IN_MISSING, "shot_id": sid,
                "detail": "the shot before the choir lip-sync piece (%r) is not a "
                          "wider nine-picture choir shot with a camera move"
                          % prev.get("shot_id")})
    return findings
