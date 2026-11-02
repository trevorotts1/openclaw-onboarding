"""Test helper: resolve_order_view for tests that fabricate snapshots.

The resolver refuses any snapshot whose adapter integrity hash does not
verify (F-harden-01). Tests that hand-build a snapshot to exercise some
other rule (identity, billing, refunds, ...) call this wrapper, which
stamps the fixture the way the adapter would and then runs the real
resolver, integrity check included. Stamping and verification both run
through the adapter's keyed HMAC path (F-harden-02) under a fixture key
(not a real secret), so live-shaped fixtures stamp and verify too. Refusal of unstamped or edited
snapshots is covered by test_resolver_integrity.py, which calls the real
resolver directly.
"""

import os
from unittest import mock

from purchase_event_adapter import SNAPSHOT_KEY_ENV, snapshot_integrity
from thank_you_resolver import resolve_order_view as _resolve_order_view


FIXTURE_KEY = "fixture-hmac-key-for-tests-only"  # not a real secret


def resolve_order_view(snapshot, *args, **kwargs):
    with mock.patch.dict(os.environ, {SNAPSHOT_KEY_ENV: FIXTURE_KEY}):
        if isinstance(snapshot, dict):
            snapshot = {**snapshot, "integrity": snapshot_integrity(snapshot)}
        return _resolve_order_view(snapshot, *args, **kwargs)
