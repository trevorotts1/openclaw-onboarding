#!/usr/bin/env python3
"""S75-T05 focused tests: reusable identity, setting separation, full cast.

Run: python3 75-drama-song-ad-factory/scripts/core/character_bible/test_identity_s75_t05.py
"""
import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

try:
    from character_bible import identity as ID  # package import
except ImportError:                            # direct script run
    import identity as ID


def mara(revision=1):
    record = {
        "client_id": "fixture_client",
        "character_id": "char_mara_001",
        "revision": revision,
        "schema_version": ID.SCHEMA_VERSION,
        "display_name": "Mara Bell",
        "aliases": [],
        "story_status": "FICTION",
        "identity_summary": ("A repair-cooperative owner who fixes a motor faster "
                             "than she admits a mistake."),
        "relevant_background_history": [
            "Helped her father close his repair stall after an avoidable cash crisis.",
            "Built the cooperative with her older brother Levi.",
        ],
        "occupation": "Repair-cooperative owner and working mechanic",
        "competence": ["diagnoses small-engine failures", "trains apprentices"],
        "social_context": "Responsible for a small team that trusts her with its livelihoods.",
        "relationships": [{
            "character_id": "char_levi_002",
            "type": "older brother and cooperative partner",
            "history": "They built the workshop together.",
            "present_tension": "She has withheld a payment warning he needs.",
            "dependency": "She trusts his judgment but fears his disappointment.",
        }],
        "wants": {"external": "Keep the cooperative open and pay the team.",
                  "internal": "Be trusted without appearing infallible."},
        "fears": ["Repeating her father's failure", "Losing the team's respect"],
        "beliefs": ["A good leader solves problems alone.",
                    "Being told late is worse than being told bad news."],
        "emotional_wound": "She was the last person told her father's stall was closing.",
        "mistaken_belief": "A good leader protects everyone by solving problems alone.",
        "contradictions": ["Demands clear estimates while hiding the warning from her partner."],
        "habits": ["Straightens tools when avoiding a question"],
        "voice": {"rhythm": "Short practical sentences; speeds up when afraid.",
                  "vocabulary": "Concrete workshop language.",
                  "restraint": "Admits the fact before naming the feeling."},
        "behavior_under_pressure": "Takes on physical work and conceals paperwork until forced.",
        "appearance_traits": "Black woman, short natural curls, alert eyes, compact posture.",
        "identity_visual": {
            "face": "Round face, wide-set eyes, a thin scar over the left eyebrow.",
            "age": "38",
            "hair": "Short natural curls, trimmed close at the sides.",
            "wardrobe_rules": ["Workwear cut for movement", "No logos or brand marks",
                               "Same silhouette in every setting"],
            "continuity_constraints": ["Scar stays on the left eyebrow",
                                       "Curls never lengthen between scenes"],
            "prompt_block": "Mara Bell, 38, Black woman, round face, left-eyebrow scar, "
                            "short natural curls, compact work-ready posture.",
        },
        "reference_ids": [],
        "provenance_by_field": {"all_story_fields": "explicit proposed fiction"},
        "draft_state": "DRAFT_COMPLETE",
        "approval_bindings": [],
        "shared_source": None,
        "local_cache": None,
        "sync_state": "LOCAL_ONLY",
    }
    record["content_digest"] = ID.canonical_digest(record)
    return record


def levi():
    record = mara()
    record.update({
        "character_id": "char_levi_002",
        "display_name": "Levi Bell",
        "identity_summary": "Mara's older brother, a mechanic who keeps the weekly accounts.",
        "relationships": [{
            "character_id": "char_mara_001",
            "type": "younger sister and cooperative partner",
            "history": "They rebuilt the workshop after their father's stall closed.",
            "present_tension": "He refuses vague reassurance about payroll.",
            "dependency": "He needs her technical leadership; she needs his discipline.",
        }],
        "identity_visual": {
            "face": "Long face, trimmed beard, steady eyes.",
            "age": "42",
            "hair": "Close-cut hair.",
            "wardrobe_rules": ["Plain work shirts", "No logos"],
            "continuity_constraints": ["Beard stays trimmed", "Same build"],
            "prompt_block": "Levi Bell, 42, Black man, close-cut hair, trimmed beard.",
        },
    })
    record["content_digest"] = ID.canonical_digest(record)
    return record


def library():
    return {"client_id": "fixture_client", "characters": [mara(), levi()]}


def setting(name, location, era, wardrobe):
    return {"schema_version": ID.EPISODE_SCHEMA_VERSION, "episode_id": "ep_001",
            "setting_name": name, "location": location, "era": era,
            "wardrobe_instance": wardrobe}


