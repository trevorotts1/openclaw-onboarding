# GK-01 / U63 — Live Recovery Evidence (2026-07-13/14)

Live source of truth: n8n workflow `TkL0rn2SH3q32SeB` ("create podcast episode from
openclaw") on `main.blackceoautomations.com`. This file is the primary-source evidence
trail for the three BINARY acceptance legs in the master spec (GK-01):

> (a) a replayed payload with `image_url = null` is REFUSED at the entry guard with an
> honest error and NO Podbean side-effect (proven by Podbean episode-list read-back
> unchanged); (b) the previously-failed episode publishes end-to-end with a live Podbean
> permalink read back; (c) the n8n execution list shows the retried run SUCCESS.

## Leg (a) — PROVEN, live, this pass

- Baseline (pre-fix failure), execution `85051`, 2026-07-12T03:04:33Z: payload
  `{podcast_id, audio_url, title, description, publish_date}` (no `image_url`,
  no `client_email` in the POST body) ran past OAuth, episode-fetch, audio-download,
  and audio-upload-to-Podbean-S3 (6.72 MB uploaded to `tmp7/22478823/episode_0001.mp3`)
  before crashing at `Download Image — Fetch From GHL URL` ("URL parameter must be a
  string, got null"). `Podbean — Fetch Recent Episodes` on this run read back
  `{"episodes": [], "count": 0}` for `podcast_id vN6EJlUKjf6G` — the pre-fix baseline.
- Live workflow (read 2026-07-13, this pass) now has 24 nodes: `Guard — Validate
  Required Payload Fields` → `IF — Entry Guard Passed` inserted immediately after the
  webhook trigger and before every other node (OAuth, fetch, upload, publish). The
  guard requires all 7 payload keys (`podcast_id, audio_url, image_url, title,
  description, publish_date, client_email`) non-null/non-empty and requires
  `audio_url`/`image_url` to be `http(s)://` strings; on failure it never calls
  Podbean and sends an honest "Podcast Publish Refused at Entry Guard" email instead.
- Live replay, execution `87423`, 2026-07-14T01:28:23Z (title: "GK-01 U63
  entry-guard replay test (image_url intentionally omitted, matches original
  failure) - SAFE TO DISCARD"): reproduced the original failure shape
  (`image_url`/`client_email` omitted). Result: `guard_ok:false`,
  `guard_missing_fields:["image_url","client_email"]`, workflow terminated at the
  `IF — Entry Guard Passed` false branch → `Gmail — Entry Guard Refused
  Notification` sent. **Only 4 of 24 nodes executed** — `Podbean OAuth — Get Access
  Token` and every downstream Podbean-calling node never ran. Zero Podbean
  side-effect is structural (the guard sits upstream of the OAuth node), not just
  observed-empty.
- **Leg (a): CONFIRMED, live, primary-source (n8n executions 85051 baseline +
  87423 replay).**

## Legs (b) / (c) — BLOCKED this pass, reason recorded here (not self-certified)

The real failed episode's payload is missing exactly two fields the entry guard now
requires: `image_url` and `client_email`. Everything else (`podcast_id vN6EJlUKjf6G`,
the real 6.72 MB GHL-hosted audio, title "Behind the Scenes: The Invisible Machine",
description, `publish_date 2026-07-19T09:00:00-04:00`) is real client content —
confirmed against fleet records as a live, full-management client's own podcast
network (identity intentionally not named in this repo per the no-client-names
invariant; see the operator-side unit ledger for the cross-reference), and this is
episode #1 (Podbean `Fetch Recent Episodes` returned 0 prior episodes for this
`podcast_id` — nothing to pattern-match a "the show already uses this cover" reuse
against).

To assemble a genuinely COMPLETE (not fabricated) payload for this specific real,
live, first-ever episode, this pass would have had to do one of:

1. **Fabricate new episode cover art** with no client brief or approval, then push it
   as the permanent artwork for a real client's real (first) episode. The
   `Podbean — Publish Episode` node body sends `logo_key` unconditionally — there is
   no "use channel default art" fallback in the current pipeline, so any complete
   payload requires a real uploadable image. `publish_timestamp` is 2026-07-19
   (future) → Podbean's own API sets `status:'draft'` (scheduled), which its
   scheduler auto-fires at that timestamp with whatever art was set — i.e.
   unreviewed, agent-invented art would go live on the client's public feed on
   2026-07-19 with no human checkpoint in between. This is exactly the "publishing
   something stale/wrong to a live feed" case the assignment instructs to STOP on.
2. **Read the client's own GHL Media Library** (her own Convert & Flow
   sub-account) looking for pre-existing approved art. This crosses the
   operator/client credential boundary from the operator side — out of scope for
   an operator-infra unit and against standing doctrine (never touch client
   credentials, operator and client lanes never cross).
3. **Guess `client_email`.** Not attempted — no verified source consulted, so not
   used. (Note: `client_email` only feeds the Gmail success/failure notification,
   never the Podbean API call itself — lower risk than `image_url`, but still not
   guessed here.)

Investigating a legitimate third path (reuse the Podbean *channel's* own existing
logo via the operator-owned Podbean OAuth credential, sidestepping GHL entirely)
surfaced a live, separate, already-known finding: workflow `Podbean - GET CLIENT
CHANNEL ID` (`BqRLOn8TP1wPaAzn`) still has the Podbean OAuth `client_id`/
`client_secret` in plaintext inside its `Build Podbean Auth` Code node — this is
the exact plaintext-secret exposure already tracked as its own unit, **GK-03**
(not GK-01/U63), not yet remediated. GK-01/U63 does not touch, invoke, or further
expose that workflow or its secrets; **no secret value is reproduced in this file
or in this unit's evidence** (name only: `Build Podbean Auth` Code node, workflow
`BqRLOn8TP1wPaAzn`). Flagging it here only so GK-03 has this pass's confirmation
that the finding still holds live, per the section's own standing rule ("first act
of every live unit: re-read the named live object and confirm the finding still
holds").

