#!/usr/bin/env python3
"""reference_sets.py: one locked reference set per character (N-40, section 3C.2). Stdlib only.

One set per character, made once in the run's locked look, before any keyframe:
a master picture (front, neutral, chest-up), a three-quarter view, a profile,
a full body, and one wardrobe picture per wardrobe the story gives them.
Every file is fingerprinted and listed in ``control/look-lock.json`` under that
character. The run owner approves the set once; after that it changes only by
the run owner's recorded order, which raises the lock version.

Wardrobe entries carry the accessories lock (section 3.5, N-13): clothing,
hair and every accessory by name (stole, head wrap, glasses), so a new clip
starts from a locked picture that shows the full wardrobe.

Every refusal is a stable code with the character id it refused. Stdlib only,
no IO beyond hashing a file the caller names, no provider or network call.
"""
from __future__ import annotations

import hashlib
import os

SCHEMA_VERSION = "blackceo.reference-sets/v1"

#: The four views every set carries (3C.2 step 1).
REFERENCE_VIEWS = ("master", "three_quarter", "profile", "full_body")

#: Refusal codes. Every one is fail-closed.
REFERENCE_SET_MISSING = "REFERENCE_SET_MISSING"
REFERENCE_VIEW_MISSING = "REFERENCE_VIEW_MISSING"
REFERENCE_UNHASHED = "REFERENCE_UNHASHED"
WARDROBE_PICTURE_MISSING = "WARDROBE_PICTURE_MISSING"
WARDROBE_ENTRY_INCOMPLETE = "WARDROBE_ENTRY_INCOMPLETE"
ACCESSORIES_UNDECLARED = "ACCESSORIES_UNDECLARED"
APPROVAL_NOT_RECORDED = "APPROVAL_NOT_RECORDED"
STALE_AFTER_LOCK_CHANGE = "STALE_AFTER_LOCK_CHANGE"

_HEX = frozenset("0123456789abcdef")


def _defect(code, character_id, detail):
    return {"code": code, "character_id": character_id, "detail": detail}


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def is_digest(value):
    """A fingerprint is a sha256 hex string (64 lowercase hex characters)."""
    if not isinstance(value, str) or len(value) != 64:
        return False
    low = value.lower()
    return low == value and all(c in _HEX for c in low)


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    """sha256 of a reference picture's bytes; raises OSError when unreadable."""
    with open(path, "rb") as handle:
        return digest_bytes(handle.read())


# --- wardrobe and accessories lock (3C.2) ----------------------------------

def wardrobe_entry(wardrobe_id, outfit, accessories):
    """One wardrobe entry: clothing, hair and every accessory by name.

    Raises ValueError when a required part is blank or accessories is not a
    list of named strings. An empty list is a declared "no accessories", which
    is allowed; omitting the field is not.
    """
    if not _text(wardrobe_id):
        raise ValueError("WARDROBE_ENTRY_INCOMPLETE: wardrobe_id")
    if not _text(outfit):
        raise ValueError("WARDROBE_ENTRY_INCOMPLETE: outfit")
    if not isinstance(accessories, list) or \
            any(not _text(a) for a in accessories):
        raise ValueError("ACCESSORIES_UNDECLARED: accessories must be a list of names")
    return {
        "wardrobe_id": _text(wardrobe_id),
        "outfit": _text(outfit),
        "accessories": [_text(a) for a in accessories],
    }


def validate_wardrobe_entry(entry):
    defects = []
    wid = (entry or {}).get("wardrobe_id")
    if not isinstance(entry, dict):
        return [_defect(WARDROBE_ENTRY_INCOMPLETE, None, "wardrobe entry is not an object")]
    for field in ("wardrobe_id", "outfit"):
        if not _text(entry.get(field)):
            defects.append(_defect(WARDROBE_ENTRY_INCOMPLETE, wid,
                                   "wardrobe entry carries no %s" % field))
    accessories = entry.get("accessories")
    if accessories is None:
        defects.append(_defect(ACCESSORIES_UNDECLARED, wid,
                               "wardrobe %r declares no accessories field; list every "
                               "accessory by name or write []" % (wid,)))
    elif not isinstance(accessories, list) or \
            any(not _text(a) for a in accessories):
        defects.append(_defect(ACCESSORIES_UNDECLARED, wid,
                               "wardrobe %r accessories must be a list of names" % (wid,)))
    return defects


# --- the set ----------------------------------------------------------------

def build_reference_set(character_id, views, wardrobes=None, main=False,
                        lock_version=1, approved=False):
    """Build one character's reference set from named files and fingerprints.

    views: {view_name: {"path": ..., "digest": ...}} for the four views. A
    caller that has the file but no digest may pass {"path": ...} and call
    ``fingerprint_set`` afterwards. wardrobes: list of wardrobe entries. main:
    True for a main character (the expression sheets of N-70 are required; see
    expression_sheets.validate_reference_set_expressions).
    """
    cid = _text(character_id)
    if not cid:
        raise ValueError("REFERENCE_SET_MISSING: character_id")
    return {
        "schema_version": SCHEMA_VERSION,
        "character_id": cid,
        "main": bool(main),
        "views": dict(views or {}),
        "wardrobes": list(wardrobes or []),
        "lock_version": lock_version,
        "approved": bool(approved),
    }


