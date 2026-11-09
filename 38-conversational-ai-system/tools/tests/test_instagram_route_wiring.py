#!/usr/bin/env python3
"""T-21 wiring pin: the production delivery driver consumes the IG route gate.

The Instagram route adapter is a contract module. Its production consumer is
``direct_fulfillment``: an Instagram destination is a first-class delivery
channel (``pb_contracts.DM_CHANNELS`` names ``IG_DM``), so an Instagram send
must pass the adapter's own account/filter/event/eligibility rules before the
common gate may dispatch.

These tests fail if the wiring is removed: an Instagram delivery would then
fall back to the generic gate alone and be sent from a Facebook Page id or
without a granted Instagram capability.
"""

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import direct_fulfillment as df  # noqa: E402


class InstagramRouteWiringTests(unittest.TestCase):
    def test_instagram_channels_are_named(self):
        self.assertIn("IG_DM", df.IG_CHANNELS)
        self.assertIn("IG_PUBLIC", df.IG_CHANNELS)

    def test_route_adapter_is_loaded_from_the_shared_tree(self):
        module = df._load_instagram_routes()
        self.assertIsNotNone(module, "T-21 route adapter not found on this tree")
        self.assertTrue(callable(getattr(module, "make_gate_evaluator", None)))

    def test_instagram_delivery_fails_closed_without_route_context(self):
        # No account/route_store: the T-21 gate refuses, never sends.
        basis = SimpleNamespace(channel="IG_DM")
        verdict = df.instagram_route_evaluator(basis, None)({})
        self.assertEqual(verdict["verdict"], "SUPPRESSED")
        self.assertEqual(verdict["evidence"]["reason"], "ig_route_unavailable")

    def test_instagram_gate_is_composed_into_fulfillment(self):
        # Structural pin: remove the IG composition and this fails.
        source = inspect.getsource(df.fulfill)
        self.assertIn("IG_CHANNELS", source)
        self.assertIn("instagram_route_evaluator", source)

    def test_non_instagram_channels_are_not_instagram(self):
        self.assertNotIn("SMS", df.IG_CHANNELS)
        self.assertNotIn("EMAIL", df.IG_CHANNELS)


if __name__ == "__main__":
    unittest.main()
