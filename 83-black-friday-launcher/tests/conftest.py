"""Offline GHL read-back for the launcher suite (PRD-12).

intake.validate() verifies the entitlement attestation against the client's GHL contact/order record through
a read-only transport (entitlement.set_transport). Every fixture in this suite carries TEST-ONLY references, so
this fixture installs the read-only static transport of fixtures/test_only_readback.py, which resolves exactly
those references and nothing else. test_entitlement_readback.py resets the seam itself and passes its own
transports, so it is unaffected.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

from launcher_core import entitlement  # noqa: E402
from test_only_readback import (TEST_ONLY_CONTACT, TEST_ONLY_ORDER, test_only_transport)  # noqa: E402,F401


@pytest.fixture(autouse=True, scope="session")
def _offline_ghl_readback_session():
    """Class-level setUpClass hooks (unittest) run before any function-scoped fixture."""
    entitlement.set_transport(test_only_transport())
    yield
    entitlement.set_transport(None)


@pytest.fixture(autouse=True)
def _offline_ghl_readback():
    entitlement.set_transport(test_only_transport())
    yield
    entitlement.set_transport(test_only_transport())  # back to the session default, never to the live reader
