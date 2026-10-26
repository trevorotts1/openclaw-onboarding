#!/usr/bin/env python3
"""reconciliation.py - resolve unknown-send outcomes without ever double-sending.

Contract basis: Purple-Billboard DATA-CONTRACTS.md section 4 ("After a crash
between provider acceptance and receipt persistence, reconcile history/status
using the same action identity. Do not blindly resend or claim exact-once
where the provider cannot guarantee it.") and section 8's crash trace.
Python 3 standard library only.

Why this exists: a process can die after the provider accepted a message and
before the local dispatch receipt was committed. On restart the action still
looks queued, so a naive worker would send it again. This module detects that
window and resolves it.

Detection - needs_reconciliation():

  * state 'unknown'                                  -> resolve
  * state 'queued' with an attempt that has no outcome and no live lease
    (the process died mid-send)                      -> resolve
  * state 'dispatched' (sent, ACK never arrived)     -> resolve the ACK only
  * state 'queued' with a live lease                 -> in flight, leave alone

On restart, sweep_inflight() promotes every queued action whose lease died
with an attempt still open to 'unknown', without closing that attempt. It is
the caller's startup step, and it never sends.

Resolution - resolve_unknown():

  The resolver is the caller's authoritative read of the provider history by
  the SAME action identity (idempotency key). This module takes NO sender and
  performs no network IO, so reconciling can never add an effect:

  * applied      -> acknowledged, dispatch receipt persisted from provider
                    evidence, separate ack receipt. Completion is NOT claimed.
  * not_applied  -> back to queued under the SAME action id; a later retry
                    must pass a fresh gate.
  * unknown      -> stays unknown, the attempt stays open, so no worker can
                    claim it. Report it, do not guess.

  A resolver that raises, or returns anything outside those three words, is
  treated as 'unknown'. Fail closed.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from durable_store import DurableStore
    from reconciliation import needs_reconciliation, resolve_unknown

Assert-based self-check:  python3 -I reconciliation.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Direct-script execution (python3 -I reconciliation.py) does not put this
# directory on sys.path; the sibling module must still resolve.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from durable_store import (
    DurableStore,
    DurableStoreError,
    STATE_DISPATCHED,
    STATE_QUEUED,
    STATE_UNKNOWN,
)

# The shared publication-receipt layer (T-25) owns what counts as a TRUE
# provider post/comment receipt. Resolving a send persists a dispatch receipt
# from the caller's provider evidence, so that evidence passes the same rule
# here: a claim, a local id echoed back, a wrong object kind, an unsupported
# status or a comment with no receipted parent is not evidence.
_RECEIPTS_DIR = Path(__file__).resolve().parents[2] / "shared-utils" / "receipts"
if str(_RECEIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_RECEIPTS_DIR))

from publication_receipts import (  # noqa: E402
    ReceiptError,
    item_kind,
    validate_provider_receipt,
)

RECONCILE_OUTCOMES = ("applied", "not_applied", "unknown")

R_APPLIED = "applied"
R_NOT_APPLIED = "not_applied"
R_UNKNOWN = "unknown"
R_NOT_NEEDED = "not_needed"
R_IN_FLIGHT = "in_flight"
R_REFUSED = "refused"


@dataclass(frozen=True)
class ReconciliationOutcome:
    status: str
    action_id: str
    state_after: Optional[str] = None
    attempt_no: Optional[int] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


def _unresolved(store: DurableStore, action_id: str) -> Optional[Dict[str, Any]]:
    return store.unresolved_attempt(action_id)


def _lease_live(action: Dict[str, Any], now: float) -> bool:
    expires = action.get("lease_expires_at")
    return expires is not None and float(expires) > now


def needs_reconciliation(store: DurableStore, action_id: str, *,
                         now: Optional[float] = None) -> bool:
    ts = time.time() if now is None else float(now)
    action = store.get_action(action_id)
    state = action["state"]
    dangling = _unresolved(store, action_id)
    if _lease_live(action, ts) and dangling is not None:
        return False                      # a worker is mid-send right now
    if state == STATE_UNKNOWN:
        return True
    if state == STATE_DISPATCHED:
        return True                       # sent, no ACK yet: reconcile the ACK
    if state == STATE_QUEUED and dangling is not None:
        return True                       # crashed mid-send: possibly sent
    return False


def sweep_inflight(store: DurableStore, *, now: Optional[float] = None) -> List[str]:
    """Recovery sweep on restart: make dead-mid-send actions explicitly unknown.

    A process killed between provider acceptance and receipt persistence leaves
    state='queued' plus an open attempt. Claiming is already blocked, but the
    truthful state is unknown. This promotes each such action to 'unknown'
    WITHOUT closing its attempt, so reconciliation still sees the possibly-sent
    evidence. It never sends and never touches a live lease. Returns the ids
    promoted, for the caller's startup log.
    """
    return store.mark_dead_inflight_unknown("restart_after_crash", now=now)

def resolve_unknown(store: DurableStore,
                    action_id: str,
                    resolver: Callable[[Dict[str, Any]], Any], *,
                    now: Optional[float] = None) -> ReconciliationOutcome:
    """Resolve one unknown/in-flight action from provider evidence.

    The resolver signature is (context) -> {"outcome": applied|not_applied|
    unknown, "receipt": {...}, "evidence": {...}} or a bare outcome string.
    When 'applied', the receipt must be a provider receipt dict.
    """
    if not callable(resolver):
        raise DurableStoreError("bad_input: resolver must be callable")
    ts = time.time() if now is None else float(now)
    action = store.get_action(action_id)
    state = action["state"]
    dangling = _unresolved(store, action_id)

    if _lease_live(action, ts) and dangling is not None:
        return ReconciliationOutcome(R_IN_FLIGHT, action_id, state,
                                     note="lease still live; a worker may be mid-send")
    if not needs_reconciliation(store, action_id, now=ts):
        return ReconciliationOutcome(R_NOT_NEEDED, action_id, state,
                                     note="no unknown effect to resolve")

    ctx = {
        "action": action,
        "action_id": action_id,
        "idempotency_key": action["idempotency_key"],
        "attempt_no": dangling["attempt_no"] if dangling else None,
        "receipts": store.receipts(action_id),
    }
    try:
        raw = resolver(dict(ctx))
    except Exception as exc:
        store.mark_reconcile_unknown(
            action_id, f"resolver_exception:{type(exc).__name__}:{exc}", now=ts)
        store.record_reconciliation(action_id, R_UNKNOWN,
                                    {"error": repr(exc)}, now=ts)
        return ReconciliationOutcome(R_UNKNOWN, action_id,
                                     store.get_action(action_id)["state"],
                                     note="resolver raised; left unknown, nothing resent")

    if isinstance(raw, str):
        outcome, receipt, evidence = raw, None, {}
    elif isinstance(raw, dict):
        outcome = raw.get("outcome")
        receipt = raw.get("receipt")
        evidence = raw.get("evidence") or {}
    else:
        outcome, receipt, evidence = None, None, {}
    if outcome not in RECONCILE_OUTCOMES:
        outcome, receipt, evidence = R_UNKNOWN, None, {
            "bad_resolver_outcome": str(outcome)}

    attempt_no = dangling["attempt_no"] if dangling else None

    if outcome == R_APPLIED:
        if not isinstance(receipt, dict) or not receipt.get("provider"):
            # Applied without a provider receipt is not evidence. Fail closed.
            store.mark_reconcile_unknown(
                action_id, "resolver_applied_without_provider_receipt", now=ts)
            store.record_reconciliation(action_id, R_UNKNOWN, evidence, now=ts)
            return ReconciliationOutcome(
                R_UNKNOWN, action_id, store.get_action(action_id)["state"],
                attempt_no=attempt_no,
                note="applied without a provider receipt is not evidence")
        # A post/reveal receipt is only evidence when it is the provider's OWN
        # object, not a claim or a local id echoed back. A non-publication item
        # has no post/comment kind, so the publication rule does not apply.
        receipt_errors: List[str] = []
        try:
            item_kind(action.get("purpose"))
        except ReceiptError:
            pass
        else:
            receipt_errors = validate_provider_receipt(action, receipt)
        if receipt_errors:
            # Applied without a true provider receipt is not evidence. Fail closed.
            store.mark_reconcile_unknown(
                action_id, "resolver_applied_without_true_provider_receipt", now=ts)
            store.record_reconciliation(
                action_id, R_UNKNOWN,
                {"receipt_errors": receipt_errors, **evidence}, now=ts)
            return ReconciliationOutcome(
                R_UNKNOWN, action_id, store.get_action(action_id)["state"],
                attempt_no=attempt_no,
                note="applied without a true provider receipt is not evidence")
        try:
            after = store.reconcile_applied(action_id, receipt, now=ts)
        except DurableStoreError as exc:
            store.record_reconciliation(action_id, R_REFUSED, {"error": str(exc)}, now=ts)
            return ReconciliationOutcome(R_REFUSED, action_id,
                                         store.get_action(action_id)["state"],
                                         attempt_no=attempt_no, note=str(exc))
        store.record_reconciliation(action_id, R_APPLIED,
                                    {"receipt": receipt, **evidence}, now=ts)
        return ReconciliationOutcome(R_APPLIED, action_id, after["state"],
                                     attempt_no=attempt_no, evidence=evidence,
                                     note="provider has the effect; acknowledged,"
                                          " not completed")

    if outcome == R_NOT_APPLIED:
        try:
            after = store.reconcile_not_applied(action_id, now=ts)
        except DurableStoreError as exc:
            store.record_reconciliation(action_id, R_REFUSED, {"error": str(exc)}, now=ts)
            return ReconciliationOutcome(R_REFUSED, action_id,
                                         store.get_action(action_id)["state"],
                                         attempt_no=attempt_no, note=str(exc))
        store.record_reconciliation(action_id, R_NOT_APPLIED, evidence, now=ts)
        return ReconciliationOutcome(R_NOT_APPLIED, action_id, after["state"],
                                     attempt_no=attempt_no, evidence=evidence,
                                     note="provider does not have it; requeued under the"
                                          " same identity, next dispatch needs a fresh gate")

    store.mark_reconcile_unknown(action_id,
                                 str(evidence.get("reason", "resolver_unknown")),
                                 now=ts)
    store.record_reconciliation(action_id, R_UNKNOWN, evidence, now=ts)
    return ReconciliationOutcome(R_UNKNOWN, action_id,
                                 store.get_action(action_id)["state"],
                                 attempt_no=attempt_no, evidence=evidence,
                                 note="unresolved; attempt stays open, no resend possible")


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> int:
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="recon-selfcheck-"))
    store = DurableStore(str(d / "r.sqlite"))
    passed = 0
    sent: list = []

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    row, _ = store.create_intent(logical_intent_key="L", idempotency_key="K",
                                 tenant_id="t", scope="person_directed",
                                 canonical_contact_id="c", content_sha256="h")
    aid = row["action_id"]
    store.queue(aid)
    claim = store.claim_for_dispatch(aid, "w1", now=100.0, lease_seconds=10)
    ok(claim is not None, "claimed")
    ok(store.begin_attempt(aid, claim["fence"], "w1", now=101.0) is True,
       "attempt began, then imagine the process died")

    ok(needs_reconciliation(store, aid, now=102.0) is False,
       "no recovery while the lease is live")
    ok(needs_reconciliation(store, aid, now=200.0) is True,
       "expired lease with an open attempt needs reconciliation")
    ok(store.claim_for_dispatch(aid, "w2", now=200.0) is None,
       "a crashed send can never be re-claimed")
    ok(sent == [], "nothing sent by reconciliation")

    out = resolve_unknown(store, aid,
                          lambda ctx: {"outcome": "applied",
                                       "receipt": {"provider": "ghl",
                                                   "provider_receipt_id": "r9"}},
                          now=201.0)
    ok(out.status == R_APPLIED and out.state_after == "acknowledged",
       "applied resolves to acknowledged")
    ok(sent == [], "applied resolution sent nothing")
    ok(set(store.receipts(aid)) == {"dispatch", "ack"},
       "dispatch and ack receipts are separate; completion is not claimed")

    row, _ = store.create_intent(logical_intent_key="L2", idempotency_key="K2",
                                 tenant_id="t", scope="person_directed",
                                 canonical_contact_id="c", content_sha256="h")
    aid2 = row["action_id"]
    store.queue(aid2)
    claim = store.claim_for_dispatch(aid2, "w1", now=300.0, lease_seconds=1)
    store.begin_attempt(aid2, claim["fence"], "w1", now=301.0)
    out = resolve_unknown(store, aid2, lambda ctx: "not_applied", now=400.0)
    ok(out.status == R_NOT_APPLIED and out.state_after == STATE_QUEUED,
       "not_applied requeues the same action")
    ok(store.get_action(aid2)["action_id"] == aid2, "same identity kept")
    ok(store.claim_for_dispatch(aid2, "w3", now=401.0) is not None,
       "requeued action can be claimed again, through a fresh gate")

    row, _ = store.create_intent(logical_intent_key="L3", idempotency_key="K3",
                                 tenant_id="t", scope="person_directed",
                                 canonical_contact_id="c", content_sha256="h")
    aid3 = row["action_id"]
    store.queue(aid3)
    claim = store.claim_for_dispatch(aid3, "w1", now=500.0, lease_seconds=1)
    store.begin_attempt(aid3, claim["fence"], "w1", now=501.0)
    out = resolve_unknown(store, aid3, lambda ctx: "unknown", now=600.0)
    ok(out.status == R_UNKNOWN and store.get_action(aid3)["state"] == STATE_UNKNOWN,
       "unknown stays unknown")
    ok(store.claim_for_dispatch(aid3, "w9", now=900.0) is None,
       "unresolved action can never be claimed")

    store.close()
    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
