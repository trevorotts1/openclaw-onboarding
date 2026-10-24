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
    script = _load("rich_causal_script.json")
    scene = _good_scene()
    scene["scene_id"] = "scene_shop_floor_002"
    scene["sequence"] = 2
    scene["causal_predecessor"] = "scene_workshop_001"
    scene["location_id"] = "loc_shop_floor_002"
    scene["dramatic_purpose"] = "Force Levi to trade reassurance for a shared repair schedule."
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
