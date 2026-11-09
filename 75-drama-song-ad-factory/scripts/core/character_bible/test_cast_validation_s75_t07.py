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


# --- round 4: filler is not content, on every surface ----------------------
#
# These proofs are written against FILLER SHAPES, not against the strings one
# particular reviewer happened to type: repeated characters, keyboard runs,
# 3-character consonant clusters, token soup, one-item filler lists, records
# whose VALUES are filler, and nested filler. Each is paired with a positive
# control so the predicate cannot pass by refusing everything.

FILLER_STRINGS = (
    "zzz", "abc", "aaa", "bbb", "foo", "bar", "baz", "test", "stuff", "things",
    "blah", "lorem", "ipsum", "placeholder", "tbd", "na", "none", "xyz",
    "xxx", "qqq", "asdf", "qwer", "zxcv", "bdf", "str", "png", "gym",
    "x y z", "x", "ab", "", "   ",
)
FILLER_STRUCTS = (
    ["zzz"], ["abc"], ["foo", "bar"], ["x"], ["zzz", "She tells the truth."],
    {"a": "zzz"}, {"a": 1}, {"a": {"b": "zzz"}}, [{"x": "zzz"}],
)

#: Every string-content surface: (label, patch builder).
def _cast_surface(field):
    return ("cast." + field,
            lambda v: {"cast_entry_patch": {"index": 0, "set": {field: v}}})


def _crowd_surface(field):
    return ("crowd_groups." + field, lambda v: {"crowd_patch": {field: v}})


def _scene_surface(field, key):
    def patch(v):
        entry = {"line_id": "line_probe", "character_id": "char_mara_001", key: v}
        return {"scene_patch": {field: [entry]}}
    return ("scene." + field + "." + key, patch)


CONTENT_SURFACES = [
    _cast_surface("character_id"), _cast_surface("identity_digest"),
    _cast_surface("episode_role"), _cast_surface("scene_ids"),
    _cast_surface("immediate_story_function"), _cast_surface("choice_or_consequence"),
    _cast_surface("identity_revision"),
    _crowd_surface("crowd_group_id"), _crowd_surface("composition"),
    _crowd_surface("age_range"), _crowd_surface("roles"),
    _crowd_surface("collective_behavior"), _crowd_surface("permitted_motion"),
    _crowd_surface("attention_direction"), _crowd_surface("interaction_with_leads"),
    _crowd_surface("wardrobe_palette"), _crowd_surface("camera_limits"),
    _crowd_surface("entry_exit_rule"), _crowd_surface("recurrence"),
    _crowd_surface("reference_provenance"), _crowd_surface("scene_ids"),
    _crowd_surface("individualized_member_ids"),
    _scene_surface("spoken_dialogue", "text"), _scene_surface("sung_lyrics", "text"),
    _scene_surface("named_actions", "action"), _scene_surface("featured_reactions", "reaction"),
]

REAL_SENTENCE = "Disclosure shifts her from isolation to shared responsibility."
REAL_SENTENCE_2 = "Must choose to expose the hidden warning."


def test_filler_is_refused_on_every_string_content_surface():
    """Presence is not content and length is not content: no surface takes filler."""
    data = _fixture()
    holes = []
    for label, patch in CONTENT_SURFACES:
        for value in FILLER_STRINGS + FILLER_STRUCTS:
            packet = CV.validate_cast(*_case(data, patch(value)))
            if packet["ok"]:
                holes.append((label, repr(value)))
    for value in FILLER_STRINGS + FILLER_STRUCTS:
        packet = CV.validate_cast(*_case(data, {"crowd_patch":
                                                {"location_placement":
                                                 {"scene_workshop_001": value}}}))
        if packet["ok"]:
            holes.append(("crowd_groups.location_placement", repr(value)))
    assert not holes, holes


def test_repeated_characters_keyboard_runs_and_consonant_clusters_are_filler():
    """The named filler shapes, each refused as a bare token."""
    data = _fixture()
    for value in ("xxx", "qqq", "aaa", "bbb", "asdf", "qwer", "zxcv",
                  "bdf", "str", "png", "gym", "x y z"):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch":
                                                {"index": 0,
                                                 "set": {"immediate_story_function": value}}}))
        assert packet["ok"] is False, value
        assert _matching(packet, {"field": "cast.immediate_story_function",
                                  "issue_contains": "no real content"}), (value, packet["defects"])


