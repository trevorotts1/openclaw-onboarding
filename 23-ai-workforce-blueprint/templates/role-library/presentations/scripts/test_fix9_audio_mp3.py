#!/usr/bin/env python3
"""
test_fix9_audio_mp3.py — FIX-9 (T-10) QC gate: speaker audio MP3 via Fish-Audio TTS.

THE REQUIREMENT (GAUNTLET LOOP T-10 / QC row FIX-9):
  Produce `audio_mp3` from a real `speech_md` by calling the Fish-Audio TTS API.
  QC gate: audio_mp3 EXISTS, is a VALID MP3 > 10 KB, decodable (parseable
  header/frame). Evidence: file size + audio-format probe (afinfo / python header
  parse). Pre-push: regenerate one MP3 through the merged producer; verify header
  + size.

THE GATE (this file, hermetic — no live Fish call required):
  1. MODEL TRUTH: the producer's default Fish model is `s2.1-pro` (the current
     PAID production model per 30-fish-audio-api-reference) — never the interim
     `s2-pro`, never the client-prohibited free `s2.1-pro-free`. The manifest
     P9-DELIVER executor invokes scripts/synthesize_full_speech.py for the
     audio_mp3 deliverable.
  2. PRODUCER WIRING: PIPELINE-MANIFEST P9-DELIVER's executor.cmd names
     scripts/synthesize_full_speech.py and writes the canonical PRESENTER-AUDIO.mp3
     (the `audio_mp3` bundle key) into working/delivery/.
  3. MP3 VALIDITY PROBE (verify_mp3): a REAL MP3 (ID3v2 header + MPEG frame sync)
     PASSES; garbage/text/missing/undersized files FAIL with a reason — this is the
     exact probe the producer runs on every chunk and the final deliverable.
  4. FIX-9 QC ROW: the probe enforces the > 10 KB floor and a parseable
     header/frame, i.e. `audio_mp3 exists, valid MP3 > 10KB, decodable`.

No network and no Fish key are used: the probe is exercised against fixtures. The
live Fish synthesis itself is the operator's runtime test (FISH_AUDIO_API_KEY /
FISH_AUDIO_VOICE_ID come from the env stores; this file never reads or prints them).

Run:  python3 test_fix9_audio_mp3.py
Exit: 0 = all assertions passed; 1 = a case failed.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------------------
# Import the producer module WITHOUT running main() (import-guarded).
# ---------------------------------------------------------------------------
import importlib.util  # noqa: E402

_PROD_SPEC = importlib.util.spec_from_file_location(
    "synthesize_full_speech", HERE / "synthesize_full_speech.py")
_prod = importlib.util.module_from_spec(_PROD_SPEC)
_PROD_SPEC.loader.exec_module(_prod)


def _manifest() -> dict:
    """Resolve PIPELINE-MANIFEST.json (walk up from scripts/)."""
    cur = HERE
    for _ in range(10):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return json.loads(cand.read_text())
        cur = cur.parent
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found by walking up from scripts/")


def _make_real_mp3(path: Path, seconds: int = 3) -> Path:
    """Generate a real, decodable MP3 with ffmpeg (ID3v2 + MPEG frames)."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:a", "libmp3lame", "-b:a", "128k", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return path


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
def test_model_truth() -> list:
    """The producer must default to the current PAID production model s2.1-pro,
    and never default to the interim s2-pro or the client-prohibited free tier."""
    fails = []
    # Default from the argparse definition.
    default_model = _prod.MAIN_MODEL_DEFAULT if hasattr(_prod, "MAIN_MODEL_DEFAULT") else None
    if default_model is None:
        fails.append("MODEL-TRUTH: no documented default-model constant")
    else:
        if default_model != "s2.1-pro":
            fails.append(f"MODEL-TRUTH: default model is {default_model!r}, expected 's2.1-pro'")
        if default_model in ("s2-pro", "s2.1-pro-free"):
            fails.append(f"MODEL-TRUTH: default model {default_model!r} is a superseded/"
                         f"prohibited tier (s2-pro interim / s2.1-pro-free)")
    # Model must never be selected from the request body; the producer sends it as
    # the HTTP `model` header in synth_chunk.
    src = (HERE / "synthesize_full_speech.py").read_text()
    if '"model": model' not in src:
        fails.append("MODEL-TRUTH: producer does not send the model as the HTTP header "
                     "('\"model\": model' header arg missing in synth_chunk)")
    print(f"MODEL-TRUTH lockstep            -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_producer_wiring() -> list:
    """The manifest P9-DELIVER phase must wire synthesize_full_speech.py to produce
    the canonical PRESENTER-AUDIO.mp3 (audio_mp3) in working/delivery/."""
    fails = []
    man = _manifest()
    phases = {p.get("id"): p for p in man.get("phases", [])}
    p9 = phases.get("P9-DELIVER")
    if p9 is None:
        fails.append("WIRING: P9-DELIVER phase missing from the manifest")
        print(f"PRODUCER-WIRING lockstep        -> {'PASS' if not fails else 'FAIL'}")
        return fails
    ex = (p9.get("executor") or {})
    cmd = ex.get("cmd", "")
    if ex.get("kind") != "script":
        fails.append("WIRING: P9-DELIVER executor kind is not 'script'")
    if "synthesize_full_speech.py" not in cmd:
        fails.append("WIRING: P9-DELIVER executor does not name synthesize_full_speech.py")
    if "PRESENTER-AUDIO.mp3" not in cmd:
        fails.append("WIRING: P9-DELIVER executor does not produce PRESENTER-AUDIO.mp3")
    if "PRESENTERS-SPEECH.md" not in cmd:
        fails.append("WIRING: P9-DELIVER executor does not read PRESENTERS-SPEECH.md")
    # audio_mp3 must be one of the nine build-bundle files.
    bb = man.get("build_bundle_files", [])
    if "audio_mp3" not in bb:
        fails.append("WIRING: 'audio_mp3' missing from manifest build_bundle_files")
    # The producer script must exist next to the runner.
    if not (HERE / "synthesize_full_speech.py").is_file():
        fails.append("WIRING: synthesize_full_speech.py missing beside the runner")
    print(f"PRODUCER-WIRING lockstep        -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_verify_mp3_probe() -> list:
    """verify_mp3: real MP3 PASSES; garbage/text/missing/undersized FAIL. This is
    the exact probe the producer runs per-chunk and on the final deliverable."""
    fails = []
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)

        # Positive control: a real, decodable MP3 (> 10 KB, ID3 + frames).
        real = _make_real_mp3(base / "real.mp3")
        r = _prod.verify_mp3(str(real))
        if r != "":
            fails.append(f"PROBE positive: real MP3 must PASS, got FAIL: {r}")
        if real.stat().st_size <= _prod.MP3_MIN_BYTES:
            fails.append(f"PROBE fixture: real.mp3 is {real.stat().st_size} bytes, expected "
                         f"> {_prod.MP3_MIN_BYTES} to exercise the size gate")

        # Negative: garbage bytes named .mp3.
        g = base / "garbage.mp3"
        g.write_bytes(b"\x00\x01\x02\x03" * 5000)
        r = _prod.verify_mp3(str(g))
        if r == "":
            fails.append("PROBE negative: garbage bytes must FAIL, got PASS")

        # Negative: plain text.
        txt = base / "not-audio.txt"
        txt.write_bytes(b"this is definitely not mp3 audio data" * 2000)
        r = _prod.verify_mp3(str(txt))
        if r == "":
            fails.append("PROBE negative: plain text must FAIL, got PASS")

        # Negative: real ID3 header but under the 10 KB size floor.
        tiny = base / "tiny.mp3"
        tiny.write_bytes(b"ID3\x03\x00" + (b"\x00" * 8) + (b"x" * 500))
        r = _prod.verify_mp3(str(tiny))
        if r == "" or "too small" not in r:
            fails.append(f"PROBE negative: tiny ID3 file must FAIL the size floor, got {r!r}")

        # Negative: missing file.
        r = _prod.verify_mp3(str(base / "missing.mp3"))
        if r == "" or "missing" not in r:
            fails.append(f"PROBE negative: missing file must FAIL, got {r!r}")
    print(f"MP3-VALIDITY-PROBE             -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_af_probe_aligns_with_ffprobe() -> list:
    """The python probe and ffprobe agree the real fixture is decodable audio
    (afinfo-equivalent cross-check, no shell grep)."""
    fails = []
    with tempfile.TemporaryDirectory() as t:
        real = _make_real_mp3(Path(t) / "real.mp3")
        if _prod.verify_mp3(str(real)) != "":
            fails.append("CROSS-CHECK: verify_mp3 failed on a real ffmpeg MP3")
            print(f"CROSS-CHECK (ffprobe agree)    -> {'PASS' if not fails else 'FAIL'}")
            return fails
        try:
            dur = _prod.ffprobe_duration(str(real))
            if dur <= 0:
                fails.append(f"CROSS-CHECK: ffprobe returned non-positive duration {dur}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"CROSS-CHECK: ffprobe could not read the fixture ({exc!r})")
    print(f"CROSS-CHECK (ffprobe agree)    -> {'PASS' if not fails else 'FAIL'}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description="FIX-9 / T-10 audio MP3 QC gate")
    ap.add_argument("--list-only", action="store_true",
                    help="print the case list and exit 0 (no assertions)")
    args = ap.parse_args()

    cases = [test_model_truth, test_producer_wiring, test_verify_mp3_probe,
             test_af_probe_aligns_with_ffprobe]
    if args.list_only:
        for c in cases:
            print(c.__name__)
        return 0

    all_fails = []
    for case in cases:
        all_fails.extend(case())

    if all_fails:
        print("test_fix9_audio_mp3 -> FAIL")
        for f in all_fails:
            print("  -", f)
        return 1
    print("test_fix9_audio_mp3 -> PASS "
          "(model-truth / producer-wiring / mp3-probe / ffprobe-cross-check)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
