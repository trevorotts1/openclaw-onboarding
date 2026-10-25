#!/usr/bin/env python3
"""Focused tests for script_validation (S75-T11 / S75-A11).

Run: python3 -m pytest -q scripts/core/test_script_validation.py
 or: python3 scripts/core/test_script_validation.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import script_validation as V  # noqa: E402
import story_first_contracts as C  # noqa: E402

FIXTURES = os.path.join(HERE, "tests", "fixtures")

CAST = {
    "cast": [
        {"character_id": "char_mara_001", "identity_revision": 1,
         "identity_digest": "identity-digest-1", "episode_role": "lead",
         "scene_ids": ["scene_workshop_001"],
         "immediate_story_function": "Must choose to expose the hidden warning.",
         "choice_or_consequence": "Disclosure shifts her from isolation to shared responsibility."},
        {"character_id": "char_levi_002", "identity_revision": 1,
         "identity_digest": "identity-digest-2", "episode_role": "supporting partner",
         "scene_ids": ["scene_workshop_001"],
         "immediate_story_function": "Refuses vague reassurance and shows the empty ledger.",
         "choice_or_consequence": "His restrained offer makes Mara's turn possible."},
    ]
}

WORLD = {
    "revision": 1,
    "locations": [
        {"location_id": "loc_workshop_front_001", "name": "Workshop front room"},
        {"location_id": "loc_shop_floor_002", "name": "Shop floor"},
    ],
}


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


def _codes(verdict):
    return {d["code"] for d in verdict["defects"]}


def _fields(verdict):
    return {d["field"] for d in verdict["defects"]}


def _single_scene_script(scene):
    return {"schema_version": "s75.script.v1", "artifact_id": "s_test", "scenes": [scene]}


# --- acceptance -----------------------------------------------------------

def test_rich_causal_script_accepted():
    verdict = V.validate_script(_load("rich_causal_script.json"), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is True, verdict["defects"]
    assert verdict["scene_count"] == 1
    assert verdict["compatibility_limited"] is False
    assert verdict["regenerate"] is False


# --- refusals for new authoring ------------------------------------------

def test_one_line_placeholder_scene_refused():
    scene = copy.deepcopy(_load("rich_causal_script.json")["scenes"][0])
    scene["spoken_dialogue"] = [{"line_id": "l1", "character_id": "char_mara_001",
                                 "text": "..."}]
    scene["sung_lyrics"] = []
    verdict = V.validate_script(_single_scene_script(scene))
    assert verdict["ok"] is False
    assert "PLACEHOLDER_SCENE" in _codes(verdict)


def test_single_short_line_scene_refused_as_placeholder():
    scene = copy.deepcopy(_load("rich_causal_script.json")["scenes"][0])
    scene["spoken_dialogue"] = [{"line_id": "l1", "character_id": "char_mara_001",
                                 "text": "She sings."}]
    scene["sung_lyrics"] = []
    verdict = V.validate_script(_single_scene_script(scene))
    assert "PLACEHOLDER_SCENE" in _codes(verdict)


def test_unstructured_scene_refused():
    verdict = V.validate_script(_single_scene_script("A sad owner sings about her business."))
    assert verdict["ok"] is False
    assert "PLACEHOLDER_SCENE" in _codes(verdict)


def test_beat_only_bypass_refused():
    script = {"schema_version": "s75.script.v1", "artifact_id": "s_beats",
              "beats": [{"beat_id": "b1", "because": "x", "therefore": "y"}]}
    verdict = V.validate_script(script)
    assert verdict["ok"] is False
    assert "BEAT_ONLY_BYPASS" in _codes(verdict)


def test_undefined_performer_refused():
    script = _load("rich_causal_script.json")
    script["scenes"][0]["cast_ids"] = ["char_mara_001"]
    verdict = V.validate_script(script, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "CAST" in _codes(verdict) or "SCENE_SCHEMA" in _codes(verdict)


def test_missing_rich_field_refused():
    script = _load("rich_causal_script.json")
    del script["scenes"][0]["visible_lip_sync"]
    verdict = V.validate_script(script)
    assert verdict["ok"] is False
    assert "visible_lip_sync" in _fields(verdict)


def test_lip_sync_interval_beyond_duration_refused():
    script = _load("rich_causal_script.json")
    script["scenes"][0]["visible_lip_sync"] = {"intervals": [[0, 40]], "performer": "char_mara_001"}
    verdict = V.validate_script(script)
    assert verdict["ok"] is False
    assert "LIP_SYNC_INTERVAL" in _codes(verdict)


def test_undefined_location_refused():
    script = _load("rich_causal_script.json")
    script["scenes"][0]["location_id"] = "loc_missing_999"
    verdict = V.validate_script(script, world=WORLD)
    assert verdict["ok"] is False
    assert "location_id" in _fields(verdict)


# --- legacy compatibility -------------------------------------------------

def test_legacy_record_readable_and_compatibility_limited():
    legacy = _load("legacy_scene_migration.json")
    before = copy.deepcopy(legacy)
    verdict = V.validate_script(legacy, origin=V.ORIGIN_LEGACY)
    assert verdict["ok"] is True, verdict["defects"]
    assert verdict["legacy"] is True
    assert verdict["compatibility_limited"] is True
    assert verdict["regenerate"] is False
    assert "spoken_dialogue" in verdict["unresolved"]
    assert "visible_lip_sync" in verdict["unresolved"]
    assert legacy == before


def test_legacy_record_cannot_satisfy_new_generation():
    legacy = _load("legacy_scene_migration.json")
    verdict = V.validate_script(legacy, origin=V.ORIGIN_NEW)
    assert verdict["ok"] is False
    assert "LEGACY_NOT_NEW_AUTHORING" in _codes(verdict)


def test_legacy_label_without_identity_is_not_legacy():
    legacy = _load("legacy_scene_migration.json")
    for key in ("artifact_id", "run_id"):
        legacy.pop(key, None)
    assert V.is_legacy(legacy) is False or V.validate_script(
        legacy, origin=V.ORIGIN_LEGACY)["ok"] is False


def test_old_shape_without_marker_is_validated_as_new():
    legacy = _load("legacy_scene_migration.json")
    legacy.pop("schema_version")
    legacy["legacy"] = False
    verdict = V.validate_script(legacy)
    assert verdict["ok"] is False
    assert "PLACEHOLDER_SCENE" in _codes(verdict) or "SCENE_SCHEMA" in _codes(verdict)


def test_rich_script_is_not_mutated():
    script = _load("rich_causal_script.json")
    before = json.dumps(script, sort_keys=True)
    V.validate_script(script, world=WORLD, cast_manifest=CAST)
    assert json.dumps(script, sort_keys=True) == before


def test_assert_new_generation_raises_contract_error():
    legacy = _load("legacy_scene_migration.json")
    try:
        V.assert_new_generation(legacy)
    except C.ContractError as exc:
        assert exc.code == "SCRIPT_INVALID"
    else:
        raise AssertionError("legacy record admitted as new generation")


# --- real aspect coverage, not presence -----------------------------------

def _good_scene():
    return copy.deepcopy(_load("rich_causal_script.json")["scenes"][0])


def test_probe_scene_with_weak_aspects_refused():
    """The independent-verdict probe: every weak aspect present, nothing valid."""
    scene = _good_scene()
    scene["location_id"] = "loc_unknown_777"
    scene["world_revision"] = 99
    scene["cast_ids"] = ["char_ghost_999"]
    scene["identity_revisions"] = {"char_ghost_999": 1}
    scene["spoken_dialogue"] = [
        {"line_id": "lp1", "character_id": "char_ghost_999", "text": "We should read the notice tonight."},
        {"line_id": "lp2", "character_id": "char_ghost_999", "text": "Then let us open the ledger now."},
    ]
    scene["sung_lyrics"] = []
    scene["performance_order"] = [{"character_id": "char_ghost_999", "line_id": "lp1"}]
    scene["dramatic_purpose"] = "reveal tension stakes catharsis resolution"
    scene["emotion_before"] = "afraid"
    scene["emotion_after"] = "afraid"
    scene["sound_music_cues"] = ["music"]
    scene["framing_movement_intent"] = "close"
    scene["transition"] = "cut"
    scene["visible_lip_sync"] = {"intervals": []}
    for kwargs in ({}, {"world": WORLD, "cast_manifest": CAST}):
        verdict = V.validate_script(_single_scene_script(scene), **kwargs)
        assert verdict["ok"] is False, verdict["defects"]
        codes = _codes(verdict)
        assert "KEYWORD_ONLY_CLAIM" in codes
        assert "EMOTION_STAGNANT" in codes
        assert "LIP_SYNC_EMPTY_CLAIM" in codes
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    codes = _codes(verdict)
    assert "PERFORMER_UNDECLARED" in codes
    assert "LOCATION_UNKNOWN" in codes
    assert "WORLD_REVISION_STALE" in codes


def test_single_long_line_scene_refused():
    scene = _good_scene()
    scene["spoken_dialogue"] = [
        {"line_id": "l1", "character_id": "char_mara_001",
         "text": "She tells him everything about the warning tonight."},
    ]
    scene["sung_lyrics"] = []
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "PLACEHOLDER_SCENE" in _codes(verdict)


def test_world_and_cast_required_for_new_authoring():
    verdict = V.validate_script(_load("rich_causal_script.json"))
    assert verdict["ok"] is False
    assert {"WORLD_REQUIRED", "CAST_REQUIRED"} <= _codes(verdict)


def test_keyword_only_purpose_refused():
    scene = _good_scene()
    scene["dramatic_purpose"] = "grief longing stakes release closure"
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "KEYWORD_ONLY_CLAIM" in _codes(verdict)
    assert "dramatic_purpose" in _fields(verdict)


def test_keyword_only_sound_framing_transition_refused():
    scene = _good_scene()
    scene["sound_music_cues"] = ["tension drone pulse riser silence"]
    scene["framing_movement_intent"] = "close push drift"
    scene["transition"] = "hard cut whip fade"
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    fields = _fields(verdict)
    assert {"sound_music_cues", "framing_movement_intent", "transition"} <= fields


def test_stale_or_missing_world_revision_refused():
    scene = _good_scene()
    scene["world_revision"] = 7
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert "WORLD_REVISION_STALE" in _codes(verdict)
    scene["world_revision"] = None
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "WORLD_REVISION_MISSING" in _codes(verdict)


def test_undeclared_line_performer_refused():
    scene = _good_scene()
    scene["spoken_dialogue"][0]["character_id"] = "char_stranger_007"
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "PERFORMER_UNDECLARED" in _codes(verdict)


def test_stagnant_emotion_refused_even_with_surface_variation():
    scene = _good_scene()
    scene["emotion_before"] = "Afraid"
    scene["emotion_after"] = "  afraid "
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "EMOTION_STAGNANT" in _codes(verdict)


def test_lip_sync_claim_without_intervals_refused():
    scene = _good_scene()
    scene["visible_lip_sync"] = {"intervals": [], "performer": "char_mara_001"}
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "LIP_SYNC_EMPTY_CLAIM" in _codes(verdict)


def test_specific_coherent_neighbouring_scene_accepted():
    """A specific, coherent neighbour is accepted.

    SPECIFIC is the load-bearing word: the neighbour states its own want, its own
    obstacle, its own action, its own choice, its own turn and its own subtext.
    A neighbour that re-uses the first scene's claims verbatim is not a second
    scene, it is the first scene wearing a second id, and
    _cross_scene_repetition_defects refuses it.
    """
    script = _load("rich_causal_script.json")
    scene = _good_scene()
    scene["scene_id"] = "scene_shop_floor_002"
    scene["sequence"] = 2
    scene["causal_predecessor"] = "scene_workshop_001"
    scene["location_id"] = "loc_shop_floor_002"
    scene["dramatic_purpose"] = "Force Levi to trade reassurance for a shared repair schedule."
    scene["immediate_want"] = "Levi wants the repair schedule written down before the doors open."
    scene["obstacle"] = "The unread warning notice blocks that writing at the bench."
    scene["visible_action"] = "Levi sets the schedule on the bench and waits for Mara to sign it."
    scene["consequential_choice"] = "Levi writes the schedule down and loses his last excuse."
    scene["turn_trigger"] = "Mara slides the pen across the bench."
    scene["subtext_and_behavior"] = "Levi hides the relief behind a flat voice at the bench."
    scene["emotion_before"] = "guarded"
    scene["emotion_after"] = "committed"
    scene["spoken_dialogue"] = [
        {"line_id": "line_levi_010", "character_id": "char_levi_002",
         "text": "We write the schedule together before the doors open."},
        {"line_id": "line_mara_010", "character_id": "char_mara_001",
         "text": "Then I sign it and we post it where everyone can see."},
    ]
    scene["sung_lyrics"] = []
    scene["performance_order"] = [
        {"character_id": "char_levi_002", "line_id": "line_levi_010"},
        {"character_id": "char_mara_001", "line_id": "line_mara_010"},
    ]
    scene["visible_lip_sync"] = {"intervals": [[1, 6]], "performer": "char_levi_002"}
    script["scenes"].append(scene)
    verdict = V.validate_script(script, world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is True, verdict["defects"]
    assert verdict["scene_count"] == 2


# --- A: a declaration never launders content ------------------------------

def _with(**over):
    scene = _good_scene()
    for key, value in over.items():
        scene[key] = value
    return scene


def test_silent_scene_flag_with_performed_lines_is_a_contradiction():
    scene = _with(silent_scene=True)
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "SILENT_SCENE_CONTRADICTION" in _codes(verdict)


def test_silent_scene_flag_with_sung_lines_is_a_contradiction():
    scene = _with(silent_scene=True, spoken_dialogue=[])
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "SILENT_SCENE_CONTRADICTION" in _codes(verdict)


def test_silent_scene_flag_with_one_line_is_still_a_contradiction():
    scene = _with(silent_scene=True, sung_lyrics=[],
                  spoken_dialogue=[{"line_id": "l1", "character_id": "char_mara_001",
                                    "text": "If I lock that door, their checks bounce tomorrow."}])
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "SILENT_SCENE_CONTRADICTION" in _codes(verdict)


def test_silent_scene_flag_must_be_a_typed_declaration():
    for value in ("true", "True", 1, 0, [], {}, ["true"], 0.0):
        scene = _with(silent_scene=value)
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is False, value
        assert "SILENT_SCENE_FLAG" in _codes(verdict), value


def test_silent_false_with_real_lines_accepted():
    scene = _with(silent_scene=False)
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is True, verdict["defects"]


# --- B: statement fields typed strict and content-validated ---------------

_STATEMENT_SAMPLES = ("causal_outcome", "timing_basis", "dramatic_purpose",
                      "time", "obstacle", "immediate_want", "subtext_and_behavior",
                      "consequential_choice", "turn_trigger", "visible_action",
                      "framing_movement_intent", "transition")

_KEYWORD_RUNS = (
    "buy backlinks cheap seo signals crypto pump diet tea mattress",
    "cheap seo backlinks high da pa guest post links",
    "crypto pump dump moon gem signals buy sell hold",
    "weight loss detox tea diet pills fast burn",
    "seo sem ppc backlinks anchor text ranking traffic funnel",
    "the buy backlinks cheap seo signals crypto pump diet tea",
    "the buy backlinks and cheap seo signals for the crypto pump",
    "we buy the backlinks and cheap seo signals for the crypto pump",
    "sell backlinks cheap seo signals crypto pump diet tea mattress now",
)


def test_statement_fields_refuse_non_text_values():
    for field in _STATEMENT_SAMPLES:
        for value in (0, 0.0, True, False, [], {}, None, ["a statement"], {"a": 1}):
            scene = _with(**{field: value})
            verdict = V.validate_script(_single_scene_script(scene), world=WORLD,
                                        cast_manifest=CAST)
            assert verdict["ok"] is False, (field, value)
            assert "CLAIM_NOT_WRITTEN" in _codes(verdict), (field, value, verdict["defects"])


def test_statement_fields_refuse_keyword_runs():
    for field in _STATEMENT_SAMPLES:
        for run in _KEYWORD_RUNS:
            scene = _with(**{field: run})
            verdict = V.validate_script(_single_scene_script(scene), world=WORLD,
                                        cast_manifest=CAST)
            assert verdict["ok"] is False, (field, run)
            assert "KEYWORD_ONLY_CLAIM" in _codes(verdict), (field, run, verdict["defects"])


def test_real_written_statements_accepted():
    """Positive controls: the rule must refuse keyword runs and accept writing."""
    cases = (
        {"causal_outcome": "Because Levi hands over the ledger, the next scene must open on "
                           "the repair schedule."},
        {"causal_outcome": "She admits the debt, so the next scene has to end the silence."},
        {"timing_basis": "authoring estimate before music"},
        {"timing_basis": "measured against the master track"},
        {"time": "evening, closing time"},
        {"time": "dawn, first light"},
        {"obstacle": "The empty ledger and his direct question block that escape."},
        {"immediate_want": "Mara wants Levi to accept one more vague promise without "
                           "reading the warning."},
        {"subtext_and_behavior": "She admits the fact before naming the feeling, and stills "
                                 "her hands on the open page."},
        {"consequential_choice": "She gives up control of the information."},
        {"turn_trigger": "Putting the notice where Levi can read it."},
        {"transition": "Cut to black, then the shop at dawn."},
        {"framing_movement_intent": "Medium shot of the empty room, then a slow push toward "
                                    "the door."},
    )
    for over in cases:
        scene = _with(**over)
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is True, (over, verdict["defects"])


# --- C: placeholder detection by meaning, not by punctuation --------------

_LINE_STUBS = (
    "The words for this part are still to be written.",
    "Insert the spoken line here after the editing.",
    "To be filled in later.",
    "Placeholder",
    "TBD",
    "TK",
    "Lorem ipsum dolor sit amet.",
    "Written later.",
    "The dialogue for this part remains unwritten.",
    "Copy to follow once the edit is locked.",
    "Words will be added after the review.",
    "Needs words about the argument between them.",
    "The words for this section are awaiting the writer.",
    "This section is awaiting the final line from the writer.",
    "Something about the argument between them goes in this part.",
    "…",
    "...",
    "[line goes here]",
    "The words for this part are still to be written by the writer.",
)


def test_reworded_stubs_refused_as_lines():
    for stub in _LINE_STUBS:
        scene = _with(sung_lyrics=[], spoken_dialogue=[
            {"line_id": "l1", "character_id": "char_mara_001", "text": stub},
            {"line_id": "l2", "character_id": "char_levi_002",
             "text": "Then why is the ledger empty tonight?"}])
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is False, stub
        assert "PLACEHOLDER_CLAIM" in _codes(verdict) or "PLACEHOLDER_SCENE" in _codes(verdict), \
            (stub, verdict["defects"])


def test_reworded_stubs_refused_as_statements():
    for stub in _LINE_STUBS:
        for field in ("obstacle", "causal_outcome", "subtext_and_behavior"):
            scene = _with(**{field: stub})
            verdict = V.validate_script(_single_scene_script(scene), world=WORLD,
                                        cast_manifest=CAST)
            assert verdict["ok"] is False, (field, stub)
            assert "PLACEHOLDER_CLAIM" in _codes(verdict) or "CLAIM_NOT_WRITTEN" in _codes(verdict), \
                (field, stub, verdict["defects"])


def test_writer_instructions_refused():
    for instruction in (
        "Insert the spoken line here after the editing.",
        "Write your own line here before the shoot.",
        "Add the dialogue for this part later.",
        "Replace this with the real line before the shoot.",
        "Describe the room in more detail here.",
    ):
        scene = _with(obstacle=instruction)
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is False, instruction
        assert "PLACEHOLDER_CLAIM" in _codes(verdict), (instruction, verdict["defects"])


def test_real_dialogue_with_writer_words_accepted():
    """A character may say "writer", "line" or "copy"; that is not a stub."""
    for line in ("Don't you dare come back here without the money tonight.",
                 "You should build your own line of work out of this.",
                 "I need the words to be true before we sing them.",
                 "This part of the road floods every spring, so we leave early."):
        scene = _with(sung_lyrics=[], spoken_dialogue=[
            {"line_id": "l1", "character_id": "char_mara_001", "text": line},
            {"line_id": "l2", "character_id": "char_levi_002",
             "text": "Then tell me everything before the doors open."}])
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is True, (line, verdict["defects"])


# --- D: one normaliser for every text comparison --------------------------

_HOMOGLYPH_AFTER = (
    "аfrаid",        # Cyrillic a (U+0430)
    "αfrαid",        # Greek alpha
    "ａfrａid",       # fullwidth a
    "áfráid",        # combining accents
    "AFRAID",
    " a f r a i d ",
    "a-f-r-a-i-d",
)


def test_emotion_stagnation_beats_homoglyphs():
    for after in _HOMOGLYPH_AFTER:
        scene = _with(emotion_before="afraid", emotion_after=after)
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is False, after
        assert "EMOTION_STAGNANT" in _codes(verdict), (after, verdict["defects"])
    for before in _HOMOGLYPH_AFTER:
        scene = _with(emotion_before=before, emotion_after="afraid")
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is False, before
        assert "EMOTION_STAGNANT" in _codes(verdict), (before, verdict["defects"])


def test_emotion_stagnation_beats_lookalike_letters_anywhere():
    for before, after in (("committed", "cοmmitted"),     # Greek omicron
                          ("committed", "cоmmittеd"),     # Cyrillic o and e
                          ("defensive and ashamed", "dеfensive and ashamed"),
                          ("afraid", "аfrаid")):           # lookalikes in both
        scene = _with(emotion_before=before, emotion_after=after)
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is False, (before, after)
        assert "EMOTION_STAGNANT" in _codes(verdict), (before, after, verdict["defects"])


def test_genuine_emotion_change_accepted():
    for before, after in (("defensive and ashamed", "still afraid but less isolated"),
                          ("guarded", "committed"),
                          ("quiet and watchful", "furious and loud about it"),
                          ("afraid", "afraid and ashamed")):
        scene = _with(emotion_before=before, emotion_after=after)
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is True, (before, after, verdict["defects"])


# --- the named bypasses stay refused --------------------------------------

_NAMED_BYPASSES = (
    ("one-line placeholder scene", {"sung_lyrics": [], "spoken_dialogue": [
        {"line_id": "b1", "character_id": "char_mara_001", "text": "..."}]}),
    ("single short line scene", {"sung_lyrics": [], "spoken_dialogue": [
        {"line_id": "b2", "character_id": "char_mara_001", "text": "She sings."}]}),
    ("silent_scene short-circuit flag", {"silent_scene": True}),
    ("trivial claim", {"immediate_want": "wants stuff"}),
    ("one-word time", {"time": "sometime"}),
    ("numeric written statement", {"causal_outcome": 0}),
    ("false values as an emotion change", {"emotion_before": False, "emotion_after": False}),
    ("keyword-list dramatic purpose", {"dramatic_purpose": "grief longing stakes release closure"}),
    ("empty lip-sync intervals with performed lines", {"visible_lip_sync": {"intervals": []}}),
    ("keyword sound/framing/transition run", {
        "sound_music_cues": ["tension drone pulse riser silence"],
        "framing_movement_intent": "close push drift",
        "transition": "hard cut whip fade"}),
    ("single long line scene", {"sung_lyrics": [], "spoken_dialogue": [
        {"line_id": "b3", "character_id": "char_mara_001",
         "text": "She tells him everything about the warning tonight."}]}),
    ("reworded stub lines", {"sung_lyrics": [], "spoken_dialogue": [
        {"line_id": "b4", "character_id": "char_mara_001",
         "text": "The words for this part are still to be written."},
        {"line_id": "b5", "character_id": "char_levi_002",
         "text": "Insert the spoken line here after the editing."}]}),
)


def test_named_bypasses_refused():
    for label, over in _NAMED_BYPASSES:
        scene = _with(**over)
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD, cast_manifest=CAST)
        assert verdict["ok"] is False, label
        assert verdict["defects"], label


def test_unstructured_scene_and_beat_only_bypass_refused():
    verdict = V.validate_script(_single_scene_script("A sad owner sings about her business."))
    assert verdict["ok"] is False
    assert "PLACEHOLDER_SCENE" in _codes(verdict)
    script = {"schema_version": "s75.script.v1", "artifact_id": "s_beats",
              "beats": [{"beat_id": "b1", "because": "x", "therefore": "y"}]}
    verdict = V.validate_script(script, world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "BEAT_ONLY_BYPASS" in _codes(verdict)


# --- E: the round-5 additions ---------------------------------------------
#
# Every case below is one of the six things round 5 was directed to add or
# correct: the four new checks (silent-scene laundering, duration versus
# performed words, emotion-state shape, cross-scene repetition) and the two
# corrections (_NON_PROSE_TOKENS cut to genuine serialization literals; the
# performed-line reader reading every key that can carry a line).

def _codes_for(**over):
    verdict = V.validate_script(_single_scene_script(_with(**over)), world=WORLD,
                                cast_manifest=CAST)
    return verdict["ok"], _codes(verdict)


def test_yes_and_no_are_dialogue_not_serialization_literals():
    """Correction (a): "yes" and "no" are ordinary speech, not data literals."""
    for line in ("Yes, I signed the manifest myself before the bell.",
                 "No, put the ledger back on the counter tonight."):
        scene = _with(sung_lyrics=[], spoken_dialogue=[
            {"line_id": "l1", "character_id": "char_mara_001", "text": line},
            {"line_id": "l2", "character_id": "char_levi_002",
             "text": "Then tell me everything before the doors open."}])
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD,
                                    cast_manifest=CAST)
        assert verdict["ok"] is True, (line, verdict["defects"])
    ok, codes = _codes_for(
        subtext_and_behavior="She waits to see whether he says no before she speaks.")
    assert ok is True, codes
    ok, codes = _codes_for(spoken_dialogue=[
        {"line_id": "l1", "character_id": "char_mara_001",
         "text": "The tally is true because we both counted it twice."},
        {"line_id": "l2", "character_id": "char_levi_002",
         "text": "Then tell me everything before the doors open."}])
    assert ok is True, codes


def test_a_bare_serialization_literal_is_still_refused():
    """Correction (a), other half: a bare literal in a prose field is a literal."""
    for field in ("dramatic_purpose", "obstacle", "immediate_want"):
        for literal in ("true", "false", "null", "none", "undefined"):
            ok, codes = _codes_for(**{field: literal})
            assert ok is False, (field, literal)
            assert "CLAIM_NOT_WRITTEN" in codes, (field, literal, codes)


def test_the_literal_rule_alone_refuses_a_literal_and_alone_admits_yes():
    """Correction (a) isolated: with a one-word floor the length rule cannot
    fire, so the only rule left is the serialization-literal rule itself."""
    assert [d["code"] for d in V._statement_defects("true", "x", 1, shape=V.SHAPE_PHRASE)] \
        == ["CLAIM_NOT_WRITTEN"]
    assert [d["code"] for d in V._statement_defects("null", "x", 1, shape=V.SHAPE_PHRASE)] \
        == ["CLAIM_NOT_WRITTEN"]
    assert V._statement_defects("yes", "x", 1, shape=V.SHAPE_PHRASE) == []
    assert V._statement_defects("no", "x", 1, shape=V.SHAPE_PHRASE) == []


def test_silent_laundering_reads_every_performed_line_key():
    """Correction (b): lines parked under any other key do not buy silence."""
    parked = ["Iris signs the manifest before the bell rings tonight.",
              "Otto slides the ledger over at the counter."]
    for key in ("dialogue", "lyrics", "voiceover_text"):
        scene = _with(silent_scene=True, spoken_dialogue=[], sung_lyrics=[],
                      performance_order=[], **{key: parked})
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD,
                                    cast_manifest=CAST)
        assert verdict["ok"] is False, key
        assert "SILENT_SCENE_LAUNDERED" in _codes(verdict), (key, verdict["defects"])


def test_silent_scene_still_proves_real_content():
    """The shared base 4bd478de reading: silence exempts nothing."""
    scene = _with(silent_scene=True, spoken_dialogue=[], sung_lyrics=[],
                  performance_order=[], visible_lip_sync={"intervals": []})
    verdict = V.validate_script(_single_scene_script(scene), world=WORLD,
                                cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "PLACEHOLDER_SCENE" in _codes(verdict), verdict["defects"]


def test_duration_must_hold_the_words_the_scene_performs():
    ok, codes = _codes_for(duration_seconds=3,
                           visible_lip_sync={"intervals": [[0, 1], [2, 3]],
                                             "performer": "char_mara_001"})
    assert ok is False
    assert "DURATION_TOO_SHORT" in codes, codes
    ok, codes = _codes_for(duration_seconds=60)
    assert ok is True, codes
    ok, codes = _codes_for(duration_seconds=601)
    assert ok is False
    assert "DURATION_NOT_REAL" in codes, codes


def test_emotion_names_a_state_not_a_sentence_about_a_person():
    for value in ("she is guarded about the ledger at the counter",
                  "he is guarded about the ledger at the counter and the bell",
                  "guarded about the ledger and the bell and the counter and the room"):
        ok, codes = _codes_for(emotion_before=value)
        assert ok is False, value
        assert "EMOTION_NOT_GENUINE" in codes, (value, codes)
    ok, codes = _codes_for(emotion_before="ashamed and guarded about the bell",
                           emotion_after="defiant about the bell")
    assert ok is True, codes


def test_cross_scene_claim_repetition_refused():
    shared = dict(_good_scene())
    shared["scene_id"] = "scene_shop_floor_002"
    shared["sequence"] = 2
    shared["causal_predecessor"] = "scene_workshop_001"
    shared["location_id"] = "loc_shop_floor_002"
    script = {"schema_version": "s75.script.v1", "artifact_id": "s_x",
              "scenes": [_good_scene(), shared]}
    verdict = V.validate_script(script, world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is False
    assert "CLAIM_REPEATED" in _codes(verdict), verdict["defects"]

    neighbour = dict(shared)
    neighbour["immediate_want"] = (
        "Levi wants the repair schedule written down before the doors open.")
    neighbour["obstacle"] = "The unread warning notice blocks that writing at the bench."
    neighbour["visible_action"] = (
        "Levi sets the schedule on the bench and waits for Mara to sign it.")
    neighbour["consequential_choice"] = "Levi writes the schedule down and loses his last excuse."
    neighbour["turn_trigger"] = "Mara slides the pen across the bench."
    neighbour["subtext_and_behavior"] = "Levi hides the relief behind a flat voice at the bench."
    neighbour["dramatic_purpose"] = "Force Levi to trade reassurance for a shared repair schedule."
    script = {"schema_version": "s75.script.v1", "artifact_id": "s_y",
              "scenes": [_good_scene(), neighbour]}
    verdict = V.validate_script(script, world=WORLD, cast_manifest=CAST)
    assert verdict["ok"] is True, verdict["defects"]


def test_hyphen_spaced_statement_repetition_refused():
    ok, codes = _codes_for(
        immediate_want="Iris wants the tally read aloud before the bell rings.",
        causal_outcome="I-r-i-s w-a-n-t-s the tally read aloud before the bell rings.")
    assert ok is False
    assert "CLAIM_REPEATED" in codes, codes


def test_slot_meaning_stubs_refused():
    for stub in ("The remaining speech is on the way.",
                 "This passage is pending revision.",
                 "Copy arrives after the rewrite.",
                 "The dialogue is scheduled for later."):
        for field in ("obstacle", "causal_outcome"):
            ok, codes = _codes_for(**{field: stub})
            assert ok is False, (field, stub)
            assert "PLACEHOLDER_CLAIM" in codes, (field, stub, codes)


def test_wholly_bracketed_value_is_a_placeholder():
    for stub in ("[insert the confrontation]", "<the argument continues>",
                 "{the song resumes}"):
        ok, codes = _codes_for(obstacle=stub)
        assert ok is False, stub
        assert "PLACEHOLDER_CLAIM" in codes, (stub, codes)


def test_label_runs_refused_and_short_prose_accepted():
    """A label run is a list; a specification of two groups is writing."""
    for field, run in (("dramatic_purpose",
                        "Tighten the crane, the winch, the bollard, the fender, the davit."),
                       ("visible_action",
                        "Wren files the harbour roster, the tally, the manifest, the ledger."),
                       ("time",
                        "the harbour crane and the winch for the bollard and fender")):
        ok, codes = _codes_for(**{field: run})
        assert ok is False, (field, run)
        assert "KEYWORD_ONLY_CLAIM" in codes, (field, run, codes)
    # The four short-prose strings the round-4 verdict measured A refusing.
    ok, codes = _codes_for(time="late evening closing hour")
    assert ok is True, codes
    ok, codes = _codes_for(turn_trigger="Otto slides the ledger over.")
    assert ok is True, codes
    for line in ("Seal the manifest tonight.", "Open the harbour manifest."):
        scene = _with(sung_lyrics=[], spoken_dialogue=[
            {"line_id": "l1", "character_id": "char_mara_001", "text": line},
            {"line_id": "l2", "character_id": "char_levi_002",
             "text": "Then tell me everything before the doors open."}])
        verdict = V.validate_script(_single_scene_script(scene), world=WORLD,
                                    cast_manifest=CAST)
        assert verdict["ok"] is True, (line, verdict["defects"])
    ok, codes = _codes_for(sound_music_cues=["low room tone and a distant horn"])
    assert ok is True, codes


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print("FAIL %s: %s" % (test.__name__, exc))
        else:
            print("ok   %s" % test.__name__)
    print("%d passed, %d failed" % (len(tests) - failures, failures))
    sys.exit(1 if failures else 0)
