# SOP Index -- Travel & Logistics Coordinator

**Department:** Travel & Logistics Coordinator (10-travel-logistics)
**Total SOPs:** 5
**Format:** DMAIC (Define, Measure, Analyze, Improve, Control)
**Last updated:** {{GENERATION_DATE}}

---

## SOP Quick Reference

| SOP ID | Name | Frequency | Trigger | Page |
|--------|------|-----------|---------|------|
| PA-10-01 | Trip Planning Intake | On-demand (every new trip) | {{OWNER_NAME}} mentions upcoming travel in any channel | [PA-10-01](PA-10-01-trip-planning-intake.md) |
| PA-10-02 | Itinerary Build | On-demand (after intake is confirmed) | {{OWNER_NAME}} approves the intake brief | [PA-10-02](PA-10-02-itinerary-build.md) |
| PA-10-03 | Booking Checklist | On-demand (after itinerary is approved) | {{OWNER_NAME}} says "book it" | [PA-10-03](PA-10-03-booking-checklist.md) |
| PA-10-04 | Day-Of Logistics | Every travel day (2 hours before first departure) + on-demand for disruptions | Travel day morning or any disruption event | [PA-10-04](PA-10-04-day-of-logistics.md) |
| PA-10-05 | Travel Debrief & Expense Capture | After every trip (24 hours post-return) | {{OWNER_NAME}} has returned home | [PA-10-05](PA-10-05-travel-debrief-expense-capture.md) |

---

## SOP Taxonomy

### Planning (Before the Trip)
- **PA-10-01 -- Trip Planning Intake:** The foundation. Structured conversation that captures purpose, constraints, preferences, logistics, and hidden needs. Nothing is booked at this stage.
- **PA-10-02 -- Itinerary Build:** Transform the intake into a door-to-door timeline with three options (A/B/C), time blocks, buffers, meal windows, downtime, and clear trade-offs.
- **PA-10-03 -- Booking Checklist:** Execute every reservation against a 9-point verification gate. Flights, hotel, ground transport, dining -- all booked in dependency order with confirmation numbers captured.

### Execution (During the Trip)
- **PA-10-04 -- Day-Of Logistics:** Real-time monitoring from 2 hours before first departure through arrival. Morning brief, active flight/weather/traffic tracking, 5-minute disruption playbook, and arrival confirmation.

### Closure (After the Trip)
- **PA-10-05 -- Travel Debrief & Expense Capture:** Five-question debrief, full expense reconciliation with receipt collection, preference-file updates, and trip file closure.

---

## SOP Dependency Map

```
PA-10-01 (Intake) ──────────── Foundation ─ feeds into PA-10-02
    │
    └── PA-10-02 (Itinerary Build) ← triggered by confirmed intake
            │
            └── PA-10-03 (Booking Checklist) ← triggered by approved itinerary
                    │
                    └── PA-10-04 (Day-Of Logistics) ← triggered by travel day
                            │
                            └── PA-10-05 (Debrief & Expenses) ← triggered by return
                                    │
                                    └── Updates preference file → improves PA-10-01 next time
```

Each SOP feeds the next. The output of PA-10-01 is the input to PA-10-02. The output of PA-10-02 is the input to PA-10-03. And the output of PA-10-05 -- the updated preference file -- feeds back into PA-10-01 and PA-10-02 for the next trip, creating a compounding improvement loop.

---

## Reading Order for New Travel & Logistics Coordinators

1. **PA-10-01 -- Trip Planning Intake** (the operating system -- read this first; everything starts here)
2. **PA-10-02 -- Itinerary Build** (how to turn intake into three clear options)
3. **PA-10-03 -- Booking Checklist** (the verification gate that prevents errors; read before you book anything)
4. **PA-10-04 -- Day-Of Logistics** (how to monitor and respond on travel day; the highest-stakes SOP)
5. **PA-10-05 -- Travel Debrief & Expense Capture** (how to close every trip and make the next one better)

---

## SOP Lifecycle

| Stage | SOPs Active | What Happens |
|-------|-------------|--------------|
| Pre-Trip (7+ days out) | PA-10-01 | Intake conversation, preference review, priority classification |
| Pre-Trip (3-7 days out) | PA-10-02 | Itinerary build, option presentation, {{OWNER_NAME}} selection |
| Pre-Trip (1-3 days out) | PA-10-03 | Booking execution, Trip Master Sheet creation, calendar coordination |
| Travel Day | PA-10-04 | Pre-departure sweep, active monitoring, disruption management, arrival confirmation |
| Post-Trip (24-72 hrs) | PA-10-05 | Debrief conversation, expense reconciliation, preference updates, trip file closure |

---

## Quality Gates Per Lifecycle Stage

| Stage | Gate |
|-------|------|
| After PA-10-01 | All 5 dimensions captured. Priority classified. Trip within 48 hours? Express mode flagged. |
| After PA-10-02 | Three options presented with trade-offs. Every timeline block has a reason. Door-to-door, not airport-to-airport. |
| After PA-10-03 | All 9 booking checklist items verified per reservation. Trip Master Sheet complete and delivered. |
| During PA-10-04 | Morning brief sent T-2 hours. Every disruption acknowledged within 5 minutes. Arrival confirmed. |
| After PA-10-05 | All 5 debrief questions answered. Every receipt collected. Preference file updated. Trip marked CLOSED. |
