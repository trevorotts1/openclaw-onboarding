#!/usr/bin/env python3
"""
tests/unit/test_binding_law_applications_71_140.py
─────────────────────────────────────────────────────────────────────────────
BLD-118 — proves the binding-law application register for SCOPE-LEDGER
applications 71-140 is complete, ordered, and machine-checked, and that the
checker actually discriminates (it goes RED on a dropped, renumbered or
falsely-PRESENT row).

Run:
    python3 tests/unit/test_binding_law_applications_71_140.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REGISTER = os.path.join(ROOT, "evidence", "binding-laws", "applications-71-140.json")
CHECKER = os.path.join(ROOT, "scripts", "check-binding-law-applications.py")


def load():
    with open(REGISTER) as fh:
        return json.load(fh)


def run_checker(register_text=None):
    """Run the checker; with register_text, run it against a mutated copy."""
    if register_text is None:
        return subprocess.run([sys.executable, CHECKER], cwd=ROOT,
                              capture_output=True, text=True)
    with tempfile.TemporaryDirectory() as tmp:
        # mirror the repo layout the checker expects
        os.makedirs(os.path.join(tmp, ".github", "workflows"))
        os.makedirs(os.path.join(tmp, "49-signature-funnel", "scripts"))
        os.makedirs(os.path.join(tmp, "evidence", "binding-laws"))
        for rel in (".github/workflows/sf-prover-pin-authority.yml",
                    "49-signature-funnel/scripts/front_door.py"):
            src = os.path.join(ROOT, rel)
            dst = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, errors="replace") as fh:
                body = fh.read()
            with open(dst, "w") as fh:
                fh.write(body)
        with open(os.path.join(tmp, "evidence", "binding-laws", "applications-71-140.json"), "w") as fh:
            fh.write(register_text)
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=False)
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts",
                                                            "check-binding-law-applications.py")],
                              cwd=tmp, capture_output=True, text=True)


class TestRegisterShape(unittest.TestCase):
    def test_exactly_70_rows_contiguous_71_to_140(self):
        rows = load()["rows"]
        self.assertEqual(len(rows), 70)
        self.assertEqual([r["n"] for r in rows], list(range(71, 141)))

    def test_ids_follow_unit_and_law_no_renumbering(self):
        # ledger order: 5 units x 16 laws from app 1 -> 71 begins at LAND-005-L7
        self.assertEqual(load()["rows"][0]["id"], "LAND-005-L7")
        self.assertEqual(load()["rows"][-1]["id"], "RES-004-L12")
        for row in load()["rows"]:
            self.assertEqual(row["id"], "%s-%s" % (row["unit"], row["law"]))

    def test_every_row_carries_a_verdict_and_evidence(self):
        for row in load()["rows"]:
            self.assertIn(row["verdict"], {"PRESENT", "ABSENT", "UNKNOWN"})
            self.assertTrue(row["evidence"].strip(), row["id"])

    def test_counts_match_rows(self):
        doc = load()
        computed = {}
        for row in doc["rows"]:
            computed[row["verdict"]] = computed.get(row["verdict"], 0) + 1
        self.assertEqual(doc["counts"]["total"], 70)
        for verdict, count in computed.items():
            self.assertEqual(doc["counts"][verdict], count)


class TestCheckerGoesGreen(unittest.TestCase):
    def test_checker_passes_on_the_committed_register(self):
        got = run_checker()
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertIn("OK", got.stdout)

    def test_checker_reverifies_tree_anchors(self):
        got = subprocess.run([sys.executable, CHECKER, "--json"], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        summary = json.loads(got.stdout)
        self.assertGreater(summary["tree_anchors_reverified"], 0)
        self.assertEqual(summary["pin_minting_workflows"], ["sf-prover-pin-authority.yml"])


class TestCheckerDiscriminates(unittest.TestCase):
    """Mutation proof: each corruption must turn the checker RED."""

    def test_dropped_row_fails(self):
        doc = load()
        doc["rows"].pop()
        doc["counts"]["total"] = len(doc["rows"])
        got = run_checker(json.dumps(doc))
        self.assertNotEqual(got.returncode, 0, "dropping a row must fail")

    def test_renumbered_row_fails(self):
        doc = load()
        doc["rows"][3]["n"] = 99
        got = run_checker(json.dumps(doc))
        self.assertNotEqual(got.returncode, 0, "renumbering a row must fail")

    def test_false_present_fails(self):
        doc = load()
        target = next(r for r in doc["rows"] if r["verdict"] == "UNKNOWN")
        target["verdict"] = "PRESENT"
        target["method"] = "transcript"
        got = run_checker(json.dumps(doc))
        self.assertNotEqual(got.returncode, 0, "PRESENT on transcript-only evidence must fail")

    def test_missing_evidence_fails(self):
        doc = load()
        doc["rows"][0]["evidence"] = ""
        got = run_checker(json.dumps(doc))
        self.assertNotEqual(got.returncode, 0, "a row with no evidence must fail")


class TestLawAuditsDiscriminate(unittest.TestCase):
    """The L12 audit must pass a clean branch and FAIL one that merged main in."""

    def _git(self, cwd, *args):
        subprocess.run(["git"] + list(args), cwd=cwd, check=True,
                       capture_output=True, text=True)

    def _repo(self, tmp):
        self._git(tmp, "init", "-q", "-b", "main")
        self._git(tmp, "config", "user.email", "t@example.com")
        self._git(tmp, "config", "user.name", "t")
        with open(os.path.join(tmp, "a.txt"), "w") as fh:
            fh.write("one\n")
        self._git(tmp, "add", "a.txt")
        self._git(tmp, "commit", "-qm", "base")
        self._git(tmp, "branch", "-M", "main")
        self._git(tmp, "update-ref", "refs/remotes/origin/main", "main")

    def test_clean_branch_passes_l12(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp)
            self._git(tmp, "checkout", "-qb", "unit")
            with open(os.path.join(tmp, "b.txt"), "w") as fh:
                fh.write("two\n")
            self._git(tmp, "add", "b.txt")
            self._git(tmp, "commit", "-qm", "unit work")
            got = subprocess.run([sys.executable, CHECKER, "--audit-ref", "unit"],
                                 cwd=tmp, capture_output=True, text=True)
            self.assertEqual(got.returncode, 0, got.stdout + got.stderr)

    def test_branch_that_merged_main_fails_l12(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp)
            self._git(tmp, "checkout", "-qb", "unit")
            with open(os.path.join(tmp, "b.txt"), "w") as fh:
                fh.write("two\n")
            self._git(tmp, "add", "b.txt")
            self._git(tmp, "commit", "-qm", "unit work")
            self._git(tmp, "checkout", "-q", "main")
            with open(os.path.join(tmp, "c.txt"), "w") as fh:
                fh.write("three\n")
            self._git(tmp, "add", "c.txt")
            self._git(tmp, "commit", "-qm", "main moved")
            self._git(tmp, "checkout", "-q", "unit")
            self._git(tmp, "merge", "-q", "--no-ff", "-m", "merge main into unit", "main")
            got = subprocess.run([sys.executable, CHECKER, "--audit-ref", "unit"],
                                 cwd=tmp, capture_output=True, text=True)
            self.assertNotEqual(got.returncode, 0, "a main-merge into the branch must fail L12")
            self.assertIn("L12", got.stdout + got.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
