"""Deterministic story-first fixtures for the S75-T32 cross-flavor acceptance cells.

All content is invented fiction. No network, no secrets, no client data.

The shapes here are the ones the production contracts in
``scripts/core/story_first_contracts.py`` and ``scripts/core/character_bible/
identity.py`` already accept, so a cell that reports PASS is reporting that the
production validator accepted a complete record -- not that a test agreed with
itself.
"""
from __future__ import annotations

LOCATION = {
    "location_id": "loc_workshop_front_001",
    "name": "Workshop front room",
    "story_function": "closing-time confrontation",
    "interior_exterior": "interior",
    "access": "Mara and Levi, cooperative partners",
    "entrances_exits": ["south glass door", "west corridor to the repair bay"],
    "visible_geography": "central ledger table, north tool bench, east counter",
}


def world(revision=1):
    return {
        "episode_id": "ep_001",
        "world_id": "world_workshop_001",
        "schema_version": "s75.world.v1",
        "revision": revision,
        "content_digest": "world-digest-%d" % revision,
        "premise": "A neighborhood repair cooperative faces a payment shortfall.",
        "era_and_timeline": "One continuous evening at closing time.",
        "locations": [dict(LOCATION)],
        "layout_and_geography": ("South entrance faces the central table; north wall "
                                 "holds the tool bench."),
        "social_rules": "Partners expect payroll warnings to be shared early.",
        "physical_and_story_rules": "Realistic drama; no unexplained rescue or new prop.",
        "light_color_atmosphere": ("Warm overhead work lights; cool fading daylight "
                                   "from the door."),
        "sound_environment": "Distant workshop fan; quiet room tone once it stops.",
        "set_dressing_and_props": [{"prop_id": "prop_notice_001",
                                    "placement": "Mara's right hand"}],
        "cast_world_relations": ["char_mara_001", "char_levi_002"],
        "wardrobe_intent": "Practical workshop clothing with clear silhouettes.",
        "continuity_rules": ("Notice sealed before admission, open afterward; ledger "
                             "stays on the table."),
        "sources_and_unknowns": {"classification": "PROPOSED_FICTION"},
        "draft_state": "COMPLETE",
        "approval_bindings": [],
    }


def cast_manifest(empty=False):
    if empty:
        return {"cast": []}
    return {
        "cast": [
            {"character_id": "char_mara_001", "identity_revision": 1,
             "identity_digest": "identity-digest-1", "episode_role": "lead",
             "scene_ids": ["scene_workshop_001"],
             "immediate_story_function": "Must choose to expose the hidden warning.",
             "choice_or_consequence": ("Disclosure shifts her from isolation to shared "
                                       "responsibility.")},
            {"character_id": "char_levi_002", "identity_revision": 1,
             "identity_digest": "identity-digest-2", "episode_role": "supporting partner",
             "scene_ids": ["scene_workshop_001"],
             "immediate_story_function": "Refuses vague reassurance and shows the empty ledger.",
             "choice_or_consequence": "His restrained offer makes Mara's turn possible."},
        ]
    }


def rich_scene():
    return {
        "scene_id": "scene_workshop_001",
        "sequence": 1,
        "causal_predecessor": None,
        "causal_outcome": ("Because Levi can see the notice, the next scene must plan "
                           "shared repair."),
        "dramatic_purpose": ("Expose the immediate cost of concealment and force Mara's "
                             "first honest choice."),
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
        "performance_order": [{"character_id": "char_mara_001",
                               "line_id": "line_mara_001"}],
        "subtext_and_behavior": "She admits the fact before naming the feeling.",
        "sound_music_cues": ["Fan clicks off before the first line."],
        "framing_movement_intent": ("Medium close-up inside the door, then insert on the "
                                    "opening envelope."),
        "duration_seconds": 24,
        "timing_basis": "authoring estimate before music",
        "transition": "Match-cut from the shared ledger to the next scene's first action.",
        "visible_lip_sync": {"intervals": [[0, 4]], "performer": "char_mara_001"},
        "claims": [],
        "references": [],
        "approval_bindings": [],
    }


