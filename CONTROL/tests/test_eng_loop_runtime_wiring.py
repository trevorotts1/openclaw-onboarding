#!/usr/bin/env python3
"""Regression tests for the T-38 runtime wiring in CONTROL/eng_loop.py.

PBB-822 defect 1: the launcher imported RUNTIME_MAC / RUNTIME_VPS / RUNTIME_DOCKER
and then keyed its adapter map with the same strings as literals, so the three
imports were declarations with no reference. The map must be the package's own
constants bound to the package's own adapter classes, so classify_runtime's
answer can never drift from the type the loop cross-checks.

PBB-822 defect 2: the census instrument counted an import declaration as a call
site. `runtime_dead_imports` is the counting rule it now uses — a name on an
`import` span is DECLARED, a reference is a Name read or an Attribute name — and
it is asserted against the launcher itself, so a dead runtime import cannot come
back unmeasured.

Run: python3 -m unittest discover -s CONTROL/tests -v
"""
import ast
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.dirname(HERE)
SCRIPT = os.path.join(CONTROL, "eng_loop.py")
HANDLER = os.path.join(CONTROL, "owner_handler.py")
sys.path.insert(0, os.path.join(os.path.dirname(CONTROL), "shared-utils"))

from runtime import host  # noqa: E402


def _load_module():
    spec = importlib.util.spec_from_file_location("eng_loop_runtime_wiring", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def runtime_dead_imports(source):
    """Names a source imports from runtime.* and references nowhere else.

    An `Import`/`ImportFrom` span (the whole parenthesised continuation) is a
    declaration. A real reference is a `Name` with ctx=Load or an `Attribute`
    attr name, taken from outside every import span.
    """
    tree = ast.parse(source)
    import_lines, declared = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            import_lines.update(range(node.lineno, end + 1))
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "runtime":
                declared.update(alias.name for alias in node.names if alias.name != "*")
    referenced = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.lineno not in import_lines:
                referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            if node.lineno not in import_lines:
                referenced.add(node.attr)
    return declared - referenced


class AdapterMapIsThePackageMap(unittest.TestCase):
    def test_keys_are_the_package_runtime_constants(self):
        mod = _load_module()
        self.assertEqual(set(mod.ADAPTERS_BY_RUNTIME), set(host.SUPPORTED_RUNTIMES))
        self.assertEqual(mod.ADAPTERS_BY_RUNTIME[host.RUNTIME_MAC], host.MacAdapter)
        self.assertEqual(mod.ADAPTERS_BY_RUNTIME[host.RUNTIME_VPS], host.VpsAdapter)
        self.assertEqual(mod.ADAPTERS_BY_RUNTIME[host.RUNTIME_DOCKER], host.DockerAdapter)

    def test_each_class_answers_for_its_own_runtime(self):
        mod = _load_module()
        for runtime_name, cls in mod.ADAPTERS_BY_RUNTIME.items():
            self.assertEqual(cls.runtime, runtime_name)


class RuntimeImportsAreRealReferences(unittest.TestCase):
    """The PBB-822 defect bytes: declarations counted as call sites."""

    OLD_BLOCK = (
        "from runtime.host import (\n"
        "    BROWSER_ABSENT, BROWSER_AVAILABLE, BROWSER_NOT_ASSUMED,\n"
        "    RUNTIME_DOCKER, RUNTIME_MAC, RUNTIME_VPS, SUPPORTED_RUNTIMES,\n"
        "    BindingRefused, BindIdentity, Capabilities, DockerAdapter, HostFacts,\n"
        "    MacAdapter, PersistencePlan, UnsupportedHost, VpsAdapter, adapter_for,\n"
        "    browser_capability, classify_runtime, detect_host, verify_persistence)\n"
        "used = (BROWSER_ABSENT, BROWSER_AVAILABLE, BROWSER_NOT_ASSUMED,\n"
        "        SUPPORTED_RUNTIMES, BindingRefused, BindIdentity, Capabilities,\n"
        "        DockerAdapter, HostFacts, MacAdapter, PersistencePlan,\n"
        "        UnsupportedHost, VpsAdapter, adapter_for, browser_capability,\n"
        "        classify_runtime, detect_host, verify_persistence)\n")

    def test_control_reports_exactly_the_three_pbb_822_declarations(self):
        self.assertEqual(runtime_dead_imports(self.OLD_BLOCK),
                         {"RUNTIME_DOCKER", "RUNTIME_MAC", "RUNTIME_VPS"})

    def test_declaration_plus_reference_is_not_dead(self):
        self.assertEqual(
            runtime_dead_imports("from runtime.host import RUNTIME_MAC\n"
                                 "ADAPTERS = {RUNTIME_MAC: 1}\n"), set())

    def test_the_launcher_has_no_dead_runtime_import(self):
        for path in (SCRIPT, HANDLER):
            with open(path) as handle:
                self.assertEqual(runtime_dead_imports(handle.read()), set(), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
