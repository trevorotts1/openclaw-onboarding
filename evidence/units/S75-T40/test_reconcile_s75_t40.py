#!/usr/bin/env python3
"""Focused checks for S75-T40 / S75-A40 reconciliation. Stdlib only, python3 -I.

Positive case runs against the live census READ-ONLY. Negative cases prove the
checker discriminates: a 40-unit census, a duplicated acceptance row and a
shrunken weight sum must all be refused.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.environ.get("S75_LEDGER", "/Users/blackceomacmini/loop-control/s75/ledger.json")
AUTHORITY = os.environ.get(
    "S75_AUTHORITY",
    "/Volumes/mac mini m4/Downloads/git trees and automations/"
    "S75_Story_First_Full_Cast_Build_20261024/task-ledger.json",
)


def _load_module():
    path = os.path.join(HERE, "reconcile.py")
    spec = importlib.util.spec_from_file_location("s75_t40_reconcile", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load_module()


def _ledger():
    with open(LEDGER, "rb") as fh:
        return json.load(fh)


def _authority():
    with open(AUTHORITY, "rb") as fh:
        return json.load(fh)


def _failing(ledger_doc, authority_doc):
    c = R.census(ledger_doc, authority_doc)
    return [ch["id"] for ch in R.checks(c) if not ch["ok"]]


class TestLiveCensus(unittest.TestCase):
    def test_live_census_reconciles(self):
        c = R.census(_ledger(), _authority())
        self.assertEqual(41, c["ledger_units"])
        self.assertEqual(41, c["ledger_weight_sum"])
        self.assertEqual(41, c["acceptance_rows_unique"])
        failed = R.checks(c)
        self.assertEqual([], [ch["id"] for ch in failed if not ch["ok"]],
                         "failing checks: %s" % [ch["id"] for ch in failed if not ch["ok"]])

    def test_declared_denominators_are_intact(self):
        c = R.census(_ledger(), _authority())
        self.assertEqual(41, c["declared_denominators"]["built"])
        self.assertEqual(41, c["declared_denominators"]["build_accepted"])
        self.assertEqual(2, c["declared_denominators"]["merged_required_targets"])


class TestNegativeControls(unittest.TestCase):
    def test_shrunken_census_is_refused(self):
        led = copy.deepcopy(_ledger())
        led["units"] = led["units"][:40]
        failed = _failing(led, _authority())
        self.assertIn("census.unit_count", failed)
        self.assertIn("census.denominator_weight", failed)

    def test_duplicated_acceptance_row_is_refused(self):
        led = copy.deepcopy(_ledger())
        led["units"][1]["acceptance_row"] = led["units"][0]["acceptance_row"]
        failed = _failing(led, _authority())
        self.assertIn("census.acceptance_rows_unique", failed)

    def test_weight_dropped_is_refused(self):
        led = copy.deepcopy(_ledger())
        led["units"][0]["weight"] = 0
        failed = _failing(led, _authority())
        self.assertIn("census.denominator_weight", failed)
        self.assertIn("census.unit_weight_is_one", failed)

    def test_missing_authority_unit_is_refused(self):
        auth = copy.deepcopy(_authority())
        auth["tasks"] = auth["tasks"][:40]
        failed = _failing(_ledger(), auth)
        self.assertIn("authority.unit_set_equal", failed)

    def test_shrunk_declared_denominator_is_refused(self):
        auth = copy.deepcopy(_authority())
        auth["counters"]["build_accepted"]["denominator"] = 40
        failed = _failing(_ledger(), auth)
        self.assertIn("denominator.not_shrunk", failed)


class TestTargetChecks(unittest.TestCase):
    def test_one_target_is_not_two(self):
        failed = [ch["id"] for ch in R.target_checks([{"revision_is_40hex": True}]) if not ch["ok"]]
        self.assertIn("targets.count", failed)

    def test_two_exact_revisions_pass(self):
        targets = [{"revision_is_40hex": True}, {"revision_is_40hex": True}]
        self.assertEqual([], [ch["id"] for ch in R.target_checks(targets) if not ch["ok"]])

    def test_unresolved_revision_fails(self):
        targets = [{"revision_is_40hex": True}, {"revision_is_40hex": False}]
        failed = [ch["id"] for ch in R.target_checks(targets) if not ch["ok"]]
        self.assertIn("targets.exact_revision", failed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
