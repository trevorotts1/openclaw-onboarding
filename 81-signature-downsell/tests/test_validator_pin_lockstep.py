#!/usr/bin/env python3
"""F24 item 18 — Skill 81's pinned validator bytes and its declared consumers
must agree on ONE hash.

Skill 49's ``downsell_wrapper.py`` copies Skill 81's validator and two schemas
and refuses any byte that differs from a sha256 compiled into it. A legitimate
repair to Skill 81 therefore BREAKS a run unless the pin moves in the same
commit. This module is the three-way proof that the binding is intact:

  1. the sha256 recorded in ``VALIDATOR-CONSUMERS.json`` (the dependency's own
     declaration of who pins it),
  2. the sha256 of the real bytes on disk, and
  3. the pin constant the consumer module actually enforces.

Any two agreeing while the third diverges is the exact failure this guard
exists to catch, so each pair is asserted separately and the negative case
drives the same predicate (a test that only ever sees agreeing inputs proves
nothing).

Run: python3 tests/test_validator_pin_lockstep.py   (from this directory)
     python3 -m unittest discover -s tests          (Skill 81's own suite)
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = ROOT / "VALIDATOR-CONSUMERS.json"


def declared():
    return json.loads(DECLARATION.read_text(encoding="utf-8"))


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repo_root_for(consumer_path):
    """Walk up from this skill until a directory holds the consumer's path."""
    for candidate in (ROOT, *ROOT.parents):
        if (candidate / consumer_path).is_file():
            return candidate
    raise AssertionError(
        "consumer %r not found under any parent of %s" % (consumer_path, ROOT))


def pin_constants(module_path):
    """The module-level PIN_* string literals the consumer actually enforces.

    Read with ``ast`` rather than by importing the module: the pin is a
    constant, and parsing it proves the value shipped in the file instead of
    whatever an import-time environment happens to produce.
    """
    tree = ast.parse(Path(module_path).read_text(encoding="utf-8"),
                     filename=str(module_path))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("PIN_"):
                        found[target.id] = node.value.value
    return found


def agreement_errors(declaration, skill_root=ROOT, pins=None):
    """Every way the three parties can disagree. Empty list == lockstep.

    ``pins`` defaults to reading the consumer module named in the declaration;
    a caller passes an explicit map to drive the negative cases.
    """
    errors = []
    pinned = declaration.get("pinned") or {}
    if not pinned:
        return ["VALIDATOR-CONSUMERS.json declares no pinned files"]
    for rel, entry in sorted(pinned.items()):
        on_disk = skill_root / rel
        if not on_disk.is_file():
            errors.append("%s: declared pinned file is missing" % rel)
            continue
        real = sha256_of(on_disk)
        if entry.get("sha256") != real:
            errors.append("%s: declaration says %s, bytes hash to %s"
                          % (rel, entry.get("sha256"), real))
        consumers = entry.get("consumers") or []
        if not consumers:
            errors.append("%s: declared as pinned but names no consumer" % rel)
            continue
        for consumer in consumers:
            path = consumer.get("path")
            constant = consumer.get("pin_constant")
            if not path or not constant:
                errors.append("%s: consumer entry needs path + pin_constant" % rel)
                continue
            root = repo_root_for(path)
            module_pins = (pins if pins is not None
                           else pin_constants(root / path))
            enforced = module_pins.get(constant)
            if enforced is None:
                errors.append("%s: consumer %s has no %s constant"
                              % (rel, path, constant))
            elif enforced != real:
                errors.append("%s: consumer %s pins %s but bytes hash to %s"
                              % (rel, path, enforced, real))
    return errors


