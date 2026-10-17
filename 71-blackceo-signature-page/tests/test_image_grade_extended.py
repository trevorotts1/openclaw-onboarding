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
             # Calibration Redesign (Rulings 1 and 2): entries record
             # active_family and style_case (required), and a blend
             # profile for their posture class. Five FULL anchors make
             # the photographic FULL class derivable; the sixth records
             # the Amendment 6 restrained case as SUPPRESS, which also
             # satisfies the validity rule.
             "active_family": "photographic",
             "style_case": "monochrome restrained case" if i == 0
                           else "full-color hero portrait",
             "blend_profile": {"hero_color_chroma":
                               "SUPPRESS" if i == 0 else "FULL"}}
            for i in range(6)]}), encoding="utf-8")
        b = brand(td, {**NULLS, "families_used": ["photographic"]})
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


# ------------------------------------------------ Calibration Redesign
# Rulings 1, 2, and 3 (2026-10-14): per-family, per-posture floors;
# family span required; Option B protected-region ceiling.

def textured(path, hue, sat, val, seed=1, size=(120, 90)):
    """Synthetic textured color image with approximately known saturation."""
    import colorsys
    rng = random.Random(seed)
    from PIL import Image
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(size[1]):
        for x in range(size[0]):
            s = max(0.0, min(1.0, sat + rng.uniform(-0.08, 0.08)))
            v = max(0.0, min(1.0, val + rng.uniform(-0.15, 0.15)))
            r, g, b = colorsys.hsv_to_rgb(hue, s, v)
            px[x, y] = (int(r * 255), int(g * 255), int(b * 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def gray_ramp(path, seed=3, size=(120, 90)):
    """Structured grayscale image (the restrained/monochrome anchor)."""
    rng = random.Random(seed)
    from PIL import Image
    im = Image.new("L", size)
    px = im.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = max(0, min(255, int(40 + 180 * (x / size[0]))
                                  + rng.randrange(-25, 26)))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(path)


def gold_entry(file, family="photographic", case="full-color hero portrait",
               posture="FULL"):
    entry = {"file": file, "source_page": "fixture",
             "approved_by": "Trevor Otts", "date": "2026-10-14",
             "active_family": family, "style_case": case}
    if posture:
        entry["blend_profile"] = {"hero_color_chroma": posture}
    return entry


def gold_set(td, entries):
    gold = Path(td) / "gold"
    gold.mkdir(exist_ok=True)
    (gold / "gold-set.json").write_text(
        json.dumps({"images": entries}), encoding="utf-8")
    return gold


def test_calibrate_full_floor_ignores_restrained_case():
    """Gap 1 regression: the pooled derivation dragged the FULL floor
    toward the restrained case; the per-class derivation must not."""
    sys.path.insert(0, str(SCRIPTS))
    import calibrate_grade as cg
    import validate_image_grade as vig
    with tempfile.TemporaryDirectory() as td:
        entries = []
        for i in range(5):
            name = f"full-{i}.png"
            textured(Path(td) / "gold" / name, 0.0, 0.80, 0.75, seed=10 + i)
            entries.append(gold_entry(name))
        gray_ramp(Path(td) / "gold" / "restr.png")
        entries.append(gold_entry("restr.png", case="monochrome restrained case",
                                  posture="SUPPRESS"))
        gold = gold_set(td, entries)
        b = brand(td, {**NULLS, "families_used": ["photographic"]})
        proc = run([PY, SCRIPTS / "calibrate_grade.py",
                    "--brand", b, "--gold", gold], 0)
        line = next(l for l in proc.stdout.splitlines()
                    if "FULL grade.floors.photographic.full.min_mean_saturation" in l)
        proposed = float(line.split("proposed")[1].split("(")[0])
        sats = [vig.measure(gold / e["file"])["mean_saturation"] for e in entries]
        pooled = cg.percentile(sats, 5) * 0.95  # the pre-redesign derivation
        assert proposed > pooled + 0.3, (proposed, pooled, proc.stdout)
        assert proposed > 0.6, proc.stdout


def test_calibrate_family_span_refusal_names_missing_families():
    """Ruling 2: no family-scoped mode; an underivable used family is a
    named refusal, even when another family derives cleanly."""
    with tempfile.TemporaryDirectory() as td:
        entries = []
        for i in range(5):
            name = f"full-{i}.png"
            textured(Path(td) / "gold" / name, 0.0, 0.80, 0.75, seed=20 + i)
            entries.append(gold_entry(name))
        gray_ramp(Path(td) / "gold" / "restr.png")
        entries.append(gold_entry("restr.png", case="monochrome restrained case",
                                  posture="SUPPRESS"))
        gold = gold_set(td, entries)
        b = brand(td, NULLS)  # no families_used: all three Router families
        proc = run([PY, SCRIPTS / "calibrate_grade.py",
                    "--brand", b, "--gold", gold], 2)
        assert "FAMILY SPAN" in proc.stdout, proc.stdout
        assert "cinematic" in proc.stdout, proc.stdout
        assert "visual-artist" in proc.stdout, proc.stdout
        assert "no family-scoped" in proc.stdout, proc.stdout


def test_calibrate_posture_class_too_small_refused():
    with tempfile.TemporaryDirectory() as td:
        entries = []
        for i in range(2):
            name = f"full-{i}.png"
            textured(Path(td) / "gold" / name, 0.0, 0.80, 0.75, seed=30 + i)
            entries.append(gold_entry(name))
        for i in range(3):
            name = f"supp-{i}.png"
            gray_ramp(Path(td) / "gold" / name, seed=40 + i)
            entries.append(gold_entry(
                name, case="monochrome restrained case" if i == 0
                else "monochrome portrait", posture="SUPPRESS"))
        gold = gold_set(td, entries)
        b = brand(td, {**NULLS, "families_used": ["photographic"]})
        proc = run([PY, SCRIPTS / "calibrate_grade.py",
                    "--brand", b, "--gold", gold], 2)
        assert "POSTURE CLASS TOO SMALL" in proc.stdout, proc.stdout
        assert "class FULL in family photographic has 2" in proc.stdout, proc.stdout


def test_calibrate_adapt_band_provisional_printed():
    with tempfile.TemporaryDirectory() as td:
        entries = []
        for i in range(4):
            name = f"full-{i}.png"
            textured(Path(td) / "gold" / name, 0.0, 0.80, 0.75, seed=50 + i)
            entries.append(gold_entry(name))
        for i in range(2):
            name = f"adapt-{i}.png"
            textured(Path(td) / "gold" / name, 0.6, 0.25, 0.65, seed=60 + i)
            entries.append(gold_entry(
                name, case="restrained case, limited palette" if i == 0
                else "limited-palette portrait", posture="ADAPT"))
        gold = gold_set(td, entries)
        b = brand(td, {**NULLS, "families_used": ["photographic"]})
        proc = run([PY, SCRIPTS / "calibrate_grade.py",
                    "--brand", b, "--gold", gold], 0)
        assert "ADAPT band [PROVISIONAL" in proc.stdout, proc.stdout
        assert "PROPOSAL ONLY" in proc.stdout, proc.stdout


def nested_brand(td, adapt_provisional=False, with_floors=True):
    grade = {"min_mean_saturation": None, "min_luma_std": None}
    if with_floors:
        grade["floors"] = {"photographic": {
            "full": {"min_mean_saturation": 0.5, "min_colorfulness": 30},
            "adapt": {"min_mean_saturation": 0.15, "max_mean_saturation": 0.45,
                      "min_colorfulness": 5, "max_colorfulness": 90,
                      "min_luma_std": 5, "provisional": adapt_provisional},
            "noncolor": {"min_luma_std": 5, "min_sharpness": 10}}}
    return brand(td, grade)


def adapt_bible(td):
    path = Path(td) / "bible-adapt.json"
    path.write_text(json.dumps(
        {"blend_profile": {"hero_color_chroma": "ADAPT"}}), encoding="utf-8")
    return path


def test_validator_adapt_band_bounds():
    with tempfile.TemporaryDirectory() as td:
        b = nested_brand(td)
        bible = adapt_bible(td)
        inside = Path(td) / "Image-101.png"
        textured(inside, 0.6, 0.30, 0.65, seed=71)
        run([PY, SCRIPTS / "validate_image_grade.py", inside,
             "--brand", b, "--bible", bible], 0)
        above = Path(td) / "Image-102.png"
        textured(above, 0.6, 0.85, 0.75, seed=72)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", above,
                    "--brand", b, "--bible", bible], 1)
        assert "ADAPT band ceiling" in proc.stdout, proc.stdout
        below = Path(td) / "Image-103.png"
        textured(below, 0.6, 0.03, 0.65, seed=73)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", below,
                    "--brand", b, "--bible", bible], 1)
        assert "ADAPT band floor" in proc.stdout, proc.stdout


