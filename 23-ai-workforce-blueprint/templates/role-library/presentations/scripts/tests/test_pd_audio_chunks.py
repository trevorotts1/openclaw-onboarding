#!/usr/bin/env python3
"""test_pd_audio_chunks.py — PD-307: the webinar video reads its own audio chunks,
a timing failure is an error, and the shared media ledger is written under a lock.

Before PD-307:
  * `synthesize_full_speech.py` wrote every synthesis into one fixed
    `<out_dir>/_audio_chunks_full`, so two syntheses in one delivery folder
    overwrote each other's chunks and `build_webinar_video.py` could not tell
    which audio the chunks belonged to;
  * `build_webinar_video.build_timing` printed the timing cross-check verdict and
    carried on into the render whatever it said, so a DRIFT track was rendered;
  * `_record_webinar_in_ledger` did a bare read-modify-write of
    `working/checkpoints/media_library.json`, the same file `ghl_media_push`
    writes under an exclusive flock — two writers, one lost.

Offline only: no network, no ffmpeg, no Fish key, no render. The timing module is
a stub in `sys.modules`, and the ledger race is driven by two local processes.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT_SYNTH = SCRIPTS / "synthesize_full_speech.py"
SCRIPT_VIDEO = SCRIPTS / "build_webinar_video.py"


def _load(name: str, path: Path):
    """Import a script by path WITHOUT running main() (both are import-guarded)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_dir(tmp: Path) -> Path:
    """A run folder shaped like a real one: renders/, the delivery audio, the speech."""
    run = tmp / "run"
    (run / "renders").mkdir(parents=True)
    (run / "working" / "delivery").mkdir(parents=True)
    (run / "working" / "delivery" / "PRESENTER-AUDIO.mp3").write_bytes(b"stub")
    (run / "working" / "deliverables").mkdir(parents=True)
    (run / "working" / "deliverables" / "PRESENTERS-SPEECH.md").write_text(
        "## Slide 1\nHello there.\n", encoding="utf-8")
    return run


class ChunkFolderNamingTest(unittest.TestCase):
    def test_folder_is_named_after_the_out_file(self):
        mod = _load("synthesize_full_speech_pd307", SCRIPT_SYNTH)
        workdir = mod.default_workdir(
            str(Path("/runs/r1/working/delivery/PRESENTER-AUDIO.mp3")))
        self.assertEqual(workdir, "/runs/r1/working/delivery/_audio_chunks_PRESENTER-AUDIO")

    def test_two_syntheses_in_one_folder_leave_two_chunk_folders(self):
        mod = _load("synthesize_full_speech_pd307b", SCRIPT_SYNTH)
        with tempfile.TemporaryDirectory() as td:
            delivery = Path(td)
            first = mod.default_workdir(str(delivery / "PRESENTER-AUDIO.mp3"))
            second = mod.default_workdir(str(delivery / "PRESENTER-AUDIO-GUEST.mp3"))
            os.makedirs(first)
            os.makedirs(second)
            self.assertNotEqual(first, second)
            self.assertTrue(Path(first).is_dir() and Path(second).is_dir())
            self.assertEqual(sorted(p.name for p in delivery.iterdir()),
                             ["_audio_chunks_PRESENTER-AUDIO",
                              "_audio_chunks_PRESENTER-AUDIO-GUEST"])
            # The old fixed name is gone: it is what made the two collide.
            self.assertNotIn("_audio_chunks_full", first)


class VideoReadsItsOwnChunksTest(unittest.TestCase):
    def test_reads_the_folder_named_after_its_audio(self):
        mod = _load("build_webinar_video_pd307", SCRIPT_VIDEO)
        with tempfile.TemporaryDirectory() as td:
            run = _run_dir(Path(td))
            own = run / "working" / "delivery" / "_audio_chunks_PRESENTER-AUDIO"
            own.mkdir()
            self.assertEqual(Path(mod.resolve_required_inputs(run)["chunks_dir"]), own)

    def test_falls_back_to_the_legacy_folder_name(self):
        mod = _load("build_webinar_video_pd307b", SCRIPT_VIDEO)
        with tempfile.TemporaryDirectory() as td:
            run = _run_dir(Path(td))
            legacy = run / "working" / "delivery" / "_audio_chunks_full"
            legacy.mkdir()
            self.assertEqual(Path(mod.resolve_required_inputs(run)["chunks_dir"]), legacy)

    def test_missing_chunks_fail_loud_naming_both_folders(self):
        mod = _load("build_webinar_video_pd307c", SCRIPT_VIDEO)
        with tempfile.TemporaryDirectory() as td:
            run = _run_dir(Path(td))
            with self.assertRaises(mod.WebinarBuildError) as ctx:
                mod.resolve_required_inputs(run)
            self.assertIn("_audio_chunks_PRESENTER-AUDIO", str(ctx.exception))
            self.assertIn("_audio_chunks_full", str(ctx.exception))


