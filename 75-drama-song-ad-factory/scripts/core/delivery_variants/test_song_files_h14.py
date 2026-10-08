"""H14: delivery folder must carry the song as audio files. Run:
python3 -m unittest scripts/core/delivery_variants/test_song_files_h14.py
(from the skill folder, or with scripts/core on sys.path)."""
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_variants import song_files as sf  # noqa: E402
import qc_gate  # noqa: E402

FF = shutil.which("ffmpeg")


@unittest.skipUnless(FF and shutil.which("ffprobe"), "ffmpeg required")
class SongFiles(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.mix = self.t / "mix.wav"
        subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", str(self.mix)], check=True)
        self.d = self.t / "delivery"

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def build(self, instr=None):
        rows = sf.build_song_files(self.mix, self.d, "Kiesett Ad", instr)
        sf.write_song_docs(self.d, rows)
        return rows

    def test_full_delivery_passes_and_lists(self):
        rows = self.build(instr=self.mix)
        self.assertEqual(sorted(r["file"] for r in rows), [
            "Kiesett-Ad-instrumental.mp3", "Kiesett-Ad-instrumental.wav",
            "Kiesett-Ad.mp3", "Kiesett-Ad.wav"])
        self.assertEqual(sf.check_song_files(self.d, "Kiesett Ad")[0], "PASS")
        self.assertIn("Kiesett-Ad.mp3", (self.d / "README.md").read_text())
        mp3 = [r for r in rows if r["file"] == "Kiesett-Ad.mp3"][0]
        self.assertGreaterEqual(mp3["bit_rate"], 315000)

    def test_no_instrumental_is_fine(self):
        self.build()
        self.assertEqual(sf.check_song_files(self.d, "Kiesett Ad")[0], "PASS")

    def test_missing_song_file_fails_qc(self):
        self.build()
        (self.d / "Kiesett-Ad.wav").unlink()
        v, why = sf.check_song_files(self.d, "Kiesett Ad")
        self.assertEqual(v, "FAIL"); self.assertIn("Kiesett-Ad.wav", why)

    def test_missing_instrumental_listed_in_receipt_fails(self):
        self.build(instr=self.mix)
        (self.d / "Kiesett-Ad-instrumental.mp3").unlink()
        self.assertEqual(sf.check_song_files(self.d, "Kiesett Ad")[0], "FAIL")

    def test_unlisted_in_readme_fails(self):
        self.build()
        (self.d / "README.md").write_text("# nothing\n")
        self.assertEqual(sf.check_song_files(self.d, "Kiesett Ad")[0], "FAIL")

    def test_no_receipt_fails_and_cli_exit(self):
        self.d.mkdir()
        self.assertEqual(sf.check_song_files(self.d, "x")[0], "FAIL")
        self.assertEqual(sf._cli(["check", str(self.d), "x"]), 5)

    def test_rewrite_keeps_other_readme_content_once(self):
        self.d.mkdir()
        (self.d / "README.md").write_text("# Mine\n\nkeep me\n")
        self.build(); self.build()
        txt = (self.d / "README.md").read_text()
        self.assertIn("keep me", txt); self.assertEqual(txt.count("song-files:begin"), 1)

    def test_qc_gate_knows_the_check(self):
        self.assertIn("song_files", qc_gate.CHECKS)
        res = qc_gate.evaluate("r", "delivery", [], {}, ["song_files"])
        self.assertEqual(res["failures"][0]["code"], "MISSING_QC")


if __name__ == "__main__":
    unittest.main()
