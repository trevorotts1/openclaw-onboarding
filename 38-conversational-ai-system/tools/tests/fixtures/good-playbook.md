# Conversation Workflow: Appointment Booking

**Created:** 2026-07-05
**Trigger:** Inbound lead asks to book or schedule
**Goal:** Book a qualified lead onto the discovery calendar
**Customer profile:** New inbound lead
**Desired customer outcome:** A confirmed appointment at a time that suits them

persona: house-standard
model-tier: realtime-standard

declares
tools-used: book_appointment, check_availability, update_tags, update_contact
exits-used: already-booked, talk-to-human
fields-used: contact.email, ZHC_budget_range
calendars: default: CAL_ID_A, on-site estimate: CAL_ID_B
pipeline: sales-pipeline
stage-map: qualified: STAGE_QUALIFIED, booked: STAGE_BOOKED

## When to invoke this workflow

The agent triggers this workflow when:
- The customer asks to book, schedule, or set up a call
- The inbound matches booking intent

## What the agent does

### Phase 1 - Acknowledge and qualify
tools: update_tags, update_contact, reference_documents
skip-if-field-filled: contact.email
max-attempts: 2
gate-if-not-met: budget qualified, closing: Thank you, it sounds like we are not the right fit right now.
Greet warmly, confirm the interest, and qualify the lead against the offer.

### Phase 2 - Gather context
tools: update_contact, reference_documents
Collect the information needed to recommend a time.

### Phase 3 - Deliver value
tools: check_availability, reference_documents
Present available times and answer questions.

### Phase 4 - Close
tools: book_appointment, check_availability, update_tags, update_contact, reference_documents
Confirm the booking and set expectations for the appointment.

## Information the agent needs

The agent should consult:
- The booking calendar configuration
- The business FAQ knowledge base

Exit rules
exit-when-tag: already-booked, action: end, closing: none
exit-when-tag: talk-to-human, action: handoff

## Edge cases

### If customer becomes frustrated
Escalate via sentiment monitoring protocol.

## On success

Apply the win tag, confirm the appointment, and schedule a reminder.

## On escalation

Escalate to the operator with the full booking context.

## Tone

Warm, concise, and helpful.
