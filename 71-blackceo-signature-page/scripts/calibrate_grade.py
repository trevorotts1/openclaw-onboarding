#!/usr/bin/env python3
"""Propose Signature grade floors from a gold set (Skill 71, Item 8).

Trevor supplies 5-10 accepted images that define the look (the gold set,
committed under assets/brand/gold-set/ with a gold-set.json manifest).
This script runs the EXACT measurements of scripts/validate_image_grade.py
over the gold set (imported, never reimplemented, so the proposal can
never drift from the screen it calibrates) and proposes a floor for each
threshold metric:

    proposed floor = (gold-set 5th percentile of the metric) x 0.95

Percentile method: linear interpolation between closest ranks (the
numpy 'linear' default), computed here with the standard library only.

If --bad names a folder of known-bad images (the failed run's images from
Item 1 are the first bad set), each bad image is measured and the table
shows which proposed floors it would fail.

THIS SCRIPT PROPOSES ONLY. It never writes the brand file, or any other
file. Trevor approves or adjusts the proposed numbers; only then does a
builder write them into the brand file's grade block and record the
calibration date and gold-set manifest hash in brand.schema.json's
documented calibration fields.

Usage:
  calibrate_grade.py --brand <brand.json> --gold <dir> [--bad <dir>]

--brand is read only to confirm it parses and to show the current
(possibly null) thresholds beside the proposal. The gold folder may
contain a gold-set.json manifest ({images: [{file, ...}]}) naming the
gold images; without one, every image file in the folder is measured.

Gold-set validity (Amendment 6, Part D, Items 8 and 9 delta): the set
must span the style range the brand actually uses, and at least one
entry must be a definingly monochrome or restrained-style case (its
manifest entry's style_case says so, or its blend profile SUPPRESSes
hero_color_chroma). A saturation floor calibrated without such a case
is INVALID BY CONSTRUCTION: the calibration would encode "correct
monochrome work is a failure" into the floor, so this script refuses
(exit 2) when a manifest records no qualifying case. The output records
each gold image's active family and blend profile beside its
measurements, so the floors' scope is auditable.

Exit codes: 0 proposal printed, 2 unreadable input or invalid gold set.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_image_grade as vig  # noqa: E402  (the screen being calibrated)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

METRICS = [
    ("mean_saturation", "min_mean_saturation"),
    ("luma_std", "min_luma_std"),
    ("sharpness", "min_sharpness"),
    ("colorfulness", "min_colorfulness"),
]


def percentile(values, pct):
    """pct-th percentile by linear interpolation between closest ranks."""
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + frac * (ordered[high] - ordered[low])


def gold_entries(gold_dir):
    """(image path, manifest entry dict) pairs for the gold set.

    Manifest-listed when gold-set.json exists (entries keep their
    recorded active_family, style_case, and blend profile); otherwise
    every image file in the folder, with empty entries.
    """
    gold_dir = Path(gold_dir)
    manifest = gold_dir / "gold-set.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"FAIL: could not read gold-set manifest {manifest}: {exc}")
        entries = data.get("images") if isinstance(data, dict) else data
        if not isinstance(entries, list) or not entries:
            raise SystemExit(
                f"FAIL: gold-set manifest {manifest} lists no images; "
                "Trevor's gold images are not in place yet (Item 8 is "
                "blocked on owner assets until they are).")
        pairs = []
        for entry in entries:
            name = entry.get("file") if isinstance(entry, dict) else entry
            if not name:
                raise SystemExit(f"FAIL: gold-set manifest entry has no file: {entry!r}")
            pairs.append((gold_dir / name, entry if isinstance(entry, dict) else {}))
        return pairs, True
    return [(p, {}) for p in sorted(gold_dir.iterdir())
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES], False


def is_restrained_case(entry):
    """True if a manifest entry records a definingly monochrome or
    restrained-style case (Amendment 6 gold-set validity rule)."""
    case = str(entry.get("style_case") or "").lower()
    if "monochrome" in case or "restrained" in case or "grayscale" in case \
            or "grey" in case or "pastel" in case:
        return True
    tags = entry.get("tags") or []
    if isinstance(tags, list):
        joined = " ".join(str(t).lower() for t in tags)
        if "monochrome" in joined or "restrained" in joined:
            return True
    profile = vig.blend_profile_of(entry)
    if profile.get(vig.COLOR_DIMENSION) == "SUPPRESS":
        return True
    return False


def measure_all(paths, label):
    rows = []
    for path in paths:
        try:
            m = vig.measure(path)
        except Exception as exc:
            print(f"FAIL: could not read {label} image {path}: {exc}")
            raise SystemExit(2)
        rows.append((path.name, m))
    return rows


def fmt(value):
    return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"


def main():
    parser = argparse.ArgumentParser(
        description="Propose Signature grade floors from a gold set (Item 8). "
                    "Prints a proposal only; never writes the brand file.")
    parser.add_argument("--brand", type=Path, required=True,
                        help="brand file to read current thresholds from (read-only)")
    parser.add_argument("--gold", type=Path, required=True,
                        help="folder of Trevor-approved gold images")
    parser.add_argument("--bad", type=Path, default=None,
                        help="optional folder of known-bad images to test the "
                             "proposed floors against")
    args = parser.parse_args()

    if vig.Image is None:
        print("FAIL: Pillow is required (pip install Pillow).")
        return 2
    if not args.gold.is_dir():
        print(f"FAIL: gold folder not found: {args.gold}")
        return 2

    # Read-only: current thresholds, shown beside the proposal.
    try:
        current = vig.load_thresholds(args.brand)
    except SystemExit as exc:
        print(exc)
        return 2

    try:
        gold_pairs, has_manifest = gold_entries(args.gold)
    except SystemExit as exc:
        print(exc)
        return 2
    if not gold_pairs:
        print(f"FAIL: no gold images found in {args.gold}. Item 8 calibration "
              "is blocked on owner assets: Trevor supplies 5-10 accepted "
              "images (see assets/brand/gold-set/README.md).")
        return 2

    # Gold-set validity (Amendment 6): a manifest set with no definingly
    # monochrome or restrained-style case cannot calibrate a saturation
    # floor; it is invalid by construction and is refused, not used.
    if has_manifest:
        if not any(is_restrained_case(entry) for _p, entry in gold_pairs):
            print("FAIL: INVALID GOLD SET: no entry is a definingly monochrome "
                  "or restrained-style case (record one via style_case or a "
                  "blend profile SUPPRESSing hero_color_chroma). A saturation "
                  "floor calibrated without such a case is invalid by "
                  "construction: it would encode 'correct monochrome work is "
                  "a failure' into the floor (Amendment 6, Part D).")
            return 2
    else:
        print("WARN: no gold-set.json manifest; the set's style span and its "
              "monochrome/restrained case cannot be audited. Prefer the "
              "manifest format (assets/brand/gold-set/README.md).")

    gold_paths = [p for p, _e in gold_pairs]
    entry_by_name = {p.name: e for p, e in gold_pairs}
    gold_rows = measure_all(gold_paths, "gold")

    print(f"Gold set: {len(gold_rows)} image(s) from {args.gold}")
    header = (f"{'image':<30} {'sat':>8} {'luma_std':>9} {'sharpness':>11} "
              f"{'colorful':>9} {'family':<16} {'style_case':<18} {'chroma':>8}")
    print(header)
    print("-" * len(header))
    for name, m in gold_rows:
        entry = entry_by_name.get(name, {})
        profile = vig.blend_profile_of(entry)
        chroma = profile.get(vig.COLOR_DIMENSION, "-")
        print(f"{name:<30} {m['mean_saturation']:>8.4f} {m['luma_std']:>9.2f} "
              f"{m['sharpness']:>11.2f} {m['colorfulness']:>9.2f} "
              f"{str(entry.get('active_family') or '-'):<16} "
              f"{str(entry.get('style_case') or '-'):<18} {chroma:>8}")
    cases = sorted({str(e.get('style_case') or e.get('active_family') or '-')
                    for _p, e in gold_pairs})
    print(f"Gold-set style span (recorded): {', '.join(cases)}")

    floors = {}
    print("\nProposed floors (gold-set 5th percentile x 0.95):")
    print(f"{'brand key':<28} {'current':>10} {'5th pct':>10} {'proposed':>10}")
    for metric_key, grade_key in METRICS:
        values = [m[metric_key] for _name, m in gold_rows]
        p5 = percentile(values, 5)
        floor = p5 * 0.95
        floors[metric_key] = floor
        cur = current.get(metric_key)
        cur_text = "null" if cur is None else fmt(cur)
        print(f"grade.{grade_key:<22} {cur_text:>10} {fmt(p5):>10} {fmt(floor):>10}")

    if args.bad:
        if not Path(args.bad).is_dir():
            print(f"FAIL: bad folder not found: {args.bad}")
            return 2
        bad_paths = sorted(p for p in Path(args.bad).iterdir()
                           if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
        bad_rows = measure_all(bad_paths, "bad")
        print(f"\nBad set: {len(bad_rows)} image(s) from {args.bad}")
        for name, m in bad_rows:
            failed = [grade_key for metric_key, grade_key in METRICS
                      if m[metric_key] < floors[metric_key]]
            verdict = ("would FAIL: " + ", ".join(f"grade.{k}" for k in failed)
                       if failed else "would PASS all proposed floors")
            print(f"{name:<36} sat={m['mean_saturation']:.4f} "
                  f"luma_std={m['luma_std']:.2f} sharpness={m['sharpness']:.2f} "
                  f"colorfulness={m['colorfulness']:.2f}  -> {verdict}")

    print("\nPROPOSAL ONLY: nothing was written. Trevor approves or adjusts "
          "these floors; the approved numbers are then written into the "
          "brand file's grade block by hand, with the calibration date and "
          "the gold-set manifest hash recorded per brand.schema.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
