#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

REQUIRED = [
    "id", "source_passage", "job", "scene", "people", "shot_plan",
    "style_grade", "text_mode", "references", "technical_plan",
    "filename", "status"
]
STATUSES = {"planned", "prompt_ready", "generated", "qc_failed", "ready"}
PROMPT_STATUSES = {"prompt_ready", "generated", "qc_failed", "ready"}
ASSET_STATUSES = {"generated", "qc_failed", "ready"}


def validate(data, base_dir=None, check_files=False):
    errors = []
    if not isinstance(data, dict) or not isinstance(data.get("images"), list):
        return ["Top-level JSON must contain an images array."]

    ids = []
    filenames = []
    for idx, item in enumerate(data["images"], start=1):
        prefix = f"images[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        for key in REQUIRED:
            if key not in item:
                errors.append(f"{prefix} missing required field {key!r}.")
        if not isinstance(item.get("references", []), list):
            errors.append(f"{prefix}.references must be an array.")
        status = item.get("status")
        if status not in STATUSES:
            errors.append(f"{prefix}.status is invalid: {status!r}.")
        item_id = item.get("id")
        filename = item.get("filename")
        if item_id:
            ids.append(item_id)
        if filename:
            filenames.append(filename)
        if status in PROMPT_STATUSES and not item.get("prompt_file"):
            errors.append(f"{prefix} with status {status!r} requires prompt_file.")
        if status in ASSET_STATUSES and not item.get("asset_file"):
            errors.append(f"{prefix} with status {status!r} requires asset_file.")

    duplicate_ids = sorted({x for x in ids if ids.count(x) > 1})
    duplicate_names = sorted({x for x in filenames if filenames.count(x) > 1})
    if duplicate_ids:
        errors.append("Duplicate image IDs: " + ", ".join(duplicate_ids))
    if duplicate_names:
        errors.append("Duplicate filenames: " + ", ".join(duplicate_names))

    id_set = set(ids)
    for idx, item in enumerate(data["images"], start=1):
        if not isinstance(item, dict):
            continue
        master_id = item.get("master_id")
        if master_id:
            if master_id == item.get("id"):
                errors.append(f"images[{idx}].master_id cannot reference itself.")
            elif master_id not in id_set:
                errors.append(f"images[{idx}].master_id references unknown ID {master_id!r}.")

    if check_files:
        base_dir = Path(base_dir or ".")
        for idx, item in enumerate(data["images"], start=1):
            if not isinstance(item, dict):
                continue
            for key in ("prompt_file", "asset_file"):
                value = item.get(key)
                if value and not (base_dir / value).exists():
                    errors.append(f"images[{idx}].{key} does not exist: {value}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate BlackCEO image-map JSON.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check-files", action="store_true")
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read JSON: {exc}")
        return 2

    errors = validate(data, args.manifest.parent, args.check_files)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS: {len(data['images'])} image-map entries are structurally valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
