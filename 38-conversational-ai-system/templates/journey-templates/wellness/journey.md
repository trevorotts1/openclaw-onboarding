# Customer Journey Template — Wellness

This template defines the workflows a complete wellness practice (health
practitioner, fitness, mental health, spa, clinic) should have, from first
inquiry through appointment, adherence, and retention. Wellness is
appointment-driven, adherence-sensitive, and trust-heavy. (Source bullet: add
Appointment Confirmations, Post-Session Check-ins, Treatment Plan Adherence,
Insurance/Payment workflows.)

> **Compliance note:** wellness often touches PHI/health data. Keep the
> PII-scrubbing protocol ON, never give medical/diagnostic advice the
> practitioner must own, and escalate clinical questions to a human.

## Pre-purchase workflows

### 1. New Inquiry → Intake & Booking
**Trigger:** Prospect asks about services, availability, pricing, or "can you
help with <concern>"
**Purpose:** Answer the access question and book the first appointment/consult
**Conversation phases:**
- Phase 1 — Answer from the services Knowledge Source (offerings, hours, location,
  telehealth?)
- Phase 2 — Qualify gently (goal/concern, new vs returning, insurance if relevant)
  — no diagnosis
- Phase 3 — Offer the first appointment / free consult slot
**Success action:** Appointment booked + intake form sent; tag
`new-client-booked`

### 2. Consult Follow-Up
**Trigger:** Consult/first session ended without committing to a plan/package
**Purpose:** Convert a hesitant prospect with care, not pressure
**Conversation phases:**
- Phase 1 — Warm check-in; answer lingering questions
- Phase 2 — Restate the recommended path; surface package/membership options
**Success action:** Plan/package decision or follow-up scheduled; tag
`consult-followup`

## Purchase moment workflows

### 3. Payment / Insurance & Package Confirmation
**Trigger:** Client commits to a package, membership, or treatment plan
**Purpose:** Confirm payment/insurance details and set expectations
**Conversation phases:**
- Phase 1 — Confirm package/plan + payment method
- Phase 2 — Handle insurance/superbill basics per policy; route specifics to
  front desk/billing
**Success action:** Package confirmed + billing handled per policy; tag
`plan-active`

## Onboarding workflows

### 4. Welcome & First-Session Prep
**Trigger:** First appointment booked
**Purpose:** Reduce first-visit anxiety and maximize the first session
**Conversation phases:**
- Phase 1 — Welcome; what to bring, what to expect, arrival/telehealth logistics
- Phase 2 — Pre-session intake or questionnaire (kept PHI-safe)
**Success action:** Prep delivered + intake complete; tag `first-session-prep`

## Engagement workflows

### 5. Appointment Confirmations & Reminders
**Trigger:** Any appointment is scheduled
**Purpose:** Cut no-shows (the core revenue leak in wellness)
**Conversation phases:**
- Phase 1 — Confirm date/time/location
- Phase 2 — Reminder 24h and 2h before; offer easy reschedule to recover the slot
**Success action:** Appointment confirmed or rescheduled (not lost); tag
`appt-confirmed`

### 6. Post-Session Check-in
**Trigger:** A session/treatment is completed
**Purpose:** Reinforce care, catch problems, and build the relationship
**Conversation phases:**
- Phase 1 — "How are you feeling after your session?" — gentle, caring tone
- Phase 2 — Surface any concern; route clinical issues to the practitioner
**Success action:** Check-in logged; concerns escalated to a human; tag
`post-session-checkin`

### 7. Treatment-Plan / Program Adherence
**Trigger:** Client is between sessions and an at-home step or next appointment
window is due
**Purpose:** Keep clients on plan — adherence drives both outcomes and retention
**Conversation phases:**
- Phase 1 — Supportive nudge toward the next step (exercise, habit, next visit)
- Phase 2 — Remove friction (rebook, answer a logistics question)
**Success action:** Next session booked / step acknowledged; on disengagement,
flag to practitioner; tag `adherence-nudge`

## Retention workflows

### 8. Membership / Renewal & Re-book
**Trigger:** Package nearing end, membership renewal date, or last visit + typical
re-visit window passed
**Purpose:** Sustain the care relationship and recurring revenue
**Conversation phases:**
- Phase 1 — Recap progress; recommend continuing care / renewal
- Phase 2 — Offer loyalty/membership terms (via F28 if a discount, per policy)
**Success action:** Renewal/re-book conversation; tag `renewal-offer`

## Win-back workflows

### 9. Lapsed-Client Outreach
**Trigger:** No visit in 60-90 days
**Purpose:** Re-engage dormant clients before the relationship goes cold
**Conversation phases:**
- Phase 1 — Caring, no-pressure "we've been thinking of you — how are you doing?"
- Phase 2 — Offer an easy path back (re-eval visit, seasonal program)
**Success action:** Re-engagement offer / re-book; tag `win-back`

## Notes on Wellness-specific tone

- Warm, caring, non-clinical in tone — never cold or transactional.
- Never diagnose, prescribe, or give medical advice; escalate clinical questions
  to the practitioner.
- Protect health data: PII-scrubbing protocol stays ON; route insurance/billing
  specifics to the right human.
- Reminders are essential — no-shows are the main leak; make rescheduling
  effortless.
- Match the practitioner's voice from Business Brain (calm-clinical vs
  energetic-motivational).
