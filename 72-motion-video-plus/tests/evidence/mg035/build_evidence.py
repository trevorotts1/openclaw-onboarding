"""Build the MG-035 evidence set from the staged delivery job.

The job package itself is assembled in scratch space by the
evidence builder for this item (fixture sources copied from
tests/fixtures/modes/powerpoint_graphic, the compiled timeline and
sidecar produced by the real TS timeline compiler, the final
rendered through the shipped Remotion dispatcher, the review bundle
built by scripts/critique_bundle.py, and the final QC record
produced by the genuine MG-034 scripts/qc.py from that item's
branch worktree, since MG-034 is not part of this item's base).

This script runs the MG-035 packager on that job, retains the
package's governing outputs here, performs the moved-deck
extraction proof and the LibreOffice PDF proof, and writes
measurements.json.

Environment:
    MG035_JOB_DIR   the staged delivery job package (required)
    MG035_SCRATCH   scratch root for intermediates (default:
                    a fresh temp directory)

Nothing in this script edits the job package or the fixture
sources; the package is rebuilt fresh under the scratch root.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

EVIDENCE_DIR = Path(__file__).resolve().parent
SKILL_ROOT = EVIDENCE_DIR.parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import powerpoint_adapter  # noqa: E402
import powerpoint_package  # noqa: E402


def sha256_file(path: Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def mean_abs_diff(a: Path, b: Path) -> float:
    def rgb(path: Path, scale: bool) -> bytes:
        args = ["ffmpeg", "-v", "error", "-i", str(path)]
        if scale:
            args += ["-vf", "scale=1920:1080"]
        args += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        proc = subprocess.run(args, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg decode failed for %s" % path)
        return proc.stdout
    left, right = rgb(a, False), rgb(b, True)
    assert len(left) == len(right)
    return sum(abs(x - y) for x, y in zip(left, right)) / len(left)


def main() -> int:
    job_dir = os.environ.get("MG035_JOB_DIR")
    if not job_dir:
        print("MG035_JOB_DIR is not set", file=sys.stderr)
        return 2
    job_dir = Path(job_dir)
    scratch = Path(os.environ.get(
        "MG035_SCRATCH", tempfile.mkdtemp(prefix="mg035-evidence-")))
    scratch.mkdir(parents=True, exist_ok=True)

    package_dir = scratch / "package"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    result = powerpoint_package.package(job_dir, package_dir)
    record = result["record"]

    retained = {}
    copies = {
        "package-record.json": package_dir / "package-record.json",
        "test-deck.pptx": package_dir / "deck.pptx",
        "poster.png": package_dir / "poster.png",
        "fallback.png": package_dir / "fallback.png",
        "component.mp4": package_dir / "component.mp4",
        "final-qc.json": package_dir / "final-qc.json",
    }
    for name, src in copies.items():
        dst = EVIDENCE_DIR / name
        shutil.copy(src, dst)
        retained[name] = {
            "sha256": sha256_file(dst), "bytes": dst.stat().st_size}

    # The moved-deck proof: a copy under a different name in a
    # different directory must still carry the media, byte-identical.
    moved_dir = scratch / "moved"
    moved_dir.mkdir(exist_ok=True)
    moved = moved_dir / "renamed-test-deck.pptx"
    shutil.copy(EVIDENCE_DIR / "test-deck.pptx", moved)
    moved_proof = powerpoint_adapter.verify_deck(
        moved,
        expect_mp4_sha256=record["artifact"]["sha256"],
        expect_fallback_sha256=record["fallback"]["sha256"])

    # The PDF proof, as far as this platform allows: LibreOffice
    # headless conversion on Linux. PowerPoint's own PDF export is
    # UNVERIFIED, and this record says so.
    pdf_dir = scratch / "pdf"
    pdf_dir.mkdir(exist_ok=True)
    proc = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf",
         str(moved), "--outdir", str(pdf_dir)],
        capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("soffice conversion failed: %s"
                           % proc.stderr[-500:])
    pdf = pdf_dir / "renamed-test-deck.pdf"
    subprocess.run(
        ["pdftoppm", "-png", "-r", "192", str(pdf),
         str(pdf_dir / "page")],
        capture_output=True, text=True, check=True)
    pages = sorted(pdf_dir.glob("page-*.png"))
    pdf_proof = {
        "tool": "LibreOffice headless (soffice) on Linux",
        "pdf_pages": len(pages),
        "page_mean_abs_diff_vs_poster": [
            round(mean_abs_diff(package_dir / "poster.png", page), 4)
            for page in pages],
        "powerpoint_pdf_export": "UNVERIFIED",
    }

    qc_record = json.loads(
        (package_dir / "final-qc.json").read_text(encoding="utf-8"))
    export_record = json.loads(
        (job_dir / "renders" / "final.mp4.export-record.json")
        .read_text(encoding="utf-8"))

    measurements = {
        "item": "MG-035",
        "section": "Directive MG-035: package PowerPoint motion "
                   "components correctly",
        "job_id": record["job_id"],
        "job_package": {
            "note": "assembled in scratch from the fixture sources; "
                    "compiled timeline and sidecar from the real TS "
                    "compiler; final rendered through the shipped "
                    "Remotion dispatcher (shared runtime, remotion "
                    "4.0.535); review bundle from "
                    "scripts/critique_bundle.py",
            "manifest_sha256": record["source_job"]["manifest_sha256"],
            "timeline_sha256": record["source_job"]["timeline_sha256"],
            "sidecar_sha256": record["source_job"]["sidecar_sha256"],
        },
        "render": {
            "artifact_sha256": record["artifact"]["sha256"],
            "export_profile": export_record["profile"],
            "export_route": export_record["route"],
            "stream": export_record["stream"],
        },
        "qc_gate": {
            "verdict": qc_record["verdict"],
            "summary": qc_record["summary"],
            "artifact_sha256": qc_record["artifact_sha256"],
            "produced_by": "the genuine MG-034 scripts/qc.py, run "
                           "from that item's branch worktree "
                           "(wt-mg034); MG-034 is not part of this "
                           "item's base, and the packager consumes "
                           "the record without importing the QC "
                           "layer",
        },
        "poster": record["poster"],
        "fallback": record["fallback"],
        "playback": record["playback"],
        "placement": record["placement"],
        "checks": record["checks"],
        "moved_deck_proof": moved_proof,
        "pdf_proof": pdf_proof,
        "platform": record["platform"],
        "font_seam": {
            "intake_alias": "fixture-sans",
            "resolved_family": "Liberation Sans",
            "note": "the canonical contracts schema constrains "
                    "family_alias to an ID token and the runtime "
                    "registry maps the token to the family; MG-034 "
                    "package.fonts resolves by exact family name "
                    "through fontconfig, so the delivery-stage "
                    "assets record names the resolved family and "
                    "the intake record is kept beside it as "
                    "intake-assets.json in the job package. See "
                    "references/powerpoint-packaging.md.",
        },
        "retained_files": retained,
    }
    (EVIDENCE_DIR / "measurements.json").write_text(
        json.dumps(measurements, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "evidence built",
        "package_dir": str(package_dir),
        "evidence_dir": str(EVIDENCE_DIR),
        "moved_deck_media_matches":
            moved_proof["media_matches_packaged_artifact"],
        "pdf_pages": pdf_proof["pdf_pages"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
