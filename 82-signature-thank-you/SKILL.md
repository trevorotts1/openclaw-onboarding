---
name: signature-thank-you
description: Builds the terminal Signature Launch thank-you / confirmation page — the final purchase-confirmation and access experience that shows exactly what the customer actually purchased (verified against the normalized purchase snapshot and S44 entitlement state), its actual charges and terms, and what happens next. This is NOT an upsell page and carries NO new pitch, new offer, or new-charge CTA; a page that says "thank you" while selling something is an upsell page owned by Skill 80. Purchased product names, amounts, totals, order numbers, and billing schedules are allowed and required here because they identify completed purchases. Fulfillment authority is S44 — this skill consumes entitlement state, never grants it, and fulfillment never depends on the buyer reaching this page.
version: 0.3.1
---

# Signature Thank-You and Fulfillment (Skill 82)

The terminal purchase-confirmation role for a Signature Launch. One reusable
skill with purchase-aware variants; never a separately authored skill per
purchase combination. Spec: packet doc 12 (S82-01 … S82-09); acceptance:
doc 18 units A13 (final summary and access exactly reflect purchases),
A14 (no-pitch allows actual purchased names/amounts), A20 (base fulfillment
survives tab close and extra-offer failure).

## What this skill produces / owns

- `references/no-pitch-policy.md` — the launch-mode no-pitch rule and the
  migration mapping from Skill 49's legacy `prove_sf_no_pitch` behavior
  (S82-01).
- `references/layout-and-copy-profiles.md` — the layout contract for
  the S82-owned Order summary / access blocks shared component (packet
  doc 16 §1) and the clean copy profiles: paid, partially-pending,
  pending, failed-extra (S82-04).
- `references/states.md` — delayed reconciliation (bounded retry /
  backoff), provider-outage cached view with "Unresolved items", and
  the wrong-order-reference / stale-session / native-read-failure
  error states; never a fake sample receipt (S82-06).
- `references/access-and-privacy.md` — the S82-07 security contract:
  order resolution only via native authenticated context or a
  short-lived opaque server-side reference, guessed/stale references
  rejected, access destinations that independently authorize the
  buyer, no PII in URLs/analytics/logs/screenshots, and the
  shared-computer rule; noindex alone is never claimed as security.
- `references/s44-fulfillment-continuity.md` — the S82-08 handoff
  contract with S44: fulfillment begins on the purchase event and
  never depends on a page visit (A20), the fulfillment-map states S82
  consumes, the single-send dedupe rule, refund handling, and the L4
  evidence still owed back from S44.
- `references/native-order-summary-integration.md` — the S82-05
  integration contract: the native Order Summary is preferred when
  verified for the selected funnel, custom content reads the same
  validated snapshot and never invents items, grouping is by native
  order relationship only (never shared email), and the live half
  (S79/S80/S81 installed mappings + S06 native read) is named as
  L3/L4-pending, not faked.
- `references/branch-matrix.md` — the S82-09 branch matrix: every
  doc 18 / spec §10 case touching the final thank-you, each marked
  COVERED-L1 (exact test cited), COVERED-DOC (contract only), or
  PENDING-L3/L4 (missing live proof named).
- `references/semantic-review-protocol.md` — the A14 independent
  semantic review layer (observation O-02): surfaces, pitch tests,
  verdict recording, and how a fail reopens S82-04.
- `scripts/purchase_event_adapter.py` — turns normalized purchase
  events (packet purchase-event shape) into one verified snapshot per
  native order, in the exact shape the resolver consumes: main+bump
  in one event stay together, later extras under the same native
  order append, identical redeliveries dedupe, conflicting ones
  raise, mixed-tenant/launch streams are rejected, and
  `require_live_evidence=True` refuses test or evidence-less events
  (S82-05 offline half).
- `scripts/render_thank_you.py` — renders the resolved order view (and
  the S82-06 states) as one self-contained accessible HTML fragment:
  `ty82-`-namespaced classes, semantic landmarks, an aria-live status
  region, the summary as a real text table, per-item Paid / Pending /
  Failed labels, access blocks only for entitlements in the view, and
  every action carrying its allowed `data-cta-class`.
- `schemas/thank-you-request.schema.json`,
  `schemas/thank-you-result.schema.json`,
  `schemas/order-view.schema.json`,
  `schemas/run-manifest.schema.json` — the input/output contracts (S82-02).
- `scripts/thank_you_resolver.py` — the one authoritative
  entitlement-to-block resolver: verified purchase snapshot in, order view
  out (S82-03). No page-local duplicate ledger.
- `scripts/validate_thank_you.py` — structured no-pitch validator
  (provenance + CTA classification, not a token blacklist).
- `scripts/validate_entitlements.py` — displayed entitlement set must equal
  the verified purchased entitlement set, exactly.
- `scripts/validate_access.py` — every access destination is https,
  claim-free (no identity/entitlement query parameters), independently
  authorizing, and keyed to an entitlement in the view (S82-07).
