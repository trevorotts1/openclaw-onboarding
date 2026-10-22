#!/usr/bin/env python3
"""install_face_model.py: download + pin Google's mediapipe face_landmarker.task.

The picture gate refuses every lip-sync job without this file. One command:

    python3 scripts/core/lip_sync/lip_gate/install_face_model.py

Fetches the model from Google's official bucket, verifies the pinned sha256 and
size, and places it at the ONE face-model path every reader resolves:
face_model_locator (env LIPSYNC_FACE_MODEL, else <skill>/assets/face_landmarker.task).
Stdlib only. Re-running with a good file in place is a no-op. A wrong hash
deletes nothing that was good and exits 1.
"""
from __future__ import annotations

import os
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_core = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _core not in sys.path:
    sys.path.insert(0, _core)
import face_model_locator as _LOC  # noqa: E402

# Public names kept for existing importers; the pins live in the locator only.
MODEL_URL = _LOC.MODEL_URL
MODEL_SHA256 = _LOC.MODEL_SHA256
MODEL_BYTES = _LOC.MODEL_BYTES
MODEL_NAME = _LOC.MODEL_NAME
DEFAULT_DEST = _LOC.default_path()
INSTALL_COMMAND = _LOC.INSTALL_COMMAND

sha256_file = _LOC.sha256_file
is_good = _LOC.is_good


def install(dest=None, url=MODEL_URL, sha256=MODEL_SHA256, opener=None):
    """-> dest (default: the resolved face-model path, override or assets/).
    Raises RuntimeError on a hash mismatch (nothing is placed)."""
    dest = os.path.abspath(dest or _LOC.resolve())
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
