#!/usr/bin/env python3
"""N-121: the place block carries the World Bible's own numbers. Stdlib only, $0.

Done when: a keyframe prompt states the room's size, its set pieces, the crowd
sentence for the shot's state and the story clock's light; a service scene with
no count is refused CROWD_SENTENCE_MISSING; a place with no bible entry is
refused PLACE_BLOCK_INCOMPLETE. No provider call, no spend.

Run: python3 scripts/core/keyframes/test_picture_prompt_n121.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from keyframes import picture_prompt as P                        # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

WORLD = {"locations": [{
    "location_id": "sanctuary",
    "size": {"pews_each_side": 12, "loft_tiers": 3},
    "set_pieces": ["the cross", "the choir loft"],
    "crowd_states": {"empty": {"count": 0},
                     "service": {"min": 110, "max": 130}},
    "background_life": {"who": "the congregation", "count": 120,
                        "doing": "standing and sitting with the service"},
    "clock": {"morning": "warm", "night": "cool"},
}]}

def test_place_block_numbers():
    place = P.place_for(WORLD, "sanctuary")
    block = P.place_block(place, "service", "morning")
    check("N121-1 size is in numbers", "12" in block and "3" in block, block)
    check("N121-2 set pieces are named",
          "the cross" in block and "the choir loft" in block, block)
    check("N121-3 crowd sentence carries the state's count range",
          "110 to 130" in block, block)
    check("N121-4 crowd sentence names who and what they do",
          "the congregation" in block and "standing and sitting" in block, block)
    check("N121-5 clock light is the beat's own",
          "warm light" in block, block)
    check("N121-6 the blanket no-people line is NOT sent for a full room",
          "empty of other people" not in block, block)

def test_empty_room_only_line():
    place = P.place_for(WORLD, "sanctuary")
    block = P.place_block(place, "empty", "morning")
    check("N121-7 an empty state sends the empty-room line",
          P.EMPTY_ROOM_LINE in block, block)
    check("N121-8 an empty state sends no crowd count", "about 1" not in block, block)

def test_full_state_without_count_is_refused():
    thin = {"location_id": "chapel", "crowd_states": {}, "set_pieces": []}
    try:
        P.place_block(thin, "service", "")
    except P.PromptError as e:
        check("N121-9 a service with no count is refused",
              e.code == "CROWD_SENTENCE_MISSING", e.code)
    else:
        check("N121-9 a service with no count is refused", False, "no refusal")

def test_unknown_place_is_refused():
    shot = {"shot_id": "S1", "location_id": "nowhere",
            "picture_part": "A room.", "crowd_state": "empty"}
    try:
        P.build_picture_prompt(shot, None, WORLD)
    except P.PromptError as e:
        check("N121-10 a place with no bible entry is refused",
              e.code == "PLACE_BLOCK_INCOMPLETE", e.code)
    else:
        check("N121-10 a place with no bible entry is refused", False,
              "no refusal")

def test_prompt_carries_place_and_words():
    entry = [{"object": "a framed diploma", "lines": ["Bachelor of Science"],
              "user": "", "faces": "camera", "viewer_must_read": True}]
    shot = {"shot_id": "S2", "location_id": "sanctuary", "town": "",
            "crowd_state": "service", "time_of_day": "morning",
            "picture_part": "She sings in the aisle."}
    prompt = P.build_picture_prompt(shot, entry, WORLD)
    check("N121-11 one prompt holds the place block and the words",
          "110 to 130" in prompt and '"Bachelor of Science"' in prompt, prompt)
    check("N121-12 the place block comes before the words",
          prompt.index("The place is sanctuary.") <
          prompt.index('"Bachelor of Science"'), prompt)

def test_run():
    test_place_block_numbers()
    test_empty_room_only_line()
    test_full_state_without_count_is_refused()
    test_unknown_place_is_refused()
    test_prompt_carries_place_and_words()

if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 12/12" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
