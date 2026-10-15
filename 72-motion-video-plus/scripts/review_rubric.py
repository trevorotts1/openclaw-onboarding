#!/usr/bin/env python3
"""Creative review rubric tooling for Skill 72 (MG-033).

Validates creative review records against
references/review-rubric-schema.json and the structural rules of
references/critique-protocol.md, and renders the quality dashboard
(receipt) for a job's append-only review history.

Why this layer is Python: review records on this base are produced
and consumed by the Python layer. The MG-031 critique bundle builder
(scripts/critique_bundle.py) writes the coverage record a review must
bind, the design and approval gates (scripts/check_style_frames.py,
scripts/check_approvals.py) validate records with jsonschema the same
way, and the evidence those reviews cite (MG-005, MG-006, MG-023,
MG-031, MG-032 records) is JSON consumed as files. The TypeScript
runtime writes motion-proof records; this tool consumes them as
evidence without the reviewer needing the render runtime installed.

Structural rules enforced here (the schema alone cannot express
them); every refusal is named and carries a Section 16.9 class exit:

- REVIEW_SELF_APPROVAL (4, authority): author and reviewer are the
  same identity. No author self-approval, ever.
- REVIEW_TEN_UNCALIBRATED (4): a score of 10 while the reference
  calibration state is not OWNER_APPROVED. A claimed 10 is reserved
  for owner-calibrated excellence.
- REVIEW_CALIBRATION_UNPROVEN (4): calibration_state claims
  OWNER_APPROVED with no approval_record citation.
- REVIEW_VISION_INCAPABLE (4): a reviewer recorded as not
  vision-capable signs a scored visual dimension. Such a reviewer may
  author and may sign data_proof_integrity from records alone.
- REVIEW_PROVISIONAL_MISMATCH (2): the provisional flag disagrees
  with the calibration state.
- REVIEW_COVERAGE_INCOMPLETE (6): the bound MG-031 coverage record's
  verdict is not complete. Incomplete bundles are never scored.
- REVIEW_FOREIGN_JOB (9) and REVIEW_HASH_MISMATCH (9): the coverage
  record or a cited proof record binds a different job, or the
  coverage record's video hash contradicts the record under review.
  Security bindings stop evaluation immediately, per Section 16.9.
- REVIEW_INPUT_MISSING (3) and REVIEW_EVIDENCE_MISSING (3): a cited
  evidence or coverage file does not exist, or a scored dimension
  cites no evidence. No evidence, no score.
- REVIEW_AUDIO_EVIDENCE_MISSING (3): a scored dimension declares an
  audio judgment but cites no audio_record evidence carrying measured
  audio data. Sound is judged from measurements, not claims.
- REVIEW_SCORE_INFLATED_UNRESOLVED (6): a defect still unresolved
  from an earlier round sits in a dimension scored higher than the
  earliest scored round that carried it. The trend is checked
  against the append-only history.
- REVIEW_DEFECT_DROPPED (6): a defect unresolved in the previous
  round is absent from this record instead of carried or resolved.
- REVIEW_HISTORY_MISSING (3): a record for round 2 or later is
  validated with no earlier history to check the trend against.
- REVIEW_ROUND_LIMIT (6): a non-escalation record beyond round five.
  Correction is capped at five rounds; after that the record
  escalates with evidence instead of inflating scores.
- REVIEW_VERDICT_INCONSISTENT (6): verdict ship while the release
  gate does not pass (every applicable dimension scored at 9 or
  higher, no unresolved critical defect).
- REVIEW_REMEDIATION_ORDER (6): the remediation list is not ordered
  worst cause first.

Exit codes follow Section 16.9 classes: 2 validation, 3 dependency
or input, 4 authority, 6 QC. When several findings exist, the
reported exit is the earliest blocking class in that order; a
security binding (9) stops evaluation immediately.

Commands:
  validate RECORD.json [--history-dir DIR]
      Print one JSON report; exit 0 only when the record is valid.
  dashboard RECORD.json [RECORD.json ...] [--history-dir DIR]
      Render the Markdown receipt for the rounds given (history-dir
      records are merged in), to stdout or --out PATH.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "references" / "review-rubric-schema.json"

DIMENSIONS = [
    "visual_storytelling",
    "asset_relevance",
    "typography_readability",
    "composition",
    "motion_clarity",
    "data_proof_integrity",
    "destination_fit",
    "finishing",
]

# Dimensions whose sign-off requires actually seeing the artifact.
# data_proof_integrity is the exception: it is judged from proof
# records, coverage records, and measured values, which a
# vision-incapable reviewer can verify from the records themselves.
VISION_DIMENSIONS = [d for d in DIMENSIONS if d != "data_proof_integrity"]

SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2}
MAX_ROUNDS = 5
RELEASE_TARGET = 9

EXIT_OK = 0
EXIT_SCHEMA = 2
EXIT_INPUT = 3
EXIT_AUTHORITY = 4
EXIT_QC = 6
EXIT_SECURITY = 9


def finding(category: str, exit_code: int, message: str) -> dict:
    return {"category": category, "exit_code": exit_code,
            "message": message}


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}"


def resolve_ref(record_dir: Path, ref: str) -> Path:
    p = Path(ref)
    return p if p.is_absolute() else (record_dir / p)


def audio_record_measured(data) -> bool:
    """True when a parsed JSON document carries measured audio data
    (an integrated loudness value), as MG-031 metrics records and
    MG-023 audio verification records do."""
    if not isinstance(data, dict):
        return False
    loud = data.get("loudness")
    if isinstance(loud, dict) and isinstance(
            loud.get("integrated_lufs"), (int, float)):
        return True
    if isinstance(data.get("integrated_lufs"), (int, float)):
        return True
    return False


def dimension_map(record: dict) -> dict:
    return {d["dimension"]: d for d in record.get("dimensions", [])}


def compute_gate(record: dict, coverage_ok: bool) -> dict:
    """The release gate for one record: every applicable dimension
    scored at RELEASE_TARGET or higher, no unresolved critical
    defects, complete coverage, within the round cap. This is a
    technical computation over the record; it is not, and is never
    presented as, the owner's artistic approval."""
    failures = []
    dims = dimension_map(record)
    for name in DIMENSIONS:
        entry = dims.get(name)
        if entry is None:
            failures.append(f"dimension {name} missing")
            continue
        if entry["status"] == "not_applicable":
            continue
        if entry["status"] == "unscored":
            failures.append(f"dimension {name} is unscored")
        elif entry["score"] < RELEASE_TARGET:
            failures.append(
                f"dimension {name} scores {entry['score']}, below "
                f"the release target {RELEASE_TARGET}")
    for entry in record.get("dimensions", []):
        for defect in entry.get("defects", []):
            if defect["severity"] == "critical" and not defect["resolved"]:
                failures.append(
                    f"critical defect {defect['defect_id']} unresolved "
                    f"in {entry['dimension']}")
    if not coverage_ok:
        failures.append("coverage verdict is not complete")
    if record.get("round", 0) > MAX_ROUNDS:
        failures.append(f"round {record['round']} exceeds the "
                        f"{MAX_ROUNDS}-round correction cap")
    return {"passes": not failures, "failures": failures,
            "release_target": RELEASE_TARGET}


