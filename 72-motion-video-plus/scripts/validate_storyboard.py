"""Planner output validator for Skill 72 Motion Graphics V2 storyboards (MG-009).

The canonical contracts layer (scripts/motion_contracts.py) proves that a
storyboard is shaped like the contracts-v2 ``storyboard`` definition. Shape
alone does not prove a plan tells a visual story: a storyboard can be
schema-valid and still be a list of headlines. This validator is the planner
gate from directive MG-009. It runs the shipped storyboard schema first and
then enforces the planner rules JSON Schema cannot express:

- Every beat carries a complete planner record (the planner record layer,
  ``planner.json`` beside the storyboard, carries the MG-009 / Section 5.3
  fields the closed beat definition cannot: idea, viewer takeaway,
  literal-vs-metaphor evidence kind, component and engine selection with a
  reason, reading order, readable hold, and transition ownership).
- Section 1.1 coverage: at least two-thirds of explanatory beats, rounding
  up, must be information-bearing non-text (chart, image, mechanism, or
  diagram). Typography beats always count as text; a typography-only
  exception is a recorded rationale and never changes the count.
- Every explanatory typography beat carries its exception rationale.
- Every explanatory (qualifying) beat binds at least one semantic motion
  assertion from its scene file, and every bound assertion must concern the
  beat's own changing subjects. An assertion about an unrelated background
  subject does not satisfy a beat.
- Literal-evidence beats must reference exact assets/data that resolve in
  the job directory, and every referenced asset or dataset ID must resolve.

Findings use the same {category, path, message} shape as motion_contracts.
Storyboard shape failures keep the contracts category MG_SCHEMA_INVALID;
planner rule failures use the MG_PLANNER_* categories defined below.

CLI:
    python3 scripts/validate_storyboard.py validate <storyboard.json|job_dir>
        [--job-dir DIR]

Prints one JSON result {storyboard, job_dir, valid, coverage, findings,
first_error_category} and exits 0 when the plan passes, 2 on any finding.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motion_contracts  # noqa: E402

SCHEMA_INVALID = motion_contracts.SCHEMA_INVALID
FIELD_MISSING = "MG_PLANNER_FIELD_MISSING"
COVERAGE = "MG_PLANNER_COVERAGE"
EXCEPTION_MISSING = "MG_PLANNER_EXCEPTION_MISSING"
ASSERTION_MISSING = "MG_PLANNER_ASSERTION_MISSING"
ASSERTION_UNRESOLVED = "MG_PLANNER_ASSERTION_UNRESOLVED"
ASSERTION_SUBJECT_MISMATCH = "MG_PLANNER_ASSERTION_SUBJECT_MISMATCH"
EVIDENCE_UNRESOLVED = "MG_PLANNER_EVIDENCE_UNRESOLVED"
REPRESENTATION_REQUIREMENTS = "MG_PLANNER_REPRESENTATION_REQUIREMENTS"

# Blocking order: contract shape first, then planner rules in rule order.
CATEGORY_ORDER = [
    SCHEMA_INVALID,
    FIELD_MISSING,
    COVERAGE,
    EXCEPTION_MISSING,
    REPRESENTATION_REQUIREMENTS,
    ASSERTION_MISSING,
    ASSERTION_UNRESOLVED,
    ASSERTION_SUBJECT_MISMATCH,
    EVIDENCE_UNRESOLVED,
]

PLANNER_VERSION = "1.0"
PLANNER_FILENAME = "planner.json"

# Representations that carry information in a non-text subject (Section 1.1).
NON_TEXT_REPRESENTATIONS = ("chart", "image", "mechanism", "diagram")
REPRESENTATIONS = NON_TEXT_REPRESENTATIONS + ("typography",)
EVIDENCE_KINDS = ("literal_evidence", "illustrative_metaphor")
ENGINES = ("remotion", "hyperframes")


def _finding(category: str, path: str, message: str) -> dict:
    return {"category": category, "path": path, "message": message}


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


def _load_json(path: Path):
    """Parse a JSON file strictly, following motion_contracts' loader."""
    text = path.read_text(encoding="utf-8")
    return json.loads(text, parse_constant=_reject_constant)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_str(value) -> bool:
    return isinstance(value, str) and len(value.strip()) > 0


def first_error_category(findings: list[dict]) -> str | None:
    """Return the first blocking category of an ordered findings list."""
    if not findings:
        return None
    return findings[0]["category"]


def _sort_findings(findings: list[dict]) -> list[dict]:
    rank = {category: i for i, category in enumerate(CATEGORY_ORDER)}
    return sorted(findings, key=lambda f: rank.get(f["category"], len(rank)))


