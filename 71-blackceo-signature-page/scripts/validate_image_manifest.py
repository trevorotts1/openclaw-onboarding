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
  Slot shape (design styles B and C, references/design-styles.md)
      An entry's shape (or mask) is rect or circle. A circle entry declares
      ratio 1:1, a ring (when present) carries a client brand color, and with
      --measure its asset must be a square RGBA PNG with alpha 0 in the four
      corner regions and an opaque center (scripts/circle_image.py check).
  Delivered filename mapping (Update Plan Item 26, proposal P6, ruled
  2026-10-15)
      One convention: the manifest and inventory carry the three-digit
      internal ID (IMG-001); the delivered file is the two-digit
      Image-NN.png derived from that ID (IMG-001 -> Image-01.png,
      IMG-012 -> Image-12.png, IMG-123 -> Image-123.png). An entry's
      filename must be exactly that delivered name for its own ID, and
      the trailing number of its prompt_file / asset_file / asset_path
      (when the file is named in the IMG-<n> / Image-<n> form) must be
      the same number, so every delivered file maps to exactly one
      internal ID and one receipt without a reader guessing the form.

Exit codes: 0 pass, 1 fail (each reason on its own line), 2 unreadable input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circle_image  # noqa: E402

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


_IMG_ID_RE = re.compile(r"^IMG-(\d+)$", re.IGNORECASE)
_NAMED_FILE_RE = re.compile(r"^(?:IMG|Image)-(\d+)$", re.IGNORECASE)


def internal_number(item_id):
    """The numeric part of a three-digit internal ID (IMG-001 -> 1).

    Accepts the IMG-<digits> string form or a bare integer ID; anything
    else has no internal number and returns None.
    """
    if isinstance(item_id, bool):
        return None
    if isinstance(item_id, int):
        return item_id
    if isinstance(item_id, str):
        m = _IMG_ID_RE.match(item_id.strip())
        if m:
            return int(m.group(1))
        if item_id.strip().isdigit():
            return int(item_id.strip())
    return None


def delivered_filename(item_id):
    """The canonical delivered filename for an internal ID (Item 26).

    Two-digit Image-NN.png: the number is zero-padded to two digits and
    grows naturally past 99 (IMG-001 -> Image-01.png, IMG-012 ->
    Image-12.png, IMG-123 -> Image-123.png). This is the save-naming
    derivation the generation route (references/kie-generation-route.md)
    and the SOP delivery text both state. Returns None when the ID has
    no internal number.
    """
    n = internal_number(item_id)
    if n is None:
        return None
    return f"Image-{n:02d}.png"


def _named_file_number(value):
    """Trailing number of an IMG-<n> / Image-<n> file name, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    m = _NAMED_FILE_RE.match(Path(value.strip()).stem)
    return int(m.group(1)) if m else None


def filename_mapping_errors(prefix, item, item_id):
    """Item 26 mapping check for one manifest entry.

    The entry's delivered filename must be exactly the canonical
    two-digit name for its three-digit internal ID, and any of its
    files named in the IMG-<n> / Image-<n> form must carry the same
    number, so the delivered file, the manifest entry, and its receipt
    map to exactly one internal ID.
    """
    errors = []
    n = internal_number(item_id)
    if n is None:
        return errors
    filename = item.get("filename")
    if isinstance(filename, str) and filename.strip():
        expected = delivered_filename(item_id)
        actual = Path(filename.strip()).name
        if actual != expected:
            errors.append(
                f"{prefix}.filename {actual!r} does not map to internal id "
                f"{item_id!r}: delivered files use the two-digit "
                f"Image-NN.png form, expected {expected!r} (Item 26)."
            )
    for key in ("prompt_file", "asset_file", "asset_path"):
        value = item.get(key)
        other = _named_file_number(value)
        if other is not None and other != n:
            errors.append(
                f"{prefix}.{key} {value!r} carries number {other} but the "
                f"entry's internal id is {item_id!r} (number {n}); a "
                f"delivered file maps to exactly one internal id (Item 26)."
            )
    return errors


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
        if circle_image.entry_shape(item) == "circle":
            for reason in circle_image.shape_failures(circle_image.alpha_stats(path)):
                errors.append(f"{prefix}.asset {asset} is a circle slot but: {reason}.")
    return errors


def shape_errors(prefix, item):
    """Static slot-shape rules for one entry (design styles B and C)."""
    shape = circle_image.entry_shape(item)
    if shape not in ("rect", "circle"):
        return [f"{prefix}.shape must be rect or circle, got {shape!r}."]
    if shape != "circle":
        return []
    out = []
    ratio = item.get("intended_ratio") or item.get("aspect_ratio") or item.get("ratio")
    if ratio not in (None, "1:1"):
        out.append(f"{prefix} is a circle slot and must declare ratio 1:1 (generated square), got {ratio!r}.")
    ring = item.get("ring")
    if ring is not None and not (isinstance(ring, dict) and circle_image.HEX.match(str(ring.get("color", "")))):
        out.append(f"{prefix}.ring needs a client brand color as #RRGGBB (no default color).")
    return out


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

        errors.extend(shape_errors(prefix, item))

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
        errors.extend(filename_mapping_errors(prefix, item, item_id))
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
