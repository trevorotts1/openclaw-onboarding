"""Style-frame design gate for Skill 72 Motion Graphics V2 (MG-010).

Directive Section 16.8 fixes the lifecycle order: a job reaches
DESIGN_APPROVED only after style frames exist for its representative
scenes and a trusted design approval covers them. Animation cannot rescue
a weak composition, so this gate runs BEFORE final animation authoring:
it proves the style-frame set exists, that the frame bytes on disk are
the bytes the records describe, that a design approval names the exact
frame hashes and the current design revision, and that the job's record
sequence shows the frames before any animation artifact.

Records this gate reads (all inside the job directory):

- ``manifest.json``: the canonical job identity (job_id, company_id,
  execution_context, approval_policy).
- ``design.json``: the canonical design token record.
- ``style-frames.json``: the MG-010 style-frame record. The canonical
  ``design`` definition is closed and chart-shaped; it cannot carry a
  per-frame focal point, crop, typography hierarchy, or reading order.
  Those live here, per scene and per frame, the same record-layer pattern
  as the MG-009 planner record and the MG-011 provenance sidecar. Each
  frame record carries its kind (``first``, ``key_proof``, ``final``),
  its job-relative path, the sha256 of its bytes, its pixel dimensions,
  a monotonic ``sequence`` number, its design record, and the named
  reference its frame.md critique compares against.
- ``approvals.json``: a list of canonical contracts-v2 ``approval``
  records. The design approval must bind this job and company, name
  every representative frame in ``artifact_refs`` with the exact current
  sha256, and carry ``subject_revision`` equal to the design revision
  recomputed from the current records.
- ``frame.md``: the human rationale; the gate checks it exists and names
  every frame kind, nothing more. Critique quality is a review matter.

Design revision (directive Section 16.7): a deterministic sha256 over
canonical UTF-8 JSON (sorted keys) of the parsed ``design.json`` plus
each frame's scene, kind, path, and design record. Frame bytes are bound
separately through the approval's ``artifact_refs`` hashes, and volatile
fields (frame hashes, dimensions, sequences, the approvals themselves)
are excluded, so writing an approval never changes the revision it
approves. A change to ``design.json`` or to any frame's design record
changes the revision and stales every earlier approval; a change to a
frame's bytes breaks the approval's hash binding the same way.

Approval authority (directive Section 16.7): do not invent a trust
boundary. Fixture jobs run under test-only authority: the single
accepted issuer is ``fixture-test-issuer``, and only when the manifest
``execution_context`` is ``fixture`` (the report then carries
``diagnostic: true``; fixture evidence never promotes a production job).
Production rejects the test issuer outright. A production approval that
claims ``verified`` authority from any other actor passes this gate's
record checks with ``authority_basis`` set to
``record_claimed_verified``; signature and event-source verification
belong to the trusted gate evaluator (MG-025 scope), and this gate says
so in its report rather than pretending to have done it.

Findings use the stable Section 16.9 categories. Exit codes: 0 pass;
2 MG_SCHEMA_INVALID (the record set is malformed or contradicts
itself, including a record sequence that puts animation before the
style frames); 3 MG_INPUT_MISSING (a required frame or record is
absent); 4 MG_APPROVAL_REQUIRED / MG_APPROVAL_STALE /
MG_APPROVAL_AUTHORITY_UNAVAILABLE; 9 MG_FOREIGN_JOB (an approval bound
to a different job or company; security stops immediately per 16.9).

CLI:
    python3 scripts/check_style_frames.py check <job_dir>

Prints one JSON report to stdout and exits with the report's exit_code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motion_contracts  # noqa: E402

SCHEMA_INVALID = motion_contracts.SCHEMA_INVALID
INPUT_MISSING = "MG_INPUT_MISSING"
APPROVAL_REQUIRED = "MG_APPROVAL_REQUIRED"
APPROVAL_STALE = "MG_APPROVAL_STALE"
APPROVAL_AUTHORITY_UNAVAILABLE = "MG_APPROVAL_AUTHORITY_UNAVAILABLE"
FOREIGN_JOB = "MG_FOREIGN_JOB"

# Section 16.9 blocking order: validation, dependency, authority,
# execution, QC, delivery. Security findings stop immediately and are
# reported ahead of every other class.
CATEGORY_ORDER = [
    SCHEMA_INVALID,
    INPUT_MISSING,
    APPROVAL_REQUIRED,
    APPROVAL_STALE,
    APPROVAL_AUTHORITY_UNAVAILABLE,
]
EXIT_BY_CATEGORY = {
    SCHEMA_INVALID: 2,
    INPUT_MISSING: 3,
    APPROVAL_REQUIRED: 4,
    APPROVAL_STALE: 4,
    APPROVAL_AUTHORITY_UNAVAILABLE: 4,
    FOREIGN_JOB: 9,
}

FRAME_KINDS = ("first", "key_proof", "final")
TEST_ISSUER = "fixture-test-issuer"

# Per-frame design fields the MG-010 record must carry. The canonical
# design record holds job-level tokens; these are the per-frame
# composition facts the directive requires style frames to record.
FRAME_DESIGN_FIELDS = (
    "typography_hierarchy",
    "focal_point",
    "crop",
    "layout",
    "colors",
    "reading_order",
)


def _finding(category: str, path: str, message: str) -> dict:
    return {"category": category, "path": path, "message": message}


def _load_json(path: Path):
    """Parse a JSON file strictly. Raises ValueError on any failure."""
    text = path.read_text(encoding="utf-8")
    return json.loads(text, parse_constant=motion_contracts._reject_constant)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    """Read (width, height) from a PNG IHDR with stdlib parsing only."""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _canonical_json(document) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_design_revision(job_dir) -> str | None:
    """Recompute the design revision from the current job records.

    Returns None when the inputs needed for the digest are absent or
    unparseable; the gate reports why separately.
    """
    job_dir = Path(job_dir)
    design_path = job_dir / "design.json"
    frames_path = job_dir / "style-frames.json"
    if not design_path.is_file() or not frames_path.is_file():
        return None
    try:
        design = _load_json(design_path)
        record = _load_json(frames_path)
    except (ValueError, OSError):
        return None
    if not isinstance(record, dict):
        return None
    frame_entries = []
    scenes = record.get("scenes")
    if isinstance(scenes, list):
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            frames = scene.get("frames")
            if not isinstance(frames, list):
                continue
            for frame in frames:
                if not isinstance(frame, dict):
                    continue
                frame_entries.append(
                    {
                        "scene_id": scene.get("scene_id"),
                        "kind": frame.get("kind"),
                        "path": frame.get("path"),
                        "design": frame.get("design"),
                    }
                )
    frame_entries.sort(key=lambda e: (str(e["scene_id"]), str(e["kind"]), str(e["path"])))
    payload = {"design": design, "frames": frame_entries}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _exit_for(findings: list[dict]) -> tuple[int, str | None]:
    if any(f["category"] == FOREIGN_JOB for f in findings):
        return 9, FOREIGN_JOB
    ordered = sorted(
        findings,
        key=lambda f: CATEGORY_ORDER.index(f["category"])
        if f["category"] in CATEGORY_ORDER
        else len(CATEGORY_ORDER),
    )
    if not ordered:
        return 0, None
    first = ordered[0]["category"]
    return EXIT_BY_CATEGORY.get(first, 2), first


def check_job(job_dir) -> dict:
    """Run the style-frame design gate over one job directory.

    Returns the full report dict; ``report["exit_code"]`` is the CLI
    exit code and ``report["verdict"]`` is "pass" only at exit 0.
    """
    job_dir = Path(job_dir)
    findings: list[dict] = []
    report: dict = {
        "job_dir": str(job_dir),
        "job_id": None,
        "gate": "design",
        "verdict": "blocked",
        "diagnostic": False,
        "design_revision": None,
        "authority_basis": None,
        "scenes": [],
        "findings": findings,
        "first_error_category": None,
        "exit_code": 2,
    }

    def finish() -> dict:
        code, first = _exit_for(findings)
        report["exit_code"] = code
        report["first_error_category"] = first
        report["verdict"] = "pass" if code == 0 else "blocked"
        return report

    # --- Job identity: the manifest binds everything else.
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.is_file():
        findings.append(_finding(INPUT_MISSING, "manifest.json", "job manifest is missing"))
        return finish()
    try:
        manifest = _load_json(manifest_path)
    except (ValueError, OSError) as exc:
        findings.append(_finding(SCHEMA_INVALID, "manifest.json", f"manifest.json is not parseable JSON: {exc}"))
        return finish()
    if not isinstance(manifest, dict):
        findings.append(_finding(SCHEMA_INVALID, "manifest.json", "manifest.json is not a JSON object"))
        return finish()
    job_id = manifest.get("job_id")
    company_id = manifest.get("company_id")
    context = manifest.get("execution_context")
    report["job_id"] = job_id
    report["diagnostic"] = context == "fixture"

    # --- Canonical design record: required input to the gate.
    design_path = job_dir / "design.json"
    if not design_path.is_file():
        findings.append(_finding(INPUT_MISSING, "design.json", "canonical design record is missing"))
    else:
        try:
            design_doc = _load_json(design_path)
            design_errors = motion_contracts.validate_document(design_doc, "design")
            for error in design_errors:
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        f"design.json#{error['path']}",
                        f"design.json fails design schema: {error['message']}",
                    )
                )
        except (ValueError, OSError) as exc:
            findings.append(_finding(SCHEMA_INVALID, "design.json", f"design.json is not parseable JSON: {exc}"))

    # --- Style-frame record.
    record_path = job_dir / "style-frames.json"
    record = None
    if not record_path.is_file():
        findings.append(
            _finding(
                INPUT_MISSING,
                "style-frames.json",
                "style-frame record is missing; no style frames have been produced for this job",
            )
        )
    else:
        try:
            record = _load_json(record_path)
        except (ValueError, OSError) as exc:
            findings.append(
                _finding(SCHEMA_INVALID, "style-frames.json", f"style-frames.json is not parseable JSON: {exc}")
            )
    if record is not None and not isinstance(record, dict):
        findings.append(_finding(SCHEMA_INVALID, "style-frames.json", "style-frames.json is not a JSON object"))
        record = None

    frames_by_path: dict[str, dict] = {}
    scene_reports: list[dict] = []
    sequences: dict[str, int] = {}
    if isinstance(record, dict):
        if record.get("job_id") != job_id:
            findings.append(
                _finding(
                    SCHEMA_INVALID,
                    "style-frames.json:job_id",
                    f"style-frame record is bound to job {record.get('job_id')!r}, "
                    f"but the manifest job is {job_id!r}",
                )
            )
        scenes = record.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            findings.append(
                _finding(
                    INPUT_MISSING,
                    "style-frames.json:scenes",
                    "style-frame record names no representative scenes",
                )
            )
            scenes = []
        for scene in scenes:
            if not isinstance(scene, dict):
                findings.append(_finding(SCHEMA_INVALID, "style-frames.json:scenes", "scene entry is not an object"))
                continue
            scene_id = scene.get("scene_id")
            scene_report = {"scene_id": scene_id, "frames": {}, "approval": "missing"}
            scene_reports.append(scene_report)
            frames = scene.get("frames")
            if not isinstance(frames, list):
                frames = []
            kinds_seen = []
            for frame in frames:
                if not isinstance(frame, dict):
                    findings.append(
                        _finding(SCHEMA_INVALID, "style-frames.json:frames", f"scene {scene_id!r} has a frame entry that is not an object")
                    )
                    continue
                kind = frame.get("kind")
                kinds_seen.append(kind)
                label = f"style-frames/{scene_id}/{kind}"
                frame_report = {"path": frame.get("path"), "recorded_sha256": frame.get("sha256"), "current_sha256": None, "sha256_ok": False}
                scene_report["frames"][str(kind)] = frame_report
                # Record structure: required design fields per frame.
                design_record = frame.get("design")
                if not isinstance(design_record, dict):
                    findings.append(
                        _finding(SCHEMA_INVALID, label, f"frame {kind!r} of scene {scene_id!r} has no design record")
                    )
                else:
                    for field in FRAME_DESIGN_FIELDS:
                        if field not in design_record:
                            findings.append(
                                _finding(
                                    SCHEMA_INVALID,
                                    label,
                                    f"frame {kind!r} of scene {scene_id!r} design record lacks {field!r}",
                                )
                            )
                sequence = frame.get("sequence")
                if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                    findings.append(
                        _finding(SCHEMA_INVALID, label, f"frame {kind!r} of scene {scene_id!r} has no usable sequence number")
                    )
                elif isinstance(frame.get("path"), str):
                    sequences[frame["path"]] = sequence
                # The frame artifact itself.
                rel = frame.get("path")
                if not isinstance(rel, str) or not rel:
                    findings.append(_finding(SCHEMA_INVALID, label, f"frame {kind!r} of scene {scene_id!r} names no path"))
                    continue
                frame_path = (job_dir / rel).resolve()
                if job_dir.resolve() not in frame_path.parents and frame_path != job_dir.resolve():
                    findings.append(_finding(SCHEMA_INVALID, label, f"frame path {rel} escapes the job directory"))
                    continue
                frames_by_path[rel] = frame
                if not frame_path.is_file():
                    findings.append(
                        _finding(INPUT_MISSING, rel, f"style frame {kind!r} of scene {scene_id!r} is recorded but the file is missing")
                    )
                    continue
                current = _sha256_file(frame_path)
                frame_report["current_sha256"] = current
                frame_report["sha256_ok"] = current == frame.get("sha256")
                if frame_path.suffix.lower() == ".png":
                    dims = _png_dimensions(frame_path)
                    if dims is not None and (dims[0] != frame.get("width") or dims[1] != frame.get("height")):
                        findings.append(
                            _finding(
                                SCHEMA_INVALID,
                                rel,
                                f"frame {rel} measures {dims[0]}x{dims[1]} but its record claims "
                                f"{frame.get('width')}x{frame.get('height')}",
                            )
                        )
            for kind in FRAME_KINDS:
                if kind not in kinds_seen:
                    findings.append(
                        _finding(
                            INPUT_MISSING,
                            f"style-frames/{scene_id}",
                            f"representative scene {scene_id!r} has no {kind!r} style frame",
                        )
                    )

        # --- Ordering: style frames precede animation artifacts.
        artifacts = record.get("animation_artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                art_scene = artifact.get("scene_id")
                art_path = artifact.get("path")
                art_seq = artifact.get("sequence")
                scene_frame_seqs = [
                    seq
                    for path_key, seq in sequences.items()
                    if any(
                        s.get("scene_id") == art_scene
                        and any(f.get("path") == path_key for f in s.get("frames", []) if isinstance(f, dict))
                        for s in scenes
                        if isinstance(s, dict)
                    )
                ]
                if isinstance(art_seq, int) and scene_frame_seqs and art_seq <= max(scene_frame_seqs):
                    findings.append(
                        _finding(
                            SCHEMA_INVALID,
                            str(art_path),
                            f"animation artifact for scene {art_scene!r} carries sequence {art_seq}, "
                            f"which does not come after the scene's style frames (latest sequence "
                            f"{max(scene_frame_seqs)}); the record does not show style frames before "
                            "animation authoring",
                        )
                    )
                if isinstance(art_path, str) and not (job_dir / art_path).is_file():
                    findings.append(
                        _finding(
                            INPUT_MISSING,
                            art_path,
                            f"animation artifact {art_path} is recorded but the file is missing",
                        )
                    )

    report["scenes"] = scene_reports
    revision = compute_design_revision(job_dir)
    report["design_revision"] = revision

    # --- frame.md rationale exists and covers every frame kind.
    frame_md_path = job_dir / "frame.md"
    if not frame_md_path.is_file():
        findings.append(_finding(INPUT_MISSING, "frame.md", "frame rationale document is missing"))
    elif isinstance(record, dict):
        try:
            frame_md_text = frame_md_path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(_finding(SCHEMA_INVALID, "frame.md", f"frame.md is unreadable: {exc}"))
            frame_md_text = ""
        for scene_report in scene_reports:
            for kind in FRAME_KINDS:
                if kind not in frame_md_text:
                    findings.append(
                        _finding(
                            SCHEMA_INVALID,
                            "frame.md",
                            f"frame.md carries no rationale naming the {kind!r} frame of scene "
                            f"{scene_report['scene_id']!r}",
                        )
                    )

    # --- Approvals.
    approvals_path = job_dir / "approvals.json"
    approvals: list[dict] = []
    if not approvals_path.is_file():
        findings.append(
            _finding(APPROVAL_REQUIRED, "approvals.json", "no approval records exist for this job; the design gate has nothing to verify")
        )
    else:
        try:
            approvals_doc = _load_json(approvals_path)
        except (ValueError, OSError) as exc:
            findings.append(_finding(SCHEMA_INVALID, "approvals.json", f"approvals.json is not parseable JSON: {exc}"))
            approvals_doc = None
        if isinstance(approvals_doc, dict):
            approvals = [approvals_doc]
        elif isinstance(approvals_doc, list):
            approvals = [a for a in approvals_doc if isinstance(a, dict)]
            if len(approvals) != len(approvals_doc):
                findings.append(_finding(SCHEMA_INVALID, "approvals.json", "approvals.json contains a non-object entry"))
        elif approvals_doc is not None:
            findings.append(_finding(SCHEMA_INVALID, "approvals.json", "approvals.json is neither an approval record nor a list of them"))
        for approval in approvals:
            for error in motion_contracts.validate_document(approval, "approval"):
                findings.append(
                    _finding(
                        SCHEMA_INVALID,
                        f"approvals.json#{error['path']}",
                        f"approval {approval.get('approval_id')!r} fails approval schema: {error['message']}",
                    )
                )
            if approval.get("job_id") != job_id or approval.get("company_id") != company_id:
                findings.append(
                    _finding(
                        FOREIGN_JOB,
                        "approvals.json",
                        f"approval {approval.get('approval_id')!r} is bound to job "
                        f"{approval.get('job_id')!r} / company {approval.get('company_id')!r}, "
                        f"not this job {job_id!r} / {company_id!r}; a foreign approval is never evidence here",
                    )
                )

    design_approvals = [
        a
        for a in approvals
        if a.get("scope") == "design" and a.get("job_id") == job_id and a.get("company_id") == company_id
    ]
    if approvals_path.is_file() and not design_approvals and not any(f["category"] == FOREIGN_JOB for f in findings):
        findings.append(
            _finding(APPROVAL_REQUIRED, "approvals.json", "no design-scope approval is recorded for this job")
        )

    current_approval = None
    if revision is not None:
        for approval in design_approvals:
            if approval.get("subject_revision") == revision:
                current_approval = approval
                break
    if design_approvals and revision is not None and current_approval is None:
        findings.append(
            _finding(
                APPROVAL_STALE,
                "approvals.json",
                "no design approval covers the current design revision; the design or a frame's "
                "design record changed after the recorded approval",
            )
        )
        for scene_report in scene_reports:
            scene_report["approval"] = "stale"
    elif current_approval is not None:
        decision = current_approval.get("decision")
        for scene_report in scene_reports:
            scene_report["approval"] = {
                "approved": "current",
                "pending": "pending",
                "rejected": "rejected",
            }.get(str(decision), "missing")
        if decision == "pending":
            findings.append(
                _finding(APPROVAL_REQUIRED, "approvals.json", f"design approval {current_approval.get('approval_id')!r} is still pending")
            )
        elif decision == "rejected":
            findings.append(
                _finding(
                    APPROVAL_REQUIRED,
                    "approvals.json",
                    f"design approval {current_approval.get('approval_id')!r} was rejected; no approval is in force",
                )
            )
        elif decision == "approved":
            # Hash binding: the approval must name every representative
            # frame with the exact current sha256.
            refs = {
                ref.get("path"): ref.get("sha256")
                for ref in current_approval.get("artifact_refs", [])
                if isinstance(ref, dict)
            }
            for rel, frame in frames_by_path.items():
                recorded = frame.get("sha256")
                bound = refs.get(rel)
                if bound is None:
                    findings.append(
                        _finding(
                            APPROVAL_STALE,
                            "approvals.json",
                            f"design approval does not name frame {rel}; it does not cover the current frame set",
                        )
                    )
                elif bound != recorded:
                    findings.append(
                        _finding(
                            APPROVAL_STALE,
                            "approvals.json",
                            f"design approval binds {rel} at sha256 {bound}, but the frame record carries {recorded}",
                        )
                    )
                frame_file = job_dir / rel
                if frame_file.is_file() and _sha256_file(frame_file) != recorded:
                    findings.append(
                        _finding(
                            APPROVAL_STALE,
                            rel,
                            f"frame {rel} changed after it was recorded and approved; its bytes no "
                            "longer match the approved hash",
                        )
                    )
            # Authority: test-only issuer discipline (Section 16.7).
            actor = current_approval.get("actor_id")
            if context == "fixture":
                if actor == TEST_ISSUER:
                    report["authority_basis"] = "fixture_test_issuer"
                else:
                    findings.append(
                        _finding(
                            APPROVAL_AUTHORITY_UNAVAILABLE,
                            "approvals.json",
                            f"fixture jobs run under test-only authority; actor {actor!r} is not "
                            f"the fixture test issuer {TEST_ISSUER!r}",
                        )
                    )
            elif context == "production":
                if actor == TEST_ISSUER:
                    findings.append(
                        _finding(
                            APPROVAL_AUTHORITY_UNAVAILABLE,
                            "approvals.json",
                            "production jobs reject the fixture test issuer; a real authorized "
                            "approval event is required",
                        )
                    )
                else:
                    # This gate verifies the record, its binding, and its
                    # revision. Signature/event verification against a
                    # trusted issuer is the trusted gate evaluator's job
                    # (MG-025); the report names that limit explicitly.
                    report["authority_basis"] = "record_claimed_verified"
            else:
                findings.append(
                    _finding(
                        APPROVAL_AUTHORITY_UNAVAILABLE,
                        "manifest.json:execution_context",
                        f"execution_context {context!r} has no authority rule in this gate",
                    )
                )

    return finish()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Skill 72 style-frame design gate (MG-010).")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check", help="Check one job directory against the style-frame gate.")
    check_parser.add_argument("job_dir", help="Path to the job directory.")
    args = parser.parse_args(argv)

    if args.command == "check":
        job_dir = Path(args.job_dir)
        if not job_dir.is_dir():
            report = {
                "job_dir": args.job_dir,
                "job_id": None,
                "gate": "design",
                "verdict": "blocked",
                "diagnostic": False,
                "design_revision": None,
                "authority_basis": None,
                "scenes": [],
                "findings": [
                    _finding(INPUT_MISSING, args.job_dir, f"job directory {args.job_dir} does not exist")
                ],
                "first_error_category": INPUT_MISSING,
                "exit_code": 3,
            }
            print(json.dumps(report, indent=2))
            return 3
        report = check_job(job_dir)
        print(json.dumps(report, indent=2))
        return int(report["exit_code"])
    return 2


if __name__ == "__main__":
    sys.exit(main())
