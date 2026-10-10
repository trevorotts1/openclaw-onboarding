"""DEL-05: the delivery folder ships the video twice -- captioned and clean.

What the unit owes, and what this file proves:

  * two clearly NAMED, numbered files land in one delivery folder per run;
  * both are produced through ``final_assembler/captions_burn`` (the one
    caption site): the captioned plan with captions on, the clean plan with
    ``style.enabled`` False -- this module writes no caption text of its own;
  * every delivered video passes ``delivery_audio.check_delivery_audio()``,
    and a refused pair leaves NOTHING behind (all or nothing);
  * the returned pair feeds ``batch_zip`` unchanged, is listed in the
    receipt and README, and ``check_video_delivery`` / its CLI say PASS only
    when both files are there, listed and AAC-gated.

Fixtures are generic (no client names) and built with ffmpeg at test time.
Run: python3 core/delivery_variants/test_video_delivery_del05.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import delivery_audio as DA  # noqa: E402
import qc_gate  # noqa: E402
from delivery_variants import video_delivery as vd  # noqa: E402
import batch_zip.batch_zip as bz  # noqa: E402
from final_assembler import captions_burn as cb  # noqa: E402

FF = shutil.which("ffmpeg")
FP = shutil.which("ffprobe")

AD = "Sample Story"
LINES = ["She kept the kitchen spotless", "for thirty years."]
CUES = [{"text": LINES[0], "start": 0.0, "end": 1.0},
        {"text": LINES[1], "start": 1.0, "end": 2.0}]


def _has_subtitles(exe):
    """True only when this ffmpeg really carries the libass subtitles filter."""
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"],
                             capture_output=True, text=True,
                             timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return re.search(r"(^|\s)subtitles(\s|$)", out, re.M) is not None


def _vendor_ffmpeg():
    """A libass build the box may carry beside PATH (CI's apt ffmpeg has one)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def burn_ffmpeg():
    for cand in (FF, _vendor_ffmpeg()):
        if cand and _has_subtitles(cand):
            return cand
    return None


BURN_FF = burn_ffmpeg() if (FF and FP) else None


def _mk_master(path):
    """A 2 s 320x568 master with real AAC audio: the input of a real run."""
    subprocess.run([FF, "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=navy:s=320x568:d=2:r=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    *DA.AUDIO_OUT_ARGS, *DA.FASTSTART_ARGS, str(path)],
                   check=True)


def _mk_mp3(path):
    subprocess.run([FF, "-y", "-v", "error",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=2",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(path)],
                   check=True)


class Names(unittest.TestCase):
    def test_the_two_files_are_numbered_and_unmistakable(self):
        cap, clean = vd.captioned_name(AD), vd.clean_name(AD)
        self.assertEqual(cap, "05 - Video Captioned.mp4")
        self.assertEqual(clean, "05 - Video Clean.mp4")
        self.assertNotEqual(cap, clean)
        self.assertTrue(cap.startswith("05 - ") and clean.startswith("05 - "))
        self.assertIn("Captioned", cap)
        self.assertIn("Clean", clean)
        self.assertTrue(cap.endswith(".mp4") and clean.endswith(".mp4"))

    def test_a_blank_ad_name_is_refused(self):
        for fn in (vd.captioned_name, vd.clean_name):
            with self.assertRaises(ValueError):
                fn("   ")

    def test_the_check_is_registered_on_the_delivery_gate(self):
        self.assertIn("video_delivery", qc_gate.CHECKS)
        res = qc_gate.evaluate({}, "delivery", [], {}, ["video_delivery"])
        self.assertEqual(res["failures"][0]["code"], "MISSING_QC")

    def test_force_style_reads_the_look_off_the_plan_only(self):
        plan, why = cb.build_plan(LINES, cues=CUES, width_px=1080,
                                  height_px=1920)
        self.assertIsNone(why)
        style = dict(plan["style"], bottom_margin_px=777, edge_margin_px=31,
                     font_size_px=99)
        fs = vd.force_style(style)
        self.assertIn("MarginV=777", fs)
        self.assertIn("MarginL=31", fs)
        self.assertIn("MarginR=31", fs)
        self.assertIn("FontSize=99", fs)
        # ASS is &HAABBGGRR: alpha 00 (opaque) + red/blue/green swapped.
        self.assertIn("BackColour=&H00ffffff", fs)     # white box
        self.assertIn("PrimaryColour=&H00000000", fs)  # black text
        self.assertIn("BorderStyle=3", fs)

    def test_the_plan_drives_both_argv_lines(self):
        plan, _ = cb.build_plan(LINES, cues=CUES)
        cap = vd.burn_argv("m.mp4", "o.mp4", "c.srt", plan["style"])
        clean = vd.clean_argv("m.mp4", "o.mp4")
        self.assertIn("subtitles=c.srt:force_style='%s'"
                      % vd.force_style(plan["style"]), cap)
        self.assertIn("libx264", cap)
        for argv in (cap, clean):
            self.assertEqual(argv[argv.index("-c:a") + 1], "aac")
            self.assertEqual(argv[argv.index("-ar") + 1], "48000")
            self.assertEqual(argv[argv.index("-movflags") + 1], "+faststart")
        self.assertIn("-c:v", clean)
        self.assertEqual(clean[clean.index("-c:v") + 1], "copy")
        self.assertNotIn("subtitles=", " ".join(clean))


@unittest.skipUnless(FF and FP, "ffmpeg + ffprobe required")
class NoMaster(unittest.TestCase):
    def test_a_missing_master_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(vd.VideoDeliveryError) as cm:
                vd.build_video_delivery(Path(td) / "none.mp4", Path(td) / "d",
                                        AD, LINES, cues=CUES)
            self.assertEqual(cm.exception.code, "MASTER_MISSING")
            self.assertFalse((Path(td) / "d").exists())


@unittest.skipUnless(BURN_FF, "an ffmpeg with the subtitles filter required")
class DeliverThePair(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="del05-"))
        self.master = self.t / "master.mp4"
        _mk_master(self.master)
        self.d = self.t / "delivery"

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def build(self, **kw):
        kw.setdefault("ffmpeg", BURN_FF)
        kw.setdefault("cues", CUES)
        kw.setdefault("provenance", "measured")
        return vd.build_video_delivery(
            self.master, self.d, AD, LINES, **kw)

    def test_two_numbered_files_land_and_both_pass_the_real_gate(self):
        res = self.build()
        cap, clean = Path(res["captioned"]), Path(res["clean_master"])
        self.assertEqual(cap.name, "05 - Video Captioned.mp4")
        self.assertEqual(clean.name, "05 - Video Clean.mp4")
        self.assertEqual(sorted(p.name for p in self.d.glob("*.mp4")),
                         sorted([cap.name, clean.name]))

        # Both went through captions_burn: same words, captions on vs off.
        self.assertTrue(res["plans"]["captioned"]["style"]["enabled"])
        self.assertFalse(res["plans"]["clean"]["style"]["enabled"])
        self.assertEqual(res["plans"]["captioned"]["lines"], LINES)
        self.assertEqual(res["plans"]["clean"]["lines"], LINES)
        self.assertTrue(res["plans"]["captioned"]["srt"])
        self.assertEqual(res["srt"], res["plans"]["captioned"]["srt"])

        # The gate, for real, on BOTH delivered videos.
        for p in (cap, clean):
            r = DA.check_delivery_audio(str(p))
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["codec"], "aac")
        self.assertEqual([r["kind"] for r in res["rows"]],
                         ["captioned", "clean_master"])
        self.assertEqual(res["resolution"], "320x568")

        # The SRT is carried, not shipped: DEL-10 owns the caption file.
        self.assertEqual(list(self.d.glob("*.srt")), [])

    def test_the_captions_are_actually_on_the_pixels(self):
        """Not just two files: the captioned cut really shows the captions."""
        res = self.build()
        cap, clean = Path(res["captioned"]), Path(res["clean_master"])
        # 0.5 s falls inside cue 1 (0.0 -> 1.0): the box must be drawn there.
        self.assertNotEqual(self._frame_digest(cap, 0.5),
                            self._frame_digest(clean, 0.5),
                            "the captioned cut is pixel-identical to the clean "
                            "one: no caption was burned")

    def _frame_digest(self, video, at):
        out = self.t / ("f-%s-%s.png" % (video.stem[:6], at))
        subprocess.run([FF, "-y", "-v", "error", "-ss", str(at), "-i",
                        str(video), "-frames:v", "1", str(out)], check=True)
        import hashlib
        return hashlib.sha256(out.read_bytes()).hexdigest()

    def test_docs_then_check_then_cli(self):
        res = self.build()
        vd.write_video_docs(self.d, res["rows"])
        receipt = json.loads((self.d / "delivery-receipt.json").read_text())
        self.assertEqual([r["file"] for r in receipt["video_delivery"]],
                         res["files"])
        readme = (self.d / "README.md").read_text()
        for name in res["files"]:
            self.assertIn(name, readme)
        self.assertEqual(vd.check_video_delivery(self.d, AD)[0], "PASS")
        self.assertEqual(vd._cli(["check", str(self.d), AD]), 0)
        self.assertEqual(vd._cli(["bogus"]), 1)

    def test_rewriting_the_docs_never_clobbers_the_readme(self):
        res = self.build()
        (self.d / "README.md").write_text("# Mine\n\nkeep me\n")
        vd.write_video_docs(self.d, res["rows"])
        vd.write_video_docs(self.d, res["rows"])
        text = (self.d / "README.md").read_text()
        self.assertIn("keep me", text)
        self.assertEqual(text.count("video-delivery:begin"), 1)

    def test_check_fails_when_a_video_is_gone_or_unlisted(self):
        res = self.build()
        vd.write_video_docs(self.d, res["rows"])
        Path(res["clean_master"]).unlink()
        v, why = vd.check_video_delivery(self.d, AD)
        self.assertEqual(v, "FAIL")
        self.assertIn(Path(res["clean_master"]).name, why)

        # Back to a full pair, then drop the clean one from the receipt.
        res = self.build()
        vd.write_video_docs(self.d, res["rows"])
        receipt = json.loads((self.d / "delivery-receipt.json").read_text())
        receipt["video_delivery"] = [receipt["video_delivery"][0]]
        (self.d / "delivery-receipt.json").write_text(json.dumps(receipt))
        v, why = vd.check_video_delivery(self.d, AD)
        self.assertEqual(v, "FAIL")
        self.assertIn("not listed", why)
        self.assertEqual(vd._cli(["check", str(self.d), AD]), 5)

    def test_a_folder_without_a_receipt_cannot_pass(self):
        self.d.mkdir(parents=True, exist_ok=True)
        self.assertEqual(vd.check_video_delivery(self.d, AD)[0], "FAIL")
        self.assertEqual(vd._cli(["check", str(self.d), AD]), 5)

    def test_a_refused_pair_leaves_nothing_behind(self):
        def refuse(path):
            return {"ok": False, "reason_code": DA.BAD_CODEC,
                    "reason": "mp3 in mp4", "codec": "mp3"}
        with self.assertRaises(vd.VideoDeliveryError) as cm:
            self.build(audio_gate=refuse)
        self.assertEqual(cm.exception.code, "DELIVERY_AUDIO_REFUSED")
        self.assertEqual(list(self.d.glob("*.mp4")), [],
                         "a half-delivered pair is never handed over")

    def test_bad_measured_cues_refuse_before_a_render(self):
        with self.assertRaises(vd.VideoDeliveryError) as cm:
            self.build(cues=[{"text": "x", "start": 9.0, "end": 1.0}])
        self.assertEqual(cm.exception.code, "CAPTION_PLAN_REFUSED")
        self.assertEqual(list(self.d.glob("*.mp4")), [])

    def test_the_pair_feeds_batch_zip_unchanged(self):
        res = self.build()
        vd.write_video_docs(self.d, res["rows"])
        song = self.d / "Sample-Story.mp3"
        _mk_mp3(song)
        ads = [{"author": "Sample Author", "title": AD,
                "captioned": res["captioned"],
                "clean_master": res["clean_master"],
                "song_mp3": str(song),
                "duration_s": res["duration_s"],
                "resolution": res["resolution"],
                "banner": "https://example.invalid/ad"}]
        out = self.t / "batch.zip"
        result = bz.build_batch_zip("Sample Client", ads, out)
        self.assertTrue(out.is_file())
        self.assertEqual(result["files"], 3)
        names = [n for n in _zip_names(out) if n != "README.md"]
        self.assertIn("Sample-Author_Sample-Story/"
                      "05 - Video Captioned.mp4", names)
        self.assertIn("Sample-Author_Sample-Story/"
                      "05 - Video Clean.mp4", names)


def _zip_names(path):
    import zipfile
    with zipfile.ZipFile(path) as z:
        return z.namelist()


if __name__ == "__main__":
    unittest.main(verbosity=2)