def test_one_item_filler_lists_and_filler_records_are_refused():
    """A one-item filler list and a record whose values are filler are both out."""
    data = _fixture()
    for value in (["zzz"], ["abc"], ["aaa"], ["foo"], {"a": "zzz"}, {"a": 1},
                  {"a": {"b": "zzz"}}, [{"x": "zzz"}], ["zzz", "She tells the truth."]):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch":
                                                {"index": 0, "set": {"choice_or_consequence": value}}}))
        assert packet["ok"] is False, value
        assert _matching(packet, {"field": "cast.choice_or_consequence",
                                  "issue_contains": ""}), (value, packet["defects"])


def test_records_are_judged_on_their_values_not_on_being_non_empty():
    """age_range={"a": 1} is a non-empty record and still has no content."""
    data = _fixture()
    for value in ({"a": 1}, {"a": "zzz"}, {"a": {"b": "zzz"}}, {"count": 4}):
        packet = CV.validate_cast(*_case(data, {"crowd_patch": {"age_range": value}}))
        assert packet["ok"] is False, value
        assert _matching(packet, {"field": "crowd_groups.age_range",
                                  "issue_contains": "no real content"}), (value, packet["defects"])
    good = CV.validate_cast(*_case(data, {"crowd_patch":
                                          {"age_range": {"youngest": "late twenties",
                                                         "oldest": "early sixties"}}}))
    assert good["ok"] is True, good["defects"]


def test_positive_controls_accept_real_content():
    """No over-refusal: real sentences, roles, consequences and ids still pass."""
    data = _fixture()
    positives = (
        {"cast_entry_patch": {"index": 0, "set": {"immediate_story_function": REAL_SENTENCE}}},
        {"cast_entry_patch": {"index": 0, "set": {"choice_or_consequence": REAL_SENTENCE}}},
        {"cast_entry_patch": {"index": 0, "set": {"choice_or_consequence":
                                                  ["She tells the truth.", "The ledger opens."]}}},
        {"cast_entry_patch": {"index": 0, "set": {"episode_role": "supporting partner"}}},
        {"cast_entry_patch": {"index": 1, "set": {"episode_role": "antagonist"}}},
        {"crowd_patch": {"composition": "four adult repair customers waiting in an ordinary queue"}},
        {"crowd_patch": {"composition": ["repair customers", "waiting couriers"]}},
        {"crowd_patch": {"age_range": "adults 25-60"}},
        {"crowd_patch": {"roles": ["waiting customers"]}},
        {"crowd_patch": {"location_placement": {"scene_workshop_001":
                                                "two seated beside the north wall"}}},
        {"scene_patch": {"spoken_dialogue": [{"line_id": "line_probe",
                                              "character_id": "char_mara_001",
                                              "text": "If I lock that door, their checks bounce tomorrow."}]}},
        {"scene_patch": {"named_actions": [{"character_id": "char_levi_002",
                                            "action": "opens the ledger where Mara can read it"}]}},
    )
    for patch in positives:
        packet = CV.validate_cast(*_case(data, patch))
        assert packet["ok"] is True, (patch, packet["defects"])


def test_crowd_dialogue_is_membership_in_a_closed_vocabulary():
    """Length never qualifies a policy token; only membership does."""
    data = _fixture()
    for value in ("zzz", "abc", "ALLOW ANYTHING", "asdf", "blah"):
        packet = CV.validate_cast(*_case(data, {"crowd_patch": {"dialogue": value}}))
        assert packet["ok"] is False, value
        assert _matching(packet, {"field": "crowd_groups.dialogue",
                                  "issue_contains": "dialogue policy"}), (value, packet["defects"])
    for value in ("PROHIBITED", "INDIVIDUALIZED_ONLY"):
        patch = {"dialogue": value}
        if value != "PROHIBITED":
            patch["individualized_member_ids"] = ["char_mara_001"]
        packet = CV.validate_cast(*_case(data, {"crowd_patch": patch}))
        assert packet["ok"] is True, (value, packet["defects"])


