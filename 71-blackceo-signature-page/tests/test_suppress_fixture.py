#!/usr/bin/env python3
"""Mandatory Item 29 fixture: the monochrome SUPPRESS pixel case.

A correct low-saturation image (real structure, near-zero chroma) must
PASS the deterministic grade screen when the run's Page Visual Bible
blend profile marks hero_color_chroma SUPPRESS (Amendment 6, Part B4:
the color floors are N/A for that image), and the SAME image under a
FULL profile (or no bible at all) must be flagged by the saturation
floor. Same bytes, same calibrated fixture brand; only the blend
profile changes, so the pair isolates the B4 handling.

Fixtures are synthetic and test-only: the brand thresholds here are
fixture values in a tmpdir, never the skill's brand file (whose real
thresholds stay null until the owner calibrates them, Item 8).
"""
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PY = sys.executable

FULL = {"min_mean_saturation": 0.1, "min_luma_std": 5,
        "min_sharpness": 10, "min_colorfulness": 5}


def run(args, expect=None):
    proc = subprocess.run([str(a) for a in args], text=True, capture_output=True)
    if expect is not None and proc.returncode != expect:
        print("COMMAND:", " ".join(str(x) for x in args))
        print("STDOUT:\n", proc.stdout)
        print("STDERR:\n", proc.stderr)
        raise AssertionError(f"Expected return code {expect}, got {proc.returncode}")
    return proc


def monochrome(path, w=160, h=90, seed=11):
    """Structured grayscale image: a horizontal gradient with noise.

    Saturation and colorfulness are ~0 by construction; luma variance
    and edge content are high, so only the color floors can fail it.
    """
    from PIL import Image
    rng = random.Random(seed)
    im = Image.new("L", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            base = int(40 + 180 * (x / max(1, w - 1)))
            px[x, y] = max(0, min(255, base + rng.randrange(-25, 26)))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(path)


def bible(td, mode):
    path = Path(td) / f"bible-{mode.lower()}.json"
    path.write_text(json.dumps(
        {"blend_profile": {"hero_color_chroma": mode}}), encoding="utf-8")
    return path


def brand(td):
    path = Path(td) / "brand-test.json"
    path.write_text(json.dumps({"grade": FULL}), encoding="utf-8")
    return path


def test_suppress_profile_passes_monochrome():
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "Image-001.png"
        monochrome(img)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", img,
                    "--brand", brand(td), "--bible", bible(td, "SUPPRESS")], 0)
        assert "SUPPRESS" in proc.stdout, proc.stdout


def test_full_profile_flags_monochrome():
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "Image-001.png"
        monochrome(img)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", img,
                    "--brand", brand(td), "--bible", bible(td, "FULL")], 1)
        assert "mean_saturation" in proc.stdout, proc.stdout


def test_no_bible_flags_monochrome():
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "Image-001.png"
        monochrome(img)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", img,
                    "--brand", brand(td)], 1)
        assert "mean_saturation" in proc.stdout, proc.stdout


def test_adapt_profile_also_passes_monochrome():
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "Image-001.png"
        monochrome(img)
        run([PY, SCRIPTS / "validate_image_grade.py", img,
             "--brand", brand(td), "--bible", bible(td, "ADAPT")], 0)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"ALL PASS: {len(fns)} suppress-fixture tests")