def required_non_text(explanatory_count: int) -> int:
    """Section 1.1 minimum: two-thirds of explanatory beats, rounding up."""
    return math.ceil(2 * explanatory_count / 3)


def coverage_report(storyboard: dict) -> dict:
    """Compute the Section 1.1 coverage numbers for a storyboard document."""
    beats = storyboard.get("beats") if isinstance(storyboard, dict) else None
    beats = beats if isinstance(beats, list) else []
    explanatory = [b for b in beats if isinstance(b, dict) and b.get("explanatory") is True]
    non_text = [b for b in explanatory if b.get("representation") in NON_TEXT_REPRESENTATIONS]
    typography = [b for b in explanatory if b.get("representation") == "typography"]
    required = required_non_text(len(explanatory))
    return {
        "explanatory_beats": len(explanatory),
        "non_text_beats": len(non_text),
        "typography_beats": len(typography),
        "required_non_text": required,
        "passes": len(explanatory) > 0 and len(non_text) >= required,
    }


def _job_indexes(job_dir: Path) -> tuple[dict, set, set, list]:
    """Index a job directory for planner resolution.

    Returns (scenes_by_id, asset_ids, dataset_ids, findings). Scene files are
    read from scenes/*.json and indexed by their document id; only the id
    and semantic_motion_assertions fields are consumed by the planner layer
    (full scene-spec validation remains motion_contracts' job). Asset IDs
    come from assets.json; dataset IDs from the id field of data/*.json.
    """
    findings: list[dict] = []
    scenes_by_id: dict[str, dict] = {}
    scenes_dir = job_dir / "scenes"
    if scenes_dir.is_dir():
        for scene_path in sorted(scenes_dir.glob("*.json")):
            label = f"scenes/{scene_path.name}"
            try:
                scene_doc = _load_json(scene_path)
            except (ValueError, OSError) as exc:
                findings.append(
                    _finding(SCHEMA_INVALID, label, f"{label} is not parseable JSON: {exc}")
                )
                continue
            if isinstance(scene_doc, dict) and isinstance(scene_doc.get("id"), str):
                scenes_by_id[scene_doc["id"]] = scene_doc

    asset_ids: set[str] = set()
    assets_path = job_dir / "assets.json"
    if assets_path.is_file():
        try:
            assets_doc = _load_json(assets_path)
        except (ValueError, OSError) as exc:
            findings.append(
                _finding(SCHEMA_INVALID, "assets.json", f"assets.json is not parseable JSON: {exc}")
            )
            assets_doc = None
        if isinstance(assets_doc, dict):
            for asset in assets_doc.get("assets") or []:
                if isinstance(asset, dict) and isinstance(asset.get("id"), str):
                    asset_ids.add(asset["id"])

    dataset_ids: set[str] = set()
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
            if isinstance(dataset_doc, dict) and isinstance(dataset_doc.get("id"), str):
                dataset_ids.add(dataset_doc["id"])

    return scenes_by_id, asset_ids, dataset_ids, findings


def _planner_records(job_dir: Path, storyboard: dict, findings: list[dict]) -> dict:
    """Load and structurally check planner.json; return records by beat id.

    A missing planner file is a planner finding (the plan was never run
    through the planner), not a schema failure. Structural mismatches
    between the planner record and the storyboard (wrong version, wrong
    storyboard id, duplicate or unknown beat ids) are MG_SCHEMA_INVALID:
    the two artifacts disagree about what plan this is.
    """
    planner_path = job_dir / PLANNER_FILENAME
    if not planner_path.is_file():
        findings.append(
            _finding(
                FIELD_MISSING,
                PLANNER_FILENAME,
                "no planner record (planner.json) sits beside the storyboard; "
                "every beat must carry the MG-009 planner fields",
            )
        )
        return {}
    try:
        planner = _load_json(planner_path)
    except (ValueError, OSError) as exc:
        findings.append(
            _finding(SCHEMA_INVALID, PLANNER_FILENAME, f"planner.json is not parseable JSON: {exc}")
        )
        return {}
    if not isinstance(planner, dict):
        findings.append(_finding(SCHEMA_INVALID, PLANNER_FILENAME, "planner.json is not a JSON object"))
        return {}
    if planner.get("planner_version") != PLANNER_VERSION:
        findings.append(
            _finding(
                SCHEMA_INVALID,
                PLANNER_FILENAME,
                f"planner_version must be {PLANNER_VERSION!r}; got {planner.get('planner_version')!r}",
            )
        )
    if planner.get("storyboard_id") != storyboard.get("id"):
        findings.append(
            _finding(
                SCHEMA_INVALID,
                PLANNER_FILENAME,
                f"planner record names storyboard {planner.get('storyboard_id')!r} but the "
                f"storyboard id is {storyboard.get('id')!r}",
            )
        )
    raw_beats = planner.get("beats")
    if not isinstance(raw_beats, list):
        findings.append(
            _finding(SCHEMA_INVALID, PLANNER_FILENAME, "planner.json beats must be an array")
        )
        return {}
    beat_ids = {
        b.get("id")
        for b in storyboard.get("beats") or []
        if isinstance(b, dict) and isinstance(b.get("id"), str)
    }
    records: dict[str, dict] = {}
    for entry in raw_beats:
        if not isinstance(entry, dict) or not isinstance(entry.get("beat_id"), str):
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    PLANNER_FILENAME,
                    "every planner beat record must be an object with a string beat_id",
                )
            )
            continue
        beat_id = entry["beat_id"]
        if beat_id in records:
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    PLANNER_FILENAME,
                    f"duplicate planner record for beat {beat_id!r}",
                )
            )
            continue
        if beat_id not in beat_ids:
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    PLANNER_FILENAME,
                    f"planner record names beat {beat_id!r}, which is not in the storyboard",
                )
            )
            continue
        records[beat_id] = entry
    return records


