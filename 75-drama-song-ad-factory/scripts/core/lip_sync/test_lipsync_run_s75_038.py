#!/usr/bin/env python3
"""S75-038: the lip-sync chain is one command (unit U-U02).

Proves, offline and at $0 (a fake Skill 74 transport, fake uploads, a fake
picture measurement -- no network, no media):
  * ``python3 -m lip_sync run`` runs the whole chain for three planned clips
    and writes three evidence rows, each with its dispatch receipt;
  * ``final_assembler``'s ``check_plan`` passes on those rows;
  * with the command not run, ``check_plan`` refuses on the same plan shape
    (the control).

Run: python3 -B scripts/core/lip_sync/test_lipsync_run_s75_038.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _path in (CORE, HERE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import lipsync_evidence as E                      # noqa: E402  module under test
import spend_ledger as L                          # noqa: E402
from lip_sync import chain                        # noqa: E402  module under test
from storyboard_director import approval_package as AP   # noqa: E402

RUN_ID = "run-u02"
CLIPS = 3
WINDOW_S = 5.0
PRICE_USD_PER_S = 0.10


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def build_run(root):
    """A synthetic approved run: three lip-sync shots, one song, a card."""
    from style_defaults.card_gate import answered_stamped
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    song = root / "music" / "mix.mp3"
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b"synthetic-selected-song")
    _write(root / "song-choices/pick.json",
           {"pick": 1, "label": "synthetic", "take": 1, "sha256": _sha(song)})
    _write(root / "control/card-receipt-block.json", answered_stamped(
        {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
         "length": 60, "video_model": "Kling 3.0"}, "U-U02 test", "2026-11-12T10:00:00Z"))
    ledger = root / "spend.sqlite3"
    L.init_run(str(ledger), RUN_ID, 10000)

    shots, contracts, stills, lines = [], {}, {}, []
    for i in range(CLIPS):
        sid, lid = "shot-%d" % i, "line-%d" % i
        start, end = i * WINDOW_S, (i + 1) * WINDOW_S
        shots.append({"shot_id": sid, "lip_sync": True, "lip_sync_line_ids": [lid],
                      "lyric_line_ids": [lid], "speaker": "cara",
                      "character_ids": ["cara"], "song_start": start,
                      "song_end": end})
        still = root / "storyboard" / (sid + ".png")
        still.parent.mkdir(parents=True, exist_ok=True)
        still.write_bytes(("synthetic-still-" + sid).encode())
        contracts[sid] = {"meaning": "synthetic fixture"}
        stills[sid] = str(still)
        lines.append({"line_id": lid, "speaker": "cara", "start": start, "end": end})
    board = root / "storyboard"
    _write(board / "shot-list.json", {"shots": shots})
    _write(board / "contracts.json", contracts)
    _write(board / "stills.json", stills)
    entries = AP.approval_entries(shots, contracts, stills)
    for entry in entries.values():
        entry["status"] = "approved"
    _write(board / "approval.json", {"state": "approved", "shots": entries})
    _write(board / "gate.json",
           {"shots": [dict(s, status="storyboard_approved") for s in shots],
            "review": {"outcome": "pass"}})
    return {"root": root, "song": str(song), "ledger": str(ledger),
            "shots": shots, "lines": lines, "stills": stills}


class Fake74:
    """A scripted Skill 74: health/preflight/budget/submit/wait/save only."""

    def __init__(self, root):
        self.root = Path(root)
        self.calls = []
        self.saves = 0

    def __call__(self, argv):
        cmd = argv[1] if len(argv) > 1 else ""
        self.calls.append(cmd)
        if cmd == "health":
            return 0, {"adapter_mode": "active", "state": "success"}
        if cmd == "preflight":
            return 0, {"state": "validated", "data": {"ok": True}}
        if cmd == "prompt-budget":
            return 0, {"state": "success",
                       "data": {"status": "OK", "exit_code": 0, "max": 20000}}
        if cmd == "submit":
            return 0, {"state": "queued", "task_id": "t-lip", "raw_family": "market"}
        if cmd == "wait":
            return 0, {"state": "success", "task_id": "t-lip",
                       "raw_family": "market", "credits_consumed": 16}
        if cmd == "save":
            self.saves += 1
            clip = self.root / "generation" / "saved" / ("clip-%d.mp4" % self.saves)
            clip.parent.mkdir(parents=True, exist_ok=True)
            clip.write_bytes(("synthetic-lip-clip-%d" % self.saves).encode())
            return 0, {"state": "success", "task_id": "t-lip",
                       "saved_paths": [str(clip)]}
        return 0, {}


def _picture_measure(path):
    return {"face_count": 1, "face_h_pct": 40.0, "roll_deg": 0.0,
            "yaw_proxy": 0.0, "jaw_open": 0.0, "smile": 0.0,
            "inner_gap_pct": 0.0, "sharp_face_256": 400.0}


def _measure_clip(clip):
    return {"grade": "SYNCED", "corr": 0.82, "margin": 0.31, "pct": 0.0,
            "offset_s": 0.0, "lag_frames": 0, "control_corr": 0.51,
            "unmeasurable": None}


def providers(run, adapter_path):
    """Every collaborator, doubled: no network, no media, no paid call."""
    from audio_c3 import lipsync_producer as producer
    from lip_sync.lip_gate import picture_gate as PG
    transport = Fake74(run["root"])

    def uploader(path):
        return "https://fixture.invalid/upload/" + _sha(path)

    def separation_runner():
        def fake(**kwargs):
            save_dir = Path(kwargs["save_dir"])
            stem = save_dir / "isolated.wav"
            stem.write_bytes(b"synthetic-isolated-lead-vocal")
            instrumental = save_dir / "instrumental.wav"
            instrumental.write_bytes(b"synthetic-instrumental")
            return {"tool": "kie_dispatch", "outcome": "ok", "run_id": RUN_ID,
                    "evidence": {"generated": True, "task_id": "t-separation",
                                 "saved_paths": [str(stem), str(instrumental)],
                                 "isolated_stem": {"path": str(stem),
                                                   "speaker_id": "cara",
                                                   "kind": "speech",
                                                   "isolated": True}}}
        return producer.skill74_runner(
            str(run["root"]), uploader, {}, lambda result: result["evidence"]["isolated_stem"],
            dispatch_fn=fake)

    def cut_runner(argv, *args, **kwargs):
        Path(argv[-1]).write_bytes(b"synthetic-own-speaker-line")

    return {"picture_measure": _picture_measure, "picture_uploader": uploader,
            "stem_uploader": uploader, "source_uploader": uploader,
            "separation_runner": separation_runner(),
            "measure_offset": lambda *a: {"offset_s": 0.5, "corr": 0.9},
            "cut_runner": cut_runner, "measure_clip": _measure_clip,
            "adapter_path": adapter_path, "dispatch_runner": transport,
            "ledger_db": run["ledger"], "usd_per_s": PRICE_USD_PER_S,
            "sung": False, "stage": "video-generation"}


def plan_from(rows, run):
    """The assembler plan shape ``check_plan`` reads, built from the rows."""
    segments, lines = [], list(run["lines"])
    for i, row in enumerate(rows):
        segments.append({"src": row["clip_path"], "shot_id": row["shot_id"],
                         "lip_sync": True,
                         "lip_sync_line_ids": row["lip_sync_line_ids"],
                         "speaker": row["speaker"],
                         "faces_on_screen": [row["speaker"]],
                         "frames": int(WINDOW_S * 30), "offset_frames": i * 150,
                         "xfade_frames": 0, "source_dur": WINDOW_S, "stretch": 1,
                         "artifact": row["artifact"]})
    return {"run_dir": str(run["root"]), "run_id": RUN_ID, "fps": 30,
            "total_dur": CLIPS * WINDOW_S, "song_path": run["song"],
            "lines": lines, "segments": segments}


class LipSyncRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = build_run(Path(self.tmp.name) / "run")

    def test_three_clips_produce_three_rows_that_check_plan_accepts(self):
        result = chain.run(str(self.run["root"]), RUN_ID,
                           providers=providers(self.run, os.path.abspath(__file__)))
        self.assertEqual("ok", result["outcome"], result)
        self.assertEqual(3, result["rows"], result)
        evidence = json.loads((self.run["root"] / "control/lip-sync/evidence.json")
                              .read_text(encoding="utf-8"))
        rows = evidence["rows"]
        self.assertEqual(3, len(rows))
        for row in rows:
            self.assertTrue(Path(row["receipt_path"]).is_file(), row)
            self.assertEqual("kie_dispatch",
                             json.loads(Path(row["receipt_path"]).read_text())
                             ["tool"])
        check = E.check_plan(plan_from(rows, self.run), require_measured=True)
        self.assertTrue(check["pass"], check)
        self.assertEqual(3, len(check["evidence"]["included"]))

    def test_without_the_command_check_plan_refuses(self):
        receipts = self.run["root"] / "control/lip-sync/receipts"
        rows = [{"shot_id": s["shot_id"], "speaker": s["speaker"],
                 "lip_sync_line_ids": s["lip_sync_line_ids"],
                 "clip_path": str(self.run["root"] / "generation" / ("c%d.mp4" % i)),
                 "artifact": {"schema_version": "1.0.0",
                              "artifact_id": "lipsync-" + s["shot_id"],
                              "run_id": RUN_ID, "stage": "generation",
                              "kind": "video",
                              "path": str(self.run["root"] / "generation" / ("c%d.mp4" % i)),
                              "sha256": "0" * 64,
                              "provenance": {"task_id": "t-lip",
                                             "receipt_path": str(
                                                 receipts / ("%s-try1.json"
                                                             % s["shot_id"]))}}}
                for i, s in enumerate(self.run["shots"])]
        check = E.check_plan(plan_from(rows, self.run), require_measured=True)
        self.assertFalse(check["pass"], check)


if __name__ == "__main__":
    unittest.main(verbosity=2)
