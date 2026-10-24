#!/usr/bin/env python3
"""progressive_capture.py - mobile-first capture and the ONE logical SMS email ask.

Contract basis: Purple-Billboard DATA-CONTRACTS.md sections 6 and 7, and
CLIENT-EXPERIENCE.md "Phone known, email missing", "Email known, mobile
missing" and "Fields captured at different times" (R-14, checks C-16 / C-F06 /
C-F11).

Nothing here is a second copy of an existing guard. The accepted upstream
modules on main are imported, not re-implemented:

  * T-11 `tenant_identity` - the later email binds to the SAME verified
    member; a second account is impossible and a cross-tenant row is never
    returned.
  * T-11 `collection_lock` - when a lock is configured, every capture
    mutation needs a live collection fence, so a stale writer cannot create
    or advance the ask.
  * T-12 `durable_store` - the ask IS one outbox action: one
    logical_intent_key, idempotency-keyed, with separate attempt and receipt
    rows. A corrected number cannot mint a second ask because no second
    identity is derivable.
  * T-12 `outbound_gate` - every send and every retry calls the evaluator
    again; a verdict from an earlier attempt is never reused.
  * T-08 `pb_contracts` - the serialized `sms_email_ask` object is checked
    against schemas/collection-state.schema.json, so this module cannot drift
    from the contract shape.

What this module adds is the capture policy: what may be asked, in what
order, at most once, and how a refusal, a corrected number or an email that
arrives before dispatch changes that answer.

States (DATA-CONTRACTS 7 / D-26), exactly:

    not_created -> queued -> dispatching -> accepted
    plus failed_not_sent, unknown, suppressed

Import (shared-utils on the path):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from capture.progressive_capture import plan_capture, SmsEmailAsk

Python 3 standard library only.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

# ── vocabulary ──────────────────────────────────────────────────────────────

MAX_SMS_EMAIL_ASKS = 1

PURPOSE_SMS_EMAIL_ASK = "SMS_EMAIL_ASK"
PURPOSE_ACCESS_PASS = "ACCESS_PASS"
PURPOSE_CAPTURE_REMINDER = "CAPTURE_REMINDER"

ASK_NOT_CREATED = "not_created"
ASK_QUEUED = "queued"
ASK_DISPATCHING = "dispatching"
ASK_ACCEPTED = "accepted"
ASK_FAILED_NOT_SENT = "failed_not_sent"
ASK_UNKNOWN = "unknown"
ASK_SUPPRESSED = "suppressed"
ASK_STATES: Tuple[str, ...] = (
    ASK_NOT_CREATED, ASK_QUEUED, ASK_DISPATCHING, ASK_ACCEPTED,
    ASK_FAILED_NOT_SENT, ASK_UNKNOWN, ASK_SUPPRESSED,
)

# An ask in one of these states is still the same live logical action: a
# second ask never becomes permissible because the person stayed silent.
ASK_OPEN = frozenset({ASK_QUEUED, ASK_DISPATCHING, ASK_ACCEPTED, ASK_UNKNOWN})

FIELD_REFUSAL = "field"
SEQUENCE_REFUSAL = "sequence"
CHANNEL_REFUSAL = "channel"
GLOBAL_REFUSAL = "global"
REFUSAL_SCOPES = (FIELD_REFUSAL, SEQUENCE_REFUSAL, CHANNEL_REFUSAL, GLOBAL_REFUSAL)
FIELD_NAMES = ("mobile", "email")

# DurableStore marks known nonexecution by requeueing the same identity; the
# ask reports it as failed_not_sent. This is the one blocked_reason that means
# "provider evidence says the effect does not exist".
NONEXECUTION_MARK = "reconciled_not_applied"


class CaptureError(ValueError):
    """Malformed input. Fail closed: nothing is asked, nothing is sent."""


class CaptureConflict(CaptureError):
    """Two records disagree. Never resolved by guessing or by merging."""


class CaptureRefused(CaptureError):
    """A rule says no. The caller must not retry against the refusal."""


# ── upstream bridge (T-08 / T-11 / T-12) ────────────────────────────────────

_UPSTREAM: Dict[str, Any] = {}


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "38-conversational-ai-system" / "tools"
                / "durable_store.py").is_file():
            return parent
    raise CaptureError(
        "capture: 38-conversational-ai-system/tools not found above %s" % here)


def upstream() -> SimpleNamespace:
    """Import the accepted upstream modules once, by path.

    The skill directory is hyphenated and therefore not an importable package
    name, so the tools directory is placed on sys.path the way Skill 38's own
    tools do it. A missing tree is a hard error: this module will not grow a
    private copy of a guard it cannot import.
    """
    if not _UPSTREAM:
        tools_dir = _repo_root() / "38-conversational-ai-system" / "tools"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import collection_lock  # noqa: F401
        import durable_store  # noqa: F401
        import outbound_gate  # noqa: F401
        import pb_contracts  # noqa: F401
        import tenant_identity  # noqa: F401
        _UPSTREAM.update({
            "collection_lock": collection_lock,
            "durable_store": durable_store,
            "outbound_gate": outbound_gate,
            "pb_contracts": pb_contracts,
            "tenant_identity": tenant_identity,
        })
    return SimpleNamespace(**_UPSTREAM)


def terminal_states() -> frozenset:
    """Reuse T-08's terminal collection set instead of restating it."""
    return frozenset(upstream().pb_contracts.TERMINAL_COLLECTION)


