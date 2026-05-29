# Customer Journey Template — Consulting

This template defines the workflows a complete consulting / advisory business
should have to support clients from first inquiry through retainer renewal and
referral. Consulting sells expertise and outcomes, not products — the journey
is scoping-heavy up front and relationship-heavy after.

## Pre-purchase workflows

### 1. Inbound Inquiry → Fit Call
**Trigger:** Prospect submits a contact form, replies to outreach, or asks
"can you help with <problem>"
**Purpose:** Qualify the engagement (problem, scope, decision-maker, budget
band) and book a fit/discovery call — do NOT quote yet
**Conversation phases:**
- Phase 1 — Acknowledge the problem in their words; ask what prompted reaching
  out now
- Phase 2 — Qualify: who owns the outcome, what does success look like in 90
  days, is there budget authority on the call
- Phase 3 — Offer the fit call; hold a slot
**Success action:** Booked fit call + tag `fit-call-scheduled`; brief the
consultant with the qualification notes

### 2. Scoping / Proposal Follow-Up
**Trigger:** Fit call ended; proposal or SOW sent, no signature within 3 days
**Purpose:** Keep a high-consideration deal warm without discounting expertise
**Conversation phases:**
- Phase 1 — Confirm the proposal landed and was readable
- Phase 2 — Surface the real objection (scope, timing, internal buy-in, price)
- Phase 3 — Offer to adjust scope (phase the engagement) rather than cut rate
**Success action:** Re-engaged decision → route to consultant for a scope call;
tag `proposal-followup-sent`

## Purchase moment workflows

### 3. Engagement Letter / SOW Signed
**Trigger:** Contract or SOW e-signed
**Purpose:** Convert "signed" into momentum within 24 hours
**Conversation phases:**
- Phase 1 — Confirm receipt + countersignature
- Phase 2 — Set the kickoff: dates, attendees, the pre-kickoff intake the
  client must complete
**Success action:** Kickoff booked + intake form sent; tag `engagement-active`

## Onboarding workflows

### 4. Kickoff & Data/Access Intake
**Trigger:** Engagement letter signed
**Purpose:** Gather the inputs the engagement needs (access, docs, stakeholders)
so the first deliverable isn't blocked
**Conversation phases:**
- Phase 1 — Send the intake checklist (systems access, documents, named
  stakeholders, current-state metrics)
- Phase 2 — Chase any missing item before kickoff; flag blockers to the
  consultant
**Success action:** Intake complete + kickoff held; tag `kickoff-complete`

## Engagement workflows

### 5. Deliverable Review Cycle
**Trigger:** A deliverable, milestone, or sprint review is scheduled or sent
**Purpose:** Tighten the feedback loop so revisions don't stall the engagement
**Conversation phases:**
- Phase 1 — Confirm the deliverable was reviewed; collect structured feedback
- Phase 2 — Log change requests; set the revision turnaround expectation
- Phase 3 — Schedule the next review
**Success action:** Feedback captured + next review booked; if scope is
expanding, flag a change-order opportunity to the consultant

### 6. Mid-Engagement Health Check
**Trigger:** Halfway through the engagement OR 30 days in
**Purpose:** Surface misalignment early; reinforce wins already delivered
**Conversation phases:**
- Phase 1 — Ask the sponsor: are we solving the right problem, is pace right
- Phase 2 — Reflect progress against the 90-day success definition from #1
**Success action:** Sentiment logged; on any red flag, escalate to consultant
within the day (use sentiment monitoring protocol)

## Retention workflows

### 7. Retainer Renewal / Next Phase
**Trigger:** 30 days before engagement end OR retainer renewal date
**Purpose:** Turn a finished project into an ongoing or follow-on engagement
**Conversation phases:**
- Phase 1 — Recap outcomes delivered vs the original success definition
- Phase 2 — Propose the next phase or a retainer to sustain/extend results
**Success action:** Renewal/next-phase conversation booked with the consultant;
tag `renewal-conversation`

## Win-back / referral workflows

### 8. Reference Calls & Referral Ask
**Trigger:** Engagement closed successfully (outcome confirmed)
**Purpose:** Convert a delivered outcome into a case study, a reference, and a
warm referral
**Conversation phases:**
- Phase 1 — Ask permission to capture the result as a case study/testimonial
- Phase 2 — Ask who else they know facing the same problem; offer a referral path
**Success action:** Testimonial captured (feeds knowledge base + sales) and/or
referral introduced; tag `reference-or-referral`

## Notes on Consulting-specific tone

- Lead with expertise and outcomes; never compete on price — phase the scope
  instead of discounting the rate.
- Speak to a decision-maker's risk: time, internal political cost, opportunity
  cost — not just dollars.
- Confidentiality matters; never reference one client's specifics to another.
- Match the consultant's voice from Business Brain (some are blunt diagnosticians,
  some are collaborative facilitators).
