#!/usr/bin/env python3
"""Validate a Skill 71 wireframe stage (fix plan Item 4; Update Plan Item 15).

Usage:
  python3 scripts/validate_wireframe.py <run_dir> <stage> [--brand <brand.json>]
  stage is desktop-wireframe or mobile-tablet.

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
     mobile-tablet, tolerance +/-2px, read with Pillow. (This replaces
     the retired part-*.png numbering/width checks, which targeted the
     pre-Item-11 HTML-render export form.)
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
  7. Brand-color trait (W4): the measured colors of every section slice
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

What this script deliberately does NOT do: judge whether the wireframe
is beautiful, or read the printed annotations off the pixels (no OCR:
the plan entry is the annotation record, the reviewer verifies the
record against the sheet by eye). That stays with the independent
reviewer (Item 2 machinery).

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import json
import re
import sys
from pathlib import Path

EXPECTED_WIDTH = {"desktop-wireframe": 1440, "mobile-tablet": 390}
WIDTH_TOLERANCE_PX = 2
RATIO_TOLERANCE = 0.02
BRAND_PIXEL_TOLERANCE = 32
PALETTE_MIN_SHARE = 0.02
OFF_BRAND_MAX_SHARE = 0.25
NEUTRAL_CHANNEL_SPREAD = 12
MIN_ART_DIRECTION_CHARS = 8


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
    """Brand file for the W4 measurement: --brand, else the run's pinned
    private/brand.json, else intake.json's brand_file, else the skill's
    own brand file (the stage gate's own resolution order)."""
    if explicit:
        return Path(explicit)
    pinned = run_dir / "private" / "brand.json"
    if pinned.exists():
        return pinned
    intake_path = run_dir / "intake.json"
    if intake_path.exists():
        try:
            intake = load_json(intake_path)
            bf = intake.get("brand_file") if isinstance(intake, dict) else None
            if bf:
                p = Path(bf)
                return p if p.is_absolute() else (run_dir / bf)
        except Exception:
            pass
    return Path(__file__).resolve().parents[1] / "assets" / "brand" / "blackceo-brand.json"


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
    for rgb in pixels:
        if near(rgb, palette):
            palette_hits += 1
        if max(rgb) - min(rgb) <= NEUTRAL_CHANNEL_SPREAD:
            continue  # neutral: B/W plates, text, anti-aliasing
        chromatic += 1
        if not near(rgb, allowed):
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


def annotation_failures(plan, stage):
    """Item 15 annotation traits (W1, W2, W5, W6), one named line per
    section per missing annotation."""
    failures = []
    want_width = EXPECTED_WIDTH[stage]
    for i, section in enumerate(plan):
        if not isinstance(section, dict):
            continue
        sid = section.get("section_id") or f"entry {i}"
        position = i + 1
        number = section.get("section_number")
        if number != position:
            failures.append(
                f"section {sid!r}: missing annotation W1 (sections numbered "
                f"and named): section_number is {number!r}, expected {position} "
                f"(the section's position in the plan)")
        name = section.get("section_name")
        if not isinstance(name, str) or not name.strip():
            failures.append(
                f"section {sid!r}: missing annotation W1 (sections numbered "
                f"and named): no section_name recorded")
        specs = section.get("type_specs")
        if not isinstance(specs, dict):
            failures.append(
                f"section {sid!r}: missing annotation W2 (type specs printed): "
                f"no type_specs record (h1, h2, body, cta sizes)")
        else:
            lowered = {str(k).lower(): v for k, v in specs.items()}
            for key in ("h1", "h2", "body", "cta"):
                value = lowered.get(key)
                if not isinstance(value, str) or not value.strip():
                    failures.append(
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
            failures.append(
                f"section {sid!r}: missing annotation W6 (behavior notes "
                f"printed per section): no behavior_notes recorded")
        if i == 0:
            strip = section.get("header_strip")
            if not isinstance(strip, dict):
                failures.append(
                    f"section {sid!r}: missing annotation W5 (header strip "
                    f"stating page width and content width): the first "
                    f"section carries no header_strip record")
            else:
                page_w = strip.get("page_width_px")
                content_w = strip.get("content_width_px")
                if page_w != want_width:
                    failures.append(
                        f"section {sid!r}: annotation W5 (header strip) "
                        f"page_width_px is {page_w!r}, expected {want_width} "
                        f"for stage {stage}")
                if (not isinstance(content_w, int) or isinstance(content_w, bool)
                        or not 0 < content_w <= want_width):
                    failures.append(
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


def main(argv):
    args = list(argv[1:])
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
        for p in slices:
            try:
                with Image.open(p) as img:
                    width = img.size[0]
            except Exception as exc:
                failures.append(f"section slice {p.name}: unreadable PNG ({exc})")
                continue
            if abs(width - want) > WIDTH_TOLERANCE_PX:
                failures.append(f"section slice {p.name}: width {width}px, expected "
                                f"{want}px (+/-{WIDTH_TOLERANCE_PX}px) for stage {stage}")

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

    # (5) Annotation traits W1, W2, W5, W6 (Item 15).
    failures.extend(annotation_failures(plan, stage))

    # (6) Slot-label trait W3 (Item 15).
    failures.extend(slot_label_failures(plan, inventory_by_id))

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
    for idx, p in enumerate(slices):
        measured = measure_slice_colors(p, palette, allowed)
        if measured is None:
            continue  # unreadable slices already failed in check (3)
        palette_share, off_share, dominant = measured
        section = plan_by_index[idx] if idx < len(plan_by_index) else {}
        sid = section.get("section_id") if isinstance(section, dict) else None
        where = f"section {sid!r} slice {p.name}" if sid else f"slice {p.name}"
        if palette_share < PALETTE_MIN_SHARE:
            failures.append(
                f"{where}: off-brand colors W4 (wireframe rendered in the "
                f"client's brand colors): measured palette share "
                f"{palette_share:.1%} of sampled pixels; no brand palette "
                f"color from {brand_path.name} is present on the slice")
        elif off_share > OFF_BRAND_MAX_SHARE:
            failures.append(
                f"{where}: off-brand colors W4 (wireframe rendered in the "
                f"client's brand colors): {off_share:.0%} of chromatic "
                f"pixels measure off-palette (dominant off-brand "
                f"{dominant}); measured colors must sit in the brand "
                f"palette from {brand_path.name}")

    if failures:
        print("FAIL")
        for line in failures:
            print(f"- {line}")
        return 1
    print(f"PASS: {stage} section-plan is complete and ordered "
          f"({len(plan_ids)} sections, {len(plan_slot_ids)} slots, "
          f"{len(slices)} section slices; annotations W1/W2/W5/W6, slot "
          f"labels W3, and brand colors W4 verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
