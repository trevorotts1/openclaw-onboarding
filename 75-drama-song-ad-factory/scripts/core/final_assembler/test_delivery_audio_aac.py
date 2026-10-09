"""FU-AAC-FINAL-MUX: delivered video audio is AAC 48 kHz + faststart, and the
delivery gate refuses mp3-in-mp4 and silent aac. Fixtures built with ffmpeg at
test time (nothing binary committed). Run: python3 test_delivery_audio_aac.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import delivery_audio as DA                      # noqa: E402
import final_assembler.assembler as A            # noqa: E402

HAVE = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _plan():
    return A.plan_timeline({
        "schema_version": A.TIMELINE_SCHEMA, "fps": 30, "width": 320,
        "height": 240, "song_path": "song.mp3", "transition": "none",
        "segments": [{"src": "clip0.mp4", "dur": 2.0}]}, ".")


class TestArgv(unittest.TestCase):
    def test_assembler_aac_48k_faststart(self):
        a = A.build_argv(_plan(), "out.mp4")
        i = a.index("-c:a")
        self.assertEqual(a[i + 1], "aac")
        self.assertEqual(a[a.index("-ar") + 1], "48000")
        self.assertIn("256k", a)
        self.assertEqual(a[a.index("-movflags") + 1], "+faststart")
        self.assertNotIn("copy", a)


def _mk(path, acodec, src):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:d=1:r=10", "-f", "lavfi", "-i", src,
                    "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", acodec, "-ar", "48000", "-strict", "-2",
                    "-movflags", "+faststart", path], check=True)


@unittest.skipUnless(HAVE, "ffmpeg not installed")
class TestGate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _gate(self, acodec, src):
        p = os.path.join(self.d, "x.mp4")
        _mk(p, acodec, src)
        return DA.check_delivery_audio(p)

    def test_passes_real_aac(self):
        r = self._gate("aac", "sine=f=440:d=1")
        self.assertTrue(r["ok"], r)

    def test_refuses_mp3_in_mp4(self):
        r = self._gate("libmp3lame", "sine=f=440:d=1")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], DA.BAD_CODEC)

    def test_refuses_silent_aac(self):
        r = self._gate("aac", "anullsrc=r=48000:cl=stereo:d=1")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], DA.SILENT)


if __name__ == "__main__":
    unittest.main()
