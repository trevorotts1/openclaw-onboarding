#!/usr/bin/env python3
"""MG-022 defect reproductions against the pre-repair scripts/assemble.sh.

Each known assembly defect is reproduced against the ORIGINAL script
(the version at the MG-022 base commit) and the observed failure is
captured into a log file next to this script:

  D-ASSEMBLE-TUPLE
      assemble.sh builds the ffmpeg argument list from the segment
      tuples (scene_id, path, duration) without unpacking them, so
      building the shell command dies with
      "TypeError: expected string or bytes-like object, got 'tuple'".
      Reproduced by running the shipped script, unmodified, on a valid
      two-scene job. It fails on ANY input.

  D-ASSEMBLE-SINGLE-SCENE-FILTER
      The video chain is terminated with prev + "[vout];", which puts
      two pad labels side by side with no filter between them, for
      every scene count: "[0:v][vout];" for one scene, "[xv1][vout];"
      for two. ffmpeg rejects the graph with "No such filter: ''".
      The tuple defect masks this, so the repro applies UNMASK PATCH 1
      (use the path element of the tuple when building -i arguments)
      and runs a single-scene job.

  D-ASSEMBLE-AUDIO-INDEX
      The ffmpeg command puts the segment files first and the audio
      files after them, but the audio filter graph addresses the
      voiceover as [0:a] and each SFX event by its position in the
      audio-only list. Those indexes name the VIDEO segment inputs.
      With video-only segments ffmpeg refuses the graph ("Stream
      specifier ':a' ... matches no streams") and prints the generated
      graph showing [0:a]/[1:a] bound to segment inputs while the real
      audio inputs (2 and 3) are never referenced. Needs UNMASK PATCH 1
      and UNMASK PATCH 2 (terminate the video chain with an explicit
      null filter) to reach the audio graph at all.

  D-ASSEMBLE-SHORTEST-SFX-DRIFT
      SFX event times accumulate UNSHORTENED scene durations
      (t += d) while the xfade chain shortens the picture by FADE per
      join, and the encode finishes with -shortest. With audio-bearing
      segments (so the misindexed graph can run at all), measurement of
      the output shows all three consequences at once: the intended
      440 Hz voiceover is absent from every window; the stream the
      graph actually delayed (scene 2's own audio, an 880 Hz tone)
      starts at the unshortened placement 2.00s although the picture
      puts that scene-local moment at 1.50s (drift = the 0.5s fade);
      and the output ends at 2.50s although the audio graph was built
      to 3.50s (the -shortest cut).

  Observation recorded for MG-023 (not one of the four reproduced
  defects): after synthesising a score, the script re-reads
  music = m.get("music_bed", "") before building the audio graph, so a
  synthesized score is silently discarded; the scenario B graph printed
  by ffmpeg contains no music input at all.

The unmask patches are minimal, applied only to a throwaway copy, and
exist solely to let execution reach the downstream defects:

  PATCH 1:  cmd += ["-i", p]      ->  cmd += ["-i", p[1]]
            (only in the segment loop, not the audio-input loop)
  PATCH 2:  vfilt += prev + "[vout];"  ->  vfilt += prev + "null[vout];"

Usage: python3 reproduce_defects.py [output_dir]
Fixtures are generated with ffmpeg lavfi into a temp dir. The four
scenario logs and the scenario C band analysis are written to
output_dir (default: this script's directory).
"""

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
ASSEMBLE_SH = os.path.join(SKILL, "scripts", "assemble.sh")
SCRIPTS = os.path.join(SKILL, "scripts")


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def make_segment(path, color, with_audio):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", "color=c=%s:s=640x360:r=30:d=1.5" % color]
    if with_audio == "tone880":
        cmd += ["-f", "lavfi", "-i", "sine=frequency=880:duration=1.5"]
    elif with_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-t", "1.5", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac"]
    cmd += [path]
    r = run(cmd)
    if r.returncode != 0:
        raise SystemExit("fixture generation failed: " + r.stderr)


