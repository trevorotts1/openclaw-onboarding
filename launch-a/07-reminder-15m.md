# Launch A — Reminder: 15 Minutes Before

- **id:** `launch-a-reminder-15m`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase C — final pre-live touch)
- **Timing:** `webinar_datetime` minus 15 minutes
- **Channels:** SMS only

## What it is
The last-quarter-hour catch. One line and the link. No email: the inbox is the wrong place fifteen minutes out, and a second message here costs more in unsubscribes than it returns in attendance.

## TRIGGER
Wait until `webinar_datetime` − 15 minutes. Send only if not purchased, future, and SMS consent is present.

**Late registrant rule:** registered inside the final 15 minutes — skip; the live reminder is the only appropriate touch left.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | T−15m | SMS — "We start in 15 minutes" + join URL |
| Guard | continuous | Purchased → exit · no SMS consent/DND → no send, no email substitute · past datetime → no send |

## COPY RULES
- One line, 160 characters where possible.
- No pitch, no price, no countdown.
- Must name the 15-minute gap; never repeat the 1-hour wording.

## FLEXIBILITY
Operators without SMS consent simply do not run this node. There is no email fallback by design.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 07 Reminder 15 Minutes`
`Tag Added webinar-registered → Wait until webinar_datetime − 15m → If not purchased, future, SMS consent → SMS → End`

## SCOPE
**In:** registered, not purchased, SMS-consented, 15 minutes out.
**Out:** email, live reminder, replay.
