"""Python validation layer for the Skill 72 Motion Graphics V2 contracts.

This module is the CONTRACTS-owned validation layer for MG-007. It loads the
canonical Draft 2020-12 schema library (references/contracts-v2.schema.json),
validates each serialized job artifact against its named $def, and then runs
validate_job_semantics: the cross-file and cross-field rules from directive
Section 16.6 that JSON Schema alone cannot express.

Findings use the stable error categories from directive Section 16.9. The
exit-class-2 family is ordered MG_SCHEMA_INVALID, MG_UNKNOWN_COMPONENT,
MG_MODE_MISMATCH, MG_TIMELINE_INVALID; validate_job returns every finding
sorted by that blocking order, and first_error_category exposes the head.

CLI:
    python3 scripts/motion_contracts.py validate <job_dir>

Prints one JSON result {job_dir, valid, findings, first_error_category} to
stdout and exits 0 when the job is valid, 2 when findings exist.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "references" / "contracts-v2.schema.json"

SCHEMA_INVALID = "MG_SCHEMA_INVALID"
UNKNOWN_COMPONENT = "MG_UNKNOWN_COMPONENT"
MODE_MISMATCH = "MG_MODE_MISMATCH"
TIMELINE_INVALID = "MG_TIMELINE_INVALID"

# Section 16.9 blocking order within the input/contract error class.
CATEGORY_ORDER = [SCHEMA_INVALID, UNKNOWN_COMPONENT, MODE_MISMATCH, TIMELINE_INVALID]

MODES = ("powerpoint_graphic", "vsl_desktop", "vsl_mobile", "standalone_video")
VSL_MODES = ("vsl_desktop", "vsl_mobile")
INSERT_MODES = ("powerpoint_graphic", "vsl_desktop", "vsl_mobile")

# The only component registered in the V2 catalog today (directive 16.1).
# MG-018 registers further closed component schemas; dispatch validation keys
# on component_id plus component_version either way.
REGISTERED_COMPONENT_ID = "C05"
REGISTERED_COMPONENT_VERSION = "1.0.0"
REGISTERED_MOTION_KIND = "linear_bar_reveal"
DISPATCH_CONST_PATHS = {("component_id",), ("component_version",), ("motion", "kind")}

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")

_SCHEMA_CACHE: dict | None = None


def load_schema() -> dict:
    """Load the canonical contracts-v2 schema library."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE


def _validator_for(def_name: str) -> Draft202012Validator:
    schema = load_schema()
    if def_name not in schema.get("$defs", {}):
        raise KeyError(f"unknown contract definition: {def_name}")
    wrapper = {
        "$schema": schema["$schema"],
        "$ref": f"#/$defs/{def_name}",
        "$defs": schema["$defs"],
    }
    return Draft202012Validator(wrapper)


def _error_path(error) -> str:
    parts = [str(p) for p in error.absolute_path]
    return "/" + "/".join(parts) if parts else ""


def _raw_errors(document, def_name: str) -> list:
    validator = _validator_for(def_name)
    errors = list(validator.iter_errors(document))
    errors.sort(key=lambda e: (_error_path(e), e.message))
    return errors


def _is_conditional_branch_error(error) -> bool:
    """True when an error comes from a root-level allOf conditional branch.

    jsonschema flattens if/then branch failures into direct errors whose
    absolute_schema_path starts with the allOf keyword. Those branches encode
    cross-field agreements (mode, parent, audio, approval context) that
    validate_job_semantics classifies into the stable Section 16.9
    categories, so the schema stage must not also report them as
    MG_SCHEMA_INVALID.
    """
    return list(error.absolute_schema_path)[:1] == ["allOf"]


def validate_document(document, def_name: str) -> list[dict]:
    """Validate a parsed JSON document against a named $def.

    Returns structured errors: {path, message, validator}. Errors from
    root-level allOf conditional branches are not returned: the agreements
    they encode are classified by validate_job_semantics instead.
    """
    structured = []
    for error in _raw_errors(document, def_name):
        if _is_conditional_branch_error(error):
            continue
        structured.append(
            {
                "path": _error_path(error),
                "message": error.message,
                "validator": error.validator,
            }
        )
    return structured


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


def _load_json(path: Path):
    """Parse a JSON file strictly. Raises ValueError on any parse failure."""
    text = path.read_text(encoding="utf-8")
    return json.loads(text, parse_constant=_reject_constant)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finding(category: str, path: str, message: str) -> dict:
    return {"category": category, "path": path, "message": message}