def make_job(root, scene_ids, with_audio):
    work = os.path.join(root, "work")
    for sid in scene_ids:
        color = "red" if sid == "intro" else "blue"
        audio = False
        if with_audio:
            audio = "tone880" if sid == "outro" else "silent"
        make_segment(os.path.join(work, "scenes", sid, sid + ".mp4"), color, audio)
    os.makedirs(os.path.join(work, "audio"), exist_ok=True)
    r = run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=2.6",
             "-c:a", "aac", os.path.join(work, "audio", "voiceover.m4a")])
    if r.returncode != 0:
        raise SystemExit("voiceover fixture failed: " + r.stderr)
    manifest = {
        "scenes": [
            {"id": "intro", "sfx_events": []},
            {"id": "outro", "sfx_events": [{"sound": "pop", "at_seconds": 0.5}]},
        ][: len(scene_ids)],
        "music_bpm": 120,
        "music_seed": 7,
    }
    with open(os.path.join(root, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return root


def unmasked_copy(dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    for name in ("assemble.sh", "synth-score.py", "synth-sfx.py", "beat-grid.py"):
        shutil.copy(os.path.join(SCRIPTS, name), dest_dir)
    p = os.path.join(dest_dir, "assemble.sh")
    s = open(p).read()
    seg_loop = 'for i, p in enumerate(segs):\n    cmd += ["-i", p]'
    assert s.count(seg_loop) == 1, "segment loop not found"
    s = s.replace(seg_loop, 'for i, p in enumerate(segs):\n    cmd += ["-i", p[1]]')
    tail = 'vfilt += prev + "[vout];"'
    assert s.count(tail) == 1, "video chain tail not found"
    s = s.replace(tail, 'vfilt += prev + "null[vout];"')
    out = os.path.join(dest_dir, "assemble-unmasked.sh")
    with open(out, "w") as f:
        f.write(s)
    os.remove(p)
    return out


def goertzel(samples, sr, freq):
    k = 2 * math.pi * freq / sr
    coeff = 2 * math.cos(k)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return math.sqrt(max(s1 * s1 + s2 * s2 - coeff * s1 * s2, 0.0)) / max(len(samples), 1)


def analyse_wav(path):
    w = wave.open(path)
    n, sr = w.getnframes(), w.getframerate()
    data = struct.unpack("<%dh" % n, w.readframes(n))
    lines = ["decoded %s: %d samples at %d Hz (%.2fs)" % (path, n, sr, n / sr)]
    win = sr // 4
    for i in range(0, n - win + 1, win):
        seg = data[i:i + win]
        lines.append("t=%.2f-%.2f  440Hz amp=%8.1f  880Hz amp=%8.1f"
                     % (i / sr, i / sr + 0.25,
                        goertzel(seg, sr, 440), goertzel(seg, sr, 880)))
    return "\n".join(lines) + "\n"


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else HERE
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="mg022-repro-")
    summary = []

    def record(name, text):
        with open(os.path.join(out_dir, name), "w") as f:
            f.write(text)

    # D-ASSEMBLE-TUPLE: the shipped script, unmodified, valid job.
    job = make_job(os.path.join(tmp, "tuple"), ["intro", "outro"], with_audio=False)
    r = run(["bash", ASSEMBLE_SH, "--manifest", "manifest.json", "--workdir", "work",
             "--voiceover", "work/audio/voiceover.m4a", "--out", "final.mp4"], cwd=job)
    record("tuple.log", r.stdout + r.stderr)
    ok = "TypeError: expected string or bytes-like object, got 'tuple'" in (r.stdout + r.stderr)
    summary.append(("D-ASSEMBLE-TUPLE", ok, "exit=%d" % r.returncode))

    unmasked = unmasked_copy(os.path.join(tmp, "unmasked"))

    def run_unmasked(jobdir, outname):
        return run(["bash", unmasked, "--manifest", "manifest.json", "--workdir", "work",
                    "--voiceover", "work/audio/voiceover.m4a", "--out", outname], cwd=jobdir)

    # D-ASSEMBLE-SINGLE-SCENE-FILTER: one scene, unmask patch 1 only is
    # not separable from patch 2 in the copy; patch 2 replaces the very
    # construction under test, so for this scenario use a copy with
    # ONLY patch 1. Build it here.
    p1dir = os.path.join(tmp, "unmasked-p1")
    os.makedirs(p1dir, exist_ok=True)
    for name in ("synth-score.py", "synth-sfx.py", "beat-grid.py"):
        shutil.copy(os.path.join(SCRIPTS, name), p1dir)
    s = open(ASSEMBLE_SH).read()
    seg_loop = 'for i, p in enumerate(segs):\n    cmd += ["-i", p]'
    s = s.replace(seg_loop, 'for i, p in enumerate(segs):\n    cmd += ["-i", p[1]]')
    p1 = os.path.join(p1dir, "assemble-p1.sh")
    open(p1, "w").write(s)
    job1 = make_job(os.path.join(tmp, "single"), ["intro"], with_audio=False)
    r = run(["bash", p1, "--manifest", "manifest.json", "--workdir", "work",
             "--voiceover", "work/audio/voiceover.m4a", "--out", "final.mp4"], cwd=job1)
    record("scenario-a-single-scene.log", r.stdout + r.stderr)
    ok = "No such filter: ''" in (r.stdout + r.stderr)
    summary.append(("D-ASSEMBLE-SINGLE-SCENE-FILTER", ok, "exit=%d" % r.returncode))

    # D-ASSEMBLE-AUDIO-INDEX: two scenes, video-only segments.
    job2 = make_job(os.path.join(tmp, "two"), ["intro", "outro"], with_audio=False)
    r = run_unmasked(job2, "final.mp4")
    record("scenario-b-audio-index.log", r.stdout + r.stderr)
    ok = "matches no streams" in (r.stdout + r.stderr) and "[1:a]adelay=2000|2000" in (r.stdout + r.stderr)
    summary.append(("D-ASSEMBLE-AUDIO-INDEX", ok, "exit=%d" % r.returncode))

    # D-ASSEMBLE-SHORTEST-SFX-DRIFT: two scenes with audio tracks.
    job3 = make_job(os.path.join(tmp, "av"), ["intro", "outro"], with_audio=True)
    r = run_unmasked(job3, "final.mp4")
    record("scenario-c-drift.log", r.stdout + r.stderr)
    analysis = ""
    out_mp4 = os.path.join(job3, "final.mp4")
    if os.path.exists(out_mp4):
        wav = os.path.join(job3, "final.wav")
        run(["ffmpeg", "-v", "error", "-y", "-i", out_mp4, "-map", "0:a",
             "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", wav])
        analysis = analyse_wav(wav)
    record("scenario-c-analysis.txt", analysis)
    dur = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", out_mp4]).stdout.strip() if os.path.exists(out_mp4) else "?"
    ok = ("440Hz amp=     0.0" in analysis and "880Hz amp=  4" in analysis
          and dur.startswith("2.5"))
    summary.append(("D-ASSEMBLE-SHORTEST-SFX-DRIFT", ok,
                    "output duration=%s, drift analysis in scenario-c-analysis.txt" % dur))

    lines = ["MG-022 defect reproduction summary (against pre-repair assemble.sh)",
             "fixtures: ffmpeg lavfi synthetic segments, 1.5s each, 30 fps, 640x360", ""]
    for name, ok, detail in summary:
        lines.append("%s: %s (%s)" % (name, "REPRODUCED" if ok else "NOT REPRODUCED", detail))
    record("summary.txt", "\n".join(lines) + "\n")
    print("\n".join(lines))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if all(ok for _, ok, _ in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
