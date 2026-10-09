#!/usr/bin/env python3
"""FU-U14 tests: the song mp3 is part of the deliverable.

Trevor's order: "make an update so that the mp3 is a part of the
deliverable". Done-when cases:

  1. an ad folder with no song file FAILS the delivery battery (fail closed);
  2. a song file whose duration does not match the ad audio, or whose
     envelope does not cross-correlate at least 0.95 with it, FAILS;
  3. a matching song passes every row and the battery PASSes;
  4. build_batch_zip() writes one zip per client: one folder per author
     with the captioned ad, the clean master and the song mp3 (exactly
     three files per ad) plus a README listing every file, its duration,
     its resolution and the banner link.

Audio fixtures are tiny stdlib WAVs (wave module), so no ffmpeg and no
network are needed: the checker probes mp3 through ffprobe/ffmpeg when it
is present and always measures wav with the wave module.

Run: python3 scripts/core/delivery_checklist/test_song_mp3_u14.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import delivery_checklist.delivery_checklist as dc   # noqa: E402
import batch_zip.batch_zip as bz                      # noqa: E402

RATE = 8000
AUTHOR = "Kiesett Parker"
TITLE = "Stop Stale"
BANNER = "https://example.test/kiesett-stop-stale"


def write_wav(path, seconds=1.0, pattern="tone"):
    """Tiny deterministic WAV: gated tone (the ad audio) / other shape."""
    n = int(RATE * seconds)
    frames = []
    for i in range(n):
        t = i / RATE
        if pattern == "tone":
            amp = 0.6 if int(t * 4) % 2 else 0.3
            v = math.sin(2 * math.pi * 440.0 * t) * amp
        elif pattern == "other":
            # different envelope AND different content: a quiet rumble that
            # stops early, so both the duration and the correlation differ
            v = math.sin(2 * math.pi * 300.0 * t) * 0.5 if t < seconds / 2 else 0.0
        else:
            v = 0.0
        frames.append(struct.pack("<h", int(v * 32767)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(frames))


class SongMp3DoneWhen(unittest.TestCase):
    # ---- done-when 1: no song file -> FAIL closed ----------------------
    def test_missing_song_mp3_fails(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            ad_audio = d / "ad-audio.wav"
            write_wav(ad_audio, 1.0, "tone")
            bat = dc.delivery_battery(d, ad_audio, TITLE, AUTHOR)
            self.assertFalse(bat["pass"], bat["detail"])
            self.assertIn("SONG_MP3", bat["reason_code"])
            rows = bat["rows"]
            self.assertTrue(rows, "battery must carry rows")
            self.assertIn("no", {r.get("answer") for r in rows})
            self.assertIn("SONG_MP3", json.dumps(rows))
            # the row shape is the checklist's own (answer + measurement)
            for r in rows:
                self.assertIn(r.get("answer"), ("yes", "no"))
                self.assertIn("measurement", r)

    # ---- done-when 2: mismatched song -> FAIL --------------------------
    def test_mismatched_song_fails(self):
        with tempfile.TemporaryDirectory() as td:
            name = dc.safe_song_name(AUTHOR, TITLE) + ".wav"
            d = Path(td)
            ad_audio = d / "ad-audio.wav"
            write_wav(ad_audio, 1.0, "tone")
            write_wav(d / name, 0.5, "other")   # wrong length and content
            bat = dc.delivery_battery(d, ad_audio, TITLE, AUTHOR)
            self.assertFalse(bat["pass"], bat["detail"])
            rows = {r["item"]: r for r in bat["rows"]}
            self.assertEqual(rows["SONG_MP3_FILE"]["answer"], "yes")
            self.assertEqual(rows["SONG_MP3_DURATION"]["answer"], "no")
            # correlation row either measured low or unmeasurable -> "no"
            self.assertEqual(rows["SONG_MP3_CORRELATION"]["answer"], "no")
            self.assertIn("SONG_MP3", bat["repair_scope"][0])

    def test_same_length_wrong_content_fails_correlation(self):
        """Same duration, different envelope: only the 0.95 corr can catch it."""
        with tempfile.TemporaryDirectory() as td:
            name = dc.safe_song_name(AUTHOR, TITLE) + ".wav"
            d = Path(td)
            ad_audio = d / "ad-audio.wav"
            write_wav(ad_audio, 1.0, "tone")
            write_wav(d / name, 1.0, "other")
            bat = dc.delivery_battery(d, ad_audio, TITLE, AUTHOR)
            self.assertFalse(bat["pass"], bat["detail"])
            rows = {r["item"]: r for r in bat["rows"]}
            self.assertEqual(rows["SONG_MP3_DURATION"]["answer"], "yes")
            self.assertEqual(rows["SONG_MP3_CORRELATION"]["answer"], "no")

    # ---- done-when 3: matching song -> PASS ----------------------------
    def test_matching_song_passes(self):
        with tempfile.TemporaryDirectory() as td:
            name = dc.safe_song_name(AUTHOR, TITLE) + ".wav"
            d = Path(td)
            ad_audio = d / "ad-audio.wav"
            write_wav(ad_audio, 1.0, "tone")
            write_wav(d / name, 1.0, "tone")    # the ad's own audio, full length
            bat = dc.delivery_battery(d, ad_audio, TITLE, AUTHOR)
            self.assertTrue(bat["pass"], bat["detail"])
            self.assertEqual(bat["repair_scope"], [])
            rows = {r["item"]: r for r in bat["rows"]}
            self.assertEqual(rows["SONG_MP3_CORRELATION"]["answer"], "yes")
            self.assertGreaterEqual(rows["SONG_MP3_CORRELATION"]["value"], 0.95)

    # ---- done-when 4: one batch zip per client, 3 files per ad + README -
    def test_batch_zip_three_files_per_ad_plus_readme(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ads = []
            for author, title in (("Kiesett Parker", "Stop Stale"),
                                  ("Maria Anderson", "Marico")):
                adir = root / "ads" / title
                adir.mkdir(parents=True)
                cap = adir / ("%s - Ad (captioned).mp4" % title)
                master = adir / ("%s - Ad (clean master).mp4" % title)
                song = adir / (dc.safe_song_name(author, title) + ".mp3")
                for p in (cap, master, song):
                    p.write_bytes(b"\x00" * 16)
                ads.append({"author": author, "title": title,
                            "ad_dir": adir, "captioned": cap,
                            "clean_master": master, "song_mp3": song,
                            "duration_s": 60.0, "resolution": "1080x1920",
                            "banner": BANNER})
            out = root / "batch.zip"
            res = bz.build_batch_zip("Black CEO", ads, out,
                                    audio_gate=lambda p: {"ok": True})
            self.assertTrue(out.is_file())
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
            self.assertIn("README.md", names)
            body = [n for n in names if n != "README.md"]
            self.assertEqual(len(body), 3 * len(ads),
                             "exactly 3 files per ad: %s" % names)
            for ad in ads:
                folder = bz.folder_name(ad["author"], ad["title"], set())
                in_folder = [n for n in body if n.startswith(folder + "/")]
                self.assertEqual(len(in_folder), 3, in_folder)
                self.assertTrue(any(n.endswith(".mp3") for n in in_folder))
                self.assertTrue(any("captioned" in n for n in in_folder))
                self.assertTrue(any("clean" in n for n in in_folder))
            readme = zipfile.ZipFile(out).read("README.md").decode("utf-8")
            self.assertIn(BANNER, readme)
            self.assertIn("1080x1920", readme)
            self.assertIn("60.0", readme)
            for ad in ads:
                self.assertIn(Path(ad["captioned"]).name, readme)
                self.assertIn(Path(ad["clean_master"]).name, readme)
                self.assertIn(Path(ad["song_mp3"]).name, readme)

    def test_batch_zip_refuses_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ads = [{"author": AUTHOR, "title": TITLE,
                    "captioned": root / "nope.mp4",
                    "clean_master": root / "nope2.mp4",
                    "song_mp3": root / "nope3.mp3",
                    "banner": BANNER}]
            with self.assertRaises(bz.BatchZipError):
                bz.build_batch_zip("Black CEO", ads, root / "batch.zip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
