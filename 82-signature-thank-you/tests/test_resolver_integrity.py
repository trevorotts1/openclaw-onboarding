"""F-harden-01: the resolver verifies snapshot integrity, not just the
"verified" boolean. A hand-assembled or edited snapshot is refused by name
(snapshot_integrity_failed) before any view is built. TEST ONLY data.
"""

import copy
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from purchase_event_adapter import SNAPSHOT_KEY_ENV  # noqa: E402
from thank_you_resolver import ResolverError, resolve_order_view  # noqa: E402
from test_event_adapter import (  # noqa: E402
    FakeS44Store, ORDER_1, build, live_event, make_event)
from test_thank_you import IDENTITY, make_fulfillment, make_snapshot  # noqa: E402


class ResolverIntegrityTest(unittest.TestCase):
    def setUp(self):
        # F-harden-02: live snapshots are signed and verified with a key.
        patcher = mock.patch.dict(
            os.environ, {SNAPSHOT_KEY_ENV: "fixture-hmac-key-for-tests-only"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _resolve(self, snapshot):
        return resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)

    def test_adapter_built_snapshots_resolve(self):
        good = live_event()
        live = build([good], evidence_store=FakeS44Store([good]))[ORDER_1]
        test = build([make_event("TEST-EVT-I1", ORDER_1, ["MAIN-A"])])[ORDER_1]
        for snapshot in (live, test):
            self.assertEqual(self._resolve(snapshot)["items"][0]["offer_id"],
                             "MAIN-A")

    def test_hand_assembled_snapshot_refused_by_name(self):
        # verified=True, right source, but never stamped by the adapter.
        snapshot = make_snapshot(["MAIN-A"])
        self.assertIs(snapshot["verified"], True)
        with self.assertRaises(ResolverError) as ctx:
            self._resolve(snapshot)
        self.assertIn("snapshot_integrity_failed", str(ctx.exception))

    def test_tampered_snapshot_refused_by_name(self):
        good = live_event()
        snapshot = build([good], evidence_store=FakeS44Store([good]))[ORDER_1]
        for edit in (
            lambda s: s["line_items"][0].update(amount_minor=1),
            lambda s: s["line_items"][0].update(payment_status="pending"),
            lambda s: s.update(journey_id="OTHER-JOURNEY"),
        ):
            forged = copy.deepcopy(snapshot)
            edit(forged)
            with self.assertRaises(ResolverError) as ctx:
                self._resolve(forged)
            self.assertIn("snapshot_integrity_failed", str(ctx.exception))
        forged = copy.deepcopy(snapshot)
        forged["integrity"] = "0" * 64  # hand-typed hash
        with self.assertRaises(ResolverError):
            self._resolve(forged)


if __name__ == "__main__":
    unittest.main()
