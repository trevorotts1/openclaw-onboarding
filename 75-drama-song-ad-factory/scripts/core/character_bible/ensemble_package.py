#!/usr/bin/env python3
"""ensemble_package: per-character delivery packaging and completeness.

T02 (C06 C07 F5 F6 F7 F9) initial implementation.

The pre-existing deliver path keys one image dictionary by VIEW alone
(F7 defect): two characters that both own a "close-up" end up in the same
slot and can silently swap pictures. This module indexes every reference
by STABLE CHARACTER ID first and VIEW second, preserves the matching text
and picture digests, refuses crossed or placeholder-only packages, and
binds the final package to the exact sent-current character approval
(F6). Preview packaging stays separate from the final owed-view check
(F7 step 4) and never starts paid generation (F7 step 5 / C07 step 4).

Late continuity (F5) is refused here unless measured audio timing is
supplied; the early identity component is valid without it. The bible's
own revision + fingerprint is re-checked before any package is called
current (F9), so a quality label cannot stand in for an actual bible.
"""
from __future__ import annotations

import json
import os

from character_bible import character_bible as CB  # noqa: E402

SCHEMA = "blackceo.character-ensemble-package/v1"
CODE_DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
CODE_CROSSED_REFERENCE = "CROSSED_REFERENCE"
CODE_STALE_REFERENCE = "STALE_REFERENCE"
CODE_MISSING_OWED_VIEW = "MISSING_OWED_VIEW"
CODE_PLACEHOLDER_VIEW = "PLACEHOLDER_VIEW"
CODE_APPROVAL_REQUIRED = "CHARACTER_APPROVAL_REQUIRED"
CODE_BIBLE_MISSING = "BIBLE_MISSING"
CODE_BIBLE_STALE = "BIBLE_STALE"
CODE_LATE_CONTINUITY_NO_TIMING = "LATE_CONTINUITY_NEEDS_MEASURED_TIMING"
CODE_IDENTITY_INCOMPLETE = "IDENTITY_INCOMPLETE"

#: view name -> the text/reference attribute it is bound to. A picture is
#: only trusted for the character it is filed under AND whose stored hash
#: matches the bytes on disk now.
OWED_VIEWS = tuple(CB.IMAGE_VIEWS)

#: stable-identity fields C06 requires; an unused biography field is not
#: character intelligence, so the snapshot names what downstream consumes.
IDENTITY_FIELDS = ("name", "role", "background", "appearance", "voice_notes")
MOTIVATION_FIELDS = ("want", "relationships")


class PackageError(ValueError):
    """A named refusal; ``reason_code`` is stable for the checker."""

    def __init__(self, reason_code, detail):
        self.reason_code = reason_code
        self.detail = detail
        ValueError.__init__(self, "%s: %s" % (reason_code, detail))


def _sha_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _sha_text(text):
    import hashlib
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def _slug(entry):
    return str(entry.get("slug") or entry.get("name") or "").strip()


def _norm(name):
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def identity_snapshot(entry):
    """The stable identity record an episode cast reuses (C06 step 2/3)."""
    if not isinstance(entry, dict):
        raise PackageError(CODE_IDENTITY_INCOMPLETE, "character entry is not an object")
    missing = [f for f in MOTIVATION_FIELDS if not str(entry.get(f) or "").strip()]
    if missing:
        raise PackageError(
            CODE_IDENTITY_INCOMPLETE,
            "%s is missing %s; a reusable identity needs a named motivation and "
            "relationship" % (_slug(entry) or "the character", ", ".join(missing)))
    return {
        "slug": _slug(entry),
        "text": {f: _sha_text(entry.get(f)) for f in IDENTITY_FIELDS},
        "fields": {f: str(entry.get(f) or "").strip()
                   for f in IDENTITY_FIELDS + MOTIVATION_FIELDS},
    }


def index(doc):
    """? character id -> {text digests, view -> {path, sha256}}.

    Duplicate ids or duplicate normalized names are refused before any
    package is produced (F7 step 3).
    """
    chars = (doc or {}).get("characters") or []
    out = {}
    seen_names = {}
    for entry in chars:
        slug = _slug(entry)
        if not slug:
            raise PackageError(CODE_DUPLICATE_IDENTITY, "a character entry has no id")
        key = slug.lower()
        name_key = _norm(entry.get("name") or slug)
        if key in out or name_key in seen_names:
            raise PackageError(
                CODE_DUPLICATE_IDENTITY,
                "character id %r is declared more than once; two characters "
                "must be distinct" % slug)
        seen_names[name_key] = slug
        views = {}
        for view, img in (entry.get("images") or {}).items():
            path = img.get("path") if isinstance(img, dict) else img
            recorded = img.get("sha256") if isinstance(img, dict) else None
            if not path:
                continue
            views[str(view)] = {"path": str(path), "sha256": recorded,
                               "exists": bool(os.path.isfile(str(path))
                                             and os.path.getsize(str(path)) > 0)}
        out[slug] = {
            "name": str(entry.get("name") or slug),
            "text": {f: _sha_text(entry.get(f)) for f in IDENTITY_FIELDS},
            "views": views,
        }
    return out


def _approval_bound(approval, slug, view, disk_sha):
    """True only when the approval recorded exactly this character+view hash."""
    hashes = ((approval or {}).get("image_hashes") or {}).get(slug) or {}
    return bool(hashes.get(view)) and hashes.get(view) == disk_sha


