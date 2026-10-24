"""S44-06/07 production purchase processor on the durable store.

The L1 PurchaseProcessor's semantics (work/events/events.py) with the
in-memory stand-ins replaced by the S44-05 durable store:

- short, wait-free spine: validate → inbox record-if-unseen → per-line
  grants → per-line fulfillment action → buyer registration → verified
  purchase tag action. Enrollment and long sequences are downstream
  actions, never steps here (A18: a long campaign can never block a
  later purchase);
- grants happen only from verified `succeeded` payment state;
- every effect is a claimed ledger action first, so concurrent or
  repeated processing never multiplies effects, and an executor whose
  outcome is unknown parks the action instead of completing it;
- fulfillment is its own claimed action per granted line, created from
  the verified event — it never depends on a thank-you page visit (A20);
- the verified-purchase tag application is a claimed action executed
  through the injected applier (the engine-side seam of DESIGN-S44-06
  section 1); with no applier configured the action stays claimed —
  visible outstanding work, never silently done;
- suppression (A21) is the store's authority check: active entitlement
  state, rechecked at dispatch time, never at enqueue time.

Execution ownership and rights reconciliation (audit lane L08):

- grants are claimed per entitlement: the durable right key carries the
  entitlement identity, so a line with several entitlements records each
  one instead of collapsing onto the line's first;
- a replay of an already-processed bundle reconciles the event's expected
  rights against the book — a right the claim says was granted but the
  book never recorded is recorded now; a revoked right is never
  resurrected, and a parked (unknown) right is left visible;
- every external effect (tag application, fulfillment execution) runs
  under the store's durable lease with a fencing token rechecked at the
  moment of the write, so two workers cannot produce two effects;
- a lost acknowledgement parks the action; it is retried only after a
  reconciler confirms the remote effect did not happen, and a confirmed
  remote success is marked done without executing again.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional

import jsonschema

# Staging note: the work-tree original imported validate_event from
# the L1 events module (work/events/events.py), which is staged
# separately and is not part of this package. Validation therefore
# lives here, against the schemas vendored beside the staged
# normalizer. Dual-version (schema v1.1 switch, CR-S44-001): every
# vendored candidate is registered under the version its own
# schema_version const declares — never the version its filename
# suggests — and validate_event dispatches on the event's stamped
# version, failing closed on any other, missing, or non-string
# version (the same registry/dispatch as the L1 events module).
# v1.2 acceptance (CR-S44-003, consumer side): the vendored copy is a
# byte-identical copy of shared-utils/signature_launch/events/
# purchase-event.v1.2.schema.json. Acceptance only — nothing here
# stamps 1.2, and parent_order_ref is never required, never identity,
# never used for grouping or dedupe.
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "normalizer"
_SCHEMA_CANDIDATES = [
    _SCHEMA_DIR / "purchase-event.schema.json",
    _SCHEMA_DIR / "purchase-event.v1.1.schema.json",
    _SCHEMA_DIR / "purchase-event.v1.2.schema.json",
]

_SCHEMAS: dict = {}
SCHEMA_SOURCES: dict = {}


def _register_schema(path: Path) -> None:
    try:
        schema = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    const = (schema.get("properties", {}).get("schema_version", {})
             .get("const"))
    if isinstance(const, str) and const not in _SCHEMAS:
        _SCHEMAS[const] = schema
        SCHEMA_SOURCES[const] = str(path)


for _candidate in _SCHEMA_CANDIDATES:
    if _candidate.exists():
        _register_schema(_candidate)

if "1.0" not in _SCHEMAS:
    raise FileNotFoundError(
        "purchase-event v1.0 schema not found beside the staged "
        "normalizer: "
        + ", ".join(str(p) for p in _SCHEMA_CANDIDATES))

# Back-compat surface: the single v1.0 schema this module originally
# loaded, and where it was loaded from.
_SCHEMA = _SCHEMAS["1.0"]
SCHEMA_PATH = Path(SCHEMA_SOURCES["1.0"])
SUPPORTED_SCHEMA_VERSIONS = tuple(sorted(_SCHEMAS))


def validate_event(event: dict) -> dict:
    """Validate a normalized envelope against its stamped schema
    version. Same contract as events.validate_event: v1.0 validates
    as before; v1.1 additionally allows the optional nullable
    contact_ref; v1.2 additionally allows the optional nullable
    parent_order_ref (acceptance only — parent_order_ref is never
    required and is not part of any identity, grouping, or dedupe
    key). An unknown, missing, or non-string schema_version fails
    closed, as does a non-object event. Raises on an invalid event,
    returns the event on success."""
    if not isinstance(event, dict):
        raise jsonschema.ValidationError(
            f"purchase event must be an object, got {type(event).__name__}")
    version = event.get("schema_version")
    if not isinstance(version, str) or version not in _SCHEMAS:
        raise jsonschema.ValidationError(
            f"unsupported schema_version {version!r}: fail closed "
            f"(installed schemas: {sorted(_SCHEMAS)})")
    jsonschema.validate(event, _SCHEMAS[version])
    return event


def _action_key(event: dict, line: dict, action_type: str,
                version: str) -> tuple:
    txn = event.get("native_transaction_ref") or event["native_order_ref"]
    return (event["tenant_id"], txn, line["native_line_ref"],
            action_type, version)


def _right_key(event: dict, line: dict, action_type: str,
               entitlement: str) -> tuple:
    """The durable per-entitlement right key. Entitlement identity is
    part of the key, so a line carrying several entitlements records one
    claim per entitlement instead of collapsing onto the line's first."""
    txn = event.get("native_transaction_ref") or event["native_order_ref"]
    return (event["tenant_id"], txn, line["native_line_ref"],
            action_type, entitlement)


