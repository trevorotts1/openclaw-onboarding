---
name: signature-order-form
description: "Skill 79: Signature Order Form, Checkout and Signature Bump Sale. Builds the reusable native Convert and Flow checkout in two modes (combined explanation-plus-checkout for one simple offer, and post-selection checkout after Skill 78 Product Selection), owns the order bump on the original checkout, the offer details and price display, and the guarantee/terms block. Status: landed in this repository; this file makes no installation, distribution-discovery or live-payment claim."
version: 0.1.3
---

# Skill 79: Signature Order Form, Checkout and Signature Bump Sale

Status: landed in this repository, with the extra-offer interface contract
carried at revision 2. Fixture-level (L1) proof lives in the skill's own tests.
This record makes no installation, distribution-discovery or live-payment
claim; installed-location native facts stay separate and are not asserted here.

## Purpose

Own the order form page of a Signature Launch: the native Convert and Flow
checkout a buyer completes after the sales page (combined mode) or after the
product selection page (post-selection mode), including the one order bump
offered on that original checkout.

## Modes (exactly two)

1. Combined mode: explanation plus native checkout for ONE simple offer.
   Product Selection (Skill 78) is skipped. The explanation must cover what
   the product includes, who it is for, access and delivery, and important
   exclusions before the price and the native form.
2. Post-selection mode: native checkout after Product Selection. The checkout
   loads the validated selection, visibly confirms package name, billing
   schedule, quantity and price, offers a change-package path back, and
   resolves a missing or expired selection to a recovery choice. It never
   silently defaults to another package, and a changed offer or price
   binding requires clear reconfirmation before any charge.

## Hard rules

- Checkout is native Convert and Flow controls only, installed with Skill 06.
  A custom HTML block with fake card fields is forbidden. No raw card or CVC
  data in homemade inputs, logs, or screenshots, ever.
- Money is integer minor units in a declared currency and exponent. Unknown
  price is not zero and never silently free. The processor quote is
  authoritative for tax, discount, shipping and the final charge.
- The order bump references an approved offer, starts UNCHECKED, and is
  suppressed (with the accurate reason) when its entitlement is already
  included in the chosen package or already owned. Checking the box only
  modifies the pending order; the initial checkout submission processes the
  purchase. Never describe checking the box as a separate authorized charge.
- Purchase states are exactly: ready, validating, submitting,
  pending_confirmation, paid, failed, requires_customer_action, cancelled.
  A failed or pending payment is neither acceptance nor decline and never
  traverses a paid route edge. An unknown outcome must be reconciled against
  native records before any retry.
- A purchase event is emitted only from a verified paid attempt. Main plus
  bump travel in one initial event; entitlements are granted exactly once,
  keyed by tenant, verified event identity and action identity, and only
  from purchase_observed events that validate against the packet schema.
- Guarantee, terms and consent copy come from approved references in the
  checkout request, never invented per launch. Consent starts unchecked.

## Contents of this skill

- `references/checkout.schema.json`: the checkout request/result contract.
- `references/extra_offer_interface.md`: the extra-offer (post-purchase)
  interface contract for the native binding.
- `references/components/`: component drafts (order bump, offer details,
  guarantee/terms, both page assemblies) with their binding README.
- `scripts/`: the fixture-level reference models: bump model, quote display
  and billing audit, purchase state machine, selection resolver, purchase
  event handoff, the cross-field checkout validator, the native-binding
  capability matrix, and the purchase-attempt recovery model.
- `tests/`: the deterministic fixture suite for the models and components.

## Proof levels

- L1 (fixture level): fixture models, schema, state machine and static
  component checks, exercised by the skill's own tests.
- L2: rendered browser proof of the components in an authorized location,
  including a parser-based no-payment-fields assertion and visual QC.
- L3: installed-location proof with Skill 06 native binding (real native
  product and price IDs, capability matrix, coupon/tax/shipping behavior).
- L4: sandbox payment proof including native line-item read-backs and the
  S44 entitlement handoff against durable records.
L2, L3 and L4 require owner-authorized test locations and sandbox permission.
They are named facts, not completion gates for this skill. Nothing in this
skill activates a live page or a live payment.
