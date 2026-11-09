# SOP-GHL-04 — Community and Learning

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Community Builder owns structure/membership; Skill 6 executes group/Learning operations · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to create or change a group, channels, membership, permissions, or to attach a
course to a group's Learning tab — including "create a private community with 2 channels" and
"attach the existing course to the group's Learning tab".

**Inputs:**
- Group purpose, visibility (private/public), channel list, posting/moderation policy.
- Member list or source of membership (never unverified imports).
- `community_group_id` (opaque backend id) and `community_group_slug` (portal slug) treated as
  separate identifiers; resolve `account.meta.groupId` when the API needs the backend id.
- The course/product id for a Learning association, and the learner membership decision.

**Required pointers:**
- Skill 6 `ghl_community_builder.py` and course/Learning operations.
- Shared Community/course selector map, `gates.json`, and selector prose (Skill 6 owner).
- Skill 44/35 public Community social operations for posts/comments (SOP-GHL-05).
- `universal-sops/ghl-hybrid-operations/SOP-GHL-03-COURSE-PRODUCTION.md`.

**Ordered steps:**
1. Resolve the location and confirm the group does not already exist (GET-first by name/slug).
2. Create the group with the approved visibility and settings; record both the opaque group id and
   the slug as separate object refs.
3. Create channels in the approved order; set posting permission and notification defaults.
4. Add members only from the approved source; record skips and failures per member.
5. Attach the course to the group's Learning tab as a SEPARATE association object. Same location
   only; idempotent — a repeated association must not duplicate.
6. Read back: group visibility, channels, member counts, Learning association state.
7. On cleanup: detach the association and mark residue inactive. Detaching never deletes the course.
8. Emit one receipt per object plus one per association; include `object_refs` for both ids.

**Allowed route changes:**
- Skill 6 managed browser for UI-only group/channel/Learning controls; public Community operations for
  supported post/member reads; existing private fallback only for a documented gap.
- Never create a second group to work around a selector or a lost response.

**Required output / receipt:** group id + slug, channel list, member operation results, Learning
association state, cleanup residue record, receipts naming the actual rail.

**Approval boundary:** changing visibility, posting permissions, moderation rules, removing members,
and publishing a member-facing announcement require Community Builder director approval. Creating a
draft group does not.

**Failures:**
- Recoverable: missing selector → capture real UI state and fix that selector; member already present
  → record idempotent skip; association already exists → record existing state.
- Terminal: course belongs to a different location → stop, never cross-locate; detach would delete the
  course → refuse and report; unapproved member source → stop.
- Residue: reused resources are never deleted; inactive residue is recorded for the next audit.

**Acceptance:** one group, correct visibility, channels, member state, and a separate idempotent
Learning association; detach leaves the course intact; receipts carry both identifiers.
