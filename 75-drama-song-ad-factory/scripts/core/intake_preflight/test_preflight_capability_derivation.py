#!/usr/bin/env python3
"""W07-U1 (D05, D12; spec 9.1/9.2): capability-derived dependency preflight.

Proves, behaviourally:
  * the empty-lists counterexample (tools/modules/credentials all empty) now
    DERIVES real checks from the production mode, media choices, durations and
    channel via PREREQS.json and fails or repairs as appropriate -- it can
    never return preflight-pass on an unchecked media production;
  * explicit tool/module/credential checks keep their exact legacy behaviour
    and reason codes;
  * 120 s and all twelve profiles are known (D12: one canonical duration
    table, six lengths, lockstep-checked against BOTH canonical copies);
  * missing FFmpeg / missing ASR (faster-whisper) / missing face-model asset
    are detected BEFORE use with actionable repair plans and the affected
    checks rerun automatically after repair;
  * a gate that requires a package marks it required, never optional (the
    manifest's optional severity never downgrades an activated capability);
  * repair is idempotent (a satisfied requirement installs nothing; the
    launching interpreter is the install target and the verification target);
  * a non-generating diagnostic run declares itself with reduced requirements;
  * an unsupported local Python/architecture names the precise incompatibility
    and attempts no install (no loop).

Run: python3 scripts/core/intake_preflight/test_preflight_capability_derivation.py
stdlib only, no network, no provider, no writes outside a temp dir.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                            # intake.py / preflight.py
sys.path.insert(0, os.path.dirname(HERE))           # core/

import preflight as P         # noqa: E402  (package under test)

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _card_receipt():
    answers = {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
               "length": 60, "video_model": "Hailuo 02 Standard 768P"}
    try:
        from style_defaults import card_gate as CG  # noqa: PLC0415
        return CG.answered_stamped(answers, "W07-U1 test", "2026-10-22T09:00:00Z")
    except Exception:  # noqa: BLE001
        return {"answers": answers, "who": "W07-U1 test", "at": "2026-10-22T09:00:00Z"}


ENV_OK = {"KIE_API_KEY": "kie-presence-2026"}       # presence only, never read

CAPS_OK = {"media": ["music", "lyrics", "voiceover", "clips", "assembly"],
           "duration_s": 60, "channel": "text",
           "transport": "callback", "callback_path": "/kie/callback",
           "model_routes": ["openrouter/xiaomi/mimo-v2.6-pro"]}


def _payload(**over):
    p = {"auth": {"scope": "campaign"}, "summary_digest": "t",
         "card_receipt": _card_receipt(), "env": dict(ENV_OK),
         "capabilities": json.loads(json.dumps(CAPS_OK))}
    p.update(over)
    return p


def _stub_bin(tmpdir, names):
    """Executable stubs so tool checks are hermetic on any box."""
    os.makedirs(tmpdir, exist_ok=True)
    for n in names:
        path = os.path.join(tmpdir, n)
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmpdir


def _no_stores(monkey=True):
    """Keep the box's real ~/.openclaw stores out of test outcomes."""
    orig = P._env_stores
    P._env_stores = lambda: []
    return orig


