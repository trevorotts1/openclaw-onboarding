#!/usr/bin/env python3
"""Signature-look screen for generated images (Skill 71, Items 8 and 9).

This is the full deterministic pixel screen for a run's generated images.
For each image it computes, with Pillow only:

  - mean HSV saturation (0-1)                       [original measure]
  - standard deviation of luminance (0-255 scale)   [original measure]
  - sharpness: variance of the FIND_EDGES (Laplacian-approximating)
    convolution over the grayscale 256px working copy
  - colorfulness: the Hasler-Susstrunk metric over the rg / yb opponent
    channels of the 256px working copy
  - an 8x8 average hash, used for near-duplicate detection (below)
  - the image's actual aspect ratio (for the ratio-truth check, below)

Threshold checks (brand file `grade` block):
  mean_saturation >= grade.min_mean_saturation
  luma_std        >= grade.min_luma_std
  sharpness       >= grade.min_sharpness        (Item 9 key)
  colorfulness    >= grade.min_colorfulness     (Item 9 key)
A metric whose threshold is null (or whose key is absent) is uncalibrated:
its value is printed as a WARN measurement and it never fails the image.
Calibrating a threshold is Item 8's procedure (scripts/calibrate_grade.py
proposes floors from Trevor's gold set; Trevor approves the numbers that
get written into the brand file). This script never writes the brand file.

Unconditional checks (no threshold to calibrate; these always apply):
  - Near-duplicate / cloned-shot detection: for every pair of images in
    the invocation set, an average-hash Hamming distance of 4 or less is
    a FAIL ("possible duplicate or near-identical shot"), UNLESS the pair
    is declared an intentional continuity series in the inventory passed
    with --inventory: both entries share the same `continuity_group`
    string, or either entry's `continuity_group` list names the other
    entry's id. Without --inventory no continuity exemption can apply.
  - Ratio truth (only with --inventory): each image matched to an
    inventory entry by id (file stem, case-insensitive, "Image-" and
    "IMG-" treated as the same prefix) must have an actual aspect ratio
    within 2% of its slot's declared ratio. The slot ratio is read from
    the entry's `aspect_ratio` ("16:9" or a number), `intended_ratio`,
    `slot_ratio`, or its declared width/height (or slot_width/slot_height,
    or desktop_slot_px). An image with no matching entry, or an entry
    with no readable slot ratio, is reported as a WARN line, not a FAIL:
    the inventory is the authority for which slots exist (the manifest
    validator owns that check), this script owns ratio truth for the
    slots that are declared.

The production gate (stage_gate.py, Item 8's close rule) is what blocks
a production image-generation-qc close while thresholds are null; this
script keeps the historical WARN-and-measure behavior for uncalibrated
metrics so test runs can still see the numbers.

CLI shape is unchanged from the original script:
  validate_image_grade.py <image> [<image> ...] --brand <brand.json>
      [--inventory <image-inventory.json>]

Exit codes: 0 pass (or uncalibrated WARN with no unconditional failure),
1 fail, 2 unreadable input.
"""
import argparse
import colorsys
import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover
    Image = None
    ImageFilter = None

WORK = 256  # working-copy edge length, as in the original script
RATIO_TOLERANCE = 0.02  # 2 percent, per Item 9
DUPLICATE_MAX_HAMMING = 4  # 8x8 average hash, per Item 9

# (metric key in the measures dict, brand grade key, display format)
THRESHOLD_METRICS = [
    ("mean_saturation", "min_mean_saturation", "{:.4f}"),
    ("luma_std", "min_luma_std", "{:.2f}"),
    ("sharpness", "min_sharpness", "{:.2f}"),
    ("colorfulness", "min_colorfulness", "{:.2f}"),
]


