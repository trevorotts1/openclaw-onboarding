#!/usr/bin/env python3
"""Focused tests for cast_writer (S75-T06 / S75-A06).

Every test uses the fixture in ``tests/fixtures/complete_cast.json`` and a fake
dispatcher. No network, no provider, no paid generation.

Run: python3 -m pytest -q scripts/core/character_bible/test_cast_writer_s75_t06.py
 or: python3 scripts/core/character_bible/test_cast_writer_s75_t06.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, HERE)

import cast_writer as W  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(CORE)),
                       "tests", "fixtures", "complete_cast.json")


def load():
    with open(FIXTURE, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return copy.deepcopy(data["request"]), copy.deepcopy(data["response"])


def fake(response, calls=None):
    """A dispatcher that records what it was asked and answers the fixture."""
    def dispatch(prompt):
        if calls is not None:
            calls.append(copy.deepcopy(prompt))
        return copy.deepcopy(response)
    return dispatch


def author(request=None, response=None, calls=None, **kwargs):
    base_request, base_response = load()
    return W.author_cast(request or base_request,
                         dispatch=fake(response or base_response, calls),
                         model="fake-author", **kwargs)


def refuse(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except W.CastWriteError as exc:
        return exc
    raise AssertionError("expected CastWriteError, got a completed cast")


# --- the authored cast ------------------------------------------------------

def test_fixture_authors_a_complete_cast():
    result = author()
    assert result["state"] == "COMPLETE"
    assert len(result["identities"]) == 3
    roles = {e["character_id"]: e["episode_role"] for e in result["manifest"]["cast"]}
    assert roles == {"char_mara_001": "lead",
                     "char_levi_002": "supporting",
                     "char_rosa_003": "recurring"}


def test_every_identity_carries_wants_fears_beliefs_and_speech():
    result = author()
    for record in result["identities"]:
        assert W.profile_defects(record) == [], record["character_id"]
        assert record["wants"]["external"] and record["wants"]["internal"]
        assert record["fears"] and record["beliefs"]
        assert record["voice"]["rhythm"] and record["voice"]["restraint"]
        assert record["emotional_wound"] and record["mistaken_belief"]
        assert record["draft_state"] == "DRAFT_COMPLETE"
        assert len(record["content_digest"]) == 64


def test_manifest_binds_revision_and_digest_from_the_record():
    result = author()
    by_id = {c["character_id"]: c for c in result["identities"]}
    for entry in result["manifest"]["cast"]:
        record = by_id[entry["character_id"]]
        assert entry["identity_revision"] == record["revision"]
        assert entry["identity_digest"] == record["content_digest"]
    assert result["manifest"]["library_digest"] == W.library_digest(result["library"])
    assert result["manifest"]["research_binding"] == {
        "revision": 4, "content_digest": "research-r4-3f9c1a05b7d24e68"}


def test_text_identity_saves_with_no_image():
    result = author()
    assert all(record["reference_ids"] == [] for record in result["identities"])
    assert result["state"] == "COMPLETE"


# --- real dispatch, correlated ----------------------------------------------

def test_dispatch_is_invoked_once_with_exact_revisions():
    calls = []
    author(calls=calls)
    assert len(calls) == 1
    prompt = calls[0]
    assert prompt["task"] == "author_complete_episode_cast"
    assert prompt["research"] == {"revision": 4,
                                  "content_digest": "research-r4-3f9c1a05b7d24e68"}
    assert prompt["library"]["revision"] == 2
    assert prompt["library"]["content_digest"] == W.library_digest({
        "schema_version": W.LIBRARY_SCHEMA_VERSION,
        "client_id": "fiction_contract_demo",
        "revision": 2,
        "characters": load()[0]["library"]["characters"],
    })
    assert prompt["selection"] == "mixed"
    assert prompt["scene_ids"] == ["sc_01", "sc_02"]
    assert prompt["premise"].startswith("A neighborhood repair cooperative")
    assert "wants" in prompt["requirements"]["full_profile_fields"]


def test_receipt_correlates_output_to_the_captured_response():
    _, response = load()
    result = author()
    receipt = result["dispatch_receipt"]
    assert receipt["calls"] == 1
    assert receipt["response_digest"] == W.canonical_digest(response)
    assert receipt["selected_character_ids"] == [
        "char_mara_001", "char_levi_002", "char_rosa_003"]
    assert receipt["authored_character_ids"] == ["char_mara_001", "char_rosa_003"]
    assert W.verify_receipt(result) is True


def test_tampered_response_breaks_the_receipt():
    result = author()
    result["dispatch_response"]["cast"][0]["episode_role"] = "lead"
    result["dispatch_response"]["extra"] = "not what the receipt recorded"
    assert W.verify_receipt(result) is False


def test_request_cannot_supply_a_prewritten_cast():
    request, response = load()
    request["cast"] = [{"character_id": "char_mara_001", "episode_role": "lead"}]
    calls = []
    result = author(request=request, response=response, calls=calls)
    assert len(calls) == 1
    # the answer is the dispatcher's, never the request's shortcut
    assert len(result["manifest"]["cast"]) == 3


# --- refusals ---------------------------------------------------------------

def test_missing_dispatcher_refuses_before_any_work():
    request, _ = load()
    exc = refuse(W.author_cast, request, dispatch=None)
    assert exc.code == "NO_DISPATCHER"


def test_incomplete_cast_is_refused_by_name():
    request, response = load()
    del response["identities"][1]["beliefs"]
    del response["identities"][1]["voice"]["restraint"]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "char_rosa_003" in str(exc)
    assert "Rosa Iyer" in str(exc)
    assert "beliefs" in str(exc)
    assert "voice.restraint" in str(exc)
    named = {d["character_id"] for d in exc.packet["incomplete"]}
    assert named == {"char_rosa_003"}


def test_a_face_only_identity_is_not_a_cast_member():
    request, response = load()
    led = response["identities"][0]
    for field in W.PROFILE_FIELDS:
        led.pop(field, None)
    led["appearance_traits"] = "Black woman, short natural curls."
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    named = [d for d in exc.packet["incomplete"] if d["character_id"] == "char_mara_001"]
    fields = {d["field"] for d in named}
    assert {"wants", "fears", "beliefs", "voice"} <= fields
    assert "Mara Bell" in str(exc)


def test_missing_cast_key_is_not_an_empty_cast():
    request, response = load()
    del response["cast"]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "MISSING_CAST"


def test_empty_cast_is_refused():
    request, response = load()
    response["cast"] = []
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "CAST_EMPTY"


def test_anonymous_speaker_is_refused():
    request, _ = load()
    request["scenes"][1]["spoken_dialogue"].append(
        {"line_id": "ln_09", "character_id": "a woman", "text": "She will not tell them."})
    exc = refuse(W.author_cast, request, dispatch=fake(load()[1]), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "a woman" in str(exc)


def test_undeclared_speaker_is_refused():
    request, _ = load()
    request["scenes"][0]["spoken_dialogue"].append(
        {"line_id": "ln_10", "character_id": "char_ghost_009",
         "text": "Nobody knows who I am."})
    exc = refuse(W.author_cast, request, dispatch=fake(load()[1]), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "char_ghost_009" in str(exc)


def test_crowd_group_may_not_speak():
    request, response = load()
    response["crowd_groups"][0]["dialogue"] = "murmured"
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "dialogue" in str(exc)


def test_crowd_group_may_not_single_a_member_out():
    request, response = load()
    response["crowd_groups"][0]["singled_out"] = True
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "singled_out" in str(exc)


def test_crowd_group_needs_placement_and_behavior_rules():
    request, response = load()
    del response["crowd_groups"][0]["location_placement"]
    del response["crowd_groups"][0]["collective_behavior"]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert "location_placement" in str(exc)
    assert "collective_behavior" in str(exc)


def test_stale_library_identity_is_refused():
    request, response = load()
    request["library"]["characters"][0]["content_digest"] = "0" * 64
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "STALE_IDENTITY"
    assert "char_levi_002" in str(exc)


def test_authored_identity_cannot_overwrite_an_existing_person():
    request, response = load()
    response["identities"].append(copy.deepcopy(
        request["library"]["characters"][0]))
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "IDENTITY_OVERWRITE"
    assert "char_levi_002" in str(exc)


def test_duplicate_identity_ids_are_refused():
    request, response = load()
    response["identities"].append(copy.deepcopy(response["identities"][0]))
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "DUPLICATE_IDENTITY"


def test_existing_selection_may_not_author_new_people():
    request, response = load()
    request["selection"] = "existing"
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "SELECTION_NEW_REFUSED"
    assert "char_mara_001" in str(exc)


def test_new_selection_may_not_reuse_library_people():
    request, response = load()
    request["selection"] = "new"
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "char_levi_002" in str(exc)


def test_unknown_scene_reference_is_refused():
    request, response = load()
    response["cast"][2]["scene_ids"] = ["sc_99"]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert "sc_99" in str(exc)


def _people_free(response):
    request, _ = load()
    request["library"]["characters"] = []
    request["scene_ids"] = []
    request["scenes"] = []
    response.update({"people_free": True, "cast": [], "crowd_groups": [],
                     "identities": []})
    return request, response


def test_people_free_requires_a_stated_reason():
    request, response = _people_free(load()[1])
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "PEOPLE_FREE"


def test_people_free_with_a_reason_is_accepted():
    request, response = _people_free(load()[1])
    response["people_free_reason"] = "A landscape-only piece with no performers."
    result = author(request=request, response=response)
    assert result["manifest"]["people_free"] is True
    assert result["manifest"]["cast"] == []


def test_people_free_contradiction_is_refused():
    request, response = load()
    response["people_free"] = True
    response["people_free_reason"] = "No performers."
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "PEOPLE_FREE_CONTRADICTION"


def test_missing_input_is_named():
    request, _ = load()
    request.pop("research_bundle")
    request["selection"] = "guess"
    exc = refuse(W.author_cast, request, dispatch=fake(load()[1]), model="fake-author")
    assert exc.code == "MISSING_INPUT"
    assert "research_bundle" in str(exc)
    assert "selection" in str(exc)


def test_client_namespace_mismatch_is_refused():
    request, response = load()
    request["library"]["client_id"] = "another_client"
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "CLIENT_MISMATCH"


def test_dangling_relationship_is_refused():
    request, response = load()
    response["identities"][0]["relationships"][0]["character_id"] = "char_ghost_010"
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    dangling = [d for d in exc.packet["incomplete"]
                if d["field"] == "relationships" and "char_ghost_010" in d["issue"]]
    assert dangling and dangling[0]["character_id"] == "char_mara_001"


# --- complete declared-participant surface (S75-A06 repair) -----------------

def test_scene_identity_revision_binding_needs_a_cast_profile():
    request, response = load()
    request["scenes"][0]["identity_revisions"]["char_ghost_009"] = 1
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "char_ghost_009" in str(exc)
    assert "char_mara_001" not in str(exc)

def test_reaction_people_and_meaningful_extras_must_be_cast():
    request, response = load()
    request["scenes"][0]["reaction_people"] = ["char_ghost_011"]
    request["scenes"][1]["meaningful_extras"] = ["char_ghost_012"]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "char_ghost_011" in str(exc)
    assert "char_ghost_012" in str(exc)

def test_lip_sync_performer_binding_must_be_cast():
    request, response = load()
    request["scenes"][0]["visible_lip_sync"] = [
        {"shot_id": "sh_01", "performer": "char_ghost_013",
         "audio_line_id": "ln_01", "interval_seconds": [0.0, 2.4]}]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "char_ghost_013" in str(exc)

def test_performer_id_binding_must_be_cast():
    request, response = load()
    request["scenes"][1]["performance_order"] = [
        {"slot": 1, "performer_id": "char_ghost_014", "line_id": "ln_03"}]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "char_ghost_014" in str(exc)

def test_scene_crowd_group_must_exist_in_the_manifest():
    request, response = load()
    request["scenes"][0]["crowd_group_ids"] = ["cg_ghost"]
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "cg_ghost" in str(exc)
    assert "no such group" in str(exc)

def test_scene_crowd_group_declared_in_the_manifest_is_accepted():
    result = author()
    assert result["state"] == "COMPLETE"
    assert result["manifest"]["crowd_groups"][0]["crowd_group_id"] == \
        "crowd_workshop_queue_001"
    # the full surface is read: ids hide in bindings, not only in the lines
    assert set(W.derive_speakers(load()[0]["scenes"])) >= {
        "char_mara_001", "char_levi_002", "char_rosa_003"}
    assert W.derive_crowds(load()[0]["scenes"]) == ["crowd_workshop_queue_001"]

def test_generic_descriptor_as_display_name_is_refused():
    request, response = load()
    response["identities"][0]["display_name"] = "a customer in line"
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    assert exc.code == "INCOMPLETE_CAST"
    assert "a customer in line" in str(exc)
    named = [d for d in exc.packet["incomplete"]
             if d["field"] == "display_name" and "char_mara_001" == d["character_id"]]
    assert named and "generic descriptor" in named[0]["issue"]

def test_generic_descriptor_refused_in_either_position():
    request, response = load()
    response["identities"][1]["display_name"] = "the manager"
    response["identities"][1]["character_id"] = "char_manager_002"
    exc = refuse(W.author_cast, request, dispatch=fake(response), model="fake-author")
    fields = {d["field"] for d in exc.packet["incomplete"]
              if d["character_id"] == "char_manager_002"}
    assert "display_name" in fields

# --- a generic descriptor is not an identity, whatever it wears (S75-A06 r3) -

#: The same descriptor dressed in punctuation, quoting, brackets, a
#: possessive or a trailing period. Every one is the same evasion.
DRESSED = ["a woman,", "the manager.", "a woman!", "a woman;", "(the manager)",
           "'the manager'", '"a woman"', "[the manager]", "the manager's",
           "  A WOMAN.  ", "a woman, leader"]

#: Real people whose names merely contain descriptor words: a name is a name.
REAL_NAMES = ["Dana Woman", "Theresa Manager", "Wanda Manager",
              "Aisha Womack", "Manny Persons"]

#: A role description, not a person: it opens on the generic descriptor, and
#: the module already refuses that shape ("a customer in line").
ROLE_DESCRIPTIONS = ["the manager of the east wing", "a customer in line"]


def test_punctuation_dressed_descriptor_is_refused_as_display_name():
    for dressed in DRESSED:
        request, response = load()
        response["identities"][0]["display_name"] = dressed
        exc = refuse(W.author_cast, request, dispatch=fake(response),
                     model="fake-author")
        assert exc.code == "INCOMPLETE_CAST", dressed
        named = [d for d in exc.packet["incomplete"]
                 if d["character_id"] == "char_mara_001"
                 and d["field"] == "display_name"
                 and "generic descriptor" in d["issue"]]
        assert named, dressed


def test_punctuation_dressed_descriptor_is_refused_as_character_id():
    for dressed in DRESSED:
        request, response = load()
        response["identities"][0]["character_id"] = dressed
        response["cast"][0]["character_id"] = dressed
        exc = refuse(W.author_cast, request, dispatch=fake(response),
                     model="fake-author")
        assert exc.code == "INCOMPLETE_CAST", dressed
        named = [d for d in exc.packet["incomplete"]
                 if d["field"] == "character_id"
                 and "generic descriptor" in d["issue"]]
        assert named, dressed


def test_punctuation_dressed_descriptor_is_refused_in_a_scene_binding():
    for dressed in ("a woman,", "(the manager)", "'the manager'"):
        request, _ = load()
        request["scenes"][0]["spoken_dialogue"].append(
            {"line_id": "ln_09", "character_id": dressed,
             "text": "She will not tell them."})
        exc = refuse(W.author_cast, request, dispatch=fake(load()[1]),
                     model="fake-author")
        assert exc.code == "INCOMPLETE_CAST", dressed
        assert "generic descriptor" in str(exc), dressed


def test_real_names_containing_descriptor_words_still_pass():
    for name in REAL_NAMES:
        request, response = load()
        response["identities"][0]["display_name"] = name
        result = author(request=request, response=response)
        assert result["state"] == "COMPLETE", name
        assert W.profile_defects(result["identities"][0]) == [], name


def test_a_role_description_is_still_not_an_identity():
    for described in ROLE_DESCRIPTIONS:
        request, response = load()
        response["identities"][0]["display_name"] = described
        exc = refuse(W.author_cast, request, dispatch=fake(response),
                     model="fake-author")
        assert exc.code == "INCOMPLETE_CAST", described


# --- nested per-shot bindings (S75-A06 r3) ----------------------------------

def _with_shots(scene_shots):
    def mutate(request):
        request["scenes"][0]["shots"] = copy.deepcopy(scene_shots)
    return mutate


def test_nested_shot_subject_binding_must_be_declared():
    shapes = [
        [{"shot_id": "sh_01", "subjects": ["char_ghost_015"]}],
        [{"shot_id": "sh_01", "subjects": {"char_ghost_016": {"frame": 3}}}],
        [{"shot_id": "sh_01", "subject_id": "char_ghost_017"}],
        [{"shot_id": "sh_01", "subjects": ["a woman,"]}],
    ]
    for shots in shapes:
        request, response = load()
        _with_shots(shots)(request)
        exc = refuse(W.author_cast, request, dispatch=fake(response),
                     model="fake-author")
        assert exc.code == "INCOMPLETE_CAST", shots
        assert ("generic descriptor" in str(exc)
                or "char_ghost_0" in str(exc)), shots


def test_nested_shot_subject_of_a_declared_person_is_accepted():
    request, response = load()
    _with_shots([{"shot_id": "sh_01",
                  "subjects": ["char_mara_001", {"char_levi_002": {"frame": 3}}]}])(request)
    result = author(request=request, response=response)
    assert result["state"] == "COMPLETE"

# --- adapters and purity ----------------------------------------------------

def test_legacy_bible_is_a_seed_not_an_identity():
    seed = W.seed_from_legacy_bible(
        {"character_name": "Mara Bell", "character_description": "A mechanic.",
         "character_background": "Built a cooperative.",
         "character_ethnicity": "Black woman.", "voice_notes": "Short sentences.",
         "reference_images": ["ref_1.png"]},
        "fiction_contract_demo", "char_mara_001")
    assert seed["seed_state"] == "SEED_ONLY_INCOMPLETE"
    assert seed["reference_ids"] == ["ref_1.png"]
    assert seed["story_status"] == "OWNER_SUPPLIED"
    missing = {d["field"] for d in W.profile_defects(seed)}
    assert {"wants", "fears", "beliefs", "voice"} <= missing


def test_module_holds_no_provider_transport():
    with open(os.path.join(HERE, "cast_writer.py"), "r", encoding="utf-8") as handle:
        source = handle.read()
    for forbidden in ("urllib", "http.client", "requests", "socket", "subprocess"):
        assert forbidden not in source, forbidden


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
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
