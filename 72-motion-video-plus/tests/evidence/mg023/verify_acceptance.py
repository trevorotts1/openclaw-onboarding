#!/usr/bin/env python3
"""MG-023 acceptance verification: audio policy and mode mixing.

Renders the MG-023 acceptance examples with the current assembler
(real ffmpeg), then judges each directive acceptance item on
measurements of the ENCODED output, taken independently of the
assembler's own probe record (fresh ffprobe inventory, fresh
loudness measurement, fresh band analysis of the decoded file):

  silent output (mode none) contains no unintended audio
      -> noaudio: the output has no audio stream at all.
  inherited audio is not duplicated
      -> inherited: the package carries a 220/330 Hz bed but the
         parent owns the soundtrack; the output has no audio stream
         and the exclusion is recorded. Contrast: the identical
         package resolved as own carries the 220 Hz band at a
         measured amplitude in the thousands of int16 units.
  the chosen score is audible in the planned sections
      -> ownmix, synthown, musicsfx: the assembler's score
         audibility check passes with its measured window, and an
         independent band measurement finds the music tones in a
         narration-free window of the decoded output.
  measured loudness on the encoded output
      -> own examples re-measured within 1.0 LU of -14 LUFS.
  clipping and missing final words fail by name
      -> doctored narration outputs (tail silenced, gained into
         clipping, gained off target) are handed to verify_audio,
         which must raise ASSEMBLE_AUDIO_FINAL_WORDS_MISSING,
         ASSEMBLE_AUDIO_CLIPPING, ASSEMBLE_AUDIO_LOUDNESS_OFF_TARGET.
  stems preserved
      -> own examples emit one non-silent stem per contributing role.

Rendered outputs land in tests/evidence/mg023/outputs/ (not
committed; only the records are). Records land in
tests/evidence/mg023/acceptance/.

Usage: python3 verify_acceptance.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPTS = os.path.join(SKILL, "scripts")
FIXTURES = os.path.join(SKILL, "tests", "fixtures", "assembly")
OUT_DIR = os.path.join(HERE, "outputs")
REC_DIR = os.path.join(HERE, "acceptance")
sys.path.insert(0, SCRIPTS)

import assemble  # noqa: E402
import audio_policy  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
RATE = audio_policy.SAMPLE_RATE
TARGET = {"integratedLufs": -14.0, "truePeakDb": -1.0}


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def render(example, work_root, plan_mutator=None):
    media_dir = os.path.join(work_root, example + "-media")
    r = run([sys.executable, os.path.join(FIXTURES, "make_media.py"),
             example, media_dir])
    assert r.returncode == 0, r.stderr
    plan_path = os.path.join(FIXTURES, "plans", example + ".json")
    if plan_mutator:
        plan = json.load(open(plan_path))
        plan_mutator(plan)
        plan_path = os.path.join(work_root, example + "-plan.json")
        json.dump(plan, open(plan_path, "w"))
    out = os.path.join(OUT_DIR, example + ".mp4")
    proc = run([sys.executable, os.path.join(SCRIPTS, "assemble.py"),
                "--plan", plan_path,
                "--media", os.path.join(media_dir, "media.json"),
                "--out", out,
                "--workdir", os.path.join(work_root, example + "-work")])
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout), out, media_dir


def probe_streams(path):
    r = run([FFPROBE, "-v", "error", "-show_entries",
             "stream=codec_type,codec_name", "-of", "json", path])
    return json.loads(r.stdout)["streams"]


def check(name, ok, **measured):
    entry = {"check": name, "ok": bool(ok)}
    entry.update(measured)
    return entry


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REC_DIR, exist_ok=True)
    work_root = tempfile.mkdtemp(prefix="mg023-accept-",
                                 dir=os.path.expanduser("~"))
    summary = {"item": "MG-023", "examples": {}, "allOk": True}

    def record(example, checks, extra=None):
        rec = {"example": example, "checks": checks,
               "allOk": all(c["ok"] for c in checks)}
        if extra:
            rec.update(extra)
        with open(os.path.join(REC_DIR, example + "-record.json"), "w") as f:
            json.dump(rec, f, indent=2, sort_keys=True)
        summary["examples"][example] = rec["allOk"]
        summary["allOk"] = summary["allOk"] and rec["allOk"]
        print(example, "OK" if rec["allOk"] else "FAILED")

    # --- mode none: silent output, no unintended audio ----------
    record_probe, out, _ = render("noaudio", work_root)
    streams = probe_streams(out)
    record("noaudio", [
        check("no_audio_stream", all(s["codec_type"] != "audio" for s in streams),
              streams=[s["codec_type"] for s in streams]),
        check("resolved_mode_none",
              record_probe["audio_plan"]["mode"] == "none"),
    ])

    # --- mode inherited: the parent bed is not duplicated -------
    rec_inh, out_inh, _ = render("inherited", work_root)
    streams = probe_streams(out_inh)
    rec_flip, out_flip, _ = render(
        "inherited", work_root,
        plan_mutator=lambda p: p["timeline"].__setitem__("audio_owner", "self"))
    flip_samples = audio_policy.decode_pcm(FFMPEG, out_flip)
    bed_amp = audio_policy.band_amplitude(flip_samples[RATE:2 * RATE], RATE, 220)
    record("inherited", [
        check("no_audio_stream", all(s["codec_type"] != "audio" for s in streams),
              streams=[s["codec_type"] for s in streams]),
        check("exclusion_recorded",
              rec_inh["audio_plan"]["exclusions"]
              and rec_inh["audio_plan"]["exclusions"][0]["code"]
              == "ASSEMBLE_AUDIO_PARENT_OWNED"),
        check("contrast_same_package_as_own_carries_the_bed", bed_amp > 1000.0,
              bandAmplitude220HzOwn=int(round(bed_amp))),
    ])

    # --- mode own: defaults, loudness, stems, score, final words -
    for example, tones in (("ownmix", (220, 330)), ("synthown", None),
                           ("musicsfx", (220, 330))):
        rec, out, _ = render(example, work_root)
        qc = rec["audio_qc"]
        remeasured = audio_policy.measure_loudness(FFMPEG, out, TARGET)
        verdict = audio_policy.loudness_verdict(remeasured, TARGET)
        samples = audio_policy.decode_pcm(FFMPEG, out)
        checks = [
            check("encoded_loudness_within_tolerance", verdict["ok"],
                  measured=verdict["measured"],
                  integratedDeltaLufs=verdict["integratedDeltaLufs"],
                  truePeakOverDb=verdict["truePeakOverDb"]),
            check("score_audible_in_planned_sections",
                  qc["scoreAudible"]["audible"],
                  windowRmsDbfs=qc["scoreAudible"]["windowRmsDbfs"],
                  expectedRmsDbfs=qc["scoreAudible"]["expectedRmsDbfs"]),
            check("final_words_present_at_planned_end",
                  qc["finalWords"]["presentAtPlannedEnd"],
                  bandRatio=qc["finalWords"]["bandRatio"]),
            check("output_not_clipped", not qc["outputClipping"]["clipped"],
                  outputPeakDbfs=qc["outputClipping"]["peakDbfs"]),
        ]
        if tones:
            sidecar = json.load(open(os.path.join(
                FIXTURES, "plans", example + ".json")))["sidecar"]
            gap = audio_policy.longest_gap(
                [(sg["startSample"], sg["endSampleExclusive"])
                 for sg in sidecar["narration"]], len(samples))
            if gap:
                mid = samples[(gap[0] + gap[1]) // 2 - RATE // 4:
                              (gap[0] + gap[1]) // 2 + RATE // 4]
                amp = max(audio_policy.band_amplitude(mid, RATE, t) for t in tones)
                checks.append(check("independent_band_measurement_of_score",
                                    amp > 100.0, bandAmplitude=int(round(amp))))
        stem_rms = {}
        for role, stem_path in sorted(rec["stems"].items()):
            s = audio_policy.decode_pcm(FFMPEG, stem_path)
            stem_rms[role] = round(audio_policy.rms_dbfs(s), 2)
        checks.append(check("stems_preserved_and_audible",
                            all(v > -45.0 for v in stem_rms.values())
                            and len(stem_rms) >= 2, stemRmsDbfs=stem_rms))
        record(example, checks, {"audioPlan": rec["audio_plan"]})

    # --- failure vocabulary on doctored outputs -----------------
    media_dir = os.path.join(work_root, "narration-media")
    r = run([sys.executable, os.path.join(FIXTURES, "make_media.py"),
             "narration", media_dir])
    assert r.returncode == 0, r.stderr
    job = assemble.job_from_plan(
        os.path.join(FIXTURES, "plans", "narration.json"), None,
        os.path.join(media_dir, "media.json"), FFPROBE)
    good = os.path.join(OUT_DIR, "narration-good.mp4")
    assemble.run_assembly(job, good, os.path.join(work_root, "narration-work"),
                          FFMPEG, FFPROBE)

    def doctor(audio_filter, name):
        doctored = os.path.join(OUT_DIR, name)
        proc = run([FFMPEG, "-y", "-i", good, "-af", audio_filter,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", doctored])
        assert proc.returncode == 0, proc.stderr[-500:]
        try:
            assemble.verify_audio(FFMPEG, doctored, job)
            return None
        except assemble.AssembleError as e:
            return e.code

    record("failure-vocabulary", [
        check("missing_final_words_fail_by_name",
              doctor("volume=0:enable='gte(t,3.2)'", "noend.mp4")
              == "ASSEMBLE_AUDIO_FINAL_WORDS_MISSING"),
        check("clipped_output_fails_by_name",
              doctor("volume=8", "clipped.mp4") == "ASSEMBLE_AUDIO_CLIPPING"),
        check("off_target_loudness_fails_by_name",
              doctor("volume=2", "loud.mp4")
              == "ASSEMBLE_AUDIO_LOUDNESS_OFF_TARGET"),
        check("undoctored_output_passes",
              doctor("volume=1", "same.mp4") is None),
    ])

    with open(os.path.join(REC_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    print("ALL OK" if summary["allOk"] else "SOME CHECKS FAILED")
    shutil.rmtree(work_root, ignore_errors=True)
    return 0 if summary["allOk"] else 1


if __name__ == "__main__":
    sys.exit(main())
