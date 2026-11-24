#!/usr/bin/env python3
"""The wireframe section plan, built by a tool from the run's own inputs (SWB-400 item 2).

<stage>/section-plan.json (stage desktop-wireframe or mobile-tablet) is the annotation record the wireframe
validator, the image stages and the hybrid board read. Until 1.3.54 no tool wrote it: a layout agent typed it by
hand and it went stale (a section 2 note about a table the copy no longer carried, a slot ratio the spec had
since changed). This module is the one writer and the one staleness check:

  build(request, stage, run_dir)         the plan, from tool inputs ONLY:
      production-request.json (built for the stage)   section ids, names, slots, printed behavior notes
      copy/copy-manifest.json                          the section ids the plan must equal, in order
      font-action-plan/font-map.json                   type specs (scripts/font_sizes.py)
      desktop-wireframe/image-inventory.json           slot ids, ratios, treatments (the closed inventory)
      references/wireframe-build-spec.json             the header strip's widths
  staleness_failures(plan, stage, run_dir)   named lines when the plan is not the current request's: a section
      name, a behavior note or a slot ratio that differs, a slot count that differs, or a plan header whose
      request sha is not the request's. Used by validate_wireframe.py as a check on top of its own.

Plan shape: the contract in references/artifact-contracts.md (an ordered array of sections). The first section
also carries `plan_header` {written_by, stage, request_sha256}: the sha256 of the production-request.json file
the plan was built from.

Never calls a provider and never reads a secret; writes nothing (scripts/write_section_plan.py writes).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import composition
import font_sizes
import page_kinds
import page_role
import validate_wireframe as vw
import wireframe_spec

STAGES = ("desktop-wireframe", "mobile-tablet")
WRITER = "scripts/write_section_plan.py"
INVENTORY = Path("desktop-wireframe") / "image-inventory.json"
MANIFEST = Path("copy") / "copy-manifest.json"


class PlanError(Exception):
    """A named refusal."""


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanError(f"{what} ({path}) cannot be read: {exc}")


def requests_for_stage(run_dir, stage) -> list:
    """[(request, path, sha256)] for the run's request files built for this stage: production-request.json
    (the runner rebuilds it per stage) first, then the saved production-request-<stage>.json."""
    out = []
    run_dir = Path(run_dir)
    for path in (run_dir / "production-request.json", run_dir / f"production-request-{stage}.json"):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = data.get("metadata") if isinstance(data, dict) and isinstance(data.get("metadata"), dict) else {}
        if meta.get("stage") == stage:
            out.append((data, path, sha256_file(path)))
    return out


def printed_slots(request, section):
    """The request section's image slots, in order."""
    return [s for s in section.get("slots") or [] if isinstance(s, dict)]


def _norm_ratio(value):
    return vw.parse_ratio(value)


def _ratio_text(value) -> str:
    return str(value or "").strip()


def inventory_for(run_dir):
    """({id: entry}, [entries]) from the closed image inventory."""
    path = Path(run_dir) / INVENTORY
    if not path.is_file():
        raise PlanError(f"{INVENTORY} is not on disk: the plan's slot ids and ratios come from the closed "
                        "image inventory")
    entries = vw.inventory_entries(_read(path, "the image inventory"))
    by_id = {}
    for entry in entries:
        eid = vw.entry_id(entry)
        if eid:
            by_id[eid] = entry
    return by_id, entries


def match_slot(slot, by_id):
    """The inventory entry for a request slot: by its slot_id or slot_name (the spec's own id, TY-IMG-01),
    else by the inventory id. None when the closed inventory has no such slot."""
    wanted = str(slot.get("slot_id") or "").strip()
    for eid, entry in by_id.items():
        names = {str(entry.get(k) or "").strip() for k in ("slot_id", "slot_name", "id")}
        if wanted and wanted in names:
            return eid, entry
    return None


def _printed_note(stage, section, request, index, total):
    return wireframe_spec.printed_note(stage, section, request, index, total)


