#!/usr/bin/env python3
"""Regression tests for the T-38 runtime wiring in CONTROL/eng_loop.py.

PBB-822 defect 1: the launcher imported RUNTIME_MAC / RUNTIME_VPS / RUNTIME_DOCKER
and then keyed its adapter map with the same strings as literals, so the three
imports were declarations with no reference. The map must be the package's own
constants bound to the package's own adapter classes, so classify_runtime's
answer can never drift from the type the loop cross-checks.

Run: python3 -m unittest discover -s CONTROL/tests -v
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.dirname(HERE)
SCRIPT = os.path.join(CONTROL, "eng_loop.py")
sys.path.insert(0, os.path.join(os.path.dirname(CONTROL), "shared-utils"))

from runtime import host  # noqa: E402


def _load_module():
    spec = importlib.util.spec_from_file_location("eng_loop_runtime_wiring", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