def effect_resource_for_tag(txn_ref: str) -> str:
    """The stable idempotency key for the verified-purchase tag effect:
    one namespace per transaction, constant across retries, workers,
    and restarts, so a provider that dedupes on it applies the effect
    at most once no matter how many times the callback runs."""
    return f"effect:apply_verified_purchase_tag:{txn_ref}"


def effect_resource_for_action(action_type: str, txn_ref: str,
                               line_ref: str) -> str:
    """The stable idempotency key for a per-line fulfillment effect:
    one namespace per (action, transaction, line). Same dedupe
    contract as the tag key."""
    return f"effect:{action_type}:{txn_ref}:{line_ref}"


class LeaseHeartbeat:
    """Renew an effect lease while its side effect is running.

    Guarded completion already refuses a stale owner, so a callback that
    outlives its lease cannot record a success it no longer owns — but
    without renewal a live owner loses the lease mid-flight and the effect
    parks as ``unknown``. This renews at a third of the TTL and stops as
    soon as the store reports the lease is no longer ours, so a stolen
    lease is never fought over.
    """

    def __init__(self, store, tenant: str, resource: str, holder: str,
                 fencing_token: int, ttl_seconds: float):
        self._store = store
        self._args = (tenant, resource, holder, fencing_token)
        self._ttl = float(ttl_seconds)
        self._interval = max(0.05, self._ttl / 3.0)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.renewals = 0
        self.lost = False

    def __enter__(self) -> "LeaseHeartbeat":
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="siglaunch-lease-heartbeat")
        self._thread.start()
        return self

    def __exit__(self, *exc) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 2.0)
        return False

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                renewed = self._store.renew_lease(
                    *self._args, ttl_seconds=self._ttl)
            except Exception:
                return
            if not renewed:
                self.lost = True
                return
            self.renewals += 1


