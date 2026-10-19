#!/usr/bin/env python3
"""Page-level color-energy check for a stitched mockup or a rendered page (Skill 71).

Why: the per-image grade screen (validate_image_grade.py) measures ONE generated photo. It says
nothing about the PAGE a visitor sees. The two reference pages (the Go Full Page captures, VA and
VB) are hypersaturated at page level: saturated brand-color fields, hard near-black, clean white,
almost no mid-tone fog. This check measures that profile on the stitched page and compares it with
thresholds DERIVED from those two references (references/page-color-thresholds.json).

Pillow only. The page is reduced to WORK_WIDTH pixels wide (box filter) so every page, whatever
its source resolution, is measured at the same scale as the calibration. Measures, all HSV based:

  mean_saturation       mean S of every pixel (0-1)
  saturated_share       share of pixels with S > 0.5 and V > 0.3 (any hue)
  near_black_share      share of pixels with V < 0.20 (covers brand darks such as navy and deep green)
  near_white_share      share of pixels with V > 0.93 and S < 0.10
  black_point           1st percentile of luma, 0-255 (lower is deeper)
  white_point           99th percentile of luma, 0-255 (higher is cleaner)
  hero_hue_saturated_share   (only with --hero) share of pixels that are saturated (as above) and
                        within 15 degrees of the client's hero hue

Floors: mean_saturation, saturated_share, near_black_share, near_white_share, white_point,
hero_hue_saturated_share must be AT LEAST the threshold. Ceiling: black_point must be AT MOST.

Commands:
  validate_page_color.py check IMAGE [--hero #HEX] [--thresholds FILE] [--json]
  validate_page_color.py measure IMAGE [--hero #HEX]
  validate_page_color.py calibrate VA_IMAGE VB_IMAGE [--hero-hex #HEX ...]
      recompute the thresholds from the two reference renders and print them (writes nothing)

Exit codes: 0 PASS, 1 FAIL, 2 usage or unreadable image, 3 UNDETERMINED (no thresholds file).

Scope and honesty: this is a PAGE check, on a stitched page or a full render. A single section
slice is expected to be mostly one ground and is not meaningful here. The thresholds come from two
desktop pages; a mobile stitch is measured the same way but has no reference of its own (see the
thresholds file `notes`). The check never decides taste: it proves that the page carries the
saturated-field profile the references carry. Which hue is the hero, and that it is the client's,
is the brand-color gate's job (scripts/brand_colors.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

Image.MAX_IMAGE_PIXELS = None  # stitched pages are tens of megapixels by design

SKILL_ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = SKILL_ROOT / "references" / "page-color-thresholds.json"

WORK_WIDTH = 600
SAT_MIN, VAL_MIN = 0.5, 0.3          # the saturated-pixel definition (analysis measure, QC-verified)
BLACK_V = 0.20                        # near-black: value below this
WHITE_V, WHITE_S = 0.93, 0.10         # near-white: value above, saturation below
HUE_TOL_DEG = 15.0                    # hero-hue window either side of the hero hue
REL_TOL = 0.10                        # relative tolerance for 0-1 metrics (resampling, crop noise)
ABS_TOL_LEVELS = 8                    # absolute tolerance for 0-255 level metrics
FLOORS = ("mean_saturation", "saturated_share", "near_black_share", "near_white_share",
          "white_point", "hero_hue_saturated_share")
CEILINGS = ("black_point",)
LEVEL_METRICS = ("black_point", "white_point")


def _byte(x: float) -> int:
    return int(x * 255 + 1e-9)


def _hist_share(mask: Image.Image) -> float:
    h = mask.histogram()
    total = sum(h)
    return h[255] / total if total else 0.0


def _bin(band: Image.Image, lo=None, hi=None) -> Image.Image:
    """255 where lo <= value <= hi, else 0."""
    lo = 0 if lo is None else lo
    hi = 255 if hi is None else hi
    return band.point([255 if lo <= i <= hi else 0 for i in range(256)])


def _percentile(hist, pct: float) -> int:
    total = sum(hist)
    target, run = total * pct / 100.0, 0
    for level, n in enumerate(hist):
        run += n
        if run >= target:
            return level
    return 255


def _hex_to_h(hex_color: str) -> int:
    text = hex_color.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"{hex_color!r} is not #RRGGBB")
    rgb = tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    return Image.new("RGB", (1, 1), rgb).convert("HSV").getpixel((0, 0))[0]


def working_copy(image: Image.Image) -> Image.Image:
    img = image.convert("RGB")
    if img.width > WORK_WIDTH:
        img = img.resize((WORK_WIDTH, max(1, round(img.height * WORK_WIDTH / img.width))),
                         Image.BOX)
    return img


def measure(path, hero: str | None = None) -> dict:
    with Image.open(path) as src:
        size = src.size
        img = working_copy(src)
    hue, sat, val = img.convert("HSV").split()
    s_hi = _bin(sat, _byte(SAT_MIN) + 1)
    v_ok = _bin(val, _byte(VAL_MIN) + 1)
    saturated = ImageChops.multiply(s_hi, v_ok)
    luma = img.convert("L").histogram()
    pixels = sum(luma)
    out = {
        "source_pixels": list(size),
        "work_pixels": [img.width, img.height],
        "mean_saturation": round(sum(i * n for i, n in enumerate(sat.histogram())) / pixels / 255, 4),
        "saturated_share": round(_hist_share(saturated), 4),
        "near_black_share": round(_hist_share(_bin(val, 0, _byte(BLACK_V) - 1)), 4),
        "near_white_share": round(_hist_share(ImageChops.multiply(
            _bin(val, _byte(WHITE_V) + 1), _bin(sat, 0, _byte(WHITE_S)))), 4),
        "black_point": _percentile(luma, 1.0),
        "white_point": _percentile(luma, 99.0),
    }
    if hero:
        target = _hex_to_h(hero)
        tol = round(HUE_TOL_DEG * 255 / 360)
        window = [255 if min((i - target) % 256, (target - i) % 256) <= tol else 0 for i in range(256)]
        out["hero_hue_saturated_share"] = round(_hist_share(
            ImageChops.multiply(saturated, hue.point(window))), 4)
    return out


def derive(ref_a: dict, ref_b: dict) -> dict:
    """The one derivation rule, applied to every metric the two references both carry.

    band      = max(|A - B|, tolerance)    tolerance = 10% of the weaker reference (0-1 metrics)
                                           or 8 levels (0-255 metrics)
    floor     = min(A, B) - band           ceiling = max(A, B) + band
    """
    thresholds = {}
    for name in FLOORS + CEILINGS:
        if name not in ref_a or name not in ref_b:
            continue
        a, b = ref_a[name], ref_b[name]
        weaker = min(a, b) if name in FLOORS else max(a, b)
        tol = ABS_TOL_LEVELS if name in LEVEL_METRICS else REL_TOL * weaker
        band = max(abs(a - b), tol)
        if name in FLOORS:
            bound = min(a, b) - band
        else:
            bound = max(a, b) + band
        bound = round(bound, 4) if name not in LEVEL_METRICS else int(bound)
        thresholds[name] = {"kind": "floor" if name in FLOORS else "ceiling", "bound": bound,
                            "va": a, "vb": b, "band": round(band, 4)}
    return thresholds


def load_thresholds(path=THRESHOLDS):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def evaluate(measures: dict, thresholds: dict) -> list:
    rows = []
    for name, rule in thresholds["thresholds"].items():
        if name not in measures:
            rows.append({"metric": name, "value": None, "kind": rule["kind"], "bound": rule["bound"],
                         "status": "SKIPPED", "why": "needs --hero" if name.startswith("hero") else "not measured"})
            continue
        value = measures[name]
        ok = value >= rule["bound"] if rule["kind"] == "floor" else value <= rule["bound"]
        rows.append({"metric": name, "value": value, "kind": rule["kind"], "bound": rule["bound"],
                     "status": "PASS" if ok else "FAIL"})
    return rows


def verdict(rows: list) -> str:
    return "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"


def _fmt(row):
    sign = ">=" if row["kind"] == "floor" else "<="
    value = "-" if row["value"] is None else row["value"]
    return f"  {row['status']:<7} {row['metric']:<26} {value!s:>8}  {sign} {row['bound']}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("image")
    c.add_argument("--hero")
    c.add_argument("--thresholds", default=str(THRESHOLDS))
    c.add_argument("--json", action="store_true")
    m = sub.add_parser("measure")
    m.add_argument("image")
    m.add_argument("--hero")
    k = sub.add_parser("calibrate")
    k.add_argument("va")
    k.add_argument("vb")
    k.add_argument("--hero-hex", action="append", default=[],
                   help="the references' own hero hex, once per reference, to derive the hero-hue floor")
    a = p.parse_args(argv)
    try:
        if a.cmd == "measure":
            print(json.dumps(measure(a.image, a.hero), indent=2))
            return 0
        if a.cmd == "calibrate":
            hero = a.hero_hex
            ma = measure(a.va, hero[0] if len(hero) > 0 else None)
            mb = measure(a.vb, hero[1] if len(hero) > 1 else (hero[0] if hero else None))
            print(json.dumps({"va": ma, "vb": mb, "thresholds": derive(ma, mb)}, indent=2))
            return 0
        data = load_thresholds(a.thresholds)
        if data is None:
            print(f"UNDETERMINED: cannot read thresholds {a.thresholds}")
            return 3
        measures = measure(a.image, a.hero)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 2
    rows = evaluate(measures, data)
    result = verdict(rows)
    if a.json:
        print(json.dumps({"verdict": result, "measures": measures, "rows": rows}, indent=2))
    else:
        print(f"PAGE_COLOR {result} {a.image}")
        for row in rows:
            print(_fmt(row))
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
