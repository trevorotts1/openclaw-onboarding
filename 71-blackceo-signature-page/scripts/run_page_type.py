#!/usr/bin/env python3
"""run_page_type.py - wireframes and mockups for one page of a non-landing page type.

A page type with its own section structure (today: the upsell, copy_version "upsell",
page roles upsell_1 and upsell_2) does not get its own pipeline. This script only
sequences Skill 71's existing parts, in order:

  1. scripts/shared_page_service.py   admit the page-request, stage the run (intake,
                                      launch record, route graph, brand, design style)
  2. scripts/build_production_request.py   one production request per stage, one request
                                      section per canonical section of the page type
  3. scripts/stage_executor.py        desktop-wireframe, mobile-tablet, visual-mockup:
                                      desktop and mobile images, one long top-to-bottom
                                      review PDF per stage, overview boards

The Design Board (per page role) and final-mockups come after the image chain and the
client's recorded approval; this script stops before them and says so. Every rule the
executor enforces (client brand colours only, hypersaturated grade, design style A/B/C,
composition variety, references for structure only) applies unchanged.

Usage:
  run_page_type.py --copy-version upsell --copy-json copy.json --bundle bundle.json \\
      --request page-request.json --launch-record launch.json --route-graph route-graph.json \\
      --brand-file brand.json --brand-owner NAME --image-cap N --run-dir RUN \\
      [--design-style A|B|C] [--provider stub|kie] [--allow-paid] [--design-prose P] [--preflight]

Exit codes: 0 done; 1 refused or a stage failed; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC_DIR = HERE.parent / "references" / "copy-specs"
STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")


def run(argv):
    print("+ " + " ".join(Path(a).name if "/" in str(a) else str(a) for a in argv))
    return subprocess.run([sys.executable, *map(str, argv)]).returncode


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--copy-version", required=True)
    p.add_argument("--copy-json", type=Path, required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--launch-record", type=Path, required=True)
    p.add_argument("--route-graph", type=Path, required=True)
    p.add_argument("--brand-file", type=Path, required=True)
    p.add_argument("--brand-owner", required=True)
    p.add_argument("--image-cap", type=int, required=True)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--design-style", choices=["A", "B", "C"])
    p.add_argument("--provider", choices=["stub", "kie"], default="stub")
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--design-prose", type=Path)
    p.add_argument("--slots", type=Path)
    p.add_argument("--preflight", action="store_true", help="compose every prompt, call no provider")
    a = p.parse_args(argv)

    spec_file = SPEC_DIR / f"{a.copy_version}-v6.json"
    if not spec_file.is_file() or not json.loads(spec_file.read_text(encoding="utf-8")).get("page_roles"):
        print(f"REFUSED: copy_version {a.copy_version!r} is not a page type this script runs")
        return 1
    roles = json.loads(spec_file.read_text(encoding="utf-8"))["page_roles"]
    try:
        role = json.loads(a.request.read_text(encoding="utf-8")).get("page_role")
        instance = json.loads(a.bundle.read_text(encoding="utf-8"))["page_plan"]["instance"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"REFUSED: cannot read the request or bundle: {exc}")
        return 1
    if role not in roles or instance != role:
        print(f"REFUSED: the request page_role is {role!r} and the bundle instance is {instance!r}; "
              f"a {a.copy_version} page runs only as one of {roles}, and both must agree")
        return 1

    service = [HERE / "shared_page_service.py", "--request", a.request, "--run-dir", a.run_dir,
               "--page-version", a.copy_version, "--brand-owner", a.brand_owner,
               "--image-cap", a.image_cap, "--brand-file", a.brand_file,
               "--launch-record", a.launch_record, "--route-graph", a.route_graph,
               "--validation-only"]  # admission seam only; the stages below generate
    if a.design_style:
        service += ["--design-style", a.design_style]
    if run(service):
        return 1
    # the copy source the executor's section-count check reads (request vs copy, one to one)
    shutil.copyfile(a.copy_json, a.run_dir / "copy.json")
    model = [] if a.provider == "kie" else ["--model", "STUB-NO-MODEL"]
    for stage in STAGES:
        name = f"production-request-{stage}.json"
        build = [HERE / "build_production_request.py", "--copy-version", a.copy_version,
                 "--page-role", role,  # the role this run verified above, never the builder's default
                 "--copy-json", a.copy_json, "--bundle", a.bundle, "--stage", stage,
                 "--out", a.run_dir / name, "--run-dir", a.run_dir, *model]
        for flag, value in (("--design-prose", a.design_prose), ("--slots", a.slots)):
            build += [flag, value] if value else []
        execute = [HERE / "stage_executor.py", a.run_dir, "--request", name, "--stages", stage,
                   "--provider", a.provider]
        if a.preflight:
            execute.append("--preflight")
        if a.allow_paid:
            execute.append("--allow-paid")
        if run(build) or run(execute):
            print(f"FAIL: {stage} did not complete; nothing after it ran")
            return 1
    run_dir = a.run_dir.resolve()
    request = run_dir / "production-request-visual-mockup.json"
    final = run_dir / "production-request-final-mockups.json"
    executor = HERE / "stage_executor.py"

    def fmt(cmd):  # one copy-pasteable shell command: the run dir may contain spaces
        return " ".join(shlex.quote(str(x)) for x in cmd)

    if a.preflight:  # prompts only: no provider call, no image, nothing is complete
        print(f"PREVIEW {role}: desktop and mobile wireframe and mockup prompts composed and "
              "validated; no provider was called, no image exists and no stage completed. "
              "Nothing after this ran. Re-run without --preflight to generate.")
    elif a.provider == "stub":  # placeholder PNGs only: never a completion
        print(f"PREVIEW {role}: the stub provider wrote placeholder PNGs for the wireframe and "
              "mockup stages; no real image exists and nothing is ready for a client. Re-run with "
              "--provider kie --allow-paid to generate.")
    else:
        print(f"DONE {role}: desktop and mobile wireframes and mockups ({a.provider} provider).")
    if a.preflight or a.provider == "stub":
        print("NOTE: nothing is complete yet; NEXT 1 and NEXT 2 are the commands for a run that "
              "generated real images.")
    print(f"NEXT 1, Design Board for this page role (client approval), on its own: "
          f"{fmt([sys.executable, executor, run_dir, '--stages', 'design-board', '--request', request.name])}")
    build_final = [sys.executable, HERE / "build_production_request.py", "--copy-version", a.copy_version,
                   "--page-role", role, "--copy-json", a.copy_json, "--bundle", a.bundle,
                   "--stage", "final-mockups", "--out", final, "--run-dir", run_dir, *model]
    for flag, value in (("--design-prose", a.design_prose), ("--slots", a.slots)):
        build_final += [flag, value] if value else []
    print(f"NEXT 2, final-mockups, only after the client's approval is recorded, in a run of its "
          f"own (the executor refuses the two stages together): build its request first, then "
          f"run it: {fmt(build_final)} && "
          f"{fmt([sys.executable, executor, run_dir, '--stages', 'final-mockups', '--request', final.name])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
