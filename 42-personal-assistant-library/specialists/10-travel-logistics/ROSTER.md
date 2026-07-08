# ROSTER -- Travel & Logistics Coordinator

**Role:** Travel & Logistics Coordinator
**Slug:** travel-logistics
**Type:** specialist
**Pod:** A -- Admin & Logistics

**When to use:** Summoned when {{OWNER_NAME}} mentions upcoming travel in any channel, when a calendar event flags an out-of-town commitment, or when a trip needs intake, itinerary building, booking, day-of monitoring, or post-trip debrief. Fires automatically on travel day (2 hours before first departure) for the day-of sweep. Also triggered by any travel disruption (delay, cancellation, missed connection).

---

## Role Assignments

| Role ID | Role Title | Primary SOP | Cross-Trained SOPs |
|---------|-----------|-------------|-------------------|
| TL-01 | Travel & Logistics Coordinator | PA-10-01 Trip Planning Intake | PA-10-02, PA-10-03, PA-10-04, PA-10-05 |

---

## SOP Catalog

| SOP ID | SOP Name | File | Word Count Target | Last Updated |
|--------|----------|------|------------------|-------------|
| PA-10-01 | Trip Planning Intake | `SOP/PA-10-01-trip-planning-intake.md` | 300-600 | -- |
| PA-10-02 | Itinerary Build | `SOP/PA-10-02-itinerary-build.md` | 300-600 | -- |
| PA-10-03 | Booking Checklist | `SOP/PA-10-03-booking-checklist.md` | 300-600 | -- |
| PA-10-04 | Day-Of Logistics | `SOP/PA-10-04-day-of-logistics.md` | 300-600 | -- |
| PA-10-05 | Travel Debrief & Expense Capture | `SOP/PA-10-05-travel-debrief-expense-capture.md` | 300-600 | -- |

---

## Cross-Functional Handoffs

| From Travel & Logistics | To Department | When |
|--------------------------|---------------|------|
| Trip dates and time blocks confirmed | Calendar & Scheduling Manager | After itinerary is approved; calendar blocks need to be created or adjusted |
| Meeting during travel requires agenda or prep | Meeting Assistant | When {{OWNER_NAME}} is traveling for a meeting and needs briefing materials |
| Expense reconciliation complete | Personal Finance Manager | After debrief closes; reconciled expenses need to be filed or tracked against budget |
| Travel requires document access (passport scan, visa) | Life Admin & Archivist | When travel documents need to be located or verified |
| Trip involves high-stakes meeting or negotiation | My Coach / Brainstorming Partner | When {{OWNER_NAME}} wants pre-trip preparation support beyond logistics |
| Travel disruption causes scheduling conflict | Calendar & Scheduling Manager | When a delay or cancellation impacts downstream calendar commitments |
| {{OWNER_NAME}} needs motivation or momentum for trip | Motivation & Momentum | When pre-trip anxiety or resistance surfaces during intake |

---

## Escalation Paths

| Situation | First Contact | If Unresolved (30 min) | Final |
|-----------|---------------|------------------------|-------|
| Technical blocker (booking site down, API failure) | Technical Support | Master Orchestrator | Human owner via Telegram |
| Budget concern (trip exceeds stated threshold) | {{OWNER_NAME}} (flag with cost-benefit brief) | -- | -- |
| Travel advisory or safety concern at destination | {{OWNER_NAME}} (surface advisory and alternatives) | -- | -- |
| Impossible timeline (earliest flight lands after meeting) | {{OWNER_NAME}} (flag with options: earlier departure, alternate airport, virtual) | -- | -- |
| Booking error (name mismatch, double-booking) | Vendor directly (airline, hotel) | {{OWNER_NAME}} (flag with resolution plan) | Master Orchestrator |
| Stranded overnight with no hotel availability | {{OWNER_NAME}} (alternatives: alternate city, airport hotel waitlist, ground transport) | -- | -- |
| Medical emergency during travel | Emergency services first, then {{OWNER_NAME}}'s emergency contact | -- | Human owner |
| Systemic issue (same problem across 3+ trips) | Master Orchestrator (pattern analysis and proposed permanent fix) | -- | Human owner |

---

## Versioning

- Role assignments reviewed quarterly
- SOPs reviewed after every completed trip cycle or when {{OWNER_NAME}} feedback indicates a gap
- Travel preference file updated after every trip debrief (PA-10-05)
- Loyalty program data refreshed monthly
- All updates logged to {{TASK_TOOL}} with tag `sop-update-travel-logistics`
- Token reference: {{TOKEN}}
