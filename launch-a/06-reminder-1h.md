# Launch A — Reminder: 1 Hour Before

- **id:** `launch-a-reminder-1h`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase C — 1h reminder)
- **Timing:** `webinar_datetime` minus 1 hour
- **Channels:** SMS (first) + Email (fallback)

## What it is
The last reliable interrupt before the event. SMS leads because it is the channel that actually reaches a phone an hour out. Email exists only so no-SMS registrants are not left out.

## TRIGGER
Wait until `webinar_datetime` − 1h. Send only if not purchased and future.

**Late registrant rule:** registered inside the final hour — send once immediately with honest "starting soon" copy.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | T−1h | If SMS consent → SMS: name, starts in 1 hour, time, join URL |
| 2 | T−1h | Else → Email: one line + single join button |
| Guard | continuous | Purchased → exit · past datetime → no send · DND → email only · no duplicate both-channel send |

## COPY RULES
- Email under 60 words; SMS one line.
- Time in the registrant's own zone.
- One CTA only: join.
- No price, no countdown.

## FLEXIBILITY
Operator may make the email primary; the SMS remains the higher-performing channel where consent exists.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 06 Reminder 1 Hour`
`Tag Added webinar-registered → Wait until webinar_datetime − 1h → If not purchased and future → If SMS consent → SMS → Else → Email → End`

## SCOPE
**In:** registered, not purchased, one hour out.
**Out:** 15-minute and live reminders, replay.
