# Customer Journey Template — SaaS

This template defines the workflows a complete SaaS subscription business should
have, from trial signup through activation, expansion, and churn prevention.
SaaS lives and dies on activation and net revenue retention, so the journey is
usage-signal-driven. (Source bullet: add Activation Tracking, Feature Discovery,
Usage Drop Alerts, Trial-to-Paid Conversion, Subscription Pause/Resume workflows.)

## Pre-purchase workflows

### 1. Trial Signup → Activation Tracking
**Trigger:** New trial/free account created
**Purpose:** Drive the user to their first "aha" / activation event fast
**Conversation phases:**
- Phase 1 — Welcome + the single first action that delivers value (the
  activation event), not a feature tour
- Phase 2 — If activation event not hit within 24-48h → nudge with the shortcut
**Success action:** Activation event reached; tag `activated`; if not, tag
`activation-stalled` and queue the rescue nudge

### 2. Pre-Sale / Plan Question
**Trigger:** Prospect asks about pricing, limits, integrations, or "does it do X"
**Purpose:** Remove the evaluation blocker and steer to the right plan
**Conversation phases:**
- Phase 1 — Answer from the product/pricing Knowledge Source
- Phase 2 — Map their use-case to the right tier; surface trial → paid path
**Success action:** Plan recommended; tag `pre-sale`; route complex/enterprise
asks to a human

## Onboarding workflows

### 3. Feature Discovery / Onboarding Sequence
**Trigger:** Activated, but core features unused (event-based, not time-based)
**Purpose:** Expand usage breadth so the product becomes sticky
**Conversation phases:**
- Phase 1 — Surface the next high-value feature relevant to THEIR usage so far
- Phase 2 — Offer a quick how-to / template / docs link
**Success action:** Feature adopted; tag `feature-<name>-adopted`

## Purchase moment workflows

### 4. Trial-to-Paid Conversion
**Trigger:** Trial nearing expiry (e.g. 3 days left) OR usage limit approaching
**Purpose:** Convert the trial before it lapses
**Conversation phases:**
- Phase 1 — Recap the value/usage they've gotten so far (proof)
- Phase 2 — Make upgrading one tap; resolve the blocker (price, approval,
  data migration)
**Success action:** Upgraded to paid; tag `converted`; if not, tag `trial-lapsed`
and queue win-back

## Engagement workflows

### 5. Usage-Drop / Health Alert
**Trigger:** Active account's usage drops sharply or logins stop (leading churn
indicator)
**Purpose:** Intervene BEFORE the renewal/cancel decision
**Conversation phases:**
- Phase 1 — Check-in: "noticed you've been away — anything blocking you?"
- Phase 2 — Offer help (onboarding refresh, a missing integration, a call)
**Success action:** Usage recovers OR escalate to CS/account owner; tag
`at-risk`

### 6. Expansion / Upsell Signal
**Trigger:** Account hits a plan limit, adds seats, or shows power-user behavior
**Purpose:** Capture expansion revenue (the core of net revenue retention)
**Conversation phases:**
- Phase 1 — Recognize the growth; surface the higher tier/add-on that fits
- Phase 2 — Offer the upgrade path; route enterprise expansion to a human
**Success action:** Expansion conversation/upgrade; tag `expansion-opportunity`

## Retention workflows

### 7. Renewal & Subscription Pause/Resume
**Trigger:** Renewal date approaching, OR a cancellation/pause request
**Purpose:** Save the subscription — offer pause as an alternative to churn
**Conversation phases:**
- Phase 1 — On renewal: reaffirm value; confirm seamless continuation
- Phase 2 — On cancel/pause intent: ask why; offer pause, downgrade, or a fix
  instead of full cancellation
**Success action:** Renewed, paused (recoverable), or downgraded rather than lost;
tag `renewed` / `paused` / `saved`

## Win-back workflows

### 8. Churned-Account Win-Back
**Trigger:** Subscription canceled / lapsed 30-60 days ago
**Purpose:** Re-acquire churned users, especially after shipping the fix for
their churn reason
**Conversation phases:**
- Phase 1 — "Here's what's new since you left" tied to their original churn
  reason
- Phase 2 — Offer a frictionless return path (data still intact, win-back offer
  via F28 if policy permits)
**Success action:** Reactivation offer sent; tag `win-back`

## Notes on SaaS-specific tone

- Drive to the NEXT in-product action, not feature dumps — activation over
  education.
- Use behavior/usage signals as triggers, not just elapsed time.
- Be a helpful product guide, not a salesperson, until a real expansion signal
  fires.
- Route enterprise/security/contract questions to a human; never invent
  pricing or SLA commitments.
- Match the brand voice from Business Brain (dev-tool terse vs
  consumer-friendly warm).
