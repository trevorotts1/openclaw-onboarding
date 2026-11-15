"""Skill 75 whole-tree pytest hygiene: one process-wide monkeypatch, undone.

`scripts/conftest.py` (TESTHYG-75) already rebinds the skill's MODULES per test
file. It sits under `scripts/`, so it governs that subtree only -- the sibling
`shared-bridge/checks/` suites never get its hooks. That is enough for modules
and not enough for `socket.socket`.

Several suites mock the network by rebinding the class at import:
`scripts/core/spoken_share_card_docs/test_share_card_docs.py`,
`scripts/core/choice_card/stl_voice_guard/test_stl_voice_guard.py` and
`scripts/core/smp/initial_questions/test_initial_questions.py` all do
`socket.socket = _NoNetwork` and never put it back. `scripts/` collects before
`shared-bridge/`, so in ONE pytest process every later suite -- including the
ones whose own stub server listens on 127.0.0.1 -- dies on
"network call during a mocked test". Solo `python3 <test>.py` runs never see it.

So: snapshot `socket.socket` where each file leaves it, restore the real class
before the next file is imported, and re-apply a file's own value before its
first test. Each guard stays armed for its own suite, exactly as a solo run
does, and leaks nowhere else. Same shape as the module snapshot in
`scripts/conftest.py`, at the level that can see both trees.
"""
import socket

import pytest

_REAL_SOCKET = socket.socket   # before any test file rebinds it
_SOCKETS = {}                  # test file nodeid -> socket.socket it installed
_ACTIVE = [None]               # the test file whose socket is currently installed


def pytest_collectstart(collector):
    if not isinstance(collector, pytest.Module):
        return
    socket.socket = _REAL_SOCKET


def pytest_collectreport(report):
    nodeid = report.nodeid
    if nodeid.endswith(".py") and "::" not in nodeid:
        _SOCKETS[nodeid] = socket.socket


def pytest_runtest_setup(item):
    nodeid = item.nodeid.split("::", 1)[0]
    if _ACTIVE[0] == nodeid:
        return
    socket.socket = _SOCKETS.get(nodeid, _REAL_SOCKET)
    _ACTIVE[0] = nodeid
