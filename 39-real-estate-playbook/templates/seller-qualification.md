# Seller Qualification Question Set

Ask CONVERSATIONALLY — one or two at a time. Honor fair-housing guardrails. The
goal is to understand motivation and set up an evidence-based CMA conversation
(never reveal a price before the CMA walk-through — see the Sales-Brain RE
extension).

## 1. Motivation
- What's prompting the move? (upsizing, downsizing, relocation, life event, financial)
- How firm is the decision to sell?

## 2. Timeline
- When would you ideally like to be sold/closed?
- Is anything driving that date (a new purchase, job, season)?

## 3. Price expectation (handle with care)
- Do you have a number in mind? (capture it, but do NOT validate or anchor on it)
- Then: "Let me put together a CMA from verified comparable sales so we anchor on
  real data, not a guess." (Never reveal a value before the CMA; never fabricate
  comps — if no comps provider is keyed, say so and defer the number.)

## 4. Occupancy
- Is the home owner-occupied, tenant-occupied, or vacant?
- If tenant-occupied: lease terms / showing constraints?

## Outcome
- Set `role: seller`; tag `ZHC-seller-lead`.
- Emit a `qualify` event. Route to a listing specialist per `lead-routing-protocol.md`.
- Surface the state disclosure pointer (seller side) and escalate the decision to the licensed agent.
- Queue the CMA: geocode → comps (provider-gated; honest gap if no key).
