#!/usr/bin/env python3
"""test_pd_audio_bank.py — PD-318: bank audio chunks so a retry does not
re-buy the whole speech.

Before PD-318 every run synthesized every chunk again, so a transport failure on
the third of five chunks cost the first two again (and again) on each retry, and
`--normalize` was a switch whose default was already on, so it could never be
turned off.

Now each `chunk_NNN.mp3` carries a sidecar `chunk_NNN.sha` holding the hash of
the chunk text plus the voice, the model and the speaking speed; a banked chunk
is reused only when that hash still matches AND `verify_mp3` still passes, and
`--no-normalize` turns normalization off while `--normalize` stays accepted.

Offline only: the Fish transport is a stub, no network, no ffmpeg, no key.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT_SYNTH = SCRIPTS / "synthesize_full_speech.py"

# A synthetic but structurally valid MP3: ID3v2 tag, then an MPEG frame sync at
# offset 10, then enough padding to clear the 10 KB floor verify_mp3 enforces.
VALID_MP3 = (b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00"
             + b"\x00" * 12000)


def _load(name: str):
    """Import the script by path WITHOUT running main() (import-guarded)."""
    spec = importlib.util.spec_from_file_location(name, SCRIPT_SYNTH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _transport(calls, fail_on=None):
    """A stub Fish transport: records the text it is asked to buy, writes a
    valid mp3 on success, raises on the chunk named by *fail_on*."""
    def buy(text, out_path):
        calls.append(text)
        if fail_on is not None and text == fail_on:
            raise RuntimeError("Fish Audio synthesis failed: HTTP 500 (stub)")
        Path(out_path).write_bytes(VALID_MP3)
        return len(VALID_MP3)
    return buy


class ChunkSignatureTest(unittest.TestCase):
    def test_the_same_request_banks_the_same_key(self):
        mod = _load("synthesize_full_speech_pd318_sig_a")
        a = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
        b = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
        self.assertEqual(a, b)

    def test_text_voice_model_and_speed_all_change_the_key(self):
        mod = _load("synthesize_full_speech_pd318_sig_b")
        base = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
        variants = {
            "text": mod.chunk_signature("Hello there!", "voice1", "s2.1-pro", 1.25),
            "voice": mod.chunk_signature("Hello there.", "voice2", "s2.1-pro", 1.25),
            "model": mod.chunk_signature("Hello there.", "voice1", "s2-pro", 1.25),
            "speed": mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.33),
        }
        for field, digest in variants.items():
            self.assertNotEqual(base, digest, f"a different {field} must not reuse the bank")

    def test_no_voice_is_a_key_of_its_own(self):
        mod = _load("synthesize_full_speech_pd318_sig_c")
        self.assertEqual(mod.chunk_signature("hi", None, "s2.1-pro", 1.25),
                         mod.chunk_signature("hi", "", "s2.1-pro", 1.25))


class ChunkBankTest(unittest.TestCase):
    def test_a_matching_banked_chunk_is_not_bought_again(self):
        mod = _load("synthesize_full_speech_pd318_bank_a")
        with tempfile.TemporaryDirectory() as td:
            calls = []
            sig = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
            mod.chunk_or_bank("Hello there.", 0, td, sig, _transport(calls))
            self.assertEqual(len(calls), 1)
            Path(td, "chunk_000.sha").write_text(sig + "\n", encoding="utf-8")
            path, reused = mod.chunk_or_bank("Hello there.", 0, td, sig, _transport(calls))
            self.assertTrue(reused)
            self.assertEqual(len(calls), 1, "the banked chunk was bought a second time")
            self.assertEqual(path, str(Path(td, "chunk_000.mp3")))

    def test_synthesis_banks_its_sidecar(self):
        mod = _load("synthesize_full_speech_pd318_bank_b")
        with tempfile.TemporaryDirectory() as td:
            sig = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
            _, reused = mod.chunk_or_bank("Hello there.", 0, td, sig, _transport([]))
            self.assertFalse(reused)
            self.assertEqual(Path(td, "chunk_000.sha").read_text(encoding="utf-8").strip(), sig)

    def test_a_corrupt_banked_chunk_is_bought_again_even_with_a_matching_hash(self):
        mod = _load("synthesize_full_speech_pd318_bank_c")
        with tempfile.TemporaryDirectory() as td:
            calls = []
            sig = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
            Path(td, "chunk_000.sha").write_text(sig + "\n", encoding="utf-8")
            Path(td, "chunk_000.mp3").write_bytes(b"not audio at all")
            _, reused = mod.chunk_or_bank("Hello there.", 0, td, sig, _transport(calls))
            self.assertFalse(reused)
            self.assertEqual(len(calls), 1)
            self.assertEqual(Path(td, "chunk_000.mp3").read_bytes(), VALID_MP3)

    def test_a_different_speed_does_not_reuse_the_bank(self):
        mod = _load("synthesize_full_speech_pd318_bank_d")
        with tempfile.TemporaryDirectory() as td:
            calls = []
            slow = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
            fast = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.33)
            mod.chunk_or_bank("Hello there.", 0, td, slow, _transport(calls))
            self.assertEqual(len(calls), 1)
            _, reused = mod.chunk_or_bank("Hello there.", 0, td, fast, _transport(calls))
            self.assertFalse(reused, "a faster read is different audio, not the banked one")
            self.assertEqual(len(calls), 2)

    def test_a_banked_chunk_that_is_not_real_audio_is_never_reused(self):
        mod = _load("synthesize_full_speech_pd318_bank_e")
        with tempfile.TemporaryDirectory() as td:
            sig = mod.chunk_signature("Hello there.", "voice1", "s2.1-pro", 1.25)
            Path(td, "chunk_000.sha").write_text(sig + "\n", encoding="utf-8")
            Path(td, "chunk_000.mp3").write_bytes(VALID_MP3[:12])
            self.assertFalse(
                mod.banked_chunk_is_good(Path(td, "chunk_000.mp3"),
                                         Path(td, "chunk_000.sha"), sig))


class RetryDoesNotRebuyTheSpeechTest(unittest.TestCase):
    def test_five_chunks_where_the_third_fails_cost_three_requests_not_five(self):
        mod = _load("synthesize_full_speech_pd318_retry")
        chunks = ["c1", "c2", "c3", "c4", "c5"]
        with tempfile.TemporaryDirectory() as td:
            sigs = {c: mod.chunk_signature(c, "voice1", "s2.1-pro", 1.25) for c in chunks}

            # Run 1: the transport fails on chunk 3 of 5.
            calls = []
            buy = _transport(calls, fail_on="c3")
            for i, c in enumerate(chunks):
                try:
                    mod.chunk_or_bank(c, i, td, sigs[c], buy)
                except RuntimeError:
                    break
            self.assertEqual(len(calls), 3, "run 1 should stop at the failed chunk 3")

            # Run 2: chunks 1 and 2 are banked, so only 3, 4 and 5 are bought.
            calls = []
            buy = _transport(calls)
            for i, c in enumerate(chunks):
                mod.chunk_or_bank(c, i, td, sigs[c], buy)
            self.assertEqual(len(calls), 3, "the retry re-bought banked chunks")
            self.assertEqual(calls, ["c3", "c4", "c5"])

            # Run 3: nothing left to buy.
            calls = []
            buy = _transport(calls)
            for i, c in enumerate(chunks):
                _, reused = mod.chunk_or_bank(c, i, td, sigs[c], buy)
                self.assertTrue(reused)
            self.assertEqual(calls, [], "a fully banked speech bought audio again")


class NormalizeSwitchTest(unittest.TestCase):
    def test_normalize_stays_accepted_and_can_now_be_turned_off(self):
        mod = _load("synthesize_full_speech_pd318_norm")
        parser = mod.build_parser()
        required = ["--speech", "s.md", "--out", "a.mp3"]
        self.assertTrue(parser.parse_args(required).normalize, "default is on")
        self.assertTrue(parser.parse_args(required + ["--normalize"]).normalize)
        self.assertFalse(parser.parse_args(required + ["--no-normalize"]).normalize)

    def test_the_help_text_names_the_way_to_turn_normalization_off(self):
        mod = _load("synthesize_full_speech_pd318_norm_b")
        help_text = mod.build_parser().format_help()
        self.assertIn("--no-normalize", help_text)


if __name__ == "__main__":
    unittest.main()