def _check_planner_fields(beat: dict, record: dict | None, findings: list[dict]) -> None:
    """Every beat carries the full MG-009 planner record fields."""
    beat_id = beat.get("id")
    label = f"planner.json:beats[{beat_id}]"
    if record is None:
        findings.append(
            _finding(FIELD_MISSING, label, f"beat {beat_id!r} has no planner record")
        )
        return
    explanatory = beat.get("explanatory") is True

    def missing(field: str, why: str) -> None:
        findings.append(
            _finding(FIELD_MISSING, f"{label}.{field}", f"beat {beat_id!r}: {why}")
        )

    if not _nonempty_str(record.get("idea")):
        missing("idea", "the planner record must state the beat's idea")
    if not _nonempty_str(record.get("viewer_takeaway")):
        missing("viewer_takeaway", "the planner record must state the viewer takeaway")
    evidence_kind = record.get("evidence_kind")
    if explanatory:
        if evidence_kind not in EVIDENCE_KINDS:
            missing(
                "evidence_kind",
                "an explanatory beat must declare literal_evidence or illustrative_metaphor",
            )
    elif evidence_kind is not None and evidence_kind not in EVIDENCE_KINDS:
        missing("evidence_kind", f"evidence_kind must be one of {EVIDENCE_KINDS} or null")
    if not _nonempty_str(record.get("component_id")):
        missing("component_id", "the planner must select a component before animation code")
    if record.get("engine") not in ENGINES:
        missing("engine", f"engine must be one of {ENGINES}")
    if not _nonempty_str(record.get("selection_reason")):
        missing("selection_reason", "the component/engine selection must carry a short reason")
    reading_order = record.get("reading_order")
    if (
        not isinstance(reading_order, list)
        or not reading_order
        or not all(_nonempty_str(item) for item in reading_order)
    ):
        missing("reading_order", "reading_order must name at least one element, first-read first")
    hold = record.get("readable_hold_frames")
    if not _is_int(hold) or hold < 0:
        missing("readable_hold_frames", "readable_hold_frames must be an integer frame count")
    elif explanatory and hold < 1:
        missing(
            "readable_hold_frames",
            "an explanatory beat needs a readable hold of at least one frame",
        )
    if not _nonempty_str(record.get("transition_owner")):
        missing("transition_owner", "every beat must name who owns its transition")
    stillness = record.get("intentional_stillness", False)
    if not isinstance(stillness, bool):
        missing("intentional_stillness", "intentional_stillness must be a boolean when present")
    elif stillness and not _nonempty_str(record.get("stillness_reason")):
        missing(
            "stillness_reason",
            "an intentionally still beat must record the reason for its stillness",
        )
    assertion_ids = record.get("assertion_ids")
    if not isinstance(assertion_ids, list) or not all(
        isinstance(a, str) for a in assertion_ids
    ):
        missing("assertion_ids", "assertion_ids must be an array of assertion id strings")