def load_history(history_dir: Path | None, record_path: Path,
                 job_id: str) -> tuple[list[dict], list[str]]:
    """Load prior review records for the same job from a history
    directory (append-only review history). Returns (records sorted
    by round, problems). The record under validation itself is
    excluded when it lives in the same directory."""
    records: list[dict] = []
    problems: list[str] = []
    if history_dir is None:
        return records, problems
    if not history_dir.is_dir():
        return records, [f"history directory {history_dir} not found"]
    for candidate in sorted(history_dir.glob("*.json")):
        if candidate.resolve() == record_path.resolve():
            continue
        data, err = load_json(candidate)
        if err:
            problems.append(err)
            continue
        if isinstance(data, dict) and \
                data.get("kind") == "creative_review_record" and \
                data.get("job_id") == job_id:
            records.append(data)
    records.sort(key=lambda r: r.get("round", 0))
    return records, problems


def validate_record(record_path: Path,
                    history_dir: Path | None) -> dict:
    record_path = Path(record_path)
    record_dir = record_path.parent
    findings: list[dict] = []
    record, err = load_json(record_path)
    if err:
        findings.append(finding("REVIEW_INPUT_MISSING", EXIT_INPUT, err))
        return _report(record_path, None, findings, None, [])

    schema, serr = load_json(SCHEMA_PATH)
    if serr:
        findings.append(finding("REVIEW_INPUT_MISSING", EXIT_INPUT, serr))
        return _report(record_path, record, findings, None, [])
    validator = Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(record),
                           key=lambda e: list(e.absolute_path))
    for e in schema_errors:
        where = "/".join(str(p) for p in e.absolute_path) or "<root>"
        findings.append(finding(
            "REVIEW_SCHEMA_INVALID", EXIT_SCHEMA,
            f"schema violation at {where}: {e.message}"))

    dims = dimension_map(record) if isinstance(record, dict) else {}
    if isinstance(record, dict) and record.get("dimensions"):
        names = [d.get("dimension") for d in record["dimensions"]]
        if sorted(names) != sorted(DIMENSIONS):
            findings.append(finding(
                "REVIEW_SCHEMA_INVALID", EXIT_SCHEMA,
                "dimensions must cover each of the eight rubric "
                f"dimensions exactly once; got {names}"))
    if findings:
        # Structural shape is broken; deeper checks would guess.
        return _report(record_path, record, findings, None, [])

    job_id = record["job_id"]
    rnd = record["round"]

    # Authority: separation of author and reviewer.
    if record["author"]["id"] == record["reviewer"]["id"]:
        findings.append(finding(
            "REVIEW_SELF_APPROVAL", EXIT_AUTHORITY,
            f"author and reviewer are the same identity "
            f"({record['author']['id']}); a review record requires "
            "an independent reviewer"))

    # Calibration doctrine.
    state = record["reference"]["calibration_state"]
    if state == "OWNER_APPROVED" and \
            not record["reference"].get("approval_record"):
        findings.append(finding(
            "REVIEW_CALIBRATION_UNPROVEN", EXIT_AUTHORITY,
            "calibration_state claims OWNER_APPROVED but cites no "
            "approval_record; owner calibration is the owner's own "
            "recorded decision and is never asserted without it"))
    if record["provisional"] != (state != "OWNER_APPROVED"):
        findings.append(finding(
            "REVIEW_PROVISIONAL_MISMATCH", EXIT_SCHEMA,
            f"provisional is {record['provisional']} but the "
            f"reference calibration state is {state}; scores against "
            "a reference that is not OWNER_APPROVED are provisional "
            "and must be labeled as such"))
    if state != "OWNER_APPROVED":
        for name, entry in dims.items():
            if entry["status"] == "scored" and entry["score"] == 10:
                findings.append(finding(
                    "REVIEW_TEN_UNCALIBRATED", EXIT_AUTHORITY,
                    f"dimension {name} claims a score of 10 against "
                    f"reference {record['reference']['reference_id']} "
                    f"whose calibration state is {state}; a 10 is "
                    "reserved for owner-calibrated excellence and "
                    "cannot be awarded by a crew reviewer until the "
                    "owner calibrates the reference"))

    # Vision capability.
    if not record["reviewer"]["vision_capable"]:
        signed = [n for n in VISION_DIMENSIONS
                  if dims[n]["status"] == "scored"]
        if signed:
            findings.append(finding(
                "REVIEW_VISION_INCAPABLE", EXIT_AUTHORITY,
                f"reviewer {record['reviewer']['id']} is recorded "
                f"as not vision-capable but signs visual dimensions: "
                f"{', '.join(signed)}; a vision-incapable reviewer "
                "may author and may sign data_proof_integrity from "
                "records, never the visual dimensions"))

    # Coverage binding (MG-031). Security bindings stop evaluation.
    coverage_path = resolve_ref(
        record_dir, record["artifact"]["coverage_record"])
    coverage = None
    if not coverage_path.is_file():
        findings.append(finding(
            "REVIEW_INPUT_MISSING", EXIT_INPUT,
            f"coverage record not found: {coverage_path}"))
    else:
        coverage, cerr = load_json(coverage_path)
        if cerr:
            findings.append(finding(
                "REVIEW_INPUT_MISSING", EXIT_INPUT, cerr))
            coverage = None
    coverage_ok = False
    if coverage is not None:
        if coverage.get("job_id") != job_id:
            findings.append(finding(
                "REVIEW_FOREIGN_JOB", EXIT_SECURITY,
                f"coverage record binds job "
                f"{coverage.get('job_id')}, this review is for job "
                f"{job_id}"))
            return _report(record_path, record, findings, None, [])
        video = record["artifact"].get("video") or {}
        cov_sha = (coverage.get("video") or {}).get("sha256")
        if video.get("sha256") and cov_sha and \
                video["sha256"] != cov_sha:
            findings.append(finding(
                "REVIEW_HASH_MISMATCH", EXIT_SECURITY,
                "the coverage record's video sha256 contradicts "
                "the artifact hash named in this review record"))
            return _report(record_path, record, findings, None, [])
        if coverage.get("verdict") != "complete":
            findings.append(finding(
                "REVIEW_COVERAGE_INCOMPLETE", EXIT_QC,
                f"coverage verdict for job {job_id} is "
                f"{coverage.get('verdict')}; a bundle whose coverage "
                "is not complete is never scored"))
        else:
            coverage_ok = True

    # Evidence: existence, audio measurement, proof-record binding.
    for name in DIMENSIONS:
        entry = dims[name]
        if entry["status"] != "scored":
            continue
        evidence = entry.get("evidence") or []
        if not evidence:
            findings.append(finding(
                "REVIEW_EVIDENCE_MISSING", EXIT_INPUT,
                f"dimension {name} is scored but cites no evidence; "
                "no evidence, no score"))
            continue
        has_audio = False
        for item in evidence:
            path = resolve_ref(record_dir, item["ref"])
            if not path.is_file():
                findings.append(finding(
                    "REVIEW_INPUT_MISSING", EXIT_INPUT,
                    f"dimension {name} cites evidence that does "
                    f"not exist: {item['ref']}"))
                continue
            if item["type"] == "audio_record":
                data, aerr = load_json(path)
                if aerr is None and audio_record_measured(data):
                    has_audio = True
            if item["type"] == "proof_record":
                data, perr = load_json(path)
                if perr is None and isinstance(data, dict) and \
                        data.get("job_id") not in (None, job_id):
                    findings.append(finding(
                        "REVIEW_FOREIGN_JOB", EXIT_SECURITY,
                        f"dimension {name} cites a proof record "
                        f"for job {data.get('job_id')}, this review "
                        f"is for job {job_id}"))
                    return _report(record_path, record, findings,
                                   None, [])
        if entry.get("audio_judgment") and not has_audio:
            findings.append(finding(
                "REVIEW_AUDIO_EVIDENCE_MISSING", EXIT_INPUT,
                f"dimension {name} signs a sound judgment but cites "
                "no audio_record evidence carrying measured audio "
                "data; sound judgments require attached measured "
                "audio evidence (MG-023 or MG-031 records), not a "
                "claim that audio exists"))

    # Round cap and escalation shape.
    if rnd > MAX_ROUNDS and record["verdict"] != "escalate":
        findings.append(finding(
            "REVIEW_ROUND_LIMIT", EXIT_QC,
            f"round {rnd} exceeds the {MAX_ROUNDS}-round correction "
            "cap; after five rounds the record escalates with "
            "evidence instead of continuing to score"))
    if record["verdict"] == "escalate" and \
            not record.get("escalation_basis"):
        findings.append(finding(
            "REVIEW_SCHEMA_INVALID", EXIT_SCHEMA,
            "verdict escalate requires an escalation_basis: the "
            "evidence summary handed upward"))

    # History: trend cap and append-only defect carriage.
    history, problems = load_history(history_dir, record_path, job_id)
    for problem in problems:
        findings.append(finding(
            "REVIEW_INPUT_MISSING", EXIT_INPUT, problem))
    if rnd > 1 and not history:
        findings.append(finding(
            "REVIEW_HISTORY_MISSING", EXIT_INPUT,
            f"round {rnd} record validated with no earlier review "
            "history; the trend rules require the append-only "
            "history of rounds 1 to " + str(rnd - 1)))
    by_round = {r["round"]: r for r in history}
    for name in DIMENSIONS:
        entry = dims[name]
        for defect in entry.get("defects", []):
            if defect["first_seen_round"] > rnd:
                findings.append(finding(
                    "REVIEW_SCHEMA_INVALID", EXIT_SCHEMA,
                    f"defect {defect['defect_id']} claims "
                    f"first_seen_round {defect['first_seen_round']} "
                    f"in a round {rnd} record"))
            if defect["resolved"] or defect["first_seen_round"] >= rnd:
                continue
            if entry["status"] != "scored":
                continue
            # The cap baseline is the earliest scored round that
            # carried the defect: the first history record where the
            # defect was present in this dimension and the dimension
            # was scored. Rounds that carried the defect but left
            # the dimension unscored set no baseline; if no scored
            # round has carried it yet, no cap applies and nothing
            # is fabricated for the unscored rounds.
            base_round = None
            base_entry = None
            for prior in history:
                if prior.get("round", 0) >= rnd:
                    continue
                candidate = dimension_map(prior).get(name)
                if candidate is None or \
                        candidate["status"] != "scored":
                    continue
                if any(d["defect_id"] == defect["defect_id"]
                       for d in candidate.get("defects", [])):
                    base_round = prior["round"]
                    base_entry = candidate
                    break
            if base_entry is not None and \
                    entry["score"] > base_entry["score"]:
                findings.append(finding(
                    "REVIEW_SCORE_INFLATED_UNRESOLVED", EXIT_QC,
                    f"defect {defect['defect_id']} in dimension "
                    f"{name} is still unresolved; the earliest "
                    f"scored round that carried it is round "
                    f"{base_round}, where the dimension scored "
                    f"{base_entry['score']}; this record scores it "
                    f"{entry['score']}. A repeated unresolved defect "
                    "cannot receive a higher score than the earliest "
                    "scored round that carried it"))
    previous = by_round.get(rnd - 1)
    if previous is not None:
        current_ids = {d["defect_id"] for e in record["dimensions"]
                       for d in e.get("defects", [])}
        for pentry in previous["dimensions"]:
            for pdefect in pentry.get("defects", []):
                if not pdefect["resolved"] and \
                        pdefect["defect_id"] not in current_ids:
                    findings.append(finding(
                        "REVIEW_DEFECT_DROPPED", EXIT_QC,
                        f"defect {pdefect['defect_id']} was "
                        f"unresolved in round {rnd - 1} and is "
                        "absent from this record; history is "
                        "append-only, so a defect is carried until "
                        "it is recorded resolved with evidence"))

    # Remediation order: worst cause first (severity rank, then
    # earliest first-seen round, then defect id as a stable final
    # key), exactly as the protocol, the schema description, and
    # the reviewer prompts state it.
    remediation = record.get("remediation") or []
    if remediation:
        order_keys = {}
        for entry in record["dimensions"]:
            for defect in entry.get("defects", []):
                order_keys[defect["defect_id"]] = (
                    SEVERITY_RANK[defect["severity"]],
                    defect["first_seen_round"],
                    defect["defect_id"])
        unknown = [d for d in remediation if d not in order_keys]
        if unknown:
            findings.append(finding(
                "REVIEW_SCHEMA_INVALID", EXIT_SCHEMA,
                f"remediation names defects not in this record: "
                f"{unknown}"))
        else:
            keys = [order_keys[d] for d in remediation]
            if keys != sorted(keys):
                findings.append(finding(
                    "REVIEW_REMEDIATION_ORDER", EXIT_QC,
                    "remediation is not ordered worst cause first "
                    "(critical before major before minor, earliest "
                    "first-seen first within a severity)"))

    # Gate and verdict consistency.
    gate = compute_gate(record, coverage_ok)
    if record["verdict"] == "ship" and not gate["passes"]:
        findings.append(finding(
            "REVIEW_VERDICT_INCONSISTENT", EXIT_QC,
            "verdict ship but the release gate does not pass: " +
            "; ".join(gate["failures"])))

    return _report(record_path, record, findings, gate,
                   [r["round"] for r in history])


