#!/usr/bin/env python3
"""keyframes.py: keyframes follow the timed continuity record (S75-A27). Stdlib only.

A keyframe is an IMAGE for one planned shot, and a shot only exists because a
timed line exists.  So keyframes are derived from the timed continuity record
(the ordered shot plan carrying song windows and the lines each shot shows),
never invented beside it:

* ``build_manifest(continuity)`` -- one keyframe per continuity shot, emitted
  in the record's own order, each bound to that shot's window and lyric line.
  The record is refused outright when it is missing or carries no shots
  (``CONTINUITY_MISSING``), when windows are out of order or overlap
  (``CONTINUITY_UNORDERED``), when a window is not a real pair of numbers
  (``CONTINUITY_SHAPE``) or when a shot id repeats
  (``CONTINUITY_DUPLICATE_SHOT``).  Nothing here sorts the record into shape:
  a record that is not already ordered is a broken plan, not a puzzle.
* ``shot_set_digest(manifest)`` -- the ``keyframes/<shot-set-digest>`` id the
  factory stage registry names, computed from the ordered keyframe rows only.
* ``write_manifest`` / ``load_manifest`` -- ``keyframes/manifest.json``, the
  artifact the ``image-keyframes`` stage declares.
* ``main`` -- CLI: ``python3 scripts/core/keyframes/keyframes.py build
  --continuity "$RUN/storyboard/shot-list.json" --out "$RUN/keyframes/manifest.json"``.

No provider call, no spend and no picture is made here: this is the ordering
contract the image dispatch reads, so a keyframe can never be generated for a
shot the timed continuity record does not carry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

SCHEMA_VERSION = "blackceo.keyframes/v1"
MANIFEST_NAME = "manifest.json"
STAGE = "image-keyframes"

#: Refusal codes. Every one is a fail-closed answer, never a warning.
CONTINUITY_MISSING = "CONTINUITY_MISSING"
CONTINUITY_UNORDERED = "CONTINUITY_UNORDERED"
CONTINUITY_SHAPE = "CONTINUITY_SHAPE"
CONTINUITY_DUPLICATE_SHOT = "CONTINUITY_DUPLICATE_SHOT"


class KeyframeError(Exception):
    """A refusal with a stable code the factory can report verbatim."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _shots(continuity):
    """The ordered shot list from a timed continuity record.

    Accepted shapes, nothing more: a shot list, or the storyboard envelope the
    runbook writes (``{"shots": [...]}``).  A missing record, a wrong type or
    an empty list is CONTINUITY_MISSING: there is no timed picture to key.
    """
    if continuity is None:
        raise KeyframeError(CONTINUITY_MISSING, "no timed continuity record")
    if isinstance(continuity, dict):
        shots = continuity.get("shots")
        if shots is None:
            raise KeyframeError(
                CONTINUITY_MISSING,
                "record has no 'shots' list; keyframes cannot be derived from "
                "a record that carries no timed shots")
    elif isinstance(continuity, list):
        shots = continuity
    else:
        raise KeyframeError(CONTINUITY_MISSING,
                            "record is %s, not a shot list" % type(continuity).__name__)
    if not isinstance(shots, list):
        raise KeyframeError(CONTINUITY_SHAPE, "'shots' must be a list")
    if not shots:
        raise KeyframeError(CONTINUITY_MISSING, "'shots' is empty")
    return shots


def _window(shot, i):
    """(shot_id, start, end) from one shot row, refusing a shape that cannot
    be ordered.  Numbers must be real and the window must run forward."""
    if not isinstance(shot, dict):
        raise KeyframeError(CONTINUITY_SHAPE, "shot %d is not an object" % i)
    sid = shot.get("shot_id")
    if not isinstance(sid, str) or not sid:
        raise KeyframeError(CONTINUITY_SHAPE, "shot %d has no shot_id" % i)
    a, b = shot.get("song_start"), shot.get("song_end")
    for name, v in (("song_start", a), ("song_end", b)):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise KeyframeError(CONTINUITY_SHAPE,
                                "shot %s %s is not a number" % (sid, name))
    if not a < b:
        raise KeyframeError(CONTINUITY_UNORDERED,
                            "shot %s window %r..%r does not run forward" % (sid, a, b))
    return sid, float(a), float(b)


def build_manifest(continuity, run_id=None):
    """One keyframe per timed continuity shot, in continuity order.

    Returns the manifest dict; raises KeyframeError on any broken record.
    The rows are emitted in the order the record carries them (never
    re-sorted), so the manifest's order IS the continuity order.
    """
    shots = _shots(continuity)
    rows, seen, prev_end = [], set(), None
    for i, shot in enumerate(shots):
        sid, a, b = _window(shot, i)
        if sid in seen:
            raise KeyframeError(CONTINUITY_DUPLICATE_SHOT,
                                "shot %s appears twice" % sid)
        seen.add(sid)
        if prev_end is not None and a < prev_end:
            raise KeyframeError(
                CONTINUITY_UNORDERED,
                "shot %s starts at %r before the previous shot ends at %r"
                % (sid, a, prev_end))
        prev_end = b
        line_ids = list(shot.get("shows_line_ids") or shot.get("lyric_line_ids") or [])
        rows.append({
            "index": len(rows) + 1,
            "shot_id": sid,
            "at_s": round(a, 3),
            "start_s": round(a, 3),
            "end_s": round(b, 3),
            "duration_s": round(b - a, 3),
            "line_ids": line_ids,
            "status": "planned",
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "run_id": run_id,
        "shot_count": len(rows),
        "keyframes": rows,
    }
    manifest["shot_set_digest"] = shot_set_digest(manifest)
    manifest["id"] = "keyframes/%s" % manifest["shot_set_digest"]
    return manifest


def shot_set_digest(manifest):
    """Stable digest of the ordered keyframe rows (the stage id's last part)."""
    rows = manifest.get("keyframes") or []
    body = "\n".join("%s|%.3f|%.3f|%s" % (r["shot_id"], r["start_s"], r["end_s"],
                                          ",".join(r.get("line_ids") or []))
                     for r in rows)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def write_manifest(path, manifest):
    """Write ``keyframes/manifest.json`` (parent dir created)."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def load_manifest(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise KeyframeError(CONTINUITY_MISSING, "cannot read %s: %s" % (path, e))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)
    b = sub.add_parser("build", help="derive keyframes from the timed continuity record")
    b.add_argument("--continuity", required=True,
                   help="timed continuity record (shot list, or {'shots': [...]})")
    b.add_argument("--out", required=True, help="keyframes/manifest.json path")
    b.add_argument("--run-id", default=None)
    ns = ap.parse_args(argv)
    if ns.action == "build":
        try:
            manifest = build_manifest(_read_json(ns.continuity), run_id=ns.run_id)
        except KeyframeError as e:
            print(str(e), file=sys.stderr)
            return 2
        write_manifest(ns.out, manifest)
        print(json.dumps({k: manifest[k] for k in
                          ("id", "shot_count", "shot_set_digest")},
                         indent=1, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
