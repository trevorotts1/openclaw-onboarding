#!/usr/bin/env python3
"""Signature-look screen for generated images (Skill 71, Items 8 and 9,
as amended by Amendment 6, Parts B4 and D).

This is the full deterministic pixel screen for a run's generated images.
For each image it computes, with Pillow only:

  - mean HSV saturation (0-1)                       [original measure]
  - standard deviation of luminance (0-255 scale)   [original measure]
  - sharpness: variance of the FIND_EDGES (Laplacian-approximating)
    convolution over the grayscale 256px working copy
  - colorfulness: the Hasler-Susstrunk metric over the rg / yb opponent
    channels of the 256px working copy
  - an 8x8 average hash, used for near-duplicate detection (below)
  - the image's actual aspect ratio and pixel dimensions (below)

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

Blend Profile handling (Amendment 6, Part B4): when --bible names the
run's Page Visual Bible, its Secret Sauce Blend Profile is read. The
saturation and colorfulness floors are color floors: when the profile's
hero_color_chroma dimension is marked SUPPRESS or ADAPT (at page level in
the bible, or per image in the inventory entry's own blend profile),
those floors are N/A for the image and can never fail it: a correct
monochrome or restrained-style image must not fail a color floor. The
decision is printed per image. With no bible (and no per-image profile),
behavior is exactly as before, including the uncalibrated WARN behavior.

Per-family, per-posture floors (Calibration Redesign, Rulings 1 and 2,
2026-10-14): the brand file's grade block may carry a nested `floors`
structure keyed by rendering family (photographic, cinematic,
visual-artist). Each family carries a FULL class (color floors), an
ADAPT class (a two-sided saturation/colorfulness band plus a luma_std
tonal floor; a band recorded `provisional` WARNs instead of failing),
and non-color floors (luma_std, sharpness) pooled across the family's
postures. The validator resolves each image's family (inventory
`active_family`, default photographic) and posture class (hero_color_
chroma posture, per image then bible; unrecorded posture resolves to
the family's FULL floors with a NOTE, never silently N/A) and applies
exactly that class's floors. SUPPRESS keeps color floors N/A. A family
with no calibrated floors is WARN-uncalibrated, never a silent pass:
brand calibration requires per-family anchors for every family the
brand uses (Ruling 2; no family-scoped calibration mode exists).
Transition: when a family has no nested block, the legacy flat grade
keys (grade.min_*) stand in as the photographic family's FULL color
floors and non-color floors, so pre-redesign brand files behave
exactly as before.

Option B selectivity (Calibration Redesign, Ruling 3): for FULL-posture
images the screen also measures the protected region: near-neutral
pixels (HSV saturation <= 0.12) plus the skin-hue band. It reports the
protected-region mean saturation and the saturated-intrusion share
(protected-territory skin-band pixels pushed past the protected cap).
The metric is WARN-only, whether or not an approved ceiling exists
(grade.max_protected_saturation, or the family's FULL
max_protected_saturation): over the ceiling the screen prints a WARN
naming the measurement and the ceiling (a global color wash colonizes
neutrals and skin; Sauce sections 2 and 23.2), and selective
hyperchroma at any hero intensity passes; with no ceiling the WARN
names itself uncalibrated Option B. Writing the ceiling into the brand
file does not change its enforcement status (owner ruling S71-OPTION-B,
Resolution A, 2026-10-16: the record's WARN-only status governs; the
code was conformed to it). When the protected
mask covers almost none of the working copy the metric reports N/A,
never a fabricated pass. This pixel proxy does not replace the
doctrine's enforcement of record: selective saturation is judged at the
Item 12 judgment gate (Guide section 13); the ceiling here is a screen,
not the judgment.

Unconditional checks (no threshold to calibrate; these always apply):
  - Near-duplicate / cloned-shot detection: for every pair of images in
    the invocation set, an average-hash Hamming distance of 4 or less is
    a FAIL ("possible duplicate or near-identical shot"), UNLESS the pair
    is declared an intentional continuity series in the inventory passed
    with --inventory: both entries share the same `continuity_group`
    string, or either entry's `continuity_group` list names the other
    entry's id. Without --inventory no continuity exemption can apply.
    (Amendment 6 Part B4 retains this hash check as a tripwire only; the
    guide's register-based distinctness check below is the enforcement
    layer, added with the Item 10 follow-up.)
  - Distinctness register (only with --inventory; Amendment 6 Part B4):
    the guide's distinctness rule is register-based, not pixel-based.
    For every pair of inventory entries that record a representation
    register (skin tone + hairstyle + facial-hair state, read from the
    entry or its people/subjects), an IDENTICAL combination is a FAIL
    unless continuity is recorded for the pair (a shared
    continuity_group, or a continuity_rationale on either entry): the
    same illustrative person may not silently recur. Separately, two
    ADJACENT entries (inventory order) whose recorded distinctness
    registers are identical across every recorded dimension (shot,
    angle, placement, lighting mood, expression, dominant color,
    treatment type, and the representation register) FAIL as
    neighboring assets that do not differ in any recorded dimension.
  - Native ratio + crop plan (only with --inventory; REWORKED by
    Amendment 6, replacing the original 2 percent slot-ratio truth
    check, which failed exactly the outputs the image guide prescribes):
    the guide sanctions generating at the entry's closest supported
    NATIVE ratio plus a recorded crop plan, and mandates N43 remapping
    on the default route (5:4 to 4:3, 4:5 to 3:4, 2:1 to 16:9, 1:2 to
    9:16; 3:1, 1:3, and 9:21 stay on the legacy route unmapped). An
    image FAILS this check only when its rendered ratio matches NEITHER
    the entry's recorded native ratio (or the wireframe/slot ratio when
    no native ratio is recorded) NOR any N43 remapping of those recorded
    ratios, AND the entry records no crop plan that bridges render ratio
    to delivery. A recorded crop plan is cited in the pass line, not
    silently assumed. Separately, when the checked file IS the entry's
    delivery file (its name matches the entry's delivery/final filename)
    and the entry records delivery dimensions, the file's actual pixel
    dimensions must equal them exactly. Ratio comparisons use a 1
    percent pixel-rounding tolerance (integer pixel dimensions cannot
    express every rational ratio exactly); this tolerance is a
    measurement allowance, not a slot-truth rule. An image with no
    matching entry, or an entry with no recorded ratio data, is a WARN
    line, not a FAIL.

The production gate (stage_gate.py, Item 8's close rule) is what blocks
a production image-generation-qc close while thresholds are null; this
script keeps the historical WARN-and-measure behavior for uncalibrated
metrics so test runs can still see the numbers.

CLI (original shape, two optional inputs added by Items 9/Amendment 6):
  validate_image_grade.py <image> [<image> ...] --brand <brand.json>
      [--inventory <image-inventory.json>]
      [--bible <page-visual-bible.json>]

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
RATIO_TOLERANCE = 0.01  # pixel-rounding allowance for ratio equality
DUPLICATE_MAX_HAMMING = 4  # 8x8 average hash, per Item 9

# (metric key in the measures dict, brand grade key, display format)
THRESHOLD_METRICS = [
    ("mean_saturation", "min_mean_saturation", "{:.4f}"),
    ("luma_std", "min_luma_std", "{:.2f}"),
    ("sharpness", "min_sharpness", "{:.2f}"),
    ("colorfulness", "min_colorfulness", "{:.2f}"),
]
# The color floors, subject to Blend Profile SUPPRESS/ADAPT handling.
COLOR_METRICS = {"mean_saturation", "colorfulness"}
# Blend Profile dimension that governs the color floors.
COLOR_DIMENSION = "hero_color_chroma"

# Rendering families (Page Art Direction Router). Brand calibration is
# per family (Ruling 2): every family the brand uses needs its own
# anchors and floors; there is no family-scoped calibration mode.
FAMILIES = ("photographic", "cinematic", "visual-artist")
DEFAULT_FAMILY = "photographic"
POSTURE_CLASSES = ("FULL", "ADAPT", "SUPPRESS", "UNRECORDED")

# Option B protected-region selectivity (Ruling 3). The protected mask
# is near-neutral pixels plus the skin-hue band, per Sauce section 2's
# protected list (neutrals, skin, whites, blacks, shadow detail). The
# hue-band skin heuristic is crude by design admission (the proposal's
# honest limits): it is a screen proxy, and the Item 12 judgment gate
# remains the enforcement of record for selective saturation.
NEUTRAL_SAT_MAX = 0.12       # HSV saturation at or below: near-neutral
SKIN_HUE_MIN = 0.03          # skin-hue band, warm orange-brown sector
SKIN_HUE_MAX = 0.13          # (colorsys hue fraction, ~11 to ~47 degrees)
SKIN_VALUE_MIN = 0.25
SKIN_VALUE_MAX = 0.95
PROTECTED_SKIN_SAT_MAX = 0.60  # skin-band pixels at or below: protected
MIN_PROTECTED_SHARE = 0.005  # mask below 0.5% of pixels: report N/A


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


def load_grade(brand_path):
    """Return the brand file's whole grade block (validated as a dict)."""
    try:
        brand = json.loads(Path(brand_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: could not read brand file {brand_path}: {exc}")
    grade = brand.get("grade")
    if not isinstance(grade, dict):
        raise SystemExit(f"FAIL: brand file {brand_path} has no grade object.")
    return grade


def _num(value):
    """A floor value: a number, or None when absent/null/not numeric."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def floor_plan(grade):
    """Normalize a grade block into per-family, per-posture floor blocks.

    Returns {family: {"full": dict|None, "adapt": dict|None,
    "noncolor": dict|None}} with every FAMILIES key present. A block is
    None when the brand file records nothing for it (uncalibrated).
    Transition: a family with no nested `floors` block at all inherits
    the legacy flat grade keys as its FULL color floors and non-color
    floors; photographic is the only family that can inherit in
    practice, because pre-redesign brand files describe the brand's one
    calibrated surface. (A nested block that exists but is empty does
    NOT inherit: empty is a recorded state, not an absence.)
    """
    floors = grade.get("floors")
    if not isinstance(floors, dict):
        floors = {}
    plan = {}
    for family in FAMILIES:
        block = floors.get(family)
        if not isinstance(block, dict):
            block = None
        full = adapt = noncolor = None
        if block is not None:
            if isinstance(block.get("full"), dict):
                full = block["full"]
            if isinstance(block.get("adapt"), dict):
                adapt = block["adapt"]
            if isinstance(block.get("noncolor"), dict):
                noncolor = block["noncolor"]
        plan[family] = {"full": full, "adapt": adapt, "noncolor": noncolor}
    if floors.get(DEFAULT_FAMILY) is None:
        legacy_full = {}
        for metric_key, grade_key, _fmt in THRESHOLD_METRICS:
            if metric_key in COLOR_METRICS:
                value = _num(grade.get(grade_key))
                if value is not None:
                    legacy_full[grade_key] = value
        legacy_noncolor = {}
        for metric_key, grade_key, _fmt in THRESHOLD_METRICS:
            if metric_key not in COLOR_METRICS:
                value = _num(grade.get(grade_key))
                if value is not None:
                    legacy_noncolor[grade_key] = value
        if legacy_full and plan[DEFAULT_FAMILY]["full"] is None:
            plan[DEFAULT_FAMILY]["full"] = legacy_full
        if legacy_noncolor and plan[DEFAULT_FAMILY]["noncolor"] is None:
            plan[DEFAULT_FAMILY]["noncolor"] = legacy_noncolor
    return plan


def protected_ceiling(grade, plan, family):
    """The approved Option B ceiling for a family, or None.

    The family's FULL max_protected_saturation wins; the brand-wide
    grade.max_protected_saturation is the fallback. Null/absent means
    uncalibrated. Either way Option B is WARN-only: the ceiling is a
    screen value the WARN names, never a failure threshold (Ruling 3;
    owner ruling S71-OPTION-B, Resolution A, 2026-10-16).
    """
    full = plan.get(family, {}).get("full") or {}
    value = _num(full.get("max_protected_saturation"))
    if value is not None:
        return value
    return _num(grade.get("max_protected_saturation"))


def family_of(entry):
    """(family, recorded) for an inventory entry.

    The recorded active_family when it names a Router family; otherwise
    the brand default (photographic) with recorded=False so the caller
    can print the NOTE Part 1.5 requires.
    """
    if isinstance(entry, dict):
        fam = entry.get("active_family")
        if isinstance(fam, str) and fam.strip().lower() in FAMILIES:
            return fam.strip().lower(), True
    return DEFAULT_FAMILY, False


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
    protected_count = 0
    protected_sat_sum = 0.0
    intrusion_count = 0
    for r, g, b in pixels:
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        total_sat += s
        # Option B protected region (Ruling 3): near-neutral pixels plus
        # the skin-hue band are the surfaces Sauce section 2 protects.
        # A skin-band pixel pushed past PROTECTED_SKIN_SAT_MAX is counted
        # as saturated intrusion (protected territory colonized by chroma)
        # instead of joining the mask. These numbers are a pixel proxy
        # only; selective saturation itself is enforced at the Item 12
        # judgment gate (Guide section 13), not by this screen.
        skin_band = (SKIN_HUE_MIN <= h <= SKIN_HUE_MAX
                     and SKIN_VALUE_MIN <= v <= SKIN_VALUE_MAX)
        if s <= NEUTRAL_SAT_MAX or (skin_band and s <= PROTECTED_SKIN_SAT_MAX):
            protected_count += 1
            protected_sat_sum += s
        elif skin_band:
            intrusion_count += 1
    mean_sat = total_sat / n
    protected_share = protected_count / n
    protected_sat = (protected_sat_sum / protected_count) if protected_count else None

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
        # Option B (Ruling 3): protected_sat is None when the protected
        # mask is empty; callers must report N/A, never 0-as-pass.
        "protected_sat": protected_sat,
        "protected_share": protected_share,
        "intrusion_share": intrusion_count / n,
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


# N43 remapping on the default route (image guide, per Amendment 6 B4):
# the requested ratio on the left is generated at the ratio on the right.
# 3:1, 1:3, and 9:21 use the legacy route and are NOT remapped.
N43_MAP = {
    (5, 4): (4, 3),
    (4, 5): (3, 4),
    (2, 1): (16, 9),
    (1, 2): (9, 16),
}


def n43_remap(ratio):
    """The N43-remapped value of a ratio, or None if it is not remapped."""
    if not ratio:
        return None
    for (a, b), (c, d) in N43_MAP.items():
        if abs(ratio - a / b) < 1e-9:
            return c / d
    return None


def recorded_ratios(entry):
    """Return (native_ratio, slot_ratio) recorded on an inventory entry.

    Native (authoritative generation) ratio fields win for the native
    slot; the wireframe/slot ratio is the requested frame the native
    ratio serves. Either may be absent.
    """
    native = None
    for key in ("native_aspect_ratio", "native_ratio", "generation_aspect_ratio",
                "aspect_ratio"):
        if entry.get(key) is not None:
            native = parse_ratio(entry.get(key))
            if native:
                break
    slot = None
    for key in ("slot_ratio", "wireframe_ratio", "slot_aspect_ratio",
                "intended_ratio"):
        if entry.get(key) is not None:
            slot = parse_ratio(entry.get(key))
            if slot:
                break
    if slot is None and entry.get("desktop_slot_px") is not None:
        slot = parse_ratio(entry.get("desktop_slot_px"))
    if native is None and slot is None:
        # Declared pixel geometry on the entry reads as its frame ratio.
        for wkey, hkey in (("slot_width", "slot_height"), ("width", "height")):
            w, h = entry.get(wkey), entry.get(hkey)
            if isinstance(w, (int, float)) and isinstance(h, (int, float)) and h:
                slot = float(w) / float(h)
                break
    return native, slot


def crop_plan(entry):
    """The entry's recorded crop plan text, or None."""
    for key in ("crop_plan", "crop"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict) and value:
            return json.dumps(value, sort_keys=True)
    plan = entry.get("technical_plan")
    if isinstance(plan, dict):
        inner = plan.get("crop_plan") or plan.get("crop")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
    if isinstance(plan, str) and "crop" in plan.lower():
        return plan.strip()
    return None


def delivery_expectation(entry, filename):
    """(width, height) the file must have if it IS the delivery export, else None.

    Applies only when the checked file's name matches the entry's
    delivery/final filename; masters are not held to delivery geometry.
    """
    names = set()
    for key in ("delivery_filename", "delivery_file", "final_filename", "filename"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            names.add(Path(value.strip()).name)
    if filename not in names:
        return None
    for wkey, hkey in (("delivery_width", "delivery_height"),
                       ("export_width", "export_height"),
                       ("width", "height")):
        w, h = entry.get(wkey), entry.get(hkey)
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            return (w, h)
    dims = entry.get("delivery_dimensions") or entry.get("delivery_size")
    if isinstance(dims, (list, tuple)) and len(dims) == 2:
        return (int(dims[0]), int(dims[1]))
    if isinstance(dims, str) and "x" in dims.lower():
        a, _, b = dims.lower().partition("x")
        try:
            return (int(a), int(b))
        except ValueError:
            return None
    plan = entry.get("technical_plan")
    if isinstance(plan, dict):
        w = plan.get("delivery_width") or plan.get("exact_delivery_width")
        h = plan.get("delivery_height") or plan.get("exact_delivery_height")
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            return (w, h)
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


def _mode_of(value):
    """Normalize a blend dimension value to FULL/ADAPT/SUPPRESS or None."""
    if isinstance(value, str):
        text = value.strip().upper()
        return text if text in ("FULL", "ADAPT", "SUPPRESS") else None
    if isinstance(value, dict):
        for key in ("mode", "status", "value", "decision"):
            mode = _mode_of(value.get(key))
            if mode:
                return mode
    return None


def blend_profile_of(container):
    """Extract a {dimension: mode} blend profile dict from a bible or entry."""
    if not isinstance(container, dict):
        return {}
    profile = None
    for key in ("SECRET_SAUCE_BLEND_PROFILE", "secret_sauce_blend_profile",
                "blend_profile", "sauce_blend_profile", "blend"):
        if isinstance(container.get(key), dict):
            profile = container[key]
            break
    if profile is None:
        # The container itself may be the profile (dimension keys at top).
        if any(_mode_of(v) for v in container.values()):
            profile = container
        else:
            return {}
    out = {}
    for dim, value in profile.items():
        mode = _mode_of(value)
        if mode:
            out[str(dim).strip().lower()] = mode
    return out


def load_bible_profile(path):
    """The page-level blend profile from a Page Visual Bible JSON, or {}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: could not read bible {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: bible {path} is not a JSON object.")
    profile = blend_profile_of(data)
    if not profile:
        # One level of nesting is common (e.g. {"page_visual_bible": {...}}).
        for value in data.values():
            if isinstance(value, dict):
                profile = blend_profile_of(value)
                if profile:
                    break
    return profile


def posture_resolution(entry, bible_profile):
    """(posture_class, source) for an image (Calibration Redesign 1.5).

    The posture class is the recorded mode of hero_color_chroma,
    per-image (inventory entry) first, then page-level (bible). FULL,
    ADAPT, and SUPPRESS return as recorded; when nothing is recorded
    anywhere the class is UNRECORDED, which the validator treats as the
    family's FULL class (floors apply, with a NOTE): never silently N/A.
    """
    if entry is not None:
        mode = blend_profile_of(entry).get(COLOR_DIMENSION)
        if mode in POSTURE_CLASSES[:3]:
            return mode, f"inventory blend profile {COLOR_DIMENSION}={mode}"
    mode = bible_profile.get(COLOR_DIMENSION)
    if mode in POSTURE_CLASSES[:3]:
        return mode, f"bible blend profile {COLOR_DIMENSION}={mode}"
    return "UNRECORDED", ""


def color_floors_na(entry, bible_profile):
    """(True, source) if the color floors are N/A for this image per B4.

    SUPPRESS or ADAPT on hero_color_chroma, per-image (inventory entry)
    first, then page-level (bible). No profile anywhere: floors apply.
    Retained for compatibility; posture_resolution() is the redesign's
    resolver and agrees with this on SUPPRESS/ADAPT.
    """
    posture, source = posture_resolution(entry, bible_profile)
    if posture in ("SUPPRESS", "ADAPT"):
        return True, source
    return False, ""


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


# ------------------------------------------------ distinctness register

def _register_value(container, *keys):
    if not isinstance(container, dict):
        return None
    for key in keys:
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def representation_register(entry):
    """(skin_tone, hairstyle, facial_hair) recorded for an entry, or None.

    Read from the entry's representation block or its first
    people/subjects record that carries the fields. An entry with no
    recorded skin tone and hairstyle has no register and is skipped:
    the check governs recorded registers, it does not invent them.
    """
    if not isinstance(entry, dict):
        return None
    sources = []
    if isinstance(entry.get("representation"), dict):
        sources.append(entry["representation"])
    for key in ("people", "subjects", "casting"):
        value = entry.get(key)
        if isinstance(value, list):
            sources += [s for s in value if isinstance(s, dict)]
        elif isinstance(value, dict):
            sources.append(value)
    sources.append(entry)
    for src in sources:
        skin = _register_value(src, "skin_tone", "skin")
        hair = _register_value(src, "hairstyle", "hair", "hair_construction")
        if skin and hair:
            facial = _register_value(src, "facial_hair", "facial_hair_state") or ""
            return (skin, hair, facial)
    return None


def distinctness_register(entry):
    """The entry's recorded distinctness dimensions (guide section 3).

    From a distinctness_register object when present, else flat fields.
    Only dimensions actually recorded participate.
    """
    if not isinstance(entry, dict):
        return {}
    reg = entry.get("distinctness_register")
    if not isinstance(reg, dict):
        reg = entry
    out = {}
    for key in ("shot", "shot_distance", "angle", "viewpoint", "placement",
                "subject_zone", "lighting_mood", "lighting", "expression",
                "dominant_color", "treatment_type", "visual_treatment_type"):
        value = _register_value(reg, key)
        if value:
            out[key] = value
    rep = representation_register(entry)
    if rep:
        out["representation"] = "|".join(rep)
    return out


def continuity_recorded(entry_a, entry_b):
    """Continuity for a pair: declared group (as for the hash tripwire)
    or a recorded continuity rationale on either entry."""
    if continuity_exempt(entry_a, entry_b):
        return True
    for entry in (entry_a, entry_b):
        for key in ("continuity_rationale", "continuity_reason"):
            value = entry.get(key) if isinstance(entry, dict) else None
            if isinstance(value, str) and value.strip():
                return True
        reg = entry.get("distinctness_register") if isinstance(entry, dict) else None
        if isinstance(reg, dict):
            value = reg.get("continuity_rationale") or reg.get("continuity")
            if isinstance(value, str) and value.strip():
                return True
    return False


def register_failures(inventory):
    """Amendment 6 Part B4: the register check is the enforcement layer.

    inventory is the {normalized_id: entry} map from load_inventory,
    whose iteration order is the inventory's own order.
    """
    failures = []
    items = list(inventory.items())
    registers = {eid: representation_register(e) for eid, e in items}
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            id_a, entry_a = items[i]
            id_b, entry_b = items[j]
            reg_a, reg_b = registers[id_a], registers[id_b]
            if reg_a is not None and reg_a == reg_b:
                if not continuity_recorded(entry_a, entry_b):
                    failures.append(
                        f"register: {id_a} / {id_b}: identical representation "
                        f"register (skin tone + hairstyle + facial-hair combination "
                        f"{reg_a[0]} / {reg_a[1]} / {reg_a[2] or 'none recorded'}) "
                        "with no recorded continuity; the guide prohibits a repeated "
                        "illustrative combination without a continuity rationale "
                        "(Amendment 6, Part B4)")
    for i in range(len(items) - 1):
        id_a, entry_a = items[i]
        id_b, entry_b = items[i + 1]
        dist_a, dist_b = distinctness_register(entry_a), distinctness_register(entry_b)
        if len(dist_a) >= 3 and dist_a == dist_b:
            failures.append(
                f"register: {id_a} / {id_b}: neighboring assets record identical "
                "distinctness registers across every recorded dimension (shot, "
                "angle, placement, lighting, expression, color, treatment, "
                "representation); neighboring assets must differ in several "
                "recorded dimensions (Amendment 6, Part B4)")
    return failures


def ratio_close(actual, expected):
    return expected and abs(actual - expected) / expected <= RATIO_TOLERANCE


def _floor_check(block, locator, metric_key, grade_key, fmt, m, reasons, uncal):
    """One floor: FAIL reason when below, uncal label when not calibrated."""
    value = _num(block.get(grade_key)) if isinstance(block, dict) else None
    if value is None:
        uncal.append(f"{locator}{grade_key}")
        return
    if m[metric_key] < value:
        reasons.append(f"{metric_key} {fmt.format(m[metric_key])} < "
                       f"{locator}{grade_key} {value}")


def apply_grade_floors(name, m, family, posture, posture_source,
                       fam_blocks, nested, ceiling):
    """Apply one family's per-posture floors to one image (Redesign 1.5).

    Prints NOTE/WARN lines for N/A decisions, provisional bands,
    unrecorded postures, and the Option B selectivity screen. Returns
    (fail_reasons, uncalibrated_flag). SUPPRESS: color floors N/A.
    ADAPT: the recorded band (or legacy N/A when no band is calibrated).
    FULL and UNRECORDED: the family's FULL color floors; unrecorded
    posture is never silently N/A.
    """
    reasons = []
    uncal = []
    fam_loc = f"grade.floors.{family}." if nested else "grade."
    full = fam_blocks.get("full")
    adapt = fam_blocks.get("adapt")
    noncolor = fam_blocks.get("noncolor")
    family_calibrated = any(b is not None for b in (full, adapt, noncolor))

    if not family_calibrated:
        print(f"WARN: uncalibrated, family not calibrated: {name}: family "
              f"{family} has no floors in this brand file's grade block. "
              "Color and non-color floors were not applied. Brand "
              "calibration requires per-family anchors for every family "
              "the brand uses (Ruling 2); production close is refused "
              "for uncalibrated families (Item 8 close rule).")
        return reasons, True

    if posture == "SUPPRESS":
        print(f"NOTE: {name}: saturation/colorfulness floors are N/A "
              f"({posture_source}); a SUPPRESS dimension is never a "
              "failure (Amendment 6, Part B4)")
    elif posture == "ADAPT":
        if adapt is None:
            print(f"NOTE: {name}: saturation/colorfulness floors are N/A "
                  f"({posture_source}); no ADAPT band is calibrated for "
                  f"family {family}, so the legacy B4 handling applies "
                  "and the band's absence is recorded, not silent")
        else:
            provisional = bool(adapt.get("provisional"))
            band_reasons = []
            band_loc = f"{fam_loc}adapt."
            for metric_key, lo_key, hi_key, fmt in (
                    ("mean_saturation", "min_mean_saturation",
                     "max_mean_saturation", "{:.4f}"),
                    ("colorfulness", "min_colorfulness",
                     "max_colorfulness", "{:.2f}")):
                lo = _num(adapt.get(lo_key))
                hi = _num(adapt.get(hi_key))
                if lo is None and hi is None:
                    uncal.append(f"{band_loc}{lo_key}/{hi_key}")
                    continue
                if lo is not None and m[metric_key] < lo:
                    band_reasons.append(
                        f"{metric_key} {fmt.format(m[metric_key])} is below "
                        f"the {family} ADAPT band floor {band_loc}{lo_key} "
                        f"{lo} (restrained work must still carry deliberate "
                        "chroma or tonal commitment; Guide section 13, "
                        "check 1)")
                if hi is not None and m[metric_key] > hi:
                    band_reasons.append(
                        f"{metric_key} {fmt.format(m[metric_key])} exceeds "
                        f"the {family} ADAPT band ceiling {band_loc}{hi_key} "
                        f"{hi} (an ADAPT image above its recorded band has "
                        "drifted toward FULL wash; Guide section 13, "
                        "check 1)")
            _floor_check(adapt, band_loc, "luma_std", "min_luma_std",
                         "{:.2f}", m, band_reasons, uncal)
            if provisional:
                print(f"WARN: PROVISIONAL ADAPT band, family {family}: "
                      f"{name}: the class was derived from 1 to 3 "
                      "anchors and is recorded uncalibrated; its band is "
                      "applied as WARN only, never as a failure")
                for reason in band_reasons:
                    print(f"WARN: PROVISIONAL ADAPT band, family {family}: "
                          f"{name}: {reason}")
                uncal.append(f"{band_loc}(provisional)")
            else:
                reasons.extend(band_reasons)
    else:  # FULL or UNRECORDED
        if posture == "UNRECORDED":
            print(f"NOTE: {name}: no posture recorded for this image; "
                  f"the {family} FULL floors apply (never silently N/A)")
        if full is None:
            uncal.append(f"{fam_loc}full")
        else:
            full_loc = f"{fam_loc}full."
            for metric_key, grade_key, fmt in THRESHOLD_METRICS:
                if metric_key in COLOR_METRICS:
                    _floor_check(full, full_loc, metric_key, grade_key,
                                 fmt, m, reasons, uncal)
    # Non-color floors: the family's pooled block, except ADAPT whose
    # luma_std tonal floor lives in its band block (handled above);
    # sharpness always comes from the non-color block.
    if posture != "ADAPT":
        if noncolor is None:
            uncal.append(f"{fam_loc}noncolor")
        else:
            nc_loc = f"{fam_loc}noncolor."
            for metric_key, grade_key, fmt in THRESHOLD_METRICS:
                if metric_key not in COLOR_METRICS:
                    _floor_check(noncolor, nc_loc, metric_key, grade_key,
                                 fmt, m, reasons, uncal)
    else:
        if noncolor is None:
            uncal.append(f"{fam_loc}noncolor.min_sharpness")
        else:
            _floor_check(noncolor, f"{fam_loc}noncolor.", "sharpness",
                         "min_sharpness", "{:.2f}", m, reasons, uncal)

    # Option B selectivity (Ruling 3), FULL-posture images only
    # (UNRECORDED resolves to FULL above). A pixel proxy: the Item 12
    # judgment gate remains the enforcement of record for selective
    # saturation; this screen never substitutes for it.
    if posture in ("FULL", "UNRECORDED"):
        if m["protected_sat"] is None or m["protected_share"] < MIN_PROTECTED_SHARE:
            print(f"NOTE: {name}: protected-region saturation N/A "
                  f"(Option B selectivity): the protected mask covers "
                  f"{m['protected_share']:.2%} of the working copy, below "
                  "the measurable minimum; reported as N/A, never as a "
                  "pass. Selective saturation remains with the Item 12 "
                  "judgment gate.")
        elif ceiling is None:
            print(f"WARN: uncalibrated Option B selectivity: {name}: "
                  f"protected-region mean saturation "
                  f"{m['protected_sat']:.4f}, saturated-intrusion share "
                  f"{m['intrusion_share']:.2%}; no approved protected-"
                  "region ceiling exists in the brand file, so this "
                  "measurement is WARN only and never fails the image. "
                  "The Item 12 judgment gate remains the enforcement of "
                  "record for selective saturation (Sauce 2, 23.2).")
            uncal.append("grade.max_protected_saturation")
        elif m["protected_sat"] > ceiling:
            # WARN only, never a failure, whether or not a ceiling is
            # written (Ruling 3; owner ruling S71-OPTION-B, Resolution
            # A, 2026-10-16: writing the ceiling does not change its
            # enforcement status, and the Item 12 judgment gate remains
            # the enforcement of record for selective saturation).
            print(f"WARN: Option B selectivity: {name}: "
                  f"protected-region mean saturation "
                  f"{m['protected_sat']:.4f} exceeds the approved "
                  f"protected-region ceiling {ceiling} (a global wash "
                  "colonizes the protected neutrals and skin; Sauce 2, "
                  "23.2; saturated-intrusion share "
                  f"{m['intrusion_share']:.2%}); WARN only, never a "
                  "failure. The Item 12 judgment gate remains the "
                  "enforcement of record for selective saturation.")
        else:
            print(f"NOTE: {name}: protected-region mean saturation "
                  f"{m['protected_sat']:.4f} is within the approved "
                  f"ceiling {ceiling} (Option B selectivity); "
                  f"saturated-intrusion share {m['intrusion_share']:.2%}")
    return reasons, bool(uncal)


def main():
    parser = argparse.ArgumentParser(
        description="Signature-look image screen (Skill 71, Items 8 and 9, "
                    "Amendment 6).")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--brand", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, default=None,
                        help="desktop-wireframe/image-inventory.json; enables the "
                             "native-ratio + crop-plan check, delivery-dimension "
                             "check, and continuity_group exemptions")
    parser.add_argument("--bible", type=Path, default=None,
                        help="visual-mockup/page-visual-bible.json; its Blend "
                             "Profile makes the color floors N/A for dimensions "
                             "marked SUPPRESS or ADAPT (Amendment 6, Part B4)")
    args = parser.parse_args()

    if Image is None:
        print("FAIL: Pillow is required (pip install Pillow).")
        return 2

    grade = load_grade(args.brand)
    plan = floor_plan(grade)
    nested_families = set()
    if isinstance(grade.get("floors"), dict):
        nested_families = {f for f in FAMILIES
                           if isinstance(grade["floors"].get(f), dict)}
    any_uncalibrated = False

    inventory = load_inventory(args.inventory) if args.inventory else {}
    bible_profile = load_bible_profile(args.bible) if args.bible else {}

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

        family, family_recorded = family_of(entry)
        if args.inventory and entry is not None and not family_recorded:
            print(f"NOTE: {path.name}: inventory entry records no "
                  f"active_family; the brand default family "
                  f"{DEFAULT_FAMILY} applies")
        posture, posture_source = posture_resolution(entry, bible_profile)
        ceiling = protected_ceiling(grade, plan, family)
        reasons, image_uncalibrated = apply_grade_floors(
            path.name, m, family, posture, posture_source,
            plan[family], family in nested_families, ceiling)
        any_uncalibrated = any_uncalibrated or image_uncalibrated

        if args.inventory:
            if entry is None:
                print(f"WARN: {path.name}: no inventory entry matches this file; "
                      "ratio and delivery checks not run")
            else:
                native, slot = recorded_ratios(entry)
                recorded = native if native is not None else slot
                if recorded is None:
                    print(f"WARN: {path.name}: inventory entry "
                          f"{entry.get('id')} records no native or slot ratio; "
                          "ratio check not run")
                else:
                    # Passing ratios: the recorded native ratio and its
                    # N43 remapping. When only a slot ratio is recorded,
                    # it stands in as the recorded ratio, and its N43
                    # remapping (the recorded remap) also passes.
                    candidates = {recorded}
                    remapped = n43_remap(recorded)
                    if remapped:
                        candidates.add(remapped)
                    if any(ratio_close(m["aspect_ratio"], c) for c in candidates):
                        pass  # rendered at the native ratio or its N43 remap
                    elif crop_plan(entry):
                        print(f"PASS: {path.name}: rendered ratio "
                              f"{m['aspect_ratio']:.4f} differs from the recorded "
                              f"native ratio {recorded:.4f}; accepted under the "
                              f"entry's recorded crop plan: {crop_plan(entry)}")
                    else:
                        reasons.append(
                            f"rendered aspect ratio {m['aspect_ratio']:.4f} matches "
                            f"neither the recorded native ratio {recorded:.4f} nor "
                            "an N43 remapping of it, and the entry records no crop "
                            f"plan (entry {entry.get('id')})")
                expected_dims = delivery_expectation(entry, path.name)
                if expected_dims is not None:
                    if (m["width"], m["height"]) != expected_dims:
                        reasons.append(
                            f"delivery dimensions {m['width']}x{m['height']} do not "
                            f"equal the entry's recorded delivery dimensions "
                            f"{expected_dims[0]}x{expected_dims[1]} "
                            f"(entry {entry.get('id')})")

        if reasons:
            failures.append(path.name)
            print(f"FAIL: {path.name}: " + "; ".join(reasons))
        elif image_uncalibrated:
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

    # Distinctness register enforcement (Amendment 6, Part B4): the
    # register check, mechanical over the inventory entries, is the
    # enforcement layer; the hash above is retained as a tripwire only.
    if args.inventory:
        for line in register_failures(inventory):
            print(f"FAIL: {line}")
            failures.append(line)

    if any_uncalibrated:
        print("WARN: uncalibrated — some grade floors that apply above are "
              "not calibrated in the brand file (per-family, per-posture "
              "floors, Calibration Redesign); those measurements were "
              "printed above with no gate applied. The native-ratio + "
              "crop-plan and near-duplicate checks are unconditional "
              "and were applied.")
    if duplicate_pairs:
        failures.append(f"{len(duplicate_pairs)} near-duplicate pair(s)")
    if failures:
        print("FAIL: image check(s) failed the Signature grade screen: "
              + ", ".join(failures))
        return 1
    if any_uncalibrated:
        return 0
    print(f"PASS: {len(args.images)} image(s) meet the Signature grade floor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
