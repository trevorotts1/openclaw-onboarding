#!/usr/bin/env python3
"""I3: the planner lists a reference set per main character + one keyframe per
shot, and the cost estimate includes them. Mocked Skill 74, $0.
Run: python3 scripts/core/catalog_calculator/test_image_plan_i3.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "extensions"))
import catalog_calculator as C                       # noqa: E402
import _fixtures as F                                # noqa: E402

SUN = "gpt-image-2-5-sunburst"


def card(**kw):
    env = C.price_card(F.choice(image=SUN, **kw), F.load_catalog(), F.FakeSkill74())
    assert env["state"] == "ok", env
    return env["card"]


c = card()                              # 60 s, one shape, default 1 main character
p = c["image_plan"]
shots = c["shots_per_shape"]            # 60 s / 15 s max shot = 4
assert shots == 4 and p["image_model"] == SUN
assert p["reference_images"] == 6 and p["keyframe_images"] == shots, p
views = {r["view"] for r in p["reference_set"]}
assert views == {"front", "three-quarter", "side", "neutral", "sad-tired",
                 "happy-relieved"}, views
assert [k["shot"] for k in p["keyframes"]] == [1, 2, 3, 4]
img = [li for li in c["line_items"] if li["component"] == "image"][0]
assert img["units"] == 10 and img["credits"] == 60.0, img      # 10 images x 6 credits
assert p["reference_set_usd"] == C.credits_to_usd(36.0)        # the added cost
# two characters, both shapes: 12 refs + 4 keyframes x 2 shapes
c2 = card(shapes=("9:16", "16:9"))
c2 = C.price_card(F.choice(image=SUN, shapes=("9:16", "16:9")) | {"main_characters": ["Ana", "Ben"]},
                  F.load_catalog(), F.FakeSkill74())["card"]
assert c2["image_plan"]["total_images"] == 12 + 8
assert c2["price_usd"] > c["price_usd"]                        # cost went up
# bad character count fails closed
bad = C.price_card(F.choice(image=SUN) | {"main_characters": 0}, F.load_catalog(), F.FakeSkill74())
assert bad["state"] == "error" and not bad["start_paid"], bad
# the choice card shows the added cost
import card_render as R                                          # noqa: E402
text, ok = R.render({"length": "60 seconds"}, F.FakeSkill74())
assert ok and "Images:" in text and "reference pictures" in text, text
print("ALL CHECKS PASS")