def test_empty_lists_derive_real_checks_and_never_pass():
    """The D05 counterexample: empty tool/module/credential lists on a media
    production derive real checks and fail or repair -- never preflight-pass."""
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        empty_bin = os.path.join(tmp, "empty-bin")
        os.makedirs(empty_bin)
        os.environ["PATH"] = empty_bin                  # no ffmpeg, no ffprobe
        try:
            payload = _payload(tools=[], modules=[], credentials=[],
                               env={}, capabilities=dict(CAPS_OK, channel="text"))
            r = P.check(payload)
            check("counterexample never passes",
                  r.get("reason_code") != "preflight-pass" and r.get("outcome") != "ok",
                  "%s/%s" % (r.get("outcome"), r.get("reason_code")))
            check("counterexample fails as dependency-missing",
                  r.get("reason_code") == "dependency-missing", repr(r.get("reason_code")))
            missing = r.get("missing") or []
            for want in ("ffmpeg-binary", "ffprobe-binary", "kie-api-key"):
                check("derived check names %s" % want, want in missing, repr(missing))
            rows = r["checks"].get("derived") or []
            check("derived set is real (non-empty with reasons)",
                  len(rows) >= 6 and all(row.get("why") for row in rows),
                  str(len(rows)))
            check("derived set covers interpreter/tool/credential/storage",
                  {"python-interpreter", "ffmpeg-binary", "kie-api-key",
                   "storage-capacity"} <= {row["id"] for row in rows},
                  str(sorted(row["id"] for row in rows)))
            plan = (r.get("repair_plan") or {}).get("plan") or []
            check("repair plan is actionable", bool(plan) and all(
                i.get("command") or i.get("action") for i in plan), repr(plan))
            pip_items = [i for i in plan if i.get("command_argv") and
                         i["command_argv"][:2] == [sys.executable, "-m"]]
            check("install commands target the launching interpreter",
                  all(i["command_argv"][0] == sys.executable for i in pip_items),
                  repr([i.get("command_argv") for i in plan]))
            # repair as appropriate: the stub repairer places the missing tools,
            # the affected checks rerun automatically, and the run then passes.
            def runner(argv):
                if argv and len(argv) >= 3 and argv[1] == "-lc" and (
                        "brew" in argv[2] or "apt" in argv[2]):
                    _stub_bin(empty_bin, ["ffmpeg", "ffprobe"])
                return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}

            fixed = _payload(tools=[], modules=[], credentials=[],
                             env=dict(ENV_OK), capabilities=json.loads(json.dumps(CAPS_OK)))
            rep = P.repair(fixed, runner=runner, allow_system_install=True)
            check("repair reruns affected checks automatically",
                  "after" in (rep.get("rerun") or {}) and
                  rep["rerun"]["after"].get("ffmpeg-binary") is True,
                  json.dumps(rep.get("rerun"), default=str)[:300])
            check("post-repair result is preflight-pass",
                  rep["result"].get("reason_code") == "preflight-pass",
                  "%s/%s" % (rep["result"].get("outcome"),
                             rep["result"].get("reason_code")))
        finally:
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


def test_explicit_checks_keep_working():
    """Explicit lists keep their exact legacy reason codes."""
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = _stub_bin(os.path.join(tmp, "bin"), ["ffmpeg", "ffprobe"])
        os.environ["PATH"] = bin_dir
        try:
            r = P.check(_payload(tools=["no-such-tool-w07u1"], env=dict(ENV_OK)))
            check("explicit missing tool -> tool-unavailable",
                  r.get("reason_code") == "tool-unavailable" and
                  r.get("missing") == ["no-such-tool-w07u1"],
                  "%s/%s" % (r.get("reason_code"), r.get("missing")))
            r = P.check(_payload(modules=["no_such_module_w07u1"], env=dict(ENV_OK)))
            check("explicit missing module -> module-unavailable",
                  r.get("reason_code") == "module-unavailable" and
                  r.get("missing") == ["no_such_module_w07u1"],
                  "%s/%s" % (r.get("reason_code"), r.get("missing")))
            r = P.check(_payload(credentials=["NO_SUCH_KEY_W07U1"], env={}))
            check("explicit missing credential -> credential-missing",
                  r.get("reason_code") == "credential-missing" and
                  r.get("missing") == ["NO_SUCH_KEY_W07U1"],
                  "%s/%s" % (r.get("reason_code"), r.get("missing")))
            r = P.check(_payload(tools=["ffmpeg"], modules=[],
                                 credentials=["KIE_API_KEY"], env=dict(ENV_OK)))
            check("explicit satisfied lists still reach preflight-pass",
                  r.get("reason_code") == "preflight-pass",
                  "%s/%s" % (r.get("outcome"), r.get("reason_code")))
        finally:
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


