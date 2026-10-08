# KIE rate limit

Source: KIE docs, "Rate Limit" section (Trevor's screenshot, 2026-10-08). Quoted exactly:

> Each account is limited to 20 new generation requests per 10 seconds (≈ 100+ concurrent tasks). Enforced per account. Excess requests return HTTP 429 and are not queued. This limit is sufficient for most users. If you consistently hit 429, contact support to request an increase (reviewed carefully).

## What it means for this skill

- Picture, video and lip-sync jobs run on KIE's servers, so a swarm may submit every ready job. But NEW generation submits are paced to 20 or fewer per rolling 10 seconds per KIE key, counted across all processes (the key is shared by every window and workflow).
- A 429 means the job did NOT run and is not queued. Resubmit it after a wait. Never count it as submitted and never drop it silently.
- Status polls are not named in the limit. Do not count them against the 20.
- About 100+ tasks can be in flight at once.
