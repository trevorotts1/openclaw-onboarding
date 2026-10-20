# Launch A — Reminder: 1 Week Before

**Built as draft, nothing sends** until the operator approves each workflow in GoHighLevel; this file ships the build, not the go-live.


- **id:** `launch-a-reminder-1wk`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase C — Show-up reminders, extended to 7 days)
- **Timing:** `webinar_datetime` minus 7 days
- **Channels:** Email

## What it is
The first pure attendance reminder. A week out, the registrant's attention has moved on; this message puts the event back on the calendar by repeating the promise in the same words as the confirmation and giving one concrete reason to be there live.

## TRIGGER
Wait until `webinar_datetime` − 7 days. Send only if not purchased and the datetime is still in the future.

**Late registrant rule:** if registration happened inside the 7-day window, do not send. Skip to the next reminder whose window is ahead. Never send a "one week" message to someone who registered yesterday.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | T−7d | Email — date/time in zone, same ONE promise, one live-only reason, curiosity loop, calendar CTA |
| Guard | continuous | Purchased → exit · missing/past datetime → build error, do not send · reschedule → recompute waits |

## COPY RULES
- Same promise wording as the confirmation.
- One live-only reason. Not five.
- No countdown, no price, no manufactured scarcity.
- If the event is genuinely capped and full, say that plainly; otherwise do not imply it.

## FLEXIBILITY
Operator copy wins. If the operator runs a shorter runway, this file simply does not fire — set its window to the next available slot.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 02 Reminder 1 Week`
`Tag Added webinar-registered → Wait until webinar_datetime − 7d → If not purchased and future → Send Email → End`

Wait is computed from the custom field, never a fixed calendar date.

## SCOPE
**In:** registered, not purchased, seven days out.
**Out:** indoctrination, day-before and same-day reminders, replay.
