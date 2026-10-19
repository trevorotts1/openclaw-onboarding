#!/usr/bin/env python3
"""Validate a Skill 71 wireframe stage (fix plan Item 4; Update Plan Item 15).

Usage:
  python3 scripts/validate_wireframe.py <run_dir> <stage> [--brand <brand.json>]
  python3 scripts/validate_wireframe.py --image <png> --brand <brand.json> [--sheet]
  stage is desktop-wireframe or mobile-tablet; --image runs the pixel traits only.

The stage must produce <stage>/section-plan.json: an ordered array of
sections, each {section_id, copy_block_ids: [...], image_slot_ids: [...],
reference_traits: [...]}. Checks, all deterministic:

  1. section-plan.json parses and its section ids exactly equal the copy
     manifest's section ids (copy/copy-manifest.json), in the same order,
     each exactly once. A missing, duplicated, or reordered section FAILs
     by name.
  2. Every image_slot_id in the plan exists in
     desktop-wireframe/image-inventory.json and vice versa (bidirectional;
     the orphan is named).
  3. Spec image set form (Update Plan Item 11, enforced here since
     Item 15): the stage folder carries one section slice
     (section-*.png) per planned section, the stitched full-page PNG
     (wireframe-full.png), and the combined PDF (wireframe.pdf). Slice
     widths match the stage: 1440px for desktop-wireframe, 390px for
     mobile-tablet, tolerance +/-2px, read with Pillow. The summed
     section heights of a desktop wireframe must reach the 16,736px
     floor derived from the standard set's own desktop wireframe sheet
     (assets/visual-standards/manifest.json: six 1440px slices summing
     to 16,736px); a short page FAILs by name. Mobile has NO height
     floor and none is asserted: the standard set contains no
     full-height mobile wireframe sheet, so the mobile floor is
     undetermined. (This replaces the retired part-*.png
     numbering/width checks, which targeted the pre-Item-11 HTML-render
     export form.)
  4. Slot ratio consistency: where the plan assigns an aspect ratio to
     a slot, it matches the ratio the inventory declares for that slot
     (within 2 percent).
  5. Annotation traits (Update Plan Item 15; trait list from Item 14):
     every section's plan entry carries its printed annotations as data:
       W1: section_number (its 1-based position) and section_name;
       W2: type_specs with non-empty h1, h2, body, and cta entries;
       W5: the first section carries header_strip {page_width_px,
           content_width_px}, page width equal to the stage width;
       W6: behavior_notes, a non-empty string or list of strings.
     Each missing annotation FAILs with a named line per section.
  6. Slot-label trait (W3): every image slot in every section carries a
     label -- in the section's image_slots list ({slot_id, aspect_ratio,
     art_direction}) or its slot_labels map -- whose aspect ratio parses
     and matches the inventory's declared ratio (within 2 percent) and
     whose art direction (what the image must show) is a real direction
     string. Each unlabeled or mislabeled slot FAILs by name.
  7. Composition treatments (references/composition-treatments.json): every
     slot's declared `treatment` is a known id, and a plan with six or more
     photo-bearing sections meets the per-page composition budget (split at
     most 40 percent, a words-over-image hero, a full-width band, two shaped
     crops with one circle, an intersecting treatment, no adjacent repeat of
     a non-split treatment). A slot with no treatment counts as split.
  8. Brand-color trait (W4): the measured colors of every section slice
     sit in the run's brand palette. The brand file resolves from
     --brand, else the run's private/brand.json pin, else intake.json's
     brand_file, else the skill's own brand file. Pixels are sampled
     with Pillow: neutral pixels (near-gray, the black-and-white
     photographic plates and text) are always allowed; a chromatic
     pixel is on-brand when it sits within BRAND_PIXEL_TOLERANCE per
     RGB channel of a palette or logo-only color. A slice FAILs W4 by
     name when less than 2 percent of its pixels measure near a palette
     color (no brand color present), or when more than 25 percent of
     its chromatic pixels measure off-palette.

  8. Style extensions (SPF016; the look of the owner's wireframes 1, 3, 4):
       W1 (numbering): when a section's plan entry records the printed chip
           `section_tag` (for example "2A") the tags must run in sequence,
           each exactly once, none skipped; `badge_reads` ({"steps": ["1",
           ...]}) lists the numerals read off a badge sequence and each must
           run 1..n once each. W1 (chip, pixels): each slice carries a
           compact filled accent-colour block (the section chip) in its top
           left zone.
       W3 (ratios): a printed ratio label must be a valid label
           (VALID_RATIO_LABELS); "3:9" is 1:3 written unreduced and FAILs.
       W4 (palette share): counted against the RESOLVED client palette, on
           chromatic pixels only: a slice must show at least ACCENT_MIN_SHARE
           of pixels near a chromatic palette colour (grey pixels never count
           toward a brand colour). A chromatic pixel also counts as on-brand
           when its hue is within HUE_TOLERANCE_DEG of a chromatic palette
           colour (an anti-aliased edge of the accent keeps its hue); this
           repairs a false off-brand reading on any real sheet with a chip.
       W8 (negative trait): a greyscale, no-colour sheet FAILs when the
           resolved palette has a chromatic colour: a slice whose chromatic
           pixel share is under GREYSCALE_MAX_CHROMA is the grey line-work
           style the owner rejected. A palette with no chromatic colour has
           nothing to measure and W8/chip/accent are reported as not measured.
     `--image <png> [--sheet] [--brand <brand.json>]` runs only the pixel
     traits (W1 chip, W4 accent share, W8) on one image; `--sheet` treats it
     as a whole-page sheet (chips anywhere) instead of one section slice.

The measured verdicts (W1-W6, W8) are written into the run record at
`<run_dir>/private/wireframe-verdicts.json`, one entry per wireframe
stage. Every verdict is computed here from the plan record, the
measured slice width, and the sampled pixels; nothing is copied from a
self-reported "annotated" flag in the plan.

What this script deliberately does NOT do: judge whether the wireframe
is beautiful, or read the printed annotations off the pixels (no OCR:
the plan entry is the annotation record, the reviewer verifies the
record against the sheet by eye). That stays with the independent
reviewer (Item 2 machinery).

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import composition  # noqa: E402

EXPECTED_WIDTH = {"desktop-wireframe": 1440, "mobile-tablet": 390}
WIDTH_TOLERANCE_PX = 2
# Summed section heights must reach the floor in this map. desktop-wireframe
# takes 16,736px from the standard set's own desktop wireframe sheet. There is
# deliberately no mobile-tablet entry: the 48,894px standard is a mockup, not a
# wireframe, so the mobile height floor is undetermined and unasserted.
HEIGHT_FLOOR = {"desktop-wireframe": 16736}
RATIO_TOLERANCE = 0.02
BRAND_PIXEL_TOLERANCE = 32
PALETTE_MIN_SHARE = 0.02
OFF_BRAND_MAX_SHARE = 0.25
NEUTRAL_CHANNEL_SPREAD = 12
MIN_ART_DIRECTION_CHARS = 8
# SPF016 style traits.
# One list for the executor and W3: references/wireframe-build-spec.json "ratio_labels".
VALID_RATIO_LABELS = set(json.loads(
    (Path(__file__).resolve().parents[1] / "references" / "wireframe-build-spec.json"
     ).read_text(encoding="utf-8"))["ratio_labels"])
ACCENT_MIN_SATURATION = 0.45   # a palette entry is an accent colour (not black, white, cream,
ACCENT_MIN_VALUE = 0.35        # charcoal or a deep navy) at this HSV saturation and value
HUE_TOLERANCE_DEG = 20      # anti-aliased blends of an accent with white, black or grey keep its hue
CHROMA_SPREAD = 24          # a pixel is chromatic at this max-min channel spread
GREYSCALE_MAX_CHROMA = 0.0025
ACCENT_MIN_SHARE = 0.0025
STYLE_WIDTH = 720           # measurement width; chips are found at this scale
CHIP_WIDTH_FRAC = (0.04, 0.40)
CHIP_HEIGHT_FRAC = (0.012, 0.08)
CHIP_ASPECT = (1.5, 8.0)
CHIP_MIN_FILL = 0.75
CHIP_ZONE = (0.50, 0.25)    # a slice's chip sits in its top-left zone (x fraction, y fraction)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_section_ids(data):
    """Section ids from copy-manifest.json, tolerating its written shapes:
    a list of section objects/strings, or an object with a sections /
    section_ids / blocks list, or an object keyed by section id."""
    if isinstance(data, list):
        ids = []
        for entry in data:
            if isinstance(entry, str):
                ids.append(entry)
            elif isinstance(entry, dict):
                for key in ("section_id", "id", "section"):
                    if isinstance(entry.get(key), str):
                        ids.append(entry[key])
                        break
        return ids
    if isinstance(data, dict):
        for key in ("sections", "section_ids", "copy_sections", "blocks"):
            value = data.get(key)
            if isinstance(value, list):
                return manifest_section_ids(value)
            if isinstance(value, dict):
                return list(value.keys())
        if data and all(isinstance(v, (dict, list)) for v in data.values()):
            return list(data.keys())
    return []


def inventory_entries(data):
    """Inventory entries as a list of dicts, tolerating list or wrapped shapes."""
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if isinstance(data, dict):
        for key in ("images", "inventory", "entries", "slots"):
            if isinstance(data.get(key), list):
                return [e for e in data[key] if isinstance(e, dict)]
        return [data] if data else []
    return []


def entry_id(entry):
    for key in ("id", "slot_id", "image_slot_id", "image_id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_ratio(value):
    """Parse '16:9', '16/9', 1.78, or {'w':..,'h':..} into a float w/h."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        m = re.match(r"^(\d+(?:\.\d+)?)\s*[:/x]\s*(\d+(?:\.\d+)?)$", text)
        if m:
            w, h = float(m.group(1)), float(m.group(2))
            return w / h if h else None
        try:
            number = float(text)
            return number if number > 0 else None
        except ValueError:
            return None
    if isinstance(value, dict):
        w = value.get("width") or value.get("w")
        h = value.get("height") or value.get("h")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and h:
            return float(w) / float(h)
    return None


