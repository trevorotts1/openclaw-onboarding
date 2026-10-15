"""MG-044 reference suite tool: run the actual shipped gates on the
staged negative exemplars and write their failing records.

Gates run, one per negative:
- small_type: the MG-013 rendered-layout audit
  (runtime/src/typography/audit.ts, via the compiled runtime) on the
  staged layout record negatives/small-type/layout-record.json.
- incorrect_crop: the MG-038 recomposition measurement
  (scripts/vsl_mobile.py measure_recomposition) on the staged
  center-cropped vertical artifact negatives/incorrect-crop/
  vertical-crop.mp4, using the shipped vsl_mobile example design and
  dataset.
- decorative_substitution: the MG-009 storyboard planner validator
  (scripts/validate_storyboard.py) on the staged storyboard
  negatives/decorative-substitution/storyboard.json, in which the
  mechanism beat is replaced by a bullet-list text card and the
  remaining explanatory beats are text cards with decorative motion
  verbs.

The static-chart negative is gated by the shipped MG-032 suite
(runtime/tests/run-motion-proof.ts, acceptance case 1); its record
is copied from that suite's output, not produced here.

Usage (from 72-motion-video-plus/):
  python3 assets/examples/reference-suite/tools/run-negative-gates.py

Every record is written next to its exemplar as gate-record.json
with the gate's exit status and findings verbatim. This tool exits 0
when every gate ran and produced the expected failure; a gate that
passes its negative, or fails to run, exits 1.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = SUITE_DIR.parents[2]
RUNTIME_DIR = SKILL_DIR / "runtime"
NEGATIVES = SUITE_DIR / "negatives"


def write_record(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def gate_small_type() -> bool:
    # A small node driver, generated beside the record, imports the
    # compiled auditLayout and the shipped typography tokens and runs
    # the audit on the staged layout record.
    record_path = NEGATIVES / "small-type" / "layout-record.json"
    inline = NEGATIVES / "small-type" / "audit-driver.mjs"
    inline.write_text(
        'import { readFileSync, writeFileSync } from "node:fs";\n'
        'import { auditLayout } from "'
        + str(RUNTIME_DIR / "dist" / "src" / "typography" / "audit.js")
        + '";\n'
        'import { loadTypographyTokens } from "'
        + str(RUNTIME_DIR / "dist" / "src" / "typography" / "tokens.js")
        + '";\n'
        "const record = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"
        "const tokens = loadTypographyTokens();\n"
        "const result = auditLayout(record, tokens);\n"
        "writeFileSync(process.argv[3], JSON.stringify(result, null, 2) + '\\n');\n"
        "console.log(JSON.stringify({ pass: result.pass, findings: result.findings.length }));\n",
        encoding="utf-8",
    )
    out_path = NEGATIVES / "small-type" / "audit-output.json"
    proc = subprocess.run(
        ["node", str(inline), str(record_path), str(out_path)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"small_type gate failed to run: {proc.stderr[-500:]}")
        return False
    audit = json.loads(out_path.read_text(encoding="utf-8"))
    failing = [f for f in audit["findings"] if f["severity"] == "error"]
    record = {
        "negative": "small_type",
        "gate": "MG-013 rendered-layout audit (runtime/src/typography/audit.ts)",
        "command": "node audit-driver.mjs layout-record.json audit-output.json "
                   "(driver imports the compiled auditLayout and the shipped "
                   "typography tokens)",
        "artifact": "frame.png",
        "layout_record": "layout-record.json",
        "audit_output": "audit-output.json",
        "gate_pass": audit["pass"],
        "expected": "fail",
        "failing_findings": failing,
        "reason_it_fails": (
            "Essential chart labels and disclosure are authored far below "
            "their role floors and shrink further at the destination "
            "placement; the audit reports each below-floor element by name "
            "instead of letting the small type ship."),
    }
    write_record(NEGATIVES / "small-type" / "gate-record.json", record)
    return audit["pass"] is False and len(failing) > 0


def gate_incorrect_crop() -> bool:
    spec = importlib.util.spec_from_file_location(
        "vsl_mobile", SKILL_DIR / "scripts" / "vsl_mobile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    design = json.loads(
        (SKILL_DIR / "assets" / "examples" / "vsl_mobile" / "design.json")
        .read_text(encoding="utf-8"))
    dataset = json.loads(
        (SKILL_DIR / "assets" / "examples" / "vsl_mobile" / "data" / "bars.json")
        .read_text(encoding="utf-8"))
    handoff = json.loads(
        (SKILL_DIR / "tests" / "fixtures" / "vsl" / "handoff-mobile.json")
        .read_text(encoding="utf-8"))
    motion = handoff["insert"].get("motion") or {
        "start_frame": 15, "end_frame_exclusive": 75,
        "hold_to_frame_exclusive": handoff["insert"]["duration_frames"]}
    artifact = NEGATIVES / "incorrect-crop" / "vertical-crop.mp4"
    record = {
        "negative": "incorrect_crop",
        "gate": "MG-038 recomposition measurement "
                "(scripts/vsl_mobile.py measure_recomposition)",
        "command": "python3 assets/examples/reference-suite/tools/"
                   "run-negative-gates.py (incorrect_crop section)",
        "artifact": "vertical-crop.mp4",
        "expected": "fail",
        "reason_it_fails": (
            "The vertical artifact is a center crop of the landscape "
            "master scaled to 1080x1920, not a recomposition: the bar "
            "origins fall outside the crop window and the decoded "
            "geometry cannot match the portrait derivation, so the "
            "MG-038 measurement refuses it by name."),
    }
    try:
        result = module.measure_recomposition(str(artifact), design, dataset, motion)
        record["gate_pass"] = True
        record["measurement"] = result
        write_record(NEGATIVES / "incorrect-crop" / "gate-record.json", record)
        print("incorrect_crop gate unexpectedly PASSED its negative")
        return False
    except module.HandoffError as err:
        record["gate_pass"] = False
        record["error"] = {
            "code": err.code,
            "mg_category": err.mg_category,
            "exit_code": err.exit_code,
            "message": err.message,
        }
        write_record(NEGATIVES / "incorrect-crop" / "gate-record.json", record)
        return True


def gate_decorative_substitution() -> bool:
    storyboard = NEGATIVES / "decorative-substitution" / "storyboard.json"
    proc = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "validate_storyboard.py"),
         "validate", str(storyboard)],
        capture_output=True, text=True)
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"storyboard validator gave no JSON: {proc.stdout[-300:]} {proc.stderr[-300:]}")
        return False
    record = {
        "negative": "decorative_substitution",
        "gate": "MG-009 storyboard planner validator "
                "(scripts/validate_storyboard.py)",
        "command": "python3 scripts/validate_storyboard.py validate "
                   "negatives/decorative-substitution/storyboard.json",
        "artifact": "storyboard.json",
        "expected": "fail",
        "validator_exit_code": proc.returncode,
        "valid": result.get("valid"),
        "coverage": result.get("coverage"),
        "findings": result.get("findings"),
        "reason_it_fails": (
            "The mechanism beat is replaced by a bullet-list text card "
            "and the other explanatory beats are text cards whose motion "
            "is decorative (a sweeping band and a sliding headline), so "
            "the storyboard fails the per-beat representation rules and "
            "the Section 1.1 rule that at least two-thirds of explanatory "
            "beats are information-bearing non-text."),
    }
    write_record(
        NEGATIVES / "decorative-substitution" / "gate-record.json", record)
    return result.get("valid") is False and proc.returncode != 0


def main() -> int:
    results = {
        "small_type": gate_small_type(),
        "incorrect_crop": gate_incorrect_crop(),
        "decorative_substitution": gate_decorative_substitution(),
    }
    print(json.dumps(results, indent=2))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
