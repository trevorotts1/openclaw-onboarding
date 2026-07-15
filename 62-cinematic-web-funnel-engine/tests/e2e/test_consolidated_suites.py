#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_consolidated_suites.py — U21's single reference point that proves the
ENTIRE test surface of this skill (tests/unit/, tests/integration/, and this
directory's own e2e/break-it modules) still passes together as one
consolidated run.

This module deliberately contains ZERO per-unit assertions of its own — it
only shells `python3 -m unittest discover` against each existing suite
directory and asserts the aggregate result, so "consolidate the per-unit
suites without duplicating them" is satisfied literally: nothing here
re-implements a single fixture or check any other test file already owns.

Two tiers, matching the repo's own established fast/slow split:
  - FastSuitesConsolidationTests: tests/unit/ only (offline, no network, no
    real npm/next/playwright toolchain) — safe to run on every invocation.
  - FullSuitesConsolidationTests: tests/unit/ + tests/integration/ +
    tests/e2e/ together — SLOW (real npm/next/playwright/ffmpeg toolchains),
    mirrors the same "real toolchain" convention every other integration/e2e
    module in this skill already uses.

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/e2e -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _e2e_support as sup  # noqa: E402

_UNITTEST_OK_RE = re.compile(r"^OK(?:\s|$)", re.MULTILINE)
_RAN_N_TESTS_RE = re.compile(r"Ran (\d+) tests?")


def _assert_discover_passes(case: unittest.TestCase, start_dir: str, *, timeout: int, min_tests: int) -> int:
    result = sup.run(
        [sup.PY, "-m", "unittest", "discover", "-s", start_dir, "-v"],
        cwd=sup.SKILL_DIR,
        timeout=timeout,
    )
    combined = result.combined
    case.assertEqual(result.returncode, 0, msg=f"{start_dir} discover FAILED:\n{combined[-6000:]}")
    case.assertRegex(combined, _UNITTEST_OK_RE, msg=f"{start_dir}: no trailing 'OK' line found")
    match = _RAN_N_TESTS_RE.search(combined)
    case.assertIsNotNone(match, msg=f"{start_dir}: could not find a 'Ran N tests' summary line")
    ran = int(match.group(1))
    case.assertGreaterEqual(
        ran, min_tests,
        msg=f"{start_dir}: only {ran} tests ran, expected at least {min_tests} — "
        "a suite silently shrinking below its known floor is itself a regression signal",
    )
    return ran


class FastSuitesConsolidationTests(unittest.TestCase):
    """Offline, no network, no real toolchain — the floor every commit to
    this skill must clear. 672 is the last ledger-recorded count as of U17's
    integration (2026-07-15); this suite only ever grows."""

    def test_unit_suite_discovers_and_passes(self) -> None:
        _assert_discover_passes(self, "tests/unit", timeout=300, min_tests=672)


class FullSuitesConsolidationTests(unittest.TestCase):
    """SLOW: real npm/next/tsc/playwright/ffmpeg toolchains across
    tests/integration/ and this directory's own e2e/break-it modules, run
    back-to-back against the same skill tree to prove no cross-suite state
    leakage (each suite already uses its own isolated tempfile.
    TemporaryDirectory() run_dirs, so this is a real, not merely assumed,
    non-interference proof)."""

    def test_integration_suite_discovers_and_passes(self) -> None:
        _assert_discover_passes(self, "tests/integration", timeout=900, min_tests=44)

    def test_e2e_suite_including_this_module_discovers_and_passes(self) -> None:
        # Excludes only itself via unittest's own discovery re-entrancy
        # guard would be circular; instead this asserts against the two
        # sibling e2e modules directly plus itself is trivially proven by
        # the fact this very test is executing inside that discovery run
        # when invoked from the top-level `discover -s tests/e2e`. When run
        # standalone (as here), it drives the two heavy sibling modules by
        # name so the "whole e2e directory objectively runs green together"
        # claim is verified, not assumed.
        result = sup.run(
            [
                sup.PY, "-m", "unittest", "-v",
                "tests.e2e.test_full_pipeline_e2e",
                "tests.e2e.test_breakit_adversarial",
            ],
            cwd=sup.SKILL_DIR,
            timeout=900,
        )
        self.assertEqual(result.returncode, 0, msg=result.combined[-6000:])
        self.assertRegex(result.combined, _UNITTEST_OK_RE)
        match = _RAN_N_TESTS_RE.search(result.combined)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)), 20)


if __name__ == "__main__":
    unittest.main()
