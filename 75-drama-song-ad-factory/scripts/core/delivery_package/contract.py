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

The folder also has to be CLEAN: the client is handed deliverables and
nothing else. verify_folder lists the folder's top-level names and fails
with DELIVERY_FOLDER_NOT_CLEAN for any name outside the contract (the 12
items' files and folders) plus the three known extras -- the delivery
receipt, the README and the song-choices folder -- and the
``<Author> - <Title> - Song.mp3`` / ``.wav`` pair. A working file an agent
or a producer dropped in there (a cost report, a QC strip, a half render)
fails the gate instead of shipping.

The Drama-to-Demand method adds TWO more deliverable names, both inert
until the caller says the run carries them (SPEC B3b, METHOD-INTEGRATION
F11/F19 -- a run that is not wired for the method behaves byte for byte as
before):
  * a method run names item 6's two files as TRAILERS -- same slot 06, same
    kind, only the label differs (``06 - Trailer 60s.mp4`` /
    ``06 - Trailer 90s.mp4``); the clip names still open there;
  * a CAMPAIGN method run also ships the optional item 13, the ad clips
    (``13 - Ad 60s.mp4`` / ``13 - Ad 90s.mp4``). Every run carries the 12
    base items; 13 is the optional one.
An ad clip or a trailer name outside those runs is a stray like any other
working file, and the working files themselves (Agnes prompts, chained
last frames, mouth strips, venvs) have their own homes in the run, never
here.

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

#: SPEC B3b / METHOD-INTEGRATION F19: the optional 13th deliverable -- the ad
#: clips (a compressed arc selling the OFFER, cut from a campaign master).
#: Campaign method runs only: a lesson or testimonial run has no ad clips to
#: sell. DEL-06 is its producing unit (``delivery_clips`` writes these names);
#: DEL-13 is this contract itself, DEL-12 the welcome sheet.
AD_CLIPS_ITEM = Item("ad_clips", 13, "DEL-06", "60 and 90 SECOND AD CLIPS",
                     ("13 - Ad 60s.mp4", "13 - Ad 90s.mp4"),
                     ("media", "media"),
                     ("delivery_clips.delivery_clips",))

#: The deliverables that are not part of every run: the 12 base items are
#: mandatory, item 13 rides along only when the run is a campaign.
OPTIONAL_ITEMS = (AD_CLIPS_ITEM,)

#: 12 base items every run ships + optional item 13 = the 13 names the gate
#: knows. PACKAGE_ITEMS itself never grows: the client map, the welcome sheet
#: and Q12 count the 12, and a run that is not a campaign never owes 13.
assert len(PACKAGE_ITEMS + OPTIONAL_ITEMS) == 13 == \
    len({item.key for item in PACKAGE_ITEMS + OPTIONAL_ITEMS})

#: SPEC B3b / METHOD-INTEGRATION F11: a METHOD run names item 6's two files as
#: trailers -- same slot 06, same media kind, only the label differs. Keyed by
#: the item's number, index-aligned with that item's own ``files``.
METHOD_ITEM_FILES = {6: ("06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4")}

#: the clean-folder gate's failure code (SPEC B3b): the client folder holds
#: deliverables only, so a top-level name outside the allow-list fails.
DELIVERY_FOLDER_NOT_CLEAN = "DELIVERY_FOLDER_NOT_CLEAN"

#: the three known extras beside the 12 items: the delivery receipt, the
#: client README and the song-choices folder.
EXTRA_ALLOWED = ("delivery-receipt.json", "README.md", "SONG-CHOICES")

#: '<Author> - <Title> - Song.mp3' and its '.wav' twin (SKILL.md song pair).
_SONG_PAIR = re.compile(r"^.+ - .+ - Song\.(mp3|wav)$")


def allowed_top_level(method_run=False, campaign_run=False):
    """The names a clean delivery folder may hold at its top level.

    The 12 items' files plus the known extras, always. A method run adds the
    trailer names for item 6; a campaign method run adds the ad clips. Both
    default False, so an ordinary run gets exactly the old allow-list.
    """
    items = PACKAGE_ITEMS + ((AD_CLIPS_ITEM,) if campaign_run else ())
    names = {name for item in items for name in item.files}
    if method_run:
        for alt in METHOD_ITEM_FILES.values():
            names.update(alt)
    names.update(EXTRA_ALLOWED)
    return frozenset(names)


def is_allowed_top_level(name, method_run=False, campaign_run=False):
    """True when this top-level folder name is a deliverable or a known extra."""
    return name in allowed_top_level(method_run, campaign_run) or \
        bool(_SONG_PAIR.match(name))


def _slot_names(item, index, method_run):
    """The file names slot `index` of an item may carry, checked in that order.

    A method run asks for item 6's trailer name first and still accepts the
    clip name; every other slot (and every non-method run) has one name, the
    canonical one.
    """
    base = item.files[index]
    alt = METHOD_ITEM_FILES.get(item.number) if method_run else None
    if alt is not None and index < len(alt):
        return (alt[index], base)
    return (base,)


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


def verify_folder(folder, method_run=False, campaign_run=False):
    """Check a delivery folder against the package items. Never raises.

    Returns {"ok", "folder", "expected", "present", "missing", "problems",
    "not_clean"} where missing holds the package keys, problems names item +
    file + the sentence that failed, and not_clean holds every top-level name
    outside the allow-list (each one also a problem, code
    DELIVERY_FOLDER_NOT_CLEAN). A folder that does not exist misses all the
    items owed.

    method_run (the run carries control/method.json) opens item 6's trailer
    names and allows them at the top level; campaign_run (a campaign purpose
    method run) also owes item 13, the ad clips, and allows those names.
    expected is the 12 base items, +13 only for a campaign run. Both default
    False: a caller that says nothing about the method gets the original
    gate -- a trailer or an ad clip in an ordinary run is a stray.
    """
    root = Path(folder)
    items = PACKAGE_ITEMS + ((AD_CLIPS_ITEM,) if campaign_run else ())
    report = {"contract_version": CONTRACT_VERSION, "folder": str(root),
              "expected": len(items), "present": [], "missing": [],
              "problems": [], "not_clean": [], "ok": False}
    if not root.is_dir():
        report["missing"] = [item.key for item in items]
        report["problems"] = [{"item": "", "unit": "", "file": str(root),
                               "problem": "delivery folder missing"}]
        return report
    for item in items:
        bad = []
        for index, kind in enumerate(item.kinds):
            names = _slot_names(item, index, method_run)
            why = None
            for name in names:
                why = _problem(root / name, kind)
                if why is None:
                    break
            if why is not None:
                bad.append(why)
                report["problems"].append({"item": item.key, "unit": item.unit,
                                           "file": names[0], "problem": why})
        if bad:
            report["missing"].append(item.key)
        else:
            report["present"].append(item.key)
    for entry in sorted(root.iterdir()):
        if is_allowed_top_level(entry.name, method_run, campaign_run):
            continue
        report["not_clean"].append(entry.name)
        report["problems"].append(
            {"item": "", "unit": "", "file": entry.name,
             "problem": "%s: extra %s %s is not in the delivery contract"
                        % (DELIVERY_FOLDER_NOT_CLEAN,
                           "directory" if entry.is_dir() else "file",
                           entry.name)})
    report["ok"] = not report["missing"] and not report["not_clean"]
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