def test_validator_adapt_provisional_warns_not_fails():
    with tempfile.TemporaryDirectory() as td:
        b = nested_brand(td, adapt_provisional=True)
        bible = adapt_bible(td)
        above = Path(td) / "Image-104.png"
        textured(above, 0.6, 0.85, 0.75, seed=74)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", above,
                    "--brand", b, "--bible", bible], 0)
        assert "PROVISIONAL ADAPT band" in proc.stdout, proc.stdout


def test_validator_uncalibrated_family_warns():
    with tempfile.TemporaryDirectory() as td:
        b = nested_brand(td)  # photographic floors only
        img = Path(td) / "Image-105.png"
        textured(img, 0.0, 0.8, 0.75, seed=75, size=(90, 90))
        inv = Path(td) / "image-inventory.json"
        inv.write_text(json.dumps({"images": [
            {"id": "IMG-105", "aspect_ratio": "1:1",
             "active_family": "cinematic"}]}), encoding="utf-8")
        proc = run([PY, SCRIPTS / "validate_image_grade.py", img,
                    "--brand", b, "--inventory", inv], 0)
        assert "family not calibrated" in proc.stdout, proc.stdout
        assert "cinematic" in proc.stdout, proc.stdout


def skin_hero(path, skin_sat, seed=81):
    """Half skin-band surface at a set saturation, half saturated hero red."""
    import colorsys
    rng = random.Random(seed)
    from PIL import Image
    im = Image.new("RGB", (120, 90))
    px = im.load()
    for y in range(90):
        for x in range(120):
            if x < 60:
                h, s, v = 0.07, skin_sat, 0.62
            else:
                h, s, v = 0.0, 0.85, 0.75
            s = max(0.0, min(1.0, s + rng.uniform(-0.03, 0.03)))
            v = max(0.0, min(1.0, v + rng.uniform(-0.10, 0.10)))
            r, g, bb = colorsys.hsv_to_rgb(h, s, v)
            px[x, y] = (int(r * 255), int(g * 255), int(bb * 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def test_option_b_wash_warns_uncalibrated():
    """A protected region carrying high chroma is measured and WARNed
    (never failed) while no ceiling is approved."""
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "Image-106.png"
        skin_hero(img, 0.45)
        b = brand(td, FULL)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", img,
                    "--brand", b], 0)
        assert "uncalibrated Option B" in proc.stdout, proc.stdout
        assert "protected-region mean saturation" in proc.stdout, proc.stdout
        assert "Item 12 judgment gate" in proc.stdout, proc.stdout


