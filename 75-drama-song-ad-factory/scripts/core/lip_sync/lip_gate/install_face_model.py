#!/usr/bin/env python3
"""install_face_model.py: download + pin Google's mediapipe face_landmarker.task.

The picture gate refuses every lip-sync job without this file. One command:

    python3 scripts/core/lip_sync/lip_gate/install_face_model.py

Downloads from Google's official bucket, verifies the pinned sha256 and size,
and places it at <skill>/assets/face_landmarker.task (where picture_measure
looks). Stdlib only. Re-running with a good file in place is a no-op. A wrong
hash deletes nothing that was good and exits 1.
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/latest/face_landmarker.task")
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
MODEL_BYTES = 3758596
MODEL_NAME = "face_landmarker.task"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DEST = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "assets", MODEL_NAME))
INSTALL_COMMAND = "python3 %s" % os.path.join(
    "scripts", "core", "lip_sync", "lip_gate", "install_face_model.py")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def is_good(path):
    return (os.path.isfile(path) and os.path.getsize(path) == MODEL_BYTES
            and sha256_file(path) == MODEL_SHA256)


def install(dest=DEFAULT_DEST, url=MODEL_URL, sha256=MODEL_SHA256, opener=None):
    """-> dest. Raises RuntimeError on a hash mismatch (nothing is placed)."""
    if is_good(dest):
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with (opener or urllib.request.urlopen)(url, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    got = sha256_file(tmp)
    if got != sha256:
        os.remove(tmp)
        raise RuntimeError("face model sha256 mismatch: got %s, pinned %s" % (got, sha256))
    os.replace(tmp, dest)
    return dest


if __name__ == "__main__":
    try:
        print("face model ready:", install())
    except Exception as exc:                                # noqa: BLE001
        print("FAIL: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(1)
