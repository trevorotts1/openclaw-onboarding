"""MG-044 reference suite tool: measure the C06 Hyperframes sample
layout polish (MG-016 sample, MG-044 workstream 3) on two rendered
frame-150 stills, before and after.

Usage:
  python3 measure-c06-polish.py <before.png> <after.png>

Prints a JSON object with, for each still:
- units_caption_bbox: the bounding box of the axis caption ("signups")
  pixels, identified by their exact blended color (ink at 0.55
  opacity over the fixture background);
- headline_ink_bottom_in_caption_columns: the lowest full-ink pixel
  row of the headline in the columns the caption occupies, so the
  caption's clearance from the headline descenders is a subtraction;
- fixture_label_accent_band: the bounding box of fixture-label accent
  pixels in the bottom region (y >= 900), where the month labels live;
- month_label_band: the fixed band the month labels occupy under the
  plot (plot bottom 900 plus the 16 px offset in the generator);
- fixture_label_overlaps_month_band: whether the fixture label's
  accent band intersects the month-label band vertically while also
  sharing its horizontal range.

The generator's own assertions (point presence at frames 0, 45, 75,
150 in runtime/tests/run-chart-components.ts) are the component
proof; this tool measures only the layout change.
"""

from __future__ import annotations

import json
import sys

from PIL import Image

INK = (25, 42, 56)
BG = (247, 244, 238)
ACCENT = (192, 74, 38)


def blend(fg, bg, alpha):
    return tuple(round(alpha * f + (1 - alpha) * b) for f, b in zip(fg, bg))


UNITS_COLOR = blend(INK, BG, 0.55)


def close(px, target, tol=8):
    return all(abs(a - b) <= tol for a, b in zip(px[:3], target))


def bbox_of(img, pred, region=None):
    w, h = img.size
    x0, y0, x1, y1 = region or (0, 0, w, h)
    pts = []
    px = img.load()
    for y in range(y0, min(y1, h)):
        for x in range(x0, min(x1, w)):
            if pred(px[x, y]):
                pts.append((x, y))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys),
            "pixels": len(pts)}


def measure(path, units_region, caption_css_top):
    img = Image.open(path).convert("RGB")
    # The caption's CSS region differs between the two layouts (the
    # whole point of the change), so each still is searched in its
    # own caption region; antialiased headline edges elsewhere in
    # the frame share the caption's blended color and must not be
    # counted as caption pixels.
    units = bbox_of(img, lambda p: close(p, UNITS_COLOR, 6), units_region)
    # Headline ink in the columns the caption occupies in this still.
    if units:
        cols = (units["x_min"], 120, units["x_max"] + 1, units["y_min"])
        headline = bbox_of(img, lambda p: close(p, INK, 10), cols)
    else:
        headline = None
    # Headline ink at or below the caption's CSS top, inside the
    # caption's own columns: the descender intrusion count. Before
    # the polish this is the "g" of "spring" dipping into the
    # caption zone; after, it must be zero.
    if units:
        intrusion = bbox_of(
            img,
            lambda p: close(p, INK, 10),
            (units["x_min"], caption_css_top, units["x_max"] + 1, 420),
        )
    else:
        intrusion = None
    fixture = bbox_of(img, lambda p: close(p, ACCENT, 10), (0, 900, 1920, 1080))
    month_band = {"y_min": 916, "y_max": 971}
    overlap = bool(
        fixture
        and fixture["y_min"] <= month_band["y_max"]
        and fixture["y_max"] >= month_band["y_min"]
    )
    return {
        "file": path,
        "units_caption_bbox": units,
        "headline_ink_bottom_above_caption": headline["y_max"] if headline else None,
        "caption_clearance_below_headline_px": (
            units["y_min"] - headline["y_max"] - 1
            if units and headline
            else None
        ),
        "headline_ink_at_or_below_caption_top_in_caption_columns": intrusion,
        "fixture_label_accent_band_bottom_region": fixture,
        "month_label_band": month_band,
        "fixture_label_overlaps_month_label_band": overlap,
        "fixture_label_clearance_below_month_band_px": (
            fixture["y_min"] - month_band["y_max"] - 1 if fixture and not overlap else None
        ),
    }


def main():
    before, after = sys.argv[1], sys.argv[2]
    # Caption regions from the two generator layouts: before, the
    # caption sat inside the plot's top edge at left plot.x + 16,
    # top plot.y + 22 (376, 322); after, it sits in the left rail,
    # right-aligned to end 32 px left of the axis, top plot.y + 36.
    print(json.dumps({
        "before": measure(before, (350, 300, 560, 400), 322),
        "after": measure(after, (100, 320, 345, 410), 336),
    }, indent=2))


if __name__ == "__main__":
    main()
