# Conversation Workflow: Runtime Tool-Gating Prover Fixture

**Created:** 2026-07-11
**Trigger:** Inbound lead in the qualify stage
**Goal:** Prove per-phase tool gating at RUNTIME (U-1)
**Customer profile:** New inbound lead, not yet qualified
**Desired customer outcome:** The right next step for their stage

persona: house-standard
model-tier: realtime-standard

declares
tools-used: check_availability, update_tags, update_contact, book_appointment
exits-used: talk-to-human
fields-used: contact.email
pipeline: sales-pipeline
stage-map: qualified: STAGE_QUALIFIED, booked: STAGE_BOOKED

## When to invoke this workflow

The agent triggers this workflow when a lead is still being qualified.

## What the agent does

### Phase 1 - Gather context and check availability
tools: check_availability, update_contact, update_tags, reference_documents
max-attempts: 3
Collect what the lead needs and, when asked, look up open times. Do NOT book
yet - booking is only granted in the Close phase after qualification.

### Phase 2 - Deliver value
tools: check_availability, reference_documents
Present available times and answer questions.

### Phase 3 - Close
tools: book_appointment, check_availability, update_tags, update_contact, reference_documents
Confirm the booking and set expectations.

## Information the agent needs

- The booking calendar configuration
- The business FAQ knowledge base

Exit rules
exit-when-tag: talk-to-human, action: handoff

## On success

Apply the win tag and schedule a reminder.

## On escalation

Escalate to the operator with the full context.

## Tone

Warm, concise, and helpful.
