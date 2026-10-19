#!/usr/bin/env python3
"""Circle-image pipeline for Skill 71 design styles B (Circle) and C (Hybrid).

The image model only returns square or rectangular images. A circle slot is
therefore generated SQUARE (subject centered, safe margins), then this script
crops to a square, applies an anti-aliased circular alpha mask, optionally adds
a ring in a CLIENT brand color, and writes an RGBA PNG whose outside is fully
transparent. Any agent or page builder can place the file as an ordinary square
image and it reads as a round photo. Deterministic: same input and flags, same
bytes. Standard library plus Pillow. Centering is the image center unless --focus
(the image map's crop_focal) is given; --face-aware opts in to OpenCV face detection
when it happens to be installed (best effort, never required).

  circle_image.py apply SRC OUT [--size N] [--focus X,Y] [--face-aware] [--ring-style
        full|crescent --ring-color #RRGGBB [--ring-width-pct 3]
        [--ring-direction br|bl|tr|tl]]
  circle_image.py check FILE [--inventory image-inventory.json] [--force-circle]

`check` is the QC shape-compliance leg. For a slot whose inventory shape is
"circle" (or with --force-circle) it passes only when the file is a square RGBA
PNG with alpha 0 in all four corner regions and fully opaque alpha in the center.
For a rect slot it passes (nothing to enforce). Exit 0 pass, 1 fail, 2 bad input.

Ring rules: the ring color must be supplied (a brand color); there is no default
color, because the design styles never borrow the example's palette.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design_style  # noqa: E402

SUPERSAMPLE = 4
CORNER_FRAC = 0.08       # each corner region is 8% of the side, per axis
CENTER_FRAC = 0.20       # the opaque center region is the middle 20% per axis
# A circle inscribed in a square leaves 1 - pi/4 = 21.5% of the pixels outside;
# a crescent ring offset trims that a little. Anything outside this band is not
# a circle (a full-bleed rectangle is 0%, a tiny dot is ~100%).
TRANSPARENT_SHARE_MIN, TRANSPARENT_SHARE_MAX = 0.10, 0.35
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
DIRECTIONS = {"br": (1, 1), "bl": (-1, 1), "tr": (1, -1), "tl": (-1, -1)}


def parse_focus(value):
    """'0.5,0.4', [0.5, 0.4] or {"x": 0.5, "y": 0.4} -> (0.5, 0.4), or None.

    Fractions of width/height; the image map's crop_focal field carries this.
    """
    if value in (None, ""):
        return None
    try:
        if isinstance(value, dict):
            x, y = float(value["x"]), float(value["y"])
        elif isinstance(value, (list, tuple)):
            x, y = (float(v) for v in value)
        else:
            x, y = (float(v) for v in str(value).split(","))
    except (ValueError, KeyError, TypeError):
        raise ValueError(f"focus must be x,y fractions, got {value!r}")
    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError(f"focus fractions must be within 0..1, got {value!r}")
    return x, y


def detect_face_focus(im):
    """Center of the largest face as (x, y) fractions, or None (best effort)."""
    try:
        import cv2
        import numpy as np
        gray = cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(gray.shape[1] // 12,) * 2)
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        return (x + w / 2) / gray.shape[1], (y + h / 2) / gray.shape[0]
    except Exception:  # cv2 absent or detector failed: caller falls back to center
        return None


def square_crop(im, focus=None):
    """Largest square crop, centered on focus (fractions) or the image center.

    The crop never leaves the image: the window is clamped at the edges. A
    square source passes through unchanged.
    """
    w, h = im.size
    side = min(w, h)
    cx, cy = (focus[0] * w, focus[1] * h) if focus else (w / 2, h / 2)
    left = int(round(min(max(cx - side / 2, 0), w - side)))
    top = int(round(min(max(cy - side / 2, 0), h - side)))
    return im.crop((left, top, left + side, top + side))


def _disc(size, center, radius):
    """Anti-aliased filled-circle alpha mask (mode L) via 4x supersampling."""
    big = size * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    cx, cy = center[0] * SUPERSAMPLE, center[1] * SUPERSAMPLE
    r = radius * SUPERSAMPLE
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def make_circle(src, size=None, focus=None, ring=None):
    """Return an RGBA square: the photo masked to a circle, transparent outside.

    ring: None, or {"style": "full"|"crescent", "color": "#RRGGBB",
    "width_pct": 3, "direction": "br"}. 'full' draws a band around the photo;
    'crescent' draws the same disc offset behind the photo so only a partial ring
    shows on one side (the Oprah-design look). The canvas stays square and the
    four corners stay transparent in every mode.
    """
    im = square_crop(src.convert("RGB"), focus)
    side = size or im.size[0]
    pct = float((ring or {}).get("width_pct", 3))
    band = int(round(side * pct / 100)) if ring else 0
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    if ring:
        color = ring.get("color")
        if not isinstance(color, str) or not HEX.match(color):
            raise ValueError("ring color must be a client brand color as #RRGGBB "
                             "(there is no default; never reuse the example's colors)")
        style = ring.get("style", "full")
        if style not in ("full", "crescent"):
            raise ValueError(f"ring style must be full or crescent, got {style!r}")
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        if style == "full":
            diameter = side - 2 * band
            photo_c, ring_c = (side / 2, side / 2), (side / 2, side / 2)
            ring_r = side / 2
        else:
            direction = ring.get("direction", "br")
            if direction not in DIRECTIONS:
                raise ValueError(f"ring direction must be one of {sorted(DIRECTIONS)}")
            sx, sy = DIRECTIONS[direction]
            diameter = side - band
            photo_c = (side / 2 - sx * band / 2, side / 2 - sy * band / 2)
            ring_c = (side / 2 + sx * band / 2, side / 2 + sy * band / 2)
            ring_r = diameter / 2
        canvas.paste(Image.new("RGBA", (side, side), rgb + (255,)), (0, 0),
                     _disc(side, ring_c, ring_r))
    else:
        diameter = side
        photo_c = (side / 2, side / 2)
    # The whole square crop is scaled to the disc diameter, then masked to the disc.
    d = int(round(diameter))
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    layer.paste(im.resize((d, d), Image.LANCZOS).convert("RGBA"),
                (int(round(photo_c[0] - d / 2)), int(round(photo_c[1] - d / 2))))
    layer.putalpha(_disc(side, photo_c, d / 2))
    canvas.alpha_composite(layer)
    return canvas


def alpha_stats(path):
    """Alpha facts for one file: corners, center, transparent share, mode, size."""
    with Image.open(path) as im:
        mode, (w, h), fmt = im.mode, im.size, im.format
        has_alpha = mode in ("RGBA", "LA") or (mode == "P" and "transparency" in im.info)
        alpha = im.convert("RGBA").getchannel("A")
    cw, ch = max(1, int(w * CORNER_FRAC)), max(1, int(h * CORNER_FRAC))
    boxes = {"top_left": (0, 0, cw, ch), "top_right": (w - cw, 0, w, ch),
             "bottom_left": (0, h - ch, cw, h), "bottom_right": (w - cw, h - ch, w, h)}
    corners = {name: alpha.crop(box).getextrema()[1] for name, box in boxes.items()}
    mx, my = int(w * (0.5 - CENTER_FRAC / 2)), int(h * (0.5 - CENTER_FRAC / 2))
    center_min = alpha.crop((mx, my, w - mx, h - my)).getextrema()[0]
    hist = alpha.histogram()
    return {"mode": mode, "format": fmt, "size": [w, h], "has_alpha": has_alpha,
            "corner_max_alpha": corners, "center_min_alpha": center_min,
            "transparent_share": round(hist[0] / (w * h), 4)}


def shape_failures(stats):
    """Named reasons a file is not a compliant circle PNG; empty means pass."""
    out = []
    w, h = stats["size"]
    if stats["format"] != "PNG":
        out.append(f"not a PNG (format {stats['format']}): a circle image is delivered as a PNG")
    if not stats["has_alpha"]:
        out.append(f"no alpha channel (mode {stats['mode']}): a square without transparency "
                   "is not a circle image")
    if abs(w - h) > 1:
        out.append(f"not square: {w}x{h}")
    bad = {k: v for k, v in stats["corner_max_alpha"].items() if v != 0}
    if bad:
        out.append("corner regions are not fully transparent (alpha must be 0): "
                   + ", ".join(f"{k}={v}" for k, v in sorted(bad.items())))
    if stats["center_min_alpha"] != 255:
        out.append(f"center is not fully opaque (min alpha {stats['center_min_alpha']})")
    share = stats["transparent_share"]
    if not TRANSPARENT_SHARE_MIN <= share <= TRANSPARENT_SHARE_MAX:
        out.append(f"transparent share {share:.1%} is outside the circle band "
                   f"{TRANSPARENT_SHARE_MIN:.0%} to {TRANSPARENT_SHARE_MAX:.0%}")
    return out


def _slot_number(value):
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def inventory_entry(inventory_path, name):
    """The inventory entry whose id number matches a file name or item id, else {}."""
    want = _slot_number(Path(str(name)).stem)
    for item in design_style.inventory_slots(inventory_path):
        if want is not None and _slot_number(item.get("id")) == want:
            return item
    return {}


def entry_shape(entry):
    """"circle" or "rect" for an inventory entry; `mask: circle` (composition library) counts."""
    return entry.get("shape") or entry.get("mask") or "rect"


def cmd_apply(a):
    ring = None
    if a.ring_style or a.ring_color:
        ring = {"style": a.ring_style or "full", "color": a.ring_color,
                "width_pct": a.ring_width_pct, "direction": a.ring_direction}
    try:
        src = Image.open(a.src)
        focus = parse_focus(a.focus) or (detect_face_focus(src) if a.face_aware else None)
        out = make_circle(src, a.size, focus, ring)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 2
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out, format="PNG")
    stats = alpha_stats(a.out)
    print(f"CIRCLE {a.out} size={stats['size'][0]}x{stats['size'][1]} mode={stats['mode']} "
          f"transparent_share={stats['transparent_share']} "
          f"center_min_alpha={stats['center_min_alpha']} "
          f"corners={stats['corner_max_alpha']}")
    return 0


def cmd_check(a):
    try:
        shape = "circle" if a.force_circle else (
            entry_shape(inventory_entry(a.inventory, a.file)) if a.inventory else "rect")
        stats = alpha_stats(a.file)
    except (OSError, ValueError) as exc:
        print(f"FAIL: could not read input: {exc}")
        return 2
    if shape != "circle":
        print(f"PASS: {Path(a.file).name} is a rect slot; no shape rule applies")
        return 0
    failures = shape_failures(stats)
    if failures:
        print(f"FAIL: {Path(a.file).name} is a circle slot but is not a compliant circle PNG")
        for line in failures:
            print(f"- {line}")
        return 1
    print(f"PASS: {Path(a.file).name} is a circle PNG: transparent corners, opaque center, "
          f"{stats['transparent_share']:.1%} transparent")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("apply")
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=None, help="output square side in px (default: crop side)")
    ap.add_argument("--focus", default=None, help="x,y fractions of the subject (default: image center)")
    ap.add_argument("--face-aware", action="store_true",
                    help="center on the largest detected face when OpenCV is installed "
                         "(output then depends on the install; pass --focus for byte-stable runs)")
    ap.add_argument("--ring-style", choices=["full", "crescent"], default=None)
    ap.add_argument("--ring-color", default=None, help="client brand color #RRGGBB (required with a ring)")
    ap.add_argument("--ring-width-pct", type=float, default=3.0)
    ap.add_argument("--ring-direction", choices=sorted(DIRECTIONS), default="br")
    ck = sub.add_parser("check")
    ck.add_argument("file")
    ck.add_argument("--inventory", default=None)
    ck.add_argument("--force-circle", action="store_true")
    a = p.parse_args(argv)
    return cmd_apply(a) if a.cmd == "apply" else cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
