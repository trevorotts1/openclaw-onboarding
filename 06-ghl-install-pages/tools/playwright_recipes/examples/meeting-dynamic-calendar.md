# Native per-appointment Meeting Room location

`meeting_dynamic.configure(page, inputs)` edits the native calendar Meeting Room
location, which differs from a permanent custom room URL. The dedicated handler
payload is shown in `meeting-dynamic-calendar.json`; the host selects it through
`meetings.integrate` with `integration_mode:dynamic_calendar_room`. Replace every
placeholder with actual inventory. The sample `observed_at:0` deliberately fails
freshness: the host must perform the real API read and must never invent a recent
timestamp or a successful receipt.

Captured November 9, 2026: Connections > Video conferencing displays the selected
staff and its native connected Meeting Room card; calendar settings use
`iframe[name=calendar-app]`; exact edit actions/Calendar ID bind the editor; Staff
& location identifies its native dropdown by the assigned staff ID; Meeting Room
is a native selectable option. Selecting it removes the previous Custom location
textbox. The live account was inspected without saving a calendar change.

The captured executable scope is one existing assigned staff and one location.
It accepts the captured Custom location without a display label, or an already
selected Meeting Room. Other native location kinds, multiple staff, multiple
locations, existing custom display labels, connecting a new conferencing provider,
and changing the selected Connections staff are refused until their complete
native controls are captured. The complete expected staff/location record is
checked before selection and again against the saved record after an independent
calendar-list reopen. The existing native calendar ID, staff ID and app origin
must agree throughout; no calendar is created or renamed.

Connections exposes the selected staff's name but no user ID. The handler therefore
requires the host's fresh successful complete same-location `users.search`
inventory. Its `users` list contains the minimal user projections `id`, `name`,
and `roles.locationIds`; `complete:true` means the host followed every pagination
page, and `total_count` must match the full returned list. Every entry must belong
to the location and IDs must be unique. The selected native name must resolve to
exactly one inventory user, including case variants, and that user's exact ID/name
must match the assigned staff. A single `users.get` result or partial first page
cannot establish this binding. The name-only connection card remains a prerequisite,
not proof of the authenticated user's opaque ID; the native calendar control binds
the actual assigned staff ID.
Receipt providers use the existing authenticated API/Skill44/MCP rail; this
handler introduces no credentials or transport. Official read contract:
<https://marketplace.gohighlevel.com/docs/ghl/users/users/index.html> (Search).

The parent runner must hold its existing tenant/evidence writer lease and record
intent before calling this handler. Any selection/Save error is uncertain and
requires read-only reconciliation on the same calendar, never automatic replay
of a write. The handler does not book an appointment, start a meeting, or send an
invitation. It saves only the native Meeting Room location and verifies its
independent readback. Receipts retain `functional_verified:false` and
`dynamic_room_generation_verified:false`; creating a fresh room link for a real
appointment has not been tested. Native community/course associations remain a
separate build gap.
