"""chains.py: a two-picture shot on H3 uses the next shot's storyboard picture (N-90).

Section 3E.3, step 2 of the TWO-PICTURE rule.

On H3 a two-picture shot does not wait for a parent clip. Its ending is set by
the NEXT shot's storyboard picture, which already exists before the video
burst, so both clips go into the same burst and neither waits. The chained
path is the default; it never blocks.

**Seamless-move mode is optional, off by default.** A run may choose to start a
shot from the previous clip's actual last frame, for one unbroken camera move.
Only then does a shot wait for its parent clip, one clip time per link. The
Shot Router marks every shot that uses the mode with ``seamless_move: true`` and
reports the longest wait in the chain *before* the burst, so the run owner sees
the price of the mode before any job is sent.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

from .common import ShotRouterError

#: A clip time per link, seconds (3E.4: H3 median 158 s, 9 in 10 within 306).
LINK_SECONDS_9_IN_10 = 306


def next_shot_map(shots):
    """shot_id -> the next shot in song order (None at the end)."""
    order = [shot.get("shot_id") for shot in shots]
    return {order[i]: (order[i + 1] if i + 1 < len(order) else None)
            for i in range(len(order))}


def resolve_two_picture(record, shots, *, seamless_move=False):
    """Set the two-picture clip's ending source and, if used, its wait.

    Returns the record, updated in place:
      ``two_picture_mode``  'chained' (default) or 'single_request'
      ``end_from``          the next shot's storyboard picture (chained) or
                            the shot's own end keyframe (single request)
      ``waits_for``         None in chained mode; the parent clip in seamless mode
      ``waits_seconds``     the longest wait this link adds, seamless mode only
    """
    if record.get("route") != "two_picture":
        return record
    if record.get("two_picture_mode") == "single_request":
        record.setdefault("end_from", "own_end_keyframe")
        record["waits_for"] = None
        return record
    shot_id = record.get("shot_id")
    nxt = next_shot_map(shots).get(shot_id)
    if not nxt:
        raise ShotRouterError(
            "TWO_PICTURE_NO_NEXT",
            "shot %r is the last shot: a chained two-picture clip needs a "
            "following storyboard picture to land on; give it an own end "
            "keyframe or route it ONE-PICTURE" % shot_id)
    record["two_picture_mode"] = "chained"
    record["end_from"] = "next_shot_storyboard_picture:%s" % nxt
    record["waits_for"] = None
    if seamless_move:
        record["seamless_move"] = True
        record["waits_for"] = "parent_clip:%s" % shot_id
        record["waits_seconds"] = LINK_SECONDS_9_IN_10
        record.setdefault("notes", []).append(
            "seamless-move mode: this shot starts from the previous clip's last "
            "frame and waits one clip time")
    else:
        record["seamless_move"] = False
        record.setdefault("notes", []).append(
            "nothing waits: both keyframes exist before the burst")
    return record


def chain_report(records):
    """Every chain's waits, for the report shown BEFORE the burst (N-90).

    Chained shots add nothing. Seamless links add one clip time each; the
    longest wait is the deepest link, not the sum, because one clip time per
    link and links run one after another in song order.
    """
    chained, seamless = [], []
    for record in records:
        if record.get("route") != "two_picture":
            continue
        if record.get("seamless_move"):
            seamless.append(record.get("shot_id"))
        else:
            chained.append(record.get("shot_id"))
    longest = LINK_SECONDS_9_IN_10 * max(1, len(seamless)) if seamless else 0
    return {
        "chained_shots": chained,
        "seamless_shots": seamless,
        "seamless_mode": bool(seamless),
        "longest_wait_seconds": longest,
        "longest_wait_minutes": round(longest / 60.0, 2) if longest else 0.0,
        "report_before_burst": True,
    }


def plan_chains(records, shots, *, seamless_move=False):
    """Resolve every two-picture row in a run. The package-level entry."""
    for record in records:
        resolve_two_picture(record, shots, seamless_move=seamless_move)
    return records


def seamless_shots(records):
    """Shot ids that use the optional seamless-move mode (off by default)."""
    return [record.get("shot_id") for record in records
            if record.get("seamless_move")]


def wait_report(records):
    """The longest wait in the chain, reported before the burst."""
    return chain_report(records)
