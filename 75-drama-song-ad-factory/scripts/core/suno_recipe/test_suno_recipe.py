#!/usr/bin/env python3
"""G12 Suno song recipe tests. Dual-mode:

    python3 core/suno_recipe/test_suno_recipe.py
    python3 -m pytest core/suno_recipe/test_suno_recipe.py
"""
from __future__ import annotations

import os
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import music_styles as MS          # noqa: E402
import suno_recipe as R            # noqa: E402

CLIENT = "We keep the lights on for every family. Come home to Dolce, come home tonight."
HOOK = ["Come home to Dolce", "come home tonight"]


def sheet(hook=HOOK, repeats=2, first="spoken"):
    s = [{"tag": "Verse 1", "delivery": first, "lines": ["We keep the lights on"]}]
    for i in range(repeats):
        s.append({"tag": "Hook", "delivery": "sung", "lines": list(hook)})
        if i < repeats - 1:
            s.append({"tag": "Verse 2", "delivery": "spoken", "lines": ["for every family"]})
    return s


def seg(d, a, b, src="measured"):
    return {"delivery": d, "start": a, "end": b, "source": src}


GOOD_TAKE = [seg("spoken", 0, 10), seg("sung", 10, 30), seg("spoken", 30, 65),
             seg("sung", 65, 100)]


class Recipe(unittest.TestCase):
    def test_every_suno_style_routes_through_recipe(self):
        ids = R.suno_style_ids()
        self.assertEqual(set(ids), set(MS.style_ids()))
        self.assertTrue(ids)
        for sid in ids:
            out = R.prepare(sid, sheet(), CLIENT)
            self.assertFalse(out["exempt"])
            self.assertEqual(R.check_style_text(out["style"]), [])
            self.assertTrue(out["style"].startswith(MS.style_prompt(sid)))
            self.assertIn("SUNG: Hook", out["style"])
            self.assertIn("SPOKEN: Verse 1, Verse 2", out["style"])

    def test_unknown_style_fails_closed(self):
        with self.assertRaises(R.RecipeError) as c:
            R.prepare("brand-new-style", sheet(), CLIENT)
        self.assertEqual(c.exception.code, "UNKNOWN_STYLE")

    def test_exemption_is_narrow(self):
        self.assertEqual(R.EXEMPT_STYLE_IDS, frozenset({"velvet_voiceover"}))
        self.assertTrue(R.prepare("velvet_voiceover", [], "")["exempt"])
        for sid in MS.style_ids() + ("all_suno", "voiceover", "velvet"):
            self.assertFalse(R.is_exempt(sid), sid)

    def test_exempt_id_matches_velvet_module(self):
        sys.path.insert(0, os.path.join(CORE, "voice_velvet_echo"))
        import velvet_voiceover as V
        self.assertEqual(R.EXEMPT_STYLE_IDS, frozenset({V.VELVET_ID}))
        self.assertNotIn(V.ALL_SUNO_ID, R.EXEMPT_STYLE_IDS)

    def test_sheet_without_repeated_client_hook_fails(self):
        for bad, why in ((sheet(repeats=1), "repeated"),
                         (sheet(hook=["Buy now and save big"]), "client's own"),
                         (sheet(first="spoken")[:1] + [
                             {"tag": "A", "delivery": "spoken", "lines": ["x"]},
                             {"tag": "B", "delivery": "sung", "lines": ["y"]},
                             {"tag": "C", "delivery": "sung", "lines": ["y"]}], "late")):
            errs = R.check_lyric_sheet(bad, CLIENT)
            self.assertTrue(any(why in e for e in errs), (why, errs))
            with self.assertRaises(R.RecipeError):
                R.prepare("soul-ballad", bad, CLIENT)

    def test_style_text_without_map_fails(self):
        raw = MS.style_prompt("soul-ballad")
        self.assertTrue(R.check_style_text(raw))
        self.assertTrue(R.check_style_text(raw + ". SUNG: none. SPOKEN: Verse."))

    def test_sheet_roundtrip(self):
        s = sheet()
        self.assertEqual(R.parse_lyrics(R.render_lyrics(s)), s)

    def test_request_seam_blocks_bypass(self):
        import music_director as MD
        raw = MS.style_prompt("rnb-flow")
        with self.assertRaises(R.RecipeError):          # raw style, no recipe
            MD.build_generate_request("la la", raw, "T")
        with self.assertRaises(R.RecipeError):          # recipe id, no map
            MD.build_generate_request("la la", raw, "T", style_id="rnb-flow",
                                      client_text=CLIENT)
        R.guard_request(raw, "la la", "velvet_voiceover")     # exempt id passes

    def test_request_seam_accepts_recipe_output(self):
        import music_director as MD
        if not MD.workcopy_paths()["models"].is_file():
            self.skipTest("68-kie-audio catalog not in this checkout")
        out = R.prepare("rnb-flow", sheet(), CLIENT)
        req = MD.build_generate_request(out["lyrics"], out["style"], "T",
                                        style_id="rnb-flow", client_text=CLIENT)
        self.assertEqual(req["input"]["style"], out["style"])

    def test_take_scored_from_labels_fails(self):
        labels = [seg("spoken", 0, 10, "label"), seg("sung", 10, 100, "label")]
        self.assertEqual(R.score_take({"segments": labels})["verdict"], "FAIL")
        self.assertEqual(R.score_take({"labels": {"sung": 0.55}})["verdict"], "FAIL")
        mixed = GOOD_TAKE[:-1] + [seg("sung", 65, 100, "label")]
        self.assertEqual(R.score_take({"segments": mixed})["verdict"], "FAIL")

    def test_measured_take_pass_late_and_no_singing(self):
        self.assertEqual(R.score_take({"segments": GOOD_TAKE})["verdict"], "PASS")
        late = [seg("spoken", 0, 45), seg("sung", 45, 70), seg("spoken", 70, 100)]
        self.assertEqual(R.score_take({"segments": late})["verdict"], "FAIL")
        none = [seg("spoken", 0, 100)]
        self.assertEqual(R.score_take({"segments": none})["verdict"], "FAIL")

    def test_rules_text_is_verbatim(self):
        self.assertEqual(len(R.RULES), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
