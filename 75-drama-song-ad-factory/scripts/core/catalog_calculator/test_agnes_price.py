#!/usr/bin/env python3
"""W1-agnes-core-U7 (SPEC A9) — the Agnes card's money lines.

Proves, in order:
  1. a card without ``agnes == "yes"`` renders byte for byte as it did on
     origin/main f825bbff2 (pinned golden) and never enters the Agnes path;
  2. a 90 s Agnes card prices ONLY the song and the lip-sync close-ups
     through the injected Skill 74 ``price_fn`` — video and images are never
     asked for — shows 90 Agnes seconds, and no Agnes line carries a figure;
  3. a price_fn that fails says "Price unavailable" (fail closed);
  4. ``quote`` returns the Agnes total for an Agnes card and None without a
     price_fn;
  5. both shapes double the Agnes video time.

No network, no spend: the price callable is a fixture backed by the shipped
Skill 74 answers (extensions/fixtures/skill74-responses.json).

Run: python3 75-drama-song-ad-factory/scripts/core/catalog_calculator/test_agnes_price.py
stdlib only, no pytest: the repo's empty-home QC sweep runs every test file
under a bare ``python3`` with an empty HOME, where pytest is not installed.
"""
from __future__ import annotations

import contextlib
import math
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
# realpath: on macOS /tmp is a symlink to /private/tmp, so sys.path (python
# invocation) and abspath HERE can disagree by the symlink, leaving the
# script's own dir on sys.path and letting catalog_calculator.py shadow the
# namespace package off CORE (same guard as test_card_render.py).
CORE = os.path.realpath(CORE)
HERE = os.path.realpath(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)
for stale in [p for p in sys.path
              if p.rstrip(os.sep) == HERE or os.path.realpath(p) == HERE]:
    sys.path.remove(stale)

from catalog_calculator import agnes_price, card_render     # noqa: E402
from catalog_calculator.extensions import _fixtures         # noqa: E402

SCALING = ("per-second", "per-1k-chars", "per-image", "per-1m-tokens")


def approx(a, b, abs_tol=0.01):
    """pytest.approx(a, abs=0.01), stdlib edition."""
    return abs(a - b) <= abs_tol


#: What card_render printed for card {} with this fixture on origin/main
#: f825bbff2, captured before this unit existed: a non-Agnes card must not
#: move a byte (BUILD-PLAN W1-agnes-core-U7 acceptance).
GOLDEN_PLAIN_CARD = (
    "  Length:      60 seconds   $2.40\n"
    "  Shape:       9:16   $0.22\n"
    "  Style:       Lifelike 3D   $0.22\n"
    "  Music:       Soul Ballad   $0.06\n"
    "  Voice:       All Suno   $0.06\n"
    "  Clips:       not offered (60/90-second lengths only)   $0.00\n"
    "  Video model: MiniMax H3 768P (RECOMMENDED)   $2.40\n"
    "  Images:      7 character reference pictures + 4 shot pictures "
    "(added $0.14 for the reference pictures, included in the total)\n"
    "  Storyboard:  8 storyboard pictures (cap 120 from configuration; "
    "separate from the 4 video shots above)\n"
    "\n"
    "  Total:       $2.68 + $0.54 retake allowance (20%) = $3.22")

#: quote(1, "90 seconds") on origin/main f825bbff2 (table rates, no adapter).
GOLDEN_QUOTE_90 = 4.7


class FakePrice:
    """Fixture price_fn: Skill 74's own answers, recording every model asked."""

    def __init__(self):
        self.calls = []
        self.responses = _fixtures.load_responses()

    def __call__(self, model, units):
        self.calls.append((model, units))
        spec = self.responses.get(model)
        if spec is None:
            return {"state": "fail",
                    "error": {"code": "price_unavailable", "msg": model}}
        unit, tier = spec["unit"], spec["tier_credits"]
        est = round(tier * units, 4) if unit in SCALING else round(tier, 4)
        return {"state": "ok", "model_id": model, "warnings": [], "data": {
            "pricing_desc": "%s credits (%s)" % (tier, unit),
            "credits_min": tier, "credits_max": tier, "unit": unit,
            "units": units, "credits_estimate": est,
            "preflight_required": None if est is None else round(est * 1.3, 2),
            "preflight_multiplier": 1.3,
            "price_source": spec.get("source", "test")}}


