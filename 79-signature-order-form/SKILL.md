---
name: signature-order-form
description: "Skill 79: Signature Order Form, Checkout and Signature Bump Sale. Builds the reusable native Convert and Flow checkout in two modes (combined explanation-plus-checkout, the wired mode, one order form per offer price choice under per_offer_instances; and post-selection checkout after Skill 78 Product Selection, which is fixture-only and outside the done claim), owns the order bump on the original checkout, the offer details and price display, and the guarantee/terms block. Status: landed in this repository; this file makes no installation, distribution-discovery or live-payment claim."
version: 0.1.10
---

# Skill 79: Signature Order Form, Checkout and Signature Bump Sale

Status: landed in this repository, with the extra-offer interface contract
carried at revision 2. Fixture-level (L1) proof lives in the skill's own tests.
This record makes no installation, distribution-discovery or live-payment
claim; installed-location native facts stay separate and are not asserted here.

## Purpose

Own the order form page of a Signature Launch: the native Convert and Flow
checkout a buyer completes after the sales page (combined mode) or after the
product selection page (post-selection mode, fixture-only), including the one order bump
offered on that original checkout.

## Modes (exactly two)

1. Combined mode: explanation plus native checkout for ONE simple offer.
   Product Selection (Skill 78) is skipped. The explanation must cover what
   the product includes, who it is for, access and delivery, and important
   exclusions before the price and the native form.
2. Post-selection mode (FIXTURE-ONLY, not part of the done claim; the wired
   route is `per_offer_instances`, see below): native checkout after Product Selection. The checkout
   loads the validated selection, visibly confirms package name, billing
   schedule, quantity and price, offers a change-package path back, and
   resolves a missing or expired selection to a recovery choice. It never
   silently defaults to another package, and a changed offer or price
   binding requires clear reconfirmation before any charge.

Realised route (owner decision, `83-black-friday-launcher/DECISIONS-PENDING.md`,
section "Ceiling"): Skill 83 calls this skill in combined mode only. For
`multiple_options` and `folded_levels` it emits ONE `combined_single_offer`
request per (main offer, price choice) under `per_offer_instances`, each with its
own page id and `selection_ref` null. The post-selection code
(`scripts/selection_flow.py`, `references/components/post-selection-checkout.html`)
is fixture-only and is excluded from every done claim until a host wires it.

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
  REVIEW-ONLY: these drafts are design references and are not installable;
  never paste them into a Skill 06 custom-code block. Order bump and consent
  are native order-form settings, never custom inputs.
- `scripts/`: the fixture-level reference models: bump model, quote display
  and billing audit, purchase state machine, selection resolver, purchase
  event handoff, the cross-field checkout validator, the native-binding
  capability matrix, and the purchase-attempt recovery model.
- `scripts/emit_checkout_manuscript.py`: the order form page's copy manuscript,
  written from the approved checkout request, the launch record and the approved
  checkout terms (see Design stages).
- `tests/`: the deterministic fixture suite for the models and components.

## Design stages (wireframes and mockups)

This skill builds no page images itself. The order form page's desktop and mobile wireframes
and visual mockups come from Skill 71's shared image service (`71-blackceo-signature-page/
scripts/shared_page_service.py`) on the five-section structure in
`71-blackceo-signature-page/references/copy-specs/roles/checkout.json`, run by Skill 49's
`49-signature-funnel/scripts/checkout_wrapper.py` (the design-only dispatch adapter). The section
order is the reading order in `references/components/QC-STATES.md`. The native form is never
drawn as card fields and is never built or bound by those stages: it stays Skill 06's.

The manuscript those stages read is not hand-written: `scripts/emit_checkout_manuscript.py`
writes the five sections from the approved checkout request (it must pass
`validate_checkout.validate_copy_request`: the full request check, price approval and bump gates
included, except that the three Skill 06 read-back keys the copy never uses are not required; the
production gate `validate_checkout.validate_request` still requires them), the launch record's offer names and the approved
`checkout_terms` text, and puts `<!-- source_request_sha256: <sha256 of the request file> -->`
on line 1. `verify_source_stamp` (or `--check`) refuses a manuscript whose stamp is missing or
no longer matches the request; the Skill 49 checkout wrapper makes the same check inline.
A recommended (not separately approved) price is accepted at the production gate only when the
request's `launch_plan_approval_ref` is a `launch_plan_build` approval that the shared
verifier confirms, the same rule Skill 78 applies.

## Design direction (Skill 45)

Design direction = Skill 71 structure + Skill 45 card/rules via `design_prose.py`. The order form page's design-only stages follow the same direction. The page's sections are Skill 71's; its look comes from the client's chosen Skill 45 style card (a registered `FN-` id, optional) and the design library's funnel page rules, composed into `design-prose.json` by `shared-utils/signature_launch/design_prose.py` and passed to Skill 71 as `--design-prose`. The file records the sha256 of every Skill 45 file it read, so a hand-typed file, an edited one, or one built against rules that have since changed is refused (`design_prose.check_design_prose`). Skill 45 is only read, never written.

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

## Python dependency: jsonschema (operator note, never for the client)

`scripts/validate_checkout.py` imports `jsonschema`. On a Homebrew or Debian Python (externally managed, PEP 668)
pip refuses a plain or `--user` install, so the package lives in the shared pydeps folder
`<root>/pydeps/py<major>.<minor>/` (`$OC_PYDEPS_DIR` as-is, else `$OPENCLAW_ROOT`, else `/data/.openclaw` when it
exists, else `$HOME/.openclaw`; `$HOME/.claude/pydeps/py<X.Y>/` is also looked up), installed with
`pip install --target`. The validator puts that folder on `sys.path` itself before it imports, so plain `python3`
works: no venv, no activation step. Never use `--break-system-packages`, never create a venv, never tell the client.
If the import fails, check with `bash update-skills.sh --check` and run the one sanctioned fix from
`83-black-friday-launcher`: `python3 -m launcher_core.cli dependencies --install`.
