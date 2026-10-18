"""S44 fulfillment-map producer — read model over the durable store.

Implements the producer S44 committed to in the CR-S82-002 reply
package (fulfillment-map section): per buyer (tenant_id, launch_id,
contact_ref) it assembles the map S82's thank-you resolver consumes
(S82 contract: 82-signature-thank-you/references/
s44-fulfillment-continuity.md section 2; verbatim copy with
provenance in s82-contract-copy.md beside this module), keyed by
entitlement ID:

    {"<entitlement_id>": {"state": "granted | pending | not_granted |
                                     revoked",
                           "delivery_url": None,
                           "next_action": <one of the six>}}

plus the buyer's ev1 entitlement_version
(Store.entitlement_version, CR-S82-002 item 5).

PURE READ MODEL: this module only SELECTs. It never writes to the
store, never grants, never sends. delivery_url is None unless the
launch record's delivery binding supplies one for a GRANTED
entitlement (CR-S82-003, below); null is contract-valid.

DELIVERY BINDING (CR-S82-003, ruling S82-DEC-DELIVERYURL-01; S49's
launch schema 1.2, landed by PR #2222): the launch record carries an
OPTIONAL top-level `delivery_bindings` object keyed by
entitlement_id, each binding {"delivery_kind": one of access /
download / schedule_included_service, "delivery_url": an https URL
or null (kind bound, no destination recorded yet)}. Absence of the
key, or of an entitlement's entry, is the only encoding of
"unbound". When the caller passes the launch record and an
entitlement's aggregated state is granted AND a binding exists for
it, the entry emits the bound kind as next_action and the bound URL
as delivery_url, in place of the pre-binding granted behavior
(access / None). Every other case — unbound entitlements, and every
non-granted state bound or not — is byte-identical to the
pre-binding producer: the binding is consulted only in the granted
branch, a bound-but-not-granted entitlement keeps delivery_url
null, and the producer never guesses a kind or fabricates a URL. A
malformed binding (not an object, unknown keys, a kind outside the
binding enum, a missing field, or a URL that is neither null nor an
https string) fails closed with VocabularyError rather than passing
through. The binding is NOT an entitlement_version input: ev1 is
computed exactly as before (CR-S82-002 item-5 settlement
undisturbed).

STATE ASSEMBLY — per (line, entitlement) unit, precedence top-down:

  1. Book row state 'active' (the book is the authority):
     - any initiate_fulfillment action for the line is 'done'
         -> granted
     - else any is 'unknown' (outcome parked, DESIGN-S44-07 section 1)
         -> pending (parked)
     - else (still 'claimed', or — defensively — none recorded)
         -> pending (fulfillment in flight)
  2. Book row state 'revoked' -> revoked.
  3. No book row: the unit is known only from stored inbox events
     naming this line and entitlement within the buyer's registered
     lines. The latest event (by received_at, tie-broken by event_id)
     decides by its payment_status:
       pending                  -> pending (payment not settled)
       failed                   -> not_granted
       requires_customer_action -> not_granted
       unknown                  -> not_granted
       succeeded                -> pending (defensive: a succeeded
                                   event with no book row is an
                                   inconsistency; never claim granted
                                   without the book)
       refunded/partially_refunded -> not_granted (defensive: refund
                                   of a unit this book never granted)

  Later non-granting events never override a book row: an active
  grant stands until a refund revokes it (A20 base survival,
  DESIGN-S44-07 section 3).

REACHABILITY NOTE: the processor registers a buyer line only on the
succeeded path, which also grants every entitlement on the line, so
within a registered buyer's scope every unit normally has a book row
and branch 3 is defensive. Payment-pending and not_granted units are
therefore NOT reachable through the real pipeline within buyer scope
today (a failed or pending first purchase creates no buyer
registration to attach a view to); branch 3 exists so the producer is
complete against the contract, and it is tested at the read-model
level with that justification named (see evidence note).

AGGREGATION: an entitlement may sit on several of the buyer's lines
(e.g. a renewal line). The entitlement's map state is the strongest
unit state: granted > pending > revoked > not_granted (an entitlement
is live while at least one line grant is live — the book's own
semantics). next_action comes from the winning unit; ties break by
smallest line_ref, deterministically.

NEXT_ACTION DECISION TABLE (vocabulary is exactly the six names in
the S82 contract section 2; anything outside them fails closed):

  unit outcome                              next_action
  ----------------------------------------  -------------------------
  granted                                   access (or the bound
                                            delivery_kind when a
                                            launch-record binding
                                            exists, CR-S82-003)
  pending, fulfillment parked 'unknown'     support
  pending, fulfillment in flight            noncommercial_next_step
  pending, payment not settled              manage_purchase
  pending, defensive succeeded-no-row       noncommercial_next_step
  not_granted, payment failed               manage_purchase
  not_granted, requires_customer_action     manage_purchase
  not_granted, payment unknown              support
  not_granted, defensive refund-no-row      manage_purchase
  revoked                                   manage_purchase

  Rationale, briefly: 'access' is the granted state's action (the
  contract: a granted item produces an access block). A parked
  unknown outcome or an unverifiable payment leaves the buyer no
  honest self-serve step, so 'support'. A fulfillment still in
  flight after a settled payment asks nothing of the buyer, so a
  'noncommercial_next_step'. Payment-side problems (unsettled,
  failed, action-required) and the post-refund remainder are all
  resolved on the purchase itself, so 'manage_purchase'. Two
  vocabulary slots, 'download' and 'schedule_included_service',
  cannot be selected from durable-store facts: the store carries no
  per-entitlement delivery-kind metadata (downloadable vs access vs
  bookable service). They are emitted only when a launch-record
  delivery binding supplies that kind for a granted entitlement
  (CR-S82-003 section above); the producer never guesses.

FAIL-CLOSED: every emitted next_action is checked against the six
names; a decision-table edit producing anything else raises
VocabularyError instead of emitting a map S82 would reject.
"""
from __future__ import annotations

