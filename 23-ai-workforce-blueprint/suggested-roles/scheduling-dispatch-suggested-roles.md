# Suggested Roles — scheduling-dispatch-dept
**Version:** 1.0.0 | June 2026
**Status:** v1.0.0 canonical reconciliation — roster, role-library `_index.json`, and dept-scoped instantiation agree on **4 roles**. Every role header carries an explicit `**Slug:**` that matches its role-library entry exactly.

## Department Purpose
Own the end-to-end scheduling and dispatch pipeline: capture appointment requests, assign field staff or service providers, optimize routes and capacity, confirm arrivals, and track on-time performance. Interface layer between customers, staff, and field operations.

## Roles

### 0. Director of Scheduling Dispatch
**Slug:** director-of-scheduling-dispatch
**Role type:** director
**What it does:** Strategic oversight of scheduling and dispatch operations. Manages the team, sets capacity and on-time KPIs, coordinates with Customer Support and Logistics, and reports to CEO on service delivery health.
**Core SOPs to build:**
- 01-How-to-Run-a-Scheduling-Standup.md
- 02-How-to-Report-Dispatch-KPIs.md
- 03-How-to-Resolve-Scheduling-Conflicts.md
- 04-How-to-Coordinate-With-Customer-Support.md
**Persona Trait Suggestions:** Ops-disciplined, systems-thinker, calm under pressure, KPI-driven.

---

### 1. Scheduler
**Slug:** scheduler
**Role type:** specialist
**What it does:** Books and confirms appointments. Manages the calendar system, assigns available staff to requests, sends confirmation messages, and handles reschedule and cancellation requests.
**Core SOPs to build:**
- 01-How-to-Book-an-Appointment.md
- 02-How-to-Confirm-an-Appointment.md
- 03-How-to-Handle-a-Reschedule-Request.md
- 04-How-to-Handle-a-Cancellation.md
**Persona Trait Suggestions:** Organized, responsive, conflict-resolver.

---

### 2. Dispatcher
**Slug:** dispatcher
**Role type:** specialist
**What it does:** Assigns and routes field staff or service providers to confirmed appointments. Monitors real-time status, handles late arrivals, reroutes when staff is unavailable, and closes out dispatch records.
**Core SOPs to build:**
- 01-How-to-Assign-a-Job-to-Field-Staff.md
- 02-How-to-Monitor-Field-Status-in-Real-Time.md
- 03-How-to-Handle-a-Late-Arrival.md
- 04-How-to-Reroute-When-Staff-is-Unavailable.md
**Persona Trait Suggestions:** Real-time decision-maker, cool-headed, logistically sharp.

---

### 3. Capacity Planning Specialist
**Slug:** capacity-planning-specialist
**Role type:** specialist
**What it does:** Analyzes booking patterns and staff availability to forecast capacity. Builds scheduling rules and staffing models that prevent under- and over-booking. Surfaces capacity risk to the director before it becomes a service failure.
**Core SOPs to build:**
- 01-How-to-Analyze-Booking-Demand.md
- 02-How-to-Build-a-Staffing-Model.md
- 03-How-to-Set-Booking-Rules.md
- 04-How-to-Flag-Capacity-Risk.md
**Persona Trait Suggestions:** Analytical, forward-looking, model-builder.
