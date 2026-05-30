# Showing Scheduler Protocol

Governs how the agent schedules and manages property showings, honoring lockbox
type and MLS showing rules. Config lives in
`templates/showing-scheduler-config.template.json` (seeded into the client master
files by `scripts/06-scaffold-showing-scheduler.sh`).

## When this protocol activates

A lead requests to view a property, OR a showing/open-house slot is offered and
accepted. Skill 38's conversation engine detects the intent; this protocol owns
the scheduling mechanics.

## Inputs (from the config)

- `lockbox_type` — `supra` / `sentrilock` / `combo` / `agent_accompanied` / `none`
- `showing_window` — allowed days/hours for unaccompanied showings
- `mls_confirmation_required` — whether the MLS requires a confirmed appointment
- `agent_must_accompany` — listings that require the agent present
- `min_notice_hours` — minimum lead time to book
- `reminder_offsets_hours` — defaults `[24, 2]`

## Steps

1. **Confirm the basics** — date, time, full address, and access details
   (lockbox type + how access works). If `agent_must_accompany` is true for this
   listing, schedule WITH the agent; do not hand out lockbox access.
2. **Respect MLS rules** — if `mls_confirmation_required`, mark the showing
   `pending_confirmation` until the listing side confirms; never tell the buyer
   it is confirmed before it is.
3. **Respect the window + notice** — reject or counter-offer slots outside
   `showing_window` or inside `min_notice_hours`.
4. **Set reminders** — schedule reminders at each `reminder_offsets_hours` value
   (default 24h + 2h). Capture cancellations early.
5. **Surface disclosure compliance** — run the state-disclosure-compliance
   protocol for the property's state; surface the pointer; ESCALATE the decision
   to the licensed agent (Skill 39 gives the pointer, not legal advice).
6. **Emit the event** — append a `showing` event to `real-estate-events.jsonl`
   with `state`, `lockbox_type`, `reminders_set`.

## Honesty floors

- Never promise access the agent has not granted.
- Never claim a showing is confirmed before the MLS / listing side confirms.
- Never give the lockbox code to an unverified party.

## Fair-housing

Schedule on availability and listing rules only — never differentiate showing
access by protected class.
