"""DEL-13: the client delivery folder contract -- 12 package items, numbered.

One delivery folder per client run, clear numbered file names. PACKAGE_ITEMS
below is THE canonical numbered file-name list: item 1..12, each with the exact
file names it must ship. Both distributions carry this file byte for byte
(scripts/core/delivery_package/ in the onboarding skill and in the runtime
twin), so the two run the same contract.

The run FAILS when the folder misses any item -- delivery_checklist Q12
(PACKAGE_COMPLETE) reads this contract and names every missing item in
repair_scope, and packaging.packaging.package_run refuses to hand over a
folder that does not verify.

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

CONTRACT_VERSION = "1.0.0"

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

PACKAGE_ITEMS = (
    Item("audio_versions", 1, "DEL-01", "THREE AUDIO VERSIONS plus note",
         ("01-audio-main.mp3", "01-audio-main.wav",
          "01-audio-instrumental.mp3", "01-audio-note.md"),
         ("media", "media", "media", "text"),
         ("delivery_variants.three_audio", "audio_versions",
          "delivery_variants.song_files")),
    Item("character_bible", 2, "DEL-02", "CHARACTER BIBLE PDF with image bible",
         ("02-character-bible.pdf", "02-character-bible-images"),
         ("pdf", "images"),
         ("character_bible", "character_library.character_library",
          "character_library")),
    Item("script_pdf", 3, "DEL-03", "SCRIPT PDF",
         ("03-script.pdf",),
         ("pdf",),
         ("script_approval.script_approval", "script_pdf")),
    Item("storyboard_pdf", 4, "DEL-04", "STORYBOARD PDF",
         ("04-storyboard.pdf",),
         ("pdf",),
         ("storyboard_pdf", "storyboard_director.storyboard_director")),
    Item("video", 5, "DEL-05", "VIDEO clean and captioned",
         ("05-video-clean.mp4", "05-video-captioned.mp4"),
         ("media", "media"),
         ("captions_burn.captions_burn", "captions_burn", "video_delivery")),
    Item("clips", 6, "DEL-06", "60 and 90 SECOND CLIPS",
         ("06-clip-60s.mp4", "06-clip-90s.mp4"),
         ("media", "media"),
         ("clip_cutdown.clip_cutdown", "clip_cutdown")),
    Item("ready_to_post_kit", 7, "DEL-07", "READY-TO-POST KIT PDF",
         ("07-ready-to-post-kit.pdf",),
         ("pdf",),
         ("batch_zip.batch_zip", "ready_to_post_kit")),
    Item("cover_thumbnail", 8, "DEL-08", "COVER THUMBNAIL",
         ("08-cover-thumbnail.png",),
         ("media",),
         ("cover_thumbnail",)),
    Item("lyric_sheet", 9, "DEL-09", "LYRIC SHEET PDF",
         ("09-lyric-sheet.pdf",),
         ("pdf",),
         ("lyric_sheet", "sung_hook.sung_hook")),
    Item("captions_srt", 10, "DEL-10", "SRT CAPTION FILE",
         ("10-captions.srt",),
         ("srt",),
         ("srt_export", "captions_burn.captions_burn", "caption_timing")),
    Item("character_images", 11, "DEL-11",
         "CHARACTER IMAGES as separate full-resolution files",
         ("11-character-images",),
         ("images",),
         ("character_library.character_library", "character_library",
          "character_images")),
    Item("welcome_sheet", 12, "DEL-12", "WELCOME SHEET PDF",
         ("12-welcome-sheet.pdf",),
         ("pdf",),
         ("welcome_sheet",)),
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


def write_reference_package(folder):
    """Write a complete, generic 12-item folder for tests. Not a deliverable.

    Fixture only: placeholder bytes that open under this contract (PDF header,
    SRT cue block, non-empty media, image files). No client name, no model
    name, no absolute path.
    """
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    srt = ("1\n00:00:00,000 --> 00:00:02,000\nfixture caption line\n\n"
           "2\n00:00:02,000 --> 00:00:04,000\nsecond fixture line\n")
    png = b"\x89PNG\r\n\x1a\n" + b"fixture-image" * 4
    media = b"fixture-media-bytes" * 16
    note = b"# Audio versions note\n\nThree audio versions of one cut.\n"
    for item in PACKAGE_ITEMS:
        for name, kind in zip(item.files, item.kinds):
            target = root / name
            if kind.startswith("images"):
                target.mkdir(parents=True, exist_ok=True)
                (target / "01.png").write_bytes(png)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind == "pdf":
                target.write_bytes(pdf)
            elif kind == "srt":
                target.write_text(srt, encoding="utf-8")
            elif kind == "text":
                target.write_bytes(note)
            else:
                target.write_bytes(media)
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
        if dest.is_dir():
            shutil.rmtree(dest)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        written.append(dest)
    return written
