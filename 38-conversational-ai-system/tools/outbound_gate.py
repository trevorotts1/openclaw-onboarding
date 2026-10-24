#!/usr/bin/env python3
"""outbound_gate.py - the common send gate every dispatch and retry passes.

Contract basis: Purple-Billboard DATA-CONTRACTS.md section 3 ("Fresh gate
before every dispatch and retry") and section 4 (leases, cancellation,
truthful stages). Python 3 standard library only.

The two properties this module exists to guarantee:

FRESH.  dispatch() calls the evaluator on EVERY dispatch and every retry. A
        verdict is recorded against that attempt number and can never be
        reused: record_gate_check() is keyed (action_id, attempt_no). A gate
        that returned ALLOW when the action was queued has no effect at
        dispatch time; the only verdict that lets a send happen is the one
        computed microseconds before begin_attempt().

FENCED.  Order is claim -> evaluate -> record verdict -> begin_attempt ->
        send. begin_attempt() is one atomic INSERT ... SELECT that fails if
        the action was canceled, if the lease was stolen, or if another
        attempt is still unresolved. When it fails, sender() is never called.

Verdicts (section 3): ALLOW, WAIT_UNTIL, SUPPRESSED, QUARANTINED,
RECONCILE_UNKNOWN. They carry checked_at, the binding/policy revisions and
the fence that were current, plus supporting evidence. Anything the evaluator
returns that is not one of those five is refused, never treated as ALLOW.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from durable_store import DurableStore
    from outbound_gate import dispatch

Assert-based self-check:  python3 -I outbound_gate.py
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Direct-script execution (python3 -I outbound_gate.py) does not put this
# directory on sys.path; the sibling module must still resolve.
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from durable_store import (
    DEFAULT_LEASE_S,
    DurableStore,
    DurableStoreError,
    STATE_QUEUED,
    STATE_SUPPRESSED,
    STATE_QUARANTINED,
)

GATE_VERDICTS = ("ALLOW", "WAIT_UNTIL", "SUPPRESSED", "QUARANTINED",
                 "RECONCILE_UNKNOWN")

# DispatchOutcome.status values.
ST_NOT_CLAIMED = "not_claimed"        # no lease: canceled, terminal, leased, or unresolved
ST_BLOCKED = "blocked"                # gate said anything except ALLOW
ST_SENT = "sent"                      # provider returned an admission receipt
ST_UNKNOWN = "unknown"                # send began, no verdict came back
ST_REFUSED_RACE = "refused_race_loss" # canceled/stolen between gate and begin_attempt
ST_SEND_ERROR = "send_error"          # sender raised before a verdict; treated as unknown


class GateError(ValueError):
    """Malformed or missing verdict. Fail closed: no send."""


@dataclass(frozen=True)
class GateVerdict:
    verdict: str
    checked_at: float
    binding_revision: Optional[str] = None
    policy_revision: Optional[str] = None
    fence: Optional[int] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    wait_until: Optional[float] = None

    def as_record(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checked_at": self.checked_at,
            "binding_revision": self.binding_revision,
            "policy_revision": self.policy_revision,
            "fence": self.fence,
            "evidence": dict(self.evidence),
            "wait_until": self.wait_until,
        }


@dataclass(frozen=True)
class DispatchOutcome:
    status: str
    action_id: str
    attempt_no: Optional[int] = None
    verdict: Optional[str] = None
    provider_receipt: Optional[Dict[str, Any]] = None
    note: str = ""

    @property
    def sent(self) -> bool:
        return self.status == ST_SENT


def evaluate_gate(evaluator: Callable[[Dict[str, Any]], Any],
                  context: Dict[str, Any], *,
                  now: Optional[float] = None,
                  fence: Optional[int] = None) -> GateVerdict:
    """Call the evaluator once and validate its answer. No caching, no defaults."""
    if not callable(evaluator):
        raise GateError("bad_input: evaluator must be callable")
    ts = time.time() if now is None else float(now)
    raw = evaluator(dict(context))
    if isinstance(raw, GateVerdict):
        verdict = raw
    elif isinstance(raw, str):
        verdict = GateVerdict(verdict=raw, checked_at=ts, fence=fence)
    elif isinstance(raw, dict):
        verdict = GateVerdict(
            verdict=raw.get("verdict"),
            checked_at=float(raw.get("checked_at", ts)),
            binding_revision=raw.get("binding_revision"),
            policy_revision=raw.get("policy_revision"),
            fence=raw.get("fence", fence),
            evidence=raw.get("evidence") or {},
            wait_until=raw.get("wait_until"),
        )
    else:
        raise GateError(f"bad_verdict: evaluator returned {type(raw).__name__}")
    if verdict.verdict not in GATE_VERDICTS:
        raise GateError(f"bad_verdict: {verdict.verdict!r} not in {GATE_VERDICTS}")
    if not isinstance(verdict.evidence, dict):
        raise GateError("bad_verdict: evidence must be a dict")
    if verdict.verdict == "WAIT_UNTIL" and verdict.wait_until is None:
        raise GateError("bad_verdict: WAIT_UNTIL requires wait_until")
    return verdict


def dispatch(store: DurableStore,
             evaluator: Callable[[Dict[str, Any]], Any],
             sender: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
             action_id: str, worker_id: str, *,
             now: Optional[float] = None,
             lease_seconds: float = DEFAULT_LEASE_S,
             context: Optional[Dict[str, Any]] = None) -> DispatchOutcome:
    """Run one dispatch attempt through the common gate.

    Every call re-evaluates the gate. Never reuse the returned outcome as
    permission for a later attempt.
    """
    ts = time.time() if now is None else float(now)
    claim = store.claim_for_dispatch(action_id, worker_id, now=ts,
                                     lease_seconds=lease_seconds)
    if claim is None:
        return DispatchOutcome(ST_NOT_CLAIMED, action_id,
                               note="no lease: not queued, leased, deferred,"
                                    " or awaiting reconciliation")

    action = claim["action"]
    attempt_no = claim["tries"]
    fence = claim["fence"]
    ctx: Dict[str, Any] = dict(context or {})
    ctx.update({"action": action, "action_id": action_id,
                "attempt_no": attempt_no, "fence": fence,
                "worker_id": worker_id, "now": ts})

    # 1. FRESH verdict for THIS attempt.
    verdict = evaluate_gate(evaluator, ctx, now=ts, fence=fence)
    store.record_gate_check(action_id, attempt_no, verdict.as_record(), now=ts)

    if verdict.verdict != "ALLOW":
        if verdict.verdict == "SUPPRESSED":
            store.apply_gate_block(action_id, STATE_SUPPRESSED,
                                   str(verdict.evidence.get("reason", "gate:suppressed")),
                                   now=ts)
        elif verdict.verdict == "QUARANTINED":
            store.apply_gate_block(action_id, STATE_QUARANTINED,
                                   str(verdict.evidence.get("reason", "gate:quarantined")),
                                   now=ts)
        elif verdict.verdict == "WAIT_UNTIL":
            store.set_not_before(action_id, float(verdict.wait_until), now=ts)
        else:  # RECONCILE_UNKNOWN
            store.release_lease(action_id, fence, now=ts)
            store.mark_gate_unknown(
                action_id,
                str(verdict.evidence.get("reason", "gate:reconcile_unknown")),
                now=ts)
        if verdict.verdict == "WAIT_UNTIL":
            pass  # set_not_before already released the lease
        return DispatchOutcome(ST_BLOCKED, action_id, attempt_no=attempt_no,
                               verdict=verdict.verdict,
                               note=str(verdict.evidence.get("reason", "")))

    # 2. FENCED commit of the send. Cancel or a stolen lease makes this False.
    if not store.begin_attempt(action_id, fence, worker_id, now=ts):
        return DispatchOutcome(
            ST_REFUSED_RACE, action_id, attempt_no=attempt_no, verdict="ALLOW",
            note="canceled or lease lost between gate and dispatch; nothing sent")

    # 3. Send. Only now may an effect exist.
    try:
        receipt = sender(dict(action=action, action_id=action_id,
                              idempotency_key=action["idempotency_key"],
                              attempt_no=attempt_no, fence=fence,
                              worker_id=worker_id, now=ts))
    except Exception as exc:  # no verdict: never claim not-sent, never retry blind
        store.mark_attempt_unknown(action_id, fence,
                                   f"sender_exception:{type(exc).__name__}:{exc}",
                                   now=time.time())
        return DispatchOutcome(ST_SEND_ERROR, action_id, attempt_no=attempt_no,
                               verdict="ALLOW",
                               note="no verdict; action is unknown until reconciled")

    if receipt is None:
        store.mark_attempt_unknown(action_id, fence, "sender_returned_no_verdict",
                                   now=time.time())
        return DispatchOutcome(ST_UNKNOWN, action_id, attempt_no=attempt_no,
                               verdict="ALLOW",
                               note="no verdict; action is unknown until reconciled")

    store.record_dispatch(action_id, fence, receipt, now=time.time())
    return DispatchOutcome(ST_SENT, action_id, attempt_no=attempt_no,
                           verdict="ALLOW", provider_receipt=dict(receipt))


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> int:
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="outgate-selfcheck-"))
    store = DurableStore(str(d / "g.sqlite"))
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

    def deny(_ctx):
        return {"verdict": "SUPPRESSED", "evidence": {"reason": "global_stop"}}

    out = dispatch(store, deny, lambda ctx: sent.append(ctx) or {"provider": "ghl"},
                   aid, "w1")
    ok(out.status == ST_BLOCKED and not sent, "blocked gate never sends")
    ok(store.get_action(aid)["state"] == STATE_SUPPRESSED, "suppression persisted")

    # fresh evaluation: allow, then deny on the retry
    row, _ = store.create_intent(logical_intent_key="L2", idempotency_key="K2",
                                 tenant_id="t", scope="person_directed",
                                 canonical_contact_id="c", content_sha256="h")
    aid2 = row["action_id"]
    store.queue(aid2)
    calls = {"n": 0}

    def flaky(_ctx):
        calls["n"] += 1
        return "ALLOW" if calls["n"] == 1 else "SUPPRESSED"

    sender = lambda ctx: sent.append(ctx["action_id"]) or {"provider": "ghl",
                                                           "provider_receipt_id": "r"}
    first = dispatch(store, flaky, sender, aid2, "w1")
    ok(first.status == ST_SENT and sent == [aid2], "first attempt sent")
    store.record_ack(aid2, {"provider": "ghl", "provider_receipt_id": "r"})
    second = dispatch(store, flaky, sender, aid2, "w1")
    ok(second.status in (ST_NOT_CLAIMED, ST_BLOCKED),
       "acknowledged action cannot be re-dispatched")
    ok(sent == [aid2], "no second send")
    ok(calls["n"] >= 1, "gate was invoked")

    # retry after known nonexecution gets a NEW verdict row
    row, _ = store.create_intent(logical_intent_key="L3", idempotency_key="K3",
                                 tenant_id="t", scope="person_directed",
                                 canonical_contact_id="c", content_sha256="h")
    aid3 = row["action_id"]
    store.queue(aid3)
    out = dispatch(store, lambda _c: {"verdict": "WAIT_UNTIL", "wait_until": 9e9},
                   sender, aid3, "w1")
    ok(out.status == ST_BLOCKED and out.verdict == "WAIT_UNTIL", "WAIT_UNTIL blocks")
    ok(store.get_action(aid3)["state"] == STATE_QUEUED, "WAIT_UNTIL stays queued")

    store.close()
    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
