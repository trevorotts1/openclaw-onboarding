#!/usr/bin/env python3
"""Validate a Skill 71 wireframe stage (fix plan Item 4).

Usage:
  python3 scripts/validate_wireframe.py <run_dir> <stage>
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
  3. Part PNGs in the stage folder are consecutively numbered with no
     gaps (part-01 ... part-NN).
  4. Part PNG widths match the stage: 1440px for desktop-wireframe, 390px
     for mobile-tablet, tolerance +/-2px, read with Pillow.
  5. Where the plan assigns an aspect ratio to a slot, it matches the
     ratio the inventory declares for that slot (within 2 percent).
     A plan that assigns no ratios has nothing to check here; the check
     never invents a ratio.

What this script deliberately does NOT do: judge whether the wireframe is
beautiful. That stays with the independent reviewer (Item 2 machinery).

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import json
import re
import sys
from pathlib import Path

EXPECTED_WIDTH = {"desktop-wireframe": 1440, "mobile-tablet": 390}
WIDTH_TOLERANCE_PX = 2
RATIO_TOLERANCE = 0.02
PART_RE = re.compile(r"^part-(\d+)\.png$", re.IGNORECASE)


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


def main(argv):
    if len(argv) != 3:
        print("usage: validate_wireframe.py <run_dir> <stage>")
        return 2
    run_dir = Path(argv[1]).resolve()
    stage = argv[2]
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

    # (3) + (4) Part PNG numbering and widths.
    stage_dir = run_dir / stage
    parts = []
    for p in sorted(stage_dir.glob("part-*.png")):
        m = PART_RE.match(p.name)
        if m:
            parts.append((int(m.group(1)), p))
    if not parts:
        failures.append(f"no part-*.png files found in {stage}/")
    else:
        numbers = [n for n, _ in parts]
        expected = list(range(1, max(numbers) + 1))
        if numbers != expected:
            missing = [n for n in expected if n not in numbers]
            failures.append(f"part PNG numbering in {stage}/ is not consecutive: found "
                            f"{numbers}, missing {missing}")
        try:
            from PIL import Image
        except Exception as exc:
            print(f"ERROR: unreadable input: Pillow is required to read PNG widths ({exc})")
            return 2
        want = EXPECTED_WIDTH[stage]
        for number, p in parts:
            try:
                with Image.open(p) as img:
                    width = img.size[0]
            except Exception as exc:
                failures.append(f"part {p.name}: unreadable PNG ({exc})")
                continue
            if abs(width - want) > WIDTH_TOLERANCE_PX:
                failures.append(f"part {p.name}: width {width}px, expected {want}px "
                                f"(+/-{WIDTH_TOLERANCE_PX}px) for stage {stage}")

    # (5) Slot ratio consistency, only where the plan assigns ratios.
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

    if failures:
        print("FAIL")
        for line in failures:
            print(f"- {line}")
        return 1
    print(f"PASS: {stage} section-plan is complete and ordered "
          f"({len(plan_ids)} sections, {len(plan_slot_ids)} slots, {len(parts)} parts)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