class ValidatorPinLockstep(unittest.TestCase):
    def assert_lockstep(self, declaration, skill_root=ROOT, pins=None):
        errors = agreement_errors(declaration, skill_root, pins)
        self.assertEqual(errors, [], "validator pin lockstep broken: "
                         + "; ".join(errors))

    def test_declaration_exists_and_names_the_wrapper(self):
        decl = declared()
        self.assertEqual(decl.get("schema_version"), 1)
        consumers = {c["path"] for entry in decl["pinned"].values()
                     for c in entry["consumers"]}
        self.assertTrue(
            any(p.endswith("signature-funnel/scripts/downsell_wrapper.py")
                for p in consumers),
            "the declaration must name Skill 49's downsell wrapper; saw %r"
            % sorted(consumers))

    def test_the_four_files_the_wrapper_loads_are_all_declared(self):
        """Issue 91: validate_request.py joined the validator and the two schemas as the fourth pinned file
        the wrapper hash-checks and RUNS; a fifth or a missing one changes who must move a pin."""
        self.assertEqual(sorted(declared()["pinned"]),
                         ["schemas/downsell-request.schema.json",
                          "schemas/downsell-result-extension.schema.json",
                          "validators/validate_downsell.py",
                          "validators/validate_request.py"])

    def test_every_declared_enforcement_point_is_a_function_in_the_consumer(self):
        """enforced_at tells a reader where the pin is checked; a name that no longer exists is a lie."""
        for rel, entry in declared()["pinned"].items():
            for consumer in entry["consumers"]:
                module, _, function = consumer["enforced_at"].rpartition(".")
                with self.subTest(file=rel, enforced_at=consumer["enforced_at"]):
                    self.assertEqual(module, Path(consumer["path"]).stem)
                    tree = ast.parse((repo_root_for(consumer["path"]) / consumer["path"]).read_text(encoding="utf-8"))
                    self.assertIn(function, {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)})

    def test_declared_hash_equals_the_bytes_on_disk(self):
        decl = declared()
        for rel, entry in sorted(decl["pinned"].items()):
            actual = sha256_of(ROOT / rel)
            self.assertEqual(entry["sha256"], actual,
                             "%s declaration drifted from its own bytes" % rel)

    def test_consumer_pin_equals_the_bytes_on_disk(self):
        """The wrapper's PIN_ constants and Skill 81's bytes are one hash."""
        decl = declared()
        for rel, entry in sorted(decl["pinned"].items()):
            actual = sha256_of(ROOT / rel)
            for consumer in entry["consumers"]:
                root = repo_root_for(consumer["path"])
                pins = pin_constants(root / consumer["path"])
                self.assertEqual(pins.get(consumer["pin_constant"]), actual,
                                 "%s: %s.%s does not pin the current bytes"
                                 % (rel, consumer["path"],
                                    consumer["pin_constant"]))

    def test_three_way_lockstep_holds(self):
        self.assert_lockstep(declared())

    def test_a_drifted_declaration_fails(self):
        """Negative control: a stale declaration must FAIL the same predicate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "validators").mkdir()
            (root / "validators" / "v.py").write_bytes(b"real bytes\n")
            decl = {"schema_version": 1, "pinned": {
                "validators/v.py": {
                    "sha256": "0" * 64,
                    "consumers": [{"path": "w.py",
                                   "pin_constant": "PIN_V"}]}}}
            with self.assertRaises(AssertionError):
                self.assert_lockstep(decl, skill_root=root,
                                     pins={"PIN_V": sha256_of(
                                         root / "validators" / "v.py")})

    def test_a_drifted_consumer_pin_fails(self):
        """Negative control: bytes changed, wrapper pin not moved -> FAIL."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "validators").mkdir()
            (root / "validators" / "v.py").write_bytes(b"repaired bytes\n")
            real = sha256_of(root / "validators" / "v.py")
            decl = {"schema_version": 1, "pinned": {
                "validators/v.py": {
                    "sha256": real,
                    "consumers": [{"path": "w.py",
                                   "pin_constant": "PIN_V"}]}}}
            with self.assertRaises(AssertionError):
                self.assert_lockstep(decl, skill_root=root,
                                     pins={"PIN_V": "f" * 64})

    def test_an_undeclared_consumer_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "validators").mkdir()
            (root / "validators" / "v.py").write_bytes(b"bytes\n")
            decl = {"schema_version": 1, "pinned": {
                "validators/v.py": {
                    "sha256": sha256_of(root / "validators" / "v.py"),
                    "consumers": []}}}
            with self.assertRaises(AssertionError):
                self.assert_lockstep(decl, skill_root=root, pins={})


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
