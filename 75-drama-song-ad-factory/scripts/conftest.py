"""Skill 75 pytest collection hygiene (unit TESTHYG-75).

Every suite under this tree is script-style: `python3 <test>.py` with a
`sys.path.insert(0, HERE)` and a top-level import of its module by bare name
(`no_echo`, `catalog_calculator`, `weekly_step`, `lip_gate`...). Several
directories ship modules with the SAME top-level name (thin re-exports under
core/smp/), and some tests mutate their module at import (kie_dispatch's
forbid-real-runner patch). In one pytest process the first-imported copy wins
sys.modules, so later suites would silently judge the WRONG module -- exactly
the hiding the per-file CI loop masks.

Before pytest collects each test file this hook drops every skill-tree module
imported so far, so each suite binds its own sys.path / its own module file
exactly as a solo `python3 <test>.py` run does.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__)) + os.sep
_KEEP = frozenset(sys.modules) | {"conftest", "sys", "os"}


def pytest_collectstart(collector):
    for name in list(sys.modules):
        if name in _KEEP or name.startswith("conftest"):
            continue
        mod = sys.modules.get(name)
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        try:
            if os.path.abspath(f).startswith(ROOT):
                del sys.modules[name]
        except (OSError, ValueError):
            pass
