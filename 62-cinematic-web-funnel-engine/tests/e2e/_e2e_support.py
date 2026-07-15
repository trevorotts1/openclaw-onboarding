#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_e2e_support.py — shared, dependency-free helpers for the U21 consolidated
end-to-end + adversarial break-it test suite (tests/e2e/).

This module intentionally contains NO test logic of its own. It exists so the
three test modules in this directory (test_full_pipeline_e2e.py,
test_breakit_adversarial.py, test_consolidated_suites.py) can share:

  - path/sys.path bootstrap identical to every other tests/unit and
    tests/integration module in this skill (same convention, not a new one);
  - a `run()` subprocess helper with a sane default timeout and consistent
    (returncode, stdout, stderr) return shape;
  - `copy_skill_dir_to_temp()` — a full on-disk copy of the skill directory
    (minus __pycache__/node_modules/.git) into a caller-owned temp directory,
    needed ONLY by the adversarial tests that must mutate CWFE-MANIFEST.json
    or a gate script's path without touching the real skill tree (this repo's
    ADR-6 front door resolves its manifest path relative to its own __file__,
    so there is no other way to safely feed it a corrupted manifest).

Nothing here duplicates any per-unit test's assertions — it only avoids
re-writing the same six lines of sys.path/subprocess boilerplate three times
in this directory.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

E2E_DIR = Path(__file__).resolve().parent
TESTS_DIR = E2E_DIR.parent
SKILL_DIR = TESTS_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"

for _p in (str(SKILL_DIR), str(SCRIPTS_DIR), str(SCRIPTS_DIR / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PY = sys.executable or "python3"

MANIFEST_PATH = SKILL_DIR / "CWFE-MANIFEST.json"
ORCHESTRATOR_PATH = SKILL_DIR / "run_cinematic_web_funnel.py"
ENTRY_SHELL_PATH = SKILL_DIR / "cinematic-web-funnel-entry.sh"

DEFAULT_TIMEOUT_SECONDS = 600

# Directories excluded when copying the skill tree into a scratch location for
# the adversarial tests that must edit CWFE-MANIFEST.json in isolation.
_COPY_EXCLUDE = {"__pycache__", "node_modules", ".git", ".next"}


class RunResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str

    @property
    def combined(self) -> str:
        return (self.stdout or "") + (self.stderr or "")


def run(
    args: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> RunResult:
    """Runs a subprocess and returns (returncode, stdout, stderr) as a
    RunResult. Never raises on a non-zero exit — callers assert on
    .returncode themselves, exactly like run_cinematic_web_funnel.py's own
    `_run_phase_gate()` treats a phase gate's exit code as the verdict."""
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


def git_tracked_gate_paths(manifest_phases: List[dict]) -> "tuple[List[str], List[str]]":
    """Splits a list of CWFE-MANIFEST.json phase dicts into (tracked_ids,
    untracked_or_absent_ids) by asking git — NOT the raw filesystem —
    whether each phase's declared `gate` path is a tracked file at HEAD.

    This build unit's workspace is shared (not per-unit-isolated) with
    concurrently running sibling build units that write directly into this
    same on-disk skill directory before their own commits land; a plain
    `Path.exists()` check is therefore not a reliable, reproducible signal
    of what THIS branch actually delivers. `git ls-files` only reports
    paths already committed to the current branch's history, which is the
    correct, deterministic ground truth for "does this build unit's
    lineage actually contain this gate script" — a stray untracked file
    dropped into the working tree by another in-flight process must never
    make this suite report a phase as implemented when it is not part of
    any commit."""
    proc = subprocess.run(
        ["git", "ls-files", "--", str(SKILL_DIR.relative_to(_repo_root()))],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_relpaths = set(proc.stdout.splitlines())
    skill_relprefix = str(SKILL_DIR.relative_to(_repo_root()))

    tracked_ids: List[str] = []
    untracked_ids: List[str] = []
    for phase in manifest_phases:
        gate_git_relpath = f"{skill_relprefix}/{phase['gate']}"
        (tracked_ids if gate_git_relpath in tracked_relpaths else untracked_ids).append(phase["id"])
    return tracked_ids, untracked_ids


def _repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(SKILL_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(proc.stdout.strip())


def copy_skill_dir_to_temp(dest_parent: Path) -> Path:
    """Copies the ENTIRE skill directory into dest_parent/62-cinematic-web-funnel-engine
    (minus caches/build artifacts) so a test can safely corrupt
    CWFE-MANIFEST.json or rewrite a phase's declared gate path without ever
    touching the real skill tree this build unit is not allowed to modify.
    Returns the path to the copied skill directory."""

    def _ignore(dir_path: str, names: List[str]) -> List[str]:
        return [n for n in names if n in _COPY_EXCLUDE]

    dest = dest_parent / SKILL_DIR.name
    shutil.copytree(SKILL_DIR, dest, ignore=_ignore)
    return dest
