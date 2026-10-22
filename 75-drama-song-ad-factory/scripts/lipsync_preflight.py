#!/usr/bin/env python3
"""lipsync_preflight.py: the lip-sync prerequisites, checked, with the repair.

    python3 scripts/lipsync_preflight.py              # check only (the default)
    python3 scripts/lipsync_preflight.py --check      # same
    python3 scripts/lipsync_preflight.py --repair     # install what is missing

Three states per prerequisite: PRESENT, MISSING, PRESENT-BUT-BROKEN (an import
raises for a reason other than the module being absent, or the model file is
there but is not the pinned size/sha256). One line each, and failed lines carry
the exact copy-paste repair command.

Exit codes mirror shared-utils/check-skill-prereqs.sh, so anything consuming
this can treat it the same way:
    0  every prerequisite present and valid
    2  one or more missing or broken (informational: it never blocks a
       non-lip-sync run, and it never lets a lip-sync job through)
    1  the check itself could not run

--repair is idempotent: it imports, it hashes, and it downloads only when
something is actually wrong, so a box that is already good pays the import and
one sha256 and nothing else. A download failure is loud (exact URL + HTTP
status), never a skip.

This file never weakens the gate. The gate is picture_gate/lip_gate, which
refuses a lip-sync job without all of this. This script only removes the
reason for that refusal to fire.
"""
from __future__ import annotations

import argparse
import importlib
import os
import shlex
import subprocess
import sys
import urllib.error

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIP_GATE = os.path.join(SKILL_ROOT, "scripts", "core", "lip_sync", "lip_gate")
REQUIREMENTS = os.path.join(SKILL_ROOT, "requirements-lipsync.txt")
MODULES = (("mediapipe", "mediapipe"), ("opencv", "cv2"), ("numpy", "numpy"))
LABELS = [label for label, _ in MODULES]
PY = sys.executable or "python3"


def _ifm():
    """install_face_model: the installer (download + place at the locator path)."""
    if LIP_GATE not in sys.path:
        sys.path.insert(0, LIP_GATE)
    import install_face_model
    return install_face_model


def _locator():
    """face_model_locator: the ONE path and pin for every reader (D19)."""
    core = os.path.join(SKILL_ROOT, "scripts", "core")
    if core not in sys.path:
        sys.path.insert(0, core)
    import face_model_locator
    return face_model_locator


def module_state(name):
    """-> (state, detail). MISSING only when THIS module is what is absent."""
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] == name:
            return "MISSING", "not importable"
        return "PRESENT-BUT-BROKEN", "%s: missing dependency %s" % (name, exc.name)
    except Exception as exc:                                  # noqa: BLE001
        return "PRESENT-BUT-BROKEN", "%s: %s" % (type(exc).__name__, str(exc)[:100])
    return "PRESENT", str(getattr(mod, "__version__", "") or "")


def model_state():
    """One state for the face model on the ONE shared locator path (D19).

    Installer, this preflight, the picture gate and the measured lip-sync gate
    all resolve through face_model_locator: $LIPSYNC_FACE_MODEL or
    <skill>/assets/face_landmarker.task, pinned sha256 verified. The old
    two-location world (assets/ plus a lip_gate/ copy for the clip gate) is
    gone — a locator path that is wrong or unpinned is PRESENT-BUT-BROKEN, and
    a missing one is MISSING.
    """
    try:
        loc = _locator()
    except Exception as exc:                                  # noqa: BLE001
        return "PRESENT-BUT-BROKEN", "face_model_locator unreadable: %s" % exc
    st = loc.preflight_status()
    if st["ok"]:
        return "PRESENT", st["path"]
    if st["present"]:
        return "PRESENT-BUT-BROKEN", st["problem"]
    return "MISSING", st["problem"]


