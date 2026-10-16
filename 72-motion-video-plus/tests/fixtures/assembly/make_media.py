#!/usr/bin/env python3
"""MG-022 fixture media generator.

Reads one example spec (specs/<id>.json) and its compiled plan
(plans/<id>.json, produced by generate_plans.mjs with the real MG-021
compiler) and writes synthetic media plus a media.json registry into
an output directory:

  scenes/<id>.mp4    ffmpeg lavfi solid-color segments, exactly the
                     declared source frame count at the plan fps.
                     Synthetic stand-ins for engine renders; the
                     "mixed" spec labels scenes with the engine they
                     stand in for, and the label is carried into
                     media.json and the evidence records.
  audio/<id>.wav     narration segments: sine tones at the spec's
                     toneHz, exactly the segment's sample length at
                     48000 Hz, so the final segment's presence and
                     length can be verified by band energy.
  audio/<sfx>.wav    short sine bursts for SFX cues.
  audio/music.wav    two-tone bed written at 44100 Hz with the stdlib
                     wave module (the legacy synth rate), so assembly
                     must resample it to the plan's 48000 Hz.

Usage: python3 make_media.py <spec_id> <out_dir>
"""

import json
import math
import os
import struct
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
RATE = 48000


def sine_wav(path, freqs, seconds, rate, amplitude=0.5):
    frames = int(round(seconds * rate))
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        buf = bytearray()
        for i in range(frames):
            v = sum(math.sin(2 * math.pi * f * i / rate) for f in freqs)
            v = int(32767 * amplitude * v / len(freqs))
            buf += struct.pack("<hh", v, v)
        w.writeframes(bytes(buf))


def main():
    spec_id, out_dir = sys.argv[1], sys.argv[2]
    spec = json.load(open(os.path.join(HERE, "specs", spec_id + ".json")))
    plan = json.load(open(os.path.join(HERE, "plans", spec_id + ".json")))
    sidecar = plan["sidecar"]
    fps = spec["fps"]
    os.makedirs(os.path.join(out_dir, "scenes"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "audio"), exist_ok=True)

    scenes = []
    for s in spec["scenes"]:
        frames = s.get("sourceDurationFrames", s["durationFrames"])
        rel = "scenes/%s.mp4" % s["id"]
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
               "-i", "color=c=%s:s=%dx%d:r=%d" % (
                   s["color"], spec["canvas"]["width"], spec["canvas"]["height"], fps),
               "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p",
               os.path.join(out_dir, rel)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("segment generation failed: " + r.stderr)
        entry = {"id": s["id"], "path": rel}
        if s.get("engine"):
            entry["engine"] = s["engine"]
        scenes.append(entry)

    narration = []
    seg_by_id = {t["id"]: t for t in sidecar["narration"]}
    for n in spec["narration"]:
        track = seg_by_id[n["id"]]
        seconds = (track["endSampleExclusive"] - track["startSample"]) / RATE
        rel = "audio/%s.wav" % n["id"]
        sine_wav(os.path.join(out_dir, rel), [n["toneHz"]], seconds, RATE)
        narration.append({"id": n["id"], "path": rel})

    sfx = []
    for x in spec["sfx"]:
        rel = "audio/%s.wav" % x["id"]
        sine_wav(os.path.join(out_dir, rel), [x["toneHz"]], x["durationSeconds"], RATE)
        sfx.append({"id": x["id"], "path": rel})

    music = None
    if spec.get("music"):
        if spec["music"].get("synthesized"):
            # MG-023: the registry declares a synthesized score; no
            # file is written. Assembly resolves and synthesizes it
            # exactly once (see scripts/audio_policy.py).
            music = {"synthesized": spec["music"]["synthesized"]}
        else:
            rel = "audio/music.wav"
            seconds = sidecar["total_samples"] / RATE
            sine_wav(os.path.join(out_dir, rel), spec["music"]["tonesHz"],
                     seconds, spec["music"].get("sampleRate", RATE), amplitude=0.8)
            music = {"path": rel}

    media = {
        "canvas": spec["canvas"],
        "fps": fps,
        "scenes": scenes,
        "narration": narration,
        "music": music,
        "sfx": sfx,
        "mix": spec.get("mix", {"musicVolume": 1.0, "ducking": None}),
    }
    if spec.get("syntheticSegments"):
        media["syntheticSegments"] = True
    with open(os.path.join(out_dir, "media.json"), "w") as f:
        json.dump(media, f, indent=2)
    print("media for %s written to %s (total %d frames)" % (spec_id, out_dir, sidecar["total_frames"]))


if __name__ == "__main__":
    main()