def test_profiles_pass_including_120s():
    """D12: one canonical duration table (six lengths), all profiles known."""
    check("six canonical lengths incl 120",
          P.PROFILE_LENGTHS_S == (60, 90, 120, 180, 300, 600),
          repr(P.PROFILE_LENGTHS_S))
    try:
        from style_defaults import defaults as D  # noqa: PLC0415
        check("lockstep with style_defaults.LENGTH_OPTIONS_S",
              P.PROFILE_LENGTHS_S == tuple(D.LENGTH_OPTIONS_S),
              repr(D.LENGTH_OPTIONS_S))
    except Exception as e:  # noqa: BLE001
        check("lockstep with style_defaults.LENGTH_OPTIONS_S", False, str(e))
    try:
        from music_styles import music_styles as MS  # noqa: PLC0415
        check("lockstep with music_styles.OFFERED_LENGTHS_S",
              P.PROFILE_LENGTHS_S == tuple(MS.OFFERED_LENGTHS_S),
              repr(MS.OFFERED_LENGTHS_S))
    except Exception as e:  # noqa: BLE001
        check("lockstep with music_styles.OFFERED_LENGTHS_S", False, str(e))
    want = tuple("drama-%s-%ss" % (shape, secs)
                 for secs in (60, 90, 120, 180, 300, 600)
                 for shape in ("9x16", "16x9"))
    check("twelve profiles derived from the table", P.DEFAULT_PROFILES == want,
          "%s != %s" % (P.DEFAULT_PROFILES, want))
    for profile in P.DEFAULT_PROFILES:
        r = P.check({"profile": profile, "auth": {"scope": "campaign"},
                     "summary_digest": "t"})
        check("profile %s known" % profile,
              r.get("reason_code") != "delivery-profile-unknown",
              repr(r.get("reason_code")))
    check("120 s profile accepted (D12)",
          P.check({"profile": "drama-9x16-120s", "auth": {"scope": "campaign"},
                   "summary_digest": "t"}).get("reason_code")
          != "delivery-profile-unknown", "drama-9x16-120s rejected")


def test_missing_ffmpeg_detected_before_use_with_plan_and_rerun():
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        empty_bin = os.path.join(tmp, "empty-bin")
        os.makedirs(empty_bin)
        os.environ["PATH"] = empty_bin
        try:
            r = P.check(_payload(env=dict(ENV_OK)))
            check("missing ffmpeg detected before use",
                  r.get("reason_code") == "dependency-missing" and
                  "ffmpeg-binary" in (r.get("missing") or []),
                  "%s/%s" % (r.get("reason_code"), r.get("missing")))
            plan = (r.get("repair_plan") or {}).get("plan") or []
            ff = [i for i in plan if i["id"] in ("ffmpeg-binary", "ffprobe-binary")]
            check("ffmpeg repair plan carries an install command",
                  len(ff) == 2 and all(i.get("command") for i in ff), repr(ff))
            calls = []

            def runner(argv):
                calls.append(argv)
                _stub_bin(empty_bin, ["ffmpeg", "ffprobe"])
                return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}

            rep = P.repair(_payload(env=dict(ENV_OK)), runner=runner,
                           allow_system_install=True)
            check("repair attempted the tool install once",
                  len(calls) >= 1, repr(calls))
            check("affected checks reran automatically after repair",
                  rep["rerun"]["before"].get("ffmpeg-binary") is False and
                  rep["rerun"]["after"].get("ffmpeg-binary") is True,
                  json.dumps(rep.get("rerun"), default=str)[:300])
            check("post-repair preflight passes",
                  rep["result"].get("reason_code") == "preflight-pass",
                  repr(rep["result"].get("reason_code")))
        finally:
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


def test_missing_asr_detected_and_required_never_optional():
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PATH"] = _stub_bin(os.path.join(tmp, "bin"),
                                       ["ffmpeg", "ffprobe"])
        try:
            caps = json.loads(json.dumps(CAPS_OK))
            caps["lyric_timing_fallback"] = "faster-whisper"
            r = P.check(_payload(capabilities=caps, env=dict(ENV_OK)))
            check("missing faster-whisper detected before use",
                  r.get("reason_code") == "dependency-missing" and
                  "faster-whisper" in (r.get("missing") or []),
                  "%s/%s" % (r.get("reason_code"), r.get("missing")))
            rows = {row["id"]: row for row in r["checks"]["requirements"]}
            check("activated ASR gate is required, never optional",
                  rows["faster-whisper"]["severity"] == "required",
                  repr(rows["faster-whisper"]))
            check("manifest's optional severity recorded but not obeyed",
                  rows["faster-whisper"]["manifest_severity"] == "optional",
                  repr(rows["faster-whisper"]))
            plan = (r.get("repair_plan") or {}).get("plan") or []
            fw = [i for i in plan if i["id"] == "faster-whisper"]
            check("ASR repair installs into the launching interpreter",
                  len(fw) == 1 and fw[0].get("command_argv", [None])[0] == sys.executable,
                  repr(fw))
            mods = os.path.join(tmp, "mods")
            os.makedirs(mods)

            def runner(argv):
                with open(os.path.join(mods, "faster_whisper.py"), "w") as f:
                    f.write("# stub\n")
                return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}

            sys.path.insert(0, mods)
            try:
                rep = P.repair(_payload(capabilities=caps, env=dict(ENV_OK)),
                               runner=runner)
                check("ASR check reran automatically after repair",
                      rep["rerun"]["before"].get("faster-whisper") is False and
                      rep["rerun"]["after"].get("faster-whisper") is True,
                      json.dumps(rep.get("rerun"), default=str)[:300])
                check("module install records a launcher-verify probe",
                      any("launcher_verify" in a for a in rep.get("attempts", [])),
                      json.dumps(rep.get("attempts"), default=str)[:300])
                check("post-repair preflight passes with ASR satisfied",
                      rep["result"].get("reason_code") == "preflight-pass",
                      repr(rep["result"].get("reason_code")))
            finally:
                sys.path.remove(mods)
        finally:
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


