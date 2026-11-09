"""PRD-12: entitlement is read back from the client's GHL contact record.

Offline: a fake read-only GHL transport stands in for the live API.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import entitlement  # noqa: E402

CM = entitlement._membership_module()


def fake(contact_tags=("brand-management-member",), order_amount=497, order_contact="c1",
         order_status="completed"):
    return CM.StaticReadTransport({
        "/contacts/c1": {"contact": {"tags": list(contact_tags)}},
        "/payments/orders/o1": {"_id": "o1", "contactId": order_contact,
                                "status": order_status, "amount": order_amount,
                                "currency": "USD"},
    })


MEMBER = {"basis": "brand_management_membership", "evidence_ref": "c1",
          "attested_by": "agent"}
PURCHASE = {"basis": "purchase", "evidence_ref": "c1", "attested_by": "agent",
            "purchase_reference": "o1", "amount_minor": 49700, "currency": "USD"}


def refused(case, attestation, transport, code):
    with case.assertRaises(entitlement.EntitlementError) as cm:
        entitlement.gate(attestation, transport)
    case.assertEqual(cm.exception.code, code)


class EntitlementReadbackTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k, None)
                     for k in (CM.TOKEN_ENV, CM.LOCATION_ENV)}
        entitlement.set_transport(None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is not None:
                os.environ[k] = v
        entitlement.set_transport(None)

    def test_free_text_no_longer_satisfies_entitlement(self):
        free = {"basis": "purchase", "evidence_ref": "evidence-1", "attested_by": "operator",
                "purchase_reference": "order-1", "amount_minor": 49700}
        refused(self, free, fake(), "AF-LAUNCH-ENTITLEMENT-EVIDENCE-UNRESOLVED")
        refused(self, {**MEMBER, "evidence_ref": "yes whatever"}, fake(),
                "AF-LAUNCH-ENTITLEMENT-EVIDENCE-UNRESOLVED")
        refused(self, {**PURCHASE, "purchase_reference": "order-1"}, fake(),
                "AF-LAUNCH-ENTITLEMENT-EVIDENCE-UNRESOLVED")

    def test_no_credential_and_no_transport_fails_closed(self):
        refused(self, MEMBER, None, "AF-LAUNCH-ENTITLEMENT-UNVERIFIED")

    def test_member_tag_read_back_qualifies(self):
        result = entitlement.gate(MEMBER, fake())
        self.assertEqual(result["evidence_kind"], "ghl_contact_readback")
        self.assertFalse(result["proves_purchase"])
        refused(self, MEMBER, fake(contact_tags=("school-of-ai",)),
                "AF-LAUNCH-ENTITLEMENT-NOT-MEMBER")
        # ZHC with Brand Management needs both tags
        zhc = {**MEMBER, "basis": "zhc_with_brand_management"}
        refused(self, zhc, fake(), "AF-LAUNCH-ENTITLEMENT-NOT-MEMBER")
        entitlement.gate(zhc, fake(contact_tags=("brand-management-member", "zhc-member")))

    def test_order_read_back_qualifies_purchase(self):
        result = entitlement.gate(PURCHASE, fake())
        self.assertTrue(result["proves_purchase"])
        refused(self, PURCHASE, fake(order_contact="someone-else"),
                "AF-LAUNCH-ENTITLEMENT-PURCHASE-UNVERIFIED")
        refused(self, PURCHASE, fake(order_status="refunded"),
                "AF-LAUNCH-ENTITLEMENT-PURCHASE-UNVERIFIED")
        refused(self, PURCHASE, fake(order_amount=1),
                "AF-LAUNCH-ENTITLEMENT-PRICE-CONTRADICTION")

    def test_purchase_requires_amount(self):
        no_amount = {k: v for k, v in PURCHASE.items() if k != "amount_minor"}
        refused(self, no_amount, fake(), "AF-LAUNCH-ENTITLEMENT-ATTESTATION")

    def test_module_seam_transport_is_used(self):
        entitlement.set_transport(fake())
        self.assertEqual(entitlement.gate(MEMBER)["basis"], "brand_management_membership")

    def test_lookup_issues_get_only(self):
        t = fake()
        entitlement.gate(PURCHASE, t)
        entitlement.gate(MEMBER, t)
        self.assertTrue(t.requests)
        self.assertEqual({m for m, _, _ in t.requests}, {"GET"})
        for verb in ("POST", "PUT", "DELETE"):
            with self.assertRaises(ValueError):
                t.request(verb, "/contacts/c1", {})
            with self.assertRaises(ValueError):
                CM.LiveReadTransport("t", "l").request(verb, "/contacts/c1", {})

    def test_interview_yes_whatever_is_not_attested(self):
        for answer in ("yes whatever", "Yes", "Yes, it is included, I think", "yes, it is included",
                       " Yes, it is included", None):
            with self.assertRaises(entitlement.EntitlementError) as cm:
                entitlement.attest_from_interview(answer, MEMBER, fake())
            self.assertEqual(cm.exception.code, "AF-LAUNCH-ENTITLEMENT-INTERVIEW-CHOICE")
        # the exact choice still needs the lookup
        refused_t = fake(contact_tags=())
        with self.assertRaises(entitlement.EntitlementError):
            entitlement.attest_from_interview(entitlement.INCLUDED_CHOICE, MEMBER, refused_t)
        ok = entitlement.attest_from_interview(entitlement.INCLUDED_CHOICE, MEMBER, fake())
        self.assertTrue(ok["qualifies"])


if __name__ == "__main__":
    unittest.main()
