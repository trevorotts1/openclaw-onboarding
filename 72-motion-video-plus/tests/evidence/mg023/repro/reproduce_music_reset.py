#!/usr/bin/env python3
"""D-ASSEMBLE-MUSIC-RESET: before/after measurement for MG-023.

The defect (defect register, status VERIFIED_CODE): the pre-MG-022
assembler resolved the music bed in step 1b (a supplied track, a
pre-synthesized --score, or a fresh synthesis by synth-score.py,
ending at `music = adir + "/score.wav"`), and then, immediately
before building the audio graph, reassigned

    music = m.get("music_bed", "")

discarding the resolved score whenever the manifest named no
music_bed. The ducking branch could then only fire for a
manifest-supplied bed; a job whose score was synthesized got
`[vo]anull[aout]` (voiceover only) while the script still printed
"music synthesized".

This repro runs ONE legacy job through both assemblers:

  BEFORE  the genuine pre-repair script, extracted from git commit
          818ce42ee (72-motion-video-plus/scripts/assemble.sh plus
          its synth-score.py / synth-sfx.py / beat-grid.py siblings
          from the same commit), with three disclosed UNMASK patches
          (below) that repair the OTHER defects which otherwise
          stop the script before the audio graph can run at all
          (they were MG-022's to fix; they are not this defect).
  AFTER   the current scripts/assemble.sh (the MG-022 wrapper over
          assemble.py, with MG-023's policy layer), on the identical
          job directory.

The job: two 45-frame scenes (2.5 s of picture), a voiceover that is
a 440 Hz tone for the first 1.0 s and silence for the remaining
1.4 s, NO sfx events, and a manifest with music_bpm/music_seed but
NO music_bed, so the score must be synthesized. The measurement
window is 1.5 s to 2.4 s of the decoded output: the voiceover is
silent there by construction, so any energy in that window is the
score, and digital silence there is the discarded score.

UNMASK PATCHES (exact string replacements, counts asserted):
  P1 (D-ASSEMBLE-TUPLE, segment loop only):
     `cmd += ["-i", p]` -> `cmd += ["-i", p[1]]`
  P2 (D-ASSEMBLE-SINGLE-SCENE-FILTER, video chain tail):
     `vfilt += prev + "[vout];"` -> `vfilt += prev + "null[vout];"`
  P3 (D-ASSEMBLE-AUDIO-INDEX, graph references vs the real input
     list, in which the segments occupy indexes 0..len(segs)-1):
     `mix_terms = ["[0:a]"]` -> `mix_terms = ["[%d:a]" % len(segs)]`
     sfx delay line gains `+ len(segs)` on its input index, and the
     music input index `mi = len(inputs) - 1` becomes
     `mi = len(segs) + len(inputs) - 1`. (This job has no sfx events
     and, post-reset, no music input; the voiceover term is the one
     that fires. The other two keep the patch honest as a class.)

Usage: python3 reproduce_music_reset.py [output_dir]
Scratch jobs live under ~/workspace/skill72-v2/mg023-repro-work
(the home filesystem, never /tmp). Records land in output_dir
(default: this script's directory).
"""

import array
import json
import math
import os
import shutil
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REPO = os.path.abspath(os.path.join(SKILL, ".."))
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)
import audio_policy  # noqa: E402

BASE_COMMIT = "818ce42ee"
SCRATCH = os.path.expanduser("~/workspace/skill72-v2/mg023-repro-work")
RATE = 48000
WIN_START, WIN_END = int(1.5 * RATE), int(2.4 * RATE)


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def extract_old_scripts(dest):
    os.makedirs(dest, exist_ok=True)
    for name in ("assemble.sh", "synth-score.py", "synth-sfx.py", "beat-grid.py"):
        r = run(["git", "-C", REPO, "show",
                 "%s:72-motion-video-plus/scripts/%s" % (BASE_COMMIT, name)])
        if r.returncode != 0:
            raise SystemExit("git extraction failed for %s: %s" % (name, r.stderr))
        with open(os.path.join(dest, name), "w") as f:
            f.write(r.stdout)


