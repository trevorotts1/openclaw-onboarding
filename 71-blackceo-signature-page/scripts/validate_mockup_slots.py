#!/usr/bin/env python3
"""Validate a Skill 71 mockup stage's slots (Update Plan Item 15).

Usage:
  python3 scripts/validate_mockup_slots.py <run_dir> [stage]
  stage defaults to final-mockups, the single client-judged mockup
  stage (Update Plan Item 5). Mockup traits bind at final-mockups only:
  the visual-mockup layout proof's solid-block slots are by design and
  are never scored here.

The mockup gate (Item 15; trait M1 from Item 14: real photography in
every slot, zero placeholder slots): every image slot of the run must
trace, through the stage's section generation record
(<stage>/generation-record.json), to exactly one of:

  - a generated image file: the record entry names source "generated"
    and a file on disk, and the file is the generated asset for that
    slot -- the image-map entry for the slot (image-map-upload/
    image-map.json) when the map records one, else the generation
    stage's Image-NNN file whose number matches the slot's IMG-NNN id;
  - a placed supplied asset: the record entry names source "supplied",
    the run's inventory entry for the slot is a supplied entry (its
    source begins with "supplied", Update Plan Item 3), and the entry
    carries the Item 3 supplied-asset transport record
    {supplied_asset: true, sha256: <sha256 of the filed bytes>},
    verified against the actual bytes on disk.

The generation record's shape:

  {"stage": "final-mockups",
   "sections": [{"section_id": "hero",
                  "slots": [{"slot_id": "IMG-001",
                             "source": "generated",
                             "file": "image-generation-qc/Image-001.png"},
                            {"slot_id": "IMG-002",
                             "source": "supplied",
                             "file": "final-mockups/assets/logo.png",
                             "supplied_asset": true,
                             "sha256": "<sha256 of the filed bytes>"}]}]}

Every slot in desktop-wireframe/image-inventory.json must appear in
the record exactly once, in the section the wireframe section plan
assigns it to (when a plan is on record). A slot that traces to
neither -- a placeholder entry, a missing entry, a missing file, a
generated claim the map does not back, a supplied claim on a
non-supplied inventory entry, or a supplied sha256 that does not
match the filed bytes -- FAILs the close by name, one line per slot,
each naming trait M1.

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_STAGE = "final-mockups"
SLOT_NUM_RE = re.compile(r"(\d+)\s*$")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inventory_entries(data):
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


def is_supplied_entry(entry):
    """Item 3: a supplied asset's inventory source begins with 'supplied'."""
    source = entry.get("source") if isinstance(entry, dict) else None
    return isinstance(source, str) and source.strip().lower().startswith("supplied")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def slot_number(slot_id):
    m = SLOT_NUM_RE.search(slot_id or "")
    return int(m.group(1)) if m else None


def plan_slot_sections(run_dir):
    """{slot_id: section_id} from the desktop wireframe section plan,
    or None when no readable plan is on record."""
    path = run_dir / "desktop-wireframe" / "section-plan.json"
    if not path.exists():
        return None
    try:
        plan = load_json(path)
    except Exception:
        return None
    if not isinstance(plan, list):
        return None
    out = {}
    for section in plan:
        if isinstance(section, dict):
            for slot_id in section.get("image_slot_ids") or []:
                if isinstance(slot_id, str):
                    out[slot_id] = section.get("section_id")
    return out


