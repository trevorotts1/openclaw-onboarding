"""Offline GHL read-back for the launcher's fixtures and tests (PRD-12).

intake.validate() verifies the entitlement attestation against the client's GHL contact/order record through a
read-only transport (entitlement.set_transport). Every fixture carries TEST-ONLY references, so this installs a
read-only static transport that resolves exactly those references and nothing else.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import entitlement  # noqa: E402

TEST_ONLY_CONTACT = "TEST-ONLY-EVIDENCE"
TEST_ONLY_ORDER = "TEST-ONLY-PURCHASE-REFERENCE"

# The read-back facts a live launch gets from the native checkout; offline they are TEST-ONLY markers.
TEST_ONLY_CHECKOUT_READBACK = {
    "native_capability_evidence_ref": "TEST-ONLY-CAPABILITY-REF",
    "fulfillment_mapping_ref": "TEST-ONLY-FULFILLMENT-REF",
    "failed_pending_requirements": {
        "failed_state_copy_ref": "TEST-ONLY-FAILED-COPY", "pending_state_copy_ref": "TEST-ONLY-PENDING-COPY",
        "retry_policy": "reconcile_native_records_first", "requires_customer_action_copy_ref": None},
    "bump": {"component_id": "TEST-ONLY-BUMP", "component_version": "0.1", "quantity_policy": "fixed_1",
             "fulfillment_rule_ref": "TEST-ONLY-RULE"},
}


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


_PAID_BRAND = []


def paid_image_plan(cap: int = 9, approval_ref: str = "TEST-APPROVAL-REF") -> dict:
    """An image_plan for a paid (test_only False) run under the money-cap contract: a client-chosen style, a
    confirmed palette and a ceiling in money (kie draws at 8 cents a picture). Use with patch_paid_budget."""
    if not _PAID_BRAND:
        path = Path(tempfile.mkdtemp(prefix="paid-brand-")) / "brand.json"
        path.write_text(json.dumps({"palette_status": "provided"}), encoding="utf-8")
        _PAID_BRAND.append(str(path))
    return {"brand_file": _PAID_BRAND[0], "design_style": "B", "image_cap": cap, "image_cap_minor": cap * 8,
            "image_currency": "USD", "paid_render_approval_ref": approval_ref}


def patch_paid_budget(testcase) -> None:
    """The budget approval itself is proved in test_image_plan_spend.py; a test about something else stubs it."""
    from launcher_core import image_plan
    patcher = mock.patch.object(image_plan, "_verify_paid_budget", return_value=None)
    patcher.start()
    testcase.addCleanup(patcher.stop)