def _schema_findings(document, def_name: str, label: str) -> list[dict]:
    return [
        _finding(SCHEMA_INVALID, f"{label}#{e['path']}", f"{label} fails {def_name} schema: {e['message']}")
        for e in validate_document(document, def_name)
    ]


def _scene_schema_findings(scene: dict, label: str) -> list[dict]:
    """Validate one scene document with the component dispatch rule.

    The registered scene definition is closed on C05 1.0.0 with motion kind
    linear_bar_reveal. When a scene's only schema failures are const
    mismatches on component_id, component_version, or motion.kind, the scene
    is addressed to a different component registration: an unknown
    component_id is MG_UNKNOWN_COMPONENT, while a known component_id with a
    wrong version or motion kind stays MG_SCHEMA_INVALID.
    """
    errors = [
        e for e in _raw_errors(scene, "scene") if not _is_conditional_branch_error(e)
    ]
    if not errors:
        return []
    dispatch_errors = [
        e
        for e in errors
        if e.validator == "const" and tuple(str(p) for p in e.absolute_path) in DISPATCH_CONST_PATHS
    ]
    if len(dispatch_errors) == len(errors):
        component_id = scene.get("component_id") if isinstance(scene, dict) else None
        if (
            isinstance(component_id, str)
            and ID_PATTERN.match(component_id)
            and component_id != REGISTERED_COMPONENT_ID
        ):
            return [
                _finding(
                    UNKNOWN_COMPONENT,
                    label,
                    f"scene {scene.get('id')!r} names unregistered component "
                    f"{component_id!r} version {scene.get('component_version')!r}; "
                    f"only {REGISTERED_COMPONENT_ID} {REGISTERED_COMPONENT_VERSION} is registered",
                )
            ]
        return [
            _finding(
                SCHEMA_INVALID,
                f"{label}#{_error_path(e)}",
                f"{label} fails scene schema: {e.message}",
            )
            for e in errors
        ]
    return [
        _finding(
            SCHEMA_INVALID,
            f"{label}#{_error_path(e)}",
            f"{label} fails scene schema: {e.message}",
        )
        for e in errors
    ]


def first_error_category(findings: list[dict]) -> str | None:
    """Return the first blocking category of an ordered findings list."""
    if not findings:
        return None
    return findings[0]["category"]


def _sort_findings(findings: list[dict]) -> list[dict]:
    rank = {category: i for i, category in enumerate(CATEGORY_ORDER)}
    return sorted(findings, key=lambda f: rank.get(f["category"], len(rank)))


def validate_job(job_dir) -> list[dict]:
    """Validate a serialized V2 job directory.

    Returns findings as {category, path, message} dicts sorted by the
    Section 16.9 blocking order. An empty list means the job is
    SCHEMA_VALID at the serialized-contract level.
    """
    findings, _semantic = _run_validation(job_dir)
    return findings


def validate_job_semantics(job_dir) -> list[dict]:
    """Return only the semantic findings for a job (directive Section 16.6).

    This is the semantic stage of validate_job: the component dispatch
    findings and every cross-file/cross-field rule, without the pure
    JSON Schema shape findings.
    """
    _findings, semantic = _run_validation(job_dir)
    return semantic


