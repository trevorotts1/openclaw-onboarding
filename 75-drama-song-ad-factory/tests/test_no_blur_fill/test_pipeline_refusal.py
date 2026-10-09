#!/usr/bin/env python3
"""DEL-14 pipeline proof: a blur-fill render attempt fails red, crop-in passes.

Feeds the forbidden path through the pipeline and the gates around it:
  1. the render attempt itself (the gblur + mask chain, run on purpose) is
     measured short of full height and refused by no_blur_fill.verify_output;
  2. the QC gate refuses the attempt's PASS record (FILL_CLAIM_MEASURED);
  3. the source-level scanner refuses a core script carrying the chain
     (the spot-2 incident was exactly that, planted here as the control);
  4. build_argv never emits a fill for any source shape;
  5. the crop-in path renders full height, passes verify_output and passes
     the QC gate.

ffmpeg/ffprobe-backed cases skip with a stated reason when the binaries are
absent; every non-media case runs everywhere, including the CI runner.
Owner order (Trevor, 2026-10-09): full height by crop-in only, never blur fill.

Run: python3 tests/test_no_blur_fill/test_pipeline_refusal.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

qc_gate = common.qc_gate
SF = common.SF


class BuildArgvNeverFills(unittest.TestCase):
    def test_no_fill_token_in_any_render_argv(self):
        """Every planned render argv is scale+crop only, for every shape."""
        for label, (w, h), kw in common.BUILD_ARGV_CASES:
            argv = SF.build_argv("in.mp4", "out.mp4", w, h, **kw)
            line = " ".join(argv).lower()
            for token in common.FILL_TOKENS_IN_ARGV:
                self.assertNotIn(token, line,
                                 "%s: %s carries %s" % (label, line, token))
            self.assertIn("scale=", line, label)
            self.assertIn("crop=", line, label)

    def test_cover_zoom_is_uniform_and_never_stretches(self):
        import re
        plan = SF.classify(1920, 1080)
        self.assertEqual(plan["fit"], SF.NO_FILL)
        self.assertEqual(plan["zoom"], 1920.0 / 1080.0)
        argv = SF.build_argv("in.mp4", "out.mp4", 1920, 1080)
        vf = argv[argv.index("-vf") + 1]
        m = re.search(r"scale=(\d+):(\d+)", vf)
        self.assertIsNotNone(m, vf)
        sw, sh = int(m.group(1)), int(m.group(2))
        # one uniform scale target (never a forced 1080x1920, which would
        # squash 16:9), then a crop to exactly the full-height frame
        self.assertAlmostEqual(sw / float(sh), 1920.0 / 1080.0, places=3)
        self.assertGreaterEqual(sw, 1080)
        self.assertGreaterEqual(sh, 1920)
        self.assertIn("crop=1080:1920:", vf)

    def test_out_of_range_center_x_is_refused(self):
        with self.assertRaises(ValueError):
            SF.build_argv("in.mp4", "out.mp4", 720, 1280, center_x=1.5)
        with self.assertRaises(ValueError):
            SF.build_argv("in.mp4", "out.mp4", 720, 1280, center_x=-0.1)


class ScanRefusesCoreFill(unittest.TestCase):
    def test_shipped_core_carries_no_fill(self):
        res = SF.scan_core_scripts(common.CORE)
        self.assertEqual(res["outcome"], "ok", res)
        self.assertEqual(res["hits"], [])

    def test_planted_incident_script_is_refused(self):
        """NC: plant the spot-2 chain in a core copy; the scanner must go
        red naming the file and the marker."""
        with tempfile.TemporaryDirectory(prefix="PKG-05-U3-scan-") as tmp:
            core = os.path.join(tmp, "core")
            os.makedirs(os.path.join(core, "vendor"))
            clean = os.path.join(core, "ok_mod.py")
            with open(clean, "w", encoding="utf-8") as fh:
                fh.write("def ok():\n    return 1\n")
            bad = os.path.join(core, "vendor", "hand_render.py")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("# the spot-2 chain, verbatim shape\n"
                         "vf = ('[bb]gblur=sigma=30:steps=3[bl];'\n"
                         "      '[bar][mk]alphamerge[bm]')\n")
            res = SF.scan_core_scripts(core)
            self.assertEqual(res["outcome"], "rejected", res)
            self.assertEqual(res["reason_code"], "BLUR_FILL_IN_CORE")
            self.assertTrue(any("hand_render.py" in h[0] for h in res["hits"]),
                            res)
            self.assertIn("crop-in", res["next_action"])


@unittest.skipUnless(common.have_media(),
                     "ffmpeg/ffprobe absent: media cases stated, not faked")
class RenderPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="PKG-05-U3-render-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.source = common.make_source(
            os.path.join(self.tmp, "src_720x1280.mp4"), 720, 1280)

    def _probe(self, path):
        proc = subprocess.run(
            [common.FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
             str(path)],
            capture_output=True, text=True)
        w, h = proc.stdout.strip().split("x")[:2]
        return int(w), int(h)

    def test_blur_fill_render_attempt_is_red_end_to_end(self):
        """THE RED CASE: produce the forbidden renders and prove the
        pipeline refuses them.

        The trap first: a blur fill lands at 1080x1920, so it *looks* full
        height and geometry alone cannot catch it (that is exactly why the
        spot-2 incident shipped). The rotation fill is caught by measurement
        (its stored frames are not full height, and an upright file with a
        stray rotation tag is refused as ROTATED_FILL). Both attempts are
        also refused by the fill-claim scanner and the QC gate, and neither
        can be produced through build_argv at all.
        """
        filled = os.path.join(self.tmp, "blur_fill_master.mp4")
        proc = common.render_blur_fill_attempt(self.source, filled)
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-400:])
        self.assertTrue(os.path.exists(filled))

        # 0. the trap: full-height geometry, indistinguishable by size
        self.assertEqual(self._probe(filled), (1080, 1920))
        self.assertEqual(SF.verify_output(filled, ffprobe=common.FFPROBE)
                         ["outcome"], "ok")

        # 0b. the rotation fill: sideways frames + rotation tag. Stored size
        #     is not full height, so measurement refuses it outright.
        rot_fill = os.path.join(self.tmp, "rotation_fill.mp4")
        proc = common.render_rotation_fill_attempt(self.source, rot_fill)
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-400:])
        verdict = SF.verify_output(rot_fill, ffprobe=common.FFPROBE)
        self.assertEqual(verdict["outcome"], "rejected", verdict)
        self.assertEqual(verdict["reason_code"], "OUTPUT_NOT_FULL_HEIGHT")

        # 0c. an upright full-height file wearing the same rotation tag is
        #     refused as ROTATED_FILL (player would show it sideways)
        upright = os.path.join(self.tmp, "upright.mp4")
        proc = common.SF.render(self.source, upright,
                                ffprobe=common.FFPROBE)
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-400:])
        tagged = os.path.join(self.tmp, "upright_tagged.mp4")
        proc = common.add_display_rotation(upright, tagged, 90)
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-400:])
        verdict = SF.verify_output(tagged, ffprobe=common.FFPROBE)
        self.assertEqual(verdict["outcome"], "rejected", verdict)
        self.assertEqual(verdict["reason_code"], "ROTATED_FILL", verdict)

        # 1. the fill-claim scanner names the chain
        chain = ("[bb]gblur=sigma=30:steps=3[bl];[bar][mk]alphamerge[bm];"
                 "pad=1080:1920:0:240")
        summary = "render chain kept: %s (full height via fill)" % chain
        self.assertTrue(qc_gate.fill_claim(summary), summary)
        self.assertTrue(SF.fill_claim(summary))

        # 2. the QC gate refuses the PASS record that would ship it
        res = common.gate([common.qc_record(summary)])
        self.assertEqual(res["gate"], "BLOCKED", res)
        self.assertIn("FILL_CLAIM_MEASURED", common.codes(res))
        self.assertEqual(res["repair_scope"], [common.RECORD_ID])

        # 3. the render path cannot produce it: build_argv for the same
        #    source carries scale+crop only
        argv = SF.build_argv("in.mp4", "out.mp4", 720, 1280)
        line = " ".join(argv).lower()
        for token in common.FILL_TOKENS_IN_ARGV:
            self.assertNotIn(token, line, line)
        self.assertIn("crop=", line)

    def test_crop_in_render_is_green_end_to_end(self):
        """THE GREEN CASE: the crop-in path reaches full height and passes
        every gate around it."""
        out = os.path.join(self.tmp, "crop_in_master.mp4")
        proc = common.SF.render(self.source, out, ffprobe=common.FFPROBE)
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-400:])
        self.assertEqual(self._probe(out), (1080, 1920))

        verdict = SF.verify_output(out, ffprobe=common.FFPROBE)
        self.assertEqual(verdict["outcome"], "ok", verdict)
        self.assertEqual(verdict["fit"], SF.NO_FILL)
        self.assertEqual(verdict["rotation_deg"], 0)

        env = SF.inspect(out, ffprobe=common.FFPROBE)
        self.assertEqual(env["outcome"], "ok", env)
        self.assertEqual(env["fit"], SF.NO_FILL)

        res = common.gate([common.qc_record(
            "video_still_fill 1.0.0: CROP_IN_OK (fit=crop-in, zoom=1.500, "
            "full height 1080x1920)")])
        self.assertEqual(res["gate"], "PASS", res)


if __name__ == "__main__":
    unittest.main(verbosity=2)