@contextlib.contextmanager
def plan():
    """``agnes_plan`` (unit W1-agnes-core-U4: 10 s windows x shapes).

    That unit's module is not on this lane's base yet, so the test stands in
    its exact contract when it cannot be imported; on a branch that carries
    U4 the real module answers and every assertion below runs against it.
    """
    try:
        import agnes_plan
        yield agnes_plan
        return
    except ImportError:
        pass
    stub = types.ModuleType("agnes_plan")

    def segments(delivered_s):
        return [None] * int(math.ceil(delivered_s / 10.0))

    def need(segs, shapes):
        video_seconds = len(segs) * 10 * len(shapes)
        return {"video_seconds": video_seconds,
                "images": video_seconds // 10,
                "allowance_seconds": video_seconds}
    stub.segments = segments
    stub.need = need
    monkeypatched = sys.modules.get("agnes_plan")
    sys.modules["agnes_plan"] = stub
    try:
        yield stub
    finally:
        if monkeypatched is None:
            del sys.modules["agnes_plan"]
        else:
            sys.modules["agnes_plan"] = monkeypatched


@contextlib.contextmanager
def swapped(obj, name, value):
    """pytest's monkeypatch.setattr, stdlib edition."""
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def _row(text, label):
    """The rendered row that starts with ``label:``."""
    return next(ln for ln in text.splitlines() if ln.strip().startswith(label + ":"))


