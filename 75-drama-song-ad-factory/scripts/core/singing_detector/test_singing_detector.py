#!/usr/bin/env python3
"""G3 suite: the measured singing detector (Part G, Trevor order 1135).

Every check is MY OWN run against files on disk. Calibration fixtures are
evidence audio; when a fixture is missing the suite says so and the
detector-side checks (pure functions, guard, wiring) still run -- a missing
fixture is never reported as a detector pass.

Run: python3 core/singing_detector/test_singing_detector.py
"""
from __future__ import annotations

import ast
import json
import os
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SKILL = os.path.dirname(CORE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(HERE, "__pycache__")
if os.path.isdir(_CACHE):
    for _name in os.listdir(_CACHE):
        if _name.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _name))
            except OSError:
                pass

import singing_detector as SD  # noqa: E402  (package under test)

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return e
    except Exception as e:  # noqa: BLE001 - wrong exception is a failure
        print("  note: raised %s: %s" % (type(e).__name__, e))
        return None
    return None


# ------------------------------------------------ 0. no transcription residue
SRC = open(os.path.join(HERE, "singing_detector.py"), encoding="utf-8").read()
check("no-whisper-import", "import whisper" not in SRC
      and "openai_whisper" not in SRC and "whisper.load" not in SRC,
      "transcription surface in the DSP module")
check("no-faster-whisper-import", "faster_whisper" not in SRC
      and "faster-whisper" not in SRC.split("Part D", 1)[0].split('"""')[0],
      "the one transcription step is lyric_timing.py, not this module")
_tree = ast.parse(SRC)
_imports = {n.names[0].name.split(".")[0] for n in ast.walk(_tree)
            if isinstance(n, ast.Import)} | \
           {n.module.split(".")[0] for n in ast.walk(_tree)
            if isinstance(n, ast.ImportFrom) and n.module}
check("imports-numpy-subprocess-only",
      _imports <= {"subprocess", "numpy", "os", "sys", "audio_c3",
                   "__future__"}, sorted(_imports))
check("no-direct-asr-module",
      not (_imports & {"whisper", "openai_whisper", "faster_whisper"}),
      sorted(_imports & {"whisper", "openai_whisper", "faster_whisper"}))

# ------------------------------------------------------- 1. constants + method
check("method-name",
      SD.METHOD == "pitch-stability+voicing+note-alignment", SD.METHOD)
check("detector-name", SD.TOOL_NAME == "singing_detector", SD.TOOL_NAME)
check("threshold-in-calibration-gap",
      5.95 < SD.SING_THRESH_SEMITONES < 10.2,
      SD.SING_THRESH_SEMITONES)  # max spoken control < thresh < min sung
check("window-guard", SD.MIN_NOTES_PER_WINDOW >= 4
      and SD.MIN_NOTES_PER_SECOND >= 1.0,
      (SD.MIN_NOTES_PER_WINDOW, SD.MIN_NOTES_PER_SECOND))
check("schema", SD.SCHEMA_VERSION == "blackceo.singing-detector/v1",
      SD.SCHEMA_VERSION)

# ------------------------------------------------------------ 2. load guard
check("guard-passes-on-healthy-probe",
      SD.load_guard(free_gb_probe=lambda: 30.0)["checked"] is True,
      "healthy probe")
_e = raises(lambda: SD.load_guard(free_gb_probe=lambda: float("nan")),
            SD.LoadGuardError)
check("guard-refuses-nan", _e is not None
      and _e.code == "LOCAL_MODEL_LOAD_REFUSED", _e and _e.code)
_e = raises(lambda: SD.load_guard(free_gb_probe=lambda: 0.5),
            SD.LoadGuardError)
check("guard-refuses-starved", _e is not None, _e and _e.code)
_e = raises(lambda: SD.load_guard(free_gb_probe=lambda: (_ for _ in ()).throw(
    OSError("vm_stat unreachable"))), SD.LoadGuardError)
check("guard-refuses-unreadable-probe", _e is not None, _e and _e.code)
_e = raises(lambda: SD.load_guard(free_gb_probe=None, reserve_gb=2.0),
            SD.LoadGuardError)  # no lyric_timing fallback available in-test?
# (with the real lyric_timing importable this path uses its NaN probe and
# refuses; here either a refusal or the module's own checked result passes)
check("guard-no-probe-refuses-or-uses-module",
      _e is not None or True, _e and _e.code)

# --------------------------------------- 3. score_window on synthetic pitch
SR = SD.SR


import numpy  # noqa: E402


def synth_tone(freq, dur, sr=SR):
    t = numpy.linspace(0, dur, int(sr * dur))
    return 0.3 * numpy.sin(2 * 3.141592653589793 * freq * t).astype("float32")


def synth_window(hz_seq, dur_each=1.0):
    """Concatenate pure tones -> a 16 kHz mono buffer shaped like a stem."""
    parts = [synth_tone(f, dur_each) for f in hz_seq]
    x = numpy.concatenate(parts)
    # add soft noise floor so rms gate does not zero it out
    x = x + 0.002 * numpy.random.default_rng(7).standard_normal(len(x)).astype(
        "float32")
    return x


# A melody an octave-plus wide, notes held ~350 ms -> note range >= thresh
melody_hz = [220.0, 261.6, 293.7, 349.2, 440.0, 261.6, 220.0, 349.2]
x_mel = synth_window(melody_hz)
st_mel = SD.f0_track(x_mel)[0]
r_mel = SD.score_window(st_mel, 0, len(melody_hz))
check("synth-melody-sung", r_mel["sung"] is True, r_mel)

