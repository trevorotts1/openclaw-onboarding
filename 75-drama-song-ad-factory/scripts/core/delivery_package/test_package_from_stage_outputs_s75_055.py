#!/usr/bin/env python3
"""U-T05 / S75-055: the packaging command runs on what the stages really write.

The finding: packaging needed four files that no stage wrote
(``music/word-timings.json``, ``music/vocal-stem.mp3``,
``music/instrumental.mp3``, ``edit/timeline.json``) and there was no command
that packaged a run and verified the folder.

This test builds ONE run folder and writes NONE of those four by hand. Each is
produced by the stage that owns it, offline:

  ``music/word-timings.json``   the song save transport (``song_transports
                                .make_save``) then ``song_choices.record_pick``
                                -- the pick publishes the chosen take's clock;
  ``music/vocal-stem.mp3``      ``audio_c3.lipsync_producer.produce`` with a
  ``music/instrumental.mp3``    fake separation runner: the one separation job
                                for the song saves both stems;
  ``edit/timeline.json``        ``final_assembler.assembler
                                .plan_run_timeline`` -- the assembler's
                                planning step, from the run's own records.

Then it runs the new command (``python3 -m delivery_package package
--run-dir <run>``) and the twelve package items must verify. The negative
control removes ``music/vocal-stem.mp3`` from a copy of the run; the command
must exit non-zero and name the MUSIC stage, not a bare path.

Every other run input (the confirmed intake, the approved script and its
approval, the approved storyboard and its stills, the character records, the
mix and the rendered master) is built the way the existing delivery end-to-end
test builds it, so nothing here is a deliverable written by hand.

Run: python3 -B scripts/core/delivery_package/test_package_from_stage_outputs_s75_055.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent                          # .../scripts/core
for _path in (str(_CORE), str(_HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import test_delivery_package_e2e as E2E         # noqa: E402  fixture helpers
import delivery_package.contract as C           # noqa: E402
import final_assembler.assembler as A           # noqa: E402
import song_transports                          # noqa: E402
from audio_c3 import lipsync_producer as LP     # noqa: E402
from song_choices import song_choices as SC     # noqa: E402
from song_dispatch import song_dispatch as SD   # noqa: E402
from sung_hook import sung_hook as SH           # noqa: E402

SHOT_S = 4.0                 # one approved shot per lyric line, 4 s each
FIRST_SHOT_START = 1.0       # leaves room for the stem offset at the head
SHOT_COUNT = 21              # 84 s of picture inside an 85 s master
MASTER_S = 85
SPEAKER = "cara"
DELIVERY_NAME = "delivery"

LINES = [
    "she opens the curtains as the light comes in",
    "the kitchen smells of coffee and warm bread",
    "she writes one line in the little blue book",
    "morning is the part of the day that is hers",
    "before the street wakes up she takes her time",
    "one small ritual and the whole day turns",
    "she closes the book and steps into the light",
]


def _line(index):
    return LINES[index % len(LINES)]


# ------------------------------------------------------------ run inputs ----

def _aligned_words():
    """Measured words, one run per line, inside that line's shot window."""
    words = []
    for index in range(SHOT_COUNT):
        clock = FIRST_SHOT_START + index * SHOT_S + 0.4
        for token in E2E.PN._tokens(_line(index)):
            words.append({"word": token, "start": round(clock, 3),
                          "end": round(clock + 0.3, 3)})
            clock += 0.4
    return words


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sine(path, frequency, seconds=MASTER_S):
    E2E._ffmpeg(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                 "-i", "sine=frequency=%d:duration=%s" % (frequency, seconds),
                 "-c:a", "libmp3lame", "-b:a", "192k", str(path)])
    return Path(path)


def _master(path):
    E2E._ffmpeg(["ffmpeg", "-y", "-v", "error",
                 "-f", "lavfi", "-i",
                 "testsrc2=s=320x568:r=15:d=%s" % MASTER_S,
                 "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=%s" % MASTER_S,
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-preset", "ultrafast", "-c:a", "aac", "-profile:a",
                 "aac_low", "-ar", "48000", "-b:a", "128k", "-ac", "2",
                 "-movflags", "+faststart", str(path)])
    return Path(path)


