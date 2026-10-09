#!/usr/bin/env python3
"""character_images: DEL-11 of the client delivery package.

Copy the character's approved pictures into the delivery folder as SEPARATE,
FULL-RESOLUTION files with clear names -- close-up, side profile, three-quarter,
full standing -- one file per view per character. Every picture already exists:
each file comes from a character_library record (its ``reference_paths``, or an
explicit ``views`` mapping the caller recorded on the record). Nothing is
generated, cropped, resized or re-encoded -- the copy is a byte-for-byte
``shutil.copyfile``, so the delivered picture is exactly the approved picture.

Which picture is which view, in order of trust:

  1. an explicit ``views`` mapping on the record (canonical view -> path);
  2. the view words in the reference file's own name (``close-up.png``,
     ``side.png``, ``three-quarter.png``, ``standing.png``) -- whole words
     only, so ``outside.png`` can never claim the side profile.

A view with no picture is a FAIL naming exactly the missing views: the
package never invents a picture to fill a slot. The whole plan is computed
BEFORE anything is written, so a failed run leaves the delivery folder
untouched.

Delivery names are numbered into slot 11 of the package (DEL-12 owns the
canonical numbered list): ``11-character-<slug>-<view>.<ext>``.

Fail closed: no characters, a record without a name, an unknown extension, a
missing source file or a duplicate slug raises ``CharacterImagesError``
naming the exact problem.

stdlib only. No network. No generation call of any kind, no spend.
Run: python3 core/character_images/test_character_images_del11.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)
from character_library import character_library as CL  # noqa: E402

TOOL_NAME = "character_images"
TOOL_VERSION = "1.0.0"
SCHEMA = "blackceo.delivery-character-images/v1"

#: The four views the package ships per character, in delivery order.
VIEWS = ("close-up", "side-profile", "three-quarter", "full-standing")

#: Numbered slot of this item in the delivery folder; DEL-12 owns the
#: canonical numbered list for all 12 package items.
FILE_PREFIX = "11-character"

#: Name-words that say "this reference IS that view" (each entry: the set of
#: whole filename words required, all of them). Whole words only.
_TOKENS = {
    "close-up": (frozenset(("closeup",)), frozenset(("close", "up")),
                 frozenset(("portrait",)), frozenset(("headshot",))),
    "side-profile": (frozenset(("sideprofile",)), frozenset(("side",))),
    "three-quarter": (frozenset(("threequarter",)),
                      frozenset(("three", "quarter"))),
    "full-standing": (frozenset(("fullstanding",)),
                      frozenset(("standing",)),
                      frozenset(("full", "body"))),
}


class CharacterImagesError(ValueError):
    """Plain-English reason the copy was refused; ``code`` names the part."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _words(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return frozenset(w for w in re.split(r"[^a-z0-9]+", stem.lower()) if w)


def _folder(record):
    """The character's own library folder, from its reference paths."""
    refs = record.get("reference_paths") or []
    if refs:
        return os.path.dirname(os.path.dirname(os.path.abspath(refs[0])))
    return None


def _resolve(record, path):
    path = str(path)
    if os.path.isabs(path):
        return path
    folder = _folder(record)
    if folder:
        candidate = os.path.join(folder, path)
        if os.path.isfile(candidate):
            return candidate
    return os.path.abspath(path)


def view_sources(record):
    """{view: source path} for one record -- only views it can honestly give.

    An explicit ``views`` mapping on the record wins; the remaining views are
    matched from the reference files' own names, each file claiming at most
    one view (views in ``VIEWS`` order, so a name that reads two ways goes to
    the first view that fits it).
    """
    out = {}
    views = record.get("views")
    if isinstance(views, dict):
        for view in VIEWS:
            p = views.get(view) or views.get(view.replace("-", " "))
            if p:
                out[view] = _resolve(record, p)
    refs = list(record.get("reference_paths") or [])
    used = set(out.values())
    for view in VIEWS:
        if view in out:
            continue
        wants = _TOKENS[view]
        for p in refs:
            if p in used:
                continue
            words = _words(p)
            if any(req <= words for req in wants):
                out[view] = p
                used.add(p)
                break
    return out