def _report(record_path: Path, record, findings: list[dict],
            gate, history_rounds: list[int]) -> dict:
    if any(f["exit_code"] == EXIT_SECURITY for f in findings):
        exit_code = EXIT_SECURITY
    elif findings:
        exit_code = min(f["exit_code"] for f in findings)
    else:
        exit_code = EXIT_OK
    return {
        "command": "review_rubric validate",
        "record": str(record_path),
        "job_id": record.get("job_id") if isinstance(record, dict)
        else None,
        "round": record.get("round") if isinstance(record, dict)
        else None,
        "status": "SUCCEEDED" if not findings else "FAILED",
        "exit_code": exit_code,
        "category": findings[0]["category"] if findings else None,
        "findings": findings,
        "gate": gate,
        "history_rounds": history_rounds,
    }


def render_dashboard(records: list[dict]) -> str:
    """Render the quality dashboard (receipt) for a job's rounds."""
    records = sorted(records, key=lambda r: r["round"])
    latest = records[-1]
    ref = latest["reference"]
    lines: list[str] = []
    lines.append(f"# Quality dashboard: {latest['job_id']}")
    lines.append("")
    lines.append(f"- Artifact mode: "
                 f"{latest['artifact'].get('mode') or 'not recorded'}")
    video = latest["artifact"].get("video") or {}
    if video:
        lines.append(f"- Artifact: {video.get('path')} "
                     f"(sha256 {video.get('sha256', '')[:16]}...)")
    lines.append(f"- Reference: {ref['reference_id']}")
    lines.append(f"- Reference calibration state: "
                 f"**{ref['calibration_state']}**")
    if ref["calibration_state"] == "OWNER_APPROVED":
        lines.append(f"- Owner approval record: "
                     f"{ref.get('approval_record')}")
    else:
        lines.append("- **PROVISIONAL SCORES.** This reference is "
                     "not owner-calibrated, so every score below is "
                     "provisional. A score of 10 cannot be awarded "
                     "against this reference. A passing gate is a "
                     "technical result, never the owner's artistic "
                     "approval.")
    lines.append(f"- Rounds recorded: {len(records)} of "
                 f"{MAX_ROUNDS} correction rounds")
    lines.append(f"- Latest verdict: {latest['verdict']}")
    lines.append("")
    lines.append("## Score history")
    lines.append("")
    header = "| Round | " + " | ".join(DIMENSIONS) + " | Verdict |"
    lines.append(header)
    lines.append("|" + "---|" * (len(DIMENSIONS) + 2))
    for rec in records:
        dims = dimension_map(rec)
        cells = []
        for name in DIMENSIONS:
            entry = dims[name]
            if entry["status"] == "scored":
                cells.append(str(entry["score"]))
            elif entry["status"] == "unscored":
                cells.append("unscored")
            else:
                cells.append("n/a")
        lines.append(f"| {rec['round']} | " + " | ".join(cells) +
                     f" | {rec['verdict']} |")
    lines.append("")
    lines.append("## Latest round detail")
    lines.append("")
    for name in DIMENSIONS:
        entry = dimension_map(latest)[name]
        lines.append(f"### {name}")
        if entry["status"] == "scored":
            lines.append(f"- Score: {entry['score']} of 10")
            lines.append(f"- Compared with the reference: "
                         f"{entry['reference_comparison']}")
            for item in entry.get("evidence", []):
                lines.append(f"- Evidence ({item['type']}): "
                             f"[{item['ref']}]({item['ref']}): "
                             f"{item['detail']}")
        elif entry["status"] == "unscored":
            lines.append(f"- UNSCORED: {entry['unscored_reason']}")
        else:
            lines.append(f"- NOT APPLICABLE: "
                         f"{entry['unscored_reason']}")
        lines.append("")
    lines.append("## Defect ledger (worst first)")
    lines.append("")
    ledger: dict[str, dict] = {}
    for rec in records:
        for entry in rec["dimensions"]:
            for defect in entry.get("defects", []):
                slot = ledger.setdefault(defect["defect_id"], {
                    "defect": defect, "dimension": entry["dimension"],
                    "rounds": []})
                slot["defect"] = defect
                slot["rounds"].append(rec["round"])
    if not ledger:
        lines.append("No defects recorded.")
    else:
        ordered = sorted(
            ledger.values(),
            key=lambda s: (SEVERITY_RANK[s["defect"]["severity"]],
                           s["defect"]["first_seen_round"]))
        lines.append("| Defect | Severity | Dimension | First seen "
                     "| Status | Cause |")
        lines.append("|---|---|---|---|---|---|")
        for slot in ordered:
            d = slot["defect"]
            status = "resolved" if d["resolved"] else "OPEN"
            lines.append(f"| {d['defect_id']} | {d['severity']} | "
                         f"{slot['dimension']} | round "
                         f"{d['first_seen_round']} | {status} | "
                         f"{d['cause']} |")
    lines.append("")
    remediation = latest.get("remediation") or []
    if remediation:
        lines.append("## Remediation order (worst cause first)")
        lines.append("")
        for i, defect_id in enumerate(remediation, 1):
            lines.append(f"{i}. {defect_id}")
        lines.append("")
    if latest["verdict"] == "escalate":
        lines.append("## Escalation")
        lines.append("")
        lines.append(latest.get("escalation_basis") or "")
        lines.append("")
    lines.append("Review history is append-only. Scores against a "
                 "reference that is not OWNER_APPROVED are "
                 "provisional and are never presented as the "
                 "owner's artistic approval.")
    lines.append("")
    return "\n".join(lines)


