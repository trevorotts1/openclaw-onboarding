#!/usr/bin/env python3
"""Focused tests for story_first_contracts (S75-T03 / S75-A03).

Run: python3 -m pytest -q scripts/core/test_story_first_contracts.py
 or: python3 scripts/core/test_story_first_contracts.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import story_first_contracts as C  # noqa: E402

LOCATION = {
    "location_id": "loc_workshop_front_001",
    "name": "Workshop front room",
    "story_function": "closing-time confrontation",
    "interior_exterior": "interior",
    "access": "Mara and Levi, cooperative partners",
    "entrances_exits": ["south glass door", "west corridor to the repair bay"],
    "visible_geography": "central ledger table, north tool bench, east counter",
}

WORLD = {
    "episode_id": "ep_001",
    "world_id": "world_workshop_001",
    "schema_version": C.WORLD_SCHEMA_VERSION,
    "revision": 1,
    "content_digest": "world-digest-1",
    "premise": "A neighborhood repair cooperative faces a payment shortfall.",
    "era_and_timeline": "One continuous evening at closing time.",
    "locations": [LOCATION],
    "layout_and_geography": "South entrance faces the central table; north wall holds the tool bench.",
    "social_rules": "Partners expect payroll warnings to be shared early.",
    "physical_and_story_rules": "Realistic drama; no unexplained rescue or new prop.",
    "light_color_atmosphere": "Warm overhead work lights; cool fading daylight from the door.",
    "sound_environment": "Distant workshop fan; quiet room tone once it stops.",
    "set_dressing_and_props": [{"prop_id": "prop_notice_001", "placement": "Mara's right hand"}],
    "cast_world_relations": ["char_mara_001", "char_levi_002"],
    "wardrobe_intent": "Practical workshop clothing with clear silhouettes.",
    "continuity_rules": "Notice sealed before admission, open afterward; ledger stays on the table.",
    "sources_and_unknowns": {"classification": "PROPOSED_FICTION"},
    "draft_state": C.COMPLETE,
    "approval_bindings": [],
}

IDENTITY = {
    "client_id": "fiction_contract_demo",
    "character_id": "char_mara_001",
    "revision": 1,
    "content_digest": "identity-digest-1",
    "schema_version": C.IDENTITY_SCHEMA_VERSION,
    "display_name": "Mara Bell",
    "aliases": [],
    "story_status": "PROPOSED_FICTION",
    "identity_summary": "A repair-cooperative owner who fixes motors faster than she admits mistakes.",
    "relevant_background_history": [
        "Helped her father close his repair stall after an avoidable cash crisis.",
        "Built the cooperative with her brother Levi and promised no more surprises.",
    ],
    "occupation": "Repair-cooperative owner and working mechanic",
    "competence": ["diagnoses small-engine failures", "trains apprentices"],
    "social_context": "Responsible for a small team that trusts her with its livelihoods.",
    "relationships": [
        {"character_id": "char_levi_002", "type": "older brother and partner",
         "history": "They built the workshop together.",
         "present_tension": "She withheld a payment warning he needs.",
         "dependency": "She trusts his judgment but fears his disappointment."},
        {"character_id": "char_levi_002", "type": "duplicate edge is allowed by id"},
    ],
    "wants": {"external": "Keep the cooperative open and pay the team.",
              "internal": "Be trusted without appearing infallible."},
    "fears": ["Repeating her father's failure", "Losing the team's respect"],
    "emotional_wound": "She was the last person told that her father's stall was closing.",
    "mistaken_belief": "A good leader protects everyone by solving problems alone.",
    "contradictions": ["Demands clear estimates while hiding the warning from her own partner."],
    "habits": ["Straightens tools when avoiding a question."],
    "voice": {"rhythm": "Short practical sentences.", "vocabulary": "Concrete workshop language.",
              "restraint": "Admits the fact before naming the feeling."},
    "behavior_under_pressure": "Takes on physical work and conceals paperwork until forced.",
    "appearance_traits": "Short natural curls, alert eyes, compact work-ready posture.",
    "reference_ids": [],
    "provenance_by_field": {"all_story_fields": "explicit proposed fiction"},
    "draft_state": C.COMPLETE,
    "approval_bindings": [],
    "shared_source": None,
    "local_cache": None,
    "sync_state": "ILLUSTRATIVE_NOT_PERSISTED",
}

MANIFEST = {
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

SCENE = {
    "scene_id": "scene_workshop_001",
    "sequence": 1,
    "causal_predecessor": None,
    "causal_outcome": "Because Levi can see the notice, the next scene must plan shared repair.",
    "dramatic_purpose": "Expose the immediate cost of concealment and force Mara's first honest choice.",
    "time": "evening, closing time",
    "location_id": "loc_workshop_front_001",
    "world_revision": 1,
    "cast_ids": ["char_mara_001", "char_levi_002"],
    "identity_revisions": {"char_mara_001": 1, "char_levi_002": 1},
    "crowd_group_ids": [],
    "immediate_want": "Mara wants Levi to accept one more vague promise.",
    "obstacle": "The empty ledger and his direct question block that escape.",
    "visible_action": "Mara opens the sealed warning and sets it beside the open ledger.",
    "consequential_choice": "She gives up control of the information.",
    "emotion_before": "defensive and ashamed",
    "emotion_after": "still afraid but less isolated",
    "turn_trigger": "Putting the notice where Levi can read it.",
    "spoken_dialogue": [
        {"line_id": "line_mara_001", "character_id": "char_mara_001",
         "text": "If I lock that door, their checks bounce tomorrow."},
    ],
    "sung_lyrics": [
        {"line_id": "line_mara_003", "character_id": "char_mara_001",
         "text": "I kept the light on, kept the truth outside."},
    ],
    "performance_order": [{"character_id": "char_mara_001", "line_id": "line_mara_001"}],
    "subtext_and_behavior": "She admits the fact before naming the feeling.",
    "sound_music_cues": ["Fan clicks off before the first line."],
    "framing_movement_intent": "Medium close-up inside the door, then insert on the opening envelope.",
    "duration_seconds": 24,
    "timing_basis": "authoring estimate before music",
    "transition": "Match-cut from the shared ledger to the next scene's first action.",
    "visible_lip_sync": {"intervals": [[0, 4]], "performer": "char_mara_001"},
    "claims": [],
    "references": [],
    "approval_bindings": [],
}

ONE_LINE_SCENE = dict(
    SCENE,
    dramatic_purpose="Make emotional",
    visible_action="She sings.",
    consequential_choice="She sings.",
    spoken_dialogue=[{"line_id": "l1", "character_id": "char_mara_001", "text": "..."}],
    sung_lyrics=[],
    performance_order=[],
)


def _raises(fn, *args):
    try:
        fn(*args)
    except C.ContractError as exc:
        return exc
    raise AssertionError("%r did not refuse" % (fn.__name__,))


def _approve(registry, kind, targets):
    return registry.put(kind, {"decision": "APPROVED"}, state=C.APPROVED,
                        approved_digests={t: registry.digest_of(t) for t in targets})


def _seed(registry):
    registry.put("research_bundle", {"claims": [{"claim_id": "c1"}]})
    registry.put("episode_world", WORLD)
    registry.put("episode_cast_manifest", MANIFEST)
    registry.put("causal_story_beats", {"beats": [{"beat_id": "b1"}]})
    registry.put("scene_plan", {"scenes": [SCENE]})
    registry.put("script", {"scenes": [SCENE]})
    registry.put("lyrics", {"lines": [{"line_id": "line_mara_001"}]})


# --- order ---------------------------------------------------------------

def test_stage_order_is_the_mandated_chain():
    assert C.STAGE_ORDER == (
        "research_premise", "cast_and_world", "story_plan", "script_lyrics",
        "package_approval", "music", "timed_storyboard", "keyframes",
        "storyboard_approval", "video", "assembly",
    )


def test_complete_fixture_passes_every_schema():
    assert C.validate_identity(IDENTITY) == []
    assert C.validate_world(WORLD) == []
    assert C.validate_cast_manifest(MANIFEST, [SCENE]) == []
    assert C.validate_scene(SCENE, world=WORLD) == []


def test_full_run_admits_every_stage_in_order():
    registry = C.RunRegistry()
    registry.put("research_bundle", {"claims": [{"claim_id": "c1"}]})
    assert C.check_stage("research_premise", registry)["admitted"] is True

    registry.put("episode_world", WORLD)
    registry.put("episode_cast_manifest", MANIFEST)
    assert C.check_stage("cast_and_world", registry)["admitted"] is True

    registry.put("causal_story_beats", {"beats": [{"beat_id": "b1"}]})
    registry.put("scene_plan", {"scenes": [SCENE]})
    assert C.check_stage("story_plan", registry)["admitted"] is True

    registry.put("script", {"scenes": [SCENE]})
    registry.put("lyrics", {"lines": [{"line_id": "line_mara_001"}]})
    assert C.check_stage("script_lyrics", registry)["admitted"] is True

    registry.put("creative_package_manifest", {"package": "v1"})
    _approve(registry, "package_approval", C.APPROVAL_BINDS["package_approval"])
    assert C.check_stage("package_approval", registry)["admitted"] is True

    registry.put("selected_music", {"style_id": "soul-ballad"})
    assert C.check_stage("music", registry)["admitted"] is True

    registry.put("timed_storyboard", {"scenes": [SCENE]})
    registry.put("production_continuity", {"scenes": [SCENE]})
    assert C.check_stage("timed_storyboard", registry)["admitted"] is True

    registry.put("keyframes", {"shots": [{"shot_id": "s1"}]})
    assert C.check_stage("keyframes", registry)["admitted"] is True

    _approve(registry, "storyboard_approval", C.APPROVAL_BINDS["storyboard_approval"])
    assert C.check_stage("storyboard_approval", registry)["admitted"] is True

    registry.put("video_checks", {"checks": ["pass"]})
    assert C.check_stage("video", registry)["admitted"] is True

    registry.put("final_delivery", {"delivered": True})
    assert C.check_stage("assembly", registry)["admitted"] is True
    assert C.next_stage("assembly") is None


def test_music_refused_before_whole_package_approval():
    registry = C.RunRegistry()
    _seed(registry)
    registry.put("creative_package_manifest", {"package": "v1"})
    exc = _raises(C.check_stage, "music", registry)
    assert "package_approval" in exc.packet["missing"]
    assert "package_approval" in exc.packet["unfinished_stages"]


def test_stale_package_approval_digest_refused():
    registry = C.RunRegistry()
    _seed(registry)
    registry.put("creative_package_manifest", {"package": "v1"})
    _approve(registry, "package_approval", C.APPROVAL_BINDS["package_approval"])
    registry.put("creative_package_manifest", {"package": "v2"})
    exc = _raises(C.check_stage, "music", registry)
    assert exc.code in ("APPROVAL", "ORDER")
    assert any(d["target"] == "creative_package_manifest"
               for d in exc.packet["approval_defects"])


def test_missing_cast_refused_before_script():
    registry = C.RunRegistry()
    registry.put("research_bundle", {"claims": [{"claim_id": "c1"}]})
    registry.put("episode_world", WORLD)
    registry.put("causal_story_beats", {"beats": [{"beat_id": "b1"}]})
    registry.put("scene_plan", {"scenes": [SCENE]})
    exc = _raises(C.check_stage, "script_lyrics", registry)
    assert "episode_cast_manifest" in exc.packet["missing"]
    assert exc.packet["stage"] == "script_lyrics"


def test_empty_cast_manifest_is_missing_not_an_opt_out():
    defects = C.validate_cast_manifest({"cast": []}, [SCENE])
    assert defects and defects[0]["field"] == "cast"
    assert "missing requirement" in defects[0]["issue"]


def test_one_line_scene_refused():
    fields = {d["field"] for d in C.validate_scene(ONE_LINE_SCENE, world=WORLD)}
    assert "dramatic_purpose" in fields
    assert "visible_action" in fields
    assert "spoken_dialogue" in fields or "dialogue" in fields

    registry = C.RunRegistry()
    _seed(registry)
    registry.put("scene_plan", {"scenes": [ONE_LINE_SCENE]})
    registry.put("script", {"scenes": [ONE_LINE_SCENE]})
    exc = _raises(C.check_stage, "script_lyrics", registry)
    assert exc.code == "SCHEMA"
    assert exc.packet["schema_defects"]


def test_undefined_location_refused():
    scene = dict(SCENE, location_id="loc_nowhere")
    fields = [d["field"] for d in C.validate_scene(scene, world=WORLD)]
    assert "location_id" in fields


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
