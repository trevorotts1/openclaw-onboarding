#!/usr/bin/env python3
"""Validate BlackCEO image-map JSON (Skill 71).

Base: installed 1.0.2 copy (unhashable-id crash fix + map/authoring dialects).
Extended per BLACKCEO-SKILL-71-ENFORCEMENT-FIX-ORDER.md C5:

  --inventory <image-inventory.json>
      The count of inventory entries that need a generated image must equal
      the number of generated masters declared in the map (entries with no
      master_id; crops pointing at a master are not separate generations).
      An inventory entry needs generation unless it sets requires_generation:
      false, or marks itself source/asset_kind as one of existing, logo,
      identity, product, library, stock (SOP:154 — existing logo/product/
      identity assets are identified separately from generated images).
  --measure
      Open each entry's asset file (asset_file or asset_path, resolved
      relative to the manifest) with Pillow; the actual width/height must
      equal the entry's declared width/height. Entries carrying an asset must
      declare positive integer width and height when --measure is used.
  qc_status
      Every entry that carries an asset (i.e. is used on the page) must
      declare qc_status "passed". Entries still planned (no asset yet) are
      not blocked by this rule. The production gate (stage_gate.py) runs this
      validator, so a non-zero exit blocks the stage.

Exit codes: 0 pass, 1 fail (each reason on its own line), 2 unreadable input.
"""
import argparse
import json
import sys
from pathlib import Path

# Shared minimum contract, present in every dialect the skill writes.
BASE_REQUIRED = ["id", "job", "filename", "status"]
# Prompt-plan entries (artifact-contracts.md "Image-map JSON" example).
AUTHORING_REQUIRED = [
    "source_passage", "scene", "people", "shot_plan",
    "style_grade", "text_mode", "references", "technical_plan",
]
# Generated-asset/map entries: the image-map stage output shape.
MAP_REQUIRED = ["alt_text", "intended_ratio", "crop_focal", "asset_path"]
# Fields that identify the map dialect when no prompt-plan fields are present.
MAP_MARKERS = ("alt_text", "intended_ratio", "intended_desktop_slot", "section_name")

STATUSES = {"planned", "blocked", "prompt_ready", "generated", "qc_failed", "ready", "missing"}
PROMPT_STATUSES = {"prompt_ready", "generated", "qc_failed", "ready"}
ASSET_STATUSES = {"generated", "qc_failed", "ready"}

# Inventory markers for assets that are NOT generated (SOP:154).
NON_GENERATED_SOURCES = {"existing", "logo", "identity", "product", "library", "stock"}


def identifier(value):
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def inventory_generation_count(data):
    """Count inventory entries that need a generated image (order C5)."""
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("images")
        if items is None:
            items = data.get("items")
        if items is None:
            raise ValueError("inventory must be a list or an object with an images/items array.")
    else:
        raise ValueError("inventory must be a list or an object with an images/items array.")

    count = 0
    for idx, item in enumerate(items, start=1):
        if item is None:
            continue
        if not isinstance(item, dict):
            raise ValueError(f"inventory[{idx}] must be an object.")
        if item.get("requires_generation") is False:
            continue
        source = item.get("source") or item.get("asset_kind") or ""
        if str(source).strip().lower() in NON_GENERATED_SOURCES:
            continue
        count += 1
    return count


def measure_assets(entries, base_dir):
    """Pillow-measure each declared asset; actual size must equal declared."""
    errors = []
    try:
        from PIL import Image
    except ImportError:
        return ["Pillow is required for --measure (pip install Pillow)."]
    base = Path(base_dir or ".")
    for entry in entries:
        if entry is None:
            continue
        prefix, item, _, _ = entry
        asset = item.get("asset_file") or item.get("asset_path")
        if not asset:
            continue
        width = item.get("width")
        height = item.get("height")
        declared_ok = (
            isinstance(width, int) and not isinstance(width, bool) and width > 0
            and isinstance(height, int) and not isinstance(height, bool) and height > 0
        )
        if not declared_ok:
            errors.append(f"{prefix} must declare positive integer width and height when --measure is used.")
            continue
        path = base / asset
        if not path.exists():
            errors.append(f"{prefix}.asset does not exist: {asset}")
            continue
        try:
            with Image.open(path) as im:
                actual = im.size
        except Exception as exc:
            errors.append(f"{prefix}.asset could not be opened with Pillow: {asset} ({exc})")
            continue
        if (actual[0], actual[1]) != (width, height):
            errors.append(
                f"{prefix}.asset {asset} measures {actual[0]}x{actual[1]} but declares {width}x{height}."
            )
    return errors


