# Existing-room co-host reconciliation

`meeting_cohosts.configure(page, inputs)` implements the captured native
candidate/row/Delete/Save path. `meeting-cohosts.json` is the dedicated handler's
input shape, not an executable client plan. For the named recipe front door,
wrap its room-specific fields under `meeting` while keeping `location_id`,
`location_name` and `start_url` at the top level; use `meetings.setup` or
`meetings.update` with `allow_creation:false`. Room metadata are unchanged
preflight guards. Perform room creation or metadata changes in a separate job,
then inventory that persisted room and complete roster before this job. Replace every inventory placeholder,
including the invalid example room origin, with independently read values.

The host must record owner approval for the exact access change before setting
`access_change_acknowledged:true`. This is a distinct room-permission change;
an approval to rename a room does not imply approval to change its co-hosts.
`expected` and `desired` are complete nonempty lists of exact native name/email pairs.
Native zero rows have no captured loaded-empty marker, so starting from an empty
roster and removing every co-host are refused. Additions stage before removals
to keep the roster independently readable throughout the transaction.
No email address, person, room identity, or previous security setting is invented.
The handler only operates on an existing verified room, never starts a meeting,
and does not touch microphone, camera, passcodes, or room security.

The parent runner records intent and holds its tenant/evidence writer lock before
calling the handler. It must retain an uncertain-write journal after any failure,
read the same room to reconcile, and never automatically retry an access write.
All additions are checked in the native directory before any permission control
is clicked. After read-only preflight, the handler discards the search by the
known room-detail URL and rereads the complete previous roster. Every selected
candidate and removed row is checked against its exact staged roster; an
unexpected dialog or confirmation stops the operation. The known Save changes
control is clicked once, then an independent room reload/reopen verifies the
complete desired roster and protected room settings.

Receipts omit names and emails. They bind the room, tenant, app origin,
expected/desired configuration hash, counts, and independent readback.
`functional_verified:false` and `notification_behavior_verified:false` remain
pending: these source/fixture checks do not prove native client access or that
HighLevel sends no notifications. The native assignment workflow has not been
executed as acceptance proof. Dynamic per-appointment rooms and native
community/course associations remain separate build gaps.