# ── small helpers ───────────────────────────────────────────────────────────

def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError("%s must be a non-empty string" % name)
    return value.strip()


def _present(value: Optional[str]) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── capture facts and the plan ──────────────────────────────────────────────

@dataclass(frozen=True)
class KnownFields:
    """Fields already known about the person. Reused, never re-asked."""

    mobile: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None


@dataclass(frozen=True)
class CaptureFacts:
    """Everything a refusal or an opt-out can change, in one immutable value."""

    state: str = "invited"
    state_version: int = 0
    field_refusals: Tuple[str, ...] = ()
    channel_optouts: Tuple[str, ...] = ()
    global_stop: bool = False
    human_owner_id: Optional[str] = None
    delivery_consent: bool = True


@dataclass(frozen=True)
class AskPlan:
    purpose: str
    channel: str
    field: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return {"purpose": self.purpose, "channel": self.channel,
                "field": self.field}


@dataclass(frozen=True)
class CapturePlan:
    state: str
    asks: Tuple[AskPlan, ...]
    reason: str
    email_ask_allowed: bool

    def as_dict(self) -> Dict[str, Any]:
        return {"state": self.state,
                "asks": [ask.as_dict() for ask in self.asks],
                "reason": self.reason,
                "email_ask_allowed": self.email_ask_allowed}


