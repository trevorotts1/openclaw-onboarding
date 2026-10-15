"""Build the MG-038 evidence set from a real producer run.

Runs scripts/vsl_mobile.py produce on the shipped acceptance
handoff fixture (tests/fixtures/vsl/handoff-mobile.json) into a
scratch work directory, then retains the governing records here:
the delivery record, the fit report, the MG-034 QC report, the
MG-032 motion-proof record, the rendered vertical artifact, and
its poster. measurements.json restates the recomposition
comparison with its numbers, the fit verdicts, the QC summary,
and the font declaration disclosure.

Environment:
    MG038_SCRATCH   scratch root for the producer run (default:
                    a fresh temp directory)

Nothing in this script edits the fixture sources or any tracked
file outside this evidence directory.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

EVIDENCE_DIR = Path(__file__).resolve().parent
SKILL_ROOT = EVIDENCE_DIR.parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import vsl_mobile  # noqa: E402


def sha256_file(path: Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    scratch = Path(os.environ.get(
        "MG038_SCRATCH", tempfile.mkdtemp(prefix="mg038-evidence-")))
    work = scratch / "produce"
    result = vsl_mobile.produce(
        str(SKILL_ROOT / "tests" / "fixtures" / "vsl"
            / "handoff-mobile.json"),
        str(work))
    record = result["delivery_record"]

    retained = {}
    copies = {
        "delivery-record.json": work / "delivery"
        / "delivery-record.json",
        "fit-report.json": work / "fit-report.json",
        "qc-mobile.json": work / "qc-mobile.json",
        "motion-proof-record.json": work / "motion-proof-record.json",
        "insert-mobile.mp4": work / "delivery" / "insert-mobile.mp4",
        "poster.png": work / "delivery" / "poster.png",
    }
    for name, src in copies.items():
        dst = EVIDENCE_DIR / name
        shutil.copy(src, dst)
        retained[name] = {
            "sha256": sha256_file(dst), "bytes": dst.stat().st_size}

    qc = result["qc_report"]
    fit = result["fit_report"]
    proof = result["proof_record"]
    measurements = {
        "item": "MG-038",
        "section": "Directive MG-038: add the mobile VSL vertical "
                   "derivative workflow",
        "handoff_id": record["handoff_id"],
        "insert_job_id": record["insert_job_id"],
        "derivative_of": record["derivative_of"],
        "canvas": record["canvas"],
        "slot": record["slot"],
        "layout": record["layout"],
        "recomposition": record["recomposition"],
        "fit": {
            "verdict": fit["verdict"],
            "narration": {
                "asset_ref": fit["narration"]["asset_ref"],
                "same_approved_narration":
                    fit["narration"]["same_approved_narration"],
                "cue": fit["narration"]["cue"],
                "compiled_total_frames":
                    fit["narration"]["compiled_total_frames"],
                "slot_length_frames":
                    fit["narration"]["slot_length_frames"],
                "parent_total_frames":
                    fit["narration"]["parent_total_frames"],
            },
            "text_elements": fit["text"]["elements"],
            "caption_profile": fit["captions"]["profile"],
            "caption_entries": fit["captions"]["entries"],
        },
        "motion_proof": {
            "verdict": proof["verdict"],
            "assertions": proof["assertions"],
        },
        "qc_gate": {
            "verdict": qc["verdict"],
            "mode": qc["mode"],
            "summary": qc["summary"],
            "fonts_check": next(
                c for c in qc["checks"] if c["id"] == "package.fonts"),
        },
        "font_declaration": record["font_declaration"],
        "artifact": record["artifacts"]["mp4"],
        "retained_files": retained,
        "note": "Produced by scripts/vsl_mobile.py produce on the "
                "acceptance fixture: the staged vsl_mobile job "
                "passes the contracts layer, compiles its own "
                "timeline in slot mode, renders through the "
                "shipped dispatcher under the shared runtime, "
                "passes the MG-032 motion proof under a portrait "
                "case, and passes the MG-034 package-lane gate. "
                "Fixture context: the approval record carries "
                "authority_status not_verified, as the shipped "
                "suites do.",
    }
    (EVIDENCE_DIR / "measurements.json").write_text(
        json.dumps(measurements, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "evidence built",
        "work_dir": str(work),
        "evidence_dir": str(EVIDENCE_DIR),
        "recomposition_verdict": record["recomposition"]["verdict"],
        "qc_verdict": qc["verdict"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
