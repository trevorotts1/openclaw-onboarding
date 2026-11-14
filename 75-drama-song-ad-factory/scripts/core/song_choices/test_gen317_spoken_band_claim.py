#!/usr/bin/env python3
"""U-GEN317: the judge docstring must not promise a band nothing supplies.

``judge_take(spoken_range_pct=...)`` has no production supplier: ``cmd_generate``
builds its kwargs without it, so every production song is judged against the
style's constant target. The module docstring used to advertise the judging as
a "per-ad target"; this test pins that claim out and pins the true statement in.

Pre-fix (song_dispatch.py module docstring carrying "(per-ad target)") this test
FAILS. Run: python3 core/song_choices/test_gen317_spoken_band_claim.py
"""
import ast
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
DISPATCH = os.path.join(CORE, "song_dispatch", "song_dispatch.py")


def module_docstring():
    with open(DISPATCH, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), DISPATCH)
    doc = ast.get_docstring(tree) or ""
    return " ".join(doc.split())


class SpokenBandClaim(unittest.TestCase):
    def test_docstring_no_longer_claims_a_per_ad_target(self):
        doc = module_docstring()
        self.assertNotIn("per-ad target", doc,
                         "the docstring still advertises a per-ad spoken band "
                         "that no run document supplies")

    def test_docstring_states_the_style_constant_governs(self):
        doc = module_docstring()
        self.assertIn("style's constant target", doc,
                      "the docstring must say the style's constant target governs")
        self.assertIn("no run document supplies one", doc,
                      "the docstring must say plainly that nothing supplies a band")


if __name__ == "__main__":
    unittest.main(verbosity=2)
