# PA-02-01 — Meeting Booking

| Field | Value |
|---|---|
| **SOP ID** | PA-02-01 |
| **Title** | Meeting Booking |
| **Version** | 1.0 |
| **Department** | Calendar & Scheduling (Specialist 2) |

## Purpose
Book meetings accurately — every commitment has clear purpose, right people, and adequate buffer.

## Trigger & Inputs
A meeting request arrives from {{OWNER_NAME}}, a stakeholder, or {{INBOX_TOOL}}. Inputs: request details (who, what, why, timing), {{CALENDAR_TOOL}} for availability, {{OWNER_NAME}}'s scheduling preferences (PA-02-03), and prior context.

## Diagnose
**Problem:** Inconsistent booking causes double-bookings and agenda-less meetings. **Root causes:** booking before availability checks, skipping buffers, omitting timezone, no prep context, booking without clarified purpose. **Track:** meetings without agendas, back-and-forth count.

## Improve

1. **Receive and acknowledge.** When a request arrives, acknowledge within your response window. "Got it — let me find a time that works and I'll get right back to you."

2. **Clarify purpose before booking.** Confirm: who needs to be there, what's the desired outcome, how long is needed. If the requester hasn't provided this, ask warmly: "Just so I book the right length — what's the main thing you want to walk away with?"

3. **Check availability against ALL rules.** Open {{CALENDAR_TOOL}} and scan the proposed window. Apply buffer rules (PA-02-03), check for focus-block conflicts, verify no adjacent meetings create back-to-back overload, and confirm timezone if attendees are in different zones.

4. **Propose 2-3 specific time slots.** Don't ask "when works for you?" — offer concrete options. "{{OWNER_NAME}} has Tuesday at 11 AM, Wednesday at 2 PM, or Thursday at 10 AM Eastern. Which fits best?"

5. **Create the event with full details.** Once confirmed, create the event in {{CALENDAR_TOOL}} with: descriptive title, date/time/timezone, attendee list, location or video link, agenda or purpose statement, and any attached prep materials.

6. **Schedule your follow-ups.** Immediately create tasks in {{TASK_TOOL}}: prep brief deadline (24 hours before — PA-02-04), confirmation send (day before — PA-02-07), and any post-meeting follow-up if needed.

7. **Confirm to all parties.** Send a warm confirmation: "All set — Tuesday at 11 AM Eastern. I'll send a quick prep note the morning of. Looking forward to it."

## Control
Verify event in {{CALENDAR_TOOL}}. Confirm prep brief task in {{TASK_TOOL}}. Weekly spot-check 3 meetings.

## CTQ (Critical to Quality) — Binary Checks

- [ ] Meeting purpose and desired outcome are documented
- [ ] All attendees confirmed with correct timezone
- [ ] Buffer rules (PA-02-03) applied — no focus-block violation
- [ ] Event in {{CALENDAR_TOOL}} has title, time, attendees, location/link, and agenda
- [ ] Prep brief and confirmation tasks created in {{TASK_TOOL}}

## Metrics

| Metric | Target |
|---|---|
| Meetings booked without back-and-forth | ≥ 80% |
| Meetings with documented purpose/agenda | 100% |
| Scheduling requests acknowledged on time | ≥ 95% |

## Escalation

Escalate to {{OWNER_NAME}} when: the requester insists on a slot that violates working hours or focus blocks, the meeting involves people whose priority you can't assess, or the purpose can't be clarified and you suspect the meeting may not be necessary.

**Partner escalation:**
- **Specialist 03 (Daily Briefing & Debrief)** — if a booked meeting conflicts with the morning briefing's Top-3 priorities
- **Specialist 04 (Task & Priority Manager)** — if a meeting request contains an implicit task or deadline needing capture

## Definition of Done

A meeting is fully booked when: purpose is clarified, a time slot is confirmed by all parties, the event exists in {{CALENDAR_TOOL}} with complete details, buffer/focus rules are satisfied, and prep brief plus confirmation tasks are scheduled in {{TASK_TOOL}}.
