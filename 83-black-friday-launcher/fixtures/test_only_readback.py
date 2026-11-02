"""Offline GHL read-back for the launcher's fixtures and tests (PRD-12).

intake.validate() verifies the entitlement attestation against the client's GHL contact/order record through a
read-only transport (entitlement.set_transport). Every fixture carries TEST-ONLY references, so this installs a
read-only static transport that resolves exactly those references and nothing else.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import entitlement  # noqa: E402

TEST_ONLY_CONTACT = "TEST-ONLY-EVIDENCE"
TEST_ONLY_ORDER = "TEST-ONLY-PURCHASE-REFERENCE"


def test_only_transport():
    cm = entitlement._membership_module()
    declaration = entitlement.load_declaration()
    tags = [t for names in declaration["membership_tags"].values() for t in names]
    price = declaration["purchase_price"]
    return cm.StaticReadTransport({
        f"/contacts/{TEST_ONLY_CONTACT}": {"contact": {"tags": tags}},
        f"/payments/orders/{TEST_ONLY_ORDER}": {
            "_id": TEST_ONLY_ORDER, "contactId": TEST_ONLY_CONTACT, "status": "completed",
            "amount": price["amount_minor"] / 100, "currency": price["currency"]},
    })


def install() -> None:
    entitlement.set_transport(test_only_transport())