def build(request, stage, run_dir, request_sha=None) -> list:
    if stage not in STAGES:
        raise PlanError(f"{stage!r} is not a wireframe stage ({', '.join(STAGES)})")
    run_dir = Path(run_dir)
    meta = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    if meta.get("stage") != stage:
        raise PlanError(f"the production request on disk was built for stage {meta.get('stage')!r}, not {stage!r}: "
                        "rebuild it for this stage (scripts/build_production_request.py --stage "
                        f"{stage}) before its plan is written")
    sections = [s for s in request.get("sections") or [] if isinstance(s, dict)]
    if not sections:
        raise PlanError("the production request carries no sections")
    manifest = vw.manifest_section_ids(_read(run_dir / MANIFEST, "the copy manifest"))
    ids = [str(s.get("section_id")) for s in sections]
    if manifest != ids:
        raise PlanError(f"the request's sections {ids} are not the copy manifest's {manifest} (copy/copy-manifest.json)")
    font_map = font_sizes.load(run_dir)
    if font_map is None:
        raise PlanError(f"{font_sizes.FONT_MAP} is not on disk: the plan's type specs come from the closed font plan")
    try:
        specs = font_sizes.plan_specs(font_map, stage)
    except font_sizes.FontMapError as exc:
        raise PlanError(str(exc))
    by_id, entries = inventory_for(run_dir)
    strip = wireframe_spec.spec()["header_strip"][stage]
    resolved = composition.assign_treatments(sections)
    plan, used = [], []
    for index, section in enumerate(sections, start=1):
        sid = str(section["section_id"])
        slot_ids, labels = [], {}
        for slot_index, slot in enumerate(printed_slots(request, section)):
            found = match_slot(slot, by_id)
            if not found:
                raise PlanError(f"section {sid} slot {slot.get('slot_id')!r}: the closed image inventory "
                                f"({INVENTORY}) has no slot by that id or name")
            eid, entry = found
            if entry.get("section_id") not in (None, "") and str(entry["section_id"]) != sid:
                raise PlanError(f"slot {eid} is in section {entry['section_id']} of the closed inventory but "
                                f"section {sid} of the request")
            want, have = _norm_ratio(slot.get("aspect_ratio")), vw.entry_ratio(entry)
            if want is not None and have is not None and abs(want - have) / have > vw.RATIO_TOLERANCE:
                raise PlanError(
                    f"section {sid} slot {slot.get('slot_id')!r}: the request plans {_ratio_text(slot.get('aspect_ratio'))} "
                    f"but the closed image inventory says {_ratio_text(entry.get('aspect_ratio') or entry.get('ratio'))} "
                    f"for {eid}; the closed inventory governs, so correct the spec or the request, never the plan")
            declared = slot.get("treatment")
            treatment = entry.get("treatment") or declared
            if not treatment:
                row = resolved[index - 1]["slots"]
                treatment = row[slot_index]["treatment"] if slot_index < len(row) else "split"
            if declared and entry.get("treatment") and declared != entry["treatment"]:
                raise PlanError(f"section {sid} slot {slot.get('slot_id')!r}: the request declares treatment "
                                f"{declared!r} but the closed inventory says {entry['treatment']!r} for {eid}")
            label = {"slot_id": eid,
                     "aspect_ratio": _ratio_text(entry.get("aspect_ratio") or entry.get("ratio") or slot.get("aspect_ratio")),
                     "art_direction": str(entry.get("art_direction") or slot.get("art_direction") or ""),
                     "treatment": treatment,
                     "mask": str(entry.get("mask") or entry.get("shape") or slot.get("shape") or "rect"),
                     "slot_name": str(slot.get("slot_id") or "")}
            if isinstance(slot.get("delivery_px"), dict):
                label["delivery_px"] = slot["delivery_px"]
            slot_ids.append(eid)
            used.append(eid)
            labels[eid] = label
        entry_out = {"section_id": sid, "section_number": index,
                     "section_name": str(section.get("section_name") or "").strip(),
                     "copy_block_ids": [f"S{sid}"],
                     "image_slot_ids": slot_ids, "slot_labels": labels,
                     "type_specs": dict(specs),
                     "behavior_notes": _printed_note(stage, section, request, index, len(sections)),
                     "reference_traits": []}
        if index == 1:
            entry_out["header_strip"] = {"page_width_px": strip["page_px"], "content_width_px": strip["content_px"]}
            entry_out["plan_header"] = {"written_by": WRITER, "stage": stage, "request_sha256": request_sha}
        plan.append(entry_out)
    unused = [eid for eid in by_id if eid not in used]
    if unused:
        raise PlanError(f"the closed image inventory holds slot(s) {unused} that no section of the request "
                        "places: every inventory slot belongs to one section")
    return plan


