"""DEL-01: three clearly-labelled audio versions + a plain-English note.

Run: python3 -m unittest scripts/core/delivery_variants/test_audio_versions_del01.py
(from the skill folder, or with scripts/core on sys.path)."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_variants import song_files as sf  # noqa: E402
import qc_gate  # noqa: E402

FF = shutil.which("ffmpeg")

# Banned in client-facing text: model names, tool names, dollar amounts,
# income promises (DEL-01 task contract).
_BANNED = re.compile(
    r"\b(suno|kie|ffmpeg|ffprobe|claude|gpt|openai|anthropic|whisper|"
    r"elevenlabs|minimax|seedance|veo|kling)\b|"
    r"\$\d|\bdollars?\b|\bearn(?:ing|s)?\b|\bincome\b|\bprofit\b|\bguarantee(?:d)?\b",
    re.I)


@unittest.skipUnless(FF and shutil.which("ffprobe"), "ffmpeg required")
class AudioVersions(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.mix = self.t / "mix.wav"
        self.instr = self.t / "instrumental.wav"
        self.stem = self.t / "vocal-stem.wav"
        for p, freq in ((self.mix, 440), (self.instr, 330), (self.stem, 550)):
            subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=%d:duration=2" % freq, str(p)],
                           check=True)
        self.d = self.t / "delivery"

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def build(self):
        rows = sf.build_audio_versions(self.mix, self.d, self.instr, self.stem)
        sf.write_version_docs(self.d, rows)
        return rows

    def test_three_numbered_mp3s_and_note(self):
        rows = self.build()
        files = sorted(r["file"] for r in rows)
        self.assertEqual(files, [
            "01 - About These Audio Files.txt",
            "01 - Full Song.mp3",
            "01 - Instrumental.mp3",
            "01 - Voice Only.mp3"])
        for r in rows:
            self.assertTrue((self.d / r["file"]).is_file())

    def test_check_passes_and_cli_exit_zero(self):
        self.build()
        v, why = sf.check_audio_versions(self.d)
        self.assertEqual(v, "PASS", why)
        self.assertEqual(sf._cli(["check-versions", str(self.d)]), 0)

    def test_note_is_plain_english_no_banned_words(self):
        self.build()
        note = (self.d / sf.VERSION_NOTE_NAME).read_text(encoding="utf-8")
        self.assertIsNone(_BANNED.search(note), _BANNED.search(note))
        for _num, label, desc in sf.DELIVERY_VERSIONS:
            self.assertIn(label, note)
        self.assertIn("same song three ways", note)

    def test_labels_and_note_cannot_drift(self):
        # One table drives labels, note and QC expectations. Every file of
        # this package item carries the ITEM number (01), never a second
        # numbering of its own -- the contract owns the names.
        text = sf.version_note_text()
        for _key, label, _d in sf.DELIVERY_VERSIONS:
            self.assertIn("%s - %s" % (sf.ITEM_NUMBER, label), text)
            self.assertIn(sf.version_file_name(sf.ITEM_NUMBER, label), [
                f for _n, _l, f in sf.expected_version_files()])

    def test_missing_source_refuses_never_two_versions(self):
        with self.assertRaises(ValueError):
            sf.build_audio_versions(self.mix, self.d, None, self.stem)
        with self.assertRaises(ValueError):
            sf.build_audio_versions(self.mix, self.d, "", self.stem)
        with self.assertRaises(ValueError):
            sf.build_audio_versions(self.mix, self.d,
                                    self.t / "nope.wav", self.stem)
        empty = self.t / "empty.wav"
        empty.write_bytes(b"")
        with self.assertRaises(ValueError):
            sf.build_audio_versions(self.mix, self.d, empty, self.stem)

    def test_missing_version_file_fails_qc(self):
        self.build()
        (self.d / "01 - Instrumental.mp3").unlink()
        v, why = sf.check_audio_versions(self.d)
        self.assertEqual(v, "FAIL")
        self.assertIn("01 - Instrumental.mp3", why)

    def test_missing_note_fails_qc(self):
        self.build()
        (self.d / sf.VERSION_NOTE_NAME).unlink()
        v, why = sf.check_audio_versions(self.d)
        self.assertEqual(v, "FAIL")
        self.assertIn(sf.VERSION_NOTE_NAME, why)

    def test_unlisted_in_receipt_or_readme_fails(self):
        self.build()
        (self.d / "README.md").write_text("# nothing\n")
        self.assertEqual(sf.check_audio_versions(self.d)[0], "FAIL")
        self.build()
        rec = json.loads((self.d / sf.RECEIPT_NAME).read_text())
        rec["audio_versions"] = [r for r in rec["audio_versions"]
                                 if r["file"] != "01 - Full Song.mp3"]
        (self.d / sf.RECEIPT_NAME).write_text(json.dumps(rec))
        self.assertEqual(sf.check_audio_versions(self.d)[0], "FAIL")

    def test_no_receipt_fails(self):
        self.d.mkdir()
        self.assertEqual(sf.check_audio_versions(self.d)[0], "FAIL")

    def test_rewrite_keeps_other_readme_content_once(self):
        self.d.mkdir()
        (self.d / "README.md").write_text("# Mine\n\nkeep me\n")
        self.build(); self.build()
        txt = (self.d / "README.md").read_text()
        self.assertIn("keep me", txt)
        self.assertEqual(txt.count("audio-versions:begin"), 1)

    def test_mp3_bitrate_and_duration(self):
        rows = self.build()
        for r in rows:
            if r["kind"] != "audio-version":
                continue
            self.assertGreaterEqual(r["bit_rate"], 315000)
            self.assertGreater(r["duration_s"], 1.0)

    def test_receipt_carries_all_three_and_note(self):
        rows = self.build()
        rec = json.loads((self.d / sf.RECEIPT_NAME).read_text())
        kinds = {r["kind"] for r in rec["audio_versions"]}
        self.assertEqual(kinds, {"audio-version", "audio-version-note"})
        # every file of this package item carries the ITEM number; the three
        # are told apart by label (and the internal source key), never by a
        # second numbering of their own.
        versions = [r for r in rec["audio_versions"]
                    if r["kind"] == "audio-version"]
        self.assertEqual({r["number"] for r in versions}, {sf.ITEM_NUMBER})
        self.assertEqual(sorted(r["source"] for r in versions),
                         ["instrumental", "mix", "vocal"])

    def test_qc_gate_knows_the_check(self):
        self.assertIn("audio_versions", qc_gate.CHECKS)
        res = qc_gate.evaluate("r", "delivery", [], {}, ["audio_versions"])
        self.assertEqual(res["failures"][0]["code"], "MISSING_QC")


if __name__ == "__main__":
    unittest.main()