def load_thresholds(brand_path):
    """Return {metric_key: threshold-or-None} from the brand file's grade block."""
    try:
        brand = json.loads(Path(brand_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: could not read brand file {brand_path}: {exc}")
    grade = brand.get("grade")
    if not isinstance(grade, dict):
        raise SystemExit(f"FAIL: brand file {brand_path} has no grade object.")
    thresholds = {}
    for metric_key, grade_key, _fmt in THRESHOLD_METRICS:
        value = grade.get(grade_key)
        if value is not None and not isinstance(value, (int, float)):
            raise SystemExit(
                f"FAIL: brand grade.{grade_key} must be a number or null, got {value!r}")
        thresholds[metric_key] = value
    return thresholds


def average_hash(gray_work):
    """8x8 average hash of a grayscale working copy, as a 64-bit int."""
    small = gray_work.resize((8, 8))
    pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    bits = 0
    for p in pixels:
        bits = (bits << 1) | (1 if p > mean else 0)
    return bits


def measure(path):
    """Return the full measures dict for one image file.

    Keys: mean_saturation, luma_std, sharpness, colorfulness,
    width, height, aspect_ratio, ahash.
    """
    with Image.open(path) as im:
        width, height = im.size
        rgb_full = im.convert("RGB")
    work = rgb_full.resize((WORK, WORK))
    pixels = list(work.getdata())
    n = len(pixels)

    total_sat = 0.0
    for r, g, b in pixels:
        _h, s, _v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        total_sat += s
    mean_sat = total_sat / n

    luma = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels]
    mean_l = sum(luma) / n
    luma_std = (sum((x - mean_l) ** 2 for x in luma) / n) ** 0.5

    # Hasler-Susstrunk colorfulness over opponent channels rg and yb.
    rg = [r - g for r, g, b in pixels]
    yb = [0.5 * (r + g) - b for r, g, b in pixels]
    mean_rg = sum(rg) / n
    mean_yb = sum(yb) / n
    std_rg = (sum((x - mean_rg) ** 2 for x in rg) / n) ** 0.5
    std_yb = (sum((x - mean_yb) ** 2 for x in yb) / n) ** 0.5
    colorfulness = (math.sqrt(std_rg ** 2 + std_yb ** 2)
                    + 0.3 * math.sqrt(mean_rg ** 2 + mean_yb ** 2))

    gray = work.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_pixels = list(edges.getdata())
    mean_e = sum(edge_pixels) / n
    sharpness = sum((x - mean_e) ** 2 for x in edge_pixels) / n

    return {
        "mean_saturation": mean_sat,
        "luma_std": luma_std,
        "sharpness": sharpness,
        "colorfulness": colorfulness,
        "width": width,
        "height": height,
        "aspect_ratio": (width / height) if height else 0.0,
        "ahash": average_hash(gray),
    }


def format_measures(m):
    return (f"mean_saturation={m['mean_saturation']:.4f} "
            f"luma_std={m['luma_std']:.2f} "
            f"sharpness={m['sharpness']:.2f} "
            f"colorfulness={m['colorfulness']:.2f} "
            f"size={m['width']}x{m['height']} "
            f"aspect={m['aspect_ratio']:.4f}")


def normalize_id(value):
    """Normalize an image id / file stem for inventory matching."""
    text = str(value).strip().upper()
    if text.startswith("IMAGE-"):
        text = "IMG-" + text[len("IMAGE-"):]
    return text


def parse_ratio(value):
    """Parse a declared ratio: '16:9', '16/9', a number, or [w, h]. Float or None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value > 0 else None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            w, h = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
        return (w / h) if h else None
    if isinstance(value, str):
        text = value.strip()
        for sep in (":", "/"):
            if sep in text:
                a, _, b = text.partition(sep)
                try:
                    w, h = float(a), float(b)
                except ValueError:
                    return None
                return (w / h) if h else None
        try:
            num = float(text)
        except ValueError:
            return None
        return num if num > 0 else None
    if isinstance(value, dict):
        w = value.get("width") or value.get("w")
        h = value.get("height") or value.get("h")
        if w and h:
            return float(w) / float(h)
    return None


def slot_ratio(entry):
    """The inventory entry's declared slot aspect ratio, or None."""
    for key in ("aspect_ratio", "intended_ratio", "slot_ratio", "ratio"):
        if entry.get(key) is not None:
            ratio = parse_ratio(entry.get(key))
            if ratio:
                return ratio
    for wkey, hkey in (("width", "height"), ("slot_width", "slot_height"),
                       ("slot_px_width", "slot_px_height")):
        w, h = entry.get(wkey), entry.get(hkey)
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and h:
            return float(w) / float(h)
    if entry.get("desktop_slot_px") is not None:
        return parse_ratio(entry.get("desktop_slot_px"))
    return None


def load_inventory(path):
    """Return {normalized_id: entry} from an image-inventory.json file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: could not read inventory {path}: {exc}")
    if isinstance(data, dict):
        items = data.get("images")
        if items is None:
            items = data.get("items")
        if items is None:
            items = data.get("inventory")
    else:
        items = data
    if not isinstance(items, list):
        raise SystemExit(f"FAIL: inventory {path} has no images/items array.")
    out = {}
    for item in items:
        if isinstance(item, dict) and item.get("id") is not None:
            out[normalize_id(item["id"])] = item
    return out


def continuity_exempt(entry_a, entry_b):
    """True if the inventory declares this pair an intentional continuity series."""
    if entry_a is None or entry_b is None:
        return False
    group_a = entry_a.get("continuity_group")
    group_b = entry_b.get("continuity_group")
    if isinstance(group_a, str) and isinstance(group_b, str):
        if group_a and group_a == group_b:
            return True
    id_a = normalize_id(entry_a.get("id", ""))
    id_b = normalize_id(entry_b.get("id", ""))
    for group, other_id in ((group_a, id_b), (group_b, id_a)):
        if isinstance(group, (list, tuple)):
            if other_id in {normalize_id(x) for x in group}:
                return True
        if isinstance(group, dict):
            members = group.get("members") or group.get("ids") or []
            if other_id in {normalize_id(x) for x in members}:
                return True
    return False


def hamming(a, b):
    return bin(a ^ b).count("1")


def main():
    parser = argparse.ArgumentParser(
        description="Signature-look image screen (Skill 71, Items 8 and 9).")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--brand", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, default=None,
                        help="desktop-wireframe/image-inventory.json; enables the "
                             "ratio-truth check and continuity_group exemptions "
                             "for near-duplicate detection")
    args = parser.parse_args()

    if Image is None:
        print("FAIL: Pillow is required (pip install Pillow).")
        return 2

    thresholds = load_thresholds(args.brand)
    uncalibrated_keys = [k for k, v in thresholds.items() if v is None]
    uncalibrated = bool(uncalibrated_keys)

    inventory = load_inventory(args.inventory) if args.inventory else {}

    measured = []  # (path, measures, entry-or-None)
    failures = []

    for path in args.images:
        try:
            m = measure(path)
        except Exception as exc:
            print(f"FAIL: could not read {path}: {exc}")
            return 2
        entry = inventory.get(normalize_id(path.stem))
        measured.append((path, m, entry))
        line = f"{path.name}: " + format_measures(m)

        reasons = []
        for metric_key, grade_key, fmt in THRESHOLD_METRICS:
            threshold = thresholds[metric_key]
            if threshold is not None and m[metric_key] < threshold:
                reasons.append(
                    f"{metric_key} {fmt.format(m[metric_key])} < "
                    f"grade.{grade_key} {threshold}")

        if args.inventory:
            if entry is None:
                print(f"WARN: {path.name}: no inventory entry matches this file; "
                      "ratio truth not checked")
            else:
                declared = slot_ratio(entry)
                if declared is None:
                    print(f"WARN: {path.name}: inventory entry "
                          f"{entry.get('id')} declares no readable slot ratio; "
                          "ratio truth not checked")
                elif abs(m["aspect_ratio"] - declared) / declared > RATIO_TOLERANCE:
                    reasons.append(
                        f"aspect ratio {m['aspect_ratio']:.4f} does not match "
                        f"inventory slot ratio {declared:.4f} for "
                        f"{entry.get('id')} (tolerance 2%)")

        if reasons:
            failures.append(path.name)
            print(f"FAIL: {path.name}: " + "; ".join(reasons))
        elif uncalibrated:
            print(f"WARN: uncalibrated — {line}")
        else:
            print(f"PASS: {line}")

    # Near-duplicate detection across the whole invocation set.
    duplicate_pairs = []
    for i in range(len(measured)):
        for j in range(i + 1, len(measured)):
            path_a, m_a, entry_a = measured[i]
            path_b, m_b, entry_b = measured[j]
            dist = hamming(m_a["ahash"], m_b["ahash"])
            if dist <= DUPLICATE_MAX_HAMMING:
                if continuity_exempt(entry_a, entry_b):
                    print(f"PASS: {path_a.name} / {path_b.name}: average-hash "
                          f"Hamming distance {dist} <= {DUPLICATE_MAX_HAMMING} but "
                          "the pair is declared in a continuity_group; exempt")
                else:
                    duplicate_pairs.append((path_a.name, path_b.name, dist))
                    print(f"FAIL: {path_a.name} / {path_b.name}: possible duplicate "
                          f"or near-identical shot (average-hash Hamming distance "
                          f"{dist} <= {DUPLICATE_MAX_HAMMING}); declare a "
                          "continuity_group in the inventory if this pair is an "
                          "intentional continuity series")

    if uncalibrated:
        grade_key_of = {mk: gk for mk, gk, _ in THRESHOLD_METRICS}
        missing = ", ".join(f"grade.{grade_key_of[k]}" for k in uncalibrated_keys)
        print("WARN: uncalibrated — the following grade thresholds are null in the "
              f"brand file ({missing}); those measurements were printed above with "
              "no gate applied. Ratio truth and near-duplicate checks are "
              "unconditional and were applied.")
    if duplicate_pairs:
        failures.append(f"{len(duplicate_pairs)} near-duplicate pair(s)")
    if failures:
        print("FAIL: image check(s) failed the Signature grade screen: "
              + ", ".join(failures))
        return 1
    if uncalibrated:
        return 0
    print(f"PASS: {len(args.images)} image(s) meet the Signature grade floor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
