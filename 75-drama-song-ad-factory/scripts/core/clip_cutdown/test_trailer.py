#!/usr/bin/env python3
"""W1-method-trailer-U1: method trailers + the offer ad clips (SPEC C5, F10/F19).

Fixture only: a 180 s timeline (a line every 5 s, nine story beats) and the
blueprint that matches it. No media is rendered, no ffmpeg is spawned, no
network is touched -- except one local ``ffmpeg -filters`` probe and one
injected governor spy in the render test.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/clip_cutdown/test_trailer.py
"""
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from clip_cutdown import (  # noqa: E402
    ClipCutdownError, ad_clip, plan_clips, trailer,
)

SHOW = {"name": "Carry It, Sis", "episode": "Episode 4",
        "channel": "youtube.com/@carryitsis",
        "destination": "youtube.com/@carryitsis"}
OFFER = {"link": "https://example.test/book", "cta": "Book now",
         "name": "The Support Circle"}

LINE_S, LINE_LEN, LINES = 5.0, 4.5, 36
HOOK_LINES = (24, 26)          # the sung hook inside SB-07
FIRST_SUNG_INDEX = 11          # 55 s: where the ERM cue says singing starts


def _lines():
    out = []
    for i in range(LINES):
        s = LINE_S * i
        out.append({"line_id": "L%02d" % i, "start_s": s, "end_s": s + LINE_LEN,
                    "beat": "SB-%02d" % (i // 4 + 1), "hook": i in HOOK_LINES})
    return out


def _beats():
    return [
        {"story_beat_id": "SB-01", "start_s": 0, "end_s": 19.5,
         "music_cue_ids": ["BASELINE"], "character_state_before_after": "before",
         "trailer_value": "she is always on and never asks",
         "viewer_understanding": "a woman who carries everyone"},
        {"story_beat_id": "SB-02", "start_s": 20, "end_s": 39.5,
         "music_cue_ids": ["PAIN_BUILD"], "character_state_before_after": "before",
         "trailer_value": "one more demand lands on her"},
        {"story_beat_id": "SB-03", "start_s": 40, "end_s": 59.5,
         "music_cue_ids": ["ERM_DROP"], "character_state_before_after": "before",
         "trailer_value": "she deletes her own message asking for help"},
        {"story_beat_id": "SB-04", "start_s": 60, "end_s": 79.5,
         "music_cue_ids": ["PAIN_DEEPEN"],
         "trailer_value": "she keeps hiding it"},
        {"story_beat_id": "SB-05", "start_s": 80, "end_s": 99.5,
         "music_cue_ids": ["HERO_SHIFT"], "character_state_before_after": "neutral",
         "trailer_value": "the invitation arrives"},
        {"story_beat_id": "SB-06", "start_s": 100, "end_s": 119.5,
         "music_cue_ids": ["BREAKTHROUGH"], "character_state_before_after": "after",
         "trailer_value": "she asks and somebody answers"},
        {"story_beat_id": "SB-07", "start_s": 120, "end_s": 139.5,
         "music_cue_ids": ["SOLUTION_HOOK"], "character_state_before_after": "after",
         "trailer_value": "the hook lands on her new state"},
        {"story_beat_id": "SB-08", "start_s": 140, "end_s": 159.5,
         "music_cue_ids": ["COMMERCIAL_CONTINUATION"],
         "trailer_value": "the offer"},
        {"story_beat_id": "SB-09", "start_s": 160, "end_s": 174.5,
         "music_cue_ids": [],
         "trailer_value": "a complication only the longer cut can carry"},
    ]


def timeline(method=True, purpose="campaign", show=True, offer=True):
    tl = {"schema_version": "blackceo.timeline/v1", "fps": 30,
          "width": 1080, "height": 1920, "duration_s": 178.0,
          "lines": _lines(), "endcard_start_s": 175.0}
    if method:
        tl["method"] = {"purpose": purpose, "chosen_length_s": 180}
        tl["blueprint"] = blueprint()
    if show:
        tl["show"] = dict(SHOW)
    if offer:
        tl["offer"] = dict(OFFER)
    return tl


def blueprint(drop=(), **overrides):
    bp = {"series_name": "Carry It, Sis",
          "story_beats": [b for b in _beats() if b["story_beat_id"] not in drop],
          "music_cues": [{"music_cue_id": "ERM_DROP", "story_beat_id": "SB-03",
                          "start_s": LINE_S * FIRST_SUNG_INDEX, "vocal_status": "sung",
                          "lyric_or_dialogue": "Who is holding me?"}],
          "commercial_intent": {"primary_action": "Book now"}}
    bp.update(overrides)
    return bp


def source_pieces(plan):
    return [p for p in plan["pieces"] if p["piece"] != trailer.END_CARD]


class Trailers(unittest.TestCase):
    def test_two_plans_inside_the_length_budget(self):
        plans = trailer.plan_trailers(timeline(), blueprint(), 180, SHOW)
        self.assertEqual([p["clip_length_s"] for p in plans], [60, 90])
        for plan, budget in zip(plans, (58, 88)):
            self.assertLessEqual(plan["duration_s"], budget)
            self.assertGreater(plan["duration_s"], 20)
        self.assertNotEqual({(p["source_in"], p["source_out"])
                             for p in source_pieces(plans[0])},
                            {(p["source_in"], p["source_out"])
                             for p in source_pieces(plans[1])})

    def test_sequence_ERM_before_hero_hook_after_breakthrough_end_card(self):
        for plan in trailer.plan_trailers(timeline(), blueprint(), 180, SHOW):
            pieces = source_pieces(plan)
            names = [p["piece"] for p in pieces]
            self.assertEqual(names[0], "opening")
            self.assertLess(names.index("erm"), names.index("hero"))
            if "hook" in names:
                self.assertIn("breakthrough", names)
                self.assertLess(names.index("breakthrough"), names.index("hook"))
            self.assertEqual(plan["pieces"][-1]["piece"], trailer.END_CARD)
            self.assertGreaterEqual(plan["end_card"]["duration_s"], 3.0)
            self.assertIn("Watch the full episode on youtube.com/@carryitsis",
                          plan["end_card"]["lines"])
            self.assertEqual(plan["destination"], "youtube.com/@carryitsis")
            self.assertTrue(plan["viewing_reason"])
            self.assertIn("master_s", plan["spoiler_boundary"])
            for p in pieces:
                for key in ("source_in", "source_out", "trailer_in", "trailer_out"):
                    self.assertIsInstance(p[key], float)
                self.assertLess(p["trailer_in"], p["trailer_out"])

    def test_erm_range_carries_the_first_sung_line(self):
        sung = timeline()["lines"][FIRST_SUNG_INDEX]
        for plan in trailer.plan_trailers(timeline(), blueprint(), 180, SHOW):
            erm = next(p for p in source_pieces(plan) if p["piece"] == "erm")
            self.assertLessEqual(erm["source_in"], sung["start_s"])
            self.assertGreaterEqual(erm["source_out"], sung["end_s"])

    def test_60_and_90_differ_in_at_least_one_source_range(self):
        short, long_ = trailer.plan_trailers(timeline(), blueprint(), 180, SHOW)
        short_ranges = {(p["source_in"], p["source_out"]) for p in source_pieces(short)}
        long_ranges = {(p["source_in"], p["source_out"]) for p in source_pieces(long_)}
        self.assertNotEqual(short_ranges, long_ranges)
        self.assertTrue(long_ranges - short_ranges,
                        "the 90 s cut repeats the 60 s cut exactly: %r" % (short_ranges,))
        self.assertLessEqual(short["duration_s"], 58)
        self.assertLessEqual(long_["duration_s"], 88)
        self.assertGreater(long_["duration_s"], short["duration_s"])

    def test_no_breakthrough_omits_the_hook_and_records_it(self):
        plans = trailer.plan_trailers(timeline(), blueprint(drop=("SB-06",)),
                                      180, SHOW)
        for plan in plans:
            names = [p["piece"] for p in source_pieces(plan)]
            self.assertNotIn("hook", names)
            hook = [o for o in plan["omitted"] if o["piece"] == "hook"]
            self.assertEqual(len(hook), 1)
            self.assertIn("pain-led teaser", hook[0]["reason"])

    def test_no_destination_fails_closed(self):
        tl = timeline(show=False)
        with self.assertRaises(ClipCutdownError) as got:
            trailer.plan_trailers(tl, blueprint(), 180, None)
        self.assertIn("TRAILER_NO_DESTINATION", str(got.exception))

    def test_no_viewing_reason_fails_closed(self):
        bp = blueprint()
        for beat in bp["story_beats"]:
            beat.pop("trailer_value", None)
            beat.pop("viewer_understanding", None)
        with self.assertRaises(ClipCutdownError) as got:
            trailer.plan_trailers(timeline(), bp, 180, SHOW)
        self.assertIn("TRAILER_NO_VIEWING_REASON", str(got.exception))

    def test_hook_before_its_breakthrough_is_refused(self):
        bp = blueprint()
        # the hook is cut from lines that sit before the turn (bad blueprint)
        next(b for b in bp["story_beats"]
             if b["story_beat_id"] == "SB-07")["story_beat_id"] = "SB-02"
        with self.assertRaises(ClipCutdownError) as got:
            trailer.plan_trailers(timeline(), bp, 180, SHOW)
        self.assertIn("TRAILER_HOOK_UNEARNED", str(got.exception))

    def test_before_state_after_the_breakthrough_breaks_the_lock(self):
        bp = blueprint()
        next(b for b in bp["story_beats"]
             if b["story_beat_id"] == "SB-07")["character_state_before_after"] = "before"
        with self.assertRaises(ClipCutdownError) as got:
            trailer.plan_trailers(timeline(), bp, 180, SHOW)
        self.assertIn("TRANSFORMATION_LOCK_BROKEN", str(got.exception))

    def test_a_flashback_tag_with_a_reason_keeps_the_before_state(self):
        bp = blueprint()
        beat = next(b for b in bp["story_beats"] if b["story_beat_id"] == "SB-07")
        beat["character_state_before_after"] = "before"
        beat["flashback"] = True
        beat["reason"] = "she remembers the cape"
        plans = trailer.plan_trailers(timeline(), bp, 180, SHOW)
        for plan in plans:
            self.assertEqual(plan["transformation_lock"], "OK")

    def test_no_state_records_never_claim_a_pass(self):
        bp = blueprint()
        for beat in bp["story_beats"]:
            beat.pop("character_state_before_after", None)
        for plan in trailer.plan_trailers(timeline(), bp, 180, SHOW):
            self.assertEqual(plan["transformation_lock"], "UNAVAILABLE")


class AdClips(unittest.TestCase):
    def test_complete_arc_end_card_and_offer_destination(self):
        plans = ad_clip.plan_ad_clips(timeline(), blueprint(), 180, OFFER)
        self.assertEqual([p["clip_length_s"] for p in plans], [60, 90])
        for plan, budget in zip(plans, (58, 88)):
            self.assertLessEqual(plan["duration_s"], budget)
            names = [p["piece"] for p in source_pieces(plan)]
            self.assertEqual(names[0], "opening")
            self.assertLess(names.index("breakthrough"), names.index("hook"))
            self.assertEqual(plan["pieces"][-1]["piece"], trailer.END_CARD)
            self.assertEqual(plan["end_card"]["lines"][0], "Book now")
            self.assertIn("https://example.test/book", plan["end_card"]["lines"])
            self.assertEqual(plan["destination"], "https://example.test/book")
            self.assertEqual(plan["offer"]["link"], "https://example.test/book")

    def test_without_an_offer_link_it_fails_closed(self):
        with self.assertRaises(ClipCutdownError) as got:
            ad_clip.plan_ad_clips(timeline(offer=False), blueprint(), 180, None)
        self.assertIn("AD_NO_OFFER_DESTINATION", str(got.exception))

    def test_without_a_breakthrough_the_arc_is_refused(self):
        with self.assertRaises(ClipCutdownError) as got:
            ad_clip.plan_ad_clips(timeline(), blueprint(drop=("SB-06",)), 180, OFFER)
        self.assertIn("AD_ARC_INCOMPLETE", str(got.exception))

    def test_a_before_state_range_after_the_turn_breaks_the_lock(self):
        bp = blueprint()
        next(b for b in bp["story_beats"]
             if b["story_beat_id"] == "SB-07")["character_state_before_after"] = "before"
        with self.assertRaises(ClipCutdownError) as got:
            ad_clip.plan_ad_clips(timeline(), bp, 180, OFFER)
        self.assertIn("TRANSFORMATION_LOCK_BROKEN", str(got.exception))


class Dispatch(unittest.TestCase):
    def test_non_method_timeline_gives_todays_plan(self):
        plans = plan_clips(timeline(method=False), 180)
        self.assertEqual([p["name"] for p in plans], ["clip-60s", "clip-90s"])
        for plan in plans:
            self.assertNotIn("kind", plan)
            self.assertNotIn("pieces", plan)
            self.assertIn("start_s", plan)
            self.assertIn("hooks", plan)

    def test_method_campaign_plan_clips_plans_both_derivatives(self):
        plans = plan_clips(timeline(), 180)
        self.assertEqual([(p["kind"], p["clip_length_s"]) for p in plans],
                         [("trailer", 60), ("trailer", 90), ("ad", 60), ("ad", 90)])

    def test_method_run_that_is_not_a_campaign_keeps_todays_plan(self):
        plans = plan_clips(timeline(purpose="testimonial"), 180)
        self.assertEqual([p["name"] for p in plans], ["clip-60s", "clip-90s"])

    def test_a_60_second_master_owes_no_derivative(self):
        self.assertEqual(trailer.plan_trailers(timeline(), blueprint(), 60, SHOW), [])
        self.assertEqual(ad_clip.plan_ad_clips(timeline(), blueprint(), 60, None), [])


class Render(unittest.TestCase):
    def setUp(self):
        self.plan = trailer.plan_trailers(timeline(), blueprint(), 180, SHOW)[0]

    def test_build_argv_joins_on_crossfades_and_writes_the_card_as_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = os.path.join(tmp, "card.txt")
            font = os.path.join(tmp, "font.ttf")
            for path, text in ((card, "Carry It, Sis\n"), (font, "")):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            argv = trailer.build_argv("master.mp4", self.plan,
                                      os.path.join(tmp, "o.mp4"), card, fontfile=font)
        graph = argv[argv.index("-filter_complex") + 1]
        self.assertIn("xfade=transition=fade:duration=0.300", graph)
        self.assertIn("acrossfade=d=0.300", graph)
        self.assertIn("drawtext=fontfile=" + font, graph)
        self.assertIn("textfile=" + card, graph)
        self.assertIn("expansion=none", graph)
        self.assertIn("tpad=stop_mode=clone:stop_duration=3.000", graph)
        self.assertIn("enable='gte(t,", graph)
        self.assertEqual(argv[argv.index("-map") + 1], "[vout]")
        self.assertIn("aac", argv)
        self.assertIn("+faststart", argv)
        self.assertEqual(argv[argv.index("-pix_fmt") + 1], "yuv420p")   # xfade -> yuv444p otherwise
        offsets = [float(o) for o in re.findall(r"offset=([0-9.]+)", graph)]
        sources = [p for p in self.plan["pieces"] if p["piece"] != trailer.END_CARD]
        self.assertEqual(len(offsets), len(sources) - 1)
        self.assertTrue(offsets and offsets[0] >= 0, offsets)
        self.assertEqual(sorted(offsets), offsets)

    def test_render_runs_through_the_load_governor(self):
        seen, gated = [], []

        class Fake:
            returncode = 0

        def spy(argv, **kw):
            seen.append(argv)
            return Fake()

        def gate(path):
            gated.append(path)
            return {"ok": True}

        real = trailer._LG.run_ffmpeg
        trailer._LG.run_ffmpeg = spy
        try:
            with tempfile.TemporaryDirectory() as out:
                paths = trailer.render("master.mp4", [self.plan], out, audio_gate=gate)
                leftovers = [n for n in os.listdir(out) if n.endswith(".txt")]
        finally:
            trailer._LG.run_ffmpeg = real
        self.assertEqual(len(paths), 1)
        self.assertEqual(len(seen), 1)
        self.assertTrue(paths[0].endswith("trailer-60s.mp4"))
        self.assertEqual(gated, paths)
        self.assertEqual(leftovers, [])          # the card text never lands in the delivery

    def test_the_end_card_holds_the_profile_cta_hold(self):
        self.assertGreaterEqual(trailer.end_card_s(), 3.0)
        self.assertGreaterEqual(self.plan["end_card"]["duration_s"],
                                trailer.CTA_HOLD_MIN_SECONDS)


if __name__ == "__main__":
    unittest.main()
