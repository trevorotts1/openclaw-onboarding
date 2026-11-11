#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_review_pending_scan.py - issue 30 acceptance: no wrapper or consumer result
hardcodes independent_review False without the REVIEW-PENDING blocker beside it.

Scans every non-test Python source in Skill 49 (the role wrappers, the five
adapters, dispatch's simulated executor AND the consumer source embedded in its
self-test string, the receipt collector) for a literal independent_review set to
False. Each hit must carry REVIEW-PENDING in the same literal, or sit beside
apply_review(), which appends it for every result that lacks an accepted record.

Run: python3 test_review_pending_scan.py [-v]
"""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
# independent_review False as a dict key ("k": False / 'k':False), a keyword
# (k=False) or an item assignment (["k"] = False); comparisons and prose do not match.
HARDCODED_FALSE = re.compile(r"""independent_review["']?\]?\s*[:=]\s*False\b""")
BESIDE = re.compile(r"REVIEW-PENDING|REVIEW_PENDING|apply_review\(")
WINDOW = 12  # lines either side: a result literal and the call that completes it


# The one deliberate exclusion: a tamper fixture whose bare False and empty blockers are the forgery
# the selection wrapper must refuse (used by tests/test_selection_wrapper.py case D).
TAMPER_FIXTURE = "tampered_emitter.py"
# The offline fixture runner of Skill 83 emits piece results too; it must carry the blocker.
LAUNCHER_FIXTURES = SKILL.parent / "83-black-friday-launcher" / "fixtures" / "run_fixtures.py"


def emitters():
    for path in sorted(SKILL.rglob("*.py")):
        if path.name.startswith("test_") or path.name == TAMPER_FIXTURE:
            continue
        yield path


def unguarded(lines):
    """Line numbers of independent_review False hits with no REVIEW-PENDING beside them."""
    bad = []
    for i, line in enumerate(lines):
        if HARDCODED_FALSE.search(line):
            # a comment naming REVIEW-PENDING is not the blocker: strip them
            near = "\n".join(re.sub(r"\s#.*", "", ln)
                             for ln in lines[max(0, i - WINDOW): i + WINDOW + 1])
            if not BESIDE.search(near):
                bad.append(i + 1)
    return bad


class EveryUnreviewedResultCarriesReviewPending(unittest.TestCase):
    def test_the_scan_reads_the_known_emitters(self):
        names = {p.name for p in emitters()}
        for need in ("dispatch_launch.py", "role_wrappers.py", "checkout_wrapper.py",
                     "downsell_wrapper.py", "translate_thank_you_result.py",
                     "collect_launch_receipts.py"):
            self.assertIn(need, names)
        hits = sum(1 for p in emitters()
                   for ln in p.read_text(encoding="utf-8").splitlines()
                   if HARDCODED_FALSE.search(ln))
        self.assertGreaterEqual(hits, 9, "the scan is not seeing the emit sites")

    def test_no_emitter_hardcodes_the_false_flag_bare(self):
        for path in emitters():
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(unguarded(lines), [],
                             f"{path.relative_to(SKILL)}: independent_review False "
                             "with no REVIEW-PENDING blocker beside it")

    def test_the_tamper_fixture_is_the_only_exclusion_and_stays_bare(self):
        fixtures = [p for p in SKILL.rglob("*.py") if "fixtures" in p.relative_to(SKILL).parts]
        self.assertEqual([p.name for p in fixtures], [TAMPER_FIXTURE])
        self.assertNotIn(TAMPER_FIXTURE, {p.name for p in emitters()})
        lines = fixtures[0].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(unguarded(lines)), 1, "the tamper fixture is bare on purpose")
        self.assertTrue(any("Deliberate tamper fixture" in ln for ln in lines))

    def test_the_83_offline_fixture_results_carry_the_blocker(self):
        lines = LAUNCHER_FIXTURES.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(HARDCODED_FALSE.search(ln) for ln in lines),
                        "the scan is not seeing the fixture runner's emit site")
        self.assertEqual(unguarded(lines), [],
                         "83 run_fixtures.py: independent_review False with no REVIEW-PENDING blocker beside it")

    def test_the_self_test_consumer_string_carries_the_blocker(self):
        text = (SKILL / "scripts" / "dispatch_launch.py").read_text(encoding="utf-8")
        m = re.search(r"'independent_review':False,(?:[^\n]*\n){2}", text)
        self.assertIsNotNone(m, "self-test consumer string not found")
        self.assertIn("REVIEW-PENDING", m.group(0))

    def test_the_scanner_itself_flags_a_bare_flag(self):
        self.assertEqual(unguarded(['"independent_review": False, "blockers": []']), [1])
        self.assertEqual(unguarded(["'independent_review':False,'blockers':[]"]), [1])
        self.assertEqual(unguarded(["r = dict(independent_review=False)"]), [1])
        self.assertEqual(unguarded(['"independent_review": False,',
                                    '"blockers": ["REVIEW-PENDING: x"]']), [])
        self.assertEqual(unguarded(['"independent_review": False,', "apply_review(r)"]), [])
        self.assertEqual(unguarded(['"independent_review": False,',
                                    "x = 1  # REVIEW-PENDING is added elsewhere"]), [1])


if __name__ == "__main__":
    unittest.main()
