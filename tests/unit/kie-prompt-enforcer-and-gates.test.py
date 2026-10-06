#!/usr/bin/env python3
"""KIE prompt rule 12 (owner order 2026-10-05): one shared Python enforcer, no separate band anywhere.

Two halves:
  * the enforcer itself (shared-utils/kie_prompt_enforcer.py): 79 percent rejected naming the chars to ADD,
    95 and 100 percent pass, 101 percent rejected naming the chars to CUT, verbatim fields exempt from the
    floor, unknown limit has no floor, the 3-try rewrite loop and its escalation, fail closed without the
    adapter. It runs the REAL Skill 74 adapter against its registry snapshot (empty HOME, no key).
  * the declared gate list (shared-utils/kie_prompt_gates.json): every gate module imports the enforcer and
    defines no band constant of its own; every data file holds no length numbers. Structural (ast and json
    walks), so a band cannot come back under a new spelling.

Run:  python3 tests/unit/kie-prompt-enforcer-and-gates.test.py   (or pytest)
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "shared-utils"))
os.environ["HOME"] = tempfile.mkdtemp()  # hermetic: no key, no cache
os.environ.pop("KIE_API_KEY", None)
os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)

import kie_prompt_enforcer as K  # noqa: E402

M = "gpt-image-2-5-sunburst-text-to-image"  # maxLength 20,000 in the registry snapshot
MAX = 20000


class TestEnforcer(unittest.TestCase):
    def test_79_percent_rejected_with_chars_to_add(self):
        v = K.check(M, "x" * (MAX * 79 // 100))
        self.assertFalse(v["ok"])
        self.assertEqual(v["status"], "BELOW_FLOOR")
        self.assertEqual(v["add"], 200)
        self.assertIn("ADD at least 200", v["message"])

    def test_floor_95_and_100_percent_pass(self):
        self.assertTrue(K.check(M, "x" * 16000)["ok"])  # 80 percent floor passes with a target warning
        self.assertEqual(K.check(M, "x" * 16000)["status"], "BELOW_TARGET")
        self.assertEqual(K.check(M, "x" * 19000)["status"], "OK")
        self.assertEqual(K.check(M, "x" * 20000)["status"], "OK")

    def test_101_percent_rejected_with_chars_to_cut(self):
        v = K.check(M, "x" * (MAX * 101 // 100))
        self.assertFalse(v["ok"])
        self.assertEqual(v["status"], "ABOVE_MAX")
        self.assertEqual(v["cut"], 200)
        self.assertIn("CUT exactly 200", v["message"])

    def test_verbatim_is_exempt_from_the_floor_but_keeps_the_ceiling(self):
        self.assertTrue(K.check(M, "a short spoken script", "verbatim")["ok"])
        self.assertFalse(K.check(M, "x" * (MAX + 1), "verbatim")["ok"])

    def test_unknown_limit_has_no_floor(self):
        v = K.check("no-such-kie-model-xyz", "tiny")
        self.assertTrue(v["ok"], v)

    def test_require_and_problems(self):
        with self.assertRaises(K.PromptBudgetError):
            K.require(M, "x" * 100)
        self.assertEqual(K.problems(M, "x" * 19000), [])
        self.assertEqual(len(K.problems(M, "x" * 100)), 1)

    def test_rewrite_loop_succeeds_within_three_tries(self):
        calls = []

        def rewriter(text, verdict):
            calls.append(verdict["add"])
            return text + "y" * verdict["add"]  # uses the exact add count it was given

        text, v = K.rewrite_to_band(M, "x" * 100, rewriter)
        self.assertTrue(v["ok"])
        self.assertEqual(len(calls), 1)  # the exact count lands in band at once

    def test_rewrite_loop_escalates_after_three_failed_tries(self):
        calls = []

        def useless(text, verdict):
            calls.append(1)
            return text

        with self.assertRaises(K.PromptBudgetEscalation):
            K.rewrite_to_band(M, "x" * 100, useless)
        self.assertEqual(len(calls), 3)

    def test_fails_closed_without_the_adapter_and_uses_a_policy_owner_limit_when_given(self):
        old = os.environ.get("KIE_LIVE_ADAPTER_PATH")
        os.environ["KIE_LIVE_ADAPTER_PATH"] = ""
        try:
            self.assertEqual(K.check(M, "x" * 19000)["status"], "ADAPTER_UNAVAILABLE")
            self.assertFalse(K.check(M, "x" * 19000)["ok"])
            self.assertTrue(K.check(M, "x" * 19000, fallback_max=MAX)["ok"])
            self.assertFalse(K.check(M, "x" * 100, fallback_max=MAX)["ok"])
        finally:
            if old is None:
                os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
            else:
                os.environ["KIE_LIVE_ADAPTER_PATH"] = old

    def test_the_adapter_is_asked_once_per_model_per_process(self):
        # a render fan-out checks every slide: one adapter call for the model, then local verdicts from its numbers
        d = tempfile.mkdtemp()
        counter, stub = os.path.join(d, "n"), os.path.join(d, "stub.py")
        with open(stub, "w") as f:
            f.write("import json, sys\nopen(%r, 'a').write('x')\nsys.stdin.read()\n"
                    "print(json.dumps({'state': 'validated', 'warnings': [], 'data': {'status': 'OK', 'max': 20000, "
                    "'floor': 16000, 'target_min': 19000, 'limit_source': 'stub'}}))\n" % counter)
        old = os.environ.get("KIE_LIVE_ADAPTER_PATH")
        os.environ["KIE_LIVE_ADAPTER_PATH"] = stub
        try:
            K.clear_cache()
            self.assertTrue(K.check("m", "x" * 19000)["ok"])
            low, high = K.check("m", "y" * 15000), K.check("m", "z" * 20200)
            self.assertEqual((low["status"], low["add"]), ("BELOW_FLOOR", 1000))
            self.assertEqual((high["status"], high["cut"]), ("ABOVE_MAX", 200))
            self.assertEqual(os.path.getsize(counter), 1)
        finally:
            K.clear_cache()
            if old is None:
                os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
            else:
                os.environ["KIE_LIVE_ADAPTER_PATH"] = old

    def test_local_verdicts_equal_the_adapters_own_check(self):
        K.clear_cache()
        for n in (100, 15999, 16000, 18999, 19000, 20000, 20001, 26000):
            first = K.check(M, "x" * n)      # the first call is the adapter's own --check
            K.clear_cache()
            K.check(M, "x" * 19000)           # prime the numbers
            local = K.check(M, "x" * n)       # judged locally from the adapter's numbers
            for key in ("ok", "status", "chars", "max", "floor", "target_min", "add", "cut", "message"):
                self.assertEqual(first[key], local[key], (n, key))
            K.clear_cache()

    def test_budget_math_matches_the_adapter(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "kie_live_adapter", REPO / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py")
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        for m in (500, 3000, 3072, 5000, 7000, 20000, 30000, 12345):
            self.assertEqual(K.budget(m), adapter.budget(m), m)


def _names(tree):
    return {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)} | \
           {n.target.id for n in tree.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


class TestDeclaredGates(unittest.TestCase):
    decl = json.loads((REPO / "shared-utils" / "kie_prompt_gates.json").read_text(encoding="utf-8"))

    def test_the_declared_list_is_not_empty_and_every_file_exists(self):
        self.assertGreaterEqual(len(self.decl["gate_modules"]), 8)
        for rel in self.decl["gate_modules"] + [d["path"] for d in self.decl["data_files"]]:
            self.assertTrue((REPO / rel).is_file(), f"declared gate file missing: {rel}")

    def test_every_gate_module_imports_the_shared_enforcer(self):
        for rel in self.decl["gate_modules"]:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
            imported = any(
                (isinstance(n, ast.Import) and any(a.name == "kie_prompt_enforcer" for a in n.names))
                or (isinstance(n, ast.ImportFrom) and n.module == "kie_prompt_enforcer")
                for n in ast.walk(tree))
            self.assertTrue(imported, f"{rel} does not import shared-utils/kie_prompt_enforcer.py")

    def test_no_gate_module_keeps_a_separate_band_constant(self):
        banned = set(self.decl["forbidden_module_constants"])
        for rel in self.decl["gate_modules"]:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
            self.assertEqual(_names(tree) & banned, set(), f"{rel} reintroduced a separate hard-coded prompt band")

    def test_no_data_file_holds_length_numbers(self):
        for d in self.decl["data_files"]:
            data = json.loads((REPO / d["path"]).read_text(encoding="utf-8"))
            self.assertEqual(set(_keys(data)) & set(d["forbidden_keys"]), set(),
                             f"{d['path']} reintroduced a hard-coded length key")

    def test_the_enforcer_is_not_itself_listed_as_a_consumer_of_a_band(self):
        self.assertNotIn(self.decl["enforcer"], self.decl["gate_modules"])


if __name__ == "__main__":
    unittest.main()
