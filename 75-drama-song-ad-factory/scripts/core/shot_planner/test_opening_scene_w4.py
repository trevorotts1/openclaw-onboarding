#!/usr/bin/env python3
"""W4-U1 tests: the approved opening line and visible action reach the scene
plan and the shot sequence, and an ambiguous image cannot invert the emotion.

Run: python3 core/shot_planner/test_opening_scene_w4.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import shot_planner.shot_planner as SP          # noqa: E402
import shot_planner.opening_scene as OS         # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _shot(sid, start, end):
    return {"shot_id": sid, "song_start": start, "song_end": end,
            "lyric_line_ids": ["L1"], "story_stage": "opening",
            "visual_objective": "the fall", "character_ids": ["c1"],
            "wardrobe_ids": ["w1"], "location_id": "hotel-room",
            "product_visibility": "none", "camera_direction": "slow push",
            "reference_assets": [],
            "image_model_capability_request": {"capabilities": ["text-to-image"]},
            "video_model_capability_request": {"capabilities": ["text-to-video"]},
            "continuity_constraints": [], "negative_constraints": [],
            "cost_estimate": 0, "qc_requirements": ["emotion_read"], "status": "planned"}


def _contract():
    return {"lyric_text": "", "viewer_understanding": "",
            "character_action": "", "visible_emotion": "",
            "change_from_prior": "first shot", "treatment": "literal-repeat",
            "necessity": "opening"}


def _script(**extra):
    doc = {"title": "The Night It Broke",
           "story": [["opening", ["She is on the red carpet."]]],
           "sheet": [{"tag": "verse", "delivery": "spoken",
                      "lines": ["I won everything and felt nothing."]}]}
    doc.update(extra)
    return doc


def test_line_and_action_from_script():
    script = _script(elements={
        "opening_spoken_hook": "I won everything and felt nothing.",
        "opening_visible_action": "she sits alone backstage, trophy beside her",
        "opening_visible_emotion": "breakdown"})
    op = OS.opening_from_script(script)
    check("explicit opening line read from elements",
          op["line"] == "I won everything and felt nothing.", op["line"])
    check("explicit visible action read from elements",
          op["action"] == "she sits alone backstage, trophy beside her", op["action"])
    check("intended emotion read", op["intended_emotion"] == "breakdown")
    check("no ambiguity declared or detected", op["declared_ambiguity"] is None)


def test_fallback_line_is_approved_words_only():
    script = _script()
    script["sheet"] = [
        {"tag": "hook", "delivery": "sung", "lines": ["singing first, not spoken"]},
        {"tag": "verse", "delivery": "spoken", "lines": ["the spoken opening"]}]
    op = OS.opening_from_script(script)
    check("fallback takes the first SPOKEN approved line",
          op["line"] == "the spoken opening", op["line"])
    check("fallback never invents an action", op["action"] == "", repr(op["action"]))


def test_plan_writes_scene_and_shot_sequence():
    script = _script(elements={
        "opening_spoken_hook": "I won everything and felt nothing.",
        "opening_visible_action": "she sits alone backstage, trophy beside her",
        "opening_visible_emotion": "breakdown"})
    shots = [_shot("s2", 6.0, 12.0), _shot("s1", 0.0, 6.0), _shot("s3", 12.0, 18.0)]
    contracts = {"s1": _contract(), "s2": _contract(), "s3": _contract()}
    out = OS.plan_opening(script, shots, contracts)
    head = shots[1]                                  # s1 is first in song order
    check("opening scene names the approved line",
          out["scene"]["line"] == "I won everything and felt nothing.")
    check("opening scene names the approved action",
          out["scene"]["action"] == "she sits alone backstage, trophy beside her")
    check("first shot in song order carries the opening record",
          head["opening"]["line"] == out["scene"]["line"]
          and head["opening"]["action"] == out["scene"]["action"])
    check("shot order is generated, not invented",
          out["receipt"]["shot_order"] == ["s1", "s2", "s3"],
          repr(out["receipt"]["shot_order"]))
    check("shot list order itself is preserved",
          [s["shot_id"] for s in shots] == ["s2", "s1", "s3"])
    check("contract carries the opening line",
          contracts["s1"]["lyric_text"] == out["scene"]["line"])
    check("contract carries the visible action",
          contracts["s1"]["character_action"] == out["scene"]["action"])
    check("contract carries the intended emotion",
          contracts["s1"]["visible_emotion"] == "breakdown")
    check("other shots are untouched",
          "opening" not in shots[0] and "opening" not in shots[2])
    check("opening shot still passes the existing shot validator",
          SP.validate_shot(head) == [], repr(SP.validate_shot(head)))


def test_ambiguous_opening_refused_without_context():
    script = _script(elements={
        "opening_spoken_hook": "I won everything and felt nothing.",
        "opening_visible_action": "tears on her face at the award ceremony",
        "opening_visible_emotion": "breakdown"})
    try:
        OS.plan_opening(script, [_shot("s1", 0.0, 6.0)], None)
    except SP.PlanError as e:
        check("award-night tears with no context refuse OPENING_AMBIGUOUS",
              e.code == "OPENING_AMBIGUOUS", e.code)
        check("the refusal names the opposite reading", "joy" in str(e), str(e))
        return
    check("award-night tears with no context refuse OPENING_AMBIGUOUS", False)


def test_ambiguous_opening_carries_context_and_negative():
    script = _script(elements={
        "opening_spoken_hook": "I won everything and felt nothing.",
        "opening_visible_action": "tears on her face at the award ceremony",
        "opening_visible_emotion": "breakdown",
        "opening_reading_context": "she is crying alone after the applause stops"})
    shots = [_shot("s1", 0.0, 6.0), _shot("s2", 6.0, 12.0)]
    out = OS.plan_opening(script, shots, {"s1": _contract()})
    amb = out["scene"]["ambiguity"]
    check("ambiguity is explicit on the scene plan",
          amb and amb["source"] == "detected" and amb["opposite_emotion"] == "joy",
          repr(amb))
    check("reading context rides into shot continuity_constraints",
          "she is crying alone after the applause stops"
          in shots[0]["continuity_constraints"],
          repr(shots[0]["continuity_constraints"]))
    check("opposite-reading negative constraint rides into the shot",
          any("no joy" in x for x in shots[0]["negative_constraints"]),
          repr(shots[0]["negative_constraints"]))
    check("validation passes for the intact plan",
          OS.validate_opening(out["scene"], shots) == [])


def test_declared_ambiguity_requires_context():
    script = _script(elements={
        "opening_spoken_hook": "I won everything and felt nothing.",
        "opening_visible_action": "she is still in the empty ballroom",
        "opening_visible_emotion": "breakdown",
        "opening_ambiguity": {"opposite_emotion": "triumph",
                              "risk": "an empty ballroom can read as a win"}})
    try:
        OS.build_opening_scene(OS.opening_from_script(script))
    except SP.PlanError as e:
        check("declared ambiguity without context refuses OPENING_AMBIGUOUS",
              e.code == "OPENING_AMBIGUOUS", e.code)
    else:
        check("declared ambiguity without context refuses OPENING_AMBIGUOUS", False)
    script["elements"]["opening_reading_context"] = "she has already lost the deal"
    scene = OS.build_opening_scene(OS.opening_from_script(script))
    check("declared ambiguity records the declared opposite",
          scene["ambiguity"]["opposite_emotion"] == "triumph")


def test_validation_catches_a_lost_opening():
    script = _script(elements={
        "opening_spoken_hook": "I won everything and felt nothing.",
        "opening_visible_action": "she sits alone backstage"})
    shots = [_shot("s1", 0.0, 6.0)]
    contracts = {"s1": _contract()}
    out = OS.plan_opening(script, shots, contracts)
    shots[0]["opening"]["line"] = "something the client never approved"
    errs = OS.validate_opening(out["scene"], shots, contracts)
    check("a changed opening line is caught as OPENING_LOST",
          any("OPENING_LOST" in e for e in errs), repr(errs))


def main():
    test_line_and_action_from_script()
    test_fallback_line_is_approved_words_only()
    test_plan_writes_scene_and_shot_sequence()
    test_ambiguous_opening_refused_without_context()
    test_ambiguous_opening_carries_context_and_negative()
    test_declared_ambiguity_requires_context()
    test_validation_catches_a_lost_opening()
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        print("FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all W4-U1 opening-scene checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
