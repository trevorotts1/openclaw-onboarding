#!/usr/bin/env python3
"""Tests for scripts/validate_image_manifest.py (C5) and scripts/validate_image_grade.py (C6).

Order rules honored here:
  - The real assets/brand/blackceo-brand.json thresholds stay null (BRAND owns them);
    the calibrated-FAIL path is proven with a TEST-ONLY brand file written in a tmpdir.
  - No calibration measurements are recorded anywhere in this test.
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


def run(args, expect=0):
    proc = subprocess.run([str(a) for a in args], text=True, capture_output=True)
    if proc.returncode != expect:
        print("COMMAND:", " ".join(str(x) for x in args))
        print("STDOUT:\n", proc.stdout)
        print("STDERR:\n", proc.stderr)
        raise AssertionError(f"Expected return code {expect}, got {proc.returncode}")
    return proc


def authoring_entry(status="ready", with_asset=False, qc_status=None, size=None):
    entry = {
        "id": "IMG-001",
        "source_passage": "Hero promise",
        "job": "Hero authority",
        "scene": "Specific hero scene",
        "people": "Fictional Black woman entrepreneur",
        "shot_plan": "Three-quarter environmental portrait",
        "style_grade": "Active page style plus compatible Secret Sauce",
        "text_mode": "no-generated-text",
        "references": [],
        "technical_plan": "Wide master",
        "prompt_file": "prompts/IMG-001.md",
        "filename": "IMG-001.png",
        "status": status,
    }
    if with_asset:
        entry["asset_file"] = "generated/IMG-001.png"
        if qc_status is not None:
            entry["qc_status"] = qc_status
        if size is not None:
            entry["width"], entry["height"] = size
    return entry


def write_run(td, entries, inventory=None):
    """Write a run folder: map, prompt placeholder, optional inventory + asset PNG."""
    td = Path(td)
    (td / "prompts").mkdir(parents=True, exist_ok=True)
    (td / "prompts" / "IMG-001.md").write_text("prompt placeholder\n", encoding="utf-8")
    for entry in entries:
        if entry.get("asset_file"):
            asset = td / entry["asset_file"]
            asset.parent.mkdir(parents=True, exist_ok=True)
            _png(asset, entry.get("width", 100), entry.get("height", 100))
    manifest = {"images": entries}
    manifest_path = td / "image-map.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    inventory_path = None
    if inventory is not None:
        inventory_path = td / "image-inventory.json"
        inventory_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return manifest_path, inventory_path


def inventory_entries(count, gen=True):
    """Inventory entries; gen=False marks requires_generation: false."""
    out = []
    for i in range(count):
        item = {"id": f"IMG-{i + 1:03d}", "role": "hero"}
        if not gen:
            item["requires_generation"] = False
        out.append(item)
    return out


def _png(path, width, height, mode="noise"):
    from PIL import Image, ImageDraw

    rng = random.Random(42)
    im = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(im)
    if mode == "noise":
        for y in range(height):
            for x in range(width):
                im.putpixel((x, y), (rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    else:  # flat gray: saturation 0, luma std 0
        d.rectangle([0, 0, width, height], fill=(128, 128, 128))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def test_manifest_base_pass():
    with tempfile.TemporaryDirectory() as td:
        manifest, _ = write_run(td, [authoring_entry(status="prompt_ready")])
        run([PY, SCRIPTS / "validate_image_manifest.py", manifest], 0)


def test_manifest_qc_status_fail_and_pass():
    # Entry carries an asset but no qc_status -> FAIL.
    with tempfile.TemporaryDirectory() as td:
        manifest, _ = write_run(td, [authoring_entry(with_asset=True)])
        run([PY, SCRIPTS / "validate_image_manifest.py", manifest], 1)
    # qc_status passed -> PASS.
    with tempfile.TemporaryDirectory() as td:
        manifest, _ = write_run(td, [authoring_entry(with_asset=True, qc_status="passed")])
        run([PY, SCRIPTS / "validate_image_manifest.py", manifest], 0)


def test_manifest_inventory_count_mismatch_fails():
    # Inventory needs 3 generated images, map declares 1 master -> FAIL naming counts.
    with tempfile.TemporaryDirectory() as td:
        manifest, inv = write_run(td, [authoring_entry(status="prompt_ready")], inventory=inventory_entries(3))
        proc = run([PY, SCRIPTS / "validate_image_manifest.py", manifest, "--inventory", inv], 1)
        assert "3" in proc.stdout and "1" in proc.stdout, proc.stdout


def test_manifest_inventory_count_match_passes():
    with tempfile.TemporaryDirectory() as td:
        manifest, inv = write_run(td, [authoring_entry(status="prompt_ready")], inventory=inventory_entries(1))
        run([PY, SCRIPTS / "validate_image_manifest.py", manifest, "--inventory", inv], 0)


def test_manifest_inventory_non_generated_excluded():
    # One generated + one requires_generation:false -> 1 needed; map has 1 master -> PASS.
    with tempfile.TemporaryDirectory() as td:
        inv = inventory_entries(1) + inventory_entries(1, gen=False)
        manifest, inv_path = write_run(td, [authoring_entry(status="prompt_ready")], inventory=inv)
        run([PY, SCRIPTS / "validate_image_manifest.py", manifest, "--inventory", inv_path], 0)


def test_manifest_measure_mismatch_fails():
    # Declared 100x100, actual PNG is 64x32 -> FAIL naming the measurements.
    with tempfile.TemporaryDirectory() as td:
        entry = authoring_entry(with_asset=True, qc_status="passed", size=(100, 100))
        td = Path(td)
        (td / "prompts").mkdir(parents=True)
        (td / "prompts" / "IMG-001.md").write_text("x\n", encoding="utf-8")
        _png(td / "generated" / "IMG-001.png", 64, 32)
        manifest = td / "image-map.json"
        manifest.write_text(json.dumps({"images": [entry]}), encoding="utf-8")
        proc = run([PY, SCRIPTS / "validate_image_manifest.py", manifest, "--measure"], 1)
        assert "64x32" in proc.stdout and "100x100" in proc.stdout, proc.stdout


def test_manifest_measure_match_passes():
    with tempfile.TemporaryDirectory() as td:
        entry = authoring_entry(with_asset=True, qc_status="passed", size=(64, 32))
        manifest, _ = write_run(td, [entry])
        run([PY, SCRIPTS / "validate_image_manifest.py", manifest, "--measure"], 0)


def test_manifest_measure_requires_declared_size():
    with tempfile.TemporaryDirectory() as td:
        entry = authoring_entry(with_asset=True, qc_status="passed")
        manifest, _ = write_run(td, [entry])
        proc = run([PY, SCRIPTS / "validate_image_manifest.py", manifest, "--measure"], 1)
        assert "width and height" in proc.stdout, proc.stdout


def test_grade_uncalibrated_warns_exit_zero():
    # Thresholds null (as the real blackceo-brand.json keeps them) -> measurements
    # printed, WARN, exit 0 — even for a maximally flat image.
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        brand = td / "brand-null.json"
        brand.write_text(json.dumps({"grade": {"min_mean_saturation": None, "min_luma_std": None}}), encoding="utf-8")
        img = td / "flat.png"
        Image.new("RGB", (64, 64), (128, 128, 128)).save(img)
        proc = run([PY, SCRIPTS / "validate_image_grade.py", img, "--brand", brand], 0)
        assert "WARN: uncalibrated" in proc.stdout, proc.stdout
        assert "mean_saturation=" in proc.stdout and "luma_std=" in proc.stdout, proc.stdout


def test_grade_calibrated_fail_and_pass_with_test_brand():
    # TEST-ONLY brand file (never the real blackceo-brand.json): proves the FAIL path.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        brand = td / "brand-test.json"
        brand.write_text(json.dumps({"grade": {"min_mean_saturation": 0.25, "min_luma_std": 20}}), encoding="utf-8")
        flat = td / "flat.png"
        _png(flat, 64, 64, mode="flat")
        run([PY, SCRIPTS / "validate_image_grade.py", flat, "--brand", brand], 1)
        rich = td / "rich.png"
        _png(rich, 64, 64, mode="noise")
        run([PY, SCRIPTS / "validate_image_grade.py", rich, "--brand", brand], 0)


def test_grade_unreadable_input_exit_two():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        brand = td / "brand-null.json"
        brand.write_text(json.dumps({"grade": {"min_mean_saturation": None, "min_luma_std": None}}), encoding="utf-8")
        bad = td / "not-an-image.png"
        bad.write_text("this is not a png", encoding="utf-8")
        run([PY, SCRIPTS / "validate_image_grade.py", bad, "--brand", brand], 2)


def main():
    tests = [
        test_manifest_base_pass,
        test_manifest_qc_status_fail_and_pass,
        test_manifest_inventory_count_mismatch_fails,
        test_manifest_inventory_count_match_passes,
        test_manifest_inventory_non_generated_excluded,
        test_manifest_measure_mismatch_fails,
        test_manifest_measure_match_passes,
        test_manifest_measure_requires_declared_size,
        test_grade_uncalibrated_warns_exit_zero,
        test_grade_calibrated_fail_and_pass_with_test_brand,
        test_grade_unreadable_input_exit_two,
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
