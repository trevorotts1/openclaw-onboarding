# Native admin-only community course association

`community_courses.run_courses(page, inputs, evidence_root,
portal_context=..., transport=...)` adds or reuses one exact course through the
community Learning tab. `communities.configure` jobs containing
`course_associations` use this dedicated portal executor. Validate with
`community_courses.validate_inputs` and bind host receipts/replay to
`configuration_hash(inputs)`, exact native group slug/ID and course ID.

The trusted host captures `community_portal.capture_context` on the exact group
home with a real authenticated same-session identity reader. The module reuses
that opaque context on the exact `/learning` URL, continuously checking the same
location, portal origin, group slug/name and user. A JSON approval/context flag
is not a reader. Zero visible cards always stops with
`NATIVE_EMPTY_COURSE_INVENTORY_UNPROVEN` until a positive native loaded/empty
marker is captured. An authenticated `group_id`, visible grid, settled network
or repeated empty counts do not establish that async course loading completed.
This implementation currently adds/reuses associations in positively populated
native course inventories; first-association creation remains a capture gap.

Supply a fresh `api_capability` proving same-location v3 `courses.readonly`.
The script reads every paginated product before using the native title-only
selector: the exact requested ID must own the sole case-insensitively matching
title. It reads that product directly again, then independently reloads Learning
before authoring. Every existing native card's DOM ID, `data-analytics` product/
group IDs, title, badge text and sibling order must match `expected_courses`.
If a native badge is absent its inventoried `visibility` is `null`; that is a
read-only absence record, not a claim about member access.

Only the native `Private` visibility is authored: the captured option is
admin-only. Public/member, purchase, time, level and channel access modes are not
substituted. An existing exact Private association is reused; a different
existing access setting refuses an implicit update. The saved native card must
expose the exact API course ID and expected native group ID. After Add Course,
the optional Share Course as Post prompt is **skipped**; Share as Post is never
clicked. No invitation or message is sent. Every sibling card is protected, and
an independent Learning reload verifies the association and its observed order.

This group-configuration executor shares `community-details-state.json` and
the existing `community_details` evidence lease. Separate operations need
separate evidence roots. Intent precedes native Add Course. Any uncertain save
retains its journal and refuses a second add; reconcile native cards first.
Exact completed replay validates the saved proof and the fresh portal context
without repeating API reads or native creation.

The receipt stays `NEEDS_VERIFICATION`, with `controls_verified:true`,
`independent_readback:VERIFIED`, `functional_verified:false`,
`behavior_verified:false`, `communication_attempted:false` and
`verification_required:true`. Root integration must bind its `course_id`,
`group_id`, `visibility:Private`, configuration hash and community object before
accepting it. Native Python/member behavior acceptance remains separate.

Replace every example identity/title/URL from approved inventory. The empty
example `expected_courses` is not evidence that the target group has no courses.
Community branding file chooser, association visibility updates and group
creation/reuse are separate operations.