def _judge(ifm, path, where):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return "MISSING", "%s: no file at %s" % (where, path)
    try:
        if ifm.is_good(path):
            return "PRESENT", path
        size = os.path.getsize(path)
    except OSError as exc:
        return "PRESENT-BUT-BROKEN", "%s: unreadable (%s)" % (path, exc)
    return ("PRESENT-BUT-BROKEN",
            "%s: size %d, want %d, sha256 not the pin" % (path, size, ifm.MODEL_BYTES))


def repair_commands(states):
    """The exact copy-paste command per failed prerequisite."""
    out = {}
    mods = sorted(label for label, _ in MODULES if states[label][0] != "PRESENT")
    if mods:
        out["modules"] = "%s -m pip install -r %s" % (shlex.quote(PY), shlex.quote(REQUIREMENTS))
    if states["face-model"][0] != "PRESENT":
        out["face-model"] = "%s %s" % (
            shlex.quote(PY),
            shlex.quote(os.path.join(LIP_GATE, "install_face_model.py")))
    return out


def repair(states):
    """Fix only what is not PRESENT. -> list of failures (empty == repaired)."""
    failures = []
    need_pip = any(states[label][0] != "PRESENT" for label in LABELS)
    if need_pip:
        cmd = [PY, "-m", "pip", "install", "-r", REQUIREMENTS]
        print("install: %s" % " ".join(shlex.quote(c) for c in cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-12:]
            failures.append("pip exited %d for %s\n  %s"
                            % (proc.returncode, REQUIREMENTS, "\n  ".join(tail)))
    if states["face-model"][0] != "PRESENT":
        failures.extend(_repair_model())
    return failures


def _repair_model():
    try:
        ifm = _ifm()
    except Exception as exc:                                  # noqa: BLE001
        return ["install_face_model unreadable: %s" % exc]
    failures = []
    try:
        dest = ifm.install()
        print("face model ready: %s" % dest)
    except urllib.error.HTTPError as exc:
        failures.append("download failed: %s -> HTTP %s" % (exc.url or ifm.MODEL_URL, exc.code))
        return failures
    except urllib.error.URLError as exc:
        failures.append("download failed: %s -> %s" % (ifm.MODEL_URL, exc.reason))
        return failures
    except Exception as exc:                                  # noqa: BLE001
        failures.append("download failed: %s -> %s: %s"
                        % (ifm.MODEL_URL, type(exc).__name__, exc))
        return failures
    # install() already places the model at the locator path every reader
    # resolves (override or assets/). The old lip_gate/ copy is never created
    # again and no gate reads it; an old copy left on a box is simply ignored.
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 75 lip-sync prerequisites.")
    ap.add_argument("--check", "--dry-run", dest="check", action="store_true",
                    help="check only, change nothing (the default)")
    ap.add_argument("--repair", action="store_true",
                    help="install the missing pieces; idempotent")
    args = ap.parse_args(argv)

    states = {label: module_state(mod) for label, mod in MODULES}
    states["face-model"] = model_state()

    width = max(len(k) for k in states)
    failed = []
    for name in LABELS + ["face-model"]:
        state, detail = states[name]
        line = "%-*s  %-20s %s" % (width, name, state, detail)
        print(line.rstrip())
        if state != "PRESENT":
            failed.append(name)

    if failed:
        cmds = repair_commands(states)
        for name in failed:
            key = "modules" if name in LABELS else "face-model"
            print("%-*s  repair: %s" % (width, name, cmds.get(key, "")))
        if not args.repair:
            print("%-*s  repair all: %s %s --repair"
                  % (width, "", shlex.quote(PY), shlex.quote(os.path.abspath(__file__))))

    if args.repair and failed:
        failures = repair(states)
        if failures:
            for f in failures:
                print("FAIL: %s" % f, file=sys.stderr)
            return 1
        states = {label: module_state(mod) for label, mod in MODULES}
        states["face-model"] = model_state()
        still = [n for n, (s, _) in states.items() if s != "PRESENT"]
        if still:
            print("FAIL: still not present after repair: %s" % ", ".join(sorted(still)),
                  file=sys.stderr)
            return 1
        print("repaired: %s" % ", ".join(sorted(failed)))
        return 0

    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
