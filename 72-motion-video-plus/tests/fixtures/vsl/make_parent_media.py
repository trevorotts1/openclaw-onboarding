"""MG-037 fixture builder: the parent VSL's own media package.

Builds, deterministically and offline, everything the PARENT job
owns in the desktop VSL acceptance build:

- host-a.mp4 / host-b.mp4: the host program before and after the
  insert slot (synthetic test-pattern segments, clearly fixtures,
  at the parent's real 1920x1080 30 fps canvas, exact frame counts
  of 900 and 360).
- narr-intro.wav / narr-cue.wav / narr-outro.wav: the parent's
  narration as word-shaped tone bursts (the MG-023 measurement
  convention: band-limited bursts the audio policy's presence
  analysis can verify). The cue segment starts exactly at parent
  frame 900 (sample 1440000) and its first word starts on that
  sample: that word is the cue the insert answers to. The final
  segment's last word ends exactly at the program's final sample
  (2304000), so the final-words check measures a real ending.
- music.wav: the parent's music bed, synthesized once through the
  shipped synth-score.py (seeded, deterministic).
- media-spec.json: the parent media package the assembly consumes
  (scene durations, narration placements with absolute word
  timings, captions, music, mix). The insert scene entry carries
  use_return_artifact so the assembler is handed the returned
  insert MP4 itself, never a copy or a re-render.

Usage: python3 make_parent_media.py OUT_DIR
"""

import array
import json
import math
import os
import subprocess
import sys
import wave

RATE = 48000
SAMPLES_PER_FRAME = RATE // 30  # 1600 at 30 fps

# (id, start_frame, end_frame_exclusive, [(word_start, word_end), ...])
# Word ranges are ABSOLUTE program samples.
SEGMENTS = [
    ("narr-intro", 0, 900,
     [(k * 72000, k * 72000 + 48000) for k in range(20)]),
    ("narr-cue", 900, 1080,
     [(1440000 + k * 48000, 1440000 + k * 48000 + 38400)
      for k in range(6)]),
    ("narr-outro", 1080, 1440,
     [(1728000 + k * 72000, 1728000 + k * 72000 + 48000)
      for k in range(7)] + [(2256000, 2304000)]),
]


def synth_segment(path, seg_start_sample, seg_end_sample, words):
    total = seg_end_sample - seg_start_sample
    samples = array.array("h", bytes(2 * total))
    for wi, (w_start, w_end) in enumerate(words):
        f0 = 190.0 + ((wi * 37) % 90)
        s = w_start - seg_start_sample
        e = w_end - seg_start_sample
        for i in range(s, e):
            t = (i - s) / max(1, (e - s))
            env = 0.5 - 0.5 * math.cos(2.0 * math.pi * t)
            tau = (i - s) / RATE
            v = env * (0.62 * math.sin(2.0 * math.pi * f0 * tau)
                       + 0.28 * math.sin(2.0 * math.pi * 2.0 * f0 * tau)
                       + 0.14 * math.sin(2.0 * math.pi * 3.13 * f0 * tau))
            samples[i] = int(0.5 * 32767 * v)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(samples.tobytes())


def host_video(path, frames):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         "testsrc2=size=1920x1080:rate=30", "-frames:v", str(frames),
         "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", path],
        check=True)


def main():
    out_dir = os.path.abspath(sys.argv[1])
    os.makedirs(out_dir, exist_ok=True)
    scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "..", "scripts")

    host_video(os.path.join(out_dir, "host-a.mp4"), 900)
    host_video(os.path.join(out_dir, "host-b.mp4"), 360)

    narration = []
    for seg_id, start_f, end_f, words in SEGMENTS:
        start_sample = start_f * SAMPLES_PER_FRAME
        end_sample = end_f * SAMPLES_PER_FRAME
        path = os.path.join(out_dir, "%s.wav" % seg_id)
        synth_segment(path, start_sample, end_sample, words)
        narration.append({
            "id": seg_id, "path": path,
            "start_frame": start_f, "end_frame_exclusive": end_f,
            "words": [{"index": i, "startSample": s, "endSample": e}
                      for i, (s, e) in enumerate(words)],
        })

    gen_dir = os.path.join(out_dir, "generated")
    subprocess.run(
        [sys.executable, os.path.join(scripts, "synth-score.py"),
         "--bpm", "120", "--duration", "48.0", "--seed", "7",
         "--outdir", gen_dir], check=True, capture_output=True)
    music_path = os.path.join(out_dir, "music.wav")
    os.replace(os.path.join(gen_dir, "score.wav"), music_path)

    spec = {
        "canvas": {"width": 1920, "height": 1080},
        "synthetic_segments": True,
        "scenes": [
            {"id": "host-a", "path": os.path.join(out_dir, "host-a.mp4"),
             "duration_frames": 900, "engine": "fixture-host"},
            {"id": "bar-01", "use_return_artifact": True},
            {"id": "host-b", "path": os.path.join(out_dir, "host-b.mp4"),
             "duration_frames": 360, "engine": "fixture-host"},
        ],
        "narration": narration,
        "captions": [
            {"id": "cap-intro", "start_frame": 0, "end_frame_exclusive": 900},
            {"id": "cap-cue", "start_frame": 900,
             "end_frame_exclusive": 1080},
            {"id": "cap-outro", "start_frame": 1080,
             "end_frame_exclusive": 1440},
        ],
        "music": {"path": music_path},
        "mix": {"musicVolume": 0.5, "ducking": None},
        "loudness_target": {"integratedLufs": -14.0, "truePeakDb": -1.0},
    }
    with open(os.path.join(out_dir, "media-spec.json"), "w") as f:
        json.dump(spec, f, indent=2)
        f.write("\n")
    print(os.path.join(out_dir, "media-spec.json"))


if __name__ == "__main__":
    main()
