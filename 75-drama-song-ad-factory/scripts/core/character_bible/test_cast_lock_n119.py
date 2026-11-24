#!/usr/bin/env python3
"""test_cast_lock_n119.py: the Cast Lock (N-119, section 3C.9).

Done when: a cast entry with no locked entry is CAST_NOT_IN_BIBLE; a locked
entry with no references is CAST_REFERENCE_MISSING; one identity block pasted
onto two characters is IDENTITY_BLOCK_WRONG_CHARACTER; two members sharing a
look are CAST_LOOKALIKE; a beat naming an unlocked person is CAST_NOT_IN_BIBLE;
and the consistency check names a stranger and a missing member.

Run: python3 scripts/core/character_bible/test_cast_lock_n119.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from character_bible import cast_lock as CL       # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def cast(cid, look=None):
    entry = {"character_id": cid}
    if look:
        entry["look_signature"] = look
    return entry


def locked(identity="ava-lock"):
    return {"identity_block": identity, "refs": [{"path": "/refs/master.png"}]}


def test_missing_lock_entry():
    manifest = {"cast": [cast("ava"), cast("mother")]}
    lock = {"characters": {"ava": locked()}}
    packet = CL.check_cast_lock(manifest, lock)
    check("N119-1 an unlocked cast member is CAST_NOT_IN_BIBLE",
          packet["outcome"] == "fail" and packet["codes"] == [CL.CAST_NOT_IN_BIBLE]
          and packet["findings"][0]["character_id"] == "mother", packet)


def test_references_required():
    manifest = {"cast": [cast("ava")]}
    packet = CL.check_cast_lock(manifest, {"characters": {"ava":
                                                          {"identity_block": "x", "refs": []}}})
    check("N119-2 a locked entry with no references is CAST_REFERENCE_MISSING",
          CL.CAST_REFERENCE_MISSING in packet["codes"], packet)


def test_shared_identity_and_look():
    manifest = {"cast": [cast("ava"), cast("mother", look="grey-bun")]}
    manifest["cast"][0]["look_signature"] = "grey-bun"
    lock = {"characters": {"ava": locked("same-lock"),
                           "mother": locked("same-lock")}}
    packet = CL.check_cast_lock(manifest, lock)
    check("N119-3 one identity block on two characters is refused",
          CL.IDENTITY_BLOCK_WRONG_CHARACTER in packet["codes"], packet)
    check("N119-4 two look-alike members are named as a pair",
          CL.CAST_LOOKALIKE in packet["codes"], packet)


def test_beats_and_consistency():
    manifest = {"cast": [cast("ava")]}
    packet = CL.check_cast_in_beats([{"beat_id": 1, "cast_ids": ["ava", "ruth"]}],
                                    manifest)
    check("N119-5 a beat naming an unlocked person is CAST_NOT_IN_BIBLE",
          packet["codes"] == [CL.CAST_NOT_IN_BIBLE]
          and packet["findings"][0]["character_id"] == "ruth", packet)
    seen = [{"character_id": "ava"}, {"character_id": "stranger"}]
    packet = CL.check_cast_consistency(seen, ["ava"])
    check("N119-6 a stranger in the frame is UNLISTED_PERSON",
          packet["codes"] == [CL.UNLISTED_PERSON], packet)
    packet = CL.check_cast_members_present(["ava", "mother"], seen)
    check("N119-7 a cast member the beat needs but the frame lacks is named",
          packet["codes"] == [CL.CAST_MEMBER_MISSING]
          and packet["findings"][0]["character_id"] == "mother", packet)
    crowd = CL.check_cast_consistency([{"character_id": "crowd-1"}], ["ava"],
                                      crowd_ids=["crowd-1"])
    check("N119-8 a declared crowd is not a stranger", crowd["outcome"] == "pass", crowd)


def test_run():
    test_missing_lock_entry()
    test_references_required()
    test_shared_identity_and_look()
    test_beats_and_consistency()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 8/8" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
