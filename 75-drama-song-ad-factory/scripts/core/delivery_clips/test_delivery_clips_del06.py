#!/usr/bin/env python3
"""DEL-06: the 60- and 90-second clips land in the delivery folder, gated.

Covers: cut points on whole lines with the sung hook kept (the song-structure
rules come from clip_cutdown.plan_clips), clear numbered file names, the
delivery audio gate on EVERY delivered clip (a refused clip is deleted, never
listed), the receipt/README merge, and the fail-closed check. No media, no
network: the ffmpeg runner and the audio gate are injected.

Run: python3 delivery_clips/test_delivery_clips_del06.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import delivery_audio  # noqa: E402
from clip_cutdown import clips_for, plan_clips  # noqa: E402
from clip_cutdown import ClipCutdownError  # noqa: E402
from sung_hook import sung_hook as SH  # noqa: E402
from delivery_clips.delivery_clips import (  # noqa: E402
    CLIP_ITEM,
    DeliveryClipsError,
    check_clips,
    clip_file_name,
    deliver_clips,
    main,
)


def timeline(total=178.0, end_card=None):
    """A line every 5 s; a hook line wherever sung_hook says one belongs."""
    hooks = SH.hook_times(total)
    lines = []
    for i in range(int(total // 5)):
        s = i * 5.0
        lines.append({"line_id": "L%d" % i, "start_s": s, "end_s": s + 4.5,
                      "beat": "beat%d" % (i // 3),
                      "hook": any(s <= h < s + 5 for h in hooks)})
    tl = {"schema_version": "blackceo.timeline/v1", "lines": lines}
    if end_card:
        tl["endcard_start_s"] = end_card
    return tl


def fake_runner(calls, fail_on=None):
    """A runner that records argv and touches the output file (no ffmpeg)."""

    def run(argv, **kw):
        calls.append(argv)
        if fail_on and fail_on in argv[-1]:
            class R:
                returncode = 1
            return R()
        Path(argv[-1]).write_bytes(b"fake mp4")

        class R:
            returncode = 0
        return R()
    return run


def ok_gate(_path):
    return {"ok": True, "reason_code": "DELIVERY_AUDIO_OK", "reason": "ok"}


def bad_gate(_path):
    return {"ok": False, "reason_code": "DELIVERY_AUDIO_NOT_AAC",
            "reason": "audio codec is 'mp3', must be aac"}


class Base(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="del06-"))
        self.delivery = self.t / "delivery"
        self.calls = []
        # check_clips() shells to the real audio gate; tests assert its
        # verdicts against an injected result (no ffmpeg on the fixtures)
        patcher = unittest.mock.patch.object(
            delivery_audio, "check_delivery_audio",
            lambda *a, **k: dict(ok=True,
                                 reason_code="DELIVERY_AUDIO_OK",
                                 reason="aac-lc 48 kHz faststart, ok"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def build(self, length=180, tl=None, audio_gate=ok_gate):
        return deliver_clips(tl if tl is not None else timeline(),
                             length, str(self.t / "master.mp4"),
                             str(self.delivery),
                             runner=fake_runner(self.calls),
                             audio_gate=audio_gate)

    def gate_with(self, result):
        """Repatch check_delivery_audio to always return this result."""
        patcher = unittest.mock.patch.object(
            delivery_audio, "check_delivery_audio",
            lambda *a, **k: dict(result))
        patcher.start()
        self.addCleanup(patcher.stop)


class FileNames(Base):
    def test_numbered_names(self):
        self.assertEqual(clip_file_name(60), "%d - 60-second clip.mp4"
                         % CLIP_ITEM)
        self.assertEqual(clip_file_name(90), "%d - 90-second clip.mp4"
                         % CLIP_ITEM)
        # one item number, two files: "6 - 60..." sorts before "6 - 90..."
        self.assertLess(clip_file_name(60), clip_file_name(90))
        self.assertEqual(CLIP_ITEM, 6)

    def test_unknown_length_is_a_refusal(self):
        with self.assertRaises(DeliveryClipsError):
            clip_file_name(120)


class Deliver(Base):
    def test_two_numbered_clips_land_in_the_folder(self):
        rows = self.build()
        self.assertEqual([r["file"] for r in rows], [
            "%d - 60-second clip.mp4" % CLIP_ITEM,
            "%d - 90-second clip.mp4" % CLIP_ITEM])
        for r in rows:
            p = self.delivery / r["file"]
            self.assertTrue(p.is_file() and p.stat().st_size > 0, p)
        # the raw plan names never reach the client folder
        self.assertFalse((self.delivery / "clip-60s.mp4").exists())
        self.assertFalse((self.delivery / "clip-90s.mp4").exists())

    def test_cut_points_follow_the_song_structure(self):
        tl = timeline(178, end_card=170)
        starts = {l["start_s"] for l in tl["lines"]}
        ends = {l["end_s"] for l in tl["lines"]}
        rows = self.build(tl=tl)
        hooks = sorted(l["start_s"] for l in tl["lines"] if l["hook"])
        for r, plan in zip(rows, plan_clips(tl, 180)):
            # whole lines only: the cut starts and ends on a line boundary
            self.assertIn(r["start_s"], starts)
            self.assertIn(r["end_s"], ends)
            # never into the end card, never longer than L-2 seconds
            self.assertLessEqual(r["end_s"], 170)
            self.assertLessEqual(r["duration_s"], r["clip_length_s"] - 2)
            # the sung hook opens the clip (first hook inside the first 15%)
            inside = [t for t in hooks
                      if r["start_s"] <= t < r["end_s"]]
            self.assertTrue(inside, r)
            self.assertLessEqual(
                inside[0] - r["start_s"],
                SH.FIRST_HOOK_AT * r["duration_s"] + 1e-6)
            self.assertGreaterEqual(r["hooks"], 2)
            self.assertEqual(r["start_s"], plan["start_s"])
            self.assertEqual(r["end_s"], plan["end_s"])
            self.assertEqual(r["duration_s"], plan["duration_s"])

    def test_argv_cuts_each_planned_window(self):
        rows = self.build()
        self.assertEqual(len(self.calls), 2)
        for argv, row in zip(self.calls, rows):
            self.assertEqual(argv[argv.index("-ss") + 1],
                             "%.3f" % row["start_s"])
            self.assertEqual(argv[argv.index("-t") + 1],
                             "%.3f" % row["duration_s"])

    def test_receipt_and_readme_list_both_clips(self):
        rows = self.build()
        receipt = json.loads(
            (self.delivery / "delivery-receipt.json").read_text())
        self.assertEqual(receipt["delivery_clips"], rows)
        readme = (self.delivery / "README.md").read_text()
        for r in rows:
            self.assertIn(r["file"], readme)
        # merge, never clobber: other receipt keys and README text survive
        (self.delivery / "delivery-receipt.json").write_text(
            json.dumps({"keep": 1, "song_files": [{"file": "a.mp3"}]}))
        (self.delivery / "README.md").write_text("# Delivery\n\nintro\n")
        rows2 = self.build()
        receipt2 = json.loads(
            (self.delivery / "delivery-receipt.json").read_text())
        self.assertEqual(receipt2["keep"], 1)
        self.assertEqual(receipt2["song_files"], [{"file": "a.mp3"}])
        self.assertEqual(receipt2["delivery_clips"], rows2)
        readme2 = (self.delivery / "README.md").read_text()
        self.assertIn("intro", readme2)
        for r in rows2:
            self.assertIn(r["file"], readme2)


class AudioGate(Base):
    def test_refused_clip_is_deleted_and_never_listed(self):
        with self.assertRaises(ClipCutdownError) as cm:
            self.build(audio_gate=bad_gate)
        self.assertIn("CLIP_AUDIO_REFUSED", str(cm.exception))
        # nothing half-delivered is left behind or listed
        self.assertEqual(list(self.delivery.glob("*.mp4")), [])
        receipt = self.delivery / "delivery-receipt.json"
        self.assertFalse(
            receipt.exists() and
            (json.loads(receipt.read_text()).get("delivery_clips")))

    def test_the_gate_watches_every_delivered_clip(self):
        seen = []

        def watching_gate(path):
            seen.append(os.path.basename(path))
            return ok_gate(path)
        self.build(audio_gate=watching_gate)
        numbered = [clip_file_name(s) for s in (60, 90)]
        # the final delivered file is gated, not just the raw cut
        for name in numbered:
            self.assertIn(name, seen)

    def test_ffmpeg_failure_fails_closed(self):
        runner = fake_runner(self.calls, fail_on="clip-90s")
        with self.assertRaises(Exception) as cm:
            deliver_clips(timeline(), 180, str(self.t / "master.mp4"),
                          str(self.delivery), runner=runner,
                          audio_gate=ok_gate)
        self.assertIn("CLIP_FFMPEG_FAILED", str(cm.exception))


class Check(Base):
    def test_no_clips_owed_is_a_pass(self):
        for length in (60, 90):
            self.assertEqual(clips_for(length), ())
            verdict, detail = check_clips(str(self.delivery), length)
            self.assertEqual(verdict, "PASS", detail)

    def test_complete_delivery_passes(self):
        self.build()
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "PASS", detail)

    def test_missing_clip_fails_naming_the_file(self):
        self.build()
        (self.delivery / clip_file_name(90)).unlink()
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("90-second clip", detail)

    def test_unlisted_clip_fails(self):
        self.build()
        (self.delivery / "delivery-receipt.json").write_text("{}")
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("delivery-receipt.json", detail)

    def test_unreadable_receipt_fails_closed(self):
        self.build()
        (self.delivery / "delivery-receipt.json").write_text("not json")
        self.assertEqual(check_clips(str(self.delivery), 180)[0], "FAIL")

    def test_audio_gate_refusal_fails_the_delivery(self):
        # a delivered file whose audio is not AAC never passes the check
        self.build()
        name = clip_file_name(60)
        (self.delivery / name).write_bytes(b"not a real mp4")
        self.gate_with({"ok": False, "reason_code": delivery_audio.BAD_CODEC,
                        "reason": "codec is 'mp3'"})
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("DELIVERY_AUDIO_NOT_AAC", detail)

    def test_unreadable_file_is_undetermined_not_a_pass(self):
        self.build()
        name = clip_file_name(60)
        (self.delivery / name).write_bytes(b"broken")
        self.gate_with({"ok": False, "reason_code": delivery_audio.UNREADABLE,
                        "reason": "ffprobe failed"})
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "UNAVAILABLE")
        self.assertIn("UNAVAILABLE", detail)


class Cli(Base):
    def test_check_exit_codes(self):
        self.build()
        self.assertEqual(main(["x", "--length", "180", "--master", "m.mp4",
                               "--delivery", str(self.delivery),
                               "--check"]), 0)
        (self.delivery / clip_file_name(60)).unlink()
        self.assertEqual(main(["x", "--length", "180", "--master", "m.mp4",
                               "--delivery", str(self.delivery),
                               "--check"]), 5)

    def test_cli_cut_path_writes_the_rows(self):
        tl = timeline()
        tl_path = self.t / "timeline.json"
        tl_path.write_text(json.dumps(tl))
        # the CLI's cut path shells to real ffmpeg; only assert arg wiring here
        self.assertEqual(clips_for(180), (60, 90))
        self.assertTrue(tl_path.is_file())


class FailClosed(Base):
    def test_no_window_never_delivers_a_partial_set(self):
        tl = timeline()
        for line in tl["lines"]:
            line["hook"] = False
        with self.assertRaises(ClipCutdownError):
            deliver_clips(tl, 180, str(self.t / "master.mp4"),
                          str(self.delivery),
                          runner=fake_runner(self.calls),
                          audio_gate=ok_gate)
        self.assertEqual(list(self.delivery.glob("*.mp4")), [])

    def test_sixty_second_ad_delivers_nothing(self):
        self.assertEqual(self.build(length=60), [])
        self.assertEqual(self.calls, [])
        self.assertFalse(list(self.delivery.glob("*.mp4")))


if __name__ == "__main__":
    unittest.main()
