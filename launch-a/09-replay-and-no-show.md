# Launch A — Replay and No-Show Branch

- **id:** `launch-a-replay-and-no-show`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase D — Replay)
- **Timing:** `webinar_end_datetime` + 2 hours (configurable 1–4h); replay window ends at `cart_close_datetime`
- **Channels:** Email + SMS (SMS only with consent)

## What it is
The post-live recovery. One branch, two messages, one shared deadline:

- **No-show** — "Sorry we missed you" + replay + real expiry.
- **Attended, no buy** — "Did you catch the offer at the end?" + replay anchored to the offer segment.

The branch exists so the copy never lies about what the person did.

## TRIGGER
Wait until `webinar_end_datetime` + 2h. Then:

1. Purchased → end.
2. `webinar-attended` **or** `webinar-buy-link-clicked` → attended branch.
3. Anything else, including no attendance signal → no-show branch. Never assume attendance from silence.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | end + 2h | Branch on attendance tags and buy-link clicks |
| 2 | end + 2h | No-show: replay email + one SMS, expiry stated once |
| 3 | end + 2h | Attended no-buy: offer-recap email + one SMS |
| Guard | continuous | Purchased → exit · missing replay URL or close datetime → build error · DND → email only · reschedule → replay stays bound to the delivered session |

## COPY RULES
- The replay expiry and `cart_close_datetime` are the same instant. If they differ, fix the build, not the copy.
- No fake extensions, no second countdown, no "we reopened it" unless it is true.
- Never shame a no-show. "Sorry we missed you" is the ceiling.
- Never re-teach the webinar to an attendee; point at the offer segment.

## FLEXIBILITY
Operator may split the branch into two workflows; the branch logic and the single deadline stay the same. If the operator has no replay page, this file does not run.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 09 Replay and No-Show`
`Tag Added webinar-registered → Wait until webinar_end_datetime + 2h → If purchased → End → If/Else attended or buy-link-clicked → attended email → Else → no-show email → If SMS consent → branch-matched SMS → Wait until cart_close_datetime → End`

Attendance tags come from the platform webhook or a join-link click. The replay page countdown must read the same `cart_close_datetime` this email cites.

## SCOPE
**In:** non-buyers after the live session ends.
**Out:** buyers (onboarding), pre-event reminders, the cart-close Emotion/Logic/Fear sequence.
