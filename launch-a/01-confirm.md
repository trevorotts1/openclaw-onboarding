# Launch A — Registration Confirmation (Set the Stage)

- **id:** `launch-a-reminder-confirm`
- **Derived from:** `44-convert-and-flow-operator/automation-templates/funnel-specific-followups/webinar-registration-reminder-replay-stack` (Phase A — Confirmation)
- **Timing:** immediately on registration (target under 2 minutes)
- **Channels:** Email + SMS (SMS only with consent)

## What it is
The first message after the registration form. It does four things and stops: confirms the registrant is in, states the exact date/time in their own zone, names the ONE promise the webinar delivers, and opens a curiosity loop that pulls them to the live event. Then it asks for the calendar hold.

It is not a sales page. The offer does not appear here.

## TRIGGER
Form Submitted on the webinar registration page, or Tag Added `webinar-registered`.
Requires `webinar_datetime` (ISO 8601 with timezone), `webinar_timezone`, `webinar_join_url`, and a calendar link.

## SEQUENCE

| Beat | Timing | What runs |
|------|--------|-----------|
| 1 | T+0 | Set `webinar_datetime` from the session field |
| 2 | T+0 | Email — Set the Stage: welcome, date/time in zone, ONE promise, curiosity loop, whitelist, add to calendar |
| 3 | T+0 | SMS (consent only) — confirm + calendar link |
| Guard | continuous | Purchased → exit path · opt-out → honour per channel · duplicate reg → update datetime, do not resend |

## COPY RULES
- Always state the time in the registrant's time zone.
- One promise, one CTA.
- No countdown, no offer language, no manufactured scarcity.
- Soap Opera #1 energy: a person talking to a person, not a broadcast.

## FLEXIBILITY
If the operator has their own confirmation copy, that copy wins. This file is a reference, never a rule.

## GHL BUILD (Skill 44)
**Workflow:** `LA — 01 Confirm (Set the Stage)`
`Form Submitted (registration) OR Tag Added webinar-registered → set webinar_datetime → Send Email → If SMS consent → Send SMS → End`

Set `order` + `parentKey` before first save. The session datetime must be a custom field so every later reminder in launch-a computes from it.

## SCOPE
**In:** a new registration.
**Out:** indoctrination emails, reminders, replay and no-show branches — each has its own launch-a file.
