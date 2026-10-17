# Extra-offer action/disclosure interface (S79/S06 shared): CONFIRMED, revision 2

Status: CONFIRMED, revision 2. This document is the confirmed
contract of record for the S79/S06 shared extra-offer
action/disclosure component: how an extra offer (an upsell, a
downsell) is presented, accepted and declined,
routed, charged, recorded as an event, and audited for disclosure on
the native order form S06 installs.

Revision: 2
Date: 2026-10-17
Base: revision 1 of this contract, extra_offer_interface-CONFIRMED.md
as confirmed by S49 on 2026-10-17, SHA-256
cb2a15f7af367432824c70b5f4c287cdb65336668cd3f6e18328612797402a0b.
Purpose: to close gap G-7 (the eight interface-text completions S79
accepted under CR-S81-001..009 on 2026-10-17 and never wrote), to
record the contract owner's ruling closing gap G-4, and to record
the closure of gap G-5 by S06's concurrence filing.

What this revision changes, and what it does not:

- Sections 1 to 6 are byte-identical to revision 1. The identity was
  verified mechanically by the authoring lane; the check and the
  hashes are recorded in the lane's build report
  (followon-g7/BUILD-REPORT.md).
- Sections 7 and 10 are carried unchanged.
- Section 8 carries the confirmation-time dispositions unchanged,
  plus a revision note and one pointer per affected entry to the
  text written in section 8A.
- Section 8A is new: the eight completions, written by S49 as
  contract owner.
- Section 9 records the resulting gap state: G-4 CLOSED BY RULING,
  G-5 CLOSED, G-7 CLOSED BY THIS REVISION; G-1, G-2, G-3, and G-6
  are carried unchanged.

Confirmation of record: S49 confirmed this contract on 2026-10-17
(the confirmation record stands beside the base file). S06 concurred
on the interface positions on 2026-10-16 and on the confirmed
revision 1 text on 2026-10-17
(rooms/S06/evidence/S06-concurrence-extra-offer-interface-confirmed.md,
SHA-256 d33d93695c4126b44b4036a3cafeb11136ad3e48a24395242207a2595869bc37).
Revision 2's new text is S49's, written under contract ownership; it
claims no concurrence from any other room.

## 1. What this interface is

Doc 16 section 1 names "Extra-offer action/disclosure" a shared component:
owner "S79/S06 shared interface", consumers S80 (upsell) and S81 (downsell),
boundary "Same guarded native purchase behavior; different copy."

An extra offer is a post-initial-purchase offer in the native one-click
chain. It is NOT the order bump: doc 09 section 1 defines the bump as part
of the initial checkout (selecting it modifies the pending order; the
initial submission processes the purchase). Extra offers act only after
the initial purchase exists. Doc 09 section 8: "If the base purchase
succeeds, its entitlements are valid even if a later extra purchase fails
or the visitor closes the page."

## 2. Ownership

| Concern | Owner | Source |
|---|---|---|
| This interface contract, disclosure behavior, price-display rules | S79 | Doc 16 section 1 |
| Native installation, native form/order/upsell elements, browser delivery, capability evidence | S06 | Doc 09 section 2; doc 16 section 1; doc 05 section 8 |
| Extra-offer copy and page sequencing | S80 / S81 | Doc 16 sections 1 and 3 |
| Approved prices, routes, cross-sell relationships | S49 | Doc 09 section 2; doc 16 section 1 |
| Purchase-event consumption, entitlement grants, fulfillment | S44 | Doc 09 sections 2, 6 and 8 |
| Brand tokens and shared design infrastructure | S71 | Doc 16 sections 1 and 2 |

One writer per shared file applies: changes to native binding behavior are
requested from S06, not made by S79 inside S06's surfaces, and the reverse
applies to disclosure copy behavior.

## 3. Inputs (per extra-offer presentation)

- Tenant, location, launch and launch revision, from the approved launch
  plan (doc 09 section 3 input discipline applies to purchase-bearing
  pages).
