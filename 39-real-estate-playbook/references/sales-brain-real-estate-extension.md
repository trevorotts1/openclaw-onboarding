# Sales Best Practices — Real-Estate Extension (ADDITIVE)

> This file is an **additive extension** to Skill 38's
> `protocols/sales-best-practices-protocol.md`. It is installed by Skill 39's
> `scripts/05-install-sales-brain-extension.sh` as a NEW file in the client's
> installed Skill 38 (`protocols/sales-best-practices-real-estate-extension.md`)
> and is loaded ONLY when the conversation is in a real-estate sales context.
> It **extends, never replaces** Skill 38's own protocol — that file is left
> byte-unchanged (verified by hash at install).

## When this extension is active

A real-estate sales context (RE conversation workflow tagged, RE journey
template active, or RE-intent detected). Outside an RE context it is not loaded,
so a non-RE client's sales brain is unaffected.

## RE objection patterns (on top of Skill 38's 6 generic patterns)

| Objection | Pattern |
|---|---|
| **Commission** ("why X%?") | Reframe on net proceeds + what the full service delivers (pricing, marketing, negotiation, transaction management). Anchor on outcome, not rate. Never disparage discount brokers; differentiate on value. |
| **"Zillow says it's worth more"** | Acknowledge the estimate, then walk the CMA: automated estimates are not appraisals and miss condition/updates/micro-location. Anchor on verified comps (never fabricate a number). |
| **Dual agency** | Be transparent about representation; surface the state pointer; escalate the disclosure/consent decision to the licensed agent. |
| **"We'll wait for rates to drop"** | Acknowledge the concern; reframe on date-the-rate / total cost of waiting vs price movement; never predict rates as fact. |
| **FSBO ("we'll sell it ourselves")** | Respect the choice; offer value on the hard parts (pricing, exposure, qualified buyers, negotiation, paperwork); no pressure. |

## CMA pricing-reveal timing

- **Never reveal a price before the CMA walk-through.** Walk the comparable
  sales first so the number is anchored on evidence, not on the seller's hoped
  list price or a portal estimate.
- Anchor on **verified comps** from the provider abstraction. If no comps
  source is keyed, say so honestly and defer the number — do NOT invent one.
- Distinguish list price from likely sale price and from automated estimates.

## SPICED-RE (the RE-tuned discovery frame)

Skill 38 offers BANT / MEDDIC / SPICED. For real estate, use **SPICED-RE**:

- **S — Situation:** current home / living situation (own/rent, size, location).
- **P — Pain:** why move now (outgrown, downsizing, commute, schools, life event).
- **I — Impact:** the cost of staying / not moving (financial + lifestyle).
- **C — Critical event:** the hard date — lease end, job start, school year,
  closing on the next home.
- **E — Decision:** who signs / co-decides (spouse, co-owner) and the timeline.
- **(D)ecision-criteria:** must-haves vs nice-to-haves, budget band, area.

## Honesty floors (inherited + RE-specific)

- Never quote a price/comp/value that is not provider-verified or explicitly
  flagged as the client's own estimate.
- Never give legal/lending/appraisal advice; escalate to the licensed
  professional.
- Fair-housing: never tailor the pitch by protected class.