class TimingFailureIsAnErrorTest(unittest.TestCase):
    def _fake_timing(self, verdict: str):
        fake = types.ModuleType("webinar_timing")
        fake.TimingError = type("TimingError", (RuntimeError,), {})
        fake.derive_timing = lambda *a, **k: {"timing": [{"duration": 1.0}]}
        fake.verify_timing = lambda result, audio_path: verdict
        return fake

    def _build(self, mod, verdict, run):
        saved = sys.modules.get("webinar_timing")
        sys.modules["webinar_timing"] = self._fake_timing(verdict)
        try:
            inputs = {"speech": Path(run / "working" / "deliverables" / "PRESENTERS-SPEECH.md"),
                      "chunks_dir": run / "working" / "delivery",
                      "audio": run / "working" / "delivery" / "PRESENTER-AUDIO.mp3"}
            return mod.build_timing(inputs, run, "deck", 280, False)
        finally:
            if saved is None:
                del sys.modules["webinar_timing"]
            else:
                sys.modules["webinar_timing"] = saved

    def test_drift_is_a_hard_error_and_writes_nothing(self):
        mod = _load("build_webinar_video_pd307d", SCRIPT_VIDEO)
        with tempfile.TemporaryDirectory() as td:
            run = _run_dir(Path(td))
            with self.assertRaises(mod.WebinarBuildError) as ctx:
                self._build(mod, "timing total = 9.0s vs audio 20.0s "
                                 "(diff 11.0s) -> DRIFT", run)
            self.assertIn("DRIFT", str(ctx.exception))
            self.assertFalse((run / "working" / "checkpoints" / "webinar_timing.json").exists())

    def test_a_cross_check_that_could_not_run_is_a_hard_error(self):
        mod = _load("build_webinar_video_pd307e", SCRIPT_VIDEO)
        with tempfile.TemporaryDirectory() as td:
            run = _run_dir(Path(td))
            with self.assertRaises(mod.WebinarBuildError):
                self._build(mod, "timing total = 9.0s; audio cross-check failed: boom", run)

    def test_a_passing_check_still_writes_the_track(self):
        mod = _load("build_webinar_video_pd307f", SCRIPT_VIDEO)
        with tempfile.TemporaryDirectory() as td:
            run = _run_dir(Path(td))
            out = self._build(mod, "timing total = 9.0s vs audio 9.2s "
                                   "(diff 0.2s) -> PASS", run)
            self.assertTrue(Path(out).is_file())
            self.assertEqual(len(json.loads(Path(out).read_text())["timing"]), 1)


_CHILD = r'''
import fcntl, json, os, sys, time
ledger, ready = sys.argv[1], sys.argv[2]
lock = ledger + ".lock"
open(lock, "a").close()
with open(lock, "w") as fh:
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    # Read FIRST, then hold the lock and write the stale view: this is the lost
    # update the lock prevents. An unlocked writer that reads and writes inside
    # this window loses its entry when the child finally writes.
    data = json.load(open(ledger))
    data.setdefault("uploaded", []).append({"kind": "webinar_mp4", "who": "uploader"})
    open(ready, "w").write("1")
    time.sleep(0.8)
    with open(ledger, "w") as out:
        json.dump(data, out)
    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
'''


class LedgerWriteIsLockedTest(unittest.TestCase):
    def test_a_second_writer_process_waits_and_keeps_both_entries(self):
        mod = _load("build_webinar_video_pd307g", SCRIPT_VIDEO)
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "run"
            ck = run / "working" / "checkpoints"
            ck.mkdir(parents=True)
            ledger = ck / "media_library.json"
            ledger.write_text(json.dumps({"deck_slug": "old"}))
            driver = Path(td) / "writer.py"
            driver.write_text(_CHILD, encoding="utf-8")
            ready = Path(td) / "ready"
            proc = subprocess.Popen([sys.executable, str(driver), str(ledger), str(ready)])
            try:
                deadline = time.time() + 20
                while not ready.exists():
                    if time.time() > deadline:
                        self.fail("child writer never took the ledger lock")
                    time.sleep(0.02)
                started = time.time()
                mod._record_webinar_in_ledger(
                    run, {"ghl_media_id": "vid1", "ghl_url": "https://x"})
                waited = time.time() - started
            finally:
                proc.wait(timeout=30)
            self.assertGreaterEqual(
                waited, 0.3, "the builder did not wait for the uploader's ledger lock")
            data = json.loads(ledger.read_text())
            who = [e.get("who") for e in data.get("uploaded", [])]
            self.assertIn("uploader", who)
            self.assertIn(None, who)  # the builder's own entry carries no 'who'
            self.assertEqual(data["webinar_mp4"]["ghl_media_id"], "vid1")
            self.assertEqual(data["deck_slug"], "old")  # never clobbered


if __name__ == "__main__":
    unittest.main()
