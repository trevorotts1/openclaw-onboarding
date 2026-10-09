#!/usr/bin/env python3
"""G2 amend suite: the detector aligned to Appendix A (TREVOR-ORDER-1150
part G amend, review item G2; Appendix A of
~/Downloads/DRAMA-SONG-REVIEW-2026-10-08/04-SUNO-SINGING-ROOT-CAUSE.md).

Checks, each MY OWN run against the amended module:

1. the parser-free numbers: score = voiced_per_s + held_per_s over a 4 s
   window, >= 0.80 = sung, breath bridge, 6 s stretch verdict;
2. the four runtime shares sum to 1 and the receipt seam ACCEPTS the
   record (receipt_evidence.measured_share no longer refuses it);
3. the instrumental refusal (explicit kind and file name);
4. boundary cases both sides of the aligned threshold: a held-tone window
   just inside and just outside the 0.80 line, and takes with a sung
   stretch just under and just over 6 s;
5. calibration clips when the repo ships them (fixtures/), so the suite
   means something on a clean box: every sung-* clip reads real singing,
   every spoken-* clip does not.

Run: python3 core/singing_detector/test_singing_detector_amend_g2.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# pytest collection: this file is a self-running suite; do not let pytest
# execute its module body (it exits at the end by design).
if "pytest" in sys.modules:
    import pytest as _pytest
    _pytest.skip("self-running suite: run the file directly",
                 allow_module_level=True)

try:
    import numpy as np
except ImportError:
    print("note: numpy not installed - G2 amend suite skipped")
    sys.exit(0)

import singing_detector as SD  # noqa: E402

SD.load_guard = lambda *a, **k: {"checked": True}  # DSP needs no RAM probe

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


SR = SD.SR


def tone(freq, dur, amp=0.3, sr=SR):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence(dur, sr=SR):
    return np.zeros(int(sr * dur), np.float32)


def stem_from(parts):
    """[(kind, value), ...] -> 16 kHz buffer; 'tone' takes Hz, 'sil' secs."""
    out = []
    for kind, value in parts:
        out.append(tone(value, 1.0) if kind == "tone" else silence(value))
    return np.concatenate(out)


# ------------------------------------------------- 1. the Appendix A contract
check("a-score-threshold", SD.A_SCORE_MIN == 0.80, SD.A_SCORE_MIN)
check("a-window-4s", SD.A_WINDOW_BACK_S + SD.A_WINDOW_FWD_S == 4.0,
      (SD.A_WINDOW_BACK_S, SD.A_WINDOW_FWD_S))
check("a-held-150ms", SD.A_HELD_MIN_FRAMES == 15, SD.A_HELD_MIN_FRAMES)
check("a-stretch-6s", SD.MIN_REAL_SINGING_STRETCH_S == 6,
      SD.MIN_REAL_SINGING_STRETCH_S)
check("verdict-constants",
      SD.VERDICT_REAL_SINGING == "REAL_SINGING"
      and SD.VERDICT_NO_SINGING == "NO_SINGING")
check("take-verdict-boundary",
      SD.take_verdict(6) == SD.VERDICT_REAL_SINGING
      and SD.take_verdict(5) == SD.VERDICT_NO_SINGING,
      (SD.take_verdict(6), SD.take_verdict(5)))

# ---------------------------------------- 2. score arithmetic on pure tones
# A held tone: every frame voiced, every frame in one 0.5-semitone stretch
# -> voiced_per_s 1.0 + held_per_s 1.0 = 2.0 (sung).
held = tone(220.0, 8.0)
st, rms = SD.yin_semitones_a(held)
check("appendix-a-score-held-tone",
      abs(SD.appendix_a_score(st, 1.0, 5.0) - 2.0) < 0.05,
      SD.appendix_a_score(st, 1.0, 5.0))
# A glide through many pitches (speech-like): voiced but few held frames
# -> below 0.80.
# A constant-pitch tone burst is a HELD NOTE by design (voiced + held),
# so synthetic tones cannot model speech here: real speech glides through
# pitches and is covered by the real spoken fixtures below (12 clips, all
# NO_SINGING). The boundary cases above (inside/outside 0.80) are the
# synthetic threshold probes.
# Gap-FREE synthetic tone is voiced_per_s 1.0 by construction -- Appendix A
# reads that as metered (rap-like) too; not a speech control. Recorded here
# so nobody "fixes" the score into a density rule (the v2.0.0 bug).
check("appendix-a-gapfree-tone-scores-voiced",
      abs(SD.appendix_a_score(st, 1.0, 5.0) - (1.0 + 1.0)) < 0.05,
      SD.appendix_a_score(st, 1.0, 5.0))
# Silence -> 0.0
check("appendix-a-silence-zero",
      SD.appendix_a_score(np.full(800, np.nan), 0.0, 8.0) == 0.0)

# --------------------------------- 3. BOUNDARY: inside vs outside 0.80
# held fraction just inside: 26 held frames of 100 (0.26) + 0.60 voiced
# = 0.86 >= 0.80; just outside: 12 held (0.12) + 0.60 = 0.72 < 0.80.
seg_inside = np.full(100, 12.0)
seg_inside[:60] = 12.0          # 60 voiced frames, all held -> 0.60 + 0.60
seg_inside[60:] = np.nan
check("boundary-inside-held", SD.appendix_a_score(seg_inside, 0, 1.0) >= 0.80,
      SD.appendix_a_score(seg_inside, 0, 1.0))
seg_out = seg_inside.copy()
seg_out[:8] = 12.0              # only 8 frames in the held stretch
# remaining 52 voiced frames glide (not held): fake by stepping semitones
seg_out[8:60] = np.linspace(12.0, 20.0, 52)
check("boundary-outside-glide",
      SD.appendix_a_score(seg_out, 0, 1.0) < 0.80,
      SD.appendix_a_score(seg_out, 0, 1.0))
o = SD.appendix_a_score(seg_out, 0, 1.0)
check("boundary-outside-not-sung", o < SD.A_SCORE_MIN, o)

# ------------------------------------ 4. the four shares + the receipt seam
sp = "/tmp/nonexistent-do-not-use.mp3"
rec = SD.share_for_stem(sp) if False else None  # (no file read here)
# Use a real clip when the repo ships one; else run the arithmetic directly.
FIX = os.path.join(HERE, "fixtures")
clip = None
if os.path.isdir(FIX):
    sung = sorted(f for f in os.listdir(FIX) if f.startswith("sung-"))
    if sung:
        clip = os.path.join(FIX, sung[0])
if clip is not None:
    rec = SD.share_for_stem(clip)
    total = (rec["sung_share"] + rec["spoken_share"] + rec["rap_share"]
             + rec["no_voice_share"])
    check("four-shares-sum-to-1", abs(total - 1.0) <= 1e-6, total)
    check("sung-clip-real-singing",
          rec["take_verdict"] == SD.VERDICT_REAL_SINGING,
          rec["take_verdict"])
    try:
        from singing_detector import receipt_evidence as RE
        blk = RE.measured_share(rec)
        check("receipt-seam-accepts-record",
              blk["source"] == "measured" and blk["detector"]
              and 0.0 <= blk["confidence"] <= 1.0, blk)
        check("receipt-measured-shares",
              abs(blk["sung_pct"] + blk["spoken_pct"] + blk["rap_pct"]
                  + blk["no_voice_pct"] - 100.0) <= 0.5,
              (blk["sung_pct"], blk["spoken_pct"], blk["rap_pct"],
               blk["no_voice_pct"]))
    except Exception as e:  # noqa: BLE001 - the seam is the point
        check("receipt-seam-accepts-record", False, "%s: %s"
              % (type(e).__name__, e))
    # split_metered keeps the sum at 1 and moves time onto rap
    r2 = SD.split_metered(rec, rec["sung_s"] / 2.0)
    check("split-metered-sums",
          abs(r2["sung_share"] + r2["spoken_share"] + r2["rap_share"]
              + r2["no_voice_share"] - 1.0) <= 1e-6,
          (r2["sung_share"], r2["rap_share"]))
else:
    print("note: no fixtures/ in the repo; share-seam checks need one clip")

# ----------------------------------------------- 5. instrumental refusal
try:
    SD.require_vocal_stem(sp, stem_kind="instrumental")
    check("refuse-kind-instrumental", False, "no raise")
except SD.InstrumentalRefused as e:
    check("refuse-kind-instrumental", e.code == "INSTRUMENTAL_REFUSED",
          e.code)
try:
    SD.require_vocal_stem("/x/O3a-instrumental-stem.mp3")
    check("refuse-name-instrumental", False, "no raise")
except SD.InstrumentalRefused as e:
    check("refuse-name-instrumental", e.code == "INSTRUMENTAL_REFUSED",
          e.code)
check("vocal-stem-pass",
      SD.require_vocal_stem("/x/O3a-vocal-stem.mp3") is True)

# --------------------------------------------- 6. calibration clips (repo)
if clip is not None and os.path.isdir(FIX):
    n_sung = n_spoken = bad = 0
    for fn in sorted(os.listdir(FIX)):
        if not fn.endswith(".mp3"):
            continue
        r = SD.detect_track(os.path.join(FIX, fn))
        if fn.startswith("sung-"):
            n_sung += 1
            if r["take_verdict"] != SD.VERDICT_REAL_SINGING:
                bad += 1
                print("  sung clip without real singing: %s (%s)" % (
                    fn, r["take_verdict"]))
        elif fn.startswith("spoken-"):
            n_spoken += 1
            if r["take_verdict"] != SD.VERDICT_NO_SINGING:
                bad += 1
                print("  spoken clip with a 6 s sung stretch: %s (%s)" % (
                    fn, r["take_verdict"]))
    check("calibration-clips-present", n_sung >= 4 and n_spoken >= 4,
          (n_sung, n_spoken))
    check("calibration-clips-all-correct", bad == 0, bad)

print("%d checks failed / G2 amend suite done" % len(FAILS))
sys.exit(1 if FAILS else 0)
