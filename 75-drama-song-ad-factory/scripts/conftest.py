"""Skill 75 pytest collection hygiene (unit TESTHYG-75).

Every suite under this tree is script-style: `python3 <test>.py` with a
`sys.path.insert(0, HERE)` and a top-level import of its module by bare name
(`no_echo`, `catalog_calculator`, `weekly_step`, `lip_gate`...). Several
directories ship modules with the SAME top-level name (thin re-exports under
core/smp/), and some tests mutate their module at import (kie_dispatch's
forbid-real-runner patch). In one pytest process the first-imported copy wins
sys.modules, so later suites would silently judge the WRONG module -- exactly
the hiding the per-file CI loop masks.

Before pytest collects each test FILE this hook drops every skill-tree module
imported so far, so each suite binds its own sys.path / its own module file
exactly as a solo `python3 <test>.py` run does.

Two rules keep that from creating a SECOND copy of a module inside one suite:
  * only a file's own (Module) collector drops modules. Class/unittest
    collectors start AFTER the file was imported, and dropping then would
    orphan every module the file already bound.
  * pytest collects every file before running any, so by run time the modules
    a file imported are long gone from sys.modules. The ones it imported are
    snapshotted when its collection ends and put back before its first test,
    so a lazy `from pkg import mod` inside the code under test resolves to the
    SAME module object the test holds (assertRaises(mod.Error), patch.object
    (mod, ...) then act on the one real module, as in a solo run).
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__)) + os.sep
_KEEP = frozenset(sys.modules) | {"conftest", "sys", "os"}
_SNAPSHOTS = {}          # test file nodeid -> {module name: module} it imported
_ACTIVE = [None]         # the test file whose modules are currently installed


def _skill_modules():
    found = {}
    for name in list(sys.modules):
        if name in _KEEP or name.startswith("conftest"):
            continue
        mod = sys.modules.get(name)
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        try:
            if os.path.abspath(f).startswith(ROOT):
                found[name] = mod
        except (OSError, ValueError):
            pass
    return found


def pytest_collectstart(collector):
    if not isinstance(collector, pytest.Module):
        return
    for name in _skill_modules():
        del sys.modules[name]


def pytest_collectreport(report):
    nodeid = report.nodeid
    if nodeid.endswith(".py") and "::" not in nodeid:
        _SNAPSHOTS[nodeid] = _skill_modules()


def pytest_runtest_setup(item):
    nodeid = item.nodeid.split("::", 1)[0]
    if _ACTIVE[0] == nodeid or nodeid not in _SNAPSHOTS:
        return
    for name in _skill_modules():
        del sys.modules[name]
    sys.modules.update(_SNAPSHOTS[nodeid])
    _ACTIVE[0] = nodeid


import pytest


@pytest.fixture
def tmp():
    """The script-style suites (test_frame_text_f9.py) take a temp DIRECTORY
    path as their first argument; a plain `python3 <test>.py` run passes one
    from main(). Under pytest the name is read as a fixture request, so hand
    back a fresh empty directory path -- same contract, pytest-shaped."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="w75-tmp-") as d:
        yield d
