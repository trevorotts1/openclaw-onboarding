#!/usr/bin/env python3
"""U-GEN321 (S75-018, audit row C10): the Resilia study requirements are MISSING.

The delivered Resilia study requirements document is outside this repository.
Nothing here integrates it, and nothing here said so: this test pins the one
thing the unit added - a prerequisite entry that names the requirement MISSING
and points at the only record of it in the tree.

It must fail where that entry is absent.

The entry can never be severity "required": scripts/qc-prereqs-json.sh Rule 16c
forces type "manual" to "optional" so an unverifiable requirement cannot hide
behind a check that can never fail. That asymmetry is the decision this test
pins; it is not an accident.

Run: python3 scripts/core/intake_preflight/test_prereqs_study_requirements.py
stdlib only, no network, no provider, no writes.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                            # preflight.py
sys.path.insert(0, os.path.dirname(HERE))           # core/

import preflight as P         # noqa: E402  (package under test)

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MANIFEST = os.path.join(SKILL, "PREREQS.json")
EVIDENCE = "evidence/SKILL75/SKILL75-65-ITEM-STATUS-2026-10-31.txt"


def _entries():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)["prerequisites"]


class StudyRequirementsAreNamedMissing(unittest.TestCase):
    def test_prereqs_name_the_study_requirements_as_missing(self):
        found = [e for e in _entries()
                 if "study requirements" in (e.get("label") or "").lower()]
        self.assertEqual(len(found), 1, "expected exactly one study-requirements entry")
        entry = found[0]
        self.assertIn("MISSING", entry["label"],
                      "the entry must say MISSING in the text a prereq check prints")

    def test_the_entry_states_the_shape_the_lint_allows(self):
        entry = [e for e in _entries()
                 if e.get("id") == "resilia-study-requirements"][0]
        self.assertEqual((entry["type"], entry["severity"]), ("manual", "optional"),
                         "Rule 16c: type manual is the only home for an unverifiable "
                         "requirement, and it is forced optional - it is stated, never enforced")

    def test_the_entry_is_naming_only(self):
        entry = [e for e in _entries()
                 if e.get("id") == "resilia-study-requirements"][0]
        readers = {"envVar", "binary", "skill", "skillId", "stateFile", "module",
                   "jsonPath", "server"} & set(entry["check"])
        self.assertEqual(readers, set(),
                         "naming only: no check may read the document (or invent a path to it)")
        self.assertIn(EVIDENCE, entry["check"]["note"],
                      "the note must name where the only record of it lives")

    def test_the_runs_own_reader_sees_the_entry(self):
        manifest = P.load_manifest()
        ids = {e.get("id") for e in manifest.get("prerequisites") or []}
        self.assertIn("resilia-study-requirements", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