def plan(run_dir, *, mode="final", bible=None, approval=None,
         measured_timing=None):
    """Build the per-character package plan. Writes nothing.

    ``mode`` is "preview" (partial, honestly labelled) or "final" (every
    owed view present, approval-current, no placeholders).
    """
    from character_bible import character_approval as CA  # noqa: PLC0415
    if mode not in ("preview", "final"):
        raise PackageError(CODE_PLACEHOLDER_VIEW, "unknown package mode %r" % mode)
    doc = bible if bible is not None else CA.load_bible(run_dir)
    if not isinstance(doc, dict) or not doc.get("characters"):
        raise PackageError(CODE_BIBLE_MISSING,
                           "no actual character bible (character/bible.json) for %s"
                           % run_dir)
    if doc.get("schema") != CA.SCHEMA_BIBLE:
        raise PackageError(CODE_BIBLE_STALE,
                           "bible schema %r is not %s" % (doc.get("schema"),
                                                         CA.SCHEMA_BIBLE))
    if doc.get("fingerprint") != CA.fingerprint(doc):
        raise PackageError(CODE_BIBLE_STALE,
                           "bible fingerprint does not match its content")
    if mode == "final" and measured_timing is None:
        # F5: late continuity depends on selected audio/timing; the early
        # identity component does not.
        raise PackageError(CODE_LATE_CONTINUITY_NO_TIMING,
                           "a final continuity package needs measured audio timing")
    appr = approval if approval is not None else CA.approval_record(run_dir)
    if mode == "final" and not (isinstance(appr, dict)
                                and appr.get("status") == CA.APPROVED):
        raise PackageError(CODE_APPROVAL_REQUIRED,
                           "the sent-current character approval is required before "
                           "a final package")
    if mode == "final" and appr.get("bible_revision") != doc.get("revision"):
        raise PackageError(CODE_STALE_REFERENCE,
                           "approval is for bible revision %r, current is %r"
                           % (appr.get("bible_revision"), doc.get("revision")))

    idx = index(doc)
    characters = {}
    for slug, rec in idx.items():
        views = {}
        for view in OWED_VIEWS:
            img = rec["views"].get(view)
            if not img or not img["exists"]:
                if mode == "final":
                    code = (CODE_PLACEHOLDER_VIEW if img
                            else CODE_MISSING_OWED_VIEW)
                    raise PackageError(
                        code, "%s is missing the %s reference" % (rec["name"], view))
                views[view] = {"status": "placeholder"}
                continue
            disk_sha = _sha_file(img["path"])
            if img["sha256"] and img["sha256"] != disk_sha:
                raise PackageError(
                    CODE_CROSSED_REFERENCE,
                    "%s %s reference bytes do not match the recorded hash "
                    "(crossed or replaced picture)" % (rec["name"], view))
            if mode == "final" and not _approval_bound(appr, slug, view, disk_sha):
                raise PackageError(
                    CODE_STALE_REFERENCE,
                    "%s %s reference is not the approved revision" % (rec["name"], view))
            views[view] = {"status": "final" if mode == "final" else "preview",
                           "path": img["path"], "sha256": disk_sha,
                           "character_id": slug, "view": view}
        characters[slug] = {"name": rec["name"], "text": rec["text"],
                            "views": views}
    return {
        "schema": SCHEMA,
        "mode": mode,
        "bible_revision": doc.get("revision"),
        "bible_fingerprint": doc.get("fingerprint"),
        "approved_by": (appr or {}).get("approved_by", "") if mode == "final" else "",
        "origin": ((appr or {}).get("origin") or {}) if mode == "final" else {},
        "measured_timing": measured_timing,
        "characters": characters,
        "count": len(characters),
    }


def write(plan_doc, images_dir, manifest_name="ensemble-package.json"):
    """Package the ALREADY APPROVED files per character. No new generation.

    Layout: ``<images_dir>/<character id>/<view>.<ext>`` so two characters
    with the same view name can never overwrite each other. Returns the
    written manifest path.
    """
    import shutil
    os.makedirs(images_dir, exist_ok=True)
    for slug, rec in (plan_doc.get("characters") or {}).items():
        dest_dir = os.path.join(images_dir, slug)
        os.makedirs(dest_dir, exist_ok=True)
        for view, meta in (rec.get("views") or {}).items():
            if meta.get("status") == "placeholder":
                continue
            src = meta.get("path")
            if not src or _sha_file(src) != meta.get("sha256"):
                raise PackageError(
                    CODE_STALE_REFERENCE,
                    "%s %s changed between plan and write" % (rec.get("name"), view))
            ext = os.path.splitext(src)[1].lower() or ".png"
            shutil.copy2(src, os.path.join(dest_dir, view + ext))
    manifest = os.path.join(images_dir, manifest_name)
    tmp = manifest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(plan_doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, manifest)
    return manifest


def assert_complete(package):
    """F9: complete only with every character and every owed view current."""
    if package.get("mode") != "final":
        raise PackageError(CODE_PLACEHOLDER_VIEW, "preview is not final complete")
    for slug, rec in (package.get("characters") or {}).items():
        for view, meta in (rec.get("views") or {}).items():
            if meta.get("status") != "final":
                raise PackageError(CODE_MISSING_OWED_VIEW,
                                   "%s %s is not final" % (slug, view))
    return True
