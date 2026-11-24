#!/usr/bin/env python3
"""world_building.py -- N-106 (section 3M): places that stay the same.

Stdlib only, no IO, no provider call. This module holds the plan-time
questions that make the location bible, the prop ledger, background life and
a changed place's two states checkable before a storyboard picture is bought:

* ``validate_location_bible(world)`` -- every place in the lock file carries
  its reference pictures; a place the story changes carries both states.
* ``validate_prop_ledger(prop_ledger, scenes)`` -- one line per story prop per
  scene: where it is, what state it is in, who holds it.
* ``validate_background_life(world)`` -- a place in use declares who is there,
  how many, and what they are doing; a room the story says is full is recorded
  full by count.
* ``validate_world_building(world, prop_ledger=None, scenes=None)`` -- the one
  packet the review reads.

Nothing here draws, spends or writes. Codes are stable and nameable.
"""
from __future__ import annotations

LOCATION_REFERENCE_MISSING = "LOCATION_REFERENCE_MISSING"
PLACE_STATE_MISSING = "PLACE_STATE_MISSING"
PROP_LEDGER_MISSING = "PROP_LEDGER_MISSING"
PROP_LEDGER_INCOMPLETE = "PROP_LEDGER_INCOMPLETE"
BACKGROUND_LIFE_MISSING = "BACKGROUND_LIFE_MISSING"

#: A place the story changes needs both of these states before pictures.
CHANGED_PLACE_STATES = ("before", "after")


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _locations(world):
    rows = world.get("locations") if isinstance(world, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _defect(code, field, message, ref=None):
    out = {"code": code, "field": field, "message": message}
    if ref is not None:
        out["ref"] = ref
    return out


def validate_location_bible(world):
    """Every place is in the location bible with reference pictures (N-106).

    ``world``: ``{"locations": [{location_id, reference_pictures,
    states?, changes?}]}``. ``changes`` true (or a ``changes`` list) means the
    story changes the place, so it must carry ``states`` for every entry in
    ``CHANGED_PLACE_STATES``. Returns a defect list.
    """
    defects = []
    locations = _locations(world)
    if not locations:
        defects.append(_defect("locations", "world",
                               "the location bible is empty; no place can be pictured"))
        return defects
    for loc in locations:
        lid = _text(loc.get("location_id"))
        if not lid:
            defects.append(_defect("location_id", "locations",
                                   "a location entry carries no location_id"))
            continue
        refs = loc.get("reference_pictures") or loc.get("references")
        if not (isinstance(refs, list) and refs):
            defects.append(_defect(
                LOCATION_REFERENCE_MISSING, "locations." + lid,
                "place '%s' has no reference pictures; it cannot hold one look" % lid,
                {"location_id": lid}))
        changes = loc.get("changes")
        if changes:
            states = loc.get("states")
            states = states if isinstance(states, dict) else {}
            for state in CHANGED_PLACE_STATES:
                if not states.get(state):
                    defects.append(_defect(
                        PLACE_STATE_MISSING, "locations." + lid,
                        "place '%s' changes in the story but has no '%s' state"
                        % (lid, state), {"location_id": lid, "state": state}))
    return defects


def validate_prop_ledger(prop_ledger, scenes=None):
    """One ledger line per story prop per scene: place, state, holder (N-106).

    ``prop_ledger``: ``{"props": [{prop_id, scenes: {scene_id: {place,
    state, holder}}}]}``. ``scenes``: the planned scene ids when known; a
    story prop missing a line for a scene it is in is refused.
    """
    defects = []
    props = prop_ledger.get("props") if isinstance(prop_ledger, dict) else None
    if not (isinstance(props, list) and props):
        defects.append(_defect(PROP_LEDGER_MISSING, "prop_ledger",
                               "the prop ledger is missing or empty"))
        return defects
    scene_ids = [_text(s.get("scene_id")) if isinstance(s, dict) else _text(s)
                 for s in (scenes or [])]
    scene_ids = [s for s in scene_ids if s]
    for prop in props:
        if not isinstance(prop, dict):
            continue
        pid = _text(prop.get("prop_id"))
        if not pid:
            defects.append(_defect(PROP_LEDGER_INCOMPLETE, "props",
                                   "a prop entry carries no prop_id"))
            continue
        lines = prop.get("scenes")
        lines = lines if isinstance(lines, dict) else {}
        for sid in scene_ids or list(lines):
            line = lines.get(sid)
            if not isinstance(line, dict):
                defects.append(_defect(
                    PROP_LEDGER_INCOMPLETE, "props." + pid,
                    "prop '%s' has no ledger line for scene '%s'" % (pid, sid),
                    {"prop_id": pid, "scene_id": sid}))
                continue
            for field in ("place", "state", "holder"):
                if not _text(line.get(field)):
                    defects.append(_defect(
                        PROP_LEDGER_INCOMPLETE, "props.%s.%s" % (pid, sid),
                        "prop '%s' scene '%s' has no %s" % (pid, sid, field),
                        {"prop_id": pid, "scene_id": sid, "field": field}))
    return defects


def validate_background_life(world):
    """A place in use declares who is there, how many, what they do (N-106).

    A place marked ``in_use`` (or given a non-empty ``crowd_state``) needs
    ``background_life``: ``{who, count, doing}``. A place the story calls
    full is recorded full by count, never left to a blank room.
    """
    defects = []
    for loc in _locations(world):
        lid = _text(loc.get("location_id")) or "?"
        crowd = loc.get("crowd_state")
        in_use = bool(loc.get("in_use")) or bool(crowd)
        if not in_use:
            continue
        life = loc.get("background_life")
        if not isinstance(life, dict):
            defects.append(_defect(
                BACKGROUND_LIFE_MISSING, "locations." + lid,
                "place '%s' is in use but names no background life" % lid,
                {"location_id": lid}))
            continue
        for field in ("who", "doing"):
            if not _text(life.get(field)):
                defects.append(_defect(
                    BACKGROUND_LIFE_MISSING, "locations.%s.%s" % (lid, field),
                    "place '%s' background life has no %s" % (lid, field),
                    {"location_id": lid, "field": field}))
        count = life.get("count")
        if isinstance(crowd, str) and "full" in crowd.lower():
            if not (isinstance(count, int) and not isinstance(count, bool) and count > 0):
                defects.append(_defect(
                    BACKGROUND_LIFE_MISSING, "locations.%s.count" % lid,
                    "place '%s' is full but its background life carries no count" % lid,
                    {"location_id": lid, "field": "count"}))
    return defects


def validate_world_building(world, prop_ledger=None, scenes=None):
    """The one packet the storyboard review reads (N-106)."""
    defects = []
    defects.extend(validate_location_bible(world))
    defects.extend(validate_background_life(world))
    if prop_ledger is not None or scenes is not None:
        defects.extend(validate_prop_ledger(prop_ledger or {}, scenes))
    return {"ok": not defects, "defect_count": len(defects), "defects": defects,
            "codes": sorted({d["code"] for d in defects})}
