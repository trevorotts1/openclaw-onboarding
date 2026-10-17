# Extra-offer action/disclosure interface (S79/S06 shared) - DRAFT

Status: fixture-level interface preparation for S79-06. Nothing here is
installed or confirmed with S06. Statements drawn from the packet are cited
by document and section; every statement that still needs S06 (or S44/S49)
confirmation is listed as an open interface question in section 7 and must
not be treated as settled.

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

## 7. Open interface questions (require confirmation, not invention)

For S06:
1. What are the exact native element and event names for the one-click
   extra-offer action in the current Skill 06 builder, and how is a
   verified native success for an extra purchase surfaced to the caller
   (synchronous result, native read-back, or both)?
2. How is capability evidence represented per payment method and billing
   type (the doc 05 section 3 `environment-capabilities.json` shape, a
   per-form record, or another artifact), and who signs it?
3. What exactly may the wrapper style or configure for extra-offer native
   elements, per the doc 16 section 6 native-element styling map, and
   which properties are native-theme-only?
4. How are decline, error and pending destinations for an extra offer
   configured in the native funnel, and can they be set per offer or only
   per funnel step?
5. When one-click is unsupported for the buyer's payment method, what is
   the approved standard-checkout fallback flow S06 installs, and where
   is the required disclosure shown?
6. Does the native session context impose an expiry on extra-offer
   eligibility after the initial purchase, and how is expiry surfaced?

For S44:
7. What field links an extra-purchase event to its parent initial order,
   and does S44 want extra events on the same normalized purchase-event
   schema as the initial event or a sibling schema?
8. Which extra-offer outcomes must S44 record for refund/chargeback
   handling, and in what shape?

For S49:
9. Are decline-then-downsell chains (S80 decline routing to S81) approved
   per launch in the route plan, and where is that approval recorded so
   this interface can check it instead of assuming it?

## 8. Proof boundary

This document plus the capability matrix fixture are L1 preparation.
Native binding (S79-06) still requires S06's installed native form in an
authorized test location, and transaction proof remains L3/L4 work. No
statement here claims a real location supports one-click extras.
