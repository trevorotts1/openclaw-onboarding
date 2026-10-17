"""Timer-detection tests for MG-030 (defect D-LINT-TIMER).

The pre-MG-030 linter matched timers with the case-broken pattern
set(TimeOut|Interval), which misses the ordinary spelling setTimeout,
and it scanned the raw source, so the same text inside a string or a
comment could not be told apart from a real call. The fixtures under
tests/fixtures/lint isolate one timer aspect each inside otherwise
clean, choreography-valid legacy scenes; these tests pin the verdict
for each one:

  - a real setTimeout call fails with [timer]
  - setTimeout named inside a string literal passes
  - setTimeout named inside comments passes
  - a timer reached by computed access (window["set" + "Timeout"])
    fails with [dynamic-timer] and not [timer]
  - a timer reached through an alias (var st = window.setTimeout)
    fails with [dynamic-timer] and not [timer]

The TypeScript validation layer (runtime/src/lint) is held to the same
verdicts on the same files by runtime/tests/run-lint.ts.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
LINTER = SKILL_ROOT / "scripts" / "lint-grammar.py"
FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "lint"


def run_linter(fixture: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINTER), str(FIXTURES / fixture)],
        capture_output=True, text=True)


class TimerFixtureTests(unittest.TestCase):
    def test_clean_scene_passes(self):
        proc = run_linter("legacy-pass-clean.html")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("grammar lint clean", proc.stdout)

    def test_direct_settimeout_fails_with_timer_id(self):
        proc = run_linter("legacy-fail-timer-direct.html")
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("[timer]", proc.stdout)
        self.assertNotIn("[dynamic-timer]", proc.stdout)

    def test_settimeout_in_a_string_passes(self):
        proc = run_linter("legacy-pass-timer-string.html")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertNotIn("[timer]", proc.stdout)
        self.assertNotIn("[dynamic-timer]", proc.stdout)

    def test_settimeout_in_comments_passes(self):
        proc = run_linter("legacy-pass-timer-comment.html")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertNotIn("[timer]", proc.stdout)
        self.assertNotIn("[dynamic-timer]", proc.stdout)

    def test_computed_access_timer_fails_as_dynamic(self):
        proc = run_linter("legacy-fail-timer-dynamic.html")
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("[dynamic-timer]", proc.stdout)
        self.assertNotIn("[timer]", proc.stdout)

    def test_aliased_timer_fails_as_dynamic(self):
        proc = run_linter("legacy-fail-timer-alias.html")
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("[dynamic-timer]", proc.stdout)
        self.assertNotIn("[timer]", proc.stdout)


if __name__ == "__main__":
    unittest.main()
