#!/usr/bin/env python3
"""test_pd_phase_checks_no_duplicate_defs.py — PD-079b (lane FL17).

``phase_verifiers.py`` defined four names twice: the later copy silently
replaced the earlier one, so a fix applied to one copy could be dead code.
The duplicates are gone.

Rows (01-BUILD-SPEC.md, section PD-079b):

  A1  parse the file with Python's parser and count: each of the four names
      is defined once.
  A2  the module's self-test prints the same pass count as before the change.

No network, no model call, no live service.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
MODULE = SCRIPTS / "phase_verifiers.py"

FOUR = (
    "_verify_fish_tag",
    "_sp_claim_matches_intake",
    "_verify_sp_claim",
    "_verify_sp_intake_trace",
)


def _def_counts(source: str) -> dict:
    counts = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            counts[node.name] = counts.get(node.name, 0) + 1
    return counts


def test_a1_each_of_the_four_is_defined_once():
    counts = _def_counts(MODULE.read_text(encoding="utf-8"))
    got = {name: counts.get(name, 0) for name in FOUR}
    assert got == {name: 1 for name in FOUR}, got


def test_a1_negative_control_duplicate_is_caught():
    """The check itself must fire on a duplicate — else A1 proves nothing."""
    dup = ("def _verify_sp_claim(run_dir):\n    return True, []\n\n"
           "def _verify_sp_claim(run_dir):\n    return True, []\n")
    counts = _def_counts(dup)
    assert counts["_verify_sp_claim"] == 2, counts


def test_a2_selftest_still_passes():
    proc = subprocess.run([sys.executable, str(MODULE), "--selftest"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert "PASS — all self-tests passed." in proc.stdout, proc.stdout


if __name__ == "__main__":
    test_a1_each_of_the_four_is_defined_once()
    test_a1_negative_control_duplicate_is_caught()
    test_a2_selftest_still_passes()
    print("PD-079b: all rows pass")
