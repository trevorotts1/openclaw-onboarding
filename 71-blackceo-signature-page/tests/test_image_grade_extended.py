#!/usr/bin/env python3
"""Tests for the Item 9 extension of scripts/validate_image_grade.py,
scripts/calibrate_grade.py (Item 8 machinery), and
scripts/check_authority_pins.py (Item 11).

Synthetic fixtures only. The real assets/brand/blackceo-brand.json
thresholds stay null; every calibrated path is proven with TEST-ONLY
brand files in a tmpdir. No gold images are committed by this test and
no calibration values are recorded anywhere in it.
"""
import hashlib
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PY = sys.executable


def run(args, expect=None):
    proc = subprocess.run([str(a) for a in args], text=True, capture_output=True)
    if expect is not None and proc.returncode != expect:
        print("COMMAND:", " ".join(str(x) for x in args))
        print("STDOUT:\n", proc.stdout)
        print("STDERR:\n", proc.stderr)
        raise AssertionError(f"Expected return code {expect}, got {proc.returncode}")
    return proc


def halves(path, w=160, h=90):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w // 2, h], fill=(220, 30, 30))
    d.rectangle([w // 2, 0, w, h], fill=(30, 30, 220))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def noise(path, w, h, seed):
    from PIL import Image
    rng = random.Random(seed)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def brand(td, grade):
    path = Path(td) / "brand-test.json"
    path.write_text(json.dumps({"grade": grade}), encoding="utf-8")
    return path


FULL = {"min_mean_saturation": 0.1, "min_luma_std": 5,
        "min_sharpness": 10, "min_colorfulness": 5}
NULLS = {"min_mean_saturation": None, "min_luma_std": None}


def test_sharpness_threshold_fails_blur():
    from PIL import Image, ImageFilter
    sys.path.insert(0, str(SCRIPTS))
    import validate_image_grade as vig
    with tempfile.TemporaryDirectory() as td:
        sharp = Path(td) / "sharp.png"
        halves(sharp)
        blur = Path(td) / "blur.png"
        Image.open(sharp).filter(ImageFilter.GaussianBlur(6)).save(blur)
        mid = (vig.measure(sharp)["sharpness"] + vig.measure(blur)["sharpness"]) / 2
        b = brand(td, {**FULL, "min_sharpness": mid})
        proc = run([PY, SCRIPTS / "validate_image_grade.py", blur, "--brand", b], 1)
        assert "sharpness" in proc.stdout, proc.stdout
        run([PY, SCRIPTS / "validate_image_grade.py", sharp, "--brand", b], 0)


def test_colorfulness_threshold_fails_gray():
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        gray = Path(td) / "gray.png"
        Image.new("RGB", (64, 64), (128, 128, 128)).save(gray)
        b = brand(td, {**FULL, "min_colorfulness": 20})
        proc = run([PY, SCRIPTS / "validate_image_grade.py", gray, "--brand", b], 1)
        assert "colorfulness" in proc.stdout, proc.stdout


def test_duplicate_pair_fails_even_uncalibrated():
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "Image-001.png"
        b_img = Path(td) / "Image-002.png"
        noise(a, 80, 80, 7)
        noise(b_img, 80, 80, 7)
        b = brand(td, NULLS)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", a, b_img,
                    "--brand", b], 1)
        assert "possible duplicate" in proc.stdout, proc.stdout


def test_continuity_group_exempts_duplicate_pair():
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "Image-001.png"
        b_img = Path(td) / "Image-002.png"
        noise(a, 80, 80, 7)
        noise(b_img, 80, 80, 7)
        inv = Path(td) / "image-inventory.json"
        inv.write_text(json.dumps({"images": [
            {"id": "IMG-001", "aspect_ratio": "1:1", "continuity_group": "series-a"},
            {"id": "IMG-002", "aspect_ratio": "1:1", "continuity_group": "series-a"},
        ]}), encoding="utf-8")
        b = brand(td, NULLS)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", a, b_img,
                    "--brand", b, "--inventory", inv], 0)
        assert "exempt" in proc.stdout, proc.stdout


def test_ratio_truth_pass_and_fail():
    with tempfile.TemporaryDirectory() as td:
        wide = Path(td) / "Image-003.png"
        noise(wide, 160, 90, 3)
        b = brand(td, NULLS)
        bad_inv = Path(td) / "inv-bad.json"
        bad_inv.write_text(json.dumps({"images": [
            {"id": "IMG-003", "aspect_ratio": "4:5"}]}), encoding="utf-8")
        proc = run([PY, SCRIPTS / "validate_image_grade.py", wide,
                    "--brand", b, "--inventory", bad_inv], 1)
        assert "aspect ratio" in proc.stdout, proc.stdout
        good_inv = Path(td) / "inv-good.json"
        good_inv.write_text(json.dumps({"images": [
            {"id": "IMG-003", "aspect_ratio": "16:9"}]}), encoding="utf-8")
        run([PY, SCRIPTS / "validate_image_grade.py", wide,
             "--brand", b, "--inventory", good_inv], 0)


