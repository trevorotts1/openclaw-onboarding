# conftest.py — rootdir-level pytest config for 06-ghl-install-pages tests.

# P0-6 capability-freshness gate: mock dispatch suites assert the SOP state-
# machine contract, NOT the freshness gate (the gate has its own dedicated
# suite in test_browser_manager_capability_wire.py). On CI / any bare box the
# default receipt (working/skill6-capability.json) is absent, which would flip
# every mock dispatch into STATE_WAITING. Autouse: redirect the dispatcher's
# DEFAULT_CAPABILITY_PATH to a fresh receipt for the duration of each test.
# Suites that test the gate itself inject their own capability_path explicitly
# (test_browser_manager_capability_wire.py), which wins over this default.

import json
import time

import pytest


@pytest.fixture(autouse=True)
def _fresh_capability_receipt(tmp_path_factory, monkeypatch):
    try:
        import v2_dispatcher as _disp
    except ImportError:
        return  # suite does not touch the dispatcher
    # OUTSIDE any test's tmp_path: clean-dir / byte-identical tests assert
    # ``list(tmp_path.iterdir()) == []`` — nothing may land there, fixture
    # included. tmp_path_factory gives a per-test dir in pytest's own base.
    capdir = tmp_path_factory.mktemp("capfix")
    cap = capdir / "skill6-capability.json"
    cap.write_text(json.dumps({"selectedLane": "agent_browser",
                               "probedAt": "mock-fixture"}), encoding="utf-8")
    import os as _os
    _os.utime(str(cap), (time.time(), time.time()))
    monkeypatch.setattr(_disp, "DEFAULT_CAPABILITY_PATH", str(cap),
                        raising=False)