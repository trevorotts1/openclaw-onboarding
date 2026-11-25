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
assigns it to (when a plan is on record).

The reverse-coverage floor: every slot the page PLANNED must appear in
the rendered mockup, whether or not the run's own inventory still lists
it. The plan is the run's request (production-request-final-mockups.json,
else production-request.json, else page-request.json) when it declares
slots, otherwise the copy spec for intake.json's copy_version (its
default_slots come from the section-image-prompt.md skeleton table). A
planned slot the generation record does not render is an ERROR naming
that slot, never a warning: a twelve-slot page rendered with two
pictures is exactly the defect this floor exists for.

A slot that traces to
neither -- a placeholder entry, a missing entry, a missing file, a
generated claim the map does not back, a supplied claim on a
non-supplied inventory entry, or a supplied sha256 that does not
match the filed bytes -- FAILs the close by name, one line per slot,
each naming trait M1.

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_STAGE = "final-mockups"
SLOT_NUM_RE = re.compile(r"(\d+)\s*$")
REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_SLOTS_REL = Path("signature_launch") / "design" / "image_slots.py"
IMAGE_SLOTS_PATH = REPO_ROOT / "shared-utils" / IMAGE_SLOTS_REL
COPY_SPECS_DIR = Path(__file__).resolve().parents[1] / "references" / "copy-specs"
REQUEST_FILES = ("production-request-final-mockups.json", "production-request.json",
                 "page-request.json")
_IMAGE_SLOTS = None

def image_slots_path():
    """The image-slot contract file: the sibling shared-utils (resolved, then as spelled), then
    OPENCLAW_SKILLS_DIR, ~/.openclaw/skills and /data/.openclaw/skills (SWB-570). A second, older
    skill copy under ~/.claude/skills has no sibling shared-utils of its own. Returns the first
    that exists, else the sibling path (so the failure names it)."""
    spelled = Path(os.path.abspath(__file__)).parents[2] / "shared-utils"
    roots = [REPO_ROOT / "shared-utils", spelled]
    if os.environ.get("OPENCLAW_SKILLS_DIR"):
        roots.append(Path(os.environ["OPENCLAW_SKILLS_DIR"]) / "shared-utils")
    roots += [Path.home() / ".openclaw" / "skills" / "shared-utils",
              Path("/data/.openclaw/skills/shared-utils")]
    for root in roots:
        if (root / IMAGE_SLOTS_REL).is_file():
            return root / IMAGE_SLOTS_REL
    return IMAGE_SLOTS_PATH

