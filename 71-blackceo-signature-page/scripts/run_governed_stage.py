#!/usr/bin/env python3
"""Run ONE image stage of ONE page through the admission gate, then the executor.

The single door for a caller that builds its own production request and wants the stage drawn: Skill 49's
legacy funnel tool (scripts/legacy_downsell_images.py) names this script and never the executor. It adds no
pipeline of its own and no rule of its own:

  1. scripts/governed_runner.py admit(kind="direct_executor") runs the stage gate's `check` for the stage
     BEFORE anything is written. A paid dispatch (--provider kie --allow-paid) is REFUSED here when the
     check fails or when ungoverned output sits in the run, so no money is spent on a stage the run has not
     reached. A stub run and a --preflight run record the verdict and continue; the executor then holds
     them to the same gate (a stub run on an ungated directory is refused there, AF-71-UNGATED).
  2. scripts/stage_executor.py draws the stage (brand colors, Design Board gate, design style,
     composition, receipts, spend ceiling), exactly as it does for every other caller.

Usage:
  run_governed_stage.py <run_dir> --request FILE --stage STAGE --provider stub|kie [--allow-paid] [--preflight]

Exit codes: 0 the stage was drawn (or the preflight composed); 1 a named refusal or a failed stage; 2 usage.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import governed_runner  # noqa: E402  the one admission caller

STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups", "design-board")


def authority_for(provider: str, allow_paid: bool, preflight: bool) -> str:
    """What the caller is about to be allowed to do: only a real paid dispatch is an authoritative boundary."""
    if preflight:
        return "preview"
    return "paid_dispatch" if (provider == "kie" and allow_paid) else "local"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--request", required=True, help="the production request file name inside the run dir")
    p.add_argument("--stage", required=True, choices=STAGES)
    p.add_argument("--provider", required=True, choices=["stub", "kie"])
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--preflight", action="store_true",
                   help="compose and validate every prompt; no provider call, no image file")
    a = p.parse_args(argv)
    run_dir = a.run_dir.resolve()
    if not (run_dir / a.request).is_file():
        print(f"FAIL: production request {run_dir / a.request} does not exist")
        return 2
    authority = authority_for(a.provider, a.allow_paid, a.preflight)
    try:
        decision = governed_runner.admit(run_dir, kind="direct_executor", authority=authority,
                                         stage=a.stage, owner="run_governed_stage")
    except governed_runner.AdmissionRefused as exc:
        print(f"REFUSED: {exc}")
        return 1
    check = decision.get("stage_check") or {}
    print(f"GATE {a.stage}: stage_gate.py check exit {check.get('exit')} "
          f"({'PASS' if check.get('exit') == 0 else 'stage not startable yet'}); authority={authority}",
          flush=True)
    cmd = [sys.executable, str(HERE / "stage_executor.py"), str(run_dir), "--request", a.request,
           "--stages", a.stage, "--provider", a.provider]
    if a.allow_paid:
        cmd.append("--allow-paid")
    if a.preflight:
        cmd.append("--preflight")
    return 1 if subprocess.run(cmd).returncode else 0


if __name__ == "__main__":
    sys.exit(main())
