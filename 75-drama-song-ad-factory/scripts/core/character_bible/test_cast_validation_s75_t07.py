#!/usr/bin/env python3
"""S75-T07 focused proofs: crowd rules, singled-out people, undeclared speakers.

Run: python3 75-drama-song-ad-factory/scripts/core/character_bible/test_cast_validation_s75_t07.py

Fiction-only fixtures. Nothing here writes, dispatches a model or reaches a
provider/Notion/client endpoint.
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SKILL = os.path.dirname(os.path.dirname(CORE))
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cast_validation as CV  # noqa: E402  (bare name: HERE precedes CORE)

FIXTURE_PATH = os.path.join(SKILL, "tests", "fixtures", "cast_rejections.json")


def _fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _case(data, case):
    manifest = copy.deepcopy(data["manifest"])
    scene = copy.deepcopy(data["scene"])
    if case.get("manifest"):
        manifest = copy.deepcopy(case["manifest"])
    if case.get("manifest_patch"):
        manifest.update(copy.deepcopy(case["manifest_patch"]))
    if case.get("crowd_patch"):
        manifest["crowd_groups"][0].update(copy.deepcopy(case["crowd_patch"]))
    if case.get("cast_entry_patch"):
        patch = case["cast_entry_patch"]
        entry = manifest["cast"][patch.get("index", 0)]
        entry.update(copy.deepcopy(patch.get("set", {})))
        for key in patch.get("delete", []):
            entry.pop(key, None)
    for patch in case.get("cast_entry_patches") or []:
        entry = manifest["cast"][patch.get("index", 0)]
        entry.update(copy.deepcopy(patch.get("set", {})))
        for key in patch.get("delete", []):
            entry.pop(key, None)
    if case.get("scene_patch"):
        scene.update(copy.deepcopy(case["scene_patch"]))
    for key in case.get("scene_delete", []):
        scene.pop(key, None)
    return manifest, [scene] + copy.deepcopy(case.get("extra_scenes") or [])


def _matching(packet, expected):
    return [d for d in packet["defects"]
            if d["field"] == expected["field"]
            and expected["issue_contains"] in d.get("issue", "")]


def test_fixture_file_is_present_and_fiction_only():
    data = _fixture()
    assert data["cases"], "no fixture cases"
    assert "fiction" in data["_note"].lower()
    assert not os.path.exists(os.path.join(HERE, ".env")), "no credential file belongs here"


def test_lawful_crowd_and_declared_cast_pass():
    data = _fixture()
    case = data["cases"][0]
    assert case["expect"] == "pass"
    packet = CV.assert_valid_cast(*_case(data, case))
    assert packet == {"ok": True, "defect_count": 0, "defects": []}


def test_every_fixture_rejection_is_refused_with_a_pointer():
    data = _fixture()
    for case in data["cases"]:
        if case["expect"] == "pass":
            continue
        packet = CV.validate_cast(*_case(data, case))
        assert packet["ok"] is False, case["name"]
        assert _matching(packet, case["expect"]), (
            case["name"], case["expect"], packet["defects"])


def test_crowd_group_requires_composition_behavior_placement():
    data = _fixture()
    group = copy.deepcopy(data["manifest"]["crowd_groups"][0])
    assert CV.validate_crowd_group(group, {"scene_workshop_001"},
                                   {"char_mara_001", "char_levi_002"}) == []

    bare = {"crowd_group_id": "crowd_bg_001", "scene_ids": ["scene_workshop_001"]}
    fields = {d["field"] for d in CV.validate_crowd_group(bare, {"scene_workshop_001"}, set())}
    for expected in ("crowd_groups.composition", "crowd_groups.location_placement",
                     "crowd_groups.collective_behavior", "crowd_groups.dialogue"):
        assert expected in fields, (expected, sorted(fields))


def test_singled_out_crowd_member_promoted_to_identity_is_accepted():
    data = _fixture()
    manifest, scenes = _case(data, data["cases"][0])
    manifest["crowd_groups"][0]["dialogue"] = "INDIVIDUALIZED_ONLY"
    manifest["crowd_groups"][0]["individualized_member_ids"] = ["char_mara_001"]
    assert CV.validate_cast(manifest, scenes)["ok"] is True


def test_group_dialogue_does_not_smuggle_an_undeclared_speaker():
    data = _fixture()
    manifest, scenes = _case(data, data["cases"][0])
    group = manifest["crowd_groups"][0]
    group["dialogue"] = "ALLOWED"
    group["individualized_member_ids"] = []
    packet = CV.validate_cast(manifest, scenes)
    assert packet["ok"] is False
    assert any(d["field"] == "crowd_groups.dialogue" for d in packet["defects"])


def test_assert_valid_cast_raises_one_packet_not_per_character():
    data = _fixture()
    case = next(c for c in data["cases"] if c["name"] == "reject_absent_cast_field")
    try:
        CV.assert_valid_cast(*_case(data, case))
    except CV.CastValidationError as exc:
        assert exc.packet["defect_count"] >= 1
        assert exc.packet["defects"][0]["field"] == "cast"
        assert exc.packet["defects"][0]["message"]
    else:
        raise AssertionError("missing cast was not refused")


def test_absent_cast_is_not_a_people_free_opt_out():
    packet = CV.validate_cast({"crowd_groups": []}, [])
    assert packet["ok"] is False
    assert packet["defects"][0]["field"] == "cast"
    assert "missing requirement" in packet["defects"][0]["issue"]


def test_scene_cast_field_absent_or_empty_fails_closed_with_a_real_speaker():
    data = _fixture()
    for patch in ({"scene_delete": ["cast_ids"]}, {"scene_patch": {"cast_ids": []}},
                  {"scene_patch": {"cast_ids": None}}):
        case = dict(data["cases"][0], **patch)
        packet = CV.validate_cast(*_case(data, case))
        assert packet["ok"] is False, patch
        assert _matching(packet, {"field": "scene.cast_ids", "issue_contains": ""}), packet["defects"]


def test_absent_and_empty_scene_cast_are_distinct_named_errors():
    data = _fixture()
    absent = CV.validate_cast(*_case(data, {"scene_delete": ["cast_ids"]}))
    empty = CV.validate_cast(*_case(data, {"scene_patch": {"cast_ids": []}}))
    assert [d["issue"] for d in absent["defects"]] == ["missing"]
    assert [d["issue"] for d in empty["defects"]] == ["empty"]


def test_cast_entry_null_and_empty_values_fail_closed():
    data = _fixture()
    for patch in ({"index": 0, "set": {"episode_role": None}},
                  {"index": 0, "set": {"episode_role": "  "}},
                  {"index": 0, "set": {"scene_ids": []}},
                  {"index": 1, "delete": ["choice_or_consequence"]}):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": patch}))
        assert packet["ok"] is False, patch
        assert packet["defects"], patch


def test_crowd_group_id_present_but_null_is_refused():
    data = _fixture()
    packet = CV.validate_cast(*_case(data, {"crowd_patch": {"crowd_group_id": None}}))
    assert packet["ok"] is False
    assert any(d["field"] == "crowd_groups.crowd_group_id" and d["issue"] == "empty"
               for d in packet["defects"])


def test_speaker_sources_cover_lyrics_actions_and_reactions():
    scene = {
        "scene_id": "scene_x",
        "cast_ids": [],
        "sung_lyrics": [{"line_id": "l1", "character_id": "char_ghost"}],
        "named_actions": [{"character_id": "char_ghost", "action": "opens the door"}],
        "featured_reactions": [{"character_id": "char_ghost", "reaction": "flinches"}],
    }
    speakers = CV.derive_speakers([scene])
    assert {s["field"] for s in speakers} == {
        "sung_lyrics", "named_actions", "featured_reactions"}
    packet = CV.validate_cast({"cast": []}, [scene])
    assert packet["ok"] is False
    assert sum(1 for d in packet["defects"] if "not declared in cast" in d["issue"]) >= 1


def _case_named(data, name):
    return next(c for c in data["cases"] if c["name"] == name)


def test_crowd_in_a_scene_its_own_record_forbids_is_refused():
    """Existence is not permission: the group exists, the scene exists, still no."""
    data = _fixture()
    case = _case_named(data, "reject_crowd_referenced_in_scene_its_record_forbids")
    before = CV.validate_cast(*_case(data, dict(case,
                                               crowd_patch={"scene_ids": ["scene_ferry_deck_103"],
                                                            "location_placement":
                                                                {"scene_ferry_deck_103": "far rail, out of focus"}})))
    assert before["ok"] is True, before["defects"]
    packet = CV.validate_cast(*_case(data, case))
    assert packet["ok"] is False
    assert _matching(packet, case["expect"]), packet["defects"]


def test_crowd_membership_error_is_distinct_from_undefined_crowd():
    data = _fixture()
    cases = {_case_named(data, n)["expect"]["issue_contains"]
             for n in ("reject_crowd_referenced_in_scene_its_record_forbids",
                       "reject_crowd_membership_unprovable",
                       "reject_undefined_crowd_reference")}
    assert len(cases) == 3, cases


def test_substantive_cast_fields_refuse_falsy_and_wrong_type_values():
    """Presence is not content: 0, False and ["x"] are each refused by name."""
    data = _fixture()
    patches = ({"episode_role": 0}, {"episode_role": False}, {"episode_role": ["lead"]},
               {"immediate_story_function": 0}, {"immediate_story_function": False},
               {"immediate_story_function": "x"},
               {"choice_or_consequence": ["x"]}, {"choice_or_consequence": 5},
               {"choice_or_consequence": True}, {"choice_or_consequence": []})
    for value in patches:
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": {"index": 0, "set": value}}))
        assert packet["ok"] is False, value
        field = "cast." + next(iter(value))
        assert any(d["field"] == field for d in packet["defects"]), (value, packet["defects"])


def test_episode_role_must_come_from_the_story_vocabulary():
    data = _fixture()
    good = {"index": 0, "set": {"episode_role": "supporting partner"}}
    assert CV.validate_cast(*_case(data, {"cast_entry_patch": good}))["ok"] is True
    for bad in ("wizard banana", "lead banana", "zzzz"):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": {"index": 0, "set": {"episode_role": bad}}}))
        assert packet["ok"] is False, bad
        assert _matching(packet, {"field": "cast.episode_role",
                                  "issue_contains": "vocabulary"}), packet["defects"]


def test_choice_or_consequence_accepts_real_text_and_real_lists():
    data = _fixture()
    for value in ("Disclosure shifts her from isolation to shared responsibility.",
                  ["She tells the truth.", "The ledger opens."]):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": {"index": 0, "set": {"choice_or_consequence": value}}}))
        assert packet["ok"] is True, (value, packet["defects"])


def test_crowd_fields_refuse_numbers_booleans_and_token_lists():
    data = _fixture()
    for patch in ({"age_range": 5}, {"dialogue": 7}, {"permitted_motion": True},
                  {"roles": ["x"]}, {"wardrobe_palette": 0}):
        packet = CV.validate_cast(*_case(data, {"crowd_patch": patch}))
        field = "crowd_groups." + next(iter(patch))
        assert packet["ok"] is False, patch
        assert any(d["field"] == field for d in packet["defects"]), (patch, packet["defects"])


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - standalone runner
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("\n%d passed, %d failed, %d total" % (len(tests) - failures, failures, len(tests)))
    sys.exit(1 if failures else 0)