import re

# The six approved classifications, verbatim from the S82 contract
# (s82-contract-copy.md, section 2; blob db6efbbe...). S44 may not
# invent a thank-you action, and a new-charge action can never be one.
NEXT_ACTIONS = frozenset({
    "access",
    "download",
    "manage_purchase",
    "support",
    "schedule_included_service",
    "noncommercial_next_step",
})

MAP_STATES = frozenset({"granted", "pending", "not_granted", "revoked"})

# The delivery-kind enum of S49's launch schema 1.2 delivery_bindings
# (a strict subset of NEXT_ACTIONS: a binding may only name a
# delivery kind, never e.g. 'support' or 'manage_purchase').
BINDING_KINDS = frozenset({
    "access",
    "download",
    "schedule_included_service",
})

# Mirrors the schema's delivery_url pattern (^https://\S+$).
_BINDING_URL = re.compile(r"^https://\S+$")

_STATE_RANK = {"not_granted": 0, "revoked": 1, "pending": 2,
               "granted": 3}


class VocabularyError(ValueError):
    """A computed next_action fell outside S82's six approved
    classifications. Raised instead of emitting an invalid map —
    the producer fails closed exactly as S82's resolver does."""


def _check_vocabulary(name: str) -> str:
    if name not in NEXT_ACTIONS:
        raise VocabularyError(
            f"next_action {name!r} is outside the six approved "
            "classifications; refusing to emit the fulfillment map")
    return name


def _bound_delivery(bindings: dict, entitlement: str):
    """Validate one entitlement's delivery binding (CR-S82-003) and
    return (delivery_kind, delivery_url). The caller has already
    established the entitlement is present in `bindings`. Anything
    malformed fails closed with VocabularyError — the producer
    refuses the map rather than passing a bad binding through."""
    binding = bindings[entitlement]
    if not isinstance(binding, dict):
        raise VocabularyError(
            f"delivery binding for {entitlement!r} is not an object; "
            "refusing to emit the fulfillment map")
    if set(binding) != {"delivery_kind", "delivery_url"}:
        raise VocabularyError(
            f"delivery binding for {entitlement!r} must carry exactly "
            "delivery_kind and delivery_url; refusing to emit the "
            "fulfillment map")
    kind = binding["delivery_kind"]
    if kind not in BINDING_KINDS:
        raise VocabularyError(
            f"delivery_kind {kind!r} for {entitlement!r} is outside "
            "the launch schema's binding enum; refusing to emit the "
            "fulfillment map")
    url = binding["delivery_url"]
    if url is not None and not (isinstance(url, str)
                                and _BINDING_URL.match(url)):
        raise VocabularyError(
            f"delivery_url for {entitlement!r} is neither null nor "
            "an https URL; refusing to emit the fulfillment map")
    return kind, url


def _extract_bindings(launch_record) -> dict:
    """The launch record's top-level delivery_bindings object, or {}
    when no record (or no bindings key) is supplied — absence is the
    encoding of 'unbound' (launch schema 1.2). A present-but-malformed
    bindings value fails closed."""
    if launch_record is None:
        return {}
    if not isinstance(launch_record, dict):
        raise VocabularyError(
            "launch_record is not an object; refusing to emit the "
            "fulfillment map")
    bindings = launch_record.get("delivery_bindings")
    if bindings is None:
        return {}
    if not isinstance(bindings, dict):
        raise VocabularyError(
            "delivery_bindings is not an object; refusing to emit "
            "the fulfillment map")
    return bindings


