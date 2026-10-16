"""MG-044 reference suite tool: build evidence-index.json.

Walks the reference suite tree and records every file with its
SHA-256 and the command (or source) that produced it. Producing
commands are assigned by path pattern below; files copied byte-for-
byte from shipped evidence name their source instead.

Usage (from 72-motion-video-plus/):
  python3 assets/examples/reference-suite/tools/build-evidence-index.py

The index is regenerated, never hand-edited: if a file is not in the
index it is not part of the suite, and tests/unit/
test_reference_suite.py fails on any file whose hash disagrees.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = SUITE_DIR.parents[2]

COMMANDS: list[tuple[str, str]] = [
    ("modes/powerpoint_graphic/clip.mp4",
     "MG-035 producer render (tests/evidence/mg035/component.mp4, byte-identical copy)"),
    ("modes/powerpoint_graphic/poster.png",
     "MG-035 package poster (tests/evidence/mg035/poster.png, byte-identical copy)"),
    ("modes/powerpoint_graphic/deck.pptx",
     "MG-035 package build (tests/evidence/mg035/test-deck.pptx, byte-identical copy)"),
    ("modes/powerpoint_graphic/fallback.png",
     "MG-035 package fallback (tests/evidence/mg035/fallback.png, byte-identical copy)"),
    ("modes/powerpoint_graphic/package-record.json",
     "MG-035 package record (tests/evidence/mg035/package-record.json, byte-identical copy)"),
    ("modes/powerpoint_graphic/qc-record.json",
     "MG-035 final QC (tests/evidence/mg035/final-qc.json, byte-identical copy)"),
    ("modes/powerpoint_graphic/coverage.json",
     "MG-031 coverage record for this render (tests/evidence/mg033/demo/coverage.json, byte-identical copy)"),
    ("modes/powerpoint_graphic/manifest.json",
     "copy of assets/examples/powerpoint_graphic/manifest.json"),
    ("modes/powerpoint_graphic/dataset.json",
     "copy of the mode example dataset (assets/examples/powerpoint_graphic/data/)"),
    ("modes/vsl_desktop/clip.mp4",
     "MG-037 return package insert (same deterministic render as tests/evidence/mg035/component.mp4; hash ties to tests/evidence/mg037/measurements.json return_package.insert_mp4_sha256)"),
    ("modes/vsl_desktop/poster.png",
     "MG-037 return package poster (produce step output; sha256 equals the MG-037 record's return_package.poster_sha256)"),
    ("modes/vsl_desktop/assembled-vsl.mp4",
     "MG-044 reproduction of the MG-037 parent assembly: python3 tests/fixtures/vsl/make_parent_media.py <dir>, then python3 scripts/vsl_handoff.py assemble-parent (verdict pass; output sha256 matches the MG-037 record's assembled hash)"),
    ("modes/vsl_desktop/return-package.json",
     "MG-037 return package record from the produce step run by MG-044 (same commands as tests/evidence/mg037/measurements.json)"),
    ("modes/vsl_desktop/handoff.json",
     "copy of tests/fixtures/vsl/handoff-desktop.json (the handoff the producer ran)"),
    ("modes/vsl_desktop/measurements.json",
     "MG-037 record (tests/evidence/mg037/measurements.json, byte-identical copy)"),
    ("modes/vsl_desktop/assembly-report.json",
     "assembly report from MG-044's reproduction of the MG-037 assembly (verdict pass; measurements match tests/evidence/mg037/assembly-report.json)"),
    ("modes/vsl_desktop/motion-proof-record.json",
     "MG-037 record (tests/evidence/mg037/motion-proof-record.json, byte-identical copy)"),
    ("modes/vsl_desktop/qc-record.json",
     "MG-037 assembled VSL plan lane QC (tests/evidence/mg037/qc-vsl.json, byte-identical copy)"),
    ("modes/vsl_desktop/qc-insert.json",
     "MG-037 insert package lane QC (tests/evidence/mg037/qc-insert.json, byte-identical copy)"),
    ("modes/vsl_desktop/qc-insert-diagnostic.json",
     "MG-037 insert lane diagnostic (tests/evidence/mg037/qc-insert-diagnostic.json, byte-identical copy)"),
    ("modes/vsl_desktop/coverage.json",
     "python3 scripts/critique_bundle.py build --video modes/vsl_desktop/clip.mp4 --job-id fixture-vsl-desktop"),
    ("modes/vsl_desktop/manifest.json",
     "copy of assets/examples/vsl_desktop/manifest.json"),
    ("modes/vsl_desktop/dataset.json",
     "copy of assets/examples/vsl_desktop/data/bars.json"),
    ("modes/vsl_desktop/parent-handoff.json",
     "copy of assets/examples/vsl_desktop/parent-handoff.json"),
    ("modes/vsl_mobile/clip.mp4",
     "MG-038 recomposed mobile insert (tests/evidence/mg038/insert-mobile.mp4, byte-identical copy)"),
    ("modes/vsl_mobile/poster.png",
     "MG-038 poster (tests/evidence/mg038/poster.png, byte-identical copy)"),
    ("modes/vsl_mobile/delivery-record.json",
     "MG-038 record (tests/evidence/mg038/delivery-record.json, byte-identical copy)"),
    ("modes/vsl_mobile/fit-report.json",
     "MG-038 record (tests/evidence/mg038/fit-report.json, byte-identical copy)"),
    ("modes/vsl_mobile/motion-proof-record.json",
     "MG-038 record (tests/evidence/mg038/motion-proof-record.json, byte-identical copy)"),
    ("modes/vsl_mobile/qc-record.json",
     "MG-038 mobile QC (tests/evidence/mg038/qc-mobile.json, byte-identical copy)"),
    ("modes/vsl_mobile/measurements.json",
     "MG-038 record (tests/evidence/mg038/measurements.json, byte-identical copy)"),
    ("modes/vsl_mobile/coverage.json",
     "python3 scripts/critique_bundle.py build --video modes/vsl_mobile/clip.mp4 --job-id fixture-vsl-mobile"),
    ("modes/vsl_mobile/manifest.json",
     "copy of assets/examples/vsl_mobile/manifest.json"),
    ("modes/vsl_mobile/dataset.json",
     "copy of assets/examples/vsl_mobile/data/bars.json"),
    ("modes/vsl_mobile/parent-handoff.json",
     "copy of assets/examples/vsl_mobile/parent-handoff.json"),
    ("modes/standalone_video/clip.mp4",
     "python3 scripts/build_standalone.py build --package tests/fixtures/standalone/silent --stage <scratch> (renders/final.mp4 of the staged job)"),
    ("modes/standalone_video/poster.png",
     "the same build's delivery poster (frame 390, the declared final state)"),
    ("modes/standalone_video/delivery-record.json",
     "the same build's delivery record (deliverables.json)"),
    ("modes/standalone_video/placement.json",
     "the same build's placement record"),
    ("modes/standalone_video/build-record.json",
     "the same build's build record (contracts findings, compile equality, proof, review, and QC step verdicts)"),
    ("modes/standalone_video/qc-record.json",
     "the same build's MG-034 QC record (job/qc/final-qc.json, verdict pass, 27 checks)"),
    ("modes/standalone_video/coverage.json",
     "the same build's MG-031 coverage record (job/review/coverage.json)"),
    ("modes/standalone_video/motion-proof-record.json",
     "the same build's motion proof record (job/motion-proof.json, verdict pass)"),
    ("modes/standalone_video/manifest.json",
     "copy of tests/fixtures/standalone/silent/manifest.json (the built package's own manifest, job fixture-standalone-silent, 405 frames)"),
    ("modes/standalone_video/source-package.json",
     "the same build's delivery source-package record (staged job delivery/source-package.json)"),
    ("components/clips/",
     "final renders of the MG-044 image-components suite (runtime/tests/run-image-components.ts)"),
    ("modes/standalone_video/storyboard.json",
     "copy of tests/fixtures/standalone/silent/storyboard.json"),
    ("modes/standalone_video/data/",
     "copies of tests/fixtures/standalone/silent/data/ (the program's literal chart inputs)"),
    ("sequence/clips/beat1-c01.mp4",
     "node tools/render-c01-clip.mjs <mg044 c01-job> <out> (adapter renderFinal on the MG-044 suite's C01 job; TMPDIR on the home filesystem)"),
    ("sequence/clips/beat3-bars.mp4",
     "the deterministic C05 production render (same bytes as modes/powerpoint_graphic/clip.mp4)"),
    ("sequence/clips/beat5-detail.mp4",
     "final render of the MG-044 C02 fixture scene through the shipped Hyperframes adapter (180 frames; frame-150 detail fraction measures 0.0477 against the suite record's 0.050372, the difference being MP4 compression at the antialiased edges; the MG-044 suite's own recorded clip for the same scene is hashed in tests/evidence/mg044/measurements.json)"),
    ("components/c01/coverage.json",
     "python3 scripts/critique_bundle.py build --video sequence/clips/beat1-c01.mp4 --job-id mg044-c01-job"),
    ("components/c06-polish-measurements.json",
     "python3 tools/measure-c06-polish.py <committed HEAD hf-c06-line-f150.png> tests/evidence/mg016/hf-c06-line-f150.png"),
    ("negatives/",
     "python3 tools/run-negative-gates.py (gate records); staged artifacts per each folder's record"),
    ("tools/",
     "authored with this suite (MG-044)"),
]

GENERIC: list[tuple[str, str]] = [
    ("sequence/frames/", "decoded still copied from the named producer evidence (see sequence/storyboard.json per-beat records)"),
    ("components/frames/", "decoded still copied from the named producer evidence (see components/index.json per-component records)"),
    ("review-record.json", "authored for this suite under the MG-033 protocol; validates with python3 scripts/review_rubric.py validate"),
    ("reference-registry.json", "authored for this suite per Directive Section 17.4; hashes computed from the shipped artifacts"),
    ("components/index.json", "authored for this suite (MG-044 component example index)"),
    ("sequence/storyboard.json", "authored for this suite per Directive Section 8"),
    ("README.md", "authored for this suite (MG-044)"),
]


def command_for(rel: str) -> str:
    for prefix, command in COMMANDS:
        if rel == prefix or (prefix.endswith("/") and rel.startswith(prefix)):
            return command
    for needle, command in GENERIC:
        if rel.startswith(needle) or needle in rel:
            return command
    return "authored or staged for this suite (MG-044); see the folder's own record"


def main() -> int:
    artifacts = []
    for path in sorted(SUITE_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SUITE_DIR).as_posix()
        if rel == "evidence-index.json":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append({
            "path": rel,
            "sha256": digest,
            "bytes": path.stat().st_size,
            "produced_by": command_for(rel),
        })
    index = {
        "schema_version": "1.0",
        "item": "MG-044",
        "note": (
            "Every artifact in the reference suite, the command or source "
            "that produced it, and its SHA-256. Regenerated by "
            "tools/build-evidence-index.py; never hand-edited. The index "
            "does not list itself."
        ),
        "artifacts": artifacts,
    }
    out = SUITE_DIR / "evidence-index.json"
    out.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} with {len(artifacts)} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