def manifest(lib=None, cast=None, **extra):
    lib = lib or library()
    body = {
        "schema_version": ID.MANIFEST_SCHEMA_VERSION,
        "client_id": "fixture_client",
        "episode_id": "ep_001",
        "library_digest": ID.library_digest(lib),
        "cast": cast if cast is not None else [
            {"character_id": "char_mara_001", "identity_revision": 1,
             "identity_digest": lib["characters"][0]["content_digest"],
             "episode_role": "lead", "scene_ids": ["sc_01"],
             "immediate_story_function": "Conceals the warning, then must expose it.",
             "choice_or_consequence": "Chooses shared responsibility over isolation.",
             "relationship_changes": ["Risks Levi's trust, then earns a working partnership."]},
            {"character_id": "char_levi_002", "identity_revision": 1,
             "identity_digest": lib["characters"][1]["content_digest"],
             "episode_role": "supporting", "scene_ids": ["sc_01"],
             "immediate_story_function": "Refuses vague reassurance.",
             "choice_or_consequence": "Makes the missing money visible.",
             "relationship_changes": ["Moves from protective silence to open accounting."]},
        ],
        "crowd_groups": [],
    }
    body.update(extra)
    return body


def crowd(**overrides):
    group = {
        "crowd_group_id": "crowd_workshop_queue_001",
        "composition": "Four adult repair customers",
        "count": 4,
        "age_range": "25-70",
        "roles": ["waiting customers"],
        "location_placement": "Two seated by the north wall, two at the counter",
        "collective_behavior": "Quiet queue behavior",
        "permitted_motion": "Shifting weight, checking phones at chest height",
        "attention_direction": "Toward the counter, never the camera",
        "interaction_with_leads": "None; they stay outside focus",
        "wardrobe_palette": "Muted everyday clothes without company marks",
        "camera_limits": "Never in close-up or focus",
        "entry_exit_rule": "Already present at scene start; exits with the queue",
        "recurrence": "single scene",
        "dialogue": "forbidden",
        "reference_provenance": "proposed fiction",
        "scene_ids": ["sc_01"],
    }
    group.update(overrides)
    return group


def codes(record):
    return {d["code"] for d in record.defects}


class IdentitySchema(unittest.TestCase):
    def test_valid_identity_passes(self):
        ID.validate_identity(mara())

    def test_text_identity_saves_without_an_image(self):
        record = mara()
        self.assertEqual(record["reference_ids"], [])
        ID.validate_identity(record)

    def test_seal_identity_stamps_a_stable_digest(self):
        sealed = ID.seal_identity(mara())
        self.assertEqual(ID.validate_identity(sealed)["content_digest"],
                         ID.canonical_digest(sealed))

    def test_setting_change_keeps_identity_and_history(self):
        barbecue = setting("Backyard barbecue", "Mara's yard", "present day",
                           "Denim jacket over the work shirt")
        white_house = setting("White House reception", "East Room", "present day",
                              "Formal navy suit, no logos")
        ID.validate_episode_setting(barbecue)
        ID.validate_episode_setting(white_house)

        before = mara()
        after = copy.deepcopy(before)
        # A wardrobe/setting change is a production revision, never an identity rewrite.
        self.assertEqual(before["character_id"], after["character_id"])
        self.assertEqual(before["content_digest"], after["content_digest"])
        self.assertNotEqual(barbecue["wardrobe_instance"], white_house["wardrobe_instance"])
        ID.validate_identity(after)

    def test_identity_rejects_episode_setting_fields(self):
        record = mara()
        record["location"] = "East Room"
        with self.assertRaises(ID.IdentityDefect) as caught:
            ID.validate_identity(record)
        self.assertIn("SETTING_IN_IDENTITY", codes(caught.exception))

    def test_incomplete_profile_names_every_missing_part(self):
        record = mara()
        for field in ("wants", "fears", "beliefs", "voice"):
            record.pop(field)
        record["content_digest"] = ID.canonical_digest(record)
        with self.assertRaises(ID.IdentityDefect) as caught:
            ID.validate_identity(record)
        fields = {d["field"] for d in caught.exception.defects}
        self.assertTrue({"wants", "fears", "beliefs", "voice"} <= fields)

    def test_face_clothes_file_is_not_a_story_bible(self):
        record = mara()
        record["identity_visual"] = {k: v for k, v in record["identity_visual"].items()
                                     if k in ("face", "hair", "wardrobe_rules")}
        record["content_digest"] = ID.canonical_digest(record)
        with self.assertRaises(ID.IdentityDefect) as caught:
            ID.validate_identity(record)
        self.assertIn("VISUAL", codes(caught.exception))

    def test_wardrobe_instance_rejected_inside_visual(self):
        record = mara()
        record["identity_visual"]["wardrobe_instance"] = "Denim jacket"
        record["content_digest"] = ID.canonical_digest(record)
        with self.assertRaises(ID.IdentityDefect) as caught:
            ID.validate_identity(record)
        self.assertIn("SETTING_IN_IDENTITY", codes(caught.exception))


