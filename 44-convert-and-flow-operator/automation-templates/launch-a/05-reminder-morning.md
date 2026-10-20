# Launch A — Reminder: Morning of the Event

**Built as draft, nothing sends** until the operator approves each workflow in GoHighLevel; this file ships the build, not the go-live.


- **id:** `launch-a-reminder-morning`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase C — same-day reminder)
- **Timing:** morning of the event, default 09:00 local, clamped to at least 2 hours before start
- **Channels:** Email + SMS (SMS only with consent)

## What it is
The day-of morning touch. Registrants decide on the day; this message puts the time and link back in front of them while the hour can still be protected, and gives one reason to protect it.

## TRIGGER
Wait until `webinar_morning_send` — computed as 09:00 in the registrant's zone on the event day, clamped to `webinar_datetime` − 2h.

If the session starts before 11:00, the morning send moves to start − 2h. If that moment is already past, send immediately with honest copy.

**Late registrant rule:** registered after the morning send — skip; the 1-hour and 15-minute reminders carry it.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | morning of | Email — today, time in zone, one reason to protect the hour, join link |
| 2 | morning of | SMS (consent) — one line, name, time, join URL |
| Guard | continuous | Purchased → exit · past datetime → no send · early session → clamp · DND → email only |

## COPY RULES
- Time in the registrant's own zone.
- Email carries the reason; SMS carries the tap.
- No price, no countdown.
- Morning sessions must read as "in a few hours", never "today" as if the day is fresh.

## FLEXIBILITY
Operator sets their own send time. The only non-negotiable is the 2-hour floor before start.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 05 Reminder Morning Of`
`Tag Added webinar-registered → Wait until webinar_morning_send → If not purchased and future → Email → If SMS consent → SMS → End`

Compute `webinar_morning_send` from `webinar_datetime` + `webinar_timezone`; do not hard-code 09:00 for early sessions.

## SCOPE
**In:** registered, not purchased, morning of the event.
**Out:** 1-hour, 15-minute and live reminders, replay.