def cmd_validate(args) -> int:
    report = validate_record(Path(args.record),
                             Path(args.history_dir)
                             if args.history_dir else None)
    print(json.dumps(report, indent=2, sort_keys=True))
    return report["exit_code"]


def cmd_dashboard(args) -> int:
    records: list[dict] = []
    seen: set[tuple[str, int]] = set()
    paths = [Path(p) for p in args.records]
    if args.history_dir:
        paths += sorted(Path(args.history_dir).glob("*.json"))
    for path in paths:
        data, err = load_json(path)
        if err:
            print(json.dumps({"command": "review_rubric dashboard",
                              "status": "FAILED",
                              "category": "REVIEW_INPUT_MISSING",
                              "exit_code": EXIT_INPUT,
                              "findings": [err]}, indent=2))
            return EXIT_INPUT
        if isinstance(data, dict) and \
                data.get("kind") == "creative_review_record":
            key = (data["job_id"], data["round"])
            if key not in seen:
                seen.add(key)
                records.append(data)
    if not records:
        print(json.dumps({"command": "review_rubric dashboard",
                          "status": "FAILED",
                          "category": "REVIEW_INPUT_MISSING",
                          "exit_code": EXIT_INPUT,
                          "findings": ["no creative review records "
                                       "found in the given paths"]},
                         indent=2))
        return EXIT_INPUT
    jobs = {r["job_id"] for r in records}
    if len(jobs) > 1:
        print(json.dumps({"command": "review_rubric dashboard",
                          "status": "FAILED",
                          "category": "REVIEW_FOREIGN_JOB",
                          "exit_code": EXIT_SECURITY,
                          "findings": [f"records span several jobs: "
                                       f"{sorted(jobs)}"]}, indent=2))
        return EXIT_SECURITY
    text = render_dashboard(records)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(json.dumps({"command": "review_rubric dashboard",
                          "status": "SUCCEEDED", "exit_code": 0,
                          "job_id": records[0]["job_id"],
                          "rounds": len(records),
                          "out": args.out}, indent=2, sort_keys=True))
    else:
        print(text)
    return EXIT_OK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Creative review rubric tooling (MG-033).")
    sub = parser.add_subparsers(dest="command", required=True)
    pv = sub.add_parser("validate")
    pv.add_argument("record")
    pv.add_argument("--history-dir")
    pv.set_defaults(func=cmd_validate)
    pd = sub.add_parser("dashboard")
    pd.add_argument("records", nargs="*")
    pd.add_argument("--history-dir")
    pd.add_argument("--out")
    pd.set_defaults(func=cmd_dashboard)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
