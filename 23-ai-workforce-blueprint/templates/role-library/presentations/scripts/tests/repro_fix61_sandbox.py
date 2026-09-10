#!/usr/bin/env python3
"""Standalone repro of the fix61 sandbox ModuleNotFoundError failure mode.

Field shape: the scheduled scripts dir (materialized department) holds
poll.sh + template ONLY — no presentation_job/ tree. The pre-repair
installer ran the authority from that dir:

    cd <dept-dir> && python3 -m presentation_job.pipeline_interp --resolve

-> ModuleNotFoundError rc=1 -> installer aborted UNRESOLVED.

The repair re-locates the module to the repo checkout beside
lib-presentation-schedules.sh (WHAT it resolves unchanged), so the same
sandbox resolves.

Usage:
    python3 repro_fix61_sandbox.py [--repo-root PATH]

Exit 0 iff BROKEN fails (ModuleNotFoundError, rc != 0) AND FIXED resolves
(absolute executable path, rc 0). Read-only: touches nothing under test,
works in a tmp dir.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
# tests -> scripts -> presentations -> role-library -> templates ->
# 23-ai-workforce-blueprint -> repo root
DEFAULT_ROOT = HERE.parents[6]


def broken_probe(sandbox: Path, repo_root: Path) -> tuple[int, str]:
    """The pre-repair invocation, verbatim, from the module-less dir."""
    for name in ("presentation-intake-poll.sh",
                 "presentation-intake-poll.plist.template"):
        shutil.copy2(repo_root / "23-ai-workforce-blueprint/templates/role-library"
                     / "presentations/scripts" / name, sandbox / name)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-m", "presentation_job.pipeline_interp", "--resolve"],
        cwd=str(sandbox), env=env, capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


def fixed_probe(sandbox: Path, repo_root: Path) -> tuple[int, str]:
    """The repaired path: the real lib resolver from the same module-less dir."""
    lib = repo_root / "lib-presentation-schedules.sh"
    env = {k: v for k, v in os.environ.items()
           if k != "PRESENTATION_PIPELINE_PIN"}
    proc = subprocess.run(
        ["/bin/bash", "-c",
         'source "$0" && _pres35_resolve_interpreter "$1"', str(lib), str(sandbox)],
        env=env, capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=str(DEFAULT_ROOT))
    args = ap.parse_args()
    repo_root = Path(args.repo_root)
    lib = repo_root / "lib-presentation-schedules.sh"
    if not lib.is_file():
        print(f"no lib at {lib} — run from a checkout", file=sys.stderr)
        return 2
    ok = True
    with tempfile.TemporaryDirectory(prefix="fix61-sandbox-") as tmp:
        sandbox = Path(tmp) / "sandbox-only"
        sandbox.mkdir()
        rc, out = broken_probe(sandbox, repo_root)
        print("== BROKEN (pre-repair invocation from module-less dir) ==")
        print(f"rc={rc}")
        print(out.strip() or "<no output>")
        if rc == 0 or "ModuleNotFoundError" not in out:
            print("UNEXPECTED: failure mode NOT reproduced", file=sys.stderr)
            ok = False
        else:
            print("reproduced: ModuleNotFoundError, installer would abort UNRESOLVED")
        print()
        rc, out = fixed_probe(sandbox, repo_root)
        print("== FIXED (repaired lib resolver from the same dir) ==")
        print(f"rc={rc}")
        print(out.strip() or "<no output>")
        first = out.strip().splitlines()[0] if out.strip() else ""
        if rc != 0 or not first.startswith("/"):
            print("NOT FIXED: resolver still refuses the sandbox", file=sys.stderr)
            ok = False
        elif not os.access(first, os.X_OK):
            print(f"NOT FIXED: resolved pin not executable: {first!r}",
                  file=sys.stderr)
            ok = False
        else:
            print(f"repaired: resolved {first}")
    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