def test_option_b_ceiling_warns_not_fails_when_approved():
    """Owner ruling S71-OPTION-B, Resolution A (2026-10-16): with an
    approved ceiling WRITTEN, an over-ceiling FULL image WARNs and does
    NOT fail; the brand note's WARN-only status governs and writing the
    value does not change its enforcement status. (This replaces the
    pre-ruling pin that asserted a FAIL here.) The fixture carries no
    inventory or bible, so its posture is UNRECORDED, which resolves
    to the FULL class the Option B screen governs."""
    with tempfile.TemporaryDirectory() as td:
        washed = Path(td) / "Image-107.png"
        skin_hero(washed, 0.45, seed=82)
        selective = Path(td) / "Image-108.png"
        skin_hero(selective, 0.15, seed=83)
        b = brand(td, {**FULL, "max_protected_saturation": 0.20})
        proc = run([PY, SCRIPTS / "validate_image_grade.py", washed,
                    "--brand", b], 0)
        assert "WARN: Option B selectivity" in proc.stdout, proc.stdout
        assert "protected-region mean saturation" in proc.stdout, proc.stdout
        assert "ceiling" in proc.stdout, proc.stdout
        assert "never a failure" in proc.stdout, proc.stdout
        assert "FAIL: Image-107" not in proc.stdout, proc.stdout
        # Under the ceiling: unchanged, the within-ceiling NOTE prints.
        proc = run([PY, SCRIPTS / "validate_image_grade.py", selective,
                    "--brand", b], 0)
        assert "within the approved ceiling" in proc.stdout, proc.stdout


