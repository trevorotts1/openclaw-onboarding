#!/usr/bin/env python3
"""test_review_all.py: the review entry point runs every row check.

Run: python3 scripts/core/storyboard_director/test_review_all.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from storyboard_director import review_all as R      # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        "" if cond else "  <- %r" % (detail,)))
    if not cond:
        FAILS.append(name)


def row(**kw):
    base = {"shot_id": "T1", "song_start": 0.0, "song_end": 6.0,
            "location_id": "sanctuary", "location_ids": ["sanctuary"],
            "camera_direction": "wide",
            "visual_objective": "she reads the letter at the table",
            "story_stage": "resolve", "character_ids": ["ava"],
            "wardrobe_ids": ["robe"], "lyric_line_ids": ["L1"],
            "qc_requirements": ["face"], "cost_estimate": 100,
            "product_visibility": "none", "continuity_constraints": [],
            "status": "storyboard_approved", "speaker": "ava",
            "route": "omnihuman_lipsync", "lip_sync": True, "label": "lead",
            "shot_size": "medium", "side_of_line": "left",
            "screen_sides": "ava left", "entry_state": "at the table",
            "exit_state": "at the table", "camera_move": "slow push",
            "camera_move_reason": "resolve holds still",
            "pace": "verse", "transition": "hard cut",
            "time_of_day": "morning", "crowd_state": "empty"}
    base.update(kw)
    return base


# 1. A plan with no lead lip-sync in the opening fails N-05 and says why.
out = R.review_storyboard([row(song_start=20.0, song_end=26.0)],
                          include_adversarial=False)


def test_run():
    global out
    check("1 opening passage is demanded", "OPENING_PASSAGE_MISSING" in out["codes"], out["codes"])

    # 2. A check that raises is REVIEW_INCOMPLETE, never a silent pass.
    out = R.review_storyboard([row(lyric_line_ids="not-a-list")],
                              include_adversarial=False)
    check("2 a broken row cannot pass silently",
          out["outcome"] == "fail" or "REVIEW_INCOMPLETE" in out["codes"], out)

    # 3. Only a MAJOR fails: the packet always carries the three counts.
    out = R.review_storyboard([row()], include_adversarial=False)
    check("3 severity counts are reported",
          set(out["severity_counts"]) == {"MINOR", "MEDIUM", "MAJOR"}, out["severity_counts"])

    # 4. The row checks actually ran: every story row check is in checks_run.
    out = R.review_storyboard([row()], include_adversarial=False)
    for name in ("check_speaker_cast", "check_speaker_labels", "check_opening",
                 "check_face_count", "check_lip_pieces_first",
                 "check_cinematic_flow", "check_choir_lead_in",
                 "review_beat_density"):
        check("4 ran %s" % name, name in out["checks_run"], out["checks_run"])

    # 5. A wardrobe id with no ledger entry fails when a ledger is supplied.
    out = R.review_storyboard([row()], wardrobe_ledger={"other": {}},
                              include_adversarial=False)
    check("5 unexplained wardrobe is refused",
          "unexplained_story_element" in out["codes"]
          or "WARDROBE_ACCESSORY_MISSING" in out["codes"], out["codes"])

    # 6. The legacy twelve-criteria review keeps its own verdict when asked.
    out = R.review_storyboard([row()], contracts={
        "T1": {"viewer_understanding": "she resolves", "visible_emotion": "resolve",
               "character_action": "reads", "necessity": "the line"}})
    check("6 adversarial review is included",
          "adversarial_review" in out["checks_run"], out["checks_run"])

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_run()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