def test_calibrate_proposes_and_never_writes():
    with tempfile.TemporaryDirectory() as td:
        gold = Path(td) / "gold"
        gold.mkdir()
        for i in range(6):
            halves(gold / f"gold-{i}.png", 120, 80)
        (gold / "gold-set.json").write_text(json.dumps({"images": [
            {"file": f"gold-{i}.png", "source_page": "fixture",
             "approved_by": "Trevor Otts", "date": "2026-10-13",
             # Assembly fix (S8): calibrate_grade.py refuses a gold set
             # with no definingly monochrome or restrained-style case
             # (Amendment 6, Part D); one entry records the case.
             **({"style_case": "monochrome"} if i == 0 else {})}
            for i in range(6)]}), encoding="utf-8")
        b = brand(td, NULLS)
        before = b.read_text(encoding="utf-8")
        proc = run([PY, SCRIPTS / "calibrate_grade.py",
                    "--brand", b, "--gold", gold], 0)
        assert "Proposed floors" in proc.stdout, proc.stdout
        assert "PROPOSAL ONLY" in proc.stdout, proc.stdout
        assert b.read_text(encoding="utf-8") == before
        empty = Path(td) / "empty"
        empty.mkdir()
        (empty / "gold-set.json").write_text('{"images": []}', encoding="utf-8")
        run([PY, SCRIPTS / "calibrate_grade.py",
             "--brand", b, "--gold", empty], 2)


def blob_sha(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def test_authority_pins_ok_drift_missing():
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        target = repo / "shared-utils" / "kie_prompt_enforcer.py"
        target.parent.mkdir(parents=True)
        target.write_text("print('fixture')\n", encoding="utf-8")
        pins = Path(td) / "pins.json"
        pins.write_text(json.dumps({"authorities": [{
            "name": "fixture-enforcer", "repo": "fixture",
            "path": "shared-utils/kie_prompt_enforcer.py",
            "blob_sha": blob_sha(target), "checked_on": "2026-10-13",
        }]}), encoding="utf-8")
        proc = run([PY, SCRIPTS / "check_authority_pins.py",
                    "--pins", pins, "--repo-root", repo], 0)
        assert "PIN OK" in proc.stdout, proc.stdout
        target.write_text("print('changed')\n", encoding="utf-8")
        proc = run([PY, SCRIPTS / "check_authority_pins.py",
                    "--pins", pins, "--repo-root", repo], 0)
        assert "PIN DRIFT" in proc.stdout, proc.stdout
        run([PY, SCRIPTS / "check_authority_pins.py",
             "--pins", pins, "--repo-root", repo, "--strict"], 1)
        # Assembly fix (S8): the missing case must be hermetic. In a
        # full repo checkout the checker's fallback roots legitimately
        # contain a real enforcer, so the original form (same path,
        # empty root) reports PIN DRIFT there by design. A pin path
        # that exists in no root exercises the missing branch anywhere.
        missing_pins = Path(td) / "pins-missing.json"
        missing_pins.write_text(json.dumps({"authorities": [{
            "name": "fixture-enforcer", "repo": "fixture",
            "path": "shared-utils/kie_prompt_enforcer_fixture_absent.py",
            "blob_sha": blob_sha(target), "checked_on": "2026-10-13",
        }]}), encoding="utf-8")
        proc = run([PY, SCRIPTS / "check_authority_pins.py",
                    "--pins", missing_pins, "--repo-root", Path(td) / "nowhere"], 0)
        assert "PIN MISSING" in proc.stdout, proc.stdout


def main():
    tests = [
        test_sharpness_threshold_fails_blur,
        test_colorfulness_threshold_fails_gray,
        test_duplicate_pair_fails_even_uncalibrated,
        test_continuity_group_exempts_duplicate_pair,
        test_ratio_truth_pass_and_fail,
        test_calibrate_proposes_and_never_writes,
        test_authority_pins_ok_drift_missing,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print("PASS", test.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL", test.__name__, "-", exc)
    if failures:
        print(f"{failures} test(s) failed")
        return 1
    print(f"ALL PASS: {len(tests)} tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
