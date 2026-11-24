#!/usr/bin/env python3
"""cast_lock.py: the cast-consistency half of the Cast Lock (N-119, section 3C.9).

What this module answers, on every picture and three frames of every clip:
is every visible face on the shot's cast (``UNLISTED_PERSON``), does each cast
member match their own lock (``CHARACTER_MISMATCH``), is each in this beat's
outfit, and is anyone missing who the beat says is here
(``CAST_MEMBER_MISSING``).

The plan-side refusals (``CAST_NOT_IN_BIBLE``, ``CAST_REFERENCE_MISSING``,
``CAST_LOOKALIKE``, ``IDENTITY_BLOCK_WRONG_CHARACTER``) are the dispatcher's
and U-STORY's; the questions themselves are ``vision.cast_check``. Only the
picked-set strip pass belongs here too, once per run, on the whole set.

stdlib only; the vision call is injected.
"""
from __future__ import annotations

from . import severity as _SV
from . import vision as _V

TOOL_NAME = "clip_checks.cast_lock"
TOOL_VERSION = "1.0.0"

UNLISTED_PERSON = "UNLISTED_PERSON"
CHARACTER_MISMATCH = "CHARACTER_MISMATCH"
CAST_MEMBER_MISSING = "CAST_MEMBER_MISSING"
CAST_NOT_IN_BIBLE = "CAST_NOT_IN_BIBLE"
CAST_REFERENCE_MISSING = "CAST_REFERENCE_MISSING"
IDENTITY_BLOCK_WRONG_CHARACTER = "IDENTITY_BLOCK_WRONG_CHARACTER"
CAST_LOOKALIKE = "CAST_LOOKALIKE"


def check(answers, cast_ids, declared_crowd=False, controls=(None, None)):
    """The four cast questions on one frame, behind a control pair."""
    gate = _V.control_gate(controls[0], controls[1],
                          _V.CONSISTENCY_CHECK_UNAVAILABLE)
    if gate:
        return {"findings": [gate], "pass": False}
    return _V.cast_check(answers, cast_ids, declared_crowd=declared_crowd)


def plan_refusal(job, bible):
    """The pre-spend refusals the dispatcher asks this module for.

    ``job``: ``{names: [...], references: [...], identity_blocks: [...]}``;
    ``bible``: ``{character id: {references: [...], identity: str}}``.
    Every named person must have a bible entry with references attached, and
    no job may carry an identity block that is not its owner's.
    """
    findings = []
    bible = bible or {}
    for name in job.get("names") or []:
        entry = bible.get(name)
        if not entry:
            findings.append({"code": CAST_NOT_IN_BIBLE, "level": _SV.MAJOR,
                             "item": 5, "text": "%s has no bible entry" % name})
            continue
        if entry.get("references"):
            attached = set(job.get("references") or [])
            if not set(entry["references"]) <= attached:
                findings.append({"code": CAST_REFERENCE_MISSING,
                                 "level": _SV.MAJOR, "item": 5,
                                 "text": "%s's locked pictures are not all "
                                         "attached" % name})
    for block_owner, block in (job.get("identity_blocks") or {}).items():
        owner = bible.get(block_owner) or {}
        if owner.get("identity") != block:
            findings.append({"code": IDENTITY_BLOCK_WRONG_CHARACTER,
                             "level": _SV.MAJOR, "item": 5,
                             "text": "an identity block on %s is not its owner's"
                                     % block_owner})
    return {"findings": findings, "pass": not _SV.only_major(findings)}


#: The four things 3C.9 rule 4 compares. Two cast members alike in all four
#: would be confused on screen, so one of them is changed before approval.
LINEUP_FIELDS = ("age", "hair", "build", "silhouette")


def _likeness(entry):
    return tuple(str((entry or {}).get(f, "")).strip().lower()
                 for f in LINEUP_FIELDS)


def line_up(bible):
    """3C.9 rule 4: no two people look alike by accident.

    ``bible``: {character id: {age, hair, build, silhouette, ...}}. Two entries
    alike in all four fields raise ``CAST_LOOKALIKE`` (MAJOR item 5) naming the
    pair; a relation ("mother", "daughter") never separates two faces by
    itself, so the four fields are what is compared. An entry with fewer than
    all four fields cannot be compared and is reported as unavailable, never
    passed silently.
    """
    findings, rows = [], []
    entries = [(cid, entry) for cid, entry in (bible or {}).items()
               if isinstance(entry, dict)]
    for cid, entry in entries:
        missing = [f for f in LINEUP_FIELDS if not _likeness(entry)[
            LINEUP_FIELDS.index(f)]]
        if missing:
            findings.append({"code": "CAST_CHECK_UNAVAILABLE", "level": _SV.MAJOR,
                             "item": 15,
                             "text": "%s has no %s; the line-up cannot compare "
                                     "it" % (cid, ", ".join(missing))})
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, ea = entries[i]
            b, eb = entries[j]
            if _likeness(ea) == _likeness(eb):
                findings.append({"code": CAST_LOOKALIKE, "level": _SV.MAJOR,
                                 "item": 5,
                                 "text": "%s and %s share %s; change one until "
                                         "a viewer cannot confuse them"
                                         % (a, b, ", ".join(LINEUP_FIELDS)),
                                 "pair": [a, b]})
                rows.append({"pair": [a, b], "alike": list(LINEUP_FIELDS)})
    return {"findings": findings, "pass": not _SV.only_major(findings),
            "pairs": rows}


if __name__ == "__main__":
    # Control: the four questions fail closed, the refusals name their item, and
    # two people alike in all four fields are named as a pair.
    def truth(images, questions):
        return {"answers": {q: True for q in questions}}

    assert check({"unlisted_person": True, "cast_match": True,
                  "wardrobe_match": True, "cast_missing": True},
                 ["lead"], controls=(True, False))["pass"]
    blind = check({}, ["lead"], controls=(None, None))
    assert not blind["pass"] and blind["findings"][0]["item"] == 15
    assert plan_refusal({"names": ["ghost"]}, {})["findings"][0]["code"] == \
        CAST_NOT_IN_BIBLE
    cast = {
        "denise": {"age": 41, "hair": "black bun", "build": "slim",
                   "silhouette": "tall"},
        "mother": {"age": 68, "hair": "grey waves", "build": "round",
                   "silhouette": "short"},
        "aunt": {"age": 68, "hair": "grey waves", "build": "round",
                 "silhouette": "short"},
    }
    out = line_up(cast)
    assert not out["pass"] and out["findings"][0]["code"] == CAST_LOOKALIKE
    assert out["findings"][0]["pair"] == ["mother", "aunt"]
    ok = line_up({"denise": cast["denise"], "mother": cast["mother"]})
    assert ok["pass"] and not ok["pairs"]
    thin = line_up({"lead": {"age": 30}})
    assert not thin["pass"] and thin["findings"][0]["item"] == 15
    print("cast_lock: control PASS")
