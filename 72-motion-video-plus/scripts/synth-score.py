#!/usr/bin/env python3
"""
Skill 72 synthesized score.

Writes an ORIGINAL royalty-free score in code: chord pads, a bass line, and
light percussion at a chosen BPM, with a seeded RNG so the same inputs always
produce the same WAV. Because we generate it, there is no licensing to clear
and we know the beat grid exactly (see scripts/beat-grid.py).

Layers (all synthesized from sine waves and filtered noise, nothing sampled):
  pad   : detuned triangle-ish chord tones, one chord per bar, slow attack
  bass  : root notes on eighth notes, soft sine
  kick  : beats 1-4, sine pitch drop 150 -> 45 Hz
  snare : beats 2 and 4, band-passed noise burst
  hat   : offbeats, high-passed noise tick

Usage:
  python3 scripts/synth-score.py --bpm 120 --duration 60 --seed 7 \
      --outdir work/audio
Writes work/audio/score.wav and work/audio/score-params.json.

The params file records bpm, beat times, and downbeats so beat-grid.py can
write beats.json without measuring anything.
"""
import argparse
import json
import math
import os

import numpy as np

SR = 44100


def note_freq(midi):
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def adsr(n, sr, attack, decay, sustain_level, release):
    """Simple attack/decay/sustain/release envelope over n samples."""
    a = int(attack * sr)
    d = int(decay * sr)
    r = int(release * sr)
    env = np.ones(n)
    if a > 0:
        env[:a] = np.linspace(0, 1, a)
    if d > 0 and a + d <= n:
        env[a:a + d] = np.linspace(1, sustain_level, d)
        env[a + d:n - r] = sustain_level
    if r > 0 and r < n:
        env[n - r:] = env[n - r] * np.linspace(1, 0, r)
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--duration", type=float, required=True,
                    help="score length in seconds")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--key", default="Am",
                    help="only Am is voiced in this version")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    os.makedirs(args.outdir, exist_ok=True)

    beat = 60.0 / args.bpm
    bar = beat * 4
    total = int(args.duration * SR)
    mix = np.zeros(total)

    # Chord progression: Am F C G, one chord per bar (MIDI note numbers).
    chords = [
        [57, 60, 64],  # Am: A3 C4 E4
        [53, 57, 60],  # F:  F3 A3 C4
        [55, 60, 64],  # C:  G3 C4 E4  (second inversion color)
        [55, 59, 62],  # G:  G3 B3 D4
    ]
    roots = [45, 41, 48, 43]  # A2, F2, C3, G2

    n_bars = max(1, int(math.ceil(args.duration / bar)))

    # --- pad: one chord per bar, detuned soft saws through a slow envelope ---
    for b in range(n_bars):
        chord = chords[b % len(chords)]
        start = int(b * bar * SR)
        length = int(bar * SR * 1.05)  # slight overlap into the next bar
        end = min(total, start + length)
        if start >= total:
            break
        n = end - start
        t = np.arange(n) / SR
        env = adsr(n, SR, attack=0.9, decay=0.4, sustain_level=0.7, release=0.8)
        layer = np.zeros(n)
        for midi in chord:
            f = note_freq(midi)
            # triangle-ish: fundamental + softened harmonics, slight detune
            for detune_cents, amp in ((0.0, 1.0), (6.0, 0.5), (-6.0, 0.5)):
                fd = f * (2.0 ** (detune_cents / 1200.0))
                wave = (np.sin(2 * np.pi * fd * t)
                        + 0.3 * np.sin(2 * np.pi * 2 * fd * t)
                        + 0.12 * np.sin(2 * np.pi * 3 * fd * t))
                layer += amp * wave
        layer = layer / (len(chord) * 2.0) * env
        mix[start:end] += layer * 0.5

    # --- bass: root eighth notes, soft sine ---
    for b in range(n_bars):
        root = roots[b % len(roots)]
        for eighth in range(8):
            start = int((b * bar + eighth * beat / 2) * SR)
            length = int(beat / 2 * SR * 0.95)
            end = min(total, start + length)
            if start >= total:
                break
            n = end - start
            t = np.arange(n) / SR
            f = note_freq(root)
            env = adsr(n, SR, attack=0.01, decay=0.05,
                       sustain_level=0.8, release=0.05)
            mix[start:end] += 0.30 * np.sin(2 * np.pi * f * t) * env

    # --- kick on beats, snare on 2 and 4, hats on offbeats ---
    n_beats = int(args.duration / beat)
    for i in range(n_beats):
        bt = i * beat
        # kick: pitch-dropping sine
        start = int(bt * SR)
        n = int(0.14 * SR)
        end = min(total, start + n)
        if start < total:
            t = np.arange(end - start) / SR
            freq = 45 + 105 * np.exp(-t * 30)
            phase = 2 * np.pi * np.cumsum(freq) / SR
            env = np.exp(-t * 28)
            mix[start:end] += 0.55 * np.sin(phase) * env
        # snare on beats 2 and 4
        if i % 4 in (1, 3):
            n2 = int(0.16 * SR)
            end2 = min(total, start + n2)
            if start < total:
                t2 = np.arange(end2 - start) / SR
                noise = rng.standard_normal(end2 - start)
                # crude band-pass around 1.8 kHz via difference of smooths
                smooth = np.convolve(noise, np.ones(24) / 24, mode="same")
                bp = noise - smooth
                env2 = np.exp(-t2 * 30)
                mix[start:end2] += 0.22 * bp * env2
        # hat on the offbeat
        hs = int((bt + beat / 2) * SR)
        nh = int(0.05 * SR)
        he = min(total, hs + nh)
        if hs < total:
            noise = rng.standard_normal(he - hs)
            smooth = np.convolve(noise, np.ones(96) / 96, mode="same")
            hp = noise - smooth
            envh = np.exp(-np.arange(he - hs) / SR * 160)
            mix[hs:he] += 0.10 * hp * envh

    # gentle master: soft clip then headroom for the later loudnorm pass
    mix = np.tanh(mix * 0.9)
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * 0.89  # -1 dBFS headroom

    pcm = (mix * 32767).astype(np.int16)
    wav_path = os.path.join(args.outdir, "score.wav")
    write_wav(wav_path, pcm)

    beat_times = [round(i * beat, 4) for i in range(n_beats + 1)
                  if i * beat <= args.duration]
    params = {
        "bpm": args.bpm,
        "seed": args.seed,
        "duration_seconds": args.duration,
        "key": args.key,
        "chords": ["Am", "F", "C", "G"],
        "beat_seconds": round(beat, 6),
        "beat_times": beat_times,
        "downbeat_times": [round(i * bar, 4) for i in range(n_bars + 1)
                           if i * bar <= args.duration],
        "score_wav": "score.wav",
    }
    with open(os.path.join(args.outdir, "score-params.json"), "w") as f:
        json.dump(params, f, indent=2)
    print("score: %s (%.1fs at %.0f BPM, seed %d)" %
          (wav_path, args.duration, args.bpm, args.seed))


def write_wav(path, pcm):
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
