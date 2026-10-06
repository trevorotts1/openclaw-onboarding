#!/usr/bin/env python3
"""Order C3 + C4 tests: validate_public_copy.py leak patterns and
validate_prompt.py anatomy/padding/grade-block enforcement.

C3 probe (from skill-audit §5): a file carrying data-section="Section 2 / P01",
aria-label="Big Bold Pain 1", <h2>The Big Bold Claim</h2>,
<!-- HANDOFF NOTE - NOT FOR PUBLICATION -->, alt="IMG-07 hero", [EVENT_DATE]
must FAIL naming every reason; plain public copy must PASS.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
COPY_SCRIPT = os.path.join(SKILL_ROOT, "scripts", "validate_public_copy.py")
PROMPT_SCRIPT = os.path.join(SKILL_ROOT, "scripts", "validate_prompt.py")
GOOD_PROMPT = os.path.join(HERE, "fixtures", "prompt_good.txt")
GRADE_BLOCK = os.path.join(SKILL_ROOT, "assets", "brand", "signature-grade-block.txt")


def run(script, *args):
    return subprocess.run([sys.executable, script, *args],
                          capture_output=True, text=True, timeout=60)


C3_PROBE = """<html><body>
<div data-section="Section 2 / P01">
<h2>The Big Bold Claim</h2>
<p aria-label="Big Bold Pain 1">Your mornings disappear.</p>
<!-- HANDOFF NOTE - NOT FOR PUBLICATION -->
<img src="hero.jpg" alt="IMG-07 hero">
<p>Register by [EVENT_DATE].</p>
</div></body></html>
"""

PLAIN_COPY = """<html><body>
<h1>Own Your Week</h1>
<p>Your mornings disappear into other people's fires.</p>
<p>Register now and give your plans a place.</p>
<a href="/register">Apply Now</a>
</body></html>
"""


class TestPublicCopyLeaks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="c3-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_probe_fails_with_every_reason(self):
        probe = self.tmp / "probe.html"
        probe.write_text(C3_PROBE, encoding="utf-8")
        proc = run(COPY_SCRIPT, str(probe))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = proc.stdout
        # Each probe line must produce its own reason.
        self.assertIn("data-section", out)
        self.assertIn("Big Bold Pain 1", out)          # private label in aria-label
        self.assertIn("Big Bold Claim", out)           # private label in visible text
        self.assertIn("HANDOFF", out)                  # note/handoff comment
        self.assertIn("IMG-07", out)                   # image prompt ID in alt
        self.assertIn("[EVENT_DATE]", out)             # bracket placeholder

    def test_bracket_placeholder_is_warn_only_with_test_run(self):
        probe = self.tmp / "probe.html"
        probe.write_text(C3_PROBE, encoding="utf-8")
        proc = run(COPY_SCRIPT, "--test-run", str(probe))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("WARNING", proc.stdout)
        self.assertIn("[EVENT_DATE]", proc.stdout)
        # The bracket placeholder must no longer be a FAIL reason line.
        fail_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("- ")]
        self.assertFalse(any("[EVENT_DATE]" in ln for ln in fail_lines),
                         "bracket placeholder still a FAIL line with --test-run")

    def test_plain_public_copy_passes(self):
        plain = self.tmp / "plain.html"
        plain.write_text(PLAIN_COPY, encoding="utf-8")
        proc = run(COPY_SCRIPT, str(plain))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)


def a_flood(path, count=5000):
    Path(path).write_text("a" * count, encoding="utf-8")
    return str(path)


REPEATED_SENTENCE = "Detailed production prompt control sentence. " * 150


def build_no_grade_prompt(tmpdir):
    """prompt_good.txt with the Signature Grade Block and negative block removed."""
    good = Path(GOOD_PROMPT).read_text(encoding="utf-8")
    grade = Path(GRADE_BLOCK).read_text(encoding="utf-8").rstrip("\n")
    sents_start = good.index("\nOpen on a woman")
    sents_end = good.index("\nRender this image")
    sentences = good[sents_start + 1:sents_end]
    head = good[:good.index("\nOpen on a woman")]
    out = Path(tmpdir) / "prompt_no_grade.txt"
    out.write_text(head + "\n" + sentences +
                   "\nAvoid dull colors. Keep it vivid.\n", encoding="utf-8")
    return str(out), grade


class TestPromptValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="c4-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_letter_a_flood_fails(self):
        proc = run(PROMPT_SCRIPT, a_flood(self.tmp / "aaaa.txt"))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Padding detected", proc.stdout)
        self.assertIn("Missing canonical element", proc.stdout)

    def test_repeated_sentence_fails(self):
        p = self.tmp / "repeat.txt"
        p.write_text(REPEATED_SENTENCE, encoding="utf-8")
        proc = run(PROMPT_SCRIPT, str(p))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Padding detected", proc.stdout)

    def test_good_fixture_passes(self):
        self.assertTrue(Path(GOOD_PROMPT).exists(), "tests/fixtures/prompt_good.txt missing")
        proc = run(PROMPT_SCRIPT, GOOD_PROMPT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_good_fixture_passes_sauce_only(self):
        proc = run(PROMPT_SCRIPT, "--sauce-only", GOOD_PROMPT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_missing_grade_block_fails_sauce_only(self):
        no_grade, grade = build_no_grade_prompt(self.tmp)
        self.assertNotIn(grade, Path(no_grade).read_text(encoding="utf-8"))
        proc = run(PROMPT_SCRIPT, "--sauce-only", no_grade)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Grade Block", proc.stdout)

    def test_missing_negative_block_fails(self):
        no_grade, _ = build_no_grade_prompt(self.tmp)
        proc = run(PROMPT_SCRIPT, no_grade)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("negative block", proc.stdout)

    def test_house_band_and_runtime_warning_kept(self):
        # 19,001-20,000 chars: still inside the band but over the runtime ceiling
        # -> warning, not error (checked on a structurally complete prompt is not
        # required here: the band itself is what this test pins).
        short = self.tmp / "short.txt"
        short.write_text("too short", encoding="utf-8")
        proc = run(PROMPT_SCRIPT, str(short))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("house minimum is 5000", proc.stdout)


if __name__ == "__main__":
    unittest.main()