def test_option_b_other_floor_still_fails_with_ceiling():
    """Resolution A changes only the Option B ceiling path: with the
    ceiling written and the image over it, a different floor breach
    (sharpness) still FAILs, and the protected-region overage appears
    only in the WARN line, never among the fail reasons."""
    with tempfile.TemporaryDirectory() as td:
        washed = Path(td) / "Image-110.png"
        skin_hero(washed, 0.45, seed=85)
        b = brand(td, {**FULL, "max_protected_saturation": 0.20,
                       "min_sharpness": 100000})
        proc = run([PY, SCRIPTS / "validate_image_grade.py", washed,
                    "--brand", b], 1)
        assert "WARN: Option B selectivity" in proc.stdout, proc.stdout
        fail_lines = [l for l in proc.stdout.splitlines()
                      if l.startswith("FAIL: Image-110")]
        assert fail_lines, proc.stdout
        assert "sharpness" in fail_lines[0], proc.stdout
        assert "protected-region" not in fail_lines[0], proc.stdout


def test_option_b_adapt_band_unchanged_with_ceiling():
    """The ADAPT band mechanism is untouched by Resolution A: with a
    ceiling written in the family's FULL block, an ADAPT image above
    its band still FAILs on the band, and one inside its band passes."""
    with tempfile.TemporaryDirectory() as td:
        grade = {"min_mean_saturation": None, "min_luma_std": None,
                 "floors": {"photographic": {
                     "full": {"min_mean_saturation": 0.5,
                              "min_colorfulness": 30,
                              "max_protected_saturation": 0.20},
                     "adapt": {"min_mean_saturation": 0.15,
                               "max_mean_saturation": 0.45,
                               "min_colorfulness": 5,
                               "max_colorfulness": 90,
                               "min_luma_std": 5},
                     "noncolor": {"min_luma_std": 5, "min_sharpness": 10}}}}
        b = brand(td, grade)
        bible = adapt_bible(td)
        above = Path(td) / "Image-111.png"
        textured(above, 0.6, 0.85, 0.75, seed=86)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", above,
                    "--brand", b, "--bible", bible], 1)
        assert "ADAPT band ceiling" in proc.stdout, proc.stdout
        inside = Path(td) / "Image-112.png"
        textured(inside, 0.6, 0.30, 0.65, seed=87)
        run([PY, SCRIPTS / "validate_image_grade.py", inside,
             "--brand", b, "--bible", bible], 0)


def test_option_b_na_when_mask_empty():
    """Full-frame hero color leaves almost no protected surface: the
    metric reports N/A, never a fabricated pass."""
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "Image-109.png"
        textured(img, 0.0, 0.85, 0.75, seed=84)
        b = brand(td, FULL)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", img,
                    "--brand", b], 0)
        assert "protected-region saturation N/A" in proc.stdout, proc.stdout


def main():
    tests = [
        test_sharpness_threshold_fails_blur,
        test_colorfulness_threshold_fails_gray,
        test_duplicate_pair_fails_even_uncalibrated,
        test_continuity_group_exempts_duplicate_pair,
        test_ratio_truth_pass_and_fail,
        test_calibrate_proposes_and_never_writes,
        test_authority_pins_ok_drift_missing,
        test_calibrate_full_floor_ignores_restrained_case,
        test_calibrate_family_span_refusal_names_missing_families,
        test_calibrate_posture_class_too_small_refused,
        test_calibrate_adapt_band_provisional_printed,
        test_validator_adapt_band_bounds,
        test_validator_adapt_provisional_warns_not_fails,
        test_validator_uncalibrated_family_warns,
        test_option_b_wash_warns_uncalibrated,
        test_option_b_ceiling_warns_not_fails_when_approved,
        test_option_b_other_floor_still_fails_with_ceiling,
        test_option_b_adapt_band_unchanged_with_ceiling,
        test_option_b_na_when_mask_empty,
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
