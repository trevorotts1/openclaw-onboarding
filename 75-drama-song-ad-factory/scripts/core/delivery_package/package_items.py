#!/usr/bin/env python3
"""DEL-12: the canonical numbered file-name list of the delivery package.

Trevor order 2026-10-09 08:50 (the complete client delivery package). One
delivery folder per client run, every file in it carrying the number of the
package item it belongs to. This module is that list: ONE constant, one
source of truth, consumed by ``core/delivery_checklist`` (the delivery gate)
and rendered by ``core/delivery_package/welcome_sheet.py`` (the client-facing
one-page map). Both distributions carry this file byte-identically -- never
edit one copy alone.

The file names themselves live in ``delivery_package.contract.PACKAGE_ITEMS``
(the DEL-13 folder gate), the single source of the ONE naming scheme every
producer writes. This module re-exports them under the DEL-12 view (a flat
list, a count, the welcome-sheet name) so the client map and the gate can
never name a file differently.

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

from .contract import PACKAGE_ITEMS as _CONTRACT_ITEMS

#: One delivery folder per client run; every name below lives directly in it.
DELIVERY_FOLDER = "delivery"

#: Nothing a client opens from this folder is set smaller than this (points).
MIN_PDF_POINT_SIZE = 12

#: One client-facing sentence per item: what the item is for. Keys are the
#: contract's machine keys. ASCII, no model or tool name, no price, no income
#: claim -- the welcome sheet prints these beside the file names.
_WHAT = {
    "audio_versions": "Three cuts of your finished song, plus a note that "
                      "explains each one.",
    "character_bible": "Your character's story and the reference images that "
                       "keep them consistent.",
    "script_pdf": "The approved script - every spoken and sung line, exactly "
                  "as signed off.",
    "storyboard_pdf": "Every scene in order: the picture, the lyric line, and "
                      "what happens.",
    "video": "The finished video: one version with captions on, one clean.",
    "clips": "The 60-second and 90-second cut-downs of the finished video.",
    "ready_to_post_kit": "Ready-to-post captions, hashtags, the link, and "
                         "where each version goes.",
    "cover_thumbnail": "Your cover image, title included, ready to sit on top "
                       "of the video.",
    "lyric_sheet": "Every word of the song, laid out to read and grouped by "
                   "the song's sections.",
    "captions_srt": "The caption file that adds subtitles when you upload the "
                    "video.",
    "character_images": "Your character at full size: close-up, side profile, "
                        "three-quarter, and full standing.",
    "welcome_sheet": "This page - your map of the folder, and what each "
                     "number is for.",
}

#: The 12 package items, in delivery-folder order. Each entry:
#:   number -- the two-digit prefix on every file of the item (01..12)
#:   key    -- stable machine name for gates, receipts and tests
#:   files  -- the canonical file names, exact, as they sit in the folder
#:   what   -- one sentence, client-facing: what the item is for
#: The file names come straight from the DEL-13 contract (one naming scheme).
PACKAGE_ITEMS = tuple(
    {"number": item.number,
     "key": item.key,
     "files": item.files,
     "what": _WHAT[item.key]}
    for item in _CONTRACT_ITEMS
)

#: How many package items the folder must carry. Hard gate constant.
PACKAGE_ITEM_COUNT = 12

#: Flat tuple of every canonical file name, in item order. The delivery gate
#: checks this; the welcome sheet prints exactly this.
PACKAGE_FILES = tuple(f for item in PACKAGE_ITEMS for f in item["files"])

#: The welcome sheet's own file name (item 12) -- what a run writes first.
WELCOME_SHEET_FILE = PACKAGE_ITEMS[11]["files"][0]


def files_for(number):
    """Canonical file names of one item (01..12). Unknown number = ()."""
    for item in PACKAGE_ITEMS:
        if item["number"] == number:
            return item["files"]
    return ()
