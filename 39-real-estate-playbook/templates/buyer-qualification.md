# Buyer Qualification Question Set

Ask these CONVERSATIONALLY — one or two at a time, woven into the conversation —
never as a checklist interrogation. Honor fair-housing guardrails
(`references/fair-housing-guardrails.md`): objective criteria only.

## 1. Timeline
- When are you hoping to be in your new home?
- Is there a hard date driving that (lease end, job, school year, sale of a current home)?

## 2. Financing
- Are you paying cash or financing?
- Have you been pre-approved yet, or would a connection to a lender help?
- What monthly payment or price range feels comfortable? (price band, not a hard limit)

## 3. Neighborhood / area
- Which areas or commute targets matter most?
- What objective criteria define the right area for you (proximity to work, lot size, walkability)?
  > Do NOT ask about or note demographic makeup — fair-housing prohibits steering.

## 4. Must-haves vs nice-to-haves
- What are the non-negotiables (beds/baths, parking, single-story, yard)?
- What would be nice but you could live without?
- Anything that's an absolute dealbreaker?

## Outcome
- Set `role: buyer`; tag `ZHC-buyer-lead`.
- If investor signals appear (ROI, rental, portfolio) → `role: investor`, tag `ZHC-investor-lead`.
- Emit a `qualify` event. Route per `lead-routing-protocol.md`.
- If a property address came up: geocode → lookup/comps/Street View (provider-gated; honest gap if no key — never fabricate a value).
