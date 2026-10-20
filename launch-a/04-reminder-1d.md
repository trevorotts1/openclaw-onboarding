# Launch A — Reminder: 1 Day Before

- **id:** `launch-a-reminder-1d`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase C — 24h reminder)
- **Timing:** `webinar_datetime` minus 24 hours
- **Channels:** Email + SMS (SMS only with consent)

## What it is
The highest-leverage reminder in the stack. Tomorrow's show-up is decided in the last 24 hours. The email carries the reason; the SMS carries the tap. They are not the same message twice.

## TRIGGER
Wait until `webinar_datetime` − 24h. Send only if not purchased and the datetime is future.

**Late registrant rule:** registered inside 24h — send immediately with honest copy. "Tomorrow" becomes "in a few hours" inside the final 12 hours.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | T−24h | Email — tomorrow, time in zone, single most valuable thing, join link, live-only moment |
| 2 | T−24h | SMS (consent) — one line, name, time, join URL |
| Guard | continuous | Purchased → exit · past/missing datetime → build error · DND → email only · reschedule → honest-gap variant once |

## COPY RULES
- Time in the registrant's own zone.
- One promise in the confirmation's wording.
- Honest timing inside 12 hours.
- No price, no countdown.
- SMS is one line plus the link.

## FLEXIBILITY
Operator copy wins. If SMS consent does not exist, email still carries the full job.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 04 Reminder 24 Hours`
`Tag Added webinar-registered → Wait until webinar_datetime − 24h → If not purchased and future → Email → If SMS consent → SMS → End`

## SCOPE
**In:** registered, not purchased, 24 hours out.
**Out:** same-day reminders, indoctrination, replay.
