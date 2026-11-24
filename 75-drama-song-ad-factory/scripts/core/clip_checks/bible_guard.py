#!/usr/bin/env python3
"""bible_guard.py: nobody and nowhere is invented in a shot (N-122, section 3C.10).

The vision half of the Bible Guard. Part 1 (pre-spend) is the dispatcher's
and is asked for here so one module holds the codes; part 2 is the post-
generation questions asked in the same call as the consistency, cast and
world checks; part 3 is the automatic fix, returned as an instruction rather
than executed (the dispatcher sends the job again).

Codes: CAST_NOT_IN_BIBLE, CAST_REFERENCE_MISSING, LOCATION_NOT_IN_WORLD_BIBLE,
WORLD_REFERENCE_MISSING, UNNAMED_PERSON_IN_PROMPT, UNNAMED_PLACE_IN_PROMPT;
then CHARACTER_MISMATCH / UNLISTED_PERSON, PLACE_MISMATCH /
SET_PIECE_MISSING, CROWD_MISMATCH / CHOIR_COUNT_MISMATCH, LIGHT_OFF_CLOCK.
"""
from __future__ import annotations

import re

from . import severity as _SV
from . import vision as _V

TOOL_NAME = "clip_checks.bible_guard"
TOOL_VERSION = "1.0.0"

CAST_NOT_IN_BIBLE = "CAST_NOT_IN_BIBLE"
CAST_REFERENCE_MISSING = "CAST_REFERENCE_MISSING"
LOCATION_NOT_IN_WORLD_BIBLE = "LOCATION_NOT_IN_WORLD_BIBLE"
WORLD_REFERENCE_MISSING = "WORLD_REFERENCE_MISSING"
UNNAMED_PERSON_IN_PROMPT = "UNNAMED_PERSON_IN_PROMPT"
UNNAMED_PLACE_IN_PROMPT = "UNNAMED_PLACE_IN_PROMPT"

#: Words a prompt uses to describe a person or a room with no id behind them.
_PERSON_WORDS = re.compile(
    r"\b(an? (older|young|elderly|grey-haired|gray-haired) (woman|man|person)"
    r"|an? (woman|man|person|girl|boy) (in|with|standing|sitting)"
    r"|some people|a crowd|the congregation|people in the background)\b",
    re.IGNORECASE)
_PLACE_WORDS = re.compile(
    r"\b(a (church|kitchen|office|sanctuary|room|house|street|yard|porch)"
    r"|an? (office|apartment))\b", re.IGNORECASE)

FIX = {
    CAST_NOT_IN_BIBLE: "create, check and lock the missing character, raise "
                       "the lock version, then send the job again",
    LOCATION_NOT_IN_WORLD_BIBLE: "create, check and lock the missing place, "
                                 "then send the job again",
    CAST_REFERENCE_MISSING: "attach the locked pictures and send again",
    WORLD_REFERENCE_MISSING: "make the missing variant from the base wide, "
                             "then attach it and send again",
    UNNAMED_PERSON_IN_PROMPT: "return the row to its writer to name the id; "
                              "the Prompt Builder rebuilds the prompt",
    UNNAMED_PLACE_IN_PROMPT: "return the row to its writer to name the id; "
                             "the Prompt Builder rebuilds the prompt",
}


def pre_spend(job, characters, places):
    """Part 1: every named person and place must be locked, with references attached."""
    findings = []
    characters = characters or {}
    places = places or {}
    attached = set(job.get("references") or [])
    for name in job.get("people") or []:
        entry = characters.get(name)
        if not entry:
            findings.append({"code": CAST_NOT_IN_BIBLE, "level": _SV.MAJOR,
                             "item": 5, "text": "%s is not in the bible" % name,
                             "fix": FIX[CAST_NOT_IN_BIBLE]})
        elif not set(entry.get("references") or []) <= attached:
            findings.append({"code": CAST_REFERENCE_MISSING, "level": _SV.MAJOR,
                             "item": 5,
                             "text": "%s's pictures are not attached" % name,
                             "fix": FIX[CAST_REFERENCE_MISSING]})
    for place in job.get("places") or []:
        entry = places.get(place)
        if not entry:
            findings.append({"code": LOCATION_NOT_IN_WORLD_BIBLE,
                             "level": _SV.MAJOR, "item": 5,
                             "text": "%s is not in the world bible" % place,
                             "fix": FIX[LOCATION_NOT_IN_WORLD_BIBLE]})
        else:
            wanted = entry.get("reference") or entry.get("references") or []
            if isinstance(wanted, str):
                wanted = [wanted]
            if not set(wanted) <= attached:
                findings.append({"code": WORLD_REFERENCE_MISSING,
                                 "level": _SV.MAJOR, "item": 5,
                                 "text": "%s's reference is not attached" % place,
                                 "fix": FIX[WORLD_REFERENCE_MISSING]})
    text = str(job.get("prompt") or "")
    named = " ".join(job.get("people") or []) + " " + " ".join(job.get("places") or [])
    if _PERSON_WORDS.search(text) and not named.strip():
        findings.append({"code": UNNAMED_PERSON_IN_PROMPT, "level": _SV.MAJOR,
                         "item": 5, "text": "a person is described with no id",
                         "fix": FIX[UNNAMED_PERSON_IN_PROMPT]})
    if _PLACE_WORDS.search(text) and not (job.get("places") or []):
        findings.append({"code": UNNAMED_PLACE_IN_PROMPT, "level": _SV.MAJOR,
                         "item": 5, "text": "a place is described with no id",
                         "fix": FIX[UNNAMED_PLACE_IN_PROMPT]})
    return {"findings": findings, "pass": not _SV.only_major(findings)}


def post_generation(answers, controls=(None, None)):
    """Part 2: the place, set-piece, crowd, choir and clock questions in one call."""
    gate = _V.control_gate(controls[0], controls[1],
                          _V.CINEMATIC_UNMEASURED)
    if gate:
        return {"findings": [gate], "pass": False}
    return _V.world_check(answers)


def escalation(attempts):
    """Part 3: after a second failed try, the shot goes to the run owner."""
    n = int(attempts or 0)
    return {"escalate": n >= 2,
            "action": ("send both takes, the reference it failed against and "
                       "the question that failed to the run owner; everything "
                       "else keeps moving") if n >= 2 else None}


if __name__ == "__main__":
    # Control: a missing person/place refuses before spend, unnamed words in a
    # prompt refuse, a locked and attached job passes, and two failed tries
    # escalate without stopping the rest of the run.
    r = pre_spend({"people": ["lead"], "places": ["kitchen"],
                   "references": []},
                  {"lead": {"references": ["a.png"]}}, {})
    codes = [f["code"] for f in r["findings"]]
    assert "CAST_REFERENCE_MISSING" in codes          # picture not attached
    assert "LOCATION_NOT_IN_WORLD_BIBLE" in codes     # place missing
    assert not r["pass"]
    ok = pre_spend({"people": ["lead"], "references": ["a.png"]},
                   {"lead": {"references": ["a.png"]}}, {})
    assert ok["pass"], ok
    unnamed = pre_spend({"prompt": "an older woman in a church"}, {}, {})
    assert [f["code"] for f in unnamed["findings"]] == \
        ["UNNAMED_PERSON_IN_PROMPT", "UNNAMED_PLACE_IN_PROMPT"]
    assert not post_generation({}, controls=(None, None))["pass"]
    assert escalation(1)["escalate"] is False
    assert escalation(2)["escalate"] is True
    print("bible_guard: control PASS")