def plan_capture(
    known: KnownFields,
    *,
    facts: Optional[CaptureFacts] = None,
    access_ready: bool = False,
    ask_state: str = ASK_NOT_CREATED,
    asks_used: int = 0,
    dm_channel: str = "FB_DM",
) -> CapturePlan:
    """Decide what this capture may ask next. Pure; no IO.

    Order matters and follows DATA-CONTRACTS 7: global stop, then human
    ownership, then a terminal sequence, then delivery consent, then "email
    already known is pass-only", then the missing field, then the single ask.
    """
    facts = facts or CaptureFacts()
    if ask_state not in ASK_STATES:
        raise CaptureError("ask_state %r not in %s" % (ask_state, ASK_STATES))
    if not isinstance(asks_used, int) or isinstance(asks_used, bool) or asks_used < 0:
        raise CaptureError("asks_used must be a non-negative integer")
    # Field names fold case the way channel_optouts do ("sms" and "SMS" are
    # one opt-out; "Mobile" and "mobile" are one refusal). Non-strings keep
    # their identity and still land in unknown_refusals, so nothing becomes
    # acceptable by being unrecognisable.
    refusals = frozenset(
        item.strip().lower() if isinstance(item, str) else item
        for item in facts.field_refusals)
    unknown_refusals = refusals - frozenset(FIELD_NAMES)
    if unknown_refusals:
        raise CaptureError("unknown field refusal %s" % sorted(unknown_refusals))
    optouts = frozenset(str(item).strip().upper() for item in facts.channel_optouts)

    has_mobile = _present(known.mobile)
    has_email = _present(known.email)

    if facts.global_stop:
        return CapturePlan(facts.state, (), "global_stop", False)
    if facts.human_owner_id:
        return CapturePlan("human_owned", (), "human_owned", False)
    if facts.state in terminal_states():
        return CapturePlan(facts.state, (), "sequence_terminal", False)
    if not facts.delivery_consent:
        # Delivery consent is separate from marketing; capture does not run on
        # an assumption of it.
        return CapturePlan(facts.state, (), "delivery_consent_missing", False)

    # Email already known: never ask for it again. The only remaining capture
    # effect is the optional pass itself, which is not an ask.
    if has_email:
        asks = ()
        if has_mobile and access_ready and "SMS" not in optouts:
            asks = (AskPlan(PURPOSE_ACCESS_PASS, "SMS", None),)
        return CapturePlan(facts.state, asks, "email_known_pass_only", False)

    if not has_mobile:
        if "mobile" in refusals:
            # A mobile refusal ends mobile chasing. It does not erase the
            # original resource or an existing email.
            return CapturePlan(facts.state, (), "field_refused:mobile", False)
        if dm_channel.strip().upper() in optouts:
            return CapturePlan(facts.state, (), "channel_optout:%s" % dm_channel, False)
        return CapturePlan(
            "awaiting_mobile",
            (AskPlan(PURPOSE_CAPTURE_REMINDER, dm_channel, "mobile"),),
            "mobile_missing", False)

    # Mobile known, email missing: exactly one logical SMS email ask.
    if "email" in refusals:
        return CapturePlan(facts.state, (), "field_refused:email", False)
    if asks_used >= MAX_SMS_EMAIL_ASKS:
        return CapturePlan(facts.state, (), "ask_budget_exhausted", False)
    if ask_state in ASK_OPEN:
        # Accepted, queued, in flight or unreconciled: still the same ask.
        return CapturePlan(facts.state, (), "ask_already_exists", False)
    if ask_state != ASK_NOT_CREATED:
        # Suppressed (terminal) or failed_not_sent (retried as the SAME
        # action): the ask exists, so the budget is spent whatever the
        # caller's counter says. asks_used=0 and asks_used=1 answer alike.
        return CapturePlan(facts.state, (), "ask_budget_exhausted", False)
    if "SMS" in optouts:
        return CapturePlan(facts.state, (), "channel_optout:SMS", False)
    if not access_ready:
        return CapturePlan("preparing_access", (), "access_not_ready", False)
    return CapturePlan(
        "awaiting_email",
        (AskPlan(PURPOSE_SMS_EMAIL_ASK, "SMS", "email"),),
        "email_missing", True)


def refuse(facts: CaptureFacts, *, scope: str, value: str = "") -> CaptureFacts:
    """Return the facts after one refusal. Unknown scope is not permission."""
    if scope not in REFUSAL_SCOPES:
        raise CaptureRefused(
            "unknown refusal scope %r is not broader permission" % (scope,))
    version = facts.state_version + 1
    if scope == FIELD_REFUSAL:
        field = value.strip().lower() if isinstance(value, str) else value
        if field not in FIELD_NAMES:
            raise CaptureRefused("field refusal must name one of %s" % (FIELD_NAMES,))
        return CaptureFacts(
            state=facts.state, state_version=version,
            field_refusals=tuple(sorted(set(facts.field_refusals) | {field})),
            channel_optouts=facts.channel_optouts, global_stop=facts.global_stop,
            human_owner_id=facts.human_owner_id,
            delivery_consent=facts.delivery_consent)
    if scope == SEQUENCE_REFUSAL:
        return CaptureFacts(
            state="stopped_declined", state_version=version,
            field_refusals=facts.field_refusals,
            channel_optouts=facts.channel_optouts, global_stop=facts.global_stop,
            human_owner_id=facts.human_owner_id,
            delivery_consent=facts.delivery_consent)
    if scope == CHANNEL_REFUSAL:
        channel = _required(value, "channel").upper()
        return CaptureFacts(
            state=facts.state, state_version=version,
            field_refusals=facts.field_refusals,
            channel_optouts=tuple(sorted(set(facts.channel_optouts) | {channel})),
            global_stop=facts.global_stop,
            human_owner_id=facts.human_owner_id,
            delivery_consent=facts.delivery_consent)
    return CaptureFacts(
        state=facts.state, state_version=version,
        field_refusals=facts.field_refusals,
        channel_optouts=facts.channel_optouts, global_stop=True,
        human_owner_id=facts.human_owner_id,
        delivery_consent=facts.delivery_consent)


