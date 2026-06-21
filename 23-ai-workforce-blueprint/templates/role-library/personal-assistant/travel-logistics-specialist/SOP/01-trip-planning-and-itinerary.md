# PA-38-01 — Trip Planning and Itinerary Build

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

Trip Planning and Itinerary Build turns a travel need into a complete, confirmed, conflict-free itinerary. The specialist owns every moving part — flights, ground transport, lodging, and timing — so the owner simply shows up and travels.

**Purpose of this procedure**
- Produce a single authoritative itinerary covering door-to-door travel.
- Eliminate timing conflicts and impossible connections before the owner ever sees them.
- Match every booking to the owner's known travel preferences.

**When to run**
- Whenever a trip is requested or a travel need is identified, well ahead of the travel date.

**Frequency**
- Per trip; revisited if the trip's parameters change.

**Inputs**
- The trip's purpose, destination, and fixed commitments (meetings, events) at the destination.
- The owner's travel preferences (seating, lodging, timing, loyalty programs, dietary and access needs).
- Budget and any policy constraints.

**Outputs**
- A complete door-to-door itinerary: outbound travel, lodging, local transport, and return.
- All confirmations consolidated in one place the owner can reach offline.

**Hand-to (downstream)**
- The Booking and Confirmation procedure (PA-38-02) to lock in reservations, and the owner for approval of the plan.

**Definition of done**
- The owner has one itinerary that gets them from their door to every destination commitment and back, with no timing conflicts and every preference honored.

## Measure

Itinerary quality is measured by how few surprises the owner hits in transit — a good plan is invisible because everything simply works.

**Signals this procedure tracks**
- Tight or impossible connections caught before booking.
- Itinerary conflicts with the owner's destination commitments.
- Preferences honored vs. missed.

**Key metrics**
- **Conflict-free rate** — itineraries with no timing conflict or impossible connection; target 100%.
- **Preference-match rate** — bookings matching the owner's known preferences; target near 100%.
- **Buffer adequacy** — connections and transfers with realistic buffers built in; verify every leg.

**Where the measurement is recorded**
- Each trip's plan and any in-transit surprise is logged in the role MEMORY.md for the post-trip review.

## Analyze

Most travel pain comes from optimistic timing — connections that look fine on paper but ignore real-world delays, security lines, and ground transfer time. Analyze every leg against reality, not the schedule.

**Decision rules**
- Build a realistic buffer into every connection and transfer; never trust the minimum legal connection time.
- Anchor the itinerary to the fixed destination commitments and work backwards from them.
- When two options are close, choose the one that best matches the owner's stated preferences.

**Common failure modes and how to read them**
- **Optimistic connections:** Booking the minimum connection time. One delay cascades the whole trip. Always buffer.
- **Ignoring door-to-door:** Planning airport-to-airport and forgetting how the owner gets to and from. Plan the whole journey.
- **Preference amnesia:** Booking against the owner's known preferences. Maintain and apply a preference profile every time.

## Improve

Planning improves as the preference profile gets richer and as buffer rules get tuned by what actually went wrong on past trips.

**Step-by-step procedure**
1. Confirm the trip's purpose, destination, dates, and every fixed commitment at the destination.
2. Pull the owner's travel preference profile and any policy or budget constraints.
3. Anchor to the fixed destination commitments; work backwards to build outbound and return travel.
4. Select flights or transport with realistic buffers on every connection and transfer.
5. Add lodging and local ground transport so the journey is complete door-to-door.
6. Cross-check the whole itinerary for timing conflicts and impossible connections; fix before presenting.
7. Present the draft itinerary to the owner for approval, then hand to Booking and Confirmation.

**Escalation path**
- If no conflict-free itinerary fits the fixed commitments and budget, escalate to the owner early with the trade-offs (move a meeting, raise the budget, accept a tighter connection) — do not silently book an impossible plan.

**Optimization loop**
- Continuously enrich the owner's preference profile from every trip.
- Tune buffer rules per route based on real delay history.

## Control

Control keeps this procedure stable and trustworthy over time. The guardrails below are non-negotiable; the review cadence catches drift; and the audit trail makes every run verifiable after the fact.

**Guardrails (never violate)**
- Never book a minimum-legal connection without a deliberate buffer decision.
- Never plan only airport-to-airport; always cover door-to-door.
- Never book against the owner's known preferences without flagging why.

**Review cadence**
- After each trip: review what went wrong in transit and feed it into planning rules.

**Failure mode to actively prevent**
- Building an itinerary that looks fine on the schedule but collapses on the first real-world delay.

**Audit trail**
- Each itinerary and its in-transit issues are logged.
- Buffer and preference rules are updated from post-trip findings.

## Worked walkthrough

A generic, end-to-end run of this procedure, shown so the assistant can see the method in motion. The names, numbers, and details below are illustrative of the shape of the work, not any one owner's private information.

- **Run step 1.** Confirm the trip's purpose, destination, dates, and every fixed commitment at the destination. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 2.** Pull the owner's travel preference profile and any policy or budget constraints. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 3.** Anchor to the fixed destination commitments; work backwards to build outbound and return travel. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 4.** Select flights or transport with realistic buffers on every connection and transfer. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 5.** Add lodging and local ground transport so the journey is complete door-to-door. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 6.** Cross-check the whole itinerary for timing conflicts and impossible connections; fix before presenting. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 7.** Present the draft itinerary to the owner for approval, then hand to Booking and Confirmation. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.

By the end of the walkthrough the definition of done is satisfied: the owner has one itinerary that gets them from their door to every destination commitment and back, with no timing conflicts and every preference honored. If any step could not be completed, the assistant follows the escalation path above rather than guessing or skipping — an honest gap surfaced early is always cheaper than a silent failure discovered late.

## Operating checklist

**Before the run**
- All required inputs are on hand: The trip's purpose, destination, and fixed commitments (meetings, events) at the destination; The owner's travel preferences (seating, lodging, timing, loyalty programs, dietary and access needs); Budget and any policy constraints.
- The trigger condition is genuinely met (see *When to run*), not merely assumed.
- The owner's current preferences and goals are loaded from the workspace USER.md.

**During the run**
- Each step is completed in order; nothing is skipped to save time under pressure.
- Every decision follows the decision rules above; exceptions are logged with the reason.
- Anything that cannot be done is escalated immediately, not deferred silently.

**After the run**
- All outputs exist and are where the downstream procedure expects them: A complete door-to-door itinerary: outbound travel, lodging, local transport, and return; All confirmations consolidated in one place the owner can reach offline.
- The metrics for this run are recorded (Conflict-free rate, Preference-match rate, Buffer adequacy).
- The hand-off is made: The Booking and Confirmation procedure (PA-38-02) to lock in reservations, and the owner for approval of the plan.
- Any lesson learned is written to the role MEMORY.md so the next run inherits it.

---

*End of PA-38-01. This procedure is owned by the Travel Logistics Specialist. Update it whenever the underlying workflow, tools, or owner preferences change, and log the change in the role MEMORY.md so the next run inherits the improvement.*
