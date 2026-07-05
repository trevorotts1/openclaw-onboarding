# Conversation Workflow: Broken Fixture (deliberately invalid)

**Created:** 2026-07-05
**Trigger:** Test fixture that violates one defect per grammar family
**Goal:** Exercise every validation failure path in the engine

persona: house-standard
model-tier: hyperspeed-max

declares
tools-used: book_appointment, teleport_customer
exits-used: never-declared-exit
fields-used: ZHC_missing_field

## What the agent does

### Phase 1 - Acknowledge and qualify
tools: update_tags, warp_drive, reference_documents
max-attempts: zero
disable-global: escalate_to_human
Greet the customer.

### Phase 2 - Close
tools: book_appointment
Book the appointment.

Exit rules
exit-when-tag: switch-to-support, action: route
exit-when-tag: bad-tag, action: teleport

## On success

Book the appointment.

## On escalation

Escalate to the operator.
