"""pictures.py: more pictures is better, and the better candidate is picked (N-82).

Trevor, binding. Three rules from 3E.2:

1. When two routes could apply, the route with MORE pictures wins a tie. The
   decision itself is in ``routes.route_shot``; ``more_pictures`` and
   ``route_weight`` here are the one scoring function it must not restate.
2. Every keyframe is made as TWO candidates, side by side, and the better one is
   picked. The pick is by the severity table (3J.3), never a checker's taste:
   no MAJOR, then the fewest MEDIUM, then the one carrying the planned words.
3. A nine-picture shot ALWAYS gets a composition keyframe, and every
   nine-picture clip of up to 10 seconds is bought as two takes (the take rule
   lives in clip_sizer; the composition keyframe lives here).
4. Cost NEVER reduces the picture list. A picture costs cents; a remade clip
   costs minutes. A list marked ``reduced_for_cost`` is refused outright.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

from .common import ShotRouterError

KEYFRAME_KINDS = frozenset({"keyframe", "composition_keyframe",
                            "lip_sync_keyframe"})
NINE_ROUTES = frozenset({"nine_picture", "long_take"})
MIN_KEYFRAME_CANDIDATES = 2

#: Route picture weights for the N-82 tie-break. routes.py owns the decision;
#: these mirror its ROUTE_PICTURE_WEIGHT so the two can be cross-checked.
ROUTE_WEIGHTS = {
    "nine_picture": 9,
    "long_take": 9,
    "two_picture": 2,
    "merged": 2,
    "one_picture": 1,
    "lip_sync": 1,
}


def route_weight(route):
    """Pictures a route can bring to a shot (the tie-break score)."""
    return ROUTE_WEIGHTS.get(route, 0)


def more_pictures(route_a, route_b):
    """The route with more pictures; a tie keeps ``route_a`` (first rule wins)."""
    return route_a if route_weight(route_a) >= route_weight(route_b) else route_b


def picture_count(record):
    """Paid pictures in a shot record (candidate counts included)."""
    total = 0
    for picture in record.get("pictures") or []:
        if picture.get("kind") == "reference_set":
            continue  # the lock's own pictures are not redrawn
        total += int(picture.get("candidates") or 1)
    return total


def ensure_two_candidates(record):
    """Every keyframe carries at least two candidates; mutates the record."""
    for picture in record.get("pictures") or []:
        kind = picture.get("kind") or ""
        if kind in KEYFRAME_KINDS or kind == "keyframe":
            current = picture.get("candidates")
            if not isinstance(current, int) or isinstance(current, bool) \
                    or current < MIN_KEYFRAME_CANDIDATES:
                picture["candidates"] = MIN_KEYFRAME_CANDIDATES
    return record


def ensure_composition_keyframe(record):
    """A nine-picture (or long-take) shot always gets a composition keyframe."""
    if record.get("route") not in NINE_ROUTES:
        return record
    pictures = record.setdefault("pictures", [])
    if any(p.get("kind") == "composition_keyframe" for p in pictures):
        return record
    refs = []
    for picture in pictures:
        if picture.get("kind") == "reference_set":
            refs = list(picture.get("refs") or [])
            break
    pictures.append({
        "purpose": "composition_keyframe",
        "kind": "composition_keyframe",
        "image_to_image": True,
        "refs": refs,
        "candidates": MIN_KEYFRAME_CANDIDATES,
    })
    return record


def enforce_more_pictures(record):
    """Apply rules 1-3 to one shot record and refuse a cost-trimmed list."""
    for picture in record.get("pictures") or []:
        if picture.get("reduced_for_cost"):
            raise ShotRouterError(
                "PICTURE_LIST_REDUCED_FOR_COST",
                "shot %s trims its picture list for cost; a picture costs cents "
                "and a remade clip costs minutes, so cost never reduces the list"
                % record.get("shot_id"),
            )
    ensure_two_candidates(record)
    ensure_composition_keyframe(record)
    return record


def enforce_run(shot_routes):
    """Apply N-82 to every shot in a ``shot-routes`` record and return it."""
    for record in shot_routes.get("shots") or []:
        enforce_more_pictures(record)
    return shot_routes


def pick_candidate(candidates):
    """Pick the better of two candidate pictures by the severity table (3J.3).

    Each candidate: ``{"major": int, "medium": int, "carries_planned_words":
    bool}``. Pass mark: no MAJOR, then the fewest MEDIUM, then the one carrying
    the planned words. A tie keeps the first candidate. Returns its index.
    """
    if not candidates:
        raise ShotRouterError("NO_CANDIDATES", "pick_candidate needs at least one")
    def key(pair):
        index, cand = pair
        major = int(cand.get("major") or 0)
        medium = int(cand.get("medium") or 0)
        words = bool(cand.get("carries_planned_words"))
        return (major > 0, major, medium, not words, index)
    return min(enumerate(candidates), key=key)[0]


def assert_cost_never_trims(pictures):
    """Refuse a picture list whose candidates were cut to save credits."""
    if any(p.get("reduced_for_cost") for p in pictures or []):
        raise ShotRouterError(
            "PICTURE_LIST_REDUCED_FOR_COST",
            "cost never reduces the picture list (N-82)",
        )
    return True
