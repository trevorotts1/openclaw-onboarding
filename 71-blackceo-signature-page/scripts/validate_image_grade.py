#!/usr/bin/env python3
"""Coarse Signature-look screen for generated images (Skill 71, order C6).

For each image compute, with Pillow:
  - mean HSV saturation in 0-1
  - standard deviation of luminance (0-255 scale)

For SECRET_SAUCE_ONLY pages, any image below brand grade.min_mean_saturation
or grade.min_luma_std FAILS. Until Trevor calibrates the thresholds (they are
null in blackceo-brand.json, owned by BRAND), the script prints the
measurements, exits 0, and warns that it is uncalibrated. This is a coarse
screen only; the independent image reviewer still scores every image.

Exit codes: 0 pass (or uncalibrated WARN), 1 fail, 2 unreadable input.
"""
import argparse
import colorsys
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def load_thresholds(brand_path):
    """Return (min_sat, min_luma_std, missing_reasons) from the brand file."""
    try:
        brand = json.loads(Path(brand_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: could not read brand file {brand_path}: {exc}")
    grade = brand.get("grade")
    if not isinstance(grade, dict):
        return None, None, ["brand file has no grade object."]
    min_sat = grade.get("min_mean_saturation")
    min_luma = grade.get("min_luma_std")
    return min_sat, min_luma, []


def measure(path):
    """Return (mean_saturation 0-1, luma std 0-255) for an image file."""
    with Image.open(path) as im:
        rgb = im.convert("RGB")
    im = rgb.resize((256, 256))
    pixels = list(im.getdata())

    total_sat = 0.0
    for r, g, b in pixels:
        _h, s, _v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        total_sat += s
    mean_sat = total_sat / len(pixels)

    luma = [
        0.2126 * r + 0.7152 * g + 0.0722 * b
        for r, g, b in pixels
    ]
    n = len(luma)
    mean_l = sum(luma) / n
    var = sum((x - mean_l) ** 2 for x in luma) / n
    luma_std = var ** 0.5
    return mean_sat, luma_std


def main():
    parser = argparse.ArgumentParser(description="Coarse Signature-look image screen (Skill 71).")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--brand", type=Path, required=True)
    args = parser.parse_args()

    if Image is None:
        print("FAIL: Pillow is required (pip install Pillow).")
        return 2

    min_sat, min_luma, _ = load_thresholds(args.brand)
    uncalibrated = min_sat is None or min_luma is None

    failures = []
    for path in args.images:
        try:
            mean_sat, luma_std = measure(path)
        except Exception as exc:
            print(f"FAIL: could not read {path}: {exc}")
            return 2
        line = f"{path.name}: mean_saturation={mean_sat:.4f} luma_std={luma_std:.2f}"
        if uncalibrated:
            print(f"WARN: uncalibrated — {line}")
            continue
        reasons = []
        if mean_sat < min_sat:
            reasons.append(f"mean_saturation {mean_sat:.4f} < {min_sat}")
        if luma_std < min_luma:
            reasons.append(f"luma_std {luma_std:.2f} < {min_luma}")
        if reasons:
            failures.append(path.name)
            print(f"FAIL: {path.name}: " + "; ".join(reasons))
        else:
            print(f"PASS: {line}")

    if uncalibrated:
        print("WARN: uncalibrated — grade thresholds are null in the brand file; "
              "measurements printed above, no gate applied.")
        return 0
    if failures:
        print(f"FAIL: {len(failures)} image(s) below the Signature grade floor: "
              + ", ".join(failures))
        return 1
    print(f"PASS: {len(args.images)} image(s) meet the Signature grade floor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
