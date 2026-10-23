#!/usr/bin/env python3
"""S75X-W4-U2: music-request inputs populated from the Story Beat Blueprint.

Proves the director turns ``creative/blueprint.json``'s own ``music_cues[]``
into the ACTUAL request inputs, and that the four turns stay distinguishable:
  1. the inputs are the blueprint's (instrumental flag, delivered length, the
     two seams at the ERM apex / Hero Shift, ``true_at_beat``);
  2. the four turns are receipted distinctly -- immediate spoken attention
     hook, first singing at the ERM Drop, a distinct Hero Shift, and the
     earned Solution Signature Hook;
  3. instrumental support before the first singing is ALLOWED and reported;
  4. no chorus/hook cue precedes the earned point, a hook before the
     breakthrough is refused, and no sung word precedes the ERM;
  5. the Hero Shift must change pace, rhythm AND emotional direction;
  6. the opening stays the attention hook (spoken, under the recipe's own
     opener cap, never carrying the earned hook) -- never dead exposition;
  7. a built request carries BOTH blueprint directions in its final style and
     the hook plan measured at the blueprint's ``true_at_beat``;
  8. the control: the untouched fixture builds.

Zero network, zero spend, fixtures only.

Run: python3 core/music_director/test_blueprint_inputs_s75xw4u2.py
     (from scripts/core; exit 0 = all pass, 1 = failures)
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(CORE, "__pycache__")
if os.path.isdir(_CACHE):
    for _n in os.listdir(_CACHE):
        if _n.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _n))
            except OSError:
                pass

import music_director as MD         # noqa: E402
import suno_recipe as R             # noqa: E402
from sung_hook import hook_placement as HP   # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def fixture():
    path = os.path.join(CORE, "method_plan", "fixtures", "blueprint-90s.json")
    return json.loads(open(path, encoding="utf-8").read())


def mutated(**cues):
    """A fixture copy with per-cue overrides: mutated(ERM_DROP={"start_s": 5})."""
    bp = copy.deepcopy(fixture())
    for cue in bp["music_cues"]:
        cue.update(cues.get(cue["music_cue_id"], {}))
    return bp


def refused(fn, *a, **kw):
    try:
        return False, fn(*a, **kw)
    except ValueError as e:
        return True, str(e)


#: A sheet that follows the fixture's cue order: spoken attention hook, an
#: instrumental bed, the ERM verse, the Hero Shift, the breakthrough, the
#: repeated earned hook, the spoken outro. Its hook repeats the client's words.
CLIENT = ("Who is holding me? You do not have to carry it alone. Asked, and "
          "someone answered me. Wake Up Happy, Sis. The morning finds me "
          "standing. Come and ask for what you need.")
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["She keeps giving."]},
         {"tag": "Instrumental", "delivery": None, "lines": []},
         {"tag": "Verse", "delivery": "sung", "lines": ["Who is holding me?"]},
         {"tag": "Verse", "delivery": "sung",
          "lines": ["Who is holding me when the room goes quiet"]},
         {"tag": "Pre-Chorus", "delivery": "sung",
          "lines": ["You do not have to carry it alone"]},
         {"tag": "Verse", "delivery": "sung",
          "lines": ["Asked, and someone answered me"]},
         {"tag": "Verse", "delivery": "sung",
          "lines": ["Asked, and someone answered me again"]},
         {"tag": "Hook 1", "delivery": "sung",
          "lines": ["Wake Up Happy, Sis", "The morning finds me standing"]},
         {"tag": "Hook 2", "delivery": "sung",
          "lines": ["Wake Up Happy, Sis", "The morning finds me standing"]},
         {"tag": "Outro", "delivery": "spoken",
          "lines": ["Come and ask for what you need."]}]
STYLE = R.style_text("soul-ballad")


def build(blueprint=None, sheet=None):
    return MD.build_blueprint_request(
        blueprint or fixture(), R.render_lyrics(sheet or SHEET), STYLE,
        "Wake Up Happy, Sis", style_id="soul-ballad", client_text=CLIENT)


# ---- 1. the inputs ARE the blueprint's ------------------------------------
def test_inputs_are_populated_from_the_blueprint():
    got = MD.blueprint_request_inputs(fixture(), style_id="soul-ballad")
    check("the input set is the request's own",
          set(got) == {"instrumental", "length_s", "pace_plan", "true_at_beat",
                       "turns", "instrumental_support_s"}, sorted(got))
    check("a blueprint that sings is not instrumental", got["instrumental"] is False)
    check("the delivered length comes from the blueprint runtime target (90 -> 88)",
          got["length_s"] == 88.0, got["length_s"])
    check("the true_at_beat is the stage where the solution is introduced",
          got["true_at_beat"] == "the_turn", got["true_at_beat"])
    order = got["pace_plan"]
    check("the pace order is a METHOD order", order.get("method") is True, order)
    check("boundary_s is the blueprint ERM apex (22 s)", order["boundary_s"] == 22.0, order)
    check("return_boundary_s is the blueprint Hero Shift (38 s)",
          order["return_boundary_s"] == 38.0, order)
    check("both seams sit on the blueprint anchors",
          (order["erm_apex_s"], order["hero_shift_s"]) == (22.0, 38.0), order)
    check("the ERM clause is the cue's pace + rhythmic change",
          "heavier, sparser half-time" in order["drop"]
          and "first sung line enters" in order["drop"], order["drop"])
    check("the Hero clause is the cue's pace + rhythm + emotional direction",
          all(x in order["return"] for x in
              ("steadier, more open pace", "second, clear and dramatic pace change",
               "cautious hope opens up")), order["return"])


# ---- 2. the four turns stay distinguishable --------------------------------
def test_four_turns_are_distinct():
    turns = MD.blueprint_request_inputs(fixture())["turns"]
    check("all four turns are receipted", tuple(turns) == MD.BLUEPRINT_TURNS,
          tuple(turns))
    check("the spoken attention hook is the script's, at zero",
          turns["spoken_attention_hook"]["source"] == "script"
          and turns["spoken_attention_hook"]["at_s"] == 0.0,
          turns["spoken_attention_hook"])
    check("the first sung word enters at the ERM Drop (22 s)",
          turns["erm_first_singing"]["cue_id"] == "ERM_DROP"
          and turns["erm_first_singing"]["at_s"] == 22.0
          and turns["erm_first_singing"]["vocal_status"] == "first_sung",
          turns["erm_first_singing"])
    check("the Hero Shift is another moment with its own three directions",
          turns["hero_shift"]["at_s"] == 38.0
          and turns["hero_shift"]["at_s"] != turns["erm_first_singing"]["at_s"]
          and all(turns["hero_shift"][k] for k in MD.HERO_SHIFT_AXES),
          turns["hero_shift"])
    check("the Solution Signature Hook is the LATER earned hook",
          turns["solution_signature_hook"]["at_s"] == 60.0
          and turns["solution_signature_hook"]["earned_from_s"] == 58.0
          and turns["solution_signature_hook"]["at_s"]
          > turns["hero_shift"]["at_s"], turns["solution_signature_hook"])


# ---- 3. instrumental support before the first singing is allowed ----------
def test_instrumental_support_before_first_singing():
    got = MD.blueprint_request_inputs(fixture())
    check("support before the ERM is reported (0 -> 22 s)",
          got["instrumental_support_s"] == 22.0, got["instrumental_support_s"])
    check("support is allowed, never refused: the request still sings",
          got["instrumental"] is False
          and got["turns"]["erm_first_singing"]["vocal_status"] == "first_sung")


# ---- 4. no chorus precedes the earned point -------------------------------
def test_chorus_before_the_earned_point_is_refused():
    bp = fixture()
    bp["music_cues"].append({"music_cue_id": "CHORUS_1", "story_beat_id": "SB-01",
                             "trigger": "early triumph", "start_s": 30.0,
                             "pace_before": "x", "pace_after": "x",
                             "rhythmic_change": "x", "emotional_direction": "x",
                             "vocal_status": "sung", "lyric_or_dialogue": "x",
                             "transition_method": "x", "verification_evidence": "x"})
    ok, err = refused(MD.blueprint_request_inputs, bp)
    check("a chorus cue before the breakthrough is refused",
          ok and "CHORUS_BEFORE_EARNED" in err, err)
    ok2, err2 = refused(MD.blueprint_request_inputs,
                        mutated(SOLUTION_HOOK={"start_s": 50.0}))
    check("a hook before the breakthrough is refused as unearned",
          ok2 and "HOOK_UNEARNED" in err2, err2)


# ---- 5. the turns cannot collapse ----------------------------------------
def test_collapsed_turns_are_refused():
    ok, err = refused(MD.blueprint_request_inputs,
                      mutated(HERO_SHIFT={"start_s": 22.0}))
    check("a Hero Shift on the ERM apex's own moment is refused",
          ok and "HERO_SHIFT_NOT_DISTINCT" in err, err)
    ok2, err2 = refused(MD.blueprint_request_inputs,
                        mutated(HERO_SHIFT={"emotional_direction": "the pain becomes personal"}))
    check("a Hero Shift that repeats the ERM's emotional direction is refused",
          ok2 and "HERO_SHIFT_NOT_DISTINCT" in err2, err2)
    ok3, err3 = refused(MD.blueprint_request_inputs,
                        mutated(ERM_DROP={"vocal_status": "instrumental"}))
    check("an ERM that is not the first sung cue is refused",
          ok3 and "ERM_NOT_FIRST_SUNG" in err3, err3)
    ok4, err4 = refused(MD.blueprint_request_inputs,
                        mutated(PAIN_BUILD={"vocal_status": "sung"}))
    check("a sung word before the ERM is refused",
          ok4 and "SINGING_BEFORE_ERM" in err4, err4)
    bp = fixture()
    del bp["music_cues"][2]
    ok5, err5 = refused(MD.blueprint_request_inputs, bp)
    check("a blueprint missing a required cue is refused",
          ok5 and "BLUEPRINT_CUES_MISSING" in err5, err5)


# ---- 6. the opening is the attention hook, never dead exposition ----------
def test_opening_rules():
    sung_open = [dict(s) for s in SHEET]
    sung_open[0] = {"tag": "Verse", "delivery": "sung",
                    "lines": ["Who is holding me?"]}
    ok, err = refused(build, sheet=sung_open)
    check("a sung opening is refused (no immediate spoken attention hook)",
          ok and "OPENING_NOT_ATTENTION_HOOK" in err, err)
    long_open = [dict(s) for s in SHEET]
    long_open[0] = {"tag": "Intro", "delivery": "spoken",
                    "lines": ["Late at night she is still answering every request "
                              "on the couch while her own message waits"]}
    ok2, err2 = refused(build, sheet=long_open)
    check("a long spoken opener is refused as dead exposition",
          ok2 and "OPENING_DEAD_EXPOSITION" in err2, err2)
    forced = [dict(s) for s in SHEET]
    forced[0] = {"tag": "Intro", "delivery": "spoken",
                 "lines": ["Wake Up Happy, Sis"]}
    ok3, err3 = refused(build, sheet=forced)
    check("the earned hook forced into the opening is refused",
          ok3 and "HOOK_FORCED_INTO_OPENING" in err3, err3)


# ---- 7. the built request follows the beats -------------------------------
def test_built_request_carries_the_blueprint():
    req = build()
    inp = req["input"]
    check("the request is the current createTask envelope",
          req["endpoint"] == MD.CREATE_TASK_ENDPOINT
          and req["model"] == MD.MUSIC_TASK_MODEL and "callBackUrl" in req)
    check("the duration is the blueprint-delivered length (88 s)",
          inp["duration"] == 88.0, inp["duration"])
    check("the final style carries BOTH blueprint directions in order",
          "heavier, sparser half-time" in inp["style"]
          and "cautious hope opens up" in inp["style"], inp["style"][-300:])
    check("the hook plan is measured at the blueprint's true_at_beat",
          req.get("_hook_plan", {}).get("true_at_beat") == "the_turn",
          req.get("_hook_plan"))
    check("the pace plan rides the request as internal metadata only",
          req.get("_pace_plan", {}).get("method") is True
          and "_pace_plan" not in json.dumps(inp), req.get("_pace_plan"))
    check("the first hook is measured at or after true_at_beat",
          all(HP.beat_start_s(req["_hook_plan"]["true_at_beat"], 88.0) <=
              p * 88.0 for p in HP.hook_positions(inp["lyrics"], "soul-ballad")[:1]),
          HP.hook_positions(inp["lyrics"], "soul-ballad"))


# ---- 8. the untouched fixture is the control ------------------------------
def test_control_fixture_builds():
    req = build()
    check("the untouched fixture builds a request (control)", bool(req["input"]["lyrics"]))


def main():
    test_inputs_are_populated_from_the_blueprint()
    test_four_turns_are_distinct()
    test_instrumental_support_before_first_singing()
    test_chorus_before_the_earned_point_is_refused()
    test_collapsed_turns_are_refused()
    test_opening_rules()
    test_built_request_carries_the_blueprint()
    test_control_fixture_builds()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
