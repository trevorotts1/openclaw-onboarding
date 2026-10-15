#!/usr/bin/env python3
"""MG-022 acceptance renders and inspection.

Renders every acceptance example with the repaired assemble.py (real
ffmpeg 8.1.2), then inspects each output independently of the
assembler's own probe: frame count via a second ffprobe count, stream
map, last frame hash (from the assembler probe record), and audio
segment presence by Goertzel band energy on the decoded output.

Segment presence is a tone-presence proof: narration fixtures are
distinct-frequency sine segments, so "the final narration segment is
present at full planned length" is checked as band energy in the
final 0.25s window and across the segment's span. It is NOT a speech
intelligibility check and does not claim to be one.

Rendered outputs land in tests/evidence/mg022/outputs/ (not committed;
only the records are). Records land in tests/evidence/mg022/acceptance/.

Usage: python3 verify_acceptance.py
"""

import json
import math
import os
import struct
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FIXTURES = os.path.join(SKILL, "tests", "fixtures", "assembly")
OUT_DIR = os.path.join(HERE, "outputs")
REC_DIR = os.path.join(HERE, "acceptance")
RATE = 48000
EXAMPLES = ["single", "multi", "noaudio", "narration", "musicsfx", "mixed"]


def goertzel(samples, rate, freq):
    n = len(samples)
    if n == 0:
        return 0.0
    k = 2 * math.pi * freq / rate
    coeff = 2 * math.cos(k)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff * s1 - s2
        s2, s1 = s1, s0
    return math.sqrt(s1 * s1 + s2 * s2 - coeff * s1 * s2) / n


