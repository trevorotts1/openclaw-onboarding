#!/usr/bin/env python3
"""Write a wireframe stage's section-plan.json from the run's own tool inputs (SWB-400 item 2).

Usage:
  write_section_plan.py <run_dir> --stage desktop-wireframe|mobile-tablet [--request PATH] [--check-only]

Reads <run_dir>/production-request.json (default; it must have been built for --stage), copy/copy-manifest.json,
font-action-plan/font-map.json and desktop-wireframe/image-inventory.json, builds the plan (scripts/section_plan.py:
section names, printed behavior notes and slot ratios are the request's; slot ids, ratios and treatments are the
closed image inventory's; type specs are the closed font plan's), validates it with the wireframe validator's own
annotation, slot-label and id checks, and only then replaces <run_dir>/<stage>/section-plan.json atomically. The
first section carries `plan_header` with the sha256 of the request file, which validate_wireframe.py checks.

A hand edit of the plan is never needed: rebuild the request, run this, and the plan follows the request.
--check-only builds and validates the plan and reports whether the plan on disk is current; it writes nothing
(the preflight runner uses it, so a preview never touches a closed stage's files).

Exit codes: 0 written (or current, with --check-only); 1 a named refusal; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import section_plan  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--stage", required=True, choices=section_plan.STAGES)
    p.add_argument("--request", type=Path, default=None,
                   help="the production request the plan is built from (default <run_dir>/production-request.json)")
    p.add_argument("--check-only", action="store_true", help="build and validate; write nothing")
    a = p.parse_args(argv)
    run_dir = a.run_dir.resolve()
    request_path = (a.request or run_dir / "production-request.json").resolve()
    try:
        if not request_path.is_file():
            raise section_plan.PlanError(f"{request_path} is not on disk: build the stage's request first")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        sha = section_plan.sha256_file(request_path)
        plan = section_plan.build(request, a.stage, run_dir, sha)
        failures = section_plan.validate(plan, a.stage, run_dir)
        if failures:
            print(f"REFUSED: the plan built for {a.stage} does not pass the wireframe checks; nothing was written")
            for line in failures:
                print(f"- {line}")
            return 1
    except (section_plan.PlanError, ValueError, OSError) as exc:
        print(f"REFUSED: {exc}")
        return 1
    target = run_dir / a.stage / "section-plan.json"
    text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    state = "absent"
    if target.is_file():
        state = "current" if target.read_text(encoding="utf-8") == text else "differs"
    slots = sum(len(s["image_slot_ids"]) for s in plan)
    summary = f"stage={a.stage} sections={len(plan)} slots={slots} request_sha256={sha}"
    if a.check_only:
        print(f"CHECKED {target} ({state} on disk) {summary}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(f"WROTE {target} ({'replaced a differing plan' if state == 'differs' else 'unchanged content' if state == 'current' else 'new'}) {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
