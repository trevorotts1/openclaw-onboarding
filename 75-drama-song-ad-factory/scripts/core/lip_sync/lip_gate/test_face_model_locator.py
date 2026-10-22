#!/usr/bin/env python3
"""test_face_model_locator.py: one face-model path across every reader (D19).

Proves the D19 acceptance: the installer, the picture gate and the measured
lip-sync gate resolve the SAME face-model path as the shared locator
(scripts/core/face_model_locator.py), including the configured override, and
the preflight seam (face_model_locator.preflight_status) plus the fleet
installer helper (shared-utils/lipsync-deps.sh) agree with them. A legacy copy
in the old lip_gate/ location must NOT win. Wrong size or wrong hash is never
"the model" for any reader.

Run:  python3 test_face_model_locator.py     (exit 0 all pass, 1 any fail)
Writes only under its own tempfile.mkdtemp scratch, plus one transient
placeholder next to the modules that is removed in a finally block.
Stdlib only; no network; no mediapipe import needed.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (HERE, CORE):
    if p not in sys.path:
        sys.path.insert(0, p)

import face_model_locator as LOC           # noqa: E402
import install_face_model as IM            # noqa: E402
import mouth_landmarks as ML               # noqa: E402
import picture_measure as PM               # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + detail) if detail else ""))
    return ok


def fake_opener(payload):
    def open_url(url, timeout=None):
        return io.BytesIO(payload)
    return open_url


def sh_helper(helper, skills_dir):
    script = ('export LIPSYNC_DEPS_LIB_ONLY=1 SKILLS_DIR="%s"\n'
              'source "%s"\n'
              'echo "PATH=$(_lipsync_model_path)"\n'
              'echo "SHA=$LIPSYNC_MODEL_SHA256"\n'
              'echo "BYTES=$LIPSYNC_MODEL_BYTES"\n' % (skills_dir, helper))
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    out = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    return r.returncode, out


def main():
    tmp = tempfile.mkdtemp(prefix="s75-w07-u2-locator-")
    saved = {}
    legacy = os.path.join(HERE, "face_landmarker.task")
    try:
        # ---- pins are single-sourced in the locator -------------------------
        check("pins-sourced-from-locator",
              IM.MODEL_SHA256 == LOC.MODEL_SHA256 and IM.MODEL_BYTES == LOC.MODEL_BYTES
              and IM.MODEL_NAME == LOC.MODEL_NAME and IM.DEFAULT_DEST == LOC.default_path(),
              "installer re-exports locator pins")

        # ---- 1) path identity, no override --------------------------------
        want_default = os.path.abspath(os.path.join(LOC.SKILL_ROOT, "assets",
                                                    "face_landmarker.task"))
        check("default-path-is-assets", LOC.resolve() == want_default, want_default)
        check("installer-default-equals-locator", IM.DEFAULT_DEST == LOC.resolve())

        saved["is_good"] = LOC.is_good
        LOC.is_good = lambda p: True          # path plumbing only; pin check below
        check("picture-gate-same-path", PM.model_path() == LOC.resolve())
        check("lip-gate-same-path", ML.model_path() == LOC.resolve())
        check("preflight-seam-same-path",
              LOC.preflight_status()["path"] == LOC.resolve()
              and LOC.preflight_status()["source"] == "default")
        LOC.is_good = saved["is_good"]

        # ---- 2) path identity, configured override ------------------------
        over = os.path.join(tmp, "custom", "my.task")
        os.makedirs(os.path.dirname(over))
        with open(over, "wb") as f:
            f.write(b"x" * 16)
        os.environ[LOC.MODEL_ENV] = over
        try:
            check("override-path-everywhere",
                  LOC.resolve() == os.path.abspath(over)
                  and IM.install.__defaults__[0] is None  # installer resolves at call
                  )
            LOC.is_good = lambda p: True
            check("override-picture-gate", PM.model_path() == os.path.abspath(over))
            check("override-lip-gate", ML.model_path() == os.path.abspath(over))
            st = LOC.preflight_status()
            check("override-preflight-seam",
                  st["path"] == os.path.abspath(over) and st["source"] == "override")
            LOC.is_good = saved["is_good"]

            # ---- 3) installer places the file where readers read ----------
            payload = b"model-bytes-for-install-test"
            real = hashlib.sha256(payload).hexdigest()
            got = IM.install(url="x", sha256=real, opener=fake_opener(payload))
            check("installer-honors-override-dest",
                  got == os.path.abspath(over) and open(over, "rb").read() == payload)
            bad = os.path.join(tmp, "nope.task")
            try:
                IM.install(dest=bad, url="x", sha256="0" * 64,
                           opener=fake_opener(payload))
                check("installer-hash-mismatch-refuses", False, "no exception")
            except RuntimeError:
                check("installer-hash-mismatch-refuses",
                      not os.path.exists(bad) and not os.path.exists(bad + ".part"))
        finally:
            os.environ.pop(LOC.MODEL_ENV, None)

        # ---- 4) verification: wrong size / wrong hash never pass ----------
        good = os.path.join(tmp, "good.task")
        with open(good, "wb") as f:
            f.write(payload)
        saved["sha"], saved["bytes"] = LOC.MODEL_SHA256, LOC.MODEL_BYTES
        LOC.MODEL_SHA256, LOC.MODEL_BYTES = real, len(payload)  # test pins
        try:
            check("is-good-accepts-pinned", LOC.is_good(good))
            trunc = os.path.join(tmp, "trunc.task")
            with open(trunc, "wb") as f:
                f.write(payload[:-1])
            check("is-good-rejects-wrong-size", not LOC.is_good(trunc))
            other = os.path.join(tmp, "other.task")
            with open(other, "wb") as f:
                f.write(payload[:-1] + b"z")
            check("is-good-rejects-wrong-hash", not LOC.is_good(other))
            check("missing-rejected", not LOC.is_good(os.path.join(tmp, "absent.task")))

            os.environ[LOC.MODEL_ENV] = other
            try:
                LOC.is_good = saved["is_good"]
                raised = False
                try:
                    PM.model_path()
                except PM.PictureGateUnavailable:
                    raised = True
                check("picture-gate-refuses-wrong-hash", raised)
                check("lip-gate-refuses-wrong-hash", ML.model_path() is None)
                check("preflight-seam-refuses-wrong-hash",
                      LOC.preflight_status()["ok"] is False
                      and "install" in (LOC.preflight_status()["problem"] or ""))
            finally:
                os.environ.pop(LOC.MODEL_ENV, None)
        finally:
            LOC.MODEL_SHA256, LOC.MODEL_BYTES = saved["sha"], saved["bytes"]

        # ---- 5) legacy lip_gate/ copy must NOT win (the D19 disagreement) --
        os.environ[LOC.MODEL_ENV] = ""
        planted_default = False
        try:
            with open(legacy, "wb") as f:
                f.write(payload)
            os.makedirs(os.path.dirname(want_default), exist_ok=True)
            with open(want_default, "wb") as f:
                f.write(payload)
            planted_default = True
            LOC.MODEL_SHA256, LOC.MODEL_BYTES = real, len(payload)
            LOC.is_good = saved["is_good"]
            check("legacy-lipgate-copy-ignored-by-lip-gate",
                  ML.model_path() == want_default)
            check("legacy-lipgate-copy-ignored-by-picture-gate",
                  PM.model_path() == want_default)
        finally:
            LOC.MODEL_SHA256, LOC.MODEL_BYTES = saved["sha"], saved["bytes"]
            os.environ.pop(LOC.MODEL_ENV, None)
            if os.path.exists(legacy):
                os.remove(legacy)
            if planted_default and os.path.exists(want_default):
                os.remove(want_default)

        # ---- 6) fleet helper agrees (path + pin drift kill) ---------------
        helper = os.environ.get("LIPSYNC_DEPS_HELPER") or os.path.abspath(os.path.join(
            CORE, "..", "..", "..", "shared-utils", "lipsync-deps.sh"))
        if os.path.isfile(helper):
            skills = os.path.join(tmp, "skills")
            os.makedirs(skills)
            os.symlink(LOC.SKILL_ROOT, os.path.join(skills, "75-drama-song-ad-factory"))
            rc, out = sh_helper(helper, skills)
            same = (os.path.realpath(out.get("PATH", "")) ==
                    os.path.realpath(LOC.resolve()))
            check("lipsync-deps-path-equals-locator",
                  rc == 0 and same, out.get("PATH", ""))
            check("lipsync-deps-pins-equal-locator",
                  out.get("SHA") == LOC.MODEL_SHA256
                  and out.get("BYTES") == str(LOC.MODEL_BYTES))
        else:
            # Named, reasoned absence, never a silent pass: the fleet helper is
            # the OpenClaw distribution's installer (shared-utils at its repo
            # root). The Claude-Nine distribution installs via this very
            # installer script, whose pins the first check above ties to the
            # locator. Set LIPSYNC_DEPS_HELPER to run the agreement elsewhere.
            check("lipsync-deps-helper-absent-is-recorded", True,
                  "not in this distribution: %s (OpenClaw fleet helper; "
                  "override with LIPSYNC_DEPS_HELPER to check it)" % helper)

        # ---- 7) preflight seam shape (U1 consumes exactly this) -----------
        st = LOC.preflight_status()
        check("preflight-status-shape",
              set(st) == {"path", "source", "ok", "present", "pinned", "sha256",
                          "bytes", "install_command", "problem"}
              and st["install_command"] == IM.INSTALL_COMMAND)

        # ---- 8) the lip-sync preflight READER resolves the same path ------
        import importlib.util
        pf_path = os.path.join(LOC.SKILL_ROOT, "scripts", "lipsync_preflight.py")
        spec = importlib.util.spec_from_file_location("lipsync_preflight", pf_path)
        PF = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(PF)
        LOC.MODEL_SHA256, LOC.MODEL_BYTES = real, len(payload)
        try:
            os.environ[LOC.MODEL_ENV] = os.path.join(tmp, "good.task")
            with open(os.environ[LOC.MODEL_ENV], "wb") as f:
                f.write(payload)
            state, detail = PF.model_state()
            check("preflight-reader-same-path-override",
                  state == "PRESENT" and detail == os.path.abspath(
                      os.environ[LOC.MODEL_ENV]),
                  "%s %s" % (state, detail))
            with open(os.environ[LOC.MODEL_ENV], "wb") as f:
                f.write(payload[:-1] + b"z")
            state, _ = PF.model_state()
            check("preflight-reader-refuses-wrong-hash",
                  state == "PRESENT-BUT-BROKEN")
            os.environ[LOC.MODEL_ENV] = os.path.join(tmp, "absent.task")
            state, _ = PF.model_state()
            check("preflight-reader-missing", state == "MISSING")
            os.environ[LOC.MODEL_ENV] = ""
            os.makedirs(os.path.dirname(want_default), exist_ok=True)
            with open(want_default, "wb") as f:
                f.write(payload)
            state, detail = PF.model_state()
            check("preflight-reader-same-path-default",
                  state == "PRESENT" and detail == want_default,
                  "%s %s" % (state, detail))
            os.remove(want_default)
        finally:
            LOC.MODEL_SHA256, LOC.MODEL_BYTES = saved["sha"], saved["bytes"]
            os.environ.pop(LOC.MODEL_ENV, None)
            if os.path.exists(want_default):
                os.remove(want_default)
    finally:
        LOC.is_good = saved.get("is_good", LOC.is_good)
        os.environ.pop(LOC.MODEL_ENV, None)
        if os.path.exists(legacy):
            os.remove(legacy)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s passed, %s failed" % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
