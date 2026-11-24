#!/usr/bin/env python3
"""bible_guard.py: nobody and nowhere is invented in a shot (N-122, section 3C.10). Stdlib only.

Two guards around every picture job and every clip job:

* before any spend, the dispatcher refuses a job whose text names a person or a
  place in words with no id behind it (``UNNAMED_PERSON_IN_PROMPT`` /
  ``UNNAMED_PLACE_IN_PROMPT``), or whose beat needs a character or place that
  has no locked bible entry (``CAST_NOT_IN_BIBLE`` /
  ``LOCATION_NOT_IN_WORLD_BIBLE``);
* after generation, one vision call names a stranger, a wrong face, a wrong
  room, a missing set piece, a wrong crowd or light off the clock.

Part 3 is the automatic fix. Code decides what to do from the failure code and
the try count: create and lock the missing entry, attach the refs, return the
row to its writer, remake once more, then escalate to the run owner after the
second try. No person is asked while a fix is still available.

Stdlib only; no provider call, no spend, no IO.
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.bible-guard/v1"

CAST_NOT_IN_BIBLE = "CAST_NOT_IN_BIBLE"
CAST_REFERENCE_MISSING = "CAST_REFERENCE_MISSING"
LOCATION_NOT_IN_WORLD_BIBLE = "LOCATION_NOT_IN_WORLD_BIBLE"
WORLD_REFERENCE_MISSING = "WORLD_REFERENCE_MISSING"
UNNAMED_PERSON_IN_PROMPT = "UNNAMED_PERSON_IN_PROMPT"
UNNAMED_PLACE_IN_PROMPT = "UNNAMED_PLACE_IN_PROMPT"
CHARACTER_MISMATCH = "CHARACTER_MISMATCH"
UNLISTED_PERSON = "UNLISTED_PERSON"
PLACE_MISMATCH = "PLACE_MISMATCH"
SET_PIECE_MISSING = "SET_PIECE_MISSING"
CROWD_MISMATCH = "CROWD_MISMATCH"
CHOIR_COUNT_MISMATCH = "CHOIR_COUNT_MISMATCH"
LIGHT_OFF_CLOCK = "LIGHT_OFF_CLOCK"

#: Nouns that describe a person by role with no id behind them.
PERSON_NOUNS = (
    "woman", "man", "child", "children", "boy", "girl", "person", "someone",
    "somebody", "mother", "father", "grandmother", "grandfather", "driver",
    "janitor", "cashier", "clerk", "nurse", "pastor", "officer", "customer",
    "neighbour", "neighbor", "stranger", "official", "worker",
)
#: Nouns that describe a place with no id behind them.
PLACE_NOUNS = (
    "church", "room", "office", "kitchen", "house", "home", "street", "store",
    "school", "hall", "sanctuary", "vestry", "narthex", "porch", "yard",
    "building", "apartment",
)

#: Codes the run fixes by itself; only the second failure escalates.
_FIXABLE = frozenset({
    CAST_NOT_IN_BIBLE, CAST_REFERENCE_MISSING, LOCATION_NOT_IN_WORLD_BIBLE,
    WORLD_REFERENCE_MISSING, UNNAMED_PERSON_IN_PROMPT, UNNAMED_PLACE_IN_PROMPT,
    CHARACTER_MISMATCH, UNLISTED_PERSON, PLACE_MISMATCH, SET_PIECE_MISSING,
    CROWD_MISMATCH, CHOIR_COUNT_MISMATCH, LIGHT_OFF_CLOCK,
})


def _text(v):
    return v.strip() if isinstance(v, str) else ""


def _ids(job, *keys):
    for k in keys:
        v = job.get(k)
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
    return []


def _words_in(text, nouns):
    low = " %s " % str(text or "").lower()
    return [n for n in nouns if (" %s " % n) in low or (" %ss " % n) in low]


def check_prompt(job):
    """Part 1 (pure): a prompt must not name a person or place with no id.

    job: {prompt, character_ids?, location_id?, needs_person?, needs_place?}.
    Returns findings for unnamed people and places in the prompt text.
    """
    findings = []
    prompt = _text(job.get("prompt") or job.get("text"))
    if not prompt:
        return findings
    who = _ids(job, "character_ids", "characters", "cast")
    where = _ids(job, "location_id", "location")
    persons = _words_in(prompt, PERSON_NOUNS)
    places = _words_in(prompt, PLACE_NOUNS)
    if persons and not who:
        findings.append({"code": UNNAMED_PERSON_IN_PROMPT,
                         "detail": "prompt names a person in words with no id: %s"
                         % ", ".join(persons)})
    if places and not where:
        findings.append({"code": UNNAMED_PLACE_IN_PROMPT,
                         "detail": "prompt names a place in words with no id: %s"
                         % ", ".join(places)})
    return findings


def check_pre_spend(job, character_bible_ids=None, world_ids=None):
    """Part 1 before any spend: unnamed words, and missing bible entries.

    character_bible_ids: the set of locked character ids.
    world_ids: the set of locked place ids.
    Refusals: UNNAMED_* from the prompt; CAST_NOT_IN_BIBLE and
    LOCATION_NOT_IN_WORLD_BIBLE when a job's ids are not in the bibles;
    CAST_REFERENCE_MISSING / WORLD_REFERENCE_MISSING when an id has no refs
    attached to the job.
    """
    findings = list(check_prompt(job))
    want_cast = _ids(job, "character_ids", "characters", "cast")
    want_place = _ids(job, "location_id", "location")
    have_cast_refs = set(_ids(job, "reference_ids", "cast_reference_ids"))
    have_world_refs = set(_ids(job, "world_reference_ids", "location_reference_ids"))
    bible = set(character_bible_ids or ())
    world = set(world_ids or ())
    for cid in want_cast:
        if cid not in bible:
            findings.append({"code": CAST_NOT_IN_BIBLE, "character_id": cid,
                             "detail": "character %r is not in the character bible" % cid})
        elif cid not in have_cast_refs and have_cast_refs:
            findings.append({"code": CAST_REFERENCE_MISSING, "character_id": cid,
                             "detail": "no locked reference attached for %r" % cid})
    for lid in want_place:
        if lid not in world:
            findings.append({"code": LOCATION_NOT_IN_WORLD_BIBLE, "location_id": lid,
                             "detail": "place %r is not in the world bible" % lid})
        elif lid not in have_world_refs and have_world_refs:
            findings.append({"code": WORLD_REFERENCE_MISSING, "location_id": lid,
                             "detail": "no world reference attached for %r" % lid})
    return findings


def decide_fix(code, try_count=0):
    """Part 3: what the run does by itself for one failure code.

    Returns {action, escalate, detail}. ``try_count`` is how many paid takes the
    shot has already had. After the second failure the shot escalates with both
    takes; everything else keeps moving.
    """
    if code not in _FIXABLE:
        return {"action": "escalate", "escalate": True,
                "detail": "unknown failure %r" % (code,)}
    if try_count >= 2:
        return {"action": "escalate", "escalate": True,
                "detail": "second try failed for %s; send both takes to the run "
                          "owner, keep the rest of the run moving" % code}
    if code in (CAST_NOT_IN_BIBLE, LOCATION_NOT_IN_WORLD_BIBLE):
        return {"action": "create_and_lock", "escalate": False,
                "detail": "create the missing entry from the Story Beats, make its "
                          "references, run the reference gate and lock it, then resend"}
    if code in (CAST_REFERENCE_MISSING, WORLD_REFERENCE_MISSING):
        return {"action": "attach_and_resend", "escalate": False,
                "detail": "attach the locked pictures (make the variant first if it "
                          "does not exist) and resend"}
    if code in (UNNAMED_PERSON_IN_PROMPT, UNNAMED_PLACE_IN_PROMPT):
        return {"action": "return_to_writer", "escalate": False,
                "detail": "return the row to its own writer to name the id; rebuild "
                          "the prompt"}
    return {"action": "remake_from_refs", "escalate": False,
            "detail": "remake this one shot from the correct references"}


def selfcheck():
    bad = check_prompt({"prompt": "an older woman stands in a church"})
    assert [f["code"] for f in bad] == [UNNAMED_PERSON_IN_PROMPT,
                                        UNNAMED_PLACE_IN_PROMPT], bad
    ok = check_prompt({"prompt": "the lead stands in the sanctuary",
                       "character_ids": ["lead"], "location_id": "sanctuary"})
    assert ok == []
    g = check_pre_spend({"prompt": "x", "character_ids": ["ghost"],
                         "location_id": "moon"},
                        character_bible_ids={"lead"}, world_ids={"sanctuary"})
    codes = {f["code"] for f in g}
    assert CAST_NOT_IN_BIBLE in codes and LOCATION_NOT_IN_WORLD_BIBLE in codes
    assert decide_fix(CAST_NOT_IN_BIBLE)["action"] == "create_and_lock"
    assert decide_fix(CHARACTER_MISMATCH, try_count=2)["escalate"] is True
    print("character_bible.bible_guard selfcheck OK")


if __name__ == "__main__":
    selfcheck()
