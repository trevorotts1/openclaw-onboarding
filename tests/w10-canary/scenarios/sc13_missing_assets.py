#!/usr/bin/env python3
"""sc13_missing_assets.py — acceptance row SC-13 (missing ffmpeg / ASR / model).

required_result (SCENARIO-MATRIX.json, verbatim):
    "NEGATIVE: a missing ffmpeg, ASR or model asset fails closed with the named
     missing asset and no partial artifact is presented as delivered"

Proves, against the tree under test:
  * with no ffmpeg/ffprobe on PATH the derived preflight refuses
    (dependency-missing) and NAMES ffmpeg-binary and ffprobe-binary as the
    missing requirements — it never returns a pass;
  * an activated ASR (faster-whisper) gate is refused by name and is held
    REQUIRED even though the manifest marks it optional;
  * a face-model asset supplied by an explicit path that does not exist is
    refused by that exact path, and model_path() returns None — no silent
    fallback to a default location;
  * a present-but-wrong face-model file is refused by path and reason;
  * an explicitly named ffprobe that does not exist is never silently replaced
    by the one on PATH: the delivery gate and the duration probe both refuse
    naming the supplied path, while the default path still measures the file.

Stdlib + ffmpeg/ffprobe on the box for the controls. Exit 2 when the tools are
absent: the controls cannot be run and the row is never claimed.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run the scenario under deliberate fixture defects and REQUIRE
              the named assertions to turn RED (proves the harness can fail)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc13"
TITLE = "missing ffmpeg / ASR / model assets fail closed by name"
PROFILE = "drama-9x16-120s"
CAPS = {"media": ["music", "lyrics", "voiceover", "clips", "assembly"],
        "duration_s": 120, "channel": "text", "transport": "callback",
        "callback_path": "/kie/callback",
        "model_routes": ["openrouter/xiaomi/mimo-v2.6-pro"]}

def card_receipt():
    answers = {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
               "length": 120, "video_model": "Hailuo 02 Standard 768P"}
    try:
        from style_defaults import card_gate as CG  # noqa: PLC0415

        return CG.answered_stamped(answers, "SC-13 harness", "2026-10-23T00:00:00Z")
    except Exception:  # noqa: BLE001 - fallback keeps the fixture literal
        return {"answers": answers, "who": "SC-13 harness",
                "at": "2026-10-23T00:00:00Z"}

def payload(**over):
    p = {"auth": {"scope": "campaign"}, "summary_digest": "t",
         "card_receipt": card_receipt(), "env": {"KIE_API_KEY": "presence-only"},
         "capabilities": json.loads(json.dumps(CAPS)), "profile": PROFILE}
    p.update(over)
    return p

def scenario(core, muts=frozenset()):
    P = H.load_pkg(core, "intake_preflight.preflight")
    FM = H.load_file(core / "face_model_locator.py", "sc13_face_locator")
    DA = H.load_file(core / "delivery_audio.py", "sc13_delivery_audio")
    ASM = H.load_pkg(core, "final_assembler.assembler")
    c = H.Checks(ROW, TITLE)
    print("SC-13 %s — tree %s%s"
          % (TITLE, core,
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))

    # the box's own ~/.openclaw stores must not contribute credentials/keys
    P._env_stores = lambda: []

    with H.Scratch() as run_dir:
        empty_bin = Path(run_dir) / "empty-bin"
        empty_bin.mkdir(parents=True, exist_ok=True)
        old_path = os.environ.get("PATH", "")
        # the defect: leave the real PATH in place, so ffmpeg/ffprobe resolve
        if "tools_on_path" not in muts:
            os.environ["PATH"] = str(empty_bin)
        try:
            no_tools = P.check(payload())
            missing = no_tools.get("missing") or []
            c.check("sc13:missing-ffmpeg-named",
                    no_tools.get("reason_code") == "dependency-missing"
                    and "ffmpeg-binary" in missing
                    and "ffprobe-binary" in missing,
                    "reason=%s missing=%s"
                    % (no_tools.get("reason_code"), missing))
            c.check("sc13:missing-ffmpeg-never-passes",
                    no_tools.get("outcome") != "ok"
                    and no_tools.get("reason_code") != "preflight-pass",
                    "outcome=%s reason=%s"
                    % (no_tools.get("outcome"), no_tools.get("reason_code")))

            caps = json.loads(json.dumps(CAPS))
            if "asr_not_activated" not in muts:
                caps["lyric_timing_fallback"] = "faster-whisper"
            no_asr = P.check(payload(capabilities=caps))
            rows = {r.get("id"): r
                    for r in ((no_asr.get("checks") or {}).get("requirements") or [])}
            fw = rows.get("faster-whisper") or {}
            c.check("sc13:missing-asr-named",
                    no_asr.get("reason_code") == "dependency-missing"
                    and "faster-whisper" in (no_asr.get("missing") or []),
                    "reason=%s missing=%s"
                    % (no_asr.get("reason_code"), no_asr.get("missing")))
            c.check("sc13:activated-asr-gate-held-required",
                    fw.get("severity") == "required"
                    and fw.get("manifest_severity") == "optional",
                    "severity=%s manifest_severity=%s"
                    % (fw.get("severity"), fw.get("manifest_severity")))
        finally:
            os.environ["PATH"] = old_path

        # ---- model asset ---------------------------------------------------
        absent = str(Path(run_dir) / "models" / "face_landmarker.task")
        if "model_asset_present" in muts:
            Path(absent).parent.mkdir(parents=True, exist_ok=True)
            Path(absent).write_bytes(b"defect: the absent asset exists\n")
        st = FM.preflight_status(env={FM.MODEL_ENV: absent})
        c.check("sc13:missing-model-asset-named",
                st.get("ok") is False and st.get("present") is False
                and st.get("source") == "override"
                and absent in str(st.get("problem")),
                "path=%s source=%s problem=%s"
                % (st.get("path"), st.get("source"),
                   str(st.get("problem"))[:110]))
        c.check("sc13:missing-model-asset-no-silent-fallback",
                FM.model_path(env={FM.MODEL_ENV: absent}) is None,
                "model_path=%s for the supplied path"
                % (FM.model_path(env={FM.MODEL_ENV: absent}),))

        wrong = Path(run_dir) / "models" / "wrong.task"
        wrong.parent.mkdir(parents=True, exist_ok=True)
        wrong.write_bytes(b"not the pinned model\n")
        # the defect: the "wrong file" is not there at all, so the product can
        # no longer report present-but-unpinned
        supplied = str(wrong if "wrong_model_missing" not in muts
                       else Path(run_dir) / "models" / "gone.task")
        bad = FM.preflight_status(env={FM.MODEL_ENV: supplied})
        c.check("sc13:wrong-model-asset-refused-by-path",
                bad.get("ok") is False and bad.get("present") is True
                and bad.get("pinned") is False
                and supplied in str(bad.get("problem")),
                "present=%s pinned=%s problem=%s"
                % (bad.get("present"), bad.get("pinned"),
                   str(bad.get("problem"))[:110]))

        # ---- an explicitly named tool path is authoritative ----------------
        take = H.aac_take(Path(run_dir) / "media" / "take.mp4", 2)
        # the defect: the "bogus" named path is in fact the real ffprobe
        bogus = str(Path(run_dir) / "no-such-ffprobe")
        if "named_ffprobe_is_real" in muts:
            bogus = shutil.which("ffprobe") or bogus
        named = DA.check_delivery_audio(take, ffprobe=bogus)
        c.check("sc13:named-ffprobe-refused-not-replaced",
                named.get("ok") is False and bogus in str(named.get("reason")),
                "code=%s detail=%s"
                % (named.get("reason_code"), str(named.get("reason"))[:120]))
        # the defect: the default probe runs with nothing on PATH
        if "default_ffprobe_absent" in muts:
            empty_bin.mkdir(parents=True, exist_ok=True)
            os.environ["PATH"] = str(empty_bin)
        try:
            default = DA.check_delivery_audio(take)
        finally:
            os.environ["PATH"] = old_path
        c.check("sc13:default-ffprobe-still-measures",
                default.get("ok") is True
                and default.get("reason_code") == "DELIVERY_AUDIO_OK",
                "code=%s codec=%s" % (default.get("reason_code"),
                                      default.get("codec")))

        raised = None
        try:
            ASM.probe_duration(take, ffprobe=bogus)
        except RuntimeError as exc:
            raised = str(exc)
        c.check("sc13:named-probe-path-named-in-refusal",
                bool(raised) and raised.startswith("PROBE_UNAVAILABLE")
                and bogus in raised,
                "raised=%s" % (raised or "nothing"))

    return c

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED
# --------------------------------------------------------------------------
# ``sc13:missing-model-asset-no-silent-fallback`` has no working mutation: the
# product returns a path only for the exact PINNED model file, and the pinned
# bytes are not in the tree — an unpinned defect file leaves model_path() at
# None, so the assertion still passes. It is left out rather than faked.
MUTATIONS = {
    "tools_on_path": [
        "sc13:missing-ffmpeg-named",
        "sc13:missing-ffmpeg-never-passes",
    ],
    "asr_not_activated": [
        "sc13:missing-asr-named",
        "sc13:activated-asr-gate-held-required",
    ],
    "model_asset_present": [
        "sc13:missing-model-asset-named",
    ],
    "wrong_model_missing": [
        "sc13:wrong-model-asset-refused-by-path",
    ],
    "named_ffprobe_is_real": [
        "sc13:named-ffprobe-refused-not-replaced",
        "sc13:named-probe-path-named-in-refusal",
    ],
    "default_ffprobe_absent": [
        "sc13:default-ffprobe-still-measures",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on all %d defects" % len(MUTATIONS)
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    selftest_mode = bool(argv) and argv[0] == "selftest"
    args = H.add_args(
        description="sc13 selftest" if selftest_mode else __doc__
    ).parse_args(argv[1:] if selftest_mode else argv)
    core = H.resolve_core(args)
    if not H.have_tools("ffprobe", "ffmpeg"):
        print("TOOLING: ffprobe and ffmpeg are required for this row's controls")
        return 2
    if selftest_mode:
        return selftest(core)
    return scenario(core).finish(args.out)

if __name__ == "__main__":
    sys.exit(main())
