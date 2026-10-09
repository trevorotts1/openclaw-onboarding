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

CLIENT = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]


def sheet(hook=HOOK, repeats=3, vocalise=True):
    s = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]}]
    if vocalise:
        s.append({"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,", "A-a-a-a-a-ah,"]})
    for i in range(repeats):
        s.append({"tag": "Hook %d" % (i + 1), "delivery": "sung", "lines": list(hook)})
        if i == 0:
            s.append({"tag": "Verse", "delivery": "sung",
                      "lines": ["One seed of truth made me stro-o-ong,", "One seed is a-all I ne-e-eed,"]})
    s.append({"tag": "Outro", "delivery": "spoken",
              "lines": ["She Found Power in the Climb. Get the book. Link below."]})
    return s


def seg(d, a, b, src="measured"):
    return {"delivery": d, "start": a, "end": b, "source": src}


# 22% spoken of runtime, 78% sung of voice time, first singing at 10%.
GOOD_TAKE = [seg("spoken", 0, 10), seg("sung", 10, 45), seg("spoken", 45, 57),
             seg("sung", 57, 100)]


class Recipe(unittest.TestCase):
    def test_every_suno_style_routes_through_recipe(self):
        ids = R.suno_style_ids()
        self.assertEqual(set(ids), set(MS.style_ids()))
        self.assertTrue(ids)
        for sid in ids:
            out = R.prepare(sid, sheet(), CLIENT)
            self.assertFalse(out["exempt"])
            self.assertEqual(R.check_style_text(out["style"]), [])
            # U15d: the style text is built from music/<style>.json, so it
            # starts from the DATA's base prompt and carries the delivery map
            # (the old startswith(MS.style_prompt) contract put the map last
            # and the lead before it; the data order is base, lead, map).
            self.assertTrue(out["style"].startswith(R.base_prompt(sid)), out["style"][:80])
            self.assertIn("The lead SPEAKS the lines tagged Spoken", out["style"])
            self.assertLessEqual(len(out["style"]), 1000)
            self.assertEqual(R.check_negatives(out["negative_tags"], sid), [])
            self.assertNotIn("spoken word", out["negative_tags"])

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

    def test_sheet_rules(self):
        late = sheet()
        late[0]["tag"] = "Verse"                      # spoken outside Intro/Outro
        bad = ((sheet(repeats=1), "repeated"), (sheet(hook=["Buy now and save big"]), "client's own"),
               (sheet(vocalise=False), "vocalise"), (late, "only allowed"),
               ([{"tag": "Hook", "delivery": "sung", "lines": HOOK}] + sheet()[1:], "may not open"))
        for b_, why in bad:
            errs = R.check_lyric_sheet(b_, CLIENT)
            self.assertTrue(any(why in e for e in errs), (why, errs))
            with self.assertRaises(R.RecipeError):
                R.prepare("soul-ballad", b_, CLIENT)
        self.assertEqual(R.check_lyric_sheet(sheet(), CLIENT, 58), [])   # the BSW shape passes at 58 s
        long_ = sheet()
        long_[1]["lines"] = ["la la la la la la la la"] * 30
        self.assertTrue(any("budget" in e for e in R.check_lyric_sheet(long_, CLIENT, 58)))

    def test_style_text_rules(self):
        raw = MS.style_prompt("soul-ballad")
        self.assertTrue(R.check_style_text(raw))                       # no band wording
        good = R.style_text("soul-ballad")
        self.assertEqual(R.check_style_text(good), [])
        self.assertTrue(R.check_style_text(good + " Spoken lines are spoken."))
        self.assertTrue(R.check_style_text("x" * 1001 + " the full band keeps playing"))

    def test_negatives_and_request(self):
        self.assertEqual(R.check_negatives(R.negative_tags("soul-ballad")), [])
        self.assertTrue(R.check_negatives("rap, choir, reverb, echo, spoken word"))
        self.assertTrue(R.check_negatives("rap"))                      # dry rule missing
        self.assertNotIn("rap", R.negative_tags("rnb-flow"))           # the rap style keeps its rap
        req = R.build_request("soul-ballad", sheet(), CLIENT, "T", 58)
        self.assertEqual((req["model"], req["custom_mode"], req["style_weight"], req["variety"],
                          req["weirdness_constraint"], req["vocal_gender"], req["duration"]),
                         ("V6", True, 0.75, 0, 0.3, "f", 58))
        self.assertIn("band dropout", req["negative_tags"])
        self.assertEqual(R.parse_lyrics(req["lyrics"]), sheet())

    def test_syllables(self):
        self.assertEqual(R.syllables("I am not sma-a-all"), 4)
        self.assertEqual(R.syllables("One seed of truth made me stro-o-ong"), 7)

    def test_sheet_roundtrip(self):
        s = sheet()
        self.assertEqual(R.parse_lyrics(R.render_lyrics(s)), s)

    def test_request_seam_blocks_bypass(self):
        import music_director as MD
        raw = MS.style_prompt("rnb-flow")
        with self.assertRaises(R.RecipeError):          # raw style, no recipe
            MD.build_generate_request("la la", raw, "T")
        with self.assertRaises(R.RecipeError):          # recipe id, no band wording
            MD.build_generate_request("la la", raw, "T", style_id="rnb-flow",
                                      client_text=CLIENT)
        R.guard_request(raw, "la la", "velvet_voiceover")     # exempt id passes

    def test_request_seam_accepts_recipe_output(self):
        import music_director as MD
        if not MD.workcopy_paths()["models"].is_file():
            self.skipTest("68-kie-audio catalog not in this checkout")
        out = R.prepare("rnb-flow", sheet(), CLIENT)
        out["style"] = out["style"]
        req = MD.build_generate_request(out["lyrics"], out["style"], "T",
                                        style_id="rnb-flow", client_text=CLIENT)
        self.assertTrue(req["input"]["style"].startswith(out["style"]))  # I5 appends ending words

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

    def test_spk001_take_bands(self):
        # spoken 31% / 37% of runtime; sung of voice 69% / 63% (first sung 10%)
        flag = [seg("spoken", 0, 10), seg("sung", 10, 45), seg("spoken", 45, 66),
                seg("sung", 66, 100)]
        r = R.score_take({"segments": flag})
        self.assertEqual(r["verdict"], "FLAG", r)
        redo = [seg("spoken", 0, 10), seg("sung", 10, 45), seg("spoken", 45, 72),
                seg("sung", 72, 100)]
        self.assertEqual(R.score_take({"segments": redo})["verdict"], "FAIL")

    def test_rules_text_is_verbatim(self):
        self.assertEqual(len(R.RULES), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