def image_slots():
    """shared-utils' one image-slot contract (the reverse-coverage floor)."""
    global _IMAGE_SLOTS
    if _IMAGE_SLOTS is None:
        spec = importlib.util.spec_from_file_location(
            "signature_launch_image_slots", image_slots_path())
        if spec is None or spec.loader is None:
            raise SystemExit(f"unreadable image-slot contract: {IMAGE_SLOTS_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _IMAGE_SLOTS = module
    return _IMAGE_SLOTS

def planned_slot_ids(run_dir):
    """(planned slot ids, where they came from) for this run.

    The run's own request wins when it declares slots; otherwise the copy spec
    for the run's ``copy_version`` is the plan (its ``default_slots`` come from
    the section-image-prompt.md skeleton table). This is the floor's universe:
    the inventory alone cannot be it, because a run that planned no image has a
    short inventory and would pass its own check.
    """
    for name in REQUEST_FILES:
        path = run_dir / name
        if not path.is_file():
            continue
        try:
            doc = load_json(path)
        except Exception:
            continue
        try:
            ids = image_slots().planned_slot_ids(doc)
        except ValueError:
            continue
        if ids:
            return ids, name
    try:
        intake = load_json(run_dir / "intake.json")
    except Exception:
        return [], None
    version = intake.get("copy_version") if isinstance(intake, dict) else None
    path = COPY_SPECS_DIR / f"{version}-v6.json"
    if not path.is_file():
        return [], None
    try:
        return image_slots().planned_slot_ids(load_json(path)), f"references/copy-specs/{path.name}"
    except ValueError:
        return [], None


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


def slot_key(slot_id):
    """The cross-namespace identity of one slot: its trailing number, else its text.

    The pipeline names the same slot ``IMG-001`` in the page request and
    ``Image-01`` in the inventory / image map / generation record; the
    inventory's own ``slot_name`` carries that bridge. The trailing integer is
    the one stable identity across those names, so every cross-file lookup is
    keyed by it. A slot id with no trailing number keeps its literal text as
    the key. Two DIFFERENT ids that share a number are ambiguous and fail
    closed (see ``keyed``), never silently merged.
    """
    text = str(slot_id or "").strip()
    m = SLOT_NUM_RE.search(text)
    return "#%d" % int(m.group(1)) if m else "id:%s" % text


def keyed(ids, items, where):
    """{slot_key: (slot_id, item)} plus ambiguity failures.

    ``ids`` and ``items`` are parallel sequences. Two different slot ids that
    resolve to the same key (e.g. ``IMG-001`` and ``PKG-1``) can never be told
    apart by the renderer, so they are reported by name instead of one quietly
    overwriting the other.
    """
    out, failures = {}, []
    for slot_id, item in zip(ids, items):
        if not isinstance(slot_id, str) or not slot_id:
            continue
        k = slot_key(slot_id)
        if k in out and out[k][0] != slot_id:
            failures.append(
                f"{where}: slots {out[k][0]!r} and {slot_id!r} share the "
                f"identity {k!r}; two different slot ids can never be told "
                f"apart by the renderer")
            continue
        out[k] = (slot_id, item)
    return out, failures


def plan_slot_sections(run_dir):
    """{slot_id: section_id} from the desktop wireframe section plan,
    or None when no readable plan is on record.

    Keyed by the id as written in the plan (its public shape, also read by
    ``design_board.py``); ``check_run`` re-keys it by ``slot_key`` when it
    compares namespaces.
    """
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
    """({slot_key: run-relative file}, failures) from
    image-map-upload/image-map.json, or ({}, []) when the map is absent or
    records nothing usable."""
    path = run_dir / "image-map-upload" / "image-map.json"
    if not path.exists():
        return {}, []
    try:
        data = load_json(path)
    except Exception:
        return {}, []
    ids, rels = [], []
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
                ids.append(slot_id)
                rels.append(rel)
    index, failures = keyed(ids, rels, "image-map-upload/image-map.json")
    return {k: v for k, (_, v) in index.items()}, failures


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
    inv_ids, inv_entries = [], []
    for entry in entries:
        eid = entry_id(entry)
        if eid:
            inv_ids.append(eid)
            inv_entries.append(entry)
    inventory_by_id, inventory_failures = keyed(
        inv_ids, inv_entries, "desktop-wireframe/image-inventory.json")
    if not inventory_by_id:
        return ([f"stage {stage}: image inventory declares no slot ids; "
                 f"the mockup gate has no slots to trace"] + inventory_failures), 0

    record_path = run_dir / stage / "generation-record.json"
    record_slots = {}  # slot_key -> (slot_id, section_id, entry)
    record_failures = list(inventory_failures)
    if not record_path.exists():
        for slot_id, _entry in inventory_by_id.values():
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
            k = slot_key(slot_id)
            if k in record_slots:
                prior_id, prior_section = record_slots[k][0], record_slots[k][1]
                if prior_id != slot_id:
                    record_failures.append(
                        f"stage {stage} slot {slot_id}: the generation record "
                        f"traces slots {prior_id!r} and {slot_id!r} as one "
                        f"identity; two different slot ids can never be told "
                        f"apart by the renderer")
                else:
                    record_failures.append(
                        f"stage {stage} slot {slot_id}: the generation record "
                        f"traces the slot more than once (sections "
                        f"{prior_section!r} and {section_id!r}); "
                        f"one trace per slot is required")
            else:
                record_slots[k] = (slot_id, section_id, entry)

    plan_display = plan_slot_sections(run_dir)
    plan_failures = []
    if plan_display is None:
        plan_sections = None
    else:
        plan_index, plan_failures = keyed(
            list(plan_display), list(plan_display.values()),
            "desktop-wireframe/section-plan.json")
        plan_sections = {k: v for k, (_, v) in plan_index.items()}
    map_files, map_failures = image_map_files(run_dir)
    failures = list(record_failures) + plan_failures + map_failures
    # The reverse-coverage floor: every PLANNED slot must appear in the rendered
    # mockup. The inventory check below can only police the slots the run itself
    # planned; a short plan is exactly how a twelve-slot page shipped with two
    # pictures, so the plan comes from the request (else the copy spec). Slots
    # are compared by their stable identity (slot_key) so the request's
    # ``IMG-001`` and the record's ``Image-01`` are the same picture.
    planned, planned_source = planned_slot_ids(run_dir)
    if planned:
        rendered_keys = set(record_slots)
        missing = [p for p in planned if slot_key(p) not in rendered_keys]
        total = len(planned)
        for slot_id in missing:
            failures.append(
                f"stage {stage} planned image slot {slot_id} is missing from "
                f"the rendered page ({total - len(missing)} of {total} "
                f"planned slot(s) rendered; every planned slot must carry "
                f"real photography) [plan: {planned_source}]")
    for k, (slot_id, _section, _entry) in record_slots.items():
        if k not in inventory_by_id:
            failures.append(
                f"stage {stage} slot {slot_id}: the generation record "
                f"traces a slot that is not in the image inventory")

    for k, (slot_id, inv_entry) in inventory_by_id.items():
        traced = record_slots.get(k)
        if traced is None:
            failures.append(
                f"stage {stage} slot {slot_id}: placeholder slot M1 "
                f"(real photography in every slot; zero placeholder "
                f"slots): the slot is absent from the section generation "
                f"record and traces to neither a generated image file "
                f"nor a placed supplied asset")
            continue
        section_id, entry = traced[1], traced[2]
        where = f"stage {stage} section {section_id} slot {slot_id}"
        if plan_sections is not None and k in plan_sections \
                and plan_sections[k] != section_id:
            failures.append(
                f"{where}: the generation record places the slot in "
                f"section {section_id!r} but the wireframe section plan "
                f"assigns it to section {plan_sections[k]!r}")
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
            mapped = map_files.get(k)
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
                expected_names = ({f"Image-{number:03d}.png",
                                   f"Image-{number:02d}.png"}
                                  if number is not None else set())
                if not expected_names or filed.name not in expected_names \
                        or filed.parent.name != "image-generation-qc":
                    failures.append(
                        f"{where}: the generation record traces the slot "
                        f"to {rel}, which is not the slot's generated "
                        f"asset (image-generation-qc/Image-{number if number is not None else 'NNN'}.png "
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
