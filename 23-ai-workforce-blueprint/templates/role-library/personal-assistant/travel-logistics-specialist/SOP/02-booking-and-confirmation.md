# PA-38-02 — Booking, Confirmation, and Documentation

**Role:** Travel Logistics Specialist
**Department:** Personal Assistant (38)
**SOP class:** Core operating procedure (generic role standard — applies to every client of this role)
**Method:** DMAIC (Define, Measure, Analyze, Improve, Control)

> This is a GENERIC role procedure. It describes HOW this role operates,
> not any one client's private data. The owner referenced below is whoever
> this assistant serves; substitute the live owner profile from the workspace
> USER.md at run time. Tools named are the workspace defaults; use whatever
> calendar, task, document, and messaging tools the workspace is wired to.

---

## Define

Booking, Confirmation, and Documentation locks the approved itinerary into real reservations and assembles every confirmation, document, and requirement the owner needs to travel without friction.

**Purpose of this procedure**
- Convert an approved plan into confirmed, paid reservations.
- Assemble all confirmations and travel documents in one reliable place.
- Verify every entry requirement (identification, visas, health rules) well before departure.

**When to run**
- Once the owner approves the itinerary from PA-38-01, and again whenever a booking changes.

**Frequency**
- Per trip, plus on any change.

**Inputs**
- The approved itinerary.
- The owner's booking credentials, loyalty accounts, and payment method on file.
- Entry and document requirements for the destination.

**Outputs**
- Confirmed reservations for every leg, with confirmation numbers captured.
- A consolidated travel pack: confirmations, documents, and requirements, available offline.

**Hand-to (downstream)**
- The owner (the travel pack) and the In-Trip Support procedure (PA-38-03) which monitors the booked trip.

**Definition of done**
- Every leg is confirmed, every confirmation is captured in one place, and every entry requirement is verified met.

## Measure

Booking quality is measured by completeness and accuracy — a single missed confirmation or unmet entry requirement can strand the owner.

**Signals this procedure tracks**
- Reservations confirmed vs. assumed-but-unconfirmed.
- Entry requirements verified vs. discovered at the gate.
- Confirmations findable offline vs. trapped in an inbox.

**Key metrics**
- **Confirmation completeness** — legs with a captured confirmation number; target 100%.
- **Requirement-verified rate** — entry requirements verified before departure; target 100%.
- **Offline availability** — the travel pack reachable without connectivity; required.

**Where the measurement is recorded**
- The travel pack and confirmation status are recorded per trip; gaps are logged in MEMORY.md.

## Analyze

Booking failures cluster at the edges: the leg that was planned but never actually paid, and the entry requirement nobody checked. Analyze for completeness, not just for the obvious bookings.

**Decision rules**
- A leg is not 'booked' until there is a confirmation number captured in the travel pack.
- Verify entry requirements against the destination's current official rules, not memory or assumption.
- If a booking cannot be confirmed (sold out, payment issue), surface it immediately and re-plan rather than assuming it will resolve.

**Common failure modes and how to read them**
- **Assumed bookings:** Treating a held-but-unpaid reservation as confirmed. Capture a real confirmation number for every leg.
- **Stale requirements:** Relying on old entry rules. Verify against current official sources every trip.
- **Inbox-only confirmations:** Leaving confirmations buried in email. Consolidate into an offline-reachable pack.

## Improve

Booking improves by making the confirmation checklist complete and by keeping the travel-pack format reliable and offline-accessible.

**Step-by-step procedure**
1. Book each leg of the approved itinerary using the owner's accounts and payment method.
2. Capture a confirmation number for every booking — no leg counts as done without one.
3. Verify the destination's current entry requirements (identification, visas, health) and confirm the owner meets them.
4. Assemble the consolidated travel pack: all confirmations, required documents, and key timings.
5. Make the travel pack reachable offline so connectivity is never a single point of failure.
6. Re-check the full pack for any leg that is missing a confirmation or any requirement unverified.
7. Deliver the travel pack to the owner and hand monitoring to the In-Trip Support procedure.

**Escalation path**
- If an entry requirement cannot be met in time (e.g., a visa that will not process before departure), escalate to the owner immediately — this can force a trip change and must never be discovered at the border.

**Optimization loop**
- Maintain a per-destination requirements checklist refreshed from official sources.
- Standardize the travel-pack format so nothing is ever omitted.

## Control

Control keeps this procedure stable and trustworthy over time. The guardrails below are non-negotiable; the review cadence catches drift; and the audit trail makes every run verifiable after the fact.

**Guardrails (never violate)**
- Never mark a leg booked without a captured confirmation number.
- Never rely on remembered entry rules; verify current official requirements.
- Never leave the travel pack reachable only online.

**Review cadence**
- After each trip: review any confirmation gap or requirement surprise; tighten the checklist.

**Failure mode to actively prevent**
- Assuming a held reservation is confirmed — the owner arrives to find there was never a real booking.

**Audit trail**
- Each trip's confirmation numbers and requirement checks are recorded.
- Any gap is logged with a checklist fix.

## Worked walkthrough

A generic, end-to-end run of this procedure, shown so the assistant can see the method in motion. The names, numbers, and details below are illustrative of the shape of the work, not any one owner's private information.

- **Run step 1.** Book each leg of the approved itinerary using the owner's accounts and payment method. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 2.** Capture a confirmation number for every booking — no leg counts as done without one. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 3.** Verify the destination's current entry requirements (identification, visas, health) and confirm the owner meets them. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 4.** Assemble the consolidated travel pack: all confirmations, required documents, and key timings. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 5.** Make the travel pack reachable offline so connectivity is never a single point of failure. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 6.** Re-check the full pack for any leg that is missing a confirmation or any requirement unverified. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 7.** Deliver the travel pack to the owner and hand monitoring to the In-Trip Support procedure. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.

By the end of the walkthrough the definition of done is satisfied: every leg is confirmed, every confirmation is captured in one place, and every entry requirement is verified met. If any step could not be completed, the assistant follows the escalation path above rather than guessing or skipping — an honest gap surfaced early is always cheaper than a silent failure discovered late.

## Operating checklist

**Before the run**
- All required inputs are on hand: The approved itinerary; The owner's booking credentials, loyalty accounts, and payment method on file; Entry and document requirements for the destination.
- The trigger condition is genuinely met (see *When to run*), not merely assumed.
- The owner's current preferences and goals are loaded from the workspace USER.md.

**During the run**
- Each step is completed in order; nothing is skipped to save time under pressure.
- Every decision follows the decision rules above; exceptions are logged with the reason.
- Anything that cannot be done is escalated immediately, not deferred silently.

**After the run**
- All outputs exist and are where the downstream procedure expects them: Confirmed reservations for every leg, with confirmation numbers captured; A consolidated travel pack: confirmations, documents, and requirements, available offline.
- The metrics for this run are recorded (Confirmation completeness, Requirement-verified rate, Offline availability).
- The hand-off is made: The owner (the travel pack) and the In-Trip Support procedure (PA-38-03) which monitors the booked trip.
- Any lesson learned is written to the role MEMORY.md so the next run inherits it.

---

*End of PA-38-02. This procedure is owned by the Travel Logistics Specialist. Update it whenever the underlying workflow, tools, or owner preferences change, and log the change in the role MEMORY.md so the next run inherits the improvement.*
