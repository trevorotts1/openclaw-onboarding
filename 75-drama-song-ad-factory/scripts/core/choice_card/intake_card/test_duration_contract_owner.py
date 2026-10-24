#!/usr/bin/env python3
"""Owner contract: exact six durations without changing unrelated intake text."""
import hashlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
from choice_card.intake_card import intake_card as IC
from music_styles import music_styles as MS

# Captured from accepted baseline 65858d2e9 before the duration restoration.
# These are complete question definitions, including every description,
# option, link, ask, recommendation and closing. VIDEO MODEL is separately
# owned by the authorized MiniMax H3 restoration.
QUESTION_SHA256 = {
    "offer": "135d6d82798543f975d19a7b38c84b4b45c860ea8245cae8e0cb53c00151279e",
    "link": "f7bae88c51a242b12f7b03c82a292cb722375cb599187846b29bf7c4928de152",
    "audience": "62f46da48b1eaa8c2d43cb14c680daef3d89e0ffeeb051c53cf2625e3e48886b",
    "character": "59fab7749a1131830aec78892073578bf9c137b3ab55bb176079392cb309ac2e",
    "photos": "691bfac5aa7f8ad6f630bf0300197c04d52363d6c35619f9da3fe45188fb7263",
    "models": "77817a30f601d05ff033e12fe60069b79c8d1c74ca104f2740143c8b1dff85eb",
    "music": "ad10b92aba8fd3a08fecd35d8d341302b8e575a93e65a83e2cc8d06cb404cb55",
    "look": "0d828d83ec361f2f26f19ca0d5c9361cddf3f6ecbb74fbf590fbcae2764b58dd",
    "spend": "5cacf6bad2179a77011f9f7d865b36d7c08ecdcecda267968a9678a902091d85",
    "storyboard": "249a2ac08375b9b6e79ca85e0a0d46699fe18d20a90ada328d54423ec4bac042",
    "song": "54ca39ff3ae50581dcb53fce2021b566a524b1df6f9c640892b4989a77ffc569",
    "script": "db5bfe711ebed43c1fa28d8c9b1a88336ccc58abc1bc461a268142df0c238559",
    "purpose": "ba2c6e713acb726ffe0b6ce60d767228db80dd5e48495f62d18509afa8aa2e0d",
    "shape": "aaa00770ab3d40bd980628e7994777a7646268aa00f70bca7b53ff2050f60b66",
    "permission": "5b47700c188a5b746dc5ab37df55bfbe073e4345cfc065f8ffcb62a095f8f802",
    "where": "5ca5da1b331bd2ef5c9de489cd1777d8b24190b6af3dff3ca99db46b9f8686e3",
    "agnes": "a397f139e3600832ecad473feb006d1d58284ae643176cfd515f7ac9616215cf",
}


def seconds(question):
    return tuple(IC._vm().length_seconds(row[0]) for row in question["options"])


class DurationOwnerContract(unittest.TestCase):
    def test_non_duration_questions_are_byte_exact_to_accepted_baseline(self):
        questions = IC.QUESTIONS + IC._conditional_questions()
        for q in questions:
            if q["id"] in ("length", "episode_length", "model"):
                continue
            with self.subTest(question=q["id"]):
                encoded = json.dumps(q, sort_keys=True, separators=(",", ":")).encode()
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), QUESTION_SHA256[q["id"]])

    def test_agnes_supplement_reaches_each_renderer_without_changing_choices(self):
        from choice_card.intake_card.agnes_explanation import lines
        q = IC._agnes_q("unknown")
        expected_options = list(q["options"])
        expected = lines()
        full = IC.render_card([q])
        step = IC.render_step(1, [q])
        screen = IC.studio_questions([q])[0]
        self.assertEqual(screen["supplementary_explanation"], expected)
        for paragraph in expected:
            self.assertIn(paragraph, full)
            self.assertIn(paragraph, step)
        self.assertEqual(q["options"], expected_options)
        self.assertEqual([o["text"] for o in screen["options"]], [o[0] for o in expected_options])

    def test_ordinary_menu_is_canonical_six(self):
        q = next(q for q in IC.QUESTIONS if q["id"] == "length")
        self.assertEqual(seconds(q), MS.CANONICAL_DURATION_S)
        self.assertEqual(q["options"][2], ("2 minutes", None))
        self.assertEqual(q["options"][0], ("60 seconds", "The standard ad length."))
        self.assertEqual(q["options"][1], ("90 seconds", "Room for a fuller story."))
        self.assertEqual(q["options"][3], ("3 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."))
        self.assertEqual(q["options"][4], ("5 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."))
        self.assertEqual(q["options"][5], ("10 minutes (the long version) + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."))

    def test_campaign_uses_six_and_preserves_its_existing_descriptions(self):
        q = IC._episode_length_q()
        self.assertEqual(seconds(q), MS.CANONICAL_DURATION_S)
        self.assertEqual(IC._vm().length_seconds(q["options"][q["recommended"]][0]), 180)
        self.assertEqual(q["options"][3], ("3 minutes", "one full story with room for the turn and the offer."))
        self.assertEqual(q["options"][4], ("5 minutes", "a deeper story with more of the solution at work."))
        self.assertEqual(q["options"][5], ("10 minutes", "the long version, a full show episode. (made with KIE, not Agnes)"))

    def test_purpose_never_removes_a_canonical_duration(self):
        for purpose in ("testimonial", "lesson", "paid_ad", "short_post"):
            with self.subTest(purpose=purpose):
                self.assertEqual(seconds(IC._length_q(purpose)), MS.CANONICAL_DURATION_S)

    def test_campaign_120_survives_shaping_and_method_record(self):
        answers = []
        while True:
            qs = IC._shaped(IC.QUESTIONS, answers)
            q = qs[len(answers)]
            reply = ("1" if q["id"] == "purpose" else
                     "Christine, a lawyer, is alone at the New Year's Eve ball drop" if q.get("free_text") else
                     "3" if q["id"] == "episode_length" else "recommended")
            parsed = IC._parse(reply, q)
            self.assertIsNotNone(parsed, (q["id"], reply))
            answers.append(parsed)
            if q["id"] == "episode_length":
                break
        for _ in range(3):
            qs = IC._shaped(IC.QUESTIONS, answers)
            rec = IC._method_record(answers, qs)
            self.assertEqual(rec["chosen_length_s"], 120)
            self.assertEqual(IC._length_text(answers, [q["id"] for q in qs], "campaign"), "2 minutes")
            self.assertEqual(answers[-1]["text"], "2 minutes")


if __name__ == "__main__":
    unittest.main()
