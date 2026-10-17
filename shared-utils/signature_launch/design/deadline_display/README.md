# Deadline display

**Component:** `deadline-display` v1.0.0 · **Owner:** S71 · **Implements:** doc 16 §1 (component inventory, "Deadline display — real deadline and timezone; never reset-fake scarcity") and doc 16 §8 (automatic failure: invented scarcity).

## Purpose

Show an approved offer page's real deadline in its real timezone — or
honestly show that there is none, or that it has passed.

## Inputs

`render_deadline_display(deadline, now, tokens=None)`:

- `deadline.deadline_at` — ISO-8601 instant **with UTC offset**, or
  `None`. A naive (offset-less) value is rejected with `ValueError`:
  an ambiguous deadline is not displayed.
- `deadline.timezone` — IANA timezone name used for display
  (e.g. `America/New_York`); defaults to `UTC`. A value that is not
  an IANA timezone name raises `ValueError` naming the value (see
  Failure modes).
- `deadline.label` — plain-text label (escaped).
- `deadline.expired_text` — optional override for the expired state.
- `now` — timezone-aware datetime the render is computed against.
  Injected (rather than read from the clock) so rendering is
  deterministic and testable; callers pass the real current time.

## Outputs and states

Returns `{html, state, deadline_at, timezone}` with exactly three
states:

- `absent` — no deadline supplied. The HTML is the shell with
  `data-state="absent"` and **no date, countdown or scarcity text**.
  The component never invents a deadline to manufacture urgency.
- `active` — deadline in the future. Renders the label, the deadline
  formatted in the launch timezone, and the remaining time computed
  from `now`. The markup carries `data-deadline-at` (UTC instant) and
  `data-timezone` so a page may tick the display client-side against
  the same fixed instant.
- `expired` — deadline at or before `now`. Renders the label, the
  deadline, and the expired text. **The deadline is never extended,
  rolled forward or reset** by this component — no reset-fake scarcity.

## Failure modes

All input failures raise `ValueError`, the component's one documented
error type:

- `deadline_at` without a UTC offset (naive) — rejected; an ambiguous
  deadline is not displayed.
- `now` without tzinfo — rejected.
- `timezone` that is not an IANA timezone name — rejected with a
  `ValueError` naming the offending value. The timezone is consulted
  only when a deadline is present, so the absent state renders
  regardless of the timezone value.

## Tests

`tests/test_deadline_display.py` (stdlib unittest): absent deadline
renders the absent state with no scarcity text; a past deadline renders
the expired state; a future deadline renders active with the deadline
formatted in the named timezone and a computed remaining time; a naive
deadline is rejected; an unknown timezone raises `ValueError` naming
the value.