def placeholder_scene():
    """The one-line / beat-only bypass the contracts must refuse."""
    scene = rich_scene()
    scene.update({
        "dramatic_purpose": "Make emotional",
        "visible_action": "She sings.",
        "consequential_choice": "She sings.",
        "spoken_dialogue": [{"line_id": "l1", "character_id": "char_mara_001",
                             "text": "..."}],
        "sung_lyrics": [],
        "performance_order": [],
    })
    return scene


def script_lyrics():
    return ({"scenes": [rich_scene()]}, {"lines": [{"line_id": "line_mara_001"}]})


def identity_record():
    """Valid reusable identity in the ``character_bible.identity`` schema.

    ``seal_identity`` must be applied by the caller (the cell does it) so the
    content digest always matches the bytes the validator hashes.
    """
    return {
        "client_id": "fixture_client",
        "character_id": "char_mara_001",
        "revision": 1,
        "schema_version": "s75.identity.v1",
        "display_name": "Mara Bell",
        "aliases": [],
        "story_status": "FICTION",
        "identity_summary": ("A repair-cooperative owner who fixes motors faster than "
                             "she admits mistakes."),
        "relevant_background_history": [
            "Helped her father close his repair stall after an avoidable cash crisis.",
            "Built the cooperative with her brother Levi and promised no more surprises.",
        ],
        "occupation": "Repair-cooperative owner and working mechanic",
        "competence": ["diagnoses small-engine failures", "trains apprentices"],
        "social_context": ("Responsible for a small team that trusts her with its "
                           "livelihoods."),
        "relationships": [],
        "wants": {"external": "Keep the cooperative open and pay the team.",
                  "internal": "Be trusted without appearing infallible."},
        "fears": ["Repeating her father's failure", "Losing the team's respect"],
        "beliefs": ["A leader carries the bad news personally before anyone else does.",
                    "Numbers on a ledger are the only honest proof of a promise."],
        "emotional_wound": ("She was the last person told that her father's stall was "
                            "closing."),
        "mistaken_belief": "A good leader protects everyone by solving problems alone.",
        "contradictions": ["Demands clear estimates while hiding the warning from Levi."],
        "habits": ["Straightens tools when avoiding a question."],
        "voice": {"rhythm": "Short practical sentences.",
                  "vocabulary": "Concrete workshop language.",
                  "restraint": "Admits the fact before naming the feeling."},
        "behavior_under_pressure": ("Takes on physical work and conceals paperwork until "
                                    "forced."),
        "appearance_traits": "Short natural curls, alert eyes, compact work-ready posture.",
        "identity_visual": {
            "face": "Wide forehead, steady dark eyes, a small scar on the left eyebrow.",
            "age": "Early thirties.",
            "hair": "Short natural curls, pinned back for work.",
            "wardrobe_rules": ["Practical work clothing with clear silhouettes.",
                               "No visible logos on any garment."],
            "continuity_constraints": ["Same eyebrow scar in every episode.",
                                       "Never a full suit while in the workshop."],
            "prompt_block": ("Mara Bell, early thirties, short natural curls, steady "
                             "dark eyes, small left-eyebrow scar, practical work clothes."),
        },
        "reference_ids": [],
        "provenance_by_field": {"all_story_fields": "explicit proposed fiction"},
        "draft_state": "DRAFT_COMPLETE",
        "approval_bindings": [],
        "shared_source": None,
        "local_cache": None,
        "sync_state": "LOCAL_ONLY",
    }


def episode_setting(setting_name="Backyard barbecue", location="Mara's yard",
                    era="present day"):
    return {
        "schema_version": "s75.episode_setting.v1",
        "episode_id": "ep_001",
        "setting_name": setting_name,
        "location": location,
        "era": era,
    }