def _run_validation(job_dir) -> tuple[list[dict], list[dict]]:
    job_dir = Path(job_dir)
    findings: list[dict] = []
    semantic: list[dict] = []

    def load(name: str, required: bool = True):
        path = job_dir / name
        if not path.is_file():
            if required:
                findings.append(
                    _finding(SCHEMA_INVALID, name, f"required job artifact {name} is missing")
                )
            return None
        try:
            return _load_json(path)
        except (ValueError, OSError) as exc:
            findings.append(
                _finding(SCHEMA_INVALID, name, f"{name} is not parseable JSON: {exc}")
            )
            return None

    manifest = load("manifest.json")
    if manifest is None:
        return _sort_findings(findings), _sort_findings(semantic)
    if isinstance(manifest, dict):
        findings.extend(_schema_findings(manifest, "manifest", "manifest.json"))
    else:
        findings.append(_finding(SCHEMA_INVALID, "manifest.json", "manifest.json is not a JSON object"))
        return _sort_findings(findings), _sort_findings(semantic)

    storyboard = load("storyboard.json")
    if isinstance(storyboard, dict):
        findings.extend(_schema_findings(storyboard, "storyboard", "storyboard.json"))
    assets_doc = load("assets.json")
    if isinstance(assets_doc, dict):
        findings.extend(_schema_findings(assets_doc, "assets", "assets.json"))
    design = load("design.json")
    if isinstance(design, dict):
        findings.extend(_schema_findings(design, "design", "design.json"))
    timeline = load("timeline.json")
    if isinstance(timeline, dict):
        findings.extend(_schema_findings(timeline, "timeline", "timeline.json"))

    mode = manifest.get("mode")
    handoff = None
    handoff_path = job_dir / "parent-handoff.json"
    if handoff_path.is_file():
        handoff = load("parent-handoff.json", required=False)
        if isinstance(handoff, dict):
            findings.extend(_schema_findings(handoff, "parent_handoff", "parent-handoff.json"))

    # Scene spec files, dispatched through the component rule.
    scenes_by_id: dict[str, dict] = {}
    scene_files: dict[str, str] = {}
    manifest_scene_entries = manifest.get("scenes") if isinstance(manifest.get("scenes"), list) else []
    for entry in manifest_scene_entries:
        if not isinstance(entry, dict):
            continue
        spec = entry.get("spec")
        entry_id = entry.get("id")
        if not isinstance(spec, str):
            continue
        label = spec
        spec_path = (job_dir / spec).resolve()
        if job_dir.resolve() not in spec_path.parents and spec_path != job_dir.resolve():
            findings.append(
                _finding(SCHEMA_INVALID, label, f"scene spec path {spec} escapes the job directory")
            )
            continue
        if not spec_path.is_file():
            findings.append(
                _finding(SCHEMA_INVALID, label, f"referenced scene spec {spec} does not exist")
            )
            continue
        if label in scene_files:
            continue
        scene_files[label] = entry_id
        try:
            scene_doc = _load_json(spec_path)
        except (ValueError, OSError) as exc:
            findings.append(
                _finding(SCHEMA_INVALID, label, f"{label} is not parseable JSON: {exc}")
            )
            continue
        if isinstance(scene_doc, dict):
            scene_findings = _scene_schema_findings(scene_doc, label)
            findings.extend(scene_findings)
            semantic.extend(f for f in scene_findings if f["category"] == UNKNOWN_COMPONENT)
            scene_id = scene_doc.get("id")
            if isinstance(scene_id, str):
                scenes_by_id[scene_id] = scene_doc
            if isinstance(entry_id, str) and isinstance(scene_id, str) and scene_id != entry_id:
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        label,
                        f"scene file id {scene_id!r} does not match manifest scene id {entry_id!r}",
                    )
                )

    # Datasets: every JSON file under data/, validated against dataset.
    datasets: dict[str, dict] = {}
    data_dir = job_dir / "data"
    if data_dir.is_dir():
        for dataset_path in sorted(data_dir.glob("*.json")):
            label = f"data/{dataset_path.name}"
            try:
                dataset_doc = _load_json(dataset_path)
            except (ValueError, OSError) as exc:
                findings.append(
                    _finding(SCHEMA_INVALID, label, f"{label} is not parseable JSON: {exc}")
                )
                continue
            if isinstance(dataset_doc, dict):
                findings.extend(_schema_findings(dataset_doc, "dataset", label))
                datasets[label] = dataset_doc

    cross_field = _semantic_findings(
        manifest=manifest,
        storyboard=storyboard if isinstance(storyboard, dict) else None,
        timeline=timeline if isinstance(timeline, dict) else None,
        handoff=handoff if isinstance(handoff, dict) else None,
        handoff_present=handoff_path.is_file(),
        scenes_by_id=scenes_by_id,
        manifest_scene_entries=manifest_scene_entries,
        datasets=datasets,
    )
    semantic.extend(cross_field)
    findings.extend(cross_field)
    return _sort_findings(findings), _sort_findings(semantic)


