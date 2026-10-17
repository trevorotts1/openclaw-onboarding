#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the FAKE Skill 71 tree used by the bridge tests.

The fake stands in for production Skill 71 (the agent-driven 14-stage
pipeline on trevorotts1/openclaw-onboarding main) at the exact seam
the audit verified:

  * scripts/launch_context.py is the REAL file copied from main (it is
    the format consumer: vendored page-request/launch/route-graph
    schemas, role/skill refusal, launch-record cross-checks,
    route-graph SHA-256 check, brand-file hash check);
  * scripts/write_intake.py is the REAL file copied from main (front
    door: operator args --page-version/--brand-owner/--image-cap plus
    the --launch-context import);
  * scripts/page_result.py and scripts/write_page_result.py are the
    REAL files copied from main (the result emitter: derives status
    from run state, validates against the vendored page-result schema,
    writes page-result.json inside the run dir);
  * scripts/stage_gate.py is a STUB. The real file is the 14-stage
    mandatory gate whose stages are closed by an agent-driven
    production process (copy, images via KIE/Agnes, browser QC); it
    cannot run in a fixture. The stub honors only the one command the
    bridge issues against production Skill 71, "report <run_dir>": it
    verifies the run's intake.json exists (the gate's init
    precondition) and exits 1 naming that production is not closed,
    which is the honest state of a fixture run.
  * references/ carries the REAL vendored schemas copied from main
    plus the REAL stage-contract.json (the emitter reads the stage
    order from it).

Usage: python3 make_fake_skill71.py <dest-dir>
The caller copies skill71-main/ from main first; this script assembles
the tree from the fetched copies and REFUSES to run if a source file
is missing (so a partial fetch can never silently become a fake).
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "71-blackceo-signature-page"

REAL_FILES = [
    "scripts/launch_context.py",
    "scripts/write_intake.py",
    "scripts/page_result.py",
    "scripts/write_page_result.py",
    "references/page-request.schema.json",
    "references/page-result.schema.json",
    "references/launch.schema.json",
    "references/route-graph.schema.json",
    "references/stage-contract.json",
]

STAGE_GATE_STUB = '''#!/usr/bin/env python3
"""FAKE stage_gate.py: fixture stand-in for Skill 71's 14-stage gate.

Honors ONLY the bridge's production invocation, "report <run_dir>".
The real gate closes stages through an agent-driven production
process (copy authoring, KIE/Agnes image generation, browser QC,
GHL install) that a fixture cannot perform; this stub therefore
verifies the gate's init precondition (intake.json exists in the
run) and exits 1 reporting that production is not closed, exactly
the state of a run whose intake was just written.
"""
import json
import sys
from pathlib import Path


def main():
    argv = sys.argv[1:]
    if len(argv) != 2 or argv[0] != "report":
        print("FAKE stage_gate: only 'report <run_dir>' is supported")
        return 2
    run_dir = Path(argv[1])
    intake = run_dir / "intake.json"
    if not intake.is_file():
        print("FAIL: intake.json missing; the gate requires intake "
              "before any stage work (init precondition)")
        return 2
    data = json.loads(intake.read_text(encoding="utf-8"))
    print(f"FAKE REPORT: run {run_dir} intake present "
          f"(profile={data.get('launch_profile')}); the 14 production "
          "stages are NOT closed in a fixture run; production is an "
          "agent-driven process and no stage is closed here.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def main(argv):
    if len(argv) != 2:
        print("USAGE: make_fake_skill71.py <dest-dir>")
        return 3
    dest = Path(argv[1])
    missing = [rel for rel in REAL_FILES if not (SRC / rel).is_file()]
    if missing:
        print("REFUSED: fetched Skill 71 sources are incomplete; "
              "missing: " + ", ".join(missing))
        return 2
    if dest.exists():
        shutil.rmtree(dest)
    for rel in REAL_FILES:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SRC / rel, out)
    stub = dest / "scripts" / "stage_gate.py"
    stub.write_text(STAGE_GATE_STUB, encoding="utf-8")
    manifest = {
        "fake_of": "trevorotts1/openclaw-onboarding "
                   "71-blackceo-signature-page",
        "real_files_copied_verbatim": REAL_FILES,
        "stubbed": {"scripts/stage_gate.py":
                    "report-only stub; the real 14-stage gate is an "
                    "agent-driven production process (see BUILD-REPORT)"},
    }
    (dest / "FAKE-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"fake Skill 71 tree assembled at {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