def test_missing_model_asset_detected_with_plan_and_rerun():
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    old_env = os.environ.get("LIPSYNC_FACE_MODEL")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PATH"] = _stub_bin(os.path.join(tmp, "bin"),
                                       ["ffmpeg", "ffprobe"])
        try:
            caps = json.loads(json.dumps(CAPS_OK))
            caps["lip_sync"] = True
            os.environ["LIPSYNC_FACE_MODEL"] = os.path.join(tmp, "nope", "face_landmarker.task")
            r = P.check(_payload(capabilities=caps, env=dict(ENV_OK)))
            check("missing face model detected before use",
                  "face-landmarker-model" in (r.get("missing") or []),
                  "%s/%s" % (r.get("reason_code"), r.get("missing")))
            rows = {row["id"]: row for row in r["checks"]["requirements"]}
            check("lip-sync asset is required, never optional",
                  rows["face-landmarker-model"]["severity"] == "required",
                  repr(rows["face-landmarker-model"]))
            plan = (r.get("repair_plan") or {}).get("plan") or []
            fm = [i for i in plan if i["id"] == "face-landmarker-model"]
            check("asset repair names the existing verified installer",
                  len(fm) == 1 and "install_face_model.py" in (fm[0].get("command") or ""),
                  repr(fm))
            # repair path: the installer's own pin is the one authority; the
            # repair runner writes a file that satisfies it and the automatic
            # rerun sees PRESENT (before False -> after True).
            dest = os.path.join(tmp, "face_landmarker.task")
            content = b"\x00" * 4096
            lip_gate = os.path.join(P.skill_root(), "scripts", "core",
                                    "lip_sync", "lip_gate")
            if lip_gate not in sys.path:
                sys.path.insert(0, lip_gate)
            import install_face_model as IFM  # noqa: PLC0415
            # pin authority is face_model_locator since W07-U2's delegation
            # landed on this base: patch BOTH modules or is_good() reads the
            # real pin and the stub file can never satisfy it.
            import face_model_locator as LOC  # noqa: PLC0415
            real_sha, real_bytes = LOC.MODEL_SHA256, LOC.MODEL_BYTES
            import hashlib
            LOC.MODEL_SHA256 = IFM.MODEL_SHA256 = hashlib.sha256(content).hexdigest()
            LOC.MODEL_BYTES = IFM.MODEL_BYTES = len(content)
            os.environ["LIPSYNC_FACE_MODEL"] = dest
            try:
                def installer(argv):
                    with open(dest, "wb") as f:
                        f.write(content)
                    return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}

                rep = P.repair(_payload(capabilities=caps, env=dict(ENV_OK)),
                               runner=installer)
                check("model-asset check reran automatically after repair",
                      rep["rerun"]["before"].get("face-landmarker-model") is False and
                      rep["rerun"]["after"].get("face-landmarker-model") is True,
                      json.dumps(rep.get("rerun"), default=str)[:300])
                # wrong-hash file is PRESENT-BUT-BROKEN, never PRESENT
                LOC.MODEL_SHA256 = IFM.MODEL_SHA256 = "0" * 64
                state, detail = P.face_model_state()
                check("wrong-hash asset is PRESENT-BUT-BROKEN, never PRESENT",
                      state == "PRESENT-BUT-BROKEN" and "mismatch" in detail,
                      "%s (%s)" % (state, detail))
            finally:
                LOC.MODEL_SHA256 = IFM.MODEL_SHA256 = real_sha
                LOC.MODEL_BYTES = IFM.MODEL_BYTES = real_bytes
        finally:
            os.environ["PATH"] = old_path
            if old_env is None:
                os.environ.pop("LIPSYNC_FACE_MODEL", None)
            else:
                os.environ["LIPSYNC_FACE_MODEL"] = old_env
            P._env_stores = orig_stores


