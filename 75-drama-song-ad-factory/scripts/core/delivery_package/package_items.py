"""DEL-12: the canonical numbered file-name list of the delivery package.

Trevor order 2026-10-09 08:50 (the complete client delivery package). One
delivery folder per client run, every file in it carrying the number of the
package item it belongs to. This module is that list: ONE constant, one
source of truth, consumed by ``core/delivery_checklist`` (the delivery gate)
and rendered by ``core/delivery_package/welcome_sheet.py`` (the client-facing
one-page map). Both distributions carry this file byte-identically -- never
edit one copy alone.

Contract
--------
* exactly 12 items, numbered 01..12 in folder order;
* every file name is exact, starts with its own item number, and is unique;
* ``what`` is one client-facing sentence, ASCII, no model or tool name, no
  price, no income claim;
* nothing in here reads a file, calls a provider, or spends.

stdlib only. No network, no client name, no absolute operator path.
"""
from __future__ import annotations

#: One delivery folder per client run; every name below lives directly in it.
DELIVERY_FOLDER = "delivery"

#: Nothing a client opens from this folder is set smaller than this (points).
MIN_PDF_POINT_SIZE = 12

#: The 12 package items, in delivery-folder order. Each entry:
#:   number -- the two-digit prefix on every file of the item (01..12)
#:   key    -- stable machine name for gates, receipts and tests
#:   files  -- the canonical file names, exact, as they sit in the folder
#:   what   -- one sentence, client-facing: what the item is for
PACKAGE_ITEMS = (
    {"number": 1,
     "key": "audio",
     "files": ("01-audio-full.mp3",
               "01-audio-instrumental.mp3",
               "01-audio-voice-only.mp3",
               "01-audio-note.txt"),
     "what": "Three cuts of your finished song, plus a note that explains "
             "each one."},
    {"number": 2,
     "key": "character-bible",
     "files": ("02-character-bible.pdf",),
     "what": "Your character's story and the reference images that keep "
             "them consistent."},
    {"number": 3,
     "key": "script",
     "files": ("03-script.pdf",),
     "what": "The approved script - every spoken and sung line, exactly as "
             "signed off."},
    {"number": 4,
     "key": "storyboard",
     "files": ("04-storyboard.pdf",),
     "what": "Every scene in order: the picture, the lyric line, and what "
             "happens."},
    {"number": 5,
     "key": "video",
     "files": ("05-video-captioned.mp4",
               "05-video-clean.mp4"),
     "what": "The finished video: one version with captions on, one clean."},
    {"number": 6,
     "key": "clips",
     "files": ("06-clip-60s.mp4",
               "06-clip-90s.mp4"),
     "what": "The 60-second and 90-second cut-downs of the finished video."},
    {"number": 7,
     "key": "post-kit",
     "files": ("07-ready-to-post-kit.pdf",),
     "what": "Ready-to-post captions, hashtags, the link, and where each "
             "version goes."},
    {"number": 8,
     "key": "cover-image",
     "files": ("08-cover-image.png",),
     "what": "Your cover image, title included, ready to sit on top of the "
             "video."},
    {"number": 9,
     "key": "lyric-sheet",
     "files": ("09-lyric-sheet.pdf",),
     "what": "Every word of the song, laid out to read and grouped by the "
             "song's sections."},
    {"number": 10,
     "key": "captions",
     "files": ("10-captions.srt",),
     "what": "The caption file that adds subtitles when you upload the "
             "video."},
    {"number": 11,
     "key": "character-images",
     "files": ("11-character-close-up.png",
               "11-character-side-profile.png",
               "11-character-three-quarter.png",
               "11-character-full-standing.png"),
     "what": "Your character at full size: close-up, side profile, "
             "three-quarter, and full standing."},
    {"number": 12,
     "key": "welcome-sheet",
     "files": ("12-welcome-sheet.pdf",),
     "what": "This page - your map of the folder, and what each number is "
             "for."},
)

#: How many package items the folder must carry. Hard gate constant.
PACKAGE_ITEM_COUNT = 12

#: Flat tuple of every canonical file name, in item order. The delivery gate
#: checks this; the welcome sheet prints exactly this.
PACKAGE_FILES = tuple(f for item in PACKAGE_ITEMS for f in item["files"])

#: The welcome sheet's own file name (item 12) -- what a run writes first.
WELCOME_SHEET_FILE = "12-welcome-sheet.pdf"


def files_for(number):
    """Canonical file names of one item (01..12). Unknown number = ()."""
    for item in PACKAGE_ITEMS:
        if item["number"] == number:
            return item["files"]
    return ()