def plan_copies(records):
    """The full copy plan (one row per view per character). Writes nothing.

    Each row: {character, slug, view, source, filename}. Raises
    CharacterImagesError naming exactly what is wrong -- computed before any
    byte moves, so a refused plan leaves the delivery folder untouched.
    """
    if not isinstance(records, list) or not records:
        raise CharacterImagesError("NO_CHARACTERS",
                                   "no character pictures to deliver")
    plan = []
    seen = set()
    for rec in records:
        if not isinstance(rec, dict):
            raise CharacterImagesError("BAD_RECORD",
                                       "every character record must be an object")
        name = str(rec.get("name") or "").strip()
        slug = str(rec.get("slug") or "").strip()
        if not slug:
            if not name:
                raise CharacterImagesError("BAD_RECORD",
                                           "every character record needs a name")
            try:
                slug = CL.slugify(name)
            except CL.LibraryError as e:
                raise CharacterImagesError("BAD_RECORD", str(e))
        found = view_sources(rec)
        missing = [v for v in VIEWS if v not in found]
        if missing:
            have = ", ".join(v for v in VIEWS if v in found) or "none"
            raise CharacterImagesError(
                "VIEW_MISSING",
                "%s has no picture for: %s (found: %s). The package copies "
                "the pictures that exist; it never regenerates one to fill "
                "a slot." % (name or slug, ", ".join(missing), have))
        for view in VIEWS:
            src = found[view]
            if not os.path.isfile(src):
                raise CharacterImagesError(
                    "SOURCE_MISSING",
                    "%s %s picture not found: %s" % (name or slug, view, src))
            ext = os.path.splitext(src)[1].lower()
            if ext not in CL.IMAGE_EXTS:
                raise CharacterImagesError(
                    "BAD_IMAGE",
                    "%s %s must be a picture (png, jpg, webp): %s"
                    % (name or slug, view, src))
            filename = "%s-%s-%s%s" % (FILE_PREFIX, slug, view, ext)
            if filename in seen:
                raise CharacterImagesError(
                    "DUPLICATE_SLUG",
                    "two character records deliver the same file name %s"
                    % filename)
            seen.add(filename)
            plan.append({"character": name or slug, "slug": slug, "view": view,
                         "source": src, "filename": filename})
    return plan


def copy_character_images(delivery_dir, records):
    """Copy every planned picture into ``delivery_dir`` at full resolution.

    Returns the receipt: one row per delivered file with the source's own
    bytes count (a copy, never a re-encode) and the source file's name.
    """
    plan = plan_copies(records)
    os.makedirs(delivery_dir, exist_ok=True)
    copied = []
    for item in plan:
        dest = os.path.join(delivery_dir, item["filename"])
        shutil.copyfile(item["source"], dest)
        row = dict(item)
        row["source"] = os.path.basename(item["source"])
        row["bytes"] = os.path.getsize(dest)
        copied.append(row)
    return copied


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="DEL-11: copy the character pictures into the delivery "
                    "folder as separate full-resolution files.")
    ap.add_argument("--delivery-dir", required=True,
                    help="The run's delivery folder (created if missing).")
    ap.add_argument("--records",
                    help="JSON file: a list of character_library records "
                         "(get_character output), or {name, views} records.")
    ap.add_argument("--client-dir",
                    help="The client's own data folder (with --name).")
    ap.add_argument("--name", action="append", default=[],
                    help="Saved character to deliver (repeatable).")
    a = ap.parse_args(argv)
    try:
        if a.records:
            with open(a.records, encoding="utf-8") as f:
                records = json.load(f)
            if not isinstance(records, list):
                raise CharacterImagesError(
                    "BAD_RECORDS", "--records must be a JSON list of character records")
        elif a.client_dir and a.name:
            try:
                records = [CL.get_character(a.client_dir, n) for n in a.name]
            except CL.LibraryError as e:
                raise CharacterImagesError("BAD_RECORD", str(e))
        else:
            raise CharacterImagesError(
                "BAD_INPUT", "give --records FILE, or --client-dir with --name")
        copied = copy_character_images(a.delivery_dir, records)
    except CharacterImagesError as e:
        sys.stderr.write("%s\n" % e)
        return 1
    except (OSError, ValueError) as e:      # includes json.JSONDecodeError
        sys.stderr.write("BAD_INPUT: %s\n" % e)
        return 1
    print(json.dumps({"schema": SCHEMA, "tool": TOOL_NAME,
                      "version": TOOL_VERSION, "count": len(copied),
                      "copied": copied}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