def test_repair_is_idempotent_in_the_launching_interpreter():
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PATH"] = _stub_bin(os.path.join(tmp, "bin"),
                                       ["ffmpeg", "ffprobe"])
        try:
            calls = []

            def runner(argv):
                calls.append(list(argv))
                return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}

            healthy = _payload(env=dict(ENV_OK))
            rep1 = P.repair(healthy, runner=runner)
            check("repair on a satisfied payload is a no-op",
                  rep1.get("attempts") == [] and
                  "idempotent" in (rep1.get("note") or ""),
                  json.dumps(rep1.get("attempts"), default=str))
            check("no-op repair runs zero installs", calls == [], repr(calls))
            check("launching interpreter recorded on the receipt",
                  rep1.get("interpreter", {}).get("path") == sys.executable,
                  repr(rep1.get("interpreter")))
            # a real failing payload: first repair installs, second is a no-op
            orig_stores2 = _no_stores()
            try:
                caps = json.loads(json.dumps(CAPS_OK))
                caps["lyric_timing_fallback"] = "faster-whisper"
                mods = os.path.join(tmp, "mods")
                os.makedirs(mods)

                def installer(argv):
                    calls.append(list(argv))
                    with open(os.path.join(mods, "faster_whisper.py"), "w") as f:
                        f.write("# stub\n")
                    return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}

                sys.path.insert(0, mods)
                try:
                    P.repair(_payload(capabilities=caps, env=dict(ENV_OK)),
                             runner=installer)
                    n_first = len(calls)
                    rep2 = P.repair(_payload(capabilities=caps, env=dict(ENV_OK)),
                                    runner=installer)
                    check("second repair rerun installs nothing (idempotent)",
                          len(calls) == n_first and rep2.get("attempts") == [],
                          "%d -> %d calls" % (n_first, len(calls)))
                finally:
                    sys.path.remove(mods)
            finally:
                P._env_stores = orig_stores2
            check("every install argv starts at the launching interpreter",
                  all(c and c[0] == sys.executable for c in calls), repr(calls))
        finally:
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


def test_diagnostic_mode_declares_itself():
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PATH"] = os.path.join(tmp, "nothing")
        try:
            r = P.check({"mode": "diagnostic", "env": {}})
            check("diagnostic run is ok",
                  r.get("outcome") == "ok", repr(r.get("reason_code")))
            check("diagnostic never claims preflight-pass",
                  r.get("reason_code") == "preflight-pass-diagnostic",
                  repr(r.get("reason_code")))
            check("diagnostic declares itself",
                  r.get("mode") == "diagnostic" and r.get("generating") is False and
                  r.get("readiness") == "diagnostic-only",
                  "%s/%s/%s" % (r.get("mode"), r.get("generating"), r.get("readiness")))
            kinds = {row["kind"] for row in r["checks"]["derived"]}
            check("diagnostic requirements are reduced",
                  kinds <= {"platform", "python", "storage", "temp"}, repr(kinds))
        finally:
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


def test_requirements_empty_never_passes_a_media_production():
    orig_stores = _no_stores()
    try:
        r = P.check(_payload(capabilities=dict(CAPS_OK, media=[]), env=dict(ENV_OK)))
        check("empty media/requirements -> requirements-empty",
              r.get("reason_code") == "requirements-empty",
              "%s/%s" % (r.get("outcome"), r.get("reason_code")))
        r2 = P.check(_payload(tools=[], modules=[], credentials=[],
                              manifest_path=os.path.join(tempfile.gettempdir(),
                                                         "no-such-PREREQS.json"),
                              env=dict(ENV_OK)))
        check("missing manifest fails closed for a media production",
              r2.get("reason_code") == "manifest-unavailable",
              "%s/%s" % (r2.get("outcome"), r2.get("reason_code")))
    finally:
        P._env_stores = orig_stores