def validate(data, base_dir=None, check_files=False, inventory_data=None, measure=False):
    errors = []
    if not isinstance(data, dict) or not isinstance(data.get("images"), list):
        return ["Top-level JSON must contain an images array."]

    ids = []
    filenames = []
    entries = []
    for idx, item in enumerate(data["images"], start=1):
        prefix = f"images[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object.")
            entries.append(None)
            continue

        item_id = identifier(item.get("id"))
        if item_id is None:
            errors.append(f"{prefix}.id must be a non-empty string or number.")
        else:
            ids.append(item_id)

        filename = identifier(item.get("filename"))
        status = item.get("status")
        if status in PROMPT_STATUSES:
            # Guide invariant: one image-map entry -> one correctly named file.
            if filename is None:
                errors.append(f"{prefix}.filename must be a non-empty string or number for status {status!r}.")
            else:
                filenames.append(filename)
        elif filename is not None:
            filenames.append(filename)

        # Dialect: the map stage writes placement/alt fields, the prompt-plan stage
        # writes prompt-authoring fields; an entry with neither meets only the
        # shared minimum contract.
        if any(item.get(marker) is not None for marker in MAP_MARKERS):
            dialect = "map"
        elif item.get("source_passage") is not None:
            dialect = "authoring"
        else:
            dialect = None
        required = BASE_REQUIRED + {
            "map": MAP_REQUIRED,
            "authoring": AUTHORING_REQUIRED,
            None: [],
        }[dialect]
        for key in required:
            if key not in item:
                errors.append(f"{prefix} missing required field {key!r}.")

        if dialect == "authoring" and not isinstance(item.get("references", []), list):
            errors.append(f"{prefix}.references must be an array.")
        if status not in STATUSES:
            errors.append(f"{prefix}.status is invalid: {status!r}.")
        if status in PROMPT_STATUSES and not item.get("prompt_file"):
            errors.append(f"{prefix} with status {status!r} requires prompt_file.")
        # The asset field is spelled asset_file in the prompt plan and asset_path in
        # the map stage; either satisfies the requirement for a generated asset.
        if status in ASSET_STATUSES and not (item.get("asset_file") or item.get("asset_path")):
            errors.append(f"{prefix} with status {status!r} requires asset_file (or asset_path).")

        # Order C5: an entry used on the page must carry a passing QC status.
        if (item.get("asset_file") or item.get("asset_path")) and item.get("qc_status") != "passed":
            errors.append(
                f"{prefix} is used on the page and requires qc_status \"passed\" "
                f"(got {item.get('qc_status')!r})."
            )

        entries.append((prefix, item, item_id, dialect))

    id_set = set(ids)
    duplicate_ids = sorted({x for x in ids if ids.count(x) > 1}, key=lambda x: str(x))
    duplicate_names = sorted({x for x in filenames if filenames.count(x) > 1}, key=lambda x: str(x))
    if duplicate_ids:
        errors.append("Duplicate image IDs: " + ", ".join(str(x) for x in duplicate_ids))
    if duplicate_names:
        errors.append("Duplicate filenames: " + ", ".join(str(x) for x in duplicate_names))

    for entry in entries:
        if entry is None:
            continue
        prefix, item, item_id, _ = entry
        master_id = identifier(item.get("master_id"))
        if master_id is None:
            continue
        if master_id == item_id:
            errors.append(f"{prefix}.master_id cannot reference itself.")
        elif master_id not in id_set:
            errors.append(f"{prefix}.master_id references unknown ID {master_id!r}.")

    if check_files:
        base_dir = Path(base_dir or ".")
        for entry in entries:
            if entry is None:
                continue
            prefix, item, _, _ = entry
            for key in ("prompt_file", "asset_file"):
                value = item.get(key)
                if value and not (base_dir / value).exists():
                    errors.append(f"{prefix}.{key} does not exist: {value}")

    if inventory_data is not None:
        try:
            planned = inventory_generation_count(inventory_data)
        except ValueError as exc:
            errors.append(f"inventory is invalid: {exc}")
        else:
            masters = sum(
                1 for entry in entries
                if entry is not None and identifier(entry[1].get("master_id")) is None
            )
            if planned != masters:
                errors.append(
                    f"Inventory needs {planned} generated image(s) but the map declares "
                    f"{masters} generated master(s); the counts must match."
                )

    if measure:
        errors.extend(measure_assets(entries, base_dir))

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate BlackCEO image-map JSON.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check-files", action="store_true")
    parser.add_argument("--inventory", type=Path, default=None,
                        help="image-inventory.json; generation entries must match the map's master count")
    parser.add_argument("--measure", action="store_true",
                        help="open each asset with Pillow; actual width/height must equal declared")
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read JSON: {exc}")
        return 2

    inventory_data = None
    if args.inventory is not None:
        try:
            inventory_data = json.loads(args.inventory.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"FAIL: could not read inventory JSON: {exc}")
            return 2

    errors = validate(data, args.manifest.parent, args.check_files,
                      inventory_data=inventory_data, measure=args.measure)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    detail = ""
    if inventory_data is not None:
        detail = f" (inventory generation count matches: {inventory_generation_count(inventory_data)})"
    print(f"PASS: {len(data['images'])} image-map entries are structurally valid.{detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
