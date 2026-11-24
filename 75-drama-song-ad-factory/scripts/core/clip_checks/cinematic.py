#!/usr/bin/env python3
"""cinematic.py: the cinematic checks with their severities (N-107, sections 3J and 3K).

Per clip: screen direction, jump cuts, entry and exit joins, light and colour
inside a scene, prop continuity, the place check and the exit-against-entry
check on the clip's last frame. A contact sheet at 2 frames per second is
required for any clip with a person in the foreground. A MEDIUM is logged and
passes; a break that confuses the story (or matters to it) is MAJOR; floaty
or morphing foreground motion is MAJOR (3J item 13).

The judgement itself lives in ``vision.cinematic_check``; this module adds
what the row names and vision does not: the sample plan and the per-clip
result row.
"""
from __future__ import annotations

from . import severity as _SV
from . import vision as _V

TOOL_NAME = "clip_checks.cinematic"
TOOL_VERSION = "1.0.0"

PLACE_MISMATCH = "PLACE_MISMATCH"
EXIT_ENTRY_MISMATCH = "EXIT_ENTRY_MISMATCH"
CONTACT_SHEET_FPS = 2


def contact_sheet_times(duration_s):
    """2 frames per second over the clip (N-107's contact sheet)."""
    try:
        d = float(duration_s)
    except (TypeError, ValueError):
        return []
    if d <= 0:
        return []
    step = 1.0 / CONTACT_SHEET_FPS
    times, t = [], 0.0
    while t < d:
        times.append(round(t, 3))
        t += step
    return times


def check(row, duration_s=None, required=None):
    """One clip's cinematic result.

    ``row`` keys (all optional, None = unasked -> UNAVAILABLE):
    screen_direction_ok, jump_cut, entry_exit_ok, light_colour_ok,
    prop_continuity_ok, place_match, floaty_motion, confuses_story, matters,
    lip_sync_picture, foreground_person.

    ``required`` names the questions this clip must answer (default: all six
    of 3J/3K); an unanswered one is UNAVAILABLE, never a pass.
    """
    row = dict(row or {})
    out = _V.cinematic_check(row, required=required)
    if duration_s is not None or row.get("duration_s") is not None:
        out["contact_sheet_times"] = contact_sheet_times(
            row.get("duration_s", duration_s))
    if row.get("foreground_person"):
        out["contact_sheet_required"] = True
    return out


if __name__ == "__main__":
    # Control: the sheet is 2 frames a second; a non-confusing break is MEDIUM
    # and passes; a confusing one is MAJOR item 16; an unasked question is
    # item 15 and never a pass.
    assert contact_sheet_times(1.0) == [0.0, 0.5]
    assert contact_sheet_times(0) == [] and contact_sheet_times("x") == []
    ok = {"screen_direction_ok": True, "jump_cut": False, "entry_exit_ok": True,
          "light_colour_ok": True, "prop_continuity_ok": True,
          "place_match": True}
    assert check(dict(ok))["pass"]
    medium = check(dict(ok, screen_direction_ok=False, confuses_story=False))
    assert medium["pass"] and medium["findings"][0]["level"] == "MEDIUM"
    major = check(dict(ok, screen_direction_ok=False, confuses_story=True))
    assert not major["pass"] and major["findings"][0]["item"] == 16
    unasked = check({"screen_direction_ok": True})
    assert not unasked["pass"]
    assert unasked["findings"][0]["code"] == "CINEMATIC_UNMEASURED"
    floaty = check(dict(ok, foreground_person=True, floaty_motion=True),
                   duration_s=1.0)
    assert floaty["contact_sheet_required"]
    assert floaty["findings"][0]["level"] == "MAJOR"
    print("cinematic: control PASS")