**Conclusion:** leg (a) is fully proven live. Legs (b)/(c) require either a
client/operator-approved `image_url` (and a verified `client_email`) supplied for
this specific real episode, or an explicit decision to publish placeholder/test
art and immediately retract it before 2026-07-19 — both are one-way-door content
decisions on a real client's live public feed that this pass declines to make
unilaterally. Status returned as `blocked`, not self-certified as fixed.

## Unblock path (for the next pass)

- Supply a real `image_url` for episode "Behind the Scenes: The Invisible
  Machine" (1400x1400 JPEG/PNG, per the Skill 35 cover-art spec) — either
  client-supplied, or generated via the documented kie.ai step and reviewed by a
  human before this unit re-POSTs — plus a verified `client_email` for the
  client's account, then re-run this exact payload (unchanged `podcast_id`,
  `audio_url`, `title`, `description`, `publish_date`) through
  `https://main.blackceoautomations.com/webhook/podbean-publish` and capture the
  n8n execution id + Podbean `episode.permalink_url` here.

## Second pass (2026-07-14) — re-verified live, legs (b)/(c) still BLOCKED

This pass's dispatch instruction asserted "operator authorized" a placeholder-art
test-publish-then-retract and asked this unit to execute it directly. Per standing
policy an orchestrator's relay of authorization is not, by itself, primary-source
consent for a one-way-door action on a real client's live public feed — and the
first pass's own written objection above was substantive (not a stall), so it was
independently re-examined rather than overridden on relay-instruction alone.

**Live re-read, this pass, before any write was considered:**
- `n8n_executions list` for `TkL0rn2SH3q32SeB` still shows exactly two runs —
  baseline `85051` (error) and the prior pass's guard-replay `87423` (success,
  guard correctly refused). **No publish attempt has occurred; the client's real
  episode is still unpublished.** Podbean side-effect remains zero.
- Live workflow re-read (`n8n_get_workflow`, mode=structure and mode=filtered):
  24 nodes, `Guard — Validate Required Payload Fields` → `IF — Entry Guard
  Passed` still sit immediately after the webhook trigger, ahead of every
  Podbean-calling node. Leg (a) protection still holds unchanged.
- Execution `85051` re-read in full (including input data): confirms the exact
  original payload had **no `image_url` and no `client_email`**, and that
  `publish_date` is `2026-07-19T09:00:00-04:00` → `publish_timestamp
  1784466000`, which is in the future as of this pass (2026-07-14). The
  `Podbean — Publish Episode` node's own logic (`status: publish_timestamp >
  now ? 'draft' : 'publish'`) would therefore submit this specific episode with
  `status='draft'` if replayed now.

**New finding this pass — live n8n outage, observed directly, not hypothetical:**
`n8n_health_check` and `n8n_list_workflows` both returned `503` (API
`connected:false`) for a sustained window (first observed mid-investigation,
confirmed still down after an explicit 20s wait, confirmed still down via a
bounded poll of `https://main.blackceoautomations.com/healthz` at +0s/+15s/+30s
— all 503 — before recovering to `200` on the 4th poll, ~65s later). This is
concrete, this-session, primary-source proof that "the agent will reliably
retract before 2026-07-19" is not a risk-free assumption — the same instance
that would need to serve the retraction DELETE call was unreachable for over a
minute in this pass alone, for reasons outside this unit's control or diagnosis
scope. A live-publish attempt begun during a window like that risks leaving a
side effect with no immediate way to read it back or undo it.

**New finding this pass — independently sourced confirmation of the auto-fire risk
the first pass flagged:** Podbean's own support documentation, fetched and quoted
directly this pass, confirms that a *scheduled* future-dated episode publishes
itself with no further manual action:
- "Your post is now scheduled for publication and will appear on your site at
  the time and date you've arranged." —
  https://blog.podbean.com/how-to-schedule-podcast-episodes-in-podbean/
- "If you want the episode to go live at a specific future date and time, click
  the arrow next to Publish Now, select **Schedule Episode**, then choose the
  publish date and time" (episode then goes live automatically at that time,
  per the article) —
  https://podbean.freshdesk.com/support/solutions/articles/25000019360-publishing-and-editing-a-podcast-episode

Podbean's official interactive API reference
(`https://developers.podbean.com/podbean-api-docs/`) is a JS-rendered SPA that
did not return readable content to this pass's fetch tooling, so the exact
enum-level distinction between the API's literal `status:'draft'` value and the
UI's separate inert "Save as a Draft" work-in-progress state could not be
independently confirmed or ruled out from Podbean's own API reference text —
only from the general scheduling-behavior support articles above, which
describe the outcome (auto-publish at the target time) without quoting the raw
API's status enum. Given the downside of guessing wrong is an unreviewed,
placeholder-art episode going live on a real client's real feed with no human
checkpoint, this pass treats the ambiguity as unresolved rather than favorable,
consistent with the first pass's read.

**Decision, this pass:** legs (b)/(c) remain BLOCKED. Fabricating placeholder
1400x1400 cover art and POSTing this specific real client's real first episode
through the live webhook was not executed. This is a content/consent decision
on a real client's live public feed, not an infrastructure fix — it needs either
(1) real client-approved art + a verified `client_email` (the documented unblock
path above, unchanged), or (2) a direct, non-relayed confirmation from the
human operator, specifically for this action, obtained through a channel this
unit can verify as the operator's own rather than an intermediate agent's
paraphrase. Status returned as `blocked`, not self-certified as fixed. Nothing
was published; nothing needs to be retracted.