def test_identifiers_are_shape_not_prose_but_filler_is_still_refused():
    """A digest is opaque and need not be a word; a word-like id still must be one."""
    data = _fixture()
    for value in ("identity-digest-2", "3f2a9c7b", "char_levi_002"):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch":
                                                {"index": 0, "set": {"identity_digest": value}}}))
        assert packet["ok"] is True, (value, packet["defects"])
    for value in ("zzz", "abc", "xxx", "asdf", "bdf", "gym", "x y z", "ab", ""):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch":
                                                {"index": 0, "set": {"identity_digest": value}}}))
        assert packet["ok"] is False, value
        assert _matching(packet, {"field": "cast.identity_digest",
                                  "issue_contains": ""}), (value, packet["defects"])


# --- round 8: content is GROUNDED, not token-shaped ------------------------
#
# The round-7 verdict proved that a token-shape proxy is beaten by any token
# that is alphabetic, >=3, carries one vowel, is not one repeated character,
# is not a keyboard run and is not on the FILLER_TOKENS list. Round 8 therefore
# stops asking what a token looks like and asks what the field carries:
# every word licensed, and a statement that states an act. These proofs are the
# measurement: nonsense refused, real content kept, and the exact cost named.

ROUND8_NAMED_FOUR = ("banana phone banana", "ababab", "hahaha", "aei")

ROUND8_SHAPE_PASSING_NONSENSE = (
    "blorpt zibble quank", "gribble frample wunk", "zeep zorp zalm",
    "tralala", "tatata", "mamama", "yayaya", "lalala", "obobob", "aeaeae",
    "abcabc", "eieie", "ueue", "qwertz", "asdfgj", "banana phone mango",
    "the banana phones the mango", "aei eau iou", "ababab titit",
    "zzz abc def ghi", "i\u0440sum", "flimp dorb nucket",
)

ROUND8_REAL_CONTENT = (
    "Not yet.", "Wait for me.", "Lock the door.",
    "If I lock that door, their checks bounce tomorrow.",
    "opens the ledger where Mara can read it",
    "Serves Wojciech before the queue moves.",
    "Finds no hygge in the empty workshop.",
    "Her choice turns ubuntu into a shared duty.",
    "Absorbs the backpressure before the quorum breaks.",
    "The choice raises throughput and ends the argument.",
)

ROUND8_REAL_CROWD_CONTENT = (
    "two regulars, Siobhan and Niamh, waiting at the counter",
    "four adults lingering after a long sobremesa at the counter",
    "muted everyday clothes, one Nguyen family scarf",
    "ordinary clothes, one Kubernetes conference hoodie",
)

#: Real words that the bounded vocabulary does NOT contain. Refusing them is the
#: measured cost of the approach, not a hidden bug: see the round-8 report.
ROUND8_OPEN_SET_COST = (
    "Her checkout migrates the payload overnight.",
    "The waveform stabilises after the calibration pass.",
    "Hiraeth", "Saudade", "Defenestration", "Petrichor",
)


def _isf(value):
    return {"cast_entry_patch": {"index": 0,
                                 "set": {"immediate_story_function": value}}}


def test_round8_named_four_strings_are_refused():
    """The four strings the round-7 verdict named are refused by the predicate."""
    data = _fixture()
    for value in ROUND8_NAMED_FOUR:
        packet = CV.validate_cast(*_case(data, _isf(value)))
        assert packet["ok"] is False, value
        assert _matching(packet, {"field": "cast.immediate_story_function",
                                  "issue_contains": ""}), (value, packet["defects"])


def test_round8_shape_passing_nonsense_family_is_refused():
    """Nonsense that satisfied every token-shape rule of rounds 1-7 is refused."""
    data = _fixture()
    holes = []
    for value in ROUND8_SHAPE_PASSING_NONSENSE:
        packet = CV.validate_cast(*_case(data, _isf(value)))
        if packet["ok"]:
            holes.append(value)
    assert not holes, holes