def _unit_from_book(state: str, fulfillment_states: list[str]):
    """Branch 1/2 of the assembly: the book row is authoritative."""
    if state == "revoked":
        return "revoked", "manage_purchase"
    # state == 'active'
    if "done" in fulfillment_states:
        return "granted", "access"
    if "unknown" in fulfillment_states:
        return "pending", "support"
    return "pending", "noncommercial_next_step"


def _unit_from_event(payment_status: str):
    """Branch 3 of the assembly: no book row; latest event decides."""
    if payment_status == "pending":
        return "pending", "manage_purchase"
    if payment_status == "failed":
        return "not_granted", "manage_purchase"
    if payment_status == "requires_customer_action":
        return "not_granted", "manage_purchase"
    if payment_status == "unknown":
        return "not_granted", "support"
    if payment_status == "succeeded":
        return "pending", "noncommercial_next_step"
    # refunded / partially_refunded with no book row (defensive)
    return "not_granted", "manage_purchase"


def _latest_event_outcomes(store, tenant_id: str, launch_id: str,
                           line_refs: list[str]) -> dict:
    """(line_ref, entitlement) -> payment_status of the latest stored
    event for this launch naming that unit. Deterministic: events are
    ordered by (received_at, event_id); the last write wins."""
    wanted = set(line_refs)
    latest: dict[tuple, tuple] = {}
    for event in store.stored_events(tenant_id):
        if event.get("launch_id") != launch_id:
            continue
        order_key = (event.get("received_at", ""), event.get("event_id", ""))
        for line in event.get("line_items", []):
            line_ref = line.get("native_line_ref")
            if line_ref not in wanted:
                continue
            for ent in line.get("entitlement_ids", []):
                key = (line_ref, ent)
                if key not in latest or order_key >= latest[key][0]:
                    latest[key] = (order_key, event.get("payment_status"))
    return {k: v[1] for k, v in latest.items()}


def build_fulfillment_map(store, tenant_id: str, launch_id: str,
                          contact_ref: str, launch_record=None) -> dict:
    """Assemble the fulfillment map for one buyer. Read-only.

    `launch_record` is optional: the launch's record of record (S49,
    launch schema 1.2). When it carries a `delivery_bindings` entry
    for a GRANTED entitlement, that entry's kind and URL are emitted
    for the entitlement (CR-S82-003); every other output is identical
    to the no-record call.

    Returns {"tenant_id", "launch_id", "contact_ref",
             "entitlement_version", "entitlements": {entitlement_id:
             {"state", "delivery_url", "next_action"}}} — the inner
    dict is exactly the map shape of the S82 contract section 2.
    """
    bindings = _extract_bindings(launch_record)
    line_refs = store.buyer_lines(tenant_id, launch_id, contact_ref)
    book = {(lr, ent): st for lr, ent, st in
            store.buyer_entitlement_rows(tenant_id, launch_id,
                                         contact_ref)}
    event_outcomes = _latest_event_outcomes(store, tenant_id, launch_id,
                                            line_refs)
    fulfillment = {lr: store.line_action_states(
        tenant_id, lr, "initiate_fulfillment") for lr in line_refs}

    units: dict[str, list] = {}
    for key in sorted(set(book) | set(event_outcomes)):
        line_ref, entitlement = key
        if key in book:
            state, action = _unit_from_book(book[key],
                                            fulfillment[line_ref])
        else:
            state, action = _unit_from_event(event_outcomes[key])
        units.setdefault(entitlement, []).append(
            (line_ref, state, action))

    entitlements = {}
    for entitlement in sorted(units):
        # strongest state wins; ties break by smallest line_ref
        _line, state, action = sorted(
            units[entitlement],
            key=lambda u: (-_STATE_RANK[u[1]], u[0]))[0]
        assert state in MAP_STATES, state
        delivery_url = None
        if state == "granted" and entitlement in bindings:
            # CR-S82-003: the launch record's binding supplies this
            # granted entitlement's delivery kind and URL. This is
            # the ONLY branch the binding may touch.
            action, delivery_url = _bound_delivery(bindings,
                                                   entitlement)
        entitlements[entitlement] = {
            "state": state,
            "delivery_url": delivery_url,
            "next_action": _check_vocabulary(action),
        }
    return {
        "tenant_id": tenant_id,
        "launch_id": launch_id,
        "contact_ref": contact_ref,
        "entitlement_version": store.entitlement_version(
            tenant_id, launch_id, contact_ref),
        "entitlements": entitlements,
    }
