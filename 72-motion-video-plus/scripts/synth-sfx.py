#!/usr/bin/env python3
"""
Skill 72 synthesized UI sounds.

Writes ORIGINAL interface sounds in code, seeded for reproducibility, so the
video needs no stock SFX library and nothing licensed:

  pop.wav    short sine blip with a downward pitch snap (selections, toggles)
  click.wav  2 ms filtered tick (buttons, small confirmations)
  whoosh.wav rising filtered-noise sweep, 0.45 s (transitions, reveals)
  thump.wav  low sine drop 110 -> 40 Hz, 0.28 s (landings, logo hits)

All mono 44.1 kHz 16-bit WAV. Royalty-free by construction.

Usage:
  python3 scripts/synth-sfx.py --seed 7 --outdir work/audio/sfx
"""
import argparse
import os
import wave

import numpy as np

SR = 44100


def write_wav(path, samples):
    samples = np.tanh(samples * 0.9)
    peak = np.max(np.abs(samples))
    if peak > 0:
        samples = samples / peak * 0.89
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def make_pop(rng):
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    freq = 900 * np.exp(-t * 40) + 320
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t * 36)


def make_click(rng):
    n = int(0.03 * SR)
    noise = rng.standard_normal(n)
    smooth = np.convolve(noise, np.ones(8) / 8, mode="same")
    tick = noise - smooth * 0.5
    return tick * np.exp(-np.arange(n) / SR * 400)


def make_whoosh(rng):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    # rising sweep: progressively less smoothing = brighter over time
    width = np.linspace(400, 12, n).astype(int)
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        w = width[i]
        alpha = 2.0 / (w + 1)
        acc = acc + alpha * (noise[i] - acc)
        out[i] = noise[i] - acc
    env = np.sin(np.pi * t / 0.45) ** 2  # swell in the middle
    return out * env * 2.0


def make_thump(rng):
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    freq = 40 + 70 * np.exp(-t * 22)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * np.exp(-t * 16)
    noise = rng.standard_normal(n)
    smooth = np.convolve(noise, np.ones(64) / 64, mode="same")
    click = (noise - smooth) * np.exp(-t * 90) * 0.4
    return body + click


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    os.makedirs(args.outdir, exist_ok=True)

    sounds = {
        "pop": make_pop(rng),
        "click": make_click(rng),
        "whoosh": make_whoosh(rng),
        "thump": make_thump(rng),
    }
    for name, samples in sounds.items():
        p = os.path.join(args.outdir, name + ".wav")
        write_wav(p, samples)
        print("sfx: %s" % p)


if __name__ == "__main__":
    main()
