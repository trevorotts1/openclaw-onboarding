#!/usr/bin/env python3
"""S75-056: one vocal-separation job per song (unit U-U01; N-117 / 3N).

Proves, with a fake dispatch runner and no paid call:
  * five clips over one song submit the separation model exactly once, keyed
    ``logical_key="vocal-stem"``, with the plain ``split_stem`` type;
  * that one job publishes the lead (``music/vocals.mp3`` and its delivery
    copy ``music/vocal-stem.mp3``), the clean backing
    (``music/backing-vocals.mp3``) and ``music/instrumental.mp3``;
  * every clip cuts from its own role's track (the lead track when the row
    names no role).

Run: python3 -B scripts/core/audio_c3/test_one_stem_s75_056.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _path in (CORE, HERE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from audio_c3 import lipsync_producer as producer  # noqa: E402  module under test

SHOTS = ("s1", "s2", "s3", "s4", "s5")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class OneStemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.song = self.root / "selected-song.wav"
        self.song.write_bytes(b"synthetic-selected-song")
        self.required = {
            sid: {"shot_id": sid, "lip_sync_line_ids": ["line-" + sid],
                  "speaker": "cara", "storyboard_revision": "rev-1",
                  "start_s": 1.0, "end_s": 3.0}
            for sid in SHOTS}
        pick = self.root / "song-choices" / "pick.json"
        pick.parent.mkdir(parents=True)
        pick.write_text(json.dumps({"pick": 1, "label": "synthetic", "take": 1,
                                    "sha256": _sha(self.song)}), encoding="utf-8")

    def _runner(self, submits, argvs):
        def fake_dispatch(**kwargs):
            submits.append(kwargs)
            save_dir = Path(kwargs["save_dir"])
            stem = save_dir / "isolated.wav"
            stem.write_bytes(b"synthetic-isolated-lead-vocal")
            backing = save_dir / "backing_vocals.wav"
            backing.write_bytes(b"synthetic-clean-backing")
            instrumental = save_dir / "instrumental.wav"
            instrumental.write_bytes(b"synthetic-instrumental")
            return {"tool": "kie_dispatch", "outcome": "ok", "run_id": "run-u01",
                    "evidence": {"generated": True, "task_id": "task-one-stem",
                                 "saved_paths": [str(stem), str(backing),
                                                 str(instrumental)],
                                 "isolated_stem": {"path": str(stem),
                                                   "speaker_id": "cara",
                                                   "kind": "speech",
                                                   "isolated": True}}}

        def cut_runner(argv, *args, **kwargs):
            argvs.append(argv)
            Path(argv[-1]).write_bytes(b"synthetic-own-speaker-line")

        runner = producer.skill74_runner(
            str(self.root), lambda p: "https://fixture.invalid/selected-song", {},
            lambda result: result["evidence"]["isolated_stem"],
            dispatch_fn=fake_dispatch)
        return runner, cut_runner

    def test_five_clips_pay_for_one_separation(self):
        submits, argvs = [], []
        separation_runner, cut_runner = self._runner(submits, argvs)
        vocal = self.root / "music" / "vocal-stem.mp3"
        lead = self.root / "music" / "vocals.mp3"
        backing = self.root / "music" / "backing-vocals.mp3"
        instrumental = self.root / "music" / "instrumental.mp3"
        stems = []
        with mock.patch.object(producer, "_approved",
                               return_value=(self.root, self.required)), \
                mock.patch.object(producer, "_approval_context", return_value={}):
            for sid in SHOTS:
                stems.append(producer.produce(
                    str(self.root), "run-u01", sid, str(self.song),
                    separation_runner,
                    measure_offset=lambda *args: {"offset_s": 0.5, "corr": 0.9},
                    cut_runner=cut_runner))
        self.assertEqual(1, len(submits), submits)
        self.assertEqual("ai-music-api/separate-vocals", submits[0]["model"])
        self.assertEqual("vocal-stem", submits[0]["logical_key"])
        self.assertEqual("split_stem",
                         submits[0]["request"]["input"]["type"])
        self.assertTrue(vocal.is_file())
        self.assertTrue(lead.is_file())
        self.assertTrue(backing.is_file())
        self.assertTrue(instrumental.is_file())
        for path in (vocal, lead, backing, instrumental):
            self.assertGreater(path.stat().st_size, 0)
        for argv in argvs:
            # The rows name no role, so they are lead pieces: the lead track.
            self.assertEqual(str(lead), argv[argv.index("-i") + 1])
        for stem in stems:
            self.assertTrue(Path(stem["path"]).is_file())
            self.assertEqual("cara", stem["speaker_id"])
            self.assertEqual("lead", stem["track"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
