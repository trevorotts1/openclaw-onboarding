# Meeting Rooms — UI-only configuration and honest live-state proof

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inherited`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## Capability boundary

No public Meeting Room lifecycle contract is confirmed. Trevor's $497 agency entitlement and recorded Meeting Room availability are **owner-supplied facts**, not measured permission for every staff user or client. Implement initial capability through Skill 6's managed browser; adopt an official API/MCP operation only after its exact contract is in the shared registry.

A calendar "meeting location" field, a physical calendar resource, or a generic room URL is not proof of a video-room creation API.

## Request-to-design map

| Request | Design | Verify |
|---|---|---|
| Permanent office-hours link | Reusable host room, schedule/admission | Same join link persists; host admits |
| Replace Zoom for discovery calls | Calendar integration, unique appointment links when supported | Two test appointments get distinct links |
| Client onboarding calls | Calendar-linked room, co-host, reminders/follow-up | Booking/reschedule/cancel consistent |
| Rooms for coaches | Rooms owned by each authorized staff user | Correct owner; no shared identity |
| Live sessions in a course | Course live-session placement + room integration | Learners find it; outsiders do not |
| Weekly group coaching | Reusable or per-session by privacy | Recurrence/timezone/admission/late join |
| Small-group breakouts | Optional advanced branch | Participants enter/return; capture behavior understood |

## Internal plan

`location_id, host_user_id, purpose, room_link_mode (reusable|appointment_unique|existing_room), existing_room_reference, calendar_id/course_id/event_id, cohost_user_ids, participant_audience, allow_guests, waiting_room_policy, passcode_secret_reference, schedule_timezone, duration/notice/buffers/recurrence, recording_policy, transcription_policy/language, summary_policy/review_owner, retention_and_sharing_policy, notification_policy, approval_references`.

Never store an actual passcode in the repo or a client-facing report: keep a secret reference.

## Managed sequence

Bind identity → probe the feature (distinguish entitlement, permission, rollout, selector drift) → inventory existing rooms → use the observed `Meeting Room > My room > Create room` flow → apply only supported settings → save and **reopen** to verify → configure calendar/course/event integration → verify guest join in an isolated context → run an authorized rehearsal → deliver join vs host vs booking links distinctly.

Calendar/Appointment API operations stay with Skill 44. No new calendar field or provider enum is invented here.

## Security and proof

Recording, transcription, summary and transcript-based features are separate capabilities. Recording alone does not prove a transcript. Do not start mics/cameras/an instant meeting/a recording merely to test a button. Do not replace existing Zoom links or customer notifications without an approved migration.

Honest sub-results: `configuration_saved_and_reopened`, `host_identity_verified`, `guest_join_flow_verified`, `calendar_link_generation_verified`, `reschedule_and_cancellation_verified`, `live_audio_video_verified`, `screen_sharing_verified`, `recording_verified`, `transcript_verified`, `summary_verified`, `follow_up_task_creation_verified`.

A headless host without media devices returns `SETUP_VERIFIED / LIVE_AV_PENDING`; it never claims audio passed.

## Registry state

`meeting_rooms.configure` is a `browser-backed` gap (WF26); selectors stay `capture-pending` until a real capture. Tests may use fakes and must label them fake.