def _check_beat_rules(
    beat: dict,
    record: dict | None,
    scenes_by_id: dict,
    asset_ids: set,
    dataset_ids: set,
    findings: list[dict],
) -> None:
    beat_id = beat.get("id")
    label = f"storyboard.json:beats[{beat_id}]"
    explanatory = beat.get("explanatory") is True
    representation = beat.get("representation")
    beat_assets = beat.get("asset_ids") if isinstance(beat.get("asset_ids"), list) else []
    beat_data = beat.get("data_ids") if isinstance(beat.get("data_ids"), list) else []

    if explanatory and representation == "typography":
        if not _nonempty_str(beat.get("typography_only_exception")):
            findings.append(
                _finding(
                    EXCEPTION_MISSING,
                    label,
                    f"explanatory typography beat {beat_id!r} carries no "
                    "typography_only_exception rationale; a text-dominant beat must "
                    "record its approved reason, and the exception never changes "
                    "the coverage count",
                )
            )

    if explanatory and representation == "chart" and not beat_data:
        findings.append(
            _finding(
                REPRESENTATION_REQUIREMENTS,
                label,
                f"chart beat {beat_id!r} names no dataset in data_ids; a chart "
                "without exact data is a drawing, not a chart",
            )
        )
    if explanatory and representation == "image" and not beat_assets:
        findings.append(
            _finding(
                REPRESENTATION_REQUIREMENTS,
                label,
                f"image beat {beat_id!r} names no asset in asset_ids; an image-led "
                "beat must reference the exact image it shows",
            )
        )

    # Semantic assertion binding: qualifying (explanatory) beats only.
    if explanatory and record is not None:
        assertion_ids = record.get("assertion_ids")
        if isinstance(assertion_ids, list):
            if not assertion_ids:
                findings.append(
                    _finding(
                        ASSERTION_MISSING,
                        f"planner.json:beats[{beat_id}].assertion_ids",
                        f"explanatory beat {beat_id!r} binds no semantic motion "
                        "assertion; semantic proof is required for every qualifying beat",
                    )
                )
            else:
                scene_id = beat.get("scene_id")
                scene = scenes_by_id.get(scene_id) if isinstance(scene_id, str) else None
                if scene is None:
                    findings.append(
                        _finding(
                            ASSERTION_UNRESOLVED,
                            label,
                            f"beat {beat_id!r} references scene {scene_id!r}, which is "
                            "not among the job's scene files, so its assertions cannot "
                            "be resolved",
                        )
                    )
                else:
                    scene_assertions = {
                        a.get("id"): a
                        for a in scene.get("semantic_motion_assertions") or []
                        if isinstance(a, dict) and isinstance(a.get("id"), str)
                    }
                    beat_subjects = {
                        s for s in beat.get("subject_ids") or [] if isinstance(s, str)
                    }
                    for assertion_id in assertion_ids:
                        assertion = scene_assertions.get(assertion_id)
                        if assertion is None:
                            findings.append(
                                _finding(
                                    ASSERTION_UNRESOLVED,
                                    f"planner.json:beats[{beat_id}].assertion_ids",
                                    f"beat {beat_id!r} binds assertion {assertion_id!r}, "
                                    f"which scene {scene_id!r} does not declare",
                                )
                            )
                            continue
                        assertion_subjects = {
                            s
                            for s in assertion.get("subject_ids") or []
                            if isinstance(s, str)
                        }
                        if not (assertion_subjects & beat_subjects):
                            findings.append(
                                _finding(
                                    ASSERTION_SUBJECT_MISMATCH,
                                    f"planner.json:beats[{beat_id}].assertion_ids",
                                    f"assertion {assertion_id!r} bound to beat {beat_id!r} "
                                    f"concerns subjects {sorted(assertion_subjects)}, none "
                                    f"of which is the beat's changing subject "
                                    f"{sorted(beat_subjects)}; motion of an unrelated "
                                    "subject does not prove this beat",
                                )
                            )

    # Referenced assets and data must resolve in the job, whatever the beat
    # claims; a literal-evidence claim must reference something exact.
    for asset_id in beat_assets:
        if asset_id not in asset_ids:
            findings.append(
                _finding(
                    EVIDENCE_UNRESOLVED,
                    label,
                    f"beat {beat_id!r} references asset {asset_id!r}, which is not in "
                    "the job's assets.json",
                )
            )
    for data_id in beat_data:
        if data_id not in dataset_ids:
            findings.append(
                _finding(
                    EVIDENCE_UNRESOLVED,
                    label,
                    f"beat {beat_id!r} references dataset {data_id!r}, which is not "
                    "among the job's data files",
                )
            )
    if record is not None and record.get("evidence_kind") == "literal_evidence":
        if not beat_assets and not beat_data:
            findings.append(
                _finding(
                    EVIDENCE_UNRESOLVED,
                    f"planner.json:beats[{beat_id}].evidence_kind",
                    f"beat {beat_id!r} claims literal_evidence but references no exact "
                    "asset or dataset; literal evidence must name the actual asset or "
                    "data shown",
                )
            )