def unmasked_copy(src_dir, dest_dir):
    shutil.copytree(src_dir, dest_dir)
    p = os.path.join(dest_dir, "assemble.sh")
    s = open(p).read()

    def patch(old, new, label):
        nonlocal s
        assert s.count(old) == 1, "unmask patch %s: pattern count %d" % (label, s.count(old))
        s = s.replace(old, new)

    patch('for i, p in enumerate(segs):\n    cmd += ["-i", p]',
          'for i, p in enumerate(segs):\n    cmd += ["-i", p[1]]', "P1")
    patch('vfilt += prev + "[vout];"', 'vfilt += prev + "null[vout];"', "P2")
    patch('mix_terms = ["[0:a]"]', 'mix_terms = ["[%d:a]" % len(segs)]', "P3a")
    patch('afilt += "[%d:a]adelay=%d|%d[sd%d];" % (inp_idx, ms, ms, k)',
          'afilt += "[%d:a]adelay=%d|%d[sd%d];" % (inp_idx + len(segs), ms, ms, k)',
          "P3b")
    patch("mi = len(inputs) - 1", "mi = len(segs) + len(inputs) - 1", "P3c")
    out = os.path.join(dest_dir, "assemble-unmasked.sh")
    with open(out, "w") as f:
        f.write(s)
    os.remove(p)
    return out


