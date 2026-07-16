# GK-01 / U63 — Legs (b)/(c), live publish result (2026-07-16)

## What was submitted

`POST https://main.blackceoautomations.com/webhook/podbean-publish`, same
`podcast_id`, `audio_url`, `title`, `description`, `publish_date` as the
original 2026-07-12T03:04Z failed payload (execution `85051`), unchanged,
plus the two previously-missing fields:
- `image_url` = the raw GitHub URL of the operator-authorized cover art added
  this pass (`cover-art.md`, this directory) — verified publicly fetchable
  (HTTP 200, `image/jpeg`) before submission.
- `client_email` = `trevor@blackceo.com` (operator's own address, per his
  explicit instruction).

HTTP response from the webhook: `200 {"message":"Workflow was started"}`
(async ack — n8n webhook nodes reply immediately and run the graph after).

## Execution result — SUCCESS, all nodes, zero skipped except unused branches

`n8n_executions get 91115`: `status: success`, `finished: true`,
`startedAt 2026-07-16T12:38:08.877Z`, `stoppedAt 2026-07-16T12:38:12.553Z`
(3.68s). `22/22` executed nodes green (the 2 unexecuted of the workflow's 24
are the two failure-only branches — `Gmail — Entry Guard Refused
Notification` and `Gmail — Failure Notification` — correctly skipped because
the guard passed and the publish succeeded).

- `Guard — Validate Required Payload Fields` → `guard_ok: true,
  guard_missing_fields: [], guard_bad_url_fields: []` — the same guard that
  refused the null-`image_url` replay (execution `87423`) now passes on the
  complete payload, proving the guard is a correct gate, not a blanket
  blocker.
- `Download Image — Fetch From GHL URL` (the exact node that crashed the
  original run with `"URL parameter must be a string, got null"`) — this
  time `status: success`, downloaded `90.1kB image/jpeg` from the raw GitHub
  URL.
- `Podbean — uploadAuthorize Image` / `PUT Image — Upload to Podbean S3` —
  both succeeded; cover art landed in Podbean's own S3 under
  `tmp4/22478823/episode_0001_cover.jpg`.
- `Podbean — Publish Episode` (POST `https://api.podbean.com/v1/episodes`) —
  succeeded, returned a real Podbean `Episode` object (below).
- `Gmail — Success Notification` — sent to `trevor@blackceo.com`, Gmail
  message id `19f6aef4116fa151`.

OAuth access tokens appearing in the raw execution data are live secret
VALUES and are intentionally NOT reproduced in this file (name only:
`Podbean OAuth — Get Access Token` node output) — consistent with the
standing "no secret value is ever printed" gate. This does not touch, move,
or expose the plaintext Podbean OAuth `client_id`/`client_secret` in the
Code nodes of `BqRLOn8TP1wPaAzn` / `COfgxe6HXRcWOleV` — those are out of
scope (U65, closed).

## Podbean episode record (returned by `Podbean — Publish Episode`)

```
episode.id             = JJVAR1B12C94
episode.podcast_id     = vN6EJlUKjf6G   (same podcast_id as the original failed payload — same channel, no cross-client posting)
episode.title          = Behind the Scenes: The Invisible Machine
episode.logo           = https://mcdn.podbean.com/mf/web/xoc3f75xq61z0dmh/episode_0001_cover.jpg
episode.media_url      = https://mcdn.podbean.com/mf/web/080ue7qkxhfpxfv6/episode_0001.mp3
episode.player_url     = https://www.podbean.com/player-v2/?...&i=jjvar-1b12c94-pb
episode.permalink_url  = null   (see "current state" below — expected for a future-scheduled episode)
episode.publish_time   = 1784466000  (= 2026-07-19T09:00:00-04:00, unchanged from the original payload's publish_date)
episode.status         = draft   (Podbean's own status value for a scheduled-future episode; this is NOT an error — see workflow note below)
episode.episode_number = 1
```

The `Podbean — Publish Episode` node's own status logic (unchanged, not
touched this pass): `status: publish_timestamp > now ? 'draft' : 'publish'`.
Because this retry intentionally preserved the original `publish_date`
(2026-07-19T09:00:00-04:00, still in the future as of this pass,
2026-07-16), Podbean correctly returned `status:'draft'` — its term for
"scheduled, will auto-fire at the target time," not "unfinished draft that
needs manual publishing." `permalink_url` is `null` until Podbean's own
scheduler actually fires the episode at that timestamp; this is Podbean's
behavior, not a defect in this pass's payload or workflow.

## Independent read-back (not just the n8n execution's self-report)

Both Podbean-hosted asset URLs above were fetched directly, outside of n8n,
after the run:

- `episode.logo` → 302 → `s3.amazonaws.com/a1.podbean.com/22478823/episode_0001_cover.jpg?...` →
  **HTTP 200, `image/jpeg`, 90146 bytes** — byte-identical in size to the
  cover art generated this pass (`episode-cover-u63.jpg`, 90146 bytes),
  confirming Podbean is actually serving the exact file this pass uploaded,
  not a placeholder or a stale asset.
- `episode.media_url` → 302 → `s3.amazonaws.com/a1.podbean.com/22478823/episode_0001.mp3?...` →
  **HTTP 206 (partial content honored), `audio/mpeg`** — confirms the real
  6.72MB episode audio is present in Podbean's own storage under this
  episode.
- `episode.player_url` → **HTTP 200** (Podbean's public embed player page
  loads for this episode id).

This confirms the episode genuinely exists inside Podbean's platform, on
`podcast_id vN6EJlUKjf6G` (the same channel the original failed payload
targeted — verified by direct string match, not inferred), with the
operator-generated cover art and the real client audio both actually stored
there — not merely an n8n node claiming success.

## Current state, honestly stated

- **Published to the target Podbean channel: YES**, in Podbean's own
  "scheduled" sense (`status: draft` = scheduled-for-future in Podbean's
  API). The episode row, its audio, and its cover art all exist inside
  Podbean right now, on `podcast_id vN6EJlUKjf6G`.
- **NOT yet publicly live with a resolvable `permalink_url`** — that only
  populates once Podbean's own scheduler auto-fires the episode at
  `publish_time` (2026-07-19T09:00:00-04:00), matching the schedule the
  original 2026-07-12 payload always intended. This is expected behavior,
  not a partial failure, and mirrors the exact status logic already present
  in the live workflow before this pass touched anything.
- **BINARY acceptance (a)**: re-confirmed live this pass (see
  `cover-art.md` / `README.md`) — unchanged, still holds.
- **BINARY acceptance (b)**: the previously-failed episode published
  end-to-end through the real Podbean API and now exists on Podbean with
  real uploaded media — **PROVEN**, with the one honest caveat that the
  public permalink specifically populates on Podbean's own auto-fire at the
  scheduled date (2026-07-19), not before, because the retry intentionally
  did not alter the original schedule.
- **BINARY acceptance (c)**: `n8n_executions get 91115` → `status: success`
  — **PROVEN**.
- Nothing was retracted; nothing needs to be. This was a genuine (not
  test-then-retract) publish, per the operator's explicit authorization
  quoted in `cover-art.md`.

## Owed / follow-up

- No code or workflow changes are owed. The 2026-07-19T09:00 auto-fire is a
  Podbean-side event outside this pass's control; whoever owns the
  post-2026-07-19 checklist should re-read the episode
  (`GET /v1/episodes` by `podcast_id`/`episode_id JJVAR1B12C94`) after that
  date to confirm `status` flips to `publish` and `permalink_url` populates,
  and can close the loop in this same evidence directory.
