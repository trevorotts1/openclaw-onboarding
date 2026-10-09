#!/usr/bin/env python3
"""DEL-14 refusal-gate tests: qc_no_blur.

Real ffmpeg fixtures, no mocks of the measurement:

  source            16:9 moving structured clip
  blur_fill.mp4     edge-sampled + gaussian backdrop (the illegal fill)
  dup_strip.mp4     duplicated blurred strip on top
  edge_col.mp4      4 px left column scaled into a backdrop
  letterbox.mp4     black bars instead of a full-height frame
  clean_916.mp4     crop-in: full height from the source frame (legal)
  plain_top_916.mp4 crop-in plus a PLAIN top band (legal, must not flag)
  clean_169.mp4     a plain 16:9 master (legal)

Asserts: the assembler gate and the quality gate both refuse every fill with
an actionable error naming the violation; a clean full-height clip passes;
the crop-in re-lip-sync path regenerates the filled clip from the SOURCE
frame and the regenerated clip passes both gates.

Run: python3 scripts/qc_no_blur/test_qc_no_blur.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:      # scripts/ on the path
    sys.path.insert(0, os.path.dirname(HERE))

import qc_no_blur as QN                      # noqa: E402
from qc_no_blur import assembler_gate as AG  # noqa: E402
from qc_no_blur import crop_relip as CR      # noqa: E402
from qc_no_blur import detect                # noqa: E402
from qc_no_blur import quality_gate as QG    # noqa: E402

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

SRC_W, SRC_H, SRC_DUR, SRC_FPS = 640, 360, 3.0, 30


def have_ffmpeg():
    return shutil.which(FFMPEG) and shutil.which(FFPROBE)


def make_source(path):
    """A structured 16:9 clip with motion: testsrc2 + moving bar."""
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-nostats", "-v", "error",
         "-f", "lavfi", "-i",
         "testsrc2=size=%dx%d:rate=%d:duration=%.1f" % (SRC_W, SRC_H,
                                                        SRC_FPS, SRC_DUR),
         "-vf", "drawbox=x=mod(t*120\\,iw):y=40:w=40:h=120:color=white:"
                "t=fill,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", str(path)],
        check=True, timeout=180)
    return path


def run(args, timeout=300):
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=timeout, check=False)


def make_blur_fill(src, out, bg="gblur"):
    """The classic illegal fill: blurred backdrop + subject strip."""
    if bg == "gblur":
        chain = ("[0:v]split[a][b];"
                 "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
                 "crop=1080:1920,gblur=sigma=24[bg];"
                 "[b]scale=1080:-2[fg];"
                 "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")
    else:                                   # edge-sampled backdrop
        chain = ("[0:v]split[a][b];"
                 "[a]crop=4:ih:0:0,scale=1080:1920,gblur=sigma=8[bg];"
                 "[b]scale=1080:-2[fg];"
                 "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")
    p = run([FFMPEG, "-y", "-hide_banner", "-nostats", "-v", "error",
             "-i", str(src), "-filter_complex", chain, "-map", "[v]",
             "-c:v", "libx264", "-preset", "veryfast", str(out)])
    assert p.returncode == 0, p.stderr[-400:]
    return out


def make_dup_strip(src, out):
    """A blurred strip duplicated onto the top of a full-height frame."""
    chain = ("[0:v]split[a][b];"
             "[a]crop=iw:4:0:ih-4,scale=1080:200,gblur=sigma=16[strip];"
             "[b]crop=ih*9/16:ih,scale=1080:1920,setsar=1[main];"
             "[strip][main]vstack=inputs=2,crop=1080:1920:0:0,"
             "format=yuv420p[v]")
    p = run([FFMPEG, "-y", "-hide_banner", "-nostats", "-v", "error",
             "-i", str(src), "-filter_complex", chain, "-map", "[v]",
             "-c:v", "libx264", "-preset", "veryfast", str(out)])
    assert p.returncode == 0, p.stderr[-400:]
    return out


def make_letterbox(src, out):
    """16:9 content letterboxed into 1080x1920."""
    chain = ("[0:v]scale=1080:608,setsar=1[fg];"
             "color=c=black:s=1080x1920:d=3:r=%d[bg];"
             "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
             % SRC_FPS)
    p = run([FFMPEG, "-y", "-hide_banner", "-nostats", "-v", "error",
             "-i", str(src), "-filter_complex", chain, "-map", "[v]",
             "-c:v", "libx264", "-preset", "veryfast", str(out)])
    assert p.returncode == 0, p.stderr[-400:]
    return out


def make_crop_in(src, out, plain_top=False, bias="center"):
    """The LEGAL path: crop-in of the source frame to full 9:16 height."""
    box = CR.crop_box(SRC_W, SRC_H, 1080, 1920, bias)
    cw, ch, ox, oy = box
    if plain_top:                           # a PLAIN top band, not a fill
        chain = ("[0:v]crop=%d:%d:%d:%d,scale=1080:1920:flags=lanczos,"
                 "setsar=1[c];"
                 "color=c=0x101820:s=1080x220:d=%.1f:r=%d[top];"
                 "[c][top]overlay=0:0,format=yuv420p[v]"
                 % (cw, ch, ox, oy, SRC_DUR, SRC_FPS))
        args = ["-filter_complex", chain, "-map", "[v]"]
    else:
        vf = ("crop=%d:%d:%d:%d,scale=1080:1920:flags=lanczos,setsar=1"
              % (cw, ch, ox, oy))
        args = ["-vf", vf]
    p = run([FFMPEG, "-y", "-hide_banner", "-nostats", "-v", "error",
             "-i", str(src)] + args + ["-c:v", "libx264",
                                       "-preset", "veryfast", str(out)])
    assert p.returncode == 0, p.stderr[-400:]
    return out


def make_plain_169(src, out):
    p = run([FFMPEG, "-y", "-hide_banner", "-nostats", "-v", "error",
             "-i", str(src), "-vf", "scale=1280:720:flags=lanczos,setsar=1",
             "-c:v", "libx264", "-preset", "veryfast", str(out)])
    assert p.returncode == 0, p.stderr[-400:]
    return out


def make_small_smooth_band(src, out):
    """A master with a SMOOTH top band of 14%: natural content, not a fill.

    Regression for the fps_h3-style master: a legitimate frame with a smooth
    (but structured) band under the gaussian-fill floor must never be
    refused. The band is blurred content, so it is not flat, not a plain
    bar and not a strip -- only its SIZE separates it from a real fill.
    """
    chain = ("[0:v]crop=203:360:218:0,scale=1080:1920:flags=lanczos,"
             "setsar=1,split[a][b];"
             "[a]crop=1080:270:0:0,gblur=sigma=16[top];"
             "[b]crop=1080:1650:0:270[body];"
             "[top][body]vstack=inputs=2,format=yuv420p[v]")
    p = run([FFMPEG, "-y", "-hide_banner", "-nostats", "-v", "error",
             "-i", str(src), "-filter_complex", chain, "-map", "[v]",
             "-c:v", "libx264", "-preset", "veryfast", str(out)])
    assert p.returncode == 0, p.stderr[-400:]
    return out


@unittest.skipUnless(have_ffmpeg(), "ffmpeg/ffprobe required")
class TestTextGates(unittest.TestCase):
    """Attempt detection: pure text, no pixels."""

    def test_gaussian_fill_named(self):
        v = QN.detect.scan_text("[0:v]gblur=sigma=30[v]")
        self.assertEqual([x["code"] for x in v], [QN.detect.GAUSSIAN_FILL])

    def test_edge_sampled_backdrop_named(self):
        v = QN.detect.scan_text(
            "[0:v]crop=4:ih:0:0,scale=1080:1920,boxblur=2:1[v]")
        self.assertIn(QN.detect.EDGE_SAMPLED_BACKDROP,
                      [x["code"] for x in v])

    def test_duplicated_blurred_strip_named(self):
        v = QN.detect.scan_text(
            "[0:v]split[a][b];[a]boxblur=8:1[s];[b]null[m];[s][m]vstack[v]")
        self.assertIn(QN.detect.DUPLICATED_BLURRED_STRIP,
                      [x["code"] for x in v])

    def test_blurred_mask_named(self):
        v = QN.detect.scan_text(
            "[0:v]gblur=sigma=10[bl];[1:v]null[m];[0:v][m]alphamerge[v]")
        self.assertIn(QN.detect.BLUR_MASK, [x["code"] for x in v])

    def test_letterbox_pad_named(self):
        v = QN.detect.scan_text("scale=1080:608,pad=1080:1920:0:656:black")
        self.assertIn(QN.detect.LETTERBOX_FILL, [x["code"] for x in v])

    def test_clean_scale_not_flagged(self):
        self.assertEqual(QN.detect.scan_text(
            "fps=30,scale=1080:1920,setsar=1"), [])

    def test_apad_audio_never_flagged(self):
        self.assertEqual(QN.detect.scan_text(
            "atrim=duration=12.0,apad=whole_dur=12.0,aresample=48000"), [])

    def test_scan_argv_finds_filter_complex(self):
        argv = ["ffmpeg", "-y", "-i", "a.mp4", "-filter_complex",
                "[0:v]gblur=sigma=20[v]", "-map", "[v]", "out.mp4"]
        v = QN.detect.scan_argv(argv)
        self.assertEqual([x["code"] for x in v], [QN.detect.GAUSSIAN_FILL])

    def test_scan_argv_clean_master_ok(self):
        argv = ["ffmpeg", "-y", "-i", "a.mp4", "-filter_complex",
                "[0:v]scale=1080:1920,setsar=1[v0];[v0]null[vout]",
                "-map", "[vout]", "-an", "out.mp4"]
        self.assertEqual(QN.detect.scan_argv(argv), [])

    def test_scan_plan_declares_fill(self):
        v = QN.detect.scan_plan({"segments": [{"src": "a.mp4",
                                               "fill_mode": "gaussian"}]})
        self.assertEqual([x["code"] for x in v], [QN.detect.FILL_ATTEMPT])

    def test_scan_plan_clean(self):
        self.assertEqual(QN.detect.scan_plan(
            {"width": 1080, "height": 1920, "segments": [{"src": "a.mp4"}]}),
            [])


@unittest.skipUnless(have_ffmpeg(), "ffmpeg/ffprobe required")
class TestGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="qc-no-blur-")
        cls.src = make_source(os.path.join(cls.d, "src.mp4"))
        cls.blur = make_blur_fill(cls.src, os.path.join(cls.d, "blur.mp4"))
        cls.edge = make_blur_fill(cls.src, os.path.join(cls.d, "edge.mp4"),
                                  bg="edge")
        cls.dup = make_dup_strip(cls.src, os.path.join(cls.d, "dup.mp4"))
        cls.ltr = make_letterbox(cls.src, os.path.join(cls.d, "ltr.mp4"))
        cls.clean = make_crop_in(cls.src, os.path.join(cls.d, "clean.mp4"))
        cls.plain = make_crop_in(cls.src, os.path.join(cls.d, "plain.mp4"),
                                 plain_top=True)
        cls.wide = make_plain_169(cls.src, os.path.join(cls.d, "wide.mp4"))
        cls.small = make_small_smooth_band(
            cls.src, os.path.join(cls.d, "small.mp4"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    # ---- the assembler refuses ----------------------------------------
    def test_assembler_refuses_gaussian_fill_argv(self):
        argv = ["ffmpeg", "-y", "-i", self.src, "-filter_complex",
                "[0:v]gblur=sigma=24,scale=1080:1920[v]", "-map", "[v]",
                "out.mp4"]
        g = AG.check_render(argv=argv, frame_scan=False)
        self.assertFalse(g["ok"])
        self.assertEqual(g["reason_code"], QN.detect.GAUSSIAN_FILL)
        self.assertIn("crop-in", g["reason"])
        self.assertIn("gblur", g["reason"])

    def test_assembler_refuses_declared_fill_plan(self):
        g = AG.check_render(plan={"fill_mode": "blur"}, frame_scan=False)
        self.assertFalse(g["ok"])
        self.assertEqual(g["reason_code"], QN.detect.FILL_ATTEMPT)

    def test_assembler_refuses_landed_fill_on_the_frame(self):
        g = AG.check_render(output=self.blur, expect_width=1080,
                            expect_height=1920)
        self.assertFalse(g["ok"])
        self.assertTrue(g["reason_code"] in QN.detect.VIOLATIONS)
        self.assertIn("crop-in", g["reason"])

    def test_assembler_refuses_edge_column_fill(self):
        g = AG.check_render(output=self.edge, expect_height=1920)
        self.assertFalse(g["ok"])
        self.assertTrue(g["reason_code"] in QN.detect.VIOLATIONS)

    def test_assembler_refuses_duplicated_blurred_strip(self):
        g = AG.check_render(output=self.dup, expect_height=1920)
        self.assertFalse(g["ok"])
        self.assertEqual(g["reason_code"],
                         QN.detect.DUPLICATED_BLURRED_STRIP)

    def test_assembler_refuses_letterbox(self):
        g = AG.check_render(output=self.ltr, expect_height=1920)
        self.assertFalse(g["ok"])
        self.assertTrue(g["reason_code"] in QN.detect.VIOLATIONS)

    def test_assembler_passes_clean_crop_in(self):
        g = AG.check_render(output=self.clean, expect_width=1080,
                            expect_height=1920)
        self.assertTrue(g["ok"], g)

    def test_assembler_passes_plain_top(self):
        """A PLAIN top band is legal; only a fill is refused."""
        g = AG.check_render(output=self.plain, expect_width=1080,
                            expect_height=1920)
        self.assertTrue(g["ok"], g)

    def test_assembler_passes_plain_169(self):
        g = AG.check_render(output=self.wide, expect_width=1280,
                            expect_height=720)
        self.assertTrue(g["ok"], g)

    def test_small_smooth_band_is_not_a_fill(self):
        """A ~14% smooth band is natural content (fps_h3-style master)."""
        g = AG.check_render(output=self.small, expect_height=1920)
        self.assertTrue(g["ok"], g)
        self.assertTrue(QG.check_deliverable(self.small,
                                             expect_height=1920)["ok"], g)

    def test_require_render_raises_with_the_violation(self):
        with self.assertRaises(AG.BlurFillRefused) as cm:
            AG.require_render(argv=["ffmpeg", "-vf", "gblur=sigma=9",
                                    "o.mp4"], frame_scan=False)
        self.assertIn("GAUSSIAN_FILL", str(cm.exception))
        self.assertIn("crop-in", str(cm.exception))

    # ---- the quality check refuses ------------------------------------
    def test_quality_check_fills_named(self):
        for path, want in ((self.blur, None), (self.edge, None),
                           (self.dup, QN.detect.DUPLICATED_BLURRED_STRIP),
                           (self.ltr, None)):
            g = QG.check_deliverable(path, expect_height=1920)
            self.assertFalse(g["ok"], path)
            if want:
                self.assertEqual(g["reason_code"], want, path)
            self.assertIn("crop-in", g["reason"], path)

    def test_quality_check_fails_short_of_full_height(self):
        g = QG.check_deliverable(self.ltr, expect_height=1920)
        self.assertFalse(g["ok"])
        self.assertTrue(any(v["code"] == QN.detect.FRAME_SHORT_OF_FULL_HEIGHT
                            for v in g["violations"]), g)

    def test_quality_check_passes_full_height(self):
        g = QG.check_deliverable(self.clean, expect_width=1080,
                                 expect_height=1920)
        self.assertTrue(g["ok"], g)

    def test_quality_check_passes_plain_top(self):
        g = QG.check_deliverable(self.plain, expect_width=1080,
                                 expect_height=1920)
        self.assertTrue(g["ok"], g)

    def test_require_no_fill_raises(self):
        with self.assertRaises(QG.BlurFillRefused) as cm:
            QG.require_no_fill(self.blur, expect_height=1920)
        text = str(cm.exception)
        self.assertIn("FILL", text.upper())
        self.assertIn("crop-in", text)
        self.assertIn(cm.exception.result["reason_code"], QN.detect.VIOLATIONS)

    # ---- the recovery path --------------------------------------------
    def test_crop_in_re_lip_sync_regenerates(self):
        """The filled clip is recovered by regenerating from the SOURCE."""
        fixed = os.path.join(self.d, "fixed.mp4")
        receipt = CR.regenerate(self.src, fixed, 1080, 1920)
        self.assertEqual(receipt["outcome"], "ok")
        self.assertEqual(receipt["reason_code"], "CROP_IN_REGENERATED")
        self.assertTrue(os.path.isfile(fixed))
        self.assertIn("re-lip-sync", receipt["next_step"])
        # no pad, no blur, no duplicate in the regeneration command
        self.assertNotIn("pad=", receipt["box"]["vf"])
        self.assertNotIn("blur", receipt["box"]["vf"])
        self.assertIn("crop=", receipt["box"]["vf"])
        self.assertIn("scale=1080:1920", receipt["box"]["vf"])
        # the regenerated clip passes BOTH gates
        self.assertTrue(QG.check_deliverable(fixed, expect_width=1080,
                                             expect_height=1920)["ok"])
        self.assertTrue(AG.check_render(output=fixed, expect_width=1080,
                                        expect_height=1920)["ok"])

    def test_regenerate_from_a_filled_clip_stays_refused(self):
        """Crop-in of an already-filled clip keeps the fill: fail closed."""
        fixed = os.path.join(self.d, "still-filled.mp4")
        with self.assertRaises(CR.CropRelipError) as cm:
            CR.regenerate(self.blur, fixed, 1080, 1920)
        self.assertEqual(cm.exception.code, "CROP_IN_STILL_FILLED")
        self.assertIn("FILL", str(cm.exception).upper())

    def test_crop_box_is_the_source_only(self):
        cw, ch, ox, oy = CR.crop_box(640, 360, 1080, 1920, "center")
        self.assertLessEqual(cw, 640)
        self.assertLessEqual(ch, 360)
        self.assertGreaterEqual(ox, 0)
        self.assertGreaterEqual(oy, 0)
        self.assertLessEqual(ox + cw, 640)
        self.assertLessEqual(oy + ch, 360)

    def test_regenerate_missing_source(self):
        with self.assertRaises(CR.CropRelipError) as cm:
            CR.regenerate(os.path.join(self.d, "nope.mp4"),
                          os.path.join(self.d, "x.mp4"))
        self.assertEqual(cm.exception.code, "MISSING_SOURCE")


class TestCropBoxPure(unittest.TestCase):
    def test_wide_source_crops_width(self):
        cw, ch, ox, oy = CR.crop_box(1920, 1080, 1080, 1920)
        self.assertEqual(ch, 1080)
        self.assertAlmostEqual(cw / float(ch), 1080 / 1920.0, delta=0.01)
        self.assertEqual(oy, 0)
        self.assertGreater(ox, 0)

    def test_already_916_keeps_everything(self):
        cw, ch, ox, oy = CR.crop_box(720, 1280, 1080, 1920)
        self.assertEqual((cw, ch, ox, oy), (720, 1280, 0, 0))

    def test_tall_source_crops_height_centered(self):
        cw, ch, ox, oy = CR.crop_box(540, 1920, 1080, 1920)
        self.assertEqual(cw, 540)
        self.assertAlmostEqual(cw / float(ch), 1080 / 1920.0, delta=0.01)
        self.assertGreater(oy, 0)

    def test_bias_top(self):
        _, _, _, oy = CR.crop_box(540, 1920, 1080, 1920, "top")
        self.assertEqual(oy, 0)

    def test_bad_bias(self):
        with self.assertRaises(CR.CropRelipError):
            CR.crop_box(640, 360, 1080, 1920, "blur")


if __name__ == "__main__":
    unittest.main(verbosity=2)
