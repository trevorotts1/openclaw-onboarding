#!/usr/bin/env python3
"""F14 / SPEC C6 / conflict C9 tests: method rows with evidence levels.

Done-when cases from BUILD-PLAN W1-method-qc-U1 (Prove line):
  1. a full fixture -> every applicable row, each carrying exactly
     {verdict, evidence_level, evidence} with a real evidence level;
  2. a missing song gate record -> ERM_DROP is UNAVAILABLE / planned
     (never PASS, never inspected);
  3. a waived storyboard -> the row reads "checked, client waived approval",
     never "approved".

Plus the two honesty laws the row states (SPEC C6 / method 11.3): UNAVAILABLE
is never PASS, and "approved" only with a recorded human answer. A run with
no control/method.json returns None (inert until wired).

stdlib only, no network, no provider call, no operator path: every run is a
fresh tempdir.

Run: python3 core/delivery_checklist/test_method_rows.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_checklist.delivery_checklist as dc  # noqa: E402

#: Every row the method adds, with the purposes that can produce it.
ALL_ROWS = tuple(row for row, _ in dc.METHOD_ROWS)
UNIVERSAL = tuple(row for row, purposes in dc.METHOD_ROWS
                  if purposes is None)
PURPOSE_ROWS = {row: purposes for row, purposes in dc.METHOD_ROWS
                if purposes is not None}
ROW_KEYS = {"verdict", "evidence_level", "evidence"}

FULL_GATES = {
    "ERM_DROP": {"verdict": "PASS", "evidence_level": "inspected",
                 "evidence": "first sung word 15.4 s vs ERM apex 15.0 s"},
    "HERO_SHIFT": {"verdict": "PASS", "evidence_level": "inspected",
                   "evidence": "second seam measured at 38.0 s"},
    "EARNED_HOOK": {"verdict": "PASS", "evidence_level": "inspected",
                    "evidence": "hook lands after the breakthrough at 41.5 s"},
    "TRANSFORMATION_LOCK": {"verdict": "PASS", "evidence_level": "approved",
                            "approval_answer": "yes",
                            "evidence": "client approved the storyboard"},
    "TRAILER_PURPOSE": {"verdict": "PASS", "evidence_level": "inspected",
                        "evidence": "trailer ends on the channel destination"},
    "CLAIMS_PERMISSION": {"verdict": "PASS", "evidence_level": "approved",
                          "approval_answer": "yes",
                          "evidence": "permission yes recorded at the card"},
    "LESSON_LINK": {"verdict": "PASS", "evidence_level": "inspected",
                    "evidence": "recap + next step link opened and checked"},
    "PLATFORM_FIT": {"verdict": "FLAG", "evidence_level": "inspected",
                     "evidence": "58 s 9:16 vs Instagram Reels ad, 60 s"},
}
PURPOSES = ("campaign", "testimonial", "lesson", "paid_ad", "short_post")


def make_run(purpose, gates=None, method_extra=None, with_method=True):
    """A throwaway run dir carrying control/method.json and its gate rows."""
    root = Path(tempfile.mkdtemp(prefix="agn-method-rows-"))
    control = root / "control"
    control.mkdir(parents=True)
    if with_method:
        method = {"purpose": purpose, "platform": None,
                  "output_types": [], "chosen_length_s": 60,
                  "gates": {"A": "planned"}}
        if method_extra:
            method.update(method_extra)
        (control / "method.json").write_text(
            json.dumps(method, indent=2), encoding="utf-8")
    for name, rec in (gates or {}).items():
        folder = control / dc.METHOD_GATES_DIR.split("/", 1)[1]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ("%s.json" % name)).write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
    return root


class MethodRowsTest(unittest.TestCase):
    def tearDown(self):
        for path in getattr(self, "_runs", []):
            shutil.rmtree(path, ignore_errors=True)

    def run_fixture(self, purpose, **kw):
        root = make_run(purpose, **kw)
        self._runs = getattr(self, "_runs", []) + [root]
        return dc.measure_method(root)

    # ---- 1. full fixture -> every applicable row, with a real level ------
    def test_full_fixture_every_row_has_an_evidence_level(self):
        seen = set()
        for purpose in PURPOSES:
            rows = self.run_fixture(purpose, gates=FULL_GATES)
            self.assertIsInstance(rows, dict)
            self.assertTrue(rows, "%s produced no rows" % purpose)
            for name, row in rows.items():
                self.assertEqual(set(row), ROW_KEYS, name)
                self.assertIn(row["evidence_level"],
                              dc.METHOD_EVIDENCE_LEVELS, name)
                self.assertTrue(row["evidence"].strip(), name)
                self.assertIn(row["verdict"],
                              dc.METHOD_VERDICTS + (dc.METHOD_WAIVED,),
                              "%s/%s" % (purpose, name))
                seen.add(name)
        self.assertEqual(seen, set(ALL_ROWS),
                         "every method row must appear somewhere")

    def test_rows_scoped_to_their_purpose(self):
        for name, purposes in PURPOSE_ROWS.items():
            for purpose in PURPOSES:
                rows = self.run_fixture(purpose, gates=FULL_GATES)
                self.assertEqual(name in rows, purpose in purposes,
                                 "%s on %s" % (name, purpose))
        for name in UNIVERSAL:
            rows = self.run_fixture("paid_ad", gates=FULL_GATES)
            self.assertIn(name, rows)

    # ---- 2. a missing song gate record ----------------------------------
    def test_missing_song_gate_record_is_unavailable_planned(self):
        gates = {k: v for k, v in FULL_GATES.items()
                 if k != "ERM_DROP"}
        rows = self.run_fixture("campaign", gates=gates)
        self.assertEqual(rows["ERM_DROP"]["verdict"], "UNAVAILABLE")
        self.assertEqual(rows["ERM_DROP"]["evidence_level"], "planned")
        self.assertIn("control/gates/ERM_DROP.json",
                      rows["ERM_DROP"]["evidence"])
        # the rows that DO have a record keep their own level
        self.assertEqual(rows["HERO_SHIFT"]["evidence_level"], "inspected")

    def test_every_missing_record_is_planned_never_inspected(self):
        rows = self.run_fixture("campaign", gates={})
        self.assertEqual(tuple(rows), ALL_ROWS[:5])
        for name, row in rows.items():
            self.assertEqual(row["evidence_level"], "planned", name)
            self.assertEqual(row["verdict"], "UNAVAILABLE", name)

    # ---- 3. a waived storyboard -----------------------------------------
    def test_waived_storyboard_reads_waived_approval(self):
        gates = dict(FULL_GATES)
        gates["TRANSFORMATION_LOCK"] = {
            "verdict": "PASS", "evidence_level": "approved",
            "approval_answer": "waived",
            "evidence": "client chose: No, just make it"}
        rows = self.run_fixture("campaign", gates=gates)
        row = rows["TRANSFORMATION_LOCK"]
        self.assertEqual(row["verdict"], "checked, client waived approval")
        self.assertEqual(row["evidence_level"], "inspected")

    def test_waiver_still_fails_when_the_check_failed(self):
        gates = dict(FULL_GATES)
        gates["TRANSFORMATION_LOCK"] = {
            "verdict": "FAIL", "evidence_level": "inspected",
            "approval_answer": "waived",
            "evidence": "cape-on shot after the breakthrough"}
        rows = self.run_fixture("campaign", gates=gates)
        self.assertEqual(rows["TRANSFORMATION_LOCK"]["verdict"], "FAIL")

    # ---- the two honesty laws -------------------------------------------
    def test_unavailable_is_never_pass(self):
        gates = dict(FULL_GATES)
        gates["ERM_DROP"] = {"verdict": "PASS", "evidence_level": "planned",
                             "evidence": "the prompt asked for the drop"}
        rows = self.run_fixture("campaign", gates=gates)
        self.assertEqual(rows["ERM_DROP"]["verdict"], "UNAVAILABLE")
        self.assertEqual(rows["ERM_DROP"]["evidence_level"], "planned")

    def test_approved_needs_a_recorded_human_answer(self):
        gates = dict(FULL_GATES)
        gates["TRANSFORMATION_LOCK"] = {
            "verdict": "PASS", "evidence_level": "approved",
            "evidence": "the storyboard prompt asked for a cape-off"}
        rows = self.run_fixture("campaign", gates=gates)
        row = rows["TRANSFORMATION_LOCK"]
        self.assertNotEqual(row["evidence_level"], "approved")
        self.assertNotEqual(row["verdict"], "PASS")

    def test_generated_is_never_a_pass(self):
        gates = dict(FULL_GATES)
        gates["LESSON_LINK"] = {"verdict": "PASS",
                                "evidence_level": "generated",
                                "artifact": "03 - Ready-to-Post Kit",
                                "evidence": "kit built, not opened"}
        rows = self.run_fixture("lesson", gates=gates)
        row = rows["LESSON_LINK"]
        self.assertEqual(row["evidence_level"], "generated")
        self.assertEqual(row["verdict"], "UNAVAILABLE")

    def test_measurement_without_a_declared_level_is_inspected(self):
        gates = dict(FULL_GATES)
        gates["ERM_DROP"] = {"verdict": "PASS",
                             "measurement": "first sung word 15.4 s"}
        rows = self.run_fixture("campaign", gates=gates)
        self.assertEqual(rows["ERM_DROP"]["evidence_level"], "inspected")
        self.assertEqual(rows["ERM_DROP"]["verdict"], "PASS")

    # ---- SPEC B1: the permission answer the card already writes ----------
    def test_claim_permission_reads_the_card_answer(self):
        rows = self.run_fixture(
            "testimonial", gates={},
            method_extra={"testimonial_permission": "yes"})
        self.assertEqual(rows["CLAIMS_PERMISSION"]["verdict"], "PASS")
        self.assertEqual(rows["CLAIMS_PERMISSION"]["evidence_level"],
                         "approved")

    # ---- inert until wired -----------------------------------------------
    def test_run_without_method_json_is_inert(self):
        root = make_run("campaign", with_method=False)
        self._runs = getattr(self, "_runs", []) + [root]
        self.assertIsNone(dc.measure_method(root))

    def test_method_json_that_is_not_an_object_is_inert(self):
        root = make_run("campaign", with_method=False)
        self._runs = getattr(self, "_runs", []) + [root]
        (root / "control" / "method.json").write_text(
            json.dumps(["campaign"]), encoding="utf-8")
        self.assertIsNone(dc.measure_method(root))


if __name__ == "__main__":
    unittest.main()