def image_map_files(run_dir):
    """{slot_id: run-relative file} from image-map-upload/image-map.json,
    or {} when the map is absent or records nothing usable."""
    path = run_dir / "image-map-upload" / "image-map.json"
    if not path.exists():
        return {}
    try:
        data = load_json(path)
    except Exception:
        return {}
    out = {}
    entries = data.get("images") if isinstance(data, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            slot_id = entry.get("id") or entry.get("master_id")
            rel = entry.get("asset_file") or entry.get("file") or entry.get("filename")
            if isinstance(slot_id, str) and isinstance(rel, str) and rel:
                if "/" not in rel and "\\" not in rel:
                    rel = f"image-generation-qc/{rel}"
                out[slot_id] = rel
    return out


def check_run(run_dir, stage=DEFAULT_STAGE):
    """Return (failures, slot_count). failures empty means the mockup
    gate passes: every slot traces to a generated file or a placed
    supplied asset."""
    run_dir = Path(run_dir)
    inventory_path = run_dir / "desktop-wireframe" / "image-inventory.json"
    if not inventory_path.exists():
        return [f"stage {stage}: image inventory missing at "
                f"desktop-wireframe/image-inventory.json; the mockup "
                f"gate has no slot universe to trace"], 0
    try:
        inventory = load_json(inventory_path)
    except Exception as exc:
        return [f"stage {stage}: image inventory unreadable: {exc}"], 0
    entries = inventory_entries(inventory)
    inventory_by_id = {}
    for entry in entries:
        eid = entry_id(entry)
        if eid:
            inventory_by_id[eid] = entry
    if not inventory_by_id:
        return [f"stage {stage}: image inventory declares no slot ids; "
                f"the mockup gate has no slots to trace"], 0

    record_path = run_dir / stage / "generation-record.json"
    record_slots = {}  # slot_id -> (section_id, entry)
    record_failures = []
    if not record_path.exists():
        for slot_id in inventory_by_id:
            record_failures.append(
                f"stage {stage} slot {slot_id}: placeholder slot M1 "
                f"(real photography in every slot; zero placeholder "
                f"slots): no section generation record at "
                f"{stage}/generation-record.json, so the slot traces to "
                f"neither a generated image file nor a placed supplied asset")
        return record_failures, len(inventory_by_id)
    try:
        record = load_json(record_path)
    except Exception as exc:
        return [f"stage {stage}: section generation record "
                f"{stage}/generation-record.json unreadable: {exc}"], len(inventory_by_id)
    sections = record.get("sections") if isinstance(record, dict) else None
    if not isinstance(sections, list) or not sections:
        return [f"stage {stage}: section generation record "
                f"{stage}/generation-record.json carries no sections list; "
                f"no slot can trace through it"], len(inventory_by_id)
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = section.get("section_id")
        for entry in section.get("slots") or []:
            if not isinstance(entry, dict):
                continue
            slot_id = entry.get("slot_id") or entry.get("id")
            if not isinstance(slot_id, str) or not slot_id:
                continue
            if slot_id in record_slots:
                record_failures.append(
                    f"stage {stage} slot {slot_id}: the generation record "
                    f"traces the slot more than once (sections "
                    f"{record_slots[slot_id][0]!r} and {section_id!r}); "
                    f"one trace per slot is required")
            else:
                record_slots[slot_id] = (section_id, entry)

    plan_sections = plan_slot_sections(run_dir)
    map_files = image_map_files(run_dir)
    failures = list(record_failures)
    for slot_id, entry in record_slots.items():
        if slot_id not in inventory_by_id:
            failures.append(
                f"stage {stage} slot {slot_id}: the generation record "
                f"traces a slot that is not in the image inventory")

    for slot_id, inv_entry in inventory_by_id.items():
        traced = record_slots.get(slot_id)
        if traced is None:
            failures.append(
                f"stage {stage} slot {slot_id}: placeholder slot M1 "
                f"(real photography in every slot; zero placeholder "
                f"slots): the slot is absent from the section generation "
                f"record and traces to neither a generated image file "
                f"nor a placed supplied asset")
            continue
        section_id, entry = traced
        where = f"stage {stage} section {section_id} slot {slot_id}"
        if plan_sections is not None and slot_id in plan_sections \
                and plan_sections[slot_id] != section_id:
            failures.append(
                f"{where}: the generation record places the slot in "
                f"section {section_id!r} but the wireframe section plan "
                f"assigns it to section {plan_sections[slot_id]!r}")
        source = entry.get("source")
        rel = entry.get("file") or entry.get("asset_file")
        if source not in ("generated", "supplied"):
            failures.append(
                f"{where}: placeholder slot M1 (real photography in "
                f"every slot; zero placeholder slots): the generation "
                f"record entry names source {source!r}; a slot traces "
                f"only as 'generated' (a generated image file) or "
                f"'supplied' (a placed supplied asset)")
            continue
        if not isinstance(rel, str) or not rel:
            failures.append(
                f"{where}: placeholder slot M1: the generation record "
                f"entry names no file; the slot traces to neither a "
                f"generated image file nor a placed supplied asset")
            continue
        filed = run_dir / rel
        if not filed.is_file():
            failures.append(
                f"{where}: placeholder slot M1: the generation record "
                f"traces the slot to {rel}, which is not on disk; the "
                f"slot traces to neither a generated image file nor a "
                f"placed supplied asset")
            continue
        if source == "generated":
            if is_supplied_entry(inv_entry):
                failures.append(
                    f"{where}: the inventory records the slot as a "
                    f"supplied asset (source "
                    f"{inv_entry.get('source')!r}) but the generation "
                    f"record traces it as generated; supplied assets "
                    f"are placed as files, never generated (Item 3)")
                continue
            mapped = map_files.get(slot_id)
            if mapped is not None:
                if Path(mapped) != Path(rel):
                    failures.append(
                        f"{where}: the generation record traces the slot "
                        f"to generated file {rel} but the image map "
                        f"records {mapped} as the slot's generated "
                        f"asset; the trace does not reach a generated "
                        f"image file for this slot")
            else:
                number = slot_number(slot_id)
                expected_name = f"Image-{number:03d}.png" if number is not None else None
                if expected_name is None or filed.name != expected_name \
                        or filed.parent.name != "image-generation-qc":
                    failures.append(
                        f"{where}: the generation record traces the slot "
                        f"to {rel}, which is not the slot's generated "
                        f"asset (image-generation-qc/{expected_name or 'Image-NNN.png'} "
                        f"and no image-map entry backs another file); "
                        f"the slot traces to no generated image file")
        else:  # supplied
            if not is_supplied_entry(inv_entry):
                failures.append(
                    f"{where}: the generation record traces the slot as "
                    f"a supplied asset but the inventory entry is not a "
                    f"supplied entry (its source does not begin with "
                    f"'supplied'); the slot traces to neither a "
                    f"generated image file nor a placed supplied asset "
                    f"under Item 3's supplied-asset record")
                continue
            if entry.get("supplied_asset") is not True:
                failures.append(
                    f"{where}: supplied-asset trace carries no "
                    f"supplied_asset: true record (Item 3's "
                    f"supplied-asset record); the placement is not proven")
                continue
            recorded_sha = entry.get("sha256")
            if not isinstance(recorded_sha, str) or not recorded_sha:
                failures.append(
                    f"{where}: supplied-asset record carries no sha256 "
                    f"of the filed bytes (Item 3); the placement is "
                    f"not proven")
                continue
            actual_sha = sha256_file(filed)
            if actual_sha != recorded_sha:
                failures.append(
                    f"{where}: supplied-asset sha256 mismatch: the "
                    f"record carries {recorded_sha[:12]}... but the "
                    f"filed bytes hash to {actual_sha[:12]}... (Item 3)")
    return failures, len(inventory_by_id)


def main(argv):
    if len(argv) not in (2, 3):
        print("usage: validate_mockup_slots.py <run_dir> [stage]")
        return 2
    run_dir = Path(argv[1]).resolve()
    stage = argv[2] if len(argv) == 3 else DEFAULT_STAGE
    if not run_dir.exists():
        print(f"ERROR: run_dir does not exist: {run_dir}")
        return 2
    failures, count = check_run(run_dir, stage)
    if failures:
        print("FAIL")
        for line in failures:
            print(f"- {line}")
        return 1
    print(f"PASS: {stage} mockup gate: all {count} slot(s) trace through "
          f"the section generation record to a generated image file or a "
          f"placed supplied asset; zero placeholder slots (M1)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