def _semantic_findings(
    *,
    manifest: dict,
    storyboard: dict | None,
    timeline: dict | None,
    handoff: dict | None,
    handoff_present: bool,
    scenes_by_id: dict[str, dict],
    manifest_scene_entries: list,
    datasets: dict[str, dict],
) -> list[dict]:
    findings: list[dict] = []
    mode = manifest.get("mode")
    canvas = manifest.get("canvas") if isinstance(manifest.get("canvas"), dict) else {}
    width = canvas.get("width")
    height = canvas.get("height")
    duration = manifest.get("duration_frames")

    # --- Scene identity: unique IDs, one consistent set across artifacts.
    manifest_ids = [e.get("id") for e in manifest_scene_entries if isinstance(e, dict)]
    manifest_ids = [i for i in manifest_ids if isinstance(i, str)]
    seen: set[str] = set()
    for scene_id in manifest_ids:
        if scene_id in seen:
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    "manifest.json:scenes",
                    f"duplicate scene id {scene_id!r} in manifest scenes",
                )
            )
        seen.add(scene_id)
    manifest_id_set = set(manifest_ids)

    if storyboard is not None:
        beats = storyboard.get("beats") if isinstance(storyboard.get("beats"), list) else []
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            beat_scene = beat.get("scene_id")
            if isinstance(beat_scene, str) and beat_scene not in manifest_id_set:
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        "storyboard.json:beats",
                        f"storyboard beat {beat.get('id')!r} references scene {beat_scene!r} "
                        "which is not in the manifest",
                    )
                )

    timeline_scenes: list = []
    if timeline is not None:
        timeline_scenes = timeline.get("scenes") if isinstance(timeline.get("scenes"), list) else []
        timeline_ids = [s.get("id") for s in timeline_scenes if isinstance(s, dict)]
        timeline_ids = [i for i in timeline_ids if isinstance(i, str)]
        timeline_seen: set[str] = set()
        for scene_id in timeline_ids:
            if scene_id in timeline_seen:
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        "timeline.json:scenes",
                        f"duplicate scene id {scene_id!r} in timeline scenes",
                    )
                )
            timeline_seen.add(scene_id)
        for scene_id in sorted(manifest_id_set - timeline_seen):
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    "timeline.json:scenes",
                    f"manifest scene {scene_id!r} has no timeline entry",
                )
            )
        for scene_id in sorted(timeline_seen - manifest_id_set):
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    "timeline.json:scenes",
                    f"timeline scene {scene_id!r} is not in the manifest",
                )
            )

    # --- Canvas: mode aspect ratios and H.264 even dimensions.
    if _is_int(width) and _is_int(height):
        is_16_9 = width * 9 == height * 16
        is_9_16 = width * 16 == height * 9
        if mode in ("powerpoint_graphic", "vsl_desktop") and not is_16_9:
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:canvas",
                    f"mode {mode} requires a 16:9 canvas; got {width}x{height}",
                )
            )
        elif mode == "vsl_mobile" and not is_9_16:
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:canvas",
                    f"mode vsl_mobile requires a 9:16 canvas; got {width}x{height}",
                )
            )
        elif mode == "standalone_video" and not (is_16_9 or is_9_16):
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:canvas",
                    f"standalone_video permits only 16:9 or 9:16 canvases; got {width}x{height}",
                )
            )
        if width % 2 != 0 or height % 2 != 0:
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:canvas",
                    f"H.264 dimensions must be even; got {width}x{height}",
                )
            )

    # --- Parent ownership by mode.
    parent = manifest.get("parent")
    if mode in VSL_MODES:
        if not isinstance(parent, dict):
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:parent",
                    f"mode {mode} requires a parent handoff; manifest parent is null",
                )
            )
        else:
            for e in validate_document(parent, "parent"):
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        f"manifest.json:parent#{e['path']}",
                        f"manifest parent fails parent schema: {e['message']}",
                    )
                )
        if not handoff_present:
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "parent-handoff.json",
                    f"mode {mode} requires parent-handoff.json in the job directory",
                )
            )
    elif mode in ("powerpoint_graphic", "standalone_video"):
        if parent is not None:
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:parent",
                    f"mode {mode} must not declare a parent",
                )
            )

    # --- Execution context and approval policy agreement.
    context = manifest.get("execution_context")
    policy = manifest.get("approval_policy")
    if context == "fixture" and policy != "fixture_only":
        findings.append(
            _finding(
                SCHEMA_INVALID,
                "manifest.json:approval_policy",
                "fixture execution_context requires approval_policy fixture_only",
            )
        )
    if context == "production" and policy != "owner_or_existing_authorized_reviewer":
        findings.append(
            _finding(
                SCHEMA_INVALID,
                "manifest.json:approval_policy",
                "production execution_context requires approval_policy "
                "owner_or_existing_authorized_reviewer",
            )
        )

    # --- Content scope agreement.
    if mode in INSERT_MODES and manifest.get("content_scope") != "insert":
        findings.append(
            _finding(
                MODE_MISMATCH,
                "manifest.json:content_scope",
                f"mode {mode} requires content_scope insert",
            )
        )

    # --- Timeline agreement.
    if timeline is not None and _is_int(duration):
        total = timeline.get("total_frames")
        if _is_int(total) and total != duration:
            findings.append(
                _finding(
                    TIMELINE_INVALID,
                    "timeline.json:total_frames",
                    f"timeline total_frames {total} does not equal manifest duration_frames {duration}",
                )
            )
        for entry in timeline_scenes:
            if not isinstance(entry, dict):
                continue
            start = entry.get("start_frame")
            end = entry.get("end_frame_exclusive")
            scene_id = entry.get("id")
            if _is_int(start) and _is_int(end):
                if not start < end:
                    findings.append(
                        _finding(
                            TIMELINE_INVALID,
                            "timeline.json:scenes",
                            f"timeline scene {scene_id!r} has an empty or reversed interval "
                            f"[{start}, {end})",
                        )
                    )
                if start < 0 or end > duration:
                    findings.append(
                        _finding(
                            TIMELINE_INVALID,
                            "timeline.json:scenes",
                            f"timeline scene {scene_id!r} interval [{start}, {end}) lies "
                            f"outside the job duration of {duration} frames",
                        )
                    )
                scene_doc = scenes_by_id.get(scene_id) if isinstance(scene_id, str) else None
                if scene_doc is not None and _is_int(scene_doc.get("duration_frames")):
                    if end - start != scene_doc["duration_frames"]:
                        findings.append(
                            _finding(
                                TIMELINE_INVALID,
                                "timeline.json:scenes",
                                f"timeline scene {scene_id!r} spans {end - start} frames but "
                                f"the scene file declares {scene_doc['duration_frames']}",
                            )
                        )

    # --- Scene motion intervals.
    for scene_id, scene_doc in scenes_by_id.items():
        motion = scene_doc.get("motion") if isinstance(scene_doc.get("motion"), dict) else {}
        start = motion.get("start_frame")
        end = motion.get("end_frame_exclusive")
        hold = motion.get("hold_to_frame_exclusive")
        scene_duration = scene_doc.get("duration_frames")
        label = f"scenes/{scene_id}:motion"
        if _is_int(start) and _is_int(end) and not start < end:
            findings.append(
                _finding(
                    TIMELINE_INVALID,
                    label,
                    f"scene {scene_id!r} motion interval [{start}, {end}) is empty or reversed",
                )
            )
        if _is_int(end) and _is_int(hold) and end > hold:
            findings.append(
                _finding(
                    TIMELINE_INVALID,
                    label,
                    f"scene {scene_id!r} motion ends at frame {end}, after its hold ends at {hold}",
                )
            )
        if _is_int(hold) and _is_int(scene_duration) and hold > scene_duration:
            findings.append(
                _finding(
                    TIMELINE_INVALID,
                    label,
                    f"scene {scene_id!r} motion holds to frame {hold}, beyond the scene "
                    f"duration of {scene_duration} frames",
                )
            )
        if _is_int(start) and _is_int(scene_duration) and start >= scene_duration:
            findings.append(
                _finding(
                    TIMELINE_INVALID,
                    label,
                    f"scene {scene_id!r} motion starts at frame {start}, outside the scene "
                    f"duration of {scene_duration} frames",
                )
            )

    # --- VSL parent slot length equals the insert length.
    if mode in VSL_MODES and _is_int(duration):
        slot_sources: list[tuple[str, object]] = []
        if isinstance(parent, dict) and isinstance(parent.get("slot"), dict):
            slot_sources.append(("manifest.json:parent.slot", parent["slot"]))
        if timeline is not None and isinstance(timeline.get("parent_slot"), dict):
            slot_sources.append(("timeline.json:parent_slot", timeline["parent_slot"]))
        if handoff is not None and isinstance(handoff.get("slot"), dict):
            slot_sources.append(("parent-handoff.json:slot", handoff["slot"]))
        for label, slot in slot_sources:
            start = slot.get("start_frame")  # type: ignore[union-attr]
            end = slot.get("end_frame_exclusive")  # type: ignore[union-attr]
            if _is_int(start) and _is_int(end) and end - start != duration:
                findings.append(
                    _finding(
                        TIMELINE_INVALID,
                        label,
                        f"parent slot length {end - start} frames does not equal the insert "
                        f"length of {duration} frames",
                    )
                )

    # --- Dataset semantics: finite values, unique IDs, exact increasing domain.
    for label, dataset in datasets.items():
        rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
        row_ids: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not math.isfinite(value):
                    findings.append(
                        _finding(
                            SCHEMA_INVALID,
                            f"{label}:rows",
                            f"dataset row {row.get('id')!r} has a non-finite value {value!r}",
                        )
                    )
            if isinstance(row.get("id"), str):
                row_ids.append(row["id"])
        if len(row_ids) != len(set(row_ids)):
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    f"{label}:rows",
                    "dataset category IDs are not unique",
                )
            )
        domain = dataset.get("domain")
        if isinstance(domain, list):
            if len(domain) != 2:
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        f"{label}:domain",
                        f"dataset domain must have exactly two endpoints; got {len(domain)}",
                    )
                )
            elif all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in domain
            ):
                if not all(math.isfinite(v) for v in domain):
                    findings.append(
                        _finding(
                            SCHEMA_INVALID,
                            f"{label}:domain",
                            "dataset domain endpoints must be finite",
                        )
                    )
                elif not domain[0] < domain[1]:
                    findings.append(
                        _finding(
                            SCHEMA_INVALID,
                            f"{label}:domain",
                            f"dataset domain must be strictly increasing; got {domain}",
                        )
                    )

    # --- Audio ownership agreement.
    audio = manifest.get("audio") if isinstance(manifest.get("audio"), dict) else {}
    audio_mode = audio.get("mode")
    if isinstance(audio, dict) and audio_mode is not None:
        if mode == "powerpoint_graphic" and audio_mode != "none":
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:audio",
                    "powerpoint_graphic graphics are silent; audio.mode must be none",
                )
            )
        if mode in VSL_MODES:
            # The canonical schema (manifest allOf, VSL branch) pins
            # audio.mode to the constant "inherited" and requires a string
            # parent_audio_ref; JSON Schema is canonical (Section 5.1), so
            # the earlier prose allowance of "none" for VSL modes does not
            # apply. Violations of a mode-conditional clause classify as
            # MG_MODE_MISMATCH, matching the TypeScript layer.
            if audio_mode != "inherited":
                findings.append(
                    _finding(
                        MODE_MISMATCH,
                        "manifest.json:audio",
                        f"VSL inserts inherit parent audio; audio.mode must be "
                        f"'inherited' for mode {mode}, got {audio_mode!r}",
                    )
                )
            else:
                parent_audio_ref = audio.get("parent_audio_ref")
                if not isinstance(parent_audio_ref, str) or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", parent_audio_ref
                ):
                    findings.append(
                        _finding(
                            MODE_MISMATCH,
                            "manifest.json:audio",
                            "VSL inserts with inherited audio must name the parent "
                            "audio asset in audio.parent_audio_ref",
                        )
                    )
            if audio.get("create_voiceover") or audio.get("create_music"):
                findings.append(
                    _finding(
                        MODE_MISMATCH,
                        "manifest.json:audio",
                        "VSL inserts must not create voiceover or music; the parent owns audio",
                    )
                )
        if mode == "standalone_video" and audio_mode == "inherited":
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:audio",
                    "standalone_video has no parent to inherit audio from",
                )
            )
        if audio_mode == "none" and (
            audio.get("create_voiceover") or audio.get("create_music") or audio.get("source_assets")
        ):
            findings.append(
                _finding(
                    MODE_MISMATCH,
                    "manifest.json:audio",
                    "audio.mode none cannot create voiceover or music or attach source assets",
                )
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Skill 72 Motion Graphics V2 jobs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="Validate a serialized V2 job directory.")
    validate_parser.add_argument("job_dir", help="Path to the job directory.")
    args = parser.parse_args(argv)

    if args.command == "validate":
        job_dir = Path(args.job_dir)
        if not job_dir.is_dir():
            result = {
                "job_dir": args.job_dir,
                "valid": False,
                "findings": [
                    _finding(SCHEMA_INVALID, args.job_dir, f"job directory {args.job_dir} does not exist")
                ],
                "first_error_category": SCHEMA_INVALID,
            }
            print(json.dumps(result, indent=2))
            return 2
        findings = validate_job(job_dir)
        result = {
            "job_dir": args.job_dir,
            "valid": not findings,
            "findings": findings,
            "first_error_category": first_error_category(findings),
        }
        print(json.dumps(result, indent=2))
        return 0 if not findings else 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
