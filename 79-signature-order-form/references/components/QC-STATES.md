# S79-09 QC state matrix (draft level)

Rendered (L2) proof is still owed in an authorized location. This matrix is
the checklist that proof must satisfy; every row names the component state,
the rule it serves, and the draft-level evidence that exists today.

## State coverage

| Surface | States | Draft evidence |
|---|---|---|
| Order bump | offered_unchecked, selected (same block, box checked by visitor), suppressed_included, suppressed_previously_purchased, disabled_unavailable | order-bump.html; bump fixture model tests |
| Offer details | one-time, scheduled installments, recurring, trial-then-recurring disclosures | offer-details.html; display model + audit tests |
| Selection | proceed summary, recovery (missing/expired), reconfirm (changed offer/price) | post-selection-checkout.html; selection resolver tests |
| Purchase status | pending, failed, requires_customer_action, paid confirmation | checkout-status.html; state machine tests |
| Native slot | present in both modes; no homemade payment fields | static component tests |

## Accessibility checks for L2 proof

- Every control has a wrapping label; bump and consent checkboxes are real
  inputs, keyboard reachable, with a visible scoped focus outline.
- Status changes announce through the polite live region; failed and
  customer-action states use role alert.
- Touch targets: bump/consent checkboxes render at least 22px, 26px under
  the 640px breakpoint.
- Color is never the only signal: failed state carries explicit copy, not
  just the error color.
- Reading order: explanation, offer details, bump, guarantee/terms, native
  slot, status region, in both modes.

## Mobile checks for L2 proof

- Price lines stack under 640px; no horizontal scroll at 360px width.
- The native slot remains fully usable; component CSS never restyles native
  controls (all component selectors are namespaced or scoped under
  .sig-checkout).

## Visual QC checks for L2 proof

- Bright palette from Skill 71 brand tokens; no dark styling.
- Displayed totals on the rendered page match the billing display audit
  output for the same fixture inputs (due now, installments, disclosures).
- Screenshots for QC contain no card data (the native slot is never filled
  with real payment details in test captures).

## Forbidden in every state

- A success or thank-you claim on a failed or pending state.
- A pre-checked bump or consent box.
- Any copy describing the bump checkbox as a separate charge.
- Any price, guarantee, or policy substance not traceable to an approved
  reference in the checkout request.