class DurableProcessor:
    def __init__(self, store, tag_applier: Optional[Callable] = None,
                 purchase_tag: Optional[str] = None, version: str = "v1",
                 holder: Optional[str] = None,
                 tag_reconciler: Optional[Callable] = None,
                 lease_ttl_seconds: float = 60.0):
        self.store = store
        self.tag_applier = tag_applier
        self.purchase_tag = purchase_tag  # verbatim Phase-A string
        self.version = version
        # Execution ownership: every side effect runs under a durable
        # lease, and the fencing token it carries is rechecked at the
        # moment of the write. The holder identity is per instance, so a
        # second worker (thread, process or box) can never act as us.
        self.holder = holder or (
            f"processor-{os.getpid()}-{uuid.uuid4().hex[:12]}")
        self.tag_reconciler = tag_reconciler
        self.lease_ttl_seconds = lease_ttl_seconds

    # ── execution ownership (durable lease + fencing) ───────────────────
    def _holder(self) -> str:
        """Per-thread holder identity. A lease held by one thread is
        never silently renewed for another thread of the same processor,
        so same-process concurrency is excluded exactly like another
        box's worker would be."""
        return f"{self.holder}:t{threading.get_ident()}"

    def _still_owner(self, tenant: str, resource: str, token: int) -> bool:
        return self.store.check_fencing(tenant, resource, self._holder(),
                                        token)

    def _release(self, tenant: str, resource: str, token: int) -> None:
        self.store.release_lease(tenant, resource, self._holder(), token)

    def _heartbeat(self, tenant: str, resource: str, holder: str,
                   token: int) -> LeaseHeartbeat:
        """Renew the lease while a side effect runs, so a callback longer
        than the TTL keeps its ownership instead of parking unknown."""
        return LeaseHeartbeat(self.store, tenant, resource, holder, token,
                              self.lease_ttl_seconds)

    def _park_takeover(self, key: tuple, tenant: str, resource: str,
                       holder: str, token: int) -> str:
        """Park after taking over an expired unreleased lease. Never
        execute: the prior owner may have started the effect and died
        mid-callback, so the outcome is uncertain and only
        reconciliation may clear it."""
        current = self.store.get_action(key)
        if current is None:
            return "not_found"
        if current["state"] == "done":
            return "already_done"
        if current["state"] == "unknown":
            return "parked_unknown"
        self.store.complete_action_if_owner(
            key, "unknown", tenant, resource, holder, token,
            evidence_ref="takeover/expired-unreleased-lease")
        return "parked_takeover"

    def _settle_lost_ownership(self, key: tuple) -> str:
        """The lease died mid-callback, so the guarded completion
        refused. Re-read: done means the effect is recorded; unknown
        stays parked; a still-claimed row is parked by us — the effect
        may have landed, so it goes through reconciliation, never a
        blind retry."""
        current = self.store.get_action(key)
        if current is None:
            return "not_found"
        if current["state"] == "done":
            return "already_done"
        if current["state"] == "unknown":
            return "parked_unknown"
        self.store.mark_action(key, "unknown",
                               evidence_ref="lease-lost-mid-callback")
        return "parked_unknown"

    def process(self, event: dict,
                contact_ref: Optional[str] = None) -> dict:
        """Process one inbox-ACCEPTED event. Recording/dedup happens
        exactly once, upstream, in the normalizer's ingest (design
        section 1 ordering); this method must only ever be called with
        events ingest accepted, so a redelivery can never reach it."""
        validate_event(event)
        tenant = event["tenant_id"]
        txn = event.get("native_transaction_ref") or event["native_order_ref"]
        if event["event_type"] == "refund_observed" or \
                event["payment_status"] in ("refunded",
                                             "partially_refunded"):
            return self._apply_refund(event, tenant, txn)
        if event["payment_status"] != "succeeded":
            return {"result": f"no_grant:{event['payment_status']}",
                    "actions_created": 0}
        created = 0
        reconciled = 0
        pending = 0
        unresolved_lines = set()
        for line in event["line_items"]:
            line_ref = line["native_line_ref"]
            expected = list(line["entitlement_ids"])
            for ent in expected:
                rkey = _right_key(event, line, "grant_access", ent)
                record = self.store.claim_right(rkey)
                if record is None:
                    # first owner of this right: record it
                    self.store.grant_entitlement(tenant, line_ref, ent)
                    self.store.mark_right(
                        rkey, "done", evidence_ref=event["evidence_ref"])
                    created += 1
                    continue
                if record["state"] == "unknown":
                    # an earlier grant outcome is unresolved: visible,
                    # never blindly repeated
                    pending += 1
                    unresolved_lines.add(line_ref)
                    continue
                # already-processed claim: reconcile the expected rights
                # against what the book actually records (a crash between
                # claim and grant leaves this bundle incomplete)
                if self.store.entitlement_state(tenant, line_ref, ent) is None:
                    self.store.grant_entitlement(tenant, line_ref, ent)
                    reconciled += 1
                # a recorded 'revoked' row is a refund's outcome and is
                # never resurrected by a replay of the purchase event
                if record["state"] == "claimed":
                    self.store.mark_right(
                        rkey, "done", evidence_ref=event["evidence_ref"])
            # line-level grant action (unchanged surface: one row per
            # line, done once every expected right is recorded)
            gkey = _action_key(event, line, "grant_access", self.version)
            if self.store.claim_action(
                    gkey, {"entitlements": expected}) is None:
                created += 1
            if line_ref not in unresolved_lines:
                current = self.store.get_action(gkey)
                if current is not None and current["state"] == "claimed":
                    self.store.mark_action(
                        gkey, "done", evidence_ref=event["evidence_ref"])
            fkey = _action_key(event, line, "initiate_fulfillment",
                               self.version)
            if self.store.claim_action(
                    fkey, {"slot": line["slot"]}) is None:
                created += 1  # stays 'claimed' for the fulfillment worker
            if contact_ref:
                self.store.add_buyer(tenant, event["launch_id"],
                                     contact_ref, line_ref)
        # verified-purchase tag: the handler workflow's entry seam
        tag_state = None
        if self.purchase_tag:
            tkey = (tenant, txn, "*",
                    "apply_verified_purchase_tag", self.version)
            record = self.store.claim_action(
                tkey, {"tag": self.purchase_tag})
            if record is None:
                created += 1
                if self.tag_applier is not None and contact_ref:
                    tag_state = self._run_tag_effect(tkey, event,
                                                     contact_ref)
                else:
                    tag_state = "claimed"  # visible outstanding work
            else:
                tag_state = record["state"]
                if tag_state == "claimed":
                    # incomplete bundle: a worker claimed the effect and
                    # never recorded an outcome. Finish it under the
                    # lease; a live owner's lease makes this a no-op.
                    if self.tag_applier is not None and contact_ref:
                        tag_state = self._run_tag_effect(
                            tkey, event, contact_ref)
                elif tag_state == "unknown":
                    # lost acknowledgement: reconcile remote state before
                    # any retry
                    tag_state = self._reconcile_tag(tkey, event,
                                                    contact_ref)
        return {"result": "processed", "actions_created": created,
                "rights_reconciled": reconciled, "pending_rights": pending,
                "tag_state": tag_state}

    def _apply_refund(self, event: dict, tenant: str, txn: str) -> dict:
        """Line-scoped revocation. Only the entitlements named on the
        refund's lines are removed; every other right is untouched. Each
        entitlement carries a durable revoke claim, so a replay completes
        an interrupted refund without repeating an unresolved one."""
        revoked = 0
        pending = 0
        for line in event["line_items"]:
            line_ref = line["native_line_ref"]
            for ent in line["entitlement_ids"]:
                rkey = (tenant, txn, line_ref, "revoke_access", ent)
                record = self.store.claim_right(rkey)
                if record is not None and record["state"] == "unknown":
                    pending += 1
                    continue
                self.store.revoke_entitlement(tenant, line_ref, ent)
                self.store.mark_right(
                    rkey, "done", evidence_ref=event.get("evidence_ref"))
                revoked += 1
        return {"result": "refund_applied", "actions_created": 0,
                "rights_revoked": revoked, "pending_rights": pending}

    def _run_tag_effect(self, key: tuple, event: dict,
                        contact_ref: str) -> str:
        """Apply the verified-purchase tag as the leased owner. The
        lease resource is the stable idempotency key for this effect
        (one namespace per transaction), so a provider that dedupes on
        it applies the effect at most once. Taking over an expired
        unreleased lease parks for reconciliation instead of executing
        — the prior owner may have started the effect. Completion is
        ownership-conditioned and atomic with the fencing check, so a
        callback that outlives its lease can never record success it
        no longer owns."""
        tenant, txn = event["tenant_id"], key[1]
        resource = effect_resource_for_tag(txn)
        holder = self._holder()
        token, took_over = self.store.acquire_effect_lease(
            tenant, resource, holder,
            ttl_seconds=self.lease_ttl_seconds)
        if token is None:
            return "held_elsewhere"
        try:
            if took_over:
                return self._park_takeover(key, tenant, resource,
                                           holder, token)
            if not self._still_owner(tenant, resource, token):
                return "fenced_out"
            current = self.store.get_action(key)
            if current is None:
                return "not_found"
            if current["state"] == "done":
                return "already_done"
            if current["state"] == "unknown":
                return "parked_unknown"
            try:
                with self._heartbeat(tenant, resource, holder, token):
                    self.tag_applier(contact_ref, self.purchase_tag)
            except Exception:
                # outcome unknown: park, never claim success
                if not self.store.complete_action_if_owner(
                        key, "unknown", tenant, resource, holder,
                        token):
                    return self._settle_lost_ownership(key)
                return "parked_unknown"
            if not self.store.complete_action_if_owner(
                    key, "done", tenant, resource, holder, token,
                    evidence_ref=event["evidence_ref"]):
                return self._settle_lost_ownership(key)
            return "done"
        finally:
            self._release(tenant, resource, token)

    def _reconcile_tag(self, key: tuple, event: dict,
                       contact_ref: Optional[str]) -> str:
        """Reconcile a parked tag action against remote state BEFORE any
        retry: a confirmed remote success is marked done without a second
        application; a confirmed absence reopens exactly one fenced
        retry; a failed or absent reconciliation leaves the park
        visible."""
        if self.tag_reconciler is None or not contact_ref:
            return "unknown"
        try:
            present = self.tag_reconciler(contact_ref, self.purchase_tag)
        except Exception:
            return "unknown"
        if present:
            self.store.mark_action(key, "done",
                                   evidence_ref=event["evidence_ref"])
            return "reconciled_done"
        if not self.store.reopen_action(key):
            current = self.store.get_action(key)
            return current["state"] if current else "not_found"
        return self._run_tag_effect(key, event, contact_ref)

    def fulfill(self, key: tuple, executor: Callable[[dict], None],
                reconcile: Optional[Callable[[dict], bool]] = None) -> str:
        """Run one claimed fulfillment action as the leased owner.

        Executor success marks it done; an exception parks it as unknown
        (visible review), never a silent retry. A parked action is only
        retried after `reconcile(payload)` confirms the remote effect did
        NOT happen (exactly one fenced retry); a confirmed success marks
        it done without executing again. Without a reconciler the park
        stands."""
        action = self.store.get_action(key)
        if action is None:
            return "not_found"
        if action["state"] == "done":
            return "already_done"
        if action["state"] == "unknown":
            if reconcile is None:
                return "parked_unknown"
            try:
                remote_done = reconcile(action["payload"])
            except Exception:
                return "parked_unknown"
            if remote_done:
                self.store.mark_action(
                    key, "done", evidence_ref="reconciled/remote-confirmed")
                return "reconciled_done"
            if not self.store.reopen_action(key):
                current = self.store.get_action(key)
                return current["state"] if current else "not_found"
        tenant, txn_ref, line_ref, action_type, _version = key
        resource = effect_resource_for_action(action_type, txn_ref,
                                             line_ref)
        holder = self._holder()
        token, took_over = self.store.acquire_effect_lease(
            tenant, resource, holder,
            ttl_seconds=self.lease_ttl_seconds)
        if token is None:
            return "held_elsewhere"
        try:
            if took_over:
                return self._park_takeover(key, tenant, resource,
                                           holder, token)
            if not self._still_owner(tenant, resource, token):
                return "fenced_out"
            current = self.store.get_action(key)
            if current is None:
                return "not_found"
            if current["state"] == "done":
                return "already_done"
            if current["state"] == "unknown":
                return "parked_unknown"
            try:
                with self._heartbeat(tenant, resource, holder, token):
                    executor(current["payload"])
            except Exception:
                if not self.store.complete_action_if_owner(
                        key, "unknown", tenant, resource, holder,
                        token):
                    return self._settle_lost_ownership(key)
                return "parked_unknown"
            if not self.store.complete_action_if_owner(
                    key, "done", tenant, resource, holder, token):
                return self._settle_lost_ownership(key)
            return "done"
        finally:
            self._release(tenant, resource, token)

    def is_suppressed(self, tenant: str, launch: str,
                      contact_ref: str) -> bool:
        return self.store.is_suppressed(tenant, launch, contact_ref)


def dispatch_marketing(processor: DurableProcessor, queued: dict,
                       sender: Callable[[dict], str]) -> str:
    """A21: suppression rechecked immediately before the send."""
    if processor.is_suppressed(queued["tenant_id"], queued["launch_id"],
                               queued["contact_ref"]):
        return "suppressed"
    return sender(queued)
