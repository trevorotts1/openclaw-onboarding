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
"""
from __future__ import annotations

import json
import os
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

def main(argv=None):
    args = H.add_args(description=__doc__).parse_args(argv)
    core = H.resolve_core(args)
    if not H.have_tools("ffprobe", "ffmpeg"):
        print("TOOLING: ffprobe and ffmpeg are required for this row's controls")
        return 2

    P = H.load_pkg(core, "intake_preflight.preflight")
    FM = H.load_file(core / "face_model_locator.py", "sc13_face_locator")
    DA = H.load_file(core / "delivery_audio.py", "sc13_delivery_audio")
    ASM = H.load_pkg(core, "final_assembler.assembler")
    c = H.Checks(ROW, TITLE)
    print("SC-13 %s — tree %s" % (TITLE, core))

    # the box's own ~/.openclaw stores must not contribute credentials/keys
    P._env_stores = lambda: []

    with H.Scratch() as run_dir:
        empty_bin = Path(run_dir) / "empty-bin"
        empty_bin.mkdir(parents=True, exist_ok=True)
        old_path = os.environ.get("PATH", "")
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
        bad = FM.preflight_status(env={FM.MODEL_ENV: str(wrong)})
        c.check("sc13:wrong-model-asset-refused-by-path",
                bad.get("ok") is False and bad.get("present") is True
                and bad.get("pinned") is False
                and str(wrong) in str(bad.get("problem")),
                "present=%s pinned=%s problem=%s"
                % (bad.get("present"), bad.get("pinned"),
                   str(bad.get("problem"))[:110]))

        # ---- an explicitly named tool path is authoritative ----------------
        take = H.aac_take(Path(run_dir) / "media" / "take.mp4", 2)
        bogus = str(Path(run_dir) / "no-such-ffprobe")
        named = DA.check_delivery_audio(take, ffprobe=bogus)
        c.check("sc13:named-ffprobe-refused-not-replaced",
                named.get("ok") is False and bogus in str(named.get("reason")),
                "code=%s detail=%s"
                % (named.get("reason_code"), str(named.get("reason"))[:120]))
        default = DA.check_delivery_audio(take)
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

        return c.finish(args.out)

if __name__ == "__main__":
    sys.exit(main())