def validate_storyboard(storyboard_path, job_dir=None) -> list[dict]:
    """Validate one storyboard artifact plus its planner record.

    storyboard_path may name the storyboard JSON file or the job directory
    containing storyboard.json. job_dir defaults to the storyboard's own
    directory. Returns findings sorted by the planner blocking order; an
    empty list means the plan passes the planner gate.
    """
    storyboard_path = Path(storyboard_path)
    if storyboard_path.is_dir():
        job_dir = Path(job_dir) if job_dir is not None else storyboard_path
        storyboard_file = storyboard_path / "storyboard.json"
    else:
        storyboard_file = storyboard_path
        job_dir = Path(job_dir) if job_dir is not None else storyboard_path.parent

    findings: list[dict] = []
    if not storyboard_file.is_file():
        return [
            _finding(
                SCHEMA_INVALID,
                str(storyboard_file),
                f"storyboard file {storyboard_file} does not exist",
            )
        ]
    try:
        storyboard = _load_json(storyboard_file)
    except (ValueError, OSError) as exc:
        return [
            _finding(
                SCHEMA_INVALID,
                str(storyboard_file),
                f"storyboard is not parseable JSON: {exc}",
            )
        ]
    if not isinstance(storyboard, dict):
        return [
            _finding(SCHEMA_INVALID, "storyboard.json", "storyboard.json is not a JSON object")
        ]

    # Stage 1: the shipped storyboard schema, via the contracts layer.
    for error in motion_contracts.validate_document(storyboard, "storyboard"):
        findings.append(
            _finding(
                SCHEMA_INVALID,
                f"storyboard.json#{error['path']}",
                f"storyboard.json fails storyboard schema: {error['message']}",
            )
        )

    # Stage 2: job context and planner records.
    scenes_by_id, asset_ids, dataset_ids, index_findings = _job_indexes(job_dir)
    findings.extend(index_findings)
    records = _planner_records(job_dir, storyboard, findings)

    beats = storyboard.get("beats") if isinstance(storyboard.get("beats"), list) else []
    beats = [b for b in beats if isinstance(b, dict)]

    # Stage 3: coverage (Section 1.1). Computed from the storyboard alone so
    # the rule cannot be evaded by omitting the planner record.
    report = coverage_report(storyboard)
    if report["explanatory_beats"] == 0:
        findings.append(
            _finding(
                COVERAGE,
                "storyboard.json:beats",
                "the storyboard declares no explanatory beats; a plan that explains "
                "nothing cannot satisfy the Section 1.1 coverage rule",
            )
        )
    elif not report["passes"]:
        findings.append(
            _finding(
                COVERAGE,
                "storyboard.json:beats",
                f"Section 1.1 coverage fails: {report['non_text_beats']} of "
                f"{report['explanatory_beats']} explanatory beats are information-bearing "
                f"non-text, but at least {report['required_non_text']} are required "
                "(two-thirds, rounding up). Typography beats count as text even when "
                "they carry a typography_only_exception.",
            )
        )

    # Stage 4: per-beat planner fields and binding rules.
    for beat in beats:
        record = records.get(beat.get("id")) if isinstance(beat.get("id"), str) else None
        _check_planner_fields(beat, record, findings)
        _check_beat_rules(beat, record, scenes_by_id, asset_ids, dataset_ids, findings)

    return _sort_findings(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Skill 72 storyboards against the MG-009 planner rules."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate", help="Validate a storyboard file or job directory."
    )
    validate_parser.add_argument(
        "path", help="Path to storyboard.json or to the job directory holding it."
    )
    validate_parser.add_argument(
        "--job-dir",
        default=None,
        help="Job directory for planner/asset/data/scene resolution "
        "(default: the storyboard's directory).",
    )
    args = parser.parse_args(argv)

    if args.command == "validate":
        path = Path(args.path)
        storyboard_file = path / "storyboard.json" if path.is_dir() else path
        job_dir = Path(args.job_dir) if args.job_dir else storyboard_file.parent
        findings = validate_storyboard(path, job_dir)
        coverage = None
        if storyboard_file.is_file():
            try:
                coverage = coverage_report(_load_json(storyboard_file))
            except (ValueError, OSError):
                coverage = None
        result = {
            "storyboard": str(storyboard_file),
            "job_dir": str(job_dir),
            "valid": not findings,
            "coverage": coverage,
            "findings": findings,
            "first_error_category": first_error_category(findings),
        }
        print(json.dumps(result, indent=2))
        return 0 if not findings else 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
