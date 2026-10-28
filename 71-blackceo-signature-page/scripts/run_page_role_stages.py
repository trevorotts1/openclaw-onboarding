#!/usr/bin/env python3
"""Run a page type's wireframe and mockup stages: the request builder, then the executor, per stage.

This is the production command a page type's wrapper hands to scripts/shared_page_service.py as
`--pipeline-command` (the thank-you page's wrapper is Skill 49's launch adapter for the thank_you
role). It adds no pipeline of its own: for each stage it runs scripts/build_production_request.py
(the one request builder, reading the page type's copy spec through scripts/page_role.py) and then
scripts/stage_executor.py (the one executor: brand colors, Design Board gate, design style,
composition, hypersaturation, desktop and mobile slices, one long PDF per stage, overview boards).

It stops after visual-mockup. The Design Board (stage_executor --stages design-board) and then
final-mockups come after the client approves the board, exactly as for a landing page; this
script never starts them.

Usage:
  run_page_role_stages.py <run_dir> [--manuscript FILE] [--stages a,b,c] [--design-prose FILE]
      [--model ID] [--provider stub|kie] [--allow-paid] [--preflight]

The run's intake.json must carry a page type's own copy_version (write_intake.py --page-version
thank-you); a landing run is refused, because its stages are driven by stage_gate as before.

Exit codes: 0 every stage ran; 1 a named refusal from the builder or the executor; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import page_role  # noqa: E402

DEFAULT_STAGES = "desktop-wireframe,mobile-tablet,visual-mockup"
DEFAULT_MODEL = "gpt-image-2-5-sunburst-image-to-image"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--manuscript", type=Path, default=None,
                   help="default <run_dir>/copy/internal-manuscript.md")
    p.add_argument("--stages", default=DEFAULT_STAGES)
    p.add_argument("--design-prose", type=Path, default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--provider", choices=["stub", "kie"], default="stub")
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--preflight", action="store_true",
                   help="compose and validate every prompt; no provider call, no image file")
    a = p.parse_args(argv)
    run_dir = a.run_dir.resolve()
    try:
        intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAIL: cannot read {run_dir / 'intake.json'}: {exc}")
        return 2
    version = intake.get("copy_version")
    spec = page_role.role_specs().get(str(version))
    if spec is None:
        print(f"FAIL: intake copy_version {version!r} is not a page type's own form "
              f"({', '.join(page_role.role_specs()) or 'none'}); a landing run is driven by stage_gate.py")
        return 2
    manuscript = a.manuscript or run_dir / "copy" / "internal-manuscript.md"
    for stage in (s.strip() for s in a.stages.split(",") if s.strip()):
        request = run_dir / "production-request.json"
        build = [sys.executable, str(HERE / "build_production_request.py"),
                 "--copy-version", version, "--manuscript", str(manuscript), "--stage", stage,
                 "--out", str(request), "--model", a.model, "--run-dir", str(run_dir)]
        if a.design_prose:
            build += ["--design-prose", str(a.design_prose)]
        run = [sys.executable, str(HERE / "stage_executor.py"), str(run_dir), "--stages", stage,
               "--provider", a.provider]
        if a.allow_paid:
            run.append("--allow-paid")
        if a.preflight:
            run.append("--preflight")
        for argv_ in (build, run):
            if subprocess.run(argv_).returncode:
                print(f"FAIL: {spec['page_label']} stage {stage} stopped at {Path(argv_[1]).name}")
                return 1
    print(f"{spec['page_label']} stages done; next: stage_executor.py {run_dir} --stages design-board "
          "(client approval), then final-mockups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
