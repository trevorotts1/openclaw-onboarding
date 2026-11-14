#!/usr/bin/env python3
"""test_pd_audio_speed.py — PD-312: the client's speech-speed choice is honored.

The producer reads `working/copy/intake.json` (two levels above the out file) for
`speech_speed_preference` and maps it onto the Fish prosody speed presets
(default 1.25 / medium 1.3 / fast 1.33). Before PD-312 the module used
`Path(...)` while importing no `pathlib` name, and the resulting NameError was
swallowed by a bare `except Exception: pass` — so the client's choice was
silently ignored and every deck was rendered at 1.25.

These tests drive `main()` only as far as the speed-resolution block: the
ffmpeg presence probe is stubbed to fail, which exits before any API call,
speech read, or file write. No network, no Fish key, no audio.
"""
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "synthesize_full_speech.py"


def _load():
    """Import the producer module WITHOUT running main() (import-guarded)."""
    spec = importlib.util.spec_from_file_location("synthesize_full_speech_pd312", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(tmp: Path, intake_text: str):
    """A run folder shaped like a real one: <run>/working/copy/intake.json and
    <run>/working/deliverables/PRESENTER-AUDIO.mp3 (the two ancestors the
    producer probes)."""
    run = tmp / "run"
    (run / "working" / "copy").mkdir(parents=True)
    (run / "working" / "copy" / "intake.json").write_text(intake_text, encoding="utf-8")
    speech = run / "working" / "copy" / "PRESENTERS-SPEECH.md"
    speech.write_text("## Slide 1\nHello there.\n", encoding="utf-8")
    out = run / "working" / "deliverables" / "PRESENTER-AUDIO.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    return speech, out


def _run_until_tool_check(mod, speech: Path, out: Path) -> str:
    """Run main() with the ffmpeg probe stubbed to 'missing' so it exits right
    after the speed block; return everything it printed."""
    argv = [str(SCRIPT), "--speech", str(speech), "--out", str(out),
            "--api-key", "stub-key-not-live"]
    buf = io.StringIO()
    with mock.patch.object(sys, "argv", argv), \
            mock.patch.object(mod.subprocess, "call", return_value=1), \
            redirect_stdout(buf):
        try:
            mod.main()
        except SystemExit:
            pass
    return buf.getvalue()


class SpeechSpeedPreferenceTest(unittest.TestCase):
    def test_path_is_imported_so_the_intake_is_readable(self):
        # The module really imports pathlib.Path (the NameError is what made the
        # client's choice dead before PD-312).
        import pathlib
        self.assertIs(_load().Path, pathlib.Path)

    def test_fast_preference_sets_133(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            speech, out = _fixture(Path(td), json.dumps({"speech_speed_preference": "fast"}))
            text = _run_until_tool_check(mod, speech, out)
        self.assertIn(
            "[speed] intake speech_speed_preference='fast' -> prosody.speed 1.33", text)
        self.assertNotIn("could not read intake", text)

    def test_medium_preference_sets_13(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            speech, out = _fixture(Path(td), json.dumps({"speech_speed_preference": "medium"}))
            text = _run_until_tool_check(mod, speech, out)
        self.assertIn(
            "[speed] intake speech_speed_preference='medium' -> prosody.speed 1.3", text)

    def test_unreadable_intake_is_printed_not_swallowed(self):
        # An unreadable intake keeps the 1.25 default but must SAY so.
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            speech, out = _fixture(Path(td), "{not json")
            text = _run_until_tool_check(mod, speech, out)
        self.assertIn("[speed] could not read intake:", text)
        self.assertNotIn("-> prosody.speed", text)


if __name__ == "__main__":
    unittest.main()
