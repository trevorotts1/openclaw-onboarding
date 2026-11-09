# Associate an existing community event with Live Room

`community_event_meeting.run_event(page, inputs, evidence_root,
portal_context=context)` is the dedicated existing-event handler. The host uses
`meetings.integrate` with `integration_mode:community_event_room`; the JSON example
shows the handler payload. Replace every placeholder and every expected value with
actual inventory. The example portal is deliberately invalid. This handler does
not create the event, change its attendees, or share a post.

The captured scope is an existing Free, USD, nonrecurring event for All members,
with a visible location, reminders off, and the native empty thumbnail state.
It preserves all title/description/date/time/AM-PM/timezone/recurrence/attendee
visibility and payment controls. Other event kinds and existing thumbnails stop
before writes. Both complete `expected.view` and `expected.form` inventories are
required; the native event/group IDs are checked through the sidebar and the
view's event-attendee analytics marker. The edit action binds the captured pencil
SVG signature, so it cannot accidentally choose the adjacent trash control.

**Selecting Live Room immediately creates a room, before Update Event.** The host
must obtain approval for that exact native creation before setting
`allow_room_creation:true`. The handler holds its existing tenant/evidence writer
lease and writes `community-event-state.json` before that selection. A failure
after selection or Save retains a reconciliation journal and never retries the
room creation. An existing Live Room can be independently verified and reused with
`allow_room_creation:false` without creating another room or updating the event.

Before execution the host captures an opaque same-session identity context:

```python
from playwright_recipes import community_event_meeting
context = community_event_meeting.capture_context(
    page, inputs, identity_reader=installed_authenticated_portal_reader)
result = community_event_meeting.run_event(
    page, inputs, evidence_root, portal_context=context)
```

The Page must already be authenticated on the exact group's `/events` route.
The installed reader must perform a real current read from that same portal
session and return authenticated/location/origin/group ID/slug/name/current-user
facts with `source_kind:same_session_authenticated_read`. A caller-authored JSON
object, a different API credential, a matching page title, or a previous account's
context is not proof. No reader means `PORTAL_CONTEXT_REQUIRED`; this handler never
logs in, seeds another account, or guesses a portal domain.

The handler first reads the existing event view, edit form, and Free payment page,
then returns to verify unchanged form values. Only the native location is changed.
The generated disabled link must be on the same portal at `/meet/<24-hex-room-id>`
without credentials, query, or fragment. After Update Event it reloads and reopens
the same event independently, waits for stable complete metadata and the exact
canonical link, then checks the complete form and payment page again. It leaves
reminders off and never clicks Share/Share as Post or a meeting start control.

Receipts omit event copy, dates, attendees and URLs. They bind location/event/group,
generated room ID, configuration hash, independent readback, and creation/reuse
state. `functional_verified:false` and `notification_behavior_verified:false`
remain pending; source/fixture validation does not prove native access or that the
platform sends no notifications. Native course live-session associations remain
separate work.
