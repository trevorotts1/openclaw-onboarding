#!/usr/bin/env python3
"""DEL-13 end-to-end: one REAL run through the packaging entry point.

The whole run, for real: this test first BUILDS a non-empty run folder with
the real producer inputs (an approved script and its approval record, the
approved storyboard records and stills, the character brief and reference
pictures, three audio sources, measured word timings, a timeline and a
rendered master -- media through ffmpeg, records as JSON, never fixture
deliverable bytes), then calls ``package_run``. Each of the twelve package
items is produced by THAT component's real deliver path reading that run:
``build_audio_versions``, ``write_delivery``, ``render``, ``deliver``,
``build_video_delivery``, ``deliver_clips``, ``prepare``+``write_kit``,
``build_cover``, ``write_delivery`` (lyrics), ``export_captions_srt``,
``copy_character_images``, ``build_welcome_sheet``. The test then opens
every produced file exactly as the client would -- PDF header, SRT cue
structure, media non-empty -- and ``contract.verify_folder`` must report all
twelve items present with zero missing.

No skip anywhere: a run that cannot build or a producer that refuses fails
this class loudly instead of turning green by doing nothing.

Proofs carried here:
  * the fixture helper ``contract.produce_item`` is REPLACED BY A RAISER for
    a full second packaging run -- all twelve adapters still produce every
    item, so no adapter reaches for fixture bytes;
  * the negative control removes one REAL produced item from a copy of this
    run's package and ``verify_folder`` must fail naming exactly that item.

Run: python3 delivery_package/test_delivery_package_e2e.py
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_package.contract as C           # noqa: E402
import delivery_package.packaging as P          # noqa: E402
import protected_names as PN                     # noqa: E402
import script_approval as SA                     # noqa: E402
from sung_hook import sung_hook as SH            # noqa: E402

# --------------------------------------------------------------- run inputs ---
#: Generic fixture material only -- no client name ever enters the repository.
TITLE = "Morning Light Sample"
LINK = "https://example.com/sample"
AD_LENGTH_S = 180            # a 3 minute ad: owes the 60 and 90 second clips
LINE_S = 4.0                 # one timeline line every 4 s
TIMELINE_S = 21 * LINE_S     # 84.0 <= master_max_s(90) = 88, hooks fit both cuts
MASTER_S = 85

SHEET = [
    {"tag": "verse one", "lines": [
        "She opens the curtains as the light comes in",
        "The kitchen smells of coffee and warm bread",
        "She writes one line in the little blue book",
    ]},
    {"tag": "hook", "lines": [
        "Morning is the part of the day that is hers",
        "Before the street wakes up she takes her time",
        "One small ritual and the whole day turns",
    ]},
    {"tag": "verse two", "lines": [
        "The neighbours pass and wave from the front gate",
        "She reads the page she wrote the day before",
        "The kettle sings and the radio comes on",
    ]},
    {"tag": "final hook", "lines": [
        "Morning is the part of the day that is hers",
        "She closes the book and steps into the light",
        "One small ritual and the whole day turns",
    ]},
]

BRIEF = {
    "title": TITLE,
    "offer": "A gentle morning routine that fits before the house wakes",
    "link": LINK,
    "shape": "9:16",
    "length_s": AD_LENGTH_S,
    "character_new": "1",
    "character_name": "Sample Character",
    "character_description": ("A warm, practical person in their late thirties "
                              "who shows up early and helps the neighbours "
                              "without being asked."),
    "character_background": ("Grew up in a small coastal town, ran the family "
                             "shop for twelve years, and learned to fix "
                             "everything twice."),
    "character_ethnicity": ("Medium-brown skin, tight coily hair kept short, "
                            "a broad easy smile, about five foot eight with a "
                            "steady build."),
    "character_voice_notes": "Low, unhurried, warm.",
}

VIEWS = ("close-up", "side-profile", "three-quarter", "full-standing")


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _png_bytes(salt, size=48, colour=(90, 130, 170)):
    """A real, openable PNG (the run's stills and reference pictures)."""
    h = zlib.crc32(str(salt).encode())
    px = bytes(((h + colour[0]) % 256, (h + colour[1]) % 256,
                (h + colour[2]) % 256))
    raw = b"".join(b"\x00" + px * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


def _write_png(path, salt, size=48, colour=(90, 130, 170)):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes(salt, size, colour))


def _ffmpeg(argv):
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError("ffmpeg failed (%s): %s"
                           % (proc.returncode, (proc.stderr or "")[-500:]))


def _w(run, rel, obj):
    path = Path(run) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return path


def build_real_run(run_dir):
    """Build a NON-EMPTY run folder with the twelve producers' real inputs.

    Media through ffmpeg (three audio sources, a rendered master), stills and
    reference pictures as real PNG files, the approval records, the measured
    word timings, the timeline and the character records as JSON. Nothing in
    this run is a deliverable: every file is an INPUT the real deliver paths
    read.
    """
    run_dir = Path(run_dir)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    # approved script + its approval record (script_pdf, lyric_sheet, kit)
    lyrics = "\n".join(ln for sec in SHEET for ln in sec["lines"])
    story = [["opening", list(SHEET[0]["lines"])],
             ["the turn", list(SHEET[3]["lines"])]]
    _w(run_dir, "creative/script.json",
       {"title": TITLE, "sheet": SHEET, "story": story, "lyrics": lyrics})
    _w(run_dir, "creative/script-approval.json",
       {"required": True, "status": "approved",
        "lyrics_sha": SA.lyrics_sha(lyrics), "sent": True})

    # brief + card answers (kit, chosen length, storyboard approval)
    _w(run_dir, "brief.json", dict(BRIEF))
    _w(run_dir, "card-answers.json", [
        {"id": "length", "text": "3 minutes", "n": AD_LENGTH_S},
        {"id": "shape", "text": "9:16 vertical"},
        {"id": "storyboard_approval", "text": "Yes"},
        {"id": "script_approval", "text": "Yes"},
    ])

    # approved storyboard: shots, cards, stills, gate + approval records
    shots, contracts, stills = [], {}, {}
    for i in range(6):
        sid = "s%d" % (i + 1)
        start = i * 14.0
        shots.append({"shot_id": sid, "song_start": start,
                      "song_end": start + 14.0,
                      "story_stage": "setup" if i < 3 else "rise",
                      "location_id": "kitchen" if i % 2 == 0 else "window",
                      "character_ids": ["sample-character"],
                      "status": "storyboard_approved"})
        contracts[sid] = {
            "lyric_text": SHEET[i % len(SHEET)]["lines"][0],
            "viewer_understanding": "the morning routine carries on",
            "character_action": "moves through the room at her own pace",
            "visible_emotion": "warm, unhurried",
        }
        rel = os.path.join("storyboard", "stills", sid + ".png")
        _write_png(run_dir / rel, sid, size=160,
                   colour=(70 + i * 25, 110, 160))
        stills[sid] = rel
    _w(run_dir, "storyboard/shot-list.json", {"shots": shots})
    _w(run_dir, "storyboard/contracts.json", contracts)
    _w(run_dir, "storyboard/stills.json", stills)
    _w(run_dir, "storyboard/gate.json",
       {"shots": shots, "review": {"outcome": "pass"}})
    _w(run_dir, "storyboard/approval.json",
       {"state": "approved", "choice": "yes"})

    # character: the brief's reference pictures + the library record
    ref_dir = run_dir / "character" / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_paths = []
    for i, view in enumerate(VIEWS):
        path = ref_dir / (view + ".png")
        _write_png(path, "ref-" + view, size=96, colour=(120 + i * 20, 90, 70))
        ref_paths.append(str(path))
    brief = dict(BRIEF)
    brief["character_reference_images"] = ref_paths
    _w(run_dir, "character/brief.json", brief)
    _w(run_dir, "character/records.json", [{
        "name": "Sample Character",
        "slug": "sample-character",
        "views": dict(zip(VIEWS, ref_paths)),
        "reference_paths": ref_paths,
    }])

    # music: the three audio sources item 01 re-encodes + measured timings
    (run_dir / "music").mkdir(parents=True, exist_ok=True)
    for name, freq in (("mix", 330), ("instrumental", 246), ("vocal-stem", 440)):
        _ffmpeg(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                 "-i", "sine=frequency=%d:duration=%s" % (freq, MASTER_S),
                 "-c:a", "libmp3lame", "-b:a", "192k",
                 str(run_dir / "music" / (name + ".mp3"))])
    words, t = [], 0.45
    for sec in SHEET:
        for line in sec["lines"]:
            for tok in PN._tokens(line):
                words.append({"word": tok, "start": round(t, 3),
                              "end": round(t + 0.35, 3)})
                t += 0.45
    _w(run_dir, "music/word-timings.json",
       {"ok": True, "source": "suno-alignedWords", "words": words})

    # edit: the timeline (hook flags from the run's own sung_hook) + master
    hooks = SH.hook_times(TIMELINE_S)
    lines = []
    for i in range(int(TIMELINE_S // LINE_S)):
        start = i * LINE_S
        lines.append({"line_id": "L%d" % i, "start_s": start,
                      "end_s": start + LINE_S, "beat": "beat%d" % (i // 4),
                      "hook": any(start <= h < start + LINE_S
                                  for h in hooks)})
    _w(run_dir, "edit/timeline.json",
       {"schema_version": "blackceo.timeline/v1", "lines": lines})
    _ffmpeg(["ffmpeg", "-y", "-v", "error",
             "-f", "lavfi", "-i",
             "testsrc2=s=320x568:r=15:d=%s" % MASTER_S,
             "-f", "lavfi", "-i",
             "sine=frequency=440:duration=%s" % MASTER_S,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
             "-c:a", "aac", "-profile:a", "aac_low", "-ar", "48000",
             "-b:a", "128k", "-ac", "2", "-movflags", "+faststart",
             str(run_dir / "edit" / "ad.mp4")])
    return run_dir


class DeliveryPackageEndToEnd(unittest.TestCase):
    """One REAL run -> packaging entry point -> 12 files that open."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="del13-e2e-"))
        cls.run_dir = build_real_run(cls.tmp / "run")
        # the run is NON-EMPTY and carries real inputs, not fixture bytes
        inputs = [cls.run_dir / "edit" / "ad.mp4",
                  cls.run_dir / "creative" / "script.json",
                  cls.run_dir / "music" / "word-timings.json"]
        for path in inputs:
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError("run input missing: %s" % path)
        cls.out = cls.tmp / "delivery"
        # a refusal here is an ERROR, never a skip: the class must run.
        cls.result = P.package_run(cls.run_dir, cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_01_real_run_packages_all_twelve_items_and_they_open(self):
        # the packaging call itself: every component discovered, every item
        # written under its canonical numbered name, folder verified.
        self.assertEqual(len(self.result["items"]), 12)
        report = C.verify_folder(self.out)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])
        self.assertEqual(sorted(report["present"]),
                         sorted(item.key for item in C.PACKAGE_ITEMS))

        # every one of the 12 package items exists AND opens
        for item in C.PACKAGE_ITEMS:
            for name, kind in zip(item.files, item.kinds):
                path = self.out / name
                with self.subTest(item=item.key, file=name, kind=kind):
                    self.assertTrue(path.exists(), "%s missing" % name)
                    self._opens(path, kind)

        # the files are the producers' own output, never fixture bytes
        fixture_bytes = (C.PDF_BYTES, C.MEDIA_BYTES, C.PNG_BYTES, C.NOTE_BYTES,
                         C.SRT_TEXT.encode("utf-8"))
        for item in C.PACKAGE_ITEMS:
            for name, kind in zip(item.files, item.kinds):
                if kind.startswith("images"):
                    continue
                blob = (self.out / name).read_bytes()
                with self.subTest(item=item.key, file=name, real=True):
                    self.assertNotIn(blob, fixture_bytes,
                                     "%s landed as fixture bytes" % name)

    def test_02_every_component_exports_produce_delivery(self):
        # no component is "not landed" any more; all twelve are wired.
        for item in C.PACKAGE_ITEMS:
            fn, note = P.resolve_producer(item)
            self.assertIsNotNone(fn, "%s not wired: %s" % (item.key, note))
            self.assertIn("wired via", note)
            dotted = note.split("wired via ", 1)[1]
            module = importlib.import_module(dotted)
            self.assertFalse(hasattr(module, "produce_item"),
                             "%s still imports the fixture helper" % dotted)

    def test_03_negative_control_one_real_item_removed_fails_the_folder(self):
        # the twelve-item gate is hard: take ONE real produced item out of a
        # copy of THIS run's package, the folder must fail and name it.
        folder = self.tmp / "neg"
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(self.out, folder)
        victim = C.ITEMS_BY_KEY["welcome_sheet"]
        first = folder / victim.files[0]
        self.assertTrue(first.is_file(), "expected a real produced welcome sheet")
        first.unlink()
        report = C.verify_folder(folder)
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing"], [victim.key])
        self.assertEqual(report["problems"][0]["file"], victim.files[0])

    def test_04_no_adapter_reaches_the_fixture_helper(self):
        # P1 proof: contract.produce_item raises for a full packaging run and
        # all twelve adapters still produce every item from the run's inputs.
        original = C.produce_item

        def boom(*_args, **_kw):
            raise AssertionError("produce_item (test fixture helper) was "
                                 "reached by a deliver path")

        C.produce_item = boom
        try:
            out = self.tmp / "delivery-no-fixture"
            result = P.package_run(self.run_dir, out)
            self.assertEqual(len(result["items"]), 12)
            report = C.verify_folder(out)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["missing"], [])
            for item in C.PACKAGE_ITEMS:
                for name, kind in zip(item.files, item.kinds):
                    if kind.startswith("images"):
                        continue
                    blob = (out / name).read_bytes()
                    self.assertNotIn(
                        blob, (C.PDF_BYTES, C.MEDIA_BYTES, C.PNG_BYTES,
                               C.NOTE_BYTES, C.SRT_TEXT.encode("utf-8")),
                        "%s came out as fixture bytes with produce_item "
                        "raising" % name)
        finally:
            C.produce_item = original

    def _opens(self, path, kind):
        """Open one delivered file the way the contract defines 'opens'."""
        if kind.startswith("images"):
            self.assertTrue(path.is_dir(), "%s is not a directory" % path.name)
            images = [p for p in path.rglob("*")
                      if p.is_file()
                      and p.suffix.lower() in C.IMAGE_SUFFIXES]
            self.assertGreaterEqual(len(images), C.MIN_IMAGES, path.name)
            for image in images:
                self.assertGreater(image.stat().st_size, 0, image.name)
            return
        self.assertTrue(path.is_file(), "%s is not a file" % path.name)
        self.assertGreater(path.stat().st_size, 0, "%s is empty" % path.name)
        if kind == "pdf":
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(5), b"%PDF-",
                                 "%s has no PDF header" % path.name)
        elif kind == "srt":
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text, r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}",
                "%s has no cue timing line" % path.name)
            self.assertRegex(text, r"(?m)^\d+\s*$",
                             "%s has no cue index line" % path.name)


class DeliveryNamesAgree(unittest.TestCase):
    """ONE scheme: every producer's native delivery name IS the contract's.

    The packaging adapters call each producer's own path, so a real run also
    writes through each producer's CLI / deliver() entry. Those two paths
    must name a file the same way, or a real delivery folder fails the Q12
    gate that the packaging test just proved green. This is the drift guard:
    it pins each producer's constant to the contract, so a rename in one
    place cannot land without the other.
    """

    def _module(self, dotted):
        return importlib.import_module(dotted)

    def test_single_file_items_use_the_contract_name(self):
        # producers whose item is exactly one file, named by a module constant
        for key, attr, dotted in (
                ("character_bible", "DELIVERY_PDF_NAME",
                 "character_bible.character_bible"),
                ("storyboard_pdf", "DELIVERY_NAME",
                 "storyboard_grid.storyboard_grid"),
                ("ready_to_post_kit", "PDF_NAME",
                 "ready_post_kit.ready_post_kit"),
                ("lyric_sheet", "FILE_NAME", "lyric_sheet.lyric_sheet"),
                ("welcome_sheet", "WELCOME_SHEET_FILE",
                 "delivery_package.package_items")):
            with self.subTest(item=key, module=dotted):
                expected = C.ITEMS_BY_KEY[key].files[0]
                self.assertEqual(getattr(self._module(dotted), attr),
                                 expected)

    def test_multi_file_items_use_the_contract_names(self):
        # audio versions: every file shares the ITEM number, told apart by
        # label -- never a second numbering of their own.
        from delivery_variants import song_files as sf
        audio = C.ITEMS_BY_KEY["audio_versions"]
        self.assertEqual(sf.VERSION_NOTE_NAME, audio.files[3])
        self.assertEqual([name for _k, _l, name in sf.expected_version_files()],
                         list(audio.files[:3]))
        for name in sf.expected_version_files():
            self.assertTrue(name[2].startswith(sf.ITEM_NUMBER + " - "))

        # the two videos and the two clips share their item number too.
        from delivery_variants import video_delivery as vd
        video = C.ITEMS_BY_KEY["video"]
        self.assertEqual(vd.captioned_name("Any Ad"), video.files[0])
        self.assertEqual(vd.clean_name("Any Ad"), video.files[1])

        from delivery_clips import delivery_clips as dc
        clips = C.ITEMS_BY_KEY["clips"]
        self.assertEqual(dc.clip_file_name(60), clips.files[0])
        self.assertEqual(dc.clip_file_name(90), clips.files[1])

    def test_directory_items_deliver_into_the_contract_directory(self):
        from delivery_variants import cover_image as ci
        self.assertEqual(ci.cover_file_name("Any Ad"),
                         C.ITEMS_BY_KEY["cover_thumbnail"].files[0])
        from character_images import character_images as cimg
        self.assertEqual(cimg.DELIVERY_DIR_NAME,
                         C.ITEMS_BY_KEY["character_images"].files[0])

    def test_character_bible_ships_both_contract_files(self):
        # DEL-02 is the PDF *and* its picture directory (P2).
        bible = C.ITEMS_BY_KEY["character_bible"]
        self.assertEqual(len(bible.files), 2)
        from character_bible import character_bible as cb
        self.assertEqual(cb.DELIVERY_PDF_NAME, bible.files[0])
        self.assertEqual(bible.files[1], "02 - Character Bible Images")

    def test_caption_and_script_names_are_the_contract_names(self):
        from delivery_variants import caption_srt as cs
        self.assertEqual(cs.srt_file_name(),
                         C.ITEMS_BY_KEY["captions_srt"].files[0])
        from script_pdf import script_pdf as sp
        self.assertEqual(sp.PDF_NAME, C.ITEMS_BY_KEY["script_pdf"].files[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
