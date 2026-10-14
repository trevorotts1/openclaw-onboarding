#!/usr/bin/env python3
"""Order C3 + C4 tests: validate_public_copy.py leak patterns and
validate_prompt.py anatomy/padding/grade-block enforcement.

C3 probe (from skill-audit §5): a file carrying data-section="Section 2 / P01",
aria-label="Big Bold Pain 1", <h2>The Big Bold Claim</h2>,
<!-- HANDOFF NOTE - NOT FOR PUBLICATION -->, alt="IMG-07 hero", [EVENT_DATE]
must FAIL naming every reason; plain public copy must PASS.
"""
import json
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
    """prompt_good.txt with the Signature Grade Block removed."""
    good = Path(GOOD_PROMPT).read_text(encoding="utf-8")
    grade = Path(GRADE_BLOCK).read_text(encoding="utf-8").rstrip("\n")
    assert grade in good
    out = Path(tmpdir) / "prompt_no_grade.txt"
    out.write_text(good.replace(grade, ""), encoding="utf-8")
    return str(out), grade


def build_no_negative_prompt(tmpdir):
    """prompt_good.txt with its Do-not statements replaced by two vague lines."""
    good = Path(GOOD_PROMPT).read_text(encoding="utf-8")
    cut = good.index("\nDo not produce flat")
    out = Path(tmpdir) / "prompt_no_negative.txt"
    out.write_text(good[:cut] + "\nAvoid dull colors. Keep it vivid.\n",
                   encoding="utf-8")
    return str(out)


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
        proc = run(PROMPT_SCRIPT, build_no_negative_prompt(self.tmp))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("negative block", proc.stdout)


_SYL = ["ba", "ko", "ri", "mu", "te", "sa", "no", "vi",
        "la", "pe", "do", "xu", "fi", "ga", "hu", "ze"]


def _gword(n):
    a, b, c = n % 16, (n // 16) % 16, (n // 256) % 16
    return _SYL[a] + _SYL[b] + _SYL[c] + "n"


def grow_to(text, target_chars):
    """Insert distinct art-direction sentences into Element J's prose,
    before its Do-not statements, until the text reaches target_chars.
    Every sentence carries unique generated words, so no 8-word
    sequence, 60-character substring, or vocabulary pattern repeats:
    the padding screens stay silent because, under Part C, length
    alone neither passes nor fails a prompt."""
    anchor = "\nDo not produce flat"
    head, tail = text.split(anchor, 1)
    i = 0
    while len(head) + len(tail) + 1 < target_chars:
        ws = [_gword(i * 10 + k) for k in range(10)]
        head += (f"Beat {i}: the {ws[0]} {ws[1]} beside the {ws[2]} keeps "
                 f"the {ws[3]} light specific to scene {i}, with {ws[4]} "
                 f"shadow, {ws[5]} air, {ws[6]} texture on the {ws[7]} "
                 f"wall, and {ws[8]} {ws[9]} detail.\n")
        i += 1
    return head + anchor + tail


SMALL_COMPLETE = """ASSET: editorial photograph | BAND: visual_long. One standalone scene image for the page.
SUBJECT + SCENE: One woman at one dining table at one interrupted moment, the room lived-in and plausible.
COMPOSITION GRID: Subject in the middle-right zone; text-safe zone upper-left; crop-safe margins of 5-10 percent.
STYLE BLOCK: One locked creative direction governs this page and no second family is imported anywhere.
TYPOGRAPHY + VERBATIM COPY: No text, no letters, no words anywhere in the image.
LIGHTING + COLOR GRADE: One motivated window key, gentle fill, protected highlights, deliberate grade.
PEOPLE / REPRESENTATION: One fictional adult, believable hands, natural unperformed expression, honest posture.
LOGO / REFERENCE DIRECTIVE: No logo is approximated on any surface; references are style-only here.
TECHNICAL: One independent master image; save the unmodified master file under its recorded name.
NEGATIVE BLOCK:
Do not produce flat, muted, pastel, desaturated, or low-contrast color.
Do not distort hands, eyes, or teeth.
Do not render any text, letters, or words anywhere in the image.
Do not invent or mutate any brand logo.
Do not render placeholder blocks or lorem text.
Do not add any watermark, caption, or badge.
"""


class TestPartCBudget(unittest.TestCase):
    """Amendment 6 Part C: element completeness governs; length is
    telemetry; the enforcer's 95-to-100 percent band and 80 percent
    floor are withdrawn (the old test_rule_12_length_band encoded that
    withdrawn design and is replaced by this class)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="partc-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.base = Path(GOOD_PROMPT).read_text(encoding="utf-8")

    def _write(self, name, text):
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_no_length_floor_at_79_percent(self):
        path = self._write("p79.txt", grow_to(self.base, 15800))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("ADD", proc.stdout)
        self.assertNotIn("CUT", proc.stdout)

    def test_overflow_warns_only_for_not_published_cap(self):
        path = self._write("p103.txt", grow_to(self.base, 20600))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("warns only", proc.stdout)

    def test_verified_cap_fails_closed(self):
        policy = {"models": [{"match": "gpt-image-2-5", "max_chars": 5000,
                              "cap_status": "VERIFIED", "unit": "chars"}],
                  "default": {"max_chars": None, "cap_status": "UNKNOWN",
                              "unit": "chars"},
                  "tripwire_chars": 2000}
        policy_path = self._write("policy.json", json.dumps(policy))
        proc = run(PROMPT_SCRIPT, "--policy", policy_path, GOOD_PROMPT)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("VERIFIED", proc.stdout)

    def test_tripwire_flags_short_complete_prompt_without_failing(self):
        path = self._write("small.txt", SMALL_COMPLETE)
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("TRIPWIRE", proc.stdout)

    def test_9500_char_complete_prompt_passes_as_telemetry(self):
        path = self._write("p9500.txt", grow_to(self.base, 9500))
        proc = run(PROMPT_SCRIPT, "--json", path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["errors"], [])
        chars = data["telemetry"]["characters"]
        self.assertGreaterEqual(chars, 9400)
        self.assertAlmostEqual(data["telemetry"]["percent_of_max"],
                               round(100.0 * chars / 20000, 2), delta=0.2)

    def test_padded_prompt_fails_on_padding_not_length(self):
        anchor = "\nDo not produce flat"
        head, tail = self.base.split(anchor, 1)
        padded = head + ("The same generic sentence about beautiful light "
                         "and nice colors repeated without any new "
                         "direction. " * 120) + anchor + tail
        path = self._write("padded.txt", padded)
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Padding detected", proc.stdout)


if __name__ == "__main__":
    unittest.main()