- `scripts/confirmation_observation.py` — builds the deterministic
  `confirmation_shown` dedupe observation (page render emits no send;
  S44 owns the single onboarding send) (S82-08).
- `scripts/run_manifest.py` — builds the run manifest emitted
  alongside (never inside) each thank-you result document: the run's
  `independent_review` facts and the `native_bindings_ref` /
  `provenance` of the inputs consumed, stated honestly or null,
  never fabricated (CR-S49-004 Path B companion contract).
- `scripts/semantic_scan.py` — the A14 semantic PRE-SCREEN (explicitly
  not the review itself): flags candidate pitch phrases in rendered
  copy for the independent reviewer (S82-09).
- `tests/test_thank_you.py` — the 64 packet normal-path fixtures, the five
  terminal purchase sets × bump, and the negative matrix.

## The rule in one screen

| Allowed / required (launch mode) | Prohibited |
|---|---|
| Actual purchased product names | Any new / unpurchased offer, recommendation, or "one more thing" pitch |
| Unit amounts, totals, order number | Any CTA that initiates a new charge (including hidden one-click) |
| Billing schedule / recurring terms for purchased items | Premium access claimed from a URL/query string (`vip=true`, names, email) |
| Access / download / scheduling CTAs for purchased benefits | "You are all set" for a purchase that is still pending |
| Support and manage-purchase CTAs | Withholding valid base access because an extra is pending/failed |

Every CTA is classified as one of: `access`, `download`, `manage_purchase`,
`support`, `schedule_included_service`, `noncommercial_next_step`.

## Purchase truth

- The order view is built **only** from a verified normalized purchase
  snapshot (packet purchase-event shape, extended per line item with
  `payment_status`, display name, and billing terms) plus the S44
  entitlement/fulfillment map. URL parameters, page-visit history, and
  contact/email matching are never authority.
- The view resolves from purchases, not pages visited: visiting U1/D1
  without buying displays none of their entitlements.
- Terminal purchase sets (U2 enabled): none; U1; U1+U2; D1; D1+U2 — each
  with or without the checkout bump, multiplied by the selected main
  package. U1 and D1 are mutually exclusive. (U2 disabled: none; U1; D1.)
- Per-item status is always separated: paid, pending, and failed items are
  labeled individually. A pending/failed extra never removes or blocks
  base access (A20).
- Historical or other-journey purchases are never grouped into this view
  by shared email; the resolver consumes only this journey's snapshot.

## Fulfillment authority (S44)

S44 owns granting entitlements and operational messages; this page only
consumes their state. Fulfillment begins on successful purchase and does
not depend on reaching this page — closing the tab after checkout cannot
strand the customer, and the confirmation email/access fallback is
coordinated with S44 (no duplicate onboarding sends from page + worker).
Access links point only to official protected destinations, which must
independently authorize the buyer; a page-render condition is never the
security boundary for premium access. Refunds/cancellations update access
through the approved entitlement policy and never remove an unrelated
original purchase.

## Privacy

No raw payment credentials ever enter a request, view, log, or fixture.
Fixtures use TEST ONLY dummy identities. Receipt data must not leak
through URL parameters, analytics, cached HTML, or screenshots; a shared
computer's next visitor must not see a previous buyer's receipt.

## Running the validators

```bash
python3 scripts/validate_thank_you.py --view order-view.json --snapshot snapshot.json
python3 scripts/validate_entitlements.py --view order-view.json --snapshot snapshot.json [--fulfillment fulfillment.json]
python3 scripts/validate_access.py --view order-view.json --links link-manifest.json
python3 scripts/confirmation_observation.py --view order-view.json
python3 scripts/run_manifest.py --view order-view.json [--snapshot snapshot.json] [--fulfillment fulfillment.json]
python3 scripts/purchase_event_adapter.py --events purchase-events.json [--require-live-evidence]
python3 scripts/semantic_scan.py rendered-thank-you.html
python3 -m unittest discover -s tests -v
```

Exit 0 = pass, 1 = validation errors (printed one per line).

## Boundaries

- Skill 80 owns purchase-bearing upsell instances (including pages that
  open with "thank you" and then sell). Skill 49 keeps its legacy
  no-name/no-price thank-you behavior in legacy mode only — see
  `references/no-pitch-policy.md`.
- Native order-summary integration (S82-05): the offline half is
  built — the event-to-snapshot adapter and the integration contract
  in `references/native-order-summary-integration.md`. The live half
  (installed S79/S80/S81 native product mappings, an S06 native order
  read, L4 sandbox proof) remains a named blocker, never a fake
  sample receipt. Delayed/pending/error UX (S82-06) is built:
  see `references/states.md`. Access/security (S82-07) and the S44
  continuity contract (S82-08) are built at the offline/L1 level:
  see `references/access-and-privacy.md` and
  `references/s44-fulfillment-continuity.md`; the live (L3/L4) proof
  items named there remain pending and are not claimed.