def _script_and_brief(run):
    lyrics = "\n".join(_line(i) for i in range(SHOT_COUNT))
    sheet = [{"tag": "s%02d" % i, "lines": [_line(i)]}
             for i in range(SHOT_COUNT)]
    story = [["opening", [_line(0), _line(1), _line(2)]],
             ["the turn", [_line(4), _line(5), _line(6)]]]
    E2E._w(run, "creative/script.json",
           {"title": E2E.TITLE, "sheet": sheet, "story": story,
            "lyrics": lyrics})
    E2E._w(run, "creative/script-approval.json",
           {"required": True, "status": "approved",
            "lyrics_sha": E2E.SA.lyrics_sha(lyrics), "sent": True})
    E2E._w(run, "brief.json", dict(E2E.BRIEF))


def _approved_storyboard(run):
    """The approved shot plan the lip-sync producer and the planner both read."""
    hooks = SH.hook_times(MASTER_S)
    shots, contracts, stills = [], {}, {}
    for index in range(SHOT_COUNT):
        sid = "s%02d" % index
        lid = "l%02d" % index
        start = FIRST_SHOT_START + index * SHOT_S
        shots.append({
            "shot_id": sid, "song_start": start, "song_end": start + SHOT_S,
            "story_stage": "setup" if index < SHOT_COUNT // 2 else "rise",
            "location_id": "kitchen" if index % 2 == 0 else "window",
            "character_ids": [SPEAKER], "status": "planned",
            "lyric_line_ids": [lid], "lip_sync": True,
            "lip_sync_line_ids": [lid], "speaker": SPEAKER,
            # the storyboard stage marks the hook lines; the planner and the
            # clip cutter both read this flag (a run with no hook line has no
            # legal 60/90 s window)
            "hook": any(start <= moment < start + SHOT_S for moment in hooks),
        })
        contracts[sid] = {
            "lyric_text": _line(index),
            "viewer_understanding": "the morning routine carries on",
            "character_action": "moves through the room at her own pace",
            "visible_emotion": "warm, unhurried",
        }
        rel = os.path.join("storyboard", "stills", sid + ".png")
        E2E._write_png(run / rel, sid, size=160,
                       colour=(70 + (index * 11) % 170, 110, 160))
        stills[sid] = rel
    E2E._w(run, "storyboard/shot-list.json", {"shots": shots})
    E2E._w(run, "storyboard/contracts.json", contracts)
    E2E._w(run, "storyboard/stills.json", stills)
    E2E.AR.record_card_answer(str(run), [{"id": "storyboard", "n": 1}],
                              [{"id": "storyboard"}])
    shown = []
    pending = E2E.AR.run(str(run),
                         lambda message, images: shown.append((message, images)))
    if pending["action"] != "waiting" or not shown or E2E.AR.gate_open(str(run)):
        raise RuntimeError("the storyboard was not presented and held")
    accepted = E2E.AR.run(str(run), lambda *_: None, reply="GO")
    if accepted["action"] != "approved" or not E2E.AR.gate_open(str(run)):
        raise RuntimeError("the whole storyboard package was not approved")
    return shots


def _character(run):
    ref_dir = run / "character" / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_paths = []
    for index, view in enumerate(E2E.VIEWS):
        path = ref_dir / (view + ".png")
        E2E._write_png(path, "ref-" + view, size=96,
                       colour=(120 + index * 20, 90, 70))
        ref_paths.append(str(path))
    brief = dict(E2E.BRIEF)
    brief["character_reference_images"] = ref_paths
    E2E._w(run, "character/brief.json", brief)
    E2E._w(run, "character/records.json", [{
        "name": "Sample Character", "slug": "sample-character",
        "views": dict(zip(E2E.VIEWS, ref_paths)),
        "reference_paths": ref_paths,
    }])


