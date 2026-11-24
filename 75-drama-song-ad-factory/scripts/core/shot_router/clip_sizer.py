"""clip_sizer.py: the Clip Sizer. Merge rule and the rendered-against-used report (N-94).

Section 3E.2 rule 2a and section 3I.4.

**Rule 2a, the merge rule.** Two or three neighbouring shots with the same
place, the same people and the same camera idea, and none carrying readable
writing, become ONE clip of 5 to 10 seconds, cut into the shots by the edit.
Merging removes the 4-second-floor waste (a 1.5-second shot otherwise pays for
4 seconds and throws most of it away) and one continuity check between them.

**The report.** Every run writes rendered seconds against used seconds, per
route and in total, before the burst and again at delivery (3I.4). In the
5-minute rebuild the plan rendered 240 seconds to use about 167; the report
makes that visible every time.

The Clip Sizer chooses for the fastest finished video and never trades a
quality rule to get it; the hard rules of 3I.2 and the length choice live in
this module too.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

MERGED_MIN_S = 5.0
MERGED_MAX_S = 10.0
#: Rule 2a merges at most this many neighbouring shots.
MERGE_GROUP_MAX = 3


def _words(value):
    return {w for w in str(value or "").lower().replace("-", "_").split()
            if w}


def _shot_start(shot):
    return shot.get("start", shot.get("song_start"))


def _shot_end(shot):
    return shot.get("end", shot.get("song_end"))


def _window(shot):
    start, end = _shot_start(shot), _shot_end(shot)
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return 0.0
    return round(float(end) - float(start), 3)


def mergeable(shot, neighbour):
    """Rule 2a: same place, same people, same camera idea, no writing."""
    if not isinstance(neighbour, dict):
        return False
    if shot.get("readable_writing") or neighbour.get("readable_writing"):
        return False
    return (
        bool(shot.get("location_id"))
        and shot.get("location_id") == neighbour.get("location_id")
        and set(shot.get("cast_ids") or ()) == set(neighbour.get("cast_ids") or ())
        and _words(shot.get("camera_move")) == _words(neighbour.get("camera_move"))
    )


def merge_group(shot, neighbours):
    """The group rule 2a merges: this shot plus up to two neighbours."""
    group = [shot]
    for neighbour in neighbours or ():
        if len({g.get("shot_id") for g in group}) >= MERGE_GROUP_MAX:
            break
        if mergeable(group[-1], neighbour):
            group.append(neighbour)
    return group if len(group) >= 2 else [shot]


def merge_clip(shot, neighbours=None):
    """One merged clip of 5 to 10 s, or None when rule 2a does not fit.

    Returns ``{"shots": [...], "window_seconds", "seconds"}``. When the group's
    own windows add up past 10 seconds the shots are not merged: rule 2a names
    a clip of 5 to 10 seconds, and the edit can only cut time out of it.
    """
    group = merge_group(shot, neighbours)
    if len(group) < 2:
        return None
    total = sum(_window(member) for member in group)
    if total > MERGED_MAX_S:
        return None
    seconds = max(total, MERGED_MIN_S)
    return {
        "shots": [member.get("shot_id") for member in group],
        "window_seconds": round(total, 3),
        "seconds": round(seconds, 3),
        "rule": "2a",
        "cut_by_edit": True,
        "pieces": len(group),
    }


def rendered_against_used(records):
    """The per-run report: rendered seconds against used seconds, by route."""
    by_route, total = {}, {"rendered_seconds": 0.0, "used_seconds": 0.0,
                           "credits": 0}
    for record in records:
        clip = record.get("clip") or {}
        if not clip:
            continue
        route = clip.get("route") or record.get("route") or "unknown"
        row = by_route.setdefault(route, {"clips": 0, "rendered_seconds": 0.0,
                                          "used_seconds": 0.0, "credits": 0})
        row["clips"] += 1
        for key in ("rendered_seconds", "used_seconds"):
            row[key] = round(row[key] + float(clip.get(key) or 0), 3)
        row["credits"] += int(clip.get("credits") or 0)
    total["rendered_seconds"] = round(
        sum(row["rendered_seconds"] for row in by_route.values()), 3)
    total["used_seconds"] = round(
        sum(row["used_seconds"] for row in by_route.values()), 3)
    total["credits"] = sum(row["credits"] for row in by_route.values())
    total["dollars"] = round(total["credits"] * 0.005, 4)
    total["waste_percent"] = (
        round(100.0 * (total["rendered_seconds"] - total["used_seconds"])
              / total["rendered_seconds"], 2)
        if total["rendered_seconds"] else 0.0)
    total["by_route"] = by_route
    return total