class Library(unittest.TestCase):
    def test_duplicate_character_ids_fail(self):
        lib = library()
        lib["characters"].append(copy.deepcopy(lib["characters"][0]))
        with self.assertRaises(ID.IdentityDefect) as caught:
            ID.validate_library(lib)
        self.assertIn("DUPLICATE_ID", codes(caught.exception))

    def test_dangling_relationship_fails(self):
        lib = library()
        lib["characters"][0]["relationships"][0]["character_id"] = "char_missing"
        lib["characters"][0]["content_digest"] = ID.canonical_digest(lib["characters"][0])
        with self.assertRaises(ID.IdentityDefect) as caught:
            ID.validate_library(lib)
        self.assertIn("DANGLING_RELATIONSHIP", codes(caught.exception))

    def test_external_relationship_is_declared_not_dangling(self):
        lib = library()
        lib["characters"][0]["relationships"][0]["external"] = True
        lib["characters"][0]["relationships"][0]["character_id"] = "client_spouse"
        lib["characters"][0]["content_digest"] = ID.canonical_digest(lib["characters"][0])
        ID.validate_library(lib)


class CastGate(unittest.TestCase):
    def test_valid_cast_passes(self):
        ID.validate_cast(manifest(), library(),
                         speakers=["char_mara_001", "char_levi_002"],
                         scene_ids=["sc_01"])

    def test_omitted_cast_fails(self):
        body = manifest()
        body.pop("cast")
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(body, library())
        self.assertIn("CAST_INCOMPLETE", codes(caught.exception))

    def test_empty_cast_fails(self):
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(cast=[]), library())
        self.assertIn("CAST_EMPTY", codes(caught.exception))

    def test_unknown_identity_fails(self):
        cast = manifest()["cast"]
        cast[0]["character_id"] = "char_nobody"
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(cast=cast), library())
        self.assertIn("UNKNOWN_IDENTITY", codes(caught.exception))

    def test_stale_identity_revision_fails(self):
        cast = manifest()["cast"]
        cast[0]["identity_revision"] = 2
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(cast=cast), library())
        self.assertIn("STALE_REVISION", codes(caught.exception))

    def test_undeclared_speaker_fails(self):
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(), library(), speakers=["char_ghost_009"])
        self.assertIn("UNDECLARED_SPEAKER", codes(caught.exception))

    def test_anonymous_speaker_fails(self):
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(), library(), speakers=["a worker"])
        self.assertIn("ANONYMOUS_SPEAKER", codes(caught.exception))

    def test_unknown_scene_fails(self):
        body = manifest()
        body["cast"][0]["scene_ids"] = ["sc_99"]
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(body, library(), scene_ids=["sc_01"])
        self.assertIn("UNKNOWN_SCENE", codes(caught.exception))

    def test_library_digest_binding_is_enforced(self):
        body = manifest()
        body["library_digest"] = "0" * 64
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(body, library())
        self.assertIn("LIBRARY_BINDING", codes(caught.exception))

    def test_people_free_episode_is_explicit_and_valid(self):
        ID.validate_cast(manifest(cast=[], people_free=True,
                                  people_free_reason="A deliberately empty workshop"),
                         library())
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(people_free=True,
                                      people_free_reason="nothing here"), library())
        self.assertIn("PEOPLE_FREE_CONTRADICTION", codes(caught.exception))


class CrowdRules(unittest.TestCase):
    def test_valid_crowd_group_passes(self):
        ID.validate_cast(manifest(crowd_groups=[crowd()]), library(), scene_ids=["sc_01"])

    def test_crowd_without_placement_or_behavior_fails(self):
        group = crowd()
        group.pop("location_placement")
        group.pop("collective_behavior")
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(crowd_groups=[group]), library())
        fields = {d["field"] for d in caught.exception.defects}
        self.assertIn("crowd_groups[0].location_placement", fields)
        self.assertIn("crowd_groups[0].collective_behavior", fields)

    def test_singled_out_member_must_be_promoted(self):
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(crowd_groups=[crowd(singled_out=["counter customer"])]),
                             library())
        self.assertIn("CROWD_SINGLED_OUT", codes(caught.exception))

    def test_crowd_dialogue_is_refused(self):
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(crowd_groups=[crowd(dialogue="murmurs approval")]),
                             library())
        self.assertIn("CROWD_DIALOGUE", codes(caught.exception))

    def test_crowd_unknown_scene_fails(self):
        with self.assertRaises(ID.CastDefect) as caught:
            ID.validate_cast(manifest(crowd_groups=[crowd(scene_ids=["sc_99"])]),
                             library(), scene_ids=["sc_01"])
        self.assertIn("UNKNOWN_SCENE", codes(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
