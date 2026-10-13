"""DEL-05 cleanup (leak L4): a render that DIES deletes what it already wrote.

``build_video_delivery`` renders the captioned file FIRST and the clean one
SECOND, and the delete-both cleanup (``cap_path`` / ``clean_path``) only ran
after the audio gate -- i.e. only when BOTH renders came back. So a clean
render that failed left ``05 - Video Captioned.mp4`` plus whatever partial
file ffmpeg had written of ``05 - Video Clean.mp4`` sitting in the client's
delivery folder.

The failure path now holds the same rule as the gate below it: ANY exception
out of the render sequence unlinks both delivery names (``missing_ok``) and
re-raises. A failed render ships NOTHING -- all or nothing, fail closed.

No ffmpeg here: both renders are stubbed, so this is a pure stdlib test of
the failure path. The success path and the real audio gate stay covered by
``test_video_delivery_del05.py``.

Run: python3 core/delivery_variants/test_video_delivery_cleanup.py
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from delivery_variants import video_delivery as vd  # noqa: E402

AD = "Sample Story"
LINES = ["She kept the kitchen spotless", "for thirty years."]
CUES = [{"text": LINES[0], "start": 0.0, "end": 1.0},
        {"text": LINES[1], "start": 1.0, "end": 2.0}]
GEO = {"width": 320, "height": 568, "duration_s": 2.0}


class RenderDying(unittest.TestCase):
    """The second render dies AFTER the captioned one has already landed."""

    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="del05-cleanup-"))
        self.addCleanup(shutil.rmtree, self.t, ignore_errors=True)
        self.master = self.t / "master.mp4"
        # Presence and non-zero size only: probe is stubbed, ffmpeg never runs.
        self.master.write_bytes(b"\x00" * 64)
        self.d = self.t / "delivery"

        self._real_probe = vd.probe
        vd.probe = lambda path, ffprobe="ffprobe": dict(GEO)
        self.addCleanup(setattr, vd, "probe", self._real_probe)

        self._real_render = vd._render

    def stub_renders(self, die_on=2):
        """Record each render's job name and whether the pair was on disk.

        Render 1 writes the finished captioned file; render N writes a
        partial file and raises. ``self.at_death`` snapshots the delivery
        folder right BEFORE the raise, so the test can prove the leak was
        real (the captioned file was already there) and not that nothing was
        ever written.
        """
        jobs, self.at_death = [], {}

        def fake_render(argv, job, cwd=None):
            jobs.append(job)
            # Both argv builders put the output path last.
            Path(argv[-1]).write_bytes(b"captioned" if len(jobs) == 1
                                       else b"partial clean file")
            if len(jobs) == die_on:
                self.at_death["mp4s"] = sorted(p.name
                                               for p in self.d.glob("*.mp4"))
                raise vd.VideoDeliveryError("RENDER_FAILED",
                                            "clean render died",
                                            str(argv[-1]))

        self._real_render = vd._render
        vd._render = fake_render
        self.addCleanup(setattr, vd, "_render", self._real_render)
        return jobs

    def build(self):
        return vd.build_video_delivery(self.master, self.d, AD, LINES,
                                       cues=CUES, provenance="measured")

    def test_a_dying_clean_render_deletes_the_captioned_file_too(self):
        jobs = self.stub_renders()
        with self.assertRaises(vd.VideoDeliveryError) as cm:
            self.build()

        self.assertEqual(cm.exception.code, "RENDER_FAILED")
        self.assertEqual(jobs, ["video-delivery-captioned",
                                "video-delivery-clean"])
        # The leak was real: the finished captioned file HAD landed on disk.
        self.assertEqual(self.at_death["mp4s"],
                         ["05 - Video Captioned.mp4", "05 - Video Clean.mp4"])
        self.assertEqual(list(self.d.glob("*.mp4")), [],
                         "a failed render ships nothing: the captioned file "
                         "and the partial clean file are both deleted")
        self.assertEqual(list(self.d.glob("*")), [],
                         "no half-written delivery leftover of any kind")

    def test_the_exception_still_propagates_unchanged(self):
        """Cleanup must not swallow or replace the failure it cleans up."""
        self.stub_renders()
        with self.assertRaises(vd.VideoDeliveryError) as cm:
            self.build()
        self.assertEqual(cm.exception.code, "RENDER_FAILED")
        self.assertIn("clean render died", str(cm.exception))

    def test_a_dying_captioned_render_leaves_nothing_behind_either(self):
        self.stub_renders(die_on=1)
        with self.assertRaises(vd.VideoDeliveryError):
            self.build()
        self.assertEqual(list(self.d.glob("*.mp4")), [])

    def test_a_plain_runtime_error_is_cleaned_up_and_propagated(self):
        """Any exception, not only this module's own error type."""
        def explode(argv, job, cwd=None):
            Path(argv[-1]).write_bytes(b"captioned")
            raise RuntimeError("ffmpeg was killed")
        vd._render = explode
        self.addCleanup(setattr, vd, "_render", self._real_render)
        with self.assertRaises(RuntimeError):
            self.build()
        self.assertEqual(list(self.d.glob("*.mp4")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
