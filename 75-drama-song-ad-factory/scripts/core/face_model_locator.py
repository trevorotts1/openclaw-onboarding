#!/usr/bin/env python3
"""face_model_locator.py: the ONE face-model path for skill 75 (D19).

Before this module the install and read locations disagreed:

  * install_face_model.py  -> <skill>/assets/face_landmarker.task
  * picture_measure.py     -> LIPSYNC_FACE_MODEL or <skill>/assets/ (agreed)
  * mouth_landmarks.py     -> LIPSYNC_FACE_MODEL or <lip_gate>/ (DISAGREED)
  * shared-utils/lipsync-deps.sh kept BOTH files in sync by mirroring.

Now every consumer resolves through this module:

  1. env LIPSYNC_FACE_MODEL  (the one legitimate configured override)
  2. <skill>/assets/face_landmarker.task  (the only default)

and verifies the pinned sha256 + size before any use. A file that fails
verification is never "the model": readers refuse (UNMEASURED /
PictureGateUnavailable), never a silent pass.

Consumers: install_face_model.py (installer), picture_measure.py (picture
gate), mouth_landmarks.py (measured lip-sync gate), intake_preflight/
preflight.py (via ``preflight_status``), shared-utils/lipsync-deps.sh (fleet
installer helper, via the CLI below).

CLI (stdlib only, no network unless asked):

    python3 face_model_locator.py path    # resolved path, override or default
    python3 face_model_locator.py pins    # name=/sha256=/bytes=/url= lines
    python3 face_model_locator.py check   # 0 good, 2 missing/mismatch, 1 usage

Exit codes match lipsync-deps.sh's check contract.
"""
from __future__ import annotations

import hashlib
import os
import sys

MODEL_ENV = "LIPSYNC_FACE_MODEL"
MODEL_NAME = "face_landmarker.task"
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
MODEL_BYTES = 3758596
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/latest/face_landmarker.task")

#: <skill root> = two levels above scripts/core/ (this file lives in core/).
SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "..", ".."))
INSTALL_COMMAND = "python3 %s" % os.path.join(
    "scripts", "core", "lip_sync", "lip_gate", "install_face_model.py")


def default_path():
    return os.path.join(SKILL_ROOT, "assets", MODEL_NAME)


def resolve(env=None):
    """The one face-model path: override if set, else <skill>/assets/."""
    env = os.environ if env is None else env
    p = (env.get(MODEL_ENV) or "").strip() or default_path()
    return os.path.abspath(p)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def is_good(path):
    """True only for the exact pinned file (size AND sha256)."""
    return (os.path.isfile(path) and os.path.getsize(path) == MODEL_BYTES
            and sha256_file(path) == MODEL_SHA256)


def problem(path):
    """None when the file is the pinned model, else one human line saying why."""
    if not os.path.isfile(path):
        return "face model not found at %s; install it with: %s" % (path, INSTALL_COMMAND)
    size = os.path.getsize(path)
    if size != MODEL_BYTES:
        return "face model at %s is %s bytes, pinned %s; reinstall with: %s" % (
            path, size, MODEL_BYTES, INSTALL_COMMAND)
    return "face model at %s failed the pinned sha256; reinstall with: %s" % (
        path, INSTALL_COMMAND)


def model_path(env=None):
    """The verified model path, or None when missing/wrong (never a silent pass)."""
    p = resolve(env)
    return p if is_good(p) else None


def preflight_status(env=None):
    """The one status record every gate reads (preflight seam included).

    -> dict(path, source, ok, present, pinned, sha256, bytes, install_command,
            problem). ``source`` is 'override' or 'default'; ``ok`` is True only
    for the exact pinned file at the resolved path.
    """
    env = os.environ if env is None else env
    override = (env.get(MODEL_ENV) or "").strip()
    p = resolve(env)
    present = os.path.isfile(p)
    pinned = is_good(p)
    return {
        "path": p,
        "source": "override" if override else "default",
        "ok": pinned,
        "present": present,
        "pinned": pinned,
        "sha256": MODEL_SHA256,
        "bytes": MODEL_BYTES,
        "install_command": INSTALL_COMMAND,
        "problem": None if pinned else problem(p),
    }


def _main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "path":
        print(resolve())
        return 0
    if cmd == "pins":
        for line in ("name=%s" % MODEL_NAME, "sha256=%s" % MODEL_SHA256,
                     "bytes=%s" % MODEL_BYTES, "url=%s" % MODEL_URL):
            print(line)
        return 0
    if cmd == "check":
        st = preflight_status()
        if st["ok"]:
            print("face model ok: %s" % st["path"])
            return 0
        print("face model NOT ready: %s" % st["problem"], file=sys.stderr)
        return 2
    print("usage: face_model_locator.py path|pins|check", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
