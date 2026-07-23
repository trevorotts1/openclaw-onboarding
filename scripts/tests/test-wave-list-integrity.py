#!/usr/bin/env python3
"""Unit tests for scripts/qc-assert-wave-list-integrity.py — the wave-list
integrity gate that proves every OC_WAVE<N>_SKILLS entry resolves to a real,
non-archived skill directory, and that the watchdog renders those lists by
interpolation (not a second copy).

WHY THIS TEST SUITE EXISTS
---------------------------
v12.26.0 (commit 0e53c677) archived skills 11 (superdesign) and 21 (tavily-search)
by renaming their folders, but their entries were never removed from the live wave
lists in lib-onboarding-state.sh. Wave 2 and Wave 3 were wedged fleet-wide — the
per-wave goal check failed condition (b) on every cycle, on every box, and the
onboarding watchdog took a strike every 6 minutes — because nothing verified that
a wave-list entry actually corresponded to a real folder on disk.

The embedded --self-test mode proves the gate's detection logic works on synthetic
fixtures. This test suite instead runs the gate against the REAL repo checkout to
prove the fix holds in production, plus demonstrates the mutation property: the
test proves that if the old phantom entries were re-introduced, the gate catches
them, and a clean checkout passes.

Run:
    python3 scripts/tests/test-wave-list-integrity.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(THIS_DIR, "..", ".."))
GATE_SCRIPT = os.path.join(REPO_ROOT, "scripts", "qc-assert-wave-list-integrity.py")
LIB_FILE = os.path.join(REPO_ROOT, "lib-onboarding-state.sh")
WATCHDOG_FILE = os.path.join(REPO_ROOT, "scripts", "watchdog-onboarding-loop.sh")


def _gate(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, GATE_SCRIPT] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or REPO_ROOT)


class TestWaveListIntegrity(unittest.TestCase):
    """Integration tests against the real repo checkout."""

    def test_clean_repo_returns_0(self) -> None:
        proc = _gate()
        if proc.returncode != 0:
            self.fail(f"exit {proc.returncode}:\n{proc.stdout}")
        self.assertIn("WAVE-LIST INTEGRITY: PASS", proc.stdout)

    def test_self_test_returns_0(self) -> None:
        proc = _gate("--self-test")
        if proc.returncode != 0:
            self.fail(f"exit {proc.returncode}:\n{proc.stdout}")
        self.assertIn("SELF-TEST: PASS", proc.stdout)

    def test_all_selftest_cases_pass(self) -> None:
        cases = [
            "clean lists pass",
            "PHANTOM entry (listed skill has no folder at all) fails",
            "ARCHIVE-DRIFT entry (folder renamed to -ARCHIVED) fails",
            "entry naming an -ARCHIVED folder directly fails",
            "duplicate entry across waves fails",
            "PHANTOM entry in the new Wave 6 fails",
            "watchdog re-typing a wave list (second copy) fails",
            "watchdog re-typing a list that MATCHES canonical still fails",
            "watchdog roster not bound to OC_WAVE<N>_SKILLS fails",
        ]
        proc = _gate("--self-test")
        for case in cases:
            self.assertIn(case, proc.stdout, f"Missing: {case}")

    def test_wave_counts_are_stable(self) -> None:
        proc = _gate()
        self.assertIn("across 6 waves", proc.stdout)

    def test_no_archived_skills_in_wave_lists(self) -> None:
        proc = _gate()
        self.assertNotIn("ARCHIVED", proc.stdout)

    def test_no_phantom_entries(self) -> None:
        proc = _gate()
        fail_lines = [l for l in proc.stdout.splitlines() if "  ✗" in l]
        self.assertEqual([], fail_lines, f"Unexpected failures:\n" + "\n".join(fail_lines))

    def test_lib_file_parseable(self) -> None:
        self.assertTrue(os.path.isfile(LIB_FILE), f"{LIB_FILE} not found")

    def test_watchdog_file_parseable(self) -> None:
        self.assertTrue(os.path.isfile(WATCHDOG_FILE), f"{WATCHDOG_FILE} not found")


class TestWaveListMutantDetection(unittest.TestCase):
    """Mutation test: proves the gate FAILS when archived skills are
    re-inserted into wave lists."""

    def setUp(self) -> None:
        import shutil
        import tempfile
        import re

        self._tmpdir = tempfile.mkdtemp(prefix="u101-mutation-")
        self._gate_copy = os.path.join(self._tmpdir, "qc-assert-wave-list-integrity.py")
        shutil.copy2(GATE_SCRIPT, self._gate_copy)

        with open(LIB_FILE) as fh:
            text = fh.read()

        mutated_w2 = 'OC_WAVE2_SKILLS="03-agent-browser 04-superpowers 05-ghl-setup 06-ghl-install-pages 07-kie-setup 08-vercel-setup 09-context7 10-github-setup 11-superdesign 12-openrouter-setup 14-google-workspace-integration 63-agnes-image"'
        orig_w2 = re.search(r'^OC_WAVE2_SKILLS="[^"]*"', text, re.MULTILINE)
        self.assertIsNotNone(orig_w2)
        text = text[:orig_w2.start()] + mutated_w2 + text[orig_w2.end():]

        mutated_w3 = 'OC_WAVE3_SKILLS="15-blackceo-team-management 16-summarize-youtube 17-self-improving-agent 18-proactive-agent 19-humanizer 20-youtube-watcher 21-tavily-search 24-storyboard-writer 25-video-creator 26-caption-creator 27-video-editor 28-cinematic-forge 29-ghl-convert-and-flow 30-fish-audio-api-reference 64-agnes-video 43-graphify-knowledge-graph"'
        orig_w3 = re.search(r'^OC_WAVE3_SKILLS="[^"]*"', text, re.MULTILINE)
        self.assertIsNotNone(orig_w3)
        text = text[:orig_w3.start()] + mutated_w3 + text[orig_w3.end():]

        self._lib_mutant = os.path.join(self._tmpdir, "lib-onboarding-state.sh")
        with open(self._lib_mutant, "w") as fh:
            fh.write(text)

        self._scripts_dir = os.path.join(self._tmpdir, "scripts")
        os.makedirs(self._scripts_dir, exist_ok=True)
        shutil.copy2(WATCHDOG_FILE, os.path.join(self._scripts_dir, "watchdog-onboarding-loop.sh"))

        for d in [
            "11-superdesign-ARCHIVED", "21-tavily-search-ARCHIVED",
            "03-agent-browser", "04-superpowers", "05-ghl-setup",
            "06-ghl-install-pages", "07-kie-setup", "08-vercel-setup",
            "09-context7", "10-github-setup", "12-openrouter-setup",
            "14-google-workspace-integration", "63-agnes-image",
            "15-blackceo-team-management", "16-summarize-youtube",
            "17-self-improving-agent", "18-proactive-agent", "19-humanizer",
            "20-youtube-watcher", "24-storyboard-writer", "25-video-creator",
            "26-caption-creator", "27-video-editor", "28-cinematic-forge",
            "29-ghl-convert-and-flow", "30-fish-audio-api-reference",
            "64-agnes-video", "43-graphify-knowledge-graph",
            "01-teach-yourself-protocol", "02-back-yourself-up-protocol",
            "31-upgraded-memory-system", "36-ghl-mcp-setup",
            "44-convert-and-flow-operator", "45-design-intelligence-library",
            "47-movie-producer", "48-facebook-ad-generator",
            "49-signature-funnel", "50-email-engine", "51-signature-presentation",
            "52-avatar-alchemist", "53-book-writer", "54-anthology-writer",
            "55-product-bio", "56-sales-page-assets", "57-social-media-in-a-box",
            "22-book-to-persona-coaching-leadership-system",
            "23-ai-workforce-blueprint", "32-command-center-setup",
            "35-social-media-planner",
        ]:
            os.makedirs(os.path.join(self._tmpdir, d), exist_ok=True)

    def test_mutant_is_detected(self) -> None:
        proc = subprocess.run(
            [sys.executable, self._gate_copy, "--root", self._tmpdir],
            capture_output=True, text=True,
        )
        self.assertNotEqual(0, proc.returncode, "Mutant not detected!")
        self.assertIn("ARCHIVED", proc.stdout)
        self.assertIn("11-superdesign", proc.stdout)
        self.assertIn("21-tavily-search", proc.stdout)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)


class TestGateSyntax(unittest.TestCase):
    """Syntax and import checks."""

    def test_gate_script_compiles(self) -> None:
        with open(GATE_SCRIPT) as fh:
            compile(fh.read(), GATE_SCRIPT, "exec")

    def test_lib_file_syntax(self) -> None:
        proc = subprocess.run(["bash", "-n", LIB_FILE], capture_output=True, text=True)
        if proc.returncode != 0:
            self.fail(f"bash -n: {proc.stderr}")

    def test_watchdog_file_syntax(self) -> None:
        proc = subprocess.run(["bash", "-n", WATCHDOG_FILE], capture_output=True, text=True)
        if proc.returncode != 0:
            self.fail(f"bash -n: {proc.stderr}")


if __name__ == "__main__":
    unittest.main()
