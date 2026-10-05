#!/usr/bin/env python3
"""Run every Skill 71 test module. Exit 0 when all pass; exit 1 on any failure.

Includes the deterministic smoke tests (tests/test_scripts.py) and the
enforcement-order test modules. Playwright-dependent tests self-skip when
Playwright/Chromium is unavailable, so this runner is safe in any environment.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

MODULES = [
    "test_scripts.py",
    "test_validate_visual_direction.py",
    "test_validate_manifest_grade.py",
    "test_stage_gate.py",
    "test_validate_copy_prompt.py",
    "test_render_compare.py",
    "test_validate_page.py",
]

def main():
    failures = []
    for mod in MODULES:
        proc = subprocess.run([sys.executable, str(HERE / mod)], text=True)
        if proc.returncode != 0:
            failures.append(mod)
            print(f"FAIL {mod}")
        else:
            print(f"PASS {mod}")
    if failures:
        print(f"TESTS FAILED: {', '.join(failures)}")
        return 1
    print(f"ALL PASS: {len(MODULES)} test modules")
    return 0

if __name__ == "__main__":
    sys.exit(main())
