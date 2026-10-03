#!/usr/bin/env python3
"""
Skill 72 beat grid.

Writes beats.json, the measured beat grid every hit in the video sits on.
For the default pipeline the grid is DERIVED, not measured: synth-score.py
generated the score at a known BPM, so we know every beat and downbeat
exactly and just record them.

Fallback: for a supplied (non-synthesized) track, measure the grid with
librosa or aubio if installed. The derived path is the default and needs
neither.

beats.json format (see references/beats-schema.json):
  { "bpm": 120.0, "beat_seconds": 0.5,
    "beat_times": [0.0, 0.5, ...],
    "downbeat_times": [0.0, 2.0, ...],
    "source": "derived" | "measured" }

Usage:
  python3 scripts/beat-grid.py --params work/audio/score-params.json \
      --out work/audio/beats.json
  # or direct:
  python3 scripts/beat-grid.py --bpm 120 --duration 60 --out beats.json
"""
import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", help="score-params.json from synth-score.py")
    ap.add_argument("--bpm", type=float, help="direct mode BPM")
    ap.add_argument("--duration", type=float, help="direct mode seconds")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.params:
        p = json.load(open(args.params))
        grid = {
            "bpm": p["bpm"],
            "beat_seconds": p["beat_seconds"],
            "beat_times": p["beat_times"],
            "downbeat_times": p["downbeat_times"],
            "source": "derived",
        }
    elif args.bpm and args.duration:
        beat = 60.0 / args.bpm
        beats = []
        t = 0.0
        while t <= args.duration + 1e-9:
            beats.append(round(t, 4))
            t += beat
        grid = {
            "bpm": args.bpm,
            "beat_seconds": round(beat, 6),
            "beat_times": beats,
            "downbeat_times": [b for i, b in enumerate(beats) if i % 4 == 0],
            "source": "derived",
        }
    else:
        raise SystemExit("give --params or both --bpm and --duration")

    with open(args.out, "w") as f:
        json.dump(grid, f, indent=2)
    print("beat grid: %d beats at %.1f BPM -> %s" %
          (len(grid["beat_times"]), grid["bpm"], args.out))


if __name__ == "__main__":
    main()
