"""Every code path that writes a client-delivered video refuses MP3 audio.

Trevor's complaint: "I DON'T HEAR ANY AUDIO" (QuickTime plays MP3-in-MP4
silent). One test per delivery path: assembler master, clip cutdowns, batch
zip, delivery battery; plus the gate itself (44.1 kHz and non-faststart are
refused). Fixtures are built with ffmpeg at test time.
Run: python3 test_delivery_gate_paths.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = os.path.dirname(os.path.abspath(__file__))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import delivery_audio as DA                          # noqa: E402
import final_assembler.assembler as A                # noqa: E402
from batch_zip import batch_zip as BZ                # noqa: E402
from clip_cutdown import clip_cutdown as CC          # noqa: E402
from delivery_checklist import delivery_checklist as DC  # noqa: E402

HAVE = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
V = ["-f", "lavfi", "-i", "testsrc2=s=64x64:d=2:r=30"]
SINE = ["-f", "lavfi", "-i", "sine=f=440:d=2"]


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def mk_video(path, audio, faststart=True):
    """audio: 'good' (AAC-LC 48k), 'mp3', 'aac44' (44.1 kHz)."""
    if audio == "mp3":
        a = ["-c:a", "libmp3lame"]
    elif audio == "aac44":
        a = ["-c:a", "aac", "-ar", "44100"]
    else:
        a = list(DA.AUDIO_OUT_ARGS)
    ff(*V, *SINE, "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", *a,
       *(DA.FASTSTART_ARGS if faststart else []), "-strict", "-2", str(path))


@unittest.skipUnless(HAVE, "ffmpeg not installed")
class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def p(self, name):
        return os.path.join(self.d, name)


class TestGateStrictness(Base):
    def test_good_passes(self):
        mk_video(self.p("g.mp4"), "good")
        self.assertTrue(DA.check_delivery_audio(self.p("g.mp4"))["ok"])

    def test_mp3_refused(self):
        mk_video(self.p("m.mp4"), "mp3")
        self.assertEqual(DA.check_delivery_audio(self.p("m.mp4"))["reason_code"],
                         DA.BAD_CODEC)

    def test_44k_refused(self):
        mk_video(self.p("r.mp4"), "aac44")
        self.assertEqual(DA.check_delivery_audio(self.p("r.mp4"))["reason_code"],
                         DA.BAD_RATE)

    def test_no_faststart_refused(self):
        mk_video(self.p("f.mp4"), "good", faststart=False)
        self.assertEqual(DA.check_delivery_audio(self.p("f.mp4"))["reason_code"],
                         DA.NO_FASTSTART)


class TestAssemblerPath(Base):
    def test_assembler_refuses_mp3_master(self):
        mk_video(self.p("clip0.mp4"), "good")
        ff(*SINE, "-c:a", "libmp3lame", self.p("song.mp3"))
        tl = self.p("timeline.json")
        with open(tl, "w") as fh:
            json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                       "width": 64, "height": 64, "song_path": "song.mp3",
                       "transition": "none",
                       "segments": [{"src": "clip0.mp4", "dur": 2.0}]}, fh)
        real = A._run

        def mp3_run(cmd, timeout=600):
            r = real(cmd, timeout)
            out = str(cmd[-1])
            tmp = out + ".tmp.mp4"
            ff("-i", out, "-c:v", "copy", "-c:a", "libmp3lame", tmp)
            os.replace(tmp, out)
            return r
        # the lip-sync coverage gates are unrelated to audio: stub them out
        saved = {n: getattr(A, n) for n in ("_run", "lipsync_gate", "face_speaks_gate")}
        A._run = mp3_run
        A.lipsync_gate = A.face_speaks_gate = lambda plan: None
        try:
            rec = A.assemble(tl, self.p("out.mp4"))
        finally:
            for n, f in saved.items():
                setattr(A, n, f)
        self.assertEqual(rec["outcome"], "error", rec)
        self.assertEqual(rec["reason_code"], DA.BAD_CODEC)


class TestClipCutdownPath(Base):
    def test_clips_refuse_mp3(self):
        mk_video(self.p("master.mp4"), "good")
        plans = [{"name": "clip-60s", "start_s": 0, "duration_s": 2.0}]

        def mp3_runner(argv, **kw):
            mk_video(argv[-1], "mp3")
            return subprocess.CompletedProcess(argv, 0)
        with self.assertRaises(CC.ClipCutdownError) as cm:
            CC.run_clips(self.p("master.mp4"), plans, self.d, runner=mp3_runner)
        self.assertIn("CLIP_AUDIO_REFUSED", str(cm.exception))
        self.assertFalse(os.path.exists(self.p("clip-60s.mp4")))

    def test_real_clip_is_aac_lc_48k_faststart(self):
        mk_video(self.p("master.mp4"), "good")
        plans = [{"name": "clip-60s", "start_s": 0, "duration_s": 2.0}]
        out = CC.run_clips(self.p("master.mp4"), plans, self.d)
        self.assertTrue(DA.check_delivery_audio(out[0])["ok"])


class TestBatchZipPath(Base):
    def _ads(self, cap_audio):
        cap, master, song = (Path(self.p(n)) for n in
                             ("cap.mp4", "master.mp4", "song.mp3"))
        mk_video(cap, cap_audio)
        mk_video(master, "good")
        song.write_bytes(b"\0" * 16)
        return [{"author": "A B", "title": "T", "captioned": cap,
                 "clean_master": master, "song_mp3": song}]

    def test_zip_refuses_mp3_captioned(self):
        with self.assertRaises(BZ.BatchZipError) as cm:
            BZ.build_batch_zip("C", self._ads("mp3"), self.p("b.zip"))
        self.assertEqual(cm.exception.code, "DELIVERY_AUDIO_REFUSED")
        self.assertFalse(os.path.exists(self.p("b.zip")))

    def test_zip_accepts_good(self):
        BZ.build_batch_zip("C", self._ads("good"), self.p("b.zip"))
        self.assertTrue(os.path.exists(self.p("b.zip")))


class TestDeliveryBatteryPath(Base):
    def test_battery_fails_on_mp3_video(self):
        mk_video(self.p("v.mp4"), "mp3")
        orig = DC.check_song_mp3
        DC.check_song_mp3 = lambda *a, **k: []
        try:
            bat = DC.delivery_battery(self.d, "x", "T", "A",
                                      video_path=self.p("v.mp4"))
        finally:
            DC.check_song_mp3 = orig
        self.assertFalse(bat["pass"])
        self.assertIn("DELIVERY_AUDIO_AAC", bat["repair_scope"])


if __name__ == "__main__":
    unittest.main()