# ----------------------------------------------- the four stage-written inputs --

def _pick_publishes_word_timings(run):
    """music/word-timings.json: the song save transport, then the pick."""
    source_dir = run / "music" / "takes-src"
    source_dir.mkdir(parents=True, exist_ok=True)
    audio = _sine(source_dir / "take-01.mp3", 440)
    take = {
        "audio_path": str(audio),
        "audio_sha256": _sha(audio),
        "aligned_words": _aligned_words(),
        "duration_s": float(MASTER_S),
        "measurement_owners": {
            "transcription_and_timing": {"source": "suno-timestamped-lyrics"}},
    }
    gate_results = {gate: {"verdict": "PASS"}
                    for gate in SD.REQUIRED_TAKE_GATES}
    saved_dir = song_transports.make_save(str(run))(
        {"id": "v01", "label": "Version 1", "description": "first arrangement"},
        take, {"gates": gate_results})
    if not saved_dir:
        raise RuntimeError("the song save transport kept no take")
    receipt = SD.constituent_receipt(
        take, {"gates": gate_results,
               "required_gates": list(SD.REQUIRED_TAKE_GATES)}, {})
    SC.init(str(run), True)
    SC._write(str(run), "state.json", {
        "required": True, "failure_fork": False, "concerns": {},
        "offered": {"1": {
            "label": "1 - Version 1 (first arrangement)",
            "file": os.path.join(saved_dir, audio.name),
            "duration": "1:25", "take": take, "receipt": receipt,
            "variant_id": "v01"}},
    })
    E2E._w(run, "music/acceptance/v01.json",
           {"variant_id": "v01", "verdict": "PASS"})
    return SC.record_pick(str(run), "1")