- Parent order reference: the VERIFIED native initial purchase. An extra
  offer may be presented only in the supported native funnel/session
  context of that purchase (doc 09 section 7: "Keep the one-click chain in
  the supported native funnel/session context").
- Extra offer identity and its verified native product/price mapping
  (doc 09 section 3: displayed and submitted terms must match the verified
  native product/price objects; browser-carried price intent is not
  authoritative).
- Price disclosure data for the extra offer: amount due, any future
  installments or renewal, trial period, currency, and the
  discount/tax/shipping policy that applies (doc 09 section 3).
- Approved copy references for the offer and its disclosures (S80/S81 own
  the copy profiles; doc 16 section 3 gives upsell and downsell the owner's
  eight-section derived profiles, while checkout itself uses transactional
  clarity and complete billing disclosures).
- Next routes for extra-offer success, decline and error, from the approved
  route plan (S49).
- Capability evidence reference for the selected native form, gateway,
  payment method and billing type (doc 09 section 7 capability matrix;
  recorded in the checkout request as `native_capability_evidence_ref`,
  a required field of S79's own checkout request schema:
  `work/schema/checkout.schema.json`, `$defs/checkout_request`).

## 4. Outputs

- The extra-offer action result in the same purchase-state vocabulary as
  doc 09 section 8 (ready, validating, submitting, pending_confirmation,
  paid, failed, requires_customer_action, cancelled), where only a
  verified native success result counts as paid; a redirect or a clicked
  button is not payment evidence (doc 09 section 8).
- The native transaction/order references for the extra purchase, read
  back from native records, for the purchase-automation handoff.
- A normalized extra-purchase event for S44 identifying the parent initial
  order it belongs to, so S44 inspects the actual native line items
  (doc 09 section 6 establishes this inspection duty for the initial
  order's event; the parent-link field shape for extra events is an open
  question for S44, section 7).
- A billing display audit result for the extra offer's displayed terms,
  using the same audit discipline as the initial checkout (doc 09
  section 9).
- On failure: the failure state and the approved failure copy reference,
  with the initial purchase explicitly unaffected (section 6).

## 5. Disclosure requirements

- The actual charge for the extra offer and any recurring obligation are
  shown before the buyer authorizes it; price is required before payment
  authorization (doc 09 sections 3 and 4 state this for checkout; the same
  material-fact rule is the interface's working requirement for extras).
- No hidden or prechecked charges, and no manipulative decline wording
  (doc 09 section 6 states these for the bump; doc 16 section 1 assigns
  extras the "same guarded native purchase behavior").
- Behavior is never promised uniformly across payment methods: doc 09
  section 7, "Do not claim every payment method has identical upsell
  behavior." Where a one-click route is unsupported, the interface either
  disables that route or uses an explicitly approved standard checkout
  fallback "with clear disclosure and user choice" (doc 09 section 7).
- Decline is a normal routed outcome, not an error state, and the copy
  for it comes from the approved S80/S81 profiles (doc 16 section 3).

## 6. The no-rollback rule (binding on both sides)

Doc 09 section 8, stated as interface law:

1. "Submit the verified event to S44's short event handler promptly; do
   not hold access until the optional upsell chain ends."
2. "An upsell failure must not roll back the base purchase automatically."
3. The base purchase's entitlements remain valid if a later extra
   purchase fails, is declined, or the visitor closes the page.

Consequences for implementers: the extra-offer action must not gate,
delay, or condition initial-purchase fulfillment; an extra-offer error
path must never render as an initial-purchase failure; and retry of an
extra offer reconciles against native records first, under the same
unknown-outcome discipline as the initial purchase (doc 09 section 8).

## 7. Dispositions of the draft's open interface questions

The draft's section 7 listed nine questions as requiring confirmation,
not invention. Each question below carries exactly one disposition:
ANSWERED FROM THE FILED RECORD, ANSWERED BY S49 RULING OR RECORD, or
OPEN GAP (in whole or in a named part). Where an answered question has a
residual evidence item outstanding, the residue is carried in section 9
and named here. No answer below is invented: each cites the filed record
it rests on.

### Q1 (S06): native element and event names; how verified success is surfaced

Disposition: ANSWERED FROM THE FILED RECORD in its surfacing rule;
OPEN GAP in its names (G-1).

- Surfacing rule (answered): paid counts only after a native read-back
  confirms success. S06 concurs with the stricter read-back requirement
  as its own built discipline: S06 exposes no synchronous success result
  that it treats as proof for anything, and every verification surface
  it built is read-back shaped. A verified native success result or a
  native read-back is the evidence route, and the read-back is the
  carrier the caller gates on.
- Exact native element and event names for the one-click extra-offer
  action: not present in any filed record. S06 states they are captured
  at the first live extra-offer install and filed as a supplement to
  its concurrence; S06 will not guess them, and neither does this
  contract. Carried as G-1.
- Source: S06 concurrence on S79's interface positions, Q1 (2026-10-16).

### Q2 (S06): capability evidence representation and signer

Disposition: ANSWERED FROM THE FILED RECORD.

- Base record: the doc 05 section 3 `environment-capabilities.json`
  (schema `skill6-environment-capabilities/1`, with evidence timestamps
  and verified location), produced and owned by S06 (S06-02). The
  checkout request references capability evidence through
  `native_capability_evidence_ref` rather than embedding a copy.
- Matrix placement (S06's counter, recorded as the position of
  record): the per-payment-method and per-billing-type matrix (doc 09
  section 7) is scoped to the selected native form, gateway, and funnel
  configuration, and lives in a companion per-form capability record.
  The base capabilities record carries a pointer to the companion
  (path plus hash). `native_capability_evidence_ref` references the
  companion per-form record, which itself references the base record,
  so a consumer resolves the full chain from one reference.
- Cardinality: one base capabilities record per probe run, per runtime
  and location. These records are evidence snapshots (append-only per
  run, each carrying its own timestamps), never a singleton silently
  overwritten.
- Signer: producer attestation. S06 signs as producer. The attestation
  is the record's own contents (producing tool and schema version named
  in the record), its internal evidence timestamps, and its SHA-256
  carried by the run record that references it. There is no PKI or
  cryptographic signature anywhere in the packet or the tree, and this
  interface invents none.
- Source: S06 concurrence, Q2 (2026-10-16).

### Q3 (S06): what the wrapper may style or configure; native-theme-only properties

Disposition: ANSWERED FROM THE FILED RECORD in its boundary;
OPEN GAP in its per-element map (G-2).

- Boundary (answered): the wrapper sets namespaced classes, token
  variables, layout, and spacing around the native element and nothing
  inside it; internal appearance changes go only through supported
  native properties inside the native form builder; parent CSS is
  never assumed to reach cross-origin internals; styling never touches
  payment authorization or token handling; form names, labels, error
  messages, and focus order are preserved (doc 16 section 6; doc 05
  section 8). This is Skill 6's standing doctrine and built practice.
- Interim binding rule (answered): until the live capture says
  otherwise, every internal property of an extra-offer native element
  is treated as native-theme-only or cannot-be-changed-safely, and no
  extra-offer element property is claimed as changeable beyond the four
  doctrine classes above.
- Per-element styling map for the extra-offer elements, property by
  property: installed-builder evidence of the same kind as Q1's names,
  filed by S06 with that capture. Carried as G-2.
- Source: S06 concurrence, Q3 (2026-10-16).

### Q4 (S06): decline, error and pending destinations; per offer or per funnel step

Disposition: ANSWERED FROM THE FILED RECORD.

- In S06's install pattern, one funnel step hosts exactly one extra
  offer: S06 builds each upsell and downsell as its own funnel step,
  and its step-type classification treats upsell and downsell steps as
  purchase steps, one offer per step. The per-offer equivalence is an
  install-pattern commitment, not an assumption.
- Native destination binding is per funnel step. Under the
  one-offer-per-step pattern, per-step binding is per-offer in effect,
  and two offers' destinations cannot merge. Destinations are declared
  in the approved route graph per offer slot (doc 02 section 4) and
  recorded per installation.
- Live confirmation of the binding on installed extra-offer steps rides
  the first live extra-offer install, with the Q1 capture; the contract
  answer does not wait on it.
- Source: S06 concurrence, Q4 (2026-10-16).

### Q5 (S06): standard-checkout fallback when one-click is unsupported; disclosure placement

Disposition: ANSWERED FROM THE FILED RECORD.

- When the capability matrix shows one-click unsupported for the
  buyer's payment method, the one-click route for that method is
  disabled, and the extra offer's step offers a standard native
  checkout for that same offer, built from the same native order
  elements as the primary checkout (a native order form step for the
  extra offer), reached by the visitor's explicit choice.
- Disclosure placement: at the point the fallback is offered, on the
  extra-offer presentation, rather than only on the fallback checkout
  surface. The extra-offer step is an S06-built page, so offer-point
  disclosure is renderable natively, and S06 commits to that placement.
- The fallback produces the same purchase states and the same
  normalized event for S44 as a one-click purchase; no successful
  result is ever faked; the base purchase is never affected.
- Sources: S06 concurrence, Q5 (2026-10-16); doc 09 section 7.

### Q6 (S06): native session expiry on extra-offer eligibility; how expiry is surfaced

Disposition: ANSWERED FROM THE FILED RECORD in behavior and mapping;
OPEN GAP in the platform fact (G-3), expressly gated as below.

- Behavior (answered): on expiry the extra offer is neither silently
  dropped nor converted into a charge; the visitor is offered the
  standard-checkout fallback (Q5) with disclosure and choice; expiry is
  never a decline (the decline edge requires the visitor's explicit
  decline action) and never a failure of the base purchase.
- Mapping (answered): expiry stays inside doc 09 section 8's fixed
  vocabulary and is carried as `requires_customer_action` with an
  auxiliary expiry reason field: one state vocabulary, one
  machine-readable surface for the reason. (S79's reply to CR-S81-006
  proposed adding a named `expired_or_unsupported_context` state once
  S06 states the fact. Under the concurred mapping no new state name
  is added to the interface vocabulary; a consumer's page-layer render
  naming is its own surface, not the interface vocabulary.)
- Platform fact (gap): whether the native session context imposes an
  expiry, its duration, and how the native surface signals it are
  native platform facts not held as captured evidence anywhere in the
  filed record. They are UNVERIFIED (LIVE_PROOF_PENDING class),
  capturable only at the first live one-click extra-offer run; S06
  files the captured fact as a supplement when that run's evidence
  exists. Carried as G-3.
- Sources: S06 concurrence, Q6 (2026-10-16); S06 addendum to S81, item
  2 (2026-10-17); S79 reply to CR-S81-001..009, CR-S81-006 (2026-10-17).

### Q7 (S44): field linking an extra-purchase event to its parent initial order; same schema or sibling

Disposition: ANSWERED BY S49 RULING.

- Same schema: extra-purchase events ride the same normalized
  purchase-event envelope as the initial event, never a sibling
  schema. Slots distinguish the lines; dedupe and action keys are
  built on verified provider event identity and line identity.
- The link field is `parent_order_ref`: OPTIONAL, nullable, type
  ["string", "null"], minLength 1 when present and non-null. Semantics:
  the opaque provider order identity of the initial order, populated
  ONLY when the provider's native read-back on the extra event
  actually carries it. Never synthesized, never derived, never
  required, and never load-bearing for dedupe, grants, or revocations:
  in the native platform a later extra purchase is generally its own
  order record with its own transaction, so S44's durable linkage is
  and remains the buyer's book (tenant_id, launch_id, contact_ref)
  plus verified transaction and line identity.
- Version and status, stated honestly: `parent_order_ref` is added in
  purchase-event schema v1.2, with v1.1 and v1.0 preserved
  byte-untouched. The v1.2 candidate (PR #2190) was presented for the
  owner's approval on 2026-10-17 and awaits that approval; it is not
  yet landed. On landing, S44 builds dual-acceptance for v1.2 (registry
  dispatch on the stamped version, fail closed on unknown versions)
  per its filed commitment, and producers emit the field only from
  real provider read-backs after that.
- This disposition closes the open clause carried in section 4 above
  ("the parent-link field shape for extra events is an open question
  for S44, section 7").
- Sources: CR-S44-003 (S44, 2026-10-16); S49 ruling on CR-S44-003
  (2026-10-17); S44 response to the S79 concurrence round, Q7
  (2026-10-16).

### Q8 (S44): extra-offer outcomes S44 records for refund/chargeback handling, and in what shape

Disposition: ANSWERED FROM THE FILED RECORD.

- Shape: append-only entries on the same purchase-event envelope; the
  original paid record is never deleted or rewritten; effects scope to
  the affected line only.
- Recorded vocabulary (S44's normalizer/processor, as implemented):
  `event_type` values are `purchase_observed`, `refund_observed`,
  `payment_updated`, `subscription_updated` (subscription
  cancellations and renewals enter as `subscription_updated`; renewals
  that bill are also purchase events for the new cycle). Money-effect
  rule: an event with `event_type` `refund_observed`, or
  `payment_status` `refunded` / `partially_refunded`, applies the
  revocation for its lines only. `payment_status` is taken only from
  verified native transaction state; a bare submission is `unknown`
  and grants nothing.
- Chargebacks are reconciliation-driven: S44 has no distinct
  chargeback event type and has never observed a native chargeback
  event; chargebacks surface through read-back reconciliation of
  transaction state and are applied through the refund-class path for
  the affected line. If a distinct native chargeback event kind is
  ever evidenced, a distinct `chargeback_observed` type is named
  through the S49 CR route rather than silently folded in. This
  interface therefore records chargeback handling as
  reconciliation-driven, as S44 directed.
- Recorded partial (S44's own statement): cancellation-shaped native
  kinds are currently quarantined by S44's normalizer pending its
  adapter addendum (recorded, not dropped; their entitlement effect
  follows the approved policy once the addendum lands). Carried as
  G-6.
- Source: S44 response to the S79 concurrence round, Q8 (2026-10-16).

### Q9 (S49): decline-then-downsell chain approval per launch; where the approval is recorded

Disposition: ANSWERED BY S49 RECORD.

- Yes: decline-then-downsell chains are approved per launch, and the
  single approval record for the chain is the route graph as bound
  into the approved launch record. There is no separate cross-sell
  approval in offer relationship metadata, and this interface must not
  look for one. Offer relationship metadata (the record's `excludes` /
  compatibility declarations) governs which offers may coexist (for
  example, U1 and D1 mutual exclusion must be declared there); it does
  not approve or create the chain.
- The authoritative enabled-slot state is the launch record's `extras`
  booleans (`upsell_1`, `downsell_1`, `upsell_2`). The route graph is
  DERIVED from the record by the deterministic compiler; the graph's
  node set is the materialization of those booleans, not an
  independent source. The check this interface performs is three-way
  agreement: (a) the graph's SHA-256 equals the record's
  `route_graph_hash`; (b) the graph's roles equal the roles the record
  compiles to (validate_graph enforces this and fails closed on any
  divergence); (c) the plan approval covers the record content.
- The approval tie: the record's `plan_approval_ref` points to an
  approval record of approval type `launch_plan_build` binding
  `plan_document_hash`, computed over the record content including the
  route group (graph ref, graph hash, extras) and the offer set;
  lifecycle fields (`status`, `plan_approval_ref`) are excluded from
  that hash by design. Only a `launch_plan_build` approval approves
  the chain; no other approval type (budget, test location, merge,
  publication, or any other) substitutes for it. If the record content
  changes after approval, the hash changes and the existing approval
  no longer binds; re-approval is the path.
- Guard law, confirmed as implemented: upsell_1 disabled requires
  downsell_1 and upsell_2 disabled; upsell_2 is reachable only after an
  accepted upsell_1 or downsell_1, never after both are declined; a
  pending or failed payment traverses no paid edge and is never a
  decline.
- Source: S49 concurrence on S79's interface positions, Q9
  (2026-10-16), `handoffs/S49-concurrence-s79-q9-int03.md`.

## 8. Disposition of CR-S81-001..009 against this revision

Revision 2 note (2026-10-17). The dispositions below are the
confirmation-time record and are carried unchanged. The accepted
text they record as unwritten is written in this revision at
section 8A; each affected entry carries a pointer to its
subsection. Gap G-7 is closed by this revision; gap G-4 is closed
by the ruling at section 8A.5; gap G-5 is closed by S06's
concurrence filing. Section 9 records the resulting gap state.

S81 filed nine change requests against the draft on 2026-10-16
(CR-S81-001..009). S79 answered all nine on 2026-10-17
(`handoffs/change-requests/S79-REPLY-CR-S81-001-009.md`), accepting
interface-text changes into this revision. The S79 room then closed
without writing the revision. The dispositions below record, per
request, what the confirmed contract position is on the filed record,
and what remains unwritten. Unwritten accepted text is carried in
section 9 (G-7), never silently assumed.

- CR-S81-001 (pending lockout and idempotency carrier): lockout
  behavior position is on the record. While an attempt's outcome is
  pending (submitting or `pending_confirmation`), a repeat submission
  is rejected: one attempt has exactly one submission path, so one
  pending attempt can produce at most one charge. Carrier of record:
  the shipped purchase-attempt state machine (S79's
  `purchase_state.py`), per S79's reply. The native side has NO
  lockout or deduplication of record: S06's filed position is "no
  native attempt lockout or dedup is known; do not rely on one"
  (S06 addendum to S81, item 3, 2026-10-17; the deduplication that
  exists of record is pipeline-level in S44's event store and
  adapter-level in Skill 82, and the platform records exactly one
  transaction per recorded payment on an invoice). The
  deduplication/idempotency KEY is named in no filed record: G-4. The
  express interface-text carry of the lockout was among S79's accepted
  changes and was never written: G-7. Revision 2: the accepted lockout text is written at section 8A.5, which also records the ruling closing G-4.
- CR-S81-002 (unknown outcome and reconciliation): the naming position
  is settled on the record. No separate `unknown_outcome` state name
  exists, and none is invented: doc 09 section 8's vocabulary is fixed
  at eight states. The unknown outcome's named carrier is
  `pending_confirmation` with `reconcile_required` set. A retry is
  refused until the caller records reconciliation; reconciliation
  resolves to paid on a verified native success or to failed when not
  paid; paid routing is held while reconciliation is outstanding.
  Carrier of record for the operation's shape: S79's shipped
  `attempt_recovery.py`, per S79's reply; the discipline itself is
  section 6 law above. The express carry of the state representation
  and the reconciliation operation (inputs, outputs,
  no-retry-until-resolved rule) into the interface text for extra
  offers was accepted by S79 and never written: G-7. Revision 2: the accepted reconciliation operation text is written at section 8A.4.
- CR-S81-003 (entry-guard eligibility): the underlying approval
  question is Q9, answered above. The eligibility OPERATION definition
  (an allow/refuse result over: verified parent purchase; explicit U1
  decline, with failed/pending expressly not satisfying it; D1 enabled
  in the approved launch record; U1 not accepted) was accepted by S79
  and never written: G-7. Revision 2: the accepted eligibility operation is written at section 8A.1.
- CR-S81-004 (decline operation and no-charge guarantee): carried in
  part by sections 5 and 6 (decline is a normal routed outcome, not an
  error; a decline never rolls back the base purchase; base
  entitlements remain valid if a later extra is declined). The decline
  OPERATION, its result record (kept permanently distinct from
  `failed`), and the express statement that invoking decline performs
  no charge action and removes no access were accepted by S79 and
  never written: G-7. Revision 2: the accepted decline operation and result record are written at section 8A.2.
- CR-S81-005 (abandonment semantics): the governing principle is on
  the record: a decline exists only on the visitor's explicit decline
  action (Q6 disposition; section 6), so abandonment, including
  closing the page, is never a decline, and no decline event may be
  fabricated from it. The express abandonment/decline/cancelled
  distinction text was accepted by S79 and never written: G-7. Revision 2: the accepted abandonment distinction text is written at section 8A.3.
- CR-S81-006 (expired or unsupported context): disposed as Q6 above.
  Behavior and mapping are confirmed; the platform fact is G-3,
  expressly gated on S06's live capture at the first live one-click
  extra-offer run.
- CR-S81-007 (route-result output): not carried in the confirmed text.
  The route-result output (the target identity actually routed to; for
  D1 paid, the canonical U2 identity from S49's route graph; and the
  entry context, `from_downsell_1`) was accepted by S79 and never
  written: G-7. Revision 2: the accepted route-result output is written at section 8A.6.
- CR-S81-008 (billing display audit criteria): carried in part by
  sections 3 and 4 (the disclosure data set is an interface input; a
  billing display audit result is an interface output, under the
  initial checkout's audit discipline, doc 09 section 9). The
  enumerated audit criteria and the express placement ruling were
  accepted by S79 and never written: G-7. S79's recorded
  recommendation, stated as a recommendation and not a ruling: values
  are audit-checked against the binding; placement is a page-layer
  responsibility; the interface should say exactly that. Revision 2: the accepted audit criteria and the express placement ruling are written at section 8A.7.
- CR-S81-009 (tenant/location binding read-back): carried for the
  initial checkout in shipped code (S79's `selection_flow` validates a
  selection's tenant and location against the live catalog read-back
  and refuses cross-tenant use). For extra offers, the binding
  read-back output and its mismatch failure signal (read-back from the
  installed configuration, never echoed from the request; a mismatch
  is a reported failure with no charge path proceeding) were accepted
  by S79 and never written: G-7. Revision 2: the accepted read-back output and mismatch signal are written at section 8A.8.

## 8A. Interface text completions for extra offers (revision 2)

This section is new in revision 2. It writes, as contract text, the
interface-text completions S79 accepted on 2026-10-17 in its reply to
CR-S81-001..009 and never wrote, carried open at confirmation as gap
G-7. It is written by S49 as contract owner of this contract. Each
subsection names the change request it discharges and the position of
record it implements. Where a subsection states operational detail
that no filed position supplies, the detail is the minimal text the
accepted position and sections 1 to 6 imply, written under the same
contract ownership; the authoring lane's build report marks each such
passage. Nothing in this section changes sections 1 to 6, and every
rule here is read subject to section 6 (no rollback) and section 4
(only a verified native success counts as paid).

### 8A.1 Eligibility operation (CR-S81-003)

The eligibility operation decides, before an extra offer is
presented or its action enabled, whether the visitor may be offered
that extra offer at all. It is an interface operation: the caller
invokes it with the facts below and gates rendering on its result.
The facts are the facts Skill 81's shipped entry guard
(check_entry_guard) consumes; this subsection is the interface
definition of that check.

Inputs: (a) the parent order reference, with the parent purchase's
verified status from native read-back; (b) the recorded outcome of
the preceding upsell offer (U1) for the same parent purchase,
carried in the field u1_event of the journey entry evidence the
operation consumes; (c) the approved launch record for the launch,
from which the extra offer's enabled state is read (the record's
extras, under route law, with the approval read of section 7, Q9:
the route graph bound into the approved launch record, checked three
ways); and (d) whether U1 was accepted (u1_accepted).

Rule: the operation returns ALLOW only when all four hold: (1) a
verified parent purchase exists for this buyer and this session;
(2) U1 was explicitly declined: u1_event carries the literal value
"explicit_decline" (a failed or pending U1 payment expressly does
not satisfy this condition, and neither does the absence of a U1
outcome); (3) the extra offer (D1) is enabled in the approved launch
record; and (4) U1 was not accepted.

Output: an allow or refuse result. A refusal is a normal reported
outcome, not an error state and not a silent absence: the result
identifies which condition or conditions failed. On a refusal, the
extra offer is not presented, no extra-offer action is enabled, and
no charge path is opened. A reference to the entry evidence is a
name, never evidence: the operation computes the result from the
evidence record itself, per the entry_guard_ref definition recorded
in Skill 81's references/native-action-states.md and accepted under
CR-S49-005.

### 8A.2 Decline operation and decline result record (CR-S81-004)

The decline operation records the visitor's explicit refusal of an
extra offer. Its inputs name which offer is declined and which
parent order the decline belongs to.

Express statement: invoking decline performs no charge action. It
removes no existing access, and it leaves the original order and any
bump purchase valid. Decline is not a submission: no charge attempt
is created by it, the lockout and reconciliation operations do not
apply to it, and it cannot be charged under any retry.

Result record: every completed decline produces a decline result
record carrying the outcome as declined, the identity of the offer
declined, the parent order reference, the record that no charge was
attempted, and the route taken (the decline target from the approved
route plan). The decline result record is kept permanently distinct
from a failed payment outcome: declined and failed are different
records, neither is ever relabeled as the other, and a failed
extra-offer payment is never recorded as a decline. The decline
action is a separate action from the purchase action: invoking one
never invokes the other. On a completed decline the visitor routes
per the approved route plan's decline route for the step (for D1,
the final thank-you step).

### 8A.3 Abandonment (CR-S81-005)

Abandonment is the visitor leaving or closing the page, or the
session ending, without acting on the extra offer. It is distinct
from both of its neighbours: it is not an explicit decline (no
decline action was invoked, so no decline result record under
section 8A.2 exists), and it is not a cancelled purchase attempt
(the cancelled state of section 4 covers an explicit pre-submission
cancel and a customer abandoning a required action step after a
submission).

Rule: abandonment records no outcome for the extra offer. No decline
event is created from it, no decline result record is produced, and
no downstream record may treat abandonment as a decline. The extra
offer simply remains unpurchased, and base-order fulfillment
proceeds independently of it (section 6). A decline exists under
this interface only where the visitor's explicit decline action
produced one.

### 8A.4 Reconciliation operation (CR-S81-002)

Trigger and state representation: when an extra-offer attempt's
outcome is unknown (the submission timed out, the connection
dropped, or the browser context was lost while the attempt was
submitting or awaiting confirmation), the attempt stands in state
pending_confirmation with reconcile_required set. That pair, state
plus flag, is this interface's named carrier of an unknown outcome.
No unknown_outcome state name exists in the interface vocabulary or
is added by this revision; the vocabulary remains the eight states
of section 4 (doc 09 section 8).

Operation: reconcile the attempt against native records before any
retry. Inputs: the parent order reference, the attempt reference, or
the equivalent identity the caller holds for the attempt under
reconciliation. The operation reads the native records for that
attempt (native read-back, sections 2 and 4: only a verified native
success counts as paid) and records the reconciliation outcome on
the attempt.

Outputs, exactly one per completed reconciliation: (a) resolved
paid: a verified native success exists for the attempt; the attempt
moves to paid, carrying the native transaction and order references
read back from native records, and paid routing may proceed;
(b) resolved failed: the native records show the attempt was not
paid; the attempt is a known failure, its reconcile_required is
cleared, and only from this resolution may a fresh submission be
made; (c) still unknown: the native records do not yet resolve the
attempt; the attempt remains in pending_confirmation with
reconcile_required set, and the operation may be run again.

Rules: no retry of the submission is accepted while reconciliation
is outstanding; a retry is refused until the caller records the
reconciliation of the earlier attempt. Paid routing is held while
reconciliation is outstanding: no paid route edge is traversed for
the attempt until it resolves paid. An attempt restored after a lost
browser context carries the same reconciliation requirement as a
timed-out attempt: restore does not clear the hold, and a
context-free restore can never claim an existing paid order. This
operation is the interface text of the discipline section 6 states
in prose; its record shape follows the shipped carrier (the shared
component's attempt record: record_reconciliation(found_paid)).

### 8A.5 Submission lockout operation (CR-S81-001)

Operation: submit an extra-offer attempt. One attempt has exactly
one submission path. While an attempt's outcome is pending (state
submitting or state pending_confirmation), a repeat submission of
the same attempt is rejected: it does not reach the native side, it
creates no second charge attempt, and the standing attempt is
unaffected. Guarantee: one pending attempt can produce at most one
charge. A submission offered for an attempt that has already reached
verified success (paid) is likewise refused: the attempt is
complete. A failed attempt with a known outcome may be submitted
afresh only as section 8A.4 allows (after reconciliation, where
reconciliation was required).

The lockout is behavior of the shared action under this interface
for extra offers, as it is for the initial purchase (doc 09
section 8, carried by the shipped purchase-state machine). It does
not depend on any native lockout or deduplication, none being known
on the native side (section 8, CR-S81-001); attempt integrity under
this contract is carried by the ruling that follows.

Attempt-integrity carrier: ruling of the contract owner (closes
G-4). Ruling of the contract owner (S49), recorded in revision 2.
The attempt-integrity carrier is this contract's attempt-key
position. The carrier is a named discipline, not a key: (1) the
pending lockout of section 8A.5, under which a repeat submission
while an attempt's outcome is pending is rejected, so one pending
attempt can produce at most one charge; (2) the reconciliation
operation of section 8A.4, under which no retry is accepted until
an unknown outcome is reconciled against native records; and (3)
the decline rule of section 8A.2, under which invoking decline
never charges. Where an interface of this kind would name an
idempotency key, this contract names the attempt-integrity carrier
instead. The reason is stated on the face of the ruling: S06's filed
position is that no native deduplication exists to key on, so a
coined key name would misdescribe the native side. The discipline
is what actually prevents a duplicate charge, and it is the carrier
S81's reconciliation evidence cites for CR-S81-001: the discipline
recorded in S81's reply to CR-S49-005, item 7. Supersession: if S06
later ships native deduplication for extra-offer attempts, a later
revision of this contract names that key and supersedes this
ruling; until then no key name is coined anywhere under this
contract, and the interim discipline recorded at gap G-4 in
revision 1 is no longer interim: it is the contract's position.
Residual evidence: CR-S81-001's acceptance-evidence fixture, a
fixture or test result from the owning side showing two submissions
during one pending attempt producing exactly one charge attempt,
remains outstanding, owned as the record states. It is an evidence
item, not an open contract position; gap G-4 is closed by this
ruling with that single residual noted.

### 8A.6 Route-result output (CR-S81-007)

On a completed extra-offer outcome, the action returns a
route-result output carrying the target identity actually routed to
and the entry context under which that target was entered.

For a paid D1 outcome with U2 enabled, the target is the canonical
U2 identity from S49's route graph: the same U2 that follows a U1
acceptance, never a D1-specific duplicate; the entry context is
from_downsell_1. For a paid outcome where the next step is not
enabled, the target is the destination the approved route plan names
(for D1, the final thank-you step). For a declined outcome, the
output carries the decline target actually routed to (for D1, the
final thank-you step). For a failed outcome, no paid edge is
traversed: the output records the error destination the approved
route plan names for the step (for D1, remaining on the D1 step in a
recoverable state), and never a paid target.

The route result is the record of the route actually taken. The
approved route plan is the plan-side truth: a route result that
contradicts the plan (including a success target that differs from
the compiled graph's paid edge for the step) is a reported failure,
not a routing choice.

### 8A.7 Billing display audit: criteria and placement ruling (CR-S81-008)

The billing display audit result named in section 4 is produced for
the extra offer's displayed terms, checked against the price
disclosure data set of section 3 (the binding). The audit criteria
are enumerated; each criterion is reported pass or fail by name in
the audit result:

1. Amount due: the amount due now is displayed, and the displayed
   value equals the binding's amount due for the offer.
2. Currency: the currency is displayed, and equals the binding's
   currency.
3. Terms as bound: the displayed billing terms match the binding's
   billing type: one-time (a single charge, with no recurring
   obligation stated or implied beyond it), recurring (amount,
   interval, and renewal terms), trial (the trial period, and the
   renewal amount and the renewal date or rule that follows it), or
   installment (the installment schedule and the full total
   obligation).
4. No understated total: a lower installment or a trial entry amount
   is never presented as a lower total price; the full obligation
   is displayed.
5. Policy data: the discount, tax, and shipping treatment is
   displayed as it applies to the offer, matching the binding's
   policy data.
6. Cancellation terms: for a trial, recurring, or installment
   offer, the cancellation terms are present in the displayed
   terms.
7. Shown before authorization: the actual charge and any recurring
   obligation are displayed before the buyer authorizes the extra
   offer (section 5), and no charge is hidden or prechecked.

Placement ruling (contract owner, revision 2): the audit checks
values against the binding; it does not audit placement. Where the
terms sit on the page (adjacency to the action, type size, and the
like) is a page-layer responsibility, governed by the page skill's
own rules, and is not an interface audit criterion. This ruling
adopts as the contract's position the recommendation recorded in
S79's reply to CR-S81-008. The audit result itself lives with the
action's outputs: it is returned as an output of the extra-offer
action for the attempt (section 4) and recorded with the attempt's
other outputs; it is not a page artifact.

### 8A.8 Tenant and location binding read-back (CR-S81-009)

For an extra offer, the interface returns a binding read-back output
carrying the tenant and the location the extra-offer action is
actually bound to. The values are read back from the installed
configuration (S06 is the installed binding source, section 2).
They are never echoed from the request:
a read-back value that merely repeats the request's tenant or
location is not a read-back.

Mismatch signal: if the read-back tenant or location differs from
the tenant and location the request carries (section 3, from the
approved launch plan), the interface reports a binding mismatch
failure for the attempt, and no charge path proceeds: under a
mismatched binding the extra-offer action is neither offered nor
submitted. The same rule already governs the initial checkout (the
shipped selection flow validates against live catalog read-back and
refuses cross-tenant use); this subsection carries the output and
the signal for extra offers.

## 9. Open gaps

Each gap below is named, owned, and carried on this contract's face.
Nothing in this section authorizes any room to assume the missing item. Items closed since confirmation are recorded in place below, marked CLOSED, so the gap numbering of record does not move.

- G-1 (from Q1): the exact native element and event names for the
  one-click extra-offer action in the current Skill 06 builder.
  Owner: S06. Gate: the first live extra-offer install; S06 files the
  names as a supplement to its 2026-10-16 concurrence when captured.
- G-2 (from Q3): the per-element styling map for extra-offer native
  elements, property by property, including which properties are
  native-theme-only. Owner: S06. Gate: the same live capture as G-1.
  Until then the interim rule in the Q3 disposition binds.
- G-3 (from Q6 / CR-S81-006): the native session-expiry platform fact:
  whether an expiry exists, its duration, and how the native surface
  signals it. Owner: S06. Class: LIVE_PROOF_PENDING; capturable only
  at the first live one-click extra-offer run; S06's supplement is
  owed the cycle that run's evidence exists.
- G-4 (from CR-S81-001): CLOSED BY RULING in revision 2. The
  naming of the deduplication/idempotency key for extra-offer
  purchase attempts is dispositioned by the contract owner's ruling
  at section 8A.5: the attempt-integrity carrier (pending lockout;
  unknown-outcome reconciliation before any retry; decline never
  charges) is this contract's attempt-key position, and no key name
  is coined, for the reason the ruling states on its face (S06's
  filed position: no native deduplication exists to key on). The
  interim contract position recorded here in revision 1 is
  superseded by that ruling. One residual evidence item remains
  outstanding and is not an open contract position: CR-S81-001's
  acceptance evidence (a fixture or test result from the owning side
  showing two submissions during one pending attempt producing
  exactly one charge attempt), owned as the record states.
- G-5: CLOSED in revision 2. S06 filed its one-shot concurrence
  on this confirmed text on 2026-10-17
  (rooms/S06/evidence/S06-concurrence-extra-offer-interface-confirmed.md,
  SHA-256 d33d93695c4126b44b4036a3cafeb11136ad3e48a24395242207a2595869bc37),
  concurring with no objection to any passage, and stating that the
  S81-05 reconciliation may cite the filing as its S06 evidence leg.
  The concurrence covers the confirmed (revision 1) text; revision
  2's completions at section 8A are written by S49 as contract owner
  and state no S06 position beyond S06's filed record.
- G-6 (from Q8): cancellation-shaped native kinds are quarantined by
  S44's normalizer pending S44's adapter addendum (recorded, not
  dropped; entitlement effect follows the approved policy once the
  addendum lands). Owner: S44.
- G-7 (from CR-S81-002/003/004/005/007/008/009 and the text half
  of CR-S81-001): CLOSED BY THIS REVISION. The interface-text
  completions S79 accepted on 2026-10-17 and never wrote are written
  at section 8A: 8A.1 eligibility operation; 8A.2 decline operation
  and result record, with the express no-charge, no-access-removal
  statement; 8A.3 abandonment distinction; 8A.4 reconciliation
  operation; 8A.5 submission lockout operation (with the G-4
  ruling); 8A.6 route-result output; 8A.7 enumerated billing-display
  audit criteria with the express placement ruling; 8A.8
  tenant/location binding read-back output with its mismatch failure
  signal. Sections 7 and 8 remain the record of what was settled at
  confirmation; this section records the resulting gap state.

## 10. Proof boundary

This document plus the capability matrix fixture are L1 preparation.
Native binding (S79-06) still requires S06's installed native form in an
authorized test location, and transaction proof remains L3/L4 work. No
statement here claims a real location supports one-click extras.

Confirmation of this contract is a status act on the contract text. It
changes no proof level, installs nothing, and claims no live capability.
