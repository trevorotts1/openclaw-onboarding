#!/usr/bin/env python3
"""role_wrappers.consume() page-identity tests (finding 11).

The public consume() checked the delivery node's role and instance but never
bound the node to the REQUEST's page, so a checkout-A request/result with a
checkout-B delivery node returned bound_complete=True. Proves:
  * a checkout-A request/result with a checkout-B node is refused;
  * a node that drops the instance declared for its page identity is refused,
    and the declared instance still binds;
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


if __name__ == "__main__":
    unittest.main()
