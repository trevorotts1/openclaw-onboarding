#!/usr/bin/env python3
"""test_reference_sets_n40.py: N-40 reference sets, wardrobe lock, approvals.

Done when: a character's set carries all four views and one wardrobe picture
per wardrobe, each fingerprinted; an unhashed view or a wardrobe with no
picture is refused; a wardrobe entry lists every accessory by name or an empty
list; a main character's set without the seven expression sheets is refused;
and the set is approved once.

Run: python3 scripts/core/character_bible/test_reference_sets_n40.py
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from character_bible import expression_sheets as EX       # noqa: E402
from character_bible import reference_sets as RS         # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def digest(char):
    return hashlib.sha256(char.encode("utf-8")).hexdigest()


def views(**over):
    base = {v: {"path": "/refs/%s.png" % v, "digest": digest(v[0])}
            for v in RS.REFERENCE_VIEWS}
    base.update(over)
    return base


def wardrobe(wid="w1", picture=True):
    entry = RS.wardrobe_entry(wid, "grey robe", ["stole", "glasses"])
    if picture:
        entry["picture"] = {"path": "/refs/%s.png" % wid, "digest": digest("a")}
    return entry


def sheets_for(cid="ava"):
    return EX.build_expression_sheets(
        cid, {name: {"path": "/refs/%s.png" % name, "digest": digest(name[0])}
              for name in EX.EXPRESSION_SHEETS},
        master={"path": "/refs/master.png", "digest": digest("m")})


def codes(findings):
    return sorted({f["code"] for f in findings})


def test_complete_set_passes():
    entry = RS.build_reference_set("ava", views(), [wardrobe()])
    check("N40-1 complete set has no defect", RS.validate_reference_set(entry) == [],
          RS.validate_reference_set(entry))
    check("N40-2 lock lists every file with its digest",
          len(RS.lock_entries([entry])["characters"]["ava"]["files"]) == 5)
    check("N40-3 wardrobes are named in the lock with accessories",
          RS.lock_entries([entry])["characters"]["ava"]["files"][-1]["accessories"]
          == ["stole", "glasses"])


def test_missing_view_and_unhashed_refused():
    bad = views()
    del bad["profile"]
    check("N40-4 a missing view is refused",
          RS.REFERENCE_VIEW_MISSING in codes(
              RS.validate_reference_set(RS.build_reference_set("ava", bad, [wardrobe()]))))
    unhashed = views(profile={"path": "/refs/profile.png"})
    check("N40-5 an unhashed view is refused",
          RS.REFERENCE_UNHASHED in codes(
              RS.validate_reference_set(RS.build_reference_set("ava", unhashed, [wardrobe()]))))


def test_wardrobe_accessories_lock():
    no_picture = wardrobe(picture=False)
    check("N40-6 a wardrobe with no picture is refused",
          RS.WARDROBE_PICTURE_MISSING in codes(
              RS.validate_reference_set(RS.build_reference_set("ava", views(), [no_picture]))))
    try:
        RS.wardrobe_entry("w1", "grey robe", None)
    except ValueError as exc:
        check("N40-7 an omitted accessories field is refused",
              "ACCESSORIES_UNDECLARED" in str(exc), exc)
    else:
        check("N40-7 an omitted accessories field is refused", False, "nothing refused")
    empty = RS.wardrobe_entry("w1", "grey robe", [])
    check("N40-8 a declared empty accessory list is allowed",
          RS.validate_wardrobe_entry(empty) == [])


def test_main_character_needs_expression_sheets():
    entry = RS.build_reference_set("ava", views(), [wardrobe()], main=True)
    check("N40-9 a main set without expression sheets is refused",
          EX.EXPRESSION_SHEETS_INCOMPLETE in codes(RS.validate_reference_set(entry)))
    entry["expressions"] = sheets_for()
    check("N40-10 a main set with the seven sheets passes",
          RS.validate_reference_set(entry) == [], RS.validate_reference_set(entry))
    short = sheets_for()
    del short["sheets"]["determined"]
    entry["expressions"] = short
    check("N40-11 a sheet set missing one of the seven is refused",
          EX.EXPRESSION_SHEETS_INCOMPLETE in codes(RS.validate_reference_set(entry)))


def test_approval_once_and_stale_lock():
    entry = RS.build_reference_set("ava", views(), [wardrobe()], lock_version=2)
    check("N40-12 an unapproved set cannot be called approved",
          not RS.approve_reference_set(entry)["ok"]
          and RS.approve_reference_set(entry)["code"] == RS.APPROVAL_NOT_RECORDED)
    ok = RS.approve_reference_set(entry, approval={"by": "run-owner", "at": "t"})
    check("N40-13 the run owner's approval records once",
          ok["ok"] and ok["reference_set"]["approved"] is True)
    again = RS.approve_reference_set(ok["reference_set"],
                                     approval={"by": "run-owner", "at": "t"})
    check("N40-14 re-approving an unchanged set changes nothing",
          again["ok"] and again["reference_set"] == ok["reference_set"])
    stale = RS.approve_reference_set(entry, approval={"by": "run-owner"}, lock_version=1)
    check("N40-15 an approval from an older lock version is refused",
          not stale["ok"] and stale["code"] == RS.STALE_AFTER_LOCK_CHANGE)


def test_run():
    test_complete_set_passes()
    test_missing_view_and_unhashed_refused()
    test_wardrobe_accessories_lock()
    test_main_character_needs_expression_sheets()
    test_approval_once_and_stale_lock()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 15/15" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