def test_round8_list_record_and_id_holes_are_closed():
    """A list entry, a record leaf and an id are each judged in full."""
    data = _fixture()
    for value in ("x y z", "foo bar baz", "blah blah blah", "a b c",
                  "aaa bbb ccc", "blorpt zibble"):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": {
            "index": 0,
            "set": {"choice_or_consequence": [
                value, "Disclosure shifts her from isolation to shared responsibility."]}}}))
        assert packet["ok"] is False, value
    for record in ({"a": "zzz", "b": "four adult repair customers waiting"},
                   {"a": 1, "b": "four adult repair customers waiting"},
                   {"a": {"b": "zzz"}, "c": {"d": "four adult repair customers waiting"}},
                   {"a": ["x y z", "four adult repair customers waiting"]},
                   {"a": "", "b": "four adult repair customers waiting"}):
        packet = CV.validate_cast(*_case(data, {"crowd_patch": {"age_range": record}}))
        assert packet["ok"] is False, record
    for identity in ("lorem-1", "tbd-1", "none-1", "test-1", "placeholder-1",
                     "zzz1", "abc123", "aaa.aaa", "aaa-aaa-aaa", "aaaaab",
                     "x1x", "blorpt"):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": {
            "index": 0, "set": {"identity_digest": identity}}}))
        assert packet["ok"] is False, identity
    for revision in (-7, 0):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": {
            "index": 0, "set": {"identity_revision": revision}}}))
        assert packet["ok"] is False, revision


def test_round8_scene_content_keys_fail_closed():
    """An entry that never names its words is refused, not skipped."""
    data = _fixture()
    for patch in ({"spoken_dialogue": [{"line_id": "zzz", "character_id": "char_mara_001"}]},
                  {"sung_lyrics": [{"line_id": "zzz", "character_id": "char_mara_001"}]},
                  {"named_actions": [{"character_id": "char_mara_001"}]},
                  {"spoken_dialogue": [{"line_id": "l1", "character_id": "char_mara_001",
                                        "text": "blorpt zibble quank"}]}):
        packet = CV.validate_cast(*_case(data, {"scene_patch": patch}))
        assert packet["ok"] is False, patch


def test_round8_placement_slot_for_an_undeclared_scene_is_refused():
    """A slot nobody would have checked is a slot filler hides in."""
    data = _fixture()
    packet = CV.validate_cast(*_case(data, {"crowd_patch": {
        "location_placement": {"scene_workshop_001": "two seated beside the north wall",
                               "scene_dead_999": "zzz"}}}))
    assert packet["ok"] is False
    assert any("not one of this group's scene_ids" in d["message"]
               for d in packet["defects"]), packet["defects"]


def test_round8_legitimate_content_is_accepted():
    """No refuse-everything fix: real lines, names, loanwords, technical words."""
    data = _fixture()
    for value in ROUND8_REAL_CONTENT:
        packet = CV.validate_cast(*_case(data, _isf(value)))
        assert packet["ok"] is True, (value, packet["defects"])
    for value in ROUND8_REAL_CROWD_CONTENT:
        packet = CV.validate_cast(*_case(data, {"crowd_patch": {"composition": value}}))
        assert packet["ok"] is True, (value, packet["defects"])
    for role in ("comic relief", "love interest", "lead", "supporting partner"):
        packet = CV.validate_cast(*_case(data, {"cast_entry_patch": {
            "index": 0, "set": {"episode_role": role}}}))
        assert packet["ok"] is True, (role, packet["defects"])


def test_round8_open_set_cost_is_measured_not_hidden():
    """The bounded vocabulary's cost: a real word it lacks is refused.

    This is asserted so the limit cannot silently drift. The round-8 report
    records it as the approach's measured over-refusal.
    """
    data = _fixture()
    for value in ROUND8_OPEN_SET_COST:
        packet = CV.validate_cast(*_case(data, _isf(value)))
        assert packet["ok"] is False, value


def test_round8_residual_licensed_nonsense_is_recorded():
    """Grammatical nonsense over licensed words still passes. Named, not hidden."""
    data = _fixture()
    packet = CV.validate_cast(*_case(data, _isf(
        "She chooses to expose the ledger before the counter opens.")))
    assert packet["ok"] is True, packet["defects"]


def test_round8_a_value_cannot_license_itself():
    """The corpus is the shipped vocabulary, never the record's own prose."""
    data = _fixture()
    packet = CV.validate_cast(*_case(data, _isf("blorpt zibble quank")))
    assert packet["ok"] is False
    ctx = CV.build_context(*_case(data, {"crowd_patch": {}}))
    assert "blorpt" not in ctx.words


def test_round8_vocabulary_is_not_read_on_import():
    """Import stays IO-free; the vocabulary loads on the first judgement."""
    import subprocess
    probe = ("import sys; sys.path[:0] = [%r, %r]; import cast_validation as C; "
             "print(C._LEXICON is None)" % (CORE, HERE))
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, check=True)
    assert out.stdout.strip() == "True", out.stdout
    assert CV.content_lexicon()["words"], "vocabulary did not load"


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