def validate(plan, stage, run_dir) -> list:
    """The wireframe validator's own checks on the plan record (ids, slots, annotations, labels). Slice
    presence and pixel measurements are not asked of a plan that is about to be drawn."""
    run_dir = Path(run_dir)
    by_id, _entries = inventory_for(run_dir)
    failures = []
    manifest = vw.manifest_section_ids(_read(run_dir / MANIFEST, "the copy manifest"))
    if [s.get("section_id") for s in plan] != manifest:
        failures.append(f"section ids {[s.get('section_id') for s in plan]} differ from the copy manifest {manifest}")
    placed = [i for s in plan for i in s.get("image_slot_ids") or []]
    for eid in by_id:
        if eid not in placed:
            failures.append(f"image slot {eid!r} is in the image inventory but assigned to no section")
    for eid in placed:
        if eid not in by_id:
            failures.append(f"image slot {eid!r} is in the plan but not in the image inventory")
    annotation = vw.annotation_failures(plan, stage)
    for trait in ("W1", "W2", "W5", "W6"):
        failures += annotation[trait]
    failures += vw.sequence_failures(plan)
    failures += vw.slot_label_failures(plan, by_id) + vw.ratio_label_failures(plan)
    return failures


def staleness_failures(plan, stage, run_dir) -> list:
    """Named lines when the plan is not the current request's. [] when the run has no request built for
    the stage (nothing to compare), or when the plan matches it."""
    found = requests_for_stage(run_dir, stage)
    if not found:
        return []
    header = None
    if plan and isinstance(plan[0], dict) and isinstance(plan[0].get("plan_header"), dict):
        header = plan[0]["plan_header"]
    sha = (header or {}).get("request_sha256")
    chosen = next((f for f in found if f[2] == sha), found[0])
    request, path, request_sha = chosen
    where = Path(path).name
    failures = []
    if header is None:
        failures.append(f"stale plan: {stage}/section-plan.json carries no plan_header, so it was not written by "
                        f"{WRITER} from {where} (rewrite it: python3 scripts/write_section_plan.py <run_dir> "
                        f"--stage {stage})")
    elif sha != request_sha:
        failures.append(f"stale plan: {stage}/section-plan.json was built from a request with sha256 "
                        f"{str(sha)[:12]}, but the request for this stage ({where}) is {request_sha[:12]}; "
                        f"rewrite the plan with {WRITER}")
    sections = [s for s in request.get("sections") or [] if isinstance(s, dict)]
    by_sid = {wireframe_spec.canon(s.get("section_id")): (i, s) for i, s in enumerate(sections, start=1)}
    for entry in plan:
        if not isinstance(entry, dict):
            continue
        sid = wireframe_spec.canon(entry.get("section_id"))
        if sid not in by_sid:
            failures.append(f"stale plan: section {entry.get('section_id')!r} is not a section of {where}")
            continue
        index, section = by_sid[sid]
        name, want = str(entry.get("section_name") or "").strip(), str(section.get("section_name") or "").strip()
        if name != want:
            failures.append(f"stale plan: section {sid} is named {name!r} in the plan but {want!r} in {where}")
        notes = entry.get("behavior_notes")
        have = notes if isinstance(notes, str) else next((n for n in notes or [] if isinstance(n, str) and n.strip()), "")
        try:
            printed = _printed_note(stage, section, request, index, len(sections))
        except Exception as exc:  # a request the sheet could not be drawn from
            failures.append(f"stale plan: the behavior note of section {sid} cannot be read from {where}: {exc}")
            continue
        if have.strip() != printed.strip():
            failures.append(f"stale plan: section {sid} behavior note is {have.strip()!r} in the plan but the "
                            f"sheet prints {printed.strip()!r} ({where})")
        slots = printed_slots(request, section)
        ids = [i for i in entry.get("image_slot_ids") or [] if isinstance(i, str)]
        if len(ids) != len(slots):
            failures.append(f"stale plan: section {sid} places {len(ids)} image slot(s) in the plan but {len(slots)} in {where}")
            continue
        labels = vw.slot_labels(entry)
        for slot, plan_slot in zip(slots, ids):
            want_ratio, have_ratio = _norm_ratio(slot.get("aspect_ratio")), vw.entry_ratio(labels.get(plan_slot) or {})
            if want_ratio is not None and (have_ratio is None or abs(want_ratio - have_ratio) / want_ratio > vw.RATIO_TOLERANCE):
                failures.append(f"stale plan: section {sid} slot {plan_slot} has ratio "
                                f"{(labels.get(plan_slot) or {}).get('aspect_ratio')!r} in the plan but "
                                f"{_ratio_text(slot.get('aspect_ratio'))!r} in {where}")
    return failures


if __name__ == "__main__":
    raise SystemExit("section_plan.py is a library; run scripts/write_section_plan.py")
