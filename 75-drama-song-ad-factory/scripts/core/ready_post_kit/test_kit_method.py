#!/usr/bin/env python3
"""W2-wiring-U6 tests: the Ready-to-Post kit's method destinations (F12).

Done-when cases (stdlib only, empty HOME, no network, no paid calls):

  1. ``resolve_link`` returns TWO distinct records -- the offer/checkout link
     and the episode/channel link -- and the episode record is never filled
     in from the offer side (SPEC C8);
  2. a campaign run gets a trailer caption per platform and NO trailer caption
     ever carries the checkout link;
  3. the platform blocks are YouTube, Instagram, TikTok, Facebook, LinkedIn
     and Pinterest, and there is no X/Twitter block anywhere;
  4. every delivered file lists the GHL destinations it provably fits through
     ``platform_fit.fits``, and a destination that refuses it only for length
     points at the 60 s / 90 s cut;
  5. every block cites its ``platform_fit`` row and the date that row was read
     (TikTok, which the GHL table does not research, says so plainly);
  6. a lesson run with no next-step link does NOT refuse KIT_NO_LINK -- it
     says "no link needed";
  7. everything still passes the copy audit and the 12 pt floor.

Only the local ffprobe read is faked: the researched spec table, its rows,
their read dates and ``platform_fit.fits`` are the real ones on this tree.

Run: python3 -m pytest -q scripts/core/ready_post_kit/test_kit_method.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[0]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from ready_post_kit import ready_post_kit as R                     # noqa: E402
from ready_post_kit.test_ready_post_kit import make_run            # noqa: E402

CHECKOUT = "https://example.com/class"
EPISODE = "https://example.com/channel/bake-with-rove"
OFFER = "Book a free class at %s" % CHECKOUT


def page_text(kit):
    """The laid-out page as one string with its wrapping whitespace gone, so a
    sentence that wrapped across two lines is still findable."""
    pages, _sizes = R.layout(kit)
    text = "\n".join(op[3] for page in pages for op in page
                     if op[0] == "text")
    return re.sub(r"\s+", "", text)


def flat(needle):
    return re.sub(r"\s+", "", needle)


def write_method(run, purpose, **extra):
    """The card's purpose record (control/method.json)."""
    control = Path(run) / "control"
    control.mkdir(parents=True, exist_ok=True)
    rec = {"purpose": purpose, "platform": None, "output_types": [],
           "chosen_length_s": 180, "gates": {"A": "planned"}}
    rec.update(extra)
    (control / "method.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


def platform_fit_module():
    """The spec-table module ``ready_post_kit`` actually imports.

    The suite drops skill-tree modules out of ``sys.modules`` before every
    collection (``scripts/conftest.py``), so a module object bound once at
    import time goes stale inside a longer pytest run. Binding it per use
    keeps this test and the kit on the same copy -- the same reason the kit
    itself imports it inside the function.
    """
    import platform_fit.platform_fit as live
    return live


def probe(duration=58.0, width=1080, height=1920, fps=30.0,
          size=8_000_000, container="mp4"):
    """A measured probe dict -- everything ``check``/``fits`` take."""
    return {"path": "file.mp4", "duration_s": duration, "size_bytes": size,
            "container": container, "format_name": "mov,mp4",
            "video_codec": "h264", "audio_codec": "aac",
            "width": width, "height": height, "fps": fps}


def with_probe(p):
    """Patch the one ffprobe read on the module the kit will import; the spec
    table, its rows, their read dates and ``fits`` stay real."""
    return mock.patch.object(platform_fit_module(), "probe_file",
                             lambda *_a, **_k: dict(p))


class TwoDestinations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-meth-")
        self.addCleanup(self.tmp.cleanup)

    def test_offer_and_episode_are_two_distinct_records(self):
        run, deliv = make_run(self.tmp.name, offer=OFFER)
        brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
        brief["channel"] = "Watch it on %s" % EPISODE
        (run / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
        links = R.resolve_link(json.loads((run / "brief.json").read_text()),
                               {"dir": str(deliv)})
        self.assertEqual(links["offer"], CHECKOUT)
        self.assertEqual(links["episode"], EPISODE)
        self.assertNotEqual(links["offer"], links["episode"])

    def test_no_episode_source_leaves_the_episode_record_none(self):
        # the offer record must never be copied across as the trailer one
        run, deliv = make_run(self.tmp.name, offer=OFFER)
        links = R.resolve_link(json.loads((run / "brief.json").read_text()),
                               {"dir": str(deliv)})
        self.assertEqual(links["offer"], CHECKOUT)
        self.assertIsNone(links["episode"])

    def test_an_episode_link_that_is_the_checkout_url_is_dropped(self):
        run, deliv = make_run(self.tmp.name, offer=OFFER,
                              link=CHECKOUT)
        brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
        brief["episode_url"] = CHECKOUT
        (run / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
        links = R.resolve_link(brief, {"dir": str(deliv)})
        self.assertEqual(links["offer"], CHECKOUT)
        self.assertIsNone(links["episode"])

    def test_the_delivery_readme_episode_line_supplies_the_episode_link(self):
        run, deliv = make_run(self.tmp.name, offer=OFFER)
        (deliv / "README.md").write_text(
            "Banner link (all ads): %s\nEpisode link (trailers): %s\n"
            % (CHECKOUT, EPISODE), encoding="utf-8")
        links = R.resolve_link(json.loads((run / "brief.json").read_text()),
                               {"dir": str(deliv)})
        self.assertEqual(links["offer"], CHECKOUT)
        self.assertEqual(links["episode"], EPISODE)


class TrailerCaptions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-trail-")
        self.addCleanup(self.tmp.cleanup)

    def _campaign(self, **kw):
        run, deliv = make_run(self.tmp.name, offer=OFFER, **kw)
        brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
        brief["channel"] = "Watch it on %s" % EPISODE
        (run / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
        write_method(run, "campaign")
        return run, deliv

    def test_a_campaign_run_gets_a_trailer_caption_on_every_block(self):
        run, deliv = self._campaign()
        kit = R.prepare(str(run), str(deliv))
        self.assertEqual(kit["links"]["offer"], CHECKOUT)
        self.assertEqual(kit["links"]["episode"], EPISODE)
        self.assertEqual(set(kit["captions"]), {
            "youtube", "instagram", "tiktok", "facebook", "linkedin",
            "pinterest"})
        for key, block in kit["captions"].items():
            self.assertIn("trailer_caption", block, key)
            self.assertIn(EPISODE, block["trailer_caption"], key)
            self.assertNotIn(CHECKOUT, block["trailer_caption"],
                             "%s trailer caption carries the checkout link"
                             % key)

    def test_a_non_campaign_run_has_no_trailer_caption(self):
        run, deliv = make_run(self.tmp.name, offer=OFFER)
        kit = R.prepare(str(run), str(deliv))
        for block in kit["captions"].values():
            self.assertNotIn("trailer_caption", block)

    def test_an_offer_derived_hook_is_dropped_from_the_trailer_caption(self):
        # the script opens with nothing long enough, so hook falls back to the
        # offer sentence -- which carries the checkout url. Fail closed.
        run, deliv = make_run(self.tmp.name, offer=OFFER,
                              length_text="180 seconds")
        (run / "creative" / "script.json").write_text(json.dumps({
            "title": "The Last Cookie",
            "story": [["Act 1", ["short"]]],
            "sheet": [{"tag": "verse", "lines": ["nope"]}],
        }), encoding="utf-8")
        write_method(run, "campaign")
        kit = R.prepare(str(run), str(deliv))
        script = json.loads((run / "creative" / "script.json").read_text())
        # the fallback happened: no usable opening line, so hook IS the offer
        self.assertEqual(R.hook_line(script, OFFER), OFFER)
        seen = 0
        for key, block in kit["captions"].items():
            cap = block.get("trailer_caption")
            if cap is None:
                continue
            seen += 1
            self.assertNotIn(CHECKOUT, cap, key)
            self.assertNotIn("Book a free class", cap, key)
            # no episode link on file, so the caption still points at the
            # channel in words -- and carries no URL at all
            self.assertIn("Watch the full episode on your channel.", cap, key)
            self.assertNotIn("http", cap, key)
        self.assertTrue(seen, "no trailer caption on a campaign run")

    def test_a_trailer_caption_without_an_episode_link_carries_no_url(self):
        run, deliv = make_run(self.tmp.name, offer=OFFER)
        write_method(run, "campaign")
        kit = R.prepare(str(run), str(deliv))
        self.assertIsNone(kit["links"]["episode"])
        for key, block in kit["captions"].items():
            cap = block.get("trailer_caption")
            if cap is None:
                continue
            self.assertNotIn(CHECKOUT, cap, key)
            self.assertIn("Watch the full episode on your channel.", cap, key)


class PlatformBlocks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-blocks-")
        self.addCleanup(self.tmp.cleanup)
        self.run, self.deliv = make_run(self.tmp.name, offer=OFFER)
        self.kit = R.prepare(str(self.run), str(self.deliv))

    def test_the_six_blocks_and_no_x_or_twitter_block(self):
        self.assertEqual(set(self.kit["captions"]), {
            "youtube", "instagram", "tiktok", "facebook", "linkedin",
            "pinterest"})
        self.assertEqual(
            {k for k in self.kit["hashtags"]
             if k in ("linkedin", "pinterest")},
            {"linkedin", "pinterest"})
        blob = json.dumps(self.kit).lower()
        self.assertNotIn("twitter", blob)
        self.assertNotIn('"x"', blob)

    def test_linkedin_and_pinterest_carry_a_caption_a_note_and_tags(self):
        for key in ("linkedin", "pinterest"):
            block = self.kit["captions"][key]
            self.assertIn(CHECKOUT, block["caption"])
            self.assertTrue(block["note"].strip())
            self.assertTrue(self.kit["hashtags"][key])

    def test_every_block_cites_its_platform_fit_row_and_read_date(self):
        rows = platform_fit_module().load_specs()
        read = next(r["read_utc"] for r in rows
                    if r["placement"] == "instagram_reel")
        for key, block in self.kit["captions"].items():
            line = block["platform_spec"]
            self.assertIn("read ", line, key)
            if key == "tiktok":
                self.assertIn("No platform_fit row", line)
            else:
                self.assertIn(read, line)
                self.assertIn("GHL Social Planner", line)
        # the real row, not a restated one
        self.assertEqual(
            R.spec_line("linkedin", rows),
            "LinkedIn video, profile or Company Page (GHL Social Planner) "
            "-- read %s" % read)

    def test_x_twitter_row_is_never_offered(self):
        rows = platform_fit_module().load_specs()
        x = [r for r in rows if r["placement"] == "x_twitter"]
        self.assertEqual(x[0]["availability"], "NOT_AVAILABLE")
        for block in self.kit["captions"].values():
            self.assertNotIn("X / Twitter", block.get("platform_spec", ""))


class PerFileFit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-fit-")
        self.addCleanup(self.tmp.cleanup)
        self.run, self.deliv = make_run(self.tmp.name, offer=OFFER)
        write_method(self.run, "campaign")
        self.rows = platform_fit_module().load_specs()

    def _fits(self, p):
        with with_probe(p):
            kit = R.prepare(str(self.run), str(self.deliv))
        return {r["file"]: r for r in kit["platform_fit"]}

    def test_a_58s_vertical_file_lists_the_destinations_it_fits(self):
        rows = self._fits(probe())
        one = rows["ad-9x16.mp4"]
        self.assertIn("Instagram Story (GHL Social Planner)", one["fits"])
        self.assertIn("YouTube Short (GHL Social Planner)", one["fits"])
        # 16:9-only destination: a vertical file does not claim it
        self.assertNotIn("YouTube video (GHL Social Planner)", one["fits"])
        self.assertEqual(one["too_long"], [])

    def test_a_longer_destination_points_at_the_60s_and_90s_cut(self):
        rows = self._fits(probe(duration=200.0))
        one = rows["ad-9x16.mp4"]
        by_dest = {t["destination"]: t for t in one["too_long"]}
        self.assertIn("Instagram Story (GHL Social Planner)", by_dest)
        self.assertEqual(by_dest["Instagram Story (GHL Social Planner)"]["use"],
                         "use the 60-second cut instead")
        self.assertIn("Facebook Story (GHL Social Planner)", by_dest)
        self.assertEqual(by_dest["Facebook Story (GHL Social Planner)"]["use"],
                         "use the 60-second or 90-second cut instead")
        # a 16:9-only destination refuses it on aspect, not on length, so the
        # kit never tells the client to cut a file that would not fit anyway
        self.assertNotIn("Facebook feed video (GHL Social Planner)", by_dest)
        # Instagram Reel takes 15 minutes: a 200 s file still fits
        self.assertIn("Instagram Reel (GHL Social Planner)", one["fits"])

    def test_an_audio_file_is_never_reported_as_too_long(self):
        rows = self._fits(probe(duration=200.0, container="mp3"))
        song = rows["Song.mp3"]
        self.assertEqual(song["fits"], [])
        self.assertEqual(song["too_long"], [])

    def test_the_fit_list_is_empty_when_the_table_is_not_installed(self):
        # the spec table lives in its own unit: without it the kit degrades
        # to no fit list and says so, it never invents a destination
        with mock.patch.object(platform_fit_module(), "load_specs",
                               side_effect=ValueError("table not on tree")):
            kit = R.prepare(str(self.run), str(self.deliv))
        self.assertEqual(kit["platform_fit"], [])
        for block in kit["captions"].values():
            self.assertIn("No researched platform spec table",
                          block["platform_spec"])


class LessonNeedsNoLink(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-lesson-")
        self.addCleanup(self.tmp.cleanup)

    def test_a_lesson_run_without_any_link_builds_and_says_no_link_needed(self):
        run, deliv = make_run(self.tmp.name, offer="Sing the lesson",
                              banner=False)
        write_method(run, "lesson")
        kit = R.prepare(str(run), str(deliv))       # no KIT_NO_LINK
        self.assertEqual(kit["link"], "")
        self.assertEqual(kit["links"], {"offer": None, "episode": None})
        self.assertEqual(kit["purpose"], "lesson")
        for key in ("youtube", "instagram", "tiktok", "facebook"):
            self.assertNotIn("Link:", kit["captions"][key]["caption"])
        pages, sizes = R.layout(kit)
        self.assertTrue(pages)
        self.assertIn(flat("No link needed for this post."), page_text(kit))
        self.assertGreaterEqual(min(sizes), 12.0)
        R.audit_kit(kit)

    def test_a_non_lesson_run_still_refuses_without_a_link(self):
        run, deliv = make_run(self.tmp.name, offer="Sing the lesson",
                              banner=False)
        write_method(run, "campaign")
        with self.assertRaises(R.KitError) as ctx:
            R.prepare(str(run), str(deliv))
        self.assertEqual(ctx.exception.code, "KIT_NO_LINK")

    def test_a_run_the_card_never_recorded_still_refuses_without_a_link(self):
        run, deliv = make_run(self.tmp.name, offer="Sing the lesson",
                              banner=False)
        with self.assertRaises(R.KitError) as ctx:
            R.prepare(str(run), str(deliv))
        self.assertEqual(ctx.exception.code, "KIT_NO_LINK")


class LayoutAndAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-layout-")
        self.addCleanup(self.tmp.cleanup)

    def test_the_ghl_section_and_both_link_records_reach_the_page(self):
        run, deliv = make_run(self.tmp.name, offer=OFFER)
        brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
        brief["channel"] = "Watch it on %s" % EPISODE
        (run / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
        write_method(run, "campaign")
        with with_probe(probe()):
            kit = R.prepare(str(run), str(deliv))
            pages, sizes = R.layout(kit)
            pdf = R.render_pdf(pages)
        text = page_text(kit)
        for needle in ("Where each file fits in GHL",
                       "Customize for Each Channel",
                       "check each post's published status",
                       "Trailers point here instead", EPISODE,
                       "LinkedIn", "Pinterest"):
            self.assertIn(flat(needle), text, needle)
        self.assertNotIn("twitter", text.lower())
        self.assertGreaterEqual(min(sizes), 12.0)
        used = [float(m) for m in re.findall(
            rb"/F[12] ([0-9]+(?:\.[0-9]+)?) Tf", pdf)]
        self.assertGreaterEqual(min(used), 12.0)
        R.audit_kit(kit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