def fingerprint_set(entry):
    """Fill each view's digest from its path; a missing file is left unfilled."""
    views = entry.setdefault("views", {})
    for view in REFERENCE_VIEWS:
        row = views.get(view)
        if not isinstance(row, dict):
            continue
        if not is_digest(row.get("digest")) and _text(row.get("path")) \
                and os.path.isfile(row["path"]):
            row["digest"] = digest_file(row["path"])
    return entry


def validate_reference_set(entry, main=None):
    """Every view present and hashed, and one wardrobe picture per wardrobe.

    Returns a findings list; ``code`` is the refusal code. An unhashed file is
    REFERENCE_UNHASHED: a picture not in the lock cannot be proven to be the
    one this generation used.
    """
    if not isinstance(entry, dict):
        return [_defect(REFERENCE_SET_MISSING, None, "reference set is not an object")]
    cid = entry.get("character_id")
    defects = []
    views = entry.get("views")
    if not isinstance(views, dict):
        return [_defect(REFERENCE_SET_MISSING, cid, "set carries no views")]
    for view in REFERENCE_VIEWS:
        row = views.get(view)
        if not isinstance(row, dict) or not (_text(row.get("path")) or
                                             is_digest(row.get("digest"))):
            defects.append(_defect(REFERENCE_VIEW_MISSING, cid,
                                   "no %s view in the set" % view))
            continue
        if not is_digest(row.get("digest")):
            defects.append(_defect(REFERENCE_UNHASHED, cid,
                                   "%s view is not fingerprinted" % view))
    wardrobes = entry.get("wardrobes")
    if not isinstance(wardrobes, list):
        defects.append(_defect(WARDROBE_ENTRY_INCOMPLETE, cid,
                               "set carries no wardrobe list"))
        wardrobes = []
    if not wardrobes:
        defects.append(_defect(WARDROBE_PICTURE_MISSING, cid,
                               "set carries no wardrobe picture"))
    for wardrobe in wardrobes:
        defects.extend(validate_wardrobe_entry(wardrobe))
        if isinstance(wardrobe, dict):
            picture = wardrobe.get("picture") or {}
            if not (is_digest(picture.get("digest")) or
                    _text(picture.get("path"))):
                defects.append(_defect(
                    WARDROBE_PICTURE_MISSING, cid,
                    "wardrobe %r has no picture" % (wardrobe.get("wardrobe_id"),)))
    if main is None:
        main = bool(entry.get("main"))
    if main:
        # N-70: a main character's set carries the seven expression sheets.
        try:
            from character_bible import expression_sheets as _ex
        except ImportError:                      # imported beside the module
            import expression_sheets as _ex
        defects.extend(_ex.validate_reference_set_expressions(entry))
    return defects


def approve_reference_set(entry, approval=None, lock_version=None):
    """The run owner's one approval of the set.

    Refuses APPROVAL_NOT_RECORDED when no approval record is supplied, and
    STALE_AFTER_LOCK_CHANGE when the set was made under an older lock version.
    Re-approving an unchanged set is idempotent: the approval is already
    recorded, so the set is returned unchanged.
    """
    if not isinstance(entry, dict):
        raise ValueError("REFERENCE_SET_MISSING")
    if approval is None:
        return {"ok": False, "code": APPROVAL_NOT_RECORDED,
                "detail": "the run owner's approval is required once per set"}
    wanted = lock_version if lock_version is not None else entry.get("lock_version")
    if wanted is not None and entry.get("lock_version") is not None \
            and wanted != entry.get("lock_version"):
        return {"ok": False, "code": STALE_AFTER_LOCK_CHANGE,
                "detail": "set was made under lock %r, approval is for %r"
                          % (entry.get("lock_version"), wanted)}
    out = dict(entry)
    out["approved"] = True
    out["approval"] = approval
    return {"ok": True, "reference_set": out}


def lock_entries(reference_sets):
    """The lock-file listing: one entry per character with file, view, digest."""
    out = {}
    for entry in reference_sets or []:
        if not isinstance(entry, dict) or not _text(entry.get("character_id")):
            continue
        cid = entry["character_id"]
        files = []
        for view, row in sorted((entry.get("views") or {}).items()):
            if isinstance(row, dict):
                files.append({"view": view, "path": row.get("path"),
                              "digest": row.get("digest")})
        for wardrobe in entry.get("wardrobes") or []:
            if not isinstance(wardrobe, dict):
                continue
            picture = wardrobe.get("picture") or {}
            files.append({"view": "wardrobe:%s" % wardrobe.get("wardrobe_id"),
                          "path": picture.get("path"),
                          "digest": picture.get("digest"),
                          "accessories": list(wardrobe.get("accessories") or [])})
        out[cid] = {
            "lock_version": entry.get("lock_version"),
            "approved": bool(entry.get("approved")),
            "files": files,
        }
    return {"schema_version": SCHEMA_VERSION, "characters": out}


__all__ = [
    "SCHEMA_VERSION", "REFERENCE_VIEWS", "REFERENCE_SET_MISSING",
    "REFERENCE_VIEW_MISSING", "REFERENCE_UNHASHED", "WARDROBE_PICTURE_MISSING",
    "WARDROBE_ENTRY_INCOMPLETE", "ACCESSORIES_UNDECLARED",
    "APPROVAL_NOT_RECORDED", "STALE_AFTER_LOCK_CHANGE", "is_digest",
    "digest_bytes", "digest_file", "wardrobe_entry", "validate_wardrobe_entry",
    "build_reference_set", "fingerprint_set", "validate_reference_set",
    "approve_reference_set", "lock_entries",
]
