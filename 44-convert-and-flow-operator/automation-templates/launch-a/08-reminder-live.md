# Launch A — Reminder: We're LIVE

**Built as draft, nothing sends** until the operator approves each workflow in GoHighLevel; this file ships the build, not the go-live.


- **id:** `launch-a-reminder-live`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase C — "We're LIVE")
- **Timing:** at `webinar_datetime`, suppressed after `webinar_end_datetime`
- **Channels:** SMS (first) + Email (fallback)

## What it is
The zero-hour push. Present tense, one link, nothing else. SMS leads; email exists for contacts without SMS consent.

## TRIGGER
Wait until `webinar_datetime`. Send only if not purchased and the current time is before `webinar_end_datetime`.

**Late registrant rule:** registered after start but while the room is open — one immediate send with honest "we're live now" copy.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | T+0 | If SMS consent → SMS: "We're LIVE — join now" + URL |
| 2 | T+0 | Else → Email: one line + one join button |
| Guard | continuous | Purchased → exit · past end datetime → no send · DND → email only · late start → follow actual start if reported |

## COPY RULES
- Present tense.
- One CTA: join.
- No price, no offer, no replay mention.
- Never send after the room closes. A dead live link teaches people to ignore the next one.

## FLEXIBILITY
Operator may shift the send to five minutes after start if the room reliably runs late; the end-datetime gate is non-negotiable.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 08 Reminder We're Live`
`Tag Added webinar-registered → Wait until webinar_datetime → If not purchased and now < webinar_end_datetime → If SMS consent → SMS → Else → Email → End`

## SCOPE
**In:** registered, not purchased, session live.
**Out:** pre-event reminders, replay and no-show branch, any offer copy.
