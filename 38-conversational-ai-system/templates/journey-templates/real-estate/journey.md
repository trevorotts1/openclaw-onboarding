# Customer Journey Template — Real Estate

This template defines the workflows a complete real-estate practice (buyer's
and seller's agents) should have, from first lead through closing and the
long-tail anniversary/referral cycle. Real estate is high-stakes, time-sensitive,
and referral-driven — speed-to-lead and post-close nurture matter most.
(Source bullet: add Listing Update Alerts, Showing Confirmations, Offer Status
Updates, Closing Day, Post-Close Anniversary workflows.)

## Pre-purchase workflows

### 1. New Lead → Speed-to-Lead Qualify
**Trigger:** Lead from a portal (Zillow/Realtor), website, sign call, or ad form
**Purpose:** Respond within minutes (lead value decays fast) and qualify
buyer vs seller, timeline, financing/price
**Conversation phases:**
- Phase 1 — Instant acknowledgment; capture buyer or seller intent
- Phase 2 — Qualify: area, price band, timeline, pre-approval (buyer) or
  reason/timeline (seller)
- Phase 3 — Offer the next step (buyer consult / listing appointment)
**Success action:** Consult/listing appointment booked; tag `ZHC-buyer-lead` or
`ZHC-seller-lead`; brief the agent

### 2. Listing Update Alerts (buyers)
**Trigger:** A new/updated listing matches a buyer's saved criteria
**Purpose:** Keep active buyers engaged with timely, relevant inventory
**Conversation phases:**
- Phase 1 — Send the matching listing(s) with the key facts
- Phase 2 — Ask if they want to tour; gauge interest level
**Success action:** Showing requested or feedback captured to refine criteria;
tag `ZHC-listing-alert-engaged`

## Purchase moment / transaction workflows

### 3. Showing Confirmations
**Trigger:** A showing/open house is scheduled
**Purpose:** Cut no-shows and prep both sides
**Conversation phases:**
- Phase 1 — Confirm date/time/address + access details
- Phase 2 — Reminder 24h and 2h before; capture cancellations early
**Success action:** Showing confirmed; post-showing feedback prompt queued; tag
`ZHC-showing-confirmed`

### 4. Offer Status Updates
**Trigger:** An offer is submitted, countered, accepted, or rejected
**Purpose:** Keep an anxious client informed at every step of a high-stakes
negotiation
**Conversation phases:**
- Phase 1 — Plain-language status of where the offer stands and what's next
- Phase 2 — On counter → set expectations + route decision to the agent fast
**Success action:** Client informed; decision points escalated to the agent;
tag `ZHC-offer-active`

## Onboarding / under-contract workflows

### 5. Under Contract → Closing Checklist
**Trigger:** Offer accepted / under contract
**Purpose:** Shepherd inspection, appraisal, financing, and contingency
deadlines so the deal doesn't fall through
**Conversation phases:**
- Phase 1 — Lay out the timeline and each deadline
- Phase 2 — Nudge on upcoming milestones (inspection, appraisal, final loan)
- Phase 3 — Flag any at-risk deadline to the agent immediately
**Success action:** Milestones tracked + reminders firing; tag `ZHC-under-contract`

## Engagement workflows

### 6. Closing Day
**Trigger:** Closing date arrives
**Purpose:** Make the biggest day feel handled and celebratory
**Conversation phases:**
- Phase 1 — Day-of logistics (time, place, what to bring)
- Phase 2 — Congratulations + immediate "what now" (keys, utilities, move-in)
**Success action:** Closing logistics confirmed + congratulations sent; tag
`ZHC-closed`; queue the review/testimonial ask

## Retention workflows

### 7. Post-Close Anniversary & Home-Value Nurture
**Trigger:** 1, 3, 6, 12 months post-close, then annually
**Purpose:** Stay top-of-mind for the next transaction and referrals (real
estate is a long-cycle referral business)
**Conversation phases:**
- Phase 1 — Check-in + an annual home-value / market update they'd care about
- Phase 2 — Light, no-pressure "know anyone buying or selling?" referral ask
**Success action:** Value/market touch delivered; referral captured if offered;
tag `ZHC-post-close-nurture`

## Win-back / sphere workflows

### 8. Past-Client & Sphere Reactivation
**Trigger:** Past client silent 12+ months, OR a life-event/market signal
(rates drop, neighborhood comp sells)
**Purpose:** Re-engage the agent's sphere for repeat and referral business
**Conversation phases:**
- Phase 1 — Relevant reason to reach out (market move, anniversary)
- Phase 2 — Offer a no-obligation home valuation or buyer consult
**Success action:** Valuation/consult offered; tag `ZHC-sphere-reactivation`

## Notes on Real-Estate-specific tone

- Speed-to-lead is the #1 conversion driver — respond in minutes, not hours.
- High-stakes emotions: be calm, plain-spoken, and reassuring through
  negotiation and closing.
- Never give legal, lending, or fiduciary advice the agent must own — escalate
  those to the agent.
- Compliance: follow fair-housing language; never steer by protected class.
- Match the agent's voice from Business Brain (luxury-concierge vs
  high-volume-friendly).