def test_unsupported_python_or_arch_names_incompatibility_no_loop():
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PATH"] = _stub_bin(os.path.join(tmp, "bin"),
                                       ["ffmpeg", "ffprobe"])
        real_archs, real_min = P.SUPPORTED_ARCHS, P.MIN_PYTHON
        try:
            P.SUPPORTED_ARCHS = ("no-such-arch-w07u1",)
            r = P.check(_payload(env=dict(ENV_OK)))
            check("unsupported arch -> platform-unsupported",
                  r.get("reason_code") == "platform-unsupported",
                  "%s/%s" % (r.get("outcome"), r.get("reason_code")))
            check("incompatibility named precisely",
                  P._platform.machine() in (r.get("next_action") or "")
                  or P._platform.machine() in json.dumps(r.get("repair_plan"),
                                                         default=str),
                  repr(r.get("next_action")))
            calls = []
            rep = P.repair(_payload(env=dict(ENV_OK)),
                           runner=lambda argv: calls.append(argv) or
                           {"rc": 0, "stdout_tail": "", "stderr_tail": ""})
            check("unsupported arch: no install attempted, no loop",
                  rep.get("attempts") == [] and rep.get("loop") is False and
                  calls == [], json.dumps(rep, default=str)[:200])
            P.SUPPORTED_ARCHS = real_archs
            P.MIN_PYTHON = (99, 0)
            r2 = P.check(_payload(env=dict(ENV_OK)))
            check("unsupported python -> python-unsupported with version named",
                  r2.get("reason_code") == "python-unsupported" and
                  P._platform.python_version() in (r2.get("next_action") or ""),
                  "%s/%s" % (r2.get("reason_code"), r2.get("next_action")))
            rep2 = P.repair(_payload(env=dict(ENV_OK)),
                            runner=lambda argv: calls.append(argv) or
                            {"rc": 0, "stdout_tail": "", "stderr_tail": ""})
            check("unsupported python: no install attempted, no loop",
                  rep2.get("attempts") == [] and rep2.get("loop") is False and
                  calls == [], json.dumps(rep2, default=str)[:200])
        finally:
            P.SUPPORTED_ARCHS, P.MIN_PYTHON = real_archs, real_min
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


def test_externally_managed_interpreter_retries_once_in_isolated_env():
    """PEP 668 (Homebrew et al): a pip install refused by the launching
    interpreter gets exactly ONE retry in the isolated env, the receipt names
    the interpreter the launcher must use, and nothing loops."""
    orig_stores = _no_stores()
    old_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PATH"] = _stub_bin(os.path.join(tmp, "bin"),
                                       ["ffmpeg", "ffprobe"])
        try:
            calls = []
            caps = json.loads(json.dumps(CAPS_OK))
            caps["lyric_timing_fallback"] = "faster-whisper"

            def runner(argv):
                calls.append(list(argv))
                if "-m" in argv and "venv" in argv:         # fake venv creation
                    vdir = argv[-1]
                    py = P.isolated_env_python(vdir)
                    os.makedirs(os.path.dirname(py), exist_ok=True)
                    open(py, "w").close()
                    return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}
                if argv and "pip" in argv and argv[0] == sys.executable:
                    return {"rc": 1, "stdout_tail": "",
                            "stderr_tail": "error: externally-managed-environment "
                                           "(PEP 668)"}
                return {"rc": 0, "stdout_tail": "", "stderr_tail": ""}

            rep = P.repair(_payload(capabilities=caps, env=dict(ENV_OK)),
                           runner=runner,
                           fallback_env_dir=os.path.join(tmp, "fallback-venv"))
            pip_calls = [c for c in calls if "pip" in c]
            check("pip refused once, retried exactly once (no loop)",
                  len(pip_calls) == 2, repr(pip_calls))
            check("retry landed in an isolated env",
                  any("isolated_retry" in a for a in rep.get("attempts", [])) and
                  bool(rep.get("isolated_env")),
                  json.dumps(rep.get("attempts"), default=str)[:300])
            check("receipt names the interpreter the launcher must use",
                  any(a.get("launcher_must_use") for a in rep.get("attempts", [])),
                  json.dumps(rep.get("attempts"), default=str)[:300])
        finally:
            os.environ["PATH"] = old_path
            P._env_stores = orig_stores


TESTS = [
    test_empty_lists_derive_real_checks_and_never_pass,
    test_explicit_checks_keep_working,
    test_profiles_pass_including_120s,
    test_missing_ffmpeg_detected_before_use_with_plan_and_rerun,
    test_missing_asr_detected_and_required_never_optional,
    test_missing_model_asset_detected_with_plan_and_rerun,
    test_repair_is_idempotent_in_the_launching_interpreter,
    test_diagnostic_mode_declares_itself,
    test_requirements_empty_never_passes_a_media_production,
    test_unsupported_python_or_arch_names_incompatibility_no_loop,
    test_externally_managed_interpreter_retries_once_in_isolated_env,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False, "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d W07-U1 capability-preflight tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
