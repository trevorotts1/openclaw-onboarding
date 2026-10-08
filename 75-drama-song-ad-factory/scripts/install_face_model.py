#!/usr/bin/env python3
"""Install the mediapipe face model the lip-sync picture gate needs (LPG001).

Downloads face_landmarker.task from Google's official URL, verifies the pinned
sha256, and places it where the gate looks (LIPSYNC_FACE_MODEL, else
core/lip_sync/lip_gate/face_landmarker.task). Without it the gate refuses every
lip-sync job. Run: python3 scripts/install_face_model.py   (stdlib only)
Exit 0 = installed or already correct; 1 = download/verify failed (nothing placed).
"""
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "lip_sync", "lip_gate"))
import picture_gate as P  # noqa: E402  (constants live in ONE place)


def _sha(path):
    return P.sha256_file(path)


def install(url=P.FACE_MODEL_URL, sha256=P.FACE_MODEL_SHA256, dest=None):
    """-> dest path. Raises RuntimeError (and places nothing) on any failure."""
    dest = dest or P._model_path()
    if os.path.isfile(dest) and _sha(dest) == sha256:
        return dest
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest) or ".", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=120) as r:
            shutil.copyfileobj(r, out)
        got = _sha(tmp)
        if got != sha256:
            raise RuntimeError("sha256 mismatch for %s: got %s, pinned %s" % (url, got, sha256))
        os.replace(tmp, dest)
        return dest
    except RuntimeError:
        raise
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("download failed from %s: %r" % (url, e))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


if __name__ == "__main__":
    try:
        print("face model ready: %s" % install())
    except RuntimeError as e:
        print("FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)