# ── identity: the later email binds to the same verified member ─────────────

def bind_email(
    identity: Any,
    *,
    tenant_id: str,
    canonical_contact_id: str,
    email: str,
    verified: bool = True,
) -> str:
    """Bind a later-captured email to the SAME member. Never a second account.

    Refuses when the email already belongs to another contact in this tenant.
    Contacts are never merged by name, and a cross-tenant row is not reachable
    because every call is keyed by tenant first (T-11 tenant_identity).
    """
    tenant_id = _required(tenant_id, "tenant_id")
    canonical_contact_id = _required(canonical_contact_id, "canonical_contact_id")
    email = _required(email, "email")
    identity.verify(tenant_id, canonical_contact_id)

    existing = identity.resolve(tenant_id, "email", email,
                                verified_only=bool(verified))
    if existing is not None and existing != canonical_contact_id:
        raise CaptureConflict(
            "email already bound to another contact in this tenant; refusing to merge")
    if existing is None:
        # Bind through the contact's existing verified identifiers so the
        # email lands on THIS member. Passing the email alone would mint a
        # second account, which is exactly the defect this clause forbids.
        identifiers = [
            (row["ident_type"], row["ident_value"], bool(row["verified"]))
            for row in identity.identifiers(tenant_id, canonical_contact_id)
            if row["ident_type"] != "email"
        ]
        identifiers.append(("email", email, bool(verified)))
        identity.bind(
            tenant_id,
            identifiers,
            provenance=upstream().tenant_identity.PROVENANCE_PERSON_DIRECTED,
            source="sms_email_ask",
        )
    resolved = identity.resolve(tenant_id, "email", email, verified_only=bool(verified))
    if resolved != canonical_contact_id:
        raise CaptureConflict(
            "email did not resolve to the verified member; refusing to create a second account")
    return resolved


# ── the one logical ask, on T-12's durable outbox ───────────────────────────

