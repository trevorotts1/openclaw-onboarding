# KIE rate limit

Source: KIE docs, "Rate Limit" section (Trevor's screenshot, 2026-10-08). Quoted exactly:

> Each account is limited to 20 new generation requests per 10 seconds (≈ 100+ concurrent tasks). Enforced per account. Excess requests return HTTP 429 and are not queued. This limit is sufficient for most users. If you consistently hit 429, contact support to request an increase (reviewed carefully).

## The limits

KIE's official `kie-models` skill "Rate limits" section (fetched 2026-10-09) names two
more limits on the same key. Both are recorded in this repository at
`07-kie-setup/references/kie-official-agent-docs-digest.md` rule 9 and restated by
`07-kie-setup/references/kie-common-rules.md` rule 3.

| Call | Limit | Source |
| --- | --- | --- |
| `createTask` (new generation submit) | 20 per 10 seconds, per account | KIE docs "Rate Limit" (quote above) |
| `recordInfo` (task status poll) | 10 per second per task | KIE `kie-models` "Rate limits" (digest rule 9; common-rules rule 3) |
| discovery (`models`, `schema`, `price`, `success-rate`) | 1 per second shared | KIE `kie-models` "Rate limits" (digest rule 9; common-rules rule 3) |

## What it means for this skill

- Picture, video and lip-sync jobs run on KIE's servers, so a swarm may submit every ready job. But NEW generation submits are paced to 20 or fewer per rolling 10 seconds per KIE key, counted across all processes (the key is shared by every window and workflow).
- A 429 means the job did NOT run and is not queued. Resubmit it after a wait. Never count it as submitted and never drop it silently.
- Status polls through `recordInfo` are capped at 10 per second per task. Never poll one task faster than 10 times a second.
- Discovery reads (`models`, `schema`, `price`, `success-rate`) share ONE budget of 1 request per second across the whole key. Cache a discovery result instead of re-reading it.
- About 100+ tasks can be in flight at once.
