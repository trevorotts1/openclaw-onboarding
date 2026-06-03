# PA-18-04 — Aging-Parents Care Coordination

| Field | Value |
|---|---|
| **SOP ID** | PA-18-04 |
| **Title** | Aging-Parents Care Coordination |
| **Version** | 1.0 |
| **Department** | Family & Life-Stage Concierge (Specialist 18) |

---

## Purpose

Manage the complex care of aging parents with structure and compassion — so {{OWNER_NAME}} can show up as a daughter or son, not just a care coordinator.

---

## Trigger

A new medical event, appointment, or care concern arises; a scheduled check-in fires in {{TASK_TOOL}}; a sibling or caregiver reaches out; or {{OWNER_NAME}} expresses worry about a parent's well-being.

---

## Inputs

- Parent medical information (conditions, medications, providers, insurance)
- Appointment calendar and follow-up notes
- Legal documents status (power of attorney, advance directive, will)
- Sibling and caregiver contact list with roles
- {{OWNER_NAME}}'s own capacity and boundaries (from IDENTITY.md)

---

## Define

Caring for aging parents is a second full-time job without a manual. Medical info scatters across portals, siblings operate from different assumptions, legal documents sit half-done. Without structure, the role becomes unsustainable.

---

## Measure

How many care tasks live in {{OWNER_NAME}}'s head vs. a system? Track: missed appointments, medication refill gaps, overdue legal documents, {{OWNER_NAME}}'s caregiving stress level (1-10).

---

## Analyze

Breakdown patterns: scattered information across providers and portals, reactive crisis-mode responses, sibling communication gaps, and caregiver burnout from carrying the mental load without respite.

---

## Improve

Build this care infrastructure:

1. **Central parent health record.** Create a single living document (or folder) for each parent: current medications with dosages, provider list with contact info, insurance details, known allergies, recent test results, and a chronological appointment log. Update it within 24 hours of every medical interaction. This document becomes the single source of truth.

2. **Appointment management system.** Every parent medical appointment goes into {{CALENDAR_TOOL}} with preparation notes (questions to ask, forms to bring, prior test results needed). After each appointment, capture a brief summary: what was discussed, what changed, what's the follow-up. This prevents the "what did the doctor say again?" spiral.

3. **Medication tracking.** Maintain a current medication list with refill dates. Set reminders in {{TASK_TOOL}} one week before every refill runs out. Coordinate with the pharmacy for auto-refill where available. Never let a parent run out of a critical medication because the refill slipped.

4. **Sibling communication rhythm.** Establish a regular cadence — a monthly update email, a shared digital log, or a standing group call. Everyone sees the same information at the same time. No one operates from assumptions. Clearly document who owns which domain (medical appointments, finances, home maintenance, social visits).

5. **Legal-document checklist.** Track the status of each parent's essential documents: power of attorney (healthcare and financial), advance directive/living will, last will and testament, and HIPAA release forms. Flag anything incomplete to {{OWNER_NAME}} monthly until resolved.

---

## Control

- After every appointment: update the health record within 24 hours
- Weekly: review upcoming appointments, medication refill status, and any open action items
- Monthly: sibling update sent and legal-document checklist reviewed
- Continuously: monitor {{OWNER_NAME}}'s caregiving load — if they're consistently above a 7 on the stress scale, flag it

---

## CTQ (Critical to Quality) — Binary Checks

- [ ] Parent health records are current (updated within 24 hours of last appointment)
- [ ] All medications have refill reminders set before they run out
- [ ] No medical appointments were missed this month
- [ ] Sibling communication went out on schedule
- [ ] Legal-document gaps are flagged to {{OWNER_NAME}} monthly

---

## Metrics

| Metric | Target |
|---|---|
| Missed appointments | 0 |
| Medication refill gaps | 0 |
| Days since last health-record update | ≤ 7 |
| {{OWNER_NAME}} caregiving stress score | ≤ 6/10 |

---

## Escalation — Named Partners

Escalate to {{OWNER_NAME}} immediately when: a parent experiences a health emergency, a new diagnosis requires major decisions, medication has run out with no refill pathway, a legal-document gap could become urgent (e.g., parent declining without a power of attorney in place), or the sibling communication system breaks down. In non-urgent situations, present a weekly summary with clear action items. If financial or estate-planning gaps surface (power of attorney, will, long-term care funding), partner with **Specialist 11 (Personal Finance)**. If caregiver stress chronically exceeds 7/10, coordinate with **Specialist 09 (Emotional Support & Wellbeing)** and **Specialist 26 (Therapeutic Support)** for caregiver-specific mental-health resources. If medical appointment logistics overwhelm the calendar, partner with **Specialist 02 (Calendar & Scheduling Manager)** for ride-coordination and family-coverage scheduling.

---

## Definition of Done

This SOP is working when {{OWNER_NAME}} can walk into a doctor's appointment with their parent carrying a complete health record, when siblings are aligned and informed, when no medication runs out unexpectedly, and — most importantly — when {{OWNER_NAME}} can be present as a child, not just a case manager.

---

## Tone Note

This is the hardest work most of us will ever do. The system exists to hold the logistics so {{OWNER_NAME}} can hold their parent's hand. It doesn't fix the grief, and it doesn't make the hard conversations easy. But it removes the chaos that compounds the pain. When a medication runs out or an appointment is missed, the system failed — not {{OWNER_NAME}}. Fix the system, not the person.
