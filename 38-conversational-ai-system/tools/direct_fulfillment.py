#!/usr/bin/env python3
"""direct_fulfillment.py - deliver the original promised item directly.

Contract basis: Purple-Billboard DATA-CONTRACTS.md section 5 ("Direct original
fulfillment") and sections 2-4. Python 3 standard library only.

What this module exists to guarantee:

IMMUTABLE.  A promised item is (item_id, version, content_sha256). A hosting
            URL is optional metadata, never identity: moving the file does not
            mint a new promise, and a different content hash under the same
            item id/version is refused. There is no dependency on any bonus
            access module, vendor API or third-party fulfillment service.

AT-MOST-ONCE.  Every externally visible effect is one outbox action sent
            through outbound_gate.dispatch() and durable_store's fenced lease.
            A retry cannot double-send: the second call finds the same action
            and never reaches the transport. No second guard is written here.

EVIDENCE.  Provider admission is labelled accepted/sent, never "delivered".
            A completion receipt exists only when the caller supplies an
            actual delivery/access receipt that matches the pinned content
            hash and recorded destination.

RESUME.     A crash between provider acceptance and receipt persistence leaves
            state unknown. resume() reconciles against the transport's own
            journal through reconciliation.resolve_unknown(), so the effect is
            never sent twice. Known nonexecution may be retried under the SAME
            action identity after a fresh gate.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from direct_fulfillment import (DeliveryBasis, Destination, FulfillmentLedger,
                                    JournalTransport, PromisedItem, fulfill)

Assert-based self-check:  python3 -I direct_fulfillment.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Direct-script execution does not put this directory on sys.path.
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from durable_store import (  # noqa: E402
    DurableStore,
    DurableStoreError,
    STATE_ACKNOWLEDGED,
    STATE_CANCELED,
    STATE_COMPLETED,
    STATE_DISPATCHED,
    STATE_FAILED,
    STATE_QUARANTINED,
    STATE_QUEUED,
    STATE_SUPPRESSED,
    STATE_UNKNOWN,
)
from outbound_gate import (  # noqa: E402
    ST_BLOCKED,
    ST_NOT_CLAIMED,
    ST_SEND_ERROR,
    ST_SENT,
    ST_UNKNOWN,
    answer_duty_evaluator,
    dispatch,
)
from reconciliation import (  # noqa: E402
    R_APPLIED,
    R_NOT_APPLIED,
    needs_reconciliation,
    resolve_unknown,
    sweep_inflight,
)

# FulfillmentOutcome.status values.
F_SENT = "sent"                          # provider admission for this call
F_ALREADY_SATISFIED = "already_satisfied"  # same action already dispatched/ack/completed
F_SUPPRESSED = "suppressed"              # gate refused: no basis, opt-out, human fence
F_BLOCKED = "blocked"                    # queued but not claimable (deferred/leased)
F_UNKNOWN = "unknown"                    # possibly sent; reconcile before anything else
F_REFUSED = "refused"                    # caller input or promise is not acceptable
F_RESUMED = "resumed"                    # reconciliation ran
F_NOTHING_TO_DO = "nothing_to_do"        # nothing to reconcile and not retried

# Delivery labels. "delivered" needs a real receipt; admission is "accepted".
D_ACCEPTED = "accepted"
D_DELIVERED = "delivered"
D_NOT_SENT = "not_sent"
D_UNKNOWN = "unknown"
D_FAILED = "failed"

BASES = ("requested_in_conversation", "owner_approved")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class FulfillmentError(ValueError):
    """Bad input or an illegal fulfillment transition. Always fail closed."""


# ── what was promised ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class PromisedItem:
    """The immutable original promise. Hosting location is not identity."""
    item_id: str
    version: str
    content_sha256: str
    approved: bool = False
    content_uri: Optional[str] = None   # current host; may move, must not matter

    def validated(self) -> "PromisedItem":
        for name in ("item_id", "version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise FulfillmentError(f"bad_input: {name} must be non-empty")
        if not isinstance(self.content_sha256, str) or not _HEX64.match(
                self.content_sha256):
            raise FulfillmentError(
                "bad_input: content_sha256 must be 64 lowercase hex characters")
        if not self.approved:
            raise FulfillmentError(
                "not_approved: the original promised item is not approved")
        if self.content_uri is not None and not isinstance(self.content_uri, str):
            raise FulfillmentError("bad_input: content_uri must be text or None")
        return self

    def identity(self) -> Dict[str, str]:
        """Identity excludes content_uri: a host migration is not a new promise."""
        return {"item_id": self.item_id, "version": self.version,
                "content_sha256": self.content_sha256}

    def matches(self, data: bytes) -> bool:
        return hashlib.sha256(data).hexdigest() == self.content_sha256


@dataclass(frozen=True)
class Destination:
    channel: str
    address: str

    def validated(self) -> "Destination":
        for name in ("channel", "address"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise FulfillmentError(f"bad_input: destination {name} must be non-empty")
        return self

    def as_record(self) -> Dict[str, str]:
        return {"channel": self.channel, "address": self.address}


@dataclass(frozen=True)
class DeliveryBasis:
    """Why this person may receive the original item, and where it goes."""
    tenant_id: str
    canonical_contact_id: str
    item_id: str
    version: str
    basis: str
    actor: str
    evidence: str
    channel: str
    address: str

    def validated(self) -> "DeliveryBasis":
        for name in ("tenant_id", "canonical_contact_id", "item_id", "version",
                     "actor", "evidence", "channel", "address"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise FulfillmentError(f"bad_input: basis {name} must be non-empty")
        if self.basis not in BASES:
            raise FulfillmentError(
                f"bad_input: basis {self.basis!r} not in {BASES}")
        return self

    def destination(self) -> Destination:
        return Destination(self.channel, self.address).validated()


# ── durable delivery basis and reader-access observation ───────────────────

_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS delivery_bases (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    item_id              TEXT NOT NULL,
    version              TEXT NOT NULL,
    basis                TEXT NOT NULL,
    actor                TEXT NOT NULL,
    evidence             TEXT NOT NULL,
    channel              TEXT NOT NULL,
    address              TEXT NOT NULL,
    recorded_at          REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id, item_id, version)
);
CREATE TABLE IF NOT EXISTS reader_access (
    tenant_id   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    version     TEXT NOT NULL,
    accessible  INTEGER NOT NULL,
    evidence    TEXT NOT NULL,
    recorded_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, item_id, version)
);
"""


