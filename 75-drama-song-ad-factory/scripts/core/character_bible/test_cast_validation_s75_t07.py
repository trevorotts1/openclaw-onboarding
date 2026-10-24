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
    if case.get("scene_patch"):
        scene.update(copy.deepcopy(case["scene_patch"]))
    return manifest, [scene]


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


def test_speaker_sources_cover_lyrics_actions_and_reactions():
    scene = {
        "scene_id": "scene_x",
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
