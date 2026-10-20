# Launch A — Reminder: 3 Days Before

- **id:** `launch-a-reminder-3d`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase C — Show-up reminders, extended to 3 days)
- **Timing:** `webinar_datetime` minus 3 days
- **Channels:** Email

## What it is
The intention-setting reminder. Three days out is when a registrant decides whether they will actually attend. This message sells the after-state and asks for one small preparation step, nothing more.

## TRIGGER
Wait until `webinar_datetime` − 3 days. Send only if not purchased and the datetime is still in the future.

**Late registrant rule:** registered under 3 days out — skip this file. The 24h reminder carries it.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | T−3d | Email — outcome first, date/time in zone, one prep step, loop reopened, calendar CTA |
| Guard | continuous | Purchased → exit · missing/past datetime → build error · reschedule → recompute |

## COPY RULES
- Lead with what they walk away with.
- One prep step, not a checklist.
- No price, no countdown, no offer language.
- Must add something the confirmation did not say.

## FLEXIBILITY
Operator copy wins. Short runways simply skip this node.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 03 Reminder 3 Days`
`Tag Added webinar-registered → Wait until webinar_datetime − 3d → If not purchased and future → Send Email → End`

## SCOPE
**In:** registered, not purchased, three days out.
**Out:** 24h and same-day reminders, indoctrination, replay.