def entry_ratio(entry):
    for key in ("aspect_ratio", "ratio", "slot_ratio", "intended_ratio"):
        if key in entry:
            parsed = parse_ratio(entry[key])
            if parsed is not None:
                return parsed
    w, h = entry.get("width"), entry.get("height")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)) and h:
        return float(w) / float(h)
    dims = entry.get("desktop_slot_px") or entry.get("slot_px")
    parsed = parse_ratio(dims) if dims is not None else None
    return parsed


def plan_slot_ratios(section):
    """Ratios the plan assigns, as {slot_id: float}. Empty when the plan
    assigns none (the section-plan schema's base shape carries ids only)."""
    out = {}
    ratios = section.get("slot_aspect_ratios") or section.get("slot_ratios")
    if isinstance(ratios, dict):
        for slot_id, value in ratios.items():
            parsed = parse_ratio(value)
            if parsed is not None:
                out[slot_id] = parsed
    slots = section.get("image_slots")
    if isinstance(slots, list):
        for slot in slots:
            if isinstance(slot, dict):
                slot_id = entry_id(slot)
                parsed = entry_ratio(slot)
                if slot_id and parsed is not None:
                    out[slot_id] = parsed
    return out


def slot_labels(section):
    """The section's slot labels as {slot_id: label_dict}: the per-slot
    art-direction record Item 15 checks (W3). Sources, in order: the
    section's image_slots list of dicts, then its slot_labels map."""
    out = {}
    slots = section.get("image_slots")
    if isinstance(slots, list):
        for slot in slots:
            if isinstance(slot, dict):
                slot_id = entry_id(slot)
                if slot_id:
                    out[slot_id] = slot
    labels = section.get("slot_labels")
    if isinstance(labels, dict):
        for slot_id, label in labels.items():
            if isinstance(slot_id, str) and slot_id not in out:
                out[slot_id] = label if isinstance(label, dict) else {}
    return out


