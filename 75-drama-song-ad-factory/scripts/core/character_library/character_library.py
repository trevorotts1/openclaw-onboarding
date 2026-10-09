#!/usr/bin/env python3
"""character_library: a per-client library of saved characters (Part I, I6).

After the client approves a character, ask ONE question (``save_question``);
on "yes", ask for a name and call ``save_character``. Later intake cards list
the saved characters under the numbered saved-character question (``saved_character_question``)
and ``brief_fields`` turns the pick into brief fields (same face, same voice).

Layout, inside the client's own data folder (never shared between clients):

    <client_dir>/character-library/<slug>/character.json
    <client_dir>/character-library/<slug>/references/<n>-<original name>

Stdlib only. No network. Writes are atomic (temp file, then rename).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

LIBRARY_DIRNAME = "character-library"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
SCHEMA = "blackceo.character-library/v1"


class LibraryError(ValueError):
    """Plain-English reason a save or lookup was refused."""


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    if not s:
        raise LibraryError("The character needs a name with letters or numbers.")
    return s


def _lib(client_dir):
    return os.path.join(os.path.expanduser(str(client_dir)), LIBRARY_DIRNAME)


def save_question(character_name):
    """The one question asked right after a character is approved."""
    return ("Do you want to save %s to your character library so you can "
            "reuse them in future ads? Reply yes or no." % character_name)


def name_question(character_name):
    return ("What name should I save %s under? Pick a name you will "
            "recognize later." % character_name)


def save_character(client_dir, name, description, reference_images,
                   voice_notes="", overwrite=False):
    """Copy the reference images into the library and write character.json.

    Refuses (LibraryError): empty name/description, no reference image, a
    missing or non-image file, or a name already saved (unless overwrite).
    """
    slug = slugify(name)
    if not str(description or "").strip():
        raise LibraryError("Describe %s in a sentence or two before saving." % name)
    refs = list(reference_images or [])
    if not refs:
        raise LibraryError("%s needs at least one approved reference image." % name)
    for p in refs:
        if not os.path.isfile(p):
            raise LibraryError("Reference image not found: %s" % p)
        if os.path.splitext(p)[1].lower() not in IMAGE_EXTS:
            raise LibraryError("Reference must be a picture (png, jpg, webp): %s" % p)
    folder = os.path.join(_lib(client_dir), slug)
    if os.path.exists(folder) and not overwrite:
        raise LibraryError("A saved character named %s already exists. "
                           "Pick another name." % name)
    tmp = folder + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "references"))
    rel = []
    for n, p in enumerate(refs, 1):
        dest = "references/%d-%s" % (n, os.path.basename(p))
        shutil.copyfile(p, os.path.join(tmp, dest))
        rel.append(dest)
    rec = {"schema": SCHEMA, "name": str(name).strip(), "slug": slug,
           "description": str(description).strip(),
           "voice_notes": str(voice_notes or "").strip(),
           "reference_images": rel}
    with open(os.path.join(tmp, "character.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
    shutil.rmtree(folder, ignore_errors=True)
    os.replace(tmp, folder)
    return get_character(client_dir, slug)


def get_character(client_dir, name):
    """Saved record with absolute reference paths. LibraryError if absent."""
    folder = os.path.join(_lib(client_dir), slugify(name))
    try:
        with open(os.path.join(folder, "character.json"), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        raise LibraryError("No saved character named %s." % name)
    rec["reference_paths"] = [os.path.join(folder, r) for r in rec["reference_images"]]
    return rec


def list_characters(client_dir):
    root = _lib(client_dir)
    if not os.path.isdir(root):
        return []
    out = []
    for slug in sorted(os.listdir(root)):
        try:
            out.append(get_character(client_dir, slug))
        except LibraryError:
            continue
    return out


def saved_character_question(client_dir):
    """The saved-character intake question (new character is option 1), or None
    when the library is empty. Same shape as the intake_card questions; ``body``
    is the exact text shown under the "Question i of M - CHARACTER" header."""
    chars = list_characters(client_dir)
    if not chars:
        return None
    n = len(chars)
    ask = "Do you want to create a new character for this ad, or use one you've used before?"
    opts = [("Create a new character", "")]
    opts += [("Use %s" % c["name"], c["description"][:90]) for c in chars]
    body = [ask, "You have %d character%s saved with us." % (n, "" if n == 1 else "s"),
            "1. Create a new character (recommended)"]
    body += ["%d. %s%s" % (i, o, " - " + d if d else "") for i, (o, d) in enumerate(opts[1:], 2)]
    body.append("Reply with a number, or 'recommended'.")
    return {"id": "saved_character", "label": "CHARACTER", "ask": ask,
            "options": opts, "recommended": 0, "body": body,
            "recap": ["Character: new"] + ["Character: %s (saved)" % c["name"] for c in chars]}


def brief_fields(record):
    """Brief fields that carry a saved character into a new ad."""
    return {"character_name": record["name"],
            "character_description": record["description"],
            "character_reference_images": record["reference_paths"],
            "character_voice_notes": record["voice_notes"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Per-client character library.")
    ap.add_argument("--client-dir", required=True,
                    help="The client's own data folder.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("ask", help="Print the save question for an approved character.")
    q.add_argument("--character", required=True)
    s = sub.add_parser("save")
    s.add_argument("--name", required=True)
    s.add_argument("--description", required=True)
    s.add_argument("--image", action="append", default=[])
    s.add_argument("--voice-notes", default="")
    s.add_argument("--overwrite", action="store_true")
    sub.add_parser("list")
    u = sub.add_parser("use", help="Print the brief fields for a saved character.")
    u.add_argument("--name", required=True)
    sub.add_parser("card", help="Print the saved-character question.")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "ask":
            print(save_question(a.character))
            print()
            print(name_question(a.character))
        elif a.cmd == "save":
            r = save_character(a.client_dir, a.name, a.description, a.image,
                               a.voice_notes, a.overwrite)
            print(json.dumps({"saved": r["name"], "slug": r["slug"]}))
        elif a.cmd == "list":
            print(json.dumps([c["name"] for c in list_characters(a.client_dir)]))
        elif a.cmd == "use":
            print(json.dumps(brief_fields(get_character(a.client_dir, a.name)), indent=2))
        else:
            q = saved_character_question(a.client_dir)
            if q is None:
                print("No saved characters yet.")
            else:
                for n, (o, sent) in enumerate(q["options"], 1):
                    print("%d. %s - %s" % (n, o, sent))
    except LibraryError as e:
        print(str(e), file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
