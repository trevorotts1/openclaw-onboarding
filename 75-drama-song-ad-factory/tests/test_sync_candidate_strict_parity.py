#!/usr/bin/env python3
"""U-J01 BUILD-only acceptance: the sync candidate gate discriminates and is deterministic.

Synthetic trees in a temp folder - no real clone needed, no network, no writes
outside the temp folder. Every refusal case is a planted negative control: if
the gate stops refusing, these fail.

Run: python3 -B -m pytest tests/test_sync_candidate_strict_parity.py
  or: python3 -B tests/test_sync_candidate_strict_parity.py
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_candidate as sc  # noqa: E402


def make(root, files):
    for rel, body in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uj01-sync-gate-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.onb, self.n99 = self.tmp / "onb", self.tmp / "n99"
        self.onb.mkdir()
        self.n99.mkdir()

    def build(self):
        return sc.build_candidate(self.onb, self.n99)

    def test_identical_trees_gate_open(self):
        files = {"a.py": b"A = 1\n", "pkg/b.py": b"B = 2\n", "spend_ledger.py": b"S = 0\n"}
        make(self.onb, files)
        make(self.n99, files)
        m = self.build()
        self.assertEqual("OPEN", m["gate"], m["reasons"])
        self.assertEqual(3, m["counts"]["same"])
        self.assertTrue(all(v["action"] == "same" for v in m["files"].values()))
        self.assertEqual(m["trees"]["onb_sha256"], m["trees"]["n99_sha256"])

    def test_onb_only_file_is_add_and_gate_stays_open(self):
        make(self.onb, {"new.py": b"N = 1\n", "spend_ledger.py": b"S = 0\n"})
        make(self.n99, {"spend_ledger.py": b"S = 0\n"})
        m = self.build()
        self.assertEqual("OPEN", m["gate"], m["reasons"])
        self.assertEqual("add", m["files"]["new.py"]["action"])
        self.assertEqual(1, m["counts"]["add"])

    def test_differing_shared_file_is_update_and_gate_stays_open(self):
        make(self.onb, {"a.py": b"A = 2\n", "spend_ledger.py": b"S = 0\n"})
        make(self.n99, {"a.py": b"A = 1\n", "spend_ledger.py": b"S = 0\n"})
        m = self.build()
        self.assertEqual("OPEN", m["gate"], m["reasons"])
        self.assertEqual("update", m["files"]["a.py"]["action"])

    def test_n99_only_file_blocks_and_names_the_file(self):
        make(self.onb, {"spend_ledger.py": b"S = 0\n"})
        make(self.n99, {"spend_ledger.py": b"S = 0\n", "orphan_test.py": b"T = 1\n"})
        m = self.build()
        self.assertEqual("BLOCKED", m["gate"])
        self.assertEqual("delete", m["files"]["orphan_test.py"]["action"])
        self.assertIn("orphan_test.py", " ".join(m["reasons"]))
        self.assertIn("delete", " ".join(m["reasons"]))

    def test_money_safety_drift_blocks(self):
        make(self.onb, {"spend_ledger.py": b"S = 0\n", "ok.py": b"O = 1\n"})
        make(self.n99, {"spend_ledger.py": b"S = 1  # newer money fix\n", "ok.py": b"O = 1\n"})
        m = self.build()
        self.assertEqual("BLOCKED", m["gate"])
        self.assertIn("money-safety", " ".join(m["reasons"]))
        self.assertIn("U-B01", " ".join(m["reasons"]))

    def test_cache_files_are_out_of_scope_on_both_sides(self):
        make(self.onb, {"spend_ledger.py": b"S = 0\n"})
        make(self.n99, {"spend_ledger.py": b"S = 0\n"})
        for root in (self.onb, self.n99):
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "x.pyc").write_bytes(b"junk")
        m = self.build()
        self.assertNotIn("__pycache__/x.pyc", m["files"])
        self.assertEqual("OPEN", m["gate"], m["reasons"])

    def test_manifest_is_deterministic_bytes(self):
        make(self.onb, {"b.py": b"B\n", "a.py": b"A\n", "spend_ledger.py": b"S\n"})
        make(self.n99, {"a.py": b"A\n", "spend_ledger.py": b"S\n"})
        one, two = sc.dump(self.build()), sc.dump(self.build())
        self.assertEqual(one, two)
        self.assertTrue(one.endswith("\n"))

    def test_verify_detects_drift(self):
        make(self.onb, {"a.py": b"A\n", "spend_ledger.py": b"S\n"})
        make(self.n99, {"a.py": b"A\n", "spend_ledger.py": b"S\n"})
        out = self.tmp / "manifest.json"
        self.assertEqual(0, sc.main(["--onb", str(self.onb), "--n99", str(self.n99), "--out", str(out)]))
        self.assertEqual(0, sc.main(["--onb", str(self.onb), "--n99", str(self.n99), "--verify", str(out)]))
        make(self.onb, {"a.py": b"A = 2\n"})  # planted drift
        self.assertEqual(2, sc.main(["--onb", str(self.onb), "--n99", str(self.n99), "--verify", str(out)]))

    def test_build_writes_nothing(self):
        make(self.onb, {"a.py": b"A\n", "spend_ledger.py": b"S\n"})
        make(self.n99, {"a.py": b"A\n", "spend_ledger.py": b"S\n"})
        before = {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()}
        self.build()
        after = {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