class FulfillmentLedger:
    """Durable proof of the delivery basis and intended-reader accessibility.

    One SQLite file, stdlib only. It stores decisions, never effects: the
    at-most-once guard for effects is the accepted T-12 outbox.
    """

    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, timeout=30.0, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        try:
            self._db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        with self._db:
            self._db.executescript(_LEDGER_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def record_basis(self, basis: DeliveryBasis) -> Dict[str, Any]:
        """Write the basis once. Repeating it is a no-op and returns the row."""
        basis.validated()
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO delivery_bases (tenant_id,"
                " canonical_contact_id, item_id, version, basis, actor, evidence,"
                " channel, address, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (basis.tenant_id, basis.canonical_contact_id, basis.item_id,
                 basis.version, basis.basis, basis.actor, basis.evidence,
                 basis.channel, basis.address, time.time()),
            )
        return self.basis(basis.tenant_id, basis.canonical_contact_id,
                          basis.item_id, basis.version)

    def basis(self, tenant_id: str, canonical_contact_id: str, item_id: str,
              version: str) -> Optional[Dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM delivery_bases WHERE tenant_id=? AND"
            " canonical_contact_id=? AND item_id=? AND version=?",
            (tenant_id, canonical_contact_id, item_id, version)).fetchone()
        return dict(row) if row is not None else None

    def record_reader_access(self, tenant_id: str, item_id: str, version: str,
                             *, accessible: bool, evidence: str) -> Dict[str, Any]:
        """An observed fact supplied by the caller. Never inferred here."""
        for name, value in (("tenant_id", tenant_id), ("item_id", item_id),
                            ("version", version), ("evidence", evidence)):
            if not isinstance(value, str) or not value.strip():
                raise FulfillmentError(f"bad_input: reader_access {name} must be non-empty")
        with self._db:
            self._db.execute(
                "INSERT INTO reader_access (tenant_id, item_id, version, accessible,"
                " evidence, recorded_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(tenant_id, item_id, version) DO UPDATE SET"
                " accessible=excluded.accessible, evidence=excluded.evidence,"
                " recorded_at=excluded.recorded_at",
                (tenant_id, item_id, version, 1 if accessible else 0, evidence,
                 time.time()),
            )
        return self.reader_access(tenant_id, item_id, version)

    def reader_access(self, tenant_id: str, item_id: str,
                      version: str) -> Optional[Dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM reader_access WHERE tenant_id=? AND item_id=?"
            " AND version=?", (tenant_id, item_id, version)).fetchone()
        return dict(row) if row is not None else None


