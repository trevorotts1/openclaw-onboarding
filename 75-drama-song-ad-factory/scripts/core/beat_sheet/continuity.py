"""beat_sheet.continuity: the continuity checks on the story script (N-64).

Plan 3F.2. The same checks that guard the Story Beats run again on the joined
story script, where they catch a writer who drifted:

  * one entrance and one exit per location -- a character who is present, then
    absent, then present again inside one beat and place entered twice:
    ``DOUBLE_ENTRANCE``;
  * time of day moves forward between scenes -- ``TIME_BACKWARD``;
  * a wardrobe id changes only on a scene change -- ``WARDROBE_MID_SCENE``.

A finding with no later rule is section 3J MEDIUM; the three above are MAJOR
item 9, the section 3J story-logic break.

Stdlib only; data in, verdicts out; no model call, no write.
"""
from __future__ import annotations

from ._util import (finding, norm, num, row_people, rows, time_rank, wardrobe)

#: a beat that is a flashback may run backwards (3F.2)
FLASHBACK_FIELDS = ("flashback", "is_flashback")


def _ordered(script):
    return sorted(rows(script), key=lambda r: num(r.get("start_s")) or 0.0)


def _is_flashback(row):
    return any(bool(row.get(field)) for field in FLASHBACK_FIELDS)


def entrance_defects(script):
    """One entrance, one exit: presence must be contiguous inside a visit."""
    ordered = _ordered(script)
    out = []
    # per (beat, place): the set of people seen, and people who dropped out
    last_seen = {}
    dropped = {}
    for index, row in enumerate(ordered):
        scope = (row.get("beat_number"), norm(row.get("location_id")))
        here = row_people(row)
        for person in here:
            if person in dropped.get(scope, set()):
                out.append(finding("DOUBLE_ENTRANCE", "/rows/%d/on_screen" % index,
                                   "%r leaves and re-enters %r inside one visit"
                                   % (person, scope[1] or "the place"), who=person))
            last_seen[(scope, person)] = index
        # anyone seen earlier in this visit but absent now has left
        seen = {person for (s, person) in last_seen if s == scope}
        for person in seen - here:
            dropped.setdefault(scope, set()).add(person)
    return out


def time_defects(script):
    """Time of day never runs backwards between scenes, unless a flashback."""
    out = []
    previous_rank = None
    previous_scene = None
    for index, row in enumerate(_ordered(script)):
        rank = time_rank(row.get("time_of_day"))
        if rank is None:
            continue
        scene = norm(row.get("location_id"))
        if previous_rank is not None and rank < previous_rank \
                and scene != previous_scene and not _is_flashback(row):
            out.append(finding("TIME_BACKWARD", "/rows/%d/time_of_day" % index,
                               "time of day runs backwards between scenes"))
        previous_rank, previous_scene = rank, scene
    return out


def wardrobe_defects(script):
    """A wardrobe id changes only where the place or the time of day changes."""
    out = []
    previous = None
    for index, row in enumerate(_ordered(script)):
        if previous is not None:
            same_scene = (norm(previous.get("location_id")) == norm(row.get("location_id"))
                          and norm(previous.get("time_of_day")) == norm(row.get("time_of_day")))
            if same_scene:
                before, now = wardrobe(previous), wardrobe(row)
                for character in set(before) & set(now):
                    if before[character] != now[character]:
                        out.append(finding("WARDROBE_MID_SCENE",
                                           "/rows/%d/wardrobe/%s" % (index, character),
                                           "%r changes wardrobe inside one scene" % character,
                                           who=character))
        previous = row
    return out


def continuity_defects(script):
    """All three continuity checks on the joined story script (N-64)."""
    return entrance_defects(script) + time_defects(script) + wardrobe_defects(script)


def check_continuity(script):
    """Result envelope for the script's continuity checks (N-64)."""
    defects = continuity_defects(script)
    return {"ok": not any(d.get("level") == "MAJOR" for d in defects),
            "defects": defects}


def _selfcheck():
    cues = {"eyes": "steady", "brows": "set", "mouth": "firm",
            "smile": "no", "teeth": "no", "tears": "none"}

    def row(i, start, place, time, who, wear):
        return {"row_id": "r%d" % i, "line_id": "l%d" % i, "beat_number": 1,
                "start_s": start, "end_s": start + 4.0, "location_id": place,
                "time_of_day": time, "on_screen": who, "wardrobe": wear,
                "emotion": "resolve", "intensity": 2, "facial_cues": cues}

    good = [row(1, 0.0, "kitchen", "morning", ["c1"], {"c1": "w1"}),
            row(2, 4.0, "kitchen", "morning", ["c1"], {"c1": "w1"}),
            row(3, 8.0, "church", "midday", ["c1"], {"c1": "w2"})]
    assert check_continuity({"rows": good})["ok"], check_continuity({"rows": good})
    back = [row(1, 0.0, "kitchen", "evening", ["c1"], {"c1": "w1"}),
            row(2, 4.0, "church", "morning", ["c1"], {"c1": "w1"})]
    assert any(d["code"] == "TIME_BACKWARD"
               for d in check_continuity({"rows": back})["defects"])
    wear = [row(1, 0.0, "kitchen", "morning", ["c1"], {"c1": "w1"}),
            row(2, 4.0, "kitchen", "morning", ["c1"], {"c1": "w2"})]
    assert any(d["code"] == "WARDROBE_MID_SCENE"
               for d in check_continuity({"rows": wear})["defects"])
    gap = [row(1, 0.0, "kitchen", "morning", ["c1"], {"c1": "w1"}),
           row(2, 4.0, "kitchen", "morning", [], {"c1": "w1"}),
           row(3, 8.0, "kitchen", "morning", ["c1"], {"c1": "w1"})]
    assert any(d["code"] == "DOUBLE_ENTRANCE"
               for d in check_continuity({"rows": gap})["defects"])


if __name__ == "__main__":
    _selfcheck()
    print("beat_sheet.continuity selfcheck: OK")