def resolve_brand_path(run_dir, explicit):
    """Brand file for the W4 measurement: --brand, else the file scripts/brand_colors.py
    resolved for the run (the same palette the prompts and the stage gate carry)."""
    if explicit:
        return Path(explicit)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import brand_colors  # SPF019: one resolution, no silent BlackCEO palette for a client's sheet
    return brand_colors.brand_path(run_dir)


def hex_to_rgb(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return None
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def brand_color_sets(brand):
    """(palette, allowed) as RGB lists: palette from brand.palette,
    allowed = palette + brand.logo_only_colors."""
    palette, allowed = [], []
    for value in (brand.get("palette") or {}).values():
        rgb = hex_to_rgb(value)
        if rgb is not None:
            palette.append(rgb)
            allowed.append(rgb)
    for value in (brand.get("logo_only_colors") or {}).values():
        rgb = hex_to_rgb(value)
        if rgb is not None:
            allowed.append(rgb)
    return palette, allowed


def near(rgb, targets):
    return any(max(abs(rgb[i] - t[i]) for i in range(3)) <= BRAND_PIXEL_TOLERANCE
               for t in targets)


def measure_slice_colors(path, palette, allowed):
    """Sample a slice's pixels; return (palette_share, off_brand_share,
    dominant_off_brand_hex_or_None), or None when unreadable."""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((80, 80))
            pixels = list(img.getdata())
    except Exception:
        return None
    if not pixels:
        return None
    total = len(pixels)
    palette_hits = 0
    chromatic = 0
    off_brand = 0
    off_counts = {}
    accents = accent_colors(palette)
    for rgb in pixels:
        if near(rgb, palette):
            palette_hits += 1
        if max(rgb) - min(rgb) <= NEUTRAL_CHANNEL_SPREAD:
            continue  # neutral: B/W plates, text, anti-aliasing
        chromatic += 1
        if not near(rgb, allowed) and not (accents and near_accent_hue(rgb, accents)):
            off_brand += 1
            bucket = tuple((c // 16) * 16 for c in rgb)
            off_counts[bucket] = off_counts.get(bucket, 0) + 1
    dominant = None
    if off_counts:
        bucket = max(off_counts, key=off_counts.get)
        dominant = "#{:02X}{:02X}{:02X}".format(*bucket)
    return (palette_hits / total,
            (off_brand / chromatic) if chromatic else 0.0,
            dominant)


def _hsv(rgb):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return h * 360, s, v


def accent_colors(palette):
    """Chromatic palette entries: the colours that make a sheet read as this
    client's. Near-neutral and deep entries (black, white, cream, charcoal, a
    deep navy) are excluded."""
    return [rgb for rgb in palette
            if _hsv(rgb)[1] >= ACCENT_MIN_SATURATION and _hsv(rgb)[2] >= ACCENT_MIN_VALUE]


def near_accent_hue(rgb, accents):
    """A chromatic pixel is a blend of an accent when its hue is within
    HUE_TOLERANCE_DEG of one: anti-aliasing never turns red into purple."""
    hue = _hsv(rgb)[0]
    return any(min(abs(hue - a), 360 - abs(hue - a)) <= HUE_TOLERANCE_DEG
               for a in (_hsv(c)[0] for c in accents))


def _mask_near(img, colors, tolerance):
    from PIL import Image, ImageChops
    out = None
    for color in colors:
        diff = ImageChops.difference(img, Image.new("RGB", img.size, tuple(color)))
        r, g, b = diff.split()
        worst = ImageChops.lighter(ImageChops.lighter(r, g), b)
        mask = worst.point(lambda v, tol=tolerance: 255 if v <= tol else 0)
        out = mask if out is None else ImageChops.lighter(out, mask)
    return out


def _find_chips(mask, slice_zone):
    """Compact, filled rectangular blocks in an accent mask (the section chip
    and CTA chips). Text knocked out of a chip is closed by a dilation first."""
    from PIL import ImageFilter
    width, height = mask.size
    closed = mask.filter(ImageFilter.MaxFilter(7))
    data = bytearray(closed.tobytes())
    chips = []
    pos = data.find(255)
    while pos != -1:
        stack = [pos]
        data[pos] = 128
        x0 = x1 = pos % width
        y0 = y1 = pos // width
        count = 0
        while stack:
            p = stack.pop()
            count += 1
            y, x = divmod(p, width)
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for q in (p - 1 if x else -1, p + 1 if x < width - 1 else -1,
                      p - width if y else -1, p + width if y < height - 1 else -1):
                if q >= 0 and data[q] == 255:
                    data[q] = 128
                    stack.append(q)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if (CHIP_WIDTH_FRAC[0] * width <= w <= CHIP_WIDTH_FRAC[1] * width
                and CHIP_HEIGHT_FRAC[0] * width <= h <= CHIP_HEIGHT_FRAC[1] * width
                and CHIP_ASPECT[0] <= w / h <= CHIP_ASPECT[1]
                and count / (w * h) >= CHIP_MIN_FILL
                and (not slice_zone or (x0 <= CHIP_ZONE[0] * width
                                        and y0 <= CHIP_ZONE[1] * height))):
            chips.append((x0, y0, w, h))
        pos = data.find(255, pos + 1)
    return chips


def measure_style(path, palette, slice_zone=True):
    """SPF016 pixel traits for one slice or sheet, or None when unreadable /
    Pillow is missing. Returns {chroma, accent, chips, accents}: the share of
    chromatic pixels, the share near a chromatic palette colour, the chip-like
    blocks found, and how many chromatic palette colours there are (zero means
    the palette is achromatic and nothing is measurable)."""
    try:
        from PIL import Image, ImageChops
    except Exception:
        return None
    accents = accent_colors(palette)
    try:
        with Image.open(path) as src:
            img = src.convert("RGB")
        if img.size[0] > STYLE_WIDTH:
            img = img.resize((STYLE_WIDTH, max(1, round(img.size[1] * STYLE_WIDTH / img.size[0]))),
                             Image.BOX)
        total = img.size[0] * img.size[1]
        r, g, b = img.split()
        hi = ImageChops.lighter(ImageChops.lighter(r, g), b)
        lo = ImageChops.darker(ImageChops.darker(r, g), b)
        chroma = ImageChops.difference(hi, lo).point(
            lambda v: 255 if v >= CHROMA_SPREAD else 0).histogram()[255] / total
        if not accents:
            return {"chroma": chroma, "accent": 0.0, "chips": [], "accents": 0}
        mask = _mask_near(img, accents, BRAND_PIXEL_TOLERANCE)
        accent = mask.histogram()[255] / total
        chips = _find_chips(mask, slice_zone)
    except Exception:
        return None
    return {"chroma": chroma, "accent": accent, "chips": chips, "accents": len(accents)}


def style_failures(where, measured, brand_name):
    """Named lines per trait for one slice: {'W1': [...], 'W4': [...], 'W8': [...]}."""
    out = {"W1": [], "W4": [], "W8": []}
    if measured is None or not measured["accents"]:
        return out
    if measured["chroma"] < GREYSCALE_MAX_CHROMA:
        out["W8"].append(
            f"{where}: greyscale no-colour style W8 (negative trait): "
            f"{measured['chroma']:.2%} of pixels carry any colour, but the client's "
            f"palette from {brand_name} has a chromatic brand colour; a grey line-work "
            f"or colourless sheet is not the wireframe style")
    if measured["accent"] < ACCENT_MIN_SHARE:
        out["W4"].append(
            f"{where}: off-brand colors W4 (palette share counted against the resolved "
            f"client palette): only {measured['accent']:.2%} of pixels sit near a "
            f"chromatic colour of {brand_name}")
    if not measured["chips"] and measured["chroma"] >= GREYSCALE_MAX_CHROMA:
        out["W1"].append(
            f"{where}: missing annotation W1 (numbered section chip): no compact "
            f"filled accent-colour chip block found in the slice's top-left zone")
    elif not measured["chips"]:
        out["W1"].append(
            f"{where}: missing annotation W1 (numbered section chip): the slice has "
            f"no chip block because it carries no colour")
    return out


def _tag_key(tag):
    m = re.fullmatch(r"0*(\d+)([A-Za-z]?)", str(tag).strip())
    return (int(m.group(1)), m.group(2).upper()) if m else None


def tag_sequence_failures(tags):
    """Printed section tags must run in sequence, once each, none skipped:
    1, 2, 2A, 3, 3A ... (a lettered tag follows its parent, or opens a
    number whose plain tag is replaced, as 5A, 5B, 5C)."""
    failures, seen = [], set()
    base, letter = 0, ""

    def expected():
        nxt = [str(base + 1)]
        if base:
            nxt.append(f"{base}{chr(ord(letter or '@') + 1)}")
        return " or ".join(nxt)

    for raw in tags:
        key = _tag_key(raw)
        if key is None:
            failures.append(f"printed tag {raw!r} is not a section number")
            continue
        n, lt = key
        shown = f"{n}{lt}"
        if shown in seen:
            failures.append(f"printed tag {shown} appears more than once; "
                            f"after {base}{letter} expected {expected()}")
            continue
        seen.add(shown)
        if not lt and n == base + 1:
            base, letter = n, ""
        elif lt and base and n == base and lt == chr(ord(letter or "@") + 1):
            letter = lt
        elif lt and n == base + 1 and lt == "A":
            base, letter = n, "A"
        else:
            failures.append(f"printed tag {shown} is out of sequence after "
                            f"{base}{letter}: expected {expected()}")
            if (n, lt) > (base, letter):
                base, letter = n, lt
    return failures


def badge_failures(reads):
    """Badge numerals read off a sheet ({name: [..]}) must run 1..n once each."""
    failures = []
    if not isinstance(reads, dict):
        return failures
    for name, values in reads.items():
        if not isinstance(values, list):
            continue
        got = []
        for v in values:
            text = str(v).strip()
            got.append(int(text) if re.fullmatch(r"\d{1,2}", text) else text)
        want = list(range(1, len(got) + 1))
        if got != want:
            failures.append(f"badge sequence {name!r} reads {[str(g) for g in got]}, "
                            f"expected {[str(w) for w in want]} (once each, in order, "
                            f"no icon or other symbol in place of a number)")
    return failures


def sequence_failures(plan):
    """W1 sequential numbering from the plan record, one named line each."""
    failures = []
    tagged = [(s.get("section_id") or f"entry {i}", s["section_tag"])
              for i, s in enumerate(plan)
              if isinstance(s, dict) and s.get("section_tag") not in (None, "")]
    if tagged:
        for line in tag_sequence_failures([tag for _sid, tag in tagged]):
            failures.append(f"missing annotation W1 (sequential numbering): {line}")
    for i, section in enumerate(plan):
        if isinstance(section, dict):
            sid = section.get("section_id") or f"entry {i}"
            for line in badge_failures(section.get("badge_reads")):
                failures.append(f"section {sid!r}: missing annotation W1 "
                                f"(sequential numbering): {line}")
    return failures


def ratio_label_failures(plan):
    """W3: a printed ratio label must be a valid label (3:9 is not)."""
    failures = []
    for section in plan:
        if not isinstance(section, dict):
            continue
        sid = section.get("section_id") or "(unnamed section)"
        for slot_id, label in slot_labels(section).items():
            value = label.get("aspect_ratio") if isinstance(label, dict) else None
            if isinstance(value, str) and re.sub(r"\s", "", value) not in VALID_RATIO_LABELS:
                failures.append(
                    f"section {sid!r} slot {slot_id!r}: slot label W3 prints an invalid "
                    f"ratio {value!r} (valid labels: "
                    f"{', '.join(sorted(VALID_RATIO_LABELS))})")
    return failures


def annotation_failures(plan, stage, measured_width=None):
    """Item 15 annotation traits (W1, W2, W5, W6), one named line per
    section per missing annotation, returned per trait so the caller can
    emit a verdict per trait. `measured_width` is the width actually
    measured off the first section slice (None when unreadable); W5 is
    judged against the sheet, not only against the stage constant."""
    failures = {"W1": [], "W2": [], "W5": [], "W6": []}
    want_width = EXPECTED_WIDTH[stage]
    for i, section in enumerate(plan):
        if not isinstance(section, dict):
            continue
        sid = section.get("section_id") or f"entry {i}"
        position = i + 1
        number = section.get("section_number")
        if number != position:
            failures["W1"].append(
                f"section {sid!r}: missing annotation W1 (sections numbered "
                f"and named): section_number is {number!r}, expected {position} "
                f"(the section's position in the plan)")
        name = section.get("section_name")
        if not isinstance(name, str) or not name.strip():
            failures["W1"].append(
                f"section {sid!r}: missing annotation W1 (sections numbered "
                f"and named): no section_name recorded")
        specs = section.get("type_specs")
        if not isinstance(specs, dict):
            failures["W2"].append(
                f"section {sid!r}: missing annotation W2 (type specs printed): "
                f"no type_specs record (h1, h2, body, cta sizes)")
        else:
            lowered = {str(k).lower(): v for k, v in specs.items()}
            for key in ("h1", "h2", "body", "cta"):
                value = lowered.get(key)
                if not isinstance(value, str) or not value.strip():
                    failures["W2"].append(
                        f"section {sid!r}: missing annotation W2 (type specs "
                        f"printed): type_specs has no {key} entry")
        notes = section.get("behavior_notes")
        if isinstance(notes, str):
            notes_ok = bool(notes.strip())
        elif isinstance(notes, list):
            notes_ok = any(isinstance(n, str) and n.strip() for n in notes)
        else:
            notes_ok = False
        if not notes_ok:
            failures["W6"].append(
                f"section {sid!r}: missing annotation W6 (behavior notes "
                f"printed per section): no behavior_notes recorded")
        if i == 0:
            strip = section.get("header_strip")
            if not isinstance(strip, dict):
                failures["W5"].append(
                    f"section {sid!r}: missing annotation W5 (header strip "
                    f"stating page width and content width): the first "
                    f"section carries no header_strip record")
            else:
                page_w = strip.get("page_width_px")
                content_w = strip.get("content_width_px")
                if page_w != want_width:
                    failures["W5"].append(
                        f"section {sid!r}: annotation W5 (header strip) "
                        f"page_width_px is {page_w!r}, expected {want_width} "
                        f"for stage {stage}")
                if (measured_width is not None and page_w == want_width
                        and abs(page_w - measured_width) > WIDTH_TOLERANCE_PX):
                    failures["W5"].append(
                        f"section {sid!r}: annotation W5 (header strip) "
                        f"page_width_px is {page_w!r} but the section slice "
                        f"measurably renders {measured_width}px wide; the strip "
                        f"states a page width the sheet contradicts")
                if (not isinstance(content_w, int) or isinstance(content_w, bool)
                        or not 0 < content_w <= want_width):
                    failures["W5"].append(
                        f"section {sid!r}: annotation W5 (header strip) "
                        f"content_width_px is {content_w!r}; it must be a "
                        f"positive width no wider than the page width "
                        f"{want_width}")
    return failures


def slot_label_failures(plan, inventory_by_id):
    """Item 15 slot-label trait (W3), one named line per section per slot."""
    failures = []
    for section in plan:
        if not isinstance(section, dict):
            continue
        sid = section.get("section_id") or "(unnamed section)"
        labels = slot_labels(section)
        for slot_id in section.get("image_slot_ids") or []:
            if not isinstance(slot_id, str):
                continue
            label = labels.get(slot_id)
            if label is None:
                failures.append(
                    f"section {sid!r} slot {slot_id!r}: unlabeled slot W3 "
                    f"(slots labeled with aspect ratio and art direction): "
                    f"no slot label recorded in the section plan")
                continue
            ratio = entry_ratio(label)
            if ratio is None:
                failures.append(
                    f"section {sid!r} slot {slot_id!r}: slot label W3 carries "
                    f"no aspect ratio")
            else:
                entry = inventory_by_id.get(slot_id)
                inv_ratio = entry_ratio(entry) if entry else None
                if inv_ratio is not None and abs(ratio - inv_ratio) / inv_ratio > RATIO_TOLERANCE:
                    failures.append(
                        f"section {sid!r} slot {slot_id!r}: slot label W3 "
                        f"ratio {ratio:.3f} does not match inventory ratio "
                        f"{inv_ratio:.3f}")
            direction = None
            for key in ("art_direction", "artDirection", "direction"):
                if isinstance(label.get(key), str):
                    direction = label[key]
                    break
            if direction is None or len(direction.strip()) < MIN_ART_DIRECTION_CHARS:
                failures.append(
                    f"section {sid!r} slot {slot_id!r}: slot label W3 "
                    f"carries no art direction (what the image must show)")
    return failures


VERDICTS_REL = "private/wireframe-verdicts.json"

def write_run_record(run_dir, stage, traits, section_count, slice_count):
    """Write this wireframe stage's W1-W6 verdicts into the run record.

    The run-scoped record is `private/wireframe-verdicts.json`; each
    wireframe stage writes its own entry, so both stages coexist. Every
    verdict is computed from the plan record, the measured slice width,
    and the sampled pixels by the checks above. A record that cannot be
    written is an error, never a silent pass."""
    path = run_dir / VERDICTS_REL
    try:
        record = load_json(path) if path.exists() else {}
        if not isinstance(record, dict):
            record = {}
    except Exception:
        record = {}
    stages = record.get("stages")
    if not isinstance(stages, dict):
        stages = {}
    overall = ("fail" if any(entry.get("verdict") == "fail"
                             for entry in traits.values()) else "pass")
    stages[stage] = {
        "stage": stage,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": f"{stage}/section-plan.json",
        "sections": section_count,
        "slices": slice_count,
        "traits": traits,
        "verdict": overall,
    }
    payload = {"schema": "skill71.wireframe-verdicts/1", "stages": stages}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".verdicts-",
                                    suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    summary = ", ".join(f"{t} {traits[t]['verdict']}" for t in sorted(traits))
    print(f"WROTE: {VERDICTS_REL} ({stage}: {summary})")

def image_mode(args):
    """--image <png> [--sheet] --brand <brand.json>: the pixel traits only."""
    def take(flag):
        if flag in args:
            i = args.index(flag)
            val = args[i + 1] if i + 1 < len(args) else None
            del args[i:i + 2]
            return val
        return None
    sheet = "--sheet" in args
    if sheet:
        args.remove("--sheet")
    image, brand_arg = take("--image"), take("--brand")
    if not image or not brand_arg or args:
        print("usage: validate_wireframe.py --image <png> --brand <brand.json> [--sheet]")
        return 2
    try:
        brand = load_json(Path(brand_arg))
        palette, allowed = brand_color_sets(brand)
    except Exception as exc:
        print(f"ERROR: unreadable input: brand file {brand_arg}: {exc}")
        return 2
    measured = measure_style(Path(image), palette, slice_zone=not sheet)
    if measured is None:
        print(f"ERROR: unreadable input: {image} (Pillow and a readable PNG are required)")
        return 2
    name = Path(brand_arg).name
    lines = style_failures(f"image {Path(image).name}", measured, name)
    share = measure_slice_colors(Path(image), palette, allowed)
    print(f"MEASURED chroma={measured['chroma']:.2%} accent={measured['accent']:.2%} "
          f"chips={len(measured['chips'])} chromatic_palette_colors={measured['accents']} "
          f"palette_share={share[0]:.1%} off_brand={share[1]:.0%}" if share else
          f"MEASURED chroma={measured['chroma']:.2%} accent={measured['accent']:.2%} "
          f"chips={len(measured['chips'])}")
    if not measured["accents"]:
        print("NOT MEASURED: the palette has no chromatic colour, so W1 chip, W4 accent "
              "share and W8 have nothing to measure")
    if share is not None and measured["accents"]:
        if share[0] < PALETTE_MIN_SHARE:
            lines["W4"].append(f"image {Path(image).name}: off-brand colors W4: palette share "
                               f"{share[0]:.1%} is under {PALETTE_MIN_SHARE:.0%}")
        elif share[1] > OFF_BRAND_MAX_SHARE:
            lines["W4"].append(f"image {Path(image).name}: off-brand colors W4: {share[1]:.0%} of "
                               f"chromatic pixels measure off-palette (dominant {share[2]})")
    bad = 0
    for trait in ("W1", "W4", "W8"):
        if lines[trait]:
            bad = 1
            for line in lines[trait]:
                print(f"FAIL {trait}: {line}")
        else:
            print(f"PASS {trait}")
    return bad


def main(argv):
    args = list(argv[1:])
    if "--image" in args:
        return image_mode(args)
    brand_arg = None
    if "--brand" in args:
        idx = args.index("--brand")
        if idx + 1 >= len(args):
            print("usage: validate_wireframe.py <run_dir> <stage> [--brand <brand.json>]")
            return 2
        brand_arg = args[idx + 1]
        del args[idx:idx + 2]
    if len(args) != 2:
        print("usage: validate_wireframe.py <run_dir> <stage> [--brand <brand.json>]")
        return 2
    run_dir = Path(args[0]).resolve()
    stage = args[1]
    if stage not in EXPECTED_WIDTH:
        print(f"ERROR: stage {stage!r} is not a wireframe stage "
              f"(expected one of {sorted(EXPECTED_WIDTH)})")
        return 2
    if not run_dir.exists():
        print(f"ERROR: run_dir does not exist: {run_dir}")
        return 2

    plan_path = run_dir / stage / "section-plan.json"
    manifest_path = run_dir / "copy" / "copy-manifest.json"
    inventory_path = run_dir / "desktop-wireframe" / "image-inventory.json"
    for path, label in ((plan_path, "section-plan"),
                        (manifest_path, "copy manifest"),
                        (inventory_path, "image inventory")):
        if not path.exists():
            print(f"ERROR: unreadable input: {label} missing at {path}")
            return 2
    try:
        plan = load_json(plan_path)
        manifest = load_json(manifest_path)
        inventory = load_json(inventory_path)
    except Exception as exc:
        print(f"ERROR: unreadable input: {exc}")
        return 2
    if not isinstance(plan, list):
        print(f"FAIL: {stage}/section-plan.json must be an ordered array of sections")
        return 1

    failures = []

    # (1) Section ids exactly equal the copy manifest's, same order, once each.
    plan_ids = []
    for i, section in enumerate(plan):
        if not isinstance(section, dict) or not isinstance(section.get("section_id"), str):
            failures.append(f"section-plan entry {i} has no string section_id")
            continue
        plan_ids.append(section["section_id"])
    manifest_ids = manifest_section_ids(manifest)
    if not manifest_ids:
        failures.append("copy manifest copy/copy-manifest.json declares no section ids "
                        "to check the section plan against")
    else:
        seen = set()
        for sid in plan_ids:
            if sid in seen:
                failures.append(f"section {sid!r} appears more than once in section-plan.json")
            seen.add(sid)
        for sid in manifest_ids:
            if sid not in seen:
                failures.append(f"section {sid!r} is in the copy manifest but missing "
                                f"from section-plan.json")
        for sid in plan_ids:
            if sid not in set(manifest_ids):
                failures.append(f"section {sid!r} is in section-plan.json but not in "
                                f"the copy manifest")
        common_plan = [s for s in plan_ids if s in set(manifest_ids)]
        common_manifest = [s for s in manifest_ids if s in seen]
        if common_plan != common_manifest:
            failures.append(f"section order differs from the copy manifest: plan has "
                            f"{common_plan}, manifest has {common_manifest}")

    # (2) Slot ids bidirectional with the inventory.
    entries = inventory_entries(inventory)
    inventory_ids = []
    inventory_by_id = {}
    for entry in entries:
        eid = entry_id(entry)
        if eid:
            inventory_ids.append(eid)
            inventory_by_id[eid] = entry
    if not inventory_ids:
        failures.append("image inventory desktop-wireframe/image-inventory.json declares "
                        "no slot ids to check the section plan against")
    plan_slot_ids = []
    for section in plan:
        if isinstance(section, dict):
            for slot_id in section.get("image_slot_ids") or []:
                if isinstance(slot_id, str):
                    plan_slot_ids.append(slot_id)
    for slot_id in plan_slot_ids:
        if slot_id not in inventory_by_id:
            failures.append(f"image slot {slot_id!r} is in section-plan.json but not in "
                            f"the image inventory")
    for slot_id in inventory_ids:
        if slot_id not in plan_slot_ids:
            failures.append(f"image slot {slot_id!r} is in the image inventory but assigned "
                            f"to no section in section-plan.json")

    # (3) Spec image set form: one section slice per planned section, the
    # stitched full-page PNG, and the combined PDF; slice widths on stage.
    stage_dir = run_dir / stage
    slices = sorted(stage_dir.glob("section-*.png"))
    if not slices:
        failures.append(f"no section-*.png slices found in {stage}/ (the spec "
                        f"image set delivers one section slice per section)")
    elif len(slices) != len(plan):
        failures.append(f"section slices in {stage}/: found {len(slices)} "
                        f"section-*.png for {len(plan)} planned sections; the "
                        f"spec image set delivers exactly one slice per section")
    if not (stage_dir / "wireframe-full.png").exists():
        failures.append(f"missing stitched full-page PNG {stage}/wireframe-full.png")
    if not (stage_dir / "wireframe.pdf").exists():
        failures.append(f"missing combined PDF {stage}/wireframe.pdf")
    if slices:
        try:
            from PIL import Image
        except Exception as exc:
            print(f"ERROR: unreadable input: Pillow is required to read PNG widths ({exc})")
            return 2
        want = EXPECTED_WIDTH[stage]
        floor = HEIGHT_FLOOR.get(stage)
        total_height = 0
        for p in slices:
            try:
                with Image.open(p) as img:
                    width, height = img.size
            except Exception as exc:
                failures.append(f"section slice {p.name}: unreadable PNG ({exc})")
                continue
            total_height += height
            if abs(width - want) > WIDTH_TOLERANCE_PX:
                failures.append(f"section slice {p.name}: width {width}px, expected "
                                f"{want}px (+/-{WIDTH_TOLERANCE_PX}px) for stage {stage}")
        if floor is not None and total_height < floor:
            failures.append(f"{stage} page height {total_height}px is under the "
                            f"{floor}px floor (summed section heights); a "
                            f"long-scroll page cannot be expressed by an aspect "
                            f"ratio, so the page is delivered at full height")

    # (4) Slot ratio consistency, only where the plan assigns ratios.
    for section in plan:
        if not isinstance(section, dict):
            continue
        for slot_id, plan_ratio in plan_slot_ratios(section).items():
            entry = inventory_by_id.get(slot_id)
            if entry is None:
                continue
            inv_ratio = entry_ratio(entry)
            if inv_ratio is None:
                failures.append(f"image slot {slot_id!r}: the plan assigns ratio "
                                f"{plan_ratio:.3f} but the inventory declares none "
                                f"to check it against")
            elif abs(plan_ratio - inv_ratio) / inv_ratio > RATIO_TOLERANCE:
                failures.append(f"image slot {slot_id!r}: plan ratio {plan_ratio:.3f} "
                                f"does not match inventory ratio {inv_ratio:.3f}")

    # (5) Annotation traits W1, W2, W5, W6 (Item 15), judged from the
    # plan record plus the width the sheet itself measures.
    measured_width = None
    if slices:
        try:
            from PIL import Image
            with Image.open(slices[0]) as img:
                measured_width = img.size[0]
        except Exception:
            measured_width = None
    annotation = annotation_failures(plan, stage, measured_width)
    annotation["W1"] += sequence_failures(plan)
    for trait in ("W1", "W2", "W5", "W6"):
        failures.extend(annotation[trait])

    # (6) Slot-label trait W3 (Item 15).
    w3_failures = slot_label_failures(plan, inventory_by_id) + ratio_label_failures(plan)
    failures.extend(w3_failures)

    # (6b) Composition treatments and the per-page budget.
    comp_failures = composition.budget_failures(
        composition.plan_sections(plan),
        composition.composition_cues(composition.load_brand(run_dir, brand_arg)))
    failures.extend(comp_failures)

    # (7) Brand-color trait W4 (Item 15): measured slice colors.
    brand_path = resolve_brand_path(run_dir, brand_arg)
    try:
        brand = load_json(brand_path)
        if not isinstance(brand, dict):
            raise ValueError("brand file is not a JSON object")
    except Exception as exc:
        print(f"ERROR: unreadable input: brand file {brand_path}: {exc}")
        return 2
    palette, allowed = brand_color_sets(brand)
    if not palette:
        print(f"ERROR: unreadable input: brand file {brand_path} declares no palette")
        return 2
    plan_by_index = list(plan)
    w4_failures = []
    for idx, p in enumerate(slices):
        measured = measure_slice_colors(p, palette, allowed)
        if measured is None:
            continue  # unreadable slices already failed in check (3)
        palette_share, off_share, dominant = measured
        section = plan_by_index[idx] if idx < len(plan_by_index) else {}
        sid = section.get("section_id") if isinstance(section, dict) else None
        where = f"section {sid!r} slice {p.name}" if sid else f"slice {p.name}"
        if palette_share < PALETTE_MIN_SHARE:
            w4_failures.append(
                f"{where}: off-brand colors W4 (wireframe rendered in the "
                f"client's brand colors): measured palette share "
                f"{palette_share:.1%} of sampled pixels; no brand palette "
                f"color from {brand_path.name} is present on the slice")
        elif off_share > OFF_BRAND_MAX_SHARE:
            w4_failures.append(
                f"{where}: off-brand colors W4 (wireframe rendered in the "
                f"client's brand colors): {off_share:.0%} of chromatic "
                f"pixels measure off-palette (dominant off-brand "
                f"{dominant}); measured colors must sit in the brand "
                f"palette from {brand_path.name}")

    failures.extend(w4_failures)

    # (7b) SPF016 style traits on the pixels: chip (W1), accent share counted
    # against the resolved client palette (W4), greyscale negative trait (W8).
    w8_failures = []
    for idx, p in enumerate(slices):
        measured = measure_style(p, palette)
        section = plan_by_index[idx] if idx < len(plan_by_index) else {}
        sid = section.get("section_id") if isinstance(section, dict) else None
        where = f"section {sid!r} slice {p.name}" if sid else f"slice {p.name}"
        lines = style_failures(where, measured, brand_path.name)
        annotation["W1"] += lines["W1"]
        w4_failures += lines["W4"]
        w8_failures += lines["W8"]
        failures.extend(lines["W1"] + lines["W4"] + lines["W8"])

    # (8) Emit the measured W1-W6, W8 verdicts into the run record, pass or
    # fail: the record is what later readers trust, never a plan flag.
    verdicts = {}
    for trait, lines in (("W1", annotation["W1"]), ("W2", annotation["W2"]),
                         ("W3", w3_failures), ("W4", w4_failures),
                         ("W5", annotation["W5"]), ("W6", annotation["W6"]),
                         ("W8", w8_failures),
                         ("COMP", comp_failures)):
        verdicts[trait] = {"verdict": "fail" if lines else "pass",
                           "failures": list(lines)}
    write_run_record(run_dir, stage, verdicts, len(plan), len(slices))

    if failures:
        print("FAIL")
        for line in failures:
            print(f"- {line}")
        return 1
    print(f"PASS: {stage} section-plan is complete and ordered "
          f"({len(plan_ids)} sections, {len(plan_slot_ids)} slots, "
          f"{len(slices)} section slices; annotations W1/W2/W5/W6, slot "
          f"labels W3, brand colors W4, and the not-greyscale trait W8 verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
