"""Test helper: resolve_order_view for tests that fabricate snapshots.

The resolver refuses any snapshot whose adapter integrity hash does not
verify (F-harden-01). Tests that hand-build a snapshot to exercise some
other rule (identity, billing, refunds, ...) call this wrapper, which
stamps the fixture the way the adapter would and then runs the real
resolver, integrity check included. Refusal of unstamped or edited
snapshots is covered by test_resolver_integrity.py, which calls the real
resolver directly.
"""

from purchase_event_adapter import snapshot_integrity
from thank_you_resolver import resolve_order_view as _resolve_order_view


def resolve_order_view(snapshot, *args, **kwargs):
    if isinstance(snapshot, dict):
        snapshot = {**snapshot, "integrity": snapshot_integrity(snapshot)}
    return _resolve_order_view(snapshot, *args, **kwargs)
