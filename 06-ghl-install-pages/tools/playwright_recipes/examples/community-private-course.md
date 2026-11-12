# Native community course association

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
is not a reader. The November 11 first-course profile permits an empty inventory
only after network idle, the exact bound Learning heading and a complete grid
containing one direct wrapper with only its captured Add New Course card/title/
description. Error/Retry states, extra children or arbitrary zero-card counts
stop with `NATIVE_EMPTY_COURSE_INVENTORY_UNPROVEN`. The whole native profile is
independently read again after reload before the first course association.

Supply a fresh `api_capability` proving same-location v3 `courses.readonly`.
The script reads every paginated product before using the native title-only
selector: the exact requested ID must own the sole case-insensitively matching
title. It reads that product directly again, then independently reloads Learning
before authoring. Every existing native card's DOM ID, `data-analytics` product/
group IDs, title, badge text and sibling order must match `expected_courses`.
If a native badge is absent its inventoried `visibility` is `null`; that is a
read-only absence record, not a claim about member access.

The captured `Private` and `All members` choices can be authored explicitly.
The November 11 Add Course modal exposes `All members` as its default. The
All members add path requires the native `Free` badge after its explicit native
selection, captured after independent reload on November 11. An existing Free
badge alone does not prove its access mode, so All members reuse refuses until
its access-details capture is available. Unbadged cards are not accepted as Free. Exact existing
Private associations can be reused. Purchase, time, level and channel modes
remain unsupported; different existing access never triggers an implicit update. The saved native card must
expose the exact API course ID and expected native group ID. After Add Course,
the optional Share Course as Post prompt is **skipped**; Share as Post is never
clicked. No invitation or message is sent. Every sibling card is protected, and
an independent Learning reload verifies the association and its observed order.

This group-configuration executor shares `community-details-state.json` and
the existing `community_details` evidence lease. Separate operations need
separate evidence roots. Intent precedes native Add Course. Any uncertain save
retains its journal and refuses a second add; reconcile native cards first.
Exact completed replay validates the saved proof and fresh portal context, then
independently reloads Learning and reads the requested association plus the
complete sibling inventory. Missing, renamed, duplicated or access-changed cards
stop for reconciliation without repeating API reads or native creation. Reusing
an existing association preserves the entire inventoried card order; a newly
added card can occupy any native position while its siblings retain their order.

The receipt stays `NEEDS_VERIFICATION`, with `controls_verified:true`,
`independent_readback:VERIFIED`, `functional_verified:false`,
`behavior_verified:false`, `communication_attempted:false` and
`verification_required:true`. Root integration must bind its `course_id`,
`group_id`, authored `visibility`, configuration hash and community object before
accepting it. Native Python/member behavior acceptance remains separate.

Replace every example identity/title/URL from approved inventory. The empty
example `expected_courses` is not evidence that the target group has no courses.
Community branding file chooser, association visibility updates and group
creation/reuse are separate operations.