class SmsEmailAsk:
    """Exactly one logical SMS email ask per (tenant, contact, sequence).

    The ask is a DurableStore outbox action. Its identity is derived from the
    collection key, so no code path can mint a second ask for the same
    sequence - including a corrected number, a retry and a replay.
    """

    def __init__(
        self,
        store: Any,
        *,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        identity: Any = None,
        lock: Any = None,
    ) -> None:
        self.store = store
        self.tenant_id = _required(tenant_id, "tenant_id")
        self.canonical_contact_id = _required(
            canonical_contact_id, "canonical_contact_id")
        self.collection_sequence_id = _required(
            collection_sequence_id, "collection_sequence_id")
        self.identity = identity
        self.lock = lock

    # -- identity ---------------------------------------------------------

    @property
    def logical_intent_key(self) -> str:
        return "sms-email-ask:%s:%s:%s" % (
            self.tenant_id, self.canonical_contact_id, self.collection_sequence_id)

    @property
    def pass_intent_key(self) -> str:
        return "access-pass:%s:%s:%s" % (
            self.tenant_id, self.canonical_contact_id, self.collection_sequence_id)

    def _check_owner(self) -> None:
        if self.identity is not None:
            self.identity.verify(self.tenant_id, self.canonical_contact_id)

    def _check_fence(self, owner_id: Optional[str], fence: Optional[int]) -> None:
        if self.lock is None:
            return
        if owner_id is None or fence is None:
            raise CaptureError(
                "a collection lock is configured: owner_id and fence are required")
        self.lock.assert_fence(
            self.tenant_id, self.canonical_contact_id,
            self.collection_sequence_id, owner_id, fence)

    # -- creation and state ----------------------------------------------

    def create_or_resume(
        self,
        *,
        body: str = "",
        content_sha256: Optional[str] = None,
        binding_revision: Optional[str] = None,
        owner_id: Optional[str] = None,
        fence: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], bool]:
        """Create the ask, or return the one that already exists.

        Repeating this for a corrected number returns the SAME action with
        created=False, because the identity changed not at all.
        """
        self._check_owner()
        self._check_fence(owner_id, fence)
        digest = content_sha256 or _sha256(body or self.logical_intent_key)
        return self.store.create_intent(
            logical_intent_key=self.logical_intent_key,
            idempotency_key=self.logical_intent_key,
            tenant_id=self.tenant_id,
            scope="person_directed",
            purpose=PURPOSE_SMS_EMAIL_ASK,
            canonical_contact_id=self.canonical_contact_id,
            content_sha256=digest,
            binding_revision=binding_revision,
        )

    def require_action(self) -> Dict[str, Any]:
        row = self.store.action_by_intent(self.logical_intent_key)
        if row is None:
            raise CaptureRefused("the SMS email ask was never created")
        return row

    def _select(self, action_id: Optional[str] = None) -> Dict[str, Any]:
        """This ask's own row, never another action or another person's.

        The identity of an ask is (tenant_id, canonical_contact_id,
        logical_intent_key, purpose). A caller-supplied action_id naming
        anything else - another contact's action, this contact's ACCESS_PASS,
        another sequence's ask - is refused before the store is touched
        further, so no path can send a foreign action AS the one logical SMS
        email ask.
        """
        if action_id is None:
            row = self.require_action()
        else:
            try:
                row = self.store.get_action(action_id)
            except upstream().durable_store.DurableStoreError as exc:
                # Unknown or malformed id: not this ask either. Same refusal
                # vocabulary as a foreign row; the store's error is chained.
                raise CaptureRefused(
                    "action %r is not this SMS email ask; refusing to touch it"
                    % (action_id,)) from exc
        if (row.get("tenant_id") != self.tenant_id
                or row.get("canonical_contact_id") != self.canonical_contact_id
                or row.get("logical_intent_key") != self.logical_intent_key
                or row.get("purpose") != PURPOSE_SMS_EMAIL_ASK):
            raise CaptureRefused(
                "action %r is not this SMS email ask; refusing to touch it"
                % (row.get("action_id"),))
        return row

    def state(self, action_id: Optional[str] = None) -> str:
        """The D-26 state of the ask, derived from the durable row."""
        row = self._select(action_id)
        if self.store.unresolved_attempt(row["action_id"]) is not None:
            return ASK_DISPATCHING
        ds = upstream().durable_store
        mapped = {
            ds.STATE_NOT_REQUESTED: ASK_NOT_CREATED,
            ds.STATE_QUEUED: ASK_QUEUED,
            ds.STATE_DISPATCHED: ASK_ACCEPTED,
            ds.STATE_ACKNOWLEDGED: ASK_ACCEPTED,
            ds.STATE_COMPLETED: ASK_ACCEPTED,
            ds.STATE_UNKNOWN: ASK_UNKNOWN,
            ds.STATE_FAILED: ASK_FAILED_NOT_SENT,
            ds.STATE_CANCELED: ASK_SUPPRESSED,
            ds.STATE_SUPPRESSED: ASK_SUPPRESSED,
            # ponytail: the contract has no quarantined ask state, so a
            # quarantined binding reports suppressed while the durable row
            # keeps the exact reason. Add a state here only when T-08 widens
            # the enum in schemas/collection-state.schema.json.
            ds.STATE_QUARANTINED: ASK_SUPPRESSED,
        }[row["state"]]
        if mapped == ASK_QUEUED and row.get("blocked_reason") == NONEXECUTION_MARK:
            return ASK_FAILED_NOT_SENT
        return mapped

    def queue(self) -> Dict[str, Any]:
        row = self.require_action()
        if row["state"] != upstream().durable_store.STATE_NOT_REQUESTED:
            return row
        return self.store.queue(row["action_id"])

    def view(self, action_id: Optional[str] = None) -> Dict[str, Any]:
        """The `sms_email_ask` object, checked against T-08's schema."""
        row = self._select(action_id)
        receipts = self.store.receipts(row["action_id"])
        dispatch = receipts.get("dispatch") or {}
        ack = receipts.get("ack") or {}
        dispatch_payload = dispatch.get("payload") or {}
        ack_payload = ack.get("payload") or {}
        view = {
            "logical_action_id": row["action_id"],
            "state": self.state(row["action_id"]),
            "provider_message_id": (dispatch.get("provider_receipt_id")
                                    or dispatch_payload.get("provider_message_id")),
            "evidence_id": (ack_payload.get("evidence_id")
                            or dispatch_payload.get("evidence_id")),
        }
        pb = upstream().pb_contracts
        schema = pb.load_schema("collection")["properties"]["sms_email_ask"]
        errs = pb.validate_schema(schema, view)
        if errs:
            raise CaptureError(
                "sms_email_ask view violates collection-state schema: %s" % errs)
        return view

    # -- dispatch: always a fresh gate ------------------------------------

    def dispatch(
        self,
        evaluator: Any,
        sender: Any,
        worker_id: str,
        *,
        action_id: Optional[str] = None,
        now: Optional[float] = None,
        lease_seconds: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send (or retry) through T-12's common gate. Never a cached verdict.

        Only this ask's own action is dispatchable: a foreign action_id is
        refused here, before the gate or the sender sees it.
        """
        row = self._select(action_id)
        ctx = {
            "purpose": PURPOSE_SMS_EMAIL_ASK,
            "tenant_id": self.tenant_id,
            "canonical_contact_id": self.canonical_contact_id,
            "collection_sequence_id": self.collection_sequence_id,
            "max_sms_email_asks": MAX_SMS_EMAIL_ASKS,
        }
        ctx.update(context or {})
        gate = upstream().outbound_gate
        kwargs: Dict[str, Any] = {"now": now, "context": ctx}
        if lease_seconds is not None:
            kwargs["lease_seconds"] = float(lease_seconds)
        return gate.dispatch(
            self.store, evaluator, sender, row["action_id"], worker_id, **kwargs)

    def state_after(self, outcome: Any) -> str:
        """Map a DispatchOutcome to the D-26 ask state.

        Only an outcome for this ask's own action is mapped: a foreign, unknown
        or missing action_id is refused before its status is read, so another
        action's result is never state-reported as this ask.
        """
        action_id = getattr(outcome, "action_id", None)
        if action_id is None:
            raise CaptureRefused(
                "outcome names no action; refusing to report it as this ask")
        self._select(action_id)
        gate = upstream().outbound_gate
        if outcome.status == gate.ST_SENT:
            return ASK_ACCEPTED
        if outcome.status in (gate.ST_UNKNOWN, gate.ST_SEND_ERROR):
            return ASK_UNKNOWN
        if outcome.status == gate.ST_BLOCKED:
            if outcome.verdict in ("SUPPRESSED", "QUARANTINED"):
                return ASK_SUPPRESSED
            if outcome.verdict == "RECONCILE_UNKNOWN":
                return ASK_UNKNOWN
            return ASK_QUEUED
        return self.state(outcome.action_id)

    # -- known nonexecution, correction and retry -------------------------

    def record_known_nonexecution(self, reason: str) -> Dict[str, Any]:
        """Provider evidence says the effect does NOT exist.

        The same identity returns to queued, so a later retry is the SAME ask
        under a fresh gate. Never call this on an unknown outcome.
        """
        _required(reason, "reason")
        row = self.require_action()
        state = self.state(row["action_id"])
        if state == ASK_UNKNOWN:
            raise CaptureRefused(
                "unknown ask must reconcile before nonexecution can be claimed")
        if state == ASK_ACCEPTED:
            raise CaptureRefused(
                "accepted ask is not proven nonexecution; a carrier failure"
                " after acceptance does not un-send it")
        current = self.store.get_action(row["action_id"])
        if current["state"] == upstream().durable_store.STATE_FAILED:
            return current  # already recorded; nothing more to close
        # requeue the SAME identity with the nonexecution mark, so a retry is
        # this ask under a fresh gate and never a new action.
        self.store.record_reconciliation(
            row["action_id"], "known_nonexecution",
            {"reason": reason, "evidence": "provider"})
        return self.store.reconcile_not_applied(row["action_id"])

    def reconcile(self, outcome: str, evidence: Optional[Dict[str, Any]] = None,
                  receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Resolve an unknown ask. Only provider evidence resolves it."""
        row = self.require_action()
        self.store.record_reconciliation(row["action_id"], outcome, evidence or {})
        if outcome == "applied":
            if not receipt:
                raise CaptureError("applied reconciliation requires a provider receipt")
            return self.store.reconcile_applied(row["action_id"], receipt)
        if outcome == "not_applied":
            return self.store.reconcile_not_applied(row["action_id"])
        if outcome == "unknown":
            return self.store.mark_reconcile_unknown(row["action_id"], "reconcile_unknown")
        raise CaptureError("reconciliation outcome must be applied|not_applied|unknown")

    def retry_after_correction(
        self,
        *,
        corrected_mobile: str,
        evaluator: Any,
        sender: Any,
        worker_id: str,
        now: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Retry the SAME ask after a corrected number.

        Allowed only after known nonexecution. Unknown is not replayed and an
        accepted ask is never resent. The retry still passes a fresh gate.
        """
        _required(corrected_mobile, "corrected_mobile")
        state = self.state()
        if state == ASK_UNKNOWN:
            raise CaptureRefused("unknown ask must reconcile; never replayed blind")
        if state == ASK_ACCEPTED:
            raise CaptureRefused("accepted ask is not a new or retryable send")
        if state == ASK_SUPPRESSED:
            raise CaptureRefused("suppressed ask is terminal; email or opt-out won")
        if state not in (ASK_FAILED_NOT_SENT, ASK_QUEUED):
            raise CaptureRefused(
                "retry requires known nonexecution, ask state is %r" % (state,))
        ctx = {"corrected_mobile": corrected_mobile}
        ctx.update(context or {})
        return self.dispatch(evaluator, sender, worker_id, now=now, context=ctx)

    # -- email arriving before dispatch -----------------------------------

    def email_arrived_before_dispatch(
        self,
        *,
        access_ready: bool = True,
        pass_body: str = "",
        owner_id: Optional[str] = None,
        fence: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Suppress an undelivered ask; leave a separate pass-only intent.

        After a dispatch attempt has begun nothing here may claim the ask never
        went out. In that case the call refuses and the durable row stands.
        """
        row = self.store.action_by_intent(self.logical_intent_key)
        result: Dict[str, Any] = {
            "ask_state": ASK_NOT_CREATED,
            "suppressed": False,
            "pass_only_action_id": None,
        }
        if row is None:
            if access_ready:
                result["pass_only_action_id"] = self._create_pass(pass_body)
            return result

        state = self.state(row["action_id"])
        if state in (ASK_ACCEPTED, ASK_DISPATCHING):
            raise CaptureRefused(
                "the ask is already dispatching or accepted; it cannot be"
                " retroactively suppressed")
        if state == ASK_UNKNOWN:
            raise CaptureRefused(
                "the ask is unknown; reconcile before claiming suppression")
        if state == ASK_SUPPRESSED:
            result["ask_state"] = ASK_SUPPRESSED
            result["suppressed"] = True
        else:
            self._check_fence(owner_id, fence)
            self.store.cancel(row["action_id"], "email_arrived_before_dispatch")
            result["ask_state"] = ASK_SUPPRESSED
            result["suppressed"] = True
        if access_ready:
            result["pass_only_action_id"] = self._create_pass(pass_body)
        return result

    def _create_pass(self, body: str) -> str:
        row, _created = self.store.create_intent(
            logical_intent_key=self.pass_intent_key,
            idempotency_key=self.pass_intent_key,
            tenant_id=self.tenant_id,
            scope="person_directed",
            purpose=PURPOSE_ACCESS_PASS,
            canonical_contact_id=self.canonical_contact_id,
            content_sha256=_sha256(body or self.pass_intent_key),
        )
        return row["action_id"]