def decode(path):
    wav = path + ".wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path,
                    "-ac", "1", "-ar", str(RATE), wav],
                   check=True, capture_output=True)
    w = wave.open(wav)
    raw = w.readframes(w.getnframes())
    return list(struct.unpack("<%dh" % (len(raw) // 2), raw))


def band(samples, freq, t0, t1):
    a, b = int(t0 * RATE), min(int(t1 * RATE), len(samples))
    return goertzel(samples[a:b], RATE, freq)


def count_frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames",
                          "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", path],
                         check=True, capture_output=True, text=True).stdout
    return int(out.strip())


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("command failed: %s\n%s" % (" ".join(cmd), r.stderr[-1500:]))
    return r


def plan_record(example, work_root):
    media_dir = os.path.join(work_root, example, "media")
    workdir = os.path.join(work_root, example, "work")
    out_path = os.path.join(OUT_DIR, example + ".mp4")
    run([sys.executable, os.path.join(FIXTURES, "make_media.py"), example, media_dir])
    run([sys.executable, os.path.join(SKILL, "scripts", "assemble.py"),
         "--plan", os.path.join(FIXTURES, "plans", example + ".json"),
         "--media", os.path.join(media_dir, "media.json"),
         "--out", out_path, "--workdir", workdir])
    probe = json.load(open(os.path.join(workdir, "assemble-probe.json")))
    plan = json.load(open(os.path.join(FIXTURES, "plans", example + ".json")))
    sidecar = plan["sidecar"]
    spec = json.load(open(os.path.join(FIXTURES, "specs", example + ".json")))
    record = {
        "example": example,
        "mode": "plan",
        "output": os.path.relpath(out_path, SKILL),
        "expected_frames": sidecar["total_frames"],
        "probe_frames": probe["decoded_frames"],
        "recount_frames": count_frames(out_path),
        "duration_seconds": probe["duration_seconds"],
        "expected_duration_seconds": sidecar["total_frames"] / sidecar["fps"],
        "stream_map": probe["stream_map"],
        "last_frame_sha256": probe["last_frame_sha256"],
        "inputs": [(i["kind"], i["id"], i["index"]) for i in probe["inputs"]],
        "media_provenance": probe.get("media_provenance"),
        "narration_segment_presence": [],
    }
    samples = decode(out_path) if probe["audio_present"] else None
    tones = {n["id"]: n["toneHz"] for n in spec["narration"]}
    for seg in sidecar["narration"]:
        t0 = seg["startSample"] / RATE
        t1 = seg["endSampleExclusive"] / RATE
        freq = tones[seg["id"]]
        mid = band(samples, freq, t0 + 0.1, t1 - 0.1 if t1 - t0 > 0.3 else t1)
        tail = band(samples, freq, t1 - 0.25, t1 - 0.02)
        record["narration_segment_presence"].append({
            "id": seg["id"], "toneHz": freq,
            "planned_window_seconds": [round(t0, 3), round(t1, 3)],
            "mid_segment_band_amplitude": round(mid, 1),
            "final_quarter_band_amplitude": round(tail, 1),
            "present_mid": mid > 500, "present_at_planned_end": tail > 500,
            "proof_kind": "tone segment presence, not speech intelligibility",
        })
    if example == "musicsfx":
        # Ducking: music 220 Hz energy before narration (0.25-0.45s)
        # vs under narration (1.0-1.5s). Music sits at volume 0.9
        # unducked; the sidechain must pull it down under speech.
        before = band(samples, 220, 0.25, 0.45)
        during = band(samples, 220, 1.0, 1.5)
        record["ducking_check"] = {
            "music_220hz_before_narration": round(before, 1),
            "music_220hz_during_narration": round(during, 1),
            "ducked": during < 0.75 * before,
        }
        record["sfx_presence"] = [
            {"id": "x1", "toneHz": 1170,
             "amplitude_at_1.0s": round(band(samples, 1170, 1.0, 1.2), 1)},
            {"id": "x2", "toneHz": 1560,
             "amplitude_at_4.0s": round(band(samples, 1560, 4.0, 4.2), 1)},
        ]
    return record


def legacy_record(work_root):
    """The pre-V2 path through assemble.sh: two segments, a voiceover,
    a synthesized score, and one pop event placed by the bridge on the
    compiled (faded) timeline."""
    wd = os.path.join(work_root, "legacy", "work")
    ff = ["ffmpeg", "-v", "error", "-y"]
    for sid, color in (("intro", "red"), ("outro", "blue")):
        d = os.path.join(wd, "scenes", sid)
        os.makedirs(d, exist_ok=True)
        run(ff + ["-f", "lavfi", "-i",
                  "color=c=%s:s=640x360:r=30" % color,
                  "-frames:v", "45", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                  os.path.join(d, sid + ".mp4")])
    # 2.4s: fits the 2.5s compiled picture (two 1.5s segments minus
    # the 0.5s fade). A longer voiceover is refused, by design.
    run(ff + ["-f", "lavfi", "-i", "sine=frequency=440:duration=2.4",
              "-ar", "48000", os.path.join(wd, "vo.wav")])
    manifest = {"scenes": [{"id": "intro"},
                           {"id": "outro", "sfx_events": [
                               {"sound": "pop", "at_seconds": 0.5}]}],
                "music_bpm": 120, "music_seed": 7}
    mpath = os.path.join(wd, "manifest.json")
    json.dump(manifest, open(mpath, "w"))
    out_path = os.path.join(OUT_DIR, "legacy.mp4")
    run(["bash", os.path.join(SKILL, "scripts", "assemble.sh"),
         "--manifest", mpath, "--workdir", wd,
         "--voiceover", os.path.join(wd, "vo.wav"), "--out", out_path])
    probe = json.load(open(os.path.join(wd, "assemble-probe.json")))
    samples = decode(out_path)
    # The pop lands at outro placed start (frame 30, after the 0.5s
    # fade) + 0.5s = 1.5s. The old script placed it at 2.0s.
    return {
        "example": "legacy",
        "mode": "legacy",
        "output": os.path.relpath(out_path, SKILL),
        "expected_frames": probe["expected_frames"],
        "probe_frames": probe["decoded_frames"],
        "recount_frames": count_frames(out_path),
        "duration_seconds": probe["duration_seconds"],
        "stream_map": probe["stream_map"],
        "last_frame_sha256": probe["last_frame_sha256"],
        "voiceover_440hz_at_0.25s": round(band(samples, 440, 0.25, 0.5), 1),
        "narrated_voice_present": band(samples, 440, 0.25, 0.5) > 500,
        "note": "music and SFX placement detail is in the probe inputs; "
                "the synthesized score is mixed (D-ASSEMBLE-MUSIC-RESET fix)",
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REC_DIR, exist_ok=True)
    work_root = os.path.join(HERE, "work")
    records = []
    for example in EXAMPLES:
        rec = plan_record(example, work_root)
        records.append(rec)
        print("%s: frames %d/%d recount=%d dur=%.3f audio=%s last=%s"
              % (example, rec["probe_frames"], rec["expected_frames"],
                 rec["recount_frames"], rec["duration_seconds"],
                 any(s["codec_type"] == "audio" for s in rec["stream_map"]),
                 rec["last_frame_sha256"][:12]))
        for seg in rec["narration_segment_presence"]:
            print("   narration %s (%d Hz): mid=%.0f end=%.0f present=%s/%s"
                  % (seg["id"], seg["toneHz"], seg["mid_segment_band_amplitude"],
                     seg["final_quarter_band_amplitude"],
                     seg["present_mid"], seg["present_at_planned_end"]))
    legacy = legacy_record(work_root)
    records.append(legacy)
    print("legacy: frames %d/%d recount=%d voice440=%.0f"
          % (legacy["probe_frames"], legacy["expected_frames"],
             legacy["recount_frames"], legacy["voiceover_440hz_at_0.25s"]))
    for rec in records:
        with open(os.path.join(REC_DIR, rec["example"] + "-record.json"), "w") as f:
            json.dump(rec, f, indent=2)
    with open(os.path.join(REC_DIR, "summary.json"), "w") as f:
        json.dump({"records": [r["example"] for r in records],
                   "all_frame_counts_exact": all(
                       r["probe_frames"] == r["expected_frames"] == r["recount_frames"]
                       for r in records)}, f, indent=2)
    print("records written to", REC_DIR)


if __name__ == "__main__":
    main()
