# SOP-GHL-05 — Community Publishing

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Community Builder owns the inside-the-room voice; Skill 35 executes approved posts · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to publish, schedule, comment on, or announce inside a community — including
"publish this post in the members-only channel" and "post this lesson announcement to our community".

**Inputs:**
- Approved copy, channel/group target, member-author identity decision, media (if any).
- The connected Social Planner account representing the Community channel, and the member contact id
  that will appear as author.
- Approval status for notifications and for member-facing announcements.

**Required pointers:**
- Skill 35 runtime publishing code; shared Community publishing adapter and public social operations.
- `universal-sops/social-media-craft/` — content calendar and brand strategy.
- `universal-sops/ghl-hybrid-operations/SOP-GHL-04-COMMUNITY-AND-LEARNING.md` — group/channel state.

**Ordered steps:**
1. Resolve the target channel/group and the author member identity. A connected Social Planner account
   id is a channel account, NOT the group id.
2. Confirm the copy is approved and the media (if any) is persisted at a permanent location.
3. Create the post with the approved visibility and author; record the returned post id.
4. Read back the post state: `scheduled` vs `published` vs `draft`. Never report scheduled as published.
5. Comments/attachments: attach against the post id; verify the attachment state separately.
6. Notifications: only after explicit approval; otherwise publish without member notification.
7. For an announcement tied to a course/lesson, record the lesson id as a reference, not as a second
   post.
8. Emit a receipt with `requested_visibility` and `actual_visibility` plus the post id.

**Allowed route changes:**
- Public Community social operation first; Skill 6/35 managed browser only for a UI-only control; a
  private fallback only for a documented gap.
- One post is created once. A lost response is reconciled by post id; never re-post.

**Required output / receipt:** post id, channel/group ref, author identity, actual state, attachment
state, receipt with the visibility pair.

**Approval boundary:** publishing to members, enabling notifications, using an agent-run account, and
speaking in the owner's voice all require the approved copy and the owner's standing voice rules. A
draft requires no additional approval.

**Failures:**
- Recoverable: duplicate post detection → reconcile and stop; missing media → persist then retry the
  attachment only; scheduled time in the past → reschedule with approval.
- Terminal: unresolved author identity → stop (never post as a human member); unapproved copy → stop;
  channel not eligible (private-channel rule) → report and offer an eligible target.
- Agent-run accounts always disclose they are agents.

**Acceptance:** exactly one post exists, state matches the requested state, attachment state is real,
notifications only when approved, and the receipt distinguishes scheduled from published.
