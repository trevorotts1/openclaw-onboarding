#!/usr/bin/env python3
"""S75-T22 repair r3: a registered extra style reaches the instruction payload.

The conformance review at cd2c6a7a found that the four S75-T22 recipes resolved
on every music_styles id seam but never reached instruction consumption:
``prepare``/``build_request`` refused them with UNKNOWN_STYLE (the recipe gate
read only the three D18 ids), and ``style_text``/``music_block`` refused them
with PROMPT_TEMPLATE_UNREADABLE (no ``references/prompt-templates/music/<id>.json``).

This test proves the end-to-end route for the one style whose per-style template
data now exists. It is deliberately narrow: the other three still lack their
template file, and this file must not pretend otherwise.

    python3 scripts/core/suno_recipe/test_recipes_instruction_payload.py
    python3 -m pytest scripts/core/suno_recipe/test_recipes_instruction_payload.py
"""
from __future__ import annotations

import os
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import suno_recipe as R          # noqa: E402

STYLE = "cinematic-orchestral-song"
CLIENT = "I am not small. I never was. One seed of truth made me strong."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}


def sheet():
    return [
        {"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
        {"tag": "Verse", "delivery": "sung",
         "lines": ["One seed of truth made me stro-o-ong,",
                   "One seed is a-all I ne-e-eed,"]},
        {"tag": "Hook 1", "delivery": "sung", "lines": list(HOOK)},
        {"tag": "Hook 2", "delivery": "sung", "lines": list(HOOK)},
        {"tag": "Hook 3", "delivery": "sung", "lines": list(HOOK)},
        {"tag": "Outro", "delivery": "spoken",
         "lines": ["Get the book. Link below."]},
    ]


class RegisteredStyleInstructionPayload(unittest.TestCase):
    def test_registered_style_is_accepted_by_the_recipe_gate(self):
        self.assertIn(STYLE, R.recipe_style_ids())
        out = R.prepare(STYLE, sheet(), CLIENT, 58, hook_plan=HOOK_PLAN)
        self.assertFalse(out["exempt"])
        self.assertEqual(R.check_style_text(out["style"]), [])
        self.assertTrue(out["lyrics"])

    def test_registered_style_builds_the_provider_request(self):
        req = R.build_request(STYLE, sheet(), CLIENT, "T", 58,
                              hook_plan=HOOK_PLAN)
        self.assertEqual(R.check_envelope(req), [])
        inp = req["input"]
        self.assertTrue(inp["style"].startswith("orchestral film-style song"))
        self.assertIn("band keeps playing", inp["style"].lower())
        self.assertIn("The lead SPEAKS", inp["style"])
        self.assertTrue(inp["lyrics"])
        self.assertIn("choir", inp["negative_tags"])
        # The client-only reference never reaches outbound text.
        self.assertNotIn("Adele", inp["style"])

    def test_unknown_style_is_still_refused(self):
        with self.assertRaises(R.RecipeError) as ctx:
            R.prepare("brand-new-style", sheet(), CLIENT, 58)
        self.assertEqual(ctx.exception.code, "UNKNOWN_STYLE")


if __name__ == "__main__":
    unittest.main()