class AgnesPriceTests(unittest.TestCase):

    # --------------------------------------------------- 1. non-Agnes card
    def test_non_aggnes_card_is_byte_identical_to_main(self):
        fake = FakePrice()
        text, priced = card_render.render({}, fake)
        self.assertEqual(text, GOLDEN_PLAIN_CARD)
        self.assertIs(priced, True)
        # the Skill 74 questions the card asked on the base, unchanged
        self.assertEqual(fake.calls, [("ai-music-api/generate", 1),
                                      ("google/imagen4-fast", 11)])

        def never(card, price_fn):          # the Agnes path must not be entered
            raise AssertionError("agnes_price.envelope used on a non-Agnes card")
        with swapped(agnes_price, "envelope", never):
            again, priced_again = card_render.render({}, fake)
            self.assertEqual((again, priced_again), (GOLDEN_PLAIN_CARD, True))
        self.assertEqual(card_render.quote(1, "90 seconds"), GOLDEN_QUOTE_90)

    # ------------------------------------------------------- 2. Agnes card
    def test_aggnes_90_prices_music_and_lipsync_only(self):
        fake = FakePrice()
        card = {"length": "90 seconds", "shape": "9:16", "agnes": "yes"}
        with plan():
            text, priced = card_render.render(card, fake)
            self.assertIs(priced, True)

            asked = [m for m, _ in fake.calls]
            self.assertEqual(sorted(set(asked)),
                             ["ai-music-api/generate", "kling/ai-avatar-standard"],
                             asked)
            self.assertNotIn("google/imagen4-fast", asked)      # pictures are Agnes work
            self.assertNotIn("minimax-h3/image-to-video", asked)  # video is Agnes work

            self.assertIn("Agnes video time: about 90 of your 500 seconds today", text)
            for label in ("Length", "Shape", "Video model"):
                row = _row(text, label)
                self.assertIn("included in your Agnes plan", row, row)
                self.assertNotIn("$", row, row)
            for label in ("Music", "Voice", "Style"):
                self.assertIn("$", _row(text, label), _row(text, label))

            env = agnes_price.envelope(card, fake)
            self.assertEqual(env["state"], "ok")
            priced_card = env["card"]
            self.assertEqual(priced_card["agnes_seconds"], 90)
            by_component = {li["component"]: li for li in priced_card["line_items"]}
            self.assertEqual(by_component["video"]["included"], agnes_price.INCLUDED)
            self.assertIsNone(by_component["video"]["usd"])
            self.assertEqual(by_component["video"]["agnes_seconds"], 90)
            self.assertEqual(by_component["image"]["included"], agnes_price.INCLUDED)
            self.assertIsNone(by_component["image"]["usd"])
            self.assertEqual(by_component["image"]["agnes_seconds"], 90)
            self.assertGreater(by_component["music"]["usd"], 0)
            self.assertGreater(by_component["lip_sync"]["usd"], 0)
            # 90 s ad -> 12 clips of the planned 60 s ceiling (lipsync_clips.budget)
            self.assertEqual(priced_card["lip_sync"], {
                "model_id": "kling/ai-avatar-standard", "seconds": 60, "lines": 12,
                "seconds_per_shape": 60, "lines_per_shape": 12, "shape_count": 1})
            # the total is the song plus the close-ups, nothing else
            self.assertTrue(approx(
                priced_card["price_usd"],
                by_component["music"]["usd"] + by_component["lip_sync"]["usd"]))
            self.assertTrue(approx(
                priced_card["spending_limit_usd"],
                priced_card["price_usd"] + priced_card["retake_allowance_usd"]))

    def test_aggnes_both_shapes_doubles_video_time(self):
        fake = FakePrice()
        card = {"length": "90 seconds", "shape": "both", "agnes": "yes"}
        with plan():
            text, priced = card_render.render(card, fake)
            self.assertIs(priced, True)
            self.assertIn("Agnes video time: about 180 of your 500 seconds today", text)
            env = agnes_price.envelope(card, fake)
            self.assertEqual(env["card"]["agnes_seconds"], 180)
            # both shapes run lip-sync
            self.assertEqual(env["card"]["lip_sync"]["seconds"], 120)

    # ----------------------------------------------- 3. price fails closed
    def test_failing_price_fn_says_price_unavailable(self):
        card = {"length": "90 seconds", "shape": "9:16", "agnes": "yes"}

        def boom(model, units):
            raise RuntimeError("skill74 runner is down")
        with plan():
            text, priced = card_render.render(card, boom)
            self.assertIs(priced, False)
            self.assertIn("Price unavailable", text)

            def refuses(model, units):
                return {"state": "fail",
                        "error": {"code": "price_unavailable", "msg": model}}
            text2, priced2 = card_render.render(card, refuses)
            self.assertIs(priced2, False)
            self.assertIn("Price unavailable", text2)
            # the plan lines are still shown: they are not a price
            self.assertIn("included in your Agnes plan", text2)
            self.assertIn("Agnes video time: about 90 of your 500 seconds today", text2)

    # ------------------------------------------------------------- 4. quote
    def test_quote_returns_the_aggnes_total(self):
        fake = FakePrice()
        with plan():
            total = card_render.quote(1, "90 seconds", agnes=True, price_fn=fake)
            env = agnes_price.envelope({"length": "90 seconds", "agnes": "yes"}, fake)
            self.assertEqual(total, env["card"]["spending_limit_usd"])
            self.assertGreater(total, 0)
            # no Skill 74, no total: never a made-up number
            self.assertIsNone(card_render.quote(1, "90 seconds", agnes=True))
            self.assertEqual(card_render.quote(1, "90 seconds"), GOLDEN_QUOTE_90)

    # --------------------------------- 5. the door only takes Agnes cards
    def test_envelope_refuses_a_card_without_agnes_yes(self):
        env = agnes_price.envelope({"length": "90 seconds"}, FakePrice())
        self.assertEqual(env["state"], "error")
        self.assertIsNone(env["card"])
        self.assertEqual(env["reasons"], ["AGNES_NOT_CHOSEN"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