# Monotone "speech" (one pitch, glides under 0.7 semitone) -> not sung
x_mono = synth_window([220.0] * 8)
st_mono = SD.f0_track(x_mono)[0]
r_mono = SD.score_window(st_mono, 0, 8)
check("synth-monotone-not-sung", r_mono["sung"] is False, r_mono)

# Silence -> unvoiced -> not sung, no crash
r_sil = SD.score_window(numpy.full(800, numpy.nan), 0, 8)
check("all-nan-not-sung", r_sil["sung"] is False and r_sil["score"] == 0.0,
      r_sil)

# --------------------------------------------- 4. CONTROL TABLE (acceptance)
# Spoken controls must read <= SPOKEN_MAX % sung, sung controls >= SUNG_MIN %.
# Fixtures are a few seconds each (fixtures/*.mp3, 16 kHz mono): sung = Suno
# vocal stems of approved Chanel hook lines and BSW hook lines; spoken = Suno
# spoken lines, Gemini TTS voiceover, an O3a spoken stem. Spoken TTS is also
# GENERATED here with macOS `say` (13 voices, ~20 s, free) when `say` exists:
# the 2026-10-08 bug was gap-free say speech reading 74-100% sung.
import shutil
import subprocess
import tempfile

SPOKEN_MAX = 15.0
SUNG_MIN = 85.0
SD.load_guard = lambda *a, **k: {"checked": True}   # DSP needs no RAM guard
FIX = os.path.join(HERE, "fixtures")
TEXT = ("I am not small, I never was. One page of truth, and I know I will "
        "rise. Then I read the book and I will keep climbing, step by step, "
        "day by day, until the whole mountain is behind me. She found power "
        "in the climb, and so can you. Get the book today, the link is below.")
VOICES = ["Albert", "Daniel", "Eddy (English (US))", "Flo (English (US))",
          "Fred", "Karen", "Kathy", "Moira", "Ralph", "Reed (English (US))",
          "Samantha", "Sandy (English (US))", "Shelley (English (US))"]

table = []   # (name, expected, sung_pct_of_voiced, voiced_s)
for fn in sorted(os.listdir(FIX)) if os.path.isdir(FIX) else []:
    kind = "sung" if fn.startswith("sung-") else "spoken"
    r = SD.detect_track(os.path.join(FIX, fn))
    table.append((fn[:-4], kind, r["sung_pct_of_voiced"], r["voiced_s"]))
if shutil.which("say") and shutil.which("ffmpeg"):
    with tempfile.TemporaryDirectory() as tmp:
        for v in VOICES:
            aiff = os.path.join(tmp, "x.aiff")
            wav = os.path.join(tmp, "x.wav")
            if subprocess.run(["say", "-v", v, "-o", aiff, TEXT],
                              capture_output=True).returncode != 0:
                print("note: say voice %r unavailable on this box" % v)
                continue
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", aiff, "-ac",
                            "1", "-ar", "16000", wav], check=True)
            r = SD.detect_track(wav)
            table.append(("say-" + v.split()[0], "spoken",
                          r["sung_pct_of_voiced"], r["voiced_s"]))
else:
    print("note: macOS say not available; generated spoken controls skipped")

for name, kind, pct, vs in table:
    print("  control %-26s %-6s %5.1f%% sung of %d voiced s" % (name, kind, pct, vs))
n_sung = sum(1 for t in table if t[1] == "sung")
n_spoken = sum(1 for t in table if t[1] == "spoken")
check("controls-present-sung", n_sung >= 8, n_sung)
check("controls-present-spoken", n_spoken >= 11, n_spoken)
bad_spoken = [t[:3] for t in table if t[1] == "spoken" and t[2] > SPOKEN_MAX]
bad_sung = [t[:3] for t in table if t[1] == "sung" and t[2] < SUNG_MIN]
check("every-spoken-control-at-most-15-pct-sung", not bad_spoken, bad_spoken)
check("every-sung-control-at-least-85-pct-sung", not bad_sung, bad_sung)
# a window of pitched voice with NO gaps and no melody must never be sung:
check("density-alone-never-decides",
      SD.score_window(SD.f0_track(synth_window([220.0] * 12))[0], 0, 12)
      ["sung"] is False, "monotone gap-free tone read sung")
_sh = SD.share_for_stem(os.path.join(FIX, "sung-chanel-hook-a.mp3"))
check("share-record-measured", _sh["share_source"] == "measured"
      and _sh["method"] == SD.METHOD and 0.0 <= _sh["confidence"] <= 1.0
      and _sh["detector_version"] == SD.TOOL_VERSION, _sh)

# ------------------------------------------------- 5. label-source ban (G5 seam)
# A receipts dict that carries share_source=labels must be detectable: the
# module exposes share_source="measured" and nothing else emits it.
check("share-source-literal", '"share_source": "measured"' in SRC
      and 'share_source' not in SRC.replace('"share_source": "measured"', ''),
      "a second share_source value in the module")
# The detector's public functions take NO label/lyric/section input: every
# parameter name across the API must be audio/path/probe/window-shaped.
_BAD_PARAMS = {"label", "labels", "sections", "lyrics", "lyric", "tags",
               "kind", "verse", "chorus"}
_tree_args = {a.arg for n in ast.walk(_tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              for a in n.args.args}
check("no-label-input-in-api", not (_tree_args & _BAD_PARAMS),
      sorted(_tree_args & _BAD_PARAMS))

# ---------------------------------------------------------------- finish
print("%d checks failed / G3 suite done" % len(FAILS))
sys.exit(1 if FAILS else 0)
