#!/usr/bin/env python3
"""KIE prompt rule 12 (owner order 2026-10-05): one shared Python enforcer, no separate band anywhere.

Two halves:
  * the enforcer itself (shared-utils/kie_prompt_enforcer.py): 79 percent rejected naming the chars to ADD,
    95 and 100 percent pass, 101 percent rejected naming the chars to CUT, verbatim fields exempt from the
    floor, unknown limit has no floor, the 3-try rewrite loop and its escalation, fail closed without the
    adapter. It runs the REAL Skill 74 adapter against its registry snapshot (empty HOME, no key).
  * the declared gate list (shared-utils/kie_prompt_gates.json), checked structurally (ast and json walks, no text
    search): (a) no declared gate holds a numeric character band under any name (a len(...) compared with a literal,
    a band-named integer constant, a min/max/floor/ceiling key with a number); (b) a gate that imports the enforcer
    must CALL it; (c) a discovery walk over every skill's scripts fails on an undeclared module that compares a
    prompt length with a literal or defines a prompt-length constant. Each rule is proven by mutation on a temp copy.

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


# ---------------------------------------------------------------------------------------------------------------
# Structural scanners (pure functions over source text, so a test can feed them a mutated copy).
# ---------------------------------------------------------------------------------------------------------------
import re  # noqa: E402

BAND_NAME = re.compile(r"(?i)(prompt|char|floor|ceil\w*|band|limit|cap|min|max|length)")
BAND_KEYS = {"min", "max", "floor", "ceiling", "min_chars", "max_chars", "maxlength", "max_length"}
PROMPT_CONST = re.compile(r"(?i)((?<!tele)prompt[_a-z0-9]*(min|max|floor|ceil|limit|cap|len|char)|house_(min|max))")
GENERIC_BAND = re.compile(r"(?i)(min|max|floor|ceil\\w*|cap|limit|chars?)")
HISTORIC_BANDS = {5000, 9000, 16000, 18000, 19000, 20000, 25000}  # the numbers earlier gates hard-coded
SKIP_DIRS = {".git", "node_modules", "__pycache__", "examples", "evidence", "tests", "test", "test-fixtures",
             "render-proof", "QUALITY-CONTROL", "backups"}


def _is_int(node, lo):
    return isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool) \
        and node.value >= lo


def _has_int(node, lo):
    return any(_is_int(n, lo) for n in ast.walk(node))


def _assigned(node):
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)], node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        return [node.target.id], node.value
    return [], None


def band_findings(src, name_re=BAND_NAME):
    """Every place a module keeps a numeric character band, as (lineno, key). Any scope. A key is the constant name,
    the dict key, or 'len-vs-literal:<expression>'."""
    tree, out = ast.parse(src), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare):
            ops = [n.left] + list(n.comparators)
            if any(isinstance(o, ast.Call) and isinstance(o.func, ast.Name) and o.func.id == "len" for o in ops) \
                    and any(_is_int(o, 500) for o in ops):
                out.append((n.lineno, "len-vs-literal:" + ast.unparse(n)))
        names, value = _assigned(n)
        for nm in names:
            if name_re.search(nm) and _has_int(value, 1000):
                out.append((n.lineno, nm))
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value.lower() in BAND_KEYS \
                        and _is_int(v, 1000):
                    out.append((n.lineno, k.value))
        if isinstance(n, ast.keyword) and n.arg and n.arg.lower() in BAND_KEYS and _is_int(n.value, 1000):
            out.append((n.value.lineno, "kw:" + n.arg))
    return out


def calls_attr(src, aliases, attrs):
    """True when the module calls <alias>.<attr>(...) for one of the attrs (an AST call, not a mention)."""
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in attrs \
                and ast.unparse(n.func.value) in aliases:
            return True
    return False


def imports_enforcer(src):
    return any((isinstance(n, ast.Import) and any(a.name == "kie_prompt_enforcer" for a in n.names))
               or (isinstance(n, ast.ImportFrom) and n.module == "kie_prompt_enforcer")
               or (isinstance(n, ast.Constant) and n.value == "kie_prompt_enforcer.py")
               for n in ast.walk(ast.parse(src)))


def undeclared_prompt_length_checks(src):
    """Discovery: a prompt length compared with a literal, or a prompt-length constant (any scope)."""
    tree, out = ast.parse(src), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare):
            ops = [n.left] + list(n.comparators)
            lens = [o for o in ops if isinstance(o, ast.Call) and isinstance(o.func, ast.Name) and o.func.id == "len"
                    and o.args and re.search(r"(?i)(?<!tele)prompt", ast.unparse(o.args[0]))]
            if lens and any(_is_int(o, 500) for o in ops):
                out.append((n.lineno, "len(prompt) vs literal: " + ast.unparse(n)))
        names, value = _assigned(n)
        for nm in names:
            if PROMPT_CONST.search(nm) and _has_int(value, 1000):
                out.append((n.lineno, "prompt-length constant: " + nm))
            elif GENERIC_BAND.search(nm) and any(isinstance(x, ast.Constant) and x.value in HISTORIC_BANDS
                                                 and not isinstance(x.value, bool) for x in ast.walk(value)):
                out.append((n.lineno, "band-named constant holding a previously hard-coded prompt band: " + nm))
    return out


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


DECL = json.loads((REPO / "shared-utils" / "kie_prompt_gates.json").read_text(encoding="utf-8"))
ALIASES = set(DECL["enforcer_aliases"])
ENF_CALLS = set(DECL["enforcer_calls"])


def _read(rel, root=REPO):
    return (root / rel).read_text(encoding="utf-8")


def gate_violations(root=REPO, decl=DECL):
    """Everything wrong with the declared gates under `root` (a repo checkout or a mutated temp copy)."""
    bad, allowed = [], decl.get("allowed_numeric", {})
    banned = set(decl["forbidden_module_constants"])
    direct = list(decl["gate_modules"])
    delegating = decl["delegating_gate_modules"]
    adapter = decl["adapter_direct_gate_modules"]
    for rel in direct + [d["path"] for d in delegating] + [d["path"] for d in adapter]:
        src = _read(rel, root)
        ok_names = set(allowed.get(rel, []))
        for line, key in band_findings(src):
            if key not in ok_names:
                bad.append(f"{rel}:{line}: a numeric character band under the name {key!r}")
        tree = ast.parse(src)
        top = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        if top & banned:
            bad.append(f"{rel}: reintroduced a banned band constant {sorted(top & banned)}")
    for rel in direct:
        src = _read(rel, root)
        if not imports_enforcer(src):
            bad.append(f"{rel}: does not import shared-utils/kie_prompt_enforcer.py")
        elif not calls_attr(src, ALIASES, ENF_CALLS):
            bad.append(f"{rel}: imports the enforcer but never calls it")
    for d in delegating:
        if not calls_attr(_read(d["path"], root), {d["via"]}, set(d["calls"])):
            bad.append(f"{d['path']}: never calls {d['via']}.{'/'.join(d['calls'])}")
    for d in adapter:
        if not calls_attr(_read(d["path"], root), {"adapter", "self._adapter()"} | {"a"}, set(d["calls"])) \
                and not calls_attr(_read(d["path"], root), set(ast.unparse(n.func.value) for n in ast.walk(ast.parse(_read(d["path"], root)))
                                                               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                                               and n.func.attr in d["calls"]), set(d["calls"])):
            bad.append(f"{d['path']}: never calls the Skill 74 prompt-budget check")
    for d in decl["data_files"]:
        data = json.loads(_read(d["path"], root))
        if "forbidden_keys" in d and set(_keys(data)) & set(d["forbidden_keys"]):
            bad.append(f"{d['path']}: reintroduced a hard-coded length key {sorted(set(_keys(data)) & set(d['forbidden_keys']))}")
        for band, keys in d.get("forbidden_keys_in", {}).items():
            node = data.get("bands", data).get(band, {})
            if set(node) & set(keys):
                bad.append(f"{d['path']}: band {band} reintroduced {sorted(set(node) & set(keys))}")
    return bad


def discovery_violations(root=REPO, decl=DECL):
    declared = set(decl["gate_modules"]) | {d["path"] for d in decl["delegating_gate_modules"]} | \
        {d["path"] for d in decl["adapter_direct_gate_modules"]} | {e["path"] for e in decl["exemptions"]}
    declared.add(decl["enforcer"])
    bad = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("test_") or fn.endswith("_test.py"):
                continue
            rel = os.path.relpath(os.path.join(base, fn), root)
            if rel in declared:
                continue
            try:
                found = undeclared_prompt_length_checks((Path(base) / fn).read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for line, what in found:
                bad.append(f"{rel}:{line}: {what} (declare the module in shared-utils/kie_prompt_gates.json "
                           "and route it through the enforcer)")
    return bad


class TestDeclaredGates(unittest.TestCase):
    def test_the_declared_list_is_not_empty_and_every_file_exists(self):
        self.assertGreaterEqual(len(DECL["gate_modules"]), 15)
        paths = DECL["gate_modules"] + [d["path"] for d in DECL["delegating_gate_modules"]] + \
            [d["path"] for d in DECL["adapter_direct_gate_modules"]] + [d["path"] for d in DECL["data_files"]] + \
            [e["path"] for e in DECL["exemptions"]]
        for rel in paths:
            self.assertTrue((REPO / rel).is_file(), f"declared file missing: {rel}")

    def test_declared_gates_are_clean(self):
        self.assertEqual(gate_violations(), [])

    def test_no_undeclared_gate_compares_a_prompt_length_with_a_literal(self):
        self.assertEqual(discovery_violations(), [])

    def test_the_enforcer_is_not_itself_listed_as_a_consumer_of_a_band(self):
        self.assertNotIn(DECL["enforcer"], DECL["gate_modules"])


class TestMutationProofs(unittest.TestCase):
    """Each guard rule is proven to fail on a mutated temp copy of a real gate (the live tree is never touched)."""

    def _mutated(self, rel, transform, extra_files=()):
        root = Path(tempfile.mkdtemp())
        for r in [rel, *extra_files]:
            dest = root / r
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_read(r), encoding="utf-8")
        if transform:
            (root / rel).write_text(transform(_read(rel)), encoding="utf-8")
        return root

    def _only(self, rel):
        one = dict(DECL, gate_modules=[rel], delegating_gate_modules=[], adapter_direct_gate_modules=[], data_files=[])
        return one

    def test_a_band_reintroduced_under_a_new_name_is_caught(self):
        rel = "66-kie-image/scripts/validate_prompt.py"
        root = self._mutated(rel, lambda s: s + "\nMY_BAND_LO = 9000\nlimits = {'max': 19000}\n")
        bad = gate_violations(root, self._only(rel))
        self.assertTrue(any("MY_BAND_LO" in b for b in bad), bad)
        self.assertTrue(any("'max'" in b for b in bad), bad)

    def test_a_len_prompt_comparison_against_a_literal_is_caught(self):
        rel = "67-kie-video/scripts/validate_prompt.py"
        root = self._mutated(rel, lambda s: s + "\ndef _mine(prompt):\n    return len(prompt) < 5000\n")
        bad = gate_violations(root, self._only(rel))
        self.assertTrue(any("len-vs-literal" in b for b in bad), bad)

    def test_an_import_without_a_call_is_caught(self):
        rel = "67-kie-video/scripts/validate_prompt.py"
        root = self._mutated(rel, lambda s: re.sub(r"KPE\.(check|problems|require|budget_for|rewrite_to_band|check_count)\(",
                                                   "(lambda *a, **k: {'ok': True, 'warnings': [], 'message': ''})(", s))
        bad = gate_violations(root, self._only(rel))
        self.assertTrue(any("never calls it" in b for b in bad), bad)

    def test_a_gate_that_stops_importing_the_enforcer_is_caught(self):
        rel = "66-kie-image/scripts/validate_prompt.py"
        root = self._mutated(rel, lambda s: s.replace("kie_prompt_enforcer", "other_module"))
        bad = gate_violations(root, self._only(rel))
        self.assertTrue(any("does not import" in b for b in bad), bad)

    def test_a_band_key_in_a_data_file_is_caught(self):
        rel = "23-ai-workforce-blueprint/templates/role-library/graphics/connection-manifest.json"
        root = self._mutated(rel, lambda s: s.replace('"prompt_budget"', '"floor": 5000, "prompt_budget"', 1))
        one = dict(self._only("66-kie-image/scripts/validate_prompt.py"), gate_modules=[],
                   data_files=[d for d in DECL["data_files"] if d["path"] == rel])
        self.assertTrue(any("hard-coded length key" in b for b in gate_violations(root, one)))

    def test_an_undeclared_gate_with_a_prompt_band_is_found_by_discovery(self):
        root = Path(tempfile.mkdtemp())
        (root / "99-new-skill" / "scripts").mkdir(parents=True)
        (root / "99-new-skill" / "scripts" / "check_prompt.py").write_text(
            "def ok(prompt):\n    return 5000 <= len(prompt) <= 19000\n\nPROMPT_MIN_CHARS = 5000\n", encoding="utf-8")
        bad = discovery_violations(root, DECL)
        self.assertTrue(any("len(prompt) vs literal" in b for b in bad), bad)
        self.assertTrue(any("PROMPT_MIN_CHARS" in b for b in bad), bad)


if __name__ == "__main__":
    unittest.main()
