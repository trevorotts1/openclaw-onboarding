#!/usr/bin/env python3
"""test_approve_once_n17.py: the run owner approves the storyboard once (N-17).

Done when: swapping a picture, clip or prompt keeps the approval; changing a
lyric line, speaker, place, wardrobe, cast or event reopens it; a new shot
reopens it; a removed shot is named; and carry_approval leaves unchanged
shots approved and resets only the changed ones.

Run: python3 scripts/core/storyboard_director/test_approve_once_n17.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from storyboard_director import approve_once as AO      # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def shot(i, **over):
    row = {"shot_id": "s%d" % i, "lyric_line_ids": ["l%d" % i],
           "speaker": "ava", "location_id": "kitchen",
           "wardrobe_ids": ["w1"], "character_ids": ["ava"],
           "visible_action": "she reads the bill", "still_path": "/s%d.png" % i,
           "clip_path": "/s%d.mp4" % i, "prompt": "p%d" % i,
           "camera_direction": "close-up", "status": "storyboard_approved"}
    row.update(over)
    return row


def test_presentation_only_keeps_approval():
    before = [shot(1), shot(2)]
    after = [shot(1, still_path="/s1-v2.png", clip_path="/s1-v2.mp4",
                  prompt="better prompt", camera_direction="medium"),
             shot(2, clip_path="/s2-v2.mp4")]
    answer = AO.approval_required(before, after)
    check("N17-1 a new picture or clip does not reopen approval",
          answer["required"] is False
          and answer["reason_code"] == AO.APPROVAL_HELD, answer)
    carried = AO.carry_approval(before, after)
    check("N17-2 unchanged shots keep storyboard_approved",
          all(r["status"] == "storyboard_approved" for r in carried["shots"]))


def test_story_change_reopens():
    cases = {
        "lyric_line_ids": ["l9"],
        "speaker": "mother",
        "location_id": "church",
        "wardrobe_ids": ["w2"],
        "character_ids": ["ava", "mother"],
        "visible_action": "she hides the bill",
    }
    for field, value in cases.items():
        before = [shot(1)]
        after = [shot(1, **{field: value})]
        answer = AO.approval_required(before, after)
        check("N17-3 a changed %s reopens approval" % field,
              answer["required"] is True
              and answer["reason_code"] == AO.APPROVAL_REQUIRED
              and answer["changed_shots"] == ["s1"], answer)


def test_added_and_removed_shots():
    before = [shot(1), shot(2)]
    after = [shot(1), shot(3)]
    answer = AO.approval_required(before, after)
    check("N17-4 an added shot reopens approval", "s3" in answer["changed_shots"], answer)
    check("N17-5 a removed shot is named", "s2" in answer["changed_shots"], answer)


def test_carry_only_resets_changed_shots():
    before = [shot(1), shot(2)]
    after = [shot(1), shot(2, speaker="mother"), shot(3)]
    carried = AO.carry_approval(before, after)
    status = {r["shot_id"]: r["status"] for r in carried["shots"]}
    check("N17-6 only the changed and new shots drop back to planned",
          status == {"s1": "storyboard_approved", "s2": "planned", "s3": "planned"},
          status)
    check("N17-7 the input list is not mutated", before[1]["status"] == "storyboard_approved")


def test_run():
    test_presentation_only_keeps_approval()
    test_story_change_reopens()
    test_added_and_removed_shots()
    test_carry_only_resets_changed_shots()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 7/7" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
