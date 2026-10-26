#!/usr/bin/env python3
"""S75-T33 — runnable entry point for the supported-install fixtures.

Thin wrapper over tests/install_fixtures/harness.py --self-check.

Candidate resolution:
  ONB   $DSAF_ONB_CANDIDATE, else the checkout this file ships in (parents[2])
  N999  $DSAF_N999_CANDIDATE (required; exit 2 with a clear message if absent)

Exit 0 = every row ok; 1 = any FAIL; 2 = a candidate could not be resolved
(nothing was checked — never reported as a pass).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "install_fixtures" / "harness.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("s75_install_harness", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not HARNESS.is_file():
        print(f"resolve-failure: harness missing at {HARNESS}", file=sys.stderr)
        return 2
    harness = load_harness()
    argv = ["--self-check", "--keep" if "--keep" in sys.argv else ""]
    argv = [a for a in argv if a]
    onb = os.environ.get("DSAF_ONB_CANDIDATE") or str(HERE.parent.parent)
    n999 = os.environ.get("DSAF_N999_CANDIDATE")
    if not n999:
        print("resolve-failure: set DSAF_N999_CANDIDATE to a 999-setup checkout "
              "(nothing checked; this is not a pass)", file=sys.stderr)
        return 2
    return harness.main(argv + ["--candidate-onb", onb, "--candidate-n999", n999])


if __name__ == "__main__":
    sys.exit(main())
