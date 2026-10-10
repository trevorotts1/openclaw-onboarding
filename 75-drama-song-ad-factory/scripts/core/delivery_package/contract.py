"""DEL-13: the client delivery folder contract -- 12 package items, numbered.

One delivery folder per client run, clear numbered file names. PACKAGE_ITEMS
below is THE canonical numbered file-name list: item 1..12, each with the exact
file names it must ship. Both distributions carry this file byte for byte
(scripts/core/delivery_package/ in the onboarding skill and in the runtime
twin), so the two run the same contract.

ONE naming scheme, used by every producer and by both halves of the package
(``contract`` here and ``package_items``, the client-facing map): every file
carries its two-digit item number, a space, a dash, a space, a human label and
its real extension -- ``01 - Full Song.mp3``, ``10 - Captions.srt``. A
producer writes that exact name; the packaging call copies it verbatim; the
folder gate opens it. No producer invents a second scheme.

The run FAILS when the folder misses any item -- delivery_checklist Q12
(PACKAGE_COMPLETE) reads this contract and names every missing item in
repair_scope, and packaging.package_run refuses to hand over a folder that
does not verify.

An item opens only when it opens:
  pdf   -- a real PDF header (%PDF-), never a renamed text file;
  srt   -- a cue block: an index line then a timing line "HH:MM:SS,mmm --> ..."
  media -- a non-empty file (the caller's own codec check stays where it was);
  text  -- a non-empty note;
  images-- a directory of separate non-empty image files (an image bible or a
           character set -- never one sprite sheet standing in for the set).

stdlib only, no network, no provider call, no client name, no operator path.

Run: python3 delivery_package/test_delivery_package_contract.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from collections import namedtuple

CONTRACT_VERSION = "1.1.0"

#: one package item: key, its 1-based number, the DEL unit that produces it,
#: the human label, the canonical file names, one kind per file, and the
#: candidate component modules (relative to core/) that may export
#: produce_delivery(run_dir, item) -> list[Path].
Item = namedtuple("Item", "key number unit label files kinds producers")

#: ponytail: an image set needs >= 1 file today; raise MIN_IMAGES to 2 when a
#: character-image producer is guaranteed to ship a set, not a single frame.
MIN_IMAGES = 1
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
_SRT_TIMING = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}", re.M)
_SRT_INDEX = re.compile(r"^\d+\s*$", re.M)

#: Canonical bytes for the TEST FIXTURE helper ``produce_item`` (and the
#: reference package built from it) only. No deliver path writes these:
#: every real producer reads its own inputs out of the run and ships its own
#: output (see ``delivery_package.run_inputs`` for where those inputs live).
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
SRT_TEXT = ("1\n00:00:00,000 --> 00:00:02,000\nfixture caption line\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nsecond fixture line\n")
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fixture-image" * 4
MEDIA_BYTES = b"fixture-media-bytes" * 16
NOTE_BYTES = b"# Audio versions note\n\nThree audio versions of one cut.\n"

PACKAGE_ITEMS = (
    Item("audio_versions", 1, "DEL-01", "THREE AUDIO VERSIONS plus note",
         ("01 - Full Song.mp3", "01 - Instrumental.mp3",
          "01 - Voice Only.mp3", "01 - About These Audio Files.txt"),
         ("media", "media", "media", "text"),
         ("delivery_variants.song_files",)),
    Item("character_bible", 2, "DEL-02", "CHARACTER BIBLE PDF with image bible",
         ("02 - Character Bible.pdf", "02 - Character Bible Images"),
         ("pdf", "images"),
         ("character_bible.character_bible",)),
    Item("script_pdf", 3, "DEL-03", "SCRIPT PDF",
         ("03 - SCRIPT.pdf",),
         ("pdf",),
         ("script_pdf.script_pdf",)),
    Item("storyboard_pdf", 4, "DEL-04", "STORYBOARD PDF",
         ("04 - Storyboard.pdf",),
         ("pdf",),
         ("storyboard_grid.storyboard_grid",)),
    Item("video", 5, "DEL-05", "VIDEO clean and captioned",
         ("05 - Video Captioned.mp4", "05 - Video Clean.mp4"),
         ("media", "media"),
         ("delivery_variants.video_delivery",)),
    Item("clips", 6, "DEL-06", "60 and 90 SECOND CLIPS",
         ("06 - Clip 60s.mp4", "06 - Clip 90s.mp4"),
         ("media", "media"),
         ("delivery_clips.delivery_clips",)),
    Item("ready_to_post_kit", 7, "DEL-07", "READY-TO-POST KIT PDF",
         ("07 - Ready-to-Post Kit.pdf",),
         ("pdf",),
         ("ready_post_kit.ready_post_kit",)),
    Item("cover_thumbnail", 8, "DEL-08", "COVER THUMBNAIL",
         ("08 - Cover Thumbnail.png",),
         ("media",),
         ("delivery_variants.cover_image",)),
    Item("lyric_sheet", 9, "DEL-09", "LYRIC SHEET PDF",
         ("09 - Lyric Sheet.pdf",),
         ("pdf",),
         ("lyric_sheet.lyric_sheet",)),
    Item("captions_srt", 10, "DEL-10", "SRT CAPTION FILE",
         ("10 - Captions.srt",),
         ("srt",),
         ("delivery_variants.caption_srt",)),
    Item("character_images", 11, "DEL-11",
         "CHARACTER IMAGES as separate full-resolution files",
         ("11 - Character Images",),
         ("images",),
         ("character_images.character_images",)),
    Item("welcome_sheet", 12, "DEL-12", "WELCOME SHEET PDF",
         ("12 - Welcome Sheet.pdf",),
         ("pdf",),
         ("delivery_package.welcome_sheet",)),
)

ITEMS_BY_KEY = {item.key: item for item in PACKAGE_ITEMS}
assert len(ITEMS_BY_KEY) == 12 == len(PACKAGE_ITEMS)


def _problem(path, kind):
    """None when the file opens, else the one sentence that says why not."""
    if kind.startswith("images"):
        if not path.is_dir():
            return "missing" if not path.exists() else "not a directory"
        images = [p for p in sorted(path.rglob("*"))
                  if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
        if len(images) < MIN_IMAGES:
            return "needs >= %d image file(s), found %d" % (MIN_IMAGES,
                                                            len(images))
        empty = [p.name for p in images if p.stat().st_size == 0]
        if empty:
            return "empty image file(s): %s" % ", ".join(empty)
        return None
    if not path.exists():
        return "missing"
    if not path.is_file():
        return "not a file"
    size = path.stat().st_size
    if size == 0:
        return "empty"
    if kind == "pdf":
        with open(path, "rb") as handle:
            if handle.read(5) != b"%PDF-":
                return "not a PDF (no %PDF- header)"
        return None
    if kind == "srt":
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "not UTF-8 text"
        if not _SRT_TIMING.search(text):
            return "no cue timing line (HH:MM:SS,mmm --> HH:MM:SS,mmm)"
        if not _SRT_INDEX.search(text):
            return "no cue index line"
        return None
    return None


def verify_folder(folder):
    """Check a delivery folder against all 12 package items. Never raises.

    Returns {"ok", "folder", "expected", "present", "missing", "problems"}
    where missing holds the package keys and problems names item + file +
    the sentence that failed. A folder that does not exist misses all 12.
    """
    root = Path(folder)
    report = {"contract_version": CONTRACT_VERSION, "folder": str(root),
              "expected": len(PACKAGE_ITEMS), "present": [], "missing": [],
              "problems": [], "ok": False}
    if not root.is_dir():
        report["missing"] = [item.key for item in PACKAGE_ITEMS]
        report["problems"] = [{"item": "", "unit": "", "file": str(root),
                               "problem": "delivery folder missing"}]
        return report
    for item in PACKAGE_ITEMS:
        bad = []
        for name, kind in zip(item.files, item.kinds):
            why = _problem(root / name, kind)
            if why is not None:
                bad.append(why)
                report["problems"].append({"item": item.key, "unit": item.unit,
                                           "file": name, "problem": why})
        if bad:
            report["missing"].append(item.key)
        else:
            report["present"].append(item.key)
    report["ok"] = not report["missing"]
    return report


def produce_item(item, out_dir):
    """TEST FIXTURE HELPER ONLY: write one item's canonical names with bytes
    that open under this contract. No deliver path may import or call it.

    This is the reference-package helper tests use to build a folder with no
    run behind it (PDF header, SRT cue block, non-empty media, image file,
    non-empty note). It never reads a run and never ships to a client: the
    twelve ``produce_delivery`` adapters read their own inputs out of the run
    (``delivery_package.run_inputs``) and call their producer's real deliver
    path instead. The packaging e2e runs all twelve with THIS function
    replaced by a raiser, so an adapter that reached for it would fail the
    suite rather than pass vacuously.
    """
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for name, kind in zip(item.files, item.kinds):
        target = root / name
        if kind.startswith("images"):
            target.mkdir(parents=True, exist_ok=True)
            (target / "01.png").write_bytes(PNG_BYTES)
            written.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "pdf":
            target.write_bytes(PDF_BYTES)
        elif kind == "srt":
            target.write_text(SRT_TEXT, encoding="utf-8")
        elif kind == "text":
            target.write_bytes(NOTE_BYTES)
        else:
            target.write_bytes(MEDIA_BYTES)
        written.append(target)
    return written


def write_reference_package(folder):
    """Write a complete, generic 12-item folder for tests. Not a deliverable.

    Fixture only (``produce_item`` bytes that open under this contract): no
    client name, no model name, no absolute path. The packaging e2e never
    uses this -- it runs the twelve real producers on a real run folder.
    """
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    for item in PACKAGE_ITEMS:
        produce_item(item, root)
    return root


def copy_item_sources(item, sources, out_dir):
    """Copy one item's produced sources into out_dir under the canonical names.

    sources must be one path per canonical file, in order; a directory item
    takes a directory source. Returns the destinations written.
    """
    if len(sources) != len(item.files):
        raise ValueError("%s produced %d file(s), contract wants %d"
                         % (item.key, len(sources), len(item.files)))
    written = []
    for name, src in zip(item.files, sources):
        src = Path(src)
        dest = Path(out_dir) / name
        if not src.exists():
            raise ValueError("%s source missing: %s" % (item.key, src.name))
        if dest.exists() and src.resolve() == dest.resolve():
            written.append(dest)        # packaging in place: already there
            continue
        if dest.is_dir():
            shutil.rmtree(dest)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        written.append(dest)
    return written
