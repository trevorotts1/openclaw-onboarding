# SOP-GHL-07 — Meeting Rooms

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 6 (Courses for live-course sessions) · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to set up a meeting room / live-session room for a course, event, or calendar
booking — including "set up a room for the live sessions in this course".

**Inputs:** host identity, location/company, course or event binding, session dates and durations,
recording/transcript/breakout decisions, join policy, security settings.

**Required pointers:** Skill 6 meeting-room coordinator and selector file; calendar integration
references; `SOP-GHL-03-COURSE-PRODUCTION.md` for course binding.

**Ordered steps:**
1. Resolve host identity and location. Rooms are host/location scoped — never borrow another host's
   room silently.
2. Search for an existing room first (reuse-first). Create only when no matching room exists.
3. Configure the room: name, join policy, host/guest roles, waiting room, recording, transcript,
   breakout availability. Record every setting as observed, not assumed.
4. Bind the room to the calendar event, course session, or booking as a separate association.
5. Save, close, and RE-OPEN the room to confirm the security settings persisted.
6. Run an isolated guest check with a controlled guest identity: real join link, admitted/denied
   behavior, AV readiness.
7. Record each functional sub-result separately: created, configured, bound, guest admitted, AV
   ready, recording ready, transcript ready, breakout ready.

**Allowed route changes:** Skill 6 managed browser for UI-only room configuration; public meeting
operations where they exist; private fallback only for a documented gap. Never duplicate a room to
work around a lost response.

**Required output / receipt:** room id, host id, location id, observed settings block, join-link
evidence, per-sub-result state, calendar/course/event refs, receipt.

**Approval boundary:** inviting real guests, enabling recording/transcription, and changing a live
room's security settings require the session owner's approval. Draft room setup does not.

**Failures:** Recoverable — room already exists → reuse and record; setting not persisted after
reopen → re-apply once and re-verify; guest check blocked by an unapproved microphone/camera →
record the AV limitation honestly. Terminal — host identity unavailable, wrong location, or a
security setting that cannot be verified → stop and report; never claim audio/video passed when no
device was available.

**Acceptance:** a real room exists with requested settings persisted through a save/reopen, bound to
the right session, and a controlled guest reached it through the real join link.
