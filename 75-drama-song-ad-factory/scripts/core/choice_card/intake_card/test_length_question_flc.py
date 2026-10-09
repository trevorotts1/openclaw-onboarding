#!/usr/bin/env python3
"""FU-LENGTH-CLIPS: the LENGTH question is a full question with numbered options
that say what the client gets; 3, 5 and 10 minutes name their clips; the recap
is plain; the card price for 3 minutes includes the clips.

Run: python3 core/choice_card/intake_card/test_length_question_flc.py
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
from choice_card.intake_card import intake_card as IC  # noqa: E402
from clip_cutdown import clips_for  # noqa: E402

STEP = IC.render_step([q["id"] for q in IC.QUESTIONS].index("length") + 1)
OPTS = [l for l in STEP.split("\n") if re.match(r"^\d\. ", l)]
FIX = os.path.join(CORE, "catalog_calculator", "extensions", "fixtures", "skill74-responses.json")


class Fake:
    R = json.load(open(FIX, encoding="utf-8"))
    SCALING = ("per-second", "per-1k-chars", "per-image", "per-1m-tokens")

    def __call__(self, model, units):
        spec = self.R.get(model)
        if spec is None:
            return {"state": "fail", "error": {"code": "price_unavailable", "msg": model}}
        unit, tier = spec["unit"], spec["tier_credits"]
        est = round(tier * units, 4) if unit in self.SCALING else round(tier, 4)
        return {"state": "ok", "model_id": model, "warnings": [], "data": {
            "pricing_desc": "%s credits (%s)" % (tier, unit), "credits_min": tier,
            "credits_max": tier, "unit": unit, "units": units, "credits_estimate": est,
            "preflight_required": round(est * 1.3, 2), "preflight_multiplier": 1.3,
            "price_source": "test"}}


class T(unittest.TestCase):
    def test_full_question_with_numbered_options(self):
        self.assertIn("How long do you want your ad to be?", STEP)
        self.assertIn("also come with short clips you can post on social media", STEP)
        self.assertEqual(len(OPTS), 5)
        self.assertIn("Reply with a number", STEP)
        self.assertIn('"recommended"', STEP)

    def test_clip_wording_on_3_5_10_minutes_only(self):
        for line, mins in zip(OPTS[2:], ("3", "5", "10")):
            self.assertIn(mins + " minutes", line)
            self.assertIn("60s and 90s clips", line)
            self.assertIn("Plus a 60-second clip and a 90-second clip", line)
        for line in OPTS[:2]:
            self.assertNotIn("clip", line)

    def test_card_wording_matches_what_the_code_cuts(self):
        for line, secs in zip(OPTS, (60, 90, 180, 300, 600)):
            self.assertEqual("clip" in line, bool(clips_for(secs)), line)

    def test_recap_is_plain(self):
        a = [{"text": "x"}, {"text": IC.QUESTIONS[1]["options"][2][0]}] + [{"text": "x"}] * (len(IC.QUESTIONS) - 2)
        self.assertIn("2. Length: 3 minutes + 60s and 90s clips", IC.render_recap(a))

    def test_three_minute_price_includes_clips(self):
        from catalog_calculator import card_render as CR
        text, ok = CR.render({"length": "3 minutes"}, Fake())
        row = [l for l in text.splitlines() if l.strip().startswith("Clips:")][0]
        self.assertIn("60-second and 90-second clips", row)
        self.assertIn("included in the price", row)
        self.assertIn("$0.00", row)
        self.assertTrue(ok and "Total:" in text)
        self.assertIn("not offered", CR.render({"length": "90 seconds"}, Fake())[0].split("Clips:")[1].split("\n")[0])


if __name__ == "__main__":
    unittest.main()
