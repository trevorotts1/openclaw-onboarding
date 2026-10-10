"""DEL-08 tests: the ONE cover image (thumbnail) per delivery folder.

Run (stdlib only, no spend, no network; the render is a fake launcher so no
test ever needs a font or a real frame):

    python3 -m unittest delivery_variants.test_cover_image_dl08
    (from the skill folder, or with scripts/core on sys.path)
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from delivery_variants import cover_image as ci        # noqa: E402
from delivery_variants import song_files as sf         # noqa: E402
import qc_gate                                         # noqa: E402

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def ffmpeg_bin():
    """The binary the real-render tests use: COVER_IMAGE_FFMPEG, else PATH.

    A box's default ffmpeg may ship without libfreetype (no drawtext), so a
    caller with a fuller build points the cover render at it.
    """
    return os.environ.get("COVER_IMAGE_FFMPEG") or "ffmpeg"


def png_bytes(w, h):
    """A real, decodable RGB PNG (zeros compress to nothing)."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * w for _ in range(h))
    return (PNG_SIG
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def fake_runner(size_from_argv=True, fixed=None, calls=None):
    """A launcher that writes a PNG of the size the argv asked for."""
    def run(argv, job="ffmpeg"):
        if calls is not None:
            calls.append(list(argv))
        if size_from_argv:
            m = re.search(r"scale=(\d+):(\d+)", argv[argv.index("-vf") + 1])
            w, h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        else:
            w, h = fixed
        Path(argv[-1]).write_bytes(png_bytes(w, h))

        class _R:
            returncode = 0
        return _R()
    return run


class CoverImage(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="del08-"))
        self.run = self.t / "run"
        self.d = self.t / "delivery"
        self._build_run()
        self.font = self.t / "font.ttf"
        self.font.write_bytes(b"ttf-stub")

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def _build_run(self, title="The Long Road", approved=True, stills=None):
        sb = self.run / "storyboard"
        (sb / "redo").mkdir(parents=True, exist_ok=True)
        (self.run / "creative").mkdir(parents=True, exist_ok=True)
        shots = [
            {"shot_id": "s1", "song_start": 0.0, "song_end": 8.0,
             "character_ids": ["ana"]},
            {"shot_id": "s2", "song_start": 8.0, "song_end": 16.0,
             "character_ids": []},
            {"shot_id": "s3", "song_start": 16.0, "song_end": 24.0,
             "character_ids": ["ana"]},
        ]
        contracts = {"s1": {"visible_emotion": ""},
                     "s2": {"visible_emotion": ""},
                     "s3": {"visible_emotion": "defiant"}}
        if stills is None:
            stills = {"s1": "storyboard/s1.png",
                      "s2": "storyboard/s2.png",
                      "s3": "storyboard/s3.png"}
        for sid, rel in stills.items():
            p = self.run / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(png_bytes(64, 36))
        (sb / "shot-list.json").write_text(json.dumps({"shots": shots}))
        (sb / "contracts.json").write_text(json.dumps(contracts))
        (sb / "stills.json").write_text(json.dumps(stills))
        (sb / "approval.json").write_text(json.dumps(
            {"state": "approved" if approved else "pending"}))
        (self.run / "creative" / "script.json").write_text(
            json.dumps({"title": title, "sheet": [{"tag": "verse", "lines": []}]}))

    def build(self, **kw):
        kw.setdefault("fontfile", str(self.font))
        kw.setdefault("runner", fake_runner())
        row = ci.build_cover(str(self.run), str(self.d), "Kiesett Ad", **kw)
        ci.write_cover_docs(self.d, row)
        return row

    # ---------------------------------------------------------- dimensions ---
    def test_default_dimensions_are_the_sensible_1280x720(self):
        self.assertEqual((ci.DEFAULT_WIDTH, ci.DEFAULT_HEIGHT), (1280, 720))

    def test_cover_file_name_is_the_contract_canonical_name(self):
        # ONE naming scheme: the DEL-13 contract owns this item's name.
        self.assertEqual(ci.cover_file_name("Kiesett Ad"),
                         "08 - Cover Thumbnail.png")
        self.assertEqual(ci.cover_file_name("Another Ad"),
                         "08 - Cover Thumbnail.png")

    def test_build_writes_exactly_one_image_and_it_measures_1280x720(self):
        row = self.build()
        self.d.mkdir(parents=True, exist_ok=True)
        images = [p.name for p in self.d.iterdir() if p.suffix == ".png"]
        self.assertEqual(images, ["08 - Cover Thumbnail.png"])
        w, h = ci.png_size(self.d / row["file"])
        self.assertEqual((w, h), (1280, 720))
        self.assertEqual((row["width"], row["height"]), (1280, 720))

    def test_explicit_dimensions_are_honoured(self):
        row = self.build(width=1080, height=1920)
        self.assertEqual(ci.png_size(self.d / row["file"]), (1080, 1920))

    def test_bad_dimensions_are_refused(self):
        for bad in ({"width": 0}, {"width": 10}, {"height": 7681},
                    {"width": True}, {"width": 720.5}):
            with self.assertRaises(ci.CoverImageError) as cm:
                ci.build_cover(str(self.run), str(self.d), "X", fontfile=str(self.font),
                               runner=fake_runner(), **bad)
            self.assertEqual(cm.exception.code, ci.BAD_INPUT)

    # -------------------------------------------------------------- sources ---
    def test_title_comes_from_the_approved_script(self):
        row = self.build()
        self.assertEqual(row["title"], "The Long Road")

    def test_title_falls_back_to_the_brief_and_never_invents_one(self):
        (self.run / "creative" / "script.json").write_text(json.dumps({}))
        (self.run / "brief.json").write_text(json.dumps({"title": "From Brief"}))
        self.assertEqual(ci.title_of(str(self.run)), "From Brief")
        (self.run / "brief.json").unlink()
        with self.assertRaises(ci.CoverImageError) as cm:
            ci.title_of(str(self.run))
        self.assertEqual(cm.exception.code, ci.NO_TITLE)

    def test_frame_selection_prefers_the_face_the_character_shows(self):
        shots, contracts, stills = ci.load_frames(str(self.run))
        picked = ci.select_frame(stills, shots, contracts)
        self.assertEqual(picked["shot_id"], "s3")          # visible_emotion
        self.assertEqual(picked["why"], "face-visible")

    def test_frame_selection_falls_through_to_character_then_first(self):
        shots, contracts, stills = ci.load_frames(str(self.run))
        contracts["s3"]["visible_emotion"] = ""            # no face anywhere
        self.assertEqual(ci.select_frame(stills, shots, contracts)["shot_id"], "s1")
        for c in contracts.values():
            c["visible_emotion"] = ""
        shots[0]["character_ids"] = []                      # only s3 has one
        self.assertEqual(ci.select_frame(stills, shots, contracts)["shot_id"], "s3")
        for s in shots:
            s["character_ids"] = []
        self.assertEqual(ci.select_frame(stills, shots, contracts)["shot_id"], "s1")

    def test_a_missing_or_empty_still_is_never_shipped(self):
        (self.run / "storyboard" / "s3.png").write_bytes(b"")
        (self.run / "storyboard" / "s1.png").unlink()
        shots, contracts, stills = ci.load_frames(str(self.run))
        self.assertEqual(ci.select_frame(stills, shots, contracts)["shot_id"], "s2")
        (self.run / "storyboard" / "s2.png").unlink()
        with self.assertRaises(ci.CoverImageError) as cm:
            ci.select_frame(stills, shots, contracts)
        self.assertEqual(cm.exception.code, ci.NO_FRAME)

    def test_relative_still_paths_resolve_against_the_run(self):
        _shots, _c, stills = ci.load_frames(str(self.run))
        self.assertEqual(stills["s1"], str(self.run / "storyboard" / "s1.png"))

    def test_an_unapproved_storyboard_gate_refuses_the_cover(self):
        self._build_run(approved=False)
        with self.assertRaises(ci.CoverImageError) as cm:
            ci.build_cover(str(self.run), str(self.d), "Kiesett Ad",
                           fontfile=str(self.font), runner=fake_runner())
        self.assertEqual(cm.exception.code, ci.NOT_APPROVED)

    # -------------------------------------------------------------- render ---
    def test_argv_is_data_no_process_runs(self):
        calls = []
        (self.run / "storyboard" / "approval.json").write_text(
            json.dumps({"state": "approved"}))
        title_file = str(self.t / "title.txt")
        Path(title_file).write_text("The Long Road")
        argv = ci.build_cover_argv(str(self.run / "storyboard" / "s3.png"),
                                   str(self.d / "x.png"), title_file,
                                   fontfile=str(self.font))
        self.assertEqual(calls, [])                        # nothing spawned
        self.assertEqual(argv[0], "ffmpeg")
        self.assertEqual(argv[-1], str(self.d / "x.png"))
        self.assertIn("-frames:v", argv)

    def test_the_title_travels_as_textfile_never_as_filter_syntax(self):
        title = "50% off: pay $5, [now] %{evil};"          # filter metacharacters
        self._build_run(title=title)
        title_file = str(self.t / "title.txt")
        Path(title_file).write_text(title)
        argv = ci.build_cover_argv("frame.png", "out.png", title_file,
                                   fontfile=str(self.font))
        vf = argv[argv.index("-vf") + 1]
        self.assertIn("textfile=" + title_file, vf)
        self.assertIn("expansion=none", vf)
        for token in ("50%", "%{evil}", "[now]", "pay $5"):
            self.assertNotIn(token, vf)                    # never parsed by ffmpeg
        row = self.build()
        self.assertEqual(row["title"], title)

    def test_a_title_with_metacharacters_still_renders_and_measures(self):
        self._build_run(title="Chapter 1: the 100% truth")
        row = self.build(width=640, height=360)
        self.assertEqual(ci.png_size(self.d / row["file"]), (640, 360))
        self.assertEqual(row["title"], "Chapter 1: the 100% truth")

    def test_control_characters_in_a_title_are_refused(self):
        self._build_run(title="bad\ntitle")
        with self.assertRaises(ci.CoverImageError) as cm:
            self.build()
        self.assertEqual(cm.exception.code, ci.BAD_INPUT)

    def test_a_missing_font_fails_closed(self):
        with self.assertRaises(ci.CoverImageError) as cm:
            ci.resolve_font(str(self.t / "nope.ttf"))
        self.assertEqual(cm.exception.code, ci.FONT_MISSING)

    def test_a_refused_render_leaves_no_half_written_cover(self):
        def fail(argv, job="ffmpeg"):
            class _R:
                returncode = 7
            return _R()
        with self.assertRaises(ci.CoverImageError) as cm:
            ci.build_cover(str(self.run), str(self.d), "Kiesett Ad",
                           fontfile=str(self.font), runner=fail)
        self.assertEqual(cm.exception.code, ci.RENDER_FAILED)
        self.assertFalse((self.d / ci.cover_file_name("Kiesett Ad")).exists())

    def test_a_render_that_writes_the_wrong_size_is_refused(self):
        with self.assertRaises(ci.CoverImageError) as cm:
            ci.build_cover(str(self.run), str(self.d), "Kiesett Ad",
                           fontfile=str(self.font),
                           runner=fake_runner(size_from_argv=False,
                                              fixed=(320, 180)))
        self.assertEqual(cm.exception.code, ci.RENDER_FAILED)

    # ------------------------------------------------------------------ docs ---
    def test_docs_merge_without_clobbering_and_write_the_block_once(self):
        self.d.mkdir(parents=True, exist_ok=True)
        (self.d / "README.md").write_text("# Mine\n\nkeep me\n")
        self.build()
        self.build()                                       # run twice
        text = (self.d / "README.md").read_text()
        self.assertIn("keep me", text)
        self.assertEqual(text.count("cover-image:begin"), 1)
        self.assertIn("08 - Cover Thumbnail.png", text)
        receipt = json.loads((self.d / "delivery-receipt.json").read_text())
        self.assertEqual(receipt["cover_image"]["file"],
                         "08 - Cover Thumbnail.png")
        self.assertEqual(list(p.name for p in self.d.iterdir()
                              if p.suffix == ".png"),
                         ["08 - Cover Thumbnail.png"])

    # ------------------------------------------------------------------- QC ---
    def test_check_passes_on_a_built_cover(self):
        self.build()
        verdict, detail = ci.check_cover_image(str(self.d), "Kiesett Ad")
        self.assertEqual(verdict, ci.PASS, detail)

    def test_check_fails_on_every_gap(self):
        self.build()
        (self.d / ci.cover_file_name("Kiesett Ad")).unlink()
        self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0], ci.FAIL)

        self.build()
        (self.d / ci.cover_file_name("Kiesett Ad")).write_bytes(png_bytes(10, 10))
        self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0], ci.FAIL)

        self.build()
        receipt = json.loads((self.d / "delivery-receipt.json").read_text())
        receipt["cover_image"]["sha256"] = "0" * 64
        (self.d / "delivery-receipt.json").write_text(json.dumps(receipt))
        self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0], ci.FAIL)

        (self.d / "delivery-receipt.json").unlink()
        self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0], ci.FAIL)

        self.build()
        (self.d / "README.md").write_text("# nothing\n")
        self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0], ci.FAIL)

        receipt = json.loads((self.d / "delivery-receipt.json").read_text())
        receipt["cover_image"].pop("title")
        (self.d / "delivery-receipt.json").write_text(json.dumps(receipt))
        self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0], ci.FAIL)

    def test_check_reads_the_pixels_not_the_receipt_claim(self):
        self.build(width=1280, height=720)
        receipt = json.loads((self.d / "delivery-receipt.json").read_text())
        receipt["cover_image"]["width"], receipt["cover_image"]["height"] = 4, 4
        (self.d / "delivery-receipt.json").write_text(json.dumps(receipt))
        verdict, detail = ci.check_cover_image(str(self.d), "Kiesett Ad")
        self.assertEqual(verdict, ci.PASS)                 # IHDR says 1280x720
        self.assertIn("1280x720", detail)

    def test_cli_check_exit_codes(self):
        self.build()
        self.assertEqual(ci._cli(["check", str(self.d), "Kiesett Ad"]), 0)
        (self.d / ci.cover_file_name("Kiesett Ad")).unlink()
        self.assertEqual(ci._cli(["check", str(self.d), "Kiesett Ad"]), 5)
        self.assertEqual(ci._cli([]), 1)

    def test_cli_build_renders_or_refuses_with_a_measured_reason(self):
        """The CLI launches the real ffmpeg: it either produces a cover that
        then passes check, or it refuses with the measured reason (no
        drawtext in this build). It never writes a cover without its title
        and never exits 0 on a refusal."""
        ff = ffmpeg_bin()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ci._cli(["build", "--run", str(self.run),
                          "--delivery", str(self.d), "--ad-name", "Kiesett Ad",
                          "--font", str(self.font), "--ffmpeg", ff])
        out = json.loads(buf.getvalue())
        if ci.has_filter("drawtext", ff):
            self.assertEqual(rc, 0, out)
            self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0],
                             ci.PASS)
        else:
            self.assertEqual(rc, 1)
            self.assertEqual(out["reason_code"], ci.NO_DRAWTEXT)

    def test_has_filter_measures_instead_of_assuming(self):
        self.assertIsInstance(ci.has_filter("drawtext"), bool)
        self.assertFalse(ci.has_filter("definitely-not-a-filter-xyz"))
        self.assertFalse(ci.has_filter("scale; rm -rf /"))
        self.assertFalse(ci.has_filter("scale", ffmpeg="/nonexistent/ffmpeg-xyz"))

    def test_qc_gate_knows_the_check(self):
        self.assertIn("cover_image", qc_gate.CHECKS)
        res = qc_gate.evaluate("r", "delivery", [], {}, ["cover_image"])
        self.assertEqual(res["failures"][0]["code"], "MISSING_QC")

    # ------------------------------------------------------- optional real ---
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_real_ffmpeg_renders_the_cover(self):
        ff = ffmpeg_bin()
        if not ci.has_filter("drawtext", ff):
            self.skipTest("no drawtext filter in %r (pass COVER_IMAGE_FFMPEG)"
                          % ff)
        try:
            font = ci.resolve_font()
        except ci.CoverImageError:
            self.skipTest("no system font on this box")
        row = ci.build_cover(str(self.run), str(self.d), "Kiesett Ad",
                             fontfile=font, ffmpeg=ff)
        ci.write_cover_docs(self.d, row)
        self.assertEqual(ci.png_size(self.d / row["file"]), (1280, 720))
        self.assertEqual(ci.check_cover_image(str(self.d), "Kiesett Ad")[0],
                         ci.PASS)


if __name__ == "__main__":
    unittest.main()