def _separation_produced_stems(run, run_id, song):
    """music/vocal-stem.mp3 and music/instrumental.mp3: ONE separation job."""
    root = run.resolve()
    song = Path(song).resolve()
    digest = _sha(song)

    def fake_separation(request):
        out = Path(request["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        vocal = _sine(out / "isolated.mp3", 440)
        instrumental = _sine(out / "instrumental.mp3", 246)
        url = "https://example.invalid/selected-song"
        receipt = out / "source-upload.json"
        receipt.write_text(json.dumps(
            {"path": str(song), "sha256": digest, "url": url}), encoding="utf-8")
        return {
            "tool": "kie_dispatch", "outcome": "ok", "run_id": run_id,
            "evidence": {
                "generated": True, "task_id": "task-s75-055",
                "separation_source": {"path": str(song), "sha256": digest,
                                      "url": url,
                                      "upload_receipt_path": str(receipt)},
                "separation_input": {"audio_url": url},
                "saved_paths": [str(vocal), str(instrumental)],
                "isolated_stem": {"path": str(vocal), "speaker_id": SPEAKER,
                                  "kind": "speech", "isolated": True},
            },
        }

    def fake_cut(argv, *_args, **_kwargs):
        Path(argv[-1]).write_bytes(b"own-speaker-line")

    return LP.produce(str(root), run_id, "s00", str(song), fake_separation,
                      measure_offset=lambda *_a: {"offset_s": 0.0,
                                                  "corr": 0.91},
                      cut_runner=fake_cut)


def _planner_writes_timeline(run, shots):
    """edit/timeline.json: the assembler's own planning step."""
    rows = []
    for index, shot in enumerate(shots):
        sid = shot["shot_id"]
        rows.append({
            "shot_id": sid,
            "path": "video/clip%02d.mp4" % (index + 1),
            "sha256": "sha-" + sid,
            "receipt_path": "video/clip%02d.receipt.json" % (index + 1),
            "task_id": "task-" + sid,
            "motion_score": {"score": 0.9, "flagged": False,
                             "evidence": "spatial"},
        })
    E2E._w(run, "video/clips.json", {"clips": rows})
    planner = getattr(A, "plan_run_timeline", None)
    if planner is None:
        raise AssertionError(
            "STAGE WRITER ABSENT: final_assembler.assembler.plan_run_timeline "
            "(U-V03, commit b7d7548a) is not in this tree, so edit/timeline.json "
            "has no stage writer. Merge the V lane (or main after its merge) "
            "before running this acceptance.")
    return planner(str(run))


def build_stage_run(run_dir):
    """One run whose four packaging inputs are all stage-written."""
    run_dir = Path(run_dir)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    run_id = E2E.confirm_intake(run_dir)      # the run's confirmed authority
    _script_and_brief(run_dir)
    shots = _approved_storyboard(run_dir)
    _character(run_dir)

    (run_dir / "music").mkdir(parents=True, exist_ok=True)
    _sine(run_dir / "music" / "mix.mp3", 330)      # the finished mix (input)
    (run_dir / "edit").mkdir(parents=True, exist_ok=True)
    _master(run_dir / "edit" / "ad.mp4")           # the rendered master (input)

    _pick_publishes_word_timings(run_dir)
    _separation_produced_stems(run_dir, run_id,
                               run_dir / "music" / "picked-song.mp3")
    _planner_writes_timeline(run_dir, shots)
    return run_dir


# ------------------------------------------------------------------ suite ----

def _run_command(run_dir, tmp):
    env = dict(os.environ, TMPDIR=str(tmp))
    return subprocess.run(
        [sys.executable, "-B", "-m", "delivery_package", "package",
         "--run-dir", str(run_dir)],
        cwd=str(_CORE), capture_output=True, text=True, env=env)


class PackageFromStageOutputs(unittest.TestCase):
    """One run built by the stages -> the packaging command -> twelve items."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="s75-055-"))
        cls.run_dir = build_stage_run(cls.tmp / "run")
        # the command's default is <run>/delivery (no --out is passed);
        # verify the folder the command wrote, not a sibling tmp/delivery.
        cls.out = cls.run_dir / DELIVERY_NAME
        cls.proc = _run_command(cls.run_dir, cls.tmp)
        try:
            cls.envelope = json.loads(cls.proc.stdout)
        except ValueError:
            cls.envelope = None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_01_the_four_inputs_were_written_by_stages(self):
        for rel in ("music/word-timings.json", "music/vocal-stem.mp3",
                    "music/instrumental.mp3", "edit/timeline.json"):
            path = self.run_dir / rel
            with self.subTest(input=rel):
                self.assertTrue(path.is_file(), "%s was never written" % rel)
                self.assertGreater(path.stat().st_size, 0)

    def test_02_the_command_packages_the_twelve_items(self):
        self.assertEqual(
            self.proc.returncode, 0,
            "packaging refused: rc=%s stdout=%s stderr=%s"
            % (self.proc.returncode, self.proc.stdout, self.proc.stderr))
        self.assertIsNotNone(self.envelope, self.proc.stdout)
        self.assertTrue(self.envelope["ok"], self.envelope)
        self.assertEqual(self.envelope["missing"], [], self.envelope)
        self.assertEqual(self.envelope["problems"], [], self.envelope)
        self.assertEqual([row["number"] for row in self.envelope["items"]],
                         list(range(1, 13)))
        self.assertTrue(all(row["present"] for row in self.envelope["items"]))
        report = C.verify_folder(self.out, campaign_run=False,
                                 chosen_length_s=180)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])
        self.assertEqual(sorted(report["present"]),
                         sorted(item.key for item in C.PACKAGE_ITEMS))

    def test_03_removing_the_vocal_stem_names_the_music_stage(self):
        copy = self.tmp / "run-no-stem"
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(self.run_dir, copy)
        (copy / "music" / "vocal-stem.mp3").unlink()
        proc = _run_command(copy, self.tmp)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        envelope = json.loads(proc.stdout)
        self.assertFalse(envelope["ok"])
        text = " ".join(envelope["problems"])
        self.assertIn("music/vocal-stem.mp3", text)
        self.assertIn("music stage", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
