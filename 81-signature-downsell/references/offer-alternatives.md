# Offer Alternatives - Skill 81 (D1 as an alternative to U1)

Status: build candidate, S81 room. Governing sources: packet 11 sections 1, 4 and 6; packet 02 sections 3 and 4.

## The one rule

D1 is an **alternative** to a declined U1: a reshaped offer, either changed scope or changed payment terms. It is never an additional charge for the identical promise, and U1 and D1 are mutually exclusive at the same slot.

## Difference table (built BEFORE any copy is written - spec 11 section 4)

For every launch, record privately:

| Field | Meaning |
|---|---|
| `u1_deliverables` | What U1 delivers (A / B / C). |
| `d1_deliverables` | What D1 delivers (an approved subset or a genuinely different set). |
| `difference_kind` | `reduced_scope`, `lower_total_price`, `changed_payment_terms`, `changed_access_terms`, or an approved combination. |
| `objection_addressed` | The remaining buyer objection D1 actually answers (price total, payment timing, scope fit, commitment length). |
| `entitlements_removed_vs_u1` | Entitlement IDs in U1 but not in D1. Must be empty of anything already bought in the base checkout. |
| `rationale` | Why this alternative exists. REQUIRED. |

Hard checks:

- A lower installment is **not** a lower total price. If only the schedule changes, `difference_kind` is `changed_payment_terms` and copy must state the full total honestly.
- If D1 is equivalent to U1 at a lower price with no approved rationale, STOP: flag for owner decision. Never invent a justification.
- D1 never removes anything already bought in the original checkout.
- A payment failure is not a reason to discount: D1 is never auto-offered merely because a payment failed (spec 11 section 1).

## Recorded artifact form

The difference table is a standalone private artifact: one table per launch, recorded before any copy is written, and kept with the launch's private working records. It is not part of this skill package (the package ships this form, not any launch's table), not part of the launch record (which has no structured home for these fields), and not part of the copy document (the rationale is a private record by design).

Each row of the table records one D1 offer variant against the U1 offer it is an alternative to: the pair a request carries as `downsell_offer_ref` and `declined_u1_offer_ref`. A row carries the six fields of the table above: `u1_deliverables`, `d1_deliverables`, `difference_kind`, `objection_addressed`, `entitlements_removed_vs_u1`, and `rationale`. `rationale` is REQUIRED: a variant with no recorded rationale has no row, and the hard check above applies (STOP, flag for owner decision; never invent a justification).

The recorded row is the only source of `difference_kind` and `rationale` values downstream. The request's `difference_kind`, the result extension's `difference_matrix`, and any dispatch-time enrichment sidecar all copy the row's values; authoring or altering these values at dispatch time is not permitted.

What remains launch-specific: the storage system and file naming for the launch's table, and how a row whose `difference_kind` is an approved combination is expressed as the request's single `difference_kind` value.

## Trial and subscription disclosure (spec 11 section 4)

For a trial or subscription D1, the page and the action-adjacent disclosure must list: amount due now, trial length, renewal amount, renewal date or rule, billing interval, cancellation terms, and access implications of cancelling. The owner sample's "$1 now, $27 later" is example data only and must never be copied into a real client flow without matching approved native pricing.

## Money representation

Integer minor units in a declared currency only (doc 02 section 3). No floating-point dollars for authoritative amounts. The processor's quote is authoritative for tax, discounts, shipping and final charge.
