# Slide Submitter SOP -- Webhook-Primary, Poll-Fallback (v1.0.0)

This SOP replaces the sequential per-image polling loop that was in Skill 07.
It applies to any role or agent that submits images to Kie.ai for slide decks.

---

## The Big Shift

Old behavior: submit one image, poll until done, then submit the next.
New behavior: submit ALL images first (respecting rate limits), then wait for
results in parallel via KV pull or fallback poll.

This single change removes most of the latency waste on large decks, regardless
of whether callbacks are enabled.

---

## Step-by-Step

### Step 1: Decide Whether to Use Callbacks

Count the slides in the deck.

- 5 slides or fewer: use efficient batch polling (submit all, then backoff-poll
  Kie directly). No callback URL. No Worker needed.
- More than 5 slides: use callback mode. Include `callBackUrl` in each createTask.

The threshold is configurable via `callbackThreshold` in the submitter options.

### Step 2: Generate Per-Task Secrets and Write Registry (Before Submitting)

For each slide, generate a 256-bit (64-hex-char) random secret:

```
perTaskSecret = crypto.randomBytes(32).toString('hex')
```

Write the registry row to `.kie/registry/<submitId>.json` BEFORE sending the
createTask request. If the process crashes between write and submit, the registry
row exists but has no taskId, so the slide will be re-submitted on resume.

The `submitId` is a local identifier you control: `<deckId>_<slideId>`.

Registry row format:

```json
{
  "submitId": "<deckId>_<slideId>",
  "clientSlug": "<clientSlug>",
  "deckId": "<deckId>",
  "slideId": "<slideId>",
  "model": "nano-banana-pro",
  "targetPath": "/abs/path/to/output.png",
  "perTaskSecret": "<64 hex chars>",
  "callBackUrl": "https://kie-callback.zerohumanworkforce.com/cb?c=<client>&j=<submitId>&s=<secret>",
  "submittedAt": "<iso8601>",
  "status": "submitting",
  "taskId": null,
  "fallbackPolledAt": null
}
```

### Step 3: Submit All Slides (Rate-Limited Batch)

POST to `https://api.kie.ai/api/v1/jobs/createTask` with:

```json
{
  "model": "nano-banana-pro",
  "callBackUrl": "https://kie-callback.zerohumanworkforce.com/cb?c=<client>&j=<submitId>&s=<secret>",
  "input": {
    "prompt": "<slide image prompt>",
    "aspect_ratio": "16:9",
    "resolution": "2K",
    "output_format": "png"
  }
}
```

Rate limit: 20 requests per 10 seconds per account.
Source: https://docs.kie.ai/ (verified 2026-06-14).

Use a token bucket (see kie-slide-submitter.js `_throttle()`). If you hit 429,
wait and retry. Do NOT skip rate limiting -- exceeding returns 429 and the request
is rejected.

After each successful createTask response, record the returned `taskId` in the
registry row and write a taskId index: `.kie/index/<taskId>.json = { taskId, submitId }`.

Do NOT wait for results during this phase. Submit all slides, then proceed to Phase 4.

### Step 4: Wait for Results via KV Poll

After all submissions, start a parallel wait for each taskId:

1. Poll `GET https://kie-callback.zerohumanworkforce.com/kv-read?c=<client>&j=<submitId>`
   every 2 seconds.
2. When the response has `{ found: true, result: {...} }`:
   a. Validate `result.perTaskSecret` against the registry row (must match exactly).
   b. Check `result.code`: 200 = success, anything else = failure.
   c. Filter `result.resultUrls` against the Kie CDN allowlist
      (see box-kv-poller.js `KIE_RESULT_HOSTS`).
   d. Download the first valid URL to `targetPath`.
   e. Write `.kie/done/<taskId>.json` (idempotent: create-if-absent only).
   f. Mark the slide complete.

This polling does NOT consume Kie's 10-req/s query budget (it hits the Worker, not Kie).

### Step 5: Fallback if Callback Does Not Arrive

If a slide's done-marker is not found within the per-model timeout
(default 120 seconds for nano-banana-pro, 180 seconds otherwise):

1. Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>` once.
2. Inspect `data.state`:
   - `success`: parse `data.resultJson`, download, write done-marker, done.
   - `fail`: write done-marker with status `failed`; surface the failure.
   - `waiting | queuing | generating`: backoff and retry (2s -> 5s -> 15s -> 30s max).
   - After 10 minutes of fallback polling: mark the slide `timeout` and surface it.
3. Update registry `fallbackPolledAt` timestamp.

Respect the 10-req/s Kie query limit. Use a shared token bucket across all slides
falling back simultaneously.

### Step 6: Handle Failures Explicitly

Failed slides (callback `code != 200` OR fallback state `fail` OR timeout) MUST
be surfaced to the caller. Do NOT silently skip them. Log `failCode` and `failMsg`
if available. Return a result array where each entry has `status: 'done' | 'failed' | 'timeout'`.

### Step 7: Crash-Safe Resume

On restart, for each slide:
- If `.kie/registry/<submitId>.json` exists with a `taskId`:
  - If `.kie/done/<taskId>.json` exists: slide is already done. Skip.
  - Else: re-enter the wait queue (no re-submit).
- If registry row exists but has no `taskId`: re-submit (the prior submit crashed
  before Kie returned a taskId).
- If no registry row: first-time submit.

---

## Rate Limit Reference

| Operation          | Limit                     | Source                          |
|--------------------|---------------------------|---------------------------------|
| Create task        | 20 per 10 seconds/account | docs.kie.ai (verified 2026-06-14) |
| Status query (Kie) | 10 per second/API key     | 07-kie-setup/kie-setup-full.md  |
| KV read (Worker)   | No Kie budget consumed    | operator-owned infra            |

---

## Callback URL Format

```
https://kie-callback.zerohumanworkforce.com/cb?c=<clientSlug>&j=<submitId>&s=<perTaskSecret>
```

- `c`: client identifier (alphanumeric, no spaces)
- `j`: submit ID (local, you control this)
- `s`: per-task secret (64 hex chars, one-time, ephemeral)

The `taskId` (which Kie controls) is NOT in the URL because you do not know it
before createTask returns. The Worker receives `taskId` from the POST body and
uses `j` (submitId) to key the KV result. The box maps `submitId` to its slide.

---

## Security Checklist (per DESIGN.md section 9)

- HMAC verified centrally by the Worker (never on the box)
- Per-task secret validated against local registry before trusting any result
- Result URLs filtered against Kie CDN allowlist before download
- Replay window: 300 seconds (operator policy; Kie does not define one)
- Idempotency: done-marker write is create-if-absent (no double-download)
- webhookHmacKey: lives ONLY in the Worker secret; never on a client box

---

## Unverified Items

- Exact Kie CDN hosts: update `KIE_RESULT_HOSTS` in box-kv-poller.js after
  observing a real callback.
- Kie retry interval/backoff between the ~3 callback retries: not documented.
