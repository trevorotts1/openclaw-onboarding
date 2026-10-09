#!/usr/bin/env python3
"""Every path that writes a client-delivered video refuses MP3-in-MP4 audio.

One test per path: final assembler output, clip cutdowns, batch zip (captioned
ad + clean master), delivery checklist; plus the gate's AAC-LC / 48 kHz /
faststart rules. Fixtures are built with ffmpeg at test time.
Run: python3 core/test_delivery_gate_paths.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = os.path.dirname(os.path.abspath(__file__))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import delivery_audio as DA                          # noqa: E402
from delivery_fixture import HAVE_FFMPEG, make_video  # noqa: E402


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class GateRules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.p = os.path.join(self.d, "x.mp4")

    def test_good_file_passes(self):
        make_video(self.p)
        self.assertTrue(DA.check_delivery_audio(self.p)["ok"])

    def test_refuses_mp3(self):
        make_video(self.p, "libmp3lame")
        self.assertEqual(DA.check_delivery_audio(self.p)["reason_code"], DA.BAD_CODEC)

    def test_refuses_44k(self):
        make_video(self.p, rate=44100)
        self.assertEqual(DA.check_delivery_audio(self.p)["reason_code"], DA.BAD_RATE)

    def test_refuses_no_faststart(self):
        make_video(self.p, faststart=False)
        self.assertEqual(DA.check_delivery_audio(self.p)["reason_code"], DA.NO_FASTSTART)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class DeliveryPaths(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_assembler_output_with_mp3_audio_is_refused(self):
        import final_assembler.assembler as A
        clip = os.path.join(self.d, "clip0.mp4")      # moving 30 fps picture (dup-frame gate)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=s=64x64:r=30:d=3", "-pix_fmt", "yuv420p", clip], check=True)
        song = os.path.join(self.d, "song.mp3")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=3",
                        song], check=True)
        tl = os.path.join(self.d, "tl.json")
        import json
        with open(tl, "w") as f:
            json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30, "width": 64, "height": 64,
                       "song_path": song, "transition": "none",
                       "segments": [{"src": clip, "dur": 2.0}]}, f)
        A.lipsync_gate = lambda plan: None   # coverage is not under test here
        ok = A.assemble(tl, os.path.join(self.d, "ok.mp4"), base_dir=self.d)
        self.assertEqual(ok.get("outcome"), "ok", ok)          # control: real AAC passes
        saved = list(DA.AUDIO_OUT_ARGS)
        DA.AUDIO_OUT_ARGS[:] = ["-c:a", "libmp3lame", "-strict", "-2"]
        try:
            bad = A.assemble(tl, os.path.join(self.d, "bad.mp4"), base_dir=self.d)
        finally:
            DA.AUDIO_OUT_ARGS[:] = saved
        self.assertNotEqual(bad.get("outcome"), "ok", bad)
        self.assertIn(DA.BAD_CODEC, str(bad))

    def test_clip_cutdown_with_mp3_audio_is_refused(self):
        import clip_cutdown.clip_cutdown as CC

        def runner(argv, **k):
            make_video(argv[-1], "libmp3lame")
            return type("R", (), {"returncode": 0})()
        plan = {"name": "clip-60s", "start_s": 0, "duration_s": 1.0}
        with self.assertRaises(CC.ClipCutdownError) as cm:
            CC.run_clips("m.mp4", [plan], self.d, runner=runner)
        self.assertIn(DA.BAD_CODEC, str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.d, "clip-60s.mp4")))

    def test_clip_cutdown_argv_uses_delivery_audio_args(self):
        import clip_cutdown.clip_cutdown as CC
        a = CC.build_argv("m.mp4", {"name": "c", "start_s": 0, "duration_s": 5}, ".")
        self.assertEqual(a[a.index("-c:a") + 1], "aac")
        self.assertEqual(a[a.index("-ar") + 1], "48000")
        self.assertEqual(a[a.index("-movflags") + 1], "+faststart")

    def test_batch_zip_refuses_mp3_video(self):
        import batch_zip.batch_zip as bz
        good = make_video(os.path.join(self.d, "good.mp4"))
        bad = make_video(os.path.join(self.d, "bad.mp4"), "libmp3lame")
        song = os.path.join(self.d, "s.mp3")
        Path(song).write_bytes(b"\0" * 16)
        for cap, master in ((bad, good), (good, bad)):
            ad = {"author": "A", "title": "T", "captioned": cap, "clean_master": master,
                  "song_mp3": song}
            with self.assertRaises(bz.BatchZipError) as cm:
                bz.build_batch_zip("C", [ad], os.path.join(self.d, "b.zip"))
            self.assertEqual(cm.exception.code, DA.BAD_CODEC)

    def test_delivery_checklist_refuses_mp3_video(self):
        import delivery_checklist.delivery_checklist as dc
        bad = make_video(os.path.join(self.d, "bad.mp4"), "libmp3lame")
        song = os.path.join(self.d, "s.mp3")
        Path(song).write_bytes(b"\0" * 16)
        bat = dc.delivery_battery(self.d, song, "T", "A", video_path=bad)
        self.assertFalse(bat["pass"])
        self.assertIn("DELIVERY_AUDIO_AAC", bat["repair_scope"])


if __name__ == "__main__":
    unittest.main()
