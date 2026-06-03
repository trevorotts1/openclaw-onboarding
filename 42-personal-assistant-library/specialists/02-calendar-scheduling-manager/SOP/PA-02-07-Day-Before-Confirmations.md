# PA-02-07 — Day-Before Confirmations

| Field | Value |
|---|---|
| **SOP ID** | PA-02-07 |
| **Title** | Day-Before Confirmations |
| **Version** | 1.0 |
| **Department** | Calendar & Scheduling (Specialist 2) |

---

## Purpose

To proactively confirm every meeting on {{OWNER_NAME}}'s calendar the day before it happens — reducing no-shows, catching last-minute conflicts, ensuring attendees are prepared, and giving {{OWNER_NAME}} the peace of mind that tomorrow is fully dialed in.

---

## Trigger

End of each business day (or early morning for same-day confirmations on meetings booked after the end-of-day window). The confirmation task should already exist in {{TASK_TOOL}} (created at booking time via PA-02-01).

---

## Inputs

- Tomorrow's calendar from {{CALENDAR_TOOL}}
- Each meeting's attendee list, time, location/link, and agenda
- Any prep materials that attendees should review beforehand
- Prior communication thread with the attendees (for tone continuity)

---

## Define

The problem: Meetings get scheduled, then forgotten. Attendees show up late, unprepared, or not at all. {{OWNER_NAME}} arrives to find the other party thought it was a different time, or that the video link doesn't work, or that key prep wasn't done. These failures are completely preventable with a simple day-before confirmation touchpoint — but without a systematic process, confirmations happen inconsistently or not at all.

---

## Measure

Current state indicators: How many meetings per month start late due to attendee confusion? How many no-shows or last-minute "wait, is this still on?" messages? How much pre-meeting anxiety does {{OWNER_NAME}} carry about whether tomorrow's meetings are solid? Track no-show rate before and after implementing confirmations.

---

## Analyze

Root causes of unconfirmed meetings: confirmation is treated as optional rather than standard operating procedure, timing is inconsistent (sometimes 3 days out, sometimes 10 minutes before), confirmation messages are purely transactional and easy to ignore, and missing confirmations aren't flagged as a quality failure.

---

## Improve

1. **Pull tomorrow's calendar.** At end of business day, open {{CALENDAR_TOOL}} and pull every meeting for the next business day. If it's Friday, pull Monday's meetings too.

2. **Verify each meeting is still valid.** Quick checks: Has anyone canceled or rescheduled without updating the event? Is the meeting link still active? Are all required attendees still listed? Has any new context emerged that changes the meeting's purpose?

3. **Send a warm, brief confirmation to all external attendees.** Keep it personal, not robotic. "Hi [Name] — just confirming our call tomorrow at 2 PM Eastern. {{OWNER_NAME}} is looking forward to it. The video link and agenda are below. Let me know if anything's changed on your end!"

4. **For internal attendees (team, staff), confirm with added value.** Don't just ping "still on?" — attach the agenda, any prep materials, and a brief note on what's expected. "Quick confirm for tomorrow's 10 AM sync. Agenda attached — please review the Q2 numbers beforehand. See you there."

5. **For {{OWNER_NAME}}: deliver the daily briefing.** A single message with tomorrow's lineup in chronological order: time, meeting name, who's attending, one-line purpose, and whether the prep brief is ready. "Tomorrow: 9 AM — Client call with Acme (prep brief ready), 11 AM — Team standup (agenda attached), 2 PM — Investor update (brief ready, slides pending — I'll flag when they're in)."

6. **Flag anything incomplete.** If a prep brief is missing, agenda isn't finalized, or attendees haven't confirmed, flag it: "Note: the 2 PM investor call still needs slides from the finance team — I've pinged them and will update you by 10 AM tomorrow."

7. **Handle non-responses.** If an external attendee doesn't confirm by morning of, send a gentle follow-up: "Just wanted to make sure you saw the confirmation for our 2 PM call today — still on? Happy to reschedule if something came up."

---

## Control

- After sending confirmations, mark each meeting as "confirmed" in {{TASK_TOOL}} or add a note to the calendar event.
- Morning of: verify all external attendees have responded. For any who haven't, send the follow-up (Step 7).
- Track no-show rate weekly. If a particular attendee or meeting type has a pattern, address it.

---

## CTQ (Critical to Quality) — Binary Checks

- [ ] All meetings for the next business day confirmed by end of current day
- [ ] Confirmation messages are warm and personalized, not generic templates
- [ ] {{OWNER_NAME}} received the daily briefing with full tomorrow lineup
- [ ] Any missing prep or unconfirmed attendees flagged in the briefing
- [ ] Morning-of follow-up sent for any outstanding non-responses

---

## Metrics

| Metric | Target |
|---|---|
| Meetings confirmed day-before | 100% of external meetings |
| No-show rate (external attendees) | ≤ 5% |
| {{OWNER_NAME}} reports "felt prepared for the day" | ≥ 9/10 |

---

## Escalation

Escalate to {{OWNER_NAME}} when: a key attendee hasn't confirmed and the meeting is high-stakes, a meeting link is broken and can't be resolved before the meeting, or confirmation outreach reveals that an attendee has a different understanding of the meeting's purpose or time.

**Partner escalation:**
- **Specialist 05 (Meeting Assistant)** — if a broken meeting link, missing agenda, or attendee confusion requires the Meeting Assistant to intervene before start time
- **Specialist 03 (Daily Briefing & Debrief)** — to integrate the day-before confirmation summary into the next morning's briefing

---

## Definition of Done

Day-before confirmations are complete when: every meeting for the next business day has been verified (still valid, link works, attendees listed), external attendees have received a warm confirmation, {{OWNER_NAME}} has received the daily briefing, and any missing items are flagged with an ETA for resolution.

---

## Tone Note

A day-before confirmation isn't just logistics — it's a relationship touchpoint. It says "we value this conversation enough to make sure it happens smoothly." The tone should feel like a trusted colleague making sure everything is set, not like an automated calendar reminder. Warmth, clarity, and the quiet confidence that comes from having everything under control.