# ── offline transport with its own journal ─────────────────────────────────

class JournalTransport:
    """A local, append-only transport that is idempotent per idempotency key.

    It stands in for the channel transport in tests and local runs: no network,
    no third-party service. The journal is the provider's own record of what it
    accepted, which is what resume() reconciles against.
    """

    def __init__(self, path: str, *, provider: str = "journal") -> None:
        self.path = Path(path)
        self.provider = provider

    def _rows(self):
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def find(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        for row in self._rows():
            if row.get("idempotency_key") == idempotency_key:
                return row
        return None

    @property
    def sends(self) -> int:
        return len(self._rows())

    def __call__(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        key = ctx["idempotency_key"]
        existing = self.find(key)
        if existing is not None:
            return dict(existing, duplicate=True)
        item = ctx["item"]
        destination = ctx["destination"]
        receipt = {
            "provider": self.provider,
            "provider_receipt_id": "jrn_" + key[:16],
            "idempotency_key": key,
            "item_id": item["item_id"],
            "version": item["version"],
            "content_sha256": item["content_sha256"],
            "destination": dict(destination),
            "accepted_at": ctx.get("now", time.time()),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return receipt


# ── the one effect: dispatch the original item ─────────────────────────────

@dataclass(frozen=True)
class FulfillmentOutcome:
    status: str
    reason: str = ""
    action_id: Optional[str] = None
    state: Optional[str] = None
    item_id: Optional[str] = None
    version: Optional[str] = None
    destination: Dict[str, str] = field(default_factory=dict)
    transport_receipt: Optional[Dict[str, Any]] = None
    delivery_status: str = D_NOT_SENT
    continuation_allowed: bool = False
    continuation_reason: str = ""


def _intent_key(basis: DeliveryBasis) -> str:
    return "fulfill:%s:%s:%s:%s" % (
        basis.tenant_id, basis.canonical_contact_id, basis.item_id, basis.version)


def _idempotency_key(intent_key: str, content_sha256: str) -> str:
    return "idem_" + hashlib.sha256(
        (intent_key + "|" + content_sha256).encode("utf-8")).hexdigest()


def _basis_evaluator(ledger: FulfillmentLedger,
                     basis: DeliveryBasis) -> Callable[[Dict[str, Any]], Any]:
    """Fresh gate check: the durable basis must still exist at dispatch time."""
    def evaluator(_ctx: Dict[str, Any]) -> Dict[str, Any]:
        row = ledger.basis(basis.tenant_id, basis.canonical_contact_id,
                           basis.item_id, basis.version)
        if row is None:
            return {"verdict": "SUPPRESSED",
                    "evidence": {"reason": "no_delivery_basis"}}
        return {"verdict": "ALLOW",
                "evidence": {"basis": row["basis"], "actor": row["actor"]}}
    return evaluator


def _compose(first: Callable[[Dict[str, Any]], Any],
             second: Optional[Callable[[Dict[str, Any]], Any]]
             ) -> Callable[[Dict[str, Any]], Any]:
    """Both gates must pass. The stricter answer wins; anything not ALLOW blocks."""
    if second is None:
        return first

    def evaluator(ctx: Dict[str, Any]) -> Any:
        left = first(ctx)
        left_verdict = left if isinstance(left, str) else left.get("verdict")
        if left_verdict != "ALLOW":
            return left
        return second(ctx)
    return evaluator


def _delivery_status(store: DurableStore, action_id: str) -> str:
    state = store.get_action(action_id)["state"]
    if state == STATE_COMPLETED:
        return D_DELIVERED
    if state in (STATE_DISPATCHED, STATE_ACKNOWLEDGED):
        return D_ACCEPTED
    if state == STATE_UNKNOWN:
        return D_UNKNOWN
    if state == STATE_FAILED:
        return D_FAILED
    return D_NOT_SENT


def fulfillment_action(store: DurableStore, basis: DeliveryBasis
                       ) -> Optional[Dict[str, Any]]:
    return store.action_by_intent(_intent_key(basis))


def can_continue(store: DurableStore, ledger: FulfillmentLedger,
                 item: PromisedItem, basis: DeliveryBasis) -> FulfillmentOutcome:
    """DATA-CONTRACTS section 5: continuation needs every fact, not just a send."""
    item.validated()
    basis.validated()
    action = fulfillment_action(store, basis)
    if action is None:
        return FulfillmentOutcome(
            F_BLOCKED, reason="no_fulfillment", continuation_allowed=False,
            continuation_reason="original item has not been sent")
    state = action["state"]
    status = _delivery_status(store, action["action_id"])
    base = dict(action_id=action["action_id"], state=state,
                item_id=item.item_id, version=item.version,
                destination=basis.destination().as_record(),
                delivery_status=status)
    if state not in (STATE_DISPATCHED, STATE_ACKNOWLEDGED, STATE_COMPLETED):
        return FulfillmentOutcome(
            F_BLOCKED, reason="not_sent_or_unknown", **base,
            continuation_allowed=False,
            continuation_reason="no supported successful transport status")
    access = ledger.reader_access(basis.tenant_id, item.item_id, item.version)
    if access is None or not access["accessible"]:
        return FulfillmentOutcome(
            F_BLOCKED, reason="reader_access_unverified", **base,
            continuation_allowed=False,
            continuation_reason="intended-reader accessibility is not verified")
    return FulfillmentOutcome(
        F_ALREADY_SATISFIED, reason="continuation_ready", **base,
        continuation_allowed=True,
        continuation_reason="approved immutable item, accessible to the reader,"
                            " correct destination, transport %s, no known failure"
                            % status)


def fulfill(store: DurableStore, ledger: FulfillmentLedger,
            transport: Callable[[Dict[str, Any]], Dict[str, Any]],
            item: PromisedItem, basis: DeliveryBasis, *, worker_id: str,
            consent_evaluator: Optional[Callable[[Dict[str, Any]], Any]] = None,
            answer_duty_log: Optional[str] = None,
            answer_channel: Optional[str] = None,
            now: Optional[float] = None) -> FulfillmentOutcome:
    """Send the original item once. Safe to call again: never double-sends.

    When the send answers a turn, pass the turn's conversational log as
    ``answer_duty_log`` and the channel it will answer on: the T-26 clause (d)
    duty gate then refuses a channel the log's last ``- duty:`` forbids. An
    original-gift send answers nothing, so the gate stands down for it.
    """
    item.validated()
    basis.validated()
    if item.item_id != basis.item_id or item.version != basis.version:
        raise FulfillmentError(
            "bad_input: delivery basis names a different promised item/version")
    destination = basis.destination()
    if ledger.basis(basis.tenant_id, basis.canonical_contact_id,
                    basis.item_id, basis.version) is None:
        # No durable requested-delivery basis: never mint one from the call.
        return FulfillmentOutcome(
            F_REFUSED, reason="no_delivery_basis",
            item_id=item.item_id, version=item.version,
            destination=destination.as_record(),
            continuation_reason="record a delivery basis before fulfillment")

    intent_key = _intent_key(basis)
    idem_key = _idempotency_key(intent_key, item.content_sha256)
    row, created = store.create_intent(
        logical_intent_key=intent_key, idempotency_key=idem_key,
        tenant_id=basis.tenant_id, scope="person_directed",
        canonical_contact_id=basis.canonical_contact_id,
        content_sha256=item.content_sha256, purpose="original_gift",
        binding_revision=item.version, now=now)
    action_id = row["action_id"]

    # Immutability: same item id/version may never carry different content.
    if row["content_sha256"] != item.content_sha256:
        raise FulfillmentError(
            "immutable_violation: item %s v%s already pinned to another content hash"
            % (item.item_id, item.version))

    def outcome(status: str, reason: str, **extra: Any) -> FulfillmentOutcome:
        return FulfillmentOutcome(
            status, reason, action_id=action_id,
            state=extra.pop("state", store.get_action(action_id)["state"]),
            item_id=item.item_id, version=item.version,
            destination=destination.as_record(), **extra)

    state = store.get_action(action_id)["state"]
    if state in (STATE_DISPATCHED, STATE_ACKNOWLEDGED, STATE_COMPLETED):
        return outcome(F_ALREADY_SATISFIED, "already_sent", state=state,
                       delivery_status=_delivery_status(store, action_id),
                       continuation_allowed=False,
                       continuation_reason="already sent under the same action identity")
    if state in (STATE_FAILED,):
        raise FulfillmentError("illegal_transition: failed action; start a new promise")
    if state in (STATE_SUPPRESSED, STATE_QUARANTINED, STATE_CANCELED):
        return outcome(F_SUPPRESSED, reason="gate_terminal_state", state=state,
                       continuation_reason="a gate refused this action permanently")

    store.queue(action_id, now=now)

    # Basis, then the T-26 clause (d) answer duty, then consent: every gate must
    # pass. The duty gate only bites when the caller says this send answers a
    # turn (answer_duty_log supplied).
    evaluator = _compose(
        _compose(_basis_evaluator(ledger, basis), answer_duty_evaluator()),
        consent_evaluator)
    payload = {"item": item.identity(), "content_uri": item.content_uri,
               "destination": destination.as_record()}

    def sender(ctx: Dict[str, Any]) -> Dict[str, Any]:
        return transport({**ctx, **payload})

    out = dispatch(store, evaluator, sender, action_id, worker_id, now=now,
                   context={"answer_duty_log": answer_duty_log,
                            "channel": answer_channel})

    if out.status == ST_SENT:
        return outcome(
            F_SENT, "provider accepted the original item",
            transport_receipt=out.provider_receipt, delivery_status=D_ACCEPTED,
            continuation_reason="accepted is not delivered; continuation also needs"
                                " a supported transport status and no known failure")
    if out.status == ST_BLOCKED:
        return outcome(F_SUPPRESSED, out.note or out.verdict or "gate_blocked")
    if out.status in (ST_UNKNOWN, ST_SEND_ERROR):
        return outcome(
            F_UNKNOWN, out.note or "no_verdict", delivery_status=D_UNKNOWN,
            continuation_reason="outcome unknown; reconcile before any retry")
    if out.status == ST_NOT_CLAIMED:
        state = store.get_action(action_id)["state"]
        if state in (STATE_DISPATCHED, STATE_ACKNOWLEDGED, STATE_COMPLETED):
            return outcome(F_ALREADY_SATISFIED, "already_sent", state=state,
                           delivery_status=_delivery_status(store, action_id))
        return outcome(F_BLOCKED, out.note or "not_claimable", state=state)
    return outcome(F_BLOCKED, out.status)


def _journal_resolver(transport: Callable[..., Any]) -> Callable[[Dict[str, Any]], Any]:
    def resolver(ctx: Dict[str, Any]) -> Dict[str, Any]:
        finder = getattr(transport, "find", None)
        receipt = finder(ctx["idempotency_key"]) if callable(finder) else None
        if receipt is None:
            return {"outcome": "not_applied",
                    "evidence": {"journal": "no accepted effect for this key"}}
        return {"outcome": "applied", "receipt": dict(receipt),
                "evidence": {"journal": "accepted effect found for this key"}}
    return resolver


def resume(store: DurableStore, ledger: FulfillmentLedger,
           transport: Callable[..., Any], item: PromisedItem,
           basis: DeliveryBasis, *, worker_id: str,
           consent_evaluator: Optional[Callable[[Dict[str, Any]], Any]] = None,
           retry: bool = False, now: Optional[float] = None) -> FulfillmentOutcome:
    """Resolve a possibly-sent original item without sending it twice.

    Never sends unless reconciliation proves the effect does NOT exist AND the
    caller asked for retry=True; that retry reuses the same action identity and
    passes a fresh gate.
    """
    item.validated()
    basis.validated()
    action = fulfillment_action(store, basis)
    if action is None:
        return FulfillmentOutcome(F_NOTHING_TO_DO, reason="no_fulfillment")
    action_id = action["action_id"]

    sweep_inflight(store, now=now)
    if not needs_reconciliation(store, action_id, now=now):
        state = store.get_action(action_id)["state"]
        if retry and state == STATE_QUEUED:
            again = fulfill(store, ledger, transport, item, basis,
                            worker_id=worker_id,
                            consent_evaluator=consent_evaluator, now=now)
            return FulfillmentOutcome(
                again.status,
                reason="retried a queued action after reconciliation: " + again.reason,
                action_id=again.action_id, state=again.state,
                item_id=again.item_id, version=again.version,
                destination=again.destination,
                transport_receipt=again.transport_receipt,
                delivery_status=again.delivery_status,
                continuation_allowed=again.continuation_allowed,
                continuation_reason=again.continuation_reason)
        return FulfillmentOutcome(
            F_NOTHING_TO_DO, reason="nothing_to_reconcile", action_id=action_id,
            state=state, item_id=item.item_id, version=item.version,
            destination=basis.destination().as_record(),
            delivery_status=_delivery_status(store, action_id))

    result = resolve_unknown(store, action_id, _journal_resolver(transport), now=now)
    state = store.get_action(action_id)["state"]
    base = dict(action_id=action_id, state=state, item_id=item.item_id,
                version=item.version, destination=basis.destination().as_record())
    if result.status == R_APPLIED:
        return FulfillmentOutcome(
            F_RESUMED, reason="provider has the effect; acknowledged, not completed",
            **base, delivery_status=D_ACCEPTED)
    if result.status == R_NOT_APPLIED:
        if not retry:
            return FulfillmentOutcome(
                F_RESUMED, reason="known nonexecution; requeued, no resend",
                **base, delivery_status=D_NOT_SENT)
        again = fulfill(store, ledger, transport, item, basis, worker_id=worker_id,
                        consent_evaluator=consent_evaluator, now=now)
        return FulfillmentOutcome(
            again.status, reason="retried after known nonexecution: " + again.reason,
            action_id=again.action_id, state=again.state, item_id=again.item_id,
            version=again.version, destination=again.destination,
            transport_receipt=again.transport_receipt,
            delivery_status=again.delivery_status,
            continuation_allowed=again.continuation_allowed,
            continuation_reason=again.continuation_reason)
    return FulfillmentOutcome(
        F_UNKNOWN, reason=result.note or "unresolved", **base,
        delivery_status=D_UNKNOWN,
        continuation_reason="outcome unresolved; no retry is possible")


def record_delivery_proof(store: DurableStore, item: PromisedItem,
                          basis: DeliveryBasis, proof: Dict[str, Any], *,
                          now: Optional[float] = None) -> FulfillmentOutcome:
    """Promote accepted -> delivered from an ACTUAL receipt. Never inferred."""
    item.validated()
    basis.validated()
    if not isinstance(proof, dict):
        raise FulfillmentError("bad_input: delivery proof must be a dict")
    for name in ("provider", "provider_receipt_id"):
        if not isinstance(proof.get(name), str) or not proof.get(name).strip():
            raise FulfillmentError(f"bad_input: proof {name} must be non-empty")
    if proof.get("content_sha256") != item.content_sha256:
        raise FulfillmentError(
            "proof_mismatch: receipt does not name the pinned content hash")
    destination = basis.destination()
    if proof.get("destination") != destination.as_record():
        raise FulfillmentError(
            "proof_mismatch: receipt does not name the recorded destination")

    action = fulfillment_action(store, basis)
    if action is None:
        raise FulfillmentError("bad_input: no fulfillment to prove")
    action_id = action["action_id"]
    state = store.get_action(action_id)["state"]
    if state == STATE_COMPLETED:
        return FulfillmentOutcome(
            F_ALREADY_SATISFIED, reason="already_delivered", action_id=action_id,
            state=state, item_id=item.item_id, version=item.version,
            destination=destination.as_record(), transport_receipt=dict(proof),
            delivery_status=D_DELIVERED)
    if state == STATE_DISPATCHED:
        store.record_ack(action_id, proof, now=now)
    elif state != STATE_ACKNOWLEDGED:
        raise FulfillmentError(
            f"illegal_transition: delivery proof from {state!r} (nothing was accepted)")
    after = store.record_completion(action_id, proof, now=now)
    return FulfillmentOutcome(
        F_ALREADY_SATISFIED, reason="delivery_verified", action_id=action_id,
        state=after["state"], item_id=item.item_id, version=item.version,
        destination=destination.as_record(), transport_receipt=dict(proof),
        delivery_status=D_DELIVERED)


# ── assert-based self-check (stdlib only) ──────────────────────────────────

def _selfcheck() -> int:
    import tempfile

    d = Path(tempfile.mkdtemp(prefix="fulfil-selfcheck-"))
    store = DurableStore(str(d / "outbox.sqlite"))
    ledger = FulfillmentLedger(str(d / "ledger.sqlite"))
    transport = JournalTransport(str(d / "journal.jsonl"))
    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    content = b"the original checklist"
    item = PromisedItem(item_id="gift-1", version="v1",
                        content_sha256=hashlib.sha256(content).hexdigest(),
                        approved=True, content_uri="https://host-a/x")
    basis = DeliveryBasis(tenant_id="t1", canonical_contact_id="c1",
                          item_id="gift-1", version="v1", basis="requested_in_conversation",
                          actor="agent", evidence="asked in chat",
                          channel="sms", address="+15550123")
    out = fulfill(store, ledger, transport, item, basis, worker_id="w1")
    ok(out.status == F_REFUSED and transport.sends == 0,
       "no basis refuses before any action or send")
    ledger.record_basis(basis)
    out = fulfill(store, ledger, transport, item, basis, worker_id="w1")
    ok(out.status == F_SENT and transport.sends == 1, "happy path sends once")
    ok(out.delivery_status == D_ACCEPTED, "admission is accepted, not delivered")
    again = fulfill(store, ledger, transport, item, basis, worker_id="w1")
    ok(again.status == F_ALREADY_SATISFIED and transport.sends == 1,
       "second call never double-sends")

    moved = PromisedItem(item_id="gift-1", version="v1",
                         content_sha256=item.content_sha256, approved=True,
                         content_uri="https://host-b/y")
    ok(fulfill(store, ledger, transport, moved, basis, worker_id="w1").status
       == F_ALREADY_SATISFIED, "host migration is the same promise")

    ledger.record_reader_access("t1", "gift-1", "v1", accessible=True,
                                evidence="operator opened the link")
    cont = can_continue(store, ledger, item, basis)
    ok(cont.continuation_allowed, "continuation allowed after access verified")
    ok(cont.delivery_status == D_ACCEPTED, "label stays accepted without a receipt")

    proof = {**out.transport_receipt}
    done = record_delivery_proof(store, item, basis, proof)
    ok(done.delivery_status == D_DELIVERED, "real receipt means delivered")

    store.close()
    ledger.close()
    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
