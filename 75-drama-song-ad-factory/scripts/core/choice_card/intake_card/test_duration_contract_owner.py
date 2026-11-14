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
    # Re-pinned for S75-006, which changes these screens on purpose: OFFER takes
    # the web address, CHARACTER carries the new wording, PHOTOS and SHAPE are
    # recap defaults, AI MODELS carries the new plain wording, MUSIC STYLE shows
    # three styles plus the full-list option, and CHECKPOINTS is new.
    "offer": "8cbe11218554e2a13153de6ed6d1d727a8bdbe77e4feee7b3f25b78e362c2299",
    "link": "732ae7a34eb770a0d20f99efda0cd9903f4fb265b10fca785602d9f9ea418664",
    "audience": "62f46da48b1eaa8c2d43cb14c680daef3d89e0ffeeb051c53cf2625e3e48886b",
    "character": "1e6bdbaacc82d59de35b56734913b9df23b0fba1bcc6ba49bc1d8bd306f2b0f2",
    "photos": "fca6e105bd1fd50fad8b3e69e5fbfb587d1903d6c197aa99cda43ca7293cc590",
    "models": "919c74f6bc6b3d43f5fedf2caa75fec466d3149b5f541fcb631f332f25bf491e",
    # Re-pinned for U-GEN437: the last MUSIC STYLE option answers nothing -- it
    # opens the ``music_full`` screen -- and the question now carries that as
    # ``opens_screen``. Every visible word, option and recommendation is
    # unchanged; only the screen-opening key is new.
    "music": "774ace65739dcd05d0262f09552c8b5ad9522ee59ecdcc780adb54a923baeabc",
    # Re-pinned for S75-074, which replaces "I start as soon as the card is
    # approved." with plain client words on the CHECKPOINTS screen.
    "checkpoints": "ddd7d0c083f4276a3e6896eab1e13a64c7e6108b844e61e00bd59f209612c812",
    "look": "0d828d83ec361f2f26f19ca0d5c9361cddf3f6ecbb74fbf590fbcae2764b58dd",
    "spend": "5cacf6bad2179a77011f9f7d865b36d7c08ecdcecda267968a9678a902091d85",
    "storyboard": "249a2ac08375b9b6e79ca85e0a0d46699fe18d20a90ada328d54423ec4bac042",
    "song": "54ca39ff3ae50581dcb53fce2021b566a524b1df6f9c640892b4989a77ffc569",
    "script": "db5bfe711ebed43c1fa28d8c9b1a88336ccc58abc1bc461a268142df0c238559",
    "purpose": "ba2c6e713acb726ffe0b6ce60d767228db80dd5e48495f62d18509afa8aa2e0d",
    "shape": "6b2e9955b66e960b5752c1c36ee72d08e4b642623d5e01e7aed41110e465c461",
    "permission": "5b47700c188a5b746dc5ab37df55bfbe073e4345cfc065f8ffcb62a095f8f802",
    "where": "5ca5da1b331bd2ef5c9de489cd1777d8b24190b6af3dff3ca99db46b9f8686e3",
    # Re-pinned for S75-020: AGNES recommends a pick only for a client who said
    # yes before, and its closing says "Reply 1 or 2." when nothing is marked.
    "agnes": "c53035ef359c1092760a0d00cf286230ebcecc64b3d7c4e43a1ccc6d7452af2a",
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
        # S75-006: no vendor name in a client question, so the row no longer
        # carries "(made with KIE, not Agnes)".
        self.assertEqual(q["options"][5], ("10 minutes", "the long version, a full show episode."))

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
