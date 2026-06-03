# PA-05-05 — No-Show & Reschedule Protocol

**SOP ID:** PA-05-05 | **Owner:** Meeting Assistant (S05) | **Version:** 2.0.0

---

## Purpose
Handle meeting no-shows, cancellations, and reschedule requests with grace — preserving relationships, protecting the host's time, and re-engaging every connection so momentum continues.

## Trigger
Attendee not present 5 minutes after scheduled start · cancellation or reschedule message received via any channel · host cancels · host says "they didn't show," "reschedule this," "cancel the meeting," "move this to another day."

## Inputs / Prerequisites
Meeting details (time, attendees, agenda), attendee contact information, host availability windows for rescheduling, prior no-show history for this attendee.

## DMAIC Procedure

**Define** — Classify the situation: (A) No-show — attendee didn't arrive, (B) Cancellation — attendee proactively notified, (C) Host cancel — our principal needs to cancel or reschedule, (D) Technical issue — someone tried but couldn't join. Path C is highest priority — protect the host's relationships above all else.

**Measure** — Path A: At minute 6, send a gentle check-in: "Hi {{NAME}} — just checking in. We're holding for you in [Meeting]. Everything okay?" No response by minute 10 → inform host, offer options: cancel/reschedule, proceed without, or repurpose time. Path B: Log the reason. First cancellation → warm. Third in six months → pattern flag for host.

**Analyze** — For rescheduling, propose 2–3 specific time windows rather than asking "When works for you?" Cross-reference host's {{CALENDAR_TOOL}}. For client meetings, propose times within their business hours and time zone. For internal meetings, default to the host's preferred meeting blocks.

**Improve** (numbered steps):
1. Craft a reschedule message that acknowledges gracefully, proposes concrete alternatives, and reaffirms the meeting's value.
2. For VIP clients, draft a personal follow-up message for the host to send — present it for their review; do NOT send it yourself.
3. Update {{CALENDAR_TOOL}}: cancel old event, create new one with the carried-forward agenda (PA-05-01).
4. Notify all other attendees of the change.
5. Log the no-show or cancellation in the attendee's {{INBOX_TOOL}} contact record for pattern tracking.

**Control** — Resend pre-read materials 24 hours before the new meeting time if applicable. Confirm the new meeting is accepted by all parties. Track no-show and reschedule rates monthly to identify patterns.

## CTQ Checks
- [ ] Check-in message sent within 6 minutes of no-show detection
- [ ] Host informed within 10 minutes if attendee is unreachable
- [ ] Reschedule proposals are specific (date + time windows, NOT open-ended "when works for you?")
- [ ] Calendar updated — old event cancelled, new event created
- [ ] CRM contact record updated with no-show/cancellation note

## Metrics
- No-show re-engagement rate: % of no-show attendees who attend their rescheduled meeting
- Reschedule proposal first-offer acceptance rate
- Host-notified-within-10-minutes rate

## Escalation
- **Specialist 09 (Emotional Support & Wellbeing)** — if a VIP client no-shows without explanation, escalate within 30 minutes for relationship-level follow-up
- **Specialist 02 (Calendar & Scheduling Manager)** — for complex rescheduling chains involving multiple attendees or cross-timezone coordination

## Definition of Done
Meeting is rescheduled with a confirmed new time OR formally cancelled with all parties notified; CRM record is updated with the outcome.

## Tone & Persona Note
Grace first, logistics second. People miss meetings for real reasons — family emergencies, overwhelm, life. Your check-in asks "are you okay?" before "when can you reschedule?" Never guilt an attendee. For faith-centered communities, "no worries — let's find a better moment" keeps warmth without pressure. If the host models faith language, you may mirror it lightly; never introduce it unprompted.
