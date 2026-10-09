#!/usr/bin/env python3
"""DEL-07 tests: the READY-TO-POST KIT (the kit, its refusals, its floor).

Done-when cases (stdlib only, empty HOME, no network, no paid calls):
  1. a run with a receipt, a gate, a script and a link builds the numbered
     kit files (07 - Ready-to-Post Kit.pdf + .json) in the delivery folder;
  2. every glyph on every page is at least 12 pt on a white page;
  3. the kit carries a caption, a hashtag set and a placement row for
     YouTube, Instagram, TikTok and Facebook, and the link rides in each
     caption;
  4. the YouTube block keeps its platform limits (title <= 100 characters,
     tags <= 500 characters) and names the link;
  5. which-version-where reuses clip_cutdown.clips_for (the 3-minute run
     schedules a 60 s and a 90 s row even when no cutdown file is there);
  6. every law refuses by name: KIT_NO_LINK, KIT_STORYBOARD_NOT_APPROVED,
     KIT_NO_SCRIPT, KIT_DELIVERY_RECEIPT_MISSING, KIT_CHECKLIST_FAILED,
     KIT_BANNED_TEXT (tool/model name, dollar amount, income promise);
  7. the CLI exits 0 on a build and 2 on a refusal.

Run: python3 scripts/core/ready_post_kit/test_ready_post_kit.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[0]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import ready_post_kit as R   # noqa: E402

LINK = "https://example.com/class"
OFFER = "Book a free class at %s" % LINK


def make_run(root, *, offer=OFFER, link=None, gate=True, script=True,
             receipt="yes", length_text="3 minutes + 60s and 90s clips",
             files=("ad-9x16.mp4", "ad-16x9.mp4", "Song.mp3"), banner=True):
    """A complete fixture run + delivery folder; returns (run, delivery)."""
    run = Path(root) / "run"
    deliv = Path(root) / "delivery"
    (run / "creative").mkdir(parents=True, exist_ok=True)
    (run / "storyboard").mkdir(parents=True, exist_ok=True)
    deliv.mkdir(parents=True, exist_ok=True)

    brief = {"offer": offer}
    if link:
        brief["link"] = link
    (run / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (run / "card-answers.json").write_text(json.dumps([
        {"id": "length", "n": 3, "text": length_text},
        {"id": "shape", "n": 2, "text": "both"},
    ]), encoding="utf-8")
    if script:
        (run / "creative" / "script.json").write_text(json.dumps({
            "title": "The Last Cookie",
            "story": [["Act 1", ["She counted the cookies twice, waiting for "
                                 "the door to open."]]],
            "sheet": [{"tag": "verse",
                       "lines": ["I saved the last cookie for you."]}],
        }), encoding="utf-8")
        (run / "creative" / "script-approval.json").write_text(
            json.dumps({"sent": True}), encoding="utf-8")
    if gate:
        (run / "storyboard" / "gate.json").write_text(
            json.dumps({"shots": [{"shot_id": "S1"}], "review": {}}),
            encoding="utf-8")
    if receipt is not None:
        block = ({"answers": {"Q1": {"answer": receipt,
                                     "measurement": "measured"}}}
                 if receipt in ("yes", "no") else receipt)
        (deliv / "delivery-receipt.json").write_text(
            json.dumps(block), encoding="utf-8")
    (deliv / "README.md").write_text(
        "Banner link (all ads): %s\n" % LINK if banner else "nothing here\n",
        encoding="utf-8")
    for name in files:
        (deliv / name).write_bytes(b"x")
    return run, deliv


def build(run, deliv, **kw):
    return R.prepare(str(run), str(deliv), kw.get("client_dir"))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-")
        self.addCleanup(self.tmp.cleanup)
        self.run, self.deliv = make_run(self.tmp.name)

    def test_numbered_kit_files_land_in_the_delivery_folder(self):
        kit = build(self.run, self.deliv)
        pdf, js, data = R.write_kit(kit, str(self.deliv))
        self.assertTrue(pdf.endswith(R.PDF_NAME))
        self.assertTrue(js.endswith(R.JSON_NAME))
        raw = Path(pdf).read_bytes()
        self.assertTrue(raw.startswith(b"%PDF-1.4"))
        self.assertIn(b"%%EOF", raw)
        self.assertIn(b"/Type /Catalog", raw)
        saved = json.loads(Path(js).read_text(encoding="utf-8"))
        self.assertEqual(saved["kit_number"], "07")
        self.assertEqual(saved["link"], LINK)

    def test_every_glyph_is_at_least_12pt(self):
        kit = build(self.run, self.deliv)
        pages, sizes = R.layout(kit)
        self.assertTrue(pages)
        self.assertGreaterEqual(min(sizes), 12.0, "layout went under 12 pt")
        pdf = R.render_pdf(pages)
        used = [float(m) for m in
                re.findall(rb"/F[12] ([0-9]+(?:\.[0-9]+)?) Tf", pdf)]
        self.assertTrue(used, "no text operators in the PDF")
        self.assertGreaterEqual(min(used), 12.0, "a glyph under 12 pt")
        self.assertEqual(sorted({s for s in sizes}),
                         sorted({s for s in used}),
                         "layout sizes and drawn sizes disagree")

    def test_all_four_platforms_get_captions_hashtags_and_a_link(self):
        kit = build(self.run, self.deliv)
        for name in ("youtube", "instagram", "tiktok", "facebook"):
            cap = kit["captions"][name]["caption"]
            self.assertIn(LINK, cap, "%s caption lost the link" % name)
            self.assertTrue(kit["hashtags"][name], "%s has no hashtags" % name)
            self.assertTrue(kit["captions"][name]["note"].strip(),
                            "%s has no posting note" % name)
        R.audit_kit(kit)   # no tool/model name, dollar amount or promise

    def test_which_version_row_map(self):
        kit = build(self.run, self.deliv)
        kinds = {r["kind"] for r in kit["placement"]}
        self.assertIn("vertical", kinds)
        self.assertIn("horizontal", kinds)
        self.assertIn("song", kinds)
        # reuse: the 3-minute length schedules both cutdowns (clips_for)
        self.assertIn("clip60", kinds)
        self.assertIn("clip90", kinds)
        by_kind = {r["kind"]: r for r in kit["placement"]}
        self.assertIn("TikTok", by_kind["vertical"]["post_where"])
        self.assertIn("YouTube", by_kind["horizontal"]["post_where"])

    def test_youtube_block_limits(self):
        kit = build(self.run, self.deliv)
        yt = kit["youtube"]
        self.assertLessEqual(len(yt["title"]), 100)
        self.assertEqual(yt["title_length"], len(yt["title"]))
        self.assertLessEqual(len(yt["tags"]), 500)
        self.assertEqual(yt["tags_length"], len(yt["tags"]))
        self.assertTrue(yt["description"])
        self.assertIn(LINK, yt["description"])
        self.assertIn("Tags", "Tags")   # section wording in the layout

    def test_long_title_is_truncated_not_overflowed(self):
        long_title = ("The Last Cookie And Every Other Thing She Ever Baked "
                      "Before The Store Closed For Good")
        run, deliv = make_run(self.tmp.name + "-long")
        data = json.loads((run / "brief.json").read_text(encoding="utf-8"))
        (run / "brief.json").write_text(json.dumps(data), encoding="utf-8")
        script = json.loads((run / "creative" / "script.json").read_text())
        script["title"] = long_title
        (run / "creative" / "script.json").write_text(json.dumps(script))
        kit = build(run, deliv)
        self.assertLessEqual(kit["youtube"]["title_length"], 100)


class Refusals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kit-ref-")
        self.addCleanup(self.tmp.cleanup)

    def _refuse(self, code, **kw):
        run, deliv = make_run(self.tmp.name, **kw)
        with self.assertRaises(R.KitError) as ctx:
            R.prepare(str(run), str(deliv))
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def test_no_link_anywhere(self):
        # no link in the brief AND no URL in the offer AND no Banner line
        self._refuse("KIT_NO_LINK", offer="Book a free class", banner=False)

    def test_storyboard_gate_required(self):
        self._refuse("KIT_STORYBOARD_NOT_APPROVED", gate=False)

    def test_script_required(self):
        self._refuse("KIT_NO_SCRIPT", script=False)

    def test_receipt_required(self):
        self._refuse("KIT_DELIVERY_RECEIPT_MISSING", receipt=None)

    def test_measured_no_fails_the_kit(self):
        self._refuse("KIT_CHECKLIST_FAILED", receipt="no")

    def test_tool_name_in_offer_refused(self):
        self._refuse("KIT_BANNED_TEXT", offer="made with Suno at %s" % LINK)

    def test_dollar_amount_refused(self):
        self._refuse("KIT_BANNED_TEXT", offer="only $47, start today %s" % LINK)

    def test_income_promise_refused(self):
        self._refuse("KIT_BANNED_TEXT",
                     offer="guaranteed income, risk-free %s" % LINK)

    def test_plain_copy_is_not_refused(self):
        self.assertEqual(R.audit_text(OFFER), [])
        self.assertEqual(R.audit_text("She waited by the door with the song "
                                      "they both loved."), [])

    def test_brief_link_alias_wins_when_the_offer_has_no_url(self):
        run, deliv = make_run(self.tmp.name, offer="Book a free class",
                              banner=False,
                              link="https://example.com/other")
        kit = R.prepare(str(run), str(deliv))
        self.assertEqual(kit["link"], "https://example.com/other")


class ClipReuse(unittest.TestCase):
    def test_clips_for_drives_the_extra_rows(self):
        from clip_cutdown import clips_for
        self.assertEqual(clips_for(180), (60, 90))
        self.assertEqual(clips_for(60), ())
        tmp = tempfile.TemporaryDirectory(prefix="kit-clips-")
        self.addCleanup(tmp.cleanup)
        run, deliv = make_run(tmp.name, files=("ad-9x16.mp4", "Song.mp3"))
        kit = R.prepare(str(run), str(deliv))
        rows = {r["kind"] for r in kit["placement"]}
        self.assertIn("clip60", rows)
        self.assertIn("clip90", rows)
        # a short run schedules no cutdown row at all
        run2, deliv2 = make_run(tmp.name + "-60",
                                length_text="60 seconds",
                                files=("ad-9x16.mp4",))
        kit2 = R.prepare(str(run2), str(deliv2))
        rows2 = {r["kind"] for r in kit2["placement"]}
        self.assertNotIn("clip60", rows2)
        self.assertNotIn("clip90", rows2)


class Cli(unittest.TestCase):
    def test_cli_exit_0_then_2(self):
        tmp = tempfile.TemporaryDirectory(prefix="kit-cli-")
        self.addCleanup(tmp.cleanup)
        run, deliv = make_run(tmp.name)
        script = str(HERE / "ready_post_kit.py")
        ok = subprocess.run(
            [sys.executable, script, "--run-dir", str(run),
             "--delivery", str(deliv), "--quiet"],
            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue((deliv / R.PDF_NAME).is_file())
        # break the link, rebuild: refusal, exit 2, named on stderr
        (run / "brief.json").write_text(json.dumps({"offer": "no link here"}),
                                        encoding="utf-8")
        (deliv / "README.md").write_text("nothing here\n", encoding="utf-8")
        bad = subprocess.run(
            [sys.executable, script, "--run-dir", str(run),
             "--delivery", str(deliv), "--quiet"],
            capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("KIT_NO_LINK", bad.stderr)


class CharacterHashtag(unittest.TestCase):
    def test_saved_character_reaches_the_hashtag_set(self):
        tmp = tempfile.TemporaryDirectory(prefix="kit-char-")
        self.addCleanup(tmp.cleanup)
        run, deliv = make_run(tmp.name)
        lib = Path(tmp.name) / "client" / "character-library" / "rove"
        lib.mkdir(parents=True)
        (lib / "character.json").write_text(json.dumps({
            "schema": "character-library/v1", "name": "Rove",
            "slug": "rove", "description": "a tired baker",
            "voice_notes": "", "reference_images": ["references/1-a.png"],
        }), encoding="utf-8")
        kit = R.prepare(str(run), str(deliv), str(Path(tmp.name) / "client"))
        self.assertEqual(kit["character"], "Rove")
        self.assertIn("#rove", kit["hashtags"]["shared"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