def make_job(root):
    work = os.path.join(root, "work")
    for sid, color in (("intro", "red"), ("outro", "blue")):
        d = os.path.join(work, "scenes", sid)
        os.makedirs(d, exist_ok=True)
        r = run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "color=c=%s:s=640x360:r=30" % color, "-frames:v", "45",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 os.path.join(d, sid + ".mp4")])
        if r.returncode != 0:
            raise SystemExit("segment fixture failed: " + r.stderr)
    adir = os.path.join(work, "audio")
    os.makedirs(adir, exist_ok=True)
    # Voiceover: 440 Hz at amplitude 0.5 for the first 1.0 s, then
    # digital silence to 2.4 s. The measurement window (1.5-2.4 s)
    # is voiceover-free by construction.
    samples = array.array("h", [
        int(0.5 * 32767 * math.sin(2 * math.pi * 440 * i / RATE))
        if i < RATE else 0
        for i in range(int(2.4 * RATE))])
    vo = os.path.join(adir, "voiceover.wav")
    with wave.open(vo, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())
    manifest = {"scenes": [{"id": "intro"}, {"id": "outro"}],
                "music_bpm": 120, "music_seed": 7}
    with open(os.path.join(root, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return root


def window_stats(path):
    samples = audio_policy.decode_pcm("ffmpeg", path)
    win = samples[WIN_START:WIN_END]
    return {
        "decodedSamples": len(samples),
        "windowSamples": len(win),
        "windowRmsDbfs": None if not win else round(audio_policy.rms_dbfs(win), 2),
        "windowMaxAbs": max((abs(x) for x in win), default=0),
        "digitalSilence": all(x == 0 for x in win) if win else None,
    }


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else HERE
    os.makedirs(out_dir, exist_ok=True)
    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH)
    os.makedirs(SCRATCH)

    extract_old_scripts(os.path.join(SCRATCH, "old"))
    unmasked = unmasked_copy(os.path.join(SCRATCH, "old"),
                             os.path.join(SCRATCH, "unmasked"))
    job = make_job(os.path.join(SCRATCH, "job"))
    work = os.path.join(job, "work")

    # BEFORE: the old (unmasked) script, identical job.
    before_out = os.path.join(SCRATCH, "before.mp4")
    rb = run(["bash", unmasked, "--manifest", "manifest.json",
              "--workdir", "work", "--voiceover", "work/audio/voiceover.wav",
              "--out", before_out], cwd=job)
    with open(os.path.join(out_dir, "before.log"), "w") as f:
        f.write(rb.stdout + rb.stderr)
    score_path = os.path.join(work, "audio", "score.wav")
    before = {
        "exitCode": rb.returncode,
        "scriptClaimedSynthesized": "music synthesized" in (rb.stdout + rb.stderr),
        "scoreFileExists": os.path.exists(score_path),
        "scoreWindow": window_stats(score_path) if os.path.exists(score_path) else None,
        "output": window_stats(before_out) if os.path.exists(before_out) else None,
    }

    # AFTER: the current wrapper on the identical job directory.
    after_out = os.path.join(SCRATCH, "after.mp4")
    ra = run(["bash", os.path.join(SCRIPTS, "assemble.sh"),
              "--manifest", os.path.join(job, "manifest.json"),
              "--workdir", work,
              "--voiceover", os.path.join(work, "audio", "voiceover.wav"),
              "--out", after_out], cwd=job)
    with open(os.path.join(out_dir, "after.log"), "w") as f:
        f.write(ra.stdout + ra.stderr)
    probe = {}
    probe_path = os.path.join(work, "assemble-probe.json")
    if os.path.exists(probe_path):
        probe = json.load(open(probe_path))
    after = {
        "exitCode": ra.returncode,
        "musicInInputRegistry": any(e.get("kind") == "music"
                                     for e in probe.get("inputs", [])),
        "output": window_stats(after_out) if os.path.exists(after_out) else None,
    }

    reproduced = bool(before["output"] and before["output"]["digitalSilence"]
                      and before["scoreWindow"]
                      and before["scoreWindow"]["windowMaxAbs"] > 1000)
    fixed = bool(after["output"] and not after["output"]["digitalSilence"]
                 and after["output"]["windowRmsDbfs"] is not None
                 and after["output"]["windowRmsDbfs"] > -45.0)
    record = {
        "defect": "D-ASSEMBLE-MUSIC-RESET",
        "item": "MG-023",
        "baseCommitForOldScript": BASE_COMMIT,
        "job": "two 45-frame scenes (2.5s picture); voiceover 440 Hz tone "
               "0-1.0s then silence to 2.4s; no sfx events; manifest "
               "music_bpm 120 music_seed 7 and NO music_bed",
        "measurementWindowSeconds": [1.5, 2.4],
        "unmaskPatches": ["P1 tuple p[1] (segment loop)",
                          "P2 video chain null[vout]",
                          "P3 audio indexes shifted by len(segs)"],
        "before": before,
        "after": after,
        "defectReproduced": reproduced,
        "fixedOnCurrentAssembler": fixed,
    }
    with open(os.path.join(out_dir, "music-reset-record.json"), "w") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    lines = [
        "D-ASSEMBLE-MUSIC-RESET before/after (MG-023)",
        "old script: git %s, three disclosed unmask patches (see script)" % BASE_COMMIT,
        "job: synthesized score, no music_bed; window 1.5-2.4s is voiceover-free",
        "BEFORE: exit=%d, script claimed synthesized=%s, score.wav window max=%s, "
        "output window RMS=%s dBFS, digital silence=%s"
        % (before["exitCode"], before["scriptClaimedSynthesized"],
           before["scoreWindow"]["windowMaxAbs"] if before["scoreWindow"] else "?",
           before["output"]["windowRmsDbfs"] if before["output"] else "?",
           before["output"]["digitalSilence"] if before["output"] else "?"),
        "AFTER: exit=%d, music in input registry=%s, output window RMS=%s dBFS, "
        "digital silence=%s"
        % (after["exitCode"], after["musicInInputRegistry"],
           after["output"]["windowRmsDbfs"] if after["output"] else "?",
           after["output"]["digitalSilence"] if after["output"] else "?"),
        "defect reproduced: %s; fixed on the current assembler: %s"
        % (reproduced, fixed),
    ]
    with open(os.path.join(out_dir, "summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if (reproduced and fixed) else 1


if __name__ == "__main__":
    sys.exit(main())
