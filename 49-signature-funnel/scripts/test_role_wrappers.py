#!/usr/bin/env python3
"""role_wrappers.consume() page-identity tests (finding 11).

The public consume() checked the delivery node's role and instance but never
bound the node to the REQUEST's page, so a checkout-A request/result with a
checkout-B delivery node returned bound_complete=True. Proves:
  * a checkout-A request/result with a checkout-B node is refused;
  * a node that drops the instance declared for its page identity is refused,
    and the declared instance still binds;
  * the declared instance binds (and its absence refuses) under a FREE-FORM
    page id — real page ids are node ids like "signature-launch-l4-THANK_YOU",
    never page_type table keys, so the lookup must key on the node's
    page_type;
  * a node whose page_type is undeclared, or declares another role, is
    refused;
  * the positive control still binds completely, so the negatives mean
    something.

Run: python3 test_role_wrappers.py
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import role_wrappers as rw  # noqa: E402


class ConsumePageIdentityTest(unittest.TestCase):

    def test_positive_control_matching_node_binds(self):
        req = rw._request("checkout", "checkout")
        rec = rw.RoleWrapper("checkout").consume(
            req, rw._result(req),
            delivery_node=rw._node("checkout", "checkout"))
        self.assertEqual(rec["page_id"], "checkout")
        self.assertTrue(rec["bound_complete"])

    def test_cross_page_delivery_node_refused(self):
        req = rw._request("checkout", "checkout")
        with self.assertRaises(rw.RoleWrapperError):
            rw.RoleWrapper("checkout").consume(
                req, rw._result(req),
                delivery_node=rw._node("checkout", "checkout-B",
                                       logical_id="pg-other-page"))

    def test_dropped_declared_instance_refused(self):
        req = rw._request("downsell_1", "downsell-2")
        with self.assertRaises(rw.RoleWrapperError):
            rw.RoleWrapper("downsell_1").consume(
                req, rw._result(req),
                delivery_node=rw._node("downsell_1", "downsell-2"))

    def test_declared_instance_binds(self):
        req = rw._request("downsell_1", "downsell-2")
        rec = rw.RoleWrapper("downsell_1").consume(
            req, rw._result(req),
            delivery_node=rw._node("downsell_1", "downsell-2",
                                   role_instance="downsell_2"))
        self.assertEqual(rec["role_instance"], "downsell_2")
        self.assertTrue(rec["bound_complete"])

    def test_free_form_page_id_declared_instance_binds(self):
        req = rw._request("downsell_1", "signature-launch-l4-DOWNSELL_2")
        rec = rw.RoleWrapper("downsell_1").consume(
            req, rw._result(req),
            delivery_node=rw._node("downsell_1",
                                   "signature-launch-l4-DOWNSELL_2",
                                   page_type="downsell-2",
                                   role_instance="downsell_2"))
        self.assertEqual(rec["role_instance"], "downsell_2")
        self.assertTrue(rec["bound_complete"])

    def test_free_form_page_id_dropped_instance_refused(self):
        req = rw._request("downsell_1", "signature-launch-l4-DOWNSELL_2")
        with self.assertRaises(rw.RoleWrapperError):
            rw.RoleWrapper("downsell_1").consume(
                req, rw._result(req),
                delivery_node=rw._node("downsell_1",
                                       "signature-launch-l4-DOWNSELL_2",
                                       page_type="downsell-2"))

    def test_page_identity_declaring_other_role_refused(self):
        req = rw._request("upsell_1", "signature-launch-l4-UPSELL")
        with self.assertRaises(rw.RoleWrapperError):
            rw.RoleWrapper("upsell_1").consume(
                req, rw._result(req),
                delivery_node=rw._node("upsell_1",
                                       "signature-launch-l4-UPSELL",
                                       page_type="checkout"))

    def test_undeclared_page_identity_refused(self):
        req = rw._request("checkout", "checkout")
        with self.assertRaises(rw.RoleWrapperError):
            rw.RoleWrapper("checkout").consume(
                req, rw._result(req),
                delivery_node=rw._node("checkout", "checkout",
                                       page_type="checkout-v2"))


if __name__ == "__main__":
    unittest.main()
