"""Skill 81 (D1) shared action wrapper (S81-05), reconciled to the
confirmed extra-offer interface contract.

Built against the confirmed binding map (adapters/
provisional-binding-map.md, replaced in place by the confirmed map on
2026-10-17; the filename is retained because S49's records cite it),
which maps D1's native-action requirements
(references/native-action-states.md) against the confirmed S79/S06
extra-offer interface contract (S49, contract owner): revision 1
(rooms/S49/s79-interface-confirmation/
extra_offer_interface-CONFIRMED.md, SHA-256
cb2a15f7af367432824c70b5f4c287cdb65336668cd3f6e18328612797402a0b) as
completed by revision 2 (followon-g7/
extra_offer_interface-CONFIRMED-r2.md, new section 8A.1 to 8A.8,
SHA-256
07f6b75794a3a8e98aad02a94fb82bcdec78d1264b0a56fa3bda066484b3022f).
Revision 2 as authored hashed
3bd42c33fe8ade1579dc2890e83e82b0a7647f5cb6ac761375e0f9f57819f2e8 and
was cured in S49's independent review by two documentary hunks (the
preamble's offer-class enumeration and the section 8A.8 citation); no
operative text changed, and 07f6b757 supersedes 3bd42c33 as the
citation of record. Nothing here is a second charge implementation
(packet 11 section 3, packet 16 section 1): the wrapper only calls the
shared component through named binding points, and it never guesses a
call the contract does not carry.

Binding-point discipline, as recorded in the confirmed binding map
(6 MAPPED, 0 PARTIAL, 0 UNMAPPED):

- MAPPED points pass through to the component: entry-guard
  eligibility confirmation (row 1, revision 2 section 8A.1),
  submission with its pending lockout (row 2, section 8A.5),
  reconciliation (row 3, section 8A.4), decline operation / decline
  result record (row 4, section 8A.2), price disclosure (row 5,
  section 8A.7), verified result read with the route-result output
  (row 6, sections 8A.6 and 8A.8).
- Row 2 (pending lockout) is the submission operation itself
  (section 8A.5): this wrapper's single submission path passes
  through that point to the component's submit hook, exactly once
  per attempt, and a repeat offered while the standing attempt is
  submitting or pending_confirmation is rejected before the point
  is invoked, so it never reaches the native side and creates no
  second charge attempt; the standing attempt is unaffected. MAIN
  accepted S49's G-4 ruling as a substituted disposition under
  S81-DEC-G4-SUBDISP-01 (2026-10-17), so section 8A.5's
  attempt-integrity carrier (pending lockout, reconcile-before-retry,
  decline never charges) IS the contract's attempt-key position of
  record. The wrapper-side edits for CR-S81-001 (this pass-through,
  binding row 2 MAPPED, retirement of the staged gap label) were
  staged on that ruling and executed in the follow-on cycle once
  the candidate carrying revision 2 landed (PR #2228, merged in
  train #2235 on main 9ccd6536, 2026-10-17; revision 2's independent
  review had already passed at the cured hash above). No
  idempotency or deduplication KEY is named anywhere under the
  contract, and none is coined here: the ruling states on its face
  that S06's filed position is that no native deduplication exists
  to key on, so a coined key name would misdescribe the native
  side. CR-S81-001's acceptance-evidence fixture remains
  outstanding as a residual evidence item, owned as the contract
  states (section 8A.5, residual evidence paragraph).

Confirmed-contract positions this wrapper follows:

- CR-S81-001 (CONFIRMED, section 8A.5): the submission operation
  carries the pending lockout: one attempt has exactly one
  submission path, a repeat while the outcome is pending is
  rejected before it can reach the native side, and a submission
  for an attempt that already reached verified success is refused.
  The attempt-integrity carrier (this lockout, the section 8A.4
  reconciliation discipline, and the section 8A.2 decline rule) is
  the contract's attempt-key position under S81-DEC-G4-SUBDISP-01;
  no idempotency key is named or coined.
- CR-S81-002 (CONFIRMED, section 8A.4): an unknown outcome is carried
  as pending_confirmation with reconcile_required set; there is NO
  separate unknown_outcome state name, and none is invented here
  (doc 09 section 8 fixes the vocabulary at eight states). A timeout
  therefore surfaces as state pending with component_state
  pending_confirmation and reconcile_required True, and blocks every
  retry until reconciliation is recorded through the confirmed
  operation: it resolves paid on verified native success, else
  failed, following the shipped carrier's record shape
  (record_reconciliation(found_paid), attempt_recovery.py).
- CR-S81-003 (CONFIRMED, section 8A.1): eligibility is decided by the
  component through the confirmed hook confirm_entry_eligibility and
  the wrapper honors the allow or the refusal; the wrapper holds no
  eligibility verdict of its own. The local facts check inside
  submit_purchase (validators check_entry_guard over the same four
  conditions) is unchanged.
- CR-S81-004 (CONFIRMED, section 8A.2): record_decline passes
  through to the component's decline operation, whose result record
  (outcome declined, offer identity, parent order reference, the
  record that no charge was attempted, route taken) is permanently
  distinct from a failed attempt record.
- CR-S81-005 (CONFIRMED, section 8A.3): abandonment records no
  outcome and is never translated into a decline. The contract's
  "cancelled" state (an explicit pre-submission cancel, or
  abandoning a required action step after submission) has no carrier
  in D1's native action states, so a component result of "cancelled"
  still fails closed by name rather than being relabeled as a
  failure, a decline, or abandonment; that refusal is a deliberate,
  recorded decision, not a missing mapping.
- CR-S81-006 (NOT CONFIRMED, no wrapper change): the confirmed
  mapping is requires_customer_action with an auxiliary expiry
  reason and NO new state name, which supersedes the earlier
  expectation of a named expired_or_unsupported_context state. Gap 6
  / assumption A2 stay open, gated on S06's platform fact at the
  first live one-click run.
- CR-S81-007 (CONFIRMED, section 8A.6): the succeeded route is now
  sourced from the component's route-result output, never from the
  request: a paid result with no route-result output, an output
  naming a target other than the canonical U2 identity for the
  upsell_2 route, or an output contradicting the plan fails closed,
  and route_result_confirmed is True only for a route the output
  actually names.

Money-safety rules enforced locally, on top of the component:

- CR-S81-002: an attempt whose outcome is unknown (for example a
  timeout) is surfaced as pending_confirmation with reconcile_required
  set and blocks every retry until reconciliation is recorded. A
  timeout is never acceptance or decline and never justifies a second
  blind charge.
- A component result of "paid" is admitted as succeeded ONLY when it
  carries the native transaction and order references read back from
  native records (contract section 4) AND the route-result output of
  section 8A.6. A redirect or a clicked button is not payment
  evidence; a paid claim without read-backs fails closed.
- The D1-side entry guard facts are checked locally by
  validators/validate_downsell.py check_entry_guard inside
  submit_purchase (adapters/README.md: "the entry-guard validator
  enforces the D1 side of it"); the interface-side eligibility
  confirmation is the MAPPED row 1 pass-through
  confirm_entry_eligibility.
- Decline is page-layer routing (native-action-states.md): this
  wrapper's decline() never calls the component at all, charges
  nothing, removes no existing access, and routes to final thank-you
  with the original order preserved. Recording that decline through
  the component is the MAPPED row 4 point record_decline.

The component is duck-typed: any object providing the hooks
submit_purchase(context), read_result(attempt_ref),
price_disclosure(context), reconcile(attempt_ref),
confirm_entry_eligibility(entry_state), decline(context). A missing
hook on a MAPPED point fails closed with
D1-ADAPTER-POINT-NOT-PROVIDED. Component results use the contract
section 4 vocabulary (ready, validating, submitting,
pending_confirmation, paid, failed, requires_customer_action,
cancelled); this wrapper translates them into the native action
states of references/native-action-states.md, with "cancelled"
refused as recorded under CR-S81-005 above.

Stdlib only. No network, no payment client, no secrets.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validators"))
from validate_downsell import check_entry_guard  # noqa: E402


class AdapterBindingError(Exception):
    """A binding point or money-safety rule failed closed. ``code`` is
    the named error; ``detail`` carries the human-readable reason and,
    where relevant, the local guard violations."""

    def __init__(self, code, detail="", violations=None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.violations = list(violations or [])


# The six interface points of the confirmed binding map, by row.
# status: MAPPED passes through; a point that is not MAPPED fails
# closed with the named error in "error" and the component is never
# invoked. All six rows stand MAPPED: row 2 moved on CR-S81-001's
# follow-on execution (see the module docstring,
# S81-DEC-G4-SUBDISP-01). Row 2's hook is the submission operation
# itself (revision 2 section 8A.5): the pending lockout is behavior
# of that operation, and submit_purchase below is the wrapper's
# single path through it.
BINDING_POINTS = {
    "entry_guard": {
        "row": 1, "status": "MAPPED", "hook": "confirm_entry_eligibility",
        "error": None,
    },
    "pending_lockout": {
        "row": 2, "status": "MAPPED", "hook": "submit_purchase",
        "error": None,
    },
    "reconciliation": {
        "row": 3, "status": "MAPPED", "hook": "reconcile",
        "error": None,
    },
    "decline": {
        "row": 4, "status": "MAPPED", "hook": "decline",
        "error": None,
    },
    "disclosure": {
        "row": 5, "status": "MAPPED", "hook": "price_disclosure",
        "error": None,
    },
    "verified_result": {
        "row": 6, "status": "MAPPED", "hook": "read_result",
        "error": None,
    },
}

# Contract section 4 vocabulary -> native action states
# (references/native-action-states.md). "paid" is handled separately in
# _admit_result because it is admitted only with native read-backs and
# the section 8A.6 route-result output. "cancelled" is deliberately
# absent: revision 2 section 8A.3 defines it (an explicit
# pre-submission cancel, or abandoning a required action step after
# submission) but D1's native action states carry no counterpart, so
# it fails closed instead of being relabeled as a failure, a decline,
# or session abandonment (CR-S81-005, recorded decision).
_STATE_TRANSLATION = {
    "ready": "idle",
    "validating": "processing",
    "submitting": "processing",
    "pending_confirmation": "pending",
    "failed": "failed",
    "requires_customer_action": "requires_customer_action",
}

# The two pending states revision 2 section 8A.5 names (CR-S81-001):
# while the standing attempt's component state is submitting or
# pending_confirmation, a repeat submission is rejected before the
# row 2 submission point is invoked, mirroring the shipped
# purchase_state.py states that carry the operation. An attempt
# carrying reconcile_required has its own stronger block
# (CR-S81-002) and is checked before this set.
_LOCK_COMPONENT_STATES = {"submitting", "pending_confirmation"}

# CR-S81-001 gap label, RETIRED in the follow-on cycle on the
# landing of the candidate carrying revision 2 (PR #2228, train
# #2235, main 9ccd6536): the staged fail-closed label that named
# the then-undefined attempt key (named in the binding map's row 2
# record) no longer exists anywhere in this wrapper. No idempotency
# or deduplication key is named anywhere under the confirmed
# contract, by ruling: revision 2 section 8A.5 names the
# attempt-integrity carrier as the contract's attempt-key position,
# and MAIN accepted that ruling as a substituted disposition under
# S81-DEC-G4-SUBDISP-01. This wrapper invents no key.

# Per-CR status under the confirmed contract (revision 1 as completed
# by revision 2 section 8A), 2026-10-17. Provenance for the discipline
# in this file; the confirmed binding map carries the full record.
CONTRACT_STATUS = {
    "CR-S81-001": "CONFIRMED_R2_8A.5",
    "CR-S81-002": "CONFIRMED_R2_8A.4",
    "CR-S81-003": "CONFIRMED_R2_8A.1",
    "CR-S81-004": "CONFIRMED_R2_8A.2",
    "CR-S81-005": "CONFIRMED_R2_8A.3",
    "CR-S81-006": "NOT_CONFIRMED_GATED_ON_S06_FACT",
    "CR-S81-007": "CONFIRMED_R2_8A.6",
    "CR-S81-008": "CONFIRMED_R2_8A.7",
    "CR-S81-009": "CONFIRMED_R2_8A.8",
}


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


class DownsellActionAdapter:
    """Thin wrapper over the shared extra-offer action component for
    the D1 page's single purchase action, reconciled to the confirmed
    contract (see the module docstring)."""

    def __init__(self, component):
        self._component = component
        # Current attempt: {"attempt_ref": str, "state": native state}
        # or None. One D1 action per page, so one live attempt at a time.
        self._attempt = None
        self._attempt_counter = 0
        self._succeeded = False

    # ---- binding-point gate: the only path to the component --------

    def call_point(self, point, *args, **kwargs):
        """Invoke one named binding point. MAPPED points pass through
        to the component hook; a point that is not MAPPED fails closed
        with its named error and the component is never invoked."""
        spec = BINDING_POINTS.get(point)
        if spec is None:
            raise AdapterBindingError(
                "D1-ADAPTER-UNKNOWN-POINT",
                f"no binding point named {point!r} in the confirmed map")
        if spec["status"] != "MAPPED":
            raise AdapterBindingError(
                spec["error"],
                f"binding point {point!r} is {spec['status']} in the "
                f"confirmed binding map (row {spec['row']}); no call "
                "is made while the point stands unmapped in the "
                "confirmed map")
        hook = getattr(self._component, spec["hook"], None)
        if not callable(hook):
            raise AdapterBindingError(
                "D1-ADAPTER-POINT-NOT-PROVIDED",
                f"component provides no callable {spec['hook']!r} for "
                f"MAPPED binding point {point!r}; no substitute call "
                "is invented")
        return hook(*args, **kwargs)

    def binding_point_status(self, point):
        """The confirmed map status of a point (MAPPED or UNMAPPED),
        for callers that branch on it without calling."""
        spec = BINDING_POINTS.get(point)
        if spec is None:
            raise AdapterBindingError(
                "D1-ADAPTER-UNKNOWN-POINT",
                f"no binding point named {point!r} in the confirmed map")
        return spec["status"]

    # ---- MAPPED pass-throughs ----------------------------------------

    def price_disclosure(self, context):
        """Row 5, MAPPED: the exact terms shown adjacent to the action
        (amount due now, currency, one-time / recurring / trial terms,
        renewal) come from the component's disclosure data, unaltered."""
        return self.call_point("disclosure", context)

    def read_status(self, attempt_ref=None):
        """Row 6, MAPPED: read the attempt's result from the component
        and admit it under the verified-evidence discipline. A read
        that times out makes the current attempt's outcome unknown, so
        it is surfaced as pending_confirmation with reconcile_required
        set (the shipped carrier, CR-S81-002) and retry locks until
        reconciliation is recorded."""
        ref = attempt_ref or self._current_ref()
        try:
            raw = self.call_point("verified_result", ref)
        except TimeoutError:
            self._mark_reconcile_required(ref)
            return {"state": "pending",
                    "component_state": "pending_confirmation",
                    "attempt_ref": ref, "reconcile_required": True}
        admitted = self._admit_result(raw, None)
        self._track(ref, admitted)
        return admitted

    def reconcile(self, attempt_ref=None):
        """Row 3, MAPPED: reconcile the attempt against native records
        BEFORE any retry. Resolves a reconcile_required block when the
        native records record the attempt paid (verified) or failed;
        a reconciliation that itself times out or records nothing
        resolvable leaves the block in place."""
        ref = attempt_ref or self._current_ref()
        try:
            raw = self.call_point("reconciliation", ref)
        except TimeoutError:
            self._mark_reconcile_required(ref)
            return {"state": "pending",
                    "component_state": "pending_confirmation",
                    "attempt_ref": ref, "reconciled": False,
                    "reconcile_required": True}
        admitted = self._admit_result(raw, None)
        # record_reconciliation(found_paid) resolves to paid on a
        # verified native success, else failed; anything short of a
        # recorded paid/failed leaves reconciliation outstanding and
        # the retry block in place (CR-S81-002).
        admitted["reconciled"] = admitted["state"] in ("succeeded",
                                                       "failed")
        admitted["reconcile_required"] = not admitted["reconciled"]
        self._track(ref, admitted)
        return admitted

    # ---- confirmed pass-throughs: eligibility and decline -----------

    def confirm_entry_eligibility(self, entry_state):
        """Row 1, MAPPED (revision 2 section 8A.1): D1 entry
        eligibility is confirmed through the interface's eligibility
        operation. The component decides and the wrapper honors the
        result verbatim: ALLOW only when a verified parent purchase
        exists, the U1 decline event record carries u1_event equal to
        the literal "explicit_decline" (a failed or pending U1
        payment expressly does not satisfy it), the launch record
        shows the extra enabled under route law with the Q9 approval
        read, and the parent purchase did not accept U1. A refusal is
        a normal reported outcome identifying which condition(s)
        failed, not an error. The wrapper holds no eligibility
        verdict of its own; the local facts check inside
        submit_purchase remains the package validator's own
        submit-time check over the same four conditions."""
        return self.call_point("entry_guard", entry_state)

    def record_decline(self, context):
        """Row 4, MAPPED (revision 2 section 8A.2): recording a
        decline through the component's decline operation. Invoking
        the operation performs no charge action of any kind, removes
        no existing access, and leaves the original order and any
        bump purchase valid; the returned result record (outcome
        declined, the offer's identity, the parent order's reference,
        the record that no charge was attempted, the route actually
        taken) is returned verbatim and is permanently distinct from
        a failed attempt record. The buyer's decline routing itself
        is decline() below: local routing that never charges and
        never calls the component."""
        return self.call_point("decline", context)

    # ---- the D1 actions ----------------------------------------------

    def submit_purchase(self, context, entry_state):
        """The page's single D1 purchase action.

        Local discipline, in order: an attempt with reconcile_required
        outstanding blocks any retry (CR-S81-002); an attempt in a
        pending state (submitting or pending_confirmation) has its
        repeats rejected under the confirmed lockout (CR-S81-001,
        revision 2 section 8A.5); a completed purchase cannot be
        submitted twice; the D1-side entry guard (check_entry_guard)
        refuses ineligible presentations without calling the
        component. Only then does the submission pass through the
        row 2 binding point to the component's submit hook, exactly
        once for this attempt, and its result is admitted under the
        same verified-evidence discipline as read_status.
        """
        if self._attempt and self._attempt.get("reconcile_required"):
            raise AdapterBindingError(
                "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED",
                "the previous attempt's outcome is unknown (carried "
                "as pending_confirmation with reconcile_required set); "
                "record reconciliation from native records before any "
                "retry (CR-S81-002)")
        if self._attempt and self._attempt.get("component_state") \
                in _LOCK_COMPONENT_STATES:
            raise AdapterBindingError(
                "D1-ADAPTER-REPEAT-ATTEMPT-LOCKED-OUT",
                "the previous attempt is submitting or "
                "pending_confirmation; the repeat submission is "
                "rejected before the row 2 submission point is "
                "invoked, so it does not reach the native side and "
                "creates no second charge attempt (revision 2 "
                "section 8A.5 lockout, confirmed map row 2 MAPPED; "
                "the attempt-integrity carrier is the contract's "
                "attempt-key position under S81-DEC-G4-SUBDISP-01 "
                "and no idempotency key name is coined anywhere "
                "under the contract)")
        if self._succeeded:
            raise AdapterBindingError(
                "D1-ADAPTER-ALREADY-SUCCEEDED",
                "this D1 purchase already completed from verified "
                "native evidence; a second submission is refused")
        violations = check_entry_guard(entry_state)
        if violations:
            return {"state": "refused", "violations": violations,
                    "charge_attempted": False, "component_called": False}
        hook = getattr(self._component, "submit_purchase", None)
        if not callable(hook):
            raise AdapterBindingError(
                "D1-ADAPTER-POINT-NOT-PROVIDED",
                "component provides no callable 'submit_purchase' "
                "for the row 2 submission point (revision 2 section "
                "8A.5); the purchase action fails closed rather than "
                "guessing another call")
        context = context if isinstance(context, dict) else {}
        self._attempt_counter += 1
        ref = context.get("attempt_ref") or f"d1-attempt-{self._attempt_counter}"
        self._attempt = {"attempt_ref": ref, "state": "processing",
                         "component_state": "submitting",
                         "reconcile_required": False}
        # The submission itself passes through the row 2 binding
        # point (the section 8A.5 submission operation, MAPPED on
        # CR-S81-001): exactly one invocation for this attempt.
        try:
            raw = self.call_point("pending_lockout", context)
        except TimeoutError:
            self._attempt = {"attempt_ref": ref, "state": "pending",
                             "component_state": "pending_confirmation",
                             "reconcile_required": True}
            return {"state": "pending",
                    "component_state": "pending_confirmation",
                    "attempt_ref": ref, "reconcile_required": True,
                    "retry_blocked": True}
        admitted = self._admit_result(raw, context)
        admitted["attempt_ref"] = ref
        self._track(ref, admitted)
        return admitted

    def decline(self, context=None):
        """The visible decline action. Pure local routing: it never
        calls the component, never charges, removes no existing
        access, and routes to final thank-you with the original order
        (and any bump) preserved. This routing act itself records
        nothing through the component, so component_decline_recorded
        stays False here; recording the decline is the separate
        MAPPED row 4 act record_decline() (revision 2 section 8A.2),
        whose carrier is named in the result."""
        result = {
            "state": "explicit_decline",
            "route": "thank_you",
            "charge_attempted": False,
            "component_called": False,
            "base_order_preserved": True,
            "component_decline_recorded": False,
            "decline_record_carrier":
                "record_decline (row 4, MAPPED; revision 2 "
                "section 8A.2)",
        }
        if self._attempt and self._attempt.get("reconcile_required"):
            # Declining charges nothing, but the outstanding attempt
            # still owes recorded reconciliation before any retry.
            result["reconcile_still_required"] = True
        return result

    # ---- internals ----------------------------------------------------

    def _current_ref(self):
        return self._attempt["attempt_ref"] if self._attempt else None

    def _mark_reconcile_required(self, ref):
        # The shipped carrier for an unknown outcome: the attempt sits
        # at pending_confirmation with reconcile_required set
        # (CR-S81-002). There is no separate unknown-outcome state.
        if self._attempt is not None:
            self._attempt["state"] = "pending"
            self._attempt["component_state"] = "pending_confirmation"
            self._attempt["reconcile_required"] = True
        elif ref is not None:
            self._attempt = {"attempt_ref": ref, "state": "pending",
                             "component_state": "pending_confirmation",
                             "reconcile_required": True}

    def _track(self, ref, admitted):
        """Fold an admitted result into the live attempt bookkeeping."""
        state = admitted["state"]
        if state == "succeeded":
            self._succeeded = True
            self._attempt = None
        elif state in ("failed", "idle"):
            # A resolved failure (or a read-back showing nothing in
            # flight) closes the attempt; retry is permitted. A failure
            # is never recorded as acceptance or decline.
            self._attempt = None
        elif ref is not None:
            self._attempt = {
                "attempt_ref": ref, "state": state,
                "component_state": admitted.get("component_state"),
                "reconcile_required":
                    bool(admitted.get("reconcile_required")),
            }

    def _admit_result(self, raw, context):
        """Translate a component result (contract section 4
        vocabulary) into a native action state, fail-closed. Only a
        "paid" result carrying native transaction/order references
        read back from native records AND the route-result output of
        revision 2 section 8A.6 is admitted as succeeded."""
        if not isinstance(raw, dict) or _blank(raw.get("state")):
            raise AdapterBindingError(
                "D1-ADAPTER-MALFORMED-RESULT",
                "component result is not a dict with a state; nothing "
                "is admitted from it")
        state = raw["state"]
        if state == "paid":
            txn = raw.get("native_transaction_ref")
            order = raw.get("native_order_ref")
            if _blank(txn) or _blank(order):
                raise AdapterBindingError(
                    "D1-ADAPTER-PAID-WITHOUT-NATIVE-READBACK",
                    "component reported paid without the native "
                    "transaction/order references read back from native "
                    "records; a redirect or a clicked button is not "
                    "payment evidence (contract section 4)")
            # CR-S81-007 (revision 2 section 8A.6): the route is
            # sourced from the component's route-result output, never
            # from the request. No route-result output for a completed
            # outcome, an output that names no canonical identity for
            # the upsell_2 route, or an output contradicting the plan
            # is a reported failure of the action, not silently
            # accepted.
            route_result = raw.get("route_result")
            if not isinstance(route_result, dict) \
                    or _blank(route_result.get("target")):
                raise AdapterBindingError(
                    "D1-ADAPTER-ROUTE-RESULT-MISSING",
                    "component reported paid without the route-result "
                    "output of revision 2 section 8A.6; the route is "
                    "never taken from the request side")
            target = route_result["target"]
            plan_route = context.get("success_route") if context \
                else None
            if target == "upsell_2":
                u2_id = route_result.get("canonical_u2_page_id")
                if _blank(u2_id):
                    raise AdapterBindingError(
                        "D1-ADAPTER-ROUTE-U2-WITHOUT-CANONICAL-ID",
                        "route-result output routes to upsell_2 but "
                        "names no canonical U2 page id; a D1-specific "
                        "duplicate U2 is never invented")
                if route_result.get("entry_context") \
                        != "from_downsell_1":
                    raise AdapterBindingError(
                        "D1-ADAPTER-ROUTE-RESULT-MISSING",
                        "route-result output for the upsell_2 route "
                        "does not carry the D1 entry context "
                        "from_downsell_1 required by section 8A.6")
                plan_u2 = context.get("canonical_u2_page_id") \
                    if context else None
                if plan_route not in (None, "upsell_2") \
                        or (not _blank(plan_u2) and plan_u2 != u2_id):
                    raise AdapterBindingError(
                        "D1-ADAPTER-ROUTE-RESULT-CONTRADICTS-PLAN",
                        "route-result output names a U2 route or "
                        "identity the plan does not contain; reported "
                        "as a failure of the action (section 8A.6), "
                        "never silently accepted")
                route = {"target": "upsell_2",
                         "canonical_u2_page_id": u2_id,
                         "entry_context": "from_downsell_1"}
            elif target == "thank_you":
                if plan_route == "upsell_2":
                    raise AdapterBindingError(
                        "D1-ADAPTER-ROUTE-RESULT-CONTRADICTS-PLAN",
                        "route-result output routes to the final "
                        "thank-you step while the plan enables the "
                        "canonical U2 route; reported as a failure of "
                        "the action (section 8A.6), never silently "
                        "accepted")
                route = {"target": "thank_you"}
            else:
                raise AdapterBindingError(
                    "D1-ADAPTER-ROUTE-RESULT-CONTRADICTS-PLAN",
                    f"route-result output names target {target!r}, "
                    "which no D1 paid plan can contain; reported as a "
                    "failure of the action (section 8A.6)")
            return {"state": "succeeded", "component_state": "paid",
                    "native_transaction_ref": txn,
                    "native_order_ref": order, "route": route,
                    # CR-S81-007: the route above is sourced from the
                    # component's route-result output (section 8A.6),
                    # so it is component-confirmed evidence.
                    "route_result_confirmed": True}
        translated = _STATE_TRANSLATION.get(state)
        if translated is None:
            raise AdapterBindingError(
                "D1-ADAPTER-UNRECOGNIZED-RESULT-STATE",
                f"component state {state!r} has no carrier in D1's "
                "native action states (revision 2 section 8A.3 "
                "defines 'cancelled' with no D1 carrier, CR-S81-005); "
                "it is never relabeled as a failure or a decline")
        return {"state": translated, "component_state": state}
