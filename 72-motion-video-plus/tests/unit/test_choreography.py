"""Choreography policy tests for MG-019 (meaning-first motion grammar).

The fixtures under tests/fixtures/choreography are legacy-format scene
files run through scripts/lint-grammar.py. The four acceptance shapes from
the MG-019 spec must pass: a linear chart, a controlled dissolve, a stable
presenter hold, and a genuine depth scene. The failure fixtures isolate
one policy each: spring overshoot on data marks (MG-015), an
everything-at-once scene over the coherence cap, and effects with no
declared intent.

The vocabulary tests keep references/choreography-vocabulary.json and
references/motion-grammar.md in sync: the grammar document is the human
source, the JSON is its machine-readable mirror, and this suite fails
when their intent or behavior lists drift apart.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
LINTER = SKILL_ROOT / "scripts" / "lint-grammar.py"
VOCABULARY_PATH = SKILL_ROOT / "references" / "choreography-vocabulary.json"
GRAMMAR_PATH = SKILL_ROOT / "references" / "motion-grammar.md"
FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "choreography"

PASS_FIXTURES = (
    "pass-linear-chart.html",
    "pass-dissolve.html",
    "pass-presenter-hold.html",
    "pass-depth.html",
)

FAIL_FIXTURES = {
    "fail-data-overshoot.html": "choreography-data-overshoot",
    "fail-everything-at-once.html": "choreography-incoherent",
    "fail-no-intent.html": "choreography-undeclared",
}


def run_linter(fixture: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINTER), str(FIXTURES / fixture)],
        capture_output=True, text=True)


def _section(text: str, heading: str) -> str:
    """Return the markdown under a '## heading' up to the next '## '."""
    m = re.search(r"^## " + re.escape(heading) + r"\s*$", text, re.M)
    if not m:
        raise AssertionError("grammar document has no section: %s" % heading)
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def _table_ids(section: str) -> set:
    return set(re.findall(r"^\|\s*`([a-z_]+)`", section, re.M))


class PassingFixtureTests(unittest.TestCase):
    def test_acceptance_shapes_pass_the_linter(self):
        for name in PASS_FIXTURES:
            with self.subTest(fixture=name):
                proc = run_linter(name)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                self.assertIn("grammar lint clean", proc.stdout)


class FailingFixtureTests(unittest.TestCase):
    def test_failure_fixtures_fail_with_their_policy_id(self):
        for name, violation in FAIL_FIXTURES.items():
            with self.subTest(fixture=name):
                proc = run_linter(name)
                self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
                self.assertIn(violation, proc.stdout)

    def test_data_overshoot_also_flags_the_intent_mismatch(self):
        proc = run_linter("fail-data-overshoot.html")
        self.assertIn("choreography-behavior-not-permitted", proc.stdout)

    def test_everything_at_once_flags_off_intent_behaviors(self):
        proc = run_linter("fail-everything-at-once.html")
        self.assertIn("choreography-behavior-not-permitted", proc.stdout)

    def test_failure_fixtures_are_clean_on_legacy_determinism_checks(self):
        legacy_ids = ("css-transition", "css-animation", "timer",
                      "unseeded-random", "gpu-layer", "settime")
        for name in FAIL_FIXTURES:
            with self.subTest(fixture=name):
                proc = run_linter(name)
                for legacy in legacy_ids:
                    self.assertNotIn("[%s]" % legacy, proc.stdout,
                                     "%s must fail on choreography policy only"
                                     % name)


class VocabularyConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocab = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
        cls.grammar = GRAMMAR_PATH.read_text(encoding="utf-8")

    def test_grammar_intents_match_vocabulary(self):
        section = _section(self.grammar, "Intents")
        self.assertEqual(set(self.vocab["intents"]), _table_ids(section))

    def test_grammar_behaviors_match_vocabulary(self):
        section = _section(self.grammar, "Behaviors")
        self.assertEqual(set(self.vocab["behaviors"]), _table_ids(section))

    def test_permitted_behaviors_are_all_known(self):
        known = set(self.vocab["behaviors"])
        for intent, spec in self.vocab["intents"].items():
            with self.subTest(intent=intent):
                self.assertTrue(set(spec["permitted_behaviors"]) <= known)

    def test_coherence_numbers_match_grammar(self):
        section = _section(self.grammar, "Coherence")
        cap = self.vocab["coherence"]["max_behaviors_per_scene"]
        seq = self.vocab["coherence"]["max_distinct_behaviors_per_sequence"]
        self.assertIn("at most %d behaviors in one scene" % cap, section)
        self.assertIn("at most %d distinct behaviors" % seq, section)

    def test_data_mark_rule_present_in_both(self):
        self.assertIn("spring", self.vocab["data_marks"]["forbidden_behaviors"])
        section = _section(self.grammar, "Data marks")
        self.assertIn("spring", section)
        self.assertIn("never", section)


class LinterBoundaryTests(unittest.TestCase):
    def test_timer_detection_regex_is_the_fixed_pattern(self):
        # MG-019 pinned the shipped pattern so its policy change could
        # not silently alter detection strength; the pinned pattern was
        # itself the D-LINT-TIMER defect (set(TimeOut|Interval) misses
        # the ordinary spelling setTimeout). MG-030 owns the fix, so
        # this pin now guards the corrected pattern against regression
        # in either direction: the defect must not come back, and the
        # fix must not vanish.
        source = LINTER.read_text(encoding="utf-8")
        self.assertIn(r"\bset(Timeout|Interval)\s*\(", source)
        self.assertNotIn(r"\bset(TimeOut|Interval)\s*\(", source)


if __name__ == "__main__":
    unittest.main()
